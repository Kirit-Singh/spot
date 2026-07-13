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
            method=FX.method(), scorer_view_sha256="a" * 64)
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

    def test_the_only_inherited_exemption_is_the_registry_scorer_view_hash(self):
        # It matches /score/ only because "scorer" contains "score". It is the hash of the
        # Stage-1 registry scorer VIEW, carried under the contract's own spelling; nothing
        # ranks or gates on it. The exemption is the exact spelling, not the shape.
        assert arm_admission.INHERITED_FIREWALL_EXCEPTIONS == {"registry_scorer_view_sha256"}
        raw = direct_admission.forbidden_keys(FX.build())
        assert raw == ["program_admission.registry_scorer_view_sha256"]

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
        assert addr["verification"]["admitted"] is True
        assert addr["n_arms"] == 20
        assert len(addr["raw_sha256"]) == 64 and len(addr["canonical_sha256"]) == 64
        assert addr["raw_sha256"] == addr["raw_sha256_on_disk"]
        on_disk = json.loads(open(addr["path_abs"], "rb").read())
        assert on_disk == b

    def test_emitting_twice_writes_the_same_bytes(self, tmp_path):
        a = arm_emit.emit_bundle(FX.build(), str(tmp_path / "one"))
        b = arm_emit.emit_bundle(FX.build(), str(tmp_path / "two"))
        assert a["raw_sha256"] == b["raw_sha256"]
        assert a["canonical_sha256"] == b["canonical_sha256"]
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
