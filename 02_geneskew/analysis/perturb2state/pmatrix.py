"""Masked perturbation matrix construction (plan §6.3).

Builds a genes x eligible-perturbations matrix from a DE effect layer. For every
perturbation column the SAME intended-target / off-target mask used by the direct
Stage-2 primary screen is applied: masked coordinates are replaced with the
neutral value 0 BEFORE model scaling (§6.3). Pure numpy/pandas so masking is
unit-testable.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import MASK_NEUTRAL_VALUE


def build_masked_X(effect_by_target: dict[str, np.ndarray],
                   de_gene_ids: list[str],
                   universe_gene_ids: list[str],
                   target_order: list[str],
                   mask_by_target: dict[str, set]) -> tuple[pd.DataFrame, dict]:
    """Assemble the masked X (genes x perturbations).

    Args:
        effect_by_target: target Ensembl -> dense effect vector over the FULL
            ordered DE gene axis (``de_gene_ids``). Joined by stable id.
        de_gene_ids: the full ordered DE gene axis for ``effect_by_target``.
        universe_gene_ids: ordered readout universe (rows of X == index of y).
        target_order: ordered eligible target Ensembl ids (columns of X).
        mask_by_target: target Ensembl -> set of masked gene Ensembl ids.

    Returns (X DataFrame [genes x targets], coverage dict per target).
    """
    de_index = {g: i for i, g in enumerate(de_gene_ids)}
    # Keep only universe genes present on this matrix's gene axis (guide/donor-pair
    # matrices may carry a subset); preserve the universe ordering.
    kept = [g for g in universe_gene_ids if g in de_index]
    uni_rows = [de_index[g] for g in kept]                   # DE row per kept gene
    uni_pos = {g: k for k, g in enumerate(kept)}
    universe_gene_ids = kept
    n_genes = len(kept)

    cols = {}
    coverage = {}
    for t in target_order:
        vec = effect_by_target.get(t)                        # stable-id join
        if vec is None:
            continue
        col = np.asarray(vec, dtype=np.float64)[uni_rows].copy()
        masked = mask_by_target.get(t, set())
        n_masked = 0
        for g in masked:
            k = uni_pos.get(g)
            if k is not None:
                col[k] = MASK_NEUTRAL_VALUE
                n_masked += 1
        cols[t] = col
        coverage[t] = {
            "n_genes_universe": n_genes,
            "n_masked_in_universe": int(n_masked),
            "n_retained": int(n_genes - n_masked),
        }
    X = pd.DataFrame(cols, index=universe_gene_ids)
    X = X[[t for t in target_order if t in cols]]            # deterministic column order
    return X, coverage


def mask_sets_from_parquet(masks_df: pd.DataFrame) -> dict[str, set]:
    """Per-target masked-gene sets from the direct screen's ``masks.parquet``.

    Only rows whose masked gene is in the DE gene universe contribute (the
    direct screen already flagged this via ``in_gene_universe``).
    """
    out: dict[str, set] = {}
    sub = masks_df[masks_df["in_gene_universe"]]
    for t, grp in sub.groupby("target_ensembl"):
        out[str(t)] = set(grp["masked_gene_ensembl"].astype(str).tolist())
    return out
