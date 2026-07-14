"""Input firewall.

Stage 4 refuses anything it cannot fully account for. Every rejection carries a
machine-readable code, because "it failed validation" is not an audit trail.

The load-bearing rule: a biology-only identifier (a drug name, a target, a Stage-3
candidate_set_id on its own) is NEVER a cache key. Identity is content.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Iterable

from pydantic import ValidationError

from .canonical import content_sha256
from .contracts import (
    ID_PATTERN,
    STAGE3_SCHEMA_ID,
    AcquisitionStatus,
    DirectionCompatibility,
    Namespace,
    Provenance,
    SourceRecord,
    Stage3Candidate,
    Stage3DrugCandidateSet,
)


class Rejection(Exception):
    """A coded refusal. `code` is stable and testable; `detail` is for humans."""

    def __init__(self, code: str, detail: str, context: dict[str, Any] | None = None):
        super().__init__(f"[{code}] {detail}")
        self.code = code
        self.detail = detail
        self.context = context or {}


@dataclass(frozen=True)
class EligibilityNote:
    candidate_id: str
    production_eligible: bool
    reason_code: str
    reason: str


# ---------------------------------------------------------------------- path safety

_UNSAFE = re.compile(r"(^\.)|(\.\.)|([/\\])|(\x00)")


def safe_path_component(name: str) -> str:
    """A single path segment we are willing to create. No traversal, no absolutes."""
    if not isinstance(name, str) or not name:
        raise Rejection("path_traversal", "empty or non-string path component")
    if _UNSAFE.search(name) or os.path.isabs(name):
        raise Rejection("path_traversal", f"unsafe path component: {name!r}")
    if not re.match(ID_PATTERN, name):
        raise Rejection("path_traversal", f"path component is not a safe id: {name!r}")
    return name


def resolve_within(root: str, candidate_path: str) -> str:
    """Resolve `candidate_path` and prove it stays under `root`."""
    root_abs = os.path.realpath(root)
    target = os.path.realpath(os.path.join(root_abs, candidate_path))
    if target != root_abs and not target.startswith(root_abs + os.sep):
        raise Rejection(
            "path_traversal",
            f"path escapes the permitted root: {candidate_path!r}",
            {"root": root_abs, "resolved": target},
        )
    return target


# ------------------------------------------------------------------ Stage-3 contract


def canonical_candidate_rows(candidates: Iterable[Stage3Candidate]) -> list[dict]:
    """The exact object the Stage-3 row hash is taken over. Row order is fixed by
    candidate_id so that a re-serialisation cannot change the hash."""
    rows = [c.model_dump(mode="json") for c in candidates]
    return sorted(rows, key=lambda r: r["candidate_id"])


def compute_candidate_rows_sha256(candidates: Iterable[Stage3Candidate]) -> str:
    return content_sha256(canonical_candidate_rows(candidates))


def validate_stage3_candidate_set(payload: dict[str, Any]) -> Stage3DrugCandidateSet:
    """Parse + verify a Stage-3 DrugCandidateSet. Raises Rejection with a code."""
    if not isinstance(payload, dict):
        raise Rejection("schema_invalid", "candidate set payload is not an object")

    schema_id = payload.get("schema_id")
    if schema_id != STAGE3_SCHEMA_ID:
        raise Rejection(
            "schema_unknown",
            f"unknown schema_id {schema_id!r}; Stage 4 accepts only {STAGE3_SCHEMA_ID!r}",
        )

    if not payload.get("candidate_rows_sha256"):
        raise Rejection("hash_missing", "candidate_rows_sha256 is absent")

    try:
        cset = Stage3DrugCandidateSet.model_validate(payload)
    except ValidationError as exc:
        raise Rejection("schema_invalid", f"candidate set failed schema validation: {exc.error_count()} error(s)",
                        {"errors": exc.errors(include_url=False)}) from exc

    # 1. The declared row hash must be the hash of the rows actually supplied.
    recomputed = compute_candidate_rows_sha256(cset.candidates)
    if recomputed != cset.candidate_rows_sha256:
        raise Rejection(
            "hash_mismatch",
            "candidate_rows_sha256 does not match the supplied candidate rows",
            {"declared": cset.candidate_rows_sha256, "recomputed": recomputed},
        )

    # 2. Identity must be unique on every axis a join could travel over.
    _reject_duplicate_identity(cset.candidates)

    # 3. Salt / prodrug / active-moiety mapping must be unambiguous.
    for c in cset.candidates:
        _validate_moiety_mapping(c)

    # 4. Namespace must be internally consistent.
    _validate_namespace(cset)

    return cset


def _reject_duplicate_identity(candidates: list[Stage3Candidate]) -> None:
    seen_ids: set[str] = set()
    seen_identity: dict[tuple, str] = {}
    for c in candidates:
        if c.candidate_id in seen_ids:
            raise Rejection("duplicate_candidate_identity",
                            f"candidate_id appears twice: {c.candidate_id!r}")
        seen_ids.add(c.candidate_id)

        # Same moiety + same target + same mechanism + same direction pair is the same
        # candidate wearing two ids. Two rows would double-count evidence downstream.
        identity = (
            c.active_moiety.active_moiety_id,
            c.target,
            c.mechanism,
            c.program_direction,
            c.drug_effect_direction,
        )
        if identity in seen_identity:
            raise Rejection(
                "duplicate_candidate_identity",
                f"candidates {seen_identity[identity]!r} and {c.candidate_id!r} share the same "
                "active moiety / target / mechanism / direction identity",
                {"identity": list(identity)},
            )
        seen_identity[identity] = c.candidate_id


def _validate_moiety_mapping(c: Stage3Candidate) -> None:
    m = c.active_moiety
    if m.administered_form == "active_moiety":
        if m.maps_to_active_moiety_id and m.maps_to_active_moiety_id != m.active_moiety_id:
            raise Rejection(
                "ambiguous_moiety_mapping",
                f"{c.candidate_id!r}: administered_form=active_moiety but maps_to_active_moiety_id "
                f"points elsewhere ({m.maps_to_active_moiety_id!r})",
            )
        return

    # Salt / prodrug / ester: we must be told what it becomes, and who says so.
    if not m.maps_to_active_moiety_id:
        raise Rejection(
            "ambiguous_moiety_mapping",
            f"{c.candidate_id!r}: administered_form={m.administered_form!r} without "
            "maps_to_active_moiety_id — the active moiety is unknown",
        )
    if m.maps_to_active_moiety_id != m.active_moiety_id:
        raise Rejection(
            "ambiguous_moiety_mapping",
            f"{c.candidate_id!r}: active_moiety_id {m.active_moiety_id!r} disagrees with "
            f"maps_to_active_moiety_id {m.maps_to_active_moiety_id!r}",
        )
    if not m.mapping_source_record_id:
        raise Rejection(
            "ambiguous_moiety_mapping",
            f"{c.candidate_id!r}: {m.administered_form!r} -> active-moiety mapping has no source record",
        )


def _validate_namespace(cset: Stage3DrugCandidateSet) -> None:
    if cset.namespace == Namespace.RESEARCH_ONLY:
        for c in cset.candidates:
            if c.namespace == Namespace.PRODUCTION:
                raise Rejection(
                    "namespace_escalation",
                    f"{c.candidate_id!r} claims production namespace inside a research_only "
                    "candidate set — research-only inputs cannot be promoted",
                )


def production_eligibility(cset: Stage3DrugCandidateSet, c: Stage3Candidate,
                           sources: dict[str, SourceRecord] | None = None) -> EligibilityNote:
    """Whether a candidate may be treated as a production candidate.

    Accumulating PK/transporter/safety annotations in Stage 4 does NOT change this. Stage 4
    adds evidence; it does not launder provenance.

    The audit relabelled fixture sources as public data and the preflight reported
    eligible=true, so eligibility now also depends on the CLASS of every consumed source:
    one synthetic or unacquired source anywhere in the evidence set and nothing in it is a
    production candidate. The independent verifier re-derives this same rule from the
    emitted source catalog.
    """
    if cset.namespace != Namespace.PRODUCTION or c.namespace != Namespace.PRODUCTION:
        research = Namespace.RESEARCH_ONLY in (cset.namespace, c.namespace)
        return EligibilityNote(
            c.candidate_id,
            False,
            "research_only_namespace" if research else "fixture_namespace",
            f"Upstream namespace is {(c.namespace if c.namespace != Namespace.PRODUCTION else cset.namespace).value}. "
            "Stage-4 evidence cannot promote it to production.",
        )
    # Compared against the enum members, which also equal their string values — so a
    # model_copy() that bypassed validation cannot slip past this check as a bare str.
    if c.direction_compatibility == DirectionCompatibility.INCOMPATIBLE:
        return EligibilityNote(
            c.candidate_id,
            False,
            "direction_incompatible",
            "The drug's effect direction is incompatible with the program direction requested upstream.",
        )
    if c.direction_compatibility == DirectionCompatibility.UNKNOWN:
        return EligibilityNote(
            c.candidate_id,
            False,
            "direction_unknown",
            "Direction compatibility with the upstream program was not established.",
        )
    if sources is not None:
        nonpublic = sorted(
            sid for sid, rec in sources.items()
            if rec.acquisition_status != AcquisitionStatus.ACQUIRED_PUBLIC
        )
        if nonpublic:
            return EligibilityNote(
                c.candidate_id,
                False,
                "non_public_source_in_evidence",
                "The evidence set consumes sources that are not acquired public records "
                f"({len(nonpublic)} of {len(sources)}). Nothing resting on synthetic or "
                "unacquired bytes is a production candidate.",
            )
    return EligibilityNote(c.candidate_id, True, "eligible",
                           "Production namespace, compatible direction, all sources acquired public.")


# ------------------------------------------------------------- evidence <-> sources


def validate_source_bindings(
    provenances: Iterable[tuple[str, Provenance]],
    source_registry: dict[str, SourceRecord],
) -> None:
    """Every number must point at a source record, and at the SAME bytes that record
    pins. A drifted raw_response_sha256 is a mutation, not a rounding difference."""
    for owner, p in provenances:
        rec = source_registry.get(p.source_record_id)
        if rec is None:
            raise Rejection(
                "unbound_source_record",
                f"{owner}: provenance points at unknown source_record_id {p.source_record_id!r}",
            )
        if rec.raw_sha256 != p.raw_response_sha256:
            raise Rejection(
                "source_hash_mismatch",
                f"{owner}: raw_response_sha256 does not match source record {p.source_record_id!r}",
                {"declared": p.raw_response_sha256, "registry": rec.raw_sha256},
            )
