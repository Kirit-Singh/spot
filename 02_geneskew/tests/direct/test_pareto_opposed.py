"""M4 — an arm that was EVALUATED and moved the wrong way is `opposed`, not `not_evaluable`.

The defect: ``joint_status`` only reached ``opposed`` when one arm was FAVOURABLE and the
other opposing. A target whose arms were both evaluated and both moved undesirably
(away=-1, toward=-1), or moved undesirably on one arm and nowhere on the other
(away=-1, toward=0), fell through every branch and landed in ``not_evaluable``.

That is a false statement about the measurement. Both arms WERE evaluable, both WERE
scored, and what they said was "this target moves the wrong way". Reporting that as
"not evaluable" merges a real negative result into the bucket for missing data — and the
bucket for missing data is exactly where a reader stops looking.

``not_evaluable`` now means what it says: an arm that could not be scored, or two arms
that both sat inside the sign tolerance and therefore pointed nowhere.

LABEL-ONLY. Arm values and arm ranks are untouched — asserted below, byte for byte.
"""
from __future__ import annotations

import pytest
from direct import config, pareto

EPS = config.SIGN_EPS


def row(away, toward, *, a_eval=True, b_eval=True, target_id="T"):
    return {"target_id": target_id,
            config.ARM_A: away, config.ARM_B: toward,
            "A_evaluable": a_eval, "B_evaluable": b_eval}


class TestTheTwoCasesTheReviewerNamed:
    def test_both_arms_evaluated_and_both_move_the_wrong_way_is_opposed(self):
        assert pareto.joint_status(row(-1.0, -1.0)) == pareto.JOINT_OPPOSED

    def test_one_arm_opposes_and_the_other_says_nothing_is_opposed(self):
        assert pareto.joint_status(row(-1.0, 0.0)) == pareto.JOINT_OPPOSED

    def test_neither_is_reported_as_not_evaluable_any_more(self):
        for r in (row(-1.0, -1.0), row(-1.0, 0.0)):
            assert pareto.joint_status(r) != pareto.JOINT_NOT_EVALUABLE


class TestOpposedCoversEveryEvaluatedWrongWayArm:
    @pytest.mark.parametrize("away,toward", [
        (-1.0, -1.0),     # both oppose
        (-1.0, 0.0),      # away opposes, toward neutral
        (0.0, -1.0),      # toward opposes, away neutral
        (-1.0, 1.0),      # away opposes, toward favourable  (already opposed before)
        (1.0, -1.0),      # away favourable, toward opposes  (already opposed before)
        (-5.0, -0.5),
    ])
    def test_an_evaluable_arm_below_minus_eps_makes_the_target_opposed(self, away,
                                                                       toward):
        assert pareto.joint_status(row(away, toward)) == pareto.JOINT_OPPOSED


class TestNotEvaluableIsReservedForWhatItSays:
    def test_a_missing_arm_value_is_not_evaluable(self):
        assert pareto.joint_status(row(None, None)) == pareto.JOINT_NOT_EVALUABLE

    def test_an_arm_the_lane_could_not_score_is_not_evaluable(self):
        r = row(-1.0, -1.0, a_eval=False, b_eval=False)
        assert pareto.joint_status(r) == pareto.JOINT_NOT_EVALUABLE

    def test_two_arms_that_both_point_nowhere_are_not_evaluable(self):
        assert pareto.joint_status(row(0.0, 0.0)) == pareto.JOINT_NOT_EVALUABLE

    def test_a_non_finite_arm_is_not_a_score(self):
        assert pareto.joint_status(row(float("nan"),
                                       float("nan"))) == pareto.JOINT_NOT_EVALUABLE

    def test_an_unscoreable_arm_beside_an_opposing_one_still_reports_opposed(self):
        # The arm that WAS scored said something, and it said the wrong way.
        r = row(-1.0, None, a_eval=True, b_eval=False)
        assert pareto.joint_status(r) == pareto.JOINT_OPPOSED


class TestTheFavourableLabelsAreUnchanged:
    def test_both_favourable_is_both_arms(self):
        assert pareto.joint_status(row(1.0, 1.0)) == pareto.JOINT_BOTH

    def test_away_only(self):
        assert pareto.joint_status(row(1.0, 0.0)) == pareto.JOINT_AWAY_ONLY

    def test_toward_only(self):
        assert pareto.joint_status(row(0.0, 1.0)) == pareto.JOINT_TOWARD_ONLY

    def test_a_favourable_arm_beside_an_opposing_one_is_still_opposed(self):
        assert pareto.joint_status(row(1.0, -1.0)) == pareto.JOINT_OPPOSED


class TestThisIsALabelOnlyChange:
    def test_the_tiers_are_a_function_of_the_values_and_do_not_read_the_label(self):
        rows = [row(2.0, 2.0, target_id="T1"), row(-1.0, -1.0, target_id="T2"),
                row(1.0, -1.0, target_id="T3"), row(-1.0, 0.0, target_id="T4")]
        pareto.assign_tiers(rows)
        # T1 dominates every other point, so it alone is the frontier
        by_id = {r["target_id"]: r for r in rows}
        assert by_id["T1"][pareto.TIER_COLUMN] == 1
        assert all(by_id[t][pareto.TIER_COLUMN] > 1 for t in ("T2", "T3", "T4"))

    def test_the_raw_arm_values_are_untouched_by_labelling(self):
        rows = [row(-1.0, -1.0, target_id="T2"), row(1.0, -1.0, target_id="T3")]
        before = [(r[config.ARM_A], r[config.ARM_B]) for r in rows]
        pareto.assign_tiers(rows)
        after = [(r[config.ARM_A], r[config.ARM_B]) for r in rows]
        assert after == before

    def test_dominance_never_consults_the_joint_status(self):
        x, y = row(-1.0, -1.0, target_id="X"), row(-2.0, -2.0, target_id="Y")
        # X is better than Y on both arms even though BOTH are opposed
        assert pareto.dominates(x, y) is True


class TestTheVocabularyIsDeclared:
    def test_opposed_is_in_the_frozen_status_set(self):
        assert pareto.JOINT_OPPOSED in pareto.JOINT_STATUSES

    def test_the_module_states_what_not_evaluable_is_reserved_for(self):
        assert pareto.NOT_EVALUABLE_MEANS
        assert "neutral" in pareto.NOT_EVALUABLE_MEANS.lower()
