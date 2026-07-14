"""The literal Stage-2 -> Stage-3-v2 -> Stage-4 chain, against a REAL bundle.

This test cannot pass yet, and that is the finding — not a gap in the test.

Stage 3's v2 path is deliberately non-producing: its own gate is red, and it refuses to write a
bundle while there is no admitted Stage-2 arm bundle to stand on. `run_stage3`'s v2 CLI exposes
only `--universe-store`, `--artifact-class` and `--output-root`; it accepts no arm bundles and
invokes no candidate generation. So there is no real v2 bundle in existence for Stage 4 to admit.

W16 must first consume an ACTUAL Stage-2 `run_release` aggregate — not an invented aggregate
envelope. A Stage-3 bundle standing on a synthetic Stage-2 shape carries synthetic numbers into
Stage 4 under a real bundle's name, and every hash downstream would be a self-consistent hash of a
fiction. That is precisely the failure that a green test suite cannot see.

So this file is the harness, armed and waiting. Drop a real, externally admitted v2 bundle at
`$SPOT_STAGE3_V2_BUNDLE` and it runs the whole chain for real:

    run_acquire -> run_materialize -> verify_bundle -> run_stage4 -> verify_stage4

Until then it SKIPS, loudly, naming exactly what is missing. A skip is not a pass, and this suite
says so rather than reporting green on a chain nobody has run.

**The moment W16's bytes land these tests are REQUIRED, not optional.** Set `SPOT_STAGE3_V2_BUNDLE`
and they must pass — a real chain that has never been run end to end is not a chain anyone should
trust, and "we could run it" is not "we ran it".
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from analysis.stage3_v2_seam import (
    STAGE3_V2_SCHEMA_SET_SHA256,
    STAGE3_V2_VERIFIER_ENTRY,
    is_v2_bundle,
)

STAGE4 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
METHOD_DIR = os.path.join(STAGE4, "method")

V2_BUNDLE = os.environ.get("SPOT_STAGE3_V2_BUNDLE", "")

needs_real_v2 = pytest.mark.skipif(
    not (V2_BUNDLE and os.path.isdir(V2_BUNDLE)),
    reason=(
        "no real Stage-3 v2 bundle. Stage 3's v2 path is fail-closed and emits nothing until it "
        "consumes an ACTUAL Stage-2 run_release aggregate (not an invented envelope). Set "
        "SPOT_STAGE3_V2_BUNDLE to an externally admitted spot.stage03_drug_annotation.v2 bundle "
        "and this chain runs for real. A fixture-only v1 green is not completion."
    ),
)


def _run(module: str, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([STAGE4, os.path.join(STAGE4, "tests"),
                                         env.get("PYTHONPATH", "")])
    return subprocess.run([sys.executable, "-m", module, *args],
                          capture_output=True, text=True, cwd=STAGE4, env=env, check=False)


# ------------------------------------------------------------- the hold, stated as an assertion

def test_stage4_is_NOT_pinned_to_v2_and_says_so():
    """The hold. Neither the schema set nor the v2 verifier is pinned, so no v2 bundle can be
    admitted — by construction, not by luck. If either of these is set, someone pinned a contract,
    and that is only legitimate after W16 PUBLISHED it."""
    assert STAGE3_V2_SCHEMA_SET_SHA256 is None
    assert STAGE3_V2_VERIFIER_ENTRY is None


# ------------------------------------------------------- and the chain, the moment it can run

@needs_real_v2
def test_the_real_v2_bundle_DECLARES_v2_and_stage4_recognises_it():
    """The seam must SEE it — whatever W16 named the document. This is the check that would have
    failed silently when the seam scanned only v1's filenames."""
    assert is_v2_bundle(V2_BUNDLE), (
        f"{V2_BUNDLE} does not declare spot.stage03_drug_annotation.v2 in any document. Stage 4 "
        "discovers a contract by DECLARATION, never by filename.")


@needs_real_v2
def test_the_LITERAL_chain_runs_against_the_real_v2_bundle(tmp_path):
    """acquire -> materialize -> verify_bundle -> run_stage4 -> verify_stage4, on real bytes.

    Every link is a real CLI in a real subprocess. This is the only thing that counts as an
    end-to-end Stage-2 -> Stage-3-v2 -> Stage-4 result, and it is what a fixture-only green does
    not give you.
    """
    run_root = str(tmp_path / "runroot")
    bundle = str(tmp_path / "evidence.json")
    outputs = str(tmp_path / "outputs")

    acquire = _run("analysis.run_acquire",
                   "--stage3-annotation-bundle", V2_BUNDLE, "--run-root", run_root)
    assert acquire.returncode == 0, acquire.stderr[-2000:]

    materialize = _run("analysis.run_materialize",
                       "--stage3-annotation-bundle", V2_BUNDLE, "--run-root", run_root,
                       "--out", bundle)
    assert materialize.returncode == 0, materialize.stderr[-2000:]

    verify_b = _run("verifier.verify_bundle", bundle, "--run-root", run_root)
    assert verify_b.returncode == 0, verify_b.stdout[-2000:]

    # gate 2 is MANDATORY on a real run: Stage 3's own verifier must actually have passed.
    stage4 = _run("analysis.run_stage4",
                  "--stage3-annotation-bundle", V2_BUNDLE, "--evidence-bundle", bundle,
                  "--outputs-root", outputs, "--require-external-verifier")
    assert stage4.returncode == 0, stage4.stderr[-2000:]

    releases = [p for p in (tmp_path / "outputs").rglob("manifest.json")]
    assert len(releases) == 1, f"expected one release, got {releases}"

    verify_s4 = _run("verifier.verify_stage4", "--release", str(releases[0].parent),
                     "--method", METHOD_DIR)
    assert verify_s4.returncode == 0, verify_s4.stdout[-2500:]


@needs_real_v2
def test_the_real_v2_release_claims_nothing_it_did_not_measure(tmp_path):
    """And when it does run: a public acquisition supplies no brain exposure, so the release
    classifies nothing. That remains true on real data — the chain running is not a licence to
    conclude."""
    import pyarrow.parquet as pq

    run_root = str(tmp_path / "rr")
    bundle = str(tmp_path / "e.json")
    outputs = str(tmp_path / "out")

    _run("analysis.run_acquire", "--stage3-annotation-bundle", V2_BUNDLE, "--run-root", run_root)
    _run("analysis.run_materialize", "--stage3-annotation-bundle", V2_BUNDLE,
         "--run-root", run_root, "--out", bundle)
    _run("analysis.run_stage4", "--stage3-annotation-bundle", V2_BUNDLE,
         "--evidence-bundle", bundle, "--outputs-root", outputs)

    release = next((tmp_path / "outputs").rglob("manifest.json")).parent
    for d in pq.read_table(str(release / "nebpi_decisions.parquet")).to_pylist():
        assert d.get("nebpi_class") in (None, "not_classifiable")
        assert not d.get("nebpi_primary_gate")

    with open(release / "scorecards.json", encoding="utf-8") as fh:
        json.load(fh)      # must parse; the firewall already refused any p/q/rank
