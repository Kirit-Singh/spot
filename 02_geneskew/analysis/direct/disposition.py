"""Explicit eligibility, evidence-tier and support-state logic (plan §5.5-§5.7).

Source QC (on-target repression, target expression, cell count) is kept
SEPARATE from the Stage-2 projection: the numeric projection is emitted
whenever axis coverage is sufficient, regardless of source QC. The eligibility
state is a single conservative disposition; ``eligibility_reasons`` carries the
complete set of applicable flags so nothing is hidden. No p/q values are
produced; ``inference_status = not_calibrated``.
"""
from __future__ import annotations

from typing import Any, Optional

from . import config
from .projection import INSUFFICIENT_AXIS_COVERAGE, sign_of

# Explicit eligibility states (plan §5.5). Order = conservative precedence:
# the first matching condition (top to bottom) is reported.
ELIGIBILITY_STATES = [
    "unavailable_in_condition",
    "insufficient_axis_coverage",
    "unresolved_mask",
    "underpowered_cells",
    "low_target_expression",
    "no_detectable_source_on_target_repression",
    "eligible_single_guide",
    "eligible_two_guide",
]


def classify_eligibility(*, row_present: bool, projection_status: str,
                         mask_resolved: bool, n_cells: Optional[float],
                         low_target_gex: Optional[bool],
                         ontarget_significant: Optional[bool],
                         n_guides: Optional[float]) -> tuple[str, list[str]]:
    """Return (eligibility_state, eligibility_reasons)."""
    reasons: list[str] = []
    if not row_present:
        return "unavailable_in_condition", ["target_condition_row_absent"]

    if projection_status == INSUFFICIENT_AXIS_COVERAGE:
        reasons.append("insufficient_axis_coverage")
    if not mask_resolved:
        reasons.append("unresolved_mask")
    if n_cells is not None and n_cells < config.N_CELLS_MIN:
        reasons.append("underpowered_cells")
    if low_target_gex:
        reasons.append("low_target_expression")
    if ontarget_significant is False:
        reasons.append("no_detectable_source_on_target_repression")
    if n_guides is not None:
        reasons.append("eligible_single_guide" if n_guides <= 1
                       else "eligible_two_guide")

    # conservative precedence
    for state in ELIGIBILITY_STATES:
        if state in reasons:
            return state, reasons
    return "eligible_two_guide", reasons or ["eligible_two_guide"]


def desired_target_modulation(balanced_skew: Optional[float]) -> str:
    """Direction of target abundance change we want for the objective.

    The screen measures CRISPRi knockdown. If knockdown moves toward the goal
    (balanced_skew > 0) the desired modulation is a DECREASE; otherwise reaching
    the goal would require an INCREASE. Null when not evaluated.
    """
    if balanced_skew is None:
        return "not_evaluated"
    if balanced_skew > config.SIGN_EPS:
        return "decrease"
    if balanced_skew < -config.SIGN_EPS:
        return "increase"
    return "neutral"


def guide_support_state(main_balanced: Optional[float],
                        guide_balanced: list[Optional[float]]) -> dict:
    """Guide sign agreement of guide-specific balanced_skew vs the main value."""
    eps = config.SIGN_EPS
    main_sign = sign_of(main_balanced, eps)
    signs = [sign_of(v, eps) for v in guide_balanced if v is not None]
    n = len(signs)
    if main_sign is None or n == 0:
        return {"n_guides_evaluated": n, "guide_sign_agreement": None,
                "n_guides_concordant": None}
    concord = sum(1 for s in signs if s == main_sign)
    return {
        "n_guides_evaluated": n,
        "n_guides_concordant": concord,
        "guide_sign_agreement": (concord == n and main_sign != 0),
    }


def donor_support_state(main_balanced: Optional[float],
                        pair_balanced: list[Optional[float]],
                        n_pairs_total: int) -> dict:
    """Donor-pair sign concordance (overlapping sensitivity estimates, n=4)."""
    eps = config.SIGN_EPS
    main_sign = sign_of(main_balanced, eps)
    evaluated = [sign_of(v, eps) for v in pair_balanced if v is not None]
    n_eval = len(evaluated)
    missing = n_pairs_total - n_eval
    if main_sign is None or n_eval == 0:
        return {"n_donor_pairs_evaluated": n_eval, "n_donor_pairs_missing": missing,
                "n_donor_pairs_concordant": None, "n_donor_pairs_discordant": None,
                "donor_pair_agreement": None, "effective_donor_n": 4}
    concord = sum(1 for s in evaluated if s == main_sign)
    discord = sum(1 for s in evaluated if s != main_sign and s != 0)
    return {
        "n_donor_pairs_evaluated": n_eval,
        "n_donor_pairs_missing": missing,
        "n_donor_pairs_concordant": concord,
        "n_donor_pairs_discordant": discord,
        "donor_pair_agreement": (concord == n_eval and main_sign != 0),
        "effective_donor_n": 4,
    }


def support_state(*, projection_ok: bool, guide_agree: Optional[bool],
                  donor_agree: Optional[bool]) -> str:
    """Combined support state (plan §5.7 vocabulary; cell-level is stubbed).

    Cell-level extraction is deferred this pass, so no target reaches
    ``cell_level_supported``; every eligible target is at most
    ``donor_supported``.
    """
    if not projection_ok:
        return "underpowered"
    if guide_agree and donor_agree:
        return "donor_supported"
    if guide_agree:
        return "guide_supported"
    return "screen_only"


def evidence_tier(*, eligibility_state: str, projection_ok: bool,
                  direction_class: str, guide_agree: Optional[bool],
                  donor_agree: Optional[bool]) -> str:
    """Frozen evidence-tier rule (plan §5.5). Ordered, explicit, no p/q.

    Reports family membership only; NOT a called multiplicity family.
    """
    if not projection_ok:
        return "not_evaluated"
    excluded = {
        "unavailable_in_condition", "insufficient_axis_coverage",
        "unresolved_mask", "underpowered_cells", "low_target_expression",
        "no_detectable_source_on_target_repression",
    }
    if eligibility_state in excluded:
        return "excluded_source_qc"
    if direction_class == "aligned_both" and guide_agree and donor_agree:
        return "tier1_directional_guide_donor"
    if direction_class in ("aligned_both", "aligned_away_a_only",
                           "aligned_toward_b_only") and guide_agree:
        return "tier2_directional_guide"
    return "tier3_screen_only"
