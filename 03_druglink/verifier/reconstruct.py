"""Independent reconstruction of the arm expansion and every derived classification.

Nothing here is copied from the emitted bundle. The arm-lever table is rebuilt from
Direct's ``screen.parquet``; the intervention effects, translation classes and PK
eligibility are re-derived from the retained SOURCE fields (the verbatim
``action_type_source``, each arm's own Direct modulation, the target entity class).
The bundle's own values are then compared against these — never trusted.
"""
from __future__ import annotations

import math
from typing import Any, Optional

import pandas as pd

from . import policy


def cell(value: Any) -> Any:
    """One cell, canonicalised. Restated, not imported.

    Order matters: parquet round-trips a list column as an ndarray, and ndarray has
    an ``.item()`` that raises for size != 1 — so containers are unwrapped BEFORE any
    scalar coercion is attempted.
    """
    if value is None or value is pd.NA:
        return None
    if isinstance(value, str):
        return value
    if type(value).__name__ == "bool_":
        return bool(value)
    if isinstance(value, dict):
        return {k: cell(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)) or type(value).__name__ == "ndarray":
        return [cell(v) for v in list(value)]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return repr(value)
    return str(value)


def rank(value: Any) -> Optional[int]:
    if value is None or value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return int(value)


def expand_arms(screen: pd.DataFrame, direct_run_id: str) -> list[dict[str, Any]]:
    """Re-derive the (immutable key -> arm facts) mapping straight from the screen.

    Only the fields whose provenance matters are rebuilt; the check is that the
    emitted arm-lever table agrees with THIS on every one of them.
    """
    out: list[dict[str, Any]] = []
    for row in screen.to_dict("records"):
        for arm in policy.ARMS:
            pole = policy.ARM_POLE[arm]
            ensembl = cell(row.get("target_ensembl"))
            out.append({
                "direct_run_id": direct_run_id,
                "released_estimate_id": cell(row.get("released_estimate_id")),
                "target_id_namespace": cell(row.get("target_id_namespace")),
                "target_id": cell(row.get("target_id")),
                "target_ensembl": ensembl,
                "condition": cell(row.get("condition")),
                "desired_arm": arm,
                "arm_value_source_string": cell(row.get(arm)),
                "arm_rank": rank(row.get(policy.ARM_RANK_COLUMN[arm])),
                "arm_evaluable": bool(cell(row.get(f"{pole}_evaluable"))),
                "arm_state": cell(row.get(f"{pole}_state")),
                "arm_evidence_tier": cell(row.get(f"{pole}_evidence_tier")),
                "arm_support_state": cell(row.get(f"{pole}_support_state")),
                "arm_desired_target_modulation": cell(
                    row.get(f"{pole}_desired_target_modulation")),
                "arm_guide_replication_state": cell(
                    row.get(f"{pole}_guide_replication_state")),
                "target_identity_state": (
                    "ensembl_mapped" if ensembl
                    else "unmapped_released_symbol_namespace"),
                "gene_target_drug_edge_permitted": bool(ensembl),
            })
    return out


ARM_FACT_FIELDS = (
    "arm_value_source_string", "arm_rank", "arm_evaluable", "arm_state",
    "arm_evidence_tier", "arm_support_state", "arm_desired_target_modulation",
    "arm_guide_replication_state", "target_identity_state",
    "gene_target_drug_edge_permitted",
)


def key_of(row: dict[str, Any]) -> tuple:
    return tuple(row.get(k) for k in policy.IMMUTABLE_KEY)


def arm_direction_measured(row: dict[str, Any]) -> bool:
    return bool(row["arm_evaluable"]
                and row["arm_value_source_string"] is not None
                and row["arm_rank"] is not None)


def edge_status(edge: dict[str, Any],
                entity_is_single_protein: bool) -> dict[str, Any]:
    """Re-derive an edge's effect + directional status from the SOURCE fields."""
    sources = list(edge.get("action_type_sources") or [])
    effects = {policy.intervention_effect(a) for a in sources} or {
        policy.intervention_effect(edge.get("action_type_normalized"))}
    effect = sorted(effects)[0] if len(effects) == 1 else policy.EFFECT_UNKNOWN
    origin = edge.get("origin_type", policy.ORIGIN_DIRECT_TARGET)

    status, reason = policy.directional_evidence(
        modulation=edge["arm_desired_target_modulation"],
        effect=effect,
        arm_evaluable=bool(edge["arm_evaluable"]),
        single_protein=entity_is_single_protein,
        action_conflict=bool(edge["action_conflict"]),
        origin=origin)
    return {
        "intervention_effect": effect,
        "directional_evidence_status": status,
        "directional_evidence_reason": reason,
        "observed_perturbation_support":
            policy.observed_perturbation_support(status, origin),
        "stage3_evidence_class": policy.evidence_class(status),
    }


def action_conflicts(assertions: list[dict[str, Any]]) -> set[tuple[str, str]]:
    """(form, entity) pairs whose sourced actions point in opposite directions."""
    reducing = {policy.ABUNDANCE_REDUCTION, policy.FUNCTIONAL_INHIBITION}
    increasing = {policy.FUNCTIONAL_ACTIVATION}
    effects: dict[tuple[str, str], set[str]] = {}
    for a in assertions:
        eff = policy.intervention_effect(a.get("action_type_source"))
        if eff in (reducing | increasing):
            effects.setdefault((a["form_id"], a["target_entity_id"]), set()).add(eff)
    return {k for k, v in effects.items() if (v & reducing) and (v & increasing)}
