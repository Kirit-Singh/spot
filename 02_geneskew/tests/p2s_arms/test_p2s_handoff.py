"""THE SCHEDULER HANDOFF — one fit per (program, condition); both sign arms come free."""
from __future__ import annotations

import os

import fixtures_p2s as fx
import pytest
from p2s_arms import disposition as D
from p2s_arms import prepare_inputs, scheduler_handoff
from p2s_arms.w10 import file_sha256

CONDITION = "Stim48hr"


@pytest.fixture
def prepared(tmp_path, view, bundle_dir, w10_report, monkeypatch):
    programs = list(view["admitted_program_ids"])
    ntc = fx.write_ntc_h5ad(str(tmp_path / "ntc.h5ad"))
    scores = fx.write_stage1_scores(str(tmp_path / "s.parquet"), ntc, programs)
    de = fx.write_de_readout(str(tmp_path / "de.h5ad"), fx.target_ids())
    monkeypatch.setitem(prepare_inputs.PINS, "ntc", file_sha256(ntc))
    monkeypatch.setitem(prepare_inputs.PINS, "de_main", file_sha256(de))

    argv = ["--ntc", ntc, "--stage1-scores", scores, "--de-main", de,
            "--direct-bundle", bundle_dir, "--w10-report", w10_report,
            "--env-lock", fx.REAL_SOLVER_LOCK, "--stage1-release", "x",
            "--condition", CONDITION, "--out-root", str(tmp_path / "prep"),
            "--lane", "synthetic", "--release-kind", "fixture"]
    args = prepare_inputs.build_parser().parse_args(argv)
    return prepare_inputs.build(args, release=fx.make_release(), view=view)


def _handoff(tmp_path, prepared, view, bundle_dir, w10_report, **over):
    a = {"--direct-bundle": bundle_dir, "--w10-report": w10_report,
         "--env-lock": fx.REAL_SOLVER_LOCK, "--stage1-release": "x",
         "--condition": CONDITION, "--inputs": prepared["out_dir"],
         "--out-root": str(tmp_path / "out"), "--out": str(tmp_path / "handoff.json"),
         "--lane": "synthetic", "--release-kind": "fixture"}
    a.update(over)
    argv = [x for k, v in a.items() for x in (k, str(v))]
    args = scheduler_handoff.build_parser().parse_args(argv)
    return scheduler_handoff.build(args, view=view)


def test_ONE_fit_per_program_condition_and_BOTH_arms_per_fit(tmp_path, prepared, view,
                                                             bundle_dir, w10_report):
    """Scheduling both arms would run the same fit twice, and invite them to disagree."""
    doc = _handoff(tmp_path, prepared, view, bundle_dir, w10_report)

    assert doc["n_units"] == view["n_admitted_programs"]
    assert doc["n_fits"] == doc["n_units"]                   # ONE fit per unit
    assert doc["n_arms"] == 2 * doc["n_units"]               # ...and TWO arms out of it
    assert doc["one_fit_per_program_condition"] is True
    assert doc["both_sign_arms_emitted_per_fit"] is True

    for u in doc["units"]:
        assert u["n_fits"] == 1 and u["arms_emitted_per_unit"] == 2
        inc, dec = u["arm_keys"]
        assert "|increase|" in inc and "|decrease|" in dec
        assert "--arm-key" in u["argv"]
        # the FIT is taken on the increase arm; decrease is its exact negation
        assert u["argv"][u["argv"].index("--arm-key") + 1] == inc


def test_EVERY_argv_is_PARSER_VALID_against_the_producers_own_CLI(tmp_path, prepared, view,
                                                                  bundle_dir, w10_report):
    """A handoff whose commands do not parse fails at 3am, one unit at a time."""
    from p2s_arms import run_p2s_arms

    doc = _handoff(tmp_path, prepared, view, bundle_dir, w10_report)
    assert doc["every_argv_is_parser_valid"] is True
    for u in doc["units"]:
        args = run_p2s_arms.build_parser().parse_args(u["argv"])   # must not SystemExit
        assert args.arm_key == u["arm_keys"][0]
        assert os.path.basename(args.cells) == "cells.npz"


def test_a_unit_whose_argv_does_not_parse_is_REFUSED():
    bad = {"unit_id": "u", "program_id": "p", "condition": CONDITION,
           "arm_keys": ["direct|p|increase|" + CONDITION], "argv": ["--nonsense"]}
    with pytest.raises(D.RefusalError):
        scheduler_handoff.validate(bad)


def test_Th9_is_ABSENT_because_the_release_says_so(tmp_path, prepared, view, bundle_dir,
                                                   w10_report):
    doc = _handoff(tmp_path, prepared, view, bundle_dir, w10_report)
    assert all(u["program_id"] != "th9_like" for u in doc["units"])
    assert doc["n_admitted_programs"] == len(doc["units"])


def test_the_handoff_is_NON_GATING_and_content_addressed(tmp_path, prepared, view,
                                                         bundle_dir, w10_report):
    doc = _handoff(tmp_path, prepared, view, bundle_dir, w10_report)
    assert doc["lane_role"] == "secondary_non_gating"
    assert doc["counts_toward_completeness"] is False
    assert all(u["may_gate_or_alter_direct_ranks"] is False for u in doc["units"])
    assert len(doc["handoff_sha256"]) == 64
    assert doc["solver_lock_sha256"].startswith("2983d140")
    assert doc["p2s_inputs_run_id"] == prepared["p2s_inputs_run_id"]


def test_a_refusal_exit_is_2_with_a_named_reason(tmp_path, prepared, view, bundle_dir,
                                                 w10_report):
    with pytest.raises(D.RefusalError) as e:
        _handoff(tmp_path, prepared, view, bundle_dir, w10_report,
                 **{"--condition": "Rest"})
    assert e.value.reason == D.REFUSE_CONDITION_MISMATCH


def test_inputs_that_preparation_did_not_produce_are_refused(tmp_path, prepared, view,
                                                             bundle_dir, w10_report):
    empty = tmp_path / "notprepared"
    empty.mkdir()
    with pytest.raises(D.RefusalError) as e:
        _handoff(tmp_path, prepared, view, bundle_dir, w10_report,
                 **{"--inputs": str(empty)})
    assert e.value.reason == D.REFUSE_BUNDLE_INCOMPLETE
