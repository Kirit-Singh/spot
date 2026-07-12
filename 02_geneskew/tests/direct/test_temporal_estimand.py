"""The temporal cross-condition estimand, as arithmetic.

The DiD is a difference of two WITHIN-CONDITION arm values. Everything a reader could
mistake for a fate claim — a trajectory, a per-cell transition, a rate — is absent by
construction: there is one subtraction here and no other operation.
"""
from __future__ import annotations

import pytest
from direct.temporal import estimand as E


class TestDifferenceInDifferences:
    def test_did_is_the_to_endpoint_minus_the_from_endpoint(self):
        assert E.temporal_did(from_value=0.5, to_value=1.25) == pytest.approx(0.75)

    def test_reversing_the_pair_negates_the_did_exactly(self):
        forward = E.temporal_did(from_value=0.5, to_value=1.25)
        reverse = E.temporal_did(from_value=1.25, to_value=0.5)
        assert forward == -reverse

    def test_identical_endpoints_give_exactly_zero_not_approximately_zero(self):
        assert E.temporal_did(from_value=-3.75, to_value=-3.75) == 0.0

    def test_a_missing_endpoint_yields_no_estimate_never_a_zero(self):
        assert E.temporal_did(from_value=None, to_value=1.0) is None
        assert E.temporal_did(from_value=1.0, to_value=None) is None
        assert E.temporal_did(from_value=None, to_value=None) is None


class TestTemporalStatus:
    def test_both_endpoints_evaluable_and_present_is_estimated(self):
        assert E.temporal_status(from_present=True, to_present=True,
                                 from_evaluable=True, to_evaluable=True) == E.ESTIMATED

    def test_an_absent_endpoint_is_named_by_the_endpoint_that_is_absent(self):
        assert E.temporal_status(from_present=False, to_present=True,
                                 from_evaluable=False,
                                 to_evaluable=True) == E.ABSENT_AT_FROM
        assert E.temporal_status(from_present=True, to_present=False,
                                 from_evaluable=True,
                                 to_evaluable=False) == E.ABSENT_AT_TO

    def test_absence_outranks_non_evaluability_because_it_is_the_stronger_fact(self):
        # a target the release never shipped at this condition was not "refused" there
        assert E.temporal_status(from_present=False, to_present=False,
                                 from_evaluable=False,
                                 to_evaluable=False) == E.ABSENT_AT_BOTH

    def test_a_present_but_non_evaluable_endpoint_is_named_as_such(self):
        assert E.temporal_status(from_present=True, to_present=True,
                                 from_evaluable=False,
                                 to_evaluable=True) == E.NOT_EVALUABLE_AT_FROM
        assert E.temporal_status(from_present=True, to_present=True,
                                 from_evaluable=True,
                                 to_evaluable=False) == E.NOT_EVALUABLE_AT_TO
        assert E.temporal_status(from_present=True, to_present=True,
                                 from_evaluable=False,
                                 to_evaluable=False) == E.NOT_EVALUABLE_AT_BOTH


class TestReliabilityAgainstTheInteractionFloor:
    """|DiD| against k x interaction_std(program). A PRECISION statement, not a p-value."""

    def test_a_movement_larger_than_the_floor_is_badged_above_it(self):
        r = E.reliability(did=0.40, interaction_std=0.157, k=2.0)
        assert r["reliability_badge"] == E.ABOVE_FLOOR
        assert r["reliability_threshold"] == pytest.approx(0.314)
        assert r["reliability_k"] == 2.0

    def test_a_movement_inside_the_floor_is_badged_within_it(self):
        r = E.reliability(did=0.20, interaction_std=0.157, k=2.0)
        assert r["reliability_badge"] == E.WITHIN_FLOOR

    def test_the_badge_reads_magnitude_so_a_large_negative_move_is_above_the_floor(self):
        r = E.reliability(did=-0.40, interaction_std=0.157, k=2.0)
        assert r["reliability_badge"] == E.ABOVE_FLOOR

    def test_exactly_at_the_threshold_counts_as_above_it(self):
        r = E.reliability(did=0.314, interaction_std=0.157, k=2.0)
        assert r["reliability_badge"] == E.ABOVE_FLOOR

    def test_a_program_with_no_measured_floor_is_never_silently_reliable(self):
        r = E.reliability(did=99.0, interaction_std=None, k=2.0)
        assert r["reliability_badge"] == E.FLOOR_UNAVAILABLE
        assert r["reliability_threshold"] is None

    def test_no_did_means_no_badge_rather_than_a_failing_one(self):
        r = E.reliability(did=None, interaction_std=0.157, k=2.0)
        assert r["reliability_badge"] == E.NOT_ESTIMATED

    def test_the_exact_threshold_used_is_always_reported_with_the_badge(self):
        r = E.reliability(did=0.4, interaction_std=0.4711131141353615, k=2.0)
        assert r["interaction_std"] == 0.4711131141353615
        assert r["reliability_threshold"] == pytest.approx(0.942226228270723)


class TestTheEstimandIsNotAFateClaim:
    def test_there_is_no_function_that_turns_a_did_into_a_rate_or_a_trajectory(self):
        # A DiD divided by elapsed time would be a velocity, and a velocity is a claim
        # about cells moving. This estimator is population-level and has no such thing.
        forbidden = ("rate", "velocity", "trajectory", "per_cell", "fate", "transition",
                     "flux", "elapsed", "hours", "slope")
        exported = [n for n in dir(E) if not n.startswith("_")]
        assert [n for n in exported if any(f in n.lower() for f in forbidden)] == []

    def test_inference_is_uncalibrated_so_no_p_or_q_is_ever_produced(self):
        assert E.INFERENCE_STATUS == "not_calibrated"
        exported = [n.lower() for n in dir(E) if not n.startswith("_")]
        assert not any(n in ("pvalue", "p_value", "qvalue", "q_value", "fdr")
                       for n in exported)
