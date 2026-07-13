"""Broad target-signature construction tests (plan §6.2, §6.9)."""
import numpy as np
from perturb2state import signature as S


def test_program_score_reproduces_panel_minus_control():
    # 2 cells, 4 genes; panel=[0,1], control=[2,3]
    expr = np.array([[2.0, 4.0, 1.0, 1.0], [0.0, 0.0, 2.0, 2.0]])
    s = S.program_score(expr, [0, 1], [2, 3])
    assert np.allclose(s, [3.0 - 1.0, 0.0 - 2.0])


def test_within_donor_z_is_per_donor():
    vals = np.array([1.0, 3.0, 10.0, 30.0])
    donors = np.array(["A", "A", "B", "B"])
    z = S.within_donor_z(vals, donors)
    # each donor standardised independently -> both donors give [-1, +1]
    assert np.allclose(z, [-1.0, 1.0, -1.0, 1.0])


def test_pseudobulk_bins_are_donor_stratified(rng):
    n = 400
    donors = np.array(["A"] * 200 + ["B"] * 200)
    z_a = rng.normal(size=n)
    z_b = rng.normal(size=n)
    act = rng.normal(size=n)
    expr = rng.normal(size=(n, 5))
    pb = S.build_pseudobulk(z_a, z_b, act, donors, expr, n_bins=5)
    # units carry a donor label from the input donors only
    assert set(pb["donor"].tolist()) <= {"A", "B"}
    assert pb["expr"].shape[1] == 5
    assert pb["weight"].sum() == n


def test_known_direction_recovered_in_betas(rng):
    """A gene whose expression tracks +z_A must get positive beta_A."""
    n = 2000
    donors = np.array(["A"] * 1000 + ["B"] * 1000)
    z_a = rng.normal(size=n)
    z_b = rng.normal(size=n)
    act = rng.normal(size=n)
    # gene 0 = +z_A ; gene 1 = +z_B ; gene 2 = noise
    expr = np.column_stack([
        3.0 * z_a + 0.01 * rng.normal(size=n),
        2.0 * z_b + 0.01 * rng.normal(size=n),
        rng.normal(size=n),
    ])
    pb = S.build_pseudobulk(z_a, z_b, act, donors, expr, n_bins=8)
    fit = S.fit_betas(pb)
    assert fit["beta_A"][0] > 1.0 and abs(fit["beta_A"][1]) < 0.5
    assert fit["beta_B"][1] > 0.5 and abs(fit["beta_B"][0]) < 0.5


def test_reversed_contributor_flips_desired_sign():
    beta_a = np.array([1.0, -2.0])
    beta_b = np.array([0.5, 0.5])
    sig = S.desired_signatures(beta_a, beta_b)
    # desired_away_A = -beta_A  -> sign flip vs beta_A
    assert np.allclose(sig["away_from_A"], [-1.0, 2.0])
    assert np.allclose(sig["toward_B"], [0.5, 0.5])


def test_away_toward_normalised_separately_then_summed():
    beta_a = np.array([1.0, 2.0, 3.0])
    beta_b = np.array([-1.0, 0.0, 1.0])
    sig = S.desired_signatures(beta_a, beta_b)
    # each normalised lane is mean 0 / unit sd
    assert abs(sig["away_from_A_norm"].mean()) < 1e-9
    assert abs(sig["toward_B_norm"].std() - 1.0) < 1e-9
    assert np.allclose(sig["combined_A_to_B"],
                       sig["away_from_A_norm"] + sig["toward_B_norm"])
