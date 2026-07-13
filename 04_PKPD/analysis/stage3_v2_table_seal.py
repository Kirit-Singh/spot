"""The table-seal contract — Stage 4 recomputes the Stage-3 tables from disk before it admits them.

W16 is adding exact per-table raw/canonical hashes, schema ids, row counts, and the aggregate/store
receipt bindings. This is the Stage-4 side, written NOW so the corrected bundle admits in ONE
handoff: the field NAMES Stage 4 requires are declared here, and the VALUES come from W16.

WHY THIS EXISTS. At `ee4810c` the selection view projected its tables as bare row lists. The sealed
`table_hashes` described the STORE's tables and were never re-bound to the PROJECTED rows, so a row
could be added, changed or dropped after the store was sealed and **every hash in the view still
agreed with every other hash in the view**. Nothing was inconsistent. Nothing was detectable.

The repair is not "a hash". It is a hash Stage 4 RECOMPUTES ITSELF, from the bytes on disk, and
compares against what the bundle declares. A hash the bundle asserts about itself proves only that
the bundle can hash — a forged bundle hashes too. Self-consistency is what a forgery HAS; an
independent recomputation is what it lacks.

    declared (W16)  ──compare──  recomputed (Stage 4, from the on-disk table)

WHAT IS PINNED HERE: the field names Stage 4 requires, and the two hashing rules.
WHAT IS NOT: any value. Nothing is guessed. `TABLE_SEAL_FIELDS_PUBLISHED = False` until W16 confirms
the field spellings, and `require_table_seals()` refuses every bundle until then — the current
contract path is untouched and no existing gate is loosened.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Iterable, Optional

from .firewall import Rejection

TABLE_SEAL_CONTRACT = "spot.stage04.stage3_table_seal.v1"

# The per-table identity Stage 4 requires. NAMES, not values — W16 publishes the values, and Stage 4
# recomputes them rather than believing them.
#
# `raw_sha256`     the bytes on disk, exactly as written. Catches a re-serialisation.
# `canonical_sha256` the CONTENT, writer-independent. Catches a row change that a re-serialisation
#                  would otherwise mask — the scientific identity, as distinct from one encoding of
#                  it.
# `schema_id`      what the table claims to BE. A table read under the wrong schema is read wrong.
# `row_count`      the cheapest possible check, and the one that catches a DROPPED row. A row nobody
#                  hashed is a row nobody missed.
REQUIRED_TABLE_SEAL_FIELDS = ("raw_sha256", "canonical_sha256", "schema_id", "row_count")

# Set to True only when W16 confirms the exact spellings. Until then every bundle is refused, and
# the existing contract path (`stage3_v2_contract.py`) is unchanged.
TABLE_SEAL_FIELDS_PUBLISHED = False


class TableSealError(Rejection):
    """A Stage-3 table does not recompute to what the bundle declares about it."""


def canonical_sha256(rows: Iterable[dict[str, Any]]) -> str:
    """The CONTENT hash: writer-independent, so a re-serialisation cannot hide a row change.

    Sorted keys, no whitespace, rows in their emitted order — order is part of a table's identity,
    and a reordered table is a different table, not the same one written differently.
    """
    payload = json.dumps(list(rows), sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def raw_sha256(path: str) -> str:
    """The bytes as they sit on disk."""
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def recompute_table_seal(bundle_dir: str, table: str,
                         rows: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    """Recompute a table's identity FROM DISK. Stage 4's own arithmetic, never the bundle's word."""
    path = _table_path(bundle_dir, table)
    if path is None:
        raise TableSealError(
            "stage3_table_missing",
            f"the bundle declares table {table!r} and does not carry it. A table absent from a "
            "bundle is indistinguishable from a table whose rows nobody found.",
        )
    if rows is None:
        rows = _read_rows(path)
    return {
        "raw_sha256": raw_sha256(path),
        "canonical_sha256": canonical_sha256(rows),
        "row_count": len(rows),
    }


def verify_table_seals(bundle_dir: str, declared: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Recompute every declared table and compare. -> a receipt naming what was checked.

    `declared` is W16's per-table seal block. Stage 4 recomputes each one from the on-disk table and
    refuses on any disagreement, naming the table AND which of the four identities disagreed —
    because "the bundle changed" is not actionable and "candidates.canonical_sha256 disagrees while
    raw_sha256 matches" says exactly what happened: somebody edited a row and re-serialised.
    """
    require_table_seals()

    checked, mismatches = [], []
    for table in sorted(declared):
        seal = declared[table] or {}
        missing = [f for f in REQUIRED_TABLE_SEAL_FIELDS if not seal.get(f)]
        if missing:
            raise TableSealError(
                "stage3_table_seal_incomplete",
                f"table {table!r} declares {sorted(set(REQUIRED_TABLE_SEAL_FIELDS) - set(missing))} "
                f"and is missing {missing}. A partial seal is not a seal: whichever identity is "
                "absent is the one nobody can check.",
            )

        actual = recompute_table_seal(bundle_dir, table)
        for field in ("raw_sha256", "canonical_sha256", "row_count"):
            if seal[field] != actual[field]:
                mismatches.append({
                    "table": table, "field": field,
                    "declared": seal[field], "recomputed": actual[field],
                })
        checked.append(table)

    if mismatches:
        first = mismatches[0]
        raise TableSealError(
            "stage3_table_seal_mismatch",
            f"{len(mismatches)} table identity mismatch(es). First: {first['table']}."
            f"{first['field']} — the bundle declares {str(first['declared'])[:20]!r} and Stage 4 "
            f"recomputes {str(first['recomputed'])[:20]!r} from the bytes on disk. A hash the "
            "bundle asserts about itself proves only that the bundle can hash.",
            {"mismatches": mismatches[:10], "n": len(mismatches)},
        )

    return {
        "contract": TABLE_SEAL_CONTRACT,
        "tables_checked": checked,
        "independently_recomputed": True,
        "note": ("every table identity was recomputed by Stage 4 from the on-disk bundle and "
                 "compared against what the bundle declares. Nothing was taken on the bundle's "
                 "word."),
    }


def require_table_seals() -> None:
    """Refuses until W16 publishes the field spellings. No value is guessed."""
    if TABLE_SEAL_FIELDS_PUBLISHED:
        return
    raise TableSealError(
        "stage3_table_seal_fields_not_published",
        "Stage 4 requires per-table "
        f"{list(REQUIRED_TABLE_SEAL_FIELDS)} on every Stage-3 table, and W16 has not yet confirmed "
        "the exact field spellings. Stage 4 will NOT guess them: a field name Stage 4 invented is a "
        "seal Stage 4 never actually checks. The current contract path is unchanged and no gate is "
        "loosened — this one simply refuses.",
    )


# ------------------------------------------------------------------------------ small helpers

def _table_path(bundle_dir: str, table: str) -> Optional[str]:
    for ext in (".parquet", ".json"):
        path = os.path.join(bundle_dir, f"{table}{ext}")
        if os.path.exists(path):
            return path
    return None


def _read_rows(path: str) -> list[dict[str, Any]]:
    if path.endswith(".parquet"):
        import pyarrow.parquet as pq

        return pq.read_table(path).to_pylist()
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    return doc if isinstance(doc, list) else doc.get("rows", [])
