"""Generic Stage-1 selection contract tests (spot.stage01_selection.v3).

No production/research split and no 0-of-33 gating anywhere in the active contract; routing is typed
(execution_status / estimator / per-pole effect_projection_status); temporal_cross_condition is READY once
its estimator (temporal_cross_condition_v1) is implemented + bound, and awaiting_estimator (never a hard
refused) when it is absent; effect-universe-unavailable poles refuse cleanly; the frozen selectability is
bound only as historical provenance (bytes unchanged); NO selection is served as current."""
import hashlib
import json
import os

import pytest

import build_registry_view as rv
import canonical
import emit_selection_contract as sc
from emit_selection_contract import SelectionError

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGRAMS = os.path.dirname(os.path.dirname(HERE))
DATA = os.path.join(PROGRAMS, "app", "data")

READY = dict(a_program_id="treg_like", a_direction="high", b_program_id="th1_like",
             b_direction="high", conditions=["Stim48hr"])
REFUSED = dict(a_program_id="th9_like", a_direction="low", b_program_id="th1_like",
               b_direction="high", conditions=["Rest"])           # th9 effect projection unavailable
TEMPORAL = dict(a_program_id="treg_like", a_direction="high", b_program_id="th1_like",
                b_direction="high", conditions=["Stim8hr", "Stim48hr"])

FORBIDDEN = ["production", "research", "0_of_33", "0-of-33", "0/33",
             "measurement_valid", "global_stage2_selectable", "namespace"]


def test_deterministic_and_generic_shape():
    c1 = sc.build_contract(**READY)
    c2 = sc.build_contract(**READY)
    assert json.dumps(c1, sort_keys=True) == json.dumps(c2, sort_keys=True)
    for kw in (REFUSED, TEMPORAL):
        c = sc.build_contract(**kw)
        assert set(c.keys()) == set(c1.keys())
        assert set(c["poles"]["A"].keys()) == set(c1["poles"]["A"].keys())


def test_no_production_research_or_0of33_fields():
    """The whole active contract is free of production/research split + 0-of-33 gating tokens."""
    for kw in (READY, REFUSED, TEMPORAL):
        blob = json.dumps(sc.build_contract(**kw)).lower()
        for tok in FORBIDDEN:
            assert tok not in blob, f"forbidden token {tok!r} present"


def test_execution_status_routing():
    assert sc.build_contract(**READY)["execution_status"] == "ready"
    assert sc.build_contract(**REFUSED)["execution_status"] == "refused"
    # temporal_cross_condition_v1 is now implemented + admitted -> ready / available (was awaiting / not_implemented)
    t = sc.build_contract(**TEMPORAL)
    assert t["execution_status"] == "ready"
    assert t["analysis_mode"] == "temporal_cross_condition"
    assert t["estimator_id"] == "temporal_cross_condition_v1" and t["estimator_status"] == "available"
    w = sc.build_contract(**READY)
    assert w["estimator_id"] == "within_condition_v1" and w["estimator_status"] == "available"


def test_temporal_awaiting_when_estimator_absent(monkeypatch):
    """Estimator genuinely absent (simulated): temporal is awaiting_estimator — NOT a hard refused, NOT
    ready — and still names its OWN estimator (never borrows within-condition). within-condition unaffected."""
    monkeypatch.setattr(sc, "IMPLEMENTED_ESTIMATORS", ("within_condition_v1",))
    t = sc.build_contract(**TEMPORAL)
    assert t["execution_status"] == "awaiting_estimator"
    assert t["execution_status"] not in ("ready", "refused")
    assert t["estimator_id"] == "temporal_cross_condition_v1" and t["estimator_status"] == "not_implemented"
    assert sc.build_contract(**READY)["execution_status"] == "ready"


def test_temporal_binds_method_identity_when_present():
    """A ready temporal contract binds a REAL method identity (id + estimand + a 64-hex method_sha256) at a
    population-level, not-calibrated, not-per-cell-fate estimand — a bound method, not a word."""
    e = sc.build_contract(**TEMPORAL)["estimator"]
    assert e["estimator_id"] == "temporal_cross_condition_v1" and e["status"] == "available"
    assert e["analysis_mode"] == "temporal_cross_condition" and e["n_conditions"] == 2
    assert e["method_id"] == "spot.stage02.temporal_cross_condition.v1"
    assert isinstance(e["method_sha256"], str) and len(e["method_sha256"]) == 64
    assert e["estimand_level"] == "population" and e["estimand_is_per_cell_fate"] is False
    assert e["inference_status"] == "not_calibrated"


def test_relabelling_does_not_manufacture_an_estimator(monkeypatch):
    """Anti-spoof (kept): estimator_status FOLLOWS from IMPLEMENTED_ESTIMATORS. With the estimator absent no
    input relabelling yields available/ready, and the contract names NO method hash — relabelling != existence."""
    monkeypatch.setattr(sc, "IMPLEMENTED_ESTIMATORS", ("within_condition_v1",))
    t = sc.build_contract(**TEMPORAL)
    assert t["estimator_status"] != "available" and t["execution_status"] != "ready"
    assert "method_sha256" not in t["estimator"]


def test_temporal_never_borrows_within_condition_estimator():
    """A temporal mode is answered by the temporal estimator, never the within-condition one — the single
    most dangerous confusion this gate prevents (borrowed numbers would look exactly like an answer)."""
    t = sc.build_contract(**TEMPORAL)
    assert t["estimator_id"] == "temporal_cross_condition_v1" and t["estimator_id"] != "within_condition_v1"
    assert t["estimator"]["estimator_id"] == "temporal_cross_condition_v1"
    assert t["estimator"]["analysis_mode"] == "temporal_cross_condition"


def test_effect_projection_status_and_reasons():
    ready = sc.build_contract(**READY)
    for side in ("A", "B"):
        p = ready["poles"][side]
        assert p["effect_projection_status"] == "available" and p["reason_codes"] == []
        assert p["n_measured"] >= 1 and p["n_panel_in_effect_universe"] >= 3 and p["n_control_in_effect_universe"] >= 10
    refused = sc.build_contract(**REFUSED)
    a = refused["poles"]["A"]                                     # th9_like
    assert a["effect_projection_status"] == "unavailable"
    assert a["n_panel_in_effect_universe"] == 0
    assert "panel_below_effect_universe_min" in a["reason_codes"]


def test_no_combined_objective_poles_separate():
    cc = sc.build_contract(**READY)["canonical_content"]
    assert cc["combined_objective"] is None and cc["poles_separate"] is True
    assert "objective" not in cc


def test_modes_and_temporal_ordered():
    w = sc.build_contract(**READY)
    assert w["analysis_mode"] == "within_condition" and w["canonical_content"]["conditions"] == ["Stim48hr"]
    t = sc.build_contract(**TEMPORAL)
    assert t["analysis_mode"] == "temporal_cross_condition" and t["canonical_content"]["conditions"] == ["Stim8hr", "Stim48hr"]
    t_rev = sc.build_contract("treg_like", "high", "th1_like", "high", ["Stim48hr", "Stim8hr"])
    assert t_rev["selection_id"] != t["selection_id"]
    coll = sc.build_contract("treg_like", "high", "th1_like", "high", ["Rest", "Rest"])
    assert coll["analysis_mode"] == "within_condition"


def test_selection_id_citation_invariant_and_full_hash():
    c = sc.build_contract(**READY)
    cc = c["canonical_content"]
    assert cc["registry_scorer_view_sha256"] == rv.build_and_hash()[2]
    assert "primary_registry_v3_raw_sha256" not in cc
    assert c["provenance_bindings"]["primary_registry_v3_raw_sha256"] is not None
    assert c["selection_id"] == hashlib.sha256(canonical.canonical_json(cc).encode()).hexdigest()[:16]
    body = {k: v for k, v in c.items() if k != "full_contract_content_sha256"}
    assert c["full_contract_content_sha256"] == hashlib.sha256(canonical.canonical_json(body).encode()).hexdigest()


def test_exact_trust_and_historical_bindings():
    c = sc.build_contract(**READY)
    tb = c["trust_bindings"]
    def raw(n): return hashlib.sha256(open(os.path.join(DATA, n), "rb").read()).hexdigest()
    assert tb["validation_raw_sha256"] == raw("stage01_validation.json")
    assert tb["validation_semantics_raw_sha256"] == raw("stage01_validation_semantics.json")
    sem = json.load(open(os.path.join(DATA, "stage01_validation_semantics.json")))
    assert tb["constituent_main_content_canonical_sha256"] == sem["constituent_evidence"]["main"]["content_canonical_sha256"]
    md = json.load(open(os.path.join(DATA, "stage01_marker_diagnostics_v2.json")))
    assert tb["marker_diagnostics_content_sha256"] == canonical.canonical_content_sha256(md)
    # frozen selectability bound ONLY as historical provenance, active_gate false, bytes exact
    hp = c["historical_validation_provenance"]
    assert hp["active_gate"] is False
    assert hp["selectability_v3_raw_sha256"] == raw("stage01_selectability_v3.json") == \
        "7c326a86d4586a851f5b91fb6f7e9796946e52eb41fe60123b41a6d3471d2420"
    assert raw("stage01_validation.json") == "1c14cd2884117f03bd26b56ff32d5575d92caa53c5391fa0e7e0ed4f3c815371"


def test_compact_no_prose():
    c = sc.build_contract(**READY)
    ALLOW_SPACES = {"effect_universe_id"}
    bad = []
    def walk(o, path):
        if isinstance(o, dict):
            for k, v in o.items():
                assert "note" not in k.lower(), f"prose field: {path}.{k}"
                walk(v, f"{path}.{k}")
        elif isinstance(o, list):
            for i, v in enumerate(o):
                walk(v, f"{path}[{i}]")
        elif isinstance(o, str):
            if path.rsplit(".", 1)[-1] not in ALLOW_SPACES and (" " in o or o.endswith((".", "!"))):
                bad.append((path, o))
    walk(c, "")
    assert not bad, f"prose-like values: {bad}"


def test_hard_refusals_raise_typed():
    cases = {
        "objective_incompatible_same_pole": dict(a_program_id="treg_like", a_direction="high",
            b_program_id="treg_like", b_direction="high", conditions=["Rest"]),
        "unknown_program": dict(a_program_id="nope", a_direction="high", b_program_id="th1_like",
            b_direction="high", conditions=["Rest"]),
        "unknown_direction": dict(a_program_id="treg_like", a_direction="sideways", b_program_id="th1_like",
            b_direction="high", conditions=["Rest"]),
        "unknown_condition": dict(a_program_id="treg_like", a_direction="high", b_program_id="th1_like",
            b_direction="high", conditions=["Whenever"]),
        "invalid_condition_count": dict(a_program_id="treg_like", a_direction="high", b_program_id="th1_like",
            b_direction="high", conditions=["Rest", "Stim8hr", "Stim48hr"]),
    }
    for reason, kw in cases.items():
        with pytest.raises(SelectionError) as ei:
            sc.build_contract(**kw)
        assert ei.value.reason == reason
    # same program opposite directions is a valid contrast
    assert sc.build_contract("treg_like", "high", "treg_like", "low", ["Rest"])["execution_status"] in ("ready", "refused")


def test_no_selection_served_as_current():
    assert not os.path.exists(os.path.join(DATA, "stage01_selection_demo_treg_th1_stim48hr.json"))
    # the served selection BUNDLE (constants for the browser v3 build) is allowed; it is NOT a materialized
    # selection contract — no served file is an actual spot.stage01_selection.v3 handoff.
    served = [f for f in os.listdir(DATA)
              if f.startswith("stage01_selection") and f != "stage01_selection_bundle.json"]
    assert served == [], served
    bundle = os.path.join(DATA, "stage01_selection_bundle.json")
    if os.path.exists(bundle):
        b = json.load(open(bundle))
        assert b["schema"] == "spot.stage01_selection_bundle.v1"
        assert "selection_id" not in b and "execution_status" not in b   # constants only, not a selection
    if os.path.isdir(sc.FIXTURES):
        for f in os.listdir(sc.FIXTURES):
            if f.endswith(".json"):
                assert json.load(open(os.path.join(sc.FIXTURES, f)))["selection_origin"] == "fixture"
