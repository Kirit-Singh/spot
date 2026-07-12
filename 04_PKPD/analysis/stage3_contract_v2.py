"""The Stage-3 drug-annotation CONTRACT, restated and verified from the bytes.

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
from typing import Any

from .firewall import Rejection
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
