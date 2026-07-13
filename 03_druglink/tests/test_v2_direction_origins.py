"""The frozen direction engine must UNDERSTAND all three typed origins.

The v2 loader stamps three origins. `direction.translate` knew only two — `direct_target` and
the v1 `pathway_node` — and its first guard is:

    if origin_type not in ORIGIN_TYPES:
        return _out(UNRESOLVED, REASON_ARM_NOT_EVALUABLE, origin_type)

So every `temporal_cross_time_measured` lever and every `endpoint_pathway_context` node would
have come back UNRESOLVED. Not refused — UNRESOLVED, which reads as "we looked and the evidence
did not resolve", when in fact nobody looked at all. Real measured cross-time evidence would
have been silently discarded under a status that says it was considered.

The frozen v2 admission contract (verifier/v2_admission.py, which this file does NOT import —
generator != verifier) fixes the vocabulary:

    MEASURED_ORIGINS  = {direct_target, temporal_cross_time_measured}
    INFERRED_ORIGINS  = {endpoint_pathway_context}

and rule 3: direction compatibility is decided by the FROZEN DIRECTION ENGINE, at view time —
never by the cache and never by the loader. So the engine is what must learn them.

WHAT MUST NOT MOVE
------------------
  * OBSERVED_PERTURBATION (the drug runs WITH the tested CRISPRi knockdown) and
    INVERSE_DIRECTION_HYPOTHESIS (knockdown moved the arm the UNDESIRED way, so an activator is
    a pharmacologic HYPOTHESIS) are DISTINCT states. The second is never observed support and
    never a measurement's evidence class;
  * `observed_perturbation_support` is true only for a MEASURED origin in a MEASURED status.
    An inferred node was never perturbed, so it can never carry it;
  * Direct and temporal are both measured and are NEVER fused: they keep distinct origin_type
    values on the row, and nothing pools them.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "analysis"))

from druglink import direction as d          # noqa: E402
from druglink import workflow as wf          # noqa: E402

DIRECT = "direct_target"
TEMPORAL = "temporal_cross_time_measured"
PATHWAY_V2 = "endpoint_pathway_context"
PATHWAY_V1 = "pathway_node"

INHIBITOR = d.FUNCTIONAL_INHIBITION          # a reducing action
ACTIVATOR = d.FUNCTIONAL_ACTIVATION          # a non-reducing action


def translate(origin, modulation, effect):
    return d.translate(desired_modulation=modulation, effect=effect,
                       arm_evaluable=True, target_entity_is_single_protein=True,
                       origin_type=origin)


class TestTheEngineKnowsAllThreeTypedOrigins:
    def test_a_TEMPORAL_lever_is_not_silently_UNRESOLVED(self):
        # the defect: an origin the engine did not know came back "unresolved", which reads as
        # "considered and did not resolve" when nothing considered it at all
        out = translate(TEMPORAL, d.MOD_DECREASE, INHIBITOR)
        assert out["directional_evidence_status"] != wf.UNRESOLVED
        assert out["directional_evidence_status"] == wf.OBSERVED_PERTURBATION

    def test_an_ENDPOINT_PATHWAY_node_is_not_silently_UNRESOLVED(self):
        out = translate(PATHWAY_V2, d.MOD_DECREASE, INHIBITOR)
        assert out["directional_evidence_status"] == wf.PATHWAY_HYPOTHESIS

    def test_the_v1_pathway_node_origin_still_works(self):
        # v1 consumers (pathways.py, mechanisms.py) still stamp pathway_node
        out = translate(PATHWAY_V1, d.MOD_DECREASE, INHIBITOR)
        assert out["directional_evidence_status"] == wf.PATHWAY_HYPOTHESIS

    def test_an_UNKNOWN_origin_is_still_refused(self):
        # widening the vocabulary must not open it: an origin nobody declared stays unresolved
        out = translate("made_up_origin", d.MOD_DECREASE, INHIBITOR)
        assert out["directional_evidence_status"] == wf.UNRESOLVED
        assert out["observed_perturbation_support"] is False


class TestObservedKnockdownIsNEVERTheInversePharmacologicHypothesis:
    """The separation the whole lane exists to protect."""

    def test_a_drug_running_WITH_the_tested_knockdown_is_OBSERVED(self):
        for origin in (DIRECT, TEMPORAL):
            out = translate(origin, d.MOD_DECREASE, INHIBITOR)
            assert out["directional_evidence_status"] == wf.OBSERVED_PERTURBATION
            assert out["observed_perturbation_support"] is True

    def test_a_drug_running_AGAINST_the_undesired_knockdown_is_a_HYPOTHESIS_not_support(self):
        # knockdown moved the arm the UNDESIRED way; an activator is a pharmacologic
        # hypothesis about the inverse direction. It was never observed.
        for origin in (DIRECT, TEMPORAL):
            out = translate(origin, d.MOD_INCREASE, ACTIVATOR)
            assert out["directional_evidence_status"] == wf.INVERSE_DIRECTION_HYPOTHESIS
            assert out["observed_perturbation_support"] is False, (
                "an inverse pharmacologic hypothesis was filed as observed support")

    def test_the_two_states_are_never_the_same_evidence_class(self):
        observed = translate(TEMPORAL, d.MOD_DECREASE, INHIBITOR)
        inverse = translate(TEMPORAL, d.MOD_INCREASE, ACTIVATOR)
        assert observed["stage3_evidence_class"] != inverse["stage3_evidence_class"]
        assert wf.OBSERVED_PERTURBATION in wf.MEASURED_EVIDENCE
        assert wf.INVERSE_DIRECTION_HYPOTHESIS not in wf.MEASURED_EVIDENCE

    def test_an_opposed_drug_is_opposed_for_every_measured_origin(self):
        for origin in (DIRECT, TEMPORAL):
            assert translate(origin, d.MOD_DECREASE, ACTIVATOR)[
                "directional_evidence_status"] == wf.OPPOSED
            assert translate(origin, d.MOD_INCREASE, INHIBITOR)[
                "directional_evidence_status"] == wf.OPPOSED


class TestAnInferredNodeCanNeverCarryMeasuredSupport:
    def test_no_pathway_origin_ever_carries_observed_perturbation_support(self):
        for origin in (PATHWAY_V1, PATHWAY_V2):
            for mod, eff in ((d.MOD_DECREASE, INHIBITOR), (d.MOD_INCREASE, ACTIVATOR)):
                out = translate(origin, mod, eff)
                assert out["observed_perturbation_support"] is False, (
                    "an inferred node was never perturbed and cannot support anything")
                assert out["directional_evidence_status"] != wf.OBSERVED_PERTURBATION
                assert out["directional_evidence_status"] != wf.INVERSE_DIRECTION_HYPOTHESIS


class TestDirectAndTemporalAreBothMeasuredAndNEVERFused:
    def test_both_are_measured_origins(self):
        assert d.MEASURED_ORIGINS == frozenset({DIRECT, TEMPORAL})

    def test_the_inferred_origins_are_disjoint_from_the_measured_ones(self):
        assert not (d.MEASURED_ORIGINS & d.INFERRED_ORIGINS)
        assert PATHWAY_V2 in d.INFERRED_ORIGINS

    def test_the_origin_STAYS_ON_the_row_so_nothing_has_to_infer_it(self):
        # Direct and temporal reach the same status by the same rule, and are still told
        # apart without inference — which is the whole point of stamping the origin.
        direct = translate(DIRECT, d.MOD_DECREASE, INHIBITOR)
        temporal = translate(TEMPORAL, d.MOD_DECREASE, INHIBITOR)
        assert direct["directional_evidence_status"] == \
            temporal["directional_evidence_status"]
        assert direct["origin_type"] != temporal["origin_type"]

    def test_the_V2_vocabulary_DECLARES_the_origin_sets(self):
        v = d.v2_origin_vocabulary()
        assert set(v["origin_types"]) == {DIRECT, TEMPORAL, PATHWAY_V2}
        assert set(v["measured_origins"]) == {DIRECT, TEMPORAL}
        assert v["direct_and_temporal_are_distinct_estimands_never_fused"] is True
        assert v["inferred_origin_can_never_carry_observed_support"] is True
        assert v["observed_knockdown_direction_is_never_the_inverse_pharmacologic_hypothesis"]
        assert v["combined_objective_permitted"] is False


class TestTheFROZENv1ContractDidNotMove:
    """Teaching the engine new origins must not move bytes Stage 4 is bound to.

    `vocabularies()` is hashed into every v1 bundle id and validated against the FROZEN Stage-3
    schema set, whose SHAs Stage 4 pins. A v1 bundle contains only v1 origins, so it still says
    so. Widening it here would have silently broken the consumer the freeze exists to protect —
    and re-pinning the freeze to make a test pass is the one thing the unfreeze note forbids.
    """

    def test_the_frozen_v1_vocabulary_still_lists_ONLY_the_v1_origins(self):
        assert d.vocabularies()["origin_types"] == list(d.V1_ORIGIN_TYPES)
        assert d.vocabularies()["origin_types"] == [DIRECT, PATHWAY_V1]

    def test_the_v2_terms_are_NOT_in_the_frozen_v1_document(self):
        blob = str(d.vocabularies())
        assert TEMPORAL not in blob
        assert PATHWAY_V2 not in blob

    def test_the_ENGINE_still_resolves_all_four_even_though_the_v1_doc_lists_two(self):
        # the distinction the whole split rests on: what the engine can RESOLVE is not what a
        # v1 bundle CONTAINS
        assert set(d.ORIGIN_TYPES) == {DIRECT, TEMPORAL, PATHWAY_V2, PATHWAY_V1}
        assert translate(TEMPORAL, d.MOD_DECREASE, INHIBITOR)[
            "directional_evidence_status"] == wf.OBSERVED_PERTURBATION
