"""The emitted-column contract: an allowlist, plus every forbidden alias.

A denylist alone cannot hold: a combined objective can always be given a new name.
So screen.parquet is validated against an EXACT allowlist, and the known aliases of
a combined objective / headline rank are additionally named so the failure message
says what actually happened.

The standalone verifier reimplements this contract independently.
"""
from __future__ import annotations

from . import config

FORBIDDEN_PQ_COLUMNS = frozenset({
    "p_value", "pvalue", "p_val", "pval", "q_value", "qvalue", "q_val", "qval",
    "padj", "adj_p_value", "fdr", "significance", "p_adj",
})

# Retired vocabulary. Two families, both fatal if they reappear:
#   (a) v2 schema residue;
#   (b) ANY combined/balanced/averaged objective, or a headline "the" rank --
#       these are exactly the shapes that make the second dropdown decorative.
FORBIDDEN_LEGACY_COLUMNS = frozenset({
    "toward_b", "contrast_id", "primary_endpoint", "desired_target_modulation",
    "is_eligible", "eligibility_state",
})

# EVERY known alias of a combined objective. A combined score is forbidden under
# any name, so the check is an allowlist AND a denylist.
COMBINED_OBJECTIVE_ALIASES = frozenset({
    "combination", "combination_score", "combination_state", "combined_score",
    "balanced_score", "balanced_skew", "balanced_a_to_b", "composite_score",
    "total_skew", "overall_score", "aggregate_score", "mean_arm_score",
    "arms_both_positive",
})
HEADLINE_RANK_ALIASES = frozenset({
    "rank", "primary_rank", "rank_primary", "headline_rank", "overall_rank",
})


def screen_column_allowlist() -> frozenset:
    """The EXACT set of columns screen.parquet may contain.

    An allowlist, not a denylist: an arbitrary extra score or rank column is a
    contract violation even if nobody thought to ban its name.
    """
    base = {
        "schema_version", "run_id", "released_estimate_id", "target_id",
        "target_id_namespace", "target_symbol", "target_ensembl", "condition",
        "base_qc_state", "base_qc_passed", "base_qc_reasons",
        "mask_resolved", "mask_unresolved_reason", "mask_gene_count",
        "contributing_guide_ids", "contributor_status", "contributor_source",
        "n_cells_target", "n_guides_source", "qc_ontarget_significant",
        "qc_ontarget_effect_size", "qc_low_target_expression", "qc_target_baseMean",
        "source_distal_offtarget_flag", "source_neighboring_gene_KD",
        "effective_donor_n", "crispri_modality", "inference_status",
        "cell_level_support_state", "concordance_class",
        "desired_modulation_agreement",
    }
    for arm in config.ARMS:
        p = config.ARM_POLE[arm]
        base |= {arm, f"{arm}_zscore", config.ARM_RANK_COLUMN[arm]}
        base |= {f"{p}_{suffix}" for suffix in (
            "delta", "panel_surviving", "control_surviving", "projection_status",
            "support_status", "evaluable", "state", "reasons", "estimate_available",
            "desired_target_modulation", "guide_replication_state",
            "guide_replication_supported", "n_guide_slots_released",
            "n_guides_mapped", "n_guides_evaluated", "n_guides_concordant",
            "guide_missing_reasons", "n_splits_total", "n_splits_evaluable",
            "n_splits_missing", "n_splits_internally_concordant",
            "n_splits_internally_discordant", "n_splits_agreeing",
            "donor_split_support", "donor_split_denominator", "support_state",
            "evidence_tier")}
    return frozenset(base)


