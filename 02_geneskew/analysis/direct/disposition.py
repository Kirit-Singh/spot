"""Base QC, independent arm evaluability, per-arm support, per-arm direction.

Frozen before any new rank was viewed.

* BASE QC is pre-outcome and computed ONCE. It depends only on input/mask/guide/
  cell availability — never on either arm's outcome, so it cannot smuggle one
  arm's result into the other arm's gate.
* Each arm then gets its OWN evaluability state, from base QC plus that arm's own
  projection status. ``A_evaluable`` and ``B_evaluable`` are independent.
* Support (guide replication, donor splits) is computed PER ARM from that arm's
  own values. A's support is never reused as B's support.
* Desired pharmacologic modulation is derived per arm, and a conflict between the
  arms is preserved as a conflict — never resolved into a winner.
* No p/q anywhere.
"""
from __future__ import annotations

from typing import Any, Optional

from . import config, domain
from .projection import (INSUFFICIENT_AXIS_COVERAGE, MASK_UNRESOLVED, OK,
                         sign_of)

# --------------------------------------------------------------------------- #
# Base (pre-outcome) QC — shared by both arms, a function of NEITHER outcome.
# --------------------------------------------------------------------------- #
BASE_QC_PRECEDENCE = [
    "unavailable_in_condition",
    # A symbol-namespace target with no explicit Ensembl id: it stays in the
    # disposition table but can never be masked or ranked as if the symbol were an
    # accession. This is more precise than "mask_unresolved", so it outranks it.
    "unresolved_target_identity",
    "mask_unresolved",
    "missing_qc_measurement",
    "invalid_qc_measurement",
    "underpowered_cells",
    "low_target_expression",
    "no_detectable_source_on_target_repression",
    "qc_pass_single_guide",
    "qc_pass_two_guide",
    "qc_pass_multi_guide",
]
BASE_QC_PASS_STATES = frozenset(
    {"qc_pass_single_guide", "qc_pass_two_guide", "qc_pass_multi_guide"})
# Targets that can never earn replicated-guide support in EITHER arm.
NEVER_REPLICATED_STATES = frozenset({"qc_pass_single_guide"})

# Per-arm evaluability states.
ARM_EVALUABLE = "evaluable"
ARM_EXCLUDED_BASE_QC = "excluded_base_qc"
ARM_INSUFFICIENT_COVERAGE = "insufficient_axis_coverage"
ARM_MASK_UNRESOLVED = "mask_unresolved"

# Support status (per arm). "evaluated" is a CLAIM: it says support was looked for and
# an answer came back. It may only be emitted when support was actually evaluable, so
# availability is asked FIRST — an arm can be perfectly evaluable in a pass where there
# was no support evidence to evaluate at all, and calling that "evaluated" reports a
# measurement nobody made.
SUPPORT_STATUS_EVALUATED = "evaluated"
SUPPORT_STATUS_NOT_EVALUATED_BASE_QC = "not_evaluated_base_qc"
SUPPORT_STATUS_NOT_EVALUATED_ARM = "not_evaluated_arm"
SUPPORT_STATUS_UNAVAILABLE = domain.SUPPORT_UNAVAILABLE
SUPPORT_STATUSES = (SUPPORT_STATUS_EVALUATED, SUPPORT_STATUS_NOT_EVALUATED_BASE_QC,
                    SUPPORT_STATUS_NOT_EVALUATED_ARM, SUPPORT_STATUS_UNAVAILABLE)

# Guide-replication states (per arm).
REPLICATION_NOT_EVALUATED = "not_evaluated"      # the arm itself is not evaluable
REPLICATION_UNAVAILABLE = "unavailable_unresolved_guides"
# The guide-slot estimates carry no contributor evidence in the pooled-main domain, so
# they were never projected. This is DIFFERENT from "the guides were unresolved": the
# question was never askable, and the state says so instead of implying a failed lookup.
REPLICATION_SUPPORT_UNAVAILABLE = domain.SUPPORT_UNAVAILABLE
REPLICATION_SINGLE = "single_guide_no_replication"
REPLICATION_CONCORDANT = "replicated_concordant"
REPLICATION_DISCORDANT = "replicated_discordant"

# Desired pharmacologic modulation (per arm).
MOD_DECREASE = "decrease"
MOD_INCREASE = "increase"
MOD_NO_DIRECTION = "no_direction_evidence"
MOD_NOT_EVALUATED = "not_evaluated"

# Cross-arm modulation agreement — descriptive, never a winner.
MOD_AGREE = "agree"
MOD_CONFLICT = "conflict"
MOD_ONLY_A = "only_away_from_A_evaluated"
MOD_ONLY_B = "only_toward_B_evaluated"
MOD_NONE = "neither_arm_evaluated"


def measurement_status(n_cells, ontarget_significant,
                       low_target_gex) -> tuple[list[str], list[str]]:
    """Presence/validity of every REQUIRED base-QC measurement.

    A missing measurement is NOT a favourable measurement, and neither is an
    invalid one. Both produce explicit reasons and a non-evaluable disposition.
    """
    missing: list[str] = []
    invalid: list[str] = []

    if n_cells is None:
        missing.append("n_cells")
    else:
        try:
            v = float(n_cells)
            if v != v or v in (float("inf"), float("-inf")) or v < 0:
                invalid.append("n_cells")
        except (TypeError, ValueError):
            invalid.append("n_cells")

    for name, value in (("ontarget_significant", ontarget_significant),
                        ("low_expression_flag", low_target_gex)):
        if value is None:
            missing.append(name)
        elif not isinstance(value, bool):
            invalid.append(name)

    return missing, invalid


def base_qc(*, row_present: bool, mask_resolved: bool,
            n_cells: Optional[float], low_target_gex: Optional[bool],
            ontarget_significant: Optional[bool],
            n_guides: Optional[float],
            target_identity_resolved: bool = True) -> tuple[str, bool, list[str]]:
    """Pre-outcome QC. Returns (state, passed, complete reason list).

    Nothing here reads a projection value. Both arms consume the SAME base QC.
    Missing/invalid required measurements are non-evaluable, never favourable.
    """
    if not row_present:
        return "unavailable_in_condition", False, ["target_condition_row_absent"]

    reasons: list[str] = []
    if not target_identity_resolved:
        reasons.append("unresolved_target_identity")
    if not mask_resolved:
        reasons.append("mask_unresolved")

    missing, invalid = measurement_status(n_cells, ontarget_significant,
                                          low_target_gex)
    if missing:
        reasons.append("missing_qc_measurement")
        reasons += [f"missing_qc:{m}" for m in missing]
    if invalid:
        reasons.append("invalid_qc_measurement")
        reasons += [f"invalid_qc:{m}" for m in invalid]

    unusable = set(missing) | set(invalid)
    if "n_cells" not in unusable and float(n_cells) < config.N_CELLS_MIN:
        reasons.append("underpowered_cells")
    if low_target_gex is True:
        reasons.append("low_target_expression")
    if ontarget_significant is False:
        reasons.append("no_detectable_source_on_target_repression")

    if n_guides is None:
        reasons.append("guide_count_unknown")
        if "mask_unresolved" not in reasons:
            reasons.append("mask_unresolved")
    else:
        n = int(n_guides)
        reasons.append("qc_pass_single_guide" if n <= 1
                       else "qc_pass_two_guide" if n == 2
                       else "qc_pass_multi_guide")

    for state in BASE_QC_PRECEDENCE:
        if state in reasons:
            return state, state in BASE_QC_PASS_STATES, reasons
    return "mask_unresolved", False, reasons or ["guide_count_unknown"]


def arm_state(*, base_state: str, base_passed: bool,
              projection_status: str) -> tuple[str, bool, list[str]]:
    """This ONE arm's evaluability, from base QC + this arm's own projection.

    The other arm's value, status and support are not inputs. Returns
    (state, evaluable, reasons).
    """
    reasons: list[str] = []
    if not base_passed:
        reasons.append(f"base_qc:{base_state}")
        return ARM_EXCLUDED_BASE_QC, False, reasons
    if projection_status == MASK_UNRESOLVED:
        return ARM_MASK_UNRESOLVED, False, ["arm_mask_unresolved"]
    if projection_status == INSUFFICIENT_AXIS_COVERAGE:
        return ARM_INSUFFICIENT_COVERAGE, False, ["arm_insufficient_axis_coverage"]
    if projection_status != OK:
        return ARM_INSUFFICIENT_COVERAGE, False, [f"arm_projection:{projection_status}"]
    return ARM_EVALUABLE, True, ["arm_evaluable"]


# --------------------------------------------------------------------------- #
# Direction (per arm), and the conflict between the arms.
# --------------------------------------------------------------------------- #
def desired_modulation(arm_value: Optional[float], *, evaluable: bool) -> str:
    """Modulation implied by ONE arm under CRISPRi knockdown.

    Derived only when that arm actually has direction evidence: an arm that is
    not evaluable, or whose value is within the sign tolerance, yields no
    pharmacologic direction at all.
    """
    if not evaluable or arm_value is None:
        return MOD_NOT_EVALUATED
    if arm_value > config.SIGN_EPS:
        return MOD_DECREASE          # knockdown moved this arm the desired way
    if arm_value < -config.SIGN_EPS:
        return MOD_INCREASE
    return MOD_NO_DIRECTION


def modulation_agreement(mod_a: str, mod_b: str) -> str:
    """Cross-arm agreement. A CONFLICT IS PRESERVED, never resolved.

    There is no best-of rule here: if the two arms imply opposite drug
    directions, that is the finding, and both arm directions stay emitted.
    """
    real = {MOD_DECREASE, MOD_INCREASE}
    a_real, b_real = mod_a in real, mod_b in real
    if a_real and b_real:
        return MOD_AGREE if mod_a == mod_b else MOD_CONFLICT
    if a_real:
        return MOD_ONLY_A
    if b_real:
        return MOD_ONLY_B
    return MOD_NONE


# --------------------------------------------------------------------------- #
# Support (per arm).
# --------------------------------------------------------------------------- #
def guide_replication(arm_value: Optional[float], slots: list[dict[str, Any]],
                      arm: str, base_state: Optional[str] = None,
                      arm_evaluable: bool = True,
                      support_available: bool = True) -> dict[str, Any]:
    """Replication across DISTINCT contributing guides, FOR ONE ARM.

    ``slots`` carries one dict per released guide modality:
    ``{"estimate_id", "guide_id"|None, "values": {arm: v|None}, "unresolved_reason"}``.
    A guide counts only if it is mapped to a real guide_id AND was evaluated IN
    THIS ARM. A single-guide target can never reach replication in either arm.

    ``support_available=False`` is this release pass: the guide-slot estimates have no
    contributor evidence, so none was projected and there is no replication claim to
    make — in either direction. The arm keeps its own score; it simply earns no guide
    support from it, and therefore cannot be elevated above tier 3.
    """
    eps = config.SIGN_EPS
    main_sign = sign_of(arm_value, eps)

    mapped = [s for s in slots if s.get("guide_id")]
    distinct = {s["guide_id"] for s in mapped}
    evaluated = {s["guide_id"]: s for s in mapped
                 if s.get("values", {}).get(arm) is not None}

    missing: list[str] = []
    for s in slots:
        if not s.get("guide_id"):
            missing.append(f"{s['estimate_id']}:{s.get('unresolved_reason') or 'unmapped'}")
        elif s.get("values", {}).get(arm) is None:
            missing.append(f"{s['estimate_id']}:not_evaluated_in_{arm}")

    n_eval = len(evaluated)
    signs = [sign_of(s["values"][arm], eps) for s in evaluated.values()]
    n_concordant = 0 if main_sign is None else sum(1 for s in signs if s == main_sign)

    if not arm_evaluable:
        # Support is inferential. A target that failed base QC, or an arm that was
        # never evaluated, cannot acquire support from raw numbers that were only
        # ever diagnostics. The counts below are retained; the VERDICT is not.
        state = REPLICATION_NOT_EVALUATED
    elif not support_available:
        # The question was never askable in this pass. Saying so is not the same as
        # saying the guides failed to resolve.
        state = REPLICATION_SUPPORT_UNAVAILABLE
    elif base_state in NEVER_REPLICATED_STATES:
        state = REPLICATION_SINGLE          # hard cap: one guide is one guide
    elif not distinct:
        state = REPLICATION_UNAVAILABLE
    elif n_eval < config.MIN_GUIDES_FOR_REPLICATION:
        state = REPLICATION_SINGLE
    elif main_sign not in (None, 0) and n_concordant == n_eval:
        state = REPLICATION_CONCORDANT
    else:
        state = REPLICATION_DISCORDANT

    return {
        "guide_replication_state": state,
        "guide_replication_supported": state == REPLICATION_CONCORDANT,
        "n_guide_slots_released": len(slots),
        "n_guides_mapped": len(distinct),
        "n_guides_evaluated": n_eval,
        "n_guides_concordant": n_concordant if n_eval else 0,
        "min_guides_required": config.MIN_GUIDES_FOR_REPLICATION,
        "guide_missing_reasons": ";".join(sorted(missing)),
    }


def support_status(*, arm_evaluable: bool, base_passed: bool,
                   support_available: bool) -> str:
    """Whether this arm's support was EVALUATED — availability decided first.

    ``evaluated`` asserts that support evidence existed and was assessed. In a pass
    where support carries no contributor evidence there is nothing to assess, so an
    evaluable arm is not "evaluated": it is explicitly unavailable. Emitting
    ``evaluated`` there would report a measurement that was never taken, and every
    downstream reader of the support columns would believe a null meant "no support
    found" rather than "no support was askable".
    """
    if not support_available:
        return SUPPORT_STATUS_UNAVAILABLE
    if arm_evaluable:
        return SUPPORT_STATUS_EVALUATED
    if not base_passed:
        return SUPPORT_STATUS_NOT_EVALUATED_BASE_QC
    return SUPPORT_STATUS_NOT_EVALUATED_ARM


def support_state(*, arm_evaluable: bool, guide_replicated: bool,
                  donor_split_supported: bool) -> str:
    """Within-dataset support FOR ONE ARM. Cell-level is deferred, so no target
    can reach ``cell_level_supported`` in this lane."""
    if not arm_evaluable:
        return "not_evaluated"
    if guide_replicated and donor_split_supported:
        return "within_dataset_replicated"
    return "screen_only"


def evidence_tier(*, arm_evaluable: bool, arm_value: Optional[float],
                  guide_replicated: bool, donor_split_supported: bool,
                  support_available: bool = True) -> str:
    """Frozen tier rule FOR ONE ARM, on that arm's own value. No p/q, no other arm.

    When support is out of domain, tiers 1 and 2 are STRUCTURALLY unreachable — not
    merely unreached. The guard is redundant with ``guide_replicated`` and
    ``donor_split_supported`` both being false, and it is here on purpose: an
    elevation is the one error whose blast radius is the published ranking, so it is
    refused twice rather than once.
    """
    if not arm_evaluable or arm_value is None:
        return "not_evaluated"
    if arm_value <= config.SIGN_EPS:
        return "evaluable_no_directional_signal"
    if not support_available:
        return "tier3_screen_only"
    if guide_replicated and donor_split_supported:
        return "tier1_guide_and_donor_split"
    if guide_replicated:
        return "tier2_guide_replicated"
    return "tier3_screen_only"
