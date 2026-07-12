"""The masked projection formula, the two arms, and per-arm ranking."""
import numpy as np
import pytest

from direct import config
from direct import projection as proj
from direct.projection import (ARM_A, ARM_B, INSUFFICIENT_AXIS_COVERAGE,
                               MASK_UNRESOLVED, OK)

EPS = config.SIGN_EPS


@pytest.fixture
def five():
    return {f"ENSG{i}": i for i in range(5)}


def test_direct_formula_hand_computed(five):
    row = np.array([2.0, 4.0, 1.0, 0.0, 2.0])
    out = proj.program_delta(row, ["ENSG0", "ENSG1"], ["ENSG2", "ENSG3", "ENSG4"],
                             five, set(), min_panel=1, min_control=1)
    assert out["status"] == OK
    assert out["panel_mean"] == pytest.approx(3.0)
    assert out["control_mean"] == pytest.approx(1.0)
    assert out["delta"] == pytest.approx(2.0)


def test_mask_recomputes_panel_and_control_means_separately(five):
    row = np.array([2.0, 4.0, 1.0, 0.0, 2.0])
    out = proj.program_delta(row, ["ENSG0", "ENSG1"], ["ENSG2", "ENSG3", "ENSG4"],
                             five, {"ENSG1"}, min_panel=1, min_control=1)
    assert out["panel_mean"] == pytest.approx(2.0)
    assert out["n_panel_surviving"] == 1


def test_an_unresolved_mask_refuses_to_project(five):
    out = proj.program_delta(np.ones(5), ["ENSG0"], ["ENSG2"], five, None,
                             min_panel=1, min_control=1)
    assert out["status"] == MASK_UNRESOLVED
    assert out["delta"] is None


def test_insufficient_axis_coverage(five):
    out = proj.program_delta(np.zeros(5), ["ENSG0"], ["ENSG2", "ENSG3"], five,
                             {"ENSG0"}, min_panel=1, min_control=1)
    assert out["status"] == INSUFFICIENT_AXIS_COVERAGE
    assert out["delta"] is None


# --------------------------------------------------------------------------- #
# Two arms, never combined.
# --------------------------------------------------------------------------- #
def test_arm_scores_returns_exactly_the_two_arms():
    s = proj.arm_scores(delta_a=-1.0, delta_b=2.0, sign_a=1, sign_b=1)
    assert s == {ARM_A: 1.0, ARM_B: 2.0}
    # there is no combined/balanced/averaged key, under any name
    assert set(s) == set(config.ARMS)
    for banned in ("combination", "balanced_skew", "combined", "total_skew",
                   "composite", "mean", "score"):
        assert banned not in s


def test_the_module_exposes_no_way_to_combine_the_arms():
    """The retired balanced objective must not survive under another name."""
    surface = dir(proj)
    for banned in ("axis_scores", "combination", "combine", "balanced",
                   "rank_eligible", "primary_rank_key", "combined"):
        assert not any(banned in name for name in surface), banned


def test_low_pole_inverts_the_sign():
    s = proj.arm_scores(delta_a=1.0, delta_b=1.0, sign_a=-1, sign_b=1)
    assert s[ARM_A] == pytest.approx(1.0)


def test_an_unevaluated_arm_is_null_and_does_not_null_the_other():
    s = proj.arm_scores(delta_a=-1.0, delta_b=None, sign_a=1, sign_b=1)
    assert s[ARM_A] == pytest.approx(1.0)      # A still stands on its own
    assert s[ARM_B] is None


# --------------------------------------------------------------------------- #
# Concordance is descriptive only.
# --------------------------------------------------------------------------- #
def test_concordance_class_is_descriptive_and_keeps_both_values():
    assert proj.concordance_class({ARM_A: 1.0, ARM_B: 2.0}, EPS) == proj.CONCORDANT
    assert proj.concordance_class({ARM_A: 1.0, ARM_B: -2.0}, EPS) == proj.A_ONLY
    assert proj.concordance_class({ARM_A: -1.0, ARM_B: 2.0}, EPS) == proj.B_ONLY
    assert proj.concordance_class({ARM_A: -1.0, ARM_B: -2.0}, EPS) == proj.DISCORDANT
    assert proj.concordance_class({ARM_A: None, ARM_B: 1.0}, EPS) == proj.PARTIAL
    assert proj.concordance_class({ARM_A: None, ARM_B: None}, EPS) == proj.NOT_EVALUATED


# --------------------------------------------------------------------------- #
# Per-arm ranking.
# --------------------------------------------------------------------------- #
def _row(tid, a, b, a_ok=True, b_ok=True):
    return {"target_id": tid, ARM_A: a, ARM_B: b,
            "A_evaluable": a_ok, "B_evaluable": b_ok}


def _rank_both(rows):
    for arm in config.ARMS:
        proj.rank_arm(rows, arm,
                      evaluable_key=f"{config.ARM_POLE[arm]}_evaluable",
                      rank_column=config.ARM_RANK_COLUMN[arm])
    return {r["target_id"]: r for r in rows}


def test_neither_arm_can_buy_rank_in_the_other():
    """THE defect: a target opposing B must not outrank one that moves toward B."""
    rows = [_row("ENSG_ANTI_B", 5.0, -4.0), _row("ENSG_TOWARD_B", 0.1, 9.0)]
    by = _rank_both(rows)
    # A-arm: the strong-A target leads, as it should
    assert by["ENSG_ANTI_B"]["rank_away_from_A"] == 1
    assert by["ENSG_TOWARD_B"]["rank_away_from_A"] == 2
    # B-arm: the target that actually moves toward B leads. The large A score
    # buys it nothing.
    assert by["ENSG_TOWARD_B"]["rank_toward_B"] == 1
    assert by["ENSG_ANTI_B"]["rank_toward_B"] == 2


def test_each_arm_ranks_only_its_own_evaluable_population():
    rows = [_row("ENSG1", 9.0, 9.0, a_ok=False, b_ok=True),   # A ineligible
            _row("ENSG2", 1.0, 1.0, a_ok=True, b_ok=False),   # B ineligible
            _row("ENSG3", 0.5, 0.5)]
    by = _rank_both(rows)
    assert by["ENSG1"]["rank_away_from_A"] is None    # not A-evaluable
    assert by["ENSG1"]["rank_toward_B"] == 1         # ...but tops the B arm
    assert by["ENSG2"]["rank_toward_B"] is None      # not B-evaluable
    assert by["ENSG2"]["rank_away_from_A"] == 1      # ...and tops the A arm
    assert by["ENSG3"]["rank_away_from_A"] == 2
    assert by["ENSG3"]["rank_toward_B"] == 2


def test_a_null_arm_value_is_never_ranked_even_if_evaluable_is_true():
    rows = [_row("ENSG1", None, 1.0), _row("ENSG2", 2.0, 2.0)]
    by = _rank_both(rows)
    assert by["ENSG1"]["rank_away_from_A"] is None
    assert by["ENSG2"]["rank_away_from_A"] == 1


def test_rank_is_row_order_invariant_and_ties_break_on_stable_id():
    base = [_row("ENSG3", 0.2, 0.2), _row("ENSG1", 0.5, 0.5),
            _row("ENSG2", 0.5, 0.5)]
    one = _rank_both([dict(r) for r in base])
    two = _rank_both([dict(r) for r in reversed(base)])
    for tid in ("ENSG1", "ENSG2", "ENSG3"):
        assert one[tid]["rank_away_from_A"] == two[tid]["rank_away_from_A"]
    assert one["ENSG1"]["rank_away_from_A"] == 1     # tie broken by stable id
    assert one["ENSG2"]["rank_away_from_A"] == 2


def test_emit_order_is_by_target_id_not_by_any_arm():
    rows = [_row("ENSG9", 9.0, 0.0), _row("ENSG1", 0.1, 9.0)]
    assert [r["target_id"] for r in proj.emit_order(rows)] == ["ENSG1", "ENSG9"]


def test_sign_of_respects_the_epsilon():
    assert proj.sign_of(0.5, EPS) == 1
    assert proj.sign_of(-0.5, EPS) == -1
    assert proj.sign_of(0.0, EPS) == 0
    assert proj.sign_of(None, EPS) is None
