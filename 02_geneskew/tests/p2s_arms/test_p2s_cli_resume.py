"""THE CLI CONTRACT, and RESUME.

THE GAP THIS CLOSES
-------------------
The W7 wrapper's preflight raises ``SECONDARY_LANE_BINDING_GAP`` against any secondary
producer that does not expose ``--env-lock``, ``--direct-bundle``, ``--w10-report`` and
``--stage1-release``, with the note:

    "Sequencing alone is not a binding."

A wrapper can run P2S *after* Direct and W10 and still have bound nothing: a producer that
does not ACCEPT the bundle and the report cannot be said to have run from them. So the flags
are REQUIRED, and their absence is a parser error rather than a default.

RESUME
------
The run id is CONTENT-ADDRESSED over the binding. That gives resume for free, and it gives
binding-drift detection for free too:

  * same bindings  -> same run id -> the same directory, byte-identical. Idempotent.
  * ANY binding changed -> a DIFFERENT run id -> a NEW directory.

A result is never silently overwritten by a run that bound something else, because a run that
bound something else is not the same run.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib

import fixtures_p2s as fx
import pytest
from p2s_arms import disposition as D
from p2s_arms import run_p2s_arms

REQUIRED_FLAGS = ("--direct-bundle", "--w10-report", "--env-lock",
                  "--p2s-env-lock", "--inputs", "--stage1-release")


def _flag_names(parser) -> set[str]:
    out: set[str] = set()
    for a in parser._actions:
        out.update(a.option_strings)
    return out


# --------------------------------------------------------------------------- #
# THE FOUR FLAGS.
# --------------------------------------------------------------------------- #
def test_the_producer_EXPOSES_the_four_bindings_the_wrapper_checks_for():
    """This is the literal SECONDARY_LANE_BINDING_GAP list."""
    names = _flag_names(run_p2s_arms.build_parser())
    missing = [f for f in REQUIRED_FLAGS if f not in names]
    assert not missing, f"SECONDARY_LANE_BINDING_GAP: {missing}"


@pytest.mark.parametrize("flag", REQUIRED_FLAGS)
def test_each_binding_is_REQUIRED_not_defaulted(flag):
    """A default here would be a binding nobody supplied — the gap wearing a value."""
    action = next(a for a in run_p2s_arms.build_parser()._actions
                  if flag in a.option_strings)
    assert action.required is True, f"{flag} is optional; a missing binding must REFUSE"


def test_omitting_a_binding_is_a_PARSER_ERROR_not_a_silent_default():
    with pytest.raises(SystemExit):
        run_p2s_arms.build_parser().parse_args(["--arm-key", "x"])


def test_there_is_no_selection_flag():
    """P2S is SELECTION-INDEPENDENT. An arm is not a pair, and a pair is a join."""
    names = _flag_names(run_p2s_arms.build_parser())
    for banned in ("--selection", "--pair", "--contrast", "--away-from-a", "--toward-b"):
        assert banned not in names


# --------------------------------------------------------------------------- #
# THE TYPED DEFERRED DISPOSITION — a refusal RECORDED, never a silence.
# --------------------------------------------------------------------------- #
def test_a_refusal_emits_a_TYPED_DEFERRED_DISPOSITION_and_exits_2(tmp_path, bundle_dir,
                                                                  view, inputs):
    """Exit 2, not 1: a scheduler must tell "declined" from "crashed"."""
    out_root = str(tmp_path / "out")
    argv = [
        "--direct-bundle", bundle_dir,
        # the bundle's OWN placeholder, not W10's report -> self-admission refusal
        "--w10-report", os.path.join(bundle_dir, "verification.json"),
        "--env-lock", fx.REAL_SOLVER_LOCK,
        "--stage1-release", "unused-because-we-refuse-first",
        "--arm-key", f"direct|{fx.PROGRAM}|increase|{fx.CONDITION}",
        "--inputs", str(tmp_path), "--p2s-env-lock", fx.REAL_P2S_LOCK,
        "--out-root", out_root, "--lane", "synthetic",
    ]
    code = run_p2s_arms.main(argv)
    assert code == run_p2s_arms.EXIT_REFUSED == 2

    path = os.path.join(out_root, run_p2s_arms.DEFERRED_FILE)
    rec = json.load(open(path))
    assert rec["state"] == D.REFUSED
    assert rec["reason"] == D.REFUSE_W10_SELF_ADMITTED
    assert rec["support_emitted"] is False
    assert rec["filled_a_primary_slot"] is False
    assert rec["counts_toward_completeness"] is False
    assert rec["lane_role"] == "secondary_non_gating"

    # a refusal emits NO support artifact. Ever.
    assert not any(n.startswith("p2s_arm_support") for n in os.listdir(out_root))


def test_a_refused_arm_is_a_RESULT_not_a_silence(tmp_path, bundle_dir, view, inputs):
    """A refused arm is not one P2S has no opinion about — it is one P2S refused to speak for."""
    out_root = str(tmp_path / "out")
    run_p2s_arms.main([
        "--direct-bundle", bundle_dir,
        "--w10-report", os.path.join(bundle_dir, "verification.json"),
        "--env-lock", fx.REAL_SOLVER_LOCK, "--stage1-release", "x",
        "--arm-key", f"direct|{fx.PROGRAM}|increase|{fx.CONDITION}",
        "--inputs", str(tmp_path), "--p2s-env-lock", fx.REAL_P2S_LOCK,
        "--out-root", out_root, "--lane", "synthetic",
    ])
    assert os.path.exists(os.path.join(out_root, run_p2s_arms.DEFERRED_FILE))


# --------------------------------------------------------------------------- #
# RESUME — the run id is content-addressed, so this is a property, not a feature.
# --------------------------------------------------------------------------- #
def _sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def _artifacts(d):
    return {n: _sha(os.path.join(d, n)) for n in sorted(os.listdir(d))
            if n != "p2s_provenance.json"}      # provenance carries created_at


def test_RESUME_the_same_bindings_give_the_same_run_id_and_identical_bytes(
        tmp_path, view, bundle_dir, w10_report, inputs):
    """Idempotent. Re-running a completed unit does not fork a second answer."""
    a = fx.run_producer(tmp_path, view=view, bundle_dir=bundle_dir,
                        w10_report=w10_report, inputs=inputs)
    b = fx.run_producer(tmp_path, view=view, bundle_dir=bundle_dir,
                        w10_report=w10_report, inputs=inputs)

    assert a["p2s_run_id"] == b["p2s_run_id"]
    assert a["out_dir"] == b["out_dir"]
    assert _artifacts(a["out_dir"]) == _artifacts(b["out_dir"])


def test_RESUME_a_DRIFTED_BINDING_gets_a_NEW_run_id_and_never_overwrites(
        tmp_path, view, bundle_dir, w10_report, inputs):
    """A run that bound something else is not the same run, so it cannot silently replace it.

    Here the SEED drifts. The old directory survives untouched beside the new one — nothing
    is overwritten by a run that was not the same run.
    """
    a = fx.run_producer(tmp_path, view=view, bundle_dir=bundle_dir,
                        w10_report=w10_report, inputs=inputs, seed=42)
    before = _artifacts(a["out_dir"])

    b = fx.run_producer(tmp_path, view=view, bundle_dir=bundle_dir,
                        w10_report=w10_report, inputs=inputs, seed=7)

    assert b["p2s_run_id"] != a["p2s_run_id"]
    assert b["out_dir"] != a["out_dir"]
    assert _artifacts(a["out_dir"]) == before, "the earlier run was overwritten"


def test_RESUME_a_DIFFERENT_DIRECT_BUNDLE_gets_a_different_run_id(tmp_path, view, inputs):
    """The bundle it supports is IN the identity — support is not portable between bundles."""
    d1 = fx.write_full_bundle(str(tmp_path / "d1"), view)
    r1 = fx.write_w10_report(str(tmp_path / "r1.json"), d1, view)
    a = fx.run_producer(tmp_path, view=view, bundle_dir=d1, w10_report=r1, inputs=inputs)

    d2 = fx.write_full_bundle(str(tmp_path / "d2"), view, condition="Rest")
    r2 = fx.write_w10_report(str(tmp_path / "r2.json"), d2, view, condition="Rest")
    # eligibility is arm-specific (no global fallback), so a Rest arm needs Rest-keyed rows.
    rest_inputs = dict(inputs, eligible=fx.make_eligible(
        str(tmp_path / "elig_rest.parquet"), condition="Rest"))
    b = fx.run_producer(tmp_path, view=view, bundle_dir=d2, w10_report=r2, inputs=rest_inputs,
                        arm_key=f"direct|{fx.PROGRAM}|increase|Rest")

    assert a["p2s_run_id"] != b["p2s_run_id"]


def test_the_run_id_binds_the_SOLVER_LOCK_and_the_W10_REPORT(tmp_path, view, bundle_dir,
                                                             w10_report, inputs):
    """Both are in the identity, so a result cannot be re-attributed to another environment
    or to an admission it never had."""
    out = fx.run_producer(tmp_path, view=view, bundle_dir=bundle_dir,
                          w10_report=w10_report, inputs=inputs)
    prov = json.load(open(os.path.join(out["out_dir"], "p2s_provenance.json")))
    method = prov["run_binding"]["method"]

    assert method["solver_lock_sha256"].startswith("2983d140")
    assert method["w10_verdict"] == "ADMIT"
    assert method["w10_report_sha256_rederived"] is True
    assert method["bundle_is_real_and_admitted"] is True
