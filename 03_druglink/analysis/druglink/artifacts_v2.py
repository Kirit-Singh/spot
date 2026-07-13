"""Atomic, content-addressed emission of the Stage-3 **v2** bundle (audit step 7).

    manifest.json          self-hashing; inventories every file by CONTENT hash and FILE hash
    <document>.json        the v2 drug-annotation document (:mod:`druglink.bundle_v2`)
    <table>.parquet        the six v2 tables (:data:`TABLES`)

The bundle is written to a staging sibling, **re-read from disk**, and only then renamed into
place. Re-reading is not ceremony: the hashes are computed from in-memory rows, and a writer
that mangled a null on the way to parquet would otherwise ship a manifest describing bytes
that are not there — and the first reader to notice would be Stage 4.

If the target id already exists with DIFFERENT bytes, the write REFUSES. Two different
sciences may never wear one identifier.

BYTES, NOT MERELY THE ID, ARE A PURE FUNCTION OF THE CONTENT
------------------------------------------------------------
The document carries no clock (``created_at`` lives in the manifest, outside its identity),
and every table is written in ONE canonical row order. So a rerun of identical science
reproduces the bundle byte for byte. Without both, a rerun would be refused as a collision —
and a refusal that says "different content" about content that is identical is worse than no
refusal, because it teaches the next reader to weaken the check.

Table identity is the row-order-invariant CONTENT hash, so permuting rows cannot change an id.
File digests are recorded too and the verifier checks both: a display-only column tampered with
in the parquet is caught by the FILE hash even though it is excluded from the content hash.

Column lists are DERIVED from :mod:`druglink.candidates_v2` and :mod:`druglink.bundle_v2`
rather than restated, so a table and the rows it holds cannot drift apart.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from typing import Any, Iterable, Mapping, Optional

import pandas as pd

from . import artifact_class as ac
from . import artifacts as v1
from . import bundle_v2 as bv2
from . import candidates_v2 as cv2
from . import pathway_context_v2 as pc2
from .bundle_v2 import (  # noqa: F401  (one front door for the v2 producer)
    GATE_COMBINED_OBJECTIVE,
    GATE_PQ_FDR,
    GATE_REPORT_BINDS_ANOTHER_MANIFEST,
    GATE_STORE_NOT_ADMITTED,
    V2_DOC,
    V2_MANIFEST_SCHEMA,
    V2_METHOD_VERSION,
    V2_SCHEMA,
    ArtifactV2Error,
    aggregate_binding,
    bind_report,
    build_document,
    check_contract,
    check_no_combined_objective,
    check_no_pq_fdr,
    method_block,
    provenance_rows,
    store_binding,
)
from .canonical_number import canonical_number  # noqa: F401  (re-exported for consumers)
from .hashing import canonical_json, content_hash, file_sha256, row_key, table_hash, without
from .stage2_aggregate import AdmittedAggregate
from .universe_rows import AdmittedStore

# THE SEVEN v2 TABLES. This set is the contract, and the verifier RESTATES it independently.
#
# `arm_slots` is not optional and is not a convenience: it carries EVERY arm slot the release
# resolved, including the ones no drug evidence reached. Without it, "this arm had no drug
# evidence" and "this arm never ran" are the same silence — and silent zero-coverage wearing a
# green check is the exact defect this project keeps finding.
#
# `source_records` carries every VERBATIM source assertion, including the ones that may never
# rank a gene (the variant-specific and ambiguous-identity lanes). A dropped assertion is
# indistinguishable from a drug nobody found.
TABLES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "arm_slots": (cv2.ARM_SLOT_COLUMNS, cv2.ARM_SLOT_KEY),
    "target_drug_edges": (cv2.EDGE_COLUMNS, cv2.EDGE_KEY),
    "pathway_context": (pc2.CONTEXT_COLUMNS, pc2.CONTEXT_KEY),
    "arm_summaries": (cv2.ARM_SUMMARY_COLUMNS, cv2.ARM_SUMMARY_KEY),
    "candidates": (cv2.CANDIDATE_COLUMNS, cv2.CANDIDATE_KEY),
    "source_records": (cv2.SOURCE_RECORD_COLUMNS, cv2.SOURCE_RECORD_KEY),
    "dispositions": (cv2.DISPOSITION_COLUMNS, cv2.DISPOSITION_KEY),
    "provenance": (bv2.PROVENANCE_COLUMNS, bv2.PROVENANCE_KEY),
}
SCIENTIFIC_TABLES = tuple(sorted(TABLES))

# Display-only: excluded from CONTENT hashes (and so from the bundle id), but still covered by
# the FILE hash. A symbol is a label; the typed identity is the identity.
DISPLAY_COLUMNS = frozenset({"preferred_name", "pref_name", "target_symbol"})

# Columns that may hold an integer OR a null. They are written as a NULLABLE integer, never as
# a float: parquet renders an int column with nulls as float64+NaN, and a consumer that calls
# int() on NaN crashes — while one that coerces it INVENTS a rank for a target that has none.
# ``variant_id = -1`` is the source's UNDEFINED MUTATION sentinel and must stay exactly -1.
NULLABLE_INT_COLUMNS = ("arm_rank", "mec_id", "variant_id")

GATE_TABLE_NOT_ON_DISK = "a_table_re_read_from_disk_is_not_the_table_that_was_hashed"
GATE_ID_COLLISION = "an_existing_bundle_with_this_id_has_different_content"


# --------------------------------------------------------------------------- #
# Tables: encoding, canonical order, and the row-order-invariant content hash.
# --------------------------------------------------------------------------- #
def _cell(value: Any) -> Any:
    """The exact value a table CELL holds. Lists and maps travel as canonical JSON strings, so
    what is hashed is what is written and a re-read reproduces it byte for byte."""
    if isinstance(value, (list, tuple, dict)):
        return canonical_json(value)
    if isinstance(value, float):        # a float never enters a Stage-3 hash
        raise ArtifactV2Error(
            GATE_TABLE_NOT_ON_DISK,
            f"a table cell holds the float {value!r}; every magnitude travels as an exact "
            "source string plus a canonical decimal (see druglink.canonical_number)")
    return value


def encode(name: str, rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """The rows as they are WRITTEN: exact cell values, in ONE canonical order.

    Ordered by the same total order the content hash uses, so the FILE BYTES are a pure
    function of the content too — and a build that assembled the same rows in a different order
    still emits the same parquet.
    """
    cols, sort_keys = TABLES[name]
    encoded = [{c: _cell(r.get(c)) for c in cols} for r in rows]
    return sorted(encoded, key=lambda r: row_key(r, sort_keys))


def table_content_hash(name: str, rows: Iterable[Mapping[str, Any]]) -> str:
    """Row-order-invariant hash over the EMITTED cell values. Permuting rows cannot move it."""
    cols, sort_keys = TABLES[name]
    content_cols = [c for c in cols if c not in DISPLAY_COLUMNS]
    keys = tuple(k for k in sort_keys if k in content_cols) or (content_cols[0],)
    return table_hash([{c: _cell(r.get(c)) for c in content_cols} for r in rows], keys)


def table_content_hashes(tables: Mapping[str, list[dict[str, Any]]]) -> dict[str, str]:
    return {name: table_content_hash(name, tables.get(name, []))
            for name in SCIENTIFIC_TABLES}


def _all_ints(values: Iterable[Any]) -> bool:
    return all(isinstance(v, int) and not isinstance(v, bool)
               for v in values if v is not None)


def _frame(name: str, rows: list[dict[str, Any]]) -> pd.DataFrame:
    cols, _ = TABLES[name]
    if not rows:
        return pd.DataFrame({c: pd.Series(dtype="object") for c in cols})
    encoded = encode(name, rows)
    frame = pd.DataFrame(encoded, columns=list(cols))
    typed: list[str] = []
    for col in NULLABLE_INT_COLUMNS:
        if col in frame.columns and _all_ints(r[col] for r in encoded):
            frame[col] = pd.array([r[col] for r in encoded], dtype="Int64")
            typed.append(col)
    return frame.astype({c: "object" for c in cols if c not in typed})


def _py(value: Any) -> Any:
    if value is None or value is pd.NA:
        return None
    if isinstance(value, str):
        return value
    if hasattr(value, "item"):                     # a numpy / pandas scalar
        value = value.item()
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    return value


def read_table(path: str, name: str) -> list[dict[str, Any]]:
    """The table as it is ON DISK. What the manifest describes must be what was written."""
    cols, _ = TABLES[name]
    frame = pd.read_parquet(path)
    return [{c: _py(row.get(c)) for c in cols} for row in frame.to_dict("records")]


# --------------------------------------------------------------------------- #
# Atomic emission.
# --------------------------------------------------------------------------- #
def write_bundle(*, output_root: str, artifact_class: str, document: Mapping[str, Any],
                 doc_id: str, tables: Mapping[str, list[dict[str, Any]]],
                 created_at: Optional[str] = None) -> str:
    """Stage, re-read, then bind. A half-written bundle never becomes a bundle."""
    ac.require(artifact_class)
    check_contract(document, tables)
    target = v1.bundle_dir(output_root, artifact_class, doc_id)
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    staging = tempfile.mkdtemp(prefix=".stage3_v2_staging_",
                               dir=os.path.dirname(target) or ".")
    try:
        files: list[dict[str, Any]] = []
        for name in SCIENTIFIC_TABLES:
            rows = list(tables.get(name, []))
            fname = f"{name}.parquet"
            path = os.path.join(staging, fname)
            _frame(name, rows).to_parquet(path, index=False)
            files.append({"file": fname, "n_rows": len(rows),
                          "content_sha256": table_content_hash(name, rows),
                          "file_sha256": file_sha256(path)})

        doc_name = V2_DOC[artifact_class]
        v1.write_json(os.path.join(staging, doc_name), dict(document))
        files.append({"file": doc_name, "n_rows": len(document["candidates"]),
                      "content_sha256": document["canonical_content_sha256"],
                      "file_sha256": file_sha256(os.path.join(staging, doc_name))})

        manifest = _manifest(document, artifact_class=artifact_class, doc_id=doc_id,
                             doc_name=doc_name, files=files, created_at=created_at)
        v1.write_json(os.path.join(staging, "manifest.json"), manifest)

        _reread(staging, tables=tables, document=document, manifest=manifest)

        if os.path.exists(target):
            _refuse_unless_identical(target, manifest)
            shutil.rmtree(staging)
            return target
        os.rename(staging, target)      # atomic bind of directory <-> manifest
        return target
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _manifest(document: Mapping[str, Any], *, artifact_class: str, doc_id: str,
              doc_name: str, files: list[dict[str, Any]],
              created_at: Optional[str]) -> dict[str, Any]:
    manifest = {
        "schema_version": V2_MANIFEST_SCHEMA,
        "artifact_class": artifact_class,
        "bundle_id": doc_id,
        "document_file": doc_name,
        "document_sha256": document["document_sha256"],
        "canonical_content_sha256": document["canonical_content_sha256"],
        "stage2_aggregate": document["stage2_aggregate"],
        "universe_store": document["universe_store"],
        "method": document["method"],
        "origin_types": document["origin_types"],
        "data_status": document["data_status"],
        "inference_status": document["inference_status"],
        "combined_objective_permitted": False,
        "headline_arm_permitted": False,
        "p_q_fdr_permitted": False,
        "deferred_lanes": document["deferred_lanes"],
        "table_hashes": document["table_hashes"],
        "counts": document["counts"],
        "files": sorted(files, key=lambda f: f["file"]),
        # WHEN the run happened. Recorded, and OUTSIDE the manifest's own identity — two runs
        # of identical science differ only in when they happened.
        "created_at": created_at,
    }
    manifest["manifest_sha256"] = content_hash(
        without(manifest, ("manifest_sha256", "created_at")))
    return manifest


def _reread(staging: str, *, tables: Mapping[str, list[dict[str, Any]]],
            document: Mapping[str, Any], manifest: Mapping[str, Any]) -> None:
    """Read the bundle back OFF THE DISK and re-derive every hash before it is bound."""
    for name in SCIENTIFIC_TABLES:
        on_disk = read_table(os.path.join(staging, f"{name}.parquet"), name)
        want = table_content_hash(name, tables.get(name, []))
        got = table_content_hash(name, on_disk)
        if got != want or len(on_disk) != len(tables.get(name, [])):
            raise ArtifactV2Error(
                GATE_TABLE_NOT_ON_DISK,
                f"{name}.parquet re-read from disk hashes to {got[:16]}… but the rows that "
                f"were hashed give {want[:16]}… ({len(on_disk)} rows on disk vs "
                f"{len(tables.get(name, []))} in memory)")

    with open(os.path.join(staging, manifest["document_file"]), encoding="utf-8") as fh:
        doc = json.load(fh)
    if content_hash(without(doc, ("document_sha256",))) != document["document_sha256"]:
        raise ArtifactV2Error(
            GATE_TABLE_NOT_ON_DISK,
            "the document re-read from disk does not hash to its own document_sha256")


def _refuse_unless_identical(target: str, manifest: Mapping[str, Any]) -> None:
    existing_path = os.path.join(target, "manifest.json")
    if not os.path.exists(existing_path):
        raise ArtifactV2Error(
            GATE_ID_COLLISION,
            f"refusing to write into {os.path.basename(target)}: it exists but has no manifest")
    with open(existing_path, encoding="utf-8") as fh:
        existing = json.load(fh)
    if existing.get("manifest_sha256") != manifest["manifest_sha256"]:
        raise ArtifactV2Error(
            GATE_ID_COLLISION,
            f"refusing to overwrite {os.path.basename(target)}: an existing bundle with the "
            f"same id has DIFFERENT content ({str(existing.get('manifest_sha256'))[:16]}… != "
            f"{manifest['manifest_sha256'][:16]}…). Two different sciences may never wear one "
            "identifier")


def emit(*, output_root: str, artifact_class: str, aggregate: AdmittedAggregate,
         store: AdmittedStore, report_path: str,
         created_at: Optional[str] = None) -> dict[str, Any]:
    """Build the v2 evidence set from the ADMITTED inputs and bind it atomically to disk."""
    ac.require(artifact_class)
    report = bind_report(report_path, aggregate)
    tables = cv2.build(artifact_class=artifact_class, aggregate=aggregate, store=store)
    tables["provenance"] = provenance_rows(
        aggregate=aggregate, store=store, report=report, method=method_block(store))
    document = build_document(
        artifact_class=artifact_class, aggregate=aggregate, store=store, report=report,
        table_hashes=table_content_hashes(tables), tables=tables)
    path = write_bundle(output_root=output_root, artifact_class=artifact_class,
                        document=document, doc_id=document["bundle_id"], tables=tables,
                        created_at=created_at)
    return {"bundle_dir": path, "bundle_id": document["bundle_id"], "document": document,
            "tables": tables}
