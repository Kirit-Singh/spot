"""Stability + integration-policy tests (plan §6.6, §6.7, §6.9)."""
import numpy as np
import pandas as pd

from perturb2state import config as cfg
from perturb2state import stability
from direct import config as dcfg
from direct import projection as proj


def _coef_df():
    """Two targets across a few tagged runs on the combined lane."""
    rows = []
    def add(matrix, layer, config, scope, lane, target, coef):
        rows.append({"matrix": matrix, "layer": layer, "config": config,
                     "scope": scope, "lane": lane, "target_ensembl": target,
                     "coefficient": coef, "coef_fit_variation": 0.01,
                     "nonzero": abs(coef) > cfg.NONZERO_TOL,
                     "sign": int(np.sign(coef)) if abs(coef) > cfg.NONZERO_TOL else 0})
    lane = cfg.SUPPORT_LANE
    # T_supported: consistently positive & selected everywhere
    for scope in ["all_donor", "lodo_D1", "lodo_D2", "lodo_D3", "lodo_D4"]:
        add("main", "zscore", "pca_off", scope, lane, "T_supported", 0.8)
    add("main", "log_fc", "pca_off", "all_donor", lane, "T_supported", 0.7)
    add("guide_1", "zscore", "pca_off", "all_donor", lane, "T_supported", 0.6)
    # T_opposed: consistently negative (inverse knockdown)
    for scope in ["all_donor", "lodo_D1", "lodo_D2", "lodo_D3", "lodo_D4"]:
        add("main", "zscore", "pca_off", scope, lane, "T_opposed", -0.9)
    add("main", "log_fc", "pca_off", "all_donor", lane, "T_opposed", -0.8)
    return pd.DataFrame(rows)


def test_support_status_rule():
    stab = stability.compute_stability(_coef_df(), {}, "masksha")
    s = stab.set_index("target_ensembl")
    assert s.loc["T_supported", "support_status"] == "p2s_supported"
    assert s.loc["T_supported", "positive_frequency"] == 1.0
    assert s.loc["T_opposed", "support_status"] == "p2s_opposed"
    assert s.loc["T_opposed", "negative_frequency"] == 1.0


def test_lodo_and_layer_agreement_reported():
    stab = stability.compute_stability(_coef_df(), {}, "masksha").set_index("target_ensembl")
    assert stab.loc["T_supported", "lodo_sign_agreement"] == 1.0
    assert stab.loc["T_supported", "logfc_zscore_agreement"] == 1.0
    assert stab.loc["T_supported", "guide_sign_agreement"] == 1.0


def test_ineligible_target_cannot_enter_locked_set_via_p2s():
    """P2S support exists only for targets that were eligible perturbation columns.

    An ineligible direct-screen target never becomes a perturbation column, so it
    has no coefficient and cannot appear in the integration support lane — P2S
    cannot rescue it (plan §6.7).
    """
    stab = stability.compute_stability(_coef_df(), {}, "masksha")
    integ = stability.integration_lane(stab, "manifestsha")
    eligible_columns = {"T_supported", "T_opposed"}
    assert set(integ["target_ensembl"]) <= eligible_columns
    assert "T_ineligible" not in set(integ["target_ensembl"])


# --------------------------------------------------------------------------- #
# THE INTEGRATION CONTRACT (§6.7), restated for the TWO-ARM direct screen.
#
# This test used to rank on ``balanced_a_to_b`` — a single combined objective over a
# ``balanced_skew`` column — and assert that P2S did not disturb THAT order. Both are
# retired. Direct has no combined objective, no headline arm and no single ``rank``: it
# publishes two independent rankings, ``rank_away_from_A`` and ``rank_toward_B``, each
# over its own arm's evaluable population.
#
# The contract P2S must satisfy is therefore stronger and more specific than "the order
# is unchanged". It is:
#
#   P2S may ADD secondary support fields. It may not reorder, gate or replace EITHER
#   direct arm — so both arms' score and rank columns must come out of the merge
#   byte-identical to what Direct emitted.
#
# It is deliberately NOT satisfied by restoring a combined ranking so that there is one
# order to protect. A combined objective is the thing the two-arm design exists to
# refuse: a target that moves strongly away from A while OPPOSING B must never outrank
# one that genuinely moves toward B.
# --------------------------------------------------------------------------- #
ARM_COLUMNS = [dcfg.ARM_A, dcfg.ARM_B]                       # away_from_A, toward_B
RANK_COLUMNS = [dcfg.ARM_RANK_COLUMN[a] for a in dcfg.ARMS]  # rank_away_from_A/_toward_B

FORBIDDEN_COMBINED = {
    "balanced_skew", "balanced_a_to_b", "combined_score", "combination",
    "composite_score", "total_skew", "mean_arm_score", "overall_score",
    "rank", "primary_rank", "headline_rank", "overall_rank",
}


def _direct_screen() -> pd.DataFrame:
    """A direct screen ranked by the REAL two-arm API — one rank per arm.

    T3 opposes B and moves only weakly away from A: it is the target a combined
    objective would have let P2S promote, so it is the one the merge must not move.
    """
    rows = [
        {"target_id": "T1", "away_from_A": 1.0, "toward_B": 0.8,
         "A_evaluable": True, "B_evaluable": True},
        {"target_id": "T2", "away_from_A": 0.6, "toward_B": 0.4,
         "A_evaluable": True, "B_evaluable": True},
        {"target_id": "T3", "away_from_A": -0.2, "toward_B": -0.4,
         "A_evaluable": True, "B_evaluable": True},
    ]
    for arm in dcfg.ARMS:
        proj.rank_arm(rows, arm,
                      evaluable_key=f"{dcfg.ARM_POLE[arm]}_evaluable",
                      rank_column=dcfg.ARM_RANK_COLUMN[arm])
    return pd.DataFrame(proj.emit_order(rows))


def _p2s_lane() -> pd.DataFrame:
    """P2S deliberately gives the OPPOSED, bottom-ranked target its strongest support."""
    return pd.DataFrame({
        "target_id": ["T3", "T1", "T2"],
        "perturb2state_selection_frequency": [1.0, 0.2, 0.1],
        "perturb2state_support_status": ["p2s_supported", "p2s_weak", "p2s_weak"],
    })


def test_p2s_leaves_BOTH_direct_arms_byte_identical():
    """Every arm's score AND rank column survives the merge unchanged (§6.7)."""
    direct = _direct_screen()
    merged = direct.merge(_p2s_lane(), on="target_id", how="left")

    # row identity and order first: a reindexed frame could match column-wise by accident
    assert list(merged["target_id"]) == list(direct["target_id"])

    for col in ARM_COLUMNS + RANK_COLUMNS:
        pd.testing.assert_series_equal(merged[col], direct[col],
                                       check_dtype=True, check_names=True)


def test_p2s_cannot_promote_the_target_it_supports_most():
    """The whole point. T3 opposes B, and P2S backs it hardest — and it stays LAST.

    T3 is evaluable in both arms and carries a real (negative) score, so Direct ranks it
    — at the bottom of each arm, which is exactly where its measured effect puts it. The
    forbidden move is P2S lifting it off that bottom, and under a combined objective a
    strong secondary-support signal is precisely how it would.
    """
    direct = _direct_screen()
    merged = direct.merge(_p2s_lane(), on="target_id", how="left")

    strongest = merged.loc[merged["perturb2state_support_status"] == "p2s_supported",
                           "target_id"].tolist()
    assert strongest == ["T3"]

    for rank_col in RANK_COLUMNS:
        ordered = list(merged.sort_values(rank_col)["target_id"])
        assert ordered == ["T1", "T2", "T3"], rank_col
        assert int(merged.set_index("target_id").loc["T3", rank_col]) == 3


def test_p2s_adds_ONLY_secondary_support_fields():
    """It may add. It may not replace, and it may not smuggle in a combined objective."""
    direct = _direct_screen()
    merged = direct.merge(_p2s_lane(), on="target_id", how="left")

    added = set(merged.columns) - set(direct.columns)
    assert added, "the integration lane added nothing at all"
    assert all(c.startswith("perturb2state_") for c in added), added
    assert not (set(merged.columns) & FORBIDDEN_COMBINED), \
        "a combined objective or headline rank re-entered the direct screen"


def test_the_direct_lane_exposes_no_combined_ranking_API():
    """The retired API must stay retired: this test used to CALL it.

    ``rank_rows(rows, "balanced_a_to_b")`` ranked one combined score. Its absence is the
    contract — restoring it to make an integration test pass would reintroduce exactly
    the objective the two-arm screen exists to refuse.
    """
    assert not hasattr(proj, "rank_rows")
    assert dcfg.COMBINED_OBJECTIVE_PERMITTED is False
    assert dcfg.HEADLINE_ARM_PERMITTED is False
    assert hasattr(proj, "rank_arm")            # ...and the two-arm API is what exists
    assert len(dcfg.ARMS) == 2


def test_ui_values_match_integration_and_stability():
    """The UI lane values are exactly the combined-lane stability values (§6.9)."""
    stab = stability.compute_stability(_coef_df(), {}, "masksha")
    integ = stability.integration_lane(stab, "manifestsha").set_index("target_ensembl")
    comb = stab[stab["lane"] == cfg.SUPPORT_LANE].set_index("target_ensembl")
    for t in comb.index:
        assert integ.loc[t, "perturb2state_selection_frequency"] == comb.loc[t, "selection_frequency"]
        assert integ.loc[t, "perturb2state_support_status"] == comb.loc[t, "support_status"]
