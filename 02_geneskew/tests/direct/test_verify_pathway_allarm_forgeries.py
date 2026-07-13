"""The all-arm gates BITE: four coherently resealed forgeries, four named refusals.

A forgery that merely corrupts a hash proves nothing except that sha256 works. Each forgery
below is rebuilt THROUGH THE PRODUCER'S OWN CODE, so every hash, every content address and
the run id itself are recomputed honestly and agree with one another perfectly. Nothing is
inconsistent. The artifact is a lie that is internally beyond reproach.

Only a verifier that RE-DERIVES the claim from the bound signatures can see it — and the test
asserts WHICH named gate saw it, because a forgery caught by the wrong gate (a hash mismatch,
a schema slip) is a coincidence, not a defence.

And the honest bundle must ADMIT first. A verifier that refuses everything refuses forgeries
too; every refusal below would be vacuous without the admission above it. That is exactly how
the previous verifier looked green while admitting nothing at all.
"""
from __future__ import annotations

import copy
import json
import os
import sys

import pytest
from fixtures_pathway import gene_set_doc
from fixtures_spec import TARGET_GENES, UNIVERSE

ANALYSIS = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "analysis")
for p in (ANALYSIS, os.path.join(ANALYSIS, "direct")):
    if p not in sys.path:
        sys.path.insert(0, p)

from direct import verify_pathway as VP  # noqa: E402

COND = "Rest"
SOURCE = "reactome"

CONVERGENCE_GATE = VP.GATE_CONVERGENCE      # support re-derives from the bound signatures
DENOMINATOR_GATE = VP.GATE_INTRA_SET_PAIRS  # the STREAMED evaluated-pair denominator
FROZEN_RULE_GATE = "convergence_verdict_follows_the_frozen_rule"


def _powered_specs():
    """One member of the divergent set gets an INVERTED effect.

    Without it every evaluated pair comes out supportive, `n_intra_set_pairs` equals the
    supportive count, and the denominator test cannot tell a true denominator from a shrunken
    one. A fixture that cannot fail is not a fixture.
    """
    import dataclasses

    from fixtures_direct import default_specs
    out = []
    for s in default_specs():
        if s.target == TARGET_GENES[5]:
            s = dataclasses.replace(
                s, a_effect=-(s.a_effect or 2.0), b_effect=-(s.b_effect or 0.0) or 2.0)
        out.append(s)
    return out


@pytest.fixture
def prepared(synthetic_run, tmp_path):
    from direct import genesets
    from direct import run_screen as rs
    from direct import signature_matrix as sm
    from direct import universe as uni

    args = synthetic_run(specs=_powered_specs(), conditions=(COND,))
    ctx = rs.prepare_bundle(args, cond=COND)
    tu = uni.target_universe(ctx["identities_by_condition"])

    doc = gene_set_doc(UNIVERSE, list(TARGET_GENES), ctx["gene_universe"]["sha256"],
                       tu["sha256"])
    doc["release"] = {"source": SOURCE, "release_id": f"{SOURCE}-2026-07-01",
                      "license": genesets.SOURCE_LICENSE[SOURCE],
                      "license_reference": genesets.SOURCE_LICENSE_REFERENCE[SOURCE]}
    gs_path = os.path.join(os.path.dirname(args.de_main), f"gene_sets.{SOURCE}.json")
    with open(gs_path, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)

    args.gene_sets = gs_path
    args.condition = COND
    args.out_root = str(tmp_path / "pw")
    args.signature_matrix_root = str(tmp_path / "sig")
    args.env_lock = os.path.join(ANALYSIS, "stage02_solver_lock.txt")
    args.convergence_workers = 2          # the fork pool, as production runs it
    args.convergence_chunk_size = 3
    sm.build_condition(args, COND, args.signature_matrix_root)
    return args


def _verify(args, out_dir):
    return VP.verify(out_dir=out_dir, gene_sets_path=args.gene_sets,
                     signature_matrix_root=args.signature_matrix_root)


def _failed(report):
    return {c["check"] for c in report["checks"] if c["status"] == VP.FAIL}


@pytest.fixture
def honest(prepared, tmp_path):
    from direct import run_pathway_arms as rpa
    return prepared, rpa.build_pathway_arms(prepared)["out_dir"]


def _reseal(args, out_root, corrupt):
    """A COMPLETE bundle whose convergence claim is false and whose every hash, id and
    binding is nonetheless computed honestly by the producer's own code."""
    from direct import pathway_arms
    from direct import run_pathway_arms as rpa

    from direct.hashing import content_hash
    real = pathway_arms.convergence_artifact

    def forged(**kw):
        doc = copy.deepcopy(real(**kw))
        corrupt(doc)
        # RESEAL. Without this the artifact's own `convergence_sha256` is stale and the
        # forgery dies on a HASH — which proves sha256 works and nothing whatsoever about
        # whether the science was recomputed. Recomputing it exactly as the producer does
        # makes the lie internally perfect: the artifact hashes to itself, the bundle names
        # that hash, the binding names it, and the run id follows from the binding.
        doc["convergence_sha256"] = content_hash(
            {k: v for k, v in doc.items() if k != "convergence_sha256"})
        return doc

    pathway_arms.convergence_artifact = forged
    try:
        a = copy.deepcopy(args)
        a.out_root = out_root
        return rpa.build_pathway_arms(a)["out_dir"]
    finally:
        pathway_arms.convergence_artifact = real


def _set_with_support(doc):
    for s in doc["sets"]:
        if s["n_supportive_pairs"] > 0:
            return s
    raise AssertionError("the fixture produced no supportive pair to forge with")


class TestTheHonestBundleIsAdmitted:
    """Without this, every refusal below is vacuous."""

    def test_the_honest_all_arm_bundle_ADMITS(self, honest):
        args, out_dir = honest
        report = _verify(args, out_dir)
        assert report["verdict"] == VP.ADMIT, sorted(_failed(report))

    def test_the_gates_that_matter_actually_RAN(self, honest):
        """ADMIT is worthless if the gate that should have looked was never reached."""
        args, out_dir = honest
        ran = {c["check"] for c in _verify(args, out_dir)["checks"]}
        for gate in (CONVERGENCE_GATE, DENOMINATOR_GATE, FROZEN_RULE_GATE,
                     VP.GATE_CONVERGENCE_SIZE, VP.GATE_CONVERGENCE_BOUND,
                     VP.GATE_SET_AGREEMENT, VP.GATE_RUN_ID):
            assert gate in ran, f"{gate} never ran"

    def test_the_bundle_ships_NO_signature_bytes_and_is_still_recomputable(self, honest):
        """The whole point of the shared matrix: no bytes in the bundle, and still checkable."""
        args, out_dir = honest
        assert not os.path.exists(os.path.join(out_dir, "pathway_signatures.parquet"))
        assert _verify(args, out_dir)["reconstruction"]["reconstructed"] is True

    def test_WITHOUT_the_shared_matrix_it_REFUSES_rather_than_taking_its_word(self, honest):
        """Fail-closed: a convergence claim nobody can recompute is not admitted."""
        args, out_dir = honest
        report = VP.verify(out_dir=out_dir, gene_sets_path=args.gene_sets)
        assert report["verdict"] == VP.REJECT
        assert "the_shared_signature_matrix_was_supplied_to_the_verifier" in _failed(report)


class TestTheGatesBite:

    def test_an_INFLATED_supportive_count_is_refused(self, prepared, tmp_path):
        def corrupt(doc):
            _set_with_support(doc)["n_supportive_pairs"] += 1
        report = _verify(prepared, _reseal(prepared, str(tmp_path / "f1"), corrupt))
        assert report["verdict"] == VP.REJECT
        assert CONVERGENCE_GATE in _failed(report), sorted(_failed(report))

    def test_a_SELF_CONSISTENTLY_deleted_supportive_pair_is_refused(self, prepared,
                                                                    tmp_path):
        """Drop a REAL supportive pair and decrement the count, so the artifact agrees with
        itself perfectly. Only re-derivation from the signatures can see the pair is missing."""
        def corrupt(doc):
            s = _set_with_support(doc)
            s["pairwise_support"].pop()
            s["n_supportive_pairs"] -= 1
        report = _verify(prepared, _reseal(prepared, str(tmp_path / "f2"), corrupt))
        assert report["verdict"] == VP.REJECT
        assert CONVERGENCE_GATE in _failed(report), sorted(_failed(report))

    def test_a_FORGED_evaluated_pair_DENOMINATOR_is_refused(self, prepared, tmp_path):
        """The streamed denominator. Nothing re-derived it before this repair."""
        def corrupt(doc):
            doc["n_intra_set_pairs"] = doc["n_intra_set_pairs"] * 7 + 13
        report = _verify(prepared, _reseal(prepared, str(tmp_path / "f3"), corrupt))
        assert report["verdict"] == VP.REJECT
        assert DENOMINATOR_GATE in _failed(report), sorted(_failed(report))

    def test_a_FLIPPED_convergence_verdict_is_refused(self, prepared, tmp_path):
        def corrupt(doc):
            for s in doc["sets"]:
                if not s["convergent"]:
                    s["convergent"] = True
                    return
            raise AssertionError("the fixture has no non-convergent set to flip")
        report = _verify(prepared, _reseal(prepared, str(tmp_path / "f4"), corrupt))
        assert report["verdict"] == VP.REJECT
        failed = _failed(report)
        assert CONVERGENCE_GATE in failed or FROZEN_RULE_GATE in failed, sorted(failed)

    def test_a_FORGED_convergence_SIZE_domain_is_refused(self, prepared, tmp_path):
        """Raise the artifact's own maximum, and an oversized root could be paired and called
        convergent. The verifier holds its OWN copy of the frozen policy for this reason."""
        def corrupt(doc):
            doc["max_convergence_set_size"] = 10_000
            for s in doc["sets"]:
                s["max_convergence_set_size"] = 10_000
        report = _verify(prepared, _reseal(prepared, str(tmp_path / "f5"), corrupt))
        assert report["verdict"] == VP.REJECT
        assert VP.GATE_CONVERGENCE_SIZE in _failed(report), sorted(_failed(report))

    def test_an_ORPHAN_convergence_claim_is_refused(self, prepared, tmp_path):
        """A convergence claim about a pathway NO record emits and the release does not
        contain. Every other gate iterates the RECORDS, so not one of them would ever look
        at it — it would ride into Stage 3 unexamined."""
        def corrupt(doc):
            ghost = copy.deepcopy(doc["sets"][0])
            ghost["set_id"] = "FX:GHOST"
            doc["sets"].append(ghost)
        report = _verify(prepared, _reseal(prepared, str(tmp_path / "f6"), corrupt))
        assert report["verdict"] == VP.REJECT
        assert VP.GATE_SET_IDS_AGREE in _failed(report), sorted(_failed(report))


class TestDeletingTheDenominatorDoesNotDisableTheGate:
    """The `X is None or ...` family. A check that a forger can switch off by DELETING the
    thing it compares against is not a check — it is a courtesy. Each attack below removes a
    bound count and reseals; the bundle stays perfectly coherent and must still be refused."""

    def test_DELETING_the_bound_set_count_is_refused(self, prepared, tmp_path):
        from direct import pathway_evidence
        real = pathway_evidence.gene_set_source_block

        def forged(*a, **kw):
            block = copy.deepcopy(real(*a, **kw))
            block["gene_set_release"].pop("n_sets", None)      # completeness has no yardstick
            return block

        pathway_evidence.gene_set_source_block = forged
        try:
            from direct import run_pathway_arms as rpa
            args = copy.deepcopy(prepared)
            args.out_root = str(tmp_path / "d1")
            out_dir = rpa.build_pathway_arms(args)["out_dir"]
        finally:
            pathway_evidence.gene_set_source_block = real

        report = _verify(prepared, out_dir)
        assert report["verdict"] == VP.REJECT
        assert "every_gene_set_in_the_bundle_is_emitted" in _failed(report), \
            sorted(_failed(report))

    def test_DELETING_the_expected_arm_slot_count_is_refused(self, prepared, tmp_path):
        from direct import pathway_arms
        real = pathway_arms.expected_slots

        def forged(*a, **kw):
            return None                                       # arm completeness has no yardstick

        pathway_arms.expected_slots = forged
        try:
            from direct import run_pathway_arms as rpa
            args = copy.deepcopy(prepared)
            args.out_root = str(tmp_path / "d2")
            out_dir = rpa.build_pathway_arms(args)["out_dir"]
        finally:
            pathway_arms.expected_slots = real

        report = _verify(prepared, out_dir)
        assert report["verdict"] == VP.REJECT
        assert "enrichment_is_emitted_per_arm_never_across_arms" in _failed(report), \
            sorted(_failed(report))


class TestTheRefusalsAreSCIENTIFIC_notIncidental:
    """A forgery that dies on a missing file, a schema slip or a hash mismatch tells us
    nothing about whether the SCIENCE was recomputed. So for each attack, the structural
    gates must still PASS — the bundle is coherent — and the refusal must come from the
    re-derivation alone."""

    STRUCTURAL = ("every_required_file_is_present", "shipped_documents_load_from_disk",
                  "no_forbidden_key_at_any_depth", "the_provenance_we_verified_is_the_"
                  "provenance_we_hashed", VP.GATE_RUN_ID,
                  "records_sha256_recomputes_from_the_emitted_records",
                  VP.GATE_CONVERGENCE_BOUND)

    @pytest.mark.parametrize("name,corrupt,gate", [
        ("inflated_support",
         lambda d: d["sets"].__setitem__(
             0, dict(d["sets"][0],
                     n_supportive_pairs=d["sets"][0]["n_supportive_pairs"] + 1))
         if d["sets"][0]["n_supportive_pairs"] else None, CONVERGENCE_GATE),
        ("forged_denominator",
         lambda d: d.__setitem__("n_intra_set_pairs",
                                 d["n_intra_set_pairs"] * 7 + 13), DENOMINATOR_GATE),
    ])
    def test_the_forgery_passes_EVERY_structural_gate_and_dies_on_the_SCIENCE(
            self, prepared, tmp_path, name, corrupt, gate):
        report = _verify(prepared, _reseal(prepared, str(tmp_path / name), corrupt))
        failed = _failed(report)
        assert report["verdict"] == VP.REJECT
        for structural in self.STRUCTURAL:
            assert structural not in failed, (
                f"the forgery was caught by {structural}, a STRUCTURAL gate. That proves "
                "sha256 works, not that the claim was recomputed")
        assert failed == {gate}, failed
