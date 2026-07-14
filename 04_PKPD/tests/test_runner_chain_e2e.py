"""THE literal chain, end to end, through the real CLIs — no helper shortcuts.

    run_acquire  ->  run_materialize  ->  verify_bundle  ->  run_stage4  ->  verify_stage4

Every earlier test drove one link. The independent audit drove the WHOLE thing and found it broken
at the first join: `run_acquire` exits 0, and `run_materialize` then dies on the records it wrote.
Nothing caught it, because nothing had ever run the second command on the first command's output.

The defects were a chain, and each one alone looks harmless:

  1. Stage 3's `source_records` carry **no access timestamp** — they pin bytes by `raw_sha256`,
     `source_release` and `access_record_sha256` instead. Stage 4 cannot know when Stage 3 fetched
     them, and must not pretend to.
  2. `run_acquire._access_date()` filled that hole with **`1970-01-01`**. An epoch placeholder is
     not a missing value; it is a FABRICATED provenance claim that reads as a real access date, and
     it went into all 29 reused records.
  3. `materialize` turned the missing `accessed_at_utc` into `""`, and the evidence contract
     rejected it — which is the only reason anybody noticed.

The repair is the honest one: a time that no source states is stated as ABSENT, with the reason,
and the bytes stay pinned by the hashes that actually identify them.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

STAGE4 = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ANNOTATION_BUNDLE = os.path.join(STAGE4, "tests", "fixtures", "stage3_annotation",
                                 "s3_0b119088734643bf")
METHOD_DIR = os.path.join(STAGE4, "method")


def _run(module: str, *args: str) -> subprocess.CompletedProcess:
    """The real CLI, in a real subprocess. Importing `main` would not prove the command works."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([STAGE4, os.path.join(STAGE4, "tests"),
                                         env.get("PYTHONPATH", "")])
    return subprocess.run([sys.executable, "-m", module, *args],
                          capture_output=True, text=True, cwd=STAGE4, env=env, check=False)


@pytest.fixture(scope="module")
def chain(tmp_path_factory):
    """Drive the whole chain once; every test below reads its artifacts."""
    root = tmp_path_factory.mktemp("chain")
    run_root = str(root / "runroot")
    bundle = str(root / "evidence_bundle.json")
    outputs = str(root / "outputs")

    acquire = _run("analysis.run_acquire",
                   "--stage3-annotation-bundle", ANNOTATION_BUNDLE, "--run-root", run_root)
    materialize = _run("analysis.run_materialize",
                       "--stage3-annotation-bundle", ANNOTATION_BUNDLE, "--run-root", run_root,
                       "--out", bundle)
    verify_b = _run("verifier.verify_bundle", bundle, "--run-root", run_root)
    stage4 = _run("analysis.run_stage4",
                  "--stage3-annotation-bundle", ANNOTATION_BUNDLE,
                  "--evidence-bundle", bundle, "--outputs-root", outputs)

    return {"root": root, "run_root": run_root, "bundle": bundle, "outputs": outputs,
            "acquire": acquire, "materialize": materialize,
            "verify_bundle": verify_b, "stage4": stage4}


# --------------------------------------------------------------------------- every link exits 0

def test_run_acquire_exits_0(chain):
    assert chain["acquire"].returncode == 0, chain["acquire"].stderr[-1500:]


def test_run_materialize_exits_0_ON_run_acquires_OWN_OUTPUT(chain):
    """THE audit's finding. `run_acquire` succeeded and `run_materialize` crashed on the records it
    had just written — an `accessed_at_utc` that was missing upstream, invented as an epoch, and
    then emptied. The two commands had never been run back to back."""
    assert chain["materialize"].returncode == 0, chain["materialize"].stderr[-2000:]


def test_verify_bundle_ADMITS_the_materialized_bundle(chain):
    assert chain["verify_bundle"].returncode == 0, chain["verify_bundle"].stdout[-2000:]


def test_run_stage4_exits_0_on_the_materialized_bundle(chain):
    assert chain["stage4"].returncode == 0, chain["stage4"].stderr[-2000:]


def test_verify_stage4_ADMITS_the_release(chain):
    """The chain ends at the INDEPENDENT verifier, not at the engine's own say-so."""
    releases = list((chain["root"] / "outputs").rglob("manifest.json"))
    assert len(releases) == 1, f"expected exactly one release, got {releases}"

    report = _run("verifier.verify_stage4", "--release", str(releases[0].parent),
                  "--method", METHOD_DIR)
    assert report.returncode == 0, report.stdout[-2500:]


# ------------------------------------------------------------- a time nobody stated is not a time

def test_no_record_carries_an_INVENTED_access_time(chain):
    """`1970-01-01` is not a missing value. It is a fabricated provenance claim wearing the shape
    of a real access date, and it reached all 29 reused records."""
    with open(os.path.join(chain["run_root"], "acquisition_manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)

    for rec in manifest["records"]:
        for field in ("access_date", "accessed_at_utc"):
            value = rec.get(field)
            assert not (value or "").startswith("1970-"), (
                f"{rec['acquisition_record_id']}: {field}={value!r} — the epoch is not a date, it "
                "is an invented one. Stage 3 states no access time, so Stage 4 must not either.")


def test_a_reused_record_STATES_that_its_access_time_is_unknown(chain):
    """Stage 3 pins its bytes by hash and release, not by a clock. So Stage 4 says so, in writing,
    and the absence travels into the evidence bundle rather than being filled in."""
    with open(chain["bundle"], encoding="utf-8") as fh:
        bundle = json.load(fh)

    reused = [r for r in bundle["source_acquisition"] if not r.get("accessed_at_utc")]
    assert reused, "this test is vacuous unless some record has no access time"

    for row in reused:
        reason = row.get("access_time_not_stated_reason") or ""
        assert len(reason) > 20, (
            f"{row['acquisition_id']}: the access time is absent and nothing says why. An "
            "unexplained blank is indistinguishable from a value nobody bothered to record.")
        # ...and the bytes are still pinned by what DOES identify them
        assert row.get("raw_sha256"), "a byte with neither a time nor a hash is not evidence"


# ------------------------------------------------------- the doors, and the flag that must bite

def test_the_RETIRED_stage3_bundle_flag_REFUSES_rather_than_misroutes():
    """`--stage3-bundle` named the OTHER door — the wire bundle. A caller who read the flag, or the
    README, handed an annotation bundle to the wrong reader. Renaming it silently would have left
    every old script quietly wrong; it refuses instead, and says which flag to use."""
    for module in ("analysis.run_acquire", "analysis.run_materialize"):
        out = _run(module, "--stage3-bundle", ANNOTATION_BUNDLE, "--run-root", "/tmp/x",
                   *(["--out", "/tmp/y.json"] if "materialize" in module else []))
        assert out.returncode == 2, f"{module} accepted the retired flag"
        assert "stage3_bundle_flag_retired" in out.stderr
        assert "--stage3-annotation-bundle" in out.stderr, "the refusal must name the right flag"


@pytest.mark.parametrize("door", [["--fixtures"],
                                  ["--stage3-bundle", ANNOTATION_BUNDLE]])
def test_require_external_verifier_is_never_SILENTLY_IGNORED(door, tmp_path):
    """The audit's probe: the flag reached only the annotation door. The others took it, dropped it
    and exited 0 — so an operator who demanded Stage 3's own verifier was told the run succeeded
    when the gate was never consulted. A verification you asked for and did not get, reported as
    success, is the worst of the three outcomes."""
    out = _run("analysis.run_stage4", *door, "--require-external-verifier",
               "--outputs-root", str(tmp_path))

    assert out.returncode == 2, (
        f"{door[0]} accepted --require-external-verifier and exited {out.returncode}; the gate was "
        "never consulted")
    assert "external_verifier_not_applicable_to_this_door" in out.stderr


def test_the_annotation_door_HONOURS_require_external_verifier(tmp_path):
    """On the door where it IS applicable, the flag must actually bite: with no Stage-3 verifier
    context configured, a real run is refused rather than admitted on the weaker gate."""
    out = _run("analysis.run_stage4", "--stage3-annotation-bundle", ANNOTATION_BUNDLE,
               "--require-external-verifier", "--outputs-root", str(tmp_path))

    assert out.returncode == 2, "gate 2 was demanded, never ran, and the run still succeeded"
    assert "stage3_external_verifier" in out.stderr.lower()


# --------------------------------------------- the candidate join: A's bytes are never B's evidence

def test_the_receipt_COUNTS_candidates_acquired_instead_of_hardcoding_zero(chain):
    """`candidates_acquired` was the literal integer 0. A count that cannot change is not a count —
    the receipt could report seven fetched records for a queued candidate and still say nothing had
    been acquired for any candidate."""
    with open(os.path.join(chain["run_root"], "acquisition_receipt.json"), encoding="utf-8") as fh:
        receipt = json.load(fh)

    acq = receipt["acquisition"]
    assert "candidates_acquired" in acq
    # this default run fetches nothing, so 0 is the TRUE answer here — but it must be a computed 0
    assert acq["candidates_acquired"] == 0
    assert acq["reused_from_stage3"] == 29, "the count must be derived from the real records"


def test_a_record_acquired_for_candidate_A_can_NEVER_become_evidence_for_candidate_B(tmp_path):
    """The join is a typed field, read — never guessed from a source id or a name substring.

    A record naming a candidate the admitted bundle does not contain is REFUSED, not silently
    reattached and not silently dropped: the acquisition and the bundle disagree about who the
    candidates are, and that is a finding, not a detail.
    """
    from analysis.acquisition import AcquisitionManifest, RunRoot
    from analysis.materialize import MaterializationError, materialize
    from analysis.stage3_annotation import adapt_annotation_bundle

    admission = adapt_annotation_bundle(ANNOTATION_BUNDLE)
    run_root = RunRoot(str(tmp_path / "rr"))

    from test_materialize import PUBCHEM_JSON, _record

    rec = _record(run_root, key="pubchem.property", raw=PUBCHEM_JSON, stable_id="5394",
                  source_type="public_api", transform="PubChem property table")
    impostor = rec.model_copy(update={"candidate_id": "AM:CHEMBL:NOT_IN_THIS_BUNDLE"})

    manifest = AcquisitionManifest(
        schema_id="spot.stage04_acquisition_manifest.v1", run_id="acqrun-x",
        stage3_binding={}, source_ledger_sha256="b" * 64, records=[impostor], missing=[])
    run_root.write_manifest(manifest)

    with pytest.raises(MaterializationError) as exc:
        materialize(admission, manifest, run_root)
    assert exc.value.code == "acquisition_candidate_not_admitted"
