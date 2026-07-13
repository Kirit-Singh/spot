"""The per-program base signature: reusable by construction, and refused when unidentified."""
from __future__ import annotations

import numpy as np
import pytest
from p2s_arms import config, signature, universe

DONORS = np.asarray(["D1"] * 100 + ["D2"] * 100 + ["D3"] * 100 + ["D4"] * 100)


def cells(seed=1, n_genes=40):
    rng = np.random.default_rng(seed)
    n = len(DONORS)
    z_p = rng.normal(size=n)
    z_act = rng.normal(size=n)
    loading = np.zeros(n_genes)
    loading[:10] = 2.0
    act_loading = np.zeros(n_genes)
    act_loading[10:20] = 2.0
    expr = (np.outer(z_p, loading) + np.outer(z_act, act_loading)
            + rng.normal(0, 0.2, size=(n, n_genes)))
    return z_p, z_act, expr


def test_within_donor_z_standardises_inside_each_donor():
    v = np.asarray([1.0, 3.0, 10.0, 30.0])
    d = np.asarray(["A", "A", "B", "B"])
    assert list(signature.within_donor_z(v, d)) == [-1.0, 1.0, -1.0, 1.0]


def test_a_donor_with_no_spread_gives_zeros_not_nans():
    v = np.asarray([5.0, 5.0])
    out = signature.within_donor_z(v, np.asarray(["A", "A"]))
    assert list(out) == [0.0, 0.0] and not np.isnan(out).any()


def test_the_pseudobulk_grid_is_2D_on_the_axes_that_are_REGRESSED_on():
    """Binning on z_program alone would average activation away inside each bin."""
    z_p, z_act, expr = cells()
    pb = signature.build_pseudobulk(z_program=z_p, activation=z_act, donors=DONORS,
                                    expr=expr, n_bins=5)
    assert pb["binning_axes"] == ["z_program", "activation"]
    # 4 donors x up to 5x5 cells of the grid; the weights account for every cell
    assert pb["weights"].sum() == len(DONORS)
    assert pb["n_units"] > len(set(DONORS.tolist()))


def test_an_empty_grid_cell_does_not_become_a_zero_row():
    """An absent unit is ABSENT. A zero row would be a pseudobulk nobody measured."""
    z_p, z_act, expr = cells()
    pb = signature.build_pseudobulk(z_program=z_p, activation=z_act, donors=DONORS,
                                    expr=expr, n_bins=10)
    assert pb["n_units"] <= 4 * 10 * 10
    assert (pb["weights"] > 0).all()


def test_the_design_has_K_minus_1_donor_dummies_not_K():
    """A full set of dummies plus an intercept is rank-deficient."""
    z_p, z_act, expr = cells()
    pb = signature.build_pseudobulk(z_program=z_p, activation=z_act, donors=DONORS,
                                    expr=expr, n_bins=5)
    _d, names = signature.design(pb)
    donor_cols = [n for n in names if n.startswith("donor_")]
    assert len(donor_cols) == len(set(DONORS.tolist())) - 1
    assert names[:3] == ["intercept", "z_program", "activation"]


def test_the_fit_recovers_the_planted_program_loading():
    z_p, z_act, expr = cells()
    got = signature.base_signature(z_program=z_p, activation=z_act, donors=DONORS,
                                   expr=expr, n_bins=5)
    beta = got["beta_program"]
    # genes 0-9 carry the program; genes 10-19 carry activation only
    assert beta[:10].mean() > 1.0
    assert abs(beta[10:20].mean()) < 0.5
    assert got["solver"] == config.SOLVER


def test_the_signature_is_standardised_across_the_readout_universe():
    z_p, z_act, expr = cells()
    sig = signature.base_signature(z_program=z_p, activation=z_act, donors=DONORS,
                                   expr=expr, n_bins=5)["signature"]
    assert abs(sig.mean()) < 1e-9
    assert abs(sig.std() - 1.0) < 1e-9


def test_a_RANK_DEFICIENT_design_is_refused_not_fitted():
    """A number returned here would be an arbitrary point on a ridge of equally good fits."""
    n = 40
    donors = np.asarray(["D1"] * n)
    z = np.linspace(-1, 1, n)
    # activation is an exact copy of z_program: the two columns are collinear
    with pytest.raises(signature.SignatureError) as e:
        signature.base_signature(z_program=z, activation=z, donors=donors,
                                 expr=np.random.default_rng(0).normal(size=(n, 8)),
                                 n_bins=6)
    assert e.value.reason in ("design_is_rank_deficient", "design_is_underdetermined")


def test_an_underdetermined_design_is_refused():
    """2 donors, 1 bin => 2 pseudobulk units for 4 parameters.

    A fit with no residual degrees of freedom reproduces its inputs exactly and has learned
    nothing — so it is refused rather than returned.
    """
    n = 8
    donors = np.asarray(["D1"] * 4 + ["D2"] * 4)
    rng = np.random.default_rng(0)
    with pytest.raises(signature.SignatureError) as e:
        signature.base_signature(z_program=rng.normal(size=n),
                                 activation=rng.normal(size=n), donors=donors,
                                 expr=rng.normal(size=(n, 5)), n_bins=1)
    assert e.value.reason in ("design_is_underdetermined", "design_is_rank_deficient")


def test_a_cell_axis_disagreement_is_refused():
    with pytest.raises(signature.SignatureError) as e:
        signature.build_pseudobulk(z_program=np.zeros(5), activation=np.zeros(4),
                                   donors=np.asarray(["A"] * 5),
                                   expr=np.zeros((5, 3)), n_bins=2)
    assert e.value.reason == "cell_axis_disagreement"


# --------------------------------------------------------------------------- #
# The readout universe.
# --------------------------------------------------------------------------- #
def test_panel_and_control_genes_may_never_enter_the_readout():
    """Otherwise the model reconstructs the program from the genes it was DEFINED by."""
    uni = universe.build(effect_gene_ids=["G1", "G2", "G3", "G4"],
                         excluded_program_genes=["G1"])
    assert uni["gene_ids"] == ["G2", "G3", "G4"]     # only panel/control G1 removed
    assert uni["n_panel_control_excluded"] == 1
    universe.assert_clean(uni, ["G1"])


def test_perturbation_target_genes_are_NOT_subtracted_globally():
    """~11k targets vs 10,282 genes: global subtraction would delete most of the assay.

    The self-gene is neutralised PER COLUMN by the Direct mask, not removed from the universe.
    """
    uni = universe.build(effect_gene_ids=["G1", "G2", "G3", "G4"],
                         excluded_program_genes=[])
    assert uni["gene_ids"] == ["G1", "G2", "G3", "G4"]   # nothing target-subtracted
    assert uni["target_genes_subtracted_globally"] is False
    assert uni["self_gene_neutralised_per_column_by_direct_mask"] is True


def test_a_leaked_panel_gene_is_caught():
    uni = {"gene_ids": ["G1", "G3"]}
    with pytest.raises(universe.UniverseError) as e:
        universe.assert_clean(uni, ["G1"])
    assert e.value.reason == "panel_or_control_gene_leaked_into_the_readout"


def test_an_empty_readout_universe_is_refused():
    with pytest.raises(universe.UniverseError) as e:
        universe.build(effect_gene_ids=["G1"], excluded_program_genes=["G1"])
    assert e.value.reason == "readout_universe_is_empty"


def test_the_universe_hash_is_order_invariant():
    a = universe.build(effect_gene_ids=["G3", "G1", "G2"], excluded_program_genes=[])
    b = universe.build(effect_gene_ids=["G1", "G2", "G3"], excluded_program_genes=[])
    assert a["gene_universe_sha256"] == b["gene_universe_sha256"]
