"""The selection-independent v2 candidate/edge builder, attacked where it could give way.

NON-PRODUCTION FIXTURES (see :mod:`candidates_v2_fixture`). Every input declares
``artifact_class="fixture"``; no biological candidate is invented anywhere in this file.

NON-VACUITY IS THE FIRST TEST. Every assertion below runs over a build that is checked to be
NON-EMPTY first, and the counts are pinned: a suite that passes over zero edges proves that
the builder returned nothing, which is exactly the failure mode audit blocker B6 describes.
So the fixture is tuned until all five directional statuses and all three typed origins really
occur, and the tests assert that they do.

What is under test is B7: reusable arms, three typed origins, and NO selection role, NO
combined objective and NO candidate-level winner anywhere in the emitted evidence.
"""
from __future__ import annotations

import copy

import pytest

import candidates_v2_fixture as fx
from druglink import candidates_v2 as cv2
from druglink import direction as dr
from druglink import stage2_aggregate as sa
from druglink import workflow as wf
from druglink.hashing import canonical_json

# What the fixture MUST produce. Pinned, so a builder that silently stops emitting a lane
# fails here rather than passing vacuously.
N_EDGES = 1200
N_ARM_SUMMARIES = 600
N_CANDIDATES = 2
N_SOURCE_RECORDS = 5          # 4 rankable + 1 variant-specific (never rankable, never an edge)


@pytest.fixture(scope="module")
def admitted(tmp_path_factory):
    root = tmp_path_factory.mktemp("v2_aggregate")
    aggregate, paths = fx.admit(root)
    return {"aggregate": aggregate, "store": fx.store(), "paths": paths}


@pytest.fixture(scope="module")
def built(admitted):
    tables = cv2.build(artifact_class="fixture", aggregate=admitted["aggregate"],
                       store=admitted["store"])
    assert len(tables["edges"]) == N_EDGES, "non-vacuity: the build must produce edges"
    assert len(tables["arm_summaries"]) == N_ARM_SUMMARIES
    assert len(tables["candidates"]) == N_CANDIDATES
    assert len(tables["source_records"]) == N_SOURCE_RECORDS
    assert tables["dispositions"], "every absence must be NAMED, not merely absent"
    return tables


class TestTheBuildIsNonVacuous:
    def test_the_admitted_aggregate_is_the_whole_topology(self, admitted):
        assert len(admitted["aggregate"].bundles) == sa.N_BUNDLES == 15
        assert len(admitted["aggregate"].arms) == sa.N_ARM_SLOTS == 300

    def test_all_three_typed_origins_are_really_present(self, built):
        origins = {e["origin_type"] for e in built["edges"]}
        assert origins == set(cv2.V2_ORIGINS), (
            "a suite that never emits a temporal or a pathway edge cannot prove they are "
            f"kept apart; got {sorted(origins)}")

    def test_all_five_directional_statuses_are_really_present(self, built):
        statuses = {e["directional_evidence_status"] for e in built["edges"]}
        assert statuses == set(wf.DIRECTIONAL_EVIDENCE_STATUSES), sorted(statuses)


class TestEveryEdgeBindsWhatItStandsOn:
    def test_the_edge_carries_every_contracted_column(self, built):
        for edge in built["edges"]:
            assert set(edge) == set(cv2.EDGE_COLUMNS)

    def test_the_edge_binds_the_reusable_arm_and_its_context(self, built, admitted):
        keys = {a.arm_key for a in admitted["aggregate"].arms}
        for edge in built["edges"]:
            assert edge["arm_key"] in keys
            assert edge["lane"] and edge["program_id"] and edge["desired_change"]
            assert edge["arm_context_sha256"]
            ctx = (edge["condition"], edge["from_condition"], edge["to_condition"])
            assert any(c is not None for c in ctx), "an arm with no context is not reusable"

    def test_the_edge_binds_the_exact_typed_target_and_the_source_assertion(self, built):
        for edge in built["edges"]:
            assert edge["target_id"] and edge["target_id_namespace"]
            assert edge["mec_id"] is not None      # the ChEMBL mechanism row
            assert edge["source_record_id"] and edge["molecule_chembl_id"]
            assert edge["target_chembl_id"] and edge["action_type_source"]

    def test_the_edge_binds_the_direction_vocabulary_it_was_classified_under(self, built):
        digest = dr.vocabulary_digest()
        assert {e["direction_vocabulary_digest"] for e in built["edges"]} == {digest}

    def test_the_edge_binds_every_upstream_admission_hash(self, built, admitted):
        agg = admitted["aggregate"]
        for edge in built["edges"]:
            for col in cv2.UPSTREAM_COLUMNS:
                assert edge[col], f"{col} is unbound on {edge['edge_id']}"
            assert edge["stage2_manifest_raw_sha256"] == agg.manifest_raw_sha256
            assert edge["stage2_manifest_self_hash"] == agg.manifest_self_hash
            assert edge["stage2_independent_verdict"] == "admit"
            assert "independent" in edge["stage2_independent_verifier_id"]
            assert edge["stage1_release_sha256"] == agg.stage1_release_sha256

    def test_the_edge_carries_the_effect_the_status_and_the_class(self, built):
        for edge in built["edges"]:
            assert edge["intervention_effect"] in dr.INTERVENTION_EFFECTS
            assert edge["intervention_effect_reason"]
            assert edge["directional_evidence_status"] in wf.DIRECTIONAL_EVIDENCE_STATUSES
            assert edge["directional_evidence_reason"]
            assert edge["stage3_evidence_class"] in wf.EVIDENCE_CLASSES
            assert isinstance(edge["observed_perturbation_support"], bool)


class TestNoSelectionRoleIsEverBakedIn:
    """A ROLE is what a selection gives an arm at join time. Bake one in and two different
    questions share one key — and nothing downstream can un-fuse them."""

    @pytest.mark.parametrize("role", cv2.SELECTION_ROLES)
    def test_no_table_carries_a_pair_role(self, built, role):
        for name, rows in built.items():
            assert role not in canonical_json(rows), f"{name} carries the role {role!r}"

    def test_the_arm_identity_is_the_reusable_key(self, built):
        assert "desired_arm" not in cv2.EDGE_COLUMNS
        assert set(cv2.ARM_IDENTITY_COLUMNS) <= set(cv2.EDGE_COLUMNS)


class TestThereIsNoWinnerAndNoCrossOriginTotal:
    def test_a_candidate_has_no_rank_no_score_and_no_scalar_total(self, built):
        for candidate in built["candidates"]:
            for key in candidate:
                low = key.lower()
                assert "rank" not in low or key == "max_phase_is_context_only"
                assert "score" not in low and "winner" not in low
            # n_edges_by_origin is a MAP. A scalar total across origins would sum a measured
            # effect, a cross-time DiD and an inference into a number with no estimand.
            assert "n_edges" not in candidate
            assert set(candidate["n_edges_by_origin"]) == set(cv2.V2_ORIGINS)

    def test_candidate_ordering_is_by_content_id_not_by_evidence(self, built):
        ids = [c["candidate_id"] for c in built["candidates"]]
        assert ids == sorted(ids)

    def test_the_vocabulary_names_the_prohibition(self):
        vocab = cv2.vocabularies()
        assert vocab["combined_objective_permitted"] is False
        assert vocab["candidate_rank_permitted"] is False
        assert vocab["selection_roles_are_assigned_at_join_time_not_in_this_bundle"] is True


class TestTheThreeTypedOriginsNeverMerge:
    def test_the_lane_decides_the_origin(self, built):
        for edge in built["edges"]:
            assert cv2.ORIGIN_FOR_LANE[edge["lane"]] == edge["origin_type"]

    def test_direct_and_temporal_are_distinct_estimands_on_the_same_target(self, built):
        by_origin = {}
        for edge in built["edges"]:
            by_origin.setdefault(edge["origin_type"], set()).add(edge["target_id"])
        shared = (by_origin[dr.ORIGIN_DIRECT_TARGET]
                  & by_origin[dr.ORIGIN_TEMPORAL_CROSS_TIME])
        assert shared, "non-vacuity: the same target must appear on both measured lanes"
        # Same target, same drug, two DIFFERENT origins — and they never collapse into one row.
        direct = [e for e in built["edges"]
                  if e["origin_type"] == dr.ORIGIN_DIRECT_TARGET]
        temporal = [e for e in built["edges"]
                    if e["origin_type"] == dr.ORIGIN_TEMPORAL_CROSS_TIME]
        assert {e["edge_id"] for e in direct}.isdisjoint({e["edge_id"] for e in temporal})

    def test_a_measured_edge_names_what_the_screen_did(self, built):
        measured = [e for e in built["edges"] if e["origin_is_measured"]]
        assert measured
        assert all(e["perturbation_modality"] for e in measured)


class TestAnInferredNodeIsNeverAMeasurement:
    def test_a_pathway_edge_carries_no_rank_no_support_and_no_modality(self, built):
        pathway = [e for e in built["edges"]
                   if e["origin_type"] == dr.ORIGIN_ENDPOINT_PATHWAY]
        assert pathway, "non-vacuity: the pathway lane must produce edges"
        for edge in pathway:
            assert edge["arm_rank"] is None
            assert edge["observed_perturbation_support"] is False
            assert edge["perturbation_modality"] is None
            assert edge["directional_evidence_status"] != wf.OBSERVED_PERTURBATION

    def test_a_pathway_edge_with_a_measured_rank_is_REFUSED(self, built):
        edge = copy.deepcopy(next(e for e in built["edges"]
                                  if e["origin_type"] == dr.ORIGIN_ENDPOINT_PATHWAY))
        edge["arm_rank"] = 3
        with pytest.raises(cv2.CandidatesV2Error) as exc:
            cv2.check_edges([edge])
        assert exc.value.gate == cv2.GATE_INFERRED_ORIGIN_HAS_A_RANK

    def test_a_pathway_RECORD_with_a_measured_rank_is_REFUSED_at_build(self, tmp_path):
        def rank_the_pathway_nodes(docs):
            for key, doc in docs.items():
                if doc["lane"] == sa.LANE_PATHWAY:
                    for arm in doc["arms"]:
                        for rec in arm["records"]:
                            rec["rank"] = 3      # nobody perturbed it; it has no rank
        aggregate, _ = fx.admit(tmp_path / "ranked_pathway",
                                mutate_bundles=rank_the_pathway_nodes)
        with pytest.raises(cv2.CandidatesV2Error) as exc:
            cv2.build(artifact_class="fixture", aggregate=aggregate, store=fx.store())
        assert exc.value.gate == cv2.GATE_INFERRED_ORIGIN_HAS_A_RANK

    def test_a_pathway_edge_claiming_observed_support_is_REFUSED(self, built):
        edge = copy.deepcopy(next(e for e in built["edges"]
                                  if e["origin_type"] == dr.ORIGIN_ENDPOINT_PATHWAY))
        edge["observed_perturbation_support"] = True
        with pytest.raises(cv2.CandidatesV2Error) as exc:
            cv2.check_edges([edge])
        assert exc.value.gate == cv2.GATE_INFERRED_ORIGIN_HAS_SUPPORT

    def test_an_origin_that_disagrees_with_its_lane_is_REFUSED(self, built):
        edge = copy.deepcopy(built["edges"][0])
        edge["origin_type"] = (dr.ORIGIN_TEMPORAL_CROSS_TIME
                               if edge["origin_type"] == dr.ORIGIN_DIRECT_TARGET
                               else dr.ORIGIN_DIRECT_TARGET)
        with pytest.raises(cv2.CandidatesV2Error) as exc:
            cv2.check_edges([edge])
        assert exc.value.gate == cv2.GATE_ORIGIN_LANE_DISAGREE


class TestDirectionIsNeverInheritedFromSetMembership:
    def test_a_node_that_states_no_direction_of_its_own_is_INERT(self, built):
        # FIXTURE_TGT_01 sits in a gene SET on the pathway lane and states no modulation. It
        # must stay direction-less — never handed the direction of the set it belongs to.
        inert = [e for e in built["edges"]
                 if e["origin_type"] == dr.ORIGIN_ENDPOINT_PATHWAY
                 and e["target_id"] == fx.TGT_INCREASE]
        assert inert, "non-vacuity: the set-membership-only node must be in the build"
        for edge in inert:
            assert edge["set_id"], "the node IS in a set; that is the whole point"
            assert edge["desired_target_modulation"] == dr.MOD_NO_DIRECTION
            assert edge["directional_evidence_status"] == wf.UNRESOLVED
            assert edge["directional_evidence_reason"] == wf.REASON_NO_DIRECTION

    def test_a_node_with_its_own_sourced_direction_is_a_pathway_HYPOTHESIS(self, built):
        sourced = [e for e in built["edges"]
                   if e["origin_type"] == dr.ORIGIN_ENDPOINT_PATHWAY
                   and e["target_id"] == fx.TGT_DECREASE
                   and e["intervention_effect"] == dr.FUNCTIONAL_INHIBITION]
        assert sourced
        for edge in sourced:
            assert edge["directional_evidence_status"] == wf.PATHWAY_HYPOTHESIS
            assert edge["stage3_evidence_class"] == wf.CLASS_PATHWAY
            assert edge["observed_perturbation_support"] is False

    def test_an_unknown_stage2_modulation_is_REFUSED_not_read_as_no_direction(self):
        with pytest.raises(cv2.CandidatesV2Error) as exc:
            cv2.desired_modulation({"desired_target_modulation": "probably_good"},
                                   arm_key="arm")
        assert exc.value.gate == cv2.GATE_UNKNOWN_MODULATION


class TestTheInverseDirectionHypothesisIsNeverAMeasurement:
    def test_it_arises_only_from_a_real_sourced_activation_on_the_undesired_arm(self, built):
        inverse = [e for e in built["edges"]
                   if e["directional_evidence_status"] == wf.INVERSE_DIRECTION_HYPOTHESIS]
        assert inverse, "non-vacuity: the fixture must produce an inverse hypothesis"
        for edge in inverse:
            assert edge["target_id"] == fx.TGT_INCREASE
            assert edge["intervention_effect"] == dr.FUNCTIONAL_ACTIVATION
            assert edge["origin_is_measured"] is True
            # It is NOT observed gain of function, and never a measurement's evidence class.
            assert edge["observed_perturbation_support"] is False
            assert edge["stage3_evidence_class"] == wf.CLASS_INVERSE

    def test_observed_support_requires_a_measured_origin_AND_a_measured_status(self, built):
        for edge in built["edges"]:
            if edge["observed_perturbation_support"]:
                assert edge["origin_is_measured"] is True
                assert edge["directional_evidence_status"] == wf.OBSERVED_PERTURBATION


class TestNullsAndRanksSurviveVerbatim:
    def test_an_unranked_measured_target_reaches_its_edge_as_NULL(self, built):
        unranked = [e for e in built["edges"]
                    if e["origin_is_measured"] and e["target_id"] == fx.TGT_INCREASE]
        assert unranked
        assert all(e["arm_rank"] is None for e in unranked), (
            "unranked is a STATE: never 0, never last, never invented")

    def test_a_ranked_measured_target_carries_stage2s_own_rank(self, built):
        ranked = [e for e in built["edges"]
                  if e["origin_is_measured"] and e["target_id"] == fx.TGT_DECREASE]
        assert ranked
        assert {e["arm_rank"] for e in ranked} == {1}

    def test_the_arm_value_travels_as_an_exact_string_never_a_float(self, built):
        measured = [e for e in built["edges"] if e["origin_is_measured"]]
        assert measured
        for edge in measured:
            assert isinstance(edge["arm_value_source_string"], str)
            assert isinstance(edge["arm_value_canonical_decimal"], str)


class TestNonRankableAssertionsArePreservedAndNeverRank:
    def test_a_variant_assertion_never_becomes_an_edge(self, built):
        assert fx.MEC_VARIANT in {s["mec_id"] for s in built["source_records"]}
        assert fx.MEC_VARIANT not in {e["mec_id"] for e in built["edges"]}
        assert fx.MOL_VARIANT_ONLY not in {c["molecule_chembl_ids"][0]
                                           for c in built["candidates"]}

    def test_every_edge_comes_from_the_general_gene_lane(self, built):
        assert {e["assertion_lane"] for e in built["edges"]} == {"general_gene_rankable"}
        assert all(e["general_gene_rankable"] is True for e in built["edges"])

    def test_the_non_rankable_assertion_is_kept_as_a_named_disposition(self, built):
        states = {d["state"] for d in built["dispositions"]}
        assert cv2.STATE_NON_RANKABLE in states


class TestEveryAbsenceIsNamed:
    def test_a_target_outside_the_admitted_universe_is_named_not_dropped(self, built):
        rows = [d for d in built["dispositions"]
                if d["state"] == cv2.STATE_NOT_IN_UNIVERSE]
        assert [r["target_id"] for r in rows] == [fx.TGT_OFF_UNIVERSE]

    def test_an_unreachable_namespace_is_not_an_absence_of_drug_evidence(self, built):
        rows = [d for d in built["dispositions"]
                if d["state"] == cv2.STATE_UNSUPPORTED_NAMESPACE]
        assert [r["target_id"] for r in rows] == [fx.TGT_UNSUPPORTED]

    def test_a_target_with_no_source_assertion_says_so(self, built):
        rows = [d for d in built["dispositions"]
                if d["state"] == cv2.STATE_NO_DRUG_EVIDENCE]
        assert [r["target_id"] for r in rows] == [fx.TGT_NO_DRUGS]

    def test_a_candidate_stage4_is_not_asked_to_assess_stays_visible(self, built):
        not_queued = [d for d in built["dispositions"]
                      if d["state"] == cv2.STATE_NOT_QUEUED]
        assert len(not_queued) == N_CANDIDATES      # a fixture never reaches Stage 4
        assert all(d["reason"] == wf.REASON_NOT_QUEUED_FIXTURE for d in not_queued)


class TestSummariesSeparateWhatTheEvidenceSeparates:
    def test_a_summary_is_per_candidate_per_ARM_per_ORIGIN(self, built):
        keys = [(s["candidate_id"], s["arm_key"], s["origin_type"])
                for s in built["arm_summaries"]]
        assert len(keys) == len(set(keys))

    def test_a_summary_never_pools_two_origins(self, built):
        for summary in built["arm_summaries"]:
            edges = [e for e in built["edges"] if e["edge_id"] in summary["edge_ids"]]
            assert {e["origin_type"] for e in edges} == {summary["origin_type"]}

    def test_an_inferred_summary_carries_no_rank_and_no_support(self, built):
        inferred = [s for s in built["arm_summaries"]
                    if s["origin_type"] == dr.ORIGIN_ENDPOINT_PATHWAY]
        assert inferred
        for summary in inferred:
            assert summary["arm_ranks"] == []
            assert summary["observed_perturbation_support"] is False


class TestTheBuildIsDeterministic:
    def test_two_builds_of_the_same_inputs_are_identical(self, admitted, built):
        again = cv2.build(artifact_class="fixture", aggregate=admitted["aggregate"],
                          store=admitted["store"])
        for name, rows in built.items():
            assert canonical_json(again[name]) == canonical_json(rows), name
