"""Direct-formula unit tests + gene-universe intersection (plan §13)."""
import numpy as np
import pytest

from direct import projection as proj
from direct.projection import OK, INSUFFICIENT_AXIS_COVERAGE


def test_direct_formula_hand_computed(gene_index):
    # effect over g0..g4
    row = np.array([2.0, 4.0, 1.0, 0.0, 2.0])
    # panel g0,g1 mean = 3.0 ; control g2,g3,g4 mean = 1.0 ; delta = 2.0
    out = proj.program_delta(row, ["ENSG0", "ENSG1"], ["ENSG2", "ENSG3", "ENSG4"],
                             gene_index, set(), min_panel=1, min_control=1)
    assert out["status"] == OK
    assert out["panel_mean"] == pytest.approx(3.0)
    assert out["control_mean"] == pytest.approx(1.0)
    assert out["delta"] == pytest.approx(2.0)


def test_mask_recomputes_means_separately(gene_index):
    # Masking g1 out of the panel must recompute the panel mean over g0 alone;
    # control mean is recomputed independently (no mixed-vector renormalisation).
    row = np.array([2.0, 4.0, 1.0, 0.0, 2.0])
    out = proj.program_delta(row, ["ENSG0", "ENSG1"], ["ENSG2", "ENSG3", "ENSG4"],
                             gene_index, {"ENSG1"}, min_panel=1, min_control=1)
    assert out["panel_mean"] == pytest.approx(2.0)   # g0 only
    assert out["control_mean"] == pytest.approx(1.0)  # unchanged
    assert out["delta"] == pytest.approx(1.0)
    assert out["n_panel_surviving"] == 1


def test_gene_universe_intersection(gene_index):
    # A panel gene absent from the universe is silently dropped from the mean;
    # only present genes contribute.
    row = np.array([2.0, 4.0, 1.0, 0.0, 2.0])
    out = proj.program_delta(row, ["ENSG0", "ENSG1", "ENSG_ABSENT"],
                             ["ENSG2", "ENSG3", "ENSG4", "ENSG_MISSING"],
                             gene_index, set(), min_panel=1, min_control=1)
    assert out["n_panel_surviving"] == 2
    assert out["n_control_surviving"] == 3
    assert out["panel_mean"] == pytest.approx(3.0)


def test_insufficient_axis_coverage(gene_index):
    row = np.zeros(5)
    out = proj.program_delta(row, ["ENSG0"], ["ENSG2", "ENSG3"], gene_index,
                             {"ENSG0"}, min_panel=1, min_control=1)
    assert out["status"] == INSUFFICIENT_AXIS_COVERAGE
    assert out["delta"] is None


def test_axis_scores_and_direction():
    ax = proj.axis_scores(delta_a=-1.0, delta_b=2.0, sign_a=1, sign_b=1)
    assert ax["away_from_A"] == pytest.approx(1.0)   # -sA*delta_A
    assert ax["toward_b"] == pytest.approx(2.0)      # sB*delta_B
    assert ax["balanced_skew"] == pytest.approx(1.5)
    assert proj.direction_class(1.0, 2.0) == "aligned_both"
    assert proj.direction_class(-1.0, 2.0) == "aligned_toward_b_only"
    assert proj.direction_class(-1.0, -2.0) == "opposed"


def test_low_pole_sign_inversion():
    # A low pole (sign -1): away_from_A = -(-1)*delta_A = +delta_A
    ax = proj.axis_scores(delta_a=1.0, delta_b=1.0, sign_a=-1, sign_b=1)
    assert ax["away_from_A"] == pytest.approx(1.0)
