"""THE INDEPENDENT EVALUATOR OF A PROJECTION: open the store, and prove the rows came from it.

generator != evaluator. :mod:`druglink.view_projection` SEALS the projection; this REFUSES it.
The contract check (``view_contract.validate``) travels with the bytes and re-hashes the rows
against the seal — which is enough to catch a cell edited after sealing, and it is what closed
the audit's attack. It is NOT enough to catch an attacker who understood the check: mutate a row,
then RE-SEAL the projection over the mutated rows, and every hash in the document agrees again.
A document can always be made self-consistent. It cannot be made consistent with bytes it does
not control.

So this verifier holds THE STORE ON DISK and re-derives, from the parquet files themselves:

  1. the RAW FILE BYTES of every store table the seal names — sha256'd here, never read out of
     the view. A table SWAP (table A's bytes served as table B) moves this even when the rows
     still parse and the row count still fits;
  2. the CONTENT of every projected row: stripped of the join-time annotations the projection
     adds, each row must be — CELL FOR CELL, display columns included — a row the store actually
     holds, under the same identity. This is the check a re-seal cannot survive: the forger would
     have to edit the store, and the store is hashed by its own manifest, by the bundle document,
     and by Stage 2's receipt;
  3. the seal's own identity, the row counts, the column contracts and the schema set.

A mismatch is a NAMED REFUSAL. It is never reconciled, and the recomputed value is never adopted:
if the projection and the store disagree, WHICH ONE IS THE SCIENCE is exactly the question nobody
can answer after the fact.

THE TABLE LIST IS RESTATED HERE, INDEPENDENTLY. A verifier that asks the producer what to verify
is a verifier that verifies whatever the producer felt like emitting.
"""
from __future__ import annotations

import os
from typing import Any, Mapping, Sequence

from druglink import artifacts_v2 as av2
from druglink import view_projection as vp
from druglink.hashing import canonical_json, content_hash, file_sha256, without

VERIFIER_ID = "spot.stage03.selection_view.projection_identity.independent_verifier.v1"

# RESTATED, not imported from the seal's own list. These are the seven tables a selection view
# projects; `provenance` is the eighth table in the store and is never projected.
PROJECTED_TABLES: tuple[str, ...] = (
    "arm_slots", "arm_summaries", "candidates", "dispositions",
    "pathway_context", "source_records", "target_drug_edges")

GATE_NO_STORE = "the_projection_was_verified_against_a_store_that_is_not_there"
GATE_STORE_TABLE_NOT_ON_DISK = vp.GATE_STORE_TABLE_NOT_ON_DISK
GATE_RAW_BYTES_ARE_NOT_THE_STORES = vp.GATE_RAW_BYTES_ARE_NOT_THE_STORES
GATE_ROW_IS_NOT_A_STORE_ROW = vp.GATE_ROW_IS_NOT_A_STORE_ROW
GATE_TABLE_NOT_SEALED = vp.GATE_TABLE_NOT_SEALED
GATE_SEALED_TABLE_NOT_PROJECTED = vp.GATE_SEALED_TABLE_NOT_PROJECTED
GATE_ROWS_ARE_NOT_THE_SEALED_ROWS = vp.GATE_ROWS_ARE_NOT_THE_SEALED_ROWS
GATE_ROW_COUNT_MOVED = vp.GATE_ROW_COUNT_MOVED
GATE_DUPLICATE_ROW = vp.GATE_DUPLICATE_ROW
GATE_ORDERED_BLOCK_REORDERED = vp.GATE_ORDERED_BLOCK_REORDERED
GATE_SCHEMA_SET_DRIFT = vp.GATE_SCHEMA_SET_DRIFT
GATE_SEAL_IDENTITY = vp.GATE_SEAL_IDENTITY
GATE_VIEW_IDENTITY = vp.GATE_VIEW_IDENTITY
GATE_STALE_RECEIPT = vp.GATE_STALE_RECEIPT


class ProjectionRefusal(ValueError):
    """A named, fail-closed refusal. The projection is not admitted, and nothing is written."""

    def __init__(self, gate: str, message: str) -> None:
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


def _refuse(gate: str, message: str) -> None:
    raise ProjectionRefusal(gate, message)


def checks() -> list[str]:
    """Every gate this verifier runs. A gate nobody can enumerate is a gate nobody can notice
    the absence of."""
    return sorted(set(vp.checks()) | set(vp.disk_checks()) | {GATE_NO_STORE})


# --------------------------------------------------------------------------- #
# The store, re-opened. Raw bytes first, then rows.
# --------------------------------------------------------------------------- #
def _raw_sha256(bundle_dir: str, name: str) -> str:
    path = os.path.join(bundle_dir, f"{name}.parquet")
    if not os.path.isfile(path):
        _refuse(GATE_STORE_TABLE_NOT_ON_DISK,
                f"the seal names the store table {name!r}, but there is no {name}.parquet in the "
                "store. A projection of bytes that are not there is a projection of nothing, and "
                "its seal names nothing.")
    return file_sha256(path)


def _store_rows(bundle_dir: str, name: str) -> dict[str, dict[str, Any]]:
    """The store's rows, canonically encoded, indexed by their own identity."""
    rows = av2.read_table(os.path.join(bundle_dir, f"{name}.parquet"), name)
    keys = av2.TABLES[name][1]
    return {canonical_json([r.get(k) for k in keys]): r for r in av2.encode(name, rows)}


def _store_projection(name: str, row: Mapping[str, Any]) -> dict[str, Any]:
    """A projected row, stripped back to the STORE row it must still be.

    ``av2.encode`` keeps exactly the store's own columns, so the join-time annotations the view
    adds (``selection_roles``, the ``view_``-prefixed candidate fields) fall away and what is left
    is what the store must hold — every column, including the display-only ones the store's
    content hash excludes. A mislabelled row would otherwise reach a rendered page under a name
    nobody wrote.
    """
    return av2.encode(name, [row])[0]


def _check_rows_are_store_rows(name: str, rows: Sequence[Mapping[str, Any]],
                               on_disk: Mapping[str, dict[str, Any]]) -> None:
    keys = av2.TABLES[name][1]
    for row in rows:
        ident = canonical_json([row.get(k) for k in keys])
        theirs = on_disk.get(ident)
        if theirs is None:
            _refuse(GATE_ROW_IS_NOT_A_STORE_ROW,
                    f"the projected {name!r} row {ident} is not a row the store holds. A view "
                    "only FILTERS and ANNOTATES rows the store already contains — it invents "
                    "nothing. A row that is in the view and not in the store is evidence nobody "
                    "produced, travelling with the authority of a release that never carried it.")
        mine = _store_projection(name, row)
        if mine != theirs:
            bad = sorted(c for c in theirs if mine.get(c) != theirs.get(c))
            _refuse(GATE_ROW_IS_NOT_A_STORE_ROW,
                    f"the projected {name!r} row {ident} differs from the store's row of the same "
                    f"identity in column(s) {bad}: the view says "
                    f"{ {c: mine.get(c) for c in bad[:3]} }, the store on disk says "
                    f"{ {c: theirs.get(c) for c in bad[:3]} }. The cell was edited after the view "
                    "was projected. Re-sealing the projection would make the DOCUMENT agree with "
                    "itself again — it cannot make it agree with the bytes it does not control, "
                    "and this is those bytes.")


# --------------------------------------------------------------------------- #
# The whole refusal.
# --------------------------------------------------------------------------- #
def verify(view: Mapping[str, Any], *, bundle_dir: str) -> dict[str, Any]:
    """REFUSE, or return what was PROVEN. Never reconcile, never adopt the recomputed value."""
    if not bundle_dir or not os.path.isdir(bundle_dir):
        _refuse(GATE_NO_STORE,
                f"there is no store at {bundle_dir!r}. Without it the seal could only be compared "
                "with itself, and a document can always be made to agree with itself.")

    block = view.get("projection")
    if not isinstance(block, Mapping) or not block.get("tables"):
        _refuse(GATE_TABLE_NOT_SEALED,
                "the view carries no projection seal, so its tables are a BARE ROW LIST: nothing "
                "in the document is about the rows the consumer reads.")

    # 1. THE CONTRACT, re-run on the bytes in hand. It refuses a post-seal edit, a reorder of the
    #    ordered arm pair, a duplicated row, a stale receipt and a moved schema set.
    vp.check(view)

    # 2. THE STORE, re-opened. This is what a re-seal cannot survive.
    tables = view.get("tables") or {}
    sealed = block["tables"]
    missing = sorted(set(PROJECTED_TABLES) - set(sealed))
    if missing:
        _refuse(GATE_TABLE_NOT_SEALED,
                f"the seal does not cover {missing}; this verifier independently restates the "
                f"seven projected tables as {list(PROJECTED_TABLES)}.")

    proven: dict[str, Any] = {}
    for name in PROJECTED_TABLES:
        if name not in tables:
            _refuse(GATE_SEALED_TABLE_NOT_PROJECTED,
                    f"the seal names {name!r} but the view carries no such table.")
        want = sealed[name]

        raw = _raw_sha256(bundle_dir, name)
        if raw != want.get("raw_sha256"):
            _refuse(GATE_RAW_BYTES_ARE_NOT_THE_STORES,
                    f"the seal says the store table {name!r} has raw bytes "
                    f"{str(want.get('raw_sha256'))[:16]}…, but {name}.parquet on disk hashes to "
                    f"{raw[:16]}…. Either these are not the bytes this view was projected from, "
                    "or one table's bytes are being served as another's. The rows might still "
                    "parse and the count might still fit — and the science would be a different "
                    "table's.")

        rows = list(tables[name])
        _check_rows_are_store_rows(name, rows, _store_rows(bundle_dir, name))
        proven[name] = {"raw_sha256": raw, "row_count": len(rows),
                        "content_sha256": vp.projected_content_hash(name, rows),
                        "schema_id": vp.table_schema_id(name)}

    return {
        "verifier_id": VERIFIER_ID,
        "verdict": "ADMIT",
        "checks": checks(),
        "n_tables_verified": len(PROJECTED_TABLES),
        "projection_sha256": block["projection_sha256"],
        "view_content_sha256": view.get("view_content_sha256"),
        "tables": proven,
        "every_projected_row_was_proven_to_be_a_row_the_store_holds": True,
        "the_recomputed_value_is_never_adopted_a_mismatch_is_a_refusal": True,
    }


def recompute_seal(view: Mapping[str, Any], *, bundle_dir: str) -> dict[str, Any]:
    """The seal this projection SHOULD carry, re-derived from the store and the rows.

    Returned for a REPORT, never written back into the view. The moment a verifier repairs what
    it was asked to judge, it has stopped being a verifier.
    """
    return vp.seal(view_rows={n: list((view.get("tables") or {}).get(n, ()))
                              for n in PROJECTED_TABLES},
                   arm_evidence=list(view.get("arm_evidence") or ()),
                   bundle_dir=bundle_dir)


def seal_identity(block: Mapping[str, Any]) -> str:
    """The seal's own id, recomputed. An artifact that never recomputes its own identity can be
    handed a forged one (audit finding B6) — and it would then vouch for anything."""
    return content_hash(without(dict(block), ("projection_sha256",)))
