"""The temporal layer must not alter the within-condition result. At all.

Two independent guarantees, both enforced here:

  1. STRUCTURAL — ``runid.code_tree_sha256`` lists only the .py files directly in the
     direct package directory, so the ``temporal`` SUBPACKAGE is invisible to it. No
     amount of temporal code can move a within-condition ``run_id``.
  2. NUMERICAL — the endpoint arm values and ranks the temporal layer differences are
     the EXACT values the within-condition screen published for the same condition,
     because both come from the one ``run_screen.condition_rows`` pass. Not "the same
     formula": the same call.

The golden hash below was captured from the within-condition build BEFORE the temporal
layer existed. If a temporal change ever moves a within-condition score, rank or tier,
this test is what fails.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil

import fixtures_temporal as T
import pandas as pd
import pytest
from direct import config as direct_config
from direct import run_screen, runid
from direct.hashing import canonical_json
from direct.temporal import run_temporal

# Captured at commit d5c71c3 (handoff: READY-FOR-REAL-RUN), before any temporal code
# existed, over the default single-condition synthetic fixture. Every screen column
# except run_id — that is, every scientific value, both arm scores, both ranks, the
# Pareto tiers, the masks, the QC and the dispositions.
# RE-PINNED (round 3). The fixture's DE object now carries realistic gene SYMBOLS in
# var/gene_name (a real GMT names genes by symbol, and the B1 crosswalk reads that column),
# so the fixture FILE's bytes changed and with them `effect_source_sha256` — which every
# screen row carries. PROVEN metadata-only: with `effect_source_sha256` excluded, the
# scientific content hashes IDENTICALLY to the pre-change value (6667465c…). The only two
# columns that moved are run_id and effect_source_sha256. Nothing scientific changed.
GOLDEN_SCREEN_CONTENT_SHA256 = (
    "4297af4537c8ddfc7ed4f8c8d5e5318b3a1149cfe8769388c0d62987138e3261")

# THE DURABLE INVARIANT: every scientific value, independent of which bytes the fixture
# source happens to have. This one does NOT move when the fixture's metadata changes, and
# it is the assertion that actually protects the science.
GOLDEN_SCREEN_SCIENCE_SHA256 = (
    "6667465c70a6c7dfa7a0194c45fd2b669f7fe570a21669c95663e3efaee8fa49")
GOLDEN_MASK_SHA256 = (
    "f3eea380f23f8714b7b77cbc7a2e385cd375c5fbc81b7df7892065d1f80f2f09")


def _scientific_content_sha256(df: pd.DataFrame) -> str:
    """Every emitted column except the run identifier."""
    rows = json.loads(df.drop(columns=["run_id"]).to_json(orient="records"))
    return hashlib.sha256(canonical_json(rows).encode()).hexdigest()


def _science_sha256(df: pd.DataFrame) -> str:
    """Every SCIENTIFIC value, independent of the fixture source's bytes.

    `effect_source_sha256` pins WHICH file produced the row — it is provenance, not a
    measurement. Excluding it gives the invariant that must never move for a reason that
    is not scientific.
    """
    rows = json.loads(
        df.drop(columns=["run_id", "effect_source_sha256"]).to_json(orient="records"))
    return hashlib.sha256(canonical_json(rows).encode()).hexdigest()


class TestTheWithinConditionScreenIsUnmoved:
    def test_every_within_condition_scientific_value_is_byte_identical(self,
                                                                       synthetic_run):
        res = run_screen.build_screen(synthetic_run())
        df = pd.read_parquet(os.path.join(res["out_dir"], "screen.parquet"))
        assert _scientific_content_sha256(df) == GOLDEN_SCREEN_CONTENT_SHA256
        assert res["mask_sha256"] == GOLDEN_MASK_SHA256

    def test_the_science_is_INVARIANT_to_the_fixture_sources_bytes(self, synthetic_run):
        """The durable one. This hash has not moved since the estimator was built, and it
        must not move for any reason that is not a change to the science."""
        res = run_screen.build_screen(synthetic_run())
        df = pd.read_parquet(os.path.join(res["out_dir"], "screen.parquet"))
        assert _science_sha256(df) == GOLDEN_SCREEN_SCIENCE_SHA256

    def test_running_the_temporal_layer_leaves_the_screen_bit_for_bit_the_same(
            self, temporal_run):
        args = temporal_run()
        before = run_screen.build_screen(args)
        before_df = pd.read_parquet(os.path.join(before["out_dir"], "screen.parquet"))

        run_temporal.build_temporal(args)

        after = run_screen.build_screen(args)
        after_df = pd.read_parquet(os.path.join(after["out_dir"], "screen.parquet"))
        assert after["run_id"] == before["run_id"]
        assert after["mask_sha256"] == before["mask_sha256"]
        assert _scientific_content_sha256(after_df) == _scientific_content_sha256(
            before_df)

    def test_the_direct_code_tree_cannot_see_the_temporal_subpackage(self, tmp_path):
        # The structural guarantee. If this ever fails, a temporal edit has started
        # changing within-condition run identity, and the additivity claim is false.
        direct_dir = os.path.dirname(os.path.abspath(run_screen.__file__))
        before = runid.code_tree_sha256(direct_dir)

        temporal_dir = os.path.join(direct_dir, "temporal")
        intruder = os.path.join(temporal_dir, "_invariance_probe.py")
        try:
            with open(intruder, "w") as fh:
                fh.write("# a new temporal module appears\n")
            assert runid.code_tree_sha256(direct_dir) == before
        finally:
            os.path.exists(intruder) and os.remove(intruder)

    def test_editing_a_direct_module_still_does_change_the_run_id(self, tmp_path):
        # The other half of the same claim: the code-tree binding is real, not inert.
        # A within-condition run_id that could NOT notice a direct edit would be a
        # weaker guarantee, not a stronger one.
        direct_dir = os.path.dirname(os.path.abspath(run_screen.__file__))
        before = runid.code_tree_sha256(direct_dir)
        probe = os.path.join(direct_dir, "_invariance_probe.py")
        try:
            with open(probe, "w") as fh:
                fh.write("# a new direct module appears\n")
            assert runid.code_tree_sha256(direct_dir) != before
        finally:
            os.path.exists(probe) and os.remove(probe)


class TestTheEndpointsAreTheScreen:
    def test_the_endpoint_rows_reproduce_the_screen_exactly_at_its_own_condition(
            self, temporal_run):
        args = temporal_run(analysis_condition=T.STIM8)
        screen = run_screen.build_screen(args)
        sdf = pd.read_parquet(os.path.join(screen["out_dir"], "screen.parquet"))

        res = run_temporal.build_temporal(args)
        edf = pd.read_parquet(os.path.join(res["out_dir"], "endpoints.parquet"))
        edf = edf[edf.condition == T.STIM8]

        cols = list(direct_config.ARMS) + list(
            direct_config.ARM_RANK_COLUMN.values()) + [
            "pareto_tier", "joint_status", "A_evaluable", "B_evaluable",
            "base_qc_state", "estimate_mask_sha256"]
        left = sdf.set_index("target_id")[cols].sort_index()
        right = edf.set_index("target_id")[cols].sort_index()
        pd.testing.assert_frame_equal(left, right, check_dtype=False)

    def test_the_did_the_layer_reports_is_a_difference_of_those_exact_values(
            self, temporal_run):
        args = temporal_run()
        res = run_temporal.build_temporal(args)
        tdf = pd.read_parquet(os.path.join(res["out_dir"], "temporal.parquet"))
        edf = pd.read_parquet(os.path.join(res["out_dir"], "endpoints.parquet"))
        by = {(r.target_id, r.condition): r for _, r in edf.iterrows()}

        for _, r in tdf.iterrows():
            for arm in direct_config.ARMS:
                if pd.isna(r[f"{arm}_temporal_did"]):
                    continue
                a = by[(r.target_id, r.from_condition)][arm]
                b = by[(r.target_id, r.to_condition)][arm]
                assert r[f"{arm}_temporal_did"] == pytest.approx(b - a, abs=1e-12)


class TestTheConditionLabelPermutationControl:
    """Permuting the condition labels must permute the estimate, and nothing else.

    If the estimator read anything except the two labelled endpoints — a cached value,
    a row order, an index — a permuted release would not produce the exactly-permuted
    answer. This is what proves the DiD is a function of its endpoints alone.
    """

    def _did(self, df, target, a, b, arm="away_from_A"):
        hit = df[(df.target_id == target) & (df.from_condition == a)
                 & (df.to_condition == b)]
        return float(hit.iloc[0][f"{arm}_temporal_did"])

    def _run(self, temporal_run, specs):
        res = run_temporal.build_temporal(temporal_run(specs))
        return pd.read_parquet(os.path.join(res["out_dir"], "temporal.parquet"))

    def test_swapping_two_conditions_labels_swaps_the_estimate_exactly(
            self, temporal_run):
        honest = self._run(temporal_run, T.temporal_specs())
        permuted = self._run(temporal_run, T.permuted_specs())

        # The MOVER's Rest and Stim48hr effect vectors have traded places, so the
        # forward estimate on the permuted release must be the honest REVERSE estimate.
        assert self._did(honest, T.MOVER, T.REST, T.STIM48) == pytest.approx(1.0)
        assert self._did(permuted, T.MOVER, T.REST, T.STIM48) == pytest.approx(
            self._did(honest, T.MOVER, T.STIM48, T.REST))
        assert self._did(permuted, T.MOVER, T.REST, T.STIM48) == pytest.approx(-1.0)

    def test_a_release_with_no_temporal_signal_yields_no_temporal_movement(
            self, temporal_run):
        # Every target gets the same effect vector at every condition — the whole-table
        # SYNTHETIC ZERO-SIGNAL control (M5; not an NTC). Every DiD on every pair must be
        # exactly zero: the estimator must invent no movement where the input has none.
        df = self._run(temporal_run, T.flattened_specs())
        for arm in direct_config.ARMS:
            assert (df[f"{arm}_temporal_did"].abs() == 0.0).all()

    def test_the_batch_flags_do_not_move_when_the_biology_does(self, temporal_run):
        # The confound is a property of the DESIGN, not of the effect sizes. A permuted
        # release has the same donor/replicate composition, so it must carry the same
        # flags — a flag that tracked the data would be a flag that could be tuned.
        honest = self._run(temporal_run, T.temporal_specs())
        flat = self._run(temporal_run, T.flattened_specs())
        key = ["from_condition", "to_condition", "batch_status",
               "batch_partially_confounded"]
        a = honest[key].drop_duplicates().sort_values(key).reset_index(drop=True)
        b = flat[key].drop_duplicates().sort_values(key).reset_index(drop=True)
        pd.testing.assert_frame_equal(a, b)


class TestTheTemporalRunStandsApart:
    def test_it_writes_its_own_directory_and_never_into_the_screens(self, temporal_run):
        args = temporal_run()
        screen = run_screen.build_screen(args)
        res = run_temporal.build_temporal(args)
        assert res["out_dir"] != screen["out_dir"]
        assert sorted(os.listdir(res["out_dir"])) == [
            "endpoints.parquet", "temporal.parquet", "temporal_provenance.json",
            "temporal_verification.json"]
        # the screen's directory is untouched: no temporal file was added to it
        assert not any(f.startswith("temporal")
                       for f in os.listdir(screen["out_dir"]))

    def test_deleting_the_temporal_output_leaves_the_screen_intact(self, temporal_run):
        args = temporal_run()
        screen = run_screen.build_screen(args)
        before = _scientific_content_sha256(
            pd.read_parquet(os.path.join(screen["out_dir"], "screen.parquet")))
        res = run_temporal.build_temporal(args)
        shutil.rmtree(res["out_dir"])
        after = _scientific_content_sha256(
            pd.read_parquet(os.path.join(screen["out_dir"], "screen.parquet")))
        assert after == before
