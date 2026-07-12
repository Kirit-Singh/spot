"""Masked DE-space program projection, the two arms, and per-arm ranking.

Pure numpy so the formulae are unit-testable without the single-cell stack.

    delta_p(X) = mean_{g in P_p \\ M_X} d_X,g  -  mean_{g in C_p \\ M_X} d_X,g

Panel and control means are recomputed SEPARATELY after the estimate-specific
mask; there is no L2 renormalisation of a mixed vector. This is a DE-space
program projection, NOT an exact predicted per-cell Stage-1 score.

TWO ARMS, NEVER COMBINED
------------------------
``away_from_A`` and ``toward_B`` are two separate biological questions. They are
scored separately, gated separately and ranked separately, over their own
evaluable populations. There is no primary arm, and there is deliberately NO
function in this module that adds, averages, weights or otherwise reduces the
two arms to one number: that was the retired balanced-skew objective, and a
target opposing B must never be able to buy rank with a large A score.

The only cross-arm output is ``concordance_class`` — a descriptive label that
never ranks, never gates, and always ships alongside both raw arm values.
"""
from __future__ import annotations

from typing import Iterable, Optional

import numpy as np

from .config import ARM_A, ARM_B, ARMS

OK = "ok"
INSUFFICIENT_AXIS_COVERAGE = "insufficient_axis_coverage"
MASK_UNRESOLVED = "mask_unresolved"

# Descriptive cross-arm classes. Never a rank key, never a gate.
CONCORDANT = "concordant_both_arms"
A_ONLY = "away_from_A_only"
B_ONLY = "toward_B_only"
DISCORDANT = "discordant_arms"
NOT_EVALUATED = "not_evaluated"
PARTIAL = "partially_evaluated"


def _present_cols(gene_ids: Iterable[str], gene_index: dict[str, int],
                  mask: set[str]) -> list[int]:
    return [gene_index[g] for g in gene_ids if g in gene_index and g not in mask]


def program_delta(effect_row, panel_ids: Iterable[str], control_ids: Iterable[str],
                  gene_index: dict[str, int], mask: Optional[set[str]],
                  min_panel: int, min_control: int) -> dict:
    """One program's masked DE-space projection for a single effect vector.

    ``mask=None`` means the contributing guides were never resolved: refuse to
    project rather than fall back to an empty (self-fulfilling) mask.
    """
    if mask is None or effect_row is None:
        return {"delta": None, "panel_mean": None, "control_mean": None,
                "n_panel_surviving": None, "n_control_surviving": None,
                "status": MASK_UNRESOLVED}
    panel_cols = _present_cols(panel_ids, gene_index, mask)
    control_cols = _present_cols(control_ids, gene_index, mask)
    n_panel, n_control = len(panel_cols), len(control_cols)
    if n_panel < min_panel or n_control < min_control:
        return {"delta": None, "panel_mean": None, "control_mean": None,
                "n_panel_surviving": n_panel, "n_control_surviving": n_control,
                "status": INSUFFICIENT_AXIS_COVERAGE}
    panel_mean = float(np.mean(effect_row[panel_cols]))
    control_mean = float(np.mean(effect_row[control_cols]))
    return {"delta": panel_mean - control_mean,
            "panel_mean": panel_mean, "control_mean": control_mean,
            "n_panel_surviving": n_panel, "n_control_surviving": n_control,
            "status": OK}


def arm_scores(delta_a: Optional[float], delta_b: Optional[float],
               sign_a: int, sign_b: int) -> dict[str, Optional[float]]:
    """The two arm values. Nothing else: there is no combined score to return."""
    return {
        ARM_A: None if delta_a is None else -sign_a * delta_a,
        ARM_B: None if delta_b is None else sign_b * delta_b,
    }


def concordance_class(values: dict[str, Optional[float]], eps: float) -> str:
    """Descriptive cross-arm label. Never ranks, never gates.

    The raw arm values always travel with it, so a reader can never mistake this
    label for a score.
    """
    a, b = values.get(ARM_A), values.get(ARM_B)
    if a is None and b is None:
        return NOT_EVALUATED
    if a is None or b is None:
        return PARTIAL
    a_pos, b_pos = a > eps, b > eps
    if a_pos and b_pos:
        return CONCORDANT
    if a_pos:
        return A_ONLY
    if b_pos:
        return B_ONLY
    return DISCORDANT


# --------------------------------------------------------------------------- #
# THE FROZEN RANKING CONTRACT (the standalone verifier reimplements this text)
# --------------------------------------------------------------------------- #
#  population : rows where this arm's evaluable flag is true AND this arm's
#               EMITTED canonical score is non-null;
#  value      : the exact canonical float64 that is emitted and hashed. Scores
#               are never display-rounded before ranking -- rounding first turns
#               distinct scores into an emitted tie and the emitted tie-break then
#               contradicts the rank actually assigned;
#  nonfinite  : NaN / +-inf are not scores. They are canonicalised to null
#               upstream and are therefore never ranked;
#  direction  : descending (largest arm value = rank 1);
#  tie-break  : target_id ascending, on exactly equal canonical values;
#  numbering  : dense 1..n over the ranked population; all other rows are null.
RANK_DIRECTION = "descending"
RANK_TIE_BREAK = "target_id_ascending"
RANK_NULL_RULE = "not_evaluable_or_null_score_or_nonfinite -> null rank"


def is_rankable(row: dict, arm: str, evaluable_key: str) -> bool:
    """The frozen rank population rule, in one place."""
    value = row.get(arm)
    return (bool(row.get(evaluable_key)) and value is not None
            and not (isinstance(value, float) and (value != value)))   # NaN


def arm_rank_key(row: dict, arm: str) -> tuple:
    """Deterministic order within ONE arm: that arm's EMITTED canonical value,
    then the stable id. No other arm, no support field, no cross-arm quantity."""
    return (-row[arm], row["target_id"])


def rank_arm(rows: list[dict], arm: str, evaluable_key: str,
             rank_column: str) -> list[dict]:
    """Assign a 1-based rank to this arm's EVALUABLE targets; others get None.

    Ranks are independent per arm: a target may be ranked in one arm, in both,
    or in neither. Ranking is invariant to input row order, and is computed on the
    exact canonical value that is emitted, so it is reconstructible from the
    published table alone.
    """
    rankable = [r for r in rows if is_rankable(r, arm, evaluable_key)]
    for i, r in enumerate(sorted(rankable, key=lambda r: arm_rank_key(r, arm)),
                          start=1):
        r[rank_column] = i
    ranked_ids = {id(r) for r in rankable}
    for r in rows:
        if id(r) not in ranked_ids:
            r[rank_column] = None
    return rows


def emit_order(rows: list[dict]) -> list[dict]:
    """Stable emission order by target id.

    Deliberately NOT ordered by either arm: an emission order sorted by one arm
    would function as a headline rank.
    """
    return sorted(rows, key=lambda r: r["target_id"])


def sign_of(x: Optional[float], eps: float) -> Optional[int]:
    if x is None:
        return None
    if x > eps:
        return 1
    if x < -eps:
        return -1
    return 0


__all__ = [
    "OK", "INSUFFICIENT_AXIS_COVERAGE", "MASK_UNRESOLVED", "ARMS", "ARM_A", "ARM_B",
    "CONCORDANT", "A_ONLY", "B_ONLY", "DISCORDANT", "NOT_EVALUATED", "PARTIAL",
    "program_delta", "arm_scores", "concordance_class", "arm_rank_key", "rank_arm",
    "emit_order", "sign_of",
]
