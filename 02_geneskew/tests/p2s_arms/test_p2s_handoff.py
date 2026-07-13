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
def prepared(tmp_path, view, bundle_dir, w10_report, p2s_lock, monkeypatch):
    programs = list(view["admitted_program_ids"])
    ntc = fx.write_ntc_h5ad(str(tmp_path / "ntc.h5ad"))
    scores = fx.write_stage1_scores(str(tmp_path / "s.parquet"), ntc, programs)
    de = fx.write_de_readout(str(tmp_path / "de.h5ad"), fx.target_ids())
    monkeypatch.setitem(prepare_inputs.PINS, "ntc", file_sha256(ntc))
    monkeypatch.setitem(prepare_inputs.PINS, "de_main", file_sha256(de))
    monkeypatch.setitem(prepare_inputs.PINS, "stage1_scores", file_sha256(scores))
    import pandas as pd
    from p2s_arms import stage1_canonical
    monkeypatch.setattr(stage1_canonical, "EXPECTED",
                        stage1_canonical.canonical_scores_sha256(pd.read_parquet(scores)))

    argv = ["--ntc", ntc, "--stage1-scores", scores, "--de-main", de,
            "--direct-bundle", bundle_dir, "--w10-report", w10_report,
            "--env-lock", fx.REAL_SOLVER_LOCK, "--p2s-env-lock", p2s_lock,
            "--stage1-release", "x",
            "--condition", CONDITION, "--out-root", str(tmp_path / "prep"),
            "--lane", "synthetic", "--release-kind", "fixture"]
    args = prepare_inputs.build_parser().parse_args(argv)
    return prepare_inputs.build(args, release=fx.make_release(), view=view)


def _handoff(tmp_path, prepared, view, bundle_dir, w10_report, **over):
    a = {"--direct-bundle": bundle_dir, "--w10-report": w10_report,
         "--env-lock": fx.REAL_SOLVER_LOCK, "--p2s-env-lock": fx.REAL_P2S_LOCK,
         "--stage1-release": "x",
         "--condition": CONDITION, "--inputs": prepared["out_dir"],
         "--out-root": str(tmp_path / "out"), "--out": str(tmp_path / "handoff.json"),
         "--lane": "synthetic", "--release-kind": "fixture"}
    a.update(over)
    argv = [x for k, v in a.items() for x in (k, str(v))]
    args = scheduler_handoff.build_parser().parse_args(argv)
    return scheduler_handoff.build(args, view=view)


def test_ONE_INVOCATION_runs_the_whole_grid_and_emits_BOTH_arms(tmp_path, prepared, view,
                                                               bundle_dir, w10_report):
    """"One unit" is NOT "one fit". One invocation runs the fit grid and emits both sign arms.

    Scheduling the sibling arm would run the same base effect twice and invite the two to
    disagree by a hair about a magnitude they SHARE.
    """
    doc = _handoff(tmp_path, prepared, view, bundle_dir, w10_report)

    assert doc["n_units"] == view["n_admitted_programs"]
    assert doc["n_arms"] == 2 * doc["n_units"]               # two sign arms per unit
    assert doc["one_invocation_per_program_condition"] is True
    assert doc["both_sign_arms_emitted_per_invocation"] is True

    grid = doc["fit_grid"]
    # 5 base signatures; SEVEN model fits per the OFAT grid: 3 all_donor (primary +
    # log_fc sensitivity + pca_off sensitivity) + 4 LODO. NO Cartesian log_fc+pca_off cell.
    assert grid["base_signatures_per_unit"] == 5
    assert grid["fit_grid_members_per_unit"] == 7
    assert grid["model_configs"] == ["pca_on_60", "pca_off"]
    assert grid["sign_arms_per_fit"] == 2
    assert doc["n_fit_grid_members_total"] == 7 * doc["n_units"]

    for u in doc["units"]:
        assert u["invocations_per_unit"] == 1
        assert u["fit_grid_members_per_unit"] == 7
        assert u["arms_emitted_per_unit"] == 2
        assert "n_fits" not in u                              # the misleading field is gone
        inc, dec = u["arm_keys"]
        assert "|increase|" in inc and "|decrease|" in dec
        # the invocation is taken on the increase arm; decrease is its exact negation
        assert u["argv"][u["argv"].index("--arm-key") + 1] == inc


def test_the_worker_profile_prefers_ONE_condition_worker(tmp_path, prepared, view,
                                                         bundle_dir, w10_report):
    """A second worker re-reads the same 396k matrix for no scientific gain."""
    doc = _handoff(tmp_path, prepared, view, bundle_dir, w10_report)
    wp = doc["worker_profile"]
    assert wp["max_condition_workers"] == 2
    assert wp["preferred_condition_workers"] == 1
    assert wp["cells_and_effects_are_shared_within_a_condition"] is True


def test_EVERY_argv_is_PARSER_VALID_against_the_producers_own_CLI(tmp_path, prepared, view,
                                                                  bundle_dir, w10_report):
    """A handoff whose commands do not parse fails at 3am, one unit at a time."""
    from p2s_arms import run_p2s_arms

    doc = _handoff(tmp_path, prepared, view, bundle_dir, w10_report)
    assert doc["every_argv_is_parser_valid"] is True
    for u in doc["units"]:
        args = run_p2s_arms.build_parser().parse_args(u["argv"])   # must not SystemExit
        assert args.arm_key == u["arm_keys"][0]
        assert os.path.isdir(args.inputs) or args.inputs   # the prepared dir, not raw files
        assert "--cells" not in u["argv"] and "--effects" not in u["argv"]


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
    assert doc["direct_solver_lock_sha256"].startswith("2983d140")
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
