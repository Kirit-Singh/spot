"""Round-4 #12 + Addendum Rule 2 — the GENERIC Stage-1 v3 release bundle + deterministic materializer.

Guards: the bundle self-hash reproduces and binds the frozen scientific pins; it declares a GENERIC selector
(any program pair, directions, timepoints) — NO biological pair is canonical; the deterministic materializer
builds a valid, verifiable contract for an arbitrary non-Treg pair; treg->th1 appears only as a labelled
demo/default; every demo selection byte-matches a fresh emit + verifies + expresses two per-program arm
references; the demo topology is exactly 3 within + 6 ordered temporal.
"""
import hashlib
import json
import os

import build_registry_view as rv
import emit_selection_contract as sc
import verify_selection_contract as vc

BRIDGE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(BRIDGE)))
REL = os.path.join(BRIDGE, "release")

SCORER_PROJECTION = "008c1da121a1ea3b08871f1bc0339b120d5dc9b46d01619768eebd046331bd85"
SCORES_CANONICAL = "43c4296d5166740c334441a69df23bb440a073382bbe79628a3bb89e43d51316"
VALIDATION_RAW = "1c14cd2884117f03bd26b56ff32d5575d92caa53c5391fa0e7e0ed4f3c815371"
SELECTABILITY_RAW = "7c326a86d4586a851f5b91fb6f7e9796946e52eb41fe60123b41a6d3471d2420"
SCORER_VIEW = "5d1d8c362ee55dba048c8b5d6718cffe4525acbcda230d503f4899433c052a0c"


def _rel(): return json.load(open(os.path.join(REL, "stage01_v3_release.json")))
def _idx(): return json.load(open(os.path.join(REL, "stage01_v3_release_index.json")))


def test_release_self_hash_reproduces():
    b = _rel()
    d = {k: v for k, v in b.items() if k != "self_release_sha256"}
    got = hashlib.sha256(json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
    assert got == b["self_release_sha256"]


def test_release_binds_the_frozen_scientific_pins():
    b = _rel()
    assert b["registry_scorer_projection_sha256"] == SCORER_PROJECTION
    assert b["scores_canonical_content_sha256"] == SCORES_CANONICAL
    assert b["registry_scorer_view_canonical_sha256"] == SCORER_VIEW == rv.build_and_hash()[2]
    assert b["components"]["validation"]["raw_sha256"] == VALIDATION_RAW
    assert b["components"]["selectability_v3"]["raw_sha256"] == SELECTABILITY_RAW
    for name, c in b["components"].items():
        assert "raw_sha256" in c or "raw_sha256_staged" in c, name


def test_release_declares_a_generic_selector():
    s = _rel()["selector"]
    assert s["kind"] == "generic_continuous_program_selector"
    assert s["materializer"] == "stage2_bridge/emit_selection_contract.build_contract"
    # admitted program set is DERIVED from the v3 scorer VIEW (10 base-portable; Th9 excluded), binds its sha
    assert s["program_set_source"] == "v3_scorer_view"
    assert s["registry_scorer_view_canonical_sha256"] == SCORER_VIEW == rv.build_and_hash()[2]
    assert len(s["admitted_programs"]) == 10 and "th9_like" not in s["admitted_programs"]
    assert s["excluded_nonportable"] == ["th9_like"]
    assert set(s["modes"]) == {"within_condition", "temporal_cross_condition"}
    assert set(s["arm_keying"]) == {"direct", "temporal", "pathway"}
    # frozen (role, pole) -> desired_change mapping (ROUND4 c4773562)
    assert s["desired_change_mapping"] == {"away_from_A(high)": "decrease", "away_from_A(low)": "increase",
                                           "toward_B(high)": "increase", "toward_B(low)": "decrease"}
    # frozen topology: 300 logical slots, 15 physical all-arm bundles, 6 convergence artifacts
    assert s["arm_topology"]["logical_slots"] == {"direct": 60, "temporal": 120, "pathway": 120, "total": 300}
    assert s["arm_topology"]["physical_bundles"]["total"] == 15
    assert s["arm_topology"]["convergence_artifacts"] == 6
    # frozen capacity: exactly 3,540 valid ordered selections (1,140 within + 2,400 temporal)
    assert s["selection_capacity"] == {"n_states_per_condition": 20, "within_condition": 1140,
                                       "temporal_cross_condition": 2400, "total": 3540}


def test_demo_default_is_labelled_demo_not_canonical():
    idx = _idx()
    assert idx["selector_is_generic"] is True
    d = idx["demo_default_selection"]
    assert d["role"] == "demo_default_only"
    assert "canonical biology" in d["note"] and "generic" in d["note"]   # explicitly denies canonical biology
    # no top-level "biological_question"/"canonical" framing survives
    assert "biological_question" not in idx


def test_generic_materializer_produces_arbitrary_pair():
    # an ARBITRARY non-Treg pair, within + different-timepoint temporal, both materialize + verify + are ready
    for conds in (["Rest"], ["Rest", "Stim48hr"]):
        c = sc.build_contract("th2_like", "high", "cd4_ctl_like", "low", conds)
        ok, reasons = vc.verify_contract(c)
        assert ok, reasons
        assert c["execution_status"] == "ready"
        assert c["arms"]["away_from_A"]["program_id"] == "th2_like"
        assert c["arms"]["toward_B"]["program_id"] == "cd4_ctl_like"
        # arms key on desired_change (th2/high away -> decrease; cd4_ctl/low toward -> decrease), NOT the pole
        assert c["arms"]["away_from_A"]["desired_change"] == "decrease"
        assert c["arms"]["toward_B"]["desired_change"] == "decrease"
        assert c["arms"]["away_from_A"]["direct_arm_key"].startswith("direct|th2_like|decrease|")


def test_every_demo_selection_matches_a_fresh_emit_and_verifies():
    modes = {}
    for e in _idx()["demo_selections"]:
        c = sc.build_contract(e["A"]["program_id"], e["A"]["direction"],
                              e["B"]["program_id"], e["B"]["direction"], e["conditions"])
        assert c["selection_id"] == e["selection_id"], e["matrix_var"]
        assert c["full_contract_content_sha256"] == e["full_contract_content_sha256"], e["matrix_var"]
        on_disk = json.load(open(os.path.join(REPO, e["path"])))
        assert on_disk["full_contract_content_sha256"] == e["full_contract_content_sha256"]
        ok, reasons = vc.verify_contract(on_disk)
        assert ok, (e["matrix_var"], reasons)
        # each selection expresses two independent per-program arm references (no fused pair object)
        assert on_disk["arms"]["away_from_A"]["program_id"] == on_disk["canonical_content"]["A"]["program_id"]
        assert on_disk["arms"]["toward_B"]["program_id"] == on_disk["canonical_content"]["B"]["program_id"]
        modes[e["analysis_mode"]] = modes.get(e["analysis_mode"], 0) + 1
    assert modes == {"within_condition": 3, "temporal_cross_condition": 6}   # demo topology
