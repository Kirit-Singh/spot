"""Narrow deterministic wrapper for upstream Perturb2StateModel.

This module does not alter the upstream scientific model.  It supplies the
model's existing ``random_state`` to the one randomized estimator for which
upstream commit 2c2e3095 leaves ``random_state=None``: TruncatedSVD.  All other
TruncatedSVD defaults, scaling, folds, and ElasticNet settings remain upstream.
"""

from __future__ import annotations

import importlib
from contextlib import contextmanager
from typing import Any, Iterator
from unittest.mock import patch

import numpy as np

UPSTREAM_COMMIT = "2c2e30959ffafadecc6af5d4d7b5bde868ab5313"


@contextmanager
def seeded_upstream_svd(seed: int) -> Iterator[None]:
    """Give every upstream TruncatedSVD instance an explicit integer seed.

    The upstream module imports ``TruncatedSVD`` into its own namespace, so the
    patch is confined to that symbol and to this context.  A future upstream
    call that explicitly supplies a different seed fails closed.
    """

    if not isinstance(seed, int) or isinstance(seed, bool):
        raise TypeError("seed must be an integer")

    upstream_module = importlib.import_module(
        "pert2state_model.Perturb2StateModel"
    )
    upstream_svd = upstream_module.TruncatedSVD

    def deterministic_svd(*args: Any, **kwargs: Any):
        supplied = kwargs.get("random_state")
        if supplied is not None and supplied != seed:
            raise ValueError(
                f"upstream supplied TruncatedSVD random_state={supplied}; "
                f"wrapper requested {seed}"
            )
        kwargs["random_state"] = seed
        return upstream_svd(*args, **kwargs)

    with patch.object(upstream_module, "TruncatedSVD", deterministic_svd):
        yield


def fit_deterministic(model, X, y, *, model_id: str, **fit_kwargs: Any) -> dict:
    """Fit upstream Perturb2StateModel with the missing SVD seed supplied."""

    seed = model.random_state
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise TypeError("model.random_state must be an integer")
    if not model.pca_transform:
        raise ValueError(
            "pca_transform=True is required: upstream get_prediction uses "
            "unscaled X when PCA is disabled at commit 2c2e3095"
        )
    if model.alpha is None or model.l1_ratio is None:
        raise ValueError(
            "alpha and l1_ratio must be explicit; upstream defaults are not a "
            "frozen production configuration"
        )
    alpha = np.atleast_1d(model.alpha).astype(float)
    l1_ratio = np.atleast_1d(model.l1_ratio).astype(float)
    if not np.isfinite(alpha).all() or np.any(alpha <= 0):
        raise ValueError("every alpha must be finite and > 0")
    if not np.isfinite(l1_ratio).all() or np.any(l1_ratio < 0) or np.any(l1_ratio > 1):
        raise ValueError("every l1_ratio must be finite and within [0, 1]")
    with seeded_upstream_svd(seed):
        model.fit(X, y, model_id=model_id, **fit_kwargs)

    fitted_pcas = [pca for pca in model.pcas if pca is not None]
    if model.pca_transform and not fitted_pcas:
        raise RuntimeError("PCA/SVD requested but no fitted TruncatedSVD exists")
    if any(pca.random_state != seed for pca in fitted_pcas):
        raise RuntimeError("not every fitted TruncatedSVD carries the frozen seed")

    svd_configs = {
        (
            pca.__class__.__name__,
            pca.algorithm,
            int(pca.n_components),
            int(pca.n_iter),
            int(pca.n_oversamples),
            pca.power_iteration_normalizer,
            int(pca.random_state),
        )
        for pca in fitted_pcas
    }
    if len(svd_configs) > 1:
        raise RuntimeError(f"inconsistent SVD configurations: {svd_configs}")

    return {
        "wrapper": "spot.p2s_explicit_svd_seed.v1",
        "upstream_commit": UPSTREAM_COMMIT,
        "model_random_state": seed,
        "svd_override": "random_state only",
        "svd_scope": "same explicit seed for each outer fold",
        "svd_config": list(next(iter(svd_configs))) if svd_configs else None,
        "alpha_grid": alpha.tolist(),
        "l1_ratio_grid": l1_ratio.tolist(),
    }


def assert_secondary_arm_schema(columns) -> None:
    """Reject combined objectives in the secondary lane's serialized fields."""

    banned = ("combined", "balanced", "weighted", "overall_rank")
    bad = [str(c) for c in columns if any(k in str(c).lower() for k in banned)]
    if bad:
        raise ValueError(f"secondary lane contains forbidden combined fields: {bad}")
