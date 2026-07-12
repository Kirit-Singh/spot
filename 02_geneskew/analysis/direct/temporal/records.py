"""One temporal record per (target, ordered condition pair). Pure assembly.

Both arms, both endpoints, always. A record carries:

  * each arm's WITHIN-CONDITION value at each endpoint — the exact number the screen
    published for that condition — and the difference between them;
  * each arm's own rank at each endpoint, over that endpoint's own population;
  * the joint status and Pareto tier at each endpoint;
  * the donor and guide denominators at each endpoint;
  * the batch status, the reliability badge and the exact threshold it was judged
    against, and the not-identifiable note.

The arms never merge. There is no combined temporal score, no averaged DiD, and no
function here that could produce one — the within-condition prohibition applies to the
difference of two within-condition values exactly as it applies to the values.
"""
from __future__ import annotations

from typing import Any, Optional

from .. import config as direct_config
from ..hashing import canonical_num
from ..pareto import STATUS_COLUMN, TIER_COLUMN
from . import config, estimand

SCHEMA_TEMPORAL = "spot.stage02_temporal.v1"

# The per-endpoint accounting a reader needs to know what the denominators WERE.
ENDPOINT_DENOMINATORS = ("n_guide_slots_released", "n_guides_mapped",
                         "n_guides_evaluated", "n_splits_total",
                         "n_splits_evaluable", "donor_split_denominator")

# pole -> arm column, taken from the direct lane's own frozen names.
POLE_ARM = {p: a for a, p in direct_config.ARM_POLE.items()}
POLES = ("A", "B")


def comparison_id(from_condition: str, to_condition: str) -> str:
    return f"{from_condition}__to__{to_condition}"


def _arm_endpoint(row: Optional[dict[str, Any]], pole: str,
                  end: str) -> dict[str, Any]:
    """One arm's fields at ONE endpoint, prefixed ``{pole}_{from|to}_``.

    ``row is None`` means the release ships no estimate for this target at this
    condition. Every field is then null and the ABSENT status says so — a zero here
    would be a measurement the release never made.
    """
    arm = POLE_ARM[pole]
    p = f"{pole}_{end}"
    if row is None:
        fields: dict[str, Any] = {
            f"{p}_evaluable": False, f"{p}_state": None, f"{p}_support_status": None,
            f"{p}_rank": None, f"{p}_base_qc_passed": None,
            f"{p}_projection_status": None, f"{p}_mask_resolved": None,
        }
        fields.update({f"{p}_{d}": None for d in ENDPOINT_DENOMINATORS})
        return fields
    fields = {
        f"{p}_evaluable": bool(row[f"{pole}_evaluable"]),
        f"{p}_state": row[f"{pole}_state"],
        f"{p}_support_status": row[f"{pole}_support_status"],
        f"{p}_rank": row[direct_config.ARM_RANK_COLUMN[arm]],
        f"{p}_base_qc_passed": bool(row["base_qc_passed"]),
        f"{p}_projection_status": row[f"{pole}_projection_status"],
        f"{p}_mask_resolved": bool(row["mask_resolved"]),
    }
    fields.update({f"{p}_{d}": row[f"{pole}_{d}"] for d in ENDPOINT_DENOMINATORS})
    return fields


def _endpoint_common(row: Optional[dict[str, Any]], end: str) -> dict[str, Any]:
    """The per-endpoint facts that belong to the TARGET, not to one arm."""
    if row is None:
        return {f"{end}_released_estimate_id": None, f"{end}_joint_status": None,
                f"{end}_pareto_tier": None, f"{end}_present": False,
                f"{end}_base_qc_state": None, f"{end}_n_cells_target": None,
                f"{end}_effective_donor_n": None}
    return {
        f"{end}_released_estimate_id": row["released_estimate_id"],
        f"{end}_joint_status": row[STATUS_COLUMN],
        f"{end}_pareto_tier": row[TIER_COLUMN],
        f"{end}_present": True,
        f"{end}_base_qc_state": row["base_qc_state"],
        f"{end}_n_cells_target": row["n_cells_target"],
        f"{end}_effective_donor_n": row["effective_donor_n"],
    }


def temporal_record(*, target_id: str, from_condition: str, to_condition: str,
                    from_row: Optional[dict[str, Any]],
                    to_row: Optional[dict[str, Any]],
                    programs: dict[str, str], batch: dict[str, Any],
                    pol, identity_hashes: dict[str, Any],
                    k: float = config.RELIABILITY_K) -> dict[str, Any]:
    """One complete cross-condition record for one target and one ORDERED pair."""
    present = from_row or to_row
    assert present is not None, "a record needs at least one endpoint to exist at"

    row: dict[str, Any] = {
        "schema_version": SCHEMA_TEMPORAL,
        "temporal_run_id": None,                 # filled once the run is named
        # --- what produced this record, ON the record ---
        "estimator_id": config.ESTIMATOR_ID,
        "estimator_version": config.ESTIMATOR_VERSION,
        "temporal_method_sha256": None,          # filled once the method is hashed
        "estimand_id": config.ESTIMAND_ID,
        "estimand_level": config.ESTIMAND_LEVEL,
        "estimand_is_per_cell_fate": config.ESTIMAND_IS_PER_CELL_FATE,
        "estimand_is_lineage_traced": config.ESTIMAND_IS_LINEAGE_TRACED,
        "formula_id": config.FORMULA_ID,
        # the endpoints were built by the UNCHANGED within-condition machinery, and the
        # record names the exact method and frozen config that built them
        "direct_method_version": identity_hashes["direct_method_version"],
        "direct_config_sha256": identity_hashes["direct_config_sha256"],
        "effect_source_sha256": identity_hashes["effect_source_sha256"],
        # --- the comparison ---
        "comparison_id": comparison_id(from_condition, to_condition),
        "from_condition": from_condition,
        "to_condition": to_condition,
        # --- target identity (stable across conditions; the release key is not) ---
        "target_id": target_id,
        "target_id_namespace": present["target_id_namespace"],
        "target_symbol": present["target_symbol"],
        "target_ensembl": present["target_ensembl"],
        # --- no calibrated null, so no p and no q ---
        "inference_status": config.INFERENCE_STATUS,
        "no_pq_reason": config.NO_PQ_REASON,
    }
    row.update(_endpoint_common(from_row, "from"))
    row.update(_endpoint_common(to_row, "to"))

    # --- the two arms, each entirely on its own ---
    sparse_any = False
    for pole in POLES:
        arm = POLE_ARM[pole]
        program = programs[pole]
        row.update(_arm_endpoint(from_row, pole, "from"))
        row.update(_arm_endpoint(to_row, pole, "to"))

        from_value = None if from_row is None else from_row[arm]
        to_value = None if to_row is None else to_row[arm]
        did = estimand.temporal_did(from_value, to_value)
        status = estimand.temporal_status(
            from_present=from_row is not None, to_present=to_row is not None,
            from_evaluable=bool(from_row and from_row[f"{pole}_evaluable"]),
            to_evaluable=bool(to_row and to_row[f"{pole}_evaluable"]))
        # A value that exists but is not evaluable is NOT differenced: the within-
        # condition lane declined to score that arm there, and a difference built on a
        # declined score would smuggle it back in under a new name.
        if status != estimand.ESTIMATED:
            did = None

        rel = estimand.reliability(did=did,
                                   interaction_std=pol.interaction_std(program), k=k)
        caution = pol.sparse_panel_caution(program)
        sparse_any = sparse_any or caution

        row.update({
            f"{arm}_from_value": canonical_num(from_value),
            f"{arm}_to_value": canonical_num(to_value),
            f"{arm}_temporal_did": canonical_num(did),
            f"{pole}_temporal_status": status,
            f"{pole}_program_id": program,
            f"{pole}_reliability_badge": rel["reliability_badge"],
            f"{pole}_reliability_threshold": canonical_num(
                rel["reliability_threshold"]),
            f"{pole}_reliability_k": rel["reliability_k"],
            f"{pole}_reliability_comparator": rel["reliability_comparator"],
            f"{pole}_interaction_std": canonical_num(rel["interaction_std"]),
            f"{pole}_did_over_interaction_std": canonical_num(
                rel["did_over_interaction_std"]),
            f"{pole}_sparse_panel_caution": caution,
        })

    # --- the batch confound, as MACHINE fields (methods-only; the UI shows none of it) ---
    row.update({
        "batch_status": batch["batch_status"],
        "batch_partially_confounded": batch["batch_partially_confounded"],
        "batch_status_reason": batch["batch_status_reason"],
        "batch_correction_applied": batch["batch_correction_applied"],
        "confound_rule_id": batch["confound_rule_id"],
        "donors_changing_replicate": ";".join(batch["donors_changing_replicate"]),
        "donors_keeping_replicate": ";".join(batch["donors_keeping_replicate"]),
        "donors_only_at_one_condition": ";".join(
            batch["donors_only_at_one_condition"]),
        "not_identifiable_quantity": batch["not_identifiable_quantity"],
        "not_identifiable_reason": batch["not_identifiable_reason"],
        "refused": batch["refused"],
        "sparse_panel_caution": sparse_any,
        "batch_policy_id": pol.policy_id,
        "batch_policy_sha256": pol.sha256,
    })
    return row


def emit_order(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable emission order. Deliberately NOT sorted by any DiD — that would be a
    headline temporal rank, and this estimator has none."""
    return sorted(rows, key=lambda r: (r["comparison_id"], r["target_id"]))
