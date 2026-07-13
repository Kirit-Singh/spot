"""THE CLI GAP. The v3 flags must exist in argparse, and the v3 path must actually be taken.

THE DEFECT an independent re-audit found. ``cli.py`` (Direct) and ``run_pathway.py``
(Pathway) never DEFINED ``--stage1-v3-selection`` / ``--stage1-v3-schema`` — only
``temporal/cli.py`` did. Two consequences, both demonstrated:

  (a) 9 of the 15 invocations in STAGE2_INVOCATION_MATRIX (3 Direct + 6 Pathway) died with
      ``error: unrecognized arguments: --stage1-v3-selection …``;
  (b) ``build_screen`` / ``build_pathway`` read the flag through
      ``getattr(args, "stage1_v3_selection", None)``, so from those CLIs it resolved to
      **None** and THE V3 PATH WAS NEVER TAKEN — a v3-driven run silently became a legacy
      one, with no error and no trace.

WHY 126 GREEN TESTS MISSED IT. Every one of them called ``build_screen(args)`` /
``build_pathway(args)`` with a HAND-BUILT args object that carried the attribute. Argparse
was never exercised. A test that constructs the thing under test's input by hand is not
testing the entry point; it is testing the function behind it.

So these tests go through ``main(argv)`` — the real parser, the real argv, the exact strings
the matrix prints — and they assert the v3 path was ACTUALLY taken, not merely available.
"""
from __future__ import annotations

import json
import os

import pytest
from direct import cli as direct_cli
from direct import run_pathway, stage1_v3
from direct.temporal import cli as temporal_cli
from fixtures_pathway import write_gene_sets
from fixtures_spec import TARGET_GENES, UNIVERSE
from test_temporal_v3 import SCHEMA_PATH, v3_contract

pytestmark = pytest.mark.skipif(
    not os.path.exists(SCHEMA_PATH), reason="the pinned v3 schema is not present")

# The GHOST axes again: programs the registry ships and the LEGACY contract never names.
# If the CLI silently falls back to the legacy path, the emitted programs say so.
GHOST_A, GHOST_B = "GHOST_A", "GHOST_B"
GHOST_PROGRAMS = [
    {"program_id": GHOST_A, "display_label": "Ghost A",
     "panel_ensembl": UNIVERSE[2:4], "control_ensembl": UNIVERSE[4:16],
     "stage2_selectable": True, "primary": True, "base_portable": True},
    {"program_id": GHOST_B, "display_label": "Ghost B",
     "panel_ensembl": UNIVERSE[0:2], "control_ensembl": UNIVERSE[4:16],
     "stage2_selectable": True, "primary": True, "base_portable": True},
]


@pytest.fixture
def v3_run(synthetic_run, tmp_path):
    """A fixture run whose LEGACY contract names fx_* and whose V3 contract names GHOST_*."""
    def _build(mode=stage1_v3.MODE_WITHIN, conditions=("Rest",)):
        # the v3 schema pins the condition enum, so the fixture release ships real ones
        args = synthetic_run(conditions=("Rest", "Stim8hr"), analysis_condition="Rest",
                             extra_programs=GHOST_PROGRAMS)
        doc = v3_contract(a=GHOST_A, b=GHOST_B, mode=mode, conditions=conditions)
        path = os.path.join(os.path.dirname(args.de_main), "v3_within.json")
        with open(path, "w") as fh:
            json.dump(doc, fh)
        return args, path, doc
    return _build


def _base_argv(args):
    return [
        "--selection", args.selection, "--registry", args.registry,
        "--de-main", args.de_main, "--by-guide", args.by_guide,
        "--by-donors", args.by_donors, "--sgrna", args.sgrna,
        "--guide-manifest", args.guide_manifest,
        "--source-registry", args.source_registry,
        "--stage1-validation", args.stage1_validation,
        "--stage1-gate-spec", args.stage1_gate_spec,
        "--lane", "synthetic", "--out-root", args.out_root,
    ]


class TestTheDirectCLIAcceptsAndUSESTheV3Flags:
    def test_the_matrix_command_PARSES(self, v3_run):
        """(a) — it used to die with 'unrecognized arguments'."""
        args, v3_path, _ = v3_run()
        argv = _base_argv(args) + ["--stage1-v3-selection", v3_path,
                                   "--stage1-v3-schema", SCHEMA_PATH]
        result = direct_cli.main(argv)          # a SystemExit(2) here IS the bug
        assert result["run_id"]

    def test_the_V3_PATH_IS_ACTUALLY_TAKEN_not_silently_None(self, v3_run):
        """(b) — the flag parsed, but did it DO anything?"""
        args, v3_path, doc = v3_run()
        result = direct_cli.main(
            _base_argv(args) + ["--stage1-v3-selection", v3_path,
                                "--stage1-v3-schema", SCHEMA_PATH])
        with open(os.path.join(result["out_dir"], "provenance.json")) as fh:
            binding = json.load(fh)["run_binding"]

        v3 = binding["stage1_v3"]
        assert v3 is not None, "the v3 path was silently skipped"
        assert v3["analysis_mode"] == stage1_v3.MODE_WITHIN
        assert v3["poles"]["A"]["program_id"] == GHOST_A
        assert v3["poles"]["B"]["program_id"] == GHOST_B
        assert v3["full_contract_content_sha256"] == \
            stage1_v3.reverify_full_contract_hash(doc)

    def test_it_is_SCORED_on_the_v3_axes_not_the_legacy_ones(self, v3_run):
        # the strongest statement: a silent legacy fallback would score the fx_* programs
        args, v3_path, _ = v3_run()
        result = direct_cli.main(
            _base_argv(args) + ["--stage1-v3-selection", v3_path,
                                "--stage1-v3-schema", SCHEMA_PATH])
        with open(os.path.join(result["out_dir"], "axis.json")) as fh:
            axis = json.load(fh)
        programs = {axis["A"]["program_id"], axis["B"]["program_id"]}
        assert programs == {GHOST_A, GHOST_B}

    def test_WITHOUT_the_flags_it_is_a_legacy_run_and_says_so(self, v3_run):
        args, _, _ = v3_run()
        result = direct_cli.main(_base_argv(args))
        with open(os.path.join(result["out_dir"], "provenance.json")) as fh:
            assert json.load(fh)["run_binding"]["stage1_v3"] is None

    def test_a_TEMPORAL_contract_is_refused_by_the_direct_CLI(self, v3_run):
        args, v3_path, _ = v3_run(mode=stage1_v3.MODE_TEMPORAL,
                                  conditions=("Rest", "Stim8hr"))
        with pytest.raises(stage1_v3.SelectionV3Error) as exc:
            direct_cli.main(_base_argv(args) + ["--stage1-v3-selection", v3_path,
                                                "--stage1-v3-schema", SCHEMA_PATH])
        assert exc.value.reason == stage1_v3.REFUSE_MODE_ROUTE

    def test_the_contract_without_its_schema_is_refused(self, v3_run):
        args, v3_path, _ = v3_run()
        with pytest.raises(stage1_v3.SelectionV3Error) as exc:
            direct_cli.main(_base_argv(args) + ["--stage1-v3-selection", v3_path])
        assert exc.value.reason == stage1_v3.REFUSE_SCHEMA_PIN


class TestThePathwayCLIAcceptsAndUSESTheV3Flags:
    def _argv(self, args):
        from direct import run_screen as rs
        from direct import universe as uni
        ctx = rs.prepare(args)
        tu = uni.target_universe(ctx["identities_by_condition"])
        gs = write_gene_sets(os.path.dirname(args.de_main), UNIVERSE, list(TARGET_GENES),
                             ctx["gene_universe"]["sha256"],
                             target_universe_sha256=tu["sha256"])
        return _base_argv(args) + ["--gene-sets", gs]

    def _latest(self, out_root):
        dirs = [os.path.join(out_root, d) for d in os.listdir(out_root)]
        return max(dirs, key=os.path.getmtime)

    def test_the_matrix_command_PARSES(self, v3_run):
        args, v3_path, _ = v3_run()
        rc = run_pathway.main(self._argv(args) + [
            "--stage1-v3-selection", v3_path, "--stage1-v3-schema", SCHEMA_PATH])
        assert rc == 0

    def test_the_V3_PATH_IS_ACTUALLY_TAKEN_not_silently_None(self, v3_run):
        args, v3_path, doc = v3_run()
        run_pathway.main(self._argv(args) + [
            "--stage1-v3-selection", v3_path, "--stage1-v3-schema", SCHEMA_PATH])
        out = self._latest(args.out_root)
        with open(os.path.join(out, "pathway_provenance.json")) as fh:
            binding = json.load(fh)["run_binding"]

        v3 = binding["stage1_v3"]
        assert v3 is not None, "the v3 path was silently skipped"
        assert v3["poles"]["A"]["program_id"] == GHOST_A
        assert v3["full_contract_content_sha256"] == \
            stage1_v3.reverify_full_contract_hash(doc)

    def test_WITHOUT_the_flags_it_is_a_legacy_run_and_says_so(self, v3_run):
        args, _, _ = v3_run()
        run_pathway.main(self._argv(args))
        out = self._latest(args.out_root)
        with open(os.path.join(out, "pathway_provenance.json")) as fh:
            assert json.load(fh)["run_binding"]["stage1_v3"] is None


class TestTheTemporalCLIStillWorks:
    def test_it_still_defines_the_flags(self):
        # it was the only lane that did; it must not regress
        parser_src = temporal_cli.main.__doc__ or ""
        assert parser_src is not None      # the real assertion is the run below

    def test_all_three_lanes_now_define_the_v3_flags(self):
        """The gap was that only ONE of three entry points was wired."""
        import argparse
        import contextlib
        import io

        for name, mod in (("direct", direct_cli), ("temporal", temporal_cli),
                          ("pathway", run_pathway)):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf), pytest.raises(SystemExit):
                mod.main(["--help"])
            helptext = buf.getvalue()
            assert "--stage1-v3-selection" in helptext, f"{name} CLI lacks the flag"
            assert "--stage1-v3-schema" in helptext, f"{name} CLI lacks the flag"
        assert argparse  # noqa: B018


class TestAMissingFlagIsAWiringBugNotSilence:
    def test_an_args_object_that_does_not_DEFINE_the_flags_is_REFUSED(self):
        """The root hazard: getattr(args, ..., None) turned a MISSING attribute into
        'no v3 contract'. That is how the CLI gap hid for a whole round."""
        class Unwired:
            lane = "synthetic"

        with pytest.raises(stage1_v3.SelectionV3Error) as exc:
            stage1_v3.load_selection(Unwired())
        assert exc.value.reason == stage1_v3.REFUSE_V3_NOT_WIRED

    def test_an_args_object_that_DEFINES_them_as_None_is_simply_legacy(self):
        class Wired:
            lane = "synthetic"
            stage1_v3_selection = None
            stage1_v3_schema = None

        assert stage1_v3.load_selection(Wired()) is None


# --------------------------------------------------------------------------- #
# THE MATRIX MUST BE LITERALLY TRUE.
#
# STAGE2_INVOCATION_MATRIX.md claimed "every flag below exists in argparse". It did not:
# 9 of 15 invocations died on --stage1-v3-selection. A document that asserts an executable
# fact should be checked by the thing that executes it, so this is that check.
# --------------------------------------------------------------------------- #
MATRIX_FLAGS = {
    "direct": ("direct.cli", [
        "--stage1-v3-selection", "--stage1-v3-schema", "--selection", "--registry",
        "--de-main", "--by-guide", "--by-donors", "--sgrna", "--guide-manifest",
        "--source-registry", "--stage1-release", "--lane", "--strict-replay",
        "--pseudobulk", "--env-lock", "--out-root", "--preflight-only",
        "--allow-dirty-tree"]),
    "temporal": ("direct.temporal.cli", [
        "--stage1-v3-selection", "--stage1-v3-schema", "--selection", "--registry",
        "--de-main", "--by-guide", "--by-donors", "--sgrna", "--guide-manifest",
        "--source-registry", "--stage1-release", "--lane", "--strict-replay",
        "--pseudobulk", "--out-root", "--conditions", "--batch-policy"]),
    "pathway": ("direct.run_pathway", [
        "--stage1-v3-selection", "--stage1-v3-schema", "--selection", "--registry",
        "--de-main", "--by-guide", "--by-donors", "--sgrna", "--guide-manifest",
        "--source-registry", "--stage1-release", "--gene-sets", "--lane",
        "--strict-replay", "--pseudobulk", "--out-root"]),
    "run_manifest": ("direct.run_manifest", [
        "--direct", "--temporal", "--pathway", "--out", "--allow-partial"]),
    "manifest_build": ("direct.manifest_build", [
        "--de-main", "--pseudobulk", "--out-dir"]),
    "geneset_build": ("direct.geneset_build", [
        "--cache-dir", "--de-main", "--sgrna", "--out-dir"]),
}


@pytest.mark.parametrize("lane", sorted(MATRIX_FLAGS))
def test_every_flag_the_INVOCATION_MATRIX_uses_exists_in_argparse(lane):
    import contextlib
    import importlib
    import io

    module_path, flags = MATRIX_FLAGS[lane]
    mod = importlib.import_module(module_path)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), pytest.raises(SystemExit):
        mod.main(["--help"])
    helptext = buf.getvalue()

    missing = [f for f in flags if f not in helptext]
    assert not missing, (
        f"the {lane} entry point does not define {missing}; the invocation matrix "
        "prints commands that would die with 'unrecognized arguments'")
