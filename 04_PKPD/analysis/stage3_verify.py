"""Reconstruct a Stage-3 bundle's integrity claims. Never accept a self-declaration.

The audit's attack: change `form_class=parent` to `prodrug` in `drug_forms.parquet`,
re-seal the FILE sha and the manifest self-hash, and leave the declared CONTENT sha stale.
The old adapter compared the document's declared `table_hashes[t]` with the manifest's
declared `content_sha256` — two declarations agreeing with each other — and never looked
at a single row. It admitted the mutated form.

So every table's content hash, row count, columns, value kinds and sort key are recomputed
HERE, from the actual parquet rows, using the independent transcription in
`stage3_contract.py`. A stale content hash cannot survive that.

Chain of custody, and where it ends:

    rows  ->  table_content_hash    (recomputed here, from the bytes on disk)
          ->  document.table_hashes (must equal it)
          ->  canonical_content_sha256 (recomputed here; table_hashes is INSIDE it)
          ->  bundle_id = <prefix><canonical_content_sha256[:16]>  (recomputed here)
          ->  the directory name     (must equal it)

Re-sealing one link breaks the next. Re-sealing all of them produces a different bundle id
and therefore a different directory name. What Stage 4 CANNOT detect is a fully
self-consistent bundle forged from scratch: its `method.code_tree_sha256` and
`env_lock_sha256` are Stage-3's own, and only Stage 3 can vouch for those. That is the
trust boundary, and it is where it belongs.
"""

from __future__ import annotations

import json
import os
from typing import Any

import pyarrow.parquet as pq

from .firewall import Rejection
from .stage3_contract import (
    CANDIDATE_CONTENT_KEYS,
    DOCUMENT_ID_KEY,
    DOCUMENT_ID_PREFIX,
    INSPECTABLE_KEY,
    RANKED_KEY,
    SCHEMA_BY_NAMESPACE,
    STAGE3_MANIFEST_SCHEMA,
    STAGE3_TABLE_CONTRACT_VERSION,
    TABLE_FILES,
    TABLES,
    ContractError,
    cell_kind_ok,
    cjson,
    content_sort_keys,
    kind_of,
    row_key,
    sha256_hex,
    table_content_hash,
)

NAMESPACE_BY_SCHEMA = {schema: ns for ns, schema in SCHEMA_BY_NAMESPACE.items()}

REQUIRED_DOCUMENT_KEYS = (
    "namespace", "canonical_content_sha256", "document_sha256", "upstream", "method",
    "source_records", "table_hashes", "source_status",
)

# Files a bundle directory may hold that the manifest does not list. Stage 3's own
# verifier writes verification.json after the manifest is sealed.
UNDECLARED_FILES_ALLOWED = frozenset({"manifest.json", "verification.json"})


def _sha_file(path: str) -> str:
    h = __import__("hashlib").sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _safe_member(name: str) -> str:
    """A manifest entry is a bare filename inside the bundle. Nothing else."""
    if (not name or name in (".", "..") or os.path.isabs(name)
            or "/" in name or "\\" in name or name.startswith(".")):
        raise Rejection(
            "stage3_unsafe_file_entry",
            f"Stage-3 manifest lists {name!r}: a bundle entry must be a bare filename inside "
            "the bundle directory, never a path, a parent reference or an absolute path",
        )
    return name


def resolve_namespace(doc: dict[str, Any]) -> str:
    schema = doc.get("schema_version")
    if schema not in NAMESPACE_BY_SCHEMA:
        raise Rejection(
            "stage3_schema_unknown",
            f"unknown Stage-3 schema_version {schema!r}; Stage 4 accepts only "
            + ", ".join(sorted(NAMESPACE_BY_SCHEMA)),
        )
    namespace = NAMESPACE_BY_SCHEMA[schema]
    for key in REQUIRED_DOCUMENT_KEYS:
        if key not in doc:
            raise Rejection("stage3_schema_invalid", f"Stage-3 document has no {key!r}")
    if doc["namespace"] != namespace:
        raise Rejection(
            "stage3_namespace_mismatch",
            f"{schema} must be namespace {namespace!r}, got {doc['namespace']!r}",
        )
    return namespace


def canonical_content(doc: dict[str, Any], namespace: str) -> dict[str, Any]:
    """Stage 3's canonical content, restated. `table_hashes` lives INSIDE it."""
    try:
        ranked = [
            {k: c[k] for k in CANDIDATE_CONTENT_KEYS}
            for c in doc.get(RANKED_KEY[namespace], []) or []
        ]
        inspectable = [
            {k: c[k] for k in CANDIDATE_CONTENT_KEYS}
            for c in doc.get(INSPECTABLE_KEY[namespace], []) or []
        ]
    except KeyError as exc:
        raise Rejection(
            "stage3_candidate_shape_invalid",
            f"a Stage-3 candidate row is missing the content key {exc.args[0]!r}",
        ) from exc

    return {
        "schema_version": doc["schema_version"],
        "namespace": namespace,
        "upstream": doc["upstream"],
        "method": doc["method"],
        "source_records": [
            {k: v for k, v in s.items() if k != "parse_detail"}
            for s in sorted(doc["source_records"], key=lambda s: s["source_record_id"])
        ],
        "table_hashes": dict(sorted(doc["table_hashes"].items())),
        "ranked_candidates": ranked,
        "inspectable_candidates": inspectable,
    }


def verify_document(doc: dict[str, Any], namespace: str) -> None:
    """The document's two self-hashes and its bundle id, all recomputed."""
    try:
        body = {k: v for k, v in doc.items() if k != "document_sha256"}
        recomputed_doc = sha256_hex(cjson(body))
        recomputed_content = sha256_hex(cjson(canonical_content(doc, namespace)))
    except ContractError as exc:
        raise Rejection("stage3_uncanonical_content", str(exc)) from exc

    if recomputed_doc != doc["document_sha256"]:
        raise Rejection(
            "stage3_document_hash_mismatch",
            "Stage-3 document_sha256 does not match the document content",
            {"declared": doc["document_sha256"], "recomputed": recomputed_doc},
        )
    if recomputed_content != doc["canonical_content_sha256"]:
        raise Rejection(
            "stage3_canonical_content_hash_mismatch",
            "Stage-3 canonical_content_sha256 does not reproduce from the document's own "
            "content. table_hashes is inside that content, so a re-sealed table hash "
            "cannot hide here.",
            {"declared": doc["canonical_content_sha256"], "recomputed": recomputed_content},
        )

    id_key = DOCUMENT_ID_KEY[namespace]
    declared_id = doc.get(id_key)
    expected_id = DOCUMENT_ID_PREFIX[namespace] + recomputed_content[:16]
    if declared_id != expected_id:
        raise Rejection(
            "stage3_bundle_id_mismatch",
            f"Stage-3 {id_key} {declared_id!r} is not the content hash of its own document "
            f"(expected {expected_id!r}). The bundle id IS the canonical content hash.",
        )

    declared_tables = set(doc["table_hashes"])
    if declared_tables != set(TABLES):
        raise Rejection(
            "stage3_table_contract_mismatch",
            f"Stage-3 document declares tables {sorted(declared_tables)}, but the frozen "
            f"Stage-4 transcription of {STAGE3_TABLE_CONTRACT_VERSION} expects "
            f"{sorted(TABLES)}",
        )


def _read_rows(path: str, table: str) -> list[dict[str, Any]]:
    """The actual rows, with the actual columns, checked against the frozen contract."""
    kinds, _sort_keys = TABLES[table]
    schema = pq.read_schema(path)
    if list(schema.names) != list(kinds):
        raise Rejection(
            "stage3_table_columns_mismatch",
            f"{table}.parquet columns do not match the frozen Stage-3 contract",
            {"declared": list(kinds), "found": list(schema.names)},
        )

    rows: list[dict[str, Any]] = pq.read_table(path).to_pylist()
    for i, row in enumerate(rows):
        for column, declared_kind in kinds.items():
            value = row.get(column)
            if not cell_kind_ok(declared_kind, value):
                raise Rejection(
                    "stage3_table_dtype_mismatch",
                    f"{table}.parquet row {i} column {column!r} is {kind_of(value)!r}, but the "
                    f"frozen Stage-3 contract declares {declared_kind!r}",
                )
    return rows


def _check_no_duplicate_keys(table: str, rows: list[dict[str, Any]]) -> None:
    keys = content_sort_keys(table)
    seen: dict[str, int] = {}
    for row in rows:
        k = cjson([row.get(c) for c in keys])
        seen[k] = seen.get(k, 0) + 1
    dupes = sorted(k for k, n in seen.items() if n > 1)
    if dupes:
        raise Rejection(
            "stage3_table_duplicate_rows",
            f"{table}.parquet has {len(dupes)} duplicated sort key(s) {keys}: a table whose "
            "primary key repeats has no single row per subject, so a lookup by that key is "
            "ambiguous",
            {"duplicate_keys": dupes[:5]},
        )


def reconstruct_tables(doc: dict[str, Any], bundle_dir: str) -> dict[str, list[dict[str, Any]]]:
    """Recompute every table's content hash, row count and shape FROM THE ROWS.

    -> the rows, once they have earned being believed.
    """
    manifest_path = os.path.join(bundle_dir, "manifest.json")
    if not os.path.exists(manifest_path):
        raise Rejection("stage3_manifest_missing",
                        f"Stage-3 bundle {bundle_dir!r} has no manifest.json")
    with open(manifest_path, encoding="utf-8") as fh:
        manifest = json.load(fh)

    if manifest.get("schema_version") != STAGE3_MANIFEST_SCHEMA:
        raise Rejection(
            "stage3_manifest_schema_unknown",
            f"Stage-3 manifest schema {manifest.get('schema_version')!r} is not "
            f"{STAGE3_MANIFEST_SCHEMA!r}",
        )

    # 1. The manifest is self-consistent. Stage 3 excludes its own hash field and the
    #    wall-clock timestamp, so a rerun on a different day still binds identically.
    try:
        recomputed = sha256_hex(cjson({k: v for k, v in manifest.items()
                                       if k not in ("manifest_sha256", "created_at")}))
    except ContractError as exc:
        raise Rejection("stage3_uncanonical_content", str(exc)) from exc
    if recomputed != manifest.get("manifest_sha256"):
        raise Rejection("stage3_manifest_hash_mismatch",
                        "Stage-3 manifest_sha256 does not match the manifest content")

    # 2. The manifest agrees with the document about the document.
    if (manifest.get("document_sha256") != doc["document_sha256"]
            or manifest.get("canonical_content_sha256") != doc["canonical_content_sha256"]):
        raise Rejection("stage3_manifest_document_mismatch",
                        "Stage-3 manifest and document disagree about the document hashes")
    if manifest.get("table_hashes") != doc["table_hashes"]:
        raise Rejection("stage3_manifest_document_mismatch",
                        "Stage-3 manifest and document disagree about the table hashes")

    entries = manifest.get("files", [])
    by_file: dict[str, dict[str, Any]] = {}
    for entry in entries:
        name = _safe_member(str(entry.get("file", "")))
        if name in by_file:
            raise Rejection("stage3_manifest_duplicate_file",
                            f"Stage-3 manifest lists {name!r} more than once")
        by_file[name] = entry

    declared_parquet = {n for n in by_file if n.endswith(".parquet")}
    expected_parquet = set(TABLE_FILES)
    unknown = sorted(declared_parquet - expected_parquet)
    absent = sorted(expected_parquet - declared_parquet)
    if unknown or absent:
        raise Rejection(
            "stage3_table_contract_mismatch",
            f"Stage-3 bundle's parquet set does not match the frozen contract "
            f"{STAGE3_TABLE_CONTRACT_VERSION}: unknown={unknown} missing={absent}",
        )

    on_disk = {n for n in os.listdir(bundle_dir) if n not in UNDECLARED_FILES_ALLOWED}
    extra = sorted(on_disk - set(by_file))
    if extra:
        raise Rejection(
            "stage3_undeclared_file",
            f"Stage-3 bundle holds file(s) the manifest does not declare: {extra}. An "
            "undeclared artifact in a sealed bundle is never benign.",
        )

    tables: dict[str, list[dict[str, Any]]] = {}
    for name, entry in sorted(by_file.items()):
        path = os.path.join(bundle_dir, name)
        if not os.path.exists(path):
            raise Rejection("stage3_table_missing",
                            f"Stage-3 manifest lists {name!r} but it is absent")

        actual_file_sha = _sha_file(path)
        if actual_file_sha != entry.get("file_sha256"):
            raise Rejection(
                "stage3_file_hash_mismatch",
                f"Stage-3 file {name!r} does not match its declared file hash",
                {"file": name, "declared": entry.get("file_sha256"),
                 "recomputed": actual_file_sha},
            )
        if not name.endswith(".parquet"):
            continue

        table = name[: -len(".parquet")]
        rows = _read_rows(path, table)
        _check_no_duplicate_keys(table, rows)

        if len(rows) != entry.get("n_rows"):
            raise Rejection(
                "stage3_table_row_count_mismatch",
                f"{name} holds {len(rows)} rows but the manifest declares "
                f"{entry.get('n_rows')!r}",
            )

        try:
            recomputed_content = table_content_hash(table, rows)
        except ContractError as exc:
            raise Rejection("stage3_uncanonical_content",
                            f"{name}: {exc}") from exc

        # THE check the audit defeated: the rows, not two agreeing declarations.
        if recomputed_content != entry.get("content_sha256"):
            raise Rejection(
                "stage3_table_content_hash_mismatch",
                f"{name}: the content hash recomputed from the actual parquet rows does not "
                "match the hash the manifest declares. The rows on disk are not the rows "
                "Stage 3 hashed.",
                {"table": table, "declared": entry.get("content_sha256"),
                 "recomputed_from_rows": recomputed_content},
            )
        if recomputed_content != doc["table_hashes"].get(table):
            raise Rejection(
                "stage3_table_content_hash_mismatch",
                f"{name}: the content hash recomputed from the actual parquet rows does not "
                "match the hash the DOCUMENT declares.",
                {"table": table, "declared": doc["table_hashes"].get(table),
                 "recomputed_from_rows": recomputed_content},
            )
        tables[table] = rows

    return tables


def verify_bundle(doc: dict[str, Any], bundle_dir: str | None) -> dict[str, list[dict[str, Any]]]:
    """Full reconstruction. -> the verified rows (empty when only a document was supplied)."""
    namespace = resolve_namespace(doc)
    verify_document(doc, namespace)
    if not bundle_dir:
        return {}

    tables = reconstruct_tables(doc, bundle_dir)

    # The directory name binds the bundle: it IS the content hash, so a fully re-sealed
    # mutation lands in a directory that no longer matches its own id.
    expected_id = doc[DOCUMENT_ID_KEY[namespace]]
    actual = os.path.basename(os.path.normpath(bundle_dir))
    if actual != expected_id:
        raise Rejection(
            "stage3_bundle_directory_mismatch",
            f"Stage-3 bundle directory is {actual!r} but the document's id is {expected_id!r}. "
            "The directory name binds the bundle to its canonical content hash.",
        )
    return tables


def sort_key_order_ok(table: str, rows: list[dict[str, Any]]) -> bool:
    """Are the rows already in the frozen sort-key order?

    Stage 3 writes tables in PIPELINE order, not sort-key order, and its content hash is
    row-order-invariant by construction (it sorts before hashing). So this is reported, not
    enforced: what pins the exact byte order of a parquet is its file_sha256, which is
    checked above. Row order carries no scientific claim here.
    """
    keys = content_sort_keys(table)
    return rows == sorted(rows, key=lambda r: row_key(r, keys))
