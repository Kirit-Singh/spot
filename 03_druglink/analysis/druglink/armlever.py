"""Deterministic two-arm expansion of a verified Direct screen.

Direct asks TWO questions — move AWAY from A, and move TOWARD B — and answers them
separately, with independent evaluability, support, tiers, nullable ranks and
desired modulations. Stage 3 must carry both, so one Direct screen row becomes
exactly TWO arm-lever rows, ALWAYS, including when an arm is not evaluable.

The frozen mapping (an A row may never read a B field, and reciprocally):

    away_from_A   value ``away_from_A``    rank ``rank_away_from_A``   fields ``A_*``
    toward_B      value ``toward_B``       rank ``rank_toward_B``      fields ``B_*``

The immutable key is

    (direct_run_id, released_estimate_id, target_id_namespace, target_id,
     target_ensembl, condition, desired_arm)

``target_ensembl`` may be null. A row whose target is still in the released SYMBOL
namespace is never discarded — it gets an explicit unmapped disposition and is
barred from every gene-target drug edge, because a symbol is not an accession.

Three properties are enforced rather than hoped for:

  * **No collapse.** A duplicate immutable key is fatal. There is no last-row-wins:
    the previous build's ``{target_ensembl: lever}`` dict silently kept the last row,
    so reversing two opposite-direction rows reversed the science.
  * **No order dependence.** Rows are emitted in immutable-key order and hashed
    order-invariantly, so permuting the input screen is byte-identical.
  * **No combined objective.** There is no mean, balanced, best-of, primary,
    headline or overall score or rank here or anywhere downstream. A target that
    moves away from A while OPPOSING B must never buy rank with its A score.

Floats never enter a content hash (see :mod:`druglink.hashing`): every magnitude is
carried as its exact lossless source string plus a canonical decimal string, so two
distinct float64 values can never hash alike.
"""
from __future__ import annotations

import math
from typing import Any, Optional

import pandas as pd

from . import joint_context
from .direction import ORIGIN_DIRECT_TARGET
from .hashing import canonical_decimal, content_hash, short_id

ARM_A = "away_from_A"
ARM_B = "toward_B"
ARMS = (ARM_A, ARM_B)
ARM_POLE = {ARM_A: "A", ARM_B: "B"}
ARM_RANK_COLUMN = {ARM_A: "rank_away_from_A", ARM_B: "rank_toward_B"}

ARMLEVER_POLICY_VERSION = "stage3-armlever-v1-two-arm"

# Every known alias of a combined objective or a headline rank. Stage 3 neither
# produces nor accepts one; a Direct screen carrying one is refused on load.
BANNED_OBJECTIVE_COLUMNS = frozenset({
    "combination", "combination_score", "combination_state", "combined_score",
    "combined_rank", "balanced_score", "balanced_skew", "balanced_a_to_b",
    "composite_score", "total_skew", "overall_score", "overall_rank",
    "aggregate_score", "mean_arm_score", "arms_both_positive",
    "rank", "primary_rank", "rank_primary", "headline_rank", "best_arm",
    "best_of_arms", "primary_arm", "headline_arm",
})

# The per-pole suffixes an arm row reads from ITS OWN pole, and nothing else.
POLE_SUFFIXES = (
    "delta", "panel_surviving", "control_surviving", "projection_status",
    "support_status", "evaluable", "state", "reasons", "estimate_available",
    "desired_target_modulation", "guide_replication_state",
    "guide_replication_supported", "n_guide_slots_released", "n_guides_mapped",
    "n_guides_evaluated", "n_guides_concordant", "guide_missing_reasons",
    "n_splits_total", "n_splits_evaluable", "n_splits_missing",
    "n_splits_internally_concordant", "n_splits_internally_discordant",
    "n_splits_agreeing", "donor_split_support", "donor_split_denominator",
    "support_state", "evidence_tier",
)

# Row-level (arm-independent) Direct columns. Base QC is pre-outcome and a function
# of NEITHER arm, so both arm rows may carry it without either reading the other.
SHARED_COLUMNS = (
    "released_estimate_id", "target_id", "target_id_namespace", "target_symbol",
    "target_ensembl", "condition", "base_qc_state", "base_qc_passed",
    "base_qc_reasons", "mask_resolved", "mask_unresolved_reason", "mask_gene_count",
    "contributing_guide_ids", "contributor_status", "contributor_source",
    "n_cells_target", "n_guides_source", "effective_donor_n", "crispri_modality",
    "inference_status", "cell_level_support_state",
)

# Descriptive cross-arm columns. They are emitted in their OWN table and are never
# read by any arm row, ranking, filter or gate: a conflict is a finding, not a tie
# to be broken.
CROSS_ARM_COLUMNS = ("concordance_class", "desired_modulation_agreement")
# Stage-2 joint context is appended to the cross-arm row: context, not direction.
JOINT_CONTEXT_COLUMNS = joint_context.ACCEPTED_FIELDS

IMMUTABLE_KEY = ("direct_run_id", "released_estimate_id", "target_id_namespace",
                 "target_id", "target_ensembl", "condition", "desired_arm")

ENSEMBL_MAPPED = "ensembl_mapped"
UNMAPPED_SYMBOL = "unmapped_released_symbol_namespace"


class ArmLeverError(ValueError):
    """The Direct screen cannot be expanded into two independent arms."""


def _cell(value: Any) -> Any:
    """One Direct cell, canonicalised. A float becomes its exact decimal string.

    ``repr(float(v))`` round-trips a float64 exactly, so 4.0e-7 and 4.9e-7 stay
    distinct; :func:`canonical_decimal` then gives them a single canonical form.
    Nothing is rounded, and no float ever reaches a content hash.
    """
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (bool,)) or type(value).__name__ == "bool_":
        return bool(value)
    if isinstance(value, str):
        return value
    # Containers first: parquet returns a list column as an ndarray, whose .item()
    # raises for size != 1.
    if isinstance(value, dict):
        return {k: _cell(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)) or type(value).__name__ == "ndarray":
        return [_cell(v) for v in list(value)]
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


def _magnitude(value: Any) -> tuple[Optional[str], Optional[str]]:
    """(exact source string, canonical decimal string) for one numeric cell."""
    cell = _cell(value)
    if cell is None:
        return None, None
    text = str(cell)
    return text, canonical_decimal(text)


def _rank(value: Any) -> Optional[int]:
    """A nullable rank stays NULL. It is never coerced to 0, -1 or NaN."""
    if value is None or value is pd.NA:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return int(value)


def _arm_row(row: dict[str, Any], arm: str, direct_run_id: str) -> dict[str, Any]:
    """Build ONE arm's lever row, reading only that arm's own fields."""
    pole = ARM_POLE[arm]
    value_source, value_decimal = _magnitude(row.get(arm))
    delta_source, delta_decimal = _magnitude(row.get(f"{pole}_delta"))
    rank = _rank(row.get(ARM_RANK_COLUMN[arm]))
    evaluable = bool(_cell(row.get(f"{pole}_evaluable")))

    ensembl = _cell(row.get("target_ensembl"))
    identity_state = ENSEMBL_MAPPED if ensembl else UNMAPPED_SYMBOL

    out: dict[str, Any] = {
        "direct_run_id": direct_run_id,
        "desired_arm": arm,
        # This gene WAS perturbed. A pathway node (see druglink.pathways) was not, and
        # carries origin_type=pathway_node. The two never merge.
        "origin_type": ORIGIN_DIRECT_TARGET,
    }
    for col in SHARED_COLUMNS:
        out[col] = _cell(row.get(col))

    out.update({
        "arm_value_source_string": value_source,
        "arm_value_canonical_decimal": value_decimal,
        "arm_delta_source_string": delta_source,
        "arm_delta_canonical_decimal": delta_decimal,
        "arm_rank": rank,
        "arm_evaluable": evaluable,
        "target_identity_state": identity_state,
        # An unmapped symbol cannot become an accession, so it can never enter a
        # gene-target drug edge. It stays fully inspectable.
        "gene_target_drug_edge_permitted": identity_state == ENSEMBL_MAPPED,
        # The arm was actually evaluated AND carries a real, ranked direction. This is
        # a property of the SCREEN. It is not an eligibility and not a promotion flag.
        "arm_direction_measured": bool(
            evaluable and value_source is not None and rank is not None),
    })
    for suffix in POLE_SUFFIXES:
        if suffix in ("delta", "evaluable"):
            continue                      # already emitted, canonicalised, above
        out[f"arm_{suffix}"] = _cell(row.get(f"{pole}_{suffix}"))

    out["arm_lever_key"] = content_hash({k: out[k] for k in IMMUTABLE_KEY})
    out["arm_lever_id"] = short_id(out)
    return out


def expand(screen: pd.DataFrame, *, direct_run_id: str) -> dict[str, Any]:
    """One Direct screen -> exactly two arm-lever rows per screen row.

    Returns ``{arm_levers, cross_arm, dispositions, counts}``. Emission order is the
    immutable key, so a permuted input screen produces byte-identical content.
    """
    banned = sorted(BANNED_OBJECTIVE_COLUMNS.intersection(screen.columns))
    if banned:
        raise ArmLeverError(
            f"the Direct screen carries a combined/headline objective column {banned}; "
            "Stage 3 refuses to consume one")

    records = screen.to_dict("records")
    rows: list[dict[str, Any]] = []
    cross_arm: list[dict[str, Any]] = []
    dispositions: list[dict[str, Any]] = []

    seen: dict[tuple, int] = {}
    for i, row in enumerate(records):
        for arm in ARMS:
            arm_row = _arm_row(row, arm, direct_run_id)
            key = tuple(arm_row[k] for k in IMMUTABLE_KEY)
            if key in seen:
                # No last-row-wins. Two rows claiming one (target, arm) means the
                # science depends on input order, which is not science.
                raise ArmLeverError(
                    "duplicate immutable arm-lever key (input rows "
                    f"{seen[key]} and {i}): {dict(zip(IMMUTABLE_KEY, key))}")
            seen[key] = i
            rows.append(arm_row)

        cross = {"direct_run_id": direct_run_id,
                 "released_estimate_id": _cell(row.get("released_estimate_id")),
                 "target_id": _cell(row.get("target_id")),
                 "target_id_namespace": _cell(row.get("target_id_namespace")),
                 "target_ensembl": _cell(row.get("target_ensembl")),
                 "condition": _cell(row.get("condition"))}
        for col in CROSS_ARM_COLUMNS:
            cross[col] = _cell(row.get(col))
        # Stage-2 joint context, verbatim. TYPED, never numeric, and never read by the
        # direction engine — there is no parameter through which it could reach it.
        cross.update(joint_context.from_screen_row(row))
        cross["descriptive_only"] = True
        cross_arm.append(cross)

        if not _cell(row.get("target_ensembl")):
            dispositions.append({
                "subject_kind": "arm_lever_target",
                "subject_id": str(_cell(row.get("target_id"))),
                "state": UNMAPPED_SYMBOL,
                "reason": "released_target_is_a_symbol_not_an_accession",
                "detail": (f"target_id_namespace="
                           f"{_cell(row.get('target_id_namespace'))}; retained for "
                           "inspection, barred from every gene-target drug edge"),
                "source_record_id": None,
            })

    rows.sort(key=lambda r: tuple("" if r[k] is None else str(r[k])
                                  for k in IMMUTABLE_KEY))
    cross_arm.sort(key=lambda r: (str(r["target_id"]), str(r["released_estimate_id"])))

    if len(rows) != 2 * len(records):
        raise ArmLeverError(
            f"expected exactly {2 * len(records)} arm rows for {len(records)} screen "
            f"rows; produced {len(rows)}")

    counts = {
        "n_screen_rows": len(records),
        "n_arm_levers": len(rows),
        "n_unique_immutable_keys": len(seen),
        "per_arm": {
            arm: {
                "n_rows": sum(1 for r in rows if r["desired_arm"] == arm),
                "n_evaluable": sum(1 for r in rows if r["desired_arm"] == arm
                                   and r["arm_evaluable"]),
                "n_ranked": sum(1 for r in rows if r["desired_arm"] == arm
                                and r["arm_rank"] is not None),
                "n_arm_direction_measured": sum(
                    1 for r in rows if r["desired_arm"] == arm
                    and r["arm_direction_measured"]),
                "n_ensembl_mapped": sum(
                    1 for r in rows if r["desired_arm"] == arm
                    and r["target_identity_state"] == ENSEMBL_MAPPED),
            } for arm in ARMS},
    }
    return {"arm_levers": rows, "cross_arm": cross_arm,
            "dispositions": dispositions, "counts": counts}


def index_by_key(arm_levers: list[dict[str, Any]]
                 ) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Levers keyed by (target_ensembl, desired_arm, origin_type).

    Never by gene alone, and never by gene+arm alone: a gene that is BOTH a measured
    direct target and an inferred pathway node holds two DIFFERENT levers, and merging
    them would let an inference borrow a measurement's evidence.

    Only Ensembl-mapped rows are indexed: an unmapped symbol has no accession to join
    a drug target on.
    """
    out: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in arm_levers:
        if not row["gene_target_drug_edge_permitted"]:
            continue
        key = (row["target_ensembl"], row["desired_arm"],
               row.get("origin_type", ORIGIN_DIRECT_TARGET))
        if key in out:
            raise ArmLeverError(
                f"duplicate (target_ensembl, desired_arm, origin_type) key: {key}")
        out[key] = row
    return out


def select_acquisition_targets(arm_levers: list[dict[str, Any]], *,
                               top_per_arm: int) -> list[dict[str, Any]]:
    """The frozen acquisition queue: top N per arm, INDEPENDENTLY, by that arm's rank.

    Selection is per arm and never pooled: a target's A rank can never promote it
    into B's queue. The union is taken only so the network is not asked the same
    question twice; every query target retains the arm and rank that selected it.

    This list is frozen and bound into the acquisition ID BEFORE any response is
    inspected. There is no adaptive expansion and no stop-when-enough-drugs-found:
    zero candidates is a valid result.
    """
    if top_per_arm < 0:
        raise ArmLeverError(f"top_per_arm must be >= 0; got {top_per_arm}")

    picks: list[dict[str, Any]] = []
    for arm in ARMS:
        eligible = [r for r in arm_levers
                    if r["desired_arm"] == arm
                    and r["target_identity_state"] == ENSEMBL_MAPPED
                    and r["arm_evaluable"]
                    and r["arm_rank"] is not None]
        eligible.sort(key=lambda r: (r["arm_rank"], r["target_ensembl"]))
        for row in eligible[:top_per_arm]:
            picks.append({
                "target_ensembl": row["target_ensembl"],
                "target_id": row["target_id"],
                "desired_arm": arm,
                "arm_rank": row["arm_rank"],
                "arm_evidence_tier": row["arm_evidence_tier"],
                "arm_desired_target_modulation": row["arm_desired_target_modulation"],
                "arm_lever_key": row["arm_lever_key"],
            })
    picks.sort(key=lambda p: (p["desired_arm"], p["arm_rank"], p["target_ensembl"]))
    return picks


def query_genes(targets: list[dict[str, Any]]) -> list[str]:
    """The deduplicated, sorted gene list actually sent to the network."""
    return sorted({t["target_ensembl"] for t in targets})


def vocabularies() -> dict[str, Any]:
    """The frozen arm vocabulary, hashed into every Stage-3 ID."""
    return {
        "armlever_policy_version": ARMLEVER_POLICY_VERSION,
        "arms": list(ARMS),
        "arm_pole": dict(ARM_POLE),
        "arm_rank_column": dict(ARM_RANK_COLUMN),
        "immutable_key": list(IMMUTABLE_KEY),
        "pole_suffixes": list(POLE_SUFFIXES),
        "cross_arm_columns": list(CROSS_ARM_COLUMNS),
        "cross_arm_rule": "descriptive_only_never_ranks_filters_or_resolves_an_arm",
        "banned_objective_columns": sorted(BANNED_OBJECTIVE_COLUMNS),
        "combined_objective_permitted": False,
        "headline_arm_permitted": False,
        "duplicate_key_rule": "fatal_no_last_row_wins",
        "nullable_rank_rule": "null_rank_stays_null_never_coerced",
        "unmapped_symbol_rule": "retained_as_disposition_barred_from_gene_drug_edges",
    }
