"""The deterministic wrapper around the pinned upstream Perturb2State model.

Seed 42, ``positive=False``, and an l1 grid that is VALIDATED rather than assumed.

WHY ``positive=False`` IS REQUIRED, NOT A PREFERENCE
---------------------------------------------------
A negative coefficient is use of the INVERSE of the measured knockdown — OPPOSED, for a
CRISPRi/inhibition hypothesis. Constraining coefficients to be non-negative would convert
every opposed contributor into a zero, silently, and a table of "no evidence" would replace
a table of contrary evidence.

It is also what makes the two arms of a program an exact sign transform. The ElasticNet
objective is symmetric in ``b``:

    (1/2n)||y - Xb||^2 + a*l1*||b||_1 + (a/2)*(1-l1)*||b||^2

Substituting ``y -> -y`` and ``b -> -b`` leaves the loss and BOTH penalty terms unchanged,
so the minimiser is exactly ``-b*``, the CV-selected alpha is the same, and the
reconstruction metrics are sign-invariant. With ``positive=True`` the feasible set is not
symmetric and none of that holds.
"""
from __future__ import annotations

import time
from typing import Any

import numpy as np
import pandas as pd

from . import config
from . import deterministic_p2s as det


class ModelError(RuntimeError):
    """The model cannot be built or run as pinned. Refuse; never fall back."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


def validate_l1_grid(grid) -> tuple[float, ...]:
    """Every l1 ratio must lie in [0, 1]. Anything else is refused, not clipped.

    The l1 ratio is a MIXING fraction between the l1 and l2 penalties. A value outside
    [0, 1] is not a weaker or a stronger penalty — it is not a penalty at all, and the fit
    that comes back is a set of numbers nobody can interpret. Clipping would hide the fact
    that the grid somebody wrote down was not the grid that ran.
    """
    values = tuple(float(v) for v in grid)
    if not values:
        raise ModelError(
            "empty_l1_grid",
            "the l1 grid is empty, so there is no elastic-net mixing to select over")
    bad = [v for v in values
           if not (config.L1_RATIO_MIN <= v <= config.L1_RATIO_MAX)
           or v != v]
    if bad:
        raise ModelError(
            "l1_ratio_out_of_range",
            f"l1 ratio(s) {bad} are outside [{config.L1_RATIO_MIN}, "
            f"{config.L1_RATIO_MAX}]. The l1 ratio is a mixing fraction between the l1 and "
            "l2 penalties; a value outside the interval is not a penalty and its fit is "
            "not interpretable. Refused rather than clipped — a clipped grid is not the "
            "grid that was written down")
    return values


def validate_positive(positive: bool) -> bool:
    """``positive=True`` would convert every opposed contributor to a silent zero."""
    if positive:
        raise ModelError(
            "positive_constraint_would_erase_opposed_contributors",
            "positive=True constrains coefficients to be non-negative, which turns every "
            "OPPOSED contributor (a negative coefficient — use of the inverse of the "
            "measured knockdown) into a zero. This lane must keep opposed contributors "
            "opposed, so the constraint is refused")
    return False


def build(cfg: config.ModelConfig, *, seed: int = config.RANDOM_STATE):
    """Construct the pinned upstream model. Lazy import — the pin is checked separately."""
    validate_l1_grid(config.L1_RATIO_GRID)
    validate_positive(config.POSITIVE)
    try:
        from pert2state_model import Perturb2StateModel
    except ImportError as e:                                    # pragma: no cover
        raise ModelError(
            "upstream_model_not_importable",
            f"the pinned upstream model {config.UPSTREAM_REPOSITORY} is not importable "
            f"({e}). It is not optional and there is no fallback estimator: a different "
            "model producing numbers under this lane's name would be the defect this pin "
            "exists to prevent") from e

    return Perturb2StateModel(
        n_splits=config.N_SPLITS,
        n_repeats=config.N_REPEATS,
        random_state=seed,
        pca_transform=cfg.pca_transform,
        n_pcs=cfg.n_pcs if cfg.pca_transform else config.N_PCS,
        positive=config.POSITIVE,
        alpha=np.asarray(config.ALPHA_GRID, dtype=float),
        l1_ratio=np.asarray(validate_l1_grid(config.L1_RATIO_GRID), dtype=float),
    )


def run_one(x: pd.DataFrame, y: pd.Series, cfg: config.ModelConfig,
            model_id: str, *, seed: int = config.RANDOM_STATE) -> dict[str, Any]:
    """One fit. Returns the coefficients and the gene-CV reconstruction metrics.

    ``y`` is reindexed onto ``x``'s gene axis EXACTLY — never positionally. A positional
    alignment that happened to be right once is a reconstruction of the wrong signature the
    first time either side is reordered.
    """
    t0 = time.time()
    model = build(cfg, seed=seed)
    y = y.reindex(x.index)
    if y.isna().any():
        raise ModelError(
            "signature_does_not_cover_the_matrix_gene_axis",
            "the target signature has no value for some gene in the perturbation matrix; a "
            "missing readout gene stays missing and is never imputed to zero")

    # DETERMINISM via the narrow wrapper, NOT a global seed. `deterministic_p2s` injects the
    # model's own random_state into upstream TruncatedSVD (which omits it at commit 2c2e3095)
    # for the scope of the fit, rejects any conflicting explicit seed, and asserts every
    # fitted SVD carries the frozen seed. Seeding the global RNG would leave each SVD's
    # random_state=None and rely on mutable global state — repeatable only by luck of call
    # order. The wrapper requires pca_transform=True (upstream's pca=None path uses unscaled
    # X), which is why the PRIMARY config is the seeded D=60 SVD, not pca_off.
    wrapper_meta: dict[str, Any] = {}
    if cfg.pca_transform:
        wrapper_meta = det.fit_deterministic(model, x, y, model_id=model_id)
    else:
        # the pca_off SENSITIVITY path. It never touches get_prediction (we read get_coefs),
        # so the unscaled-X bug does not reach us; and it carries no SVD to seed.
        model.fit(x, y, model_id=model_id)
        wrapper_meta = {"wrapper": "none", "svd_override": "n/a_pca_off_sensitivity"}
    coefs = model.get_coefs()
    coefs.index = model.perturbation_names

    ev = model.eval
    return {
        "svd_determinism": wrapper_meta,
        "coefficients": pd.DataFrame({
            "coefficient": coefs["coef_mean"].astype(float),
            config.COEF_SEM_COLUMN: coefs["coef_sem"].astype(float),
        }, index=coefs.index),
        "reconstruction": {
            "reconstruction_gene_cv_test_r2_mean": float(ev["test_r2"].mean()),
            "reconstruction_gene_cv_test_r2_median": float(ev["test_r2"].median()),
            "reconstruction_gene_cv_test_spearman_mean": float(ev["test_spearman"].mean()),
            "reconstruction_gene_cv_train_r2_mean": float(ev["train_r2"].mean()),
            "n_folds": int(len(ev)),
            "cv_label": config.RECONSTRUCTION_CV_LABEL,
            "cv_semantics": config.RECONSTRUCTION_CV_SEMANTICS,
            "seconds": round(time.time() - t0, 1),
        },
    }


def model_block() -> dict[str, Any]:
    """The model configuration, as one hashable object. Ids, numbers and booleans."""
    return {
        "random_state": config.RANDOM_STATE,
        "positive": config.POSITIVE,
        "positive_semantics": (
            "a negative coefficient is use of the INVERSE of the measured knockdown, i.e. "
            "OPPOSED for an inhibition hypothesis; it is kept, never zeroed"),
        "alpha_grid": list(config.ALPHA_GRID),
        "l1_ratio_grid": list(validate_l1_grid(config.L1_RATIO_GRID)),
        "l1_ratio_range": [config.L1_RATIO_MIN, config.L1_RATIO_MAX],
        "n_splits": config.N_SPLITS,
        "n_repeats": config.N_REPEATS,
        "configs": [{"name": c.name, "pca_transform": c.pca_transform,
                     "n_pcs": (c.n_pcs if c.pca_transform else None)}
                    for c in config.CONFIGS],
        "cv_label": config.RECONSTRUCTION_CV_LABEL,
        "cv_semantics": config.RECONSTRUCTION_CV_SEMANTICS,
        "coefficient_semantics": config.COEFFICIENT_SEMANTICS,
        "coef_sem_column": config.COEF_SEM_COLUMN,
    }
