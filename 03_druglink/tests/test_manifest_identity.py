"""The manifest must prove its OWN identity — external review finding B6.

The manifest is the root of trust for the whole bundle: the document hash and every file
hash are recorded *in* it. The verifier checked all of those entries and never recomputed
the manifest's own canonical identity — so setting

    manifest["manifest_sha256"] = "0" * 64

still passed all 60 checks. A verifier that validates the entries of a document whose own
identity it never checks has proved that the manifest agrees with itself, which is exactly
the self-consistency this verifier exists to refuse.

(Stage 4 recomputes the manifest hash independently, so downstream admission was never
open. What was false was Stage 3's STANDALONE verification claim — and that claim is the
whole product of this lane.)

These tests hold the gate to what it now claims, including the two ways a gate like this
is usually born broken: it never fires, or it fires on everything.
"""
from __future__ import annotations

import json
import os

import pytest

from druglink import artifacts
from verifier import canon, checks, verify_stage3

MANIFEST = "manifest.json"


def _write(tmp_path, build, name="out"):
    return artifacts.write_bundle(
        output_root=str(tmp_path / name), artifact_class="analysis",
        document=build["document"], doc_id=build["document_id"],
        tables=build["tables"], created_at="2026-07-12T00:00:00+00:00")


def _verify(bundle, direct_run, cache_root):
    return verify_stage3.verify(
        bundle=bundle, cache_root=cache_root, direct_run=direct_run["run_dir"],
        direct_inputs_root=direct_run["inputs_root"], artifact_class="analysis",
        direct_analysis=direct_run["analysis"])


def _read_manifest(bundle):
    with open(os.path.join(bundle, MANIFEST), encoding="utf-8") as fh:
        return json.load(fh)


def _rewrite_manifest(bundle, manifest):
    with open(os.path.join(bundle, MANIFEST), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)


def _result(rep, gate):
    """The (ok, detail) of one NAMED check. Raises if the gate is not even present —
    a gate that silently stopped running would otherwise read as a pass."""
    for name, ok, detail in rep.checks:
        if name == gate:
            return ok, detail
    raise AssertionError(f"the {gate!r} gate did not run at all")


def _failed(rep):
    return [n for n, ok, _ in rep.checks if not ok]


# --------------------------------------------------------------------------- #
# B6, exactly as the external review reported it.
# --------------------------------------------------------------------------- #
def test_a_forged_manifest_sha256_fails_at_the_named_identity_gate(
        tmp_path, analysis_build, direct_run, analysis_cache):
    """Change ONLY manifest_sha256. Nothing else. The verifier must refuse."""
    bundle = _write(tmp_path, analysis_build)

    manifest = _read_manifest(bundle)
    authentic = manifest["manifest_sha256"]
    manifest["manifest_sha256"] = "0" * 64
    _rewrite_manifest(bundle, manifest)

    # Nothing but the identity moved: the bundle's real content is untouched.
    assert _read_manifest(bundle) == {**manifest}
    assert authentic != "0" * 64

    rep = _verify(bundle, direct_run, analysis_cache)

    ok, detail = _result(rep, checks.MANIFEST_IDENTITY_GATE)
    assert not ok, "a forged manifest_sha256 passed the identity gate"
    assert "0000" in detail                      # it names what the manifest claimed
    assert _failed(rep) == [checks.MANIFEST_IDENTITY_GATE], (
        "the forgery must fail at the identity gate and ONLY there — a broad failure "
        "would mean this gate is not what actually caught it")


def test_a_manifest_with_no_identity_at_all_fails_closed(
        tmp_path, analysis_build, direct_run, analysis_cache):
    """Deleting the field must not read as 'nothing to check'."""
    bundle = _write(tmp_path, analysis_build)
    manifest = _read_manifest(bundle)
    del manifest["manifest_sha256"]
    _rewrite_manifest(bundle, manifest)

    ok, _ = _result(_verify(bundle, direct_run, analysis_cache),
                    checks.MANIFEST_IDENTITY_GATE)
    assert not ok, "a manifest with no identity must fail closed, not pass vacuously"


@pytest.mark.parametrize("field", ["bundle_id", "document_sha256", "artifact_class"])
def test_tampering_with_a_covered_field_also_breaks_the_identity(
        field, tmp_path, analysis_build, direct_run, analysis_cache):
    """The identity COVERS the manifest's semantic content — so re-sealing a tampered
    manifest is not a way around the gate: the recomputed hash moves with the content."""
    bundle = _write(tmp_path, analysis_build)
    manifest = _read_manifest(bundle)
    manifest[field] = "tampered"
    _rewrite_manifest(bundle, manifest)

    ok, _ = _result(_verify(bundle, direct_run, analysis_cache),
                    checks.MANIFEST_IDENTITY_GATE)
    assert not ok, f"{field} is not covered by the manifest identity"


# --------------------------------------------------------------------------- #
# The gate must not fire on everything — a check that always fails is not a check.
# --------------------------------------------------------------------------- #
def test_the_identity_gate_passes_on_an_honest_bundle(
        tmp_path, analysis_build, direct_run, analysis_cache):
    bundle = _write(tmp_path, analysis_build)
    rep = _verify(bundle, direct_run, analysis_cache)

    ok, detail = _result(rep, checks.MANIFEST_IDENTITY_GATE)
    assert ok, f"the identity gate rejects an honest bundle: {detail}"
    assert not _failed(rep), f"clean bundle must have zero failures: {_failed(rep)}"


def test_created_at_is_excluded_because_it_is_not_semantic(
        tmp_path, analysis_build, direct_run, analysis_cache):
    """The same bundle rebuilt at a different wall-clock time is the SAME bundle, so
    created_at is deliberately outside the identity. This pins that choice: if someone
    later folds the timestamp in, the identity stops being reproducible and this fails."""
    bundle = _write(tmp_path, analysis_build)
    manifest = _read_manifest(bundle)
    manifest["created_at"] = "2099-01-01T00:00:00+00:00"
    _rewrite_manifest(bundle, manifest)

    ok, detail = _result(_verify(bundle, direct_run, analysis_cache),
                         checks.MANIFEST_IDENTITY_GATE)
    assert ok, f"created_at must not participate in the manifest identity: {detail}"


def test_the_identity_is_recomputed_independently_of_the_writer(
        tmp_path, analysis_build):
    """The verifier must derive the hash from the BYTES, not trust the writer's field.

    Recomputed here with the verifier's own canonicaliser — which shares no code with
    ``druglink.artifacts`` — so agreement is two implementations agreeing, not one
    implementation agreeing with itself.
    """
    bundle = _write(tmp_path, analysis_build)
    manifest = _read_manifest(bundle)

    assert canon.chash(canon.without(manifest, checks.MANIFEST_IDENTITY_EXCLUDED)) \
        == manifest["manifest_sha256"]

    # And the exclusion set is exactly the two fields that cannot be in it: the hash
    # itself (nothing can cover its own value) and the non-semantic timestamp.
    assert set(checks.MANIFEST_IDENTITY_EXCLUDED) == {"manifest_sha256", "created_at"}
