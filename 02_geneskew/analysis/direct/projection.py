"""Target-masked DE-space program projection and deterministic ranking.

Pure functions (numpy only) so the direct formula is unit-testable without the
single-cell stack. The projection is a DE-space program projection, NOT an
exact predicted per-cell Stage-1 score (plan §5.3).

    delta_p(X) = mean_{g in P_p \\ M_X} d_X,g  -  mean_{g in C_p \\ M_X} d_X,g

Panel and control means are recomputed SEPARATELY after masking; there is no
L2 renormalisation of a mixed vector.
"""
from __future__ import annotations

from typing import Iterable, Optional

import numpy as np

# Projection disposition constants.
OK = "ok"
INSUFFICIENT_AXIS_COVERAGE = "insufficient_axis_coverage"


def _present_cols(gene_ids: Iterable[str], gene_index: dict[str, int],
                  mask: set[str]) -> list[int]:
    return [gene_index[g] for g in gene_ids
            if g in gene_index and g not in mask]


def program_delta(
    effect_row: np.ndarray,
    panel_ids: Iterable[str],
    control_ids: Iterable[str],
    gene_index: dict[str, int],
    mask: set[str],
    min_panel: int,
    min_control: int,
) -> dict:
    """Compute one program's masked DE-space projection for a single target row.

    ``effect_row`` is the dense 1-D measured-effect vector over the ordered gene
    universe. Returns a dict with delta, surviving counts and a status.
    """
    panel_cols = _present_cols(panel_ids, gene_index, mask)
    control_cols = _present_cols(control_ids, gene_index, mask)
    n_panel, n_control = len(panel_cols), len(control_cols)
    if n_panel < min_panel or n_control < min_control:
        return {
            "delta": None,
            "panel_mean": None,
            "control_mean": None,
            "n_panel_surviving": n_panel,
            "n_control_surviving": n_control,
            "status": INSUFFICIENT_AXIS_COVERAGE,
        }
    panel_mean = float(np.mean(effect_row[panel_cols]))
    control_mean = float(np.mean(effect_row[control_cols]))
    return {
        "delta": panel_mean - control_mean,
        "panel_mean": panel_mean,
        "control_mean": control_mean,
        "n_panel_surviving": n_panel,
        "n_control_surviving": n_control,
        "status": OK,
    }


def project_balanced(effect_row, prog_a: dict, prog_b: dict,
                     gene_index: dict[str, int], mask: set[str],
                     min_panel: int, min_control: int) -> Optional[float]:
    """Convenience: masked balanced_skew for one effect vector, or None.

    ``prog_a``/``prog_b`` are {"panel", "control", "sign"} dicts. Used by the
    guide/donor support lanes; the target is looked up by stable id upstream so
    the same masked projection is applied identically to every lane (§5.6).
    """
    da = program_delta(effect_row, prog_a["panel"], prog_a["control"],
                       gene_index, mask, min_panel, min_control)
    db = program_delta(effect_row, prog_b["panel"], prog_b["control"],
                       gene_index, mask, min_panel, min_control)
    if da["status"] != OK or db["status"] != OK:
        return None
    ax = axis_scores(da["delta"], db["delta"], prog_a["sign"], prog_b["sign"])
    return ax["balanced_skew"]


def axis_scores(delta_a: Optional[float], delta_b: Optional[float],
                sign_a: int, sign_b: int) -> dict:
    """Map program deltas to away-from-A / toward-B / balanced_skew (plan §5.3)."""
    away = None if delta_a is None else -sign_a * delta_a
    toward = None if delta_b is None else sign_b * delta_b
    if away is None or toward is None:
        balanced = None
    else:
        balanced = (away + toward) / 2.0
    return {"away_from_A": away, "toward_b": toward, "balanced_skew": balanced}


def direction_class(away: Optional[float], toward: Optional[float],
                    eps: float = 1e-9) -> str:
    """Directional class for the balanced_a_to_b objective."""
    if away is None or toward is None:
        return "not_evaluated"
    a_pos = away > eps
    b_pos = toward > eps
    if a_pos and b_pos:
        return "aligned_both"
    if a_pos:
        return "aligned_away_a_only"
    if b_pos:
        return "aligned_toward_b_only"
    return "opposed"


# Tier order for ranking: aligned_both first, then one-sided, then the rest.
_TIER_RANK = {
    "aligned_both": 0,
    "aligned_away_a_only": 1,
    "aligned_toward_b_only": 1,
    "opposed": 2,
    "not_evaluated": 3,
}


def balanced_rank_key(row: dict) -> tuple:
    """Deterministic sort key for balanced_a_to_b (plan §5.3 tie-break).

    1. tier (aligned_both < one-sided < opposed < not_evaluated)
    2. balanced_skew descending
    3. min(away_from_A, toward_b) descending
    4. stable target id ascending
    Rows without a projection sort last, ordered by target id.
    """
    dclass = row["direction_class"]
    tier = _TIER_RANK.get(dclass, 3)
    balanced = row["balanced_skew"]
    away = row["away_from_A"]
    toward = row["toward_b"]
    if balanced is None or away is None or toward is None:
        return (tier, 0.0, 0.0, row["target_ensembl"])
    return (tier, -balanced, -min(away, toward), row["target_ensembl"])


def away_from_a_rank_key(row: dict) -> tuple:
    """Deterministic sort key for the away_from_a objective (plan §5.3)."""
    away = row["away_from_A"]
    if away is None:
        return (1, 0.0, row["target_ensembl"])
    return (0, -away, row["target_ensembl"])


def rank_rows(rows: list[dict], objective: str) -> list[dict]:
    """Return rows sorted with a deterministic total order and a 1-based rank.

    Ranking is invariant to input row order (the target id is the final,
    strictly total tie-break).
    """
    key = balanced_rank_key if objective == "balanced_a_to_b" else away_from_a_rank_key
    ordered = sorted(rows, key=key)
    for i, r in enumerate(ordered, start=1):
        r["rank"] = i
    return ordered


def sign_of(x: Optional[float], eps: float) -> Optional[int]:
    if x is None:
        return None
    if x > eps:
        return 1
    if x < -eps:
        return -1
    return 0
