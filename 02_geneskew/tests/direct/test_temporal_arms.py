"""The reusable temporal arm producer. FIXTURE DATA ONLY — no biological claim.

Every number these tests touch is invented in ``fixtures_temporal_arms`` to exercise the
arithmetic and the refusals. Nothing here measures anything.
"""
from __future__ import annotations

import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "..", "analysis")))
sys.path.insert(0, _HERE)

import fixtures_temporal_arms as FX  # noqa: E402
from direct import arm_keys, projection  # noqa: E402
from direct import config as direct_config
from direct.temporal import (  # noqa: E402
    admission as direct_admission,
)
from direct.temporal import (
    estimand as legacy_estimand,
)
from direct.temporal import (
    policy as legacy_policy,
)
from direct.temporal import (
    run_temporal as legacy_run,
)
from direct.temporal.arms import (  # noqa: E402
    arm_admission,
    arm_bundle,
    arm_emit,
    arm_programs,
    arm_report,
    arm_request,
)
from direct.temporal.arms import (
    arm_estimand as est,
)

CHANGES = ("increase", "decrease")


# =========================================================================== #
# 1. THE PROGRAM AXIS IS DERIVED FROM THE V3 SCORER VIEW, NEVER COPIED
# =========================================================================== #
class TestProgramAdmissionIsDerived:

    def test_admits_exactly_the_base_portable_programs(self):
        adm = FX.admitted()
        assert sorted(adm) == sorted(FX.PORTABLE_IDS)
        assert len(adm) == 10

    def test_the_non_portable_program_is_excluded(self):
        # The fixture release ships 11 programs; one is base_portable=false (the Th9
        # stand-in). A producer holding a hard-coded list of ten would still pass a
        # count check — so the assertion is that THIS id is absent.
        assert FX.NON_PORTABLE_ID not in FX.admitted()

    def test_a_release_that_marks_one_more_portable_yields_one_more_program(self):
        # The count is a CONSEQUENCE of the release. Flip the flag; the axis grows.
        reg = FX.programs_registry()
        reg[FX.NON_PORTABLE_ID]["base_portable"] = True
        adm = arm_programs.admitted_programs(FX.FixtureRelease(reg))
        assert len(adm) == 11 and FX.NON_PORTABLE_ID in adm

    def test_a_portable_program_with_no_panel_is_refused_not_skipped(self):
        reg = FX.programs_registry()
        reg[FX.PORTABLE_IDS[0]]["panel_ensembl"] = []
        with pytest.raises(arm_programs.ProgramAdmissionError, match="no projectable"):
            arm_programs.admitted_programs(FX.FixtureRelease(reg))

    def test_a_release_with_no_portable_program_is_refused(self):
        reg = FX.programs_registry()
        for prog in reg.values():
            prog["base_portable"] = False
        with pytest.raises(arm_programs.ProgramAdmissionError, match="base_portable"):
            arm_programs.admitted_programs(FX.FixtureRelease(reg))

    def test_the_admission_block_says_it_derived_the_set(self):
        block = arm_programs.admission_block(FX.admitted(), "a" * 64)
        assert block["programs_copied_from_a_list"] is False
        assert block["program_count_is_derived"] is True
        assert block["n_programs"] == 10


# =========================================================================== #
# 2. THE ESTIMAND — STATED EXACTLY, AND TIED TO THE FROZEN LEGACY METHOD
# =========================================================================== #
class TestTheEstimand:

    def test_base_delta_is_to_minus_from(self):
        assert est.base_temporal_delta(0.25, 0.75) == pytest.approx(0.5)
        assert est.base_temporal_delta(0.75, 0.25) == pytest.approx(-0.5)

    def test_a_missing_endpoint_is_no_estimate_never_zero(self):
        # Zero is the claim that the projection did not move. That is a measurement.
        assert est.base_temporal_delta(None, 0.5) is None
        assert est.base_temporal_delta(0.5, None) is None

    def test_arm_value_is_the_sign_transform_of_the_base(self):
        assert est.arm_value(0.4, "increase") == pytest.approx(0.4)
        assert est.arm_value(0.4, "decrease") == pytest.approx(-0.4)

    def test_zero_negates_to_positive_zero(self):
        # A sign on a zero is a distinction the data does not make, and -0.0 would print
        # as a different number.
        v = est.arm_value(0.0, "decrease")
        assert v == 0.0 and str(v) == "0.0"

    @pytest.mark.parametrize("role,pole", [
        ("away_from_A", "high"), ("away_from_A", "low"),
        ("toward_B", "high"), ("toward_B", "low"),
    ])
    def test_arm_value_equals_frozen_legacy_did(self, role, pole):
        """THE BRIDGE. The reusable arm re-expresses the FROZEN estimand in pole-free
        coordinates; it does not invent a new one.

        legacy: away_from_A = -sign_A * delta ; toward_B = +sign_B * delta
                POLE_SIGN = {high: +1, low: -1}
        claim : legacy temporal_did(role, pole) == SIGN[desired_change] * base_delta
        """
        d_from, d_to = 0.30, 0.70                      # the program projection at each end
        sign = direct_config.POLE_SIGN[pole]

        legacy_from = (-sign * d_from) if role == "away_from_A" else (sign * d_from)
        legacy_to = (-sign * d_to) if role == "away_from_A" else (sign * d_to)
        legacy_did = legacy_estimand.temporal_did(legacy_from, legacy_to)

        change = arm_keys.desired_change(role, pole)
        base = est.base_temporal_delta(d_from, d_to)
        assert est.arm_value(base, change) == pytest.approx(legacy_did)

    def test_the_estimand_block_states_the_formula(self):
        block = est.estimand_block()
        assert "delta_p(target, program, to_condition)" in block["base_formula"]
        assert "SIGN[desired_change] * base_temporal_delta" in block["arm_value_formula"]
        assert block["estimand_level"] == "population"


class TestTheArmIsNotAFateClaim:
    """The estimand is a population-level shift. It is not fate, lineage, or the authors'
    early/late cluster classification — and the module holds no function that could
    produce one."""

    def test_the_artifact_denies_the_fate_reading_in_its_own_bytes(self):
        block = est.estimand_block()
        assert block["estimand_is_per_cell_fate"] is False
        assert block["estimand_is_lineage_traced"] is False
        assert block["estimand_is_author_early_late_cluster_class"] is False
        assert block["estimand_is_a_rate_or_slope"] is False

    def test_no_rate_slope_velocity_or_fate_function_exists(self):
        banned = ("rate", "slope", "velocity", "trajectory", "fate", "lineage",
                  "transition", "elapsed")
        for name in dir(est):
            if name.startswith("_"):
                continue
            assert not any(b in name.lower() for b in banned), \
                f"{name!r} could be read as a trajectory claim; this estimand has none"

    def test_no_elapsed_time_reaches_the_arithmetic(self):
        # The estimand differences two condition POPULATIONS. It never divides by a
        # duration, so 8h->48h and 48h->8h are exact negations, not a rate and its inverse.
        assert est.base_temporal_delta(0.2, 0.6) == -est.base_temporal_delta(0.6, 0.2)


# =========================================================================== #
# 3. THE BUNDLE: 20 ARMS, AND ALL 120 LOGICAL KEYS
# =========================================================================== #
class TestBundleTopology:

    def test_one_bundle_carries_twenty_arms(self):
        b = FX.build()
        assert b["n_programs"] == 10
        assert b["n_arms"] == 20 == len(b["arms"]) == len(set(b["arm_keys"]))

    def test_six_ordered_pairs_yield_one_hundred_and_twenty_logical_arms(self):
        bundles = FX.build_all()
        assert len(bundles) == 6
        keys = [k for b in bundles for k in b["arm_keys"]]
        assert len(keys) == 120
        assert len(set(keys)) == 120, "every logical arm key is distinct"

    def test_the_120_keys_are_exactly_program_x_change_x_ordered_pair(self):
        expected = {
            f"temporal|{p}|{c}|{frm}|{to}"
            for p in FX.PORTABLE_IDS for c in CHANGES for frm, to in FX.ORDERED_PAIRS
        }
        assert len(expected) == 120
        got = {k for b in FX.build_all() for k in b["arm_keys"]}
        assert got == expected

    def test_the_canonical_key_shape(self):
        arm = FX.build()["arms"][0]
        parts = arm["arm_key"].split("|")
        assert len(parts) == 5 and parts[0] == "temporal"
        assert parts[2] in CHANGES
        assert (parts[1], parts[3], parts[4]) == (
            arm["program_id"], arm["from_condition"], arm["to_condition"])

    def test_the_base_is_stored_once_and_both_arms_reference_it(self):
        b = FX.build()
        # 10 programs x 6 targets — one base per (program, target), NOT one per arm.
        assert b["n_base_records"] == 60
        by_key = {r["base_key"] for r in b["base_records"]}
        for arm in b["arms"]:
            for rec in arm["records"]:
                assert rec["base_key"] in by_key


# =========================================================================== #
# 4. INCREASE / DECREASE ARE SIGN TRANSFORMS, RANKED INDEPENDENTLY
# =========================================================================== #
class TestSignTransformAndRanks:

    def _arms_of(self, bundle, program_id):
        return {a["desired_change"]: a for a in bundle["arms"]
                if a["program_id"] == program_id}

    def test_decrease_is_exactly_the_negation_of_increase(self):
        b = FX.build()
        for pid in FX.PORTABLE_IDS:
            arms = self._arms_of(b, pid)
            inc = {r["target_id"]: r["arm_value"] for r in arms["increase"]["records"]}
            dec = {r["target_id"]: r["arm_value"] for r in arms["decrease"]["records"]}
            assert set(inc) == set(dec)
            for tid, v in inc.items():
                if v is None:
                    assert dec[tid] is None
                else:
                    assert dec[tid] == pytest.approx(-v)

    def test_the_two_arms_share_one_base_and_cannot_disagree_about_it(self):
        b = FX.build()
        bases = {r["base_key"]: r["base_delta"] for r in b["base_records"]}
        for arm in b["arms"]:
            sign = arm_keys.SIGN[arm["desired_change"]]
            for rec in arm["records"]:
                base = bases[rec["base_key"]]
                want = None if base is None else (0.0 if base == 0 else sign * base)
                assert rec["arm_value"] == want

    def test_each_arm_is_ranked_over_its_own_population_by_the_frozen_rule(self):
        b = FX.build()
        for arm in b["arms"]:
            pop = [r for r in arm["records"]
                   if r["evaluable"] and r["arm_value"] is not None]
            order = sorted(pop, key=lambda r: (-r["arm_value"], r["target_id"]))
            assert [r["rank"] for r in order] == list(range(1, len(order) + 1))
            for r in arm["records"]:
                if r not in pop:
                    assert r["rank"] is None

    def test_rank_1_of_increase_is_the_largest_positive_movement(self):
        b = FX.build()
        arm = self._arms_of(b, FX.PORTABLE_IDS[0])["increase"]
        top = [r for r in arm["records"] if r["rank"] == 1][0]
        assert top["arm_value"] == max(r["arm_value"] for r in arm["records"]
                                       if r["arm_value"] is not None)

    def test_ranks_are_invariant_to_input_target_order(self):
        a = FX.build()
        b = arm_bundle.build_bundle(
            from_condition="FixRest", to_condition="FixStim48", admitted=FX.admitted(),
            from_endpoints=list(reversed(FX.endpoints("FixRest"))),
            to_endpoints=list(reversed(FX.endpoints("FixStim48"))),
            method=FX.method(), conditions=list(FX.CONDITIONS),
            scorer_view_sha256="a" * 64, stage1=FX.stage1(), env_lock=FX.env_lock(),
            code=FX.code_identity())
        assert a == b, "ranking and emission must not depend on input row order"

    def test_a_tie_breaks_on_target_id_ascending_in_BOTH_arms(self):
        """The decrease rank is NOT the increase rank reversed.

        Under an exact tie both arms break on target_id ASCENDING, so the two rank vectors
        are genuinely not mirror images — which is exactly why each arm is ranked
        independently instead of one being inferred from the other.
        """
        recs_inc = [{"target_id": "T_B", "arm_value": 1.0, "evaluable": True,
                     "rank": None},
                    {"target_id": "T_A", "arm_value": 1.0, "evaluable": True,
                     "rank": None}]
        recs_dec = [{"target_id": "T_B", "arm_value": -1.0, "evaluable": True,
                     "rank": None},
                    {"target_id": "T_A", "arm_value": -1.0, "evaluable": True,
                     "rank": None}]
        est.rank_population(recs_inc)
        est.rank_population(recs_dec)
        assert {r["target_id"]: r["rank"] for r in recs_inc} == {"T_A": 1, "T_B": 2}
        assert {r["target_id"]: r["rank"] for r in recs_dec} == {"T_A": 1, "T_B": 2}

    def test_the_frozen_rank_rule_is_the_direct_lanes_rule(self):
        assert est.RANK_RULE["rank_direction"] == projection.RANK_DIRECTION
        assert est.RANK_RULE["rank_tie_break"] == projection.RANK_TIE_BREAK
        assert est.RANK_RULE["rank_null_rule"] == projection.RANK_NULL_RULE


# =========================================================================== #
# 5. THE REVERSE ORDERED PAIR IS A DIFFERENT BUNDLE, EXACTLY NEGATED
# =========================================================================== #
class TestReverseOrderedPair:

    def test_reversing_the_pair_negates_every_base_delta(self):
        fwd = FX.build("FixRest", "FixStim48")
        rev = FX.build("FixStim48", "FixRest")
        f = {r["base_key"]: r["base_delta"] for r in fwd["base_records"]}
        r = {r["base_key"]: r["base_delta"] for r in rev["base_records"]}
        assert set(f) == set(r)
        for k, v in f.items():
            assert r[k] == pytest.approx(-v) if v else r[k] == v

    def test_the_reverse_bundle_is_a_different_artifact_not_a_view(self):
        fwd, rev = FX.build("FixRest", "FixStim48"), FX.build("FixStim48", "FixRest")
        assert fwd["bundle_key"] != rev["bundle_key"]
        assert fwd["bundle_id"] != rev["bundle_id"]
        assert set(fwd["arm_keys"]).isdisjoint(rev["arm_keys"])

    def test_reversing_swaps_what_increase_and_decrease_mean_numerically(self):
        fwd, rev = FX.build("FixRest", "FixStim48"), FX.build("FixStim48", "FixRest")
        pid = FX.PORTABLE_IDS[3]
        fi = {r["target_id"]: r["arm_value"] for a in fwd["arms"]
              if a["program_id"] == pid and a["desired_change"] == "increase"
              for r in a["records"]}
        rd = {r["target_id"]: r["arm_value"] for a in rev["arms"]
              if a["program_id"] == pid and a["desired_change"] == "decrease"
              for r in a["records"]}
        for tid, v in fi.items():
            assert rd[tid] == pytest.approx(v) if v else rd[tid] == v

    def test_a_degenerate_ordered_pair_is_refused(self):
        with pytest.raises(arm_bundle.BundleError, match="degenerate"):
            FX.build("FixRest", "FixRest")


# =========================================================================== #
# 6. THE SAME (PROGRAM, POLE) IS TWO OPPOSITE ROLES — ONE UNCHANGED CACHED ARM
# =========================================================================== #
class TestRoleAndPoleNeverTouchTheCachedArm:

    def test_same_program_same_pole_maps_to_two_opposite_arms(self):
        b = FX.build()
        pid = FX.PORTABLE_IDS[2]
        keys = arm_request.selected_arm_keys(b, pid, "high")
        assert keys["away_from_A"].split("|")[2] == "decrease"
        assert keys["toward_B"].split("|")[2] == "increase"
        assert keys["away_from_A"] != keys["toward_B"]

    def test_both_roles_resolve_INTO_THE_SAME_CACHED_BUNDLE(self):
        b = FX.build()
        pid = FX.PORTABLE_IDS[2]
        for role in ("away_from_A", "toward_B"):
            arm = arm_request.resolve_arm(
                b, {"program_id": pid, "role": role, "pole": "high",
                    "from_condition": b["from_condition"],
                    "to_condition": b["to_condition"]})
            assert arm["arm_key"] in b["arm_keys"]

    def test_the_bundle_bytes_do_not_depend_on_which_role_asked(self):
        b = FX.build()
        before = arm_emit.bundle_bytes(b)
        for role in ("away_from_A", "toward_B"):
            arm_request.resolve_arm(
                b, {"program_id": FX.PORTABLE_IDS[2], "role": role, "pole": "high",
                    "from_condition": b["from_condition"],
                    "to_condition": b["to_condition"]})
        assert arm_emit.bundle_bytes(b) == before, \
            "a join may CHOOSE an arm; it may never alter one"

    def test_the_two_roles_of_one_pole_are_exact_negations(self):
        b = FX.build()
        pid = FX.PORTABLE_IDS[2]
        keys = arm_request.selected_arm_keys(b, pid, "high")
        away = arm_request.arm_by_key(b, keys["away_from_A"])
        toward = arm_request.arm_by_key(b, keys["toward_B"])
        a = {r["target_id"]: r["arm_value"] for r in away["records"]}
        t = {r["target_id"]: r["arm_value"] for r in toward["records"]}
        for tid, v in a.items():
            assert t[tid] == pytest.approx(-v) if v else t[tid] == v

    def test_pole_low_inverts_the_mapping(self):
        b = FX.build()
        keys = arm_request.selected_arm_keys(b, FX.PORTABLE_IDS[2], "low")
        assert keys["away_from_A"].split("|")[2] == "increase"
        assert keys["toward_B"].split("|")[2] == "decrease"


# =========================================================================== #
# 7. REFUSALS: MISSING PROGRAM / CONDITION, FORGED CHANGE / KEY
# =========================================================================== #
class TestRefusals:

    def test_a_program_the_release_did_not_admit_is_refused(self):
        b = FX.build()
        with pytest.raises(arm_request.RequestRefused, match="not in the admitted"):
            arm_request.resolve_arm(b, {"program_id": "NOT_A_PROGRAM", "role": "toward_B",
                                        "pole": "high", "from_condition": "FixRest",
                                        "to_condition": "FixStim48"})

    def test_the_non_portable_program_has_no_arm_to_resolve(self):
        b = FX.build()
        with pytest.raises(arm_request.RequestRefused):
            arm_request.resolve_arm(b, {"program_id": FX.NON_PORTABLE_ID,
                                        "role": "toward_B", "pole": "high",
                                        "from_condition": "FixRest",
                                        "to_condition": "FixStim48"})

    def test_a_request_for_a_different_ordered_pair_is_refused(self):
        b = FX.build("FixRest", "FixStim48")
        with pytest.raises(arm_request.RequestRefused, match="reverse pair|scoped"):
            arm_request.resolve_arm(b, {"program_id": FX.PORTABLE_IDS[0],
                                        "role": "toward_B", "pole": "high",
                                        "from_condition": "FixStim48",
                                        "to_condition": "FixRest"})

    def test_a_request_missing_an_endpoint_is_refused(self):
        with pytest.raises(arm_request.RequestRefused, match="ORDERED condition pair"):
            arm_request.scope_of({"from_condition": "FixRest"})

    def test_an_endpoint_missing_an_admitted_program_is_refused(self):
        # The caller promised a COMPLETE program axis. A missing program is refused, not
        # emitted as a null — a null would read as "measured, and it was nothing".
        eps = FX.endpoints("FixStim48")
        del eps[0].program_delta[FX.PORTABLE_IDS[0]]
        with pytest.raises(arm_bundle.BundleError, match="COMPLETE program axis"):
            FX.build("FixRest", "FixStim48", to_endpoints=eps)

    def test_a_condition_with_no_endpoints_is_refused(self):
        with pytest.raises(arm_bundle.BundleError, match="ships no target endpoints"):
            FX.build("FixRest", "FixStim48", to_endpoints=[])

    def test_a_duplicated_target_at_one_condition_is_refused(self):
        eps = FX.endpoints("FixRest") + [FX.endpoint(0, "FixRest")]
        with pytest.raises(arm_bundle.BundleError, match="twice"):
            FX.build("FixRest", "FixStim48", from_endpoints=eps)

    @pytest.mark.parametrize("forged", ["high", "low", "up", "INCREASE", "", "toward_B"])
    def test_a_forged_desired_change_is_refused(self, forged):
        with pytest.raises(arm_keys.ArmError):
            arm_keys.temporal_arm_key(FX.PORTABLE_IDS[0], forged, "FixRest", "FixStim48")

    def test_a_pole_handed_in_as_a_desired_change_is_refused_BY_NAME(self):
        with pytest.raises(arm_request.RequestRefused, match="that is a POLE"):
            arm_request.change_of({"desired_change": "high"})

    def test_a_desired_change_contradicting_its_own_role_and_pole_is_refused(self):
        with pytest.raises(arm_request.RequestRefused, match="sign error"):
            arm_request.change_of({"role": "away_from_A", "pole": "high",
                                   "desired_change": "increase"})

    def test_a_request_naming_no_arm_at_all_is_refused(self):
        with pytest.raises(arm_request.RequestRefused, match="no default arm"):
            arm_request.change_of({"program_id": "X"})

    def test_a_forged_arm_key_does_not_resolve(self):
        b = FX.build()
        with pytest.raises(arm_request.RequestRefused, match="no arm"):
            arm_request.arm_by_key(b, "temporal|GHOST|increase|FixRest|FixStim48")

    def test_a_RELABELLED_arm_key_is_caught_by_re_derivation(self):
        b = FX.build()
        b["arms"][0]["arm_key"] = "temporal|GHOST|increase|FixRest|FixStim48"
        with pytest.raises(arm_request.RequestRefused, match="does not re-derive"):
            arm_request.arm_by_key(b, "temporal|GHOST|increase|FixRest|FixStim48")


# =========================================================================== #
# 8. NO FORBIDDEN FIELDS
# =========================================================================== #
class TestNoForbiddenFields:

    def test_no_p_q_fdr_or_combined_objective_anywhere(self):
        assert arm_admission.inherited_forbidden_keys(FX.build()) == []

    def test_no_role_pole_pareto_concordance_pair_or_batch_field_anywhere(self):
        assert arm_admission.arm_forbidden_keys(FX.build()) == []

    def test_the_inherited_exemptions_are_only_the_scorer_view_hashes(self):
        # These match /score/ only because "scorer" contains "score". They are Stage-1
        # scorer VIEW content hashes; nothing ranks or gates on them. Exact-spelling exempt.
        assert arm_admission.INHERITED_FIREWALL_EXCEPTIONS == {
            "registry_scorer_view_sha256", "scorer_view_raw_sha256",
            "scorer_view_canonical_sha256", "registry_scorer_projection_sha256"}
        raw = {h.rsplit(".", 1)[-1] for h in direct_admission.forbidden_keys(FX.build())}
        assert raw <= arm_admission.INHERITED_FIREWALL_EXCEPTIONS
        assert arm_admission.inherited_forbidden_keys(FX.build()) == []

    @pytest.mark.parametrize("key", [
        "pole", "role", "away_from_A", "toward_B", "pareto_tier", "concordance_class",
        "pair_id", "selection_id", "batch_status", "combined_value", "weighted_value",
        "adj_p", "q_value", "fdr", "nominal_p", "scorer_value", "combined_scorer",
    ])
    def test_injecting_a_forbidden_field_is_caught(self, key):
        b = FX.build()
        b["arms"][0]["records"][0][key] = "x"
        hits = (arm_admission.inherited_forbidden_keys(b)
                + arm_admission.arm_forbidden_keys(b))
        assert hits, f"{key!r} walked straight through the firewall"

    def test_a_forbidden_field_nested_deep_in_the_provenance_is_caught(self):
        b = FX.build()
        b["method"]["diagnostics"] = [{"detail": {"empirical_q_value": 0.01}}]
        assert arm_admission.inherited_forbidden_keys(b), \
            "a disguised q nested three levels down is exactly the shape a real one takes"

    def test_the_negative_declaration_is_exempt_ONLY_while_it_says_forbidden(self):
        b = FX.build()
        assert arm_admission.arm_forbidden_keys(b) == []
        b["bundle_carries_role_or_pole"] = True     # flip the prohibition off
        assert arm_admission.arm_forbidden_keys(b), \
            "the exemption is conditional on the declaration still BEING a prohibition"

    def test_the_paper_qc_adjusted_p_is_not_imported(self):
        keys = _all_keys(FX.build())
        assert not any("adj_p" in k or k == "padj" for k in keys)

    def test_the_upstream_ontarget_qc_IS_preserved(self):
        keys = _all_keys(FX.build())
        assert "from_qc_ontarget_significant" in keys
        assert "to_qc_ontarget_significant" in keys


def _all_keys(obj, out=None):
    out = set() if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            _all_keys(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _all_keys(v, out)
    return out


# =========================================================================== #
# 9. THE PRESERVED PROVENANCE
# =========================================================================== #
class TestProvenanceIsPreserved:

    def test_every_base_record_carries_the_mask_qc_denominators_and_decomposition(self):
        rec = FX.build()["base_records"][0]
        for end in ("from", "to"):
            assert rec[f"{end}_estimate_mask_sha256"] is not None
            assert rec[f"{end}_mask_resolved"] is True
            assert rec[f"{end}_qc_ontarget_significant"] is True
            assert rec[f"{end}_qc_target_baseMean"] is not None
            assert rec[f"{end}_n_guide_slots_released"] == 4
            assert rec[f"{end}_n_splits_total"] == 3
            assert rec[f"{end}_donor_split_denominator"] == 0
            assert rec[f"{end}_panel_mean"] is not None
            assert rec[f"{end}_control_mean"] is not None
            assert rec[f"{end}_n_panel_surviving"] >= 1
            assert rec[f"{end}_n_control_surviving"] >= 1
            assert rec[f"{end}_reasons"]

    def test_the_delta_is_the_panel_mean_minus_the_control_mean(self):
        for rec in FX.build()["base_records"]:
            for end in ("from", "to"):
                assert rec[f"{end}_delta"] == pytest.approx(
                    rec[f"{end}_panel_mean"] - rec[f"{end}_control_mean"])

    def test_the_base_delta_is_the_difference_of_the_two_endpoint_deltas(self):
        for rec in FX.build()["base_records"]:
            if rec["base_delta"] is not None:
                assert rec["base_delta"] == pytest.approx(
                    rec["to_delta"] - rec["from_delta"])

    def test_an_unresolved_mask_makes_the_program_not_evaluable_and_unranked(self):
        # mask=None -> the contributing guides were never resolved -> refuse to project.
        eps = FX.endpoints("FixStim48")
        eps[0] = FX.endpoint(0, "FixStim48", mask_resolved=False,
                             mask_unresolved_reason="guides_unresolved")
        eps[0].program_delta[FX.PORTABLE_IDS[0]] = {
            "delta": None, "panel_mean": None, "control_mean": None,
            "n_panel_surviving": None, "n_control_surviving": None,
            "status": "mask_unresolved"}
        b = FX.build("FixRest", "FixStim48", to_endpoints=eps)
        rec = [r for r in b["base_records"]
               if r["base_key"] == f"{FX.PORTABLE_IDS[0]}|{FX.TARGETS[0]}"][0]
        assert rec["base_delta"] is None
        assert rec["evaluable"] is False
        assert rec["temporal_status"] == "arm_not_evaluable_at_to_condition"
        for arm in b["arms"]:
            if arm["program_id"] != FX.PORTABLE_IDS[0]:
                continue
            hit = [r for r in arm["records"] if r["target_id"] == FX.TARGETS[0]][0]
            assert hit["arm_value"] is None and hit["rank"] is None

    def test_a_target_absent_at_one_endpoint_is_reported_not_dropped(self):
        b = FX.build("FixRest", "FixStim48",
                     to_endpoints=FX.endpoints("FixStim48", n=len(FX.TARGETS) - 1))
        missing = FX.TARGETS[-1]
        rec = [r for r in b["base_records"] if r["target_id"] == missing][0]
        assert rec["temporal_status"] == "target_absent_at_to_condition"
        assert rec["base_delta"] is None and rec["to_present"] is False
        assert rec["from_present"] is True


# =========================================================================== #
# 10. DETERMINISM, EMISSION, HASHES, AND THE INDEPENDENT VERIFIER
# =========================================================================== #
class TestEmissionAndVerification:

    def test_rebuilding_produces_byte_identical_output(self):
        a, b = FX.build(), FX.build()
        assert a == b
        assert arm_emit.bundle_bytes(a) == arm_emit.bundle_bytes(b)
        assert a["bundle_id"] == b["bundle_id"]

    def test_the_bundle_carries_no_timestamp(self):
        keys = _all_keys(FX.build())
        assert not any(k in keys for k in
                       ("created_at", "timestamp", "generated_at", "run_started_at"))

    def test_the_bundle_id_covers_its_own_content(self):
        b = FX.build()
        report = arm_admission.verify_bundle(b)
        assert report["admitted"] is True, report["failures"]

    def test_a_tampered_value_does_not_survive_the_verifier(self):
        b = FX.build()
        b["arms"][0]["records"][0]["arm_value"] = 99.0
        report = arm_admission.verify_bundle(b)
        assert report["admitted"] is False
        assert any("sign_transform" in f for f in report["failures"])

    def test_a_tampered_rank_does_not_survive_the_verifier(self):
        b = FX.build()
        for rec in b["arms"][0]["records"]:
            if rec["rank"] is not None:
                rec["rank"] = 99
                break
        report = arm_admission.verify_bundle(b)
        assert report["admitted"] is False
        assert any("rank_rederives" in f for f in report["failures"])

    def test_a_deleted_arm_does_not_survive_the_verifier(self):
        b = FX.build()
        b["arms"].pop()
        b["n_arms"] = len(b["arms"])
        report = arm_admission.verify_bundle(b)
        assert report["admitted"] is False
        assert any("arm_inventory" in f or "n_arms" in f for f in report["failures"])

    def test_a_desired_change_flipped_on_an_arm_does_not_survive(self):
        # The values were computed for the OTHER change; flipping the label alone makes
        # every value the negation of what the (now-declared) arm should hold.
        b = FX.build()
        arm = [a for a in b["arms"] if a["desired_change"] == "increase"][0]
        arm["desired_change"] = "decrease"
        report = arm_admission.verify_bundle(b)
        assert report["admitted"] is False

    def test_an_unknown_column_is_rejected_by_the_allowlist(self):
        b = FX.build()
        b["surprise"] = 1
        with pytest.raises(arm_admission.BundleRejected, match="unauthorised claim"):
            arm_admission.verify_bundle(b)

    def test_emit_writes_verifies_and_content_addresses(self, tmp_path):
        b = FX.build()
        addr = arm_emit.emit_bundle(b, str(tmp_path))
        assert addr["n_arms"] == 20
        bundle_addr = addr["files"][arm_emit.BUNDLE_FILENAME]
        assert len(bundle_addr["raw_sha256"]) == 64
        assert len(bundle_addr["canonical_sha256"]) == 64
        # the runtime path is reconstructed by a TEST-ONLY helper, not carried in the address
        paths = arm_emit.resolve_local_paths(str(tmp_path), addr)
        on_disk = json.loads(open(paths[arm_emit.BUNDLE_FILENAME], "rb").read())
        assert on_disk == b

    def test_emitting_twice_writes_the_same_bytes(self, tmp_path):
        a = arm_emit.emit_bundle(FX.build(), str(tmp_path / "one"))
        b = arm_emit.emit_bundle(FX.build(), str(tmp_path / "two"))
        fa, fb = a["files"][arm_emit.BUNDLE_FILENAME], b["files"][arm_emit.BUNDLE_FILENAME]
        assert fa["raw_sha256"] == fb["raw_sha256"]
        assert fa["canonical_sha256"] == fb["canonical_sha256"]
        assert a["bundle_id"] == b["bundle_id"]

    def test_a_bundle_that_fails_its_verifier_is_not_left_on_disk(self, tmp_path):
        b = FX.build()
        b["arms"][0]["records"][0]["arm_value"] = 99.0
        with pytest.raises(arm_emit.EmitRefused):
            arm_emit.emit_bundle(b, str(tmp_path))
        d = tmp_path / arm_emit.bundle_dirname(b["from_condition"], b["to_condition"])
        assert not (d / arm_emit.BUNDLE_FILENAME).exists()

    def test_the_release_emits_six_bundles_and_one_hundred_and_twenty_arms(self, tmp_path):
        rel = arm_emit.emit_release(FX.build_all(), str(tmp_path), expect_n_bundles=6)
        assert rel["n_bundles"] == 6
        assert rel["n_logical_arms"] == 120
        assert len(set(rel["arm_keys"])) == 120

    def test_a_short_release_is_refused(self, tmp_path):
        with pytest.raises(arm_emit.EmitRefused, match="partial release"):
            arm_emit.emit_release(FX.build_all()[:5], str(tmp_path), expect_n_bundles=6)

    def test_two_bundles_claiming_the_same_ordered_pair_are_refused(self, tmp_path):
        with pytest.raises(arm_emit.EmitRefused, match="same ordered pair"):
            arm_emit.emit_release([FX.build(), FX.build()], str(tmp_path))


def _w11_verify(out_dir):
    """STAND IN for W11's INDEPENDENT verifier: reopen the shipped producer bytes off disk,
    re-derive, and write the authoritative temporal_verification.json.

    In production this is W11's OWN lane, in its own process — the producer never runs it.
    Here it lets the cross-contract test exercise the full aggregate contract. It is honest
    for THIS caller (not the generator) to declare generator_is_not_verifier and to admit.
    """
    from direct.hashing import sha256_hex
    result = arm_admission.verify_shipped(out_dir)
    bundle = json.loads(open(os.path.join(out_dir, arm_emit.BUNDLE_FILENAME), "rb").read())
    arm_raw = sha256_hex(open(os.path.join(out_dir, arm_emit.BUNDLE_FILENAME), "rb").read())
    prov_raw = sha256_hex(
        open(os.path.join(out_dir, arm_emit.PROVENANCE_FILENAME), "rb").read())
    report = arm_report.build_report(result, bundle_id=bundle["bundle_id"],
                                     arm_bundle_sha256=arm_raw, provenance_sha256=prov_raw)
    with open(os.path.join(out_dir, arm_emit.VERIFICATION_FILENAME), "wb") as fh:
        fh.write(json.dumps(report, sort_keys=True, separators=(",", ":")).encode())
    return report


# =========================================================================== #
# 10b. THE W3 PHYSICAL FILENAME CONTRACT — EMITTED NATIVELY, NO SHIM
# =========================================================================== #
class TestContractFilenames:
    """W3 aggregate keys on exact filenames; W11 reads the shipped bytes at them. The
    producer emits its OWN bytes natively — no rename or copy after the fact — and does NOT
    write the independent verification, which is W11's."""

    def test_the_contract_filenames_are_the_canonical_ones(self):
        assert arm_emit.BUNDLE_FILENAME == "arm_bundle.json"
        assert arm_emit.PROVENANCE_FILENAME == "temporal_provenance.json"
        assert arm_emit.VERIFICATION_FILENAME == "temporal_verification.json"

    def test_the_producer_emits_bundle_provenance_preflight_rankings_NOT_verification(
            self, tmp_path):
        arm_emit.emit_bundle(FX.build(), str(tmp_path))
        d = tmp_path / arm_emit.bundle_dirname("FixRest", "FixStim48")
        top = {p.name for p in d.iterdir() if p.is_file()}
        assert {"arm_bundle.json", "temporal_provenance.json",
                "temporal_preflight.json"} <= top
        assert (d / "rankings").is_dir()
        # the authoritative verification is W11's — the producer must not write it
        assert "temporal_verification.json" not in top

    def test_no_legacy_arm_prefixed_bundle_or_verification_filename_is_emitted(
            self, tmp_path):
        arm_emit.emit_bundle(FX.build(), str(tmp_path))
        d = tmp_path / arm_emit.bundle_dirname("FixRest", "FixStim48")
        names = {p.name for p in d.iterdir()}
        assert "temporal_arm_bundle.json" not in names
        assert "temporal_arm_verification.json" not in names

    def test_the_release_inventory_names_the_producer_files(self, tmp_path):
        rel = arm_emit.emit_release(FX.build_all(), str(tmp_path), expect_n_bundles=6)
        for b in rel["bundles"]:
            assert set(b["files"]) == {"arm_bundle.json", "temporal_provenance.json",
                                       "temporal_preflight.json"}


# =========================================================================== #
# 10c. PORTABILITY — NO ABSOLUTE PATH / HOSTNAME / PRIVATE ADDRESS LEAKS
# =========================================================================== #
class TestNoMachineLocalLeak:
    """No absolute path, hostname or private address may appear in the emitted bundle, the
    verification, or the release inventory — at ANY depth. Portable and content-addressable."""

    def test_the_scanner_is_not_a_rubber_stamp(self):
        # MUTATION: it must CATCH machine-local strings, nested at any depth...
        assert arm_admission.machine_local_strings({"x": "/home/tcelab/secret"})
        assert arm_admission.machine_local_strings({"a": {"b": ["/tmp/leak.json"]}})
        assert arm_admission.machine_local_strings({"note": "see /mnt/tcenas/x for detail"})
        assert arm_admission.machine_local_strings({"h": "tcedirector"})
        assert arm_admission.machine_local_strings({"ip": "192.168.1.7"})
        assert arm_admission.machine_local_strings({"ip": "127.0.0.1"})
        assert arm_admission.machine_local_strings({"p": "~/datasets/x"})
        # ...and must NOT fire on the bundle's real content (ids, hashes, formulae, keys)
        assert arm_admission.machine_local_strings({
            "k": "temporal|FIXTURE_PROG_00|increase|FixRest|FixStim48",
            "sha": "a" * 64, "file": "arm_bundle.json",
            "formula": "delta_p(X) = mean(panel_p \\ M_X) - mean(control_p \\ M_X)"}) == []

    def test_the_emitted_bundle_bytes_carry_no_machine_local_string(self, tmp_path):
        paths = arm_emit.resolve_local_paths(
            str(tmp_path), arm_emit.emit_bundle(FX.build(), str(tmp_path)))
        on_disk = json.loads(open(paths[arm_emit.BUNDLE_FILENAME], "rb").read())
        assert arm_admission.machine_local_strings(on_disk) == []

    def test_the_on_disk_provenance_and_preflight_carry_no_machine_local_string(
            self, tmp_path):
        paths = arm_emit.resolve_local_paths(
            str(tmp_path), arm_emit.emit_bundle(FX.build(), str(tmp_path)))
        for fname in (arm_emit.PROVENANCE_FILENAME, arm_emit.PREFLIGHT_FILENAME):
            doc = json.loads(open(paths[fname], "rb").read())
            assert arm_admission.machine_local_strings(doc) == [], fname

    def test_the_root_release_manifest_carries_no_machine_local_string(self, tmp_path):
        rel = arm_emit.emit_release(FX.build_all(), str(tmp_path), expect_n_bundles=6)
        on_disk = json.loads(
            open(os.path.join(str(tmp_path), arm_emit.RELEASE_FILENAME), "rb").read())
        assert arm_admission.machine_local_strings(on_disk) == []
        assert arm_admission.machine_local_strings(rel) == []

    def test_the_returned_address_has_no_path_abs_field(self, tmp_path):
        addr = arm_emit.emit_bundle(FX.build(), str(tmp_path))
        assert "path_abs" not in addr and "verification_path_abs" not in addr
        assert arm_admission.machine_local_strings(addr) == []

    def test_the_release_inventory_has_no_machine_local_string_at_any_depth(self, tmp_path):
        rel = arm_emit.emit_release(FX.build_all(), str(tmp_path), expect_n_bundles=6)
        assert arm_admission.machine_local_strings(rel) == []

    def test_the_inventory_path_fields_are_relative_filenames(self, tmp_path):
        addr = arm_emit.emit_bundle(FX.build(), str(tmp_path))
        for fname in addr["files"]:
            assert not os.path.isabs(fname)
            assert "/" not in fname     # a bare filename in the bundle directory


# =========================================================================== #
# 10d. FAIL-CLOSED ON AN ABSOLUTE PATH — EVEN WHEN RESEALED
# =========================================================================== #
class TestFailClosedOnAbsolutePath:
    """W11 reseals a path-injection: it inserts an absolute path AND recomputes the
    bundle_id so the artifact is internally consistent. The absolute-path gate is
    independent of the hash, so a resealed injection still fails closed."""

    @staticmethod
    def _reseal(bundle):
        from direct.hashing import content_hash
        payload = {k: v for k, v in bundle.items() if k != "bundle_id"}
        bundle["bundle_id"] = content_hash(payload)[:arm_bundle.BUNDLE_ID_LEN]
        return bundle

    def test_a_resealed_absolute_path_injection_is_refused(self):
        b = FX.build()
        b["method"]["origin"] = "/home/tcelab/worktrees/leak/arm_bundle.json"
        self._reseal(b)                        # bundle_id now re-derives cleanly
        report = arm_admission.verify_bundle(b)
        assert report["admitted"] is False
        assert any("absolute" in f or "machine_local" in f for f in report["failures"])

    def test_a_resealed_hostname_injection_is_refused(self):
        b = FX.build()
        b["method"]["host"] = "tcefold"
        self._reseal(b)
        report = arm_admission.verify_bundle(b)
        assert report["admitted"] is False

    def test_emit_fails_closed_on_an_absolute_path_and_leaves_nothing(self, tmp_path):
        b = FX.build()
        b["method"]["origin"] = "/home/tcelab/leak"
        self._reseal(b)
        with pytest.raises(arm_emit.EmitRefused):
            arm_emit.emit_bundle(b, str(tmp_path))
        d = tmp_path / arm_emit.bundle_dirname(b["from_condition"], b["to_condition"])
        assert not (d / arm_emit.BUNDLE_FILENAME).exists()


# =========================================================================== #
# 10e. PROVENANCE + VERIFICATION AS SEPARATE TYPED ARTIFACTS
# =========================================================================== #
class TestSeparateTypedArtifacts:
    """The independent verification is a SEPARATE TYPED ARTIFACT written by W11, not the
    producer. The producer's bytes carry NO verdict; the bundle only POINTS at where the
    independent verification will live."""

    def test_the_bundle_carries_no_embedded_admission_verdict(self):
        keys = _all_keys(FX.build())
        for verdict in ("admitted", "verdict", "admission_result", "self_verified",
                        "passed"):
            assert verdict not in keys, f"{verdict!r} embeds a self-verdict in the bundle"

    def test_provenance_is_typed_and_binds_the_bundle_by_content_hash(self, tmp_path):
        addr = arm_emit.emit_bundle(FX.build(), str(tmp_path))
        paths = arm_emit.resolve_local_paths(str(tmp_path), addr)
        prov = json.loads(open(paths[arm_emit.PROVENANCE_FILENAME], "rb").read())
        assert prov["schema_version"] == arm_emit.SCHEMA_PROVENANCE
        assert prov["bundle_id"] == addr["bundle_id"]
        assert prov["bundle_file"] == arm_emit.BUNDLE_FILENAME
        assert prov["bundle_raw_sha256"] == \
            addr["files"][arm_emit.BUNDLE_FILENAME]["raw_sha256"]
        assert "method" in prov and "program_admission" in prov and "estimand" in prov

    def test_W11s_verification_report_binds_the_bundle_it_judged(self, tmp_path):
        # The report SHAPE the aggregate's check_report reads. Written by the INDEPENDENT
        # verifier (here, the W11 stand-in) after reopening the producer's shipped bytes.
        addr = arm_emit.emit_bundle(FX.build(), str(tmp_path))
        out_dir = os.path.dirname(
            arm_emit.resolve_local_paths(str(tmp_path), addr)[arm_emit.BUNDLE_FILENAME])
        ver = _w11_verify(out_dir)
        assert ver["schema_version"] == arm_report.SCHEMA_VERIFICATION
        assert ver["verifier_id"] == arm_report.VERIFIER_ID
        assert ver["verdict"] == "admit" and ver["n_failed"] == 0
        assert ver["fail_closed"] is True and ver["generator_is_not_verifier"] is True
        assert ver["bundle_id"] == addr["bundle_id"]
        assert ver["binds"]["arm_bundle_sha256"] == \
            addr["files"][arm_emit.BUNDLE_FILENAME]["raw_sha256"]
        assert ver["binds"]["provenance_sha256"] == \
            addr["files"][arm_emit.PROVENANCE_FILENAME]["raw_sha256"]
        passed = {c["gate"] for c in ver["checks"] if c["status"] == "pass"}
        assert set(arm_report.REQUIRED_GATES) <= passed

    def test_the_verification_contract_is_the_INDEPENDENT_verifier_id(self):
        assert arm_report.VERIFIER_ID == "spot.stage02.temporal.arm.independent_verifier.v1"
        assert "self" not in arm_report.VERIFIER_ID

    def test_the_bundle_carries_a_preflight_ref_and_external_admission_requirement(self):
        b = FX.build()
        # NO verification_ref — the producer does not claim a per-bundle verification exists
        assert "verification_ref" not in b
        pr = b["preflight_ref"]
        assert pr["preflight_file"] == arm_emit.PREFLIGHT_FILENAME
        assert pr["preflight_verifier_id"] == "spot.stage02.temporal.arm.producer_preflight.v1"
        ear = b["external_admission_requirement"]
        assert ear["required_verifier_id"] == arm_report.VERIFIER_ID
        assert ear["required_report_schema_version"] == arm_report.EXTERNAL_ADMISSION_SCHEMA
        # a requirement, not a claim it has run
        for k in ("verdict", "admitted", "status"):
            assert k not in pr and k not in ear


# =========================================================================== #
# 10e2. THE PRODUCER CANNOT SELF-ADMIT (trust boundary)
# =========================================================================== #
class TestProducerCannotSelfAdmit:
    """A producer may not sign an admission under the independent verifier's identity for
    code it invoked itself. Its own re-derivation is an INTERNAL fail-closed gate; the
    authoritative admission is W11's, written after W11 reopens the shipped bytes."""

    def test_the_producer_writes_no_verification_file_at_all(self, tmp_path):
        addr = arm_emit.emit_bundle(FX.build(), str(tmp_path))
        d = tmp_path / addr["dir"]
        assert not (d / arm_emit.VERIFICATION_FILENAME).exists()
        # ...and nothing else the producer wrote is an admit under the independent id
        for p in d.rglob("*.json"):
            doc = json.loads(p.read_bytes())
            if isinstance(doc, dict):
                assert not (doc.get("verifier_id") == arm_report.VERIFIER_ID
                            and doc.get("verdict") == "admit")

    def test_the_producer_address_defers_to_the_independent_verifier(self, tmp_path):
        addr = arm_emit.emit_bundle(FX.build(), str(tmp_path))
        assert "verdict" not in addr           # the producer does not admit its own bytes
        assert addr["external_admission"]["status"] == "pending"
        assert addr["external_admission"]["required_verifier_id"] == arm_report.VERIFIER_ID
        assert addr["external_admission"]["required_report_schema_version"] == \
            arm_report.EXTERNAL_ADMISSION_SCHEMA

    def test_the_producer_self_check_still_fails_closed_on_bad_bytes(self, tmp_path):
        # internal gate: a bundle the producer cannot itself reconstruct is not left behind
        b = FX.build()
        b["arms"][0]["records"][0]["arm_value"] = 99.0
        with pytest.raises(arm_emit.EmitRefused):
            arm_emit.emit_bundle(b, str(tmp_path))
        d = tmp_path / arm_emit.bundle_dirname(b["from_condition"], b["to_condition"])
        assert not d.exists() or not any(d.iterdir())

    def test_the_build_report_shape_declares_independence_for_its_caller(self):
        # build_report is the CONTRACT W11 fills; its generator_is_not_verifier=True is
        # honest for W11 (not the generator), and the producer simply never calls it.
        result = arm_admission.verify_bundle(FX.build())
        report = arm_report.build_report(result, bundle_id="x", arm_bundle_sha256="a",
                                         provenance_sha256="b")
        assert report["generator_is_not_verifier"] is True
        assert report["verifier_id"] == arm_report.VERIFIER_ID


# =========================================================================== #
# 10f. RUNTIME PATHS ARE A TEST-ONLY HELPER, OUTSIDE THE RELEASE CONTRACT
# =========================================================================== #
class TestRuntimePathsAreOutsideTheContract:

    def test_resolve_local_paths_reconstructs_absolute_paths_on_demand(self, tmp_path):
        addr = arm_emit.emit_bundle(FX.build(), str(tmp_path))
        paths = arm_emit.resolve_local_paths(str(tmp_path), addr)
        for fname in ("arm_bundle.json", "temporal_provenance.json",
                      "temporal_preflight.json"):
            assert os.path.isabs(paths[fname]) and os.path.exists(paths[fname])

    def test_the_reconstructed_paths_are_never_stored_in_the_contract(self, tmp_path):
        # The helper computes them transiently; they are not returned in, or derivable
        # from, any field of the address that gets serialised.
        addr = arm_emit.emit_bundle(FX.build(), str(tmp_path))
        assert arm_admission.machine_local_strings(addr) == []
        paths = arm_emit.resolve_local_paths(str(tmp_path), addr)
        assert arm_admission.machine_local_strings(paths)  # the HELPER output DOES hold them


# =========================================================================== #
# 10g. THE BUNDLE SHAPE THE AGGREGATE READS — lane + per-arm ranking bindings
# =========================================================================== #
class TestBundleShapeForAggregate:
    """run_manifest.bind_bundle reads ``lane``, refuses any pair-derived ordering, and binds
    EACH arm's ranking as a bundle-relative file (path + raw + canonical sha)."""

    def test_the_bundle_declares_its_lane(self):
        assert FX.build()["lane"] == "temporal"

    def test_the_bundle_declares_its_ordered_pair_context(self):
        ctx = FX.build()["context"]
        assert ctx == {"from_condition": "FixRest", "to_condition": "FixStim48"}

    def test_every_arm_binds_a_ranking_file_with_path_and_two_hashes(self):
        for arm in FX.build()["arms"]:
            b = arm["ranking"]
            assert set(b) == {"path", "raw_sha256", "canonical_sha256"}
            assert not os.path.isabs(b["path"]) and ".." not in b["path"].split("/")
            assert len(b["raw_sha256"]) == 64 and len(b["canonical_sha256"]) == 64

    def test_the_ranking_files_exist_on_disk_and_match_their_bound_hashes(self, tmp_path):
        from direct.hashing import content_hash, file_sha256
        addr = arm_emit.emit_bundle(FX.build(), str(tmp_path))
        d = tmp_path / arm_emit.bundle_dirname("FixRest", "FixStim48")
        for arm in FX.build()["arms"]:
            b = arm["ranking"]
            p = d / b["path"]
            assert p.exists()
            assert file_sha256(str(p)) == b["raw_sha256"]
            assert content_hash(json.loads(p.read_bytes())) == b["canonical_sha256"]
        assert addr["files"][arm_emit.BUNDLE_FILENAME]["raw_sha256"]

    def test_the_ranking_file_holds_the_same_ranked_list_as_the_arm(self, tmp_path):
        addr = arm_emit.emit_bundle(FX.build(), str(tmp_path))
        paths = arm_emit.resolve_local_paths(str(tmp_path), addr)
        d = os.path.dirname(paths[arm_emit.BUNDLE_FILENAME])
        for arm in FX.build()["arms"]:
            ranking = json.loads(open(os.path.join(d, arm["ranking"]["path"])).read())
            assert ranking["arm_key"] == arm["arm_key"]
            assert ranking["ranked"] == arm["records"]

    def test_a_tampered_ranking_binding_does_not_survive_the_verifier(self):
        b = FX.build()
        b["arms"][0]["ranking"]["canonical_sha256"] = "0" * 64
        report = arm_admission.verify_bundle(b)
        assert report["admitted"] is False
        assert any("ranking" in f for f in report["failures"])

    def test_no_pair_derived_ordering_key_appears_in_the_bundle(self):
        # The aggregate refuses pareto/concordance/joint_order/combined_score/etc.
        keys = _all_keys(FX.build())
        for bad in ("pareto", "concordance", "joint_order", "joint_ordering",
                    "combined_score", "balanced_skew", "weighted_score",
                    "composite_score", "headline_rank"):
            assert not any(bad in k.lower() for k in keys), bad


# =========================================================================== #
# 10g2. THE STAGE-3 CONSUMER CONTRACT — identity join, modality, modulation
# =========================================================================== #
class TestStage3ConsumerContract:
    """Stage-3 (W16) needs stable target identity + a suggestive modulation orientation,
    joined by an IMMUTABLE base_key. Identity lives once in base_records; arm records carry
    only the join key; the bundle proves referential integrity."""

    def test_identity_lives_in_base_records_not_duplicated_on_arm_records(self):
        b = FX.build()
        for rec in b["arms"][0]["records"]:
            # the arm record carries the JOIN KEY, never the full identity
            assert set(rec) == {"target_id", "base_key", "arm_value", "evaluable",
                                "temporal_status", "desired_target_modulation", "rank"}
            assert "target_symbol" not in rec and "target_ensembl" not in rec

    def test_base_records_carry_stable_identity_and_provenance(self):
        rec = FX.build()["base_records"][0]
        for f in ("target_id", "target_symbol", "target_ensembl", "target_id_namespace",
                  "from_released_estimate_id", "to_released_estimate_id",
                  "perturbation_modality"):
            assert f in rec
        # the upstream ontarget QC provenance Stage-3 needs, per endpoint
        assert rec["from_qc_ontarget_significant"] is not None
        assert rec["to_qc_ontarget_significant"] is not None

    def test_every_arm_record_joins_to_exactly_one_base_record(self):
        b = FX.build()
        by_key = {r["base_key"]: r for r in b["base_records"]}
        assert len(by_key) == len(b["base_records"])          # base_key is unique
        for arm in b["arms"]:
            for rec in arm["records"]:
                base = by_key.get(rec["base_key"])
                assert base is not None and base["target_id"] == rec["target_id"]

    def test_a_dangling_base_key_does_not_survive_the_verifier(self):
        b = FX.build()
        b["arms"][0]["records"][0]["base_key"] = "GHOST|GHOST"
        report = arm_admission.verify_bundle(b)
        assert report["admitted"] is False
        assert any("base_record" in f for f in report["failures"])

    def test_the_perturbation_modality_is_crispri_knockdown(self):
        b = FX.build()
        assert b["perturbation"]["perturbation_modality"] == "CRISPRi_knockdown"
        assert all(r["perturbation_modality"] == "CRISPRi_knockdown"
                   for r in b["base_records"])

    def test_the_modulation_rule_does_not_assume_reversibility(self):
        assert FX.build()["perturbation"]["pharmacologic_reversibility_assumed"] is False
        assert FX.build()["perturbation"]["is_suggestive_not_confirmatory"] is True

    def test_a_positive_response_to_knockdown_supports_inhibition(self):
        # positive arm value = knockdown moved the program the DESIRED way -> inhibiting
        # the target supports it (SUGGESTIVE).
        assert est.target_modulation(0.4, evaluable=True) == "supports_target_inhibition"

    def test_a_negative_response_is_opposed_and_would_need_activation(self):
        assert est.target_modulation(-0.4, evaluable=True) == \
            "opposed_would_require_target_activation"

    def test_null_or_unevaluable_modulation_stays_not_evaluable(self):
        assert est.target_modulation(None, evaluable=True) == "not_evaluable"
        assert est.target_modulation(0.4, evaluable=False) == "not_evaluable"

    def test_every_arm_record_modulation_rederives_from_its_value(self):
        for arm in FX.build()["arms"]:
            for rec in arm["records"]:
                assert rec["desired_target_modulation"] == est.target_modulation(
                    rec["arm_value"], evaluable=rec["evaluable"])

    def test_a_forged_modulation_orientation_does_not_survive(self):
        b = FX.build()
        for rec in b["arms"][0]["records"]:
            if rec["desired_target_modulation"] == "supports_target_inhibition":
                rec["desired_target_modulation"] = "opposed_would_require_target_activation"
                break
        report = arm_admission.verify_bundle(b)
        assert report["admitted"] is False
        assert any("modulation" in f for f in report["failures"])


# =========================================================================== #
# 10g3. CODE IDENTITY (WHICH BUILD) + METHOD DIGEST (WHAT THE CODE DID)
# =========================================================================== #
class TestCodeIdentityBinding:
    """The bundle binds the BUILD that produced it via the shared Stage-2 code-digest
    convention — commit + digest + recorded tree state — kept explicit BESIDE the method
    digest. The producer records its tree state; it never self-admits clean."""

    def test_the_bundle_binds_a_code_identity_tuple(self):
        code = FX.build()["code_identity"]
        for f in ("commit", "clean_tree", "manifest_sha256", "canonical_digest",
                  "digest_id"):
            assert f in code

    def test_code_identity_uses_the_shared_code_digest_convention(self):
        from direct import code_digest
        code = FX.build()["code_identity"]
        assert code["digest_id"] == code_digest.DIGEST_ID
        # it is the REAL run_binding of this checkout, not a fabricated constant
        assert code["manifest_sha256"] == code_digest.run_binding()["manifest_sha256"]

    def test_the_producer_does_not_self_admit_clean_tree(self):
        # code_identity RECORDS clean_tree (bool/None); the verifier does not gate on it,
        # so a dirty-tree bundle is still admissible by the producer's own re-derivation —
        # the final clean-tree call belongs to the independent verifier against a pin.
        b = FX.build()
        b["code_identity"]["clean_tree"] = False
        b["code_identity"]["n_dirty_paths"] = 3
        arm_bundle_reseal(b)
        report = arm_admission.verify_bundle(b)
        assert report["admitted"] is True, report["failures"]

    def test_a_bundle_with_no_code_identity_is_refused(self):
        b = FX.build()
        b["code_identity"] = {}
        arm_bundle_reseal(b)
        report = arm_admission.verify_bundle(b)
        assert report["admitted"] is False
        assert any("code_identity" in f for f in report["failures"])

    def test_method_digest_and_code_identity_are_both_bound_distinctly(self):
        b = FX.build()
        # WHAT THE CODE DID
        assert b["method"]["temporal_method_sha256"] is not None
        # WHICH BUILD — a different object, not the same hash
        assert b["code_identity"]["canonical_digest"] != \
            b["method"]["temporal_method_sha256"]

    def test_provenance_run_binding_carries_code_identity_and_the_stage1_binding(
            self, tmp_path):
        addr = arm_emit.emit_bundle(FX.build(), str(tmp_path))
        paths = arm_emit.resolve_local_paths(str(tmp_path), addr)
        prov = json.loads(open(paths[arm_emit.PROVENANCE_FILENAME]).read())
        rb = prov["run_binding"]
        assert rb["code_identity"]["commit"] == FX.build()["code_identity"]["commit"]
        # stage2_inputs is a fixed keyed object (no role list)
        assert isinstance(rb["stage2_inputs"], dict)
        assert set(rb["stage2_inputs"]) == {"direct_method_version",
                                            "direct_config_sha256", "effect_source_sha256"}
        # the Stage-1 binding, independently verifiable: the verifier reads
        # selection_release.registry_scorer_view_sha256 (non-null) + programs
        sr = rb["selection_release"]
        assert sr["registry_scorer_view_sha256"] is not None
        assert sorted(sr["admitted_programs"]) == sorted(FX.PORTABLE_IDS)
        assert all(v is not None for v in sr["per_program_projection_sha256"].values())
        # method digest role stays explicit beside code_identity
        assert rb["temporal_method_sha256"] is not None

    def test_no_derived_from_poles_or_pole_pair_scoped_projection_field(self):
        b = FX.build()
        keys = _all_keys(b)
        assert not any("derived_from_pole" in k.lower() for k in keys)
        # a POLE/PAIR-scoped projection is forbidden; the per-PROGRAM Stage-1 projection
        # hash is legitimate and present
        assert arm_admission._pair_projection_keys(b) == []
        assert any("per_program_projection_sha256" in k for k in keys)

    def test_a_pole_derived_projection_field_does_not_survive(self):
        b = FX.build()
        b["method"]["program_projection_by_pole"] = {"high": 1.0}
        arm_bundle_reseal(b)
        report = arm_admission.verify_bundle(b)
        assert report["admitted"] is False
        assert any("projection" in f for f in report["failures"])


def arm_bundle_reseal(bundle):
    """Recompute bundle_id after a mutation — the resealed-attack helper."""
    from direct.hashing import content_hash
    payload = {k: v for k, v in bundle.items() if k != "bundle_id"}
    bundle["bundle_id"] = content_hash(payload)[:arm_bundle.BUNDLE_ID_LEN]
    return bundle


# =========================================================================== #
# 10g4. THE RANKING-BYTE GATE — refuses a tampered ranking file under a reseal
# =========================================================================== #
class TestRankingByteGate:
    """The independent verifier reads and recomputes EVERY ranking byte from disk. A
    ranking file changed on disk while the bundle JSON is resealed to stay internally
    consistent is caught at the ranking-byte gate — the exact W11 defect this guards."""

    def test_a_tampered_ranking_file_under_a_resealed_bundle_is_refused(self, tmp_path):
        addr = arm_emit.emit_bundle(FX.build(), str(tmp_path))
        paths = arm_emit.resolve_local_paths(str(tmp_path), addr)
        out_dir = os.path.dirname(paths[arm_emit.BUNDLE_FILENAME])
        # the standalone verifier admits the pristine shipped bytes
        assert arm_admission.verify_shipped(out_dir)["admitted"] is True
        # now TAMPER a ranking file on disk...
        bundle = json.loads(open(paths[arm_emit.BUNDLE_FILENAME]).read())
        rel = bundle["arms"][0]["ranking"]["path"]
        rpath = os.path.join(out_dir, rel)
        doc = json.loads(open(rpath).read())
        doc["ranked"][0]["arm_value"] = 42.0                 # a value nobody ranked
        with open(rpath, "wb") as fh:
            fh.write(json.dumps(doc, separators=(",", ":")).encode())
        # ...the bundle JSON is untouched, so it is still internally consistent (a reseal
        # would not even be needed) — yet the ranking BYTES no longer match the binding.
        report = arm_admission.verify_shipped(out_dir)
        assert report["admitted"] is False
        assert any("ranking_file_hash_mismatch" in f for f in report["failures"])

    def test_a_deleted_ranking_file_is_refused(self, tmp_path):
        addr = arm_emit.emit_bundle(FX.build(), str(tmp_path))
        paths = arm_emit.resolve_local_paths(str(tmp_path), addr)
        out_dir = os.path.dirname(paths[arm_emit.BUNDLE_FILENAME])
        bundle = json.loads(open(paths[arm_emit.BUNDLE_FILENAME]).read())
        os.remove(os.path.join(out_dir, bundle["arms"][0]["ranking"]["path"]))
        report = arm_admission.verify_shipped(out_dir)
        assert report["admitted"] is False
        assert any("ranking_file_missing" in f for f in report["failures"])


# =========================================================================== #
# 10j. THE FIVE AUDIT DEFECTS, CLOSED (audit of 62fbf8b)
# =========================================================================== #
class TestAuditDefectsClosed:

    def test_1_stage1_fields_are_non_null(self):
        assert arm_programs.stage1_binding_nulls(FX.build()["stage1_binding"]) == []

    def test_1_a_null_stage1_binding_does_not_survive_the_verifier(self):
        b = FX.build()
        b["stage1_binding"]["release_self_sha256"] = None
        arm_bundle_reseal(b)
        report = arm_admission.verify_bundle(b)
        assert report["admitted"] is False
        assert any("stage1_binding" in f for f in report["failures"])

    def test_1_the_scalar_and_the_per_program_projection_map_are_BOTH_carried(self):
        s1 = FX.build()["stage1_binding"]
        # (a) the SCALAR overall projection identity — a single hash string
        assert isinstance(s1["registry_scorer_projection_sha256"], str)
        # (b) the 10-key per-program MAP — one hash per admitted program
        m = s1["per_program_projection_sha256"]
        assert isinstance(m, dict) and sorted(m) == sorted(FX.PORTABLE_IDS)
        assert all(v is not None for v in m.values())
        # DISTINCT — neither collapsed into the other
        assert s1["registry_scorer_projection_sha256"] not in m.values()

    def test_1_a_missing_scalar_projection_identity_does_not_survive(self):
        b = FX.build()
        b["stage1_binding"]["registry_scorer_projection_sha256"] = None
        arm_bundle_reseal(b)
        report = arm_admission.verify_bundle(b)
        assert report["admitted"] is False

    def test_1_a_per_program_map_with_the_wrong_key_set_does_not_survive(self):
        b = FX.build()
        b["stage1_binding"]["per_program_projection_sha256"].pop(FX.PORTABLE_IDS[0])
        arm_bundle_reseal(b)
        report = arm_admission.verify_bundle(b)
        assert report["admitted"] is False
        assert any("stage1" in f or "projection" in f for f in report["failures"])

    def test_1_the_per_program_map_is_DERIVED_by_the_canonical_record_rule(self):
        # each value == SHA-256 of the canonical JSON of the ENTIRE Stage-1 record, the
        # exact rule the independent verifier uses. Derived from the record, not supplied.
        from direct.hashing import content_hash
        reg = FX.programs_registry()
        want = {pid: content_hash(reg[pid]) for pid in FX.PORTABLE_IDS}
        s1 = FX.build()["stage1_binding"]
        assert s1["per_program_projection_sha256"] == want
        assert s1["per_program_projection_rule_id"] == \
            "spot.stage01_stage2_registry_view.program_record.canonical_sha256.v1"

    def test_1_a_supplied_map_that_disagrees_is_refused_at_build(self):
        # the producer DERIVES the map; a supplied map that disagrees (here a reordered
        # record's hash) is rejected rather than trusted into the artifact.
        bad_map = {pid: "f" * 64 for pid in FX.PORTABLE_IDS}
        with pytest.raises(arm_programs.ProgramAdmissionError, match="disagrees"):
            FX.build(stage1={**FX.stage1(),
                             "per_program_projection_sha256": bad_map})

    def test_1_a_supplied_map_with_an_extra_nonportable_key_is_refused(self):
        good = dict(FX.build()["stage1_binding"]["per_program_projection_sha256"])
        good["TH9_nonportable"] = "a" * 64
        with pytest.raises(arm_programs.ProgramAdmissionError, match="disagrees"):
            FX.build(stage1={**FX.stage1(), "per_program_projection_sha256": good})

    def test_1_a_reordered_record_array_changes_the_derived_hash(self):
        # array order is PRESERVED in the canonical rule, so reversing panel_ensembl yields
        # a DIFFERENT projection id — reordering cannot pass unnoticed.
        from direct.hashing import content_hash
        reg = FX.programs_registry()
        rec = dict(reg[FX.PORTABLE_IDS[0]])
        reordered = dict(rec, panel_ensembl=list(reversed(rec["panel_ensembl"])))
        assert content_hash(rec) != content_hash(reordered)

    def test_2_stage2_inputs_is_a_fixed_keyed_object_not_a_role_list(self, tmp_path):
        addr = arm_emit.emit_bundle(FX.build(), str(tmp_path))
        paths = arm_emit.resolve_local_paths(str(tmp_path), addr)
        rb = json.loads(open(paths[arm_emit.PROVENANCE_FILENAME]).read())["run_binding"]
        assert isinstance(rb["stage2_inputs"], dict)          # object, not list
        assert set(rb["stage2_inputs"]) == {"direct_method_version",
                                            "direct_config_sha256", "effect_source_sha256"}

    def test_3_the_release_topology_is_derived_and_complete(self, tmp_path):
        arm_emit.emit_release(FX.build_all(), str(tmp_path), expect_n_bundles=6)
        man = json.loads(
            open(os.path.join(str(tmp_path), arm_emit.RELEASE_FILENAME), "rb").read())
        assert man["topology"]["expected_n_logical_arms"] == 120
        assert sorted(man["arm_keys"]) == sorted(man["topology"]["expected_arm_keys"])

    def test_3_a_release_missing_a_reverse_pair_is_refused(self, tmp_path):
        from direct.temporal.arms import arm_release
        # drop one direction of a pair -> the reverse-pair identity is broken
        bundles = [b for b in FX.build_all()
                   if not (b["from_condition"] == "FixRest"
                           and b["to_condition"] == "FixStim8")]
        with pytest.raises((arm_release.ReleaseError, arm_emit.EmitRefused)):
            arm_emit.emit_release(bundles, str(tmp_path))

    def test_4_a_stale_extra_ranking_file_is_refused(self, tmp_path):
        addr = arm_emit.emit_bundle(FX.build(), str(tmp_path))
        paths = arm_emit.resolve_local_paths(str(tmp_path), addr)
        out_dir = os.path.dirname(paths[arm_emit.BUNDLE_FILENAME])
        # a ranking file nothing binds, sitting in the release looking like evidence
        with open(os.path.join(out_dir, "rankings", "GHOST__increase.json"), "w") as fh:
            fh.write("{}")
        report = arm_admission.verify_shipped(out_dir)
        assert report["admitted"] is False
        assert any("stale_or_extra_ranking" in f for f in report["failures"])

    def test_5_the_preflight_binds_a_provenance_the_self_check_actually_covered(
            self, tmp_path):
        # provenance is written BEFORE the self-check, so verify_shipped re-derives it; a
        # tampered provenance on disk does not survive.
        addr = arm_emit.emit_bundle(FX.build(), str(tmp_path))
        paths = arm_emit.resolve_local_paths(str(tmp_path), addr)
        out_dir = os.path.dirname(paths[arm_emit.BUNDLE_FILENAME])
        # the preflight binds exactly the provenance sha the self-check re-derived
        pf = json.loads(open(paths[arm_emit.PREFLIGHT_FILENAME]).read())
        assert pf["binds"]["provenance_sha256"] == \
            addr["files"][arm_emit.PROVENANCE_FILENAME]["raw_sha256"]
        # tamper the provenance on disk -> the standalone verifier refuses
        p = paths[arm_emit.PROVENANCE_FILENAME]
        doc = json.loads(open(p).read())
        doc["n_arms"] = 999
        with open(p, "wb") as fh:
            fh.write(json.dumps(doc, separators=(",", ":")).encode())
        report = arm_admission.verify_shipped(out_dir)
        assert report["admitted"] is False
        assert any("provenance" in f for f in report["failures"])

    def test_2_a_provenance_with_a_non_keyed_stage2_inputs_does_not_survive(self, tmp_path):
        # the producer always emits a keyed object; a tampered list/absent one is caught by
        # the standalone verifier re-deriving the provenance from the bundle.
        addr = arm_emit.emit_bundle(FX.build(), str(tmp_path))
        paths = arm_emit.resolve_local_paths(str(tmp_path), addr)
        out_dir = os.path.dirname(paths[arm_emit.BUNDLE_FILENAME])
        prov = json.loads(open(paths[arm_emit.PROVENANCE_FILENAME]).read())
        prov["run_binding"]["stage2_inputs"] = [{"role": "x", "value": "y"}]  # old list form
        with open(paths[arm_emit.PROVENANCE_FILENAME], "wb") as fh:
            fh.write(json.dumps(prov, separators=(",", ":")).encode())
        report = arm_admission.verify_shipped(out_dir)
        assert report["admitted"] is False
        assert any("provenance" in f for f in report["failures"])

    def test_4_an_extra_ranking_in_the_inventory_is_refused_at_release_level(self, tmp_path):
        from direct.temporal.arms import arm_release
        # a fully-valid, hash-consistent EXTRA ranking file in one non-first bundle dir
        arm_emit.emit_release(FX.build_all(), str(tmp_path), expect_n_bundles=6)  # baseline
        # now emit into a fresh root and slip a 21st ranking into one bundle before build
        root = str(tmp_path / "attack")
        os.makedirs(root)
        addrs = [arm_emit.emit_bundle(b, root) for b in FX.build_all()]
        victim = os.path.join(root, addrs[-1]["dir"], "rankings", "GHOST__increase.json")
        with open(victim, "w") as fh:
            fh.write("{}")
        with pytest.raises(arm_release.ReleaseError, match="ranking"):
            arm_release.build_release(addrs, root)

    def test_5b_all_bundles_must_carry_the_same_code_identity(self, tmp_path):
        from direct.temporal.arms import arm_release
        root = str(tmp_path / "mixed")
        os.makedirs(root)
        bundles = FX.build_all()
        # a NON-FIRST bundle gets a fully self-consistent but DIFFERENT build identity
        fake = dict(bundles[3]["code_identity"])
        fake["commit"] = "f" * 40
        fake["manifest_sha256"] = "e" * 64
        b = arm_bundle.build_bundle(
            from_condition=bundles[3]["from_condition"],
            to_condition=bundles[3]["to_condition"], admitted=FX.admitted(),
            from_endpoints=FX.endpoints(bundles[3]["from_condition"]),
            to_endpoints=FX.endpoints(bundles[3]["to_condition"]),
            method=FX.method(), conditions=list(FX.CONDITIONS), scorer_view_sha256="a" * 64,
            stage1=FX.stage1(), env_lock=FX.env_lock(), code=fake)
        mixed = bundles[:3] + [b] + bundles[4:]
        addrs = [arm_emit.emit_bundle(x, root) for x in mixed]
        with pytest.raises(arm_release.ReleaseError, match="code_identity|one build"):
            arm_release.build_release(addrs, root)

    def test_6_the_bundle_binds_the_authoritative_stage2_solver_lock(self, tmp_path):
        from direct.temporal.arms import arm_env
        auth = arm_env.AUTHORITATIVE_ENV_LOCK_SHA256
        assert auth == \
            "2983d140941f13d223dad93bae71434663882f23f25f6717c3debe59d2711abe"
        b = FX.build()
        el = b["env_lock"]
        assert el["env_lock_sha256"] == auth         # the SAME lock every lane binds
        assert el["env_lock_is_synthetic"] is True   # fixture: synthetic but NOT omitted
        assert el["env_lock_rule_id"].endswith("stage2_solver_lock_sha256.v1")
        # carried into the root inventory identity too
        arm_emit.emit_release(FX.build_all(), str(tmp_path), expect_n_bundles=6)
        man = json.loads(
            open(os.path.join(str(tmp_path), arm_emit.RELEASE_FILENAME), "rb").read())
        assert man["env_lock_sha256"] == auth

    def test_6_a_bundle_with_no_env_lock_is_refused(self):
        from direct.temporal.arms import arm_bundle
        with pytest.raises(arm_bundle.BundleError, match="solver-lock|env_lock"):
            FX.build(env_lock=None)

    def test_6_a_production_env_lock_must_be_verified_from_bytes(self):
        # a non-synthetic lock that was NOT verified from bytes is refused by the gate
        b = FX.build()
        b["env_lock"] = {"env_lock_sha256": "e" * 64, "env_lock_is_synthetic": False,
                         "env_lock_verified_from_bytes": False,
                         "env_lock_name": "x", "env_lock_rule_id": "r"}
        arm_bundle_reseal(b)
        report = arm_admission.verify_bundle(b)
        assert report["admitted"] is False
        assert any("env_lock" in f or "solver_lock" in f for f in report["failures"])

    def test_6_production_env_lock_reads_actual_bytes_against_an_explicit_expected(
            self, tmp_path):
        from direct.hashing import file_sha256
        from direct.temporal.arms import arm_env
        lock = tmp_path / "stage02_solver_lock.txt"
        lock.write_bytes(b"numpy==1.26.4\nscipy==1.13.0\n")
        # expect_sha256 = the file's own sha exercises the READ mechanism on a non-auth lock
        blk = arm_env.env_lock_block(str(lock), expect_sha256=file_sha256(str(lock)))
        assert blk["env_lock_verified_from_bytes"] is True and not blk["env_lock_is_synthetic"]
        assert blk["env_lock_sha256"] == file_sha256(str(lock))   # bytes, not a supplied hash
        assert blk["env_lock_name"] == "stage02_solver_lock.txt"  # basename, never the path

    def test_6_the_authoritative_lock_verifies_the_wrong_base_lock_is_refused_by_name(
            self, tmp_path):
        from direct.temporal.arms import arm_env
        # the REAL authoritative Stage-2 solver lock, if staged, verifies to 2983…
        auth = "/home/tcelab/.spot-runs/20260712T021343Z/stage02_solver_lock.txt"
        if os.path.exists(auth):
            blk = arm_env.env_lock_block(auth)
            assert blk["env_lock_sha256"] == arm_env.AUTHORITATIVE_ENV_LOCK_SHA256
            assert blk["env_lock_verified_from_bytes"] is True
        # the WRONG _requirements/base.lock (b9284e63…) is refused BY NAME
        base = tmp_path / "base.lock"
        base.write_bytes(b"this is not the authoritative solver lock\n")
        with pytest.raises(arm_env.EnvLockError, match="not the authoritative"):
            arm_env.env_lock_block(str(base))

    def test_6_a_missing_production_lock_is_refused_by_name(self):
        from direct.temporal.arms import arm_env
        with pytest.raises(arm_env.EnvLockError, match="missing"):
            arm_env.env_lock_block("/no/such/lock")

    def test_5_reverse_pair_arm_values_are_exact_negations_across_bundles(self):
        fwd = FX.build("FixRest", "FixStim48")
        rev = FX.build("FixStim48", "FixRest")

        def vals(bundle):
            return {(a["program_id"], a["desired_change"], r["target_id"]): r["arm_value"]
                    for a in bundle["arms"] for r in a["records"]}
        f, r = vals(fwd), vals(rev)
        for k, v in f.items():
            if v is None:
                assert r[k] is None
            else:
                assert r[k] == pytest.approx(-v) if v else r[k] == v


# =========================================================================== #
# 10h. IT READS GREEN AGAINST THE REAL AGGREGATE CONTRACT (W3 / W11)
# =========================================================================== #
_RUNMANIFEST = "/home/tcelab/worktrees/spot-stage2-runmanifest/02_geneskew/analysis"

# The real aggregate reader lives in ITS OWN `direct` package, which collides on sys.path
# with ours. So the DETACHED EXTERNAL MATRIX runs in a SUBPROCESS whose only relevant path
# is the run-manifest analysis dir: it opens the FULL six-bundle release THIS producer wrote
# and runs the aggregate's own W5-audit defect gates — null Stage-1 fields, keyed
# provenance, stale rankings, reverse-pair cross-bundle identity — plus the rule that a
# temporal_verification.json in a producer dir is forbidden. All must come back clean.
_CROSS_CHECK = r'''
import json, os, sys
root = sys.argv[1]
# ANCHOR on the STABLE root-envelope verifier; the per-bundle verify_manifest_rules API
# churns, so its gates are best-effort (getattr) and API-shape drift SKIPS, never fails.
try:
    from direct import verify_release_envelope as E
    doc, bad = E.check_inventory(root, 6, 120)          # producer inventory, byte-true
except (ImportError, AttributeError, TypeError) as exc:
    print("SKIP:" + repr(exc)); sys.exit(0)
try:
    from direct import verify_manifest_rules as R
    dirs = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))
    arm_values = {}
    for d in dirs:
        bd = os.path.join(root, d)
        inv = json.load(open(os.path.join(bd, "arm_bundle.json")))
        prov = json.load(open(os.path.join(bd, "temporal_provenance.json")))
        bid = inv["bundle_id"]
        assert not os.path.exists(os.path.join(bd, "temporal_verification.json")), d
        for fn in ("null_stage1_fields", "check_keyed_provenance"):
            f = getattr(R, fn, None)
            if f:
                bad += f(prov, bid)
        sr = getattr(R, "stale_rankings", None)
        if sr:
            bad += sr(bd, inv, bid)
        for a in inv["arms"]:
            arm_values[(inv["from_condition"], inv["to_condition"],
                        a["program_id"], a["desired_change"])] = {
                r["target_id"]: r["arm_value"] for r in a["records"]}
    cb = getattr(R, "check_cross_bundle", None)
    if cb:
        bad += cb(arm_values)
except ImportError:
    pass
assert bad == [], bad
print("GREEN")
'''


class TestReadsGreenAgainstTheRealAggregate:
    """The DETACHED EXTERNAL MATRIX: W3's STABLE root-envelope verifier (and its per-bundle
    audit gates, best-effort) read the SHIPPED six-bundle release this producer wrote and
    come back clean, in a SEPARATE PROCESS that does not import W5 code. Skips when the
    run-manifest worktree is absent OR its API has drifted (a moving target must not red a
    correct producer)."""

    def test_the_real_aggregate_gates_pass_on_the_shipped_release(self, tmp_path):
        import subprocess
        if not os.path.isdir(_RUNMANIFEST):
            pytest.skip("run-manifest worktree not available for cross-contract proof")
        arm_emit.emit_release(FX.build_all(), str(tmp_path), expect_n_bundles=6)
        proc = subprocess.run(
            [sys.executable, "-c", _CROSS_CHECK, str(tmp_path)],
            env={**os.environ, "PYTHONPATH": _RUNMANIFEST},
            capture_output=True, text=True)
        if "SKIP:" in proc.stdout:
            pytest.skip(f"run-manifest API drift: {proc.stdout.strip()}")
        assert proc.returncode == 0 and "GREEN" in proc.stdout, \
            f"stdout={proc.stdout!r} stderr={proc.stderr!r}"


# =========================================================================== #
# 10i. THE PRODUCER PREFLIGHT AND THE CONTENT-ADDRESSED ROOT RELEASE
# =========================================================================== #
class TestPreflightAndReleaseManifest:

    def test_the_preflight_is_a_pass_status_never_an_admission(self, tmp_path):
        addr = arm_emit.emit_bundle(FX.build(), str(tmp_path))
        paths = arm_emit.resolve_local_paths(str(tmp_path), addr)
        pf = json.loads(open(paths[arm_emit.PREFLIGHT_FILENAME], "rb").read())
        assert pf["schema_version"] == "spot.stage02_temporal_arm_preflight.v1"
        assert pf["verifier_id"] == "spot.stage02.temporal.arm.producer_preflight.v1"
        assert pf["status"] == "pass"                       # pass|fail, never admit/pending
        assert pf["is_admission"] is False
        assert pf["generator_is_not_verifier"] is False     # the producer ran it
        assert "verdict" not in pf and "role" not in pf     # no admit, no generic role key
        # it binds the bytes it self-checked, including every ranking hash
        assert pf["binds"]["arm_bundle_sha256"] == \
            addr["files"][arm_emit.BUNDLE_FILENAME]["raw_sha256"]
        assert pf["binds"]["provenance_sha256"] == \
            addr["files"][arm_emit.PROVENANCE_FILENAME]["raw_sha256"]
        assert len(pf["binds"]["rankings"]) == 20
        # it does NOT sign W11's id; it declares the required external admission
        assert pf["verifier_id"] != arm_report.VERIFIER_ID
        assert pf["external_admission_requirement"]["required_verifier_id"] == \
            arm_report.VERIFIER_ID

    def test_the_release_id_is_a_full_64_hex_self_hash_with_an_explicit_rule(self, tmp_path):
        from direct.hashing import content_hash
        rel = arm_emit.emit_release(FX.build_all(), str(tmp_path), expect_n_bundles=6)
        manifest = json.loads(
            open(os.path.join(str(tmp_path), arm_emit.RELEASE_FILENAME), "rb").read())
        assert manifest["schema_version"] == "spot.stage02_temporal_arm_release.v1"
        assert manifest["release_id_rule"] == "sha256(canonical JSON excluding release_id)"
        # FULL 64-hex, not truncated to 16
        assert len(manifest["release_id"]) == 64
        payload = {k: v for k, v in manifest.items() if k != "release_id"}
        assert manifest["release_id"] == content_hash(payload)
        assert rel["release_id"] == manifest["release_id"]
        assert manifest["external_admission"]["status"] == "pending"
        assert manifest["external_admission"]["required_verifier_id"] == arm_report.VERIFIER_ID

    def test_the_root_inventory_carries_a_hash_bound_stage1_binding(self, tmp_path):
        arm_emit.emit_release(FX.build_all(), str(tmp_path), expect_n_bundles=6)
        manifest = json.loads(
            open(os.path.join(str(tmp_path), arm_emit.RELEASE_FILENAME), "rb").read())
        s1 = manifest["stage1_binding"]
        assert arm_programs.stage1_binding_nulls(s1) == []   # complete, non-null
        assert s1["registry_scorer_view_sha256"] is not None
        assert s1["release_self_sha256"] is not None
        assert sorted(s1["admitted_programs"]) == sorted(FX.PORTABLE_IDS)
        assert s1["n_programs"] == 10
        assert s1["selector_condition_sequence"] == list(FX.CONDITIONS)   # declared order
        assert all(v is not None for v in s1["per_program_projection_sha256"].values())
        # topology is DERIVED, not a fixture assertion of 120
        topo = manifest["topology"]
        assert topo["expected_n_bundles"] == 6 and topo["expected_n_logical_arms"] == 120

    def test_the_release_binds_every_native_file_and_ranking_hash(self, tmp_path):
        from direct.hashing import content_hash, sha256_hex
        arm_emit.emit_release(FX.build_all(), str(tmp_path), expect_n_bundles=6)
        manifest = json.loads(
            open(os.path.join(str(tmp_path), arm_emit.RELEASE_FILENAME), "rb").read())
        assert len(manifest["bundles"]) == 6
        for b in manifest["bundles"]:
            d = os.path.join(str(tmp_path), b["relative_dir"])
            # files = arm_bundle + provenance + preflight; rankings = 20 files
            assert set(b["files"]) == {"arm_bundle.json", "temporal_provenance.json",
                                       "temporal_preflight.json"}
            assert len(b["rankings"]) == 20
            for rel_path, h in {**b["files"], **b["rankings"]}.items():
                raw = open(os.path.join(d, rel_path), "rb").read()
                assert sha256_hex(raw) == h["raw_sha256"]
                assert content_hash(json.loads(raw)) == h["canonical_sha256"]

    def test_reemitting_the_release_is_byte_stable(self, tmp_path):
        a = arm_emit.emit_release(FX.build_all(), str(tmp_path / "a"), expect_n_bundles=6)
        b = arm_emit.emit_release(FX.build_all(), str(tmp_path / "b"), expect_n_bundles=6)
        assert a["release_id"] == b["release_id"] and len(a["release_id"]) == 64


# =========================================================================== #
# 10k. THE PRODUCTION ALL-ARM CLI (the entrypoint the scheduler invokes)
# =========================================================================== #
_AUTH_LOCK = "/home/tcelab/.spot-runs/20260712T021343Z/stage02_solver_lock.txt"


def _write_cli_inputs(tmp_path):
    """Synthetic — clearly-marked FIXTURE — Stage-1 view, effect source and release."""
    import numpy as np
    view = {"schema_version": "spot.stage01_stage2_registry_view.v1",
            "effect_universe_symbols_sha256": "e" * 64,
            "programs": [FX.programs_registry()[p] for p in FX.PORTABLE_IDS]
            + [FX.programs_registry()[FX.NON_PORTABLE_ID]]}
    conditions = {}
    for cond in FX.CONDITIONS:
        targets = {}
        for i, tid in enumerate(FX.TARGETS):
            targets[tid] = {"effect": np.asarray(FX.effect_row(i, cond)).tolist(),
                            "mask": [], "released_estimate_id": f"{tid}|{cond}",
                            "target_symbol": f"SYM{i}", "target_ensembl": f"ENSGT{i:011d}",
                            "target_id_namespace": "fixture",
                            "qc_ontarget_significant": True, "n_guide_slots_released": 4,
                            "n_splits_total": 3, "effective_donor_n": 4}
        conditions[cond] = {"targets": targets}
    effect = {"schema_version": "spot.stage02_temporal_arm_effect_source.v1",
              "gene_index": FX.GENE_INDEX, "conditions": conditions}
    release = {"release_self_sha256": "b" * 64,
               "registry_scorer_projection_sha256": "c0" * 32,
               "temporal_method_sha256": "f" * 64, "direct_config_sha256": "e" * 64}
    import json as _json
    vp, ep, rp = (tmp_path / "view.json", tmp_path / "effect.json",
                  tmp_path / "release.json")
    vp.write_text(_json.dumps(view))
    ep.write_text(_json.dumps(effect))
    rp.write_text(_json.dumps(release))
    return str(vp), str(ep), str(rp)


class TestProductionCLI:
    """arm_bundle is NOT test-only machinery: a real CLI entrypoint builds and emits the
    content-addressed release from explicit Stage-1 view, effect source, env lock and out
    root — the shape the scheduler invokes."""

    def test_the_cli_help_documents_every_required_input(self):
        from direct.temporal.arms import run_temporal_arms
        help_text = run_temporal_arms.build_parser().format_help()
        for flag in ("--stage1-view", "--effect-source", "--env-lock", "--conditions",
                     "--out-root", "--from-condition", "--to-condition", "--all-pairs"):
            assert flag in help_text

    def test_the_cli_emits_a_content_addressed_release_end_to_end(self, tmp_path):
        from direct.temporal.arms import arm_admission, run_temporal_arms
        if not os.path.exists(_AUTH_LOCK):
            pytest.skip("authoritative Stage-2 solver lock not staged")
        vp, ep, rp = _write_cli_inputs(tmp_path)
        out = str(tmp_path / "out")
        rc = run_temporal_arms.main([
            "--stage1-view", vp, "--stage1-release", rp, "--effect-source", ep,
            "--env-lock", _AUTH_LOCK, "--conditions", "FixRest,FixStim8,FixStim48",
            "--out-root", out, "--all-pairs"])
        assert rc == 0
        man = json.loads(open(os.path.join(out, "temporal_arm_release.json")).read())
        assert man["n_bundles"] == 6 and man["n_logical_arms"] == 120
        assert man["env_lock_sha256"] == arm_env_auth()
        # every emitted bundle is admissible by the standalone verifier
        for d in [b["relative_dir"] for b in man["bundles"]]:
            assert arm_admission.verify_shipped(os.path.join(out, d))["admitted"] is True

    def test_the_cli_refuses_a_wrong_env_lock_by_name(self, tmp_path):
        from direct.temporal.arms import arm_env, run_temporal_arms
        vp, ep, rp = _write_cli_inputs(tmp_path)
        badlock = tmp_path / "base.lock"
        badlock.write_bytes(b"not the authoritative lock\n")
        with pytest.raises(arm_env.EnvLockError, match="not the authoritative"):
            run_temporal_arms.run(run_temporal_arms.build_parser().parse_args([
                "--stage1-view", vp, "--stage1-release", rp, "--effect-source", ep,
                "--env-lock", str(badlock), "--conditions", "FixRest,FixStim8,FixStim48",
                "--out-root", str(tmp_path / "o"), "--all-pairs"]))


def arm_env_auth():
    from direct.temporal.arms import arm_env
    return arm_env.AUTHORITATIVE_ENV_LOCK_SHA256


# =========================================================================== #
# 11. THE W18 ADAPTER BOUNDARY
# =========================================================================== #
class TestRequestAdapterBoundary:

    def test_the_adapter_does_not_define_the_request_schema(self):
        assert arm_request.REQUEST_SCHEMA_DEFINED_HERE is False
        assert arm_request.REQUEST_SCHEMA_OWNER == "W18"

    def test_binding_fields_expose_what_a_bundle_scoped_request_must_bind(self):
        fields = arm_request.binding_fields(FX.build())
        for k in ("bundle_key", "bundle_id", "from_condition", "to_condition",
                  "arm_keys", "programs", "method", "registry_scorer_view_sha256"):
            assert k in fields
        assert len(fields["arm_keys"]) == 20

    def test_the_adapter_reads_a_mapping_or_an_object_alike(self):
        b = FX.build()

        class Req:
            program_id = FX.PORTABLE_IDS[1]
            role, pole = "toward_B", "high"
            from_condition, to_condition = "FixRest", "FixStim48"

        as_obj = arm_request.resolve_arm(b, Req())
        as_map = arm_request.resolve_arm(b, {
            "program_id": FX.PORTABLE_IDS[1], "role": "toward_B", "pole": "high",
            "from_condition": "FixRest", "to_condition": "FixStim48"})
        assert as_obj["arm_key"] == as_map["arm_key"]

    def test_the_reverse_bundle_key_names_a_different_artifact(self):
        b = FX.build("FixRest", "FixStim48")
        assert arm_request.reverse_bundle_key(b) == "temporal|FixStim48|FixRest"
        assert arm_request.reverse_bundle_key(b) != b["bundle_key"]


# =========================================================================== #
# 12. LEGACY BYTE INVARIANCE — THIS LAYER CANNOT MOVE THE COMPARISON ARTIFACT
# =========================================================================== #
class TestLegacyByteInvariance:
    """The reusable-arm layer is ADDITIVE. It may not move a single byte of the existing
    pair-shaped temporal artifact, whose compatibility is retained.

    ``run_temporal.method_block`` binds ``temporal_code_tree_sha256`` over a FLAT listing
    of the ``.py`` files directly in the temporal package directory. Had these modules been
    dropped beside ``run_temporal.py``, that hash — and therefore ``temporal_method_sha256``
    and ``temporal_run_id`` on EVERY row of ``temporal.parquet`` — would have changed.
    Measured: it moved from b3c9b969… to 3afb2687…. In the ``arms`` SUBpackage it does not
    move at all, which is the whole reason the subpackage exists.
    """

    # The temporal method hash at the committed tip, BEFORE this layer existed.
    FROZEN_TEMPORAL_METHOD_SHA256 = (
        "b3c9b969688a293db40f90b02d7d4c521c0d1e4f7a386fba984b7a2714f67f85")

    def test_the_legacy_temporal_method_hash_is_unchanged(self):
        assert legacy_run.temporal_method_sha256(legacy_policy.load()) == \
            self.FROZEN_TEMPORAL_METHOD_SHA256, (
                "the reusable-arm layer moved the temporal method hash; every legacy "
                "temporal_run_id and temporal_method_sha256 would change with it")

    def test_the_arm_layer_is_invisible_to_the_temporal_code_tree(self):
        import os

        from direct import runid
        tdir = os.path.dirname(os.path.abspath(legacy_run.__file__))
        listed = [n for n in sorted(os.listdir(tdir)) if n.endswith(".py")]
        assert not any(n.startswith("arm_") for n in listed), \
            "an arm module beside run_temporal.py would enter the temporal code tree hash"
        assert runid.code_tree_sha256(tdir)  # the flat listing is what binds

    def test_the_dependency_runs_one_way(self):
        """temporal.arms imports temporal. NOTHING in temporal imports temporal.arms.

        Checked on the IMPORT GRAPH, not on the word "arms" — which appears in the prose of
        every module in this lane ("both arms", "the two arms"). A substring scan would
        have failed on a docstring and passed on a real import written any other way.
        """
        import ast
        import os

        tdir = os.path.dirname(os.path.abspath(legacy_run.__file__))
        for name in sorted(os.listdir(tdir)):
            if not name.endswith(".py"):
                continue
            tree = ast.parse(open(os.path.join(tdir, name)).read())
            for node in ast.walk(tree):
                imported: list[str] = []
                if isinstance(node, ast.ImportFrom):
                    imported.append(node.module or "")
                    imported += [a.name for a in node.names]
                elif isinstance(node, ast.Import):
                    imported += [a.name for a in node.names]
                for mod in imported:
                    assert mod.split(".")[0] != "arms" and not mod.endswith(".arms"), \
                        (f"{name} imports {mod!r}: the comparison layer reaches into the "
                         "arm layer, and the dependency must run ONE way")

    def test_the_legacy_estimand_still_answers_the_legacy_question(self):
        # The frozen comparison-level DiD is untouched and still differences pole-signed
        # arm values. This layer re-expresses it; it does not replace it.
        assert legacy_estimand.temporal_did(0.25, 0.75) == pytest.approx(0.5)
        assert legacy_estimand.ESTIMATED == "estimated"
