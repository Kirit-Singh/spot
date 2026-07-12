"""The verifier must REFUSE a tampered artifact. generator != verifier, proven.

A verifier that only ever passes is a rubber stamp. Each test here corrupts exactly one
claim in the shipped artifact, re-runs the standalone verifier over the bytes on disk,
and demands that the specific check which owns that claim fails.
"""
from __future__ import annotations

import json
import os

import fixtures_temporal as T
import pandas as pd
import pytest
from direct.temporal import run_temporal, verify_temporal


@pytest.fixture
def artifact(temporal_run):
    """A clean, passing temporal artifact and its provenance — the thing to attack."""
    res = run_temporal.build_temporal(temporal_run())
    out = res["out_dir"]
    with open(os.path.join(out, "temporal_provenance.json")) as fh:
        prov = json.load(fh)
    assert res["verification"]["verdict"] == verify_temporal.ADMIT
    return out, prov


def reverify(out_dir, prov, mutate):
    """Rewrite temporal.parquet through ``mutate`` and re-run the verifier on it."""
    path = os.path.join(out_dir, "temporal.parquet")
    df = pd.read_parquet(path)
    mutate(df).to_parquet(path, index=False)
    return verify_temporal.verify(out_dir=out_dir, provenance=prov)


def failed(report) -> set[str]:
    return {c["check"] for c in report["checks"] if c["status"] == verify_temporal.FAIL}


class TestTheVerifierIsNotVacuous:
    def test_a_clean_artifact_passes_every_check(self, artifact):
        out, prov = artifact
        report = verify_temporal.verify(out_dir=out, provenance=prov)
        assert report["verdict"] == verify_temporal.ADMIT
        assert report["n_failed"] == 0
        assert len(report["checks"]) >= 11

    def test_a_did_that_is_not_the_difference_of_its_endpoints_is_caught(self,
                                                                        artifact):
        out, prov = artifact

        def mutate(df):
            df.loc[df.index[0], "away_from_A_temporal_did"] = 99.0
            return df

        report = reverify(out, prov, mutate)
        assert report["verdict"] == verify_temporal.REJECT
        assert "did_equals_to_minus_from" in failed(report)

    def test_a_broken_antisymmetry_is_caught(self, artifact):
        out, prov = artifact

        def mutate(df):
            # nudge BOTH the DiD and its endpoint so the arithmetic check still passes:
            # only the reverse-record comparison can see this one
            m = ((df.target_id == T.MOVER) & (df.from_condition == T.REST)
                 & (df.to_condition == T.STIM48))
            i = df.index[m][0]
            df.loc[i, "away_from_A_to_value"] = df.loc[i, "away_from_A_to_value"] + 0.5
            df.loc[i, "away_from_A_temporal_did"] = (
                df.loc[i, "away_from_A_temporal_did"] + 0.5)
            return df

        report = reverify(out, prov, mutate)
        assert report["verdict"] == verify_temporal.REJECT
        assert "reversing_the_pair_negates_the_did" in failed(report)

    def test_a_reverse_record_that_was_dropped_is_caught(self, artifact):
        out, prov = artifact

        def mutate(df):
            m = ((df.target_id == T.MOVER) & (df.from_condition == T.STIM48)
                 & (df.to_condition == T.REST))
            return df[~m]

        report = reverify(out, prov, mutate)
        assert report["verdict"] == verify_temporal.REJECT
        assert "reversing_the_pair_negates_the_did" in failed(report)

    def test_a_forged_reliability_badge_is_caught(self, artifact):
        out, prov = artifact

        def mutate(df):
            df["A_reliability_badge"] = "above_interaction_floor"   # all of them
            return df

        report = reverify(out, prov, mutate)
        assert report["verdict"] == verify_temporal.REJECT
        assert "reliability_badge_rederives_from_policy" in failed(report)

    def test_a_loosened_threshold_is_caught_even_if_the_badge_agrees_with_it(
            self, artifact):
        out, prov = artifact

        def mutate(df):
            df["A_reliability_threshold"] = 0.0        # everything clears a zero floor
            df["A_reliability_badge"] = "above_interaction_floor"
            return df

        report = reverify(out, prov, mutate)
        assert report["verdict"] == verify_temporal.REJECT
        assert "reliability_badge_rederives_from_policy" in failed(report)

    def test_a_confounded_pair_quietly_relabelled_clean_is_caught(self, artifact):
        out, prov = artifact

        def mutate(df):
            m = (df.from_condition == T.REST) & (df.to_condition == T.STIM48)
            df.loc[m, "batch_partially_confounded"] = False
            df.loc[m, "batch_status"] = "batch_balanced_identical_composition"
            return df

        report = reverify(out, prov, mutate)
        assert report["verdict"] == verify_temporal.REJECT
        assert "batch_verdict_rederives_from_composition" in failed(report)

    def test_a_comparison_that_was_refused_is_caught(self, artifact):
        out, prov = artifact

        def mutate(df):
            df.loc[df.index[0], "refused"] = True
            return df

        report = reverify(out, prov, mutate)
        assert report["verdict"] == verify_temporal.REJECT
        assert "no_comparison_was_refused" in failed(report)

    def test_a_whole_comparison_dropped_from_the_artifact_is_caught(self, artifact):
        out, prov = artifact

        def mutate(df):
            return df[~((df.from_condition == T.STIM8)
                        & (df.to_condition == T.STIM48))]

        report = reverify(out, prov, mutate)
        assert report["verdict"] == verify_temporal.REJECT
        assert "all_ordered_pairs_both_directions_present" in failed(report)

    def test_a_combined_temporal_objective_is_caught(self, artifact):
        out, prov = artifact

        def mutate(df):
            # the retired balanced-skew score, smuggled back in a temporal coordinate
            df["combined_temporal_did"] = (df["away_from_A_temporal_did"]
                                           + df["toward_B_temporal_did"]) / 2
            return df

        report = reverify(out, prov, mutate)
        assert report["verdict"] == verify_temporal.REJECT
        # B4: refused at the ADMISSION gate now — the exact-column allowlist and the
        # recursive key firewall both catch it, before any claim is re-derived.
        assert failed(report) & {"temporal_columns_match_the_exact_allowlist",
                                 "no_forbidden_key_at_any_depth"}

    def test_a_smuggled_p_value_is_caught(self, artifact):
        out, prov = artifact

        def mutate(df):
            df["p_value"] = 0.01
            return df

        report = reverify(out, prov, mutate)
        assert report["verdict"] == verify_temporal.REJECT
        assert failed(report) & {"temporal_columns_match_the_exact_allowlist",
                                 "no_forbidden_key_at_any_depth"}

    def test_an_endpoint_that_does_not_match_the_within_condition_screen_is_caught(
            self, artifact):
        out, prov = artifact

        def mutate(df):
            # move BOTH endpoint values and the DiD consistently, so the arithmetic and
            # the antisymmetry still hold. Only the comparison against the emitted
            # within-condition rows can see that the endpoints are not the screen's.
            for col in ("away_from_A_from_value", "away_from_A_to_value"):
                df[col] = df[col] + 1.0
            return df

        report = reverify(out, prov, mutate)
        assert report["verdict"] == verify_temporal.REJECT
        assert "endpoints_are_the_within_condition_arm_values" in failed(report)

    def test_a_did_asserted_where_the_arm_was_never_estimated_is_caught(self,
                                                                       artifact):
        out, prov = artifact

        def mutate(df):
            i = df.index[0]
            df.loc[i, "A_temporal_status"] = "arm_not_evaluable_at_from_condition"
            return df

        report = reverify(out, prov, mutate)
        assert report["verdict"] == verify_temporal.REJECT
        assert "did_equals_to_minus_from" in failed(report)
