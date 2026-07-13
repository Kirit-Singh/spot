"""Generic Stage-1 selection emitter (schema spot.stage01_selection.v3).

Stage-1 is a continuous measurement system + generic selector. There is NO production/research split
and NO 0-of-33 gating anywhere in the active contract. Any supported (program A, direction A, program B,
direction B, condition/mode) yields the SAME typed contract. The two ordered poles are emitted
SEPARATELY; there is no combined objective (that belongs to Stage-2).

Active routing is compact + typed:
  execution_status      : ready | refused | awaiting_estimator
  analysis_mode         : within_condition | temporal_cross_condition
  estimator_id          : within_condition_v1 | temporal_cross_condition_v1
  estimator_status      : available | not_implemented
  poles[X].effect_projection_status : available | unavailable, with exact measured / effect-universe
                          gene counts and reason codes.

Routing rules:
  * within_condition is `ready` ONLY when BOTH poles' effect projection is available (the required
    projection inputs exist); otherwise `refused` (a well-formed contract that refuses cleanly).
  * temporal_cross_condition is `ready` when its estimator (temporal_cross_condition_v1) is implemented +
    bound (estimator_status `available`); `awaiting_estimator` (NOT a hard refusal) when it is absent. The
    temporal method identity is bound (contract `estimator` block) so Stage-2 can re-verify — a contract
    cannot vote itself an estimator; Stage-1 never runs the within-condition formula across conditions.
Hard structural refusals (objective incompatibility / missing input) RAISE — they are not selections.
Effect-universe unavailability is NOT a raise; it is a clean `refused` contract.

The frozen 0/33 marker-removal validation is preserved ONLY as historical provenance (its hash, bytes
unchanged) — never as an active field or a research blocker. Effect-universe projection availability uses
the EXISTING frozen base-portability thresholds (read from the validation), not a new threshold.

Machine artifact = compact enums, ids, hashes, counts, values, booleans ONLY. No prose/note fields.
Two hashes: `selection_id` (biological, citation-invariant — over canonical_content, whose registry hash
is the citation-invariant scoring VIEW) and `full_contract_content_sha256` (whole artifact).
"""
from __future__ import annotations

import hashlib
import json
import os

import build_registry_view as rv
import canonical

import arm_keys as ak   # canonical desired_change keying + frozen topology (ROUND4_ADDENDUM c4773562)

SCHEMA = "spot.stage01_selection.v3"
STAGE1_METHOD_VERSION = "stage1-continuous-v3.0.1"
DATASET_ID = "marson2025_gwcd4_perturbseq"
EFFECT_UNIVERSE_ID = "marson2025_gwcd4_perturbseq : GWCD4i.DE_stats.h5ad"
SOURCE_H5AD_SHA256 = "2edc6d318415c8b0ee779d707ab86e26ddb6f0274db51ab4a12f21ebfda50e43"
SOURCE_HF_REVISION = "e5fcf98b56a9302921d402e97fc5a190bd88f9a6"
DONOR_SCOPE = "all"

DIRECTIONS = ("high", "low")
REAL_CONDITIONS = ("Rest", "Stim8hr", "Stim48hr")
SELECTION_ORIGINS = ("user_selected", "fixture")
# Estimators Stage-1 will route as executable. temporal_cross_condition_v1 is now implemented + verified on
# the Stage-2 side (W18, agent/stage2-direct-v3). Membership here means "Stage-1 emits ready/available";
# Stage-2 INDEPENDENTLY re-verifies the method exists (a contract cannot vote itself an estimator), so a
# stale/spoofed membership fails closed downstream (estimator_declared_available_but_stage2_has_not_built_it).
# The absent case is exercised in tests by monkeypatching IMPLEMENTED_ESTIMATORS.
IMPLEMENTED_ESTIMATORS = ("within_condition_v1", "temporal_cross_condition_v1")
ESTIMATOR_FOR_MODE = {"within_condition": "within_condition_v1",
                      "temporal_cross_condition": "temporal_cross_condition_v1"}
# Bound METHOD identity per estimator: a contract that says "available" while naming no method hash has
# admitted only a word. Mirror of the Stage-2 stage1_v3.estimator_registry() entry (handoff W18->W13 §4).
# method_sha256 covers the temporal method + the within-condition method it differences + the batch-confound
# policy + k + the display policy + BOTH code trees. CROSS-LANE PIN: re-sync when the Stage-2 temporal method
# moves — Stage-2's gate fail-closes on a mismatch. Live value as of Stage-2 commit 5001e36.
ESTIMATOR_REGISTRY = {
    "temporal_cross_condition_v1": {
        "estimator_id": "temporal_cross_condition_v1",
        "analysis_mode": "temporal_cross_condition",
        "n_conditions": 2,
        "method_id": "spot.stage02.temporal_cross_condition.v1",
        "method_version": "stage2-temporal-cross-condition-v1-did-on-program-projections",
        "estimand_id": "spot.stage02.temporal.estimand.population_program_projection_shift.v1",
        "estimand_level": "population",
        "estimand_is_per_cell_fate": False,
        "inference_status": "not_calibrated",
        "method_sha256": "c05baa8f847f284a6cb187df24668ac0e5197dfdf2d238ced04c7847b7226e77",
    },
}


def _estimator_binding(mode, ordered_conditions):
    """Derive (estimator_id, status, binding) for a mode. status FOLLOWS from IMPLEMENTED_ESTIMATORS and is
    never asserted independently. A present estimator binds its full method identity; an absent one names NO
    method hash — relabelling can never manufacture existence."""
    estimator_id = ESTIMATOR_FOR_MODE[mode]
    present = estimator_id in IMPLEMENTED_ESTIMATORS
    status = "available" if present else "not_implemented"
    if present and estimator_id in ESTIMATOR_REGISTRY:
        binding = {**ESTIMATOR_REGISTRY[estimator_id], "status": status,
                   "n_conditions": len(ordered_conditions)}
    else:
        binding = {"estimator_id": estimator_id, "analysis_mode": mode,
                   "n_conditions": len(ordered_conditions), "status": status}
    return estimator_id, status, binding

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYSIS = os.path.dirname(HERE)
PROGRAMS = os.path.dirname(ANALYSIS)
DATA = os.path.join(PROGRAMS, "app", "data")


class SelectionError(ValueError):
    """Hard structural refusal: objective incompatibility or a malformed/missing input. Typed reason,
    never a results-dependent threshold. (Effect-universe unavailability is NOT this — it is a clean
    `refused` contract.)"""
    def __init__(self, reason, detail=""):
        self.reason = reason
        super().__init__(f"{reason}: {detail}" if detail else reason)


def _sha_file(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest() if os.path.exists(path) else None


def _canonical_content_sha(path):
    return canonical.canonical_content_sha256(json.load(open(path))) if os.path.exists(path) else None


def _effect_universe_thresholds():
    """The EXISTING frozen base-portability thresholds (not a new threshold), read from the validation."""
    v = json.load(open(os.path.join(DATA, "stage01_validation.json")))
    any_prog = next(iter(v["stage2_base_portability"].values()))
    thr = {m["metric"]: m["threshold"] for m in any_prog["metrics"]}
    return int(thr["n_panel_in_effect_universe"]), int(thr["n_control_in_effect_universe"])


def _norm_conditions(conditions):
    if isinstance(conditions, str):
        conditions = [conditions]
    conditions = list(conditions)
    if not (1 <= len(conditions) <= 2):
        raise SelectionError("invalid_condition_count", f"{len(conditions)} conditions (expect 1 or 2)")
    for c in conditions:
        if c not in REAL_CONDITIONS:
            raise SelectionError("unknown_condition", str(c))
    seen, ordered = set(), []
    for c in conditions:
        if c not in seen:
            seen.add(c); ordered.append(c)
    mode = "within_condition" if len(ordered) == 1 else "temporal_cross_condition"
    return ordered, mode


def _pole(view_prog, direction, min_panel, min_ctrl):
    n_panel = view_prog["n_panel_in_effect_universe"]
    n_ctrl = view_prog["n_control_in_effect_universe"]
    reasons = []
    if n_panel < min_panel:
        reasons.append("panel_below_effect_universe_min")
    if n_ctrl < min_ctrl:
        reasons.append("control_below_effect_universe_min")
    available = not reasons
    return {
        "program_id": view_prog["program_id"],
        "direction": direction,
        "effect_projection_status": "available" if available else "unavailable",
        "n_measured": view_prog["n_panel_symbols"],
        "n_panel_in_effect_universe": n_panel,
        "n_control_in_effect_universe": n_ctrl,
        "reason_codes": reasons,
    }, available


def _arm_ref(role, program_id, direction, condition, mode, ordered_conditions):
    """One INDEPENDENT reusable per-program arm reference (ROUND4_ADDENDUM c4773562). Keyed by DESIRED CHANGE
    (ak.desired_change(role, direction)) — NEVER the pole direction/role: the same high pole means opposite
    perturbations by role, so a cached arm must not depend on role/pole. `pole_direction` (high|low) is kept
    as SELECTION metadata only. The pole sits at THIS condition (away_from_A@conditions[0], toward_B@[-1]) —
    its endpoint disambiguates poles so a same-program+pole pair at DIFFERENT timepoints is two distinct arms.
    A temporal (cross-condition) selection additionally references the (from, to) temporal-arm key. The UI
    JOINS the two arms with NO combined/balanced/weighted score."""
    dc = ak.desired_change(role, direction)
    ref = {"role": role, "program_id": program_id, "pole_direction": direction, "desired_change": dc,
           "condition": condition,
           "direct_arm_key": ak.direct_key(program_id, dc, condition),
           "pathway_arm_key_base": ak.pathway_key_base(program_id, dc, condition)}  # + '|<source>' at invocation
    if mode == "temporal_cross_condition":
        ref["temporal_arm_key"] = ak.temporal_key(program_id, dc, ordered_conditions[0], ordered_conditions[-1])
    return ref


def build_contract(a_program_id, a_direction, b_program_id, b_direction, conditions,
                   selection_origin="user_selected"):
    if selection_origin not in SELECTION_ORIGINS:
        raise SelectionError("unknown_selection_origin", str(selection_origin))
    for d, side in ((a_direction, "A"), (b_direction, "B")):
        if d not in DIRECTIONS:
            raise SelectionError("unknown_direction", f"{side}={d!r}")

    view, view_raw_str, view_canon = rv.build_and_hash()   # pure; no write side effect
    view_raw_sha = canonical.sha256_hex(view_raw_str)
    primaries = {p["program_id"]: p for p in view["programs"]}
    for pid, side in ((a_program_id, "A"), (b_program_id, "B")):
        if pid not in primaries:
            raise SelectionError("unknown_program", f"{side}={pid!r} (not a selectable primary)")

    ordered_conditions, mode = _norm_conditions(conditions)
    # POLE IDENTITY = (program, direction, condition). Refuse ONLY when all three are identical — i.e. same
    # program+direction in WITHIN-condition mode (both poles at the same timepoint -> a true self-comparison).
    # Same program+direction at DIFFERENT timepoints is a VALID temporal comparison (condition disambiguates
    # the poles), so _norm_conditions collapsing to one condition (mode == within_condition) is the test.
    if a_program_id == b_program_id and a_direction == b_direction and mode == "within_condition":
        raise SelectionError("objective_incompatible_same_pole",
                             f"{a_program_id}/{a_direction}@{ordered_conditions[0]}")
    estimator_id, estimator_status, estimator = _estimator_binding(mode, ordered_conditions)
    min_panel, min_ctrl = _effect_universe_thresholds()
    pole_a, a_avail = _pole(primaries[a_program_id], a_direction, min_panel, min_ctrl)
    pole_b, b_avail = _pole(primaries[b_program_id], b_direction, min_panel, min_ctrl)

    if mode == "temporal_cross_condition" and estimator_status != "available":
        execution_status = "awaiting_estimator"      # temporal estimator not implemented -> NOT a hard refusal
    elif a_avail and b_avail:
        execution_status = "ready"                   # estimator present (within or temporal) + both poles project
    else:
        execution_status = "refused"                 # effect-universe projection unavailable for a pole

    cc = {
        "A": {"program_id": a_program_id, "score_field": f"{a_program_id}_score", "direction": a_direction},
        "B": {"program_id": b_program_id, "score_field": f"{b_program_id}_score", "direction": b_direction},
        "analysis_mode": mode,
        "combined_objective": None,
        "conditions": ordered_conditions,
        "dataset_id": DATASET_ID,
        "donor_scope": DONOR_SCOPE,
        "effect_universe_id": EFFECT_UNIVERSE_ID,
        "poles_separate": True,
        "registry_scorer_view_sha256": view_canon,
        "source_h5ad_sha256": SOURCE_H5AD_SHA256,
        "source_hf_revision": SOURCE_HF_REVISION,
        "stage1_method_version": STAGE1_METHOD_VERSION,
    }
    sel_id = hashlib.sha256(canonical.canonical_json(cc).encode("utf-8")).hexdigest()

    sem = json.load(open(os.path.join(DATA, "stage01_validation_semantics.json")))
    ce = sem.get("constituent_evidence", {})
    contract = {
        "schema_version": SCHEMA,
        "selection_origin": selection_origin,
        "execution_status": execution_status,
        "analysis_mode": mode,
        "estimator_id": estimator_id,
        "estimator_status": estimator_status,
        "estimator": estimator,
        "selection_id": sel_id[:16],
        "selection_full_sha256": sel_id,
        "canonical_content": cc,
        "poles": {"A": pole_a, "B": pole_b},
        # the pair expressed as two INDEPENDENT per-program arm references (no fused pair object, no combined
        # score). Each arm sits at its OWN pole condition: away_from_A at conditions[0], toward_B at
        # conditions[-1] (same as [0] within-condition; the later timepoint for a temporal comparison).
        "arms": {
            "away_from_A": _arm_ref("away_from_A", a_program_id, a_direction, ordered_conditions[0], mode, ordered_conditions),
            "toward_B": _arm_ref("toward_B", b_program_id, b_direction, ordered_conditions[-1], mode, ordered_conditions),
        },
        "trust_bindings": {
            "validation_raw_sha256": _sha_file(os.path.join(DATA, "stage01_validation.json")),
            "validation_semantics_raw_sha256": _sha_file(os.path.join(DATA, "stage01_validation_semantics.json")),
            "validation_semantics_self_canonical_sha256": sem.get("self_canonical_sha256"),
            "gate_spec_raw_sha256": _sha_file(os.path.join(DATA, "stage01_gate_spec.json")),
            "constituent_main_content_canonical_sha256": (ce.get("main") or {}).get("content_canonical_sha256"),
            "constituent_overlay_donor_content_canonical_sha256": (ce.get("overlay_donor") or {}).get("content_canonical_sha256"),
            "marker_diagnostics_content_sha256": _canonical_content_sha(os.path.join(DATA, "stage01_marker_diagnostics_v2.json")),
            "scoring_view_raw_sha256": view_raw_sha,
            "scoring_view_canonical_sha256": view_canon,
        },
        "provenance_bindings": {
            "primary_registry_v3_raw_sha256": _sha_file(os.path.join(DATA, "stage01_program_registry_v3.json")),
        },
        "historical_validation_provenance": {
            "kind": "frozen_lomo_within_condition_validation_v3",
            "selectability_v3_raw_sha256": _sha_file(os.path.join(DATA, "stage01_selectability_v3.json")),
            "active_gate": False,
        },
    }
    contract["full_contract_content_sha256"] = hashlib.sha256(
        canonical.canonical_json(contract).encode("utf-8")).hexdigest()
    return contract


def emit_json(contract) -> str:
    return json.dumps(contract, indent=2, ensure_ascii=True, sort_keys=False) + "\n"


FIXTURES = os.path.join(HERE, "fixtures")   # OUTSIDE the served release
FIXTURE_CASES = [
    ("within_ready", dict(a_program_id="treg_like", a_direction="high", b_program_id="th1_like",
                          b_direction="high", conditions=["Stim48hr"])),
    ("within_refused", dict(a_program_id="th9_like", a_direction="low", b_program_id="th1_like",
                            b_direction="high", conditions=["Rest"])),
    ("temporal_ready", dict(a_program_id="treg_like", a_direction="high", b_program_id="th1_like",
                            b_direction="high", conditions=["Stim8hr", "Stim48hr"])),
]


def write_fixtures():
    os.makedirs(FIXTURES, exist_ok=True)
    # remove any stale v2 fixtures
    for f in os.listdir(FIXTURES):
        if f.startswith("stage01_selection_") and f.endswith(".json"):
            os.remove(os.path.join(FIXTURES, f))
    out = []
    for name, kw in FIXTURE_CASES:
        c = build_contract(selection_origin="fixture", **kw)
        p = os.path.join(FIXTURES, f"stage01_selection_{name}_example.json")
        with open(p, "w") as fh:
            fh.write(emit_json(c))
        out.append((name, p, c["selection_id"], c["execution_status"]))
    return out


if __name__ == "__main__":
    for name, p, sid, status in write_fixtures():
        print(f"fixture {name:18s} -> {os.path.relpath(p, PROGRAMS)}  id={sid}  execution_status={status}")
    print("NOTE: fixtures live under stage2_bridge/fixtures/ (selection_origin=fixture); NO selection is served as current.")
