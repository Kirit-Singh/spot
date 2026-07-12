"""Mechanistically honest direction: what the drug DOES vs what the screen TESTED.

An earlier build called an INHIBITOR ``pharmacologic_effect=decrease`` and compared that
to a CRISPRi abundance direction — silently asserting that blocking a protein's activity
is the same as having less of it. It is not. An antagonist can shut down signalling
without changing abundance at all.

So three quantities are kept strictly apart:

  perturbation_modality                what Stage 2 actually did   (CRISPRi knockdown)
  observed_target_abundance_direction  what that did to ABUNDANCE  (decrease)
  intervention_effect                  what the DRUG does, closed vocabulary

``intervention_effect`` (closed; unrecognised/mixed/insufficient -> ``unknown``):

  abundance_reduction    lowers target ABUNDANCE (degrader, downregulator, PROTAC,
                         antisense/RNAi). Kept distinguishable from inhibition.
  functional_inhibition  reduces target FUNCTION/signalling (inhibitor, antagonist,
                         blocker, negative (allosteric) modulator, inverse agonist).
                         Asserts NOTHING about abundance.
  functional_activation  increases target FUNCTION/signalling (agonist, activator,
                         positive (allosteric) modulator, opener).
  unknown                fail-closed. **Activation is NEVER inferred from inhibition.**

The drug's action direction must MATCH the arm's desired biological direction. The
result is a ``directional_evidence_status`` (see :mod:`druglink.workflow`) plus a
compact reason code:

  origin=direct_target, arm wants DECREASE (the tested CRISPRi direction),
    drug reduces abundance or function        -> observed_perturbation
  origin=direct_target, arm wants INCREASE (knockdown moved the arm the UNDESIRED way),
    a REAL sourced activation/agonism exists  -> inverse_direction_hypothesis
  origin=pathway_node, direction-compatible   -> pathway_hypothesis   (never measured)
  drug runs opposite to the desired direction -> opposed
  everything else                             -> unresolved

THE INVERSE-DIRECTION HYPOTHESIS
--------------------------------
A NEGATIVE arm score means knockdown moved that arm the WRONG way. Wanting an INCREASE is
therefore the UNTESTED INVERSE of a deleterious result. When a REAL activation/agonism
mechanism exists on the exact single-protein target, that is a distinct, nameable state —
``inverse_direction_hypothesis`` — and it is kept apart from everything else:

  * ``observed_perturbation_support = false``. It is NOT observed gain of function, and
    it is NOT the same evidence class as a measured perturbation
    (``stage3_evidence_class`` separates them, and that class is UNORDERED).
  * It is queued for a Stage-4 LOOK, with reason ``mapped_inverse_direction_hypothesis``.
    Queuing is not endorsement.
  * The supporting ARM and the exact source MECHANISM are preserved on the edge.
  * Claude Science reviews its biological plausibility LATER. Stage 3 flags it and does
    not judge it.
  * If NO real activation mechanism is sourced, NOTHING is invented: there is no
    inverse-hypothesis edge, and the candidate is not queued on that basis.
  * It never alters a Direct rank, a Direct arm evidence tier, or a Stage-2 Pareto tier.

Nothing here converts an association into a causal claim.
"""
from __future__ import annotations

import re
from typing import Any, Optional

from . import workflow as wf

DIRECTION_POLICY_VERSION = "stage3-direction-v4-workflow-states"

# What the SCREEN did. CRISPRi knockdown lowers target abundance; that is the only
# genetic direction this lane has evidence about.
MODALITY_ABUNDANCE_DIRECTION = {
    "CRISPRi_knockdown": "decrease",
    "crispri": "decrease",
}

# --------------------------------------------------------------------------- #
# What the DRUG does. Closed; anything unlisted fails closed to unknown.
# --------------------------------------------------------------------------- #
ABUNDANCE_REDUCTION = "abundance_reduction"
FUNCTIONAL_INHIBITION = "functional_inhibition"
FUNCTIONAL_ACTIVATION = "functional_activation"
EFFECT_UNKNOWN = "unknown"
INTERVENTION_EFFECTS = (ABUNDANCE_REDUCTION, FUNCTIONAL_INHIBITION,
                        FUNCTIONAL_ACTIVATION, EFFECT_UNKNOWN)

ACTION_ABUNDANCE_REDUCTION = frozenset({
    "DEGRADER", "DOWNREGULATOR", "PROTEOLYSIS TARGETING CHIMERA",
    "ANTISENSE INHIBITOR", "RNAI INHIBITOR",
})
ACTION_FUNCTIONAL_INHIBITION = frozenset({
    "INHIBITOR", "ANTAGONIST", "BLOCKER", "NEGATIVE ALLOSTERIC MODULATOR",
    "NEGATIVE MODULATOR", "INVERSE AGONIST",
})
ACTION_FUNCTIONAL_ACTIVATION = frozenset({
    "AGONIST", "ACTIVATOR", "POSITIVE ALLOSTERIC MODULATOR", "POSITIVE MODULATOR",
    "OPENER",
})
# Named explicitly so the reason says WHY, not merely "unrecognised". UPREGULATOR and
# STABILISER plausibly raise abundance, but the closed vocabulary has no
# abundance-increase term and calling them functional_activation would assert a
# signalling effect the source never stated — so they stay unknown, deliberately.
ACTION_EXPLICIT_UNKNOWN = frozenset({
    "BINDER", "BINDING AGENT", "MODULATOR", "ALLOSTERIC MODULATOR", "PARTIAL AGONIST",
    "SUBSTRATE", "OTHER", "UNKNOWN", "CROSS-LINKING AGENT", "HYDROLYTIC ENZYME",
    "SEQUESTERING AGENT", "DISRUPTING AGENT", "CHELATING AGENT", "RELEASING AGENT",
    "STABILISER", "STABILIZER", "UPREGULATOR", "OXIDATIVE ENZYME",
    "PROTEOLYTIC ENZYME",
})
_DUAL_RE = re.compile(r"[/&+]| AND |,")

# Where a lever came from. A pathway node was NEVER PERTURBED.
ORIGIN_DIRECT_TARGET = "direct_target"
ORIGIN_PATHWAY_NODE = "pathway_node"
ORIGIN_TYPES = (ORIGIN_DIRECT_TARGET, ORIGIN_PATHWAY_NODE)

# Direct's per-arm desired-modulation vocabulary, consumed verbatim, never renamed.
MOD_DECREASE = "decrease"
MOD_INCREASE = "increase"
MOD_NO_DIRECTION = "no_direction_evidence"
MOD_NOT_EVALUATED = "not_evaluated"


def normalize_action_type(action_type: Optional[str]) -> str:
    """Uppercase, whitespace-folded. The SOURCE string is retained separately."""
    if action_type is None:
        return "UNKNOWN"
    s = re.sub(r"[\s_-]+", " ", str(action_type)).strip().upper()
    return s or "UNKNOWN"


def intervention_effect(action_type: Optional[str]) -> tuple[str, str]:
    """(effect, reason). An inhibitor is NEVER 'decreases target abundance'."""
    norm = normalize_action_type(action_type)
    tag = norm.lower().replace(" ", "_")
    if norm in ACTION_ABUNDANCE_REDUCTION:
        return ABUNDANCE_REDUCTION, f"action_{tag}_lowers_target_abundance"
    # "abundance" appears ONLY where an abundance change is actually asserted, so a
    # grep over the artifacts finds real claims and no negations of claims.
    if norm in ACTION_FUNCTIONAL_INHIBITION:
        return FUNCTIONAL_INHIBITION, (
            f"action_{tag}_reduces_target_function_not_target_level")
    if norm in ACTION_FUNCTIONAL_ACTIVATION:
        return FUNCTIONAL_ACTIVATION, (
            f"action_{tag}_increases_target_function_not_target_level")
    if norm in ACTION_EXPLICIT_UNKNOWN:
        return EFFECT_UNKNOWN, f"action_{tag}_has_no_enumerated_intervention_effect"
    if _DUAL_RE.search(norm):
        return EFFECT_UNKNOWN, "mixed_or_compound_action_type_not_translatable"
    return EFFECT_UNKNOWN, "unrecognised_action_type_fails_closed"


def translate(*, desired_modulation: str, effect: str, arm_evaluable: bool,
              target_entity_is_single_protein: bool,
              action_conflict: bool = False,
              origin_type: str = ORIGIN_DIRECT_TARGET) -> dict[str, Any]:
    """Classify ONE (arm, origin, drug, exact single-protein target) edge. Fail-closed.

    Returns ``directional_evidence_status`` + a compact reason code. No promotion, no
    eligibility, no recommendation: only what the evidence is.
    """
    pathway = origin_type == ORIGIN_PATHWAY_NODE

    if origin_type not in ORIGIN_TYPES:
        return _out(wf.UNRESOLVED, wf.REASON_ARM_NOT_EVALUABLE, origin_type)
    if not target_entity_is_single_protein:
        return _out(wf.UNRESOLVED, wf.REASON_NOT_SINGLE_PROTEIN, origin_type)
    if action_conflict:
        return _out(wf.UNRESOLVED, wf.REASON_ACTION_CONFLICT, origin_type)
    if not arm_evaluable or desired_modulation == MOD_NOT_EVALUATED:
        return _out(wf.UNRESOLVED, wf.REASON_ARM_NOT_EVALUABLE, origin_type)
    if desired_modulation == MOD_NO_DIRECTION:
        return _out(wf.UNRESOLVED, wf.REASON_NO_DIRECTION, origin_type)
    if effect == EFFECT_UNKNOWN:
        return _out(wf.UNRESOLVED, wf.REASON_ACTION_UNKNOWN, origin_type)

    reducing = effect in (ABUNDANCE_REDUCTION, FUNCTIONAL_INHIBITION)

    if desired_modulation == MOD_DECREASE:
        # The arm's TESTED CRISPRi direction. The drug either runs with it or against it.
        if not reducing:
            return _out(wf.OPPOSED, wf.REASON_ACTION_OPPOSES, origin_type)
        # A direct target was itself perturbed: this is a measured direction. A pathway
        # node was not perturbed, so the same action is only an inference about it.
        if pathway:
            return _out(wf.PATHWAY_HYPOTHESIS, wf.REASON_PATHWAY_COMPATIBLE,
                        origin_type)
        return _out(wf.OBSERVED_PERTURBATION, wf.REASON_ACTION_MATCHES_TESTED,
                    origin_type)

    # desired_modulation == MOD_INCREASE: knockdown moved this arm the UNDESIRED way.
    if reducing:
        return _out(wf.OPPOSED, wf.REASON_ACTION_OPPOSES, origin_type)
    if pathway:
        # The node states its own desired increase; an activator is compatible with it.
        return _out(wf.PATHWAY_HYPOTHESIS, wf.REASON_PATHWAY_COMPATIBLE, origin_type)
    # A DIRECT TARGET with a REAL sourced activation/agonism mechanism. This is the
    # inverse-direction hypothesis: a distinct, named state — never observed support,
    # never observed gain of function, and never the same evidence class as a
    # measurement.
    return _out(wf.INVERSE_DIRECTION_HYPOTHESIS, wf.REASON_INVERSE_ACTIVATION,
                origin_type)


def _out(status: str, reason: str, origin_type: str) -> dict[str, Any]:
    # Only a MEASURED direct target carries observed-perturbation support. An
    # inverse-direction hypothesis and a pathway hypothesis are inferences: false.
    supported = (status in wf.MEASURED_EVIDENCE
                 and origin_type == ORIGIN_DIRECT_TARGET)
    return {
        "directional_evidence_status": status,
        "directional_evidence_reason": reason,
        "origin_type": origin_type,
        "observed_perturbation_support": supported,
        # A LABEL, not a tier, and deliberately unordered. It exists so an inverse
        # hypothesis can never be filed under a measurement's evidence class.
        "stage3_evidence_class": wf.evidence_class(status),
    }


def vocabularies() -> dict[str, Any]:
    """The frozen direction vocabulary, hashed into every Stage-3 bundle id."""
    return {
        "direction_policy_version": DIRECTION_POLICY_VERSION,
        "modality_abundance_direction": dict(sorted(
            MODALITY_ABUNDANCE_DIRECTION.items())),
        "intervention_effects": list(INTERVENTION_EFFECTS),
        "action_abundance_reduction": sorted(ACTION_ABUNDANCE_REDUCTION),
        "action_functional_inhibition": sorted(ACTION_FUNCTIONAL_INHIBITION),
        "action_functional_activation": sorted(ACTION_FUNCTIONAL_ACTIVATION),
        "action_explicit_unknown": sorted(ACTION_EXPLICIT_UNKNOWN),
        "origin_types": list(ORIGIN_TYPES),
        "inhibition_is_not_abundance_reduction": True,
        "activation_is_never_inferred_from_inhibition": True,
        "pathway_node_is_never_a_measurement": True,
        "inverse_direction_hypothesis_requires_a_real_sourced_activation_mechanism": True,
        "inverse_direction_hypothesis_is_never_observed_gain_of_function": True,
        "association_is_never_converted_to_causality": True,
        "stage2_joint_context_never_infers_drug_direction": True,
    }
