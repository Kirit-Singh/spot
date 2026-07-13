"""The end-to-end cross-worktree proof: the CURRENT frozen Stage-3 bundle enters Stage 4.

The committed annotation fixture is a real current-engine emission, so the gate-1 tests
already run against the true shape. This test closes the remaining gap the external re-audit
found: it drives the CURRENT frozen Stage-3 engine (03_druglink @ e5aa666) to BUILD a fresh
bundle + acquisition cache + verified Direct run, then admits that same bundle through Stage 4
with BOTH gates — including Stage-3's own `verifier.verify_stage3`.

    admit(bundle, require_external_verifier=True)  ->  external_verifier == passed

633 green tests that never fed a real frozen-Stage-3 bundle through the door were how the
stale-fixture drift hid. This is the test that would have caught it, and the one that catches
the next drift: it binds nothing by hash, it rebuilds from the live engine every run.

The build runs in a SUBPROCESS (`_build_real_stage3_bundle.py`) so the Stage-3
`druglink`/`verifier` packages never enter this interpreter, where a `verifier` of the same
name already lives.

Skips ONLY when no Stage-3 checkout is reachable (`SPOT_STAGE3_ROOT` unset) — the same rule
as the pin tests. A configured Stage 3 that FAILS to build for a Stage-3/Stage-4 reason FAILS
the test. The one honest exception is an UPSTREAM Stage-2 PRECONDITION — the Direct worktree
being dirty (a sibling lane mid-edit, so Direct refuses a release-grade run), or the known
Direct-verifier defect: that skips with its exact reason, because it is a Stage-2 state, not a
Stage-4 contract failure, and gate-1 admission of the real current shape is proven on every
run by the committed fixture regardless.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from analysis.firewall import Rejection
from analysis.method_config import STAGE4_DIR
from analysis.stage3_admission import (
    ENV_CACHE_ROOT,
    ENV_DIRECT_ANALYSIS,
    ENV_DIRECT_INPUTS,
    ENV_DIRECT_RUN,
    ENV_VERIFIER_ROOT,
    PASSED,
    admit,
)

BUILDER = os.path.join(STAGE4_DIR, "tests", "_build_real_stage3_bundle.py")
UPSTREAM_EXIT = 3
BUILD_TIMEOUT_S = 900


def _stage2_now_dirty(roots: dict) -> bool:
    """Is the Stage-2 Direct worktree dirty RIGHT NOW? A sibling lane editing it between the
    build and gate-2 re-verify is an upstream race, not a Stage-4 contract failure."""
    wt = roots.get("stage2_wt")
    if not wt:
        return False
    out = subprocess.run(["git", "-C", wt, "status", "--porcelain"],
                         capture_output=True, text=True, check=False)
    return out.returncode == 0 and bool(out.stdout.strip())


def _stage3_root() -> str | None:
    """A Stage-3 checkout carrying the frozen engine + verifier, or None.

    Configured-but-broken is a FAILURE, never a skip: an explicit root that cannot host the
    build is exactly the cross-lane NO-GO this test exists to surface.
    """
    root = os.environ.get("SPOT_STAGE3_ROOT")
    if not root:
        return None
    if not (os.path.isdir(os.path.join(root, "analysis", "druglink"))
            and os.path.isdir(os.path.join(root, "verifier"))):
        pytest.fail(
            f"SPOT_STAGE3_ROOT={root!r} is set but has no analysis/druglink + verifier/. An "
            "explicitly configured Stage-3 root that cannot build is a FAILURE, not a skip.")
    return root


def test_a_current_frozen_stage3_bundle_is_admitted_end_to_end(tmp_path, monkeypatch):
    root = _stage3_root()
    if root is None:
        pytest.skip("no SPOT_STAGE3_ROOT; the committed real fixture still exercises gate 1")

    dest = str(tmp_path / "realrun")
    # A clean PYTHONPATH of ONLY the Stage-3 roots: the builder imports Stage-3's
    # `druglink`/`verifier`, which must not be shadowed by Stage-4's like-named packages.
    env = dict(os.environ,
               PYTHONPATH=os.pathsep.join(
                   [root, os.path.join(root, "analysis"), os.path.join(root, "tests")]))
    proc = subprocess.run([sys.executable, BUILDER, root, dest], env=env,
                          capture_output=True, text=True, timeout=BUILD_TIMEOUT_S, check=False)

    if proc.returncode == UPSTREAM_EXIT:
        # A Stage-2 PRECONDITION not met (a dirty Direct worktree mid-edit, or the known
        # Direct-verifier defect) — not a Stage-3/Stage-4 contract break. Gate-1 admission of
        # the real current shape is proven on every run by the committed fixture regardless.
        pytest.skip("UPSTREAM Stage-2 precondition: " + proc.stdout.strip())
    assert proc.returncode == 0, (
        "building a bundle from the current frozen Stage-3 engine FAILED — that is a real "
        f"cross-stage break, not a skip.\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}")

    with open(os.path.join(dest, "roots.json"), encoding="utf-8") as fh:
        roots = json.load(fh)
    assert roots["n_verifier_checks"] >= 30, "Stage-3's own verifier must actually check things"

    # Point Stage 4's gate 2 at the freshly-built Stage-3 context and admit end-to-end.
    monkeypatch.setenv(ENV_VERIFIER_ROOT, root)
    monkeypatch.setenv(ENV_CACHE_ROOT, roots["cache"])
    monkeypatch.setenv(ENV_DIRECT_RUN, roots["direct_run"])
    monkeypatch.setenv(ENV_DIRECT_INPUTS, roots["direct_inputs"])
    monkeypatch.setenv(ENV_DIRECT_ANALYSIS, roots["direct_analysis"])

    try:
        admission = admit(roots["bundle"], require_external_verifier=True)
    except Rejection as exc:
        # gate 2 re-runs Direct's verifier over the Stage-2 tree. If a sibling lane edited that
        # tree BETWEEN the build and this re-verify, the code identity no longer reproduces —
        # an upstream race, not a Stage-4 defect. Only skip if the tree is genuinely dirty now;
        # a clean-tree refusal is real and must fail.
        if exc.code == "stage3_external_verifier_refused" and _stage2_now_dirty(roots):
            pytest.skip("UPSTREAM Stage-2 precondition: the Direct worktree was edited between "
                        "the build and gate-2 re-verify, so the code identity no longer "
                        f"reproduces. {exc}")
        raise

    assert admission.external_verifier == PASSED
    assert admission.gates == ("stage4_restatement", "verifier.verify_stage3")
    assert admission.data_bound_integration_ready is True
    assert admission.document["schema_version"] == "spot.stage03_drug_annotation.v1"
    assert admission.document["artifact_class"] == "analysis"
    # the current shape really flowed through: the disease-context review carried, per candidate
    assert admission.document["candidates"], "a real analysis bundle has candidates"
    for cand in admission.document["candidates"]:
        assert "disease_context_review_status" in cand
        assert "claude_science_review_status" not in cand, "the retired r5 flag is gone"


def test_the_builder_never_lets_a_stage3_build_failure_masquerade_as_a_skip():
    """The guard on the guard: every skip is an UPSTREAM Stage-2 precondition or a missing
    checkout. A real Stage-3/Stage-4 break must FAIL, never skip.

    Exactly THREE skips are allowed, and only these three:
      1. no Stage-3 checkout reachable (`SPOT_STAGE3_ROOT` unset);
      2. the build returns UPSTREAM_EXIT (Stage-2 tree dirty, or Direct-verifier defect);
      3. gate 2 refuses AND the Stage-2 tree is dirty NOW (a mid-test edit race).
    A bare `returncode != 0` skip, or a gate-2 refusal skip that did NOT re-check dirtiness,
    would be a NO-GO wearing a pass's clothes.
    """
    with open(__file__, encoding="utf-8") as fh:
        source = fh.read()
    marker = "pytest" + ".skip("  # split literal so this check does not count itself
    assert source.count(marker) == 3, (
        "exactly three skips are allowed here — no-checkout, build-time UPSTREAM (exit 3), and "
        "the gate-2 mid-test dirty-tree race. A fourth skip risks hiding a real failure.")
    # a failed build that is NOT upstream still asserts, and gate-2's skip is gated on dirtiness
    assert "returncode == 0, (" in source, "a failed build must be an assertion, not a skip."
    assert "returncode == UPSTREAM_EXIT" in source
    assert "_stage2_now_dirty(roots)" in source, (
        "the gate-2 refusal skip MUST re-check the Stage-2 tree is genuinely dirty; an "
        "unconditional skip there would hide a real verifier refusal.")
