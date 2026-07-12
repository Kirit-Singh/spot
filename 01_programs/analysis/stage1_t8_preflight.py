#!/usr/bin/env python3
"""Stage-1 selection ROUTING (no production/research split, no 0-of-33 gate).

Stage-1 is a continuous measurement system + generic selector. `route_selection` verifies the hash-bound
bundle integrity, then emits the generic selection contract (spot.stage01_selection.v3). Routing is typed:
execution_status is `ready` (within-condition with both poles' effect projection available), `refused`
(effect-universe projection unavailable), or `awaiting_estimator` (temporal, until Stage-2 implements the
estimator). Hard structural refusals (objective incompatibility / missing input) surface as a typed
reason. The frozen selectability is verified only as HISTORICAL provenance (active_gate:false); it is
never a live gate.
"""
import hashlib
import json
import os
import sys

DATA = os.path.join(os.path.dirname(__file__), "..", "app", "data")
REAL_CONDITIONS = {"Rest", "Stim8hr", "Stim48hr"}
V2_METHOD = "stage1-continuous-v2"
V3_METHOD = "stage1-continuous-v3.0.1"
VALIDATION_RAW_SHA = "1c14cd2884117f03bd26b56ff32d5575d92caa53c5391fa0e7e0ed4f3c815371"
SELECTABILITY_RAW_SHA = "7c326a86d4586a851f5b91fb6f7e9796946e52eb41fe60123b41a6d3471d2420"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "stage2_bridge"))


def _raw(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest() if path and os.path.exists(path) else None


def _canon(obj):
    d = {k: v for k, v in obj.items() if k != "self_canonical_sha256"}
    return hashlib.sha256(json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def verify_bundle(d):
    """Verify the hash-bound bundle integrity. Returns (ok, reasons, cur, sem). No production gate.
    The frozen selectability is verified only as historical provenance (active_gate:false)."""
    reasons = []
    def PP(n): return os.path.join(d, n)
    try:
        cur = json.load(open(PP("stage01_current.json")))
        sem = json.load(open(PP("stage01_validation_semantics.json")))
    except Exception as e:
        return False, [f"bundle load failed: {e}"], None, None

    if _raw(PP("stage01_validation.json")) != VALIDATION_RAW_SHA:
        reasons.append("immutable validation raw sha mismatch")
    for n, o in [("stage01_current.json", cur), ("stage01_validation_semantics.json", sem)]:
        if o.get("self_canonical_sha256") != _canon(o):
            reasons.append(f"{n} self_canonical_sha256 does not reproduce (tampered)")
    hv = cur.get("historical_validation_source", {})
    if hv.get("active_gate") is not False:
        reasons.append("historical_validation_source.active_gate must be false (frozen validation is not a live gate)")
    if hv.get("raw_sha256") != _raw(PP("stage01_selectability_v3.json")):
        reasons.append("current -> historical validation raw-sha cross-pointer mismatch")
    if cur.get("validation_semantics_source", {}).get("raw_sha256") != _raw(PP("stage01_validation_semantics.json")):
        reasons.append("current -> semantics raw-sha cross-pointer mismatch")
    if cur.get("v2_registry", {}).get("status") != "HISTORICAL_NOT_CURRENT":
        reasons.append("v2 registry not marked HISTORICAL_NOT_CURRENT")
    # no production/research split or 0-of-33 fields anywhere in the active pointer
    blob = json.dumps(cur).lower()
    for tok in ("global_stage2_selectable", "production_stage2_ready", "n_selectable_program_conditions",
                "0/33", "research_only"):
        if tok in blob:
            reasons.append(f"retired production/research/0-of-33 field present in current: {tok}")
    return (len(reasons) == 0), reasons, cur, sem


def route_selection(request, data_dir=None):
    """Verify the bundle, then emit the generic selection contract. Returns the typed routing."""
    d = data_dir or DATA
    ok, reasons, cur, _ = verify_bundle(d)
    if not ok:
        return {"bundle_verified": False, "execution_status": "refused", "reasons": reasons}
    import emit_selection_contract as sc
    A, B = request.get("A") or {}, request.get("B") or {}
    try:
        contract = sc.build_contract(A.get("program_id"), A.get("direction"),
                                     B.get("program_id"), B.get("direction"), request.get("conditions"),
                                     selection_origin=request.get("selection_origin", "user_selected"))
    except sc.SelectionError as e:
        return {"bundle_verified": True, "execution_status": "refused", "refusal_reason": e.reason, "reasons": [e.reason]}
    return {"bundle_verified": True, "execution_status": contract["execution_status"],
            "selection_id": contract["selection_id"], "analysis_mode": contract["analysis_mode"],
            "estimator_status": contract["estimator_status"], "contract": contract, "reasons": []}


if __name__ == "__main__":
    d = DATA
    req = {"A": {"program_id": "treg_like", "direction": "high"},
           "B": {"program_id": "th1_like", "direction": "high"}, "conditions": ["Stim48hr"]}
    out = route_selection(req)
    print(json.dumps({k: v for k, v in out.items() if k != "contract"}, indent=2))
    assert out["bundle_verified"] and out["execution_status"] == "ready", "within-condition available pair must route ready"
    print("OK: within-condition available pair routes ready; no production/research/0-of-33 gate.")
