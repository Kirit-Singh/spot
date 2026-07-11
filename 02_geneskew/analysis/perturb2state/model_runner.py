"""Thin wrapper around the pinned upstream ``Perturb2StateModel`` (plan §6.4-§6.5).

The package's built-in cross-validation splits GENES; its metrics are therefore
labelled ``reconstruction_gene_cv`` and are NEVER donor CV, guide validation,
perturbation holdout, or external validation (plan §6.5). ``coef_sem`` is
variation across overlapping fits, never inferential uncertainty (§6.5).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import config


def _make_model(cfg: config.ModelConfig):
    from pert2state_model import Perturb2StateModel
    return Perturb2StateModel(
        n_splits=config.N_SPLITS,
        n_repeats=config.N_REPEATS,
        random_state=config.RANDOM_STATE,
        pca_transform=cfg.pca_transform,
        n_pcs=cfg.n_pcs if cfg.pca_transform else 50,
        positive=config.POSITIVE,                       # False (required, §6.4)
        alpha=np.asarray(config.EN_ALPHAS, dtype=float),
        l1_ratio=np.asarray(config.EN_L1_RATIOS, dtype=float),
    )


def run_one(X: pd.DataFrame, y: pd.Series, cfg: config.ModelConfig,
            model_id: str) -> dict:
    """Fit one Perturb2State model and extract coefficients + recon metrics.

    Returns a dict with:
      - ``coefs``: DataFrame index=target, columns [coef_mean, coef_sem]
      - ``recon``: reconstruction_gene_cv summary (mean/median test r2/spearman)
    """
    y = y.reindex(X.index)                              # exact ordered alignment
    model = _make_model(cfg)
    model.fit(X, y, model_id=model_id)
    coefs = model.get_coefs().copy()
    coefs.index = list(model.perturbation_names)
    ev = model.eval
    recon = {
        "reconstruction_gene_cv_test_r2_mean": float(ev["test_r2"].mean()),
        "reconstruction_gene_cv_test_r2_median": float(ev["test_r2"].median()),
        "reconstruction_gene_cv_test_spearman_mean": float(ev["test_spearman"].mean()),
        "reconstruction_gene_cv_train_r2_mean": float(ev["train_r2"].mean()),
        "reconstruction_gene_cv_n_folds": int(ev.shape[0]),
        "cv_label": config.RECONSTRUCTION_CV_LABEL,
        "cv_semantics": "splits genes; reconstruction of the desired signature, "
                        "not donor/guide/perturbation holdout or external validation",
    }
    return {"coefs": coefs, "recon": recon}


def coef_records(coefs: pd.DataFrame, run_meta: dict) -> list[dict]:
    """Flatten a run's coefficients into per-target rows for coefficients.parquet."""
    rows = []
    for target, r in coefs.iterrows():
        cm = float(r["coef_mean"])
        rows.append({
            **run_meta,
            "target_ensembl": str(target),
            "coefficient": cm,
            # coef_sem is fit-variation, NOT a p-value / standard error of inference
            "coef_fit_variation": float(r["coef_sem"]),
            "nonzero": abs(cm) > config.NONZERO_TOL,
            "sign": int(np.sign(cm)) if abs(cm) > config.NONZERO_TOL else 0,
        })
    return rows
