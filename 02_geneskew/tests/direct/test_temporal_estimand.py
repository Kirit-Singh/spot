"""The temporal cross-condition estimand, as arithmetic.

The DiD is a difference of two WITHIN-CONDITION arm values. Everything a reader could
mistake for a fate claim — a trajectory, a per-cell transition, a rate — is absent by
construction: there is one subtraction here and no other operation. The estimand lives in
``direct.temporal.arms.estimand`` and its identity in ``direct.temporal.arms.config`` (the
fixed-pair flat lane that once hosted them, and its reliability floor, were retired).
"""
from __future__ import annotations

import pytest
from direct.temporal.arms import config as C
from direct.temporal.arms import estimand as E


class TestDifferenceInDifferences:
    def test_did_is_the_to_endpoint_minus_the_from_endpoint(self):
        assert E.temporal_did(from_value=0.5, to_value=1.25) == pytest.approx(0.75)

    def test_reversing_the_pair_negates_the_did_exactly(self):
        forward = E.temporal_did(from_value=0.5, to_value=1.25)
        reverse = E.temporal_did(from_value=1.25, to_value=0.5)
        assert forward == pytest.approx(-reverse)

    def test_identical_endpoints_give_exactly_zero_not_approximately_zero(self):
        assert E.temporal_did(from_value=-3.75, to_value=-3.75) == 0.0

    def test_a_missing_endpoint_yields_no_estimate_never_a_zero(self):
        assert E.temporal_did(from_value=None, to_value=1.0) is None
        assert E.temporal_did(from_value=1.0, to_value=None) is None
        assert E.temporal_did(from_value=None, to_value=None) is None

    def test_a_non_finite_endpoint_is_not_a_value(self):
        assert E.temporal_did(from_value=float("nan"), to_value=1.0) is None
        assert E.temporal_did(from_value=1.0, to_value=float("inf")) is None


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


class TestTheEstimandIsNotAFateClaim:
    def test_there_is_no_function_that_turns_a_did_into_a_rate_or_a_trajectory(self):
        # A DiD divided by elapsed time would be a velocity, and a velocity is a claim about
        # cells moving. This estimator is population-level and has no such thing.
        forbidden = ("rate", "velocity", "trajectory", "per_cell", "fate", "transition",
                     "flux", "elapsed", "hours", "slope")
        exported = [n for n in dir(E) if not n.startswith("_")]
        assert [n for n in exported if any(f in n.lower() for f in forbidden)] == []

    def test_inference_is_uncalibrated_so_no_p_or_q_is_ever_produced(self):
        assert C.INFERENCE_STATUS == "not_calibrated"
        assert C.ESTIMAND_IS_PER_CELL_FATE is False
        assert C.ESTIMAND_IS_LINEAGE_TRACED is False
        exported = [n.lower() for n in dir(E) if not n.startswith("_")]
        assert not any(n in ("pvalue", "p_value", "qvalue", "q_value", "fdr")
                       for n in exported)
