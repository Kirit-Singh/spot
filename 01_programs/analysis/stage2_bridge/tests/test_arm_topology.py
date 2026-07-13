"""Task C — the frozen arm TOPOLOGY inventory (ROUND4_ADDENDUM.md sha c4773562).

Independent re-derivation (generator != verifier): the 300-slot logical inventory, the 15 physical all-arm
bundle identities, the 6 shared convergence artifacts, the four (role, pole) -> desired_change mappings, the
3,540 selection capacity, and same-program/same-pole cross-time admission — all derived from the bound v3
scorer VIEW (10 base-portable programs; Th9 excluded), never a legacy registry path.
"""
import arm_keys as ak
import build_registry_view as rv
import emit_selection_contract as sc
import verify_selection_contract as vc

SCORER_VIEW = "5d1d8c362ee55dba048c8b5d6718cffe4525acbcda230d503f4899433c052a0c"
FROZEN_MAP = {("away_from_A", "high"): "decrease", ("away_from_A", "low"): "increase",
              ("toward_B", "high"): "increase", ("toward_B", "low"): "decrease"}


def test_program_set_from_view_binds_its_hash_10_portable():
    progs, canon = ak.base_portable_programs()
    assert len(progs) == 10 and "th9_like" not in progs
    assert canon == SCORER_VIEW == rv.build_and_hash()[2]   # bound to the v3 scorer VIEW, not a legacy registry


def test_desired_change_mapping_all_four_role_pole():
    for (role, pole), dc in FROZEN_MAP.items():
        assert ak.desired_change(role, pole) == dc
    # pole is NOT the arm direction: the same pole gives OPPOSITE desired_change by role
    assert ak.desired_change("away_from_A", "high") != ak.desired_change("toward_B", "high")
    assert ak.desired_change("away_from_A", "low") != ak.desired_change("toward_B", "low")


def test_logical_inventory_is_300_and_collision_free():
    progs, _ = ak.base_portable_programs()
    log = ak.enumerate_logical(progs)
    assert len(log["direct"]) == 60 and len(log["temporal"]) == 120 and len(log["pathway"]) == 120
    allk = log["direct"] + log["temporal"] + log["pathway"]
    assert len(allk) == 300 and len(set(allk)) == 300      # no collisions across lanes


def test_15_physical_bundles_carry_all_300_slots():
    progs, _ = ak.base_portable_programs()
    bundles = ak.physical_bundles(progs)
    assert len(bundles) == 15
    kinds = {}
    for b in bundles:
        kinds[b["kind"]] = kinds.get(b["kind"], 0) + 1
        assert len(b["arms"]) == 20 and len(set(b["arms"])) == 20   # every bundle carries all 20 program x desired_change arms
    assert kinds == {"direct": 3, "temporal": 6, "pathway": 6}
    covered = [a for b in bundles for a in b["arms"]]
    log = ak.enumerate_logical(progs)
    assert set(covered) == set(log["direct"] + log["temporal"] + log["pathway"])   # union == all 300, no gaps
    assert len(covered) == 300 and len(set(covered)) == 300                        # each slot admitted exactly once


def test_six_shared_convergence_artifacts_one_per_pathway_bundle():
    progs, _ = ak.base_portable_programs()
    pathway = [b for b in ak.physical_bundles(progs) if b["kind"] == "pathway"]
    conv = [b["convergence_artifact"] for b in pathway]
    assert len(pathway) == 6 and len(set(conv)) == 6           # one shared convergence per (condition, source); not duplicated 20x


def test_selection_capacity_is_exactly_3540():
    progs, _ = ak.base_portable_programs()
    cap = ak.selection_capacity(len(progs))
    assert cap["n_states_per_condition"] == 20
    assert cap["within_condition"] == 1140 == 3 * 20 * 19     # exclude the identical tuple
    assert cap["temporal_cross_condition"] == 2400 == 6 * 20 * 20
    assert cap["total"] == 3540


def test_materializer_maps_all_four_role_pole_to_desired_change():
    # emit contracts covering all four (role, pole) combinations; each arm key must use desired_change, not pole
    c = sc.build_contract("th1_like", "high", "th2_like", "low", ["Rest"])
    away, toward = c["arms"]["away_from_A"], c["arms"]["toward_B"]
    assert away["pole_direction"] == "high" and away["desired_change"] == "decrease"    # away_from_A(high)
    assert toward["pole_direction"] == "low" and toward["desired_change"] == "decrease"  # toward_B(low)
    c2 = sc.build_contract("th1_like", "low", "th2_like", "high", ["Rest"])
    assert c2["arms"]["away_from_A"]["desired_change"] == "increase"   # away_from_A(low)
    assert c2["arms"]["toward_B"]["desired_change"] == "increase"      # toward_B(high)
    for cc in (c, c2):
        for role in ("away_from_A", "toward_B"):
            arm = cc["arms"][role]
            dc = FROZEN_MAP[(role, arm["pole_direction"])]                     # independent re-derivation, no arm_keys
            assert arm["desired_change"] == dc
            assert arm["direct_arm_key"] == "direct|%s|%s|%s" % (arm["program_id"], dc, arm["condition"])
            parts = arm["direct_arm_key"].split("|")
            assert parts[2] in ("increase", "decrease") and parts[2] not in ("high", "low")   # never pole-keyed


def test_same_program_same_pole_cross_time_admitted_two_distinct_arms():
    c = sc.build_contract("th1_like", "high", "th1_like", "high", ["Stim8hr", "Stim48hr"])
    ok, reasons = vc.verify_contract(c)
    assert ok, reasons
    assert c["execution_status"] == "ready" and c["analysis_mode"] == "temporal_cross_condition"
    a, b = c["arms"]["away_from_A"], c["arms"]["toward_B"]
    assert a["desired_change"] == "decrease" and b["desired_change"] == "increase"   # opposite by role -> two arms
    assert a["temporal_arm_key"] == "temporal|th1_like|decrease|Stim8hr|Stim48hr"    # independent literal, no arm_keys
    assert b["temporal_arm_key"] == "temporal|th1_like|increase|Stim8hr|Stim48hr"
    assert a["direct_arm_key"] != b["direct_arm_key"]


def test_exact_identical_pole_refused_only_within_condition():
    # exactly identical (program, pole, condition) -> refused at emit
    try:
        sc.build_contract("treg_like", "high", "treg_like", "high", ["Rest"])
        assert False, "identical within-condition pole must raise"
    except sc.SelectionError as e:
        assert e.reason == "objective_incompatible_same_pole"
    # same program+pole at DIFFERENT timepoints -> NOT refused (valid temporal)
    c = sc.build_contract("treg_like", "high", "treg_like", "high", ["Rest", "Stim48hr"])
    assert c["execution_status"] in ("ready", "awaiting_estimator")
