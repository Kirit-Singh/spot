"""The Stage-3 drug-annotation consumer (spot.stage34_annotation_adapter.v1).

Stage 3 retired its promotion lattice outright. `namespace`, `production_candidate`,
`production_promotion_eligible`, `may_write_production_pointer`, `stage3_eligible`,
`stage4_eligible`, `annotation_only`, `research_pk_annotation_eligible` and the whole
`eligibility.py` module are GONE — not deprecated, deleted. `spot.stage03_research_annotation.v1`
is not emitted any more and `load()` no longer takes `namespace=`.

Stage 4's previous research adapter was written against that retired contract. It has been
deleted, not adapted: an adapter that still believed in `namespace=research_only` and
`research_pk_annotation_eligible` would be reading fields no producer writes.

What Stage 3 emits now:

    schema_version           spot.stage03_drug_annotation.v1
    artifact_class           analysis   (the only real class; `fixture` never reaches Stage 4)
    stage4_assessment_status queued | not_queued   (+ a compact reason code)

`stage4_assessment_status = queued` is the ONLY admission signal, and it is not a promotion
signal. Stage 3 says so in the document itself:

    "a stage-4 assessment computes PK/safety properties; it is not biological promotion and
     not a recommendation"

WHAT IS VERIFIED before a single row is believed — recomputed from the bytes, never read back:

  1. `schema_version == spot.stage03_drug_annotation.v1` and `artifact_class == analysis`;
  2. no RETIRED key anywhere in the document, at any depth — including set to `false`, because
     the point of a relabel is to ADD the field;
  3. `manifest_sha256` recomputed from the manifest's own content;
  4. `document_sha256` recomputed from the document's own content;
  5. `canonical_content_sha256` re-derived by restating Stage-3's canonical composition, and
     `bundle_id` re-derived from it;
  6. every table's content hash recomputed from the parquet ROWS;
  7. every file's sha256 recomputed against the manifest;
  8. no production-pointer file, under any of its names.

Imports nothing from Stage 3. A verifier that imported Stage 3's hasher would let a bug or a
tamper in Stage 3 validate itself.

WHAT IS CARRIED THROUGH UNCHANGED, and must never be collapsed:

  * `arm_evidence_states` — one entry per (desired_arm, origin_type). Stage 4 computes NO
    combined rank, NO headline arm, NO cross-arm objective. There is no field to hold one.
  * `inverse_direction_hypothesis_arms` + `inverse_direction_support` — a LABELLED HYPOTHESIS.
    Never reported as observed gain of function. `stage3_evidence_classes` is an UNORDERED
    label set, not a tier.
  * `claude_science_review_status` — an inverse hypothesis is PENDING a Claude Science
    plausibility review. Stage 4 must not treat it as reviewed.
  * `origin_type` — a `pathway_node` result may NEVER be reported as a measured one.
  * science-evidence refs `{science_evidence_id, science_evidence_sha256, record_type}` —
    carried verbatim as typed REFERENCES. Stage 4 never dereferences, embeds or summarises
    them: an interpretation is not a computation, and an un-hashed blob cannot be attributed.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from .contracts import (
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
from .stage3_contract import content_hash, table_hash

ADAPTER_ID = "spot.stage34_annotation_adapter.v1"
ADAPTER_VERSION = "1.0.0"

# The exact Stage-3 contract this restatement was written against. Bump ONLY after re-reading
# the Stage-3 handoff and re-verifying the pinned bundle.
STAGE3_CONTRACT_VERSION = "spot.stage03_drug_annotation.v1/2026-07-12-r5"

ANNOTATION_SCHEMA = "spot.stage03_drug_annotation.v1"
ANNOTATION_DOC = "drug_annotation.json"
MANIFEST_SCHEMA = "spot.stage03_manifest.v1"
BUNDLE_ID_PREFIX = "s3_"

# The ONLY artifact class Stage 4 may assess. A `fixture` bundle is synthetic and never
# reaches Stage 4 no matter how good its evidence looks.
ANALYSIS_CLASS = "analysis"

QUEUED = "queued"

# Retired by Stage 3, and structurally refused here. Even `false` is a refusal: a relabel
# attack ADDS the field, and a consumer that tolerates it invites one back.
RETIRED_KEYS = frozenset({
    "namespace", "production_candidate", "production_promotion_eligible",
    "may_write_production_pointer", "production_pointer_written", "production_eligible",
    "research_pk_annotation_eligible", "research_annotation_eligible",
    "research_direction_evaluable", "stage3_eligible", "stage4_eligible",
    "annotation_only", "eligibility",
})

POINTER_FILES = ("production_pointer.json", "current.json", "PRODUCTION_POINTER.json")

# Restated from Stage-3's `bundle.CANDIDATE_CONTENT_KEYS`, in order.
CANDIDATE_CONTENT_KEYS = (
    "candidate_id", "active_moiety_id", "identity_status", "identity_conflicts",
    "arm_evidence_states", "observed_perturbation_arms",
    "inverse_direction_hypothesis_arms", "inverse_direction_support",
    "pathway_hypothesis_arms", "opposed_arms", "stage3_evidence_classes",
    "claude_science_review_status", "form_ids", "target_ensembls", "n_edges",
    "n_direct_gene_edges", "development_state_aggregate", "n_potency_rows",
    "potency_state", "stage4_assessment_status", "stage4_assessment_reason",
    "source_record_ids",
)

# Restated from Stage-3's `bundle.canonical_content`, key for key, in order.
CANONICAL_CONTENT_KEYS = (
    "schema_version", "artifact_class", "upstream", "acquisition", "pathway_hypotheses",
    "stage2_joint_context", "method", "deferred_lanes", "table_hashes", "candidates",
)

# Excluded from CONTENT hashes (still covered by the file hash).
DISPLAY_COLUMNS = frozenset({"preferred_name", "target_symbol"})

# table -> content-hash sort keys. Restated from Stage-3's `artifacts.TABLES`.
READ_TABLES: dict[str, tuple[str, ...]] = {
    "candidates": ("candidate_id",),
    "active_moieties": ("active_moiety_id",),
    "drug_forms": ("form_id",),
    "drug_identifiers": ("form_id", "id_type", "id_value", "source_record_id"),
    "source_records": ("source_record_id",),
    "dispositions": ("disposition_id",),
    "drug_mapping": ("target_ensembl", "desired_arm"),
    "candidate_arm_summaries": ("candidate_id", "desired_arm"),
    "target_drug_edges": ("edge_id",),
    "pathway_nodes": ("pathway_node_id",),
    "pathways": ("pathway_id",),
}

# A science-evidence reference is a typed pointer. Never an object, never a string.
SCIENCE_REF_KEYS = ("science_evidence_id", "science_evidence_sha256", "record_type")

_ID_TYPE_TO_FIELD = {"chembl_id": "chembl_id", "pubchem_cid": "pubchem_cid",
                     "rxcui": "rxcui", "drugbank_id": "drugbank_id"}

ACQUISITION_STATUSES = ("acquired_public", "synthetic_fixture", "not_acquired")


@dataclass
class ArmEvidence:
    """One (desired_arm, origin_type) cell. The arms are never merged."""

    desired_arm: str
    origin_type: str
    arm_evidence_state: str
    raw: dict[str, Any]


@dataclass
class QueuedCandidate:
    """What Stage 3 queued, carried through without collapse."""

    candidate_id: str
    active_moiety_id: str
    stage4_assessment_reason: str
    arm_evidence_states: list[ArmEvidence]
    observed_perturbation_arms: list[str]
    inverse_direction_hypothesis_arms: list[str]
    inverse_direction_support: list[dict[str, Any]]
    pathway_hypothesis_arms: list[str]
    opposed_arms: list[str]
    stage3_evidence_classes: list[str]
    claude_science_review_status: str
    potency_state: str
    science_evidence_refs: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AnnotationAdmission:
    bundle_id: str
    bundle_dir: str
    schema_version: str
    artifact_class: str
    document_sha256: str
    canonical_content_sha256: str
    manifest_sha256: str
    data_status: str
    n_candidates_in_bundle: int
    admitted_as_candidates: int
    not_queued: int
    candidate_set: Optional[Stage3DrugCandidateSet]
    queued: list[QueuedCandidate] = field(default_factory=list)
    not_queued_reasons: dict[str, str] = field(default_factory=dict)
    source_records: dict[str, SourceRecord] = field(default_factory=dict)
    refusal_reason: Optional[str] = None


# ------------------------------------------------------------------------------ bytes


def _read_json(path: str) -> dict[str, Any]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _cell(value: Any) -> Any:
    """One parquet cell, back to the value Stage 3 hashed.

    Stage-3 canonical content carries NO floats by construction — every magnitude is an exact
    source string plus a canonical decimal string, so that 4.0e-7 M and 4.9e-7 M can never
    collide. A float coming OUT of the parquet is therefore not a magnitude: it is pandas
    having widened a nullable integer column to float64 to make room for the nulls. Narrowing
    it back is the exact inverse. A NON-INTEGRAL float would mean a real float reached Stage-3
    content, which the contract forbids — that is a rejection, not a rounding decision.
    """
    import math

    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, (list, tuple)):
        return [_cell(v) for v in value]
    if isinstance(value, dict):
        return {k: _cell(v) for k, v in value.items()}
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        if not value.is_integer():
            raise Rejection(
                "stage3_contract_mismatch",
                f"a non-integral float ({value!r}) appears in a Stage-3 content column. "
                "Stage-3 content carries exact decimal strings, never floats.")
        return int(value)
    if isinstance(value, int):
        return int(value)
    return value


def _rows(bundle_dir: str, table: str) -> list[dict[str, Any]]:
    import pyarrow.parquet as pq

    path = os.path.join(bundle_dir, f"{table}.parquet")
    if not os.path.exists(path):
        raise Rejection("stage3_table_missing",
                        f"the bundle has no {table}.parquet; Stage 4 cannot reconstruct what "
                        "it cannot read")
    return [{k: _cell(v) for k, v in row.items()}
            for row in pq.read_table(path).to_pylist()]


def _find_retired(node: Any, path: str, hits: list[str]) -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k in RETIRED_KEYS:
                hits.append(f"{path}.{k}")
            _find_retired(v, f"{path}.{k}", hits)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _find_retired(v, f"{path}[{i}]", hits)


# ----------------------------------------------------------------------- verification


def verify_annotation_bundle(bundle_dir: str) -> tuple[dict[str, Any], dict[str, list[dict]]]:
    """Independently establish that this bundle is what it says it is. -> (document, tables)."""
    if not os.path.isdir(bundle_dir):
        raise Rejection("stage3_bundle_missing",
                        f"no Stage-3 bundle directory at {bundle_dir!r}")

    doc_path = os.path.join(bundle_dir, ANNOTATION_DOC)
    man_path = os.path.join(bundle_dir, "manifest.json")
    for p in (doc_path, man_path):
        if not os.path.exists(p):
            raise Rejection(
                "stage3_bundle_incomplete",
                f"the bundle is missing {os.path.basename(p)}. Stage 4 reads "
                f"{ANNOTATION_SCHEMA!r}; a bundle without {ANNOTATION_DOC!r} is either a "
                "retired contract or not a Stage-3 bundle at all.")

    doc = _read_json(doc_path)
    manifest = _read_json(man_path)

    # 1. the schema id is the gate. A retired contract is refused here, by name.
    if doc.get("schema_version") != ANNOTATION_SCHEMA:
        raise Rejection(
            "stage3_schema_unsupported",
            f"Stage 4 consumes {ANNOTATION_SCHEMA!r}. This document declares "
            f"{doc.get('schema_version')!r}. Stage 4 does not widen to absorb whatever "
            "arrives, and it does not read retired contracts.")
    if manifest.get("schema_version") != MANIFEST_SCHEMA:
        raise Rejection("stage3_manifest_mismatch",
                        f"manifest schema is {manifest.get('schema_version')!r}")

    # 2. artifact_class. `fixture` never reaches Stage 4, however good its evidence looks.
    for where, obj in (("document", doc), ("manifest", manifest)):
        if obj.get("artifact_class") != ANALYSIS_CLASS:
            raise Rejection(
                "stage3_artifact_class_refused",
                f"the {where} declares artifact_class={obj.get('artifact_class')!r}. Stage 4 "
                f"assesses {ANALYSIS_CLASS!r} only — a fixture is synthetic and never reaches "
                "Stage 4 regardless of how good its evidence looks.")

    # 3. retired vocabulary, at any depth, even set to false
    hits: list[str] = []
    _find_retired(doc, "$", hits)
    _find_retired(manifest, "$", hits)
    if hits:
        raise Rejection(
            "stage3_retired_key_present",
            f"a retired promotion field is present at {sorted(hits)}. Stage 3 deleted these; "
            "even setting one to false is a refusal, because the point of a relabel is to add "
            "the field.")

    for name in POINTER_FILES:
        if os.path.exists(os.path.join(bundle_dir, name)):
            raise Rejection("stage3_carries_a_production_pointer",
                            f"the bundle contains {name!r}")

    # 4. manifest self-hash
    want = content_hash({k: v for k, v in manifest.items()
                         if k not in ("manifest_sha256", "created_at")})
    if manifest.get("manifest_sha256") != want:
        raise Rejection("stage3_manifest_hash_mismatch",
                        f"manifest_sha256 declared {manifest.get('manifest_sha256')!r}, "
                        f"recomputed {want!r}")

    # 5. document self-hash — transitively binds every candidate row and every table hash
    want = content_hash({k: v for k, v in doc.items() if k != "document_sha256"})
    if doc.get("document_sha256") != want:
        raise Rejection(
            "stage3_document_hash_mismatch",
            f"document_sha256 declared {doc.get('document_sha256')!r}, recomputed {want!r}. "
            "The rows in this document are not the rows Stage 3 signed.")

    # 6. canonical content + the bundle id derived from it
    try:
        canonical = {
            "schema_version": doc["schema_version"],
            "artifact_class": doc["artifact_class"],
            "upstream": doc["upstream"],
            "acquisition": doc["acquisition"],
            "pathway_hypotheses": doc["pathway_hypotheses"],
            "stage2_joint_context": doc["stage2_joint_context"],
            "method": doc["method"],
            "deferred_lanes": dict(sorted(doc["deferred_lanes"].items())),
            "table_hashes": dict(sorted(doc["table_hashes"].items())),
            "candidates": [{k: c[k] for k in CANDIDATE_CONTENT_KEYS}
                           for c in doc["candidates"]],
        }
    except KeyError as exc:
        raise Rejection(
            "stage3_contract_mismatch",
            f"the Stage-3 contract Stage 4 restates ({STAGE3_CONTRACT_VERSION}) does not match "
            f"this document: missing {exc}. Re-read the Stage-3 handoff before widening this "
            "adapter.") from exc

    assert tuple(canonical) == CANONICAL_CONTENT_KEYS
    recomputed = content_hash(canonical)
    if doc.get("canonical_content_sha256") != recomputed:
        raise Rejection(
            "stage3_canonical_content_mismatch",
            f"canonical_content_sha256 declared {doc.get('canonical_content_sha256')!r}, "
            f"recomputed {recomputed!r} from the document's own content.")

    want_id = BUNDLE_ID_PREFIX + recomputed[:16]
    if doc.get("bundle_id") != want_id or manifest.get("bundle_id") != want_id:
        raise Rejection("stage3_bundle_id_mismatch",
                        f"bundle_id is {doc.get('bundle_id')!r}; the content it commits to "
                        f"derives {want_id!r}")

    # 7. the parquet ROWS are the rows Stage 3 hashed
    tables: dict[str, list[dict]] = {}
    declared = doc["table_hashes"]
    for table, sort_keys in READ_TABLES.items():
        rows = _rows(bundle_dir, table)
        tables[table] = rows
        if table not in declared:
            raise Rejection("stage3_contract_mismatch",
                            f"the document declares no table hash for {table!r}")
        if not rows:
            continue
        cols = [c for c in rows[0] if c not in DISPLAY_COLUMNS]
        keys = tuple(k for k in sort_keys if k in cols) or (cols[0],)
        got = table_hash([{c: r.get(c) for c in cols} for r in rows], keys)
        if got != declared[table]:
            raise Rejection(
                "stage3_table_content_hash_mismatch",
                f"{table}.parquet: the content hash recomputed from the actual rows ({got}) is "
                f"not the one the document declares ({declared[table]}). The rows on disk are "
                "not the rows Stage 3 hashed.")

    # 8. every file is the file the manifest signed
    for entry in manifest.get("files", []):
        path = os.path.join(bundle_dir, entry["file"])
        if not os.path.exists(path):
            raise Rejection("stage3_bundle_incomplete",
                            f"the manifest lists {entry['file']!r}, which is not in the bundle")
        actual = sha256_file(path)
        if actual != entry["file_sha256"]:
            raise Rejection("stage3_file_hash_mismatch",
                            f"{entry['file']}: sha256 on disk is {actual}, the manifest signed "
                            f"{entry['file_sha256']}")

    return doc, tables


# --------------------------------------------------------------------------- admission


def _science_refs(tables: dict[str, list[dict]]) -> list[dict[str, Any]]:
    """Typed science-evidence REFERENCES, carried verbatim. Never dereferenced or embedded.

    Stage 3 refuses a free-form object or string in their place: an interpretation is not a
    computation, and an un-hashed blob cannot be verified or attributed. Stage 4 keeps them a
    reference too — it does not read the record, summarise it, or let it stand in for
    programmatic evidence.
    """
    refs: list[dict[str, Any]] = []
    for table in ("pathway_nodes", "pathways"):
        for row in tables.get(table, []):
            for ref in (row.get("science_evidence_ids") or []):
                if not isinstance(ref, dict) or set(SCIENCE_REF_KEYS) - set(ref):
                    raise Rejection(
                        "stage3_science_ref_untyped",
                        f"{table}: a science-evidence reference must be a typed "
                        f"{list(SCIENCE_REF_KEYS)} record, not {type(ref).__name__}. An "
                        "un-hashed blob cannot be verified or attributed.")
                refs.append({k: ref[k] for k in SCIENCE_REF_KEYS})
    refs.sort(key=lambda r: (r["science_evidence_id"], r["record_type"]))
    return refs


def _source_records(rows: list[dict[str, Any]], access_date: str) -> dict[str, SourceRecord]:
    """Stage-3's classes, carried across VERBATIM. `not_acquired` stays `not_acquired`."""
    out: dict[str, SourceRecord] = {}
    for r in rows:
        status = r.get("acquisition_status")
        if status not in ACQUISITION_STATUSES:
            raise Rejection(
                "stage3_unknown_acquisition_status",
                f"source record declares acquisition_status={status!r}, which Stage 4 does not "
                f"recognise. Known: {list(ACQUISITION_STATUSES)}. Stage 4 refuses rather than "
                "guessing whether bytes exist behind a row.")
        out[r["source_record_id"]] = SourceRecord(
            source_record_id=r["source_record_id"],
            source_type="public_api",
            source_name=f"Stage-3 {r.get('source')} ({r.get('adapter')})",
            acquisition_status=status,
            access_date=access_date,
            url=r.get("retrieval_url"),
            record_id=r.get("source_record_id"),
            release_version=r.get("source_release"),
            license=r.get("license"),
            raw_sha256=r.get("raw_sha256"),
            raw_bytes=r.get("raw_bytes"),
            raw_media_type=r.get("raw_media_type"),
        )
    return out


def _access_date(doc: dict[str, Any]) -> str:
    acq = doc.get("acquisition") or {}
    for key in ("acquired_at", "access_date", "acquisition_date"):
        v = acq.get(key)
        if isinstance(v, str) and len(v) >= 10:
            return v[:10]
    return "1970-01-01"


def adapt_annotation_bundle(bundle_dir: str) -> AnnotationAdmission:
    """Verify, then admit ONLY the rows Stage 3 queued for a Stage-4 assessment."""
    doc, tables = verify_annotation_bundle(bundle_dir)

    candidates = tables["candidates"]
    moieties = {m["active_moiety_id"]: m for m in tables["active_moieties"]}
    forms_by_moiety: dict[str, list[dict]] = {}
    for f in tables["drug_forms"]:
        forms_by_moiety.setdefault(f["active_moiety_id"], []).append(f)
    ids_by_form: dict[str, list[dict]] = {}
    for i in tables["drug_identifiers"]:
        ids_by_form.setdefault(i["form_id"], []).append(i)

    science = _science_refs(tables)

    queued = [c for c in candidates if c.get("stage4_assessment_status") == QUEUED]
    not_queued = {c["candidate_id"]: c.get("stage4_assessment_reason") or "not_queued"
                  for c in candidates if c.get("stage4_assessment_status") != QUEUED}

    carried: list[QueuedCandidate] = []
    for c in sorted(queued, key=lambda r: r["candidate_id"]):
        arms = [
            ArmEvidence(desired_arm=a["desired_arm"], origin_type=a["origin_type"],
                        arm_evidence_state=a["arm_evidence_state"], raw=dict(a))
            for a in sorted(c.get("arm_evidence_states") or [],
                            key=lambda a: (a["desired_arm"], a["origin_type"]))
        ]
        carried.append(QueuedCandidate(
            candidate_id=c["candidate_id"],
            active_moiety_id=c["active_moiety_id"],
            stage4_assessment_reason=c.get("stage4_assessment_reason") or "",
            arm_evidence_states=arms,
            observed_perturbation_arms=list(c.get("observed_perturbation_arms") or []),
            inverse_direction_hypothesis_arms=list(
                c.get("inverse_direction_hypothesis_arms") or []),
            inverse_direction_support=[dict(s) for s in
                                       (c.get("inverse_direction_support") or [])],
            pathway_hypothesis_arms=list(c.get("pathway_hypothesis_arms") or []),
            opposed_arms=list(c.get("opposed_arms") or []),
            stage3_evidence_classes=list(c.get("stage3_evidence_classes") or []),
            claude_science_review_status=c.get("claude_science_review_status") or "not_required",
            potency_state=c.get("potency_state") or "not_evaluated",
            science_evidence_refs=science,
        ))

    admission = AnnotationAdmission(
        bundle_id=doc["bundle_id"],
        bundle_dir=os.path.abspath(bundle_dir),
        schema_version=doc["schema_version"],
        artifact_class=doc["artifact_class"],
        document_sha256=doc["document_sha256"],
        canonical_content_sha256=doc["canonical_content_sha256"],
        manifest_sha256=_read_json(os.path.join(bundle_dir, "manifest.json"))["manifest_sha256"],
        data_status=doc.get("data_status", "unknown"),
        n_candidates_in_bundle=len(candidates),
        admitted_as_candidates=len(queued),
        not_queued=len(not_queued),
        candidate_set=None,
        queued=carried,
        not_queued_reasons=not_queued,
        source_records=_source_records(tables["source_records"], _access_date(doc)),
    )

    if not queued:
        admission.refusal_reason = (
            "no candidate in this bundle has stage4_assessment_status=queued. Stage 4 assesses "
            "only what Stage 3 queued; it does not queue rows itself.")
        return admission

    built: list[Stage3Candidate] = []
    for q in carried:
        m = moieties.get(q.active_moiety_id)
        if m is None:
            raise Rejection("stage3_dangling_moiety",
                            f"candidate {q.candidate_id!r} names active moiety "
                            f"{q.active_moiety_id!r}, which has no row")
        if m.get("identity_status") != "resolved":
            raise Rejection(
                "stage3_unresolved_moiety",
                f"candidate {q.candidate_id!r} has identity_status="
                f"{m.get('identity_status')!r}. An unresolved molecule cannot be PK-assessed, "
                "and Stage 4 will not guess which one it is.")

        forms = sorted(forms_by_moiety.get(q.active_moiety_id, []),
                       key=lambda f: f["form_id"])
        parent = next((f for f in forms if f.get("form_class") == "parent"), None) or (
            forms[0] if forms else {})

        compound: dict[str, Any] = {}
        for f in forms:
            for i in ids_by_form.get(f["form_id"], []):
                key = _ID_TYPE_TO_FIELD.get(str(i.get("id_type") or ""))
                if key and not compound.get(key):
                    compound[key] = i.get("id_value")
        if not compound.get("chembl_id") and m.get("moiety_chembl_id"):
            compound["chembl_id"] = m["moiety_chembl_id"]

        src = next((c for c in candidates if c["candidate_id"] == q.candidate_id), {})
        built.append(Stage3Candidate(
            candidate_id=q.candidate_id,
            namespace=Namespace.RESEARCH_ONLY,
            active_moiety=ActiveMoiety(
                active_moiety_id=q.active_moiety_id,
                active_moiety_name=m.get("preferred_name") or q.active_moiety_id,
                unii=m.get("moiety_unii"),
                inchikey=m.get("moiety_inchikey"),
                administered_form="active_moiety",
                administered_form_name=parent.get("preferred_name"),
                maps_to_active_moiety_id=q.active_moiety_id,
                mapping_source_record_id=(src.get("source_record_ids") or [None])[0],
            ),
            compound_ids=CompoundIds(**compound),
            target=", ".join(src.get("target_ensembls") or []) or "unspecified",
            mechanism=q.stage4_assessment_reason or "unspecified",
            # NO single direction, in ANY field. `away_from_A` and `toward_B` are independent
            # hypotheses with their own evidence states per origin_type; collapsing them into
            # one program direction, one drug-effect direction or one compatibility would BE
            # the cross-arm objective Stage 3 forbids, and would silently privilege whichever
            # arm happened to be listed first. The per-arm states travel intact on `queued`.
            program_direction="unspecified",
            drug_effect_direction="unspecified",
            direction_compatibility=DirectionCompatibility.UNKNOWN,
            stage3_evidence_source_record_ids=list(src.get("source_record_ids") or []),
        ))

    admission.candidate_set = Stage3DrugCandidateSet(
        # Stage-4's INTERNAL normalized form. The Stage-3 wire schema is on the binding below.
        schema_id="spot.stage03_drug_candidate_set.v1",
        stage3_run_id=doc["upstream"].get("direct_run_id") or doc["bundle_id"],
        candidate_set_id=doc["bundle_id"],
        candidate_rows_sha256=compute_candidate_rows_sha256(built),
        # Stage 3 retired `namespace`. Stage 4 keeps its OWN internal namespace enum and pins
        # every Stage-3 assessment to the non-promotable lane: a Stage-4 assessment is not
        # biological promotion, and there is no Stage-3 field that could say otherwise.
        namespace=Namespace.RESEARCH_ONLY,
        is_fixture=False,
        stage3_method_version=str((doc.get("method") or {}).get("stage3_method_version")
                                  or STAGE3_CONTRACT_VERSION),
        candidates=built,
        stage3_binding=Stage3Binding(
            stage3_schema_version=doc["schema_version"],
            stage3_document_id=doc["bundle_id"],
            stage3_namespace=Namespace.RESEARCH_ONLY,
            canonical_content_sha256=doc["canonical_content_sha256"],
            document_sha256=doc["document_sha256"],
            table_hashes=dict(sorted(doc["table_hashes"].items())),
            stage3_method={k: str(v) for k, v in (doc.get("method") or {}).items()
                           if isinstance(v, (str, int, float, bool))},
            stage3_upstream={k: str(v) for k, v in (doc.get("upstream") or {}).items()
                             if isinstance(v, (str, int, float, bool))},
            stage3_source_status={
                "n_source_records": len(tables["source_records"]),
                "n_acquired_public": sum(1 for r in tables["source_records"]
                                         if r.get("acquisition_status") == "acquired_public"),
                "n_not_acquired": sum(1 for r in tables["source_records"]
                                      if r.get("acquisition_status") != "acquired_public"),
            },
            stage3_eligible=False,
            stage4_eligible=True,
            production_candidate=False,
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
        ),
    )
    return admission
