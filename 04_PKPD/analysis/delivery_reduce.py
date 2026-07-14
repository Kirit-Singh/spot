"""Permutation-invariant reduction of delivery-requirement assignments.

The same failure the NEBPI reducer was built to kill (`nebpi_reduce.py`), in the other
lane. `resolve_delivery_requirement` checked only whether two assignments disagreed on
the requirement VALUE, and then took `mine[0]`. So two assignments for one
(candidate, context) that both requested `local_CNS_target_engagement_required` — one on
pharmacology evidence, one on the explicitly-rejected `target_biology_only` basis —
reduced to `local_CNS`/gate=true or to `uncertain` purely on which came first in the list,
under ONE `scorecard_set_id`. One cache key, two different scientific documents, and both
verifications passed.

The rule here is a function of the SET of rows, never of their order:

    0 rows                  -> no_assignment          (Stage 4 does not infer one)
    1 row (after dedupe)    -> that row is validated and applied
    >1 distinct rows        -> conflicting_assignments -> uncertain

`conflicting_assignments` is fail-closed even when the requested requirement AGREES,
because the requirement is not the whole claim: the basis, the assigner, the rule and the
evidence binding are what make it admissible, and there is no source-justified rule for
merging two distinct assignments. Choosing between them silently is exactly the failure
this module exists to prevent.

Identity is the whole row — every field including `assignment_id` and the full provenance
binding. Two rows are the same row only if they are literally the same record; anything
less than byte-identical is a distinct row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .canonical import strict_content_sha256
from .evidence_records import DeliveryAssignment

REDUCTION_POLICY_ID = "delivery_assignment_reduction_v1"

CONFLICTING = "conflicting_assignments"
NO_ASSIGNMENT = "no_assignment"
RESOLVED = "resolved"

# The whole assignment row, flat. This is exactly the column set
# `delivery_assignments.parquet` carries, so the independent verifier reduces the same
# identity from the emitted table that the engine reduced from the input record.
ASSIGNMENT_IDENTITY_FIELDS = (
    "assignment_id",
    "candidate_id",
    "context_id",
    "requirement",
    "basis",
    "assigned_by",
    "rule_id",
    "rule_version",
    "rationale",
    "evidence_source_record_id",
    "evidence_source_url",
    "evidence_access_date",
    "evidence_release_version",
    "evidence_sha256",
    "evidence_extraction_transform",
)


@dataclass(frozen=True)
class AssignmentReduction:
    """The reduced assignment for one (candidate, context), and what backs it."""

    state: str
    row: Optional[DeliveryAssignment]
    n_distinct_rows: int
    conflicting_assignment_ids: tuple[str, ...] = ()


def assignment_content(a: DeliveryAssignment) -> dict[str, Any]:
    """The flat row, exactly as it is emitted. The unit of identity."""
    e = a.evidence
    return {
        "assignment_id": a.assignment_id,
        "candidate_id": a.candidate_id,
        "context_id": a.context_id,
        "requirement": a.requirement.value,
        "basis": a.basis.value,
        "assigned_by": a.assigned_by,
        "rule_id": a.rule_id,
        "rule_version": a.rule_version,
        "rationale": a.rationale,
        "evidence_source_record_id": e.source_record_id if e else None,
        "evidence_source_url": e.source_url if e else None,
        "evidence_access_date": e.access_date if e else None,
        "evidence_release_version": e.release_version if e else None,
        "evidence_sha256": e.raw_response_sha256 if e else None,
        "evidence_extraction_transform": e.extraction_transform if e else None,
    }


def assignment_identity(a: DeliveryAssignment) -> str:
    """sha256 of the canonical whole row. Order-free, and stable across a round trip."""
    return strict_content_sha256(assignment_content(a))


def distinct_assignments(rows: list[DeliveryAssignment]) -> list[DeliveryAssignment]:
    """Collapse byte-identical duplicates; keep every genuinely distinct row.

    Sorted by identity, so neither the survivor of a duplicate group nor the order of the
    remaining rows depends on the input order.
    """
    by_identity: dict[str, DeliveryAssignment] = {}
    for row in rows:
        by_identity.setdefault(assignment_identity(row), row)
    return [by_identity[k] for k in sorted(by_identity)]


def reduce_assignments(
    assignments: list[DeliveryAssignment], candidate_id: str, context_id: str
) -> AssignmentReduction:
    """The one reducer. Every delivery decision goes through it, in every order."""
    rows = distinct_assignments(
        [a for a in assignments
         if a.candidate_id == candidate_id and a.context_id == context_id]
    )

    if not rows:
        return AssignmentReduction(NO_ASSIGNMENT, None, 0)

    if len(rows) > 1:
        return AssignmentReduction(
            CONFLICTING,
            None,
            len(rows),
            tuple(sorted(a.assignment_id for a in rows)),
        )

    return AssignmentReduction(RESOLVED, rows[0], 1)
