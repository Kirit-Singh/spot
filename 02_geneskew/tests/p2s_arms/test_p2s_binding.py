"""THE ADMISSION CHAIN — every link, and what happens when each one is broken.

P2S may run ONLY from a real Direct arm bundle that W10 — the INDEPENDENT verifier, which is
not the producer — has ADMITTED, under the pinned Stage-2 solver lock.

Every test here builds a REAL ten-file Direct bundle through ``direct.arm_bundle`` and a REAL
W10 report (content-addressed over its own body, exactly as W10 writes one), then breaks
exactly one link. A secondary lane that survived any of these would be lending its credit to
an artifact nobody stands behind.
"""
from __future__ import annotations

import json
import os

import fixtures_p2s as fx
import pandas as pd
import pytest
from direct import envlock, scorer_view
from fixtures_p2s import CONDITION, PROGRAM, make_release
from p2s_arms import binding, config
from p2s_arms import disposition as D

KEY = f"direct|{PROGRAM}|increase|{CONDITION}"


def _bind(bundle_dir, w10_report, view, **kw):
    kw.setdefault("env_lock", fx.REAL_SOLVER_LOCK)
    kw.setdefault("lane", "synthetic")
    return binding.bind(arm_key=kw.pop("arm_key", KEY), bundle_dir=bundle_dir,
                        w10_report=w10_report, view=view, **kw)


def test_a_clean_admission_binds(bundle_dir, w10_report, view):
    bound = _bind(bundle_dir, w10_report, view)
    assert bound["arm"].arm_key == KEY
    assert bound["base_portable"] is True
    a = bound["admission"]
    assert a["w10_verdict"] == "ADMIT"                      # uppercase, as W10 writes it
    assert a["w10_verifier_id"] == config.W10_VERIFIER_ID
    assert a["w10_report_sha256_rederived"] is True
    assert a["bundle_is_real_and_admitted"] is True
    assert bound["solver_lock"]["sha256"] == config.PINNED_SOLVER_LOCK_SHA256
    # every one of the ten shipped files was re-hashed
    assert len(a["direct_bundle_artifact_sha256"]) == len(config.DIRECT_BUNDLE_FILES)


# --------------------------------------------------------------------------- #
# THE SOLVER LOCK.
# --------------------------------------------------------------------------- #
def test_MUTATION_a_MISSING_env_lock_is_refused(bundle_dir, w10_report, view):
    with pytest.raises(D.RefusalError) as e:
        _bind(bundle_dir, w10_report, view, env_lock=None)
    assert e.value.reason == D.REFUSE_LOCK_ABSENT


def test_MUTATION_a_SWAPPED_env_lock_is_refused(tmp_path, bundle_dir, w10_report, view):
    other = fx.write_solver_lock(str(tmp_path / "other.txt"), pinned=False)
    with pytest.raises(D.RefusalError) as e:
        _bind(bundle_dir, w10_report, view, env_lock=other)
    assert e.value.reason == D.REFUSE_LOCK_MISMATCH


def test_MUTATION_the_STAGE1_lock_is_refused_BY_NAME(tmp_path, bundle_dir, w10_report, view):
    """It is a valid, honest lock — for a DIFFERENT environment. Not a bare hash mismatch."""
    stage1 = fx.write_solver_lock(str(tmp_path / "x.txt"), pinned=False, stage1=True)
    with pytest.raises(D.RefusalError) as e:
        _bind(bundle_dir, w10_report, view, env_lock=stage1)
    assert e.value.reason == D.REFUSE_LOCK_MISMATCH
    assert "STAGE-1 lock" in str(e.value)
    assert "scvi_gpu" in str(e.value)


def test_the_P2S_pin_is_its_OWN_literal_and_must_AGREE_with_Directs():
    """A pin the checker borrowed from the thing it checks is a pin nobody checked."""
    from p2s_arms.w10 import file_sha256

    assert config.PINNED_SOLVER_LOCK_SHA256 == envlock.EXPECTED_SHA256
    assert config.PINNED_SOLVER_LOCK_SHA256.startswith("2983d140")
    # ...and the real committed lock actually hashes to it
    assert file_sha256(fx.REAL_SOLVER_LOCK) == config.PINNED_SOLVER_LOCK_SHA256


def test_MUTATION_arms_computed_under_a_DIFFERENT_lock_are_refused(
        tmp_path, bundle_dir, view):
    """Support computed in one environment, attached to arms computed in another."""
    bad = fx.write_w10_report(str(tmp_path / "w10.json"), bundle_dir, view,
                              solver_lock_sha256="e" * 64)
    with pytest.raises(D.RefusalError) as e:
        _bind(bundle_dir, bad, view)
    assert e.value.reason == D.REFUSE_LOCK_DISAGREES_WITH_BUNDLE


# --------------------------------------------------------------------------- #
# THE W10 REPORT.
# --------------------------------------------------------------------------- #
def test_MUTATION_a_MISSING_w10_report_is_refused(bundle_dir, view):
    with pytest.raises(D.RefusalError) as e:
        _bind(bundle_dir, None, view)
    assert e.value.reason == D.REFUSE_W10_REPORT_MISSING


def test_MUTATION_the_BUNDLES_OWN_verification_json_is_refused_as_SELF_ADMISSION(
        bundle_dir, view):
    """The easiest wrong file in the world to pass: it is sitting right there in the bundle.

    It is the producer's EMPTY SLOT (verifier_id: null, verdict: pending), not a verdict.
    """
    placeholder = os.path.join(bundle_dir, "verification.json")
    with pytest.raises(D.RefusalError) as e:
        _bind(bundle_dir, placeholder, view)
    assert e.value.reason == D.REFUSE_W10_SELF_ADMITTED
    assert "empty slot" in str(e.value)


def test_MUTATION_a_bundle_that_ADMITTED_ITSELF_is_refused(tmp_path, view):
    """A generator that signs its own homework is the same process asserting twice."""
    d = fx.write_full_bundle(str(tmp_path / "direct"), view, self_admitted=True)
    report = fx.write_w10_report(str(tmp_path / "w10.json"), d, view)
    with pytest.raises(D.RefusalError) as e:
        _bind(d, report, view)
    assert e.value.reason == D.REFUSE_W10_SELF_ADMITTED


def test_MUTATION_a_report_from_ANOTHER_CHECKER_is_refused(tmp_path, bundle_dir, view):
    bad = fx.write_w10_report(str(tmp_path / "w10.json"), bundle_dir, view,
                              verifier_id="spot.stage02.some.other.verifier.v1")
    with pytest.raises(D.RefusalError) as e:
        _bind(bundle_dir, bad, view)
    assert e.value.reason == D.REFUSE_W10_WRONG_VERIFIER


def test_MUTATION_a_report_against_a_DIFFERENT_SPEC_is_refused(tmp_path, bundle_dir, view):
    bad = fx.write_w10_report(str(tmp_path / "w10.json"), bundle_dir, view,
                              spec_sha256="f" * 64)
    with pytest.raises(D.RefusalError) as e:
        _bind(bundle_dir, bad, view)
    assert e.value.reason == D.REFUSE_W10_SPEC_DRIFT


def test_MUTATION_a_REFUSE_verdict_is_not_a_weaker_admit(tmp_path, bundle_dir, view):
    bad = fx.write_w10_report(str(tmp_path / "w10.json"), bundle_dir, view,
                              verdict="REFUSE")
    with pytest.raises(D.RefusalError) as e:
        _bind(bundle_dir, bad, view)
    assert e.value.reason == D.REFUSE_W10_NOT_ADMITTED


def test_MUTATION_a_verdict_flipped_to_ADMIT_does_not_survive_its_own_hash(
        tmp_path, bundle_dir, view):
    """``report_sha256`` is RE-DERIVED here, never quoted.

    A verdict that can be edited after it was cited is a claim, not a result — and the edit
    that matters is REFUSE -> ADMIT.
    """
    path = str(tmp_path / "w10.json")
    fx.write_w10_report(path, bundle_dir, view, verdict="REFUSE")
    doc = json.load(open(path))
    doc["verdict"] = "ADMIT"                      # flip it, keep the old hash
    with open(path, "w") as fh:
        json.dump(doc, fh)

    with pytest.raises(D.RefusalError) as e:
        _bind(bundle_dir, path, view)
    assert e.value.reason == D.REFUSE_W10_REPORT_TAMPERED


def test_MUTATION_a_verifier_that_will_not_declare_independence_is_refused(
        tmp_path, bundle_dir, view):
    bad = fx.write_w10_report(str(tmp_path / "w10.json"), bundle_dir, view,
                              independent=False)
    with pytest.raises(D.RefusalError) as e:
        _bind(bundle_dir, bad, view)
    assert e.value.reason == D.REFUSE_W10_NOT_INDEPENDENT


# --------------------------------------------------------------------------- #
# A REPORT ABOUT ANOTHER BUNDLE, AND A SWAPPED / STALE BUNDLE.
# --------------------------------------------------------------------------- #
def test_MUTATION_a_real_ADMIT_report_for_ANOTHER_BUNDLE_is_refused(tmp_path, view):
    """A genuine ADMIT, beside the wrong bundle.

    Both bundles are real and both were honestly admitted — but the report names the bytes it
    looked at, and they are not these bytes.
    """
    a = fx.write_full_bundle(str(tmp_path / "A"), view)
    b = fx.write_full_bundle(str(tmp_path / "B"), view, condition="Rest")
    report_for_b = fx.write_w10_report(str(tmp_path / "w10_B.json"), b, view,
                                       condition="Rest")
    with pytest.raises(D.RefusalError) as e:
        _bind(a, report_for_b, view)              # A's bundle, B's admission
    assert e.value.reason in (D.REFUSE_BUNDLE_SWAPPED_FILE,
                              D.REFUSE_W10_REPORT_IS_ABOUT_ANOTHER_BUNDLE,
                              D.REFUSE_ARM_WRONG_CONDITION)


def test_MUTATION_a_SWAPPED_FILE_in_the_bundle_is_caught_by_rehashing(
        bundle_dir, w10_report, view):
    """A directory keeps its name when its contents are edited."""
    path = os.path.join(bundle_dir, "masks.parquet")
    pd.DataFrame([{"target_id": "TAMPERED", "gene_id": "X"}]).to_parquet(path, index=False)

    with pytest.raises(D.RefusalError) as e:
        _bind(bundle_dir, w10_report, view)
    assert e.value.reason == D.REFUSE_BUNDLE_SWAPPED_FILE


def test_MUTATION_an_INCOMPLETE_bundle_is_refused(bundle_dir, w10_report, view):
    os.remove(os.path.join(bundle_dir, "gene_universe.json"))
    with pytest.raises(D.RefusalError) as e:
        _bind(bundle_dir, w10_report, view)
    assert e.value.reason == D.REFUSE_BUNDLE_INCOMPLETE


def test_MUTATION_a_missing_direct_bundle_is_refused(tmp_path, w10_report, view):
    with pytest.raises(D.RefusalError) as e:
        _bind(str(tmp_path / "nope"), w10_report, view)
    assert e.value.reason == D.REFUSE_BUNDLE_MISSING


# --------------------------------------------------------------------------- #
# ALTERED RANKS / VALUES.
# --------------------------------------------------------------------------- #
def test_MUTATION_an_altered_RANK_is_caught(tmp_path, view):
    d = fx.write_full_bundle(str(tmp_path / "direct"), view, tamper_rank=True)
    report = fx.write_w10_report(str(tmp_path / "w10.json"), d, view)
    with pytest.raises(D.RefusalError) as e:
        _bind(d, report, view)
    assert e.value.reason == D.REFUSE_ALTERED_ROWS


def test_MUTATION_an_altered_VALUE_is_caught_too(bundle_dir, w10_report, view):
    rows_path = os.path.join(bundle_dir, "arms.parquet")
    df = pd.read_parquet(rows_path)
    df.loc[0, "value"] = float(df.loc[0, "value"] or 0.0) + 1.0
    df.to_parquet(rows_path, index=False)

    with pytest.raises(D.RefusalError) as e:
        _bind(bundle_dir, w10_report, view)
    # caught by the artifact re-hash, or by the row hash — either is a refusal
    assert e.value.reason in (D.REFUSE_BUNDLE_SWAPPED_FILE, D.REFUSE_ALTERED_ROWS)


# --------------------------------------------------------------------------- #
# FIXTURE / LANE.
# --------------------------------------------------------------------------- #
def test_MUTATION_a_SYNTHETIC_bundle_may_not_carry_PRODUCTION_support(
        tmp_path, bundle_dir, view):
    """Fixture output wearing a production artifact's provenance."""
    report = fx.write_w10_report(str(tmp_path / "w10.json"), bundle_dir, view,
                                 lane="synthetic")
    with pytest.raises(D.RefusalError) as e:
        _bind(bundle_dir, report, view, lane="production", release=make_release())
    assert e.value.reason == D.REFUSE_FIXTURE_INPUT


def test_MUTATION_a_FIXTURE_release_may_not_back_a_production_run():
    """The TYPE is the lane. A fixture cannot be relabelled by editing a string."""
    with pytest.raises(D.RefusalError) as e:
        binding.refuse_fixture_release(make_release(), "production")
    assert e.value.reason == D.REFUSE_FIXTURE_INPUT


# --------------------------------------------------------------------------- #
# THE ARM.
# --------------------------------------------------------------------------- #
def test_MUTATION_th9_is_refused_as_not_base_portable(bundle_dir, w10_report, view):
    with pytest.raises(D.RefusalError) as e:
        _bind(bundle_dir, w10_report, view, arm_key=f"direct|th9_like|increase|{CONDITION}")
    assert e.value.reason == D.REFUSE_NOT_BASE_PORTABLE


@pytest.mark.parametrize("pid,reason", [
    ("cd4_ctl_like_actadj", D.REFUSE_SENSITIVITY_LANE),
    ("rq_probe", D.REFUSE_RESEARCH_NAMESPACE),
])
def test_MUTATION_sensitivity_and_research_lanes_are_refused(pid, reason, bundle_dir,
                                                             w10_report, view):
    with pytest.raises(D.RefusalError) as e:
        _bind(bundle_dir, w10_report, view, arm_key=f"direct|{pid}|increase|{CONDITION}")
    assert e.value.reason == reason


def test_MUTATION_scorer_view_mismatch_is_refused(tmp_path, view):
    built = scorer_view.view(make_release())
    d = fx.write_full_bundle(str(tmp_path / "direct"), built)
    report = fx.write_w10_report(str(tmp_path / "w10.json"), d, built)

    other = scorer_view.view(make_release(portable={"th1_like": False}))
    with pytest.raises(D.RefusalError) as e:
        _bind(d, report, other)
    assert e.value.reason in (D.REFUSE_SCORER_MISMATCH, D.REFUSE_BUNDLE_STALE)


def test_MUTATION_missing_panel_refuses_the_arm_and_never_returns_zeros(tmp_path):
    empty = scorer_view.view(make_release(panels={PROGRAM: []}))
    d = fx.write_full_bundle(str(tmp_path / "direct"), empty)
    report = fx.write_w10_report(str(tmp_path / "w10.json"), d, empty)

    with pytest.raises(D.RefusalError) as e:
        _bind(d, report, empty)
    assert e.value.reason == D.REFUSE_NO_PANEL
    assert "table of zeros" in str(e.value)


# --------------------------------------------------------------------------- #
# EVERY refusal is TYPED — a scheduler can branch on it.
# --------------------------------------------------------------------------- #
def test_every_refusal_reason_is_enumerated():
    """An unenumerated refusal is how 'declined' becomes indistinguishable from 'crashed'."""
    assert len(set(D.REFUSAL_REASONS)) == len(D.REFUSAL_REASONS)
    with pytest.raises(ValueError, match="not an enumerated refusal reason"):
        D.record(D.REFUSED, reason="something_i_made_up")


def test_a_refusal_record_carries_no_support():
    rec = D.RefusalError(D.REFUSE_NO_PANEL, "x").record(arm_key=KEY)
    assert rec["state"] == D.REFUSED
    assert rec["support_emitted"] is False
    assert rec["reason"] == D.REFUSE_NO_PANEL
    assert rec["arm_key"] == KEY
