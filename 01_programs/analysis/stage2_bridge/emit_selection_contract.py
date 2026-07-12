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
  * temporal_cross_condition is `awaiting_estimator` until Stage-2 implements + verifies the temporal
    estimator; Stage-1 never calls it executable and never runs the within-condition formula across
    conditions.
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
ESTIMATOR = {"within_condition": ("within_condition_v1", "available"),
             "temporal_cross_condition": ("temporal_cross_condition_v1", "not_implemented")}

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


def build_contract(a_program_id, a_direction, b_program_id, b_direction, conditions,
                   selection_origin="user_selected"):
    if selection_origin not in SELECTION_ORIGINS:
        raise SelectionError("unknown_selection_origin", str(selection_origin))
    for d, side in ((a_direction, "A"), (b_direction, "B")):
        if d not in DIRECTIONS:
            raise SelectionError("unknown_direction", f"{side}={d!r}")
    if a_program_id == b_program_id and a_direction == b_direction:
        raise SelectionError("objective_incompatible_same_pole", f"{a_program_id}/{a_direction}")

    view, view_raw_str, view_canon = rv.build_and_hash()   # pure; no write side effect
    view_raw_sha = canonical.sha256_hex(view_raw_str)
    primaries = {p["program_id"]: p for p in view["programs"]}
    for pid, side in ((a_program_id, "A"), (b_program_id, "B")):
        if pid not in primaries:
            raise SelectionError("unknown_program", f"{side}={pid!r} (not a selectable primary)")

    ordered_conditions, mode = _norm_conditions(conditions)
    estimator_id, estimator_status = ESTIMATOR[mode]
    min_panel, min_ctrl = _effect_universe_thresholds()
    pole_a, a_avail = _pole(primaries[a_program_id], a_direction, min_panel, min_ctrl)
    pole_b, b_avail = _pole(primaries[b_program_id], b_direction, min_panel, min_ctrl)

    if mode == "temporal_cross_condition":
        execution_status = "awaiting_estimator"      # estimator not implemented yet
    elif a_avail and b_avail:
        execution_status = "ready"                   # within-condition projection inputs exist
    else:
        execution_status = "refused"                 # effect-universe projection unavailable

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
        "selection_id": sel_id[:16],
        "selection_full_sha256": sel_id,
        "canonical_content": cc,
        "poles": {"A": pole_a, "B": pole_b},
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
    ("temporal_awaiting", dict(a_program_id="treg_like", a_direction="high", b_program_id="th1_like",
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
