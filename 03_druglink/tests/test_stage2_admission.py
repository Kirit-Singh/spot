"""The Stage-2 aggregate admission chain: every way an aggregate is REFUSED.

The aggregate is admitted from bytes on disk, never from a Boolean in Stage-3's own source.
Each test asserts the SPECIFIC gate name, so a refusal for the wrong reason still fails.

Topology and the fixture firewall: ``test_stage2_aggregate.py``.
"""
from __future__ import annotations

import ast
import copy
import json
import os

import pytest

from druglink import stage2_aggregate as sa

from stage2_release_fixture import (
    TARGETS,
    PROGRAMS,
    _gate,
    build_release,
)

# --------------------------------------------------------------------------- #
# THE POINT OF THE MODULE: admission is on the bytes, not on a source constant.
# --------------------------------------------------------------------------- #
def test_admission_is_not_a_source_code_boolean():
    """The gate this module replaces was a constant. A constant admits nothing.

    Checked over the AST, not the text: the prose names the flag deliberately (that is
    the whole point of the module), so a substring search would pass on a module that
    still *read* it. Only an actual load of the name counts.
    """
    with open(sa.__file__, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())

    names = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    names |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert "DETACHED_CLONE_MATRIX_GREEN" not in names, (
        "admission still reads the stale source-code flag")

    imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)
                for a in n.names}
    assert "arm_query" not in imported

    module_bools = [k for k, v in vars(sa).items() if isinstance(v, bool)]
    assert module_bools == [], (
        f"module-level Booleans {module_bools} — a constant in a source file names no "
        "manifest, no report, no verifier and no bytes; it cannot admit anything")


def test_the_manifest_must_prove_its_own_identity(tmp_path):
    def tamper(manifest):
        manifest["inventory"][0]["raw_sha256"] = "f" * 64      # resealed? no: post-seal
    paths = build_release(tmp_path, mutate_after_seal=tamper)
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_MANIFEST_SELF_HASH in _gate(exc)


def test_the_self_hash_ignores_non_semantic_timestamps():
    a = {"artifact_class": "fixture", "inventory": [], "generated_at": "2026-01-01"}
    b = dict(a, generated_at="2099-12-31")
    assert sa.manifest_self_hash(a) == sa.manifest_self_hash(b)
    c = dict(a, inventory=[{"bundle_key": "direct|Rest"}])
    assert sa.manifest_self_hash(c) != sa.manifest_self_hash(a)


# --------------------------------------------------------------------------- #
# The independent report. It must ADMIT, and it must admit THESE bytes.
# --------------------------------------------------------------------------- #
def test_a_report_binding_a_DIFFERENT_manifest_is_refused(tmp_path):
    paths = build_release(
        tmp_path,
        mutate_report=lambda r: r["admits"].update({"manifest_raw_sha256": "f" * 64}))
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_REPORT_BINDS_ANOTHER_MANIFEST in _gate(exc)


def test_a_report_binding_a_different_CANONICAL_hash_is_refused(tmp_path):
    paths = build_release(
        tmp_path,
        mutate_report=lambda r: r["admits"].update(
            {"manifest_canonical_sha256": "e" * 64}))
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_REPORT_BINDS_ANOTHER_MANIFEST in _gate(exc)


def test_a_report_that_names_no_hash_at_all_is_an_opinion_not_an_admission(tmp_path):
    paths = build_release(tmp_path, mutate_report=lambda r: r.update({"admits": {}}))
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_REPORT_BINDS_NOTHING in _gate(exc)


def test_a_verdict_that_is_not_admit_is_refused(tmp_path):
    paths = build_release(tmp_path, mutate_report=lambda r: r.update({"verdict": "reject"}))
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_VERDICT_NOT_ADMIT in _gate(exc)


def test_a_non_independent_verifier_cannot_admit(tmp_path):
    paths = build_release(
        tmp_path,
        mutate_report=lambda r: r.update({"verifier_id": "spot.stage02.self_verifier.v1"}))
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_VERIFIER_NOT_INDEPENDENT in _gate(exc)


def test_the_report_may_not_BE_the_manifest(honest):
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(manifest_path=honest["manifest_path"],
                           report_path=honest["manifest_path"],
                           bundles_root=honest["bundles_root"],
                           stage1_release_path=honest["stage1_release_path"])
    assert sa.GATE_SELF_ADMISSION in _gate(exc)


def test_a_missing_manifest_refuses_and_never_falls_back_to_a_fixture(tmp_path):
    paths = build_release(tmp_path)
    os.remove(paths["manifest_path"])
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_ARTIFACT_NOT_ON_DISK in _gate(exc)


# --------------------------------------------------------------------------- #
# Path traversal. Every bundle resolves INSIDE the root, or it is not read.
# --------------------------------------------------------------------------- #
def test_a_traversing_bundle_path_is_refused(tmp_path):
    def escape(inv):
        inv[0]["path"] = "../../etc/arm_bundle.json"
    paths = build_release(tmp_path, mutate_inventory=escape)
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_PATH_TRAVERSAL in _gate(exc)


def test_an_absolute_bundle_path_is_refused(tmp_path):
    def escape(inv):
        inv[4]["path"] = "/etc/passwd"
    paths = build_release(tmp_path, mutate_inventory=escape)
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_PATH_TRAVERSAL in _gate(exc)


def test_a_symlink_out_of_the_root_is_refused(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "arm_bundle.json").write_text("{}", encoding="utf-8")

    def link(paths):
        target = os.path.join(paths["bundles_root"], "direct", "escape.json")
        os.symlink(str(outside / "arm_bundle.json"), target)

    paths = build_release(tmp_path / "rel",
                          mutate_inventory=lambda inv: inv[0].update(
                              {"path": "direct/escape.json"}),
                          mutate_disk=link)
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_PATH_TRAVERSAL in _gate(exc)


# --------------------------------------------------------------------------- #
# The inventory: missing, duplicate, unknown, partial — each refused BY NAME.
# --------------------------------------------------------------------------- #
def test_a_missing_bundle_is_refused(tmp_path):
    paths = build_release(tmp_path, mutate_inventory=lambda inv: inv.pop(7))
    with pytest.raises(sa.AggregateTopologyRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_MISSING_BUNDLE in _gate(exc)


def test_a_missing_LANE_is_refused_and_named(tmp_path):
    def drop_temporal(inv):
        inv[:] = [e for e in inv if e["lane"] != sa.LANE_TEMPORAL]
    paths = build_release(tmp_path, mutate_inventory=drop_temporal)
    with pytest.raises(sa.AggregateTopologyRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_MISSING_BUNDLE in _gate(exc)
    assert "temporal|Rest|Stim8hr" in _gate(exc)


def test_a_duplicate_bundle_key_cannot_fill_a_missing_slot(tmp_path):
    def dup(inv):
        inv[14] = copy.deepcopy(inv[0])          # count still says 15
    paths = build_release(tmp_path, mutate_inventory=dup)
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_DUPLICATE_BUNDLE in _gate(exc)


def test_an_unknown_lane_is_refused(tmp_path):
    paths = build_release(
        tmp_path, mutate_inventory=lambda inv: inv[0].update({"lane": "chronological"}))
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_UNKNOWN_LANE in _gate(exc)


def test_an_unknown_CONTEXT_is_refused(tmp_path):
    def alien(inv):
        inv[0].update({"bundle_key": "direct|Stim72hr", "condition": "Stim72hr"})
    paths = build_release(tmp_path, mutate_inventory=alien)
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_UNKNOWN_LANE in _gate(exc)


def test_a_bundle_key_that_disagrees_with_its_own_context_is_refused(tmp_path):
    def mislabel(inv):
        inv[0]["bundle_key"] = "direct|Stim48hr"          # entry's condition is Rest
    paths = build_release(tmp_path, mutate_inventory=mislabel)
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_UNKNOWN_LANE in _gate(exc)


def test_a_partial_inventory_is_never_admissible(tmp_path):
    paths = build_release(tmp_path, mutate_inventory=lambda inv: inv.clear())
    with pytest.raises(sa.AggregateTopologyRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_INCOMPLETE_TOPOLOGY in _gate(exc)


def test_a_partial_BUNDLE_short_of_its_arm_slots_is_refused(tmp_path):
    def drop_arms(docs):
        docs["temporal|Rest|Stim48hr"]["arms"] = \
            docs["temporal|Rest|Stim48hr"]["arms"][:18]
    paths = build_release(tmp_path, mutate_bundles=drop_arms)
    with pytest.raises(sa.AggregateTopologyRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_INCOMPLETE_TOPOLOGY in _gate(exc)
    assert "298" in _gate(exc)


def test_a_missing_program_across_the_release_is_refused(tmp_path):
    def drop_program(docs):
        for doc in docs.values():
            doc["arms"] = [a for a in doc["arms"] if a["program_id"] != PROGRAMS[3]]
    paths = build_release(tmp_path, mutate_bundles=drop_program)
    with pytest.raises(sa.AggregateTopologyRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_INCOMPLETE_TOPOLOGY in _gate(exc)
    assert "9 programs" in _gate(exc)


# --------------------------------------------------------------------------- #
# The bytes on disk are the bytes that were admitted.
# --------------------------------------------------------------------------- #
def test_a_bundle_mutated_after_admission_is_refused(tmp_path):
    def mutate(paths):
        victim = os.path.join(paths["bundles_root"], "direct", "direct__Rest.json")
        with open(victim, encoding="utf-8") as fh:
            doc = json.load(fh)
        doc["arms"][0]["records"][2]["rank"] = 1        # promote the UNRANKED target
        with open(victim, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(doc, sort_keys=True, separators=(",", ":")))

    paths = build_release(tmp_path, mutate_disk=mutate)
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_BUNDLE_BYTES_MOVED in _gate(exc)


def test_a_stage1_release_that_is_not_the_pinned_one_is_refused(tmp_path):
    def swap(paths):
        with open(paths["stage1_release_path"], "w", encoding="utf-8") as fh:
            fh.write(json.dumps({"release_id": "some_other_release"}))

    paths = build_release(tmp_path, mutate_disk=swap)
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_STAGE1_RELEASE_UNBOUND in _gate(exc)


def test_a_dangling_base_key_resolves_to_no_identity_and_is_refused(tmp_path):
    def dangle(docs):
        docs["direct|Rest"]["arms"][0]["records"][0]["base_key"] = "NOPE|NOPE"
    paths = build_release(tmp_path, mutate_bundles=dangle)
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_ARM_IDENTITY_UNRESOLVED in _gate(exc)


def test_a_base_key_resolving_to_a_DIFFERENT_target_is_refused(tmp_path):
    def swap(docs):
        rec = docs["direct|Rest"]["arms"][0]["records"][0]
        rec["base_key"] = f"{PROGRAMS[0]}|{TARGETS[1]}"     # says TGT_00, resolves TGT_01
    paths = build_release(tmp_path, mutate_bundles=swap)
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.admit_aggregate(**paths)
    assert sa.GATE_ARM_IDENTITY_UNRESOLVED in _gate(exc)


