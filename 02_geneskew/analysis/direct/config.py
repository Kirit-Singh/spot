"""Frozen Stage-2 direct-lane policy.

Everything here is GENERIC: no program ids, no condition, no dataset hashes.
The biology of a run arrives exclusively through the immutable Stage-1 selection
contract (``selection.py``).

TWO ORDERED ARMS, NEVER COMBINED
--------------------------------
The Stage-1 question is an ordered pair of states: move AWAY from A, and TOWARD
B. Those are two different biological questions and they are kept apart end to
end. There is:

  * no primary/headline arm — neither arm outranks the other;
  * no combined, balanced, averaged or best-of objective, score, rank or gate;
  * one nullable rank PER ARM, over that arm's own evaluable population.

A target that moves strongly away from A while OPPOSING B must never outrank a
target that genuinely moves toward B, and vice versa. Collapsing the arms (even
into a descriptive mean) reintroduces the retired balanced-skew objective and
makes the second dropdown decorative, so it is forbidden and verifier-enforced.
"""
from __future__ import annotations

# --------------------------------------------------------------------------- #
# Method identity (enters run_id).
# --------------------------------------------------------------------------- #
METHOD_ID = "spot.stage02.direct.masked_program_projection"
# v5, not v4: the evidence domain is the GLOBAL all-condition pooled-main scope set,
# by-guide/donor support is explicitly unavailable (never projected, never masked, never
# tier-elevating), and the primary gene universe is the pooled object's own axis rather
# than an intersection with support matrices no score is taken over. Each of those
# changes what the emitted numbers ARE, so the method version changes with them.
METHOD_VERSION = "stage2-direct-v5-pooled-main-two-arm"
# A compact id and the bare expression. An emitted artifact is a MACHINE artifact: it
# carries ids, enums, counts and hashes, and what the method MEANS is stated once — in
# this module's docstring, in projection.py and in HANDOFF — rather than re-serialised
# into every run. The id is what run_id binds, so a changed method still changes the run.
FORMULA_ID = "spot.stage02.direct.formula.masked_program_delta.v1"
FORMULA_EXPR = "delta_p(X) = mean(P_p \\ M_X) - mean(C_p \\ M_X)"
EFFECT_LAYER_PRIMARY = "log_fc"
EFFECT_LAYER_SENSITIVITY = "zscore"

# --------------------------------------------------------------------------- #
# Compact rule IDs for the artifact contract. Each names a rule stated ONCE, in the
# method docs; none of them is a place to re-narrate it. A consumer resolves the id;
# a human reads the docs. Prose repeated in every run is not provenance — it is noise
# that drifts away from the code while looking authoritative.
# --------------------------------------------------------------------------- #
RUN_KEY_RULE_ID = "spot.stage02.direct.run_key_rule.run_id_not_question_id.v1"
CONSUMER_RULE_ID = "spot.stage02.direct.consumer_rule.explicit_arm_choice.v1"
CROSS_ARM_RULE_ID = "spot.stage02.direct.cross_arm_rule.descriptive_never_gating.v1"
ARM_STATE_RULE_ID = "spot.stage02.direct.arm_state_rule.independent_per_arm.v1"
MODULATION_RULE_ID = "spot.stage02.direct.modulation_rule.conflict_preserved.v1"
FAMILY_SIZE_RULE_ID = "spot.stage02.direct.family_size_rule.not_a_multiplicity_family.v1"
DONOR_SPLIT_RULE_ID = "spot.stage02.direct.donor_split_rule.complementary_halves_only.v1"
ID_RECOMPUTE_RULE_ID = "spot.stage02.direct.id_rule.rederived_canonical_fatal.v1"
SELECTABILITY_RULE_ID = "spot.stage01.selectability.rederived_from_validation_rows.v1"
NO_PQ_REASON = "no_calibrated_null_for_this_projection"
INDEPENDENT_VERIFICATION_PENDING = "pending"

# --------------------------------------------------------------------------- #
# The two arms (frozen). Order is presentation only; it confers no precedence.
# --------------------------------------------------------------------------- #
ARM_A = "away_from_A"
ARM_B = "toward_B"
ARMS = (ARM_A, ARM_B)

ARM_RANK_COLUMN = {ARM_A: "rank_away_from_A", ARM_B: "rank_toward_B"}
ARM_POLE = {ARM_A: "A", ARM_B: "B"}
ARM_FORMULA = {ARM_A: "-sign_A * delta_A", ARM_B: "sign_B * delta_B"}

# Hard invariants the verifier re-checks against the emitted artifacts.
COMBINED_OBJECTIVE_PERMITTED = False
HEADLINE_ARM_PERMITTED = False
RANK_POPULATION = "arm_evaluable_and_non_null_canonical_score"
RANK_TIE_BREAK = "target_id_ascending"
RANK_DIRECTION = "descending"
RANK_DTYPE = "Int64"                        # nullable; never a NaN float
# Scores are emitted, hashed AND ranked at canonical float64. Display rounding is
# a UI concern and never touches a scientific value or a rank.
SCORE_REPRESENTATION = "canonical_float64_no_display_rounding"
DISPLAY_ROUNDING_IS_UI_ONLY = True
NONFINITE_SCORE_RULE = "nan_and_inf_are_canonicalised_to_null_and_never_ranked"

# --------------------------------------------------------------------------- #
# Production firewall (fail-closed).
# --------------------------------------------------------------------------- #
LANE_PRODUCTION = "production"
LANE_RESEARCH = "research_only"
LANE_SYNTHETIC = "synthetic"
LANES = (LANE_PRODUCTION, LANE_RESEARCH, LANE_SYNTHETIC)
# Research-namespace identifiers may never enter the production lane.
RESEARCH_NAMESPACE_PREFIXES = ("rq_", "ra_")

# research_only executes the SAME projection/masking/disposition as production and
# demands the same complete measured evidence. It differs in exactly one place: it
# does not require the Stage-1 production-selectability gate to PASS. It records the
# failed gate as provenance, is never production-eligible, never Stage-3 eligible for
# production promotion, and can never write a production pointer.
RESEARCH_REQUIRES_PRODUCTION_GATE_PASS = False
RESEARCH_BRIDGE_SCHEMA = "spot.stage01_selection.v1"
RESEARCH_BRIDGE_SOURCE = "stage01_research_bridge"
RESEARCH_NAMESPACE = "research_only"
# A research pole must be a PRIMARY, BASE-PORTABLE axis (declared by Stage-1).
RESEARCH_REQUIRES_PRIMARY_BASE_PORTABLE_AXES = True
# A production run additionally requires each pole's program to be declared
# production-selectable by the frozen Stage-1 registry.
PRODUCTION_REQUIRES_PRODUCTION_SELECTABLE = True

# --------------------------------------------------------------------------- #
# Stage-1 compatibility (generic version-family policy, not a pinned hash).
# --------------------------------------------------------------------------- #
ACCEPTED_STAGE1_METHOD_PREFIX = "stage1-continuous-v3"
REJECTED_STAGE1_METHOD_PREFIXES = ("stage1-continuous-v1", "stage1-continuous-v2")

# Pole sign s: +1 high pole, -1 low pole.
POLE_SIGN = {"high": +1, "low": -1}

# --------------------------------------------------------------------------- #
# Mask policy (frozen).
# --------------------------------------------------------------------------- #
MASK_NEIGHBORHOOD_COLUMN = "nearby_gene_within_30kb"
MASK_WINDOW_KB = 30
MASK_REASONS = ("intended_target", "neighbor_within_window", "offtarget_alignment")
# WHICH mask rule built the removed-gene set. Emitted per row alongside the estimate's
# own mask id, and bound into the run: the intended target, its 30-kb neighbourhood and
# every off-target alignment of the CONTRIBUTING guides are removed before the panel and
# control means are recomputed. A different mask rule is a different measurement, and a
# row that names its mask hash without naming the rule that produced it can be compared
# only against itself.
MASK_METHOD_VERSION = "stage2-direct-mask-v1-contributing-guide-and-offtarget"

# --------------------------------------------------------------------------- #
# Contributing-guide resolution ladder (frozen; never guess a guide identity).
# --------------------------------------------------------------------------- #
#   1. an explicit, source-hash-bound contributor manifest, proven per row and
#      covering exactly the GLOBAL pooled-main released scope universe;
#   2. otherwise the estimate is unresolved: no mask, no score, no support.
#
# There is no third rung. The released by-guide object carries no per-row sgRNA
# identity. The public CZI v1.0.0 release README DOES define guide_1/guide_2 by
# alphanumeric guide-ID rank, and the donor modalities by named donor pairs
# (data_sharing_readme.md, sha256
# 9275bad99701534e109691f2ce6ff8c474dacb3912e9a6f22cbaa009237ceab7, lines 135-153) —
# that rank is a PUBLISHED rule, not a guess. It is simply not evidence of WHICH guide
# contributed to a given estimate, which is what a mask needs, so no slot->guide
# mapping is applied in this lane.
GUIDE_RESOLUTION_LADDER = ("manifest", "unresolved")
GUIDE_IDENTITY_INFERENCE_PERMITTED = False
GUIDE_IDENTITY_NOTE = (
    "guide identity enters Stage-2 only through an explicit contributor manifest; "
    "an ambiguous identity stays unavailable and is never rounded to a guess. The "
    "public slot rule (alphanumeric guide-ID rank) is a published rule, not a guess, "
    "but a slot name is not evidence of an estimate's contributor set"
)

# --------------------------------------------------------------------------- #
# Evidence domain of THIS release pass (see domain.py).
# --------------------------------------------------------------------------- #
# The audited contributor artifact is global, all-condition, POOLED-MAIN only. By-guide
# and donor-pair support carry no contributor evidence and are explicitly unavailable:
# no mask, no projection, no replication claim, no tier elevation. Support is feasible
# later, but it needs its own provenance method and its own contract.
SUPPORT_AVAILABLE_IN_THIS_PASS = False

# --------------------------------------------------------------------------- #
# Coverage / QC thresholds (frozen before viewing ranks).
# --------------------------------------------------------------------------- #
# Required base-QC measurements. A MISSING or INVALID measurement is not favourable
# evidence: it is an explicit non-evaluable disposition. Presence/validity rules are
# frozen here and reimplemented independently by the standalone verifier.
REQUIRED_BASE_QC_MEASUREMENTS = ("n_cells", "ontarget_significant",
                                 "low_expression_flag")
BASE_QC_VALIDITY = {
    "n_cells": "finite_non_negative_number",
    "ontarget_significant": "boolean",
    "low_expression_flag": "boolean",
}

MIN_SURVIVING_PANEL = 1
MIN_SURVIVING_CONTROL = 10
N_CELLS_MIN = 30
MIN_GUIDES_FOR_REPLICATION = 2   # distinct, mapped AND evaluated guides, PER ARM

# Sign tolerance: |x| below this is treated as no sign / no direction evidence.
SIGN_EPS = 1e-9

INFERENCE_STATUS = "not_calibrated"       # no calibrated null -> no p/q
CRISPRI_MODALITY = "CRISPRi_knockdown"

# Emitted in the run binding so a policy change changes run_id.
ELIGIBILITY_POLICY = {
    "policy_id": "spot.stage02.direct.two_arm_eligibility.v1",
    "pre_outcome_base_qc_only": True,
    "arms": list(ARMS),
    "arm_formula": dict(ARM_FORMULA),
    "arm_rank_column": dict(ARM_RANK_COLUMN),
    "combined_objective_permitted": COMBINED_OBJECTIVE_PERMITTED,
    "headline_arm_permitted": HEADLINE_ARM_PERMITTED,
    "rank_population": RANK_POPULATION,
    "rank_tie_break": RANK_TIE_BREAK,
    "rank_direction": RANK_DIRECTION,
    "rank_dtype": RANK_DTYPE,
    "score_representation": SCORE_REPRESENTATION,
    "nonfinite_score_rule": NONFINITE_SCORE_RULE,
    "support_requires_arm_evaluable": True,
    "required_base_qc_measurements": list(REQUIRED_BASE_QC_MEASUREMENTS),
    "base_qc_validity": dict(BASE_QC_VALIDITY),
    "missing_qc_is_non_evaluable": True,
    "arms_are_independent": True,
    "arm_support_is_never_shared": True,
    "min_surviving_panel": MIN_SURVIVING_PANEL,
    "min_surviving_control": MIN_SURVIVING_CONTROL,
    "n_cells_min": N_CELLS_MIN,
    "min_guides_for_replication": MIN_GUIDES_FOR_REPLICATION,
    "mask_window_kb": MASK_WINDOW_KB,
    "mask_neighborhood_column": MASK_NEIGHBORHOOD_COLUMN,
    "guide_resolution_ladder": list(GUIDE_RESOLUTION_LADDER),
    "guide_identity_inference_permitted": GUIDE_IDENTITY_INFERENCE_PERMITTED,
    "single_guide_targets_never_replicated": True,
    "modulation_conflicts_are_preserved_not_resolved": True,
    "sign_eps": SIGN_EPS,
    "float_decimals": 6,
}
