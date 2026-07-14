"""Delivery requirement — the switch that decides whether NEBPI is a primary gate.

Getting this wrong in either direction is expensive: call a locally-acting agent
"systemic priming" and you excuse it from the exposure evidence it actually needs;
call a systemic-priming agent "local CNS engagement" and you fail it for low brain
exposure it never needed. So there is no inference path into either value — only an
explicit, attributed, evidence-bound assignment. Everything else is uncertain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

from .delivery_reduce import CONFLICTING, NO_ASSIGNMENT, reduce_assignments
from .evidence_records import DeliveryAssignment, DeliveryBasis, DeliveryRequirement


@dataclass(frozen=True)
class DeliveryResult:
    candidate_id: str
    context_id: str
    requirement: str
    nebpi_primary_gate: Optional[bool]
    assigned_by: Optional[str]
    rule_id: Optional[str]
    rule_version: Optional[str]
    rationale: Optional[str]
    basis: Optional[str]
    evidence_source_record_id: Optional[str]
    evidence_sha256: Optional[str]
    reason_code: str
    downgraded_from: Optional[str] = None
    # Which input row this decision came from, and — when it came from none of them —
    # exactly which rows were in conflict. Both are emitted, so the reduction is auditable
    # rather than a claim.
    assignment_id: Optional[str] = None
    conflicting_assignment_ids: tuple[str, ...] = ()


def _llm_assigner_patterns(rules: dict[str, Any]) -> list[str]:
    for r in rules["assignment_rules"]:
        if r["rule_id"] == "llm_is_not_an_assigner":
            return [p.lower() for p in r["rejected_assigner_patterns"]]
    return []


def _gate_for(rules: dict[str, Any], requirement: str) -> Optional[bool]:
    for v in rules["values"]:
        if v["value"] == requirement:
            return v["nebpi_primary_gate"]
    raise KeyError(f"unknown delivery requirement {requirement!r}")


def _uncertain(
    candidate_id: str,
    context_id: str,
    rules: dict[str, Any],
    reason_code: str,
    # The generated cases carry NO rationale sentence. `reason_code` is the claim, and the
    # sentence for each code lives in method/stage4_prose_v1.json and METHODS.md. A sentence
    # emitted from here would be bound by nothing: a resealed release could rewrite "no
    # assignment was supplied" into "the reviewer confirmed local CNS engagement" while the
    # code beside it stayed honest. A rationale that IS present came from the input row and is
    # bound by the evidence-input digest.
    rationale: Optional[str] = None,
    downgraded_from: Optional[str] = None,
    assignment_id: Optional[str] = None,
    conflicting_assignment_ids: tuple[str, ...] = (),
) -> DeliveryResult:
    return DeliveryResult(
        candidate_id=candidate_id,
        context_id=context_id,
        requirement=DeliveryRequirement.UNCERTAIN.value,
        nebpi_primary_gate=_gate_for(rules, DeliveryRequirement.UNCERTAIN.value),
        assigned_by=None,
        rule_id=None,
        rule_version=None,
        rationale=rationale,
        basis=None,
        evidence_source_record_id=None,
        evidence_sha256=None,
        reason_code=reason_code,
        downgraded_from=downgraded_from,
        assignment_id=assignment_id,
        conflicting_assignment_ids=conflicting_assignment_ids,
    )


def resolve_delivery_requirement(
    candidate_id: str,
    context_id: str,
    assignments: list[DeliveryAssignment],
    rules: dict[str, Any],
) -> DeliveryResult:
    """Resolve exactly one delivery requirement for one (candidate, context).

    The reduction is permutation-invariant (`delivery_reduce.py`): it is a function of the
    SET of assignment rows, never of their order.
    """
    reduction = reduce_assignments(assignments, candidate_id, context_id)

    if reduction.state == NO_ASSIGNMENT:
        return _uncertain(candidate_id, context_id, rules, "no_assignment")

    if reduction.state == CONFLICTING:
        # Two distinct assignments for one context are not merged, not majority-voted and
        # not resolved by list order — even when they request the same requirement. The
        # basis, the assigner and the evidence binding are part of the claim.
        return _uncertain(
            candidate_id,
            context_id,
            rules,
            "conflicting_assignments",
            conflicting_assignment_ids=reduction.conflicting_assignment_ids,
        )

    a = reduction.row
    assert a is not None  # reduce_assignments returns a row for every other state

    if a.requirement == DeliveryRequirement.UNCERTAIN:
        return _uncertain(candidate_id, context_id, rules, "explicitly_uncertain", a.rationale,
                          assignment_id=a.assignment_id)

    # The assigner must be a person or a named rule. Not a model.
    assigner = (a.assigned_by or "").lower()
    for pat in _llm_assigner_patterns(rules):
        if re.search(rf"\b{re.escape(pat)}\b", assigner) or pat in assigner.replace("-", " ").split():
            return _uncertain(
                candidate_id, context_id, rules, "assigner_not_accepted",
                downgraded_from=a.requirement.value, assignment_id=a.assignment_id,
            )

    # The named bad inference: immune target biology alone.
    if a.basis == DeliveryBasis.TARGET_BIOLOGY_ONLY:
        return _uncertain(
            candidate_id, context_id, rules,
            "immune_target_is_not_evidence_of_systemic_priming",
            downgraded_from=a.requirement.value, assignment_id=a.assignment_id,
        )

    # An unevidenced assignment is downgraded, not refused: "nobody cited anything" is a
    # legal (and honest) input. An assignment that DOES cite a source has already been
    # resolved against the source registry by `check_referential_integrity` — an unknown,
    # unacquired or hash-mismatched source is a rejected evidence set, not an uncertain
    # requirement, and never reaches this function.
    if a.evidence is None:
        return _uncertain(
            candidate_id, context_id, rules, "no_evidence_binding",
            downgraded_from=a.requirement.value, assignment_id=a.assignment_id,
        )

    return DeliveryResult(
        candidate_id=candidate_id,
        context_id=context_id,
        requirement=a.requirement.value,
        nebpi_primary_gate=_gate_for(rules, a.requirement.value),
        assigned_by=a.assigned_by,
        rule_id=a.rule_id,
        rule_version=a.rule_version,
        rationale=a.rationale,
        basis=a.basis.value,
        evidence_source_record_id=a.evidence.source_record_id,
        evidence_sha256=a.evidence.raw_response_sha256,
        reason_code="assigned",
        assignment_id=a.assignment_id,
    )
