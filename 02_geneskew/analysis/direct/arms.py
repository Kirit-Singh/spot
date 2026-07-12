"""Per-arm scoring, support and disposition.

Each arm (``away_from_A``, ``toward_B``) is built by the SAME code path from its
OWN pole, its OWN projection, its OWN guide values and its OWN donor values. The
two arms never share a value, a gate, a support field or a rank, and there is no
function here that reduces them to one number.

Emitted field names are arm-prefixed (``A_*`` / ``B_*``), plus the two arm score
columns (``away_from_A`` / ``toward_B``) and the two rank columns
(``rank_away_from_A`` / ``rank_toward_B``).
"""
from __future__ import annotations

from typing import Any, Optional

from . import config, disposition, donors
from . import projection as proj
from .hashing import canonical_num


def arm_of_pole(pole: str) -> str:
    """``"A"`` -> ``away_from_A``; ``"B"`` -> ``toward_B``."""
    return config.ARM_A if pole == "A" else config.ARM_B


def project_arm(effect_row, axis: dict, pole: str, gene_index: dict,
                mask_set: Optional[set]) -> dict:
    """One arm's masked program projection for one effect vector."""
    prog = axis[pole]
    return proj.program_delta(effect_row, prog["panel"], prog["control"], gene_index,
                              mask_set, config.MIN_SURVIVING_PANEL,
                              config.MIN_SURVIVING_CONTROL)


def arm_values(effect_row, axis: dict, gene_index: dict,
               mask_set: Optional[set]) -> dict[str, Optional[float]]:
    """BOTH arm values for one support estimate (a guide slot, a donor pair).

    Support is computed for each arm separately, so A's guide/donor evidence is
    never reused as B's.
    """
    da = project_arm(effect_row, axis, "A", gene_index, mask_set)
    db = project_arm(effect_row, axis, "B", gene_index, mask_set)
    return proj.arm_scores(da["delta"], db["delta"],
                           axis["A"]["sign"], axis["B"]["sign"])


def empty_values() -> dict[str, Optional[float]]:
    return {arm: None for arm in config.ARMS}


def arm_fields(*, pole: str, value: Optional[float], delta: dict,
               base_state: str, base_passed: bool, slots: list[dict],
               pair_values: dict[str, dict], splits: list,
               zscore_value: Optional[float],
               support_available: bool = True) -> dict[str, Any]:
    """Every emitted field for ONE arm, prefixed with its pole."""
    arm = arm_of_pole(pole)
    p = pole  # emitted prefix

    state, evaluable, reasons = disposition.arm_state(
        base_state=base_state, base_passed=base_passed,
        projection_status=delta["status"])

    # Support is INFERENTIAL: it may only exist where this arm is evaluable.
    # Raw counts are still computed, but they are diagnostics, and when the arm is
    # not evaluable they can never become a support tier or a support boolean.
    # ``support_available`` is the second, stronger gate: in this release pass the
    # support estimates were never projected at all, so there is nothing to infer FROM.
    rep = disposition.guide_replication(value, slots, arm, base_state=base_state,
                                        arm_evaluable=evaluable,
                                        support_available=support_available)
    arm_pairs = {pid: vals.get(arm) for pid, vals in pair_values.items()}
    dsupport = donors.split_support(value, arm_pairs, splits, config.SIGN_EPS,
                                    arm_evaluable=evaluable,
                                    support_available=support_available)
    # AVAILABILITY FIRST. An evaluable arm in a pass with no support evidence was not
    # "evaluated": there was nothing to evaluate. Claiming otherwise would make every
    # null support column read as a negative result instead of an absent question.
    status = disposition.support_status(arm_evaluable=evaluable,
                                        base_passed=base_passed,
                                        support_available=support_available)

    fields: dict[str, Any] = {
        # --- score: CANONICAL full precision, exactly what the rank sorts on ---
        arm: canonical_num(value) if evaluable else None,
        f"{p}_delta": canonical_num(delta["delta"]),
        f"{p}_panel_surviving": delta["n_panel_surviving"],
        f"{p}_control_surviving": delta["n_control_surviving"],
        f"{p}_projection_status": delta["status"],
        f"{arm}_zscore": canonical_num(zscore_value),
        f"{p}_support_status": status,
        # --- independent evaluability ---
        f"{p}_evaluable": evaluable,
        f"{p}_state": state,
        f"{p}_reasons": ";".join(reasons),
        f"{p}_estimate_available": value is not None,
        # --- this arm's own direction ---
        f"{p}_desired_target_modulation": disposition.desired_modulation(
            value, evaluable=evaluable),
        # --- this arm's own support ---
        f"{p}_guide_replication_state": rep["guide_replication_state"],
        f"{p}_guide_replication_supported": rep["guide_replication_supported"],
        f"{p}_n_guide_slots_released": rep["n_guide_slots_released"],
        f"{p}_n_guides_mapped": rep["n_guides_mapped"],
        f"{p}_n_guides_evaluated": rep["n_guides_evaluated"],
        f"{p}_n_guides_concordant": rep["n_guides_concordant"],
        f"{p}_guide_missing_reasons": rep["guide_missing_reasons"],
        f"{p}_n_splits_total": dsupport["n_splits_total"],
        f"{p}_n_splits_evaluable": dsupport["n_splits_evaluable"],
        f"{p}_n_splits_missing": dsupport["n_splits_missing"],
        f"{p}_n_splits_internally_concordant":
            dsupport["n_splits_internally_concordant"],
        f"{p}_n_splits_internally_discordant":
            dsupport["n_splits_internally_discordant"],
        f"{p}_n_splits_agreeing": dsupport["n_splits_agreeing_with_main"],
        f"{p}_donor_split_support": dsupport["donor_split_support"],
        f"{p}_donor_split_denominator": dsupport["donor_split_support_denominator"],
        # --- this arm's own tier / support state ---
        f"{p}_support_state": disposition.support_state(
            arm_evaluable=evaluable,
            guide_replicated=rep["guide_replication_supported"],
            donor_split_supported=dsupport["donor_split_support"]),
        f"{p}_evidence_tier": disposition.evidence_tier(
            arm_evaluable=evaluable, arm_value=value if evaluable else None,
            guide_replicated=rep["guide_replication_supported"],
            donor_split_supported=dsupport["donor_split_support"],
            support_available=support_available),
    }
    return fields


def donor_support_rows(target: str, cond: str, pair_values: dict[str, dict],
                       splits: list, arm_value: dict[str, Optional[float]],
                       run_id: Optional[str],
                       support_available: bool = True) -> list[dict[str, Any]]:
    """One row per (split, arm): both arms' halves, evaluability and concordance.

    When support is out of domain the splits are still enumerated — the release ships
    them, and a silently absent row reads as "no such split" rather than "this split
    was never evaluated". Each carries null halves and the explicit reason.
    """
    rows: list[dict[str, Any]] = []
    for arm in config.ARMS:
        arm_pairs = {pid: vals.get(arm) for pid, vals in pair_values.items()}
        support = donors.split_support(arm_value.get(arm), arm_pairs, splits,
                                       config.SIGN_EPS,
                                       support_available=support_available)
        for r in support["rows"]:
            rows.append({
                "run_id": run_id, "target_id": target, "condition": cond,
                "arm": arm,
                "split_id": r["split_id"], "half_a": r["half_a"],
                "half_b": r["half_b"],
                "half_a_value": canonical_num(r["half_a_value"]),
                "half_b_value": canonical_num(r["half_b_value"]),
                "evaluable": r["evaluable"],
                "missing_halves": r["missing_halves"],
                "missing_reason": r["missing_reason"],
                "internal_sign_agreement": r["internal_sign_agreement"],
                "agrees_with_target_estimate": r["agrees_with_main"],
            })
    return rows


def guide_support_rows(target: str, cond: str, slots: list[dict],
                       run_id: Optional[str]) -> list[dict[str, Any]]:
    """One row per (guide slot, arm): that arm's own value for that guide."""
    rows: list[dict[str, Any]] = []
    for s in slots:
        for arm in config.ARMS:
            v = s.get("values", {}).get(arm)
            rows.append({
                "run_id": run_id, "target_id": target, "condition": cond,
                "estimate_id": s["estimate_id"], "guide_id": s["guide_id"],
                "arm": arm,
                "value": canonical_num(v),
                "evaluated": v is not None,
                "unresolved_reason": s["unresolved_reason"],
            })
    return rows
