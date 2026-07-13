"""The all-arm compatibility repair, and the frozen convergence-size domain it must respect.

WHY THIS FILE EXISTS
--------------------
1. `verify_pathway` required `pathway.json` — the LEGACY pair-scoped records file. The
   all-arm producer ships `arm_bundle.json` and never emitted one, so the verifier refused
   every honest bundle at `every_required_file_is_present` and then died in its own reporter
   on `KeyError: 'pathway_run_id'`. It failed CLOSED — it never false-admitted — but it could
   not admit anything either, and a crash is not a verdict.

2. The all-arm bundle ships NO signature bytes: one shared per-condition matrix serves all
   six bundles. So the reconstruction now loads the signatures from that matrix, binding it
   by hashes the VERIFIER recomputes from the arrow bytes.

3. The producer streams only SUPPORTIVE pair records now, declaring `n_intra_set_pairs` for
   all EVALUATED pairs. Nothing re-derived that denominator.

THE TRAP THIS FILE IS REALLY GUARDING
-------------------------------------
Re-deriving the denominator over EVERY set is wrong, and wrong in the direction that looks
right: the frozen size policy makes an OVERSIZED set contribute ZERO pairs, so a verifier
that paired every set would compute a LARGER denominator than the honest producer declared,
and would REFUSE A TRUE PRODUCTION BUNDLE. Worse, it would find real supportive pairs inside
a giant root that the producer never evaluated, and refuse the convergence claim too.

The synthetic fixture has 14 targets and cannot reach the 500-endpoint maximum, so it would
have passed either way. Reactome and GO contain roots that blow straight through it. The bug
would therefore have appeared for the first time on the real release — which is exactly the
class of bug that a fixture is supposed to catch and this one structurally could not.

So the domain is regressed here, directly, with a set that IS oversized.
"""
from __future__ import annotations

import os
import sys

import pytest

ANALYSIS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "analysis")
if ANALYSIS not in sys.path:
    sys.path.insert(0, ANALYSIS)
if os.path.join(ANALYSIS, "direct") not in sys.path:
    sys.path.insert(0, os.path.join(ANALYSIS, "direct"))

from direct import verify_pathway as VP  # noqa: E402
from direct import verify_reconstruct as RC  # noqa: E402
from direct import verify_signature_matrix as VSM  # noqa: E402

MAX = RC.SPEC_MAX_CONVERGENCE_SET_SIZE          # 500, the frozen maximum
N_GENES = 12                                    # > MIN_SHARED_GENES, so a cosine is defined


def _identical_signatures(targets):
    """Every target the same vector: EVERY pair would be supportive if it were evaluated.

    That is deliberate. If the size domain is ignored, an oversized set does not merely
    contribute a few stray pairs — it contributes a full clique and a convergence claim.
    """
    vec = {f"G{i}": 1.0 + i for i in range(N_GENES)}
    return {t: dict(vec) for t in targets}


class TestTheFrozenConvergenceSizeDomain:

    def test_an_OVERSIZED_set_contributes_ZERO_pairs(self):
        members = [f"T{i:04d}" for i in range(MAX + 1)]        # 501 measured endpoints
        sigs = _identical_signatures(members)

        pairs = RC.evaluated_pair_union({"BIG": members}, sigs)
        assert pairs == set(), (
            f"{len(pairs)} pairs were unioned from a set with {len(members)} measured "
            f"endpoints, which is over the frozen maximum of {MAX}. The producer evaluates "
            "NONE of them, so the re-derived denominator would exceed the honest declared "
            "one and REFUSE A TRUE BUNDLE")

    def test_an_OVERSIZED_set_can_never_be_convergent(self):
        members = [f"T{i:04d}" for i in range(MAX + 1)]
        conv = RC.converge(members, _identical_signatures(members))
        assert conv["n_measured"] == MAX + 1                  # still measured, still reported
        assert conv["n_supportive_pairs"] == 0
        assert conv["supporting"] == []
        assert conv["convergent"] is False
        assert conv["size"]["convergence_evaluable"] is False
        assert conv["size"]["convergence_size_disposition"] == RC.SIZE_TOO_LARGE
        assert conv["size"]["n_measured_convergence_endpoints"] == MAX + 1

    def test_a_set_AT_the_maximum_is_still_evaluable(self):
        """The boundary is INCLUSIVE. Off-by-one here silently drops real pathways."""
        members = [f"T{i:04d}" for i in range(3)]
        big = [f"S{i:04d}" for i in range(MAX)]
        sigs = _identical_signatures(members + big)

        assert RC.converge(big, sigs)["size"]["convergence_evaluable"] is True
        assert RC.converge(big, sigs)["convergent"] is True

    def test_the_denominator_counts_ONLY_the_in_domain_sets(self):
        """The union across a mixed bundle: the small set contributes, the root does not."""
        small = [f"T{i:04d}" for i in range(3)]
        oversized = [f"S{i:04d}" for i in range(MAX + 1)]
        sigs = _identical_signatures(small + oversized)

        pairs = RC.evaluated_pair_union({"SMALL": small, "BIG": oversized}, sigs)
        assert len(pairs) == 3                                # C(3,2), and nothing from BIG
        assert all(not (a.startswith("S") or b.startswith("S")) for a, b in pairs)

    def test_a_pair_shared_by_TWO_sets_is_evaluated_ONCE(self):
        """`n_intra_set_pairs` is a UNION, not a sum: the producer evaluates each pair once."""
        a = ["T0", "T1", "T2"]
        b = ["T1", "T2", "T3"]                                # (T1,T2) belongs to both
        sigs = _identical_signatures(["T0", "T1", "T2", "T3"])
        assert len(RC.evaluated_pair_union({"A": a, "B": b}, sigs)) == 5

    def test_the_verifier_holds_its_OWN_copy_of_the_frozen_policy(self):
        """Reimplemented, not imported from the producer — and not drifting internally.

        Two verifier-side copies of one constant is two things that can disagree, and a
        verifier disagreeing with itself is the last place a drift would ever be noticed.
        """
        assert RC.SPEC_MAX_CONVERGENCE_SET_SIZE == VSM.MAX_CONVERGENCE_SET_SIZE
        assert RC.SPEC_CONVERGENCE_SIZE_POLICY_ID == VSM.CONVERGENCE_SIZE_POLICY_ID
        assert RC.SPEC_CONVERGENCE_SIZE_BASIS == VSM.CONVERGENCE_SIZE_BASIS
        assert RC.SIZE_TOO_LARGE == VSM.SIZE_TOO_LARGE


class TestTheAllArmContract:

    def test_the_verifier_reads_the_ALL_ARM_contract(self):
        assert "arm_bundle.json" in VP.REQUIRED_FILES
        assert "convergence.json" in VP.REQUIRED_FILES
        assert "signature_ref.json" in VP.REQUIRED_FILES
        assert "pathway.json" not in VP.REQUIRED_FILES        # the legacy pair-scoped file

    def test_a_provenance_with_no_run_identity_REJECTS_and_does_not_CRASH(self, tmp_path):
        """It used to die on KeyError: 'pathway_run_id' inside its own reporter.

        A crash is not a verdict: a harness that reads the report gets nothing at all, and a
        harness that reads the exit code gets a refusal with no reason attached to it.
        """
        out = tmp_path / "empty_bundle"
        out.mkdir()
        report = VP.verify(out_dir=str(out))                  # presents NEITHER contract
        assert report["verdict"] == VP.REJECT
        assert report["pathway_run_id"] is None
        failed = {c["check"] for c in report["checks"] if c["status"] == VP.FAIL}
        assert VP.GATE_CONTRACT in failed, failed

    def test_a_bundle_MISSING_a_file_of_its_OWN_contract_is_named(self, tmp_path):
        """It presents the all-arm contract, so it is held to the all-arm file set."""
        out = tmp_path / "half_bundle"
        out.mkdir()
        (out / VP.ALL_ARM_RECORDS_FILE).write_text("{}")      # claims all-arm...
        report = VP.verify(out_dir=str(out))                  # ...and ships nothing else
        assert report["verdict"] == VP.REJECT
        failed = {c["check"] for c in report["checks"] if c["status"] == VP.FAIL}
        assert "every_required_file_is_present" in failed
        assert report["artifact_identity"]["contract"] == VP.CONTRACT_ALL_ARM

    def test_a_bundle_presenting_BOTH_contracts_is_refused(self, tmp_path):
        """Two records files is not a bundle two readers can share; it is two bundles, and
        whichever one the verifier picked, the other would go unchecked."""
        out = tmp_path / "both"
        out.mkdir()
        (out / VP.ALL_ARM_RECORDS_FILE).write_text("{}")
        (out / VP.LEGACY_RECORDS_FILE).write_text("{}")
        report = VP.verify(out_dir=str(out))
        assert report["verdict"] == VP.REJECT
        assert VP.GATE_CONTRACT in {c["check"] for c in report["checks"]
                                    if c["status"] == VP.FAIL}

    def test_the_new_gates_are_named(self):
        for gate in (VP.GATE_INTRA_SET_PAIRS, VP.GATE_CONVERGENCE_SIZE,
                     VP.GATE_CONVERGENCE_BOUND, VP.GATE_SET_AGREEMENT,
                     VP.GATE_PROVENANCE_USABLE):
            assert gate and isinstance(gate, str)
