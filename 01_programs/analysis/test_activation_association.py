"""Regression for the external-review S1-M4 re-audit bounce.

The CD4-CTL activation-adjusted residual column is ``cd4_ctl_like_score_actadj`` — it ends in ``_actadj``,
NOT ``_score``, so an ``endswith('_score')`` filter silently dropped it and the pooled-CTL-residual
activation association was absent from the served artifact. Guard: the residual must appear with its
per-condition/donor association, and the artifact must stay descriptive (no p/q/FDR).
"""
import json
import os

import hashlib

ANALYSIS = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(ANALYSIS), "app", "data")
ART = os.path.join(DATA, "stage01_activation_association_v1.json")


def _load():
    return json.load(open(ART))


def test_actadj_residual_present_with_association():
    r = _load()["programs"].get("cd4_ctl_like_score_actadj")
    assert r is not None, "the CD4-CTL _actadj residual must not be silently dropped"
    assert isinstance(r["pooled_rho"], (int, float))
    assert r["by_condition"], "residual must carry per-condition association"
    for v in r["by_condition"].values():
        assert "donor_rho" in v and "max_abs_donor_rho" in v
    assert any(v["donor_rho"] for v in r["by_condition"].values()), "residual must carry per-condition/donor numbers"
    # the disclosure's "near-zero pooled overlap but retained condition/donor structure" must be a real number
    assert abs(r["pooled_rho"]) < 0.1
    assert r["max_abs_donor_rho_any_condition"] > 0.1


def test_activation_association_descriptive_only():
    a = _load()
    assert a["inference_status"] == "descriptive_only_no_p_q_fdr"
    # the activation axis is included with its trivial self-association (≡1), for completeness
    assert abs(a["programs"]["diff_activated_score"]["pooled_rho"] - 1.0) < 1e-9


def test_every_primary_axis_and_the_residual_reported():
    progs = _load()["programs"]
    assert "cd4_ctl_like_score_actadj" in progs                    # the sensitivity lane
    assert len([k for k in progs if k.endswith("_score")]) == 11   # all 11 primary program axes (incl diff_activated)
    assert len(progs) == 12                                        # 11 primary axes + the actadj residual


def test_activation_artifact_hash_bound_in_current_manifest_protected():
    """S1-M4: the artifact's raw hash is bound into current.json, the release manifest AND PROTECTED_HASHES,
    so it cannot be silently swapped."""
    raw = hashlib.sha256(open(ART, "rb").read()).hexdigest()
    cur = json.load(open(os.path.join(DATA, "stage01_current.json")))
    assert cur["activation_association_source"]["raw_sha256"] == raw
    assert cur["activation_association_source"]["active_gate"] is False   # descriptive, never a gate
    man = json.load(open(os.path.join(DATA, "stage01_release_manifest.json")))
    assert raw in json.dumps(man), "activation artifact hash absent from the release manifest"
    prot = json.load(open(os.path.join(ANALYSIS, "stage2_bridge", "PROTECTED_HASHES.json")))
    assert prot["raw_sha256"].get("activation_association") == raw
