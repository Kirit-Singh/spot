"""Mechanistically honest action vocabulary, and the directional evidence statuses.

The defects this locks shut:

  1. an INHIBITOR was called ``pharmacologic_effect=decrease`` and compared to a CRISPRi
     ABUNDANCE direction — asserting that blocking activity is the same as having less;
  2. a degrader was indistinguishable from a functional inhibitor;
  3. **activation was inferrable from inhibition**;
  4. an activator wanted by a NEGATIVE arm score was counted as evidence, when it aligns
     only with the UNTESTED inverse of a deleterious result.
"""
from __future__ import annotations

import pytest

from druglink import direction, science_review, workflow as wf
from druglink.direction import (ABUNDANCE_REDUCTION, FUNCTIONAL_ACTIVATION,
                                FUNCTIONAL_INHIBITION, ORIGIN_DIRECT_TARGET,
                                ORIGIN_PATHWAY_NODE)


@pytest.mark.parametrize("action", [
    "INHIBITOR", "ANTAGONIST", "BLOCKER", "NEGATIVE ALLOSTERIC MODULATOR",
    "NEGATIVE MODULATOR", "INVERSE AGONIST",
])
def test_functional_inhibitor_is_not_abundance_reduction(action):
    effect, reason = direction.intervention_effect(action)

    assert effect == FUNCTIONAL_INHIBITION
    assert effect != ABUNDANCE_REDUCTION
    # Never rendered or serialized as a claim about target ABUNDANCE. The word appears
    # only where an abundance change is actually asserted.
    assert "abundance" not in reason
    assert "not_target_level" in reason
    assert effect != "decrease"          # the retired vocabulary is gone

    # Still mechanistically compatible with the tested knockdown direction.
    out = direction.translate(desired_modulation="decrease", effect=effect,
                              arm_evaluable=True,
                              target_entity_is_single_protein=True)
    assert out["directional_evidence_status"] == wf.OBSERVED_PERTURBATION
    assert out["directional_evidence_reason"] == wf.REASON_ACTION_MATCHES_TESTED
    assert out["observed_perturbation_support"] is True


@pytest.mark.parametrize("action", [
    "DEGRADER", "DOWNREGULATOR", "PROTEOLYSIS TARGETING CHIMERA",
    "ANTISENSE INHIBITOR", "RNAI INHIBITOR",
])
def test_degrader_remains_abundance_reduction(action):
    effect, reason = direction.intervention_effect(action)

    assert effect == ABUNDANCE_REDUCTION
    assert "abundance" in reason
    # Degraders stay DISTINGUISHABLE from functional inhibitors.
    assert effect != FUNCTIONAL_INHIBITION
    assert direction.intervention_effect("INHIBITOR")[0] != effect

    out = direction.translate(desired_modulation="decrease", effect=effect,
                              arm_evaluable=True,
                              target_entity_is_single_protein=True)
    assert out["directional_evidence_status"] == wf.OBSERVED_PERTURBATION


def test_activation_is_never_inferred_from_inhibition():
    """No inhibitory action may ever yield functional_activation, under any name."""
    for action in (direction.ACTION_FUNCTIONAL_INHIBITION
                   | direction.ACTION_ABUNDANCE_REDUCTION):
        effect, _ = direction.intervention_effect(action)
        assert effect != FUNCTIONAL_ACTIVATION, action

    # And an inhibitor on an arm that wants an INCREASE is OPPOSED — never quietly
    # flipped into an activation.
    out = direction.translate(desired_modulation="increase",
                              effect=FUNCTIONAL_INHIBITION, arm_evaluable=True,
                              target_entity_is_single_protein=True)
    assert out["directional_evidence_status"] == wf.OPPOSED
    assert out["directional_evidence_reason"] == wf.REASON_ACTION_OPPOSES


def test_inverse_direction_hypothesis_is_a_distinct_state():
    """Knockdown moved the arm the UNDESIRED way, and a REAL activation exists.

    That is its own state — never folded into `unresolved`, and never folded into
    observed support. It is queued for a Stage-4 LOOK, and Claude Science reviews its
    biological plausibility later.
    """
    effect, _ = direction.intervention_effect("AGONIST")
    assert effect == FUNCTIONAL_ACTIVATION

    inverse = direction.translate(desired_modulation="increase", effect=effect,
                                  arm_evaluable=True,
                                  target_entity_is_single_protein=True)

    # A distinct, named status. NOT unresolved, NOT observed support.
    assert inverse["directional_evidence_status"] == wf.INVERSE_DIRECTION_HYPOTHESIS
    assert inverse["directional_evidence_status"] != wf.UNRESOLVED
    assert inverse["directional_evidence_status"] != wf.OBSERVED_PERTURBATION
    assert inverse["directional_evidence_reason"] == wf.REASON_INVERSE_ACTIVATION

    # It is NOT observed gain of function.
    assert inverse["observed_perturbation_support"] is False
    assert wf.MEASURED_EVIDENCE == frozenset({wf.OBSERVED_PERTURBATION})

    # It does NOT share an evidence class with a measurement, and the class is unordered.
    assert inverse["stage3_evidence_class"] == wf.CLASS_INVERSE
    assert inverse["stage3_evidence_class"] != wf.CLASS_MEASURED
    assert wf.EVIDENCE_CLASSES_ARE_UNORDERED is True

    # It IS queued — with its own reason code. Queuing is a look, not an endorsement.
    #
    # This line used to assert membership in DIRECTION_COMPATIBLE, which is how the conflation
    # was locked in: the comment says "queued", the assertion said "direction-compatible", and
    # one frozenset was answering both questions. Queue-eligibility is what "it IS queued"
    # actually means; direction-compatible EVIDENCE is a claim the untested inverse cannot make.
    assert wf.INVERSE_DIRECTION_HYPOTHESIS in wf.QUEUE_ELIGIBLE
    assert wf.INVERSE_DIRECTION_HYPOTHESIS not in wf.DIRECTION_COMPATIBLE
    status, reason = wf.stage4_assessment(
        artifact_class="analysis", identity_status="resolved",
        active_moiety_id="AM:CHEMBL:CHEMBL1",
        directional_statuses={wf.INVERSE_DIRECTION_HYPOTHESIS})
    assert status == wf.QUEUED
    assert reason == wf.REASON_QUEUED_INVERSE == "mapped_inverse_direction_hypothesis"

    # Claude Science reviews plausibility LATER; Stage 3 only flags it.
    # The review is owned by science_review, and an un-reviewed inverse hypothesis is
    # PENDING — never favourable, never quietly not_required.
    pending = science_review.for_candidate({}, "M1", has_inverse=True)
    assert pending["disease_context_review_status"] == science_review.PENDING
    assert pending["disease_context_review_result"] is None
    assert science_review.for_candidate({}, "M1", has_inverse=False)[
        "disease_context_review_status"] == science_review.NOT_REQUIRED

    # A measurement always outranks it in the summary; it never masks an opposed action.
    assert wf.summary_state({wf.OBSERVED_PERTURBATION,
                             wf.INVERSE_DIRECTION_HYPOTHESIS}) == (
        wf.OBSERVED_PERTURBATION)
    assert wf.summary_state({wf.OPPOSED, wf.INVERSE_DIRECTION_HYPOTHESIS}) == wf.OPPOSED

    # On the arm that WAS tested, an activator is opposed — not a hypothesis.
    assert direction.translate(
        desired_modulation="decrease", effect=effect, arm_evaluable=True,
        target_entity_is_single_protein=True
    )["directional_evidence_status"] == wf.OPPOSED


def test_no_activation_mechanism_means_no_inverse_hypothesis_is_invented():
    """If nothing activates the target, Stage 3 invents nothing."""
    # An inhibitor on the undesired-direction arm is OPPOSED — not converted.
    assert direction.translate(
        desired_modulation="increase", effect=FUNCTIONAL_INHIBITION,
        arm_evaluable=True, target_entity_is_single_protein=True
    )["directional_evidence_status"] == wf.OPPOSED

    # An unknown action stays UNRESOLVED — never upgraded into a hypothesis.
    out = direction.translate(
        desired_modulation="increase", effect="unknown", arm_evaluable=True,
        target_entity_is_single_protein=True)
    assert out["directional_evidence_status"] == wf.UNRESOLVED
    assert out["directional_evidence_reason"] == wf.REASON_ACTION_UNKNOWN

    # With no direction-compatible evidence at all, the candidate is NOT queued.
    assert wf.stage4_assessment(
        artifact_class="analysis", identity_status="resolved",
        active_moiety_id="AM:CHEMBL:CHEMBL1",
        directional_statuses={wf.OPPOSED, wf.UNRESOLVED}
    ) == (wf.NOT_QUEUED, wf.REASON_NOT_QUEUED_NO_EVIDENCE)


def test_a_pathway_node_can_never_be_an_observed_perturbation():
    """Same action, same arm — but the node was never perturbed."""
    for modulation in ("decrease", "increase"):
        effect = (FUNCTIONAL_INHIBITION if modulation == "decrease"
                  else FUNCTIONAL_ACTIVATION)
        node = direction.translate(
            desired_modulation=modulation, effect=effect, arm_evaluable=True,
            target_entity_is_single_protein=True,
            origin_type=ORIGIN_PATHWAY_NODE)
        assert node["directional_evidence_status"] == wf.PATHWAY_HYPOTHESIS
        assert node["observed_perturbation_support"] is False

    # The very same call on a MEASURED target is an observed perturbation.
    target = direction.translate(
        desired_modulation="decrease", effect=FUNCTIONAL_INHIBITION,
        arm_evaluable=True, target_entity_is_single_protein=True,
        origin_type=ORIGIN_DIRECT_TARGET)
    assert target["directional_evidence_status"] == wf.OBSERVED_PERTURBATION
    assert target["observed_perturbation_support"] is True


def test_everything_else_fails_closed_to_unresolved():
    for modulation in ("no_direction_evidence", "not_evaluated"):
        out = direction.translate(
            desired_modulation=modulation, effect=FUNCTIONAL_INHIBITION,
            arm_evaluable=True, target_entity_is_single_protein=True)
        assert out["directional_evidence_status"] == wf.UNRESOLVED
        assert out["observed_perturbation_support"] is False

    # A non-evaluable arm never acquires a direction from a drug label.
    assert direction.translate(
        desired_modulation="decrease", effect=FUNCTIONAL_INHIBITION,
        arm_evaluable=False, target_entity_is_single_protein=True
    )["directional_evidence_reason"] == wf.REASON_ARM_NOT_EVALUABLE

    # A complex/family is not a gene, in either arm.
    assert direction.translate(
        desired_modulation="decrease", effect=FUNCTIONAL_INHIBITION,
        arm_evaluable=True, target_entity_is_single_protein=False
    )["directional_evidence_reason"] == wf.REASON_NOT_SINGLE_PROTEIN

    # Contradictory sourced actions resolve to unresolved, not to a winner.
    assert direction.translate(
        desired_modulation="decrease", effect=FUNCTIONAL_INHIBITION,
        arm_evaluable=True, target_entity_is_single_protein=True,
        action_conflict=True
    )["directional_evidence_reason"] == wf.REASON_ACTION_CONFLICT

    # An unrecognised action fails closed rather than guessing.
    assert direction.intervention_effect("SOMETHING NOBODY ENUMERATED")[0] == "unknown"
    assert direction.intervention_effect(None)[0] == "unknown"
    assert direction.intervention_effect("BINDING AGENT")[0] == "unknown"


def test_real_conflict_row_keeps_both_arms_apart(analysis_build):
    """End-to-end on REAL public evidence: one target, two opposite arms.

    The SAME real drug is an observed_perturbation on one arm and OPPOSED on the other.
    Both edges survive. A contract test, not a scientific finding.
    """
    levers = analysis_build["tables"]["arm_levers"]
    edges = analysis_build["tables"]["target_drug_edges"]

    mods: dict[str, dict[str, str]] = {}
    for row in levers:
        mods.setdefault(row["target_ensembl"] or row["target_id"], {})[
            row["desired_arm"]] = row["arm_desired_target_modulation"]
    conflict = [g for g, m in mods.items()
                if {m.get("away_from_A"), m.get("toward_B")} == {"decrease", "increase"}]
    assert conflict, "the run must contain a cross-arm conflict target"

    direct_gene = [e for e in edges if e["target_ensembl"] in conflict
                   and e["lane"] == "direct_gene_mechanism"]
    assert direct_gene, "the conflict target must carry real direct-gene drug edges"

    by_arm: dict[str, set[str]] = {}
    for edge in direct_gene:
        by_arm.setdefault(edge["desired_arm"], set()).add(
            edge["directional_evidence_status"])

    assert wf.OBSERVED_PERTURBATION in by_arm["away_from_A"]
    assert wf.OPPOSED in by_arm["toward_B"]
    assert wf.OBSERVED_PERTURBATION not in by_arm["toward_B"]
    assert {e["desired_arm"] for e in direct_gene} == {"away_from_A", "toward_B"}

    # The source action string survives verbatim, and an inhibitor's effect is a
    # FUNCTION claim — never a target-abundance claim.
    inhibitors = [e for e in direct_gene
                  if e["intervention_effect"] == FUNCTIONAL_INHIBITION]
    assert inhibitors
    for edge in inhibitors:
        assert edge["action_type_sources"]
        assert "abundance" not in edge["intervention_effect_reason"]
