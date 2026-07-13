"""ATTACKS on the Stage-2 aggregate admission chain. Each dies at the gate that NAMES it.

The honest release is the REAL one — Stage-2's generated manifest and its generated admission
report, byte for byte (``stage2_release_fixture``). Every attack below breaks exactly ONE
thing in a copy of those real bytes, so what is under test is the gate, not the fixture.

THE ADMISSION. Stage 2 declares no ``artifact_class``, so there is no such field for a
fixture firewall to key on. What admits a release is Stage-2's OWN admission, and each clause
is a separate gate:

    verdict == "admit"  AND  admission.status == "admitted"
    AND generator_is_not_verifier is True   AND  n_failed == 0
    AND topology_complete is True           AND  release_admissible is True
    AND the report's manifest_sha256 == the semantic self-hash WE recompute from the bytes

Topology and the fixture firewall: ``test_stage2_aggregate.py``.
"""
from __future__ import annotations

import json
import os
import shutil

import pytest
from druglink import stage2_aggregate as sa

from stage2_release_fixture import build_invented_release, build_release


def _refused(paths, gate, exc=sa.Stage2AggregateError):
    with pytest.raises(exc) as err:
        sa.admit_aggregate(**{k: v for k, v in paths.items()
                              if k != "other_manifest_path"})
    assert gate in str(err.value), f"expected gate {gate!r}, got: {err.value}"
    return str(err.value)


# --------------------------------------------------------------------------- #
# 0. THE CONTROL. Without it, every refusal below proves nothing.
# --------------------------------------------------------------------------- #
def test_the_REAL_release_is_ADMITTED(honest):
    agg = sa.admit_aggregate(**honest)
    assert agg.verdict == sa.ADMIT
    assert len(agg.bundles) == 15 and len(agg.arms) == 300     # non-vacuous


# --------------------------------------------------------------------------- #
# 1. THE RETIRED INVENTED SHAPE. It must be REFUSED, not silently accepted.
# --------------------------------------------------------------------------- #
def test_the_OLD_INVENTED_SHAPE_is_refused(tmp_path):
    """The regression that closes this defect.

    ``inventory[]`` instead of ``bundles[]``, an ``admits{}`` block instead of the report's
    own ``manifest_sha256``, a top-level ``artifact_class`` Stage 2 has never declared, and a
    verifier id containing the word "independent". The old loader REQUIRED all of it. It is a
    schema Stage 2 never emitted, and it now dies at the first gate that reads the bytes.
    """
    paths = build_invented_release(tmp_path)
    _refused(paths, sa.GATE_MANIFEST_NOT_NATIVE)


def test_the_invented_verifier_id_substring_no_longer_admits_anything(tmp_path):
    """'…independent…' in a name proves nothing: the id must BE the pinned verifier.

    The retired gate required that substring — so it would have REFUSED the genuine report
    (whose id does not contain it) and ADMITTED this forgery (whose id does).
    """
    paths = build_release(tmp_path, mutate_report=lambda r: r.update(
        {"verifier_id": "spot.stage02.aggregate.independent_verifier.v1"}))
    _refused(paths, sa.GATE_VERIFIER_NOT_PINNED)


# --------------------------------------------------------------------------- #
# 2. THE ADMISSION. One clause broken at a time.
# --------------------------------------------------------------------------- #
def test_a_verdict_that_is_not_admit_is_refused(tmp_path):
    paths = build_release(tmp_path, mutate_report=lambda r: r.update({"verdict": "reject"}))
    _refused(paths, sa.GATE_VERDICT_NOT_ADMIT)


def test_a_report_with_FAILED_GATES_is_refused(tmp_path):
    """verdict='admit' but n_failed>0: a release with a failed gate is not admitted,
    whatever its verdict string says."""
    paths = build_release(tmp_path, mutate_report=lambda r: r.update(
        {"n_failed": 1, "failed_gates": ["the_manifest_binds_the_release"]}))
    _refused(paths, sa.GATE_GATES_FAILED)


def test_a_report_that_does_not_assert_generator_is_not_verifier_is_refused(tmp_path):
    paths = build_release(tmp_path, mutate_report=lambda r: r.update(
        {"generator_is_not_verifier": False}))
    _refused(paths, sa.GATE_GENERATOR_IS_VERIFIER)


def test_a_report_MISSING_generator_is_not_verifier_is_refused(tmp_path):
    """A missing field is a refusal, never a default."""
    paths = build_release(tmp_path,
                          mutate_report=lambda r: r.pop("generator_is_not_verifier"))
    _refused(paths, sa.GATE_GENERATOR_IS_VERIFIER)


def test_an_INCOMPLETE_TOPOLOGY_is_refused(tmp_path):
    paths = build_release(tmp_path, mutate_report=lambda r: r.update(
        {"topology_complete": False}))
    _refused(paths, sa.GATE_TOPOLOGY_NOT_COMPLETE)


def test_a_release_the_verifier_did_not_find_ADMISSIBLE_is_refused(tmp_path):
    paths = build_release(tmp_path, mutate_report=lambda r: r.update(
        {"release_admissible": False}))
    _refused(paths, sa.GATE_NOT_RELEASE_ADMISSIBLE)


def test_an_admission_status_that_is_not_ADMITTED_is_refused(tmp_path):
    paths = build_release(tmp_path, mutate_report=lambda r: r["admission"].update(
        {"status": "refused_by_independent_aggregate_admission"}))
    _refused(paths, sa.GATE_ADMISSION_NOT_GRANTED)


def test_a_report_from_an_UNPINNED_verifier_is_refused(tmp_path):
    paths = build_release(tmp_path, mutate_report=lambda r: r.update(
        {"verifier_id": "spot.stage02.some.other.verifier.v9"}))
    _refused(paths, sa.GATE_VERIFIER_NOT_PINNED)


def test_a_report_that_is_not_the_native_schema_is_refused(tmp_path):
    paths = build_release(tmp_path, mutate_report=lambda r: r.update(
        {"schema_version": "spot.stage02_aggregate_verification.v1"}))
    _refused(paths, sa.GATE_REPORT_NOT_NATIVE)


# --------------------------------------------------------------------------- #
# 3. IDENTITY. The manifest proves who it is; the report admits THOSE bytes.
# --------------------------------------------------------------------------- #
def test_a_manifest_that_cannot_recompute_its_own_identity_is_refused(tmp_path):
    """Edited after sealing, self-hash left stale."""
    paths = build_release(tmp_path, reseal_manifest=False,
                          mutate_manifest=lambda m: m.update({"n_bundles": 14}))
    _refused(paths, sa.GATE_MANIFEST_SELF_HASH)


def test_a_manifest_MUTATED_AFTER_ADMISSION_and_RESEALED_is_refused(tmp_path):
    """The forger with repo access: edit the manifest AND re-seal its self-hash.

    The self-hash now recomputes cleanly, so the ONLY thing that catches this is that the
    report admitted a DIFFERENT number. This is precisely why the report must bind the bytes
    and why the self-hash alone is not enough.
    """
    paths = build_release(tmp_path, reseal_manifest=True,
                          mutate_manifest=lambda m: m.update({"n_bundles": 14}))
    _refused(paths, sa.GATE_REPORT_BINDS_ANOTHER_MANIFEST)


def test_a_report_that_admits_a_DIFFERENT_manifest_is_refused(tmp_path):
    """The report is genuine and says ADMIT — about other bytes."""
    paths = build_release(tmp_path, second_manifest=True)
    paths["manifest_path"] = paths.pop("other_manifest_path")
    _refused(paths, sa.GATE_REPORT_BINDS_ANOTHER_MANIFEST)


def test_a_report_whose_RECOMPUTATION_disagrees_with_its_claim_is_refused(tmp_path):
    """manifest_sha256 matches ours, manifest_sha256_recomputed does not: a verifier
    contradicting itself is not an admission."""
    paths = build_release(tmp_path, mutate_report=lambda r: r.update(
        {"manifest_sha256_recomputed": "0" * 64}))
    _refused(paths, sa.GATE_REPORT_BINDS_ANOTHER_MANIFEST)


def test_the_manifest_and_the_report_may_not_be_the_SAME_FILE(tmp_path):
    paths = build_release(tmp_path)
    paths["report_path"] = paths["manifest_path"]
    _refused(paths, sa.GATE_SELF_ADMISSION)


def test_a_manifest_that_is_not_the_native_schema_is_refused(tmp_path):
    paths = build_release(tmp_path, mutate_manifest=lambda m: m.update(
        {"schema_version": "spot.stage02_aggregate_run_manifest.v1"}))
    _refused(paths, sa.GATE_MANIFEST_NOT_NATIVE)


def test_a_manifest_that_is_not_readable_json_is_refused(tmp_path):
    def corrupt(paths):
        with open(paths["manifest_path"], "w") as fh:
            fh.write("{not json")
    paths = build_release(tmp_path, mutate_disk=corrupt)
    _refused(paths, sa.GATE_MANIFEST_UNREADABLE)


def test_a_MISSING_artifact_is_refused_and_never_defaulted(tmp_path):
    paths = build_release(tmp_path, mutate_disk=lambda p: os.remove(p["report_path"]))
    _refused(paths, sa.GATE_ARTIFACT_NOT_ON_DISK)


# --------------------------------------------------------------------------- #
# 4. THE STAGE-1 RELEASE the aggregate stands on.
# --------------------------------------------------------------------------- #
def test_a_DIFFERENT_stage1_release_on_disk_is_refused(tmp_path):
    def swap(paths):
        with open(paths["stage1_release_path"], "w") as fh:
            json.dump({"schema": "spot.stage01_v3_release.v1", "forged": True}, fh)
    paths = build_release(tmp_path, mutate_disk=swap)
    _refused(paths, sa.GATE_STAGE1_RELEASE_UNBOUND)


def test_a_manifest_binding_ANOTHER_RELEASE_is_refused(tmp_path):
    """A release of another shape is a different aggregate, and its arms are not these."""
    paths = build_release(tmp_path, reforge_admission=True,
                          mutate_manifest=lambda m: m["stage1_v3_release"].update(
                              {"conditions": ["Rest", "Stim8hr"]}))
    _refused(paths, sa.GATE_RELEASE_IS_NOT_THE_PINNED_ONE)


# --------------------------------------------------------------------------- #
# 5. THE BUNDLES. Bytes, paths, counts.
# --------------------------------------------------------------------------- #
def test_a_bundle_whose_BYTES_MOVED_is_refused(tmp_path):
    """One ranking file edited after the verifier read it. Every bound byte is re-hashed."""
    def tamper(bundles_root):
        for base, _dirs, files in os.walk(bundles_root):
            if os.path.basename(base) == "rankings":
                for fn in sorted(files):
                    path = os.path.join(base, fn)
                    doc = json.load(open(path))
                    doc["records"][0]["arm_value"] = 999.0
                    with open(path, "w") as fh:
                        json.dump(doc, fh)
                    return
    paths = build_release(tmp_path, mutate_bundles=tamper)
    _refused(paths, sa.GATE_BUNDLE_BYTES_MOVED)


def test_a_bundle_whose_ARM_INVENTORY_was_edited_is_refused(tmp_path):
    def tamper(bundles_root):
        for base, _dirs, files in os.walk(bundles_root):
            if "arm_bundle.json" in files:
                path = os.path.join(base, "arm_bundle.json")
                doc = json.load(open(path))
                doc["arms"] = doc["arms"][:-1]            # quietly drop an arm
                with open(path, "w") as fh:
                    json.dump(doc, fh)
                return
    paths = build_release(tmp_path, mutate_bundles=tamper)
    _refused(paths, sa.GATE_BUNDLE_BYTES_MOVED)


def test_a_MISSING_bundle_directory_is_refused(tmp_path):
    paths = build_release(
        tmp_path,
        mutate_bundles=lambda root: shutil.rmtree(os.path.join(root, "direct")))
    _refused(paths, sa.GATE_ARTIFACT_NOT_ON_DISK)


def test_a_bundle_DROPPED_from_the_manifest_is_refused(tmp_path):
    """The forger owns BOTH files, so the hash chain closes — and the topology, re-derived
    from the release, still says a bundle is missing."""
    paths = build_release(tmp_path, reforge_admission=True,
                          mutate_manifest=lambda m: m["bundles"].pop(0))
    _refused(paths, sa.GATE_MISSING_BUNDLE, exc=sa.AggregateTopologyRefused)


def test_a_DUPLICATE_bundle_is_refused(tmp_path):
    """A repeated invocation is not two: a duplicate silently fills a missing slot."""
    def dup(m):
        m["bundles"][1] = json.loads(json.dumps(m["bundles"][0]))
    paths = build_release(tmp_path, reforge_admission=True, mutate_manifest=dup)
    _refused(paths, sa.GATE_DUPLICATE_BUNDLE)


def test_a_bundle_path_that_ESCAPES_the_bundles_root_is_refused(tmp_path):
    """An out_dir is a bare NAME. A traversing path reads bytes nobody bound."""
    paths = build_release(tmp_path, reforge_admission=True,
                          mutate_manifest=lambda m: m["bundles"][0].update(
                              {"out_dir": "../../../etc"}))
    _refused(paths, sa.GATE_PATH_TRAVERSAL)


def test_an_ABSOLUTE_bundle_path_is_refused(tmp_path):
    paths = build_release(tmp_path, reforge_admission=True,
                          mutate_manifest=lambda m: m["bundles"][0].update(
                              {"out_dir": "/etc"}))
    _refused(paths, sa.GATE_PATH_TRAVERSAL)


def test_a_manifest_with_NO_BUNDLES_is_refused(tmp_path):
    paths = build_release(tmp_path, reforge_admission=True,
                          mutate_manifest=lambda m: m.update({"bundles": []}))
    _refused(paths, sa.GATE_INCOMPLETE_TOPOLOGY, exc=sa.AggregateTopologyRefused)


def test_an_INVENTORY_array_is_not_a_BUNDLES_array(tmp_path):
    """The old shape's field name, on an otherwise-real manifest. It binds nothing."""
    paths = build_release(tmp_path, reforge_admission=True,
                          mutate_manifest=lambda m: m.update({"inventory": m.pop("bundles")}))
    _refused(paths, sa.GATE_INCOMPLETE_TOPOLOGY, exc=sa.AggregateTopologyRefused)
