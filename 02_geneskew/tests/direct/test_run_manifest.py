"""The aggregate run manifest: which ARMS belong to the same Stage-2 run, and is it whole.

Counting invocations was never completeness. Three copies of one Direct result counted as
three and passed. A run is complete when every LOGICAL ARM SLOT the frozen release implies
is filled exactly once — and the arms are keyed by DESIRED CHANGE, because that, and not
the pole direction, is what fixes the sign of the arm value.

All bundles here are FIXTURES (``fixtures_run_manifest``). The cardinality is real.
"""
from __future__ import annotations

import json
import os
import shutil

import fixtures_run_manifest as F
import pytest
from direct import arm_topology as T
from direct import config, run_manifest


def _build(tmp_path, run, **kw):
    release = run_manifest.load_release(run["release_path"], run["release_root"])
    bundles = [run_manifest.bind_bundle(d)
               for d in run["direct"] + run["temporal"] + run["pathway"]]
    return run_manifest.build(
        bundles=bundles, out_path=os.path.join(str(tmp_path), "manifest.json"),
        release=release,
        code_identity={"commit": "f" * 40, "clean_tree": True,
                       "manifest_sha256": "0" * 64, "canonical_digest": "0" * 16},
        **kw)


class TestTheDesiredChangeMapping:
    """The arm key is the DESIRED CHANGE. Role and pole decide it only jointly."""

    @pytest.mark.parametrize("role,pole,expected", [
        ("away_from_A", "high", T.DECREASE),
        ("away_from_A", "low", T.INCREASE),
        ("toward_B", "high", T.INCREASE),
        ("toward_B", "low", T.DECREASE),
    ])
    def test_all_four_role_x_pole_combinations(self, role, pole, expected):
        assert T.desired_change_for(role, pole) == expected

    def test_the_mapping_is_DERIVED_from_the_producers_own_arm_algebra(self):
        # not transcribed: it falls out of ARM_FORMULA x POLE_SIGN, so it cannot drift
        # away from the arithmetic the screen actually performs
        for role in config.ARMS:
            for pole, sign in config.POLE_SIGN.items():
                mult = -sign if role == config.ARM_A else sign
                want = T.INCREASE if mult > 0 else T.DECREASE
                assert T.desired_change_for(role, pole) == want

    def test_the_same_pole_in_the_two_ROLES_is_the_OPPOSITE_desired_change(self):
        # THE bug the pole-direction key would have shipped: away_from_A(high) DECREASES
        # the program and toward_B(high) INCREASES it. Keyed by pole, they collide.
        assert (T.desired_change_for("away_from_A", "high")
                != T.desired_change_for("toward_B", "high"))
        assert (T.desired_change_for("away_from_A", "low")
                != T.desired_change_for("toward_B", "low"))

    def test_the_two_origins_that_mean_the_SAME_thing_share_one_arm(self):
        # away_from_A(high) and toward_B(low) both compute -delta: ONE arm, two origins.
        assert (T.desired_change_for("away_from_A", "high")
                == T.desired_change_for("toward_B", "low") == T.DECREASE)
        assert (T.desired_change_for("away_from_A", "low")
                == T.desired_change_for("toward_B", "high") == T.INCREASE)

    def test_the_same_program_and_pole_ACROSS_TIME_is_one_desired_change_two_slots(self):
        # same program, same pole, two ordered pairs -> the SAME desired change, and two
        # DISTINCT temporal slots. A cross-time question is not a within-condition one.
        dc = T.desired_change_for("toward_B", "high")
        a = T.arm_key("temporal", "treg_like", dc,
                      {"from_condition": "Rest", "to_condition": "Stim8hr"})
        b = T.arm_key("temporal", "treg_like", dc,
                      {"from_condition": "Stim8hr", "to_condition": "Rest"})
        assert a != b
        assert a == "temporal|treg_like|increase|Rest|Stim8hr"

    def test_the_key_carries_neither_the_role_nor_the_pole(self):
        key = T.arm_key("direct", "treg_like", T.DECREASE, {"condition": "Rest"})
        assert key == "direct|treg_like|decrease|Rest"
        for token in ("away_from_A", "toward_B", "high", "low"):
            assert token not in key


class TestTheTopology:
    def test_a_complete_run_is_300_arm_slots_over_15_bundles(self, tmp_path):
        run = F.complete_run(tmp_path)
        doc = _build(tmp_path, run)
        assert doc["topology_complete"] is True
        assert doc["n_expected_arm_slots"] == doc["n_bound_arm_slots"] == 300
        assert doc["n_bundles"] == doc["n_expected_bundles"] == 15
        assert {lane: doc["per_lane"][lane]["n_expected_slots"] for lane in T.LANES} == {
            "direct": 60, "temporal": 120, "pathway": 120}
        assert {lane: doc["per_lane"][lane]["n_bundles_expected"] for lane in T.LANES} == {
            "direct": 3, "temporal": 6, "pathway": 6}

    def test_every_bundle_carries_EVERY_program_arm(self, tmp_path):
        run = F.complete_run(tmp_path)
        doc = _build(tmp_path, run)
        for b in doc["bundles"]:
            assert b["n_arms"] == 2 * len(run["programs"]) == 20

    def test_the_slot_algebra_is_derived_from_the_release(self):
        # 4 programs, 2 conditions -> 4*2*2 direct, 4*2*2 temporal (2 ordered pairs),
        # 4*2*2*2 pathway. Nothing is hard-coded.
        slots = T.expected_slots(["a", "b", "c", "d"], ["C1", "C2"], ["s1", "s2"])
        assert len(slots["direct"]) == 16
        assert len(slots["temporal"]) == 16
        assert len(slots["pathway"]) == 32

    def test_the_selection_capacity_is_3540(self):
        cap = T.selection_capacity(n_programs=10, n_conditions=3)
        assert cap["pole_states_per_condition"] == 20
        assert cap["within_condition_selections"] == 3 * 20 * 19 == 1140
        assert cap["temporal_selections"] == 6 * 20 * 20 == 2400
        assert cap["total_valid_ordered_selections"] == 3540

    def test_the_manifest_publishes_no_fixed_pair(self, tmp_path):
        run = F.complete_run(tmp_path)
        doc = _build(tmp_path, run)
        assert doc["combined_objective"] is None
        assert doc["cross_arm_score_or_order"] is None
        assert doc["combined_objective_permitted"] is False
        assert doc["pair_derived_views"]["stored_in_reusable_arm_bundles"] is False
        assert doc["pair_derived_views"]["part_of_release_completeness"] is False


class TestTheAuthoritativeReleaseIsTheSourceOfTruth:
    """The REAL release (55899ac), not a scorer view we wished for.

    The previous version of these tests built a view carrying
    ``base_portable_programs`` / ``base_portability_source_field`` / per-program
    ``method_hash``. None of those fields exists, so the suite was green against a fiction.
    """

    def test_the_admitted_set_is_DERIVED_from_program_base_portable(self, tmp_path):
        run = F.complete_run(tmp_path)
        rel = run_manifest.load_release(run["release_path"], run["release_root"])
        view = run["staged"]["view"]
        assert rel["programs"] == sorted(
            p["program_id"] for p in view["programs"] if p["base_portable"])
        assert rel["n_programs"] == 10
        assert rel["admitted_set_rederived_from_base_portable"] is True

    def test_the_derivation_is_CHECKED_against_the_releases_own_selector(self, tmp_path):
        # two independent statements of the same fact; a disagreement refuses the release
        run = F.complete_run(tmp_path)
        rel = run_manifest.load_release(run["release_path"], run["release_root"])
        assert rel["programs"] == sorted(
            run["staged"]["release"]["selector"]["admitted_programs"])
        assert rel["derived_agrees_with_selector"] is True

    def test_a_selector_that_DISAGREES_with_base_portable_is_refused(self, tmp_path):
        run = F.complete_run(tmp_path)
        doc = json.load(open(run["release_path"]))
        doc["selector"]["admitted_programs"].append("th9_like")   # not base_portable
        with open(run["release_path"], "w") as fh:
            json.dump(doc, fh)
        with pytest.raises(T.RunManifestError, match="selector declares"):
            run_manifest.load_release(run["release_path"], run["release_root"])

    def test_the_non_portable_program_is_excluded(self, tmp_path):
        run = F.complete_run(tmp_path)
        rel = run_manifest.load_release(run["release_path"], run["release_root"])
        assert "th9_like" not in rel["programs"]

    def test_the_conditions_come_from_the_release_selector_NOT_a_batch_policy(
            self, tmp_path):
        run = F.complete_run(tmp_path)
        rel = run_manifest.load_release(run["release_path"], run["release_root"])
        # ORDER PRESERVED: temporal, not alphabetical (which would be Rest, Stim48hr, ...)
        assert rel["conditions"] == ["Rest", "Stim8hr", "Stim48hr"]
        assert rel["condition_universe_source"] == "release.selector.conditions"
        assert rel["batch_policy_is_not_an_authority_here"] is True

    def test_the_pathway_sources_come_from_the_release(self, tmp_path):
        run = F.complete_run(tmp_path)
        rel = run_manifest.load_release(run["release_path"], run["release_root"])
        assert rel["gene_set_sources"] == ["GO-BP", "Reactome"]

    def test_there_is_no_default_and_no_legacy_registry_fallback(self):
        with pytest.raises(T.RunManifestError, match="legacy"):
            run_manifest.load_release(None, None)

    def test_a_component_must_be_STAGED_not_resolved_from_a_machine_default(
            self, tmp_path):
        run = F.complete_run(tmp_path)
        os.remove(os.path.join(run["release_root"], F.VIEW_PATH))
        with pytest.raises(T.RunManifestError, match="not staged"):
            run_manifest.load_release(run["release_path"], run["release_root"])

    def test_a_reusable_arm_is_PAIR_AGNOSTIC(self, tmp_path):
        # No role, no pole, no pair-derived program id. Requiring one would drag a pair
        # back into the artifact whose whole purpose is to be reusable.
        run = F.complete_run(tmp_path)
        inv = json.load(open(os.path.join(run["direct"][0], "arm_bundle.json")))
        for arm in inv["arms"]:
            assert "derived_from_poles" not in arm
            assert "program_projection_sha256" not in arm
            assert "role" not in arm and "pole_direction" not in arm
            # what it DOES carry is pair-free: the program and which way it must move
            assert arm["desired_change"] in (T.INCREASE, T.DECREASE)
            assert arm["arm_key"].split("|")[2] == arm["desired_change"]

    def test_the_bundle_binds_the_STAGE1_identity_its_arms_stand_on(self, tmp_path):
        # what replaces the per-arm id: the scorer view + the admitted programs, bound at
        # bundle level and re-derived by the verifier against the release
        run = F.complete_run(tmp_path)
        rel = run_manifest.load_release(run["release_path"], run["release_root"])
        b = run_manifest.bind_bundle(run["direct"][0])
        assert (b["selection_release"]["registry_scorer_view_sha256"]
                == rel["registry_scorer_view_canonical_sha256"])
        assert sorted(b["admitted_programs"]) == rel["programs"]
        assert b["program_admission"]["programs_copied_from_a_list"] is False

    def test_the_release_binds_the_scorer_view_and_projection_it_publishes(self, tmp_path):
        run = F.complete_run(tmp_path)
        rel = run_manifest.load_release(run["release_path"], run["release_root"])
        assert rel["registry_scorer_view_canonical_sha256"].startswith("5d1d8c36")
        assert rel["registry_scorer_projection_sha256"].startswith("008c1da1")


class TestBatchStaysOutOfTheReusableChain:
    def test_the_manifest_declares_the_population_level_DiD_estimand(self, tmp_path):
        doc = _build(tmp_path, F.complete_run(tmp_path))
        est = doc["temporal_estimand"]
        assert est["estimand_level"] == "population"
        assert est["is_per_cell_fate"] is False
        assert est["is_lineage_traced"] is False
        assert est["batch_commentary_in_reusable_bundles"] is False

    def test_a_bundle_carrying_BATCH_COMMENTARY_is_refused(self, tmp_path):
        run = F.complete_run(tmp_path)
        d = run["temporal"][0]
        inv = json.load(open(os.path.join(d, "arm_bundle.json")))
        inv["batch_status"] = "partially_confounded"
        with open(os.path.join(d, "arm_bundle.json"), "w") as fh:
            json.dump(inv, fh)
        with pytest.raises(T.RunManifestError, match="batch commentary"):
            run_manifest.bind_bundle(d)


class TestPathwayBindsTheBytesItsCountsCameFrom:
    def test_the_ranking_and_the_membership_are_bound_on_disk(self, tmp_path):
        run = F.complete_run(tmp_path)
        b = run_manifest.bind_bundle(run["pathway"][0])
        for what in T.BUNDLE_BINDINGS["pathway"]:
            assert b["bound_artifacts"][what]["raw_sha256"]
        assert any(k.endswith("::ranking") for k in b["bound_artifacts"])

    def test_a_binding_whose_bytes_moved_is_REFUSED(self, tmp_path):
        run = F.complete_run(tmp_path)
        with open(os.path.join(run["pathway"][0], "gene_set_membership.json"), "w") as fh:
            json.dump({"sets": {}}, fh)
        with pytest.raises(T.RunManifestError, match="hashes to"):
            run_manifest.bind_bundle(run["pathway"][0])

    def test_convergence_is_ONE_artifact_per_bundle_shared_by_its_20_arms(self, tmp_path):
        run = F.complete_run(tmp_path)
        ids = set()
        for d in run["pathway"]:
            inv = json.load(open(os.path.join(d, "arm_bundle.json")))
            cid = inv["convergence"]["convergence_id"]
            ids.add(cid)
            assert {a["convergence_id"] for a in inv["arms"]} == {cid}
            assert len(inv["arms"]) == 20
        # six bundles, six DISTINCT convergence artifacts — not one duplicated 20 times
        assert len(ids) == 6


class TestAPartialRunIsVisiblyPartial:
    def test_a_missing_bundle_REFUSES_to_be_called_complete(self, tmp_path):
        run = F.complete_run(tmp_path)
        run["pathway"] = run["pathway"][:-1]
        with pytest.raises(T.RunManifestError, match="TOPOLOGY is incomplete"):
            _build(tmp_path, run)

    def test_a_partial_run_MAY_be_manifested_but_is_NEVER_release_admissible(
            self, tmp_path):
        run = F.complete_run(tmp_path)
        run["pathway"] = run["pathway"][:-1]
        doc = _build(tmp_path, run, allow_partial=True)
        assert doc["topology_complete"] is False
        assert doc["release_admissible"] is not True
        assert doc["per_lane"]["pathway"]["n_filled_slots"] == 100
        assert len(doc["per_lane"]["pathway"]["missing_slots"]) == 20

    def test_a_pair_specific_bundle_leaves_18_of_its_20_slots_empty(self, tmp_path):
        # the failure the reusable-arm topology introduces, and the reason 15 bundles is
        # only sufficient IF each one carries every program arm
        run = F.complete_run(tmp_path)
        F.build_bundle(run["root"], "direct", {"condition": run["conditions"][0]},
                       run["staged"],
                       arms_for=[("treg_like", T.DECREASE), ("th1_like", T.INCREASE)])
        doc = _build(tmp_path, run, allow_partial=True)
        assert doc["topology_complete"] is False


class TestItIsAnIndexAndSaysSo:
    def test_it_produces_no_science(self, tmp_path):
        doc = _build(tmp_path, F.complete_run(tmp_path))
        assert doc["produces_scientific_values"] is False
        assert doc["binds_arm_outputs"] is True
        assert doc["emits_p_q_or_fdr"] is False

    def test_it_is_content_addressed(self, tmp_path):
        run = F.complete_run(tmp_path)
        doc = _build(tmp_path, run)
        on_disk = json.load(open(doc["path"]))
        assert on_disk["manifest_sha256"] == doc["manifest_sha256"]
        assert len(doc["manifest_sha256"]) == 64

    def test_it_records_the_exact_per_lane_CLI_invocation_contract(self, tmp_path):
        doc = _build(tmp_path, F.complete_run(tmp_path))
        for lane in T.LANES:
            c = doc["cli_invocation_contracts"][lane]
            assert c["command"].startswith("python -m direct")
            assert c["required_arguments"] and c["output_filenames"]
            assert c["expected_row_count_source"]
            assert c["expected_exit_code"] == 0
        # the pathway hit count is RECONSTRUCTED, never declared
        assert "RECONSTRUCTED" in (
            doc["cli_invocation_contracts"]["pathway"]["expected_hit_count_source"])

    def test_it_binds_the_frozen_addendum_it_was_built_against(self, tmp_path):
        doc = _build(tmp_path, F.complete_run(tmp_path))
        assert doc["frozen_topology_addendum_sha256"] == (
            "c477356278c5b7d2842659f5354792c9db7203ee774f8dd70653921124477a9f")


class TestPairDerivedOrderingsAreJoinTimeOnly:
    def test_a_bundle_that_STORES_a_pareto_tier_is_refused(self, tmp_path):
        run = F.complete_run(tmp_path)
        d = run["direct"][0]
        inv = json.load(open(os.path.join(d, "arm_bundle.json")))
        inv["arms"][0]["pareto_tier"] = 1
        with open(os.path.join(d, "arm_bundle.json"), "w") as fh:
            json.dump(inv, fh)
        with pytest.raises(T.RunManifestError, match="JOIN-TIME"):
            run_manifest.bind_bundle(d)

    def test_a_bundle_that_STORES_a_concordance_class_is_refused(self, tmp_path):
        run = F.complete_run(tmp_path)
        d = run["direct"][1]
        inv = json.load(open(os.path.join(d, "arm_bundle.json")))
        inv["concordance_class"] = "CONCORDANT"
        with open(os.path.join(d, "arm_bundle.json"), "w") as fh:
            json.dump(inv, fh)
        with pytest.raises(T.RunManifestError, match="JOIN-TIME"):
            run_manifest.bind_bundle(d)


class TestTheVerifierTopologyAgreesWithTheProducer:
    """generator != verifier — but they must reach the SAME arm keys.

    ``arm_topology`` is VERIFIER-OWNED and carried by this commit: it derives the key
    algebra independently, so it can disagree with the producer. That is only useful if the
    two are then CHECKED against each other — an independent derivation nobody compares is
    just a second opinion nobody asked for.

    The producer's interface (``arm_keys``, authoritative at fc9bdcd) is imported here ONLY
    to be compared. If it is absent — this branch predates it — the check skips rather than
    silently passing.
    """

    @staticmethod
    def _producer():
        try:
            from direct import arm_keys
        except ImportError:
            pytest.skip("the producer's arm_keys is not on this head")
        return arm_keys

    def test_the_four_role_x_pole_origins_map_IDENTICALLY(self):
        K = self._producer()
        for role in ("away_from_A", "toward_B"):
            for pole in ("high", "low"):
                assert (T.desired_change_for(role, pole)
                        == K.DESIRED_CHANGE_BY_ROLE_AND_POLE[(role, pole)])

    @pytest.mark.parametrize("dc", ["increase", "decrease"])
    def test_every_lane_key_is_BYTE_IDENTICAL_to_the_producers(self, dc):
        K = self._producer()
        p = "treg_like"
        assert (T.arm_key("direct", p, dc, {"condition": "Rest"})
                == K.direct_arm_key(p, dc, "Rest"))
        assert (T.arm_key("temporal", p, dc,
                          {"from_condition": "Rest", "to_condition": "Stim8hr"})
                == K.temporal_arm_key(p, dc, "Rest", "Stim8hr"))
        assert (T.arm_key("pathway", p, dc,
                          {"condition": "Rest", "gene_set_source": "Reactome"})
                == K.pathway_arm_key(p, dc, "Rest", "Reactome"))

    def test_the_key_carries_neither_pole_nor_role_on_EITHER_side(self):
        K = self._producer()
        for token in ("away_from_A", "toward_B", "high", "low"):
            assert token not in K.ARM_KEY_RULE.split("—")[0]


class TestGate7TheReleaseScope:
    """A scheduler must not discover a lane the aggregate is obliged to refuse."""

    def test_the_temporal_command_is_the_PRODUCTION_all_arm_path(self, tmp_path):
        doc = _build(tmp_path, F.complete_run(tmp_path))
        cmd = doc["cli_invocation_contracts"]["temporal"]["command"]
        assert cmd == "python -m direct.temporal.arms.run_temporal_arms"
        # the RETIRED flat lane emits one pair's two arms, not six all-arm bundles
        assert "direct.temporal.cli" not in cmd

    def test_NO_contract_names_a_RETIRED_entry_point(self, tmp_path):
        doc = _build(tmp_path, F.complete_run(tmp_path))
        printed = json.dumps(doc["cli_invocation_contracts"])
        for retired in T.RETIRED_ENTRY_POINTS:
            assert retired not in printed, retired

    def test_the_release_SAYS_what_it_is_NOT(self, tmp_path):
        doc = _build(tmp_path, F.complete_run(tmp_path))
        scope = doc["release_scope"]
        assert "direct.temporal.cli" in scope["retired_entry_points"]
        # deferred secondary method + scratch analysis: neither is Stage-2's science, and a
        # code digest that swept them in would move the run identity for nothing
        assert "perturb2state" in scope["excluded_from_release"]
        assert "temporal_exploration" in scope["excluded_from_release"]

    def test_the_PINNED_lane_verifiers_are_published_for_W7(self, tmp_path):
        doc = _build(tmp_path, F.complete_run(tmp_path))
        pins = doc["pinned_lane_verifiers"]
        assert pins["temporal"]["verifier_id"] == (
            "spot.stage02.temporal.arm.independent_verifier.v1")
        assert pins["temporal"]["commit"] == "99eaa81"


class TestTheDiscoveryRefusesAtNamedGates:
    """Discovery must resolve EXACTLY 3 Direct + 6 temporal + 6 pathway physical bundles.

    A 2/6/6 or a duplicated bundle is refused BY DEFAULT at the gate that names the
    violation; --allow-partial is the only (never-admissible) escape. The producer states
    the TOPOLOGY and never the ADMISSION.
    """

    def test_the_gate_tokens_are_the_pinned_names(self):
        assert run_manifest.GATE_BUNDLE_COUNT == (
            "each_lane_ships_EXACTLY_its_expected_physical_bundle_count"
            "_3_direct_6_temporal_6_pathway")
        assert run_manifest.GATE_NO_DUPLICATE_BUNDLE == (
            "no_bundle_id_appears_more_than_once_a_repeated_invocation_is_not_two")
        assert run_manifest.GATE_TOPOLOGY_COMPLETE == (
            "every_expected_arm_slot_is_filled_exactly_once_by_a_distinct_bundle")

    def test_a_2_6_6_direct_shortfall_dies_at_the_BUNDLE_COUNT_gate(self, tmp_path):
        run = F.complete_run(tmp_path)
        run["direct"] = run["direct"][:2]          # 2 Direct bundles, not 3
        with pytest.raises(run_manifest.RunManifestError,
                           match=run_manifest.GATE_BUNDLE_COUNT):
            _build(tmp_path, run)

    def test_a_5_6_6_pathway_shortfall_dies_at_the_BUNDLE_COUNT_gate(self, tmp_path):
        run = F.complete_run(tmp_path)
        run["pathway"] = run["pathway"][:5]        # 5 pathway bundles, not 6
        with pytest.raises(run_manifest.RunManifestError,
                           match=run_manifest.GATE_BUNDLE_COUNT):
            _build(tmp_path, run)

    def test_a_DUPLICATE_bundle_dies_at_the_NO_DUPLICATE_gate(self, tmp_path):
        run = F.complete_run(tmp_path)
        dupe = os.path.join(run["root"], "DUPE-direct-0")
        shutil.copytree(run["direct"][0], dupe)     # same content -> same bundle_id
        run["direct"] = [run["direct"][0], dupe, run["direct"][1]]
        with pytest.raises(run_manifest.RunManifestError,
                           match=run_manifest.GATE_NO_DUPLICATE_BUNDLE):
            _build(tmp_path, run)

    def test_EXACTLY_3_6_6_is_topology_complete_and_NEVER_self_admits(self, tmp_path):
        doc = _build(tmp_path, F.complete_run(tmp_path))
        assert doc["n_bundles"] == doc["n_expected_bundles"] == 15
        assert {lane: doc["per_lane"][lane]["n_bundles_present"] for lane in T.LANES} == {
            "direct": 3, "temporal": 6, "pathway": 6}
        assert doc["topology_complete"] is True
        # the PRODUCER states topology only; admission is not its to grant
        assert doc["topology_complete_is_an_admission"] is False
        assert doc["release_admissible"] is None
        assert doc["admission"]["status"] == run_manifest.ADMISSION_PENDING
        assert doc["admission"]["granted_by"] is None
        assert doc["admission"]["producer_may_declare_admission"] is False
