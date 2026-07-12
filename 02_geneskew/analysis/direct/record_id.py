"""THE source-record identity rule — one compiled rule, no compatibility exception.

A source record's id must be a function of the WHOLE claim it makes, including the
proof. The superseded rule (``srec-`` + a 32-hex truncation of a payload that omitted
``pseudobulk_source_offsets`` / ``pseudobulk_source_rows``) failed that on three
counts, and the third is the dangerous one:

  * the prefix was ``srec-``, not the declared ``srcrec:sha256:``;
  * the digest was truncated to 32 hex characters, not the full SHA-256;
  * the hashed payload OMITTED the offset and row-name arrays. So the all-offset
    completeness proof was never bound into the record's identity: a producer could
    swap a record's offsets and row names for a different, smaller or fabricated set
    and EVERY id would still re-derive perfectly. The id certified the claim while
    leaving the evidence for that claim free to move.

An emitted table and a runtime that agree with each other under the same obsolete
algorithm have proved nothing. This module compiles the declared rule ONCE:

    source_record_id = 'srcrec:sha256:' + sha256( canonical_json(identity_payload) )

over the full identity payload, offsets and row names included, and the table's own
declared rule metadata is machine-validated against it (``rule_metadata_violation``).
A table whose stated rule is not this rule is refused before a single record is
indexed — a rule nobody checks is documentation, not a contract.

Ids under the superseded rule are NEVER grandfathered: they are re-issued
(``reissue.py``) and every manifest citation is rewritten with them.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

# The rule, exactly as the schema declares it.
RECORD_ID_PREFIX = "srcrec:sha256:"
SHA256_HEX_LEN = 64                      # the FULL digest; a truncation is not the id

# The all-offset completeness proof. In the payload BY CONTRACT: the id must change
# when the evidence changes.
OFFSETS_FIELD = "pseudobulk_source_offsets"
ROWS_FIELD = "pseudobulk_source_rows"
PROOF_FIELDS = (OFFSETS_FIELD, ROWS_FIELD)

# Every identity AND proof field, in the declared order.
IDENTITY_PAYLOAD_FIELDS = (
    "estimate_type", "estimate_id", "released_estimate_id", "target_id",
    "target_id_namespace", "target_ensembl", "target_symbol", "condition",
    "donor_pair", "guide_id", "identity_method", "source_id", "source_sha256",
    OFFSETS_FIELD, ROWS_FIELD,
)

CANONICAL_JSON_RULE = ("json.dumps(obj, sort_keys=True, ensure_ascii=False, "
                       "separators=(',',':'), allow_nan=False) encoded UTF-8")
NULL_HANDLING = ("target_ensembl and donor_pair serialize as JSON null when absent; "
                 "they are part of the hashed payload.")
RULE = ("source_record_id = 'srcrec:sha256:' + sha256( "
        "canonical_json(identity_payload) )")

# What a v2 source-record table MUST declare, byte for byte. Compiled from the
# constants above so the metadata cannot drift away from the code that enforces it.
RULE_METADATA = {
    "canonical_json": CANONICAL_JSON_RULE,
    "identity_payload_fields": list(IDENTITY_PAYLOAD_FIELDS),
    "null_handling": NULL_HANDLING,
    "rule": RULE,
}
RULE_METADATA_KEY = "canonical_source_record_id_rule"

# The superseded rule. Named ONLY so its residue can be recognised and refused.
SUPERSEDED_ID_PREFIX = "srec-"
SUPERSEDED_ID_LEN = 32

_NULLISH = frozenset({"", "none", "nan", "null", "na", "<na>"})


class RecordIdError(ValueError):
    """The record-identity rule is not the compiled rule. Refuse; never coerce."""


def is_nullish(v: Any) -> bool:
    return v is None or str(v).strip().lower() in _NULLISH


def canonical_payload_json(payload: dict[str, Any]) -> str:
    """The declared canonical form. ``ensure_ascii=False``, exactly as stated."""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False,
                      separators=(",", ":"), allow_nan=False)


def _scalar(v: Any) -> Optional[str]:
    return None if is_nullish(v) else str(v)


def _offsets(v: Any) -> list[int]:
    """The offset array, as integers. A malformed offset is not a proof."""
    if not isinstance(v, list):
        raise RecordIdError(
            f"source record: {OFFSETS_FIELD!r} must be a list of source row "
            f"offsets, got {type(v).__name__}; a record with no complete offset "
            "proof cannot be identified, because its id binds that proof")
    out: list[int] = []
    for x in v:
        if not isinstance(x, int) or isinstance(x, bool):
            raise RecordIdError(
                f"source record: {OFFSETS_FIELD!r} holds a non-integer offset "
                f"{x!r}; an offset is a row index into the pinned raw source")
        out.append(int(x))
    return out


def _rows(v: Any) -> list[str]:
    if not isinstance(v, list):
        raise RecordIdError(
            f"source record: {ROWS_FIELD!r} must be a list of source row names, "
            f"got {type(v).__name__}")
    return [str(x) for x in v]


def identity_payload(rec: dict[str, Any]) -> dict[str, Any]:
    """The EXACT payload the id is taken over: identity and proof, nothing else."""
    payload: dict[str, Any] = {}
    for field in IDENTITY_PAYLOAD_FIELDS:
        if field == OFFSETS_FIELD:
            payload[field] = _offsets(rec.get(field))
        elif field == ROWS_FIELD:
            payload[field] = _rows(rec.get(field))
        else:
            payload[field] = _scalar(rec.get(field))
    return payload


def derive_record_id(rec: dict[str, Any]) -> str:
    """THE record id: prefix + the FULL sha256 of the canonical identity payload.

    Because the offsets and row names are inside the payload, re-issuing a record
    with a different contributor-row set necessarily re-issues its id — and every
    manifest citation that named the old id then fails to resolve.
    """
    blob = canonical_payload_json(identity_payload(rec)).encode("utf-8")
    return RECORD_ID_PREFIX + hashlib.sha256(blob).hexdigest()


def id_shape_violation(rid: Any) -> Optional[str]:
    """Why this string is not a well-formed record id under the compiled rule."""
    if is_nullish(rid):
        return "source_record_id_is_null"
    rid = str(rid)
    if rid.startswith(SUPERSEDED_ID_PREFIX):
        return "source_record_id_uses_the_superseded_srec_prefix"
    if not rid.startswith(RECORD_ID_PREFIX):
        return "source_record_id_does_not_carry_the_srcrec_sha256_prefix"
    digest = rid[len(RECORD_ID_PREFIX):]
    if len(digest) != SHA256_HEX_LEN:
        return ("source_record_id_digest_is_not_a_full_sha256_"
                f"(len={len(digest)}, expected {SHA256_HEX_LEN})")
    if any(c not in "0123456789abcdef" for c in digest):
        return "source_record_id_digest_is_not_lowercase_hex"
    return None


def rule_metadata_violation(declared: Any) -> Optional[str]:
    """MACHINE-validate a table's declared rule against the compiled rule.

    A schema that merely *describes* its identity rule in prose, while its producer
    implements another one, is exactly the failure this refuses. The declaration must
    equal the compiled rule — including the payload field list, because that list is
    what decides whether the completeness proof is bound into the id at all.
    """
    if not isinstance(declared, dict):
        return f"{RULE_METADATA_KEY}_is_missing_or_not_an_object"
    if str(declared.get("rule", "")) != RULE:
        return f"{RULE_METADATA_KEY}.rule_is_not_the_compiled_rule"
    if str(declared.get("canonical_json", "")) != CANONICAL_JSON_RULE:
        return f"{RULE_METADATA_KEY}.canonical_json_is_not_the_compiled_form"
    if str(declared.get("null_handling", "")) != NULL_HANDLING:
        return f"{RULE_METADATA_KEY}.null_handling_is_not_the_compiled_rule"
    fields = declared.get("identity_payload_fields")
    if not isinstance(fields, list) or \
            [str(f) for f in fields] != list(IDENTITY_PAYLOAD_FIELDS):
        return (f"{RULE_METADATA_KEY}.identity_payload_fields_is_not_the_compiled "
                "payload (the offset and row-name proof must be inside the id)")
    return None
