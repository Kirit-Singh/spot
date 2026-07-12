"""ADMISSION: the exact column allowlists and the recursive key-name firewall.

FAIL-CLOSED, BY CONSTRUCTION
---------------------------
The retired verifier used a DENYLIST of exact column names. It refused ``p_value`` and
admitted ``did_pval``, ``q_val_adjusted``, ``significance_padj`` and ``fdr_adjusted``,
because none of those is spelled like a name on the list. Its combined-objective check
was a substring scan that did not include ``weighted`` at all, and nothing recursed, so a
disguised p/q nested one level down in the provenance was never even looked at.

A denylist can only refuse what somebody thought of in advance. That is the wrong shape
for this job: the whole point of the no-p/q rule is that a number which LOOKS like
significance will be READ as significance, and the person adding it will not be trying to
sneak it past a list. So admission is now two independent, fail-closed gates:

  1. AN EXACT COLUMN ALLOWLIST, per emitted file. Every column an artifact ships must be
     on it. An unknown column is a REJECT — not a warning, not a shrug. The allowlist IS
     the contract, and a generator that grows a column has to come here and authorise it.

  2. A RECURSIVE KEY-NAME FIREWALL over every emitted object — parquet columns AND the
     provenance JSON — at ANY nesting depth, case-insensitively. If a key name matches
     the forbidden pattern anywhere in the artifact, the artifact is refused.

THE EXCEPTIONS ARE ENUMERATED, NOT IMPLIED
------------------------------------------
Two kinds, both exact-named and both short enough to audit in one glance.

EXACT-NAME EXEMPTIONS. ``away_from_A_zscore`` and ``toward_B_zscore`` match ``/score/``
and are legitimate: they are the within-condition SENSITIVITY effect layer
(``config.EFFECT_LAYER_SENSITIVITY``), carried verbatim in the endpoint rows, and they
are not an objective — nothing ranks or gates on them. There is no pattern-shaped hole
for a ``combined_zscore`` to walk through: the exemption is the exact spelling, not the
shape.

NEGATIVE DECLARATIONS. ``combined_objective_permitted`` matches ``/combined/`` and is the
artifact stating that a combined objective is FORBIDDEN. A firewall that refused it would
make the artifact unable to write down its own prohibition — the rule would be
unstatable. So it is exempt ONLY while its value is exactly ``False``. Flip it to
``True`` and the firewall fires, which is precisely the event it exists to catch. The
exemption is conditional on the declaration still being a prohibition.
"""
from __future__ import annotations

import re
from typing import Any

# The pattern, exactly as the remediation specifies it. Case-insensitive, matched as a
# SUBSTRING of a key name, so ``did_pval`` and ``empirical_fdr`` are caught along with
# the bare spellings.
FORBIDDEN_KEY_PATTERN = (
    r"p_value|q_value|fdr|pval|padj|combined|balanced|weighted|score")
FORBIDDEN_KEY_RE = re.compile(FORBIDDEN_KEY_PATTERN, re.IGNORECASE)

# The ONLY names exempt from the firewall, by exact spelling. See the module docstring.
KEY_FIREWALL_EXCEPTIONS = frozenset({"away_from_A_zscore", "toward_B_zscore"})

# ...and the NEGATIVE DECLARATIONS: exempt ONLY while they still say "forbidden". The
# artifact has to be able to write down its own prohibition; it does not get to keep the
# exemption after flipping the prohibition off.
NEGATIVE_DECLARATIONS = {"combined_objective_permitted": False}

REQUIRED_FILES = ("temporal.parquet", "endpoints.parquet", "temporal_provenance.json")

TEMPORAL_COLUMNS = frozenset({
    "A_did_over_interaction_std", "A_from_base_qc_passed",
    "A_from_donor_split_denominator", "A_from_evaluable", "A_from_mask_resolved",
    "A_from_n_guide_slots_released", "A_from_n_guides_evaluated",
    "A_from_n_guides_mapped", "A_from_n_splits_evaluable", "A_from_n_splits_total",
    "A_from_projection_status", "A_from_rank", "A_from_state",
    "A_from_support_status", "A_interaction_std", "A_program_id",
    "A_reliability_badge", "A_reliability_comparator", "A_reliability_k",
    "A_reliability_threshold", "A_sparse_panel_caution", "A_temporal_status",
    "A_to_base_qc_passed", "A_to_donor_split_denominator", "A_to_evaluable",
    "A_to_mask_resolved", "A_to_n_guide_slots_released", "A_to_n_guides_evaluated",
    "A_to_n_guides_mapped", "A_to_n_splits_evaluable", "A_to_n_splits_total",
    "A_to_projection_status", "A_to_rank", "A_to_state", "A_to_support_status",
    "B_did_over_interaction_std", "B_from_base_qc_passed",
    "B_from_donor_split_denominator", "B_from_evaluable", "B_from_mask_resolved",
    "B_from_n_guide_slots_released", "B_from_n_guides_evaluated",
    "B_from_n_guides_mapped", "B_from_n_splits_evaluable", "B_from_n_splits_total",
    "B_from_projection_status", "B_from_rank", "B_from_state",
    "B_from_support_status", "B_interaction_std", "B_program_id",
    "B_reliability_badge", "B_reliability_comparator", "B_reliability_k",
    "B_reliability_threshold", "B_sparse_panel_caution", "B_temporal_status",
    "B_to_base_qc_passed", "B_to_donor_split_denominator", "B_to_evaluable",
    "B_to_mask_resolved", "B_to_n_guide_slots_released", "B_to_n_guides_evaluated",
    "B_to_n_guides_mapped", "B_to_n_splits_evaluable", "B_to_n_splits_total",
    "B_to_projection_status", "B_to_rank", "B_to_state", "B_to_support_status",
    "away_from_A_from_value", "away_from_A_temporal_did", "away_from_A_to_value",
    "batch_correction_applied", "batch_partially_confounded", "batch_policy_id",
    "batch_policy_sha256", "batch_status", "batch_status_reason", "comparison_id",
    "confound_rule_id", "direct_config_sha256", "direct_method_version",
    "donors_changing_replicate", "donors_keeping_replicate",
    "donors_only_at_one_condition", "effect_source_sha256", "estimand_id",
    "estimand_is_lineage_traced", "estimand_is_per_cell_fate", "estimand_level",
    "estimator_id", "estimator_version", "formula_id", "from_base_qc_state",
    "from_condition", "from_effective_donor_n", "from_joint_status",
    "from_n_cells_target", "from_pareto_tier", "from_present",
    "from_released_estimate_id", "inference_status", "no_pq_reason",
    "not_identifiable_quantity", "not_identifiable_reason", "refused",
    "schema_version", "sparse_panel_caution", "target_ensembl", "target_id",
    "target_id_namespace", "target_symbol", "temporal_method_sha256",
    "temporal_run_id", "to_base_qc_state", "to_condition", "to_effective_donor_n",
    "to_joint_status", "to_n_cells_target", "to_pareto_tier", "to_present",
    "to_released_estimate_id", "toward_B_from_value", "toward_B_temporal_did",
    "toward_B_to_value",
})

ENDPOINT_COLUMNS = frozenset({
    "A_control_surviving", "A_delta", "A_desired_target_modulation",
    "A_donor_split_denominator", "A_donor_split_support", "A_estimate_available",
    "A_evaluable", "A_evidence_tier", "A_guide_missing_reasons",
    "A_guide_replication_state", "A_guide_replication_supported",
    "A_n_guide_slots_released", "A_n_guides_concordant", "A_n_guides_evaluated",
    "A_n_guides_mapped", "A_n_splits_agreeing", "A_n_splits_evaluable",
    "A_n_splits_internally_concordant", "A_n_splits_internally_discordant",
    "A_n_splits_missing", "A_n_splits_total", "A_panel_surviving",
    "A_projection_status", "A_reasons", "A_state", "A_support_state",
    "A_support_status", "B_control_surviving", "B_delta",
    "B_desired_target_modulation", "B_donor_split_denominator",
    "B_donor_split_support", "B_estimate_available", "B_evaluable", "B_evidence_tier",
    "B_guide_missing_reasons", "B_guide_replication_state",
    "B_guide_replication_supported", "B_n_guide_slots_released",
    "B_n_guides_concordant", "B_n_guides_evaluated", "B_n_guides_mapped",
    "B_n_splits_agreeing", "B_n_splits_evaluable", "B_n_splits_internally_concordant",
    "B_n_splits_internally_discordant", "B_n_splits_missing", "B_n_splits_total",
    "B_panel_surviving", "B_projection_status", "B_reasons", "B_state",
    "B_support_state", "B_support_status", "away_from_A", "away_from_A_zscore",
    "base_qc_passed", "base_qc_reasons", "base_qc_state", "cell_level_support_state",
    "concordance_class", "condition", "contributing_guide_ids", "contributor_source",
    "contributor_status", "crispri_modality", "desired_modulation_agreement",
    "direct_config_sha256", "direct_method_version", "effect_source_sha256",
    "effective_donor_n", "estimate_mask_sha256", "inference_status",
    "joint_ordering_method_id", "joint_status", "mask_gene_count",
    "mask_method_version", "mask_resolved", "mask_unresolved_reason",
    "n_cells_target", "n_guides_source", "pareto_tier", "qc_low_target_expression",
    "qc_ontarget_effect_size", "qc_ontarget_significant", "qc_target_baseMean",
    "rank_away_from_A", "rank_toward_B", "released_estimate_id", "run_id",
    "schema_version", "source_distal_offtarget_flag", "source_neighboring_gene_KD",
    "target_ensembl", "target_id", "target_id_namespace", "target_symbol",
    "temporal_run_id", "toward_B", "toward_B_zscore",
})


ALLOWLISTS = {"temporal.parquet": TEMPORAL_COLUMNS,
              "endpoints.parquet": ENDPOINT_COLUMNS}


def forbidden_keys(obj: Any, path: str = "") -> list[str]:
    """Every key name matching the firewall, at ANY depth, as a dotted path.

    Walks dicts and lists alike: a p-value buried in a list of diagnostics inside a
    comparison block is exactly the shape a disguised one would take, and a scan that
    only looked at the top level would never see it.
    """
    hits: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            here = f"{path}.{key}" if path else str(key)
            if FORBIDDEN_KEY_RE.search(str(key)) and not _exempt(str(key), value):
                hits.append(here)
            hits.extend(forbidden_keys(value, here))
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            hits.extend(forbidden_keys(value, f"{path}[{i}]"))
    return hits


def _exempt(key: str, value: Any) -> bool:
    """Is this matching key one of the enumerated exceptions? See the module docstring."""
    if key in KEY_FIREWALL_EXCEPTIONS:
        return True
    if key in NEGATIVE_DECLARATIONS:
        # exempt ONLY while it still says "forbidden": `is` on the literal, so a truthy
        # 1 or "false" cannot pose as the prohibition
        return value is NEGATIVE_DECLARATIONS[key]
    return False


def column_violations(columns: list[str], filename: str) -> dict[str, list[str]]:
    """UNKNOWN columns and MISSING columns, against this file's exact allowlist.

    Both are refusals. An unknown column is an unauthorised claim; a missing one means
    the artifact is not the thing the contract describes.
    """
    allowed = ALLOWLISTS[filename]
    got = set(columns)
    return {"unknown": sorted(got - set(allowed)),
            "missing": sorted(set(allowed) - got)}
