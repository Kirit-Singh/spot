"""Perturb2State stability aggregation (plan §6.6, §6.7).

Aggregates per-run reconstruction coefficients into per-target stability
records. Every field is a frequency / sign / range retained verbatim; the single
categorical ``support_status`` follows a rule frozen before unblinding (§6.6)
and never overrides the direct ranking (§6.7).

Run tags carried on each coefficient row:
    matrix  : main | guide_1 | guide_2 | donorpair_<pair>
    layer   : zscore | log_fc
    config  : pca_off | pca_on_50
    scope   : all_donor | lodo_D1..lodo_D4
    lane    : away_from_A | toward_b | combined_A_to_B
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


def _freq(mask: pd.Series) -> float:
    return float(mask.mean()) if len(mask) else 0.0


def _sign_agreement(signs: pd.Series) -> float:
    """Fraction of nonzero signs sharing the dominant sign (1.0 if <=1 nonzero)."""
    nz = signs[signs != 0]
    if len(nz) <= 1:
        return 1.0 if len(nz) == 1 else 0.0
    pos = int((nz > 0).sum())
    neg = int((nz < 0).sum())
    return max(pos, neg) / len(nz)


def _support_status(sel_freq: float, pos_freq: float, neg_freq: float) -> str:
    if sel_freq <= 0:
        return "p2s_not_selected"
    if sel_freq < config.SUPPORT_MIN_SELECTION:
        return "p2s_weak"
    pos_dom = (pos_freq / sel_freq) if sel_freq else 0.0
    neg_dom = (neg_freq / sel_freq) if sel_freq else 0.0
    if pos_dom >= config.SUPPORT_SIGN_DOMINANCE:
        return "p2s_supported"
    if neg_dom >= config.SUPPORT_SIGN_DOMINANCE:
        return "p2s_opposed"
    return "p2s_mixed"


def _rank_within_runs(coef_df: pd.DataFrame) -> pd.Series:
    """Rank targets by coefficient (descending) within each run; 1 = most supportive."""
    run_keys = ["matrix", "layer", "config", "scope", "lane"]
    return coef_df.groupby(run_keys)["coefficient"].rank(
        ascending=False, method="min")


def compute_stability(coef_df: pd.DataFrame, coverage: dict,
                      mask_sha: str) -> pd.DataFrame:
    """Per (target, lane) stability rows across all runs of that lane."""
    coef_df = coef_df.copy()
    coef_df["run_rank"] = _rank_within_runs(coef_df)
    rows = []
    for (target, lane), g in coef_df.groupby(["target_ensembl", "lane"]):
        sel = g["nonzero"]
        pos = g["sign"] > 0
        neg = g["sign"] < 0
        sel_freq = _freq(sel)
        pos_freq = _freq(pos)
        neg_freq = _freq(neg)

        lodo = g[g["scope"].str.startswith("lodo_")]
        guide = g[g["matrix"].str.startswith("guide_")]
        dpair = g[g["matrix"].str.startswith("donorpair_")]

        # zscore vs logFC sign agreement on matched (scope, config) main runs
        mn = g[g["matrix"] == "main"]
        piv = mn.pivot_table(index=["scope", "config"], columns="layer",
                             values="sign", aggfunc="first")
        if {"zscore", "log_fc"}.issubset(piv.columns):
            both = piv.dropna(subset=["zscore", "log_fc"])
            agree = ((both["zscore"] == both["log_fc"]) &
                     (both["zscore"] != 0)).mean() if len(both) else np.nan
            zlf = float(agree) if not np.isnan(agree) else None
        else:
            zlf = None

        cov = coverage.get(str(target), {})
        rows.append({
            "target_ensembl": str(target),
            "lane": lane,
            "n_runs": int(len(g)),
            "selection_frequency": round(sel_freq, 6),
            "positive_frequency": round(pos_freq, 6),
            "negative_frequency": round(neg_freq, 6),
            "median_coefficient": round(float(g["coefficient"].median()), 6),
            "coefficient_min": round(float(g["coefficient"].min()), 6),
            "coefficient_max": round(float(g["coefficient"].max()), 6),
            "rank_min": int(g["run_rank"].min()),
            "rank_max": int(g["run_rank"].max()),
            "lodo_sign_agreement": round(_sign_agreement(lodo["sign"]), 6)
                if len(lodo) else None,
            "n_lodo_runs": int(len(lodo)),
            "guide_sign_agreement": round(_sign_agreement(guide["sign"]), 6)
                if len(guide) else None,
            "n_guide_runs": int(len(guide)),
            "donor_pair_sign_agreement": round(_sign_agreement(dpair["sign"]), 6)
                if len(dpair) else None,
            "donor_pair_coefficient_range": round(
                float(dpair["coefficient"].max() - dpair["coefficient"].min()), 6)
                if len(dpair) else None,
            "n_donor_pair_runs": int(len(dpair)),
            "logfc_zscore_agreement": (round(zlf, 6) if zlf is not None else None),
            "mask_sha256": mask_sha,
            "target_signature_coverage_retained": cov.get("n_retained"),
            "target_signature_coverage_masked": cov.get("n_masked_in_universe"),
            "support_status": _support_status(sel_freq, pos_freq, neg_freq),
        })
    df = pd.DataFrame(rows).sort_values(["lane", "target_ensembl"]).reset_index(drop=True)
    return df


def integration_lane(stability_df: pd.DataFrame, model_manifest_sha: str) -> pd.DataFrame:
    """Per-target secondary support lane for Stage-2 integration (plan §6.7).

    Derived ONLY from the combined_A_to_B lane. These columns are the visible
    secondary support lane; they never change the direct ranking.
    """
    s = stability_df[stability_df["lane"] == config.SUPPORT_LANE].copy()
    out = pd.DataFrame({
        "target_ensembl": s["target_ensembl"],
        "perturb2state_selection_frequency": s["selection_frequency"],
        "perturb2state_positive_frequency": s["positive_frequency"],
        "perturb2state_negative_frequency": s["negative_frequency"],
        "perturb2state_lodo_sign_agreement": s["lodo_sign_agreement"],
        "perturb2state_guide_agreement": s["guide_sign_agreement"],
        "perturb2state_logfc_zscore_agreement": s["logfc_zscore_agreement"],
        "perturb2state_support_status": s["support_status"],
        "perturb2state_median_coefficient": s["median_coefficient"],
    })
    out["perturb2state_model_manifest_sha256"] = model_manifest_sha
    return out.sort_values("target_ensembl").reset_index(drop=True)
