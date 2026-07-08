"""Pure QC + guide-assignment logic (numpy only).

The cellqc stage imports these so the manifest thresholds are enforced by tested
code, not re-implemented per stage. No scanpy/anndata here -- keeps it CI-testable.
"""

from __future__ import annotations

import numpy as np


def mad_low_bound(values: np.ndarray, nmads: float) -> float:
    """Lower MAD-based outlier bound: median - nmads * MAD (MAD floored at 1.0)."""
    med = float(np.median(values))
    mad = float(np.median(np.abs(values - med))) or 1.0
    return med - nmads * mad


def cell_qc_mask(
    genes: np.ndarray,
    counts: np.ndarray,
    mito: np.ndarray,
    *,
    min_genes: int,
    min_counts: int,
    max_pct_mito: float,
    mad_nmads: float,
) -> np.ndarray:
    """Boolean keep-mask: fixed floors AND (adaptive) MAD lower bound on log counts."""
    log_counts = np.log1p(np.asarray(counts, dtype=float))
    return (
        (np.asarray(genes) >= min_genes)
        & (np.asarray(counts) >= min_counts)
        & (np.asarray(mito) <= max_pct_mito)
        & (log_counts >= mad_low_bound(log_counts, mad_nmads))
    )


def assign_guides(
    matrix: np.ndarray, guide_names: list[str], min_umi: int
) -> tuple[list[str], np.ndarray]:
    """Assign each cell its top guide over the ambient floor; flag low-MOI multiplets.

    Returns (per-cell guide name or 'unassigned', boolean multiplet mask [>=2 over floor]).
    """
    matrix = np.asarray(matrix)
    over = matrix >= min_umi
    n_over = over.sum(axis=1)
    top_idx = matrix.argmax(axis=1)
    names = np.asarray(guide_names)
    assigned = [
        str(names[i]) if n >= 1 else "unassigned" for i, n in zip(top_idx, n_over, strict=True)
    ]
    return assigned, n_over >= 2
