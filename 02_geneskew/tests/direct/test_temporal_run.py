"""The temporal cross-condition estimator, end to end on a three-condition release.

The fixture's arithmetic is known by hand (see ``fixtures_temporal``), so every DiD
asserted here is a number the test computed itself — never one the code reported.
"""
from __future__ import annotations

import os

import fixtures_temporal as T
import pandas as pd
import pytest
from direct.temporal import estimand as E
from direct.temporal import policy as P
from direct.temporal import run_temporal


@pytest.fixture(scope="module")
def _cache():
    return {}


@pytest.fixture
def built(temporal_run):
    args = temporal_run()
    res = run_temporal.build_temporal(args)
    df = pd.read_parquet(os.path.join(res["out_dir"], "temporal.parquet"))
    return res, df


def rec(df, target, from_cond, to_cond):
    hit = df[(df.target_id == target) & (df.from_condition == from_cond)
             & (df.to_condition == to_cond)]
    assert len(hit) == 1, f"expected exactly one record, got {len(hit)}"
    return hit.iloc[0]


class TestEveryComparisonIsComputed:
    def test_all_six_directed_pairs_are_emitted(self, built):
        _, df = built
        pairs = set(zip(df.from_condition, df.to_condition))
        assert len(pairs) == 6
        assert all(a != b for a, b in pairs)

    def test_no_comparison_is_refused_or_withheld(self, built):
        res, df = built
        assert res["n_comparisons"] == 6
        assert bool(df["refused"].any()) is False
        # one record per (target, ordered pair): nothing is filtered out of the artifact
        assert len(df) == df.target_id.nunique() * 6

    def test_both_directions_of_a_pair_are_present_and_negate_each_other(self, built):
        _, df = built
        fwd = rec(df, T.MOVER, T.REST, T.STIM48)
        rev = rec(df, T.MOVER, T.STIM48, T.REST)
        assert fwd["away_from_A_temporal_did"] == -rev["away_from_A_temporal_did"]
        assert fwd["toward_B_temporal_did"] == -rev["toward_B_temporal_did"]


class TestTheDiDIsTheDifferenceOfTwoWithinConditionArmValues:
    def test_the_did_equals_the_endpoint_arm_values_it_reports(self, built):
        _, df = built
        for _, r in df.iterrows():
            for arm in ("away_from_A", "toward_B"):
                did = r[f"{arm}_temporal_did"]
                a, b = r[f"{arm}_from_value"], r[f"{arm}_to_value"]
                if pd.isna(did):
                    continue
                assert did == pytest.approx(b - a, abs=1e-12)

    def test_the_mover_moves_by_exactly_the_amount_the_fixture_built(self, built):
        # away_from_A = -a_effect: Rest +1.0 -> Stim48hr +2.0, so the DiD is +1.0
        _, df = built
        r = rec(df, T.MOVER, T.REST, T.STIM48)
        assert r["away_from_A_from_value"] == pytest.approx(1.0)
        assert r["away_from_A_to_value"] == pytest.approx(2.0)
        assert r["away_from_A_temporal_did"] == pytest.approx(1.0)
        assert r["A_temporal_status"] == E.ESTIMATED

    def test_the_b_arm_moves_on_its_own_and_the_a_arm_does_not_follow_it(self, built):
        _, df = built
        r = rec(df, T.B_MOVER, T.REST, T.STIM48)
        assert r["toward_B_temporal_did"] == pytest.approx(1.2)
        assert r["away_from_A_temporal_did"] == pytest.approx(0.0)

    def test_each_endpoint_reports_its_own_rank_at_its_own_condition(self, built):
        _, df = built
        r = rec(df, T.MOVER, T.REST, T.STIM48)
        # the MOVER has the largest away_from_A at Stim48hr (+2.0), so it ranks first
        assert r["A_to_rank"] == 1
        assert r["A_from_rank"] >= 1

    def test_both_endpoints_report_their_own_joint_status_and_tier(self, built):
        _, df = built
        r = rec(df, T.MOVER, T.REST, T.STIM48)
        for col in ("from_joint_status", "to_joint_status", "from_pareto_tier",
                    "to_pareto_tier"):
            assert col in r.index

    def test_donor_and_guide_denominators_are_reported_at_each_condition(self, built):
        _, df = built
        r = rec(df, T.MOVER, T.REST, T.STIM48)
        for p in ("A", "B"):
            for end in ("from", "to"):
                assert r[f"{p}_{end}_n_splits_total"] >= 0
                assert r[f"{p}_{end}_n_guide_slots_released"] >= 0


class TestTheSyntheticZeroSignalControl:
    """A CONSTRUCTED zero-signal target must not move. This is NOT an NTC (M5).

    It proves the estimator fabricates no movement where its input holds none — a
    property of the code. A real non-targeting control would carry real donor and batch
    variation and would not come back exactly zero; that validation is PENDING and is not
    available from this effect representation (the DE object ships no NTC target rows —
    NTC is the contrast baseline, not a projectable row).
    """

    def test_an_unchanging_target_has_exactly_zero_did_on_every_pair(self, built):
        _, df = built
        still = df[df.target_id == T.STILL]
        assert len(still) == 6
        for _, r in still.iterrows():
            assert r["away_from_A_temporal_did"] == 0.0
            assert r["toward_B_temporal_did"] == 0.0

    def test_a_zero_shift_never_clears_the_interaction_floor(self, built):
        _, df = built
        for _, r in df[df.target_id == T.STILL].iterrows():
            assert r["A_reliability_badge"] == E.WITHIN_FLOOR
            assert r["B_reliability_badge"] == E.WITHIN_FLOOR


class TestTheConfoundPolicyOnRealRecords:
    def test_rest_to_stim8hr_is_clean_and_carries_no_batch_flag(self, built):
        _, df = built
        for a, b in [(T.REST, T.STIM8), (T.STIM8, T.REST)]:
            r = rec(df, T.MOVER, a, b)
            assert bool(r["batch_partially_confounded"]) is False
            assert r["batch_status"] == P.BATCH_CLEAN

    def test_every_stim48_pair_is_flagged_batch_partially_confounded(self, built):
        _, df = built
        for a, b in [(T.REST, T.STIM48), (T.STIM48, T.REST),
                     (T.STIM8, T.STIM48), (T.STIM48, T.STIM8)]:
            r = rec(df, T.MOVER, a, b)
            assert bool(r["batch_partially_confounded"]) is True
            assert r["batch_status"] == P.BATCH_PARTIALLY_CONFOUNDED
            assert r["donors_changing_replicate"] == "D1;D2"

    def test_a_flagged_pair_is_still_fully_estimated_never_blanked(self, built):
        _, df = built
        r = rec(df, T.MOVER, T.REST, T.STIM48)
        assert r["away_from_A_temporal_did"] == pytest.approx(1.0)
        assert r["A_temporal_status"] == E.ESTIMATED

    def test_the_not_identifiable_note_travels_on_every_record(self, built):
        _, df = built
        assert (df["not_identifiable_quantity"] == "pure_batch_effect").all()
        assert df["not_identifiable_reason"].str.contains("aliased").all()

    def test_no_batch_correction_is_applied_anywhere(self, built):
        _, df = built
        assert bool(df["batch_correction_applied"].any()) is False


class TestTheReliabilityBadge:
    def test_a_movement_that_clears_its_programs_floor_is_badged_above_it(self, built):
        _, df = built
        r = rec(df, T.MOVER, T.REST, T.STIM48)      # |DiD| = 1.0 vs 2 x 0.1568
        assert r["A_reliability_badge"] == E.ABOVE_FLOOR
        assert r["A_reliability_threshold"] == pytest.approx(0.3136, abs=1e-3)

    def test_a_real_but_small_movement_is_badged_within_the_floor(self, built):
        _, df = built
        r = rec(df, T.DRIFTER, T.REST, T.STIM48)    # |DiD| = 0.1 vs 0.3136
        assert r["away_from_A_temporal_did"] == pytest.approx(0.1)
        assert r["A_reliability_badge"] == E.WITHIN_FLOOR

    def test_the_exact_threshold_and_k_ship_with_every_badge(self, built):
        _, df = built
        assert (df["A_reliability_k"] == 2.0).all()
        assert (df["B_reliability_k"] == 2.0).all()
        r = rec(df, T.MOVER, T.REST, T.STIM48)
        assert r["A_interaction_std"] == pytest.approx(0.1568, abs=1e-3)
        assert r["B_interaction_std"] == pytest.approx(0.4348, abs=1e-3)

    def test_the_badge_is_computed_per_arm_from_that_arms_own_program(self, built):
        _, df = built
        r = rec(df, T.B_MOVER, T.REST, T.STIM48)
        # toward_B moves 1.2 against th17_like's 0.8695 floor -> above
        assert r["B_reliability_badge"] == E.ABOVE_FLOOR
        # away_from_A does not move at all against diff_naive's 0.3136 floor -> within
        assert r["A_reliability_badge"] == E.WITHIN_FLOOR


class TestSparsePanelCaution:
    def test_a_sparse_panel_program_carries_the_extra_caution_flag(self, built):
        _, df = built
        assert (df["B_sparse_panel_caution"]).all()      # th17_like
        assert not (df["A_sparse_panel_caution"]).any()  # diff_naive
        assert (df["sparse_panel_caution"]).all()        # either arm flags the record


class TestTheRecordSaysWhatItIs:
    def test_every_record_names_the_estimator_and_declares_no_calibrated_inference(
            self, built):
        _, df = built
        assert (df["estimator_id"] == "spot.stage02.temporal_cross_condition.v1").all()
        assert (df["inference_status"] == "not_calibrated").all()

    def test_no_p_or_q_column_exists_anywhere_in_the_artifact(self, built):
        _, df = built
        bad = [c for c in df.columns
               if c.lower() in ("pvalue", "p_value", "qvalue", "q_value", "fdr", "padj")]
        assert bad == []

    def test_the_estimand_is_declared_population_level_and_not_a_fate_claim(self, built):
        _, df = built
        assert (df["estimand_level"] == "population").all()
        assert not (df["estimand_is_per_cell_fate"]).any()
        assert not (df["estimand_is_lineage_traced"]).any()

    def test_the_temporal_run_has_its_own_id_and_its_own_method_hash(self, built):
        res, df = built
        assert res["temporal_run_id"]
        assert len(res["temporal_method_sha256"]) == 64
        assert (df["temporal_run_id"] == res["temporal_run_id"]).all()

    def test_a_rerun_of_the_same_science_reproduces_the_same_temporal_run_id(
            self, temporal_run):
        a = run_temporal.build_temporal(temporal_run())
        b = run_temporal.build_temporal(temporal_run())
        assert a["temporal_run_id"] == b["temporal_run_id"]
