"""Tests for the pure QC + guide-assignment logic (the manifest thresholds)."""

import numpy as np
from spot_pipeline import assign_guides, cell_qc_mask, mad_low_bound


def test_cell_qc_mask_applies_floors_and_mito() -> None:
    genes = np.array([100, 300, 400])  # cell0 below min_genes
    counts = np.array([500, 2000, 5000])  # cell0 below min_counts
    mito = np.array([5.0, 8.0, 30.0])  # cell2 above max mito
    mask = cell_qc_mask(
        genes, counts, mito, min_genes=200, min_counts=1000, max_pct_mito=15.0, mad_nmads=5.0
    )
    assert mask.tolist() == [False, True, False]


def test_assign_guides_threshold_and_multiplet() -> None:
    mat = np.array([[5, 0, 0], [0, 4, 3], [1, 0, 0]])  # c0->gA; c1 multiplet; c2 below floor
    assigned, multiplet = assign_guides(mat, ["gA", "gB", "gC"], min_umi=3)
    assert assigned == ["gA", "gB", "unassigned"]
    assert multiplet.tolist() == [False, True, False]


def test_mad_low_bound_below_median() -> None:
    assert mad_low_bound(np.array([1.0, 1.0, 1.0, 1.0, 10.0]), 5.0) <= 1.0
