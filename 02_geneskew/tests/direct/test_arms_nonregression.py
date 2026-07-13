"""Enabling the ALL-ARM producer does not move one number in the legacy Direct payload.

The audit ran the same synthetic legacy input at the parent commit and at head and compared
all five legacy Parquets. Every scientific value was identical; only `run_id` differed, and it
differed for a legitimate reason — the reproducible code digest includes the new source files,
so adding any file to the package changes the run id by design.

That is a SCIENTIFIC non-regression, not byte identity of the content-addressed run, and the
distinction is worth keeping honest: a test that demanded byte identity would fail the moment
anyone added a module, and a test that demanded nothing would not notice the pair screen
quietly changing.

So this pins the property that actually matters: the all-arm producer writes into its OWN
bundle directory and cannot reach the legacy artifacts, and the legacy screen computes the
same science whether or not an arm bundle was built beside it.
"""
from __future__ import annotations

import os

import pandas as pd
from direct import run_arms
from direct.hashing import content_hash
from direct.run_screen import build_screen

LEGACY_PARQUETS = ("screen.parquet", "masks.parquet", "contributing_guides.parquet",
                   "guide_support.parquet", "donor_support.parquet")


def scientific_content(out_dir: str) -> dict[str, str]:
    """Every legacy artifact's content, with `run_id` set aside.

    `run_id` is EXCLUDED deliberately: it binds the code tree, so it moves whenever a file is
    added to the package. Excluding it is what makes this a test of the SCIENCE rather than a
    test of the file list.
    """
    out: dict[str, str] = {}
    for name in LEGACY_PARQUETS:
        df = pd.read_parquet(os.path.join(out_dir, name))
        df = df[[c for c in df.columns if c != "run_id"]]
        out[name] = content_hash(
            df.sort_index(axis=1).to_json(orient="records", double_precision=15))
    return out


class TestTheAllArmProducerLeavesTheLegacyDirectPayloadAlone:
    def test_the_legacy_science_is_IDENTICAL_before_and_after_an_arm_bundle_is_built(
            self, synthetic_run, tmp_path):
        first = build_screen(synthetic_run())
        before = scientific_content(first["out_dir"])

        arm_args = synthetic_run()
        arm_args.condition = "StimX"
        arm_args.out_root = str(tmp_path / "arms")
        run_arms.build_bundle(arm_args)

        second = build_screen(synthetic_run())
        after = scientific_content(second["out_dir"])

        assert before == after, (
            "the all-arm producer changed the legacy Direct scientific payload")

    def test_the_arm_bundle_writes_ONLY_into_its_own_directory(self, synthetic_run,
                                                               tmp_path):
        # a producer that could overwrite a legacy artifact could silently retire one
        legacy = build_screen(synthetic_run())
        legacy_files = {
            name: open(os.path.join(legacy["out_dir"], name), "rb").read()
            for name in LEGACY_PARQUETS
        }

        arm_args = synthetic_run()
        arm_args.condition = "StimX"
        arm_args.out_root = legacy["out_dir"]        # aimed straight at the legacy run dir
        result = run_arms.build_bundle(arm_args)

        # the bundle went into its OWN content-addressed subdirectory...
        assert os.path.dirname(result["out_dir"].rstrip("/")) == legacy["out_dir"]
        # ...and every legacy artifact is byte-for-byte what it was
        for name, blob in legacy_files.items():
            with open(os.path.join(legacy["out_dir"], name), "rb") as fh:
                assert fh.read() == blob, f"the arm producer overwrote {name}"

    def test_the_legacy_screen_still_emits_its_own_pair_arms(self, synthetic_run):
        # the all-arm bundle removes pair fields from ITS OWN output; it does not retire the
        # pair screen, which is a different artifact answering a different question
        result = build_screen(synthetic_run())
        screen = pd.read_parquet(os.path.join(result["out_dir"], "screen.parquet"))
        assert "rank_away_from_A" in screen.columns
        assert "rank_toward_B" in screen.columns
