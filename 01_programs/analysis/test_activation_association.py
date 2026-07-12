"""Regression for the external-review S1-M4 re-audit bounce.

The CD4-CTL activation-adjusted residual column is ``cd4_ctl_like_score_actadj`` — it ends in ``_actadj``,
NOT ``_score``, so an ``endswith('_score')`` filter silently dropped it and the pooled-CTL-residual
activation association was absent from the served artifact. Guard: the residual must appear with its
per-condition/donor association, and the artifact must stay descriptive (no p/q/FDR).
"""
import json
import os

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "data")
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
    assert "diff_activated_score" not in a["programs"]   # the reference axis is not self-correlated


def test_every_program_and_the_residual_reported():
    progs = _load()["programs"]
    assert "cd4_ctl_like_score_actadj" in progs
    assert len([k for k in progs if k.endswith("_score")]) == 10   # 11 primary programs minus the activation axis
    assert len(progs) == 11                                        # + the actadj residual
