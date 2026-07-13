"""THE PROJECTED TABLES ARE SEALED — a row nobody bound is a row anybody may edit.

    view["tables"] = {"arm_slots": [ …6 rows… ], "target_drug_edges": [ …10 rows… ], …}

That is what Stage 4 CONSUMES. And until this module existed it was a BARE ROW LIST with no
identity of its own: the view's ``store.table_hashes`` describe the GLOBAL STORE (all eight
tables, every row in the release), NOT the PROJECTED SUBSET. So a single cell edited AFTER the
view was sealed —

    view["tables"]["arm_slots"][0]["arm_context_sha256"] = "MUTATED"

— left every hash in the document mutually consistent, and the contract ADMITTED it. The store's
digest was still honest, because the store had not been touched. The rows the consumer reads had,
and nothing in the view was about THEM.

This is the same defect as the one closed one level up (``view_store``: a hash you COPY is not a
hash you CHECKED), turned inward. There the view republished the STORE's claims about itself.
Here the view republished NOTHING about the rows it actually shipped.

WHAT A SEALED TABLE CARRIES, AND WHICH BYTES EACH FIELD IS ABOUT
---------------------------------------------------------------
Two hashes, because they FAIL DIFFERENTLY and neither alone is sufficient:

``raw_sha256``      the RAW FILE BYTES of the STORE table this projection was taken FROM
                    (``<name>.parquet`` on disk). The subset in the view has no file of its own,
                    so this is the only RAW identity that exists for it — and it is the one that
                    catches a byte-level edit to the store that canonicalisation would smooth
                    over (a re-typed null, a re-encoded column, a mislabelled display cell).
``content_sha256``  the CANONICAL CONTENT of the PROJECTED ROWS THEMSELVES — every column,
                    including the display-only ones the store's content hash excludes and the
                    join-time ``selection_roles`` annotation the projection adds. It catches a
                    re-serialisation that changes bytes but not science, and it is what moves
                    when one cell of one projected row is edited.
``row_count``       how many rows this question projected. An added or deleted row moves it.
``schema_id``       the column contract this table was sealed under.

The two are about DIFFERENT SCOPES on purpose, and the field descriptions say so: a reader must
never think ``raw_sha256`` is a digest of the subset. It is the fingerprint of the bytes the
subset was drawn from, and the verifier uses it to prove the store it re-opens is the store this
view was projected from — before it proves, row by row, that every projected row is one of ITS
rows.

REORDER: A ROW SET IS A SET; THE ARM PAIR IS NOT
-----------------------------------------------
``content_sha256`` is ROW-ORDER-INVARIANT. That is not laziness: the view already guarantees
``row_order_is_by_content_id_and_is_not_a_ranking``, so permuting rows changes no science, and a
refusal that fired on it would be teaching the next reader to weaken the check. A DUPLICATED row
identity is refused, because a set cannot hold the same row twice and a duplicate double-counts
the evidence it carries.

``arm_evidence`` IS ORDERED, and its order is its meaning: index 0 is the arm the question moves
AWAY FROM (role ``away_from_A``), index 1 the arm it moves TOWARD (``toward_B``). A consumer that
reads positionally is reading the question's poles, so the ORDERED (arm_key, role) pairing is
sealed and a swap is refused BY NAME.

NEVER RECONCILE, NEVER ADOPT
----------------------------
A mismatch is a refusal. The recomputed value is never written back and never preferred: if the
rows and the seal disagree, WHICH ONE IS THE SCIENCE is exactly the question nobody can answer
afterwards.
"""
from __future__ import annotations

import os
from typing import Any, Mapping, Sequence

from . import artifacts_v2 as av2
from . import candidates_v2 as cv2
from . import pathway_context_v2 as pc2
from . import schemas
from .hashing import canonical_json, content_hash, file_sha256, table_hash, without
from .view_store import ROLE_COLUMN

PROJECTION_SEAL_SCHEMA = "spot.stage03_selection_view.projection_seal.v1"
PROJECTION_VERIFIER_ID = "spot.stage03.selection_view.projection_identity.v1"
TABLE_SCHEMA_PREFIX = "spot.stage03_selection_view.table."

# THE SCHEMA SET, BOUND EXACTLY — the digest EVERY bundle publishes as `method.schemas_sha256`,
# re-derived from the schema files on disk by `druglink.schemas.schemas_tree`.
#
# EXACT EQUALITY. NOT a substring, NOT a pattern, NOT a "looks-about-right" prefix. The v2 schema
# once carried `verifier_id: {pattern: "independent"}` on a report binding: it REFUSED every
# honest Stage-2 report (the real verifier is `spot.stage02.run_manifest.verifier.v1`, which
# contains no such substring) while ADMITTING any forgery that merely renamed ITSELF "…
# independent…". A name is not a binding and a substring is not an identity. That rule is dead,
# and its SHAPE may not come back here.
#
# The pin is compared against the digest re-derived from the files on disk, so a schema edit is a
# DELIBERATE re-pin (here and in tests/test_frozen_contract.py, which asserts the two agree) and
# never a silent follow.
#
# MOVED THIS ROUND, DELIBERATELY: 23559703… -> b19f26cb…. The selection-view schema now REQUIRES
# the projection seal, and a schema that does not require it cannot enforce it — the view's top
# level is `additionalProperties: false`, so the seal could not even be CARRIED without the move.
# `spot.stage03_drug_annotation.v1` (361d0833…), the generic contract Stage 4 binds to, is
# BYTE-IDENTICAL and did not budge.
PINNED_SCHEMAS_SHA256 = \
    "b19f26cb1992b1c4bf1cca74ab720e6b1cc219e8d540de1a0c422210c00810bf"

# The candidate's VIEW-SCOPED evidence, alongside (never instead of) the store's global fields.
VIEW_CANDIDATE_COLUMNS: tuple[str, ...] = (
    "view_arm_keys_by_origin", "view_n_edges_by_origin", "view_roles", "view_edge_ids",
    "view_stage3_evidence_classes", "view_directional_evidence_statuses",
    "view_observed_perturbation_support", "view_arm_ranks",
)

# EVERY column a projected row may carry. DERIVED from the producer's own column tuples
# (`candidates_v2` / `pathway_context_v2`), so the seal and the tables it seals cannot drift.
ROW_COLUMNS: dict[str, frozenset[str]] = {
    "arm_slots": frozenset(cv2.ARM_SLOT_COLUMNS) | {ROLE_COLUMN},
    "target_drug_edges": frozenset(cv2.EDGE_COLUMNS) | {ROLE_COLUMN},
    "arm_summaries": frozenset(cv2.ARM_SUMMARY_COLUMNS) | {ROLE_COLUMN},
    "candidates": frozenset(cv2.CANDIDATE_COLUMNS) | frozenset(VIEW_CANDIDATE_COLUMNS),
    "pathway_context": frozenset(pc2.CONTEXT_COLUMNS) | {ROLE_COLUMN},
    "source_records": frozenset(cv2.SOURCE_RECORD_COLUMNS),
    "dispositions": frozenset(cv2.DISPOSITION_COLUMNS) | {ROLE_COLUMN},
}
SEALED_TABLES: tuple[str, ...] = tuple(sorted(ROW_COLUMNS))

# The join-time annotations. Stripped to recover the STORE row a projected row must still be.
ANNOTATION_COLUMNS: frozenset[str] = frozenset({ROLE_COLUMN}) | frozenset(VIEW_CANDIDATE_COLUMNS)

# WHERE ORDER IS MEANING, and where it is not. Published in the view, because a consumer must be
# able to tell which of its lists it may safely re-sort.
ROW_ORDER_CARRIES_MEANING: dict[str, Any] = {
    "tables": False,
    "tables_reason": ("every projected table is ordered by CONTENT ID, which is not a ranking; a "
                      "row set is a SET and its content hash is row-order-invariant. A DUPLICATE "
                      "row identity is still refused: a set cannot hold the same row twice, and a "
                      "duplicate double-counts the evidence it carries"),
    "arm_evidence": True,
    "arm_evidence_reason": ("index 0 is the arm this question moves AWAY FROM (away_from_A) and "
                            "index 1 the arm it moves TOWARD (toward_B); a consumer that reads "
                            "positionally is reading the question's poles, so the ordered "
                            "(arm_key, role) pairing is sealed and a swap is refused"),
}

GATE_TABLE_NOT_SEALED = "a_projected_table_carries_no_identity_of_its_own"
GATE_SEALED_TABLE_NOT_PROJECTED = "the_seal_names_a_table_the_view_does_not_carry"
GATE_ROWS_ARE_NOT_THE_SEALED_ROWS = "the_projected_rows_are_not_the_rows_the_seal_names"
GATE_ROW_COUNT_MOVED = "the_projection_holds_a_different_number_of_rows_than_the_seal_names"
GATE_DUPLICATE_ROW = "the_projection_holds_the_same_row_identity_twice"
GATE_ORDERED_BLOCK_REORDERED = "the_ordered_arm_evidence_was_reordered_and_its_order_is_its_meaning"
GATE_SCHEMA_SET_DRIFT = "the_projection_was_sealed_under_a_different_schema_set"
GATE_SEAL_IDENTITY = "the_projection_seal_does_not_hash_to_the_identity_it_publishes"
GATE_VIEW_IDENTITY = "the_view_does_not_hash_to_the_identity_it_publishes"
GATE_STALE_RECEIPT = "the_receipt_presented_was_written_about_a_different_projection"

# The gates only a verifier WITH THE STORE ON DISK can run. Named here so the vocabulary is one
# vocabulary, and published in the view so a consumer can tell which gates a bare contract check
# did NOT run — an unenumerated gate is a gate nobody can notice the absence of.
GATE_STORE_TABLE_NOT_ON_DISK = "the_seal_names_a_store_table_that_is_not_on_disk"
GATE_RAW_BYTES_ARE_NOT_THE_STORES = "the_sealed_raw_bytes_are_not_the_store_table_bytes_on_disk"
GATE_ROW_IS_NOT_A_STORE_ROW = "a_projected_row_is_not_a_row_the_store_holds"


class ProjectionSealError(ValueError):
    """A named, fail-closed refusal. The projection does not leave, and is not consumed."""

    def __init__(self, gate: str, message: str) -> None:
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


def _refuse(gate: str, message: str) -> None:
    raise ProjectionSealError(gate, message)


# --------------------------------------------------------------------------- #
# 1. The identity of ONE projected table.
# --------------------------------------------------------------------------- #
def table_schema_id(name: str) -> str:
    return f"{TABLE_SCHEMA_PREFIX}{name}.v1"


def schema_set_digest() -> str:
    """The COLUMN contract of every projected table. An added, renamed or dropped column moves
    it — which is schema-set drift, and it is a refusal rather than a surprise downstream."""
    return content_hash({name: sorted(cols) for name, cols in sorted(ROW_COLUMNS.items())})


def projected_content_hash(name: str, rows: Sequence[Mapping[str, Any]]) -> str:
    """The canonical content of the PROJECTED ROWS. Every column: the display-only ones the
    store's content hash excludes (a mislabelled symbol still reaches a rendered page) and the
    join-time role annotation (it is part of the answer this question was given).

    ROW-ORDER-INVARIANT, by the same total order the store uses. A permutation is not a finding.
    """
    return table_hash([dict(r) for r in rows], av2.TABLES[name][1])


def _row_identity(name: str, row: Mapping[str, Any]) -> str:
    return canonical_json([row.get(k) for k in av2.TABLES[name][1]])


def _check_no_duplicates(name: str, rows: Sequence[Mapping[str, Any]]) -> None:
    seen: set[str] = set()
    for row in rows:
        ident = _row_identity(name, row)
        if ident in seen:
            _refuse(GATE_DUPLICATE_ROW,
                    f"the projected table {name!r} holds the row identity {ident} twice. A row "
                    "set is a SET: the same row projected twice double-counts every piece of "
                    "evidence it carries, and a consumer counting rows would read one measurement "
                    "as two.")
        seen.add(ident)


def table_identity(name: str, rows: Sequence[Mapping[str, Any]], *,
                   bundle_dir: str) -> dict[str, Any]:
    """EXACT identity for one projected table. Raw AND canonical; they fail differently."""
    path = os.path.join(bundle_dir, f"{name}.parquet")
    if not os.path.isfile(path):
        _refuse(GATE_STORE_TABLE_NOT_ON_DISK,
                f"the projection would seal {name!r}, but the store has no {name}.parquet. A "
                "projection OF nothing is not a projection, and a seal over bytes that are not "
                "there names nothing.")
    _check_no_duplicates(name, rows)
    return {
        "schema_id": table_schema_id(name),
        "row_count": len(rows),
        # The PROJECTED rows — the subset in this view, every column.
        "content_sha256": projected_content_hash(name, rows),
        # The STORE table's RAW FILE BYTES — the bytes this subset was drawn FROM.
        "raw_sha256": file_sha256(path),
    }


def arm_evidence_order_hash(arm_evidence: Sequence[Mapping[str, Any]]) -> str:
    """The ORDERED (arm_key, role) pairing. Index 0 is A, index 1 is B — and that IS the science:
    swap them and the question is asking to move away from the arm it meant to move toward."""
    return content_hash([[str(a.get("arm_key")), str(a.get("role"))] for a in arm_evidence])


# --------------------------------------------------------------------------- #
# 2. THE SEAL. Built by the producer, over the rows it actually projected.
# --------------------------------------------------------------------------- #
def seal(*, view_rows: Mapping[str, Sequence[Mapping[str, Any]]],
         arm_evidence: Sequence[Mapping[str, Any]], bundle_dir: str) -> dict[str, Any]:
    """The projection's own identity. Bound INSIDE the view id, so a re-seal moves the view."""
    missing = sorted(set(SEALED_TABLES) - set(view_rows))
    if missing:
        _refuse(GATE_TABLE_NOT_SEALED,
                f"the projection is missing table(s) {missing}; it projects exactly "
                f"{list(SEALED_TABLES)}. A table nobody sealed is a table anybody can edit, and "
                "Stage 4 reads the projected rows.")

    block: dict[str, Any] = {
        "projection_seal_schema": PROJECTION_SEAL_SCHEMA,
        "projection_verifier_id": PROJECTION_VERIFIER_ID,
        "projection_checks": checks(),
        "projection_disk_checks": disk_checks(),
        "schemas_sha256": bound_schemas_sha256(),
        "projection_schema_set_sha256": schema_set_digest(),
        "n_tables_sealed": len(SEALED_TABLES),
        "tables": {name: table_identity(name, view_rows[name], bundle_dir=bundle_dir)
                   for name in SEALED_TABLES},
        "arm_evidence_order_sha256": arm_evidence_order_hash(arm_evidence),
        "row_order_carries_meaning": dict(ROW_ORDER_CARRIES_MEANING),
        "the_projected_rows_carry_an_identity_of_their_own_not_the_global_stores": True,
        "the_seal_is_never_reconciled_with_the_rows_a_mismatch_is_a_refusal": True,
    }
    block["projection_sha256"] = content_hash(block)
    return block


def bound_schemas_sha256() -> str:
    """The schema set, RE-DERIVED from the files on disk and required to EQUAL the pin.

    Two independent statements of the same fact. If a schema file moves, the re-derivation and
    the pin diverge and this REFUSES — so unfreezing is a deliberate act (re-hash, hand the value
    to the Stage-4 / W12 owners, re-pin) and never a number that quietly followed an edit.
    """
    derived = schemas.schemas_tree()["schemas_sha256"]
    if derived != PINNED_SCHEMAS_SHA256:
        _refuse(GATE_SCHEMA_SET_DRIFT,
                f"the schema files on disk hash to {derived} but the pinned schema set is "
                f"{PINNED_SCHEMAS_SHA256}. The pin is compared EXACTLY — never by substring and "
                "never by pattern. If the schema move is intended: re-hash, hand the new digest "
                "to the Stage-4 (W6) and frontend (W12) owners, and re-pin here and in "
                "tests/test_frozen_contract.py, in that order.")
    return derived


# --------------------------------------------------------------------------- #
# 3. THE CHECK. Re-derived from the view's OWN rows. No disk; refuses a post-seal edit.
# --------------------------------------------------------------------------- #
def check(view: Mapping[str, Any]) -> None:
    """Every sealed value RECOMPUTED from the rows the view actually ships, and compared.

    This is the gate the audit's attack walks into: mutate one cell of one projected row after
    the view was sealed, and the recomputed ``content_sha256`` for that table no longer equals
    the one the seal names. REFUSED, by name, naming the table.

    It runs WITHOUT the store on disk, so it is the gate that can travel with the bytes. It
    cannot re-derive ``raw_sha256`` (that needs the parquet) — the on-disk verifier does, and the
    gates it adds are enumerated in ``projection_disk_checks`` so nobody can mistake a contract
    check for a full verification.
    """
    block = view.get("projection")
    if not isinstance(block, Mapping) or not block.get("tables"):
        _refuse(GATE_TABLE_NOT_SEALED,
                "the view carries no projection seal. Its tables are then a BARE ROW LIST: the "
                "store's table_hashes describe the GLOBAL STORE, not this subset, so a cell "
                "edited after sealing would leave every hash in the document mutually consistent "
                "and reach Stage 4 unnoticed.")

    _check_schema_set(block)
    _check_tables(view, block)
    _check_ordered_blocks(view, block)
    _check_seal_identity(block)
    _check_receipts(view, block)
    _check_view_identity(view)


def _check_schema_set(block: Mapping[str, Any]) -> None:
    for field, got in (("schemas_sha256", bound_schemas_sha256()),
                       ("projection_schema_set_sha256", schema_set_digest()),
                       ("projection_seal_schema", PROJECTION_SEAL_SCHEMA),
                       ("projection_verifier_id", PROJECTION_VERIFIER_ID),
                       ("n_tables_sealed", len(SEALED_TABLES))):
        if block.get(field) != got:
            _refuse(GATE_SCHEMA_SET_DRIFT,
                    f"the seal declares {field}={str(block.get(field))[:24]!r} but this code "
                    f"derives {str(got)[:24]!r}. The projection was sealed under a DIFFERENT "
                    "contract than the one reading it, so the columns a consumer expects and the "
                    "columns it is handed are not the same columns. Compared EXACTLY: no "
                    "substring rule, no pattern.")


def _check_tables(view: Mapping[str, Any], block: Mapping[str, Any]) -> None:
    tables = view.get("tables") or {}
    sealed = block.get("tables") or {}

    for name in SEALED_TABLES:
        if name not in tables:
            _refuse(GATE_SEALED_TABLE_NOT_PROJECTED,
                    f"the seal names {name!r} but the view carries no such table. A table that "
                    "vanished between the seal and the consumer is a dropped row set, and a "
                    "dropped row is indistinguishable from a row nobody found.")
        if name not in sealed:
            _refuse(GATE_TABLE_NOT_SEALED,
                    f"the view ships the table {name!r} with no identity of its own. Its rows "
                    "are what Stage 4 reads, and nothing in the document is about them.")

    for name in sorted(set(tables) - set(sealed)):
        _refuse(GATE_TABLE_NOT_SEALED,
                f"the view ships an UNSEALED table {name!r}; the seal covers exactly "
                f"{list(SEALED_TABLES)}.")

    for name in SEALED_TABLES:
        rows, want = list(tables[name]), sealed[name]
        _check_no_duplicates(name, rows)

        if len(rows) != want.get("row_count"):
            _refuse(GATE_ROW_COUNT_MOVED,
                    f"the projected table {name!r} holds {len(rows)} rows; the seal names "
                    f"{want.get('row_count')}. A row was ADDED or DELETED after the view was "
                    "sealed — and an added row is evidence nobody produced, while a deleted one "
                    "is evidence nobody can miss.")

        if want.get("schema_id") != table_schema_id(name):
            _refuse(GATE_SCHEMA_SET_DRIFT,
                    f"the projected table {name!r} is sealed under schema_id "
                    f"{want.get('schema_id')!r}, but this contract emits "
                    f"{table_schema_id(name)!r}.")

        got = projected_content_hash(name, rows)
        if got != want.get("content_sha256"):
            _refuse(GATE_ROWS_ARE_NOT_THE_SEALED_ROWS,
                    f"the projected table {name!r} hashes to {got[:16]}… but the seal names "
                    f"{str(want.get('content_sha256'))[:16]}…. A cell of a row this question "
                    "SHIPS was changed after the view was sealed. The store's own digest is still "
                    "honest — the store was never touched — which is exactly why nothing else "
                    "notices. The mismatch is NOT reconciled and the recomputed hash is NOT "
                    "adopted: which of the two is the science is the question nobody can answer "
                    "after the fact.")


def _check_ordered_blocks(view: Mapping[str, Any], block: Mapping[str, Any]) -> None:
    got = arm_evidence_order_hash(list(view.get("arm_evidence") or ()))
    if got != block.get("arm_evidence_order_sha256"):
        _refuse(GATE_ORDERED_BLOCK_REORDERED,
                f"the ordered arm_evidence hashes to {got[:16]}… but the seal names "
                f"{str(block.get('arm_evidence_order_sha256'))[:16]}…. Unlike a row set, THIS "
                "order is meaning: index 0 is the arm the question moves AWAY FROM and index 1 "
                "the arm it moves TOWARD. Reordered or re-roled, the view answers a question "
                "nobody asked — with the poles of the one they did.")
    if block.get("row_order_carries_meaning") != ROW_ORDER_CARRIES_MEANING:
        _refuse(GATE_SCHEMA_SET_DRIFT,
                "the seal's statement of WHERE ORDER CARRIES MEANING is not this contract's. A "
                "consumer reads it to decide which of its lists it may re-sort.")


def _check_seal_identity(block: Mapping[str, Any]) -> None:
    got = content_hash(without(dict(block), ("projection_sha256",)))
    if got != block.get("projection_sha256"):
        _refuse(GATE_SEAL_IDENTITY,
                f"the seal publishes projection_sha256="
                f"{str(block.get('projection_sha256'))[:16]}… but its own content hashes to "
                f"{got[:16]}…. A seal edited after it was addressed vouches for bytes that no "
                "longer exist — and it is the first thing an attacker who understood the check "
                "would rewrite.")


def _check_receipts(view: Mapping[str, Any], block: Mapping[str, Any]) -> None:
    """The store receipt and the aggregate receipt must be about THIS projection.

    A receipt is a statement about specific bytes. Lifted from another view — a different
    question over the same store, or the same question over a different one — it is a receipt for
    a projection nobody made, and it would travel with an authority it never had.
    """
    seal_id = block.get("projection_sha256")
    for where in ("store", "admission"):
        got = (view.get(where) or {}).get("projection_sha256")
        if got != seal_id:
            _refuse(GATE_STALE_RECEIPT,
                    f"the {where} receipt binds projection {str(got)[:16]}…, but the projection "
                    f"presented seals to {str(seal_id)[:16]}…. The receipt was written about a "
                    "DIFFERENT view: it admits rows this document does not carry, and the rows "
                    "this document does carry were admitted by nobody.")


def _check_view_identity(view: Mapping[str, Any]) -> None:
    base = without(dict(view), ("view_id", "view_content_sha256"))
    content = content_hash(base)
    if content != view.get("view_content_sha256") or content[:16] != view.get("view_id"):
        _refuse(GATE_VIEW_IDENTITY,
                f"the view publishes view_id={view.get('view_id')!r} / view_content_sha256="
                f"{str(view.get('view_content_sha256'))[:16]}…, but its own content hashes to "
                f"{content[:16]}…. The document was edited after it was addressed, so its id is "
                "about bytes that no longer exist.")


# --------------------------------------------------------------------------- #
# 4. What the seal PROMISES, and which gates it ran.
# --------------------------------------------------------------------------- #
def checks() -> list[str]:
    """The gates a CONTRACT check runs — with the bytes alone, anywhere they travel."""
    return sorted((GATE_DUPLICATE_ROW, GATE_ORDERED_BLOCK_REORDERED, GATE_ROWS_ARE_NOT_THE_SEALED_ROWS,
                   GATE_ROW_COUNT_MOVED, GATE_SCHEMA_SET_DRIFT, GATE_SEALED_TABLE_NOT_PROJECTED,
                   GATE_SEAL_IDENTITY, GATE_STALE_RECEIPT, GATE_TABLE_NOT_SEALED,
                   GATE_VIEW_IDENTITY))


def disk_checks() -> list[str]:
    """The gates only a verifier HOLDING THE STORE can run. Enumerated in the view, because a
    consumer must be able to tell a contract check from a full verification — and a gate nobody
    can name is a gate nobody can notice the absence of."""
    return sorted((GATE_RAW_BYTES_ARE_NOT_THE_STORES, GATE_ROW_IS_NOT_A_STORE_ROW,
                   GATE_STORE_TABLE_NOT_ON_DISK))


def guarantees() -> dict[str, Any]:
    """Bound into the view id, so revoking one moves every id that ever carried it."""
    return {
        "every_projected_table_carries_its_own_raw_and_canonical_identity": True,
        "the_projected_rows_are_re_hashed_before_the_view_is_admitted_never_copied": True,
        "a_single_cell_edited_after_sealing_is_refused_by_name": True,
        "a_row_set_is_a_set_and_a_reorder_is_not_a_finding_but_a_duplicate_is_refused": True,
        "the_arm_evidence_order_is_meaning_and_a_swap_of_the_poles_is_refused": True,
        "a_receipt_that_was_written_about_another_projection_is_refused": True,
    }


def vocabularies() -> dict[str, Any]:
    return {
        "projection_seal_schema": PROJECTION_SEAL_SCHEMA,
        "projection_verifier_id": PROJECTION_VERIFIER_ID,
        "sealed_tables": list(SEALED_TABLES),
        "table_schema_ids": {name: table_schema_id(name) for name in SEALED_TABLES},
        "projection_schema_set_sha256": schema_set_digest(),
        "annotation_columns": sorted(ANNOTATION_COLUMNS),
        "row_order_carries_meaning": dict(ROW_ORDER_CARRIES_MEANING),
        "checks": checks(),
        "disk_checks": disk_checks(),
        **guarantees(),
    }
