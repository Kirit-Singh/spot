"""CP3b tests — the TYPED constituent derivation reproduces the frozen T7b/T8 evidence
exactly (per-subcheck pass, per-pair failing set, 0/33 measurement-valid, 10/11 portable),
preserves the 8 wholly-null + 2 partially-undefined budget with NO numeric sentinel, and
refuses last-write-wins duplicates, an inexact universe, and every null-relabel attack.

These are the strengthened successors of the two previously-red tests: they now require
EXACT per-subcheck/per-pair evidence equivalence (not merely the 0/33 total)."""
import copy
import json
import os

import pytest

import build_gate_projection as bgp
import constituents as C
import rederive_selectability as rs
from rederive_selectability import RederiveError

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROGRAMS = os.path.dirname(os.path.dirname(HERE))
DATA = os.path.join(PROGRAMS, "app", "data")
STAGING = os.path.join(HERE, "_release_staging")
MIRROR = os.path.join(STAGING, "stage01_gate_constituents_v1.json.gz")

pytestmark = pytest.mark.skipif(
    not os.path.exists(MIRROR),
    reason="constituent evidence not staged (run gen_gate_constituents.py on tcefold + pull to _release_staging)")

# our subcheck_id -> frozen (gate_id, metric)
SUBCHECK_TO_FROZEN = {
    "coverage.n_panel_genes_used": ("global_coverage", "n_panel_genes_used"),
    "condition_measurability.panel_score_iqr": ("condition_measurability", "panel_score_iqr"),
    "condition_measurability.n_panel_genes_detected_ge_1pct_cells":
        ("condition_measurability", "n_panel_genes_detected_ge_1pct_cells"),
    "lomo.spearman_rho_full_minus_gene":
        ("lomo_panel_robustness", "spearman_rho(panel_mean_full, panel_mean_minus_gene)"),
    "lomo.median_abs_delta_over_iqr":
        ("lomo_panel_robustness", "median(abs(delta_panel))/iqr(panel_mean_full)"),
    "control_draw.spearman_rho_primary_alt":
        ("control_draw_sensitivity", "spearman_rho(score_primary, score_alt_seed)"),
    "control_draw.abs_median_delta_over_iqr":
        ("control_draw_sensitivity", "abs(median_alt - median_primary)/iqr_primary"),
    "base_portability.n_panel_in_effect_universe":
        ("stage2_base_portability", "n_panel_in_effect_universe"),
    "base_portability.n_control_in_effect_universe":
        ("stage2_base_portability", "n_control_in_effect_universe"),
}


@pytest.fixture(scope="module")
def built():
    return bgp.build_all()          # (gate_spec, validation, aggregates, manifest)


@pytest.fixture(scope="module")
def frozen_validation():
    return json.load(open(os.path.join(DATA, "stage01_validation.json")))


@pytest.fixture(scope="module")
def frozen_selectability():
    return json.load(open(os.path.join(DATA, "stage01_selectability_v3.json")))


def _frozen_results_index(fv):
    return {(r["gate_id"], r["metric"], r["stratum_instance"]): r for r in fv["results"]}


def test_typed_shape(built):
    gate_spec, validation, aggregates, _ = built
    assert gate_spec["measurement_hard_gates"] == list(C.MEASUREMENT_SUBCHECKS)
    assert len(gate_spec["measurement_hard_gates"]) == 7
    assert len(gate_spec["base_portability_checks"]) == 2
    assert validation["n_measurement_rows"] == 11 * 3 * 7        # 231
    assert validation["n_portability_rows"] == 22


def test_regression_budget_8_wholly_null_plus_2_partial(built):
    """Derived from constituents (not program names): exactly 8 wholly-null LOMO aggregates
    + exactly 2 partially-defined aggregates with hidden undefined constituents = 10 null rows."""
    _, _, aggregates, _ = built
    measurement = {k: a for k, a in aggregates.items() if a["gate_class"] == "measurement_validity"}
    undefined_aggs = {k: a for k, a in measurement.items() if a["n_undefined"] > 0}
    wholly = {k: a for k, a in undefined_aggs.items() if a["n_defined"] == 0}
    partial = {k: a for k, a in undefined_aggs.items() if a["n_defined"] > 0}
    assert len(wholly) == 8, sorted(wholly)
    assert all("lomo" in k[2] for k in wholly)
    assert len(partial) == 2, sorted(partial)
    assert {(k[0], k[1], k[2]) for k in partial} == {
        ("th2_like", "Stim8hr", "lomo.median_abs_delta_over_iqr"),
        ("th9_like", "Rest", "control_draw.abs_median_delta_over_iqr")}


def test_zero_numerator_rows_remain_defined(built):
    """Valid zero-numerator production rows (positive denominator) stay DEFINED, not undefined:
    Tfh LOMO ratio 8h/48h and Th9 control-draw ratio 8h/48h (value 0.0, n_undefined 0)."""
    _, _, aggregates, _ = built
    for pid, cond, sid in [
        ("tfh_like", "Stim8hr", "lomo.median_abs_delta_over_iqr"),
        ("tfh_like", "Stim48hr", "lomo.median_abs_delta_over_iqr"),
        ("th9_like", "Stim8hr", "control_draw.abs_median_delta_over_iqr"),
        ("th9_like", "Stim48hr", "control_draw.abs_median_delta_over_iqr"),
    ]:
        a = aggregates[(pid, cond, sid)]
        assert a["n_undefined"] == 0, (pid, cond, sid, a["n_undefined"])
        assert a["measurement_state"] == "measured"
        assert a["worst_defined_value"] == 0.0
        assert a["subcheck_pass"] is True


def test_per_subcheck_pass_and_worst_equal_frozen(built, frozen_validation):
    """STRENGTHENED successor of the old comparator-on-observed test: every derived
    subcheck_pass equals the frozen per-check `pass`, and worst_defined_value equals the
    frozen `observed_value` — for the DEFINED extremum AND the mixed/undefined rows."""
    _, _, aggregates, _ = built
    ridx = _frozen_results_index(frozen_validation)
    for (pid, cond, sid), a in aggregates.items():
        gate_id, metric = SUBCHECK_TO_FROZEN[sid]
        stratum = pid if cond is None else f"{pid}|{cond}"
        fr = ridx[(gate_id, metric, stratum)]
        assert a["subcheck_pass"] == fr["pass"], (sid, pid, cond, a["subcheck_pass"], fr["pass"])
        assert a["worst_defined_value"] == fr["observed_value"], (sid, pid, cond)


def test_measurement_valid_0_of_33_and_portable_10_of_11(built):
    gate_spec, validation, _, _ = built
    ev = rs.rederive(validation, gate_spec)
    assert ev["n_pairs_evaluated"] == 33
    assert ev["n_measurement_valid"] == 0
    assert ev["n_base_portable"] == 10
    assert "th9_like" not in ev["base_portable_programs"]
    assert len(ev["base_portable_programs"]) == 10


def test_per_pair_failing_set_matches_frozen_measurement_gates(built, frozen_selectability):
    """STRENGTHENED successor of the old per-pair test: derived failing measurement
    subchecks equal the frozen T8 failing gates EXCLUDING base_portability (portability is
    a separate Stage-2 verdict, never a Stage-1 measurement failure)."""
    gate_spec, validation, _, _ = built
    ev = rs.rederive(validation, gate_spec)
    frozen = {}
    for rec in frozen_selectability["records"]:
        key = f"{rec['program_id']}|{rec['condition']}"
        frozen[key] = {(g["gate_id"], g["metric"]) for g in rec["failed_or_undefined_hard_gates"]
                       if g["gate_id"] != "stage2_base_portability"}
    assert set(ev["pair_evidence"]) == set(frozen)
    for pair, info in ev["pair_evidence"].items():
        derived = {SUBCHECK_TO_FROZEN[s] for s in info["failing_subchecks"]}
        assert derived == frozen[pair], f"{pair}: derived {derived} != frozen {frozen[pair]}"


def test_no_synthetic_numeric_sentinels(built):
    """Every measurement row is null (undefined) or an exact worst_defined_value; nothing invented."""
    _, validation, _, _ = built
    for r in validation["measurement_rows"]:
        if r["measurement_state"] == "undefined":
            assert r["value"] is None and r["n_undefined"] > 0
        else:
            assert r["value"] == r["source_worst_defined_value"] and r["n_undefined"] == 0


# ── attacks ──────────────────────────────────────────────────────────────────────────

def test_attack_last_write_wins_duplicate_refused(built):
    """The saved diff_memory|Rest last-write-wins mutation must be refused, not silently won."""
    gate_spec, validation, _, _ = built
    v2 = copy.deepcopy(validation)
    victim = next(r for r in v2["measurement_rows"]
                  if r["program_id"] == "diff_memory" and r["condition"] == "Rest"
                  and r["gate_id"] == "lomo.median_abs_delta_over_iqr")
    forged = copy.deepcopy(victim)
    forged.update({"value": 0.0, "measurement_state": "measured", "n_undefined": 0,
                   "n_defined": forged["n_expected"], "n_present": forged["n_expected"]})
    v2["measurement_rows"].append(forged)
    with pytest.raises(RederiveError, match="duplicate measurement row"):
        rs.rederive(v2, gate_spec)


def test_attack_missing_row_inexact_universe_refused(built):
    gate_spec, validation, _, _ = built
    v2 = copy.deepcopy(validation)
    v2["measurement_rows"] = [r for r in v2["measurement_rows"]
                              if not (r["program_id"] == "treg_like" and r["condition"] == "Stim48hr"
                                      and r["gate_id"] == "control_draw.spearman_rho_primary_alt")]
    with pytest.raises(RederiveError, match="universe mismatch"):
        rs.rederive(v2, gate_spec)


def test_attack_unknown_program_refused(built):
    gate_spec, validation, _, _ = built
    v2 = copy.deepcopy(validation)
    v2["measurement_rows"][0] = {**v2["measurement_rows"][0], "program_id": "evil_program"}
    with pytest.raises(RederiveError, match="unknown program_id"):
        rs.rederive(v2, gate_spec)


def test_attack_null_relabeled_measured_refused(built):
    gate_spec, validation, _, _ = built
    v2 = copy.deepcopy(validation)
    r = next(r for r in v2["measurement_rows"] if r["value"] is None)
    r["measurement_state"] = "measured"        # try to relabel an undefined null as measured
    with pytest.raises(RederiveError, match="null value without measurement_state=='undefined'"):
        rs.rederive(v2, gate_spec)


def test_attack_numeric_under_undefined_refused(built):
    gate_spec, validation, _, _ = built
    v2 = copy.deepcopy(validation)
    r = next(r for r in v2["measurement_rows"] if r["measurement_state"] == "measured" and r["value"] is not None)
    r["measurement_state"] = "undefined"       # numeric value under an undefined state
    with pytest.raises(RederiveError, match="numeric value is refused"):
        rs.rederive(v2, gate_spec)


def test_attack_duplicate_constituent_key_refused(built):
    _, _, _, _ = built
    rows, man = C.load_constituents(MIRROR, os.path.join(STAGING, "stage01_gate_constituents_v1.manifest.json"))
    n_markers = C.load_registry_markers()
    dup = copy.deepcopy(rows) + [copy.deepcopy(rows[100])]
    with pytest.raises(C.ConstituentError, match="duplicate constituent key"):
        C.aggregate(dup, n_markers)
