"""ONE fit per (program, condition). TWO arms, as an exact sign transform.

    y(direct|P|increase|C) = +base_sig(P, C)      <- THE fit
    y(direct|P|decrease|C) = -base_sig(P, C)      <- its exact negation, not a re-estimate

The two arms of a program in a context are ONE measurement and a sign. Re-fitting the
second would let them disagree, by a hair of floating point, about a magnitude they share —
and a reader comparing the two would be reading a difference nothing measured. So the second
arm is DERIVED, and it costs half the compute as well.

This is valid because the ElasticNet objective is symmetric in ``b`` (see ``model.py``), and
it holds only while ``positive=False``, which ``model.validate_positive`` enforces.

THE SIGN TRANSFORM IS LOCAL TO THIS LANE
----------------------------------------
``direct.arm_keys.derive_arm_values`` refuses any quantity outside its own
``SIGN_TRANSFORM_APPLIES_TO`` tuple — and that tuple is emitted inside Direct's HASHED
``method_block()``. Adding ``p2s_base_coefficient`` to it would change Direct's bytes, which
is exactly what this lane may not do. So the transform is re-stated here, over this lane's
own quantity, and Direct is not touched.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

import numpy as np
import pandas as pd

from . import armref, config, model

# This lane's OWN signed quantity. Deliberately not registered with direct.arm_keys.
QUANTITY = "p2s_base_coefficient"

SIGN = {"increase": 1, "decrease": -1}


def negate(values, change: str) -> list[float]:
    """The arm's values, as an exact sign transform of the ONE base effect.

    ``0.0`` negates to ``0.0``, never ``-0.0``: a sign on a zero is a distinction the data
    does not make, and it would print as a different number.
    """
    if change not in SIGN:
        raise armref.ArmRefError(
            "desired_change_is_not_a_desired_change",
            f"cannot sign-transform for desired_change={change!r}")
    s = SIGN[change]
    return [(0.0 if v == 0 else s * float(v)) for v in values]


def fit_program(*, program_id: str, condition: str, base_signature: np.ndarray,
                x: pd.DataFrame, cfg: config.ModelConfig, layer: str, scope: str,
                fit: Optional[Callable[..., dict]] = None,
                seed: int = config.RANDOM_STATE) -> dict[str, Any]:
    """Both arms of one program, from ONE fit. Rows keyed by ``arm_key``.

    Returns ``{"coefficients": [...], "reconstruction": [...]}`` — the metrics come back
    with the coefficients because they are outputs of the SAME fit, and a caller that had to
    go and find them somewhere else would eventually pair the wrong ones.

    ``fit`` is injectable so the arm arithmetic can be tested without the upstream model;
    production always uses the pinned one.
    """
    fit = fit or model.run_one
    inc, dec = armref.both_arms(program_id, condition)

    y = pd.Series(np.asarray(base_signature, dtype=float), index=x.index)
    model_id = "|".join((inc.arm_key, layer, cfg.name, scope))
    out = fit(x, y, cfg, model_id, seed=seed)

    coefs = out["coefficients"]
    base = [float(v) for v in coefs["coefficient"].to_numpy()]
    sem = [float(v) for v in coefs[config.COEF_SEM_COLUMN].to_numpy()]
    targets = [str(t) for t in coefs.index]

    rows: list[dict[str, Any]] = []
    for ref in (inc, dec):
        # DERIVED for `decrease`; the identity transform for `increase`. Never a re-fit.
        values = negate(base, ref.desired_change)
        for target_id, value, s in zip(targets, values, sem):
            nonzero = abs(value) > config.NONZERO_TOL
            rows.append({
                "arm_key": ref.arm_key,
                "program_id": ref.program_id,
                "desired_change": ref.desired_change,
                "condition": ref.condition,
                "target_id": target_id,
                "coefficient": value,
                # fit variation across overlapping fits. NOT inference, and never a p-value.
                config.COEF_SEM_COLUMN: s,
                "nonzero": bool(nonzero),
                "sign": int(np.sign(value)) if nonzero else 0,
                "effect_layer": layer,
                "model_config": cfg.name,
                "donor_scope": scope,
                "quantity": QUANTITY,
            })

    return {
        "coefficients": rows,
        "reconstruction": reconstruction_rows(
            program_id=program_id, condition=condition, layer=layer, scope=scope,
            cfg_name=cfg.name, recon=out["reconstruction"]),
    }


def reconstruction_rows(*, program_id: str, condition: str, layer: str, scope: str,
                        cfg_name: str, recon: dict[str, Any]) -> list[dict[str, Any]]:
    """The gene-CV metrics, emitted once PER ARM.

    The metrics are SIGN-INVARIANT — reconstructing ``-y`` from ``-b`` fits exactly as well
    as reconstructing ``y`` from ``b`` — so both arms carry the same numbers, from the one
    fit. They are stated per arm because a reader asks about ONE arm and must not have to
    know that the other arm's row is where the number lives.
    """
    inc, dec = armref.both_arms(program_id, condition)
    return [
        dict(recon, arm_key=ref.arm_key, program_id=ref.program_id,
             desired_change=ref.desired_change, condition=ref.condition,
             effect_layer=layer, model_config=cfg_name, donor_scope=scope,
             metrics_are_sign_invariant=True)
        for ref in (inc, dec)
    ]
