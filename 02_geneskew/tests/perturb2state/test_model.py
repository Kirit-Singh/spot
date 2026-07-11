"""Perturb2State model behaviour tests (plan §6.4-§6.6, §6.9).

Require the pinned upstream package; skipped where it is unavailable.
"""
import numpy as np
import pandas as pd
import pytest

pytest.importorskip("pert2state_model")

from perturb2state import config as cfg          # noqa: E402
from perturb2state import model_runner as MR     # noqa: E402

CFG = cfg.CONFIGS[0]                              # pca_off


def _known_target(X, contributors):
    """y = sum_j w_j * X[:, j] (+ tiny noise); returns Series aligned to X.index."""
    y = np.zeros(X.shape[0])
    for col, w in contributors.items():
        y += w * X[col].to_numpy()
    y += 0.01 * np.random.default_rng(1).normal(size=X.shape[0])
    return pd.Series(y, index=X.index)


def test_deterministic_under_fixed_seed(synthetic_matrix):
    X, _, _ = synthetic_matrix
    y = _known_target(X, {"ENSGT03": 2.0})
    r1 = MR.run_one(X, y, CFG, "m")["coefs"]["coef_mean"]
    r2 = MR.run_one(X, y, CFG, "m")["coefs"]["coef_mean"]
    assert np.allclose(r1.to_numpy(), r2.to_numpy())


def test_target_order_invariance(synthetic_matrix):
    X, _, perts = synthetic_matrix
    y = _known_target(X, {"ENSGT03": 2.0, "ENSGT05": 1.5})
    base = MR.run_one(X, y, CFG, "m")["coefs"]["coef_mean"]
    permuted = list(reversed(perts))
    c2 = MR.run_one(X[permuted], y, CFG, "m")["coefs"]["coef_mean"]
    # per-target coefficient is invariant to column order up to numerical noise
    # (StandardScaler + coordinate-descent ordering differ only at ~1e-6)
    for t in perts:
        assert abs(float(base[t]) - float(c2[t])) < 1e-4


def test_synthetic_contributor_recovered(synthetic_matrix):
    X, _, _ = synthetic_matrix
    y = _known_target(X, {"ENSGT03": 2.0, "ENSGT05": 1.5})
    coefs = MR.run_one(X, y, CFG, "m")["coefs"]["coef_mean"]
    top2 = coefs.abs().sort_values(ascending=False).index[:2].tolist()
    assert set(top2) == {"ENSGT03", "ENSGT05"}
    assert coefs["ENSGT03"] > 0 and coefs["ENSGT05"] > 0


def test_reversed_contributor_gets_negative_coefficient(synthetic_matrix):
    X, _, _ = synthetic_matrix
    y = _known_target(X, {"ENSGT03": -2.0})       # inverse of the measured signature
    coefs = MR.run_one(X, y, CFG, "m")["coefs"]["coef_mean"]
    assert coefs["ENSGT03"] < 0                    # opposed -> negative coefficient


def test_shuffled_signature_loses_reconstruction(synthetic_matrix):
    X, _, _ = synthetic_matrix
    y = _known_target(X, {"ENSGT03": 2.0, "ENSGT05": 1.5})
    true_r2 = MR.run_one(X, y, CFG, "m")["recon"]["reconstruction_gene_cv_test_r2_mean"]
    y_shuf = pd.Series(np.random.default_rng(7).permutation(y.to_numpy()), index=y.index)
    shuf_r2 = MR.run_one(X, y_shuf, CFG, "m")["recon"]["reconstruction_gene_cv_test_r2_mean"]
    assert true_r2 - shuf_r2 > 0.2                 # shuffling destroys reconstruction


def test_coef_records_carry_fit_variation_not_pvalue(synthetic_matrix):
    X, _, _ = synthetic_matrix
    y = _known_target(X, {"ENSGT03": 2.0})
    res = MR.run_one(X, y, CFG, "m")
    recs = MR.coef_records(res["coefs"], {"matrix": "main", "layer": "zscore",
                                          "config": "pca_off", "scope": "all_donor"})
    cols = set(recs[0].keys())
    assert "coef_fit_variation" in cols
    assert not ({"p_value", "pvalue", "coef_sem"} & cols)  # SEM never a p-value column


def test_reconstruction_cv_label_is_gene_cv(synthetic_matrix):
    X, _, _ = synthetic_matrix
    y = _known_target(X, {"ENSGT03": 2.0})
    recon = MR.run_one(X, y, CFG, "m")["recon"]
    assert recon["cv_label"] == "reconstruction_gene_cv"
    assert "donor" not in recon["cv_label"] and "external" not in recon["cv_label"]
