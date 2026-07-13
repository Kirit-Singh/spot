"""Standalone, producer-INDEPENDENT semantic verifier for a spot.stage01_selection.v3 artifact.

The formal JSON Schema validates each field independently; it cannot (fully) reject an impossible
cross-field TUPLE. This verifier re-derives the scorer VIEW, the selection_id, the full-contract hash and
the key trust bindings from the frozen data, and enforces the mode/estimator/execution SEMANTICS — so a
fully resealed contradictory contract (e.g. temporal_cross_condition + ready + not_implemented) is REJECTED
even though it passes field-wise schema validation. generator != verifier: it never imports the emitter's
routing decision — it recomputes from artifacts + the semantic rules.
"""
from __future__ import annotations

import hashlib
import json
import os

import build_registry_view as rv
import canonical

# generator != verifier: the verifier RE-DERIVES the frozen (role, pole) -> desired_change mapping and the
# arm-key string formats from THESE LOCAL literals (ROUND4_ADDENDUM c4773562) — it does NOT import arm_keys
# (the producer/release module), so a shared helper bug or key-format drift cannot pass both. These literals
# ARE the spec re-stated here for the independent check.
_V_DESIRED = {("away_from_A", "high"): "decrease", ("away_from_A", "low"): "increase",
              ("toward_B", "high"): "increase", ("toward_B", "low"): "decrease"}


def _v_desired_change(role, pole):
    return _V_DESIRED.get((role, pole))


def _v_direct_key(pid, dc, cond):
    return "direct|" + "|".join((pid, dc, cond))


def _v_pathway_base(pid, dc, cond):
    return "pathway|" + "|".join((pid, dc, cond))


def _v_temporal_key(pid, dc, frm, to):
    return "temporal|" + "|".join((pid, dc, frm, to))

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYSIS = os.path.dirname(HERE)
PROGRAMS = os.path.dirname(ANALYSIS)
DATA = os.path.join(PROGRAMS, "app", "data")

ESTIMATOR_FOR_MODE = {"within_condition": "within_condition_v1",
                      "temporal_cross_condition": "temporal_cross_condition_v1"}


def _raw(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest() if os.path.exists(path) else None


def verify_contract(contract, data_dir=DATA):
    """Return (ok, reasons). ok iff every structural re-derivation matches AND the semantic tuple is valid."""
    reasons = []
    cc = contract.get("canonical_content") or {}

    # ---- 1) structural: selection_id + full-contract hash rederive from canonical content ----
    sel_full = hashlib.sha256(canonical.canonical_json(cc).encode()).hexdigest()
    if contract.get("selection_full_sha256") != sel_full:
        reasons.append("selection_full_sha256 does not rederive from canonical_content")
    if contract.get("selection_id") != sel_full[:16]:
        reasons.append("selection_id does not rederive from canonical_content")
    body = {k: v for k, v in contract.items() if k != "full_contract_content_sha256"}
    if contract.get("full_contract_content_sha256") != hashlib.sha256(canonical.canonical_json(body).encode()).hexdigest():
        reasons.append("full_contract_content_sha256 does not rederive (contract body was tampered)")

    # ---- 2) scorer VIEW binding: independently rebuild the Stage-2 view, compare its canonical hash ----
    view_canon = rv.build_and_hash()[2]
    if cc.get("registry_scorer_view_sha256") != view_canon:
        reasons.append("registry_scorer_view_sha256 != independently rebuilt Stage-2 view")

    # ---- 3) key trust bindings rederive from the frozen files (source h5ad + validation + view) ----
    tb = contract.get("trust_bindings") or {}
    checks = {
        "validation_raw_sha256": _raw(os.path.join(data_dir, "stage01_validation.json")),
        "validation_semantics_raw_sha256": _raw(os.path.join(data_dir, "stage01_validation_semantics.json")),
        "gate_spec_raw_sha256": _raw(os.path.join(data_dir, "stage01_gate_spec.json")),
        "scoring_view_canonical_sha256": view_canon,
        "marker_diagnostics_content_sha256": canonical.canonical_content_sha256(
            json.load(open(os.path.join(data_dir, "stage01_marker_diagnostics_v2.json")))),
    }
    for k, expected in checks.items():
        if expected is not None and tb.get(k) != expected:
            reasons.append(f"trust_bindings.{k} does not rederive")
    pv = (contract.get("provenance_bindings") or {}).get("primary_registry_v3_raw_sha256")
    if pv != _raw(os.path.join(data_dir, "stage01_program_registry_v3.json")):
        reasons.append("provenance_bindings.primary_registry_v3_raw_sha256 does not rederive")

    # ---- 4) SEMANTIC tuple (mode / estimator / execution) — the impossible-tuple gate ----
    mode = contract.get("analysis_mode")
    est_status = contract.get("estimator_status")
    exec_status = contract.get("execution_status")
    est_id = contract.get("estimator_id")
    # ready is possible ONLY with an available estimator; not_implemented can never be ready.
    if exec_status == "ready" and est_status != "available":
        reasons.append("impossible tuple: execution_status=ready requires estimator_status=available")
    if est_status == "not_implemented" and exec_status == "ready":
        reasons.append("impossible tuple: a not_implemented estimator can never be ready")
    if mode == "temporal_cross_condition" and est_status == "not_implemented" and exec_status != "awaiting_estimator":
        reasons.append("impossible tuple: temporal_cross_condition + not_implemented must be awaiting_estimator")
    # the estimator must match the mode — a temporal mode may NEVER borrow the within-condition estimator.
    if est_id != ESTIMATOR_FOR_MODE.get(mode):
        reasons.append(f"estimator_id {est_id!r} does not match analysis_mode {mode!r}")
    # the bound estimator block must agree, and an available estimator must NAME its method (not a word).
    e = contract.get("estimator") or {}
    if e.get("status") != est_status:
        reasons.append("estimator.status disagrees with top-level estimator_status")
    if e.get("estimator_id") != est_id or e.get("analysis_mode") != mode:
        reasons.append("estimator block id/mode disagrees with the contract")
    if est_status == "available" and mode == "temporal_cross_condition":
        ms = e.get("method_sha256")
        if not (isinstance(ms, str) and len(ms) == 64):
            reasons.append("an available temporal estimator must bind a 64-hex method_sha256 (a word cannot pass)")
    if est_status == "not_implemented" and "method_sha256" in e:
        reasons.append("a not_implemented estimator must NOT name a method (relabelling != existence)")

    # ---- 5) POLE IDENTITY = (program, pole, condition); ARMS re-derive with desired_change keying ----
    a, b = cc.get("A") or {}, cc.get("B") or {}
    conds = cc.get("conditions") or []
    # refuse ONLY when program+pole+condition are all identical -> within-condition same program+direction.
    # (a temporal comparison of the same program+pole at DIFFERENT timepoints is valid and must be admitted)
    if (a.get("program_id") == b.get("program_id") and a.get("direction") == b.get("direction")
            and mode == "within_condition"):
        reasons.append("impossible tuple: identical pole (same program+pole+condition) must be refused at emit")
    arms = contract.get("arms") or {}
    if conds:
        # each arm is INDEPENDENTLY re-derived from the LOCAL frozen rules above (NEVER the producer's arm_keys):
        # desired_change from the (role, pole) mapping, keys from _v_*, endpoint away_from_A@[0] / toward_B@[-1].
        expect = {"away_from_A": (a.get("program_id"), a.get("direction"), conds[0]),
                  "toward_B": (b.get("program_id"), b.get("direction"), conds[-1])}
        for role, (pid, pole_dir, condition) in expect.items():
            arm = arms.get(role) or {}
            dc = _v_desired_change(role, pole_dir)   # LOCAL frozen mapping (no arm_keys import)
            if dc is None:
                reasons.append(f"arms.{role}: cannot rederive desired_change for pole {pole_dir!r}")
                continue
            if (arm.get("role"), arm.get("program_id"), arm.get("pole_direction"),
                    arm.get("desired_change"), arm.get("condition")) != (role, pid, pole_dir, dc, condition):
                reasons.append(f"arms.{role} does not rederive (role/program/pole_direction/desired_change/condition)")
            if arm.get("direct_arm_key") != _v_direct_key(pid, dc, condition):
                reasons.append(f"arms.{role}.direct_arm_key does not rederive (must key desired_change, not pole)")
            if arm.get("pathway_arm_key_base") != _v_pathway_base(pid, dc, condition):
                reasons.append(f"arms.{role}.pathway_arm_key_base does not rederive")
            if mode == "temporal_cross_condition":
                if arm.get("temporal_arm_key") != _v_temporal_key(pid, dc, conds[0], conds[-1]):
                    reasons.append(f"arms.{role}.temporal_arm_key does not rederive")
            elif "temporal_arm_key" in arm:
                reasons.append(f"arms.{role}.temporal_arm_key present on a within-condition selection")

    return (len(reasons) == 0), reasons


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        # self-check against a freshly emitted ready contract
        import emit_selection_contract as sc
        c = sc.build_contract(a_program_id="treg_like", a_direction="high", b_program_id="th1_like",
                              b_direction="high", conditions=["Stim48hr"])
    else:
        c = json.load(open(path))
    ok, reasons = verify_contract(c)
    print("SELECTION CONTRACT VERIFIER:", "PASS" if ok else "REJECT")
    for r in reasons:
        print("  -", r)
    sys.exit(0 if ok else 1)
