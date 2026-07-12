"""The source-record table: contributor evidence RESOLVED, not asserted.

A contributor manifest row says "estimate E's guide is G, and record R in source S
proves it". Hash-pinning S proves only that S's bytes are what they claimed to be. It
does not prove that R exists in S, nor that R says anything about E and G.

So every determined manifest row is RESOLVED here:

  * ``source_record_id`` must exist in a hash-pinned source-record table;
  * every record's id is RE-DERIVED from its own canonical payload under the ONE
    compiled rule (``record_id.py``) — prefix ``srcrec:sha256:``, the full 64-hex
    digest, and a payload that INCLUDES the complete offset and row-name proof. A
    record whose offsets move gets a new id, so its citations stop resolving;
  * the resolved record must match the FULL released-estimate key — the estimate
    (estimate_type, estimate_id, condition, donor_pair) AND the whole released target
    identity (released_estimate_id, target_id, target_id_namespace, target_symbol,
    target_ensembl);
  * it must carry the same guide identity, the same identity method, and the same
    source id + source hash the manifest row claims;
  * and it must do so UNIQUELY: one (full key, guide) pair, one record.

The manifest row does not re-derive the id it cites — it cannot, because the payload
now binds the offset proof, which lives in the table. It does not need to: a row can
only resolve against a record that matches its ENTIRE key and guide, so it can never
borrow another estimate's evidence, and the record's own id binds the evidence to the
record. The completeness of that evidence is then decided against the RAW source by
the replay/completeness report (``replay.py``), never by the table agreeing with the
manifest.

EVERY record carries the all-offset proof. Not "all or none": a table where one record
omits it is a table with an unproven record in it.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from . import identity, record_id
from .record_id import (OFFSETS_FIELD, RECORD_ID_PREFIX, ROWS_FIELD,  # noqa: F401
                        RULE_METADATA, RULE_METADATA_KEY, derive_record_id)

# v2: the record id binds the completeness proof, and the proof is mandatory.
SCHEMA_VERSION = "spot.stage02_source_records.v2"
SUPERSEDED_SCHEMA_VERSIONS = ("spot.stage02_source_records.v1",
                              "spot.stage02_source_records.target_id_proposal.v1")

# The full key a record must reproduce: the estimate AND the whole released target
# identity. Nothing may be omitted, and no field may stand in for another.
ESTIMATE_KEY = ("estimate_type", "estimate_id", "released_estimate_id",
                "target_id", "target_id_namespace", "target_symbol",
                "target_ensembl", "condition", "donor_pair")
GUIDE_FIELDS = ("guide_id", "identity_method", "source_id", "source_sha256")
# ``source_row_index`` is the LOCATOR — the one row replay checks first. The offset
# and row-name arrays are the COMPLETE proof: every kept raw row for this record's
# (target, condition, guide). Both are required on every record.
LOCATOR_FIELDS = ("source_row_index", OFFSETS_FIELD, ROWS_FIELD)
REQUIRED_RECORD_COLUMNS = (("source_record_id",) + ESTIMATE_KEY + GUIDE_FIELDS
                           + LOCATOR_FIELDS)

RESOLVED = "resolved"
# A compact rule ID, not a paragraph: the emitted artifact carries enums, counts and
# hashes. What the rule means is stated once, in this module's docstring.
RESOLUTION_RULE_ID = "spot.stage02.direct.evidence_resolution.full_scope_1to1.v2"
# Refusal reasons (each emitted; never collapsed).
RECORD_NOT_FOUND = "source_record_id_not_found_in_source"
RECORD_KEY_MISMATCH = "source_record_does_not_match_estimate_key"
RECORD_GUIDE_MISMATCH = "source_record_guide_identity_mismatch"
RECORD_METHOD_MISMATCH = "source_record_identity_method_mismatch"
RECORD_SOURCE_MISMATCH = "source_record_source_id_mismatch"
RECORD_HASH_MISMATCH = "source_record_source_hash_mismatch"
RECORD_ID_NOT_DERIVED = "source_record_id_is_not_derived_from_its_own_payload"
BAD_ID_SHAPE = "source_record_id_is_not_shaped_by_the_compiled_rule"
BAD_LOCATOR = "source_row_index_is_not_a_non_negative_integer"
BAD_OFFSET_PROOF = "pseudobulk_source_offsets_is_not_a_complete_offset_proof"
BAD_ROW_PROOF = "pseudobulk_source_rows_does_not_match_the_offset_proof"
LOCATOR_NOT_IN_PROOF = "source_row_index_is_not_one_of_the_records_own_offsets"
RULE_METADATA_MISMATCH = "table_rule_metadata_is_not_the_compiled_record_id_rule"
ORPHAN_RECORD = "source_record_is_cited_by_no_determined_manifest_row"
DUPLICATE_RECORD_ID = "duplicate_source_record_id"
DUPLICATE_RECORD_KEY = "duplicate_source_record_estimate_key_and_guide"
TABLE_ABSENT = "source_record_table_absent"


class SourceRecordError(ValueError):
    """The source-record table is unusable, or a cited record does not resolve."""


def _require(cond: bool, msg: str) -> None:
    if not cond:
        raise SourceRecordError(msg)


def _nullish(v: Any) -> bool:
    return v is None or str(v).strip().lower() in ("", "none", "nan", "null")


def _norm(v: Any) -> Optional[str]:
    return None if _nullish(v) else str(v)


def _check_offset_proof(rec: dict[str, Any], i: int) -> None:
    """The record's own completeness proof must be well formed. EVERY record.

    Whether the offsets are the RIGHT rows is decided against the raw source by
    replay; whether they are a coherent proof at all is decided here.
    """
    offsets = rec.get(OFFSETS_FIELD)
    _require(isinstance(offsets, list) and bool(offsets),
             f"source-record table row {i}: {BAD_OFFSET_PROOF} — {OFFSETS_FIELD!r} "
             f"must be a non-empty list, got {type(offsets).__name__}. A record with "
             "no offset proof claims a contributor it never showed the rows for")
    for x in offsets:
        _require(isinstance(x, int) and not isinstance(x, bool) and x >= 0,
                 f"source-record table row {i}: {BAD_OFFSET_PROOF} — offset {x!r} is "
                 "not a non-negative integer row index")
    _require(len(set(offsets)) == len(offsets),
             f"source-record table row {i}: {BAD_OFFSET_PROOF} — duplicate offsets; "
             "the same raw row cannot be counted twice")
    _require(list(offsets) == sorted(offsets),
             f"source-record table row {i}: {BAD_OFFSET_PROOF} — offsets are not in "
             "ascending order; the proof's ORDER is part of the hashed identity, so "
             "a reordered proof is a different, unverified claim")

    rows = rec.get(ROWS_FIELD)
    _require(isinstance(rows, list) and len(rows) == len(offsets),
             f"source-record table row {i}: {BAD_ROW_PROOF} — {ROWS_FIELD!r} must "
             f"name exactly one raw row per offset (got "
             f"{len(rows) if isinstance(rows, list) else type(rows).__name__} for "
             f"{len(offsets)} offset(s))")
    for x in rows:
        _require(isinstance(x, str) and x.strip() != "",
                 f"source-record table row {i}: {BAD_ROW_PROOF} — row name {x!r} is "
                 "not a non-empty string")

    locator = rec.get("source_row_index")
    _require(isinstance(locator, int) and not isinstance(locator, bool)
             and locator >= 0,
             f"source-record table row {i}: {BAD_LOCATOR} (got {locator!r})")
    _require(locator in offsets,
             f"source-record table row {i}: {LOCATOR_NOT_IN_PROOF} — the locator "
             f"{locator!r} is not among the record's own offsets {offsets!r}")


def load_table(path: Optional[str]) -> dict[str, dict[str, Any]]:
    """Load and index the hash-pinned source-record table by ``source_record_id``.

    The table's declared identity rule is machine-validated against the compiled rule
    BEFORE a single record is indexed: a table that states one rule while its producer
    implemented another is refused, not reconciled.
    """
    _require(bool(path) and os.path.exists(str(path)),
             "contributor evidence: the source-record table is absent; a manifest "
             "assertion is not evidence")
    with open(str(path)) as fh:
        doc = json.load(fh)
    _require(isinstance(doc, dict), "source-record table: malformed document")

    declared_schema = str(doc.get("schema_version", ""))
    _require(declared_schema not in SUPERSEDED_SCHEMA_VERSIONS,
             f"source-record table: schema_version {declared_schema!r} is SUPERSEDED. "
             "Its record ids were minted under the obsolete rule (a truncated digest "
             "over a payload that omitted the offset proof), so its offsets could be "
             "swapped without changing a single id. Re-issue the table under "
             f"{SCHEMA_VERSION!r}; superseded ids are never grandfathered")
    _require(declared_schema == SCHEMA_VERSION,
             f"source-record table: schema_version must be exactly "
             f"{SCHEMA_VERSION!r}, got {declared_schema!r}")

    # THE RULE, machine-validated. A rule nobody checks is documentation.
    violation = record_id.rule_metadata_violation(doc.get(RULE_METADATA_KEY))
    _require(violation is None,
             f"source-record table: {RULE_METADATA_MISMATCH} ({violation}). The table "
             "must declare the SAME identity rule the verifier compiles, including "
             "the payload field list — that list is what decides whether the "
             "completeness proof is bound into the record id at all")

    rows = doc.get("records")
    _require(isinstance(rows, list) and bool(rows),
             "source-record table: 'records' must be a non-empty list")

    index: dict[str, dict[str, Any]] = {}
    by_key: dict[tuple, str] = {}
    for i, rec in enumerate(rows):
        missing = [c for c in REQUIRED_RECORD_COLUMNS if c not in rec]
        _require(not missing,
                 f"source-record table row {i}: missing columns {missing}")
        rid = _norm(rec["source_record_id"])
        _require(rid is not None,
                 f"source-record table row {i}: null source_record_id")

        shape = record_id.id_shape_violation(rid)
        _require(shape is None,
                 f"source-record table row {i}: {BAD_ID_SHAPE} ({shape}); got "
                 f"{rid!r}")
        _require(rid not in index,
                 f"source-record table: {DUPLICATE_RECORD_ID} {rid!r}")

        # A record is EVIDENCE about a released target. It obeys the same identity
        # contract the manifest does: a record that promotes an ENSG-looking release
        # key into target_ensembl is not evidence, it is the forgery.
        violation = identity.identity_violation(rec)
        _require(violation is None,
                 f"source-record table row {i}: inadmissible target identity "
                 f"({violation}); target_id={rec.get('target_id')!r} "
                 f"namespace={rec.get('target_id_namespace')!r} "
                 f"target_ensembl={rec.get('target_ensembl')!r}")

        # The COMPLETE proof, on every record — checked before the id, because the id
        # is a hash OF the proof and a malformed proof cannot be hashed meaningfully.
        _check_offset_proof(rec, i)

        # The id is RE-DERIVED from the record's own full payload, never believed.
        # Because that payload holds the offsets and row names, a record whose proof
        # was edited cannot keep its id — and every citation of the old id dies.
        derived = derive_record_id(rec)
        _require(rid == derived,
                 f"source-record table row {i}: {RECORD_ID_NOT_DERIVED} — declares "
                 f"{rid!r} but its own payload (identity AND offset/row proof) "
                 f"derives {derived!r}")

        # 1:1. Two records for one (key, guide) means a citation could resolve to
        # either, and "either" is not a proof.
        key = tuple(_norm(rec.get(f)) for f in ESTIMATE_KEY) + \
            (_norm(rec.get("guide_id")),)
        _require(key not in by_key,
                 f"source-record table row {i}: {DUPLICATE_RECORD_KEY} — records "
                 f"{by_key.get(key)!r} and {rid!r} both claim {key}")
        by_key[key] = rid
        index[rid] = rec
    return index


def resolve_row(row: dict[str, Any], table: dict[str, dict[str, Any]],
                source_shas: dict[str, str]) -> Optional[str]:
    """Resolve ONE determined manifest row against the source-record table.

    Returns None when the row resolves, else the exact refusal reason. The row cannot
    recompute the id it cites (the payload binds the offset proof, which lives in the
    table), so borrowing is refused a different way: the record must match the row's
    ENTIRE released scope key and guide, and the table is 1:1 on that key.
    """
    rid = _norm(row.get("source_record_id"))
    if rid is None:
        return RECORD_NOT_FOUND
    if record_id.id_shape_violation(rid) is not None:
        return BAD_ID_SHAPE
    if rid not in table:
        return RECORD_NOT_FOUND

    rec = table[rid]
    for field in ESTIMATE_KEY:
        if _norm(rec.get(field)) != _norm(row.get(field)):
            return RECORD_KEY_MISMATCH
    if _norm(rec.get("guide_id")) != _norm(row.get("guide_id")):
        return RECORD_GUIDE_MISMATCH
    if _norm(rec.get("identity_method")) != _norm(row.get("identity_method")):
        return RECORD_METHOD_MISMATCH

    src = _norm(rec.get("source_id"))
    if src != _norm(row.get("source_id")):
        return RECORD_SOURCE_MISMATCH
    # BOTH the row's and the RECORD's own source hash must be the pinned bytes.
    pinned = source_shas.get(str(src))
    if pinned is None or str(row.get("source_sha256", "")).lower() != pinned \
            or str(rec.get("source_sha256", "")).lower() != pinned:
        return RECORD_HASH_MISMATCH
    return None


def resolve_manifest(rows: list[dict[str, Any]], table: dict[str, dict[str, Any]],
                     source_shas: dict[str, str],
                     determined_state: str = "determined") -> dict[str, Any]:
    """Resolve every determined row. Any unresolved row is FATAL.

    An unresolvable citation is not downgraded to "ambiguous": the manifest claimed
    evidence it does not have, so the whole manifest is refused.
    """
    failures: list[dict[str, Any]] = []
    cited: set[str] = set()
    n_resolved = 0
    for i, row in enumerate(rows):
        if str(row.get("evidence_state", determined_state)) != determined_state:
            continue
        excluded = row.get("included", True) in (False, "false", "False", 0)
        if excluded and _norm(row.get("source_record_id")) is None:
            # An excluded row that cites nothing claims nothing. But an excluded row
            # that DOES cite a record is still making a claim, and it is checked:
            # an unchecked citation is exactly where a fabrication would hide.
            continue
        reason = resolve_row(row, table, source_shas)
        if reason is None:
            n_resolved += 1
            cited.add(_norm(row.get("source_record_id")))
        else:
            failures.append({"row": i, "source_record_id":
                             row.get("source_record_id"), "reason": reason})

    if failures:
        raise SourceRecordError(
            f"contributor evidence: {len(failures)} determined row(s) do not "
            f"resolve to a source record (first: {failures[0]})")

    # An ORPHAN record is evidence for a claim nobody made. The table must be
    # exactly the evidence the manifest cites — no more, no less.
    orphans = sorted(set(table) - cited)
    if orphans:
        raise SourceRecordError(
            f"contributor evidence: {ORPHAN_RECORD} — {len(orphans)} source "
            f"record(s) are cited by no determined manifest row "
            f"(first: {orphans[0]!r})")
    return {
        "status": RESOLVED,
        "schema_version": SCHEMA_VERSION,
        "resolution_rule_id": RESOLUTION_RULE_ID,
        "n_determined_rows_resolved": n_resolved,
        "n_source_records": len(table),
    }
