"""Broad transcriptomic target-signature construction (plan §6.2).

Pure numpy so the regression is unit-testable without the single-cell stack.
The desired signature is a *reconstruction target*, not a measured effect: it
encodes, for each readout gene, how its expression co-varies with the within-
donor-standardised A/B program scores across donor-stratified pseudobulk bins.

    mean_expression_g ~ 1 + z_A + z_B + activation + donor        (WLS)
    desired_away_A,g   = -beta_A,g
    desired_toward_B,g = +beta_B,g

away/toward are z-scored SEPARATELY across the readout gene universe before the
combined signature is formed (§6.2.11). Exact A/B panel + control genes are
excluded from the readout universe upstream (§6.2.8): they may define the
scores but cannot improve reconstruction.
"""
from __future__ import annotations

import numpy as np


# --------------------------------------------------------------------------- #
# Score reproduction + within-donor standardisation.
# --------------------------------------------------------------------------- #
def program_score(expr: np.ndarray, panel_cols: list[int],
                  control_cols: list[int]) -> np.ndarray:
    """Reproduce a frozen Stage-1 score_genes score for every cell.

    score = mean(panel expr) - mean(control expr), uniform coefficients, over
    the panel/control genes present in the expression universe (plan §4.4 /
    registry ``coefficient_scheme``). ``expr`` is cells x genes (dense).
    """
    if not panel_cols or not control_cols:
        raise ValueError("panel and control must be non-empty in the universe")
    panel = expr[:, panel_cols].mean(axis=1)
    control = expr[:, control_cols].mean(axis=1)
    return np.asarray(panel - control, dtype=np.float64)


def within_donor_z(values: np.ndarray, donors: np.ndarray) -> np.ndarray:
    """Standardise ``values`` to mean 0 / sd 1 WITHIN each donor (plan §6.2.1)."""
    out = np.zeros_like(values, dtype=np.float64)
    for d in np.unique(donors):
        m = donors == d
        v = values[m]
        sd = v.std()
        out[m] = (v - v.mean()) / sd if sd > 0 else 0.0
    return out


# --------------------------------------------------------------------------- #
# Donor-stratified pseudobulk quantile bins (plan §6.2.3).
# --------------------------------------------------------------------------- #
def _quantile_bin(x: np.ndarray, n_bins: int) -> np.ndarray:
    """Assign each value to a within-array quantile bin [0, n_bins)."""
    if x.size == 0:
        return np.zeros(0, dtype=int)
    ranks = np.argsort(np.argsort(x, kind="stable"), kind="stable")
    edges = (ranks * n_bins) // len(x)
    return np.minimum(edges, n_bins - 1).astype(int)


def build_pseudobulk(z_a: np.ndarray, z_b: np.ndarray, activation: np.ndarray,
                     donors: np.ndarray, expr: np.ndarray, n_bins: int) -> dict:
    """Collapse cells into (donor, binA, binB) pseudobulk units.

    Bins are formed WITHIN donor along z_A and z_B (donor-stratified). Returns
    per-unit mean predictors, mean expression, donor label and cell weight.
    """
    unit_za, unit_zb, unit_act, unit_expr, unit_w, unit_donor = [], [], [], [], [], []
    for d in np.unique(donors):
        dm = donors == d
        ba = _quantile_bin(z_a[dm], n_bins)
        bb = _quantile_bin(z_b[dm], n_bins)
        za_d, zb_d, act_d, expr_d = z_a[dm], z_b[dm], activation[dm], expr[dm]
        key = ba * n_bins + bb
        for k in np.unique(key):
            km = key == k
            unit_za.append(za_d[km].mean())
            unit_zb.append(zb_d[km].mean())
            unit_act.append(act_d[km].mean())
            unit_expr.append(expr_d[km].mean(axis=0))
            unit_w.append(int(km.sum()))
            unit_donor.append(str(d))
    return {
        "z_a": np.asarray(unit_za, dtype=np.float64),
        "z_b": np.asarray(unit_zb, dtype=np.float64),
        "activation": np.asarray(unit_act, dtype=np.float64),
        "expr": np.asarray(unit_expr, dtype=np.float64),   # units x genes
        "weight": np.asarray(unit_w, dtype=np.float64),
        "donor": np.asarray(unit_donor, dtype=object),
    }


# --------------------------------------------------------------------------- #
# Per-gene donor-aware WLS (plan §6.2.5).
# --------------------------------------------------------------------------- #
def _design(pb: dict) -> tuple[np.ndarray, list[str]]:
    """Design matrix: [1, z_A, z_B, activation, donor(K-1 dummies)]."""
    n = pb["z_a"].shape[0]
    cols = [np.ones(n), pb["z_a"], pb["z_b"], pb["activation"]]
    names = ["intercept", "z_A", "z_B", "activation"]
    donors = sorted(set(pb["donor"].tolist()))
    for d in donors[1:]:                     # drop-first dummy coding
        cols.append((pb["donor"] == d).astype(np.float64))
        names.append(f"donor_{d}")
    return np.column_stack(cols), names


def fit_betas(pb: dict) -> dict:
    """Vectorised WLS for every gene at once.

    Solves (D^T W D) B = D^T W Y with weight = per-unit cell count. Returns the
    z_A and z_B coefficient vectors (one value per gene) and design metadata.
    """
    design, names = _design(pb)
    w = pb["weight"]
    y = pb["expr"]                            # units x genes
    dw = design * w[:, None]
    xtx = design.T @ dw                       # P x P
    xty = dw.T @ y                            # P x genes
    beta = np.linalg.solve(xtx, xty)          # P x genes
    ia, ib = names.index("z_A"), names.index("z_B")
    return {"beta_A": beta[ia], "beta_B": beta[ib],
            "design_columns": names, "n_units": int(design.shape[0])}


# --------------------------------------------------------------------------- #
# Desired signatures + normalisation (plan §6.2.6, §6.2.11).
# --------------------------------------------------------------------------- #
def _zscore(v: np.ndarray) -> np.ndarray:
    sd = v.std()
    return (v - v.mean()) / sd if sd > 0 else np.zeros_like(v)


def desired_signatures(beta_a: np.ndarray, beta_b: np.ndarray) -> dict:
    """away = -beta_A, toward = +beta_B; combined = z(away) + z(toward)."""
    away = -beta_a
    toward = beta_b
    away_n = _zscore(away)
    toward_n = _zscore(toward)
    return {
        "away_from_A": away,
        "toward_b": toward,
        "away_from_A_norm": away_n,
        "toward_b_norm": toward_n,
        "combined_A_to_B": away_n + toward_n,
    }


def build_signature_frame(pb: dict, gene_ids: list[str]) -> dict:
    """Full signature build for one donor scope: betas -> normalised lanes."""
    fit = fit_betas(pb)
    sig = desired_signatures(fit["beta_A"], fit["beta_B"])
    sig["gene_ids"] = list(gene_ids)
    sig["design_columns"] = fit["design_columns"]
    sig["n_units"] = fit["n_units"]
    return sig
