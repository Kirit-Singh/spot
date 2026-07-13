"""The PER-PROGRAM base signature. One program, one context, no pair anywhere.

    mean_expr_g ~ 1 + z_program + activation + donor(K-1 dummies)
    weight = n_cells_unit
    solved by lstsq on sqrt(W)D and sqrt(W)Y

THE PAIR BINDING THIS REMOVES
-----------------------------
Legacy fit BOTH programs in ONE model — ``~ 1 + z_A + z_B + activation + donor`` — and read
the away/toward signatures off ``z_A``/``z_B``. So a program's fitted beta depended on WHICH
OTHER PROGRAM shared the design matrix. The same reusable ``arm_key`` would then carry one
value when the treg/th1 pair asked for it and another when treg/th17 did, with both cached
under the same name and served interchangeably. Nothing in the numbers would look wrong.

Fitting one program at a time makes the arm reusable by construction, which is the whole
point of the migration.

WHY THE PSEUDOBULK GRID IS 2-D
------------------------------
It bins on exactly the axes that are REGRESSED on — here ``(z_program, activation)``.
Legacy binned on ``(z_A, z_B)`` for the same reason: those were its two regressors.

Binning on ``z_program`` alone would collapse activation to a near-constant inside each bin
and strip the covariate of the leverage it exists to have. The activation confound would
then leak straight back into ``beta_program`` — and it would leak as a plausible number.

WHY LSTSQ AND NOT THE NORMAL EQUATIONS
--------------------------------------
``D'WD`` squares the condition number, and a rank-deficient donor block comes back from it
as numbers rather than as a failure. A least-squares solve on the whitened system reports
its own rank, so a degenerate design is a refusal instead of a signature.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from . import config


class SignatureError(ValueError):
    """The base signature cannot be fitted. Refuse; never return a plausible one."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


def within_donor_z(values: np.ndarray, donors: np.ndarray) -> np.ndarray:
    """Standardise within each donor. A donor with no spread contributes zeros, not NaNs."""
    values = np.asarray(values, dtype=float)
    out = np.zeros_like(values)
    for d in np.unique(donors):
        m = donors == d
        v = values[m]
        sd = v.std()
        out[m] = (v - v.mean()) / sd if sd > 0 else 0.0
    return out


def quantile_bin(x: np.ndarray, n_bins: int) -> np.ndarray:
    """Rank-based quantile bins in ``[0, n_bins)``. Ties do not create empty edge bins."""
    x = np.asarray(x, dtype=float)
    n = x.shape[0]
    if n == 0:
        return np.zeros(0, dtype=int)
    order = np.argsort(x, kind="stable")
    ranks = np.empty(n, dtype=float)
    ranks[order] = np.arange(n, dtype=float)
    b = np.floor(ranks / n * n_bins).astype(int)
    return np.clip(b, 0, n_bins - 1)


def build_pseudobulk(*, z_program: np.ndarray, activation: np.ndarray, donors: np.ndarray,
                     expr: np.ndarray, n_bins: int = config.N_SCORE_BINS) -> dict[str, Any]:
    """Donor-stratified 2-D quantile pseudobulk on ``(z_program, activation)``.

    ``expr`` is cells x genes. Each unit is the WEIGHTED-MEAN cell of one (donor, z bin,
    activation bin) cell, and its weight is the number of cells in it. Empty cells of the
    grid simply do not become units — an absent unit is absent, never a zero row.
    """
    z_program = np.asarray(z_program, dtype=float)
    activation = np.asarray(activation, dtype=float)
    donors = np.asarray(donors)
    expr = np.asarray(expr, dtype=float)

    if not (z_program.shape[0] == activation.shape[0] == donors.shape[0]
            == expr.shape[0]):
        raise SignatureError(
            "cell_axis_disagreement",
            "z_program, activation, donors and expr must agree on the cell axis; they are "
            f"{z_program.shape[0]}, {activation.shape[0]}, {donors.shape[0]} and "
            f"{expr.shape[0]}")

    u_z, u_act, u_donor, u_expr, u_w = [], [], [], [], []
    for d in np.unique(donors):
        dm = donors == d
        bz = quantile_bin(z_program[dm], n_bins)
        ba = quantile_bin(activation[dm], n_bins)
        key = bz * n_bins + ba                       # the 2-D grid, flattened
        zd, ad, ed = z_program[dm], activation[dm], expr[dm]
        for k in np.unique(key):
            km = key == k
            n_cells = int(km.sum())
            u_z.append(float(zd[km].mean()))
            u_act.append(float(ad[km].mean()))
            u_donor.append(d)
            u_expr.append(ed[km].mean(axis=0))
            u_w.append(float(n_cells))

    if not u_z:
        raise SignatureError(
            "no_pseudobulk_units",
            "the 2-D grid produced no units, so there is nothing to regress on")

    return {
        "z_program": np.asarray(u_z, dtype=float),
        "activation": np.asarray(u_act, dtype=float),
        "donors": np.asarray(u_donor),
        "expr": np.vstack(u_expr),                    # units x genes
        "weights": np.asarray(u_w, dtype=float),      # n_cells per unit
        "n_units": len(u_z),
        "n_bins": int(n_bins),
        "binning_axes": list(config.BINNING_AXES),
    }


def design(pb: dict[str, Any]) -> tuple[np.ndarray, list[str]]:
    """``[1, z_program, activation, donor(K-1)]``. The reference donor is the first, sorted.

    K-1 dummies, not K: a full set plus an intercept is rank-deficient, and a solver handed
    a rank-deficient design does not always say so.
    """
    n = pb["n_units"]
    donors = pb["donors"]
    levels = sorted(set(donors.tolist()))
    cols = [np.ones(n), pb["z_program"], pb["activation"]]
    names = ["intercept", "z_program", "activation"]
    for lv in levels[1:]:                             # K-1: the first level is the reference
        cols.append((donors == lv).astype(float))
        names.append(f"donor_{lv}")
    return np.column_stack(cols), names


def fit_base_signature(pb: dict[str, Any]) -> dict[str, Any]:
    """The fitted ``z_program`` beta, per gene. Weighted, whitened, solved by lstsq.

    The weighted problem is solved on the WHITENED system ``sqrt(W)D b = sqrt(W)y`` rather
    than by forming ``D'WD``: the normal equations square the condition number, and a
    degenerate donor block comes back from them as numbers instead of as a failure.
    """
    d, names = design(pb)
    w = pb["weights"]
    y = pb["expr"]                                    # units x genes

    n_units, n_params = d.shape
    if n_units <= n_params:
        raise SignatureError(
            "design_is_underdetermined",
            f"{n_units} pseudobulk unit(s) cannot fit {n_params} parameter(s) "
            f"({names}). A fit with no residual degrees of freedom reproduces its inputs "
            "exactly and has learned nothing")

    sw = np.sqrt(w)[:, None]
    dw = d * sw
    yw = y * sw

    beta, _residuals, rank, _sv = np.linalg.lstsq(dw, yw, rcond=None)
    if rank < n_params:
        raise SignatureError(
            "design_is_rank_deficient",
            f"the whitened design has rank {rank} for {n_params} parameters ({names}) — "
            "some column is a linear combination of the others, so the z_program beta is "
            "not identified. A number returned here would be an arbitrary point on a ridge "
            "of equally good fits")

    i = names.index("z_program")
    return {
        "beta_program": np.asarray(beta[i], dtype=float),     # per gene
        "design_columns": names,
        "n_units": int(n_units),
        "rank": int(rank),
        "solver": config.SOLVER,
    }


def standardise(v: np.ndarray) -> np.ndarray:
    """Standardise across the readout gene universe. A flat signature stays flat."""
    v = np.asarray(v, dtype=float)
    sd = v.std()
    return (v - v.mean()) / sd if sd > 0 else np.zeros_like(v)


def base_signature(*, z_program: np.ndarray, activation: np.ndarray, donors: np.ndarray,
                   expr: np.ndarray, n_bins: int = config.N_SCORE_BINS) -> dict[str, Any]:
    """``base_sig(program, condition)`` — the whole path, cells to standardised signature.

    This is the ONE base effect. Both arms of the program in this condition are exact sign
    transforms of it, so they can never disagree about a magnitude they share.
    """
    pb = build_pseudobulk(z_program=z_program, activation=activation, donors=donors,
                          expr=expr, n_bins=n_bins)
    fit = fit_base_signature(pb)
    return {
        "signature": standardise(fit["beta_program"]),
        "beta_program": fit["beta_program"],
        "design_columns": fit["design_columns"],
        "n_units": fit["n_units"],
        "rank": fit["rank"],
        "n_bins": pb["n_bins"],
        "binning_axes": pb["binning_axes"],
        "signature_model_id": config.SIGNATURE_MODEL_ID,
        "solver": config.SOLVER,
    }
