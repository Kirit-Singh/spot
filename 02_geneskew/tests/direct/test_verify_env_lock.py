"""THE SOLVER-LOCK GATE: the environment is in the identity, and the pin is not negotiable.

A result whose environment is unrecorded cannot be reproduced, and one whose environment is
UNBOUND can be re-attributed to a different environment after the fact. So the Stage-2 solver
lock is hashed into the run identity — and this verifier re-derives it from the BYTES rather
than reading the number the artifact wrote down.

The decisive attack is the SELF-CONSISTENT FORGERY. Swap the lock, then honestly reseal the
artifact's `environment_lock` block so its `sha256`, its `expected_sha256` and its
`verified: true` all agree with each other, and reseal the run id so it re-derives. Nothing is
internally inconsistent — and it is still the wrong environment. Self-consistency is not
authenticity, so the only thing that can refuse it is a pin the artifact does not get a vote
on. That pin is a literal in the verifier, never imported from the producer's `envlock`.
"""
from __future__ import annotations

import json
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "analysis", "direct"))

import verify_arm_bundle as VB  # noqa: E402
import verify_arm_gates as G  # noqa: E402
import verify_arm_rules as AR  # noqa: E402
from direct import run_arms  # noqa: E402  (the PRODUCER — driven by the harness only)

import fixtures_direct as F  # noqa: E402  isort:skip

PINNED = "2983d140941f13d223dad93bae71434663882f23f25f6717c3debe59d2711abe"
LOCK = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "analysis", "stage02_solver_lock.txt")


def _args(bundle_dir, prod, **over):
    argv = ["--bundle", bundle_dir, "--de-main", prod.de_main, "--sgrna", prod.sgrna,
            "--by-guide", prod.by_guide, "--by-donors", prod.by_donors,
            "--guide-manifest", prod.guide_manifest, "--registry", prod.registry,
            "--condition", prod.condition, "--recompute", "all",
            "--env-lock", LOCK]
    for flag, attr in (("--source-registry", "source_registry"),
                       ("--pseudobulk", "pseudobulk")):
        value = getattr(prod, attr, None)
        if value:
            argv += [flag, value]
    ns = VB.build_parser().parse_args(argv)
    for k, v in over.items():
        setattr(ns, k, v)
    return ns


@pytest.fixture
def built(synthetic_run, tmp_path):
    def _build(**kw):
        prod = synthetic_run(**kw)
        prod.condition = F.CONDITION
        prod.env_lock = LOCK
        prod.out_root = str(tmp_path / f"arms{len(os.listdir(tmp_path))}")
        res = run_arms.build_bundle(prod)
        return res, _args(res["out_dir"], prod)
    return _build


def run(args) -> dict:
    return VB.verify(args).doc()


def failed(args, gate_substring: str) -> bool:
    doc = run(args)
    return (doc["verdict"] == "REFUSE"
            and any(gate_substring in g for g in doc["failed_gates"]))


def _reseal_lock(bundle_dir, lock_block):
    """Rewrite the bundle's bound lock block AND reseal the run id, so the forgery is
    internally perfect — nothing is left inconsistent for arithmetic to catch."""
    path = os.path.join(bundle_dir, VB.PROVENANCE_FILE)
    prov = json.load(open(path))
    prov["run_binding"]["environment_lock"] = lock_block
    full = AR.sha256_hex(AR.canonical_json(prov["run_binding"]))
    prov["arm_bundle_run_sha256"] = full
    prov["arm_bundle_run_id"] = full[:VB.BUNDLE_RUN_ID_LEN]
    prov["artifacts"] = [
        {"name": e["name"],
         "size_bytes": os.path.getsize(os.path.join(bundle_dir, e["name"])),
         "raw_sha256": AR.sha256_file(os.path.join(bundle_dir, e["name"]))}
        for e in prov.get("artifacts", [])]
    with open(path, "w") as fh:
        json.dump(prov, fh, indent=2, sort_keys=True)
        fh.write("\n")


class TestThePinIsTheVerifiersOwn:
    def test_the_pin_is_a_LITERAL_in_the_verifier_not_imported_from_the_producer(self):
        # a pin the checker borrowed from the thing it checks is a pin nobody checked: it
        # would move the instant the producer's constant moved
        assert G.PINNED_SOLVER_LOCK_SHA256 == PINNED
        source = open(os.path.join(
            os.path.dirname(os.path.abspath(G.__file__)),
            "verify_arm_gates.py")).read()
        # the pin is written out, in full, in the verifier's own bytes...
        assert PINNED in source
        # ...and the producer's lock module is never IMPORTED. (Naming it in a comment is
        # fine — what would be fatal is taking the constant from it.)
        assert not re.search(r"^\s*(?:from\s+\S*envlock|import\s+\S*envlock)", source,
                             re.M)

    def test_the_shipped_lock_on_disk_IS_the_pinned_lock(self):
        assert AR.sha256_file(LOCK) == PINNED


class TestTheHonestRunAdmits:
    def test_a_bundle_bound_to_the_PINNED_lock_ADMITS(self, built):
        _, args = built()
        doc = run(args)
        assert doc["verdict"] == "ADMIT", doc["failed_gates"]

    def test_the_lock_is_BOUND_into_the_verified_report_identity(self, built):
        _, args = built()
        bound = run(args)["bound_artifact"]
        assert bound["solver_lock_sha256"] == PINNED
        assert bound["solver_lock_pinned_sha256"] == PINNED

    def test_the_report_is_PER_RUN_and_content_addressed(self, built):
        # temporal anchors its DiD on these reports: two runs must not share a report id
        res_a, args_a = built()
        res_b, args_b = built(direction_a="low")
        a, b = run(args_a), run(args_b)
        assert a["report_sha256"] != b["report_sha256"]
        for doc in (a, b):
            body = {k: v for k, v in doc.items() if k != "report_sha256"}
            assert doc["report_sha256"] == AR.content_sha256(body)


class TestAMissingOrSwappedLockRefusesAtANamedGate:
    def test_a_MISSING_lock_REFUSES(self, built):
        _, args = built()
        args.env_lock = None
        assert failed(args, "solver lock is SUPPLIED to the verifier")

    def test_a_lock_that_is_not_on_DISK_REFUSES(self, built, tmp_path):
        _, args = built()
        args.env_lock = str(tmp_path / "nowhere.txt")
        assert failed(args, "solver lock is SUPPLIED to the verifier")

    def test_a_SWAPPED_lock_REFUSES(self, built, tmp_path):
        _, args = built()
        forged = tmp_path / "stage02_solver_lock.txt"
        forged.write_text("# not the pinned environment\nnumpy=1.0.0\n")
        args.env_lock = str(forged)
        assert failed(args, "hash to the hard-pinned Stage-2 lock")

    def test_the_STAGE_1_lock_is_refused_BY_NAME_not_as_a_hash_mismatch(self, built,
                                                                        tmp_path):
        # a valid solver lock — for a DIFFERENT environment. The lanes do not run the same
        # environment and their locks are not interchangeable.
        _, args = built()
        stage1 = tmp_path / "stage01_solver_lock.txt"
        stage1.write_text("# stage-1 environment (scvi_gpu, py3.11)\n")
        args.env_lock = str(stage1)
        doc = run(args)
        assert doc["verdict"] == "REFUSE"
        detail = next(g["detail"] for g in doc["gates"]
                      if "hard-pinned Stage-2 lock" in g["gate"])
        assert "STAGE-1 lock" in detail


class TestTheSelfConsistentForgeryIsStillRefused:
    """The decisive one. Everything agrees with everything; it is still the wrong
    environment. Only a pin the artifact does not get a vote on can refuse it."""

    def test_a_bundle_binding_a_DIFFERENT_lock_is_REFUSED_even_fully_RESEALED(self, built):
        res, args = built()
        forged_sha = "b928" + "0" * 60
        _reseal_lock(res["out_dir"], {
            "lock_id": "spot.stage02.solver_lock.v1",
            "name": "stage02_solver_lock.txt",
            "sha256": forged_sha,
            "expected_sha256": forged_sha,      # it agrees with ITSELF...
            "verified": True,                   # ...and declares itself verified
            "status": "locked",
        })
        assert failed(args, "IS the hard-pinned Stage-2 lock")

    def test_the_forged_run_id_STILL_re_derives_so_arithmetic_cannot_catch_it(self, built):
        # proving the forgery is internally perfect: the identity gate PASSES, and the run is
        # refused only by the pin
        res, args = built()
        forged_sha = "b928" + "0" * 60
        _reseal_lock(res["out_dir"], {
            "lock_id": "spot.stage02.solver_lock.v1",
            "name": "stage02_solver_lock.txt",
            "sha256": forged_sha, "expected_sha256": forged_sha,
            "verified": True, "status": "locked",
        })
        doc = run(args)
        assert doc["verdict"] == "REFUSE"
        assert "the run id RE-DERIVES from its own binding" not in doc["failed_gates"]

    def test_an_ARTIFACT_that_declares_its_OWN_expectation_is_REFUSED(self, built):
        # an artifact may not declare what it was supposed to be
        res, args = built()
        _reseal_lock(res["out_dir"], {
            "lock_id": "spot.stage02.solver_lock.v1",
            "name": "stage02_solver_lock.txt",
            "sha256": PINNED,
            "expected_sha256": "b928" + "0" * 60,
            "verified": True, "status": "locked",
        })
        assert failed(args, "own EXPECTATION is the hard pin")

    def test_a_bundle_that_binds_NO_lock_is_REFUSED(self, built):
        res, args = built()
        _reseal_lock(res["out_dir"], {})
        assert failed(args, "BINDS a solver lock into its run identity")

    def test_a_lock_block_that_disagrees_with_the_BYTES_on_disk_is_REFUSED(self, built):
        # the bound sha is the pin, but it is not the sha of the file the verifier hashed
        res, args = built()
        _reseal_lock(res["out_dir"], {
            "lock_id": "spot.stage02.solver_lock.v1",
            "name": "stage02_solver_lock.txt",
            "sha256": PINNED, "expected_sha256": PINNED,
            "verified": False,                  # it did not actually verify
            "status": "locked",
        })
        assert failed(args, "BINDS a solver lock into its run identity")
