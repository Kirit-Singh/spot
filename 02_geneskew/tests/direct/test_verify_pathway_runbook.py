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


@pytest.mark.skipif(not os.path.exists(SCRIPT), reason="runbook not present")
def test_the_verifier_module_is_the_one_the_runbook_names():
    from direct import verify_signature_matrix
    assert hasattr(verify_signature_matrix, "main")
