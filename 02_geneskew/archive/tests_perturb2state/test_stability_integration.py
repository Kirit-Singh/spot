"""P2S is SECONDARY SUPPORT. It may add; it may never rank, gate, promote or demote.

Two things were wrong here, and only one of them was a Direct defect.

1. THE RETIRED COMBINED API. The integration test ranked on
   ``projection.rank_rows(..., "balanced_a_to_b")`` over a ``balanced_skew`` column.
   Both are gone. Direct publishes two independent rankings and no combined objective,
   and restoring one so an integration test has a single order to protect would
   reintroduce exactly the thing the two-arm screen exists to refuse.

2. THE COMBINED SUPPORT LANE. P2S judged support on ``combined_A_to_B``, which is
   z(away) + z(toward) — an unweighted sum of two z-scored arms. That is a combined
   objective by another name. P2S never ranked anything with it, so it was not a Direct
   defect; it was the same mistake one layer out, and it was worse in one specific way:
   a single ``perturb2state_support_status`` cannot say WHICH arm it supports.
   "Supported" on a target whose support is entirely away-arm, while its toward arm is
   actively OPPOSED, is a sentence that means the opposite of what it looks like.

So support is now emitted once PER ARM, under the arms' own names, and the combined lane
is quarantined as a reconstruction diagnostic that never reaches a consumer's table.
"""
import numpy as np
import pandas as pd
import pytest
from direct import config as dcfg
from direct import projection as proj
from perturb2state import config as cfg
from perturb2state import stability

AWAY, TOWARD = "away_from_A", "toward_B"
COMBINED = cfg.RECONSTRUCTION_DIAGNOSTIC_LANE

ARM_COLUMNS = [dcfg.ARM_A, dcfg.ARM_B]
RANK_COLUMNS = [dcfg.ARM_RANK_COLUMN[a] for a in dcfg.ARMS]

FORBIDDEN_COMBINED = {
    "balanced_skew", "balanced_a_to_b", "combined_score", "combination",
    "composite_score", "total_skew", "mean_arm_score", "overall_score",
    "rank", "primary_rank", "headline_rank", "overall_rank",
}


def _coef_df():
    """Targets whose two arms DISAGREE — the case the combined lane used to hide.

    T_SPLIT is supported on the away arm and OPPOSED on the toward arm. Summed, those
    cancel into something unremarkable; reported per arm, they are the finding.
    """
    rows = []

    def add(matrix, layer, cfgname, scope, lane, target, coef):
        rows.append({"matrix": matrix, "layer": layer, "config": cfgname,
                     "scope": scope, "lane": lane, "target_ensembl": target,
                     "coefficient": coef, "coef_fit_variation": 0.01,
                     "nonzero": abs(coef) > cfg.NONZERO_TOL,
                     "sign": int(np.sign(coef)) if abs(coef) > cfg.NONZERO_TOL else 0})

    scopes = ["all_donor", "lodo_D1", "lodo_D2", "lodo_D3", "lodo_D4"]
    plan = {
        # target      away   toward  combined (the quarantined diagnostic)
        "T_BOTH":    (0.8,   0.8,    0.9),
        "T_SPLIT":   (0.8,  -0.9,    0.1),     # supported away, OPPOSED toward
        "T_OPPOSED": (-0.9, -0.9,   -0.9),
    }
    for target, (away, toward, comb) in plan.items():
        for lane, coef in ((AWAY, away), (TOWARD, toward), (COMBINED, comb)):
            for scope in scopes:
                add("main", "zscore", "pca_off", scope, lane, target, coef)
            add("main", "log_fc", "pca_off", "all_donor", lane, target, coef * 0.9)
            add("guide_1", "zscore", "pca_off", "all_donor", lane, target, coef * 0.8)
    return pd.DataFrame(rows)


@pytest.fixture
def stab():
    return stability.compute_stability(_coef_df(), {}, "masksha")


@pytest.fixture
def integ(stab):
    return stability.integration_lane(stab, "manifestsha", model_commit="abc123")


# --------------------------------------------------------------------------- #
# 1. SUPPORT IS PER ARM. The split target is the whole point.
# --------------------------------------------------------------------------- #
def test_support_is_reported_SEPARATELY_for_each_arm(integ):
    i = integ.set_index("target_ensembl")
    assert i.loc["T_SPLIT", f"perturb2state_{AWAY}_support_status"] == "p2s_supported"
    assert i.loc["T_SPLIT", f"perturb2state_{TOWARD}_support_status"] == "p2s_opposed"


def test_the_OPPOSED_arm_is_FLAGGED_and_never_averaged_away(integ):
    """A negative coefficient wanted the INVERSE of the measured knockdown signature.

    That is a finding, not a weak yes. It is flagged per arm, and it cannot be summed
    into the away arm's support to produce a target that looks quietly fine.
    """
    i = integ.set_index("target_ensembl")
    assert bool(i.loc["T_SPLIT", f"perturb2state_{TOWARD}_opposed"]) is True
    assert bool(i.loc["T_SPLIT", f"perturb2state_{AWAY}_opposed"]) is False
    assert bool(i.loc["T_OPPOSED", f"perturb2state_{AWAY}_opposed"]) is True
    assert bool(i.loc["T_OPPOSED", f"perturb2state_{TOWARD}_opposed"]) is True


def test_a_reader_cannot_get_ONE_support_status_for_a_target(integ):
    """There is no unarmed `perturb2state_support_status` to misread."""
    assert "perturb2state_support_status" not in integ.columns
    for arm in cfg.ARM_LANES:
        assert f"perturb2state_{arm}_support_status" in integ.columns


def test_both_arms_report_every_frequency_and_agreement(integ):
    for arm in cfg.ARM_LANES:
        for field in ("selection_frequency", "positive_frequency",
                      "negative_frequency", "lodo_sign_agreement",
                      "guide_agreement", "logfc_zscore_agreement",
                      "median_coefficient"):
            assert f"perturb2state_{arm}_{field}" in integ.columns


# --------------------------------------------------------------------------- #
# 2. THE COMBINED LANE IS QUARANTINED.
# --------------------------------------------------------------------------- #
def test_the_combined_lane_NEVER_reaches_the_integration_table(integ):
    """It is a combined objective. A consumer must not be able to join it in by accident."""
    assert not [c for c in integ.columns if COMBINED in c]
    assert not [c for c in integ.columns if "combined" in c.lower()]
    assert not (set(integ.columns) & FORBIDDEN_COMBINED)


def test_the_combined_lane_survives_ONLY_as_a_named_diagnostic(stab):
    diag = stability.reconstruction_diagnostic(stab)
    assert set(diag["target_ensembl"]) == {"T_BOTH", "T_SPLIT", "T_OPPOSED"}
    # it says what it is, in the artifact, where a consumer will see it
    assert bool(diag["p2s_reconstruction_is_a_combined_objective"].iloc[0]) is True
    assert bool(diag["p2s_reconstruction_may_rank_or_gate"].iloc[0]) is False
    assert "integration_lane" in diag["p2s_reconstruction_excluded_from"].iloc[0]


def test_the_config_declares_the_lane_quarantined():
    assert cfg.RECONSTRUCTION_DIAGNOSTIC_IS_RANKING is False
    assert COMBINED not in cfg.SUPPORT_LANES
    assert cfg.SUPPORT_LANES == cfg.ARM_LANES == [AWAY, TOWARD]
    assert COMBINED in cfg.LANES          # still computed — as a diagnostic


def test_the_p2s_lanes_are_named_EXACTLY_as_the_direct_arms():
    """``toward_b`` was the retired v2 casing, sitting on one side of a join whose other
    side said ``toward_B``. Nothing joined them, so nothing noticed — and the first code
    to merge P2S onto the screen by lane name would have matched zero rows for that arm
    and reported no support where support existed."""
    assert cfg.ARM_LANES == list(dcfg.ARMS)


# --------------------------------------------------------------------------- #
# 3. PROVENANCE: the model is pinned, and a coefficient is not a p-value.
# --------------------------------------------------------------------------- #
def test_the_model_commit_and_manifest_hash_are_pinned(integ):
    assert set(integ["perturb2state_model_manifest_sha256"]) == {"manifestsha"}
    assert set(integ["perturb2state_model_commit"]) == {"abc123"}


def test_a_coefficient_is_NOT_a_p_value_and_says_so(integ):
    assert set(integ["perturb2state_coefficient_semantics"]) == \
        {"fitted_reconstruction_weight_not_inference"}
    assert cfg.COEF_SEM_SEMANTICS == "fit_variation_not_inference"
    # no p/q anywhere in the support lane
    assert not [c for c in integ.columns
                if any(t in c.lower() for t in ("pval", "p_value", "qval", "fdr"))]


def test_the_lane_declares_itself_secondary_and_non_ranking(integ):
    assert set(integ["perturb2state_is_secondary_support_only"]) == {True}
    assert set(integ["perturb2state_may_rank_or_gate"]) == {False}


def test_an_unknown_lane_is_refused(stab):
    bad = stab.copy()
    bad.loc[0, "lane"] = "balanced_a_to_b"
    with pytest.raises(ValueError, match="unknown lane"):
        stability.integration_lane(bad, "manifestsha")


# --------------------------------------------------------------------------- #
# 4. THE DIRECT ARMS SURVIVE THE MERGE, BYTE FOR BYTE.
# --------------------------------------------------------------------------- #
def _direct_screen() -> pd.DataFrame:
    """T3 opposes B and moves only weakly away from A — the target a combined objective
    would have let P2S promote, so it is the one the merge must not move."""
    rows = [
        {"target_id": "T1", "away_from_A": 1.0, "toward_B": 0.8,
         "A_evaluable": True, "B_evaluable": True},
        {"target_id": "T2", "away_from_A": 0.6, "toward_B": 0.4,
         "A_evaluable": True, "B_evaluable": True},
        {"target_id": "T3", "away_from_A": -0.2, "toward_B": -0.4,
         "A_evaluable": True, "B_evaluable": True},
    ]
    for arm in dcfg.ARMS:
        proj.rank_arm(rows, arm, evaluable_key=f"{dcfg.ARM_POLE[arm]}_evaluable",
                      rank_column=dcfg.ARM_RANK_COLUMN[arm])
    return pd.DataFrame(proj.emit_order(rows))


def _p2s_lane() -> pd.DataFrame:
    """P2S gives the OPPOSED, bottom-ranked target its strongest support in BOTH arms."""
    return pd.DataFrame({
        "target_id": ["T3", "T1", "T2"],
        f"perturb2state_{AWAY}_selection_frequency": [1.0, 0.2, 0.1],
        f"perturb2state_{AWAY}_support_status": ["p2s_supported", "p2s_weak",
                                                 "p2s_weak"],
        f"perturb2state_{TOWARD}_selection_frequency": [1.0, 0.2, 0.1],
        f"perturb2state_{TOWARD}_support_status": ["p2s_supported", "p2s_weak",
                                                   "p2s_weak"],
    })


def test_p2s_leaves_BOTH_direct_arms_byte_identical():
    direct = _direct_screen()
    merged = direct.merge(_p2s_lane(), on="target_id", how="left")

    assert list(merged["target_id"]) == list(direct["target_id"])
    for col in ARM_COLUMNS + RANK_COLUMNS:
        pd.testing.assert_series_equal(merged[col], direct[col],
                                       check_dtype=True, check_names=True)


def test_p2s_cannot_promote_the_target_it_supports_most():
    """T3 opposes B, P2S backs it hardest in both arms — and it stays LAST in both."""
    direct = _direct_screen()
    merged = direct.merge(_p2s_lane(), on="target_id", how="left")

    strongest = merged.loc[
        merged[f"perturb2state_{AWAY}_support_status"] == "p2s_supported",
        "target_id"].tolist()
    assert strongest == ["T3"]

    for rank_col in RANK_COLUMNS:
        assert list(merged.sort_values(rank_col)["target_id"]) == ["T1", "T2", "T3"]
        assert int(merged.set_index("target_id").loc["T3", rank_col]) == 3


def test_p2s_adds_ONLY_secondary_support_fields():
    direct = _direct_screen()
    merged = direct.merge(_p2s_lane(), on="target_id", how="left")

    added = set(merged.columns) - set(direct.columns)
    assert added
    assert all(c.startswith("perturb2state_") for c in added), added
    assert not (set(merged.columns) & FORBIDDEN_COMBINED)


def test_the_direct_lane_exposes_no_combined_ranking_API():
    """The retired API must stay retired: this test used to CALL it."""
    assert not hasattr(proj, "rank_rows")
    assert dcfg.COMBINED_OBJECTIVE_PERMITTED is False
    assert dcfg.HEADLINE_ARM_PERMITTED is False
    assert hasattr(proj, "rank_arm")
    assert len(dcfg.ARMS) == 2


# --------------------------------------------------------------------------- #
# 5. P2S support exists only for targets that were eligible perturbation columns.
# --------------------------------------------------------------------------- #
def test_ineligible_target_cannot_enter_the_support_lane_via_p2s(integ):
    """An ineligible direct-screen target never becomes a perturbation column, so it has
    no coefficient and cannot appear here. P2S cannot rescue it (§6.7)."""
    assert set(integ["target_ensembl"]) <= {"T_BOTH", "T_SPLIT", "T_OPPOSED"}
    assert "T_INELIGIBLE" not in set(integ["target_ensembl"])
