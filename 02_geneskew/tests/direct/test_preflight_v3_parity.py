"""B2 — the preflight must check the EXACT contract production executes.

THE DEFECT: ``preflight.run`` called ``run_screen.prepare(args)`` with no v3 argument at
all. Production called ``stage1_v3.load_selection(...)`` first and then
``prepare(args, v3=...)``. So ``--preflight-only`` with a v3 contract bound the LEGACY
selection, certified THAT, and returned GO — for a run that production would then execute
against entirely different programs. A preflight of a different program certifies nothing
about this one, and it is worse than no preflight because it produces a GO.

There is now ONE function — ``run_screen.load_and_prepare`` — and preflight, Direct and
Pathway all call it. The preflight cannot check a weaker or different contract than the
build, because it is not able to: there is no second loader to drift from.

The LEGACY contract is not a hidden source. When both are supplied the v3 contract wins
(that is the point), but the legacy one is HASHED and DECLARED UNCONSUMED in the run
binding — so a reader can see it was present and ignored, rather than having to infer from
the absence of evidence that it did nothing.
"""
from __future__ import annotations

# F811: importing a pytest fixture and then naming it as a test parameter is the fixture
# -reuse idiom, not a redefinition. Sharing the GHOST fixture beats a second copy that has
# to be kept in step with it.
# ruff: noqa: F811
import copy
import inspect
import json
import os

import pytest
from direct import cli as direct_cli
from direct import preflight, run_screen, stage1_v3
from test_cli_v3 import GHOST_A, GHOST_B, _base_argv, v3_run  # noqa: F401  (fixture)
from test_temporal_v3 import SCHEMA_PATH, v3_contract

pytestmark = pytest.mark.skipif(
    not os.path.exists(SCHEMA_PATH), reason="the pinned v3 schema is not present")


def _preflight(args, v3_path=None, extra=()):
    argv = _base_argv(args) + ["--preflight-only"] + list(extra)
    if v3_path:
        argv += ["--stage1-v3-selection", v3_path, "--stage1-v3-schema", SCHEMA_PATH]
    return direct_cli.main(argv)


def _production(args, v3_path):
    return direct_cli.main(
        _base_argv(args) + ["--stage1-v3-selection", v3_path,
                            "--stage1-v3-schema", SCHEMA_PATH])


def _rewrite(path, doc):
    with open(path, "w") as fh:
        json.dump(doc, fh)


class TestThePreflightChecksTheV3ContractAtAll:
    def test_it_BINDS_the_v3_contract_instead_of_silently_certifying_the_legacy_one(
            self, v3_run):
        args, v3_path, doc = v3_run()
        report = _preflight(args, v3_path)

        assert report["verdict"] == preflight.GO
        v3 = report["stage1_v3"]
        assert v3 is not None, "the preflight certified a run it never looked at"
        assert v3["poles"]["A"]["program_id"] == GHOST_A
        assert v3["poles"]["B"]["program_id"] == GHOST_B
        assert v3["analysis_mode"] == stage1_v3.MODE_WITHIN

    def test_WITHOUT_a_v3_contract_it_says_so_rather_than_implying_one(self, v3_run):
        args, _, _ = v3_run()
        assert _preflight(args)["stage1_v3"] is None

    def test_it_still_writes_NO_result_artifact_and_reads_NO_dense_layer(self, v3_run):
        args, v3_path, _ = v3_run()
        report = _preflight(args, v3_path)
        assert report["dense_layer_reads"] == 0
        assert report["result_artifacts_written"] == 0


class TestPreflightAndProductionDeriveTheSAMEHashes:
    """The whole point: the preflight certified THIS run, not a different one."""

    def test_the_full_contract_hash_is_IDENTICAL(self, v3_run):
        args, v3_path, doc = v3_run()
        pre = _preflight(args, v3_path)["stage1_v3"]
        prod = _production(args, v3_path)
        with open(os.path.join(prod["out_dir"], "provenance.json")) as fh:
            run = json.load(fh)["run_binding"]["stage1_v3"]

        assert pre["full_contract_content_sha256"] == \
            prod_hash(run) == stage1_v3.reverify_full_contract_hash(doc)

    def test_the_selection_BIOLOGY_hash_is_IDENTICAL(self, v3_run):
        args, v3_path, _ = v3_run()
        pre = _preflight(args, v3_path)["stage1_v3"]
        prod = _production(args, v3_path)
        with open(os.path.join(prod["out_dir"], "provenance.json")) as fh:
            run = json.load(fh)["run_binding"]["stage1_v3"]
        assert pre["selection_biology_sha256"] == run["selection_biology_sha256"]

    def test_they_agree_on_the_POLES_and_the_CONDITIONS(self, v3_run):
        args, v3_path, _ = v3_run()
        pre = _preflight(args, v3_path)["stage1_v3"]
        prod = _production(args, v3_path)
        with open(os.path.join(prod["out_dir"], "provenance.json")) as fh:
            run = json.load(fh)["run_binding"]["stage1_v3"]
        assert pre["poles"] == run["poles"]
        assert pre["conditions"] == run["conditions"]


def prod_hash(run):
    return run["full_contract_content_sha256"]


class TestThePreflightREFUSESWhatProductionWouldRefuse:
    """A refusal is the ANSWER — a machine-readable NO_GO, not a traceback."""

    def test_a_TEMPORAL_contract_is_NO_GO_in_the_within_condition_lane(self, v3_run):
        args, v3_path, _ = v3_run()
        _rewrite(v3_path, v3_contract(a=GHOST_A, b=GHOST_B,
                                      mode=stage1_v3.MODE_TEMPORAL,
                                      conditions=("Rest", "Stim8hr")))
        report = _preflight(args, v3_path)
        assert report["verdict"] == preflight.NO_GO
        assert stage1_v3.REFUSE_MODE_ROUTE in str(report["failures"])

    def test_a_FORGED_full_contract_hash_is_NO_GO(self, v3_run):
        args, v3_path, doc = v3_run()
        forged = copy.deepcopy(doc)
        forged["full_contract_content_sha256"] = "0" * 64
        _rewrite(v3_path, forged)
        report = _preflight(args, v3_path)
        assert report["verdict"] == preflight.NO_GO
        assert stage1_v3.REFUSE_CONTENT_HASH in str(report["failures"])

    def test_a_v3_PROGRAM_ABSENT_from_the_registry_is_NO_GO(self, v3_run):
        args, v3_path, _ = v3_run()
        _rewrite(v3_path, v3_contract(a="NOT_IN_THE_REGISTRY", b=GHOST_B,
                                      mode=stage1_v3.MODE_WITHIN, conditions=("Rest",)))
        report = _preflight(args, v3_path)
        assert report["verdict"] == preflight.NO_GO
        assert "NOT_IN_THE_REGISTRY" in str(report["failures"])

    def test_a_DEGENERATE_axis_is_NO_GO(self, v3_run):
        args, v3_path, _ = v3_run()
        _rewrite(v3_path, v3_contract(a=GHOST_A, b=GHOST_A,
                                      mode=stage1_v3.MODE_WITHIN, conditions=("Rest",)))
        report = _preflight(args, v3_path)
        assert report["verdict"] == preflight.NO_GO
        assert stage1_v3.REFUSE_DEGENERATE_AXIS in str(report["failures"])

    def test_the_contract_without_its_PINNED_SCHEMA_is_NO_GO(self, v3_run):
        args, v3_path, _ = v3_run()
        report = direct_cli.main(
            _base_argv(args) + ["--preflight-only",
                                "--stage1-v3-selection", v3_path])
        assert report["verdict"] == preflight.NO_GO
        assert stage1_v3.REFUSE_SCHEMA_PIN in str(report["failures"])


class TestTheLegacyContractIsBoundNotHidden:
    """It is ignored — and the run SAYS it was ignored, with its hash."""

    def test_the_legacy_contract_is_declared_SUPPLIED_and_UNCONSUMED(self, v3_run):
        args, v3_path, _ = v3_run()
        prod = _production(args, v3_path)
        with open(os.path.join(prod["out_dir"], "provenance.json")) as fh:
            legacy = json.load(fh)["run_binding"]["legacy_selection"]
        assert legacy["supplied"] is True
        assert legacy["consumed"] is False
        assert len(legacy["sha256"]) == 64

    def test_the_preflight_declares_it_the_same_way(self, v3_run):
        args, v3_path, _ = v3_run()
        legacy = _preflight(args, v3_path)["legacy_selection"]
        assert legacy["supplied"] is True and legacy["consumed"] is False

    def test_a_LEGACY_ONLY_run_declares_it_CONSUMED(self, v3_run):
        args, _, _ = v3_run()
        prod = direct_cli.main(_base_argv(args))
        with open(os.path.join(prod["out_dir"], "provenance.json")) as fh:
            legacy = json.load(fh)["run_binding"]["legacy_selection"]
        assert legacy["supplied"] is True and legacy["consumed"] is True

    def test_the_legacy_contract_NEVER_supplies_an_axis_when_v3_is_present(self, v3_run):
        # the GHOST proof, restated at the preflight: the legacy file names fx_* programs
        args, v3_path, _ = v3_run()
        report = _preflight(args, v3_path)
        assert report["stage1_v3"]["poles"]["A"]["program_id"] == GHOST_A
        assert "fx_" not in json.dumps(report["stage1_v3"])


class TestThereIsExactlyONELoader:
    def test_preflight_and_the_build_call_the_SAME_function(self):
        import inspect
        src = inspect.getsource(preflight.run)
        assert "load_and_prepare" in src, \
            "preflight has its own loader again — it will drift from the build"
        assert "run_screen.prepare(args)" not in src

    def test_the_shared_loader_exists_and_takes_the_expected_mode(self):
        sig = inspect.signature(run_screen.load_and_prepare)
        assert "expect_mode" in sig.parameters


