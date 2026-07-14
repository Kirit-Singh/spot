"""Stage-1 <-> Stage-2 temporal estimator IDENTITY gate.

The Stage-1 bridge must bind the EXACT authoritative Stage-2 temporal method identity — re-derived on
tcedirector at spot-stage2-temporal-arms @ 276a9ad via stage1_v3.estimator_registry() ->
temporal.arms.config.method_sha256() (the GENERIC estimand identity: a population-level difference-in-
differences on program projections, no batch/code-tree material). A resealed contract carrying a stale or
forged method identity is REFUSED downstream (mirrors Stage-2's fail-closed admission gate).

Independent: the authoritative identity is RE-STATED here, not imported from the producer registry, so an
emit-side drift from the true Stage-2 registry is caught.
"""
import hashlib

import canonical
import emit_selection_contract as sc
import verify_selection_contract as vc

# stage1_v3.estimator_registry()["temporal_cross_condition_v1"] at spot-stage2-temporal-arms @ 276a9ad
AUTHORITATIVE = {
    "estimator_id": "temporal_cross_condition_v1",
    "analysis_mode": "temporal_cross_condition",
    "method_id": "spot.stage02.temporal_cross_condition.v1",
    "method_version": "stage2-temporal-cross-condition-v1-did-on-program-projections",
    "estimand_id": "spot.stage02.temporal.estimand.population_program_projection_shift.v1",
    "estimand_level": "population",
    "estimand_is_per_cell_fate": False,
    "inference_status": "not_calibrated",
    "method_sha256": "343f20db53aed3f34f45f6c4adebc2cdf26985ab179b7df264dbd0d02587c4b5",
}
STALE = "c05baa8f847f284a6cb187df24668ac0e5197dfdf2d238ced04c7847b7226e77"


def _temporal():
    return sc.build_contract("treg_like", "high", "th1_like", "high", ["Stim8hr", "Stim48hr"])


def _reseal(c):
    """Recompute full_contract_content_sha256 so the STRUCTURAL hash gate passes; only a SEMANTIC gate can
    then catch the forgery."""
    body = {k: v for k, v in c.items() if k != "full_contract_content_sha256"}
    c["full_contract_content_sha256"] = hashlib.sha256(canonical.canonical_json(body).encode()).hexdigest()
    return c


def test_emitted_temporal_estimator_exactly_matches_stage2_registry():
    c = _temporal()
    e = c["estimator"]
    assert c["execution_status"] == "ready" and c["estimator_status"] == "available"
    for k, want in AUTHORITATIVE.items():
        assert e.get(k) == want, f"{k}: {e.get(k)!r} != authoritative {want!r}"
    assert e["method_sha256"] == "343f20db53aed3f34f45f6c4adebc2cdf26985ab179b7df264dbd0d02587c4b5"
    assert e["method_sha256"] != STALE            # the stale c05baa8f is gone
    ok, r = vc.verify_contract(c)
    assert ok, r


def test_resealed_stale_method_sha256_refused_downstream():
    c = _temporal()
    c["estimator"]["method_sha256"] = STALE       # the retired hash, resealed so section-1 hash gate passes
    _reseal(c)
    ok, r = vc.verify_contract(c)
    assert not ok, "a resealed stale/forged method_sha256 must be refused"
    assert not any("full_contract_content_sha256 does not rederive" in x for x in r), r
    assert any("temporal estimator identity mismatch" in x and "method_sha256" in x for x in r), r


def test_resealed_drifted_identity_field_refused():
    c = _temporal()
    c["estimator"]["method_version"] = "stage2-temporal-cross-condition-v0-OLD"
    _reseal(c)
    ok, r = vc.verify_contract(c)
    assert not ok and any("temporal estimator identity mismatch" in x and "method_version" in x for x in r), r


def test_same_program_same_direction_different_times_is_valid_temporal():
    c = sc.build_contract("th1_like", "high", "th1_like", "high", ["Stim8hr", "Stim48hr"])
    assert c["analysis_mode"] == "temporal_cross_condition" and c["execution_status"] == "ready"
    assert c["estimator"]["method_sha256"] == AUTHORITATIVE["method_sha256"]
    # two INDEPENDENT arms (opposite desired_change by role), distinct temporal keys
    assert c["arms"]["away_from_A"]["desired_change"] == "decrease"
    assert c["arms"]["toward_B"]["desired_change"] == "increase"
    ok, r = vc.verify_contract(c)
    assert ok, r


def test_identical_full_endpoints_refused():
    # identical (program, pole, condition) for both A and B -> objective_incompatible_same_pole
    try:
        sc.build_contract("th1_like", "high", "th1_like", "high", ["Stim48hr"])
        assert False, "identical full endpoints must be refused"
    except sc.SelectionError as ex:
        assert ex.reason == "objective_incompatible_same_pole"
