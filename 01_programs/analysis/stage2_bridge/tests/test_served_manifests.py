"""Attack: contradictory served release manifests must be REFUSED, and the retired 0-of-33 production
outcome must be recorded as HISTORICAL (active_gate:false), never as the current deployment state.

The packaging audit found the Stage-1 gate manifest declaring app_deployment_ready=false while the served
deployment manifest declares the app deployed. verify_served_manifests refuses that pair; the frozen
within-condition validation is never a deployment-state input.
"""
import json
import os

import verify_served_manifests as vsm

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
DATA = os.path.join(REPO, "01_programs", "app", "data")
ANALYSIS = os.path.join(REPO, "01_programs", "analysis")
GATE = os.path.join(DATA, "stage01_release_manifest.json")
CURRENT = os.path.join(DATA, "stage01_current.json")
FULLVERIFY = os.path.join(ANALYSIS, "stage01_full_release_verification.json")


def test_real_stage1_gate_declares_deployed_after_readiness_repair():
    # After the authorized readiness repair the gate DERIVES app_deployment_ready + overlay_release_ok
    # from verified served-artifact integrity + overlay==full fidelity (NOT the historical selectability),
    # so both served gate manifests now declare DEPLOYED — and agree with each other.
    assert vsm.declared_deployed(json.load(open(GATE))) is True
    assert vsm.declared_deployed(json.load(open(CURRENT))) is True


def test_deployment_manifest_shape_declares_deployed():
    # the shape of app/release_manifest.json (a `release` id serving built app files)
    deployment = {"release": "spot-8347-same-origin",
                  "files": [{"path": "programs.html", "sha256": "0" * 64, "class": "built"}]}
    assert vsm.declared_deployed(deployment) is True


def test_attack_contradictory_pair_refused():
    # A gate that declares NOT deployed paired with a deployment manifest that declares deployed is a
    # release-state contradiction the verifier refuses — independent of the current real gate value.
    not_deployed_gate = {"release_gates": {"app_deployment_ready": False, "overlay_release_ok": False}}
    deployment = {"release": "spot-8347-same-origin",
                  "files": [{"path": "programs.html", "sha256": "0" * 64, "class": "built"}]}
    reason = vsm.contradictory_served_manifests(not_deployed_gate, deployment)
    assert reason is not None and "contradiction" in reason           # the attack is caught
    ok, reasons = vsm.check_paths(GATE)                                # single manifest -> nothing to contradict
    assert ok


def test_consistent_pair_ok():
    gate = json.load(open(GATE))                                       # now declares DEPLOYED (readiness repair)
    deployment = {"release": "spot-8347-same-origin",
                  "files": [{"path": "programs.html", "sha256": "0" * 64, "class": "built"}]}
    # a deployed gate AGREES with a deployment manifest that serves built app files (promotion unblocked)
    assert vsm.contradictory_served_manifests(gate, deployment) is None
    assert vsm.contradictory_served_manifests(gate, {"release_gates": {"app_deployment_ready": True, "overlay_release_ok": True}}) is None
    # the real served gate manifests (release_manifest + current) agree with each other
    ok, reasons = vsm.check_paths(GATE, CURRENT)
    assert ok, reasons


def test_historical_validation_is_never_a_deployment_input():
    # a manifest that IS deployment-approved but also carries the frozen 0/33 historical validation must NOT
    # be flipped to not-deployed by that historical outcome.
    m = {"release_statuses": {"app_deployment_ready": True, "overlay_release_ok": True},
         "historical_validation_source": {"kind": "frozen_lomo_within_condition_validation_v3", "active_gate": False}}
    assert vsm.declared_deployed(m) is True


def test_full_verification_frames_0of33_as_historical_not_current():
    d = json.load(open(FULLVERIFY))
    scope = d.get("scope_and_limits", {})
    # the obsolete current-state field is gone; the 0/33 outcome is recorded as historical
    assert "production_stage2_ready" not in scope
    hv = scope.get("historical_within_condition_validation", "")
    assert "HISTORICAL" in hv and "0 of 33" in hv and "active_gate:false" in hv
    assert "NOT the current release/deployment state" in hv
    # no lingering claim that 0/33 is a current production result
    assert "0/33 production result" not in json.dumps(scope)
