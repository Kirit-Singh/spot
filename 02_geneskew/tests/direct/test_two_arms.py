"""The ordered two-state contract, asserted end to end on emitted artifacts.

This is the regression suite for the arbitrary-contrast defect: an arbitrary
A-to-B dropdown question was silently made one-sided, so a perturbation moving
strongly away from A while OPPOSING B outranked one that genuinely moved toward
B, and the second dropdown was decorative.
"""
import json
import os

import pandas as pd
import pytest
from direct import config
from direct.run_screen import build_screen
from fixtures_direct import TARGET_GENES

ANTI_B = TARGET_GENES[10]        # strong away-from-A, NEGATIVE toward-B
TOWARD_B = TARGET_GENES[11]      # weak away-from-A, STRONG toward-B
A_ONLY = TARGET_GENES[12]        # A-evaluable, B-ineligible
B_ONLY = TARGET_GENES[13]        # B-evaluable, A-ineligible


@pytest.fixture
def screen(synthetic_run):
    result = build_screen(synthetic_run())
    df = pd.read_parquet(os.path.join(result["out_dir"], "screen.parquet"))
    return result, df.set_index("target_id")


def _prov(result):
    with open(os.path.join(result["out_dir"], "provenance.json")) as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- #
# The defect itself.
# --------------------------------------------------------------------------- #
def test_a_target_opposing_B_cannot_outrank_one_that_moves_toward_B(screen):
    _, df = screen
    anti, toward = df.loc[ANTI_B], df.loc[TOWARD_B]

    # the fixture really does encode the attack
    assert anti["away_from_A"] > toward["away_from_A"]     # 8.0 vs 0.05
    assert anti["toward_B"] < 0 < toward["toward_B"]       # -4.0 vs 9.0

    # A arm: the strong-A target leads, correctly
    assert anti["rank_away_from_A"] < toward["rank_away_from_A"]

    # B arm: the target that ACTUALLY moves toward B leads. Its tiny A score buys
    # it nothing, and the anti-B target's huge A score buys IT nothing.
    assert toward["rank_toward_B"] == 1
    assert anti["rank_toward_B"] > toward["rank_toward_B"]


def test_the_two_arms_produce_genuinely_different_orderings(screen):
    result, df = screen
    a_order = df["rank_away_from_A"].dropna().sort_values().index.tolist()
    b_order = df["rank_toward_B"].dropna().sort_values().index.tolist()
    assert a_order != b_order, "the arms are one ranking wearing two names"
    v = result["verification"]["ranking"]
    assert v["arms_rank_independently"] is True
    assert v["arm_ranks_all_valid"] is True


def test_neither_arm_gates_the_other(screen):
    _, df = screen
    # A-evaluable / B-ineligible
    a = df.loc[A_ONLY]
    assert bool(a["A_evaluable"]) is True
    assert bool(a["B_evaluable"]) is False
    assert pd.notna(a["rank_away_from_A"])
    assert pd.isna(a["rank_toward_B"])
    assert pd.isna(a["toward_B"])
    assert a["B_state"] == "insufficient_axis_coverage"
    assert a["A_state"] == "evaluable"

    # B-evaluable / A-ineligible: the exact mirror
    b = df.loc[B_ONLY]
    assert bool(b["B_evaluable"]) is True
    assert bool(b["A_evaluable"]) is False
    assert pd.notna(b["rank_toward_B"])
    assert pd.isna(b["rank_away_from_A"])
    assert pd.isna(b["away_from_A"])
    assert b["A_state"] == "insufficient_axis_coverage"


def test_each_arm_ranks_only_its_own_evaluable_population(screen):
    _, df = screen
    for arm in config.ARMS:
        rank_col = config.ARM_RANK_COLUMN[arm]
        evaluable = df[f"{config.ARM_POLE[arm]}_evaluable"].astype(bool)
        ranked = df[rank_col].notna()
        assert not (ranked & ~evaluable).any(), f"{arm}: a non-evaluable row is ranked"
        assert sorted(df.loc[ranked, rank_col]) == list(range(1, int(ranked.sum()) + 1))


# --------------------------------------------------------------------------- #
# No combined objective, under any name.
# --------------------------------------------------------------------------- #
def test_no_combined_or_headline_field_survives_anywhere(screen):
    result, df = screen
    banned = {"rank", "primary_rank", "headline_rank", "combination",
              "combination_state", "balanced_skew", "combined_score", "total_skew",
              "arms_both_positive", "is_eligible", "desired_target_modulation"}
    assert not (banned & set(df.columns))

    v = result["verification"]["ranking"]
    assert v["no_headline_rank"] is True
    assert v["no_combined_objective"] is True
    assert result["verification"]["no_legacy_columns"] is True

    # and no emitted value equals the retired (A+B)/2 objective
    both = df[df["away_from_A"].notna() & df["toward_B"].notna()]
    mean = (both["away_from_A"] + both["toward_B"]) / 2
    for col in df.select_dtypes("number").columns:
        if col in ("away_from_A", "toward_B"):
            continue
        assert not both[col].equals(mean), f"{col} is the balanced objective in disguise"


def test_emission_order_is_not_a_headline_rank(screen):
    _, df = screen
    assert list(df.index) == sorted(df.index)     # by target id, not by any arm


# --------------------------------------------------------------------------- #
# Direction: conflicts preserved, never resolved.
# --------------------------------------------------------------------------- #
def test_conflicting_arm_directions_are_preserved_as_conflict(screen):
    _, df = screen
    anti = df.loc[ANTI_B]
    # knockdown moves A the desired way but moves B the WRONG way
    assert anti["A_desired_target_modulation"] == "decrease"
    assert anti["B_desired_target_modulation"] == "increase"
    assert anti["desired_modulation_agreement"] == "conflict"
    # both directions stay emitted; no winner was chosen
    assert anti["A_desired_target_modulation"] != anti["B_desired_target_modulation"]


def test_agreement_is_reported_when_the_arms_agree(screen):
    _, df = screen
    toward = df.loc[TOWARD_B]
    assert toward["A_desired_target_modulation"] == "decrease"
    assert toward["B_desired_target_modulation"] == "decrease"
    assert toward["desired_modulation_agreement"] == "agree"


def test_a_single_evaluated_arm_yields_no_collapsed_direction(screen):
    _, df = screen
    a = df.loc[A_ONLY]
    assert a["B_desired_target_modulation"] == "not_evaluated"
    assert a["desired_modulation_agreement"] == "only_away_from_A_evaluated"


def test_concordance_class_is_descriptive_and_never_gates(screen):
    _, df = screen
    assert df.loc[ANTI_B, "concordance_class"] == "away_from_A_only"
    assert df.loc[TOWARD_B, "concordance_class"] == "concordant_both_arms"
    assert df.loc[A_ONLY, "concordance_class"] == "partially_evaluated"
    # the descriptive class did not stop either arm being ranked on its own merits
    assert pd.notna(df.loc[ANTI_B, "rank_away_from_A"])
    assert pd.notna(df.loc[ANTI_B, "rank_toward_B"])


# --------------------------------------------------------------------------- #
# Arm-specific support is never shared.
# --------------------------------------------------------------------------- #
def test_support_is_per_arm_shaped_but_carries_no_value_in_either_arm(screen):
    """The support tables stay keyed BY ARM — the release ships these estimates and the
    shape must not quietly collapse — but neither arm gets a value from them.

    A projected support value would be a number with no mask behind it, and it would
    then flow into replication and the evidence tier. So the arm-specificity that is
    asserted here is structural, not numeric: there is no number to differ.
    """
    result, df = screen
    guide = pd.read_parquet(os.path.join(result["out_dir"], "guide_support.parquet"))
    donor = pd.read_parquet(os.path.join(result["out_dir"], "donor_support.parquet"))

    # both support tables are keyed BY ARM
    assert set(guide["arm"]) == set(config.ARMS)
    assert set(donor["arm"]) == set(config.ARMS)

    # ...and in BOTH arms the slot is unevaluated, unmapped and unvalued
    g = guide[(guide["target_id"] == ANTI_B)
              & (guide["estimate_id"] == "guide_1")].set_index("arm")
    assert set(g.index) == set(config.ARMS)
    for arm in config.ARMS:
        assert pd.isna(g.loc[arm, "value"])
        assert bool(g.loc[arm, "evaluated"]) is False
        assert pd.isna(g.loc[arm, "guide_id"])

    # per-arm coverage counts and per-arm replication both exist
    for pole in ("A", "B"):
        for field in ("panel_surviving", "guide_replication_state",
                      "n_guides_evaluated", "donor_split_support", "evidence_tier",
                      "support_state"):
            assert f"{pole}_{field}" in df.columns


def test_arm_bindings_are_in_the_run_binding(screen):
    result, _ = screen
    method = _prov(result)["run_binding"]["stage2_method"]
    assert method["arms"] == list(config.ARMS)
    assert method["arm_rank_column"] == dict(config.ARM_RANK_COLUMN)
    assert method["combined_objective_permitted"] is False
    assert method["headline_arm_permitted"] is False

    contract = _prov(result)["stage2_direct_contract"]["screen"]
    assert contract["no_headline_rank"] is True
    assert contract["no_combined_objective"] is True
    assert contract["arm_rank_columns"] == dict(config.ARM_RANK_COLUMN)


def test_null_ranks_survive_the_parquet_round_trip(screen):
    result, df = screen
    for arm in config.ARMS:
        col = config.ARM_RANK_COLUMN[arm]
        assert str(df[col].dtype) == "Int64"          # never a NaN float
        assert df[col].isna().any()                   # some rows really are null
        # a null rank must not silently become 0 or -1
        assert (df[col].dropna() >= 1).all()
