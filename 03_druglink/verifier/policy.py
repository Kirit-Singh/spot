"""The Stage-3 contract, RESTATED — deliberately not imported from the generator.

Every rule below is written out again from the specification. If the generator and
this file ever disagree, verification FAILS. That is the point: a verifier that
imported ``druglink.direction`` would happily bless whatever ``druglink.direction``
decided to do today.
"""
from __future__ import annotations

import re
from typing import Any, Optional

ARM_A = "away_from_A"
ARM_B = "toward_B"
ARMS = (ARM_A, ARM_B)
ARM_POLE = {ARM_A: "A", ARM_B: "B"}
ARM_RANK_COLUMN = {ARM_A: "rank_away_from_A", ARM_B: "rank_toward_B"}

IMMUTABLE_KEY = ("direct_run_id", "released_estimate_id", "target_id_namespace",
                 "target_id", "target_ensembl", "condition", "desired_arm")

# A combined objective can always be given a new name, so this denylist backs up the
# per-table column allowlists.
BANNED_KEYS = frozenset({
    "combination", "combination_score", "combination_state", "combined_score",
    "combined_rank", "balanced_score", "balanced_skew", "balanced_a_to_b",
    "composite_score", "total_skew", "overall_score", "overall_rank",
    "aggregate_score", "mean_arm_score", "arms_both_positive", "rank",
    "primary_rank", "rank_primary", "headline_rank", "best_arm", "best_of_arms",
    "primary_arm", "headline_arm", "rank_tuple",
    # the retired field that called an INHIBITOR "decrease"
    "pharmacologic_effect",
    # numeric combined objectives remain refused under ANY name. TYPED
    # joint_status / pareto_tier / joint_ordering_method_id are context and
    # are NOT banned — they are strings, and nothing reads them for direction.
    "combined_score", "balanced_skew",
})

PRODUCTION_POINTER_KEYS = ("production_pointer", "production_pointer_path",
                           "promoted_to_production", "current_pointer")
PRODUCTION_POINTER_FILES = ("production_pointer.json", "current.json")

LOCAL_PATH_RE = re.compile(
    r"(^|[\s\"'=(])(/home/|/Users/|/mnt/|/media/|/root/|/tmp/|/var/folders/"
    r"|/private/var/|[A-Za-z]:\\)")

# --------------------------------------------------------------------------- #
# Intervention effect, restated. An INHIBITOR is NOT an abundance reduction.
# --------------------------------------------------------------------------- #
ABUNDANCE_REDUCTION = "abundance_reduction"
FUNCTIONAL_INHIBITION = "functional_inhibition"
FUNCTIONAL_ACTIVATION = "functional_activation"
EFFECT_UNKNOWN = "unknown"

ACTION_ABUNDANCE_REDUCTION = frozenset({
    "DEGRADER", "DOWNREGULATOR", "PROTEOLYSIS TARGETING CHIMERA",
    "ANTISENSE INHIBITOR", "RNAI INHIBITOR"})
ACTION_FUNCTIONAL_INHIBITION = frozenset({
    "INHIBITOR", "ANTAGONIST", "BLOCKER", "NEGATIVE ALLOSTERIC MODULATOR",
    "NEGATIVE MODULATOR", "INVERSE AGONIST"})
ACTION_FUNCTIONAL_ACTIVATION = frozenset({
    "AGONIST", "ACTIVATOR", "POSITIVE ALLOSTERIC MODULATOR", "POSITIVE MODULATOR",
    "OPENER"})

# directional_evidence_status, restated.
OBSERVED_PERTURBATION = "observed_perturbation"
INVERSE_DIRECTION_HYPOTHESIS = "inverse_direction_hypothesis"
PATHWAY_HYPOTHESIS = "pathway_hypothesis"
OPPOSED = "opposed"
UNRESOLVED = "unresolved"

# Stage-3 evidence CLASS: a LABEL, not a tier, and deliberately UNORDERED. An inverse
# hypothesis may never share a class with a measurement.
CLASS_MEASURED = "measured_perturbation"
CLASS_INVERSE = "inverse_direction_hypothesis"
CLASS_PATHWAY = "pathway_hypothesis"
CLASS_NONE = "no_supporting_evidence"
EVIDENCE_CLASS_FOR = {
    OBSERVED_PERTURBATION: CLASS_MEASURED,
    INVERSE_DIRECTION_HYPOTHESIS: CLASS_INVERSE,
    PATHWAY_HYPOTHESIS: CLASS_PATHWAY,
    OPPOSED: CLASS_NONE,
    UNRESOLVED: CLASS_NONE,
}

# Canonical Stage-2 joint context. pareto_tier IS numeric — a positive integer tier
# LABEL from 1, or null when not jointly evaluable. That is not a combined score.
JOINT_STATUS_VALUES = ("both_arms", "away_from_A_only", "toward_B_only", "opposed",
                       "not_evaluable")

# Compact reason codes, restated.
REASON_ACTION_MATCHES_TESTED = "action_matches_tested_direction"
REASON_PATHWAY_COMPATIBLE = "pathway_node_direction_compatible"
REASON_ACTION_OPPOSES = "action_opposes_desired_direction"
REASON_INVERSE_ACTIVATION = "activation_mechanism_on_undesired_direction_arm"
REASON_ACTION_UNKNOWN = "action_effect_unknown"
REASON_NOT_SINGLE_PROTEIN = "entity_not_single_protein"
REASON_ACTION_CONFLICT = "conflicting_source_actions"
REASON_ARM_NOT_EVALUABLE = "arm_not_evaluable"
REASON_NO_DIRECTION = "no_direction_evidence"

# drug_mapping_status / stage4_assessment_status, restated.
MAPPED, UNMAPPED, REFUSED = "mapped", "unmapped", "refused"
QUEUED, NOT_QUEUED = "queued", "not_queued"

# The RETIRED promotion/eligibility vocabulary. None of it may appear, at any depth.
RETIRED_KEYS = frozenset({
    "production_candidate", "production_promotion_eligible",
    "may_write_production_pointer", "production_pointer_written",
    "research_pk_annotation_eligible", "research_pk_annotation_reason",
    "research_annotation_eligible", "research_direction_evaluable",
    "production_eligible", "stage3_eligible", "stage4_eligible",
    "annotation_only", "production_pointer", "promoted_to_production",
    "current_pointer", "namespace",
})

# A pathway node was INFERRED, never perturbed.
ORIGIN_DIRECT_TARGET = "direct_target"
ORIGIN_PATHWAY_NODE = "pathway_node"
ORIGINS = (ORIGIN_DIRECT_TARGET, ORIGIN_PATHWAY_NODE)

TESTED_LOF_DIRECTION = "tested_loss_of_function_direction"
INVERSE_DIRECTION_UNTESTED = "inverse_direction_hypothesis_untested"
NO_DIRECTION_EVIDENCE = "no_direction_evidence"
DIRECTION_NOT_EVALUATED = "not_evaluated"

MOD_DECREASE = "decrease"
MOD_INCREASE = "increase"
MOD_NO_DIRECTION = "no_direction_evidence"

DIRECTION_COMPATIBLE = frozenset({OBSERVED_PERTURBATION,
                                 INVERSE_DIRECTION_HYPOTHESIS,
                                 PATHWAY_HYPOTHESIS})
MEASURED_EVIDENCE = frozenset({OBSERVED_PERTURBATION})
REASON_QUEUED_INVERSE = "mapped_inverse_direction_hypothesis"
# The disease-context review, restated. A review is a RESULT, not a one-way flag: a
# COMPLETED review carries a verdict AND the evidence bindings that pay for it. Anything
# not completed carries NO result, and pending never drifts favourable.
REVIEW_PENDING = "pending"
REVIEW_COMPLETED = "completed"
REVIEW_NOT_REQUIRED = "not_required"
REVIEW_STATUSES = (REVIEW_PENDING, REVIEW_COMPLETED, REVIEW_NOT_REQUIRED)

REVIEW_RESULTS = ("supportive", "contradictory", "mixed", "insufficient")
SUBSTANTIVE_RESULTS = frozenset({"supportive", "contradictory", "mixed"})

DIRECT_GENE_LANE = "direct_gene_mechanism"


def normalize_action(action: Optional[str]) -> str:
    if action is None:
        return "UNKNOWN"
    return re.sub(r"[\s_-]+", " ", str(action)).strip().upper() or "UNKNOWN"


def intervention_effect(action: Optional[str]) -> str:
    norm = normalize_action(action)
    if norm in ACTION_ABUNDANCE_REDUCTION:
        return ABUNDANCE_REDUCTION
    if norm in ACTION_FUNCTIONAL_INHIBITION:
        return FUNCTIONAL_INHIBITION
    if norm in ACTION_FUNCTIONAL_ACTIVATION:
        return FUNCTIONAL_ACTIVATION
    return EFFECT_UNKNOWN


def direction_evidence_state(modulation: str, *, arm_evaluable: bool) -> str:
    if not arm_evaluable:
        return DIRECTION_NOT_EVALUATED
    if modulation == MOD_DECREASE:
        return TESTED_LOF_DIRECTION
    if modulation == MOD_INCREASE:
        # knockdown moved this arm the WRONG way; wanting an increase is the
        # untested inverse of a deleterious result
        return INVERSE_DIRECTION_UNTESTED
    if modulation == MOD_NO_DIRECTION:
        return NO_DIRECTION_EVIDENCE
    return DIRECTION_NOT_EVALUATED


def directional_evidence(*, modulation: str, effect: str, arm_evaluable: bool,
                         single_protein: bool, action_conflict: bool,
                         origin: str = ORIGIN_DIRECT_TARGET) -> tuple[str, str]:
    """(directional_evidence_status, reason). Restated, not imported."""
    pathway = origin == ORIGIN_PATHWAY_NODE
    if not single_protein:
        return UNRESOLVED, REASON_NOT_SINGLE_PROTEIN
    if action_conflict:
        return UNRESOLVED, REASON_ACTION_CONFLICT
    if not arm_evaluable or modulation == "not_evaluated":
        return UNRESOLVED, REASON_ARM_NOT_EVALUABLE
    if modulation == MOD_NO_DIRECTION:
        return UNRESOLVED, REASON_NO_DIRECTION
    if effect == EFFECT_UNKNOWN:
        return UNRESOLVED, REASON_ACTION_UNKNOWN

    reducing = effect in (ABUNDANCE_REDUCTION, FUNCTIONAL_INHIBITION)
    if modulation == MOD_DECREASE:
        if not reducing:
            return OPPOSED, REASON_ACTION_OPPOSES
        # A pathway node was never perturbed: the same action is only an inference.
        if pathway:
            return PATHWAY_HYPOTHESIS, REASON_PATHWAY_COMPATIBLE
        return OBSERVED_PERTURBATION, REASON_ACTION_MATCHES_TESTED

    # modulation == MOD_INCREASE: knockdown moved this arm the UNDESIRED way.
    if reducing:
        return OPPOSED, REASON_ACTION_OPPOSES
    if pathway:
        return PATHWAY_HYPOTHESIS, REASON_PATHWAY_COMPATIBLE
    # A DIRECT TARGET with a REAL sourced activation mechanism: the inverse-direction
    # hypothesis. A distinct state — never observed support, never gain of function.
    return INVERSE_DIRECTION_HYPOTHESIS, REASON_INVERSE_ACTIVATION


def observed_perturbation_support(status: str,
                                  origin: str = ORIGIN_DIRECT_TARGET) -> bool:
    """Only a MEASURED direct target carries observed-perturbation support."""
    return status in MEASURED_EVIDENCE and origin == ORIGIN_DIRECT_TARGET


def evidence_class(status: str) -> str:
    return EVIDENCE_CLASS_FOR.get(status, CLASS_NONE)


def baseline_review_status(statuses: set[str]) -> str:
    """What a candidate's review status must be when NO review has been supplied.

    An inverse-direction hypothesis is PENDING and stays pending. Everything else is
    not_required. Neither is ever a favourable verdict — only a COMPLETED review, with
    resolvable evidence bindings, can carry one.
    """
    return (REVIEW_PENDING if INVERSE_DIRECTION_HYPOTHESIS in statuses
            else REVIEW_NOT_REQUIRED)


def arm_evidence_state(statuses: set[str]) -> str:
    if not statuses:
        return "not_annotated"
    if OBSERVED_PERTURBATION in statuses and OPPOSED in statuses:
        return "conflicting"
    if OBSERVED_PERTURBATION in statuses:
        return OBSERVED_PERTURBATION
    if OPPOSED in statuses:
        return OPPOSED
    if INVERSE_DIRECTION_HYPOTHESIS in statuses:
        return INVERSE_DIRECTION_HYPOTHESIS
    if PATHWAY_HYPOTHESIS in statuses:
        return PATHWAY_HYPOTHESIS
    return UNRESOLVED


def stage4_status(*, identity_status: str, moiety_id: str,
                  statuses: set[str]) -> tuple[str, str]:
    """(status, reason). Queued iff identity resolves AND some edge is compatible."""
    if moiety_id.startswith("AM:UNRESOLVED:") or identity_status != "resolved":
        return NOT_QUEUED, "identity"
    if OBSERVED_PERTURBATION in statuses:
        return QUEUED, "direction_compatible_observed_perturbation"
    if INVERSE_DIRECTION_HYPOTHESIS in statuses:
        return QUEUED, REASON_QUEUED_INVERSE
    if PATHWAY_HYPOTHESIS in statuses:
        return QUEUED, "direction_compatible_pathway_hypothesis"
    return NOT_QUEUED, "no_direction_compatible_evidence"


def retired_keys_in(obj: Any) -> list[str]:
    return _walk(obj, "$", lambda k, v, p: [p] if k in RETIRED_KEYS else [])


def _walk(obj: Any, path: str, hit) -> list[str]:
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            hits += hit(k, v, f"{path}.{k}")
            hits += _walk(v, f"{path}.{k}", hit)
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            hits += _walk(v, f"{path}[{i}]", hit)
    return hits


def banned_keys_in(obj: Any) -> list[str]:
    return _walk(obj, "$",
                 lambda k, v, p: [p] if k in BANNED_KEYS else [])


def production_pointer_keys_in(obj: Any) -> list[str]:
    return _walk(obj, "$",
                 lambda k, v, p: [p] if k in PRODUCTION_POINTER_KEYS
                 and v not in (None, False, "") else [])


def contains_local_path(obj: Any) -> list[str]:
    hits: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v)
        elif isinstance(node, str) and LOCAL_PATH_RE.search(node):
            hits.append(node)

    walk(obj)
    return hits
