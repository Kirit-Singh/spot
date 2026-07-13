"""Scientific workflow states. Not promotion, not eligibility, not a recommendation.

The retired build asked Stage 3 to answer questions it has no standing to answer —
whether a drug is a "production candidate", whether it is "promotion eligible", whether
a pointer may be written. Those are programme decisions, not results of a target→drug
computation, and encoding them here meant a scientific artifact carried a business
verdict it could not justify. All of it is retired.

Stage 3 now reports four things, and nothing else:

  origin_type                 WHERE the lever came from        (druglink.direction)
                              direct_target | pathway_node

  directional_evidence_status WHAT the evidence actually is
                              observed_perturbation  the gene was PERTURBED and the
                                                     arm moved; the drug's action runs
                                                     in the direction the arm wants
                              pathway_hypothesis     the gene was INFERRED from a
                                                     pathway, never perturbed; the
                                                     drug's action is direction-
                                                     compatible with the node's own
                                                     stated direction
                              opposed                the drug's action runs OPPOSITE to
                                                     the desired direction
                              unresolved             fail-closed: unknown action, not a
                                                     single protein, contradictory
                                                     source actions, no arm direction,
                                                     or an UNTESTED inverse direction

  drug_mapping_status         whether the target reached a drug at all
                              mapped | unmapped | refused

  stage4_assessment_status    whether Stage 4 is asked to LOOK at it
                              queued | not_queued  (+ a compact reason code)

**A Stage-4 assessment is not biological promotion and not a recommendation.** Queuing
a candidate asks Stage 4 to compute PK/safety properties. It asserts nothing about
whether the drug should be used, tried, or believed.

Only ``observed_perturbation`` is evidence from a measurement. ``pathway_hypothesis`` is
an inference about a gene nobody perturbed. They are never summed, and the reason codes
below keep the distinction that the four-state vocabulary alone would flatten — in
particular ``inverse_direction_untested``, which is direction-compatible on paper but
rests on the UNTESTED inverse of a deleterious result, and is therefore ``unresolved``
rather than evidence.
"""
from __future__ import annotations

from typing import Any, Iterable

from . import artifact_class as ac

WORKFLOW_POLICY_VERSION = "stage3-workflow-v1-states-not-promotion"

# --------------------------------------------------------------------------- #
# directional_evidence_status (closed)
# --------------------------------------------------------------------------- #
OBSERVED_PERTURBATION = "observed_perturbation"
INVERSE_DIRECTION_HYPOTHESIS = "inverse_direction_hypothesis"
PATHWAY_HYPOTHESIS = "pathway_hypothesis"
OPPOSED = "opposed"
UNRESOLVED = "unresolved"
DIRECTIONAL_EVIDENCE_STATUSES = (OBSERVED_PERTURBATION, INVERSE_DIRECTION_HYPOTHESIS,
                                 PATHWAY_HYPOTHESIS, OPPOSED, UNRESOLVED)

# Compact reason codes. They carry what the statuses alone would flatten.
REASON_ACTION_MATCHES_TESTED = "action_matches_tested_direction"
REASON_INVERSE_ACTIVATION = "activation_mechanism_on_undesired_direction_arm"
REASON_PATHWAY_COMPATIBLE = "pathway_node_direction_compatible"
REASON_ACTION_OPPOSES = "action_opposes_desired_direction"
REASON_NO_ACTIVATION_MECHANISM = "no_sourced_activation_mechanism_for_inverse_direction"
REASON_ACTION_UNKNOWN = "action_effect_unknown"
REASON_NOT_SINGLE_PROTEIN = "entity_not_single_protein"
REASON_ACTION_CONFLICT = "conflicting_source_actions"
REASON_ARM_NOT_EVALUABLE = "arm_not_evaluable"
REASON_NO_DIRECTION = "no_direction_evidence"
DIRECTIONAL_REASONS = (
    REASON_ACTION_MATCHES_TESTED, REASON_INVERSE_ACTIVATION,
    REASON_PATHWAY_COMPATIBLE, REASON_ACTION_OPPOSES,
    REASON_NO_ACTIVATION_MECHANISM, REASON_ACTION_UNKNOWN,
    REASON_NOT_SINGLE_PROTEIN, REASON_ACTION_CONFLICT, REASON_ARM_NOT_EVALUABLE,
    REASON_NO_DIRECTION,
)

# Only a MEASURED perturbation is observed support. The inverse-direction hypothesis and
# the pathway hypothesis are INFERENCES, and neither is ever observed support.
MEASURED_EVIDENCE = frozenset({OBSERVED_PERTURBATION})

# TWO QUESTIONS, TWO SETS. One frozenset used to answer both, and that was the defect: it was
# NAMED for the evidence question and USED for the queuing question, so an untested inverse had
# to be called "direction-compatible" in order to be assessed at all. The docstring below then
# described the name while the code did the other thing — and the code is what ships.
#
# Is this DIRECTION-COMPATIBLE EVIDENCE? Only a measured perturbation whose observed sign
# supports the arm's desired change. An inverse-direction hypothesis is the inverse of a result
# nobody ran: CRISPRi never tested activation, so there is no observation to be compatible WITH.
DIRECTION_COMPATIBLE = frozenset({OBSERVED_PERTURBATION})

# Is this worth a Stage-4 ASSESSMENT? A wider question, and queuing is not endorsement. An
# inverse hypothesis IS a lead worth a human's attention — but dropping it silently would be
# worse than either queuing or refusing it, because a dropped candidate is indistinguishable
# from a candidate nobody found. So it is queued, TYPED, and never promotable.
QUEUE_ELIGIBLE = frozenset({OBSERVED_PERTURBATION, INVERSE_DIRECTION_HYPOTHESIS,
                            PATHWAY_HYPOTHESIS})
# The classes Stage 4 must carry VERBATIM and may never promote into observed support.
HYPOTHESIS_ONLY = frozenset({INVERSE_DIRECTION_HYPOTHESIS, PATHWAY_HYPOTHESIS})

# --------------------------------------------------------------------------- #
# Stage-3 evidence CLASS. A LABEL, not a tier, and deliberately NOT ordered.
#
# It exists so an inverse-direction hypothesis can never be filed under the same
# evidence tier as an observed perturbation. It is NOT comparable to, and never
# alters, Direct's own arm evidence tiers, Direct's ranks, or Stage-2 Pareto tiers —
# those are upstream facts that Stage 3 carries verbatim and never rewrites.
# --------------------------------------------------------------------------- #
CLASS_MEASURED = "measured_perturbation"
CLASS_INVERSE = "inverse_direction_hypothesis"
CLASS_PATHWAY = "pathway_hypothesis"
CLASS_NONE = "no_supporting_evidence"
EVIDENCE_CLASSES = (CLASS_MEASURED, CLASS_INVERSE, CLASS_PATHWAY, CLASS_NONE)
EVIDENCE_CLASS_FOR = {
    OBSERVED_PERTURBATION: CLASS_MEASURED,
    INVERSE_DIRECTION_HYPOTHESIS: CLASS_INVERSE,
    PATHWAY_HYPOTHESIS: CLASS_PATHWAY,
    OPPOSED: CLASS_NONE,
    UNRESOLVED: CLASS_NONE,
}
EVIDENCE_CLASSES_ARE_UNORDERED = True

# Claude Science reviews the biological plausibility of an inverse-direction
# hypothesis LATER. Stage 3 flags it; Stage 3 never judges it.
# The disease-context review is owned by ``science_review``. It used to live here as a
# one-way PENDING flag, which could be set and never resolved; a review now arrives as an
# ingestible RESULT that must pay for itself with resolvable evidence bindings.

# --------------------------------------------------------------------------- #
# drug_mapping_status (closed)
# --------------------------------------------------------------------------- #
MAPPED = "mapped"
UNMAPPED = "unmapped"
REFUSED = "refused"
DRUG_MAPPING_STATUSES = (MAPPED, UNMAPPED, REFUSED)

REASON_NO_ACCESSION = "target_is_a_symbol_not_an_accession"
REASON_NO_SOURCE_MAPPING = "no_public_source_maps_this_accession"
REASON_ONLY_NON_GENE_ENTITY = "only_complex_or_family_entities_matched"
MAPPING_REASONS = (REASON_NO_ACCESSION, REASON_NO_SOURCE_MAPPING,
                   REASON_ONLY_NON_GENE_ENTITY, "mapped_to_single_protein_target")

# --------------------------------------------------------------------------- #
# stage4_assessment_status (closed)
# --------------------------------------------------------------------------- #
QUEUED = "queued"
NOT_QUEUED = "not_queued"
STAGE4_ASSESSMENT_STATUSES = (QUEUED, NOT_QUEUED)

REASON_QUEUED_OBSERVED = "direction_compatible_observed_perturbation"
REASON_QUEUED_INVERSE = "mapped_inverse_direction_hypothesis"
REASON_QUEUED_PATHWAY = "direction_compatible_pathway_hypothesis"
REASON_NOT_QUEUED_IDENTITY = "active_moiety_identity_unresolved"
REASON_NOT_QUEUED_AMBIGUOUS = "active_moiety_identity_ambiguous"
REASON_NOT_QUEUED_MULTI = "active_moiety_multi_ingredient"
REASON_NOT_QUEUED_NO_EVIDENCE = "no_direction_compatible_evidence"
REASON_NOT_QUEUED_FIXTURE = "fixture_artifact_class_never_reaches_stage4"
STAGE4_REASONS = (
    REASON_QUEUED_OBSERVED, REASON_QUEUED_INVERSE, REASON_QUEUED_PATHWAY,
    REASON_NOT_QUEUED_IDENTITY, REASON_NOT_QUEUED_AMBIGUOUS, REASON_NOT_QUEUED_MULTI,
    REASON_NOT_QUEUED_NO_EVIDENCE, REASON_NOT_QUEUED_FIXTURE,
)

STAGE4_ASSESSMENT_NOTE = (
    "a stage-4 assessment computes PK/safety properties; it is not biological "
    "promotion and not a recommendation")


def drug_mapping_status(*, has_accession: bool, n_single_protein_entities: int,
                        n_non_gene_entities: int) -> tuple[str, str]:
    """Did this target reach a drug-mappable single-protein entity, and if not, why?"""
    if not has_accession:
        return UNMAPPED, REASON_NO_ACCESSION
    if n_single_protein_entities > 0:
        return MAPPED, "mapped_to_single_protein_target"
    if n_non_gene_entities > 0:
        # Entities matched, but every one was a complex/family. A complex is not a gene
        # and is never translated into one of its components — so this is a REFUSAL,
        # which is a different fact from "nothing matched".
        return REFUSED, REASON_ONLY_NON_GENE_ENTITY
    return UNMAPPED, REASON_NO_SOURCE_MAPPING


def stage4_assessment(*, artifact_class: str, identity_status: str,
                      active_moiety_id: str,
                      directional_statuses: Iterable[str]) -> tuple[str, str]:
    """Should Stage 4 be asked to ASSESS this candidate? Returns (status, reason).

    Queuing is not endorsement, and queuing is not evidence. A candidate is queued when its
    identity resolves and at least one edge is QUEUE_ELIGIBLE.

    FROZEN POLICY on the untested inverse. An ``inverse_direction_hypothesis`` rests on the
    inverse of a deleterious result that nobody ran: the knockdown moved the program the WRONG
    way, and CRISPRi never tested activation. It is therefore:

      * QUEUED — because silently dropping it is the worse failure. A dropped candidate is
        indistinguishable from a candidate nobody found, and this one is a real lead a human
        should see;
      * HYPOTHESIS-ONLY, always — never observed-compatible, never a phenocopy, never supported
        evidence, never sharing a tier with a measurement;
      * NOT PROMOTABLE — Stage 4 carries the weaker class VERBATIM and may not raise it.

    This docstring previously claimed the inverse hypothesis was withheld from the queue, while
    ``DIRECTION_COMPATIBLE`` contained it and the code queued it anyway. The prose described the
    intent; the code shipped the opposite, and the code is what Stage 4 received. The sets are
    now split (DIRECTION_COMPATIBLE = evidence, QUEUE_ELIGIBLE = assessment) so the two
    questions cannot be conflated again, and a test asserts the prose and the code agree.
    """
    if not ac.stage4_queue_permitted(artifact_class):
        return NOT_QUEUED, REASON_NOT_QUEUED_FIXTURE
    if active_moiety_id.startswith("AM:UNRESOLVED:") or identity_status == "unresolved":
        return NOT_QUEUED, REASON_NOT_QUEUED_IDENTITY
    if identity_status == "ambiguous":
        return NOT_QUEUED, REASON_NOT_QUEUED_AMBIGUOUS
    if identity_status == "multi_ingredient":
        return NOT_QUEUED, REASON_NOT_QUEUED_MULTI

    statuses = set(directional_statuses)
    if OBSERVED_PERTURBATION in statuses:
        return QUEUED, REASON_QUEUED_OBSERVED
    if INVERSE_DIRECTION_HYPOTHESIS in statuses:
        # Queued for a LOOK, on an explicitly labelled hypothesis. Not evidence, not a
        # gain-of-function observation, and not a recommendation.
        return QUEUED, REASON_QUEUED_INVERSE
    if PATHWAY_HYPOTHESIS in statuses:
        return QUEUED, REASON_QUEUED_PATHWAY
    return NOT_QUEUED, REASON_NOT_QUEUED_NO_EVIDENCE


def evidence_class(status: str) -> str:
    """The Stage-3 evidence CLASS for a directional status. A label, never a tier."""
    return EVIDENCE_CLASS_FOR.get(status, CLASS_NONE)




def summary_state(statuses: set[str]) -> str:
    """One (candidate, arm, origin) state. A contradiction is preserved, not resolved.

    An inverse-direction hypothesis NEVER outranks a measured perturbation and never
    hides an opposed sourced action — it surfaces only when neither is present.
    """
    if not statuses:
        return "not_annotated"
    if OBSERVED_PERTURBATION in statuses and OPPOSED in statuses:
        return "conflicting"          # the sources contradict each other
    if OBSERVED_PERTURBATION in statuses:
        return OBSERVED_PERTURBATION
    if OPPOSED in statuses:
        return OPPOSED
    if INVERSE_DIRECTION_HYPOTHESIS in statuses:
        return INVERSE_DIRECTION_HYPOTHESIS
    if PATHWAY_HYPOTHESIS in statuses:
        return PATHWAY_HYPOTHESIS
    return UNRESOLVED


def vocabularies() -> dict[str, Any]:
    """The frozen workflow vocabulary, hashed into every Stage-3 bundle id."""
    return {
        "workflow_policy_version": WORKFLOW_POLICY_VERSION,
        "directional_evidence_statuses": list(DIRECTIONAL_EVIDENCE_STATUSES),
        "directional_reasons": list(DIRECTIONAL_REASONS),
        "drug_mapping_statuses": list(DRUG_MAPPING_STATUSES),
        "mapping_reasons": list(MAPPING_REASONS),
        "stage4_assessment_statuses": list(STAGE4_ASSESSMENT_STATUSES),
        "stage4_reasons": list(STAGE4_REASONS),
        "evidence_classes": list(EVIDENCE_CLASSES),
        "evidence_classes_are_unordered": EVIDENCE_CLASSES_ARE_UNORDERED,
        "measured_evidence_statuses": sorted(MEASURED_EVIDENCE),
        "direction_compatible_statuses": sorted(DIRECTION_COMPATIBLE),
        # Published SEPARATELY, because they answer different questions. A candidate may be
        # QUEUE_ELIGIBLE (worth a look) without being DIRECTION_COMPATIBLE (evidence). Stage 4
        # reads both: it may assess anything queued, and may promote nothing in HYPOTHESIS_ONLY.
        "queue_eligible_statuses": sorted(QUEUE_ELIGIBLE),
        "hypothesis_only_statuses": sorted(HYPOTHESIS_ONLY),
        "queued_is_not_evidence": True,
        "stage4_must_preserve_the_hypothesis_only_class_without_promoting_it": True,
        "stage4_assessment_is_not_promotion_or_recommendation": True,
        "pathway_hypothesis_is_never_a_measurement": True,
        "inverse_direction_hypothesis_is_never_observed_gain_of_function": True,
        "inverse_direction_hypothesis_is_never_observed_support": True,
        "inverse_direction_hypothesis_never_shares_a_tier_with_a_measurement": True,
        "stage3_never_alters_direct_ranks_or_stage2_pareto_tiers": True,
        "no_activation_mechanism_means_no_inverse_hypothesis_is_invented": True,
        "promotion_and_eligibility_vocabulary_is_retired": True,
        "retired_keys": sorted(ac.RETIRED_KEYS),
    }
