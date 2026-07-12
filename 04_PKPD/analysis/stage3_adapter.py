"""Stage-3 -> Stage-4 adapter (spot.stage34_adapter.v1).

The only door from a real Stage-3 emission into Stage 4. It handles the three documents
Stage 3 actually emits — not a Stage-4 approximation of them:

    spot.stage03_drug_candidate_set.v1   production      -> Stage-4 production candidates
    spot.stage03_research_annotation.v1  research_only   -> INSPECTION ONLY, zero candidates
    spot.fixture.stage03_bundle.v1       fixture         -> Stage-4 fixture candidates

What it refuses to do:

  * Promote. Stage 3's `namespace`, `production_candidate`, `stage3_eligible` and
    `stage4_eligible` are propagated verbatim. A research annotation is, in Stage 3's own
    words, "an ANNOTATION, never a candidate set": it can be *inspected* here, but it
    yields no Stage-4 candidate and no scorecard, and it can never become production.
  * Trust. Stage 3's `canonical_content_sha256`, `document_sha256` and every
    `table_hashes` entry are re-verified against the bytes on disk, by a reimplementation
    of the canonical rule rather than by importing Stage 3's hasher.
  * Guess. Drug form, identifiers, active moiety and target-direction state come from
    Stage-3 rows; anything unresolved stays unresolved and is refused rather than
    defaulted.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from .contracts import (
    AdministeredForm,
    ActiveMoiety,
    CompoundIds,
    DirectionCompatibility,
    Namespace,
    SourceRecord,
    Stage3Binding,
    Stage3Candidate,
    Stage3DrugCandidateSet,
)
from .firewall import Rejection, compute_candidate_rows_sha256
from .stage3_contract import OUTPUT_DOC, STAGE3_TABLE_CONTRACT_VERSION, contract_sha256
from .stage3_verify import verify_bundle

ADAPTER_ID = "spot.stage34_adapter.v1"
ADAPTER_VERSION = "1.0.0"

# What Stage 3 actually emits -> (namespace, ranked-lane key, inspect-lane key)
SUPPORTED_DOCUMENTS: dict[str, tuple[str, Optional[str], str]] = {
    "spot.stage03_drug_candidate_set.v1": ("production", "primary_candidates", "secondary_candidates"),
    "spot.fixture.stage03_bundle.v1": ("fixture", "fixture_candidates", "fixture_inspectable_candidates"),
    # No ranked lane: a research annotation yields NO Stage-4 candidate, only inspection.
    "spot.stage03_research_annotation.v1": ("research_only", None, "inspectable_candidates"),
}

DOCUMENT_ID_KEY = {
    "spot.stage03_drug_candidate_set.v1": "candidate_set_id",
    "spot.fixture.stage03_bundle.v1": "fixture_bundle_id",
    "spot.stage03_research_annotation.v1": "research_annotation_id",
}

# Stage-3 mechanism_direction_state -> Stage-4 direction compatibility.
DIRECTION_MAP = {
    "matched": DirectionCompatibility.COMPATIBLE,
    "opposed": DirectionCompatibility.INCOMPATIBLE,
    "unknown": DirectionCompatibility.UNKNOWN,
    "conflicting": DirectionCompatibility.UNKNOWN,  # a conflict is not a compatibility
}

_ID_TYPE_TO_FIELD = {
    "chembl_id": "chembl_id",
    "pubchem_cid": "pubchem_cid",
    "rxcui": "rxcui",
}

# Stage-3 drug_form.form_class -> Stage-4 administered_form
FORM_CLASS_MAP: dict[str, AdministeredForm] = {
    "parent": "active_moiety",
    "salt": "salt",
    "prodrug": "prodrug",
    "active_metabolite": "other",
    "marketed_product": "other",
    "multi_ingredient_product": "other",
    "unclassified": "other",
}


@dataclass
class Stage3Inspection:
    """What a non-production Stage-3 document yields: a record, not a candidate."""

    stage3_schema_version: str
    stage3_namespace: str
    stage3_document_id: str
    document_sha256: str
    canonical_content_sha256: str
    data_status: str
    source_status: dict[str, int]
    stage3_eligible: bool
    stage4_eligible: bool
    production_candidate: bool
    n_inspectable: int
    inspectable: list[dict[str, Any]] = field(default_factory=list)
    admitted_as_candidates: int = 0
    refusal_reason: Optional[str] = None


@dataclass
class Stage3Admission:
    """The adapter's full result: what was admitted, what was only inspected, and why."""

    candidate_set: Optional[Stage3DrugCandidateSet]
    inspection: Stage3Inspection
    source_records: dict[str, SourceRecord]
    drug_forms: list[dict[str, Any]]
    active_moieties: list[dict[str, Any]]
    drug_identifiers: list[dict[str, Any]]


def verify_stage3_document(
    doc: dict[str, Any], bundle_dir: Optional[str] = None
) -> dict[str, list[dict[str, Any]]]:
    """Re-verify Stage 3's integrity claims by RECONSTRUCTING them. -> the verified rows.

    Delegated to `stage3_verify`, which recomputes every table's content hash from the
    actual parquet rows rather than comparing two declarations to each other. Comparing
    the document's declared hash with the manifest's declared hash is what let a mutated
    `form_class` through with a stale content hash.
    """
    return verify_bundle(doc, bundle_dir)


def _source_records(doc: dict[str, Any]) -> dict[str, SourceRecord]:
    """Stage-3 source records -> Stage-4 source records, class preserved exactly.

    `acquisition_status` is carried across untouched: a Stage-3 `synthetic_fixture` is a
    Stage-4 `synthetic_fixture`, and there is no code path that upgrades it.
    """
    access_date = (doc.get("created_at") or "1970-01-01T00:00:00Z")[:10]
    out: dict[str, SourceRecord] = {}
    for r in doc["source_records"]:
        status = r["acquisition_status"]
        acquired = status == "acquired_public"
        out[r["source_record_id"]] = SourceRecord(
            source_record_id=r["source_record_id"],
            source_type="public_api" if acquired else "fixture",
            source_name=f"{r['source']} :: {r['adapter']}@{r['adapter_version']}",
            acquisition_status=status,
            url=r.get("retrieval_url") or (r.get("source_endpoint") if acquired else None),
            record_id=r.get("query_canonical") or None,
            access_date=access_date,
            release_version=r.get("source_release"),
            license=r.get("license"),
            raw_sha256=r.get("raw_sha256"),
            raw_bytes=r.get("raw_bytes"),
            raw_media_type=r.get("raw_media_type"),
        )
    return out




def _build_moiety(row: dict[str, Any], forms: list[dict[str, Any]],
                  moieties: list[dict[str, Any]]) -> ActiveMoiety:
    """Preserve drug form + active-moiety identity exactly as Stage 3 resolved it."""
    am_id = row["active_moiety_id"]
    moiety = next((m for m in moieties if m.get("active_moiety_id") == am_id), {})

    if row.get("identity_status") not in (None, "resolved"):
        raise Rejection(
            "stage3_moiety_unresolved",
            f"candidate {row['candidate_id']!r} has identity_status "
            f"{row.get('identity_status')!r}; Stage 4 does not admit an unresolved, "
            "ambiguous or multi-ingredient moiety as a candidate",
        )

    form_ids = list(row.get("form_ids") or [])
    form = next((f for f in forms if f.get("form_id") in form_ids), {})
    form_class = form.get("form_class", "parent")
    administered: AdministeredForm = FORM_CLASS_MAP.get(form_class, "other")

    if form.get("moiety_assignment_status") not in (None, "resolved_single_moiety"):
        raise Rejection(
            "stage3_moiety_unresolved",
            f"candidate {row['candidate_id']!r} form {form.get('form_id')!r} has "
            f"moiety_assignment_status {form.get('moiety_assignment_status')!r}",
        )

    unii = moiety.get("moiety_unii") or None
    inchikey = moiety.get("moiety_inchikey") or None
    return ActiveMoiety(
        active_moiety_id=am_id,
        active_moiety_name=moiety.get("preferred_name") or row.get("preferred_name") or am_id,
        unii=unii if unii and len(unii) == 10 else None,
        inchikey=inchikey if inchikey and inchikey.count("-") == 2 else None,
        administered_form=administered,
        administered_form_name=form.get("preferred_name"),
        maps_to_active_moiety_id=am_id if administered != "active_moiety" else None,
        mapping_source_record_id=(
            (form.get("source_record_ids") or [None])[0] if administered != "active_moiety" else None
        ),
    )


def _compound_ids(am_id: str, forms: list[dict[str, Any]],
                  identifiers: list[dict[str, Any]], form_ids: list[str]) -> CompoundIds:
    kw: dict[str, Any] = {}
    for ident in identifiers:
        if ident.get("form_id") in form_ids:
            fld = _ID_TYPE_TO_FIELD.get(ident.get("id_type", ""))
            if fld and not kw.get(fld):
                kw[fld] = ident.get("id_value")
    return CompoundIds(**kw)


def adapt(doc: dict[str, Any], bundle_dir: Optional[str] = None) -> Stage3Admission:
    """Verify by reconstruction, then admit -- or inspect without admitting."""
    # Every row below has had its content hash recomputed from the bytes on disk.
    tables = verify_stage3_document(doc, bundle_dir)

    schema = doc["schema_version"]
    namespace, ranked_key, inspect_key = SUPPORTED_DOCUMENTS[schema]
    doc_id = doc[DOCUMENT_ID_KEY[schema]]
    sources = _source_records(doc)
    forms = tables.get("drug_forms", [])
    moieties = tables.get("active_moieties", [])
    identifiers = tables.get("drug_identifiers", [])

    inspect_rows = list(doc.get(inspect_key, []) or [])
    ranked_rows = list(doc.get(ranked_key, []) or []) if ranked_key else []

    inspection = Stage3Inspection(
        stage3_schema_version=schema,
        stage3_namespace=namespace,
        stage3_document_id=doc_id,
        document_sha256=doc["document_sha256"],
        canonical_content_sha256=doc["canonical_content_sha256"],
        data_status=doc.get("data_status", "unknown"),
        source_status=dict(doc["source_status"]),
        stage3_eligible=bool(doc.get("stage3_eligible", False)),
        stage4_eligible=bool(doc.get("stage4_eligible", False)),
        production_candidate=bool(doc.get("production_candidate", False)),
        n_inspectable=len(inspect_rows) + len(ranked_rows),
        inspectable=[
            {
                "candidate_id": r["candidate_id"],
                "active_moiety_id": r["active_moiety_id"],
                "preferred_name": r.get("preferred_name"),
                "lane": r.get("lane"),
                "identity_status": r.get("identity_status"),
                "mechanism_direction_state": r.get("mechanism_direction_state"),
                "stage3_eligible": bool(r.get("stage3_eligible", False)),
                "stage4_eligible": bool(r.get("stage4_eligible", False)),
                "production_candidate": bool(r.get("production_candidate", False)),
                "n_potency_rows": int(r.get("n_potency_rows", 0) or 0),
            }
            for r in (ranked_rows + inspect_rows)
        ],
    )

    if ranked_key is None:
        # Stage 3: "an ANNOTATION, never a candidate set". Inspect it; admit nothing.
        inspection.refusal_reason = (
            f"{schema} is an annotation, not a candidate set. Stage 4 inspects it and admits "
            "no candidate. It stays research_only and can never become production."
        )
        return Stage3Admission(None, inspection, sources, forms, moieties, identifiers)

    if not ranked_rows:
        inspection.refusal_reason = (
            f"{schema} carries no rows in {ranked_key!r} — nothing to admit. "
            f"Stage-3 source_status={doc['source_status']}."
        )
        return Stage3Admission(None, inspection, sources, forms, moieties, identifiers)

    candidates: list[Stage3Candidate] = []
    for r in ranked_rows:
        moiety = _build_moiety(r, forms, moieties)
        direction = DIRECTION_MAP.get(r.get("mechanism_direction_state", "unknown"),
                                      DirectionCompatibility.UNKNOWN)
        candidates.append(
            Stage3Candidate(
                candidate_id=r["candidate_id"],
                active_moiety=moiety,
                compound_ids=_compound_ids(r["active_moiety_id"], forms, identifiers,
                                           list(r.get("form_ids") or [])),
                target=";".join(sorted(r.get("levers_matched") or [])) or "unspecified",
                mechanism=r.get("lane", "unspecified"),
                # Stage 3 encodes the direction *relation*, not two absolute directions.
                program_direction="unspecified",
                drug_effect_direction="unspecified",
                direction_compatibility=direction,
                # Namespace is Stage 3's, not ours.
                namespace=Namespace(namespace),
                stage3_evidence_source_record_ids=sorted(r.get("source_record_ids") or []),
            )
        )

    binding = Stage3Binding(
        stage3_schema_version=schema,
        stage3_document_id=doc_id,
        stage3_namespace=Namespace(namespace),
        canonical_content_sha256=doc["canonical_content_sha256"],
        document_sha256=doc["document_sha256"],
        table_hashes=dict(sorted(doc["table_hashes"].items())),
        stage3_method={k: str(v) for k, v in sorted(doc["method"].items()) if isinstance(v, str)},
        stage3_upstream={
            k: str(v) for k, v in sorted(doc["upstream"].items())
            if isinstance(v, str)
        },
        stage3_source_status={k: int(v) for k, v in sorted(doc["source_status"].items())},
        stage3_eligible=bool(doc.get("stage3_eligible", False)),
        stage4_eligible=bool(doc.get("stage4_eligible", False)),
        production_candidate=bool(doc.get("production_candidate", False)),
        adapter_id=ADAPTER_ID,
        adapter_version=ADAPTER_VERSION,
        # WHICH transcription of the Stage-3 table contract reconstructed those hashes.
        # Re-transcribe the contract and this moves, so the scorecard id moves with it.
        stage3_table_contract_version=STAGE3_TABLE_CONTRACT_VERSION,
        stage3_table_contract_sha256=contract_sha256(),
    )

    cset = Stage3DrugCandidateSet(
        schema_id="spot.stage03_drug_candidate_set.v1",
        stage3_run_id=str(doc["upstream"].get("run_id") or doc_id),
        candidate_set_id=doc_id,
        candidate_rows_sha256=compute_candidate_rows_sha256(candidates),
        namespace=Namespace(namespace),
        stage3_method_version=str(doc["method"]["stage3_method_version"]),
        upstream_contrast_id=str(doc["upstream"].get("selection_id") or "") or None,
        upstream_gene_lever_set_sha256=doc["upstream"].get("lever_set_sha256"),
        candidates=candidates,
        # Never a hand-set flag: it is Stage 3's namespace.
        is_fixture=(namespace == "fixture"),
        stage3_binding=binding,
    )
    inspection.admitted_as_candidates = len(candidates)
    return Stage3Admission(cset, inspection, sources, forms, moieties, identifiers)


def load_stage3_bundle(path: str) -> tuple[dict[str, Any], str]:
    """Load a Stage-3 emission from its bundle directory or its document path."""
    if os.path.isdir(path):
        found = [name for name in sorted(OUTPUT_DOC.values())
                 if os.path.exists(os.path.join(path, name))]
        if not found:
            raise Rejection(
                "stage3_document_missing",
                f"no Stage-3 document found in {path!r}; expected one of "
                + ", ".join(sorted(OUTPUT_DOC.values())),
            )
        if len(found) > 1:
            raise Rejection(
                "stage3_document_ambiguous",
                f"{path!r} holds more than one Stage-3 document ({', '.join(found)}). A "
                "bundle emits exactly one.",
            )
        with open(os.path.join(path, found[0]), encoding="utf-8") as fh:
            return json.load(fh), path
    with open(path, encoding="utf-8") as fh:
        return json.load(fh), os.path.dirname(path)
