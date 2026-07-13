"""The SHIPPED CLI, driven the way a runbook drives it — and a bundle that is not a pair's.

Two defects the in-process tests could never see, because they called `build_bundle` with a
fixture dataclass that happened to define every attribute the runtime reads:

  * THE CLI CRASHED. `build_parser()` defines no `donor_crosswalk` and no `selection`, but
    the production path reads both. A `RunArgs` has them; an `argparse.Namespace` does not.
    So every committed test passed while the only entry point a human can actually invoke
    died with AttributeError. These tests go through `build_parser().parse_args(...)`, so
    the parser and the runtime are held to the SAME contract.

  * THE "PAIR-INDEPENDENT" BUNDLE WAS NOT. `stage2_input_manifest` hashed `args.selection`,
    so changing the A/B programs of a pair the bundle never loaded, never read and never
    named still changed its identity. The rows were identical and the id was not — which is
    precisely the cache fragmentation the all-arm topology exists to remove. A bundle that
    declares `names_a_program_pair: false` must PROVE it: same inputs, same context, any
    unused pair, byte-identical bundle.
"""
from __future__ import annotations

import json
import os

import pytest
from direct import run_arms


def argv_for(args, *, condition: str, out_root: str) -> list[str]:
    """THE argv a runbook writes. Only flags the parser actually defines — no pair."""
    argv = ["--condition", condition, "--out-root", out_root,
            "--de-main", args.de_main, "--lane", args.lane]
    for flag, value in (("--registry", args.registry),
                        ("--by-guide", args.by_guide),
                        ("--by-donors", args.by_donors),
                        ("--sgrna", args.sgrna),
                        ("--guide-manifest", args.guide_manifest),
                        ("--source-registry", args.source_registry),
                        ("--stage1-release", args.stage1_release),
                        ("--stage1-validation", args.stage1_validation),
                        ("--stage1-gate-spec", args.stage1_gate_spec),
                        ("--donor-crosswalk", args.donor_crosswalk),
                        ("--target-identity-map", getattr(args, "target_identity_map", None)),
                        ("--pseudobulk", args.pseudobulk),
                        ("--strict-replay-source",
                         getattr(args, "strict_replay_source", None)),
                        ("--env-lock", args.env_lock)):
        if value:
            argv += [flag, value]
    if getattr(args, "allow_dirty_tree", False):
        argv.append("--allow-dirty-tree")
    if getattr(args, "strict_replay", False):
        argv.append("--strict-replay")
    return argv


class TestTheShippedCLIActuallyRuns:
    """BLOCKER 1. Not 'the function works' — the COMMAND works."""

    def test_the_CLI_emits_a_bundle_end_to_end(self, synthetic_run, tmp_path):
        args = synthetic_run()
        out_root = str(tmp_path / "cli")
        result = run_arms.main(argv_for(args, condition="StimX", out_root=out_root))

        assert result["n_arm_slots"] == result["n_expected_arm_slots"]
        assert result["n_arm_rows"] > 0
        for name in (run_arms.ROWS_FILE, run_arms.BUNDLE_FILE):
            assert os.path.exists(os.path.join(result["out_dir"], name))

    def test_the_parser_defines_EVERY_attribute_the_runtime_reads(self, synthetic_run,
                                                                  tmp_path):
        # the exact crash: 'Namespace' object has no attribute 'donor_crosswalk'
        args = synthetic_run()
        ns = run_arms.build_parser().parse_args(
            argv_for(args, condition="StimX", out_root=str(tmp_path / "ns")))
        assert hasattr(ns, "donor_crosswalk")
        run_arms.build_bundle(ns)          # would raise AttributeError before the repair

    def test_the_parser_defines_NO_pair_selection_at_all(self, synthetic_run, tmp_path):
        # not "defaults to None" — the all-arm producer has no such input to be given
        args = synthetic_run()
        ns = run_arms.build_parser().parse_args(
            argv_for(args, condition="StimX", out_root=str(tmp_path / "ns")))
        assert not hasattr(ns, "selection")
        with pytest.raises(SystemExit):
            run_arms.build_parser().parse_args(
                argv_for(args, condition="StimX", out_root=str(tmp_path / "ns2"))
                + ["--selection", args.selection])


class TestAnUnusedPairCannotMoveTheBundle:
    """BLOCKER 5. The bundle's identity may not be a function of a pair it never loaded."""

    def _build(self, args, out_root: str):
        result = run_arms.build_bundle(args)
        with open(os.path.join(result["out_dir"], run_arms.BUNDLE_FILE), "rb") as fh:
            bundle_bytes = fh.read()
        with open(os.path.join(result["out_dir"], run_arms.ROWS_FILE), "rb") as fh:
            rows_bytes = fh.read()
        return result, bundle_bytes, rows_bytes

    def test_changing_the_UNUSED_pair_leaves_the_bundle_BYTE_IDENTICAL(
            self, synthetic_run, tmp_path):
        args = synthetic_run()
        args.condition = "StimX"

        args.out_root = str(tmp_path / "a")
        first, first_bundle, first_rows = self._build(args, args.out_root)

        # the SAME measurement, with a DIFFERENT pair sitting unused on the command line
        other = synthetic_run()
        rewritten = str(tmp_path / "other_selection.json")
        with open(other.selection) as fh:
            contract = json.load(fh)
        contract["A"]["program_id"], contract["B"]["program_id"] = (
            contract["B"]["program_id"], contract["A"]["program_id"])
        with open(rewritten, "w") as fh:
            json.dump(contract, fh)
        args.selection = rewritten

        args.out_root = str(tmp_path / "b")
        second, second_bundle, second_rows = self._build(args, args.out_root)

        assert first["arm_bundle_run_id"] == second["arm_bundle_run_id"], (
            "the bundle's identity moved when a pair it never loaded changed")
        assert first_bundle == second_bundle
        assert first_rows == second_rows

    def test_the_bundle_is_identical_when_NO_selection_attribute_exists_at_all(
            self, synthetic_run, tmp_path):
        # a Namespace from the real parser has no `selection`; a RunArgs does. They must
        # produce the same bundle, or the CLI and the fixture are two different producers.
        args = synthetic_run()
        args.condition = "StimX"
        args.out_root = str(tmp_path / "with")
        with_selection, _, _ = self._build(args, args.out_root)

        ns = run_arms.build_parser().parse_args(
            argv_for(args, condition="StimX", out_root=str(tmp_path / "without")))
        without = run_arms.build_bundle(ns)

        assert with_selection["arm_bundle_run_id"] == without["arm_bundle_run_id"]

    def test_NO_selection_contract_is_hashed_into_the_bundle_inputs(self, synthetic_run,
                                                                    tmp_path):
        args = synthetic_run()
        args.condition = "StimX"
        args.out_root = str(tmp_path / "inputs")
        result = run_arms.build_bundle(args)
        blob = json.dumps(result["provenance"]["run_binding"])
        assert "selection_contract" not in blob
        names = {i["name"] for i in
                 result["provenance"]["run_binding"]["stage2_inputs"]}
        assert not any("selection" in n for n in names), names
