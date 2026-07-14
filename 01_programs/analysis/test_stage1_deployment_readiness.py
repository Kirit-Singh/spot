#!/usr/bin/env python3
"""Fail-closed tests for the app/overlay deployment-readiness derivation.

Contract (authorized repair): app_deployment_ready is DERIVED from verified served-artifact integrity +
overlay==full fidelity, and is DECOUPLED from the frozen historical within-condition selectability
(0-of-33). These tests prove: a MISSING or HASH-MISMATCHED overlay (or registry/summary) REFUSES; an
unproven recovery receipt REFUSES; a valid served bundle is READY regardless of the historical
selectability outcome (which is not even a parameter). An integration case runs the REAL served bytes.
"""
import inspect
import json
import os

import pytest

import stage1_deployment_readiness as DR

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "app", "data")
EXP = DR.V3_DISPLAY_EXPECTED


def valid_served():
    ov = EXP["stage01_umap_overlay_v3.json"]
    return {
        "stage01_program_registry_v3.json": {"present": True, "raw_sha256": EXP["stage01_program_registry_v3.json"]["raw_sha256"]},
        "stage01_umap_overlay_v3.json": {"present": True, "raw_sha256": ov["raw_sha256"],
                                         "scores_canonical_content_sha256": ov["scores_canonical_content_sha256"],
                                         "coordinates_sha256": ov["coordinates_sha256"]},
        "stage01_summary_v3.json": {"present": True, "raw_sha256": EXP["stage01_summary_v3.json"]["raw_sha256"]},
    }


def valid_receipt():
    return {"all_pass": True, "checks": {
        "overlay_equals_full": {"overlay_eq_full_all_fields": True, "mismatches": 0, "barcodes_all_present": True},
        "scores_canonical_content_sha256": {"match": True}}}


def test_valid_bundle_is_ready():
    r = DR.derive_deployment_readiness(valid_served(), valid_receipt())
    assert r["app_deployment_ready"] is True
    assert r["served_artifact_integrity_ok"] is True
    assert r["overlay_release_fidelity_ok"] is True
    assert r["overlay_release_ok"] is True
    assert r["integrity_reason_codes"] == [] and r["fidelity_reason_codes"] == []


def test_missing_overlay_refuses():
    s = valid_served(); s["stage01_umap_overlay_v3.json"] = {"present": False, "raw_sha256": None}
    r = DR.derive_deployment_readiness(s, valid_receipt())
    assert r["app_deployment_ready"] is False and r["overlay_release_ok"] is False
    assert "overlay_missing" in r["integrity_reason_codes"]


def test_hash_mismatched_overlay_raw_refuses():
    s = valid_served(); s["stage01_umap_overlay_v3.json"]["raw_sha256"] = "0" * 64
    r = DR.derive_deployment_readiness(s, valid_receipt())
    assert r["app_deployment_ready"] is False
    assert "overlay_raw_sha_mismatch" in r["integrity_reason_codes"]


def test_hash_mismatched_overlay_scores_content_refuses():
    s = valid_served(); s["stage01_umap_overlay_v3.json"]["scores_canonical_content_sha256"] = "0" * 64
    r = DR.derive_deployment_readiness(s, valid_receipt())
    assert r["app_deployment_ready"] is False
    assert "overlay_scores_content_sha_mismatch" in r["integrity_reason_codes"]


def test_hash_mismatched_overlay_coordinates_refuses():
    s = valid_served(); s["stage01_umap_overlay_v3.json"]["coordinates_sha256"] = "0" * 64
    r = DR.derive_deployment_readiness(s, valid_receipt())
    assert r["app_deployment_ready"] is False
    assert "overlay_coordinates_sha_mismatch" in r["integrity_reason_codes"]


def test_hash_mismatched_registry_refuses():
    s = valid_served(); s["stage01_program_registry_v3.json"]["raw_sha256"] = "0" * 64
    r = DR.derive_deployment_readiness(s, valid_receipt())
    assert r["app_deployment_ready"] is False
    assert "registry_v3_raw_sha_mismatch" in r["integrity_reason_codes"]


def test_missing_summary_refuses():
    s = valid_served(); s["stage01_summary_v3.json"] = {"present": False, "raw_sha256": None}
    r = DR.derive_deployment_readiness(s, valid_receipt())
    assert r["app_deployment_ready"] is False
    assert "summary_v3_missing" in r["integrity_reason_codes"]


def test_receipt_not_all_pass_refuses():
    rc = valid_receipt(); rc["all_pass"] = False
    r = DR.derive_deployment_readiness(valid_served(), rc)
    assert r["app_deployment_ready"] is False and r["overlay_release_fidelity_ok"] is False
    assert "recovery_receipt_not_all_pass" in r["fidelity_reason_codes"]


def test_overlay_equals_full_unproven_refuses():
    rc = valid_receipt(); rc["checks"]["overlay_equals_full"]["mismatches"] = 3
    r = DR.derive_deployment_readiness(valid_served(), rc)
    assert r["app_deployment_ready"] is False
    assert "overlay_equals_full_unproven" in r["fidelity_reason_codes"]


def test_missing_receipt_refuses():
    r = DR.derive_deployment_readiness(valid_served(), None)
    assert r["app_deployment_ready"] is False and r["overlay_release_fidelity_ok"] is False


def test_selectability_0of33_is_never_an_input():
    # The historical within-condition selectability outcome cannot gate deployment: it is not a parameter,
    # and a valid served bundle is READY irrespective of it (a release with 0 production-selectable pairs
    # still serves its continuous scores + overlay).
    params = set(inspect.signature(DR.derive_deployment_readiness).parameters)
    assert params == {"served", "receipt", "expected"}
    assert not any(t in p for p in params for t in ("select", "n_true", "production", "lomo", "33"))
    assert DR.derive_deployment_readiness(valid_served(), valid_receipt())["app_deployment_ready"] is True


def test_integration_real_served_bundle_is_ready():
    """The ACTUAL served v3 display bundle + the committed recovery receipt derive to ready."""
    import hashlib

    def raw(p):
        return hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.exists(p) else None

    ovl = json.load(open(os.path.join(DATA, "stage01_umap_overlay_v3.json")))
    served = {
        "stage01_program_registry_v3.json": {"present": True, "raw_sha256": raw(os.path.join(DATA, "stage01_program_registry_v3.json"))},
        "stage01_umap_overlay_v3.json": {"present": True, "raw_sha256": raw(os.path.join(DATA, "stage01_umap_overlay_v3.json")),
                                         "scores_canonical_content_sha256": ovl.get("scores_canonical_content_sha256"),
                                         "coordinates_sha256": ovl.get("coordinates_sha256")},
        "stage01_summary_v3.json": {"present": True, "raw_sha256": raw(os.path.join(DATA, "stage01_summary_v3.json"))},
    }
    receipt = json.load(open(os.path.join(HERE, "stage01_v3_recovery_verification.json")))
    r = DR.derive_deployment_readiness(served, receipt)
    assert r["app_deployment_ready"] is True, r


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
