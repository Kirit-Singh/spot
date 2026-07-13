"""The TYPED disposition: why a run proceeded, or exactly why it refused.

A refusal that is only an exception message is a refusal nobody downstream can read. The
scheduler needs to tell "P2S declined this arm, for this named reason" apart from "P2S
crashed", and a human reading a run directory needs the same thing. So every refusal has an
ENUMERATED reason, and a refused run still emits a disposition record -- it just emits no
support.

REFUSED IS A RESULT. An arm that P2S declined is not an arm P2S has no opinion about; it is
an arm P2S refused to speak for, and the record says which.
"""
from __future__ import annotations

from typing import Any, Optional

DISPOSITION_SCHEMA = "spot.stage02_p2s_arm_disposition.v1"

PROCEEDED = "proceeded"
REFUSED = "refused"

# --------------------------------------------------------------------------- #
# The enumerated refusal reasons. Grouped by what they protect.
# --------------------------------------------------------------------------- #
# -- the W10 admission chain -------------------------------------------------- #
REFUSE_W10_REPORT_MISSING = "w10_report_not_supplied"
REFUSE_W10_REPORT_UNREADABLE = "w10_report_is_not_readable_json"
REFUSE_W10_WRONG_VERIFIER = "w10_report_is_not_from_the_pinned_verifier"
REFUSE_W10_WRONG_CODE = "w10_report_does_not_name_the_pinned_verifier_code"
REFUSE_W10_SPEC_DRIFT = "w10_report_was_written_against_a_different_spec"
REFUSE_W10_NOT_ADMITTED = "w10_did_not_admit_this_bundle"
REFUSE_W10_SELF_ADMITTED = "the_bundle_arrived_admitting_itself"
REFUSE_W10_NOT_INDEPENDENT = "the_verifier_did_not_declare_itself_independent"
REFUSE_W10_REPORT_TAMPERED = "the_w10_report_does_not_hash_to_its_own_content"
REFUSE_W10_REPORT_IS_ABOUT_ANOTHER_BUNDLE = "the_w10_report_is_not_about_this_bundle"

# -- the Direct bundle on disk ------------------------------------------------ #
REFUSE_BUNDLE_MISSING = "direct_bundle_not_supplied"
REFUSE_BUNDLE_INCOMPLETE = "the_direct_bundle_is_missing_a_shipped_file"
REFUSE_BUNDLE_STALE = "the_direct_bundle_on_disk_is_not_the_one_that_was_admitted"
REFUSE_BUNDLE_SWAPPED_FILE = "a_file_in_the_direct_bundle_does_not_hash_to_its_admitted_value"
REFUSE_ALTERED_ROWS = "the_arm_rows_do_not_hash_to_the_bundle_claim"

# -- the environment ---------------------------------------------------------- #
REFUSE_LOCK_ABSENT = "solver_lock_not_supplied"
REFUSE_LOCK_MISMATCH = "solver_lock_is_not_the_pinned_stage2_lock"
REFUSE_LOCK_DISAGREES_WITH_BUNDLE = "the_arms_were_computed_under_a_different_solver_lock"

# -- the lane ----------------------------------------------------------------- #
REFUSE_FIXTURE_INPUT = "a_synthetic_or_fixture_bundle_may_not_carry_production_support"
REFUSE_LANE_MISMATCH = "the_run_lane_is_not_the_lane_the_bundle_was_produced_in"

# -- the arm ------------------------------------------------------------------ #
REFUSE_ARM_NOT_IN_BUNDLE = "arm_is_not_in_the_bound_bundle"
REFUSE_ARM_WRONG_CONDITION = "arm_condition_is_not_the_bundle_condition"
REFUSE_SCORER_MISMATCH = "bundle_scorer_view_does_not_match_the_bound_release"
REFUSE_NOT_BASE_PORTABLE = "program_is_not_base_portable"     # this is how Th9 is refused
REFUSE_SENSITIVITY_LANE = "sensitivity_lane_refused"
REFUSE_RESEARCH_NAMESPACE = "research_namespace_refused"
REFUSE_NO_PANEL = "program_has_no_surviving_panel"
REFUSE_INCOMPATIBLE_ARM = "arm_kind_is_not_answerable_by_this_lane"
REFUSE_RELEASE_UNREADABLE = "the_bound_stage1_release_could_not_be_loaded"

REFUSAL_REASONS = (
    REFUSE_W10_REPORT_MISSING, REFUSE_W10_REPORT_UNREADABLE, REFUSE_W10_WRONG_VERIFIER,
    REFUSE_W10_WRONG_CODE,
    REFUSE_W10_SPEC_DRIFT, REFUSE_W10_NOT_ADMITTED, REFUSE_W10_SELF_ADMITTED,
    REFUSE_W10_NOT_INDEPENDENT, REFUSE_W10_REPORT_TAMPERED,
    REFUSE_W10_REPORT_IS_ABOUT_ANOTHER_BUNDLE,
    REFUSE_BUNDLE_MISSING, REFUSE_BUNDLE_INCOMPLETE, REFUSE_BUNDLE_STALE,
    REFUSE_BUNDLE_SWAPPED_FILE, REFUSE_ALTERED_ROWS,
    REFUSE_LOCK_ABSENT, REFUSE_LOCK_MISMATCH, REFUSE_LOCK_DISAGREES_WITH_BUNDLE,
    REFUSE_FIXTURE_INPUT, REFUSE_LANE_MISMATCH,
    REFUSE_ARM_NOT_IN_BUNDLE, REFUSE_ARM_WRONG_CONDITION, REFUSE_SCORER_MISMATCH,
    REFUSE_NOT_BASE_PORTABLE, REFUSE_SENSITIVITY_LANE, REFUSE_RESEARCH_NAMESPACE,
    REFUSE_NO_PANEL, REFUSE_INCOMPATIBLE_ARM, REFUSE_RELEASE_UNREADABLE,
)


class RefusalError(ValueError):
    """A NAMED refusal. Never a bare exception, and never a silent proceed."""

    def __init__(self, reason: str, message: str):
        super().__init__(f"[{reason}] {message}")
        self.reason = reason
        self.message = message

    def record(self, *, arm_key: Optional[str] = None) -> dict[str, Any]:
        return record(REFUSED, reason=self.reason, detail=self.message, arm_key=arm_key)


def record(state: str, *, reason: Optional[str] = None, detail: str = "",
           arm_key: Optional[str] = None, bound: Optional[dict[str, Any]] = None,
           ) -> dict[str, Any]:
    """The disposition a run emits — whether it proceeded or refused."""
    if state == REFUSED and reason not in REFUSAL_REASONS:
        raise ValueError(
            f"{reason!r} is not an enumerated refusal reason. An unenumerated refusal is a "
            "refusal a consumer cannot branch on, which is how 'declined' becomes "
            "indistinguishable from 'crashed'")
    return {
        "schema_version": DISPOSITION_SCHEMA,
        "state": state,
        "reason": reason,
        "detail": detail,
        "arm_key": arm_key,
        "bound": bound or {},
        "support_emitted": state == PROCEEDED,
    }


# -- input preparation --------------------------------------------------------- #
REFUSE_INPUT_NOT_PINNED = "an_input_does_not_hash_to_its_pin"
REFUSE_DUPLICATE_BARCODE = "the_score_table_carries_a_duplicate_barcode"
REFUSE_MISSING_BARCODE = "a_cell_has_no_stage1_score_row"
REFUSE_NAMESPACE_DRIFT = "gene_namespace_drift_between_the_cells_and_the_readout"
REFUSE_FIXTURE_PATH = "a_fixture_or_synthetic_path_may_not_feed_a_production_run"
REFUSE_CONDITION_MISMATCH = "the_condition_is_not_the_admitted_bundles_condition"
REFUSE_PROGRAM_SET_MISMATCH = "the_score_table_does_not_cover_the_admitted_program_set"
REFUSE_SUBSAMPLE_IN_PRODUCTION = "a_subsampled_cell_matrix_may_not_feed_a_production_run"

REFUSAL_REASONS = REFUSAL_REASONS + (
    REFUSE_INPUT_NOT_PINNED, REFUSE_DUPLICATE_BARCODE, REFUSE_MISSING_BARCODE,
    REFUSE_NAMESPACE_DRIFT, REFUSE_FIXTURE_PATH, REFUSE_CONDITION_MISMATCH,
    REFUSE_PROGRAM_SET_MISMATCH, REFUSE_SUBSAMPLE_IN_PRODUCTION,
)


# -- the real Direct inventory / environment ----------------------------------- #
REFUSE_MASK_MISSING_FOR_ELIGIBLE = "an_eligible_target_has_no_mask_in_the_admitted_bundle"
REFUSE_MASK_SCOPE_UNION = "mask_rows_were_selected_across_estimate_scopes"
REFUSE_MASK_EMPTY = "the_admitted_bundle_ships_no_main_estimate_mask"
REFUSE_ELIGIBLE_EMPTY = "the_admitted_bundle_ships_no_evaluable_target_for_this_arm"
REFUSE_ARM_INVENTORY_ASYMMETRY = "the_two_sign_arms_do_not_share_one_target_inventory"
REFUSE_P2S_LOCK_ABSENT = "p2s_runtime_lock_not_supplied"
REFUSE_P2S_LOCK_MISMATCH = "p2s_runtime_lock_is_not_the_pinned_p2s_lock"
REFUSE_UPSTREAM_TREE_UNPINNED = "the_upstream_model_tree_hash_is_not_the_pinned_one"
REFUSE_ACTIVATION_ARM = "program_is_the_activation_covariate_of_its_own_design"
REFUSE_BARCODE_INVENTORY = "the_cell_and_score_barcode_inventories_are_not_identical"

REFUSAL_REASONS = REFUSAL_REASONS + (
    REFUSE_MASK_MISSING_FOR_ELIGIBLE, REFUSE_MASK_SCOPE_UNION, REFUSE_MASK_EMPTY,
    REFUSE_ELIGIBLE_EMPTY, REFUSE_ARM_INVENTORY_ASYMMETRY,
    REFUSE_P2S_LOCK_ABSENT, REFUSE_P2S_LOCK_MISMATCH, REFUSE_UPSTREAM_TREE_UNPINNED,
    REFUSE_ACTIVATION_ARM, REFUSE_BARCODE_INVENTORY,
)


# -- symbol-namespace target identity ------------------------------------------ #
REFUSE_TARGET_SYMBOL_PRESENT_UNMAPPED = "a_symbol_target_is_in_the_readout_but_not_mapped"

REFUSAL_REASONS = REFUSAL_REASONS + (REFUSE_TARGET_SYMBOL_PRESENT_UNMAPPED,)
