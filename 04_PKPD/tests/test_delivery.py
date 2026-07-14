"""Delivery requirement: no inference path into either non-uncertain value."""

from __future__ import annotations

import pytest

from analysis.delivery import resolve_delivery_requirement
from analysis.evidence_records import (
    DeliveryAssignment,
    DeliveryBasis,
    DeliveryRequirement,
    Provenance,
)
from analysis.method_config import load_method_bundle

RULES = load_method_bundle().delivery_rules

EVIDENCE = Provenance(source_record_id="src.test", access_date="2026-07-11",
                      raw_response_sha256="0" * 64, extraction_transform="test")


def assignment(**kw) -> DeliveryAssignment:
    base = dict(
        assignment_id="DLV-1",
        candidate_id="C1", context_id="CTX-1", requirement=DeliveryRequirement.SYSTEMIC_PRIMING,
        basis=DeliveryBasis.CLINICAL_EVIDENCE, assigned_by="reviewer-1",
        rule_id="explicit_assignment_required", rule_version="1.0.0", rationale="because",
        evidence=EVIDENCE,
    )
    base.update(kw)
    return DeliveryAssignment(**base)


def resolve(assignments):
    return resolve_delivery_requirement("C1", "CTX-1", assignments, RULES)


def test_no_assignment_defaults_to_uncertain():
    r = resolve([])
    assert r.requirement == "delivery_requirement_uncertain"
    assert r.reason_code == "no_assignment"
    assert r.nebpi_primary_gate is None


def test_immune_target_alone_does_not_assign_systemic_priming():
    """The named bad inference. An immune-related target may still need to be engaged on
    lymphocytes *inside* non-enhancing brain."""
    r = resolve([assignment(basis=DeliveryBasis.TARGET_BIOLOGY_ONLY,
                            rationale="the upstream target is an immune gene")])
    assert r.requirement == "delivery_requirement_uncertain"
    assert r.reason_code == "immune_target_is_not_evidence_of_systemic_priming"
    assert r.downgraded_from == "systemic_immune_priming"
    assert r.nebpi_primary_gate is None


def test_target_biology_alone_also_cannot_assign_local_cns():
    """The refusal is symmetric: target biology does not establish either requirement."""
    r = resolve([assignment(requirement=DeliveryRequirement.LOCAL_CNS,
                            basis=DeliveryBasis.TARGET_BIOLOGY_ONLY)])
    assert r.requirement == "delivery_requirement_uncertain"
    assert r.downgraded_from == "local_CNS_target_engagement_required"


@pytest.mark.parametrize("who", ["claude", "gpt-4", "an LLM reviewer", "model", "spot-ai", "gemini"])
def test_model_output_cannot_assign_a_delivery_requirement(who):
    r = resolve([assignment(assigned_by=who)])
    assert r.requirement == "delivery_requirement_uncertain"
    assert r.reason_code == "assigner_not_accepted"


def test_assignment_without_evidence_binding_is_downgraded():
    r = resolve([assignment(evidence=None)])
    assert r.requirement == "delivery_requirement_uncertain"
    assert r.reason_code == "no_evidence_binding"


def test_conflicting_assignments_are_not_merged_or_voted():
    r = resolve([
        assignment(assignment_id="DLV-a", requirement=DeliveryRequirement.SYSTEMIC_PRIMING),
        assignment(assignment_id="DLV-b", requirement=DeliveryRequirement.LOCAL_CNS),
    ])
    assert r.requirement == "delivery_requirement_uncertain"
    assert r.reason_code == "conflicting_assignments"
    assert r.conflicting_assignment_ids == ("DLV-a", "DLV-b")


def test_valid_assignments_set_the_gate():
    local = resolve([assignment(requirement=DeliveryRequirement.LOCAL_CNS,
                                basis=DeliveryBasis.MECHANISM_WITH_PHARMACOLOGY_EVIDENCE)])
    assert local.requirement == "local_CNS_target_engagement_required"
    assert local.nebpi_primary_gate is True
    assert local.assigned_by == "reviewer-1"

    systemic = resolve([assignment()])
    assert systemic.requirement == "systemic_immune_priming"
    assert systemic.nebpi_primary_gate is False


def test_every_result_records_who_what_and_on_what_evidence():
    r = resolve([assignment()])
    assert r.assigned_by and r.rule_id and r.rule_version and r.rationale
    assert r.evidence_source_record_id and r.evidence_sha256
    assert r.basis == "clinical_evidence"


def test_exactly_three_delivery_values_exist():
    assert {v["value"] for v in RULES["values"]} == {
        "local_CNS_target_engagement_required",
        "systemic_immune_priming",
        "delivery_requirement_uncertain",
    }
    assert RULES["default"] == "delivery_requirement_uncertain"
