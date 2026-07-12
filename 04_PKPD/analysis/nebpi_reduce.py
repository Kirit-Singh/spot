"""Permutation-invariant reduction of NEBPI criterion observations.

The policy is frozen in `method/nebpi_grossman2026_v1.json::evidence_reduction_policy`;
this module implements it and nothing else.

Why it exists. Grossman gives Part-II branch logic over criteria, but says nothing about
how to combine two observations of the SAME criterion in the SAME context. The first
implementation took `rows[0]`, so the class depended on the order the evidence list
happened to be in: the same two `observed_absent` rows — one adequate, one not — produced
`impermeable` in one order and `not_classifiable` in the other, under ONE
`scorecard_set_id`. One cache key, two scientifically different documents.

The rule here is a function of the SET of rows, never of their order:

    0 rows                  -> not_evaluated
    1 row (after dedupe)    -> its state, or `absent_claim_inadequate` if it claims an
                               absence that no adequate assessment backs
    >1 distinct rows        -> conflicting   (satisfies NO Part-II branch)

`conflicting` is fail-closed on purpose. Aggregating two distinct observations of one
criterion — averaging them, voting, preferring the larger study — needs a source-justified
rule that Grossman does not supply, and this implementation must not invent one. So two
rows that AGREE are `conflicting` too, not "doubly confirmed".

Identity is the whole row. Two rows are the same row only if every field is equal,
including `observation_id` and the full provenance binding — i.e. they are literally the
same record, bound to the same source response by the same extraction transform, and so
cannot add evidence. Anything less than byte-identical is a distinct row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from .canonical import strict_content_sha256
from .evidence_records import NebpiCriterionId, NebpiObservation, ObservationState

REDUCTION_POLICY_ID = "nebpi_evidence_reduction_v1"

# The reduced state of a criterion that no single row supports.
CONFLICTING = "conflicting"
ABSENT_CLAIM_INADEQUATE = "absent_claim_inadequate"

# The whole observation row, flat. This is exactly the column set
# `nebpi_observations.parquet` carries, so the independent verifier reduces the same
# identity from the emitted table that the engine reduced from the input record.
OBSERVATION_IDENTITY_FIELDS = (
    "observation_id",
    "candidate_id",
    "context_id",
    "criterion_id",
    "state",
    "assessment_adequate",
    "adequacy_rationale",
    "measurement_id",
    "potency_id",
    "evidence_type",
    "source_record_id",
    "source_url",
    "access_date",
    "release_version",
    "raw_response_sha256",
    "extraction_transform",
)


@dataclass(frozen=True)
class CriterionReduction:
    """The reduced state of one (candidate, context, criterion), and what backs it."""

    state: str
    row: Optional[NebpiObservation]
    n_distinct_rows: int
    conflicting_observation_ids: tuple[str, ...] = ()

    @property
    def satisfies_branches(self) -> bool:
        """`conflicting` proves nothing, in either direction."""
        return self.state != CONFLICTING


def observation_content(o: NebpiObservation) -> dict[str, Any]:
    """The flat row, exactly as it is emitted. The unit of identity."""
    p = o.provenance
    return {
        "observation_id": o.observation_id,
        "candidate_id": o.candidate_id,
        "context_id": o.context_id,
        "criterion_id": o.criterion_id.value,
        "state": o.state.value,
        "assessment_adequate": o.assessment_adequate,
        "adequacy_rationale": o.adequacy_rationale,
        "measurement_id": o.measurement_id,
        "potency_id": o.potency_id,
        "evidence_type": o.evidence_type.value,
        "source_record_id": p.source_record_id,
        "source_url": p.source_url,
        "access_date": p.access_date,
        "release_version": p.release_version,
        "raw_response_sha256": p.raw_response_sha256,
        "extraction_transform": p.extraction_transform,
    }


def observation_identity(o: NebpiObservation) -> str:
    """sha256 of the canonical whole row. Order-free, and stable across a round trip."""
    return strict_content_sha256(observation_content(o))


def distinct_rows(rows: list[NebpiObservation]) -> list[NebpiObservation]:
    """Collapse byte-identical duplicates; keep every genuinely distinct row.

    Sorted by identity, so the survivor of a duplicate group — and the order of the
    remaining rows — does not depend on the input order.
    """
    by_identity: dict[str, NebpiObservation] = {}
    for row in rows:
        by_identity.setdefault(observation_identity(row), row)
    return [by_identity[k] for k in sorted(by_identity)]


def reduce_criterion(
    observations: list[NebpiObservation], criterion: NebpiCriterionId
) -> CriterionReduction:
    """The one reducer. Branch logic and criterion_states both go through it."""
    rows = distinct_rows([o for o in observations if o.criterion_id == criterion])

    if not rows:
        return CriterionReduction(ObservationState.NOT_EVALUATED.value, None, 0)

    if len(rows) > 1:
        return CriterionReduction(
            CONFLICTING,
            None,
            len(rows),
            tuple(sorted(o.observation_id for o in rows)),
        )

    row = rows[0]
    # An absence that no adequate assessment looked for is not evidence of absence.
    if row.state == ObservationState.OBSERVED_ABSENT and not row.assessment_adequate:
        return CriterionReduction(ABSENT_CLAIM_INADEQUATE, row, 1)
    return CriterionReduction(row.state.value, row, 1)
