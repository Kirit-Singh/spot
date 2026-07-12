"""Frozen policy for the temporal cross-condition estimator.

Generic: no program ids, no condition names, no dataset hashes. WHICH conditions exist
comes from the release; WHICH confound policy applies to them comes from ``policy.py``,
which is loaded from a frozen, hash-pinned diagnostic artifact rather than guessed here.

THE ESTIMAND, STATED ONCE
-------------------------
For a target and an ORDERED condition pair (from_condition -> to_condition), and for
each arm independently:

    temporal_did(arm) = arm_value(arm, to_condition) - arm_value(arm, from_condition)

where ``arm_value`` is EXACTLY the within-condition Stage-2 direct arm value — the
masked program projection of the pooled-main effect vector, scored by the same code
that produces ``screen.parquet``. Both endpoints are recomputed by that same machinery;
nothing is re-derived, re-scaled or re-fitted here.

WHAT IT IS: a difference in a POPULATION-LEVEL program projection between two condition
populations. The within-condition arm value is already a difference (panel mean minus
control mean, after the estimate's own contributor mask), so the cross-condition
difference of the two is a difference-in-differences.

WHAT IT IS NOT: it is NOT lineage tracing, NOT fate mapping, NOT a per-cell transition
probability, and NOT a rate. No cell is followed from one condition to the next — the
conditions are separate cell populations, separately fitted by the release. A reader who
takes this for a trajectory has been misled, so the estimator emits no rate, no
velocity, no slope and no elapsed time, and there is no function anywhere in this
subpackage that would produce one.

NO CALIBRATED NULL
------------------
There is no null distribution for this projection, so there is no p, no q, and no
significance. ``inference_status`` is ``not_calibrated`` and stays that way. The
reliability badge below is a PRECISION statement — is this movement larger than the
donor/batch interaction spread of its own program? — and it is not, and must never be
presented as, a test.
"""
from __future__ import annotations

# --------------------------------------------------------------------------- #
# Estimator identity (enters the temporal method hash and the temporal run id).
# --------------------------------------------------------------------------- #
ESTIMATOR_ID = "spot.stage02.temporal_cross_condition.v1"
ESTIMATOR_VERSION = "stage2-temporal-cross-condition-v1-did-on-program-projections"
FORMULA_ID = "spot.stage02.temporal.formula.cross_condition_did.v1"
FORMULA_EXPR = "temporal_did(arm) = arm_value(arm, to_cond) - arm_value(arm, from_cond)"

ESTIMAND_ID = "spot.stage02.temporal.estimand.population_program_projection_shift.v1"
ESTIMAND_LEVEL = "population"
ESTIMAND_IS_PER_CELL_FATE = False
ESTIMAND_IS_LINEAGE_TRACED = False
NOT_A_FATE_CLAIM_RULE_ID = "spot.stage02.temporal.rule.not_lineage_or_fate.v1"

# No calibrated null for this projection -> no p, no q, ever.
INFERENCE_STATUS = "not_calibrated"
NO_PQ_REASON = "no_calibrated_null_for_this_cross_condition_projection"

# --------------------------------------------------------------------------- #
# Direction policy: every ordered pair, both ways, none refused.
# --------------------------------------------------------------------------- #
# All ordered pairs of released conditions are computed. A confounded pair is FLAGGED
# and BADGED, never withheld: suppressing a comparison hides the confound instead of
# reporting it, and the reader cannot audit what was never emitted.
ALL_ORDERED_PAIRS = True
PAIRS_MAY_BE_REFUSED = False
DIRECTION_RULE_ID = "spot.stage02.temporal.rule.all_ordered_pairs_both_directions.v1"

# --------------------------------------------------------------------------- #
# Reliability: |DiD| against k x interaction_std(program).
# --------------------------------------------------------------------------- #
# k is frozen BEFORE any temporal result was looked at. It comes from the batch
# diagnostic's recommendation (k ~ 2), and it is emitted on every record alongside the
# exact threshold it produced, so a consumer never has to trust the badge alone.
RELIABILITY_K = 2.0
RELIABILITY_RULE_ID = "spot.stage02.temporal.rule.did_vs_k_times_interaction_std.v1"
RELIABILITY_IS_A_SIGNIFICANCE_TEST = False
RELIABILITY_COMPARATOR = "abs_did_ge_k_times_interaction_std"

# WHAT THE FLOOR IS, AND WHAT IT IS NOT (M6). The earlier wording claimed the
# batch x perturbation interaction "does not bias the DiD" because it is donor noise
# "symmetric across shared donors". That symmetry is an ASSUMPTION, it is UNVERIFIED, and
# it cannot be verified in this design — batch is perfectly aliased with donor, so an
# interaction that is not symmetric across the donors that flip replicate would bias a
# Stim48hr DiD and nothing here could see it. These fields ship on the artifact so the
# limitation travels with the number instead of living only in a document.
RELIABILITY_FLOOR_KIND = "uncalibrated_donor_batch_interaction_reference_floor"
RELIABILITY_FLOOR_IS_CALIBRATED = False
RELIABILITY_ABSENCE_OF_BIAS_CLAIMED = False
RELIABILITY_SYMMETRY_ASSUMPTION = (
    "the interaction is assumed symmetric across the donors shared by the two endpoints; "
    "this is UNVERIFIED and is not verifiable in this design (batch is aliased with "
    "donor), so no absence-of-bias claim is made")
RELIABILITY_SCALE_CAVEAT = (
    "the diagnostic's interaction_std was computed on UNMASKED program projections over "
    "all released targets; the estimator's arm values are TARGET-SPECIFIC MASKED "
    "projections. The two scales are close but not guaranteed to match, so a badge near "
    "the threshold means 'near the reference floor', not 'measured against this target's "
    "own noise'")

# --------------------------------------------------------------------------- #
# Display policy (user decision, recorded so the artifact cannot drift from it).
# --------------------------------------------------------------------------- #
# METHODS-ONLY. The batch flag and the reliability badge are MACHINE fields, emitted for
# provenance and methods traceability. The UI shows every comparison plainly: no inline
# batch flag, no per-comparison caveat, no hidden or filtered rows. The 48hr batch
# confound and the precision limitation are documented ONCE, in the Stage-2 methods doc,
# and surfaced through the methods/provenance drawer.
DISPLAY_POLICY_ID = "spot.stage02.temporal.display_policy.methods_only_no_inline_flag.v1"
UI_RENDERS_INLINE_BATCH_FLAG = False
UI_RENDERS_INLINE_RELIABILITY_BADGE = False
UI_HARD_FILTERS_CONFOUNDED_PAIRS = False
UI_SHOWS_ALL_COMPARISONS = True
LIMITATIONS_LIVE_IN = "methods_provenance_drawer"

# The emitted policy block, hashed into the temporal method id: a run that quietly
# loosened k, started refusing pairs, or began hiding confounded comparisons would be
# making a different claim, and it must not be able to keep this estimator's identity.
TEMPORAL_POLICY = {
    "policy_id": "spot.stage02.temporal.policy.v1",
    "estimator_id": ESTIMATOR_ID,
    "estimand_id": ESTIMAND_ID,
    "estimand_level": ESTIMAND_LEVEL,
    "estimand_is_per_cell_fate": ESTIMAND_IS_PER_CELL_FATE,
    "estimand_is_lineage_traced": ESTIMAND_IS_LINEAGE_TRACED,
    "formula_id": FORMULA_ID,
    "formula_expr": FORMULA_EXPR,
    "inference_status": INFERENCE_STATUS,
    "no_pq_reason": NO_PQ_REASON,
    "all_ordered_pairs": ALL_ORDERED_PAIRS,
    "pairs_may_be_refused": PAIRS_MAY_BE_REFUSED,
    "direction_rule_id": DIRECTION_RULE_ID,
    "reliability_k": RELIABILITY_K,
    "reliability_rule_id": RELIABILITY_RULE_ID,
    "reliability_comparator": RELIABILITY_COMPARATOR,
    "reliability_is_a_significance_test": RELIABILITY_IS_A_SIGNIFICANCE_TEST,
    "reliability_floor_kind": RELIABILITY_FLOOR_KIND,
    "reliability_floor_is_calibrated": RELIABILITY_FLOOR_IS_CALIBRATED,
    "reliability_absence_of_bias_claimed": RELIABILITY_ABSENCE_OF_BIAS_CLAIMED,
    "reliability_symmetry_assumption": RELIABILITY_SYMMETRY_ASSUMPTION,
    "reliability_scale_caveat": RELIABILITY_SCALE_CAVEAT,
    "display_policy_id": DISPLAY_POLICY_ID,
    "ui_renders_inline_batch_flag": UI_RENDERS_INLINE_BATCH_FLAG,
    "ui_renders_inline_reliability_badge": UI_RENDERS_INLINE_RELIABILITY_BADGE,
    "ui_hard_filters_confounded_pairs": UI_HARD_FILTERS_CONFOUNDED_PAIRS,
    "ui_shows_all_comparisons": UI_SHOWS_ALL_COMPARISONS,
    "limitations_live_in": LIMITATIONS_LIVE_IN,
}
