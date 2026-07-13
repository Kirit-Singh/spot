"""Stability across the run grid, and the SUPPORT STATUS — judged PER ARM.

There is no other kind of support here. Legacy judged support on ``combined_A_to_B``, which
is ``z(away) + z(toward)`` — a combined objective by another name. A target whose support
was entirely on one arm, and OPPOSED on the other, carried a strong combined number, and a
consumer reading one ``support_status`` could not tell which arm the support was for.
"Supported", on such a target, means the opposite of what it appears to mean.

So support is emitted once per reusable ``arm_key``, and there is no combined lane to
quarantine — there is no combined lane at all.

THREE COUNTING RULES, EACH FROM A REAL DEFECT
---------------------------------------------
  * a ZERO coefficient does not disappear from coverage. ``n_runs`` counts every run in
    which the target was a column, not only the runs in which it was selected — otherwise a
    target selected once out of twenty renders as a flawless 1.0;
  * the DENOMINATOR ships with the frequency. One nonzero of many is not robustness;
  * overlapping LODO fits are NOT independent replicates. ``lodo_sign_agreement`` is
    agreement among overlapping fits and says so — it is not a replication claim.

NO RANK COLUMN. A lane with no rank column has no surface on which to reorder anything,
which is a stronger guarantee than a rule saying it must not.
"""
from __future__ import annotations

from typing import Any, Iterable

import numpy as np

from . import config

ALL_DONOR = "all_donor"
LODO_PREFIX = "lodo_"

LODO_SEMANTICS = ("agreement among OVERLAPPING leave-one-donor-out fits; they share most "
                  "of their cells and are not independent replicates")


def _freq(flags: list[bool]) -> float:
    return round(sum(1 for f in flags if f) / len(flags), 6) if flags else 0.0


def _sign_agreement(signs: list[int]) -> Any:
    """The fraction of NONZERO signs that share the dominant sign, or None if there are 0.

    ``None``, not ``1.0``: no evidence is not perfect agreement, and a 1.0 here would read
    as the strongest possible support for a target nothing ever selected.
    """
    nz = [s for s in signs if s != 0]
    if not nz:
        return None
    dominant = max(sum(1 for s in nz if s > 0), sum(1 for s in nz if s < 0))
    return round(dominant / len(nz), 6)


def support_status(*, selection_frequency: float, positive_frequency: float,
                   negative_frequency: float) -> str:
    """The frozen categorical rule. Positive = supportive; NEGATIVE = OPPOSED, and stays so.

    ``positive_frequency`` and ``negative_frequency`` are fractions OF THE SELECTED RUNS.
    """
    if selection_frequency <= 0:
        return config.NOT_SELECTED
    if selection_frequency < config.SUPPORT_MIN_SELECTION:
        return config.WEAK
    if positive_frequency >= config.SUPPORT_SIGN_DOMINANCE:
        return config.SUPPORTED
    if negative_frequency >= config.SUPPORT_SIGN_DOMINANCE:
        return config.OPPOSED
    return config.MIXED


def compute(coef_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per (arm_key, target_id), over every run that target appeared in."""
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in coef_rows:
        by_key.setdefault((str(r["arm_key"]), str(r["target_id"])), []).append(r)

    out: list[dict[str, Any]] = []
    for (arm_key, target_id), rows in sorted(by_key.items()):
        first = rows[0]
        coefs = [float(r["coefficient"]) for r in rows]
        nonzero = [bool(r["nonzero"]) for r in rows]
        signs = [int(r["sign"]) for r in rows]

        n_runs = len(rows)                      # the DENOMINATOR. Zeros are counted.
        sel_freq = _freq(nonzero)
        selected_signs = [s for s in signs if s != 0]
        n_sel = len(selected_signs)
        pos_freq = round(sum(1 for s in selected_signs if s > 0) / n_sel, 6) if n_sel else 0.0
        neg_freq = round(sum(1 for s in selected_signs if s < 0) / n_sel, 6) if n_sel else 0.0

        lodo = [r for r in rows if str(r["donor_scope"]).startswith(LODO_PREFIX)]
        layers = {str(r["effect_layer"]) for r in rows}
        layer_signs = [int(r["sign"]) for r in rows if str(r["donor_scope"]) == ALL_DONOR]

        status = support_status(selection_frequency=sel_freq,
                                positive_frequency=pos_freq,
                                negative_frequency=neg_freq)

        out.append({
            "arm_key": arm_key,
            "program_id": str(first["program_id"]),
            "desired_change": str(first["desired_change"]),
            "condition": str(first["condition"]),
            "target_id": target_id,
            "n_runs": n_runs,
            "n_selected_runs": n_sel,
            "selection_frequency": sel_freq,
            "positive_frequency": pos_freq,
            "negative_frequency": neg_freq,
            "median_coefficient": round(float(np.median(coefs)), 6),
            "coefficient_min": round(float(np.min(coefs)), 6),
            "coefficient_max": round(float(np.max(coefs)), 6),
            "lodo_sign_agreement": _sign_agreement([int(r["sign"]) for r in lodo]),
            "n_lodo_runs": len(lodo),
            # renamed from the legacy `logfc_zscore_agreement`: that name contains "score",
            # which the round-4 key-name firewall refuses at any depth.
            "effect_layer_agreement": _sign_agreement(layer_signs) if len(layers) > 1
            else None,
            "n_effect_layers": len(layers),
            "support_status": status,
            "opposed": status == config.OPPOSED,
        })
    return out


def method_block() -> dict[str, Any]:
    """The support rule, as one hashable object."""
    return {
        "support_is_judged_per_arm": True,
        "support_min_selection": config.SUPPORT_MIN_SELECTION,
        "support_sign_dominance": config.SUPPORT_SIGN_DOMINANCE,
        "support_status_values": list(config.SUPPORT_STATUS_VALUES),
        "nonzero_tolerance": config.NONZERO_TOL,
        "zero_coefficients_counted_in_denominator": True,
        "lodo_semantics": LODO_SEMANTICS,
        "lodo_fits_are_independent_replicates": False,
        "rank_column_emitted": config.RANK_COLUMN_EMITTED,
        "opposed_contributors_are_kept_opposed": True,
    }
