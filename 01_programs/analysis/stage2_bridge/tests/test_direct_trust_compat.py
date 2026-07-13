"""CP4.4 — isolated compatibility test for the paired Direct trust rule (see DIRECT_TRUST_PATCH.md).

Exercises the corrected `derive_selectable_pairs` logic (rederive_selectability.rederive) on the
Direct-shape rows Direct would load, proving the guarantees Direct must adopt WITHOUT editing the
remote Direct worktree: typed 7-vs-2 lists, constituent-derived null/partial-undefined handling
(never observed_value), duplicate rejection, and the separate 0/33 vs 10/11 verdicts."""
import copy

import pytest

import build_gate_projection as bgp
import rederive_selectability as rs
from rederive_selectability import RederiveError


def _built():
    return bgp.build_all()   # (gate_spec, validation, aggregates, manifest)


def test_typed_seven_vs_two_lists():
    gate_spec, _, _, _ = _built()
    assert len(gate_spec["measurement_hard_gates"]) == 7
    assert len(gate_spec["base_portability_checks"]) == 2
    # portability ids are NOT among the measurement gates
    assert not (set(gate_spec["measurement_hard_gates"]) & set(gate_spec["base_portability_checks"]))


def test_production_selectable_and_portable_are_separate_verdicts():
    gate_spec, validation, _, _ = _built()
    ev = rs.rederive(validation, gate_spec)
    assert ev["n_measurement_valid"] == 0            # 0/33 production measurement-valid
    assert ev["n_base_portable"] == 10               # 10/11 base-portable, separate verdict
    assert "th9_like" not in ev["base_portable_programs"]


def test_partial_undefined_ratios_fail_via_constituents_not_observed_value():
    """The two aggregates whose finite extremum would pass the comparator but that fail on an
    UNDEFINED constituent must be re-derived as failing subchecks (observed_value is never trusted)."""
    gate_spec, validation, _, _ = _built()
    ev = rs.rederive(validation, gate_spec)
    th2 = ev["pair_evidence"]["th2_like|Stim8hr"]
    assert "lomo.median_abs_delta_over_iqr" in th2["failing_subchecks"]
    assert th2["subcheck_pass"]["lomo.median_abs_delta_over_iqr"] is False
    th9 = ev["pair_evidence"]["th9_like|Rest"]
    assert "control_draw.abs_median_delta_over_iqr" in th9["failing_subchecks"]
    assert th9["subcheck_pass"]["control_draw.abs_median_delta_over_iqr"] is False


def test_declared_undefined_null_fails_by_policy_never_relabeled():
    gate_spec, validation, _, _ = _built()
    null_rows = [r for r in validation["measurement_rows"] if r["value"] is None]
    assert null_rows, "expected at least one declared-undefined null measurement row"
    for r in null_rows:
        assert r["measurement_state"] == "undefined" and r["n_undefined"] > 0


def test_last_write_wins_duplicate_refused():
    gate_spec, validation, _, _ = _built()
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


def test_numeric_under_undefined_state_refused():
    gate_spec, validation, _, _ = _built()
    v2 = copy.deepcopy(validation)
    r = next(r for r in v2["measurement_rows"] if r["measurement_state"] == "measured" and r["value"] is not None)
    r["measurement_state"] = "undefined"
    with pytest.raises(RederiveError, match="numeric value is refused"):
        rs.rederive(v2, gate_spec)
