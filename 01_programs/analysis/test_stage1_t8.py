"""Mutation / failure tests for the fail-closed Stage-1 T8 production layer.

Two adversary models:
  * NAIVE attacker: edits a byte/field but forgets bookkeeping -> caught by self-hash / manifest checks.
  * SOPHISTICATED attacker: edits a derived artifact AND recomputes its self_canonical_sha256 AND
    fixes every cross-pointer + manifest raw-hash so a naive integrity check would pass. This is still
    caught because the verifier INDEPENDENTLY re-derives the 33 selectability records and the full
    semantics table from the immutable validation and exact-compares (generator != verifier).

Preflight-caught mutations call the preflight directly and assert rejection. A clean bundle must
verify, while every current production selection must still reject (0/33 pass).
"""
import json, os, shutil, subprocess, sys, hashlib
import pytest

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "app", "data")
STAGING = os.path.join(HERE, "_t8_staging")
DATA_FILES = ["stage01_validation.json", "stage01_selectability_v3.json", "stage01_validation_semantics.json",
              "stage01_current.json", "stage01_release_manifest.json", "stage01_gate_spec.json",
              "stage01_input_manifest.json", "stage01_control_method.json", "stage01_controls_v3.csv",
              "stage01_bins_v3.csv", "stage01_control_eligible_pool.json", "stage01_program_registry.json",
              "stage01_validation_independent_check.json"]
sys.path.insert(0, HERE)
from stage1_t8_preflight import route_selection, verify_bundle, V3_METHOD  # noqa: E402


# ---- own canonical/raw helpers (do not depend on the generator) ----
def _raw(p): return hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.exists(p) else None
def _canon(o):
    d = {k: v for k, v in o.items() if k != "self_canonical_sha256"}
    return hashlib.sha256(json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()
def _jload(d, n): return json.load(open(os.path.join(d, n)))
def _write_sealed(d, n, o):
    """Write an artifact in the generator's exact byte format with a recomputed self hash."""
    o = dict(o); o["self_canonical_sha256"] = _canon(o)
    with open(os.path.join(d, n), "w") as f:
        json.dump(o, f, indent=2, ensure_ascii=False, sort_keys=False); f.write("\n")


def _copy_data(tmp):
    d = os.path.join(tmp, "data"); os.makedirs(d, exist_ok=True)
    for f in DATA_FILES:
        src = os.path.join(DATA, f)
        if os.path.exists(src): shutil.copy2(src, os.path.join(d, f))
    return d


def _reseal_bundle(d):
    """Fix ALL bookkeeping a sophisticated attacker would fix: self-hashes, current cross-pointers,
    and manifest raw hashes of served artifacts. Does NOT re-derive from the raw validation."""
    for n in ["stage01_selectability_v3.json", "stage01_validation_semantics.json"]:
        _write_sealed(d, n, _jload(d, n))
    sel, sem, cur = _jload(d, "stage01_selectability_v3.json"), _jload(d, "stage01_validation_semantics.json"), _jload(d, "stage01_current.json")
    cur["historical_validation_source"]["raw_sha256"] = _raw(os.path.join(d, "stage01_selectability_v3.json"))
    cur["historical_validation_source"]["self_canonical_sha256"] = sel["self_canonical_sha256"]
    cur["validation_semantics_source"]["raw_sha256"] = _raw(os.path.join(d, "stage01_validation_semantics.json"))
    cur["validation_semantics_source"]["self_canonical_sha256"] = sem["self_canonical_sha256"]
    _write_sealed(d, "stage01_current.json", cur)
    man = _jload(d, "stage01_release_manifest.json")
    for name, e in man["artifacts"].items():
        p = os.path.join(d, name)
        if e.get("location") in (None, "served") and os.path.exists(p):
            e["raw_sha256"] = _raw(p); e["present"] = True
    _write_sealed(d, "stage01_release_manifest.json", man)


def _verify(dir_):
    return subprocess.run([sys.executable, os.path.join(HERE, "verify_stage1_t8.py"), dir_],
                          capture_output=True, text=True).returncode


# ---- clean bundle verifies; routing is typed (no production/research/0-of-33 gate) ----
def test_clean_bundle_verifies():
    assert _verify(DATA) == 0

def test_routing_within_available_ready():
    out = route_selection({"A": {"program_id": "treg_like", "direction": "high"},
                           "B": {"program_id": "th1_like", "direction": "high"}, "conditions": ["Stim48hr"]})
    assert out["bundle_verified"] is True and out["execution_status"] == "ready"

def test_routing_no_production_research_or_0of33():
    """The active routing return + the served current pointer carry no production/research SPLIT field
    and no 0-of-33 gating field (retired field-name/value tokens; descriptive prose is not a field)."""
    out = route_selection({"A": {"program_id": "treg_like", "direction": "high"},
                           "B": {"program_id": "th1_like", "direction": "high"}, "conditions": ["Rest"]})
    cur = _jload(DATA, "stage01_current.json")
    forbidden = ("global_stage2_selectable", "production_stage2_ready", "n_selectable_program_conditions",
                 "production_execution_status", "research_execution_status", "per_condition_selectability_source",
                 "measurement_valid", "research_only", "0/33", "0-of-33", "0_of_33")
    for blob in (json.dumps(out).lower(), json.dumps(cur).lower()):
        for tok in forbidden:
            assert tok not in blob, f"forbidden gating token {tok!r} in active routing"


# ---- CP3c definedness amendment: constituent-derived regression budget (NO value/name heuristic) ----
def _semantics():
    return _jload(DATA, "stage01_validation_semantics.json")

def test_cp3c_regression_budget_from_constituents():
    """Derived from n_*_constituents (NOT program names): exactly 8 wholly-undefined + 2 measurement
    partially-undefined LOMO/control aggregates, and 9 zero-numerator pass:true rows stay DEFINED."""
    rows = _semantics()["results_semantics"]
    hard = [r for r in rows if r["semantic_class"] == "hard_selectability"]
    wholly = [r for r in hard if r.get("n_undefined_constituents", 0) > 0 and r.get("n_defined_constituents", 1) == 0]
    partial = [r for r in hard if r.get("n_undefined_constituents", 0) > 0 and r.get("n_defined_constituents", 0) > 0]
    zero_def = [r for r in rows if r["source_worst_defined_value"] == 0.0 and r["metric_defined"] is True and r["raw_pass"] is True]
    assert len(wholly) == 8 and all(r["gate_id"] == "lomo_panel_robustness" for r in wholly)
    assert len(partial) == 2
    assert len(zero_def) == 9

def test_cp3c_edge_rows_flipped_correctly():
    rows = _semantics()["results_semantics"]
    def find(strat, gid, sub):
        return next(r for r in rows if r["stratum_instance"] == strat and r["gate_id"] == gid and sub in r["metric"])
    th2 = find("th2_like|Stim8hr", "lomo_panel_robustness", "iqr(panel_mean_full)")
    tfh = find("tfh_like|Stim8hr", "lomo_panel_robustness", "iqr(panel_mean_full)")
    # false-negative fixed: the partially-undefined aggregate is now UNDEFINED (heuristic said defined)
    assert th2["metric_defined"] is False and th2["n_undefined_constituents"] == 8
    assert th2["source_worst_defined_value"] == 0.21961529056385867
    # false-positive fixed: a real zero-numerator over a positive denominator is DEFINED (heuristic said undefined)
    assert tfh["metric_defined"] is True and tfh["n_undefined_constituents"] == 0
    assert tfh["source_worst_defined_value"] == 0.0

def test_cp3c_no_value_zero_heuristic():
    """A metric value of exactly 0.0 is never treated as undefined by itself."""
    rows = _semantics()["results_semantics"]
    defined_zeros = [r for r in rows if r["source_worst_defined_value"] == 0.0 and r["metric_defined"] is True]
    assert len(defined_zeros) >= 9


# ---- NAIVE attacks (bookkeeping not fixed -> caught by hash checks) ----
def test_naive_alter_validation_byte(tmp_path):
    d = _copy_data(tmp_path); p = os.path.join(d, "stage01_validation.json")
    b = bytearray(open(p, "rb").read()); b[100] ^= 0x01; open(p, "wb").write(bytes(b))
    assert _verify(d) != 0

def test_naive_flip_selectability_bit_no_reseal(tmp_path):
    d = _copy_data(tmp_path); s = _jload(d, "stage01_selectability_v3.json")
    s["records"][0]["production_selectable"] = True
    json.dump(s, open(os.path.join(d, "stage01_selectability_v3.json"), "w"), indent=2)
    assert _verify(d) != 0


# ---- SOPHISTICATED attacks (fully resealed -> still caught by independent re-derivation) ----
def test_sophisticated_flip_two_selectability_rows(tmp_path):
    d = _copy_data(tmp_path); s = _jload(d, "stage01_selectability_v3.json")
    s["records"][0]["production_selectable"] = True
    s["records"][1]["production_selectable"] = True
    s["n_production_selectable_true"] = 2; s["n_selectable_program_conditions"] = 2
    _write_sealed(d, "stage01_selectability_v3.json", s)
    _reseal_bundle(d)
    assert _verify(d) != 0

def test_sophisticated_erase_failure_reasons(tmp_path):
    d = _copy_data(tmp_path); s = _jload(d, "stage01_selectability_v3.json")
    s["records"][0]["failed_or_undefined_hard_gates"] = []   # erase the exact reasons
    _write_sealed(d, "stage01_selectability_v3.json", s)
    _reseal_bundle(d)
    assert _verify(d) != 0

def test_sophisticated_change_semantic_outcome(tmp_path):
    d = _copy_data(tmp_path); sem = _jload(d, "stage01_validation_semantics.json")
    row = next(r for r in sem["results_semantics"] if r["semantic_class"] == "hard_selectability" and r["gate_outcome"] is False)
    row["metric_predicate_met"] = True; row["gate_outcome"] = True   # forge a hard-gate pass
    _write_sealed(d, "stage01_validation_semantics.json", sem)
    _reseal_bundle(d)
    assert _verify(d) != 0

def test_sophisticated_reinterpret_hardgate_as_advisory(tmp_path):
    d = _copy_data(tmp_path); sem = _jload(d, "stage01_validation_semantics.json")
    row = next(r for r in sem["results_semantics"] if r["semantic_class"] == "hard_selectability")
    row["semantic_class"] = "advisory_flag"; row["flagged"] = False; row["metric_predicate_met"] = None
    _write_sealed(d, "stage01_validation_semantics.json", sem)
    _reseal_bundle(d)
    assert _verify(d) != 0

def test_sophisticated_alter_source_index(tmp_path):
    d = _copy_data(tmp_path); sem = _jload(d, "stage01_validation_semantics.json")
    sem["results_semantics"][10]["source_result_index"] = 999
    _write_sealed(d, "stage01_validation_semantics.json", sem)
    _reseal_bundle(d)
    assert _verify(d) != 0

def test_sophisticated_alter_metric_field(tmp_path):
    d = _copy_data(tmp_path); sem = _jload(d, "stage01_validation_semantics.json")
    sem["results_semantics"][10]["metric"] = "forged_metric"
    _write_sealed(d, "stage01_validation_semantics.json", sem)
    _reseal_bundle(d)
    assert _verify(d) != 0

def test_sophisticated_alter_undefined_state(tmp_path):
    d = _copy_data(tmp_path); sem = _jload(d, "stage01_validation_semantics.json")
    row = next(r for r in sem["results_semantics"] if r["metric_defined"] is False)
    row["metric_defined"] = True; row["undefined_reason"] = None    # hide undefinedness
    _write_sealed(d, "stage01_validation_semantics.json", sem)
    _reseal_bundle(d)
    assert _verify(d) != 0

def test_sophisticated_reintroduce_production_field_caught(tmp_path):
    """Re-adding a retired production/0-of-33 gate to the current pointer (fully resealed) is caught."""
    d = _copy_data(tmp_path); cur = _jload(d, "stage01_current.json")
    cur["global_stage2_selectable"] = True
    _write_sealed(d, "stage01_current.json", cur)
    _write_sealed(d, "stage01_release_manifest.json", _jload(d, "stage01_release_manifest.json"))
    assert _verify(d) != 0

def test_sophisticated_flip_historical_active_gate_caught(tmp_path):
    """Turning the frozen historical validation back into a live gate (active_gate:true) is caught."""
    d = _copy_data(tmp_path); cur = _jload(d, "stage01_current.json")
    cur["historical_validation_source"]["active_gate"] = True
    _write_sealed(d, "stage01_current.json", cur)
    _write_sealed(d, "stage01_release_manifest.json", _jload(d, "stage01_release_manifest.json"))
    assert _verify(d) != 0

def test_sophisticated_alter_registry_binding(tmp_path):
    d = _copy_data(tmp_path); s = _jload(d, "stage01_selectability_v3.json")
    s["bound_hashes"]["v2_registry_raw_sha256"] = "0" * 64     # forge the registry binding
    _write_sealed(d, "stage01_selectability_v3.json", s)
    _reseal_bundle(d)
    assert _verify(d) != 0


# ---- routing refusals/statuses (typed; no production/research/0-of-33) ----
def _route(a="treg_like", ad="high", b="th1_like", bd="high", conds=("Stim48hr")):
    return route_selection({"A": {"program_id": a, "direction": ad},
                            "B": {"program_id": b, "direction": bd},
                            "conditions": list(conds) if not isinstance(conds, str) else [conds]})

def test_route_temporal_awaiting_estimator():
    out = _route(conds=["Stim8hr", "Stim48hr"])
    assert out["execution_status"] == "awaiting_estimator" and out["estimator_status"] == "not_implemented"

def test_route_effect_unavailable_refused():
    out = _route(a="th9_like", ad="low", conds=["Rest"])       # th9 effect projection unavailable
    assert out["execution_status"] == "refused"

def test_route_unknown_program_refused():
    out = _route(a="not_a_program")
    assert out["execution_status"] == "refused" and out["refusal_reason"] == "unknown_program"

def test_route_bad_direction_refused():
    out = _route(ad="sideways")
    assert out["execution_status"] == "refused" and out["refusal_reason"] == "unknown_direction"

def test_route_same_pole_refused():
    out = _route(a="treg_like", ad="high", b="treg_like", bd="high", conds=["Rest"])
    assert out["execution_status"] == "refused" and out["refusal_reason"] == "objective_incompatible_same_pole"

def test_route_unknown_condition_refused():
    out = _route(conds=["Whenever"])
    assert out["execution_status"] == "refused" and out["refusal_reason"] == "unknown_condition"

def test_route_verifies_bundle_first():
    out = _route()
    assert out["bundle_verified"] is True and out["execution_status"] == "ready"
