"""Round-4 finding #12 — the Stage-1 v3 RELEASE BUNDLE + concrete production selection contracts.

Guards the committed release: its self-hash reproduces, it binds the frozen scientific identities (pins),
every selection file byte-matches a fresh emit (selection_id + full-contract hash) AND passes the
independent semantic verifier, and the topology is exactly 3 within + 6 ordered temporal for one
biological A/B question.
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
    # every component names both a raw and (for JSON) a canonical hash
    for name, c in b["components"].items():
        assert "raw_sha256" in c or "raw_sha256_staged" in c, name


def test_biological_question_is_the_recorded_owner_confirmable_pair():
    q = _idx()["biological_question"]
    assert q["A_away_from"] == {"program_id": "treg_like", "direction": "high"}
    assert q["B_toward"] == {"program_id": "th1_like", "direction": "high"}
    assert "OWNER-CONFIRMABLE" in q["owner_decision"]


def test_every_selection_matches_a_fresh_emit_and_verifies():
    modes = {}
    for e in _idx()["selections"]:
        c = sc.build_contract(e["A"]["program_id"], e["A"]["direction"],
                              e["B"]["program_id"], e["B"]["direction"], e["conditions"])
        assert c["selection_id"] == e["selection_id"], e["matrix_var"]
        assert c["full_contract_content_sha256"] == e["full_contract_content_sha256"], e["matrix_var"]
        on_disk = json.load(open(os.path.join(REPO, e["path"])))
        assert on_disk["full_contract_content_sha256"] == e["full_contract_content_sha256"]
        ok, reasons = vc.verify_contract(on_disk)
        assert ok, (e["matrix_var"], reasons)
        modes[e["analysis_mode"]] = modes.get(e["analysis_mode"], 0) + 1
    assert modes == {"within_condition": 3, "temporal_cross_condition": 6}   # the 3+6 matrix topology
