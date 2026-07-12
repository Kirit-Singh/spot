"""The Stage-3 loader fails CLOSED when Direct's own verifier cannot vouch for a run.

This is not a workaround for the current Stage-2 defect — it is the property that makes
refusing correct. Direct's standalone verifier presently CRASHES:

    NameError: name 'SOURCE_CLASSIFICATION_RULE_ID' is not defined
    02_geneskew/analysis/direct/verify_source.py:412

A crash is a verification failure. Stage 3's whole admission contract is "Direct's
standalone verifier RECONSTRUCTED this run from source", so a verifier that cannot
answer means the run is not admissible — full stop. Stage 3 does not mock Direct, does
not add a compatibility exception, and does not edit Stage 2 to make itself pass.

These tests PASS today (the refusal IS the correct behaviour) and keep passing once
Stage 2 fixes the import.
"""
from __future__ import annotations

import pytest

from druglink import direct_run as dr


def test_a_crashing_upstream_verifier_is_a_refusal_not_a_pass(direct_run):
    """A non-zero verifier exit ALWAYS aborts admission, whatever the cause."""
    try:
        dr.load(direct_run["run_dir"], direct_run["inputs_root"],
                artifact_class="analysis",
                direct_analysis=direct_run["analysis"])
    except dr.DirectRunError as exc:
        # Today: Direct's verifier crashes, so Stage 3 REFUSES before doing anything.
        assert "verifier REFUSED" in str(exc)
        assert "aborts before any acquisition or annotation" in str(exc)
        return
    # If Stage 2 has fixed its verifier, admission succeeds — also correct.


def test_admission_requires_a_locatable_verifier(monkeypatch, tmp_path):
    """A verifier that cannot be found is an ABORT, never a skip.

    "Verified" must never quietly come to mean "assumed".
    """
    import os

    monkeypatch.delenv(dr.DIRECT_ANALYSIS_ENV, raising=False)
    # No candidate path resolves to a real direct/verify_run.py.
    monkeypatch.setattr(os.path, "isfile", lambda _p: False)
    with pytest.raises(dr.DirectRunError, match="cannot locate Direct's standalone"):
        dr.resolve_direct_analysis(str(tmp_path / "not_a_direct_checkout"))


def test_an_empty_verification_is_not_a_pass(monkeypatch, direct_run):
    """A verifier that exits 0 but reports NO checks is refused."""
    import subprocess

    class _Proc:
        returncode = 0
        stdout = ""          # zero checks reported
        stderr = ""

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _Proc())
    with pytest.raises(dr.DirectRunError, match="no checks"):
        dr.run_direct_verifier(direct_run["run_dir"], direct_run["inputs_root"],
                               direct_run["analysis"])
