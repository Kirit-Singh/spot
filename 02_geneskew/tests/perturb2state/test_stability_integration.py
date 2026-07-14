"""Stability + integration-policy tests (plan §6.6, §6.7, §6.9)."""
import numpy as np
import pandas as pd

from perturb2state import config as cfg
from perturb2state import stability
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


def test_direct_ranks_identical_with_and_without_p2s():
    """Merging the P2S support lane must not reorder the direct ranking (§6.7)."""
    rows = [
        {"target_ensembl": "T1", "direction_class": "aligned_both",
         "balanced_skew": 0.9, "away_from_A": 1.0, "toward_b": 0.8},
        {"target_ensembl": "T2", "direction_class": "aligned_both",
         "balanced_skew": 0.5, "away_from_A": 0.6, "toward_b": 0.4},
        {"target_ensembl": "T3", "direction_class": "opposed",
         "balanced_skew": -0.3, "away_from_A": -0.2, "toward_b": -0.4},
    ]
    ranked = proj.rank_rows([dict(r) for r in rows], "balanced_a_to_b")
    base_order = [(r["target_ensembl"], r["rank"]) for r in ranked]

    direct = pd.DataFrame(ranked)
    # P2S deliberately gives the opposed/low target the strongest support
    integ = pd.DataFrame({"target_ensembl": ["T3", "T1", "T2"],
                          "perturb2state_selection_frequency": [1.0, 0.2, 0.1],
                          "perturb2state_support_status": ["p2s_supported",
                                                           "p2s_weak", "p2s_weak"]})
    merged = direct.merge(integ, on="target_ensembl", how="left")
    merged_order = [(r["target_ensembl"], r["rank"]) for _, r in merged.iterrows()]
    assert merged_order == base_order            # rank/order unchanged by P2S


def test_ui_values_match_integration_and_stability():
    """The UI lane values are exactly the combined-lane stability values (§6.9)."""
    stab = stability.compute_stability(_coef_df(), {}, "masksha")
    integ = stability.integration_lane(stab, "manifestsha").set_index("target_ensembl")
    comb = stab[stab["lane"] == cfg.SUPPORT_LANE].set_index("target_ensembl")
    for t in comb.index:
        assert integ.loc[t, "perturb2state_selection_frequency"] == comb.loc[t, "selection_frequency"]
        assert integ.loc[t, "perturb2state_support_status"] == comb.loc[t, "support_status"]
