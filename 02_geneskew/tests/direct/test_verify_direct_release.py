"""The WHOLE Direct release: every condition the bound Stage-1 release ships, exactly once.

Audit BLOCKER 6. `run_arms` emits one condition per invocation and nothing said what a whole
release is — so a one-bundle run was indistinguishable from a finished Direct release, and no
verifier could tell them apart because the expectation existed nowhere.

The expected conditions are DERIVED from the bound Stage-1 release, never from a constant
here: a hard-coded three would keep passing after Stage-1 shipped a fourth, and an incomplete
release would sail under a complete-looking name.

Omission, duplication and a condition relabel each fail at their own NAMED gate.
"""
from __future__ import annotations

import json
import os
import shutil
import sys

import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "analysis", "direct"))

import fixtures_v3_release as V3  # noqa: E402
import verify_direct_release as VR  # noqa: E402

# The PRODUCER, and the shared Stage-1 release FIXTURE. Both are driven by the HARNESS only.
# The verifier itself imports neither: gate_independence proves that against its own source.
from direct import arm_release  # noqa: E402

CONDITIONS = ("Rest", "Stim8hr", "Stim48hr")

# THE PINNED STAGE-2 SOLVER LOCK. Every run binds it; the verifier re-hashes it and hard-pins
# it, so the harness must supply the real one — a fixture that skipped it would be testing a
# configuration the lane refuses.
LOCK = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "analysis", "stage02_solver_lock.txt")



@pytest.fixture
def release(synthetic_run, tmp_path):
    """A real three-condition Direct release from the producer, and verifier args for it."""
    prod = synthetic_run(conditions=CONDITIONS)
    stage1_root = str(tmp_path / "root")
    stage1 = V3.stage_release(stage1_root, conditions=CONDITIONS)
    prod.stage1_release = stage1
    prod.stage1_release_root = stage1_root
    prod.env_lock = LOCK
    prod.out_root = str(tmp_path / "release")
    res = arm_release.build_release(prod)

    argv = [
        "--release", res["out_dir"],
        "--de-main", prod.de_main, "--sgrna", prod.sgrna,
        "--by-guide", prod.by_guide, "--by-donors", prod.by_donors,
        "--guide-manifest", prod.guide_manifest,
        "--registry", prod.registry,
        "--stage1-v3-release", stage1, "--release-root", stage1_root,
        "--recompute", "all", "--env-lock", LOCK,
    ]
    for flag, attr in (("--source-registry", "source_registry"),
                       ("--pseudobulk", "pseudobulk")):
        value = getattr(prod, attr, None)
        if value:
            argv += [flag, value]
    return res, VR.build_parser().parse_args(argv)


def run(args) -> dict:
    return VR.verify(args).doc()


def failed(args, gate_substring: str) -> bool:
    doc = run(args)
    return doc["verdict"] == "REFUSE" and any(
        gate_substring in g for g in doc["failed_gates"])


def _rewrite(args, mutate):
    path = os.path.join(args.release, VR.RELEASE_FILE)
    doc = json.load(open(path))
    mutate(doc)
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)


class TestTheCompleteReleaseInventory:
    def test_the_release_ships_exactly_the_bound_releases_conditions(self, release):
        res, args = release
        assert sorted(res["expected_conditions"]) == sorted(CONDITIONS)
        assert res["n_physical_bundles"] == 3

    def test_the_expected_conditions_are_DERIVED_from_the_bound_Stage1_release(
            self, release):
        # never a constant here: a hard-coded three keeps passing after Stage-1 ships a
        # fourth, and the release goes out incomplete under a complete-looking name
        _, args = release
        bound = run(args)["bound_artifact"]
        assert sorted(bound["expected_conditions"]) == sorted(CONDITIONS)

    def test_the_logical_arm_count_is_the_sum_of_the_bundles_derived_slots(self, release):
        res, args = release
        per_bundle = res["bundles"][0]["n_expected_arm_slots"]
        assert res["n_logical_arms"] == per_bundle * 3

    def test_the_producer_does_NOT_admit_its_own_release(self, release):
        res, _ = release
        doc = json.load(open(os.path.join(res["out_dir"], VR.RELEASE_FILE)))
        assert doc["admitted"] is False
        assert doc["self_admitted"] is False
        assert doc["verifier_id"] is None


class TestOmissionDuplicationAndRelabelEachFailAtANamedGate:
    def test_an_OMITTED_condition_is_REFUSED(self, release):
        _, args = release
        _rewrite(args, lambda d: d["bundles"].pop())
        assert failed(args, "every condition the bound Stage-1 release ships HAS a bundle")

    def test_a_DUPLICATED_condition_is_REFUSED(self, release):
        _, args = release
        _rewrite(args, lambda d: d["bundles"].append(dict(d["bundles"][0])))
        assert failed(args, "no condition was produced more than once")

    def test_a_RELABELLED_condition_is_REFUSED(self, release):
        # rename a bundle's condition to one the bound release never shipped
        _, args = release
        def relabel(d):
            d["bundles"][0]["condition"] = "StimNever"
        _rewrite(args, relabel)
        assert failed(args, "never shipped")

    def test_a_relabel_onto_an_EXISTING_condition_is_REFUSED_as_a_duplicate(self, release):
        _, args = release
        def relabel(d):
            d["bundles"][0]["condition"] = d["bundles"][1]["condition"]
        _rewrite(args, relabel)
        assert failed(args, "no condition was produced more than once")

    def test_a_MISSING_bundle_DIRECTORY_is_REFUSED(self, release):
        _, args = release
        doc = json.load(open(os.path.join(args.release, VR.RELEASE_FILE)))
        shutil.rmtree(os.path.join(args.release, doc["bundles"][0]["path"]))
        assert failed(args, "is on disk at the path the release cites")

    def test_a_DECLARED_condition_list_that_disagrees_with_the_derivation_is_REFUSED(
            self, release):
        _, args = release
        _rewrite(args, lambda d: d.update(expected_conditions=["Rest"]))
        assert failed(args, "DERIVED from the bound release")


class TestTheThreeBundlesAreONERelease:
    def test_a_bundle_id_the_release_does_not_cite_is_REFUSED(self, release):
        _, args = release
        def swap(d):
            d["bundles"][0]["arm_bundle_run_id"] = "deadbeefdeadbeef"
        _rewrite(args, swap)
        assert failed(args, "id is the one the release cites")

    def test_a_FORGED_scorer_view_on_the_release_is_REFUSED(self, release):
        # three bundles built from three program sets would be three measurements
        _, args = release
        _rewrite(args, lambda d: d.update(scorer_view_sha256="0" * 64))
        assert failed(args, "cites the SAME scorer view")

    def test_a_TAMPERED_release_document_fails_its_own_self_hash(self, release):
        _, args = release
        _rewrite(args, lambda d: d.update(n_logical_arms=999))
        assert failed(args, "SELF-HASHED")

    def test_a_release_that_ADMITS_ITSELF_is_REFUSED(self, release):
        _, args = release
        _rewrite(args, lambda d: d.update(
            verdict="ADMIT", admitted=True, self_admitted=True,
            verifier_id="spot.stage02.direct.all_arm_runner.v1"))
        assert failed(args, "did not admit its own release")

    def test_every_bundle_is_verified_IN_FULL_not_merely_counted(self, release):
        # an inventory says the bundles are present; it does not say any of them is true
        _, args = release
        doc = run(args)
        per = doc["bound_artifact"]["bundles"]
        assert len(per) == 3
        for entry in per:
            assert entry["report_sha256"] and entry["arm_bundle_run_id"]
        assert sum(1 for g in doc["gate_inventory"]
                   if "INDEPENDENTLY ADMITTED in full" in g) == 3
