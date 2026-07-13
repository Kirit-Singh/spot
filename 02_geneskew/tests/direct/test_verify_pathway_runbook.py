"""The runbook invokes W4's independent verifier on the shipped bytes (verify-pathway target).

generator != verifier: verification is a SEPARATE gate, not part of the producer `all` flow, so
it does not disturb the 15-bundle producer invocation matrix W18's tests pin.
"""
from __future__ import annotations

import os
import subprocess

import pytest

SCRIPT = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "analysis", "run_stage2.sh")

ENV = {"SEL_DIR": "/x", "V3_SCHEMA": "/x", "REGISTRY": "/x", "STAGE1_RELEASE": "/x",
       "DE": "/de.h5ad", "GUIDE": "/x", "DONOR": "/x", "SGRNA": "/x", "MANIFEST": "/x",
       "SRCREG": "/x", "PB": "/x", "ENV_LOCK": "/x", "OUT": "/out",
       "W10_REPORT_DIR": "/w10", "SPOT_DRY_RUN": "1"}


def _dry(target):
    return subprocess.run(["bash", SCRIPT, target], env={**os.environ, **ENV},
                          capture_output=True, text=True)


def _invocations(out):
    labels = []
    for line in out.splitlines():
        if line.startswith("=== BEGIN "):
            labels.append(line[len("=== BEGIN "):])
    return labels


class TestTheRunbookInvokesTheVerifier:
    def test_bash_n_accepts_the_script(self):
        assert subprocess.run(["bash", "-n", SCRIPT]).returncode == 0

    def test_verify_pathway_is_three_conditions_times_two_sources(self):
        labels = _invocations(_dry("verify-pathway").stdout)
        assert len(labels) == 6
        assert all(x.startswith("verify-pathway:") for x in labels)

    def test_each_verify_step_invokes_the_INDEPENDENT_verifier_on_a_shipped_bundle(self):
        out = _dry("verify-pathway").stdout
        assert out.count("analysis.direct.verify_signature_matrix") == 6
        # it consumes the shipped pathway bundle + the shared signatures, and reads the env
        # lock from provenance (it is NOT passed on the command line — that would be trusting
        # the caller instead of the shipped bytes)
        assert "=== CONSUMES pathway:Rest:reactome" in out
        assert "--env-lock" not in out.split("verify-pathway:Rest:reactome")[1].split("END")[0]

    def test_verification_is_NOT_part_of_the_producer_all_flow(self):
        # generator != verifier: `all` stays the 15 producer bundles + 3 Step-0 artifacts.
        labels = _invocations(_dry("all").stdout)
        assert not any(x.startswith("verify-pathway:") for x in labels)


class TestTheRunbookInvokesTheReleaseVerifier:
    def test_verify_release_is_a_single_aggregate_invocation_over_all_six_bundles(self):
        out = _dry("verify-release").stdout
        labels = _invocations(out)
        assert labels == ["verify-release"]                 # ONE aggregate gate, not per-cell
        assert out.count("analysis.direct.verify_pathway_release") == 1
        # --bundle appears 6 times as a flag; --bundle-report also 6 — count the exact flags
        assert len([ln for ln in out.splitlines() if ln == "--bundle"]) == 6
        assert len([ln for ln in out.splitlines() if ln == "--bundle-report"]) == 6

    def test_verify_release_anchors_the_universe_to_the_authoritative_stage1_release(self):
        out = _dry("verify-release").stdout
        assert "--release" in out.splitlines()               # the Stage-1 v3 release universe

    def test_verify_release_consumes_the_independent_per_bundle_reports_not_producer_bytes(self):
        out = _dry("verify-release").stdout
        # every cell's INDEPENDENT verify-pathway report is consumed (never pathway_verification)
        assert "=== CONSUMES verify-pathway:Rest:reactome" in out
        assert "pathway_verification.json" not in out
        assert out.count("/verification/pathway_") >= 6      # the six report paths

    def test_verify_release_requires_the_pending_producer_inventory(self):
        out = _dry("verify-release").stdout
        assert "pathway_arm_release.json" in out             # the PENDING producer inventory
        assert "--inventory" in out
        assert "pathway_arm_external_admission.json" in out  # the lane-specific envelope it emits
        assert "=== CONSUMES pathway-release-inventory" in out

    def test_the_release_gate_is_NOT_part_of_the_producer_all_flow(self):
        labels = _invocations(_dry("all").stdout)
        assert not any(x == "verify-release" for x in labels)


@pytest.mark.skipif(not os.path.exists(SCRIPT), reason="runbook not present")
def test_the_verifier_module_is_the_one_the_runbook_names():
    from direct import verify_pathway_release, verify_signature_matrix
    assert hasattr(verify_signature_matrix, "main")
    assert hasattr(verify_pathway_release, "main")
