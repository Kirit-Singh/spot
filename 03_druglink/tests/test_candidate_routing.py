"""The FROZEN policy on the untested inverse direction.

`workflow.py` said one thing and did another: its docstring declared that an
`inverse_direction_hypothesis` is "deliberately NOT queued", while `DIRECTION_COMPATIBLE`
contained it and the code queued it anyway. Prose describes intent; code ships. The code was
what reached Stage 4.

The root cause was one frozenset answering two different questions — "is this
direction-compatible EVIDENCE?" and "is this worth a Stage-4 ASSESSMENT?" — so an untested
inverse had to be labelled direction-compatible in order to be looked at at all.

The policy, now frozen and split:
  * an inverse-direction hypothesis IS queued — silently dropping it is the worse failure,
    because a dropped candidate is indistinguishable from a candidate nobody found;
  * it is HYPOTHESIS-ONLY, always: never observed-compatible, never a phenocopy, never
    supported evidence, never sharing a tier with a measurement;
  * Stage 4 carries the weaker class verbatim and may not promote it.
"""
from __future__ import annotations

import pytest

from druglink import workflow as wf

QUEUEABLE = "analysis"


def _route(*statuses):
    return wf.stage4_assessment(artifact_class=QUEUEABLE, identity_status="resolved",
                                  active_moiety_id="AM:CHEMBL25", directional_statuses=statuses)


# --------------------------------------------------------------------------- #
# The two questions are two sets, and they are NOT the same set.
# --------------------------------------------------------------------------- #
def test_an_untested_inverse_is_not_direction_compatible_evidence():
    assert wf.INVERSE_DIRECTION_HYPOTHESIS not in wf.DIRECTION_COMPATIBLE, (
        "an inverse-direction hypothesis is the inverse of a result nobody ran: CRISPRi never "
        "tested activation, so there is no observation for it to be compatible WITH")
    assert wf.DIRECTION_COMPATIBLE == wf.MEASURED_EVIDENCE == {wf.OBSERVED_PERTURBATION}


def test_an_untested_inverse_IS_worth_a_look():
    assert wf.INVERSE_DIRECTION_HYPOTHESIS in wf.QUEUE_ELIGIBLE
    assert wf.DIRECTION_COMPATIBLE < wf.QUEUE_ELIGIBLE, (
        "queue-eligible must be strictly WIDER than direction-compatible; if they were equal, "
        "the two questions would have collapsed back into one set")


def test_the_hypothesis_only_classes_are_exactly_the_inferred_ones():
    assert wf.HYPOTHESIS_ONLY == {wf.INVERSE_DIRECTION_HYPOTHESIS, wf.PATHWAY_HYPOTHESIS}
    assert not (wf.HYPOTHESIS_ONLY & wf.MEASURED_EVIDENCE), (
        "a hypothesis can never also be a measurement")


# --------------------------------------------------------------------------- #
# Routing. Each status reaches Stage 4 under its OWN reason — never another's.
# --------------------------------------------------------------------------- #
def test_a_measured_perturbation_is_queued_as_observed():
    status, reason = _route(wf.OBSERVED_PERTURBATION)
    assert (status, reason) == (wf.QUEUED, wf.REASON_QUEUED_OBSERVED)


def test_an_inverse_hypothesis_is_queued_under_its_OWN_reason():
    """Queued — but the reason names it a hypothesis, so Stage 4 can never mistake it for a
    measurement. If it were queued under REASON_QUEUED_OBSERVED, the class would be laundered."""
    status, reason = _route(wf.INVERSE_DIRECTION_HYPOTHESIS)
    assert status == wf.QUEUED
    assert reason == wf.REASON_QUEUED_INVERSE
    assert reason != wf.REASON_QUEUED_OBSERVED


def test_an_inverse_hypothesis_is_never_classed_as_a_measurement():
    klass = wf.evidence_class(wf.INVERSE_DIRECTION_HYPOTHESIS)
    assert klass == wf.CLASS_INVERSE
    assert klass != wf.evidence_class(wf.OBSERVED_PERTURBATION)


def test_a_measured_edge_wins_the_reason_when_both_are_present():
    """A candidate with BOTH a measurement and an inverse hypothesis is queued as OBSERVED —
    the measurement is the stronger claim and must not be downgraded either."""
    status, reason = _route(wf.INVERSE_DIRECTION_HYPOTHESIS, wf.OBSERVED_PERTURBATION)
    assert (status, reason) == (wf.QUEUED, wf.REASON_QUEUED_OBSERVED)


def test_no_directional_evidence_at_all_is_not_queued():
    status, reason = _route()
    assert status == wf.NOT_QUEUED
    assert reason == wf.REASON_NOT_QUEUED_NO_EVIDENCE


def test_a_fixture_is_never_queued_whatever_its_evidence():
    status, _ = wf.stage4_assessment(
        artifact_class="fixture", identity_status="resolved",
        active_moiety_id="AM:CHEMBL25",
        directional_statuses=[wf.OBSERVED_PERTURBATION])
    assert status == wf.NOT_QUEUED


# --------------------------------------------------------------------------- #
# What Stage 4 is told. It reads FIELDS, not docstrings.
# --------------------------------------------------------------------------- #
def test_the_method_block_publishes_BOTH_sets_and_the_no_promotion_rule():
    m = wf.vocabularies()
    assert m["direction_compatible_statuses"] == sorted(wf.DIRECTION_COMPATIBLE)
    assert m["queue_eligible_statuses"] == sorted(wf.QUEUE_ELIGIBLE)
    assert m["hypothesis_only_statuses"] == sorted(wf.HYPOTHESIS_ONLY)
    assert m["queued_is_not_evidence"] is True
    assert m["stage4_must_preserve_the_hypothesis_only_class_without_promoting_it"] is True
    # the older guarantees must survive the split
    assert m["inverse_direction_hypothesis_is_never_observed_support"] is True
    assert m["inverse_direction_hypothesis_never_shares_a_tier_with_a_measurement"] is True


def test_the_docstring_no_longer_contradicts_the_code():
    """The contradiction itself, as a test: the prose claimed 'deliberately NOT queued' while
    the code queued it. Whichever way the policy is frozen, the two must agree."""
    doc = wf.stage4_assessment.__doc__ or ""
    queued, _ = _route(wf.INVERSE_DIRECTION_HYPOTHESIS)
    says_not_queued = "deliberately NOT queued" in doc
    assert not (says_not_queued and queued == wf.QUEUED), (
        "the docstring says the inverse hypothesis is not queued, but the code queues it")


@pytest.mark.parametrize("status", sorted(wf.HYPOTHESIS_ONLY))
def test_no_hypothesis_only_status_is_ever_measured_evidence(status):
    assert status not in wf.MEASURED_EVIDENCE
    assert status not in wf.DIRECTION_COMPATIBLE
