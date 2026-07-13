"""A4 — the verifier RECOUNTS from the bound artifacts. It never reads a count from the record.

A3 made ``verify_pathway`` re-derive the coverage arithmetic. It re-derived it FROM THE
RECORD: ``target_source_coverage`` was checked against the record's own
``n_genes_in_target_universe / n_source_symbols``. Every number in that division came out of
the document under attack. So a forger edited the counts AND the ratios AND the dispositions
AND the leading edge in one consistent sweep, honestly resealed ``records_sha256``, and
promoted ``FX:UNMEASURED`` — a pathway with ZERO members in the perturbation-target universe,
whose genes were never perturbed and appear in no arm's ranking — to headline-rankable in
BOTH arms with an enrichment of 0.95. The verifier ADMITTED it, with n_failed = 0.

Internal consistency is not provenance. A count nobody can recount is a claim.

Every attack below is an HONEST-PRODUCER forgery: it reseals every self-hash it touches, so
content-addressing cannot catch it and only an independent RECOUNT can. Each must die at its
own named gate, and the valid fixture must still ADMIT.
"""
from __future__ import annotations

import json
import os

import pytest
from direct import run_pathway, verify_pathway
from direct.hashing import content_hash, file_sha256
from fixtures_pathway import write_gene_sets
from fixtures_spec import TARGET_GENES, UNIVERSE

# THE NAMED GATES, as literals. A test that imported them from the verifier would rename
# itself in step with a gate that had been quietly deleted.
GATE_EVIDENCE_PRESENT = "the_reconstruction_evidence_artifact_is_present"
GATE_EVIDENCE_BOUND = "the_reconstruction_evidence_hashes_to_the_run_binding"
GATE_SIGNATURES_BOUND = "the_masked_signature_artifact_hashes_to_the_run_binding"
GATE_BUNDLE_BOUND = "the_pinned_gene_set_bundle_is_shipped_inside_the_artifact"
GATE_BUNDLE_LOADS = "the_shipped_gene_set_bundle_loads_from_its_bundle_relative_path"
GATE_SOURCE_CACHE = "the_shipped_gene_set_copy_matches_the_original_source_cache"
SOURCE_BUNDLE_FILE = "gene_sets.source.json"
GATE_TARGET_UNIVERSE = "the_bound_target_universe_is_the_one_the_pinned_bundle_declares"
GATE_READOUT_UNIVERSE = "the_bound_readout_universe_is_the_one_the_pinned_bundle_declares"
GATE_TWO_UNIVERSES = "enrichment_tests_membership_in_the_perturbation_target_universe"
GATE_RANKING_IN_UNIVERSE = "every_ranked_target_lies_in_the_bound_target_universe"
GATE_SIGNATURES_IN_UNIVERSE = "every_signature_target_lies_in_the_bound_target_universe"

# the four DRIFT gates the audit asks for by name
GATE_RAW_HASH = "gene_set_raw_hash_mismatch"
GATE_RELEASE_IDENTITY = "gene_set_release_identity_mismatch"
GATE_FULL_MEMBERSHIP = "full_membership_mismatch"
GATE_TARGET_INTERSECTION = "target_intersection_count_mismatch"
GATE_RANKING_HITS = "ranking_hit_count_mismatch"

GATE_N_SOURCE = "n_source_genes_rederives_from_the_pinned_gene_set_bundle"
GATE_COVERAGE = "global_coverage_and_disposition_rederive_from_the_bound_artifacts"
GATE_ARM_ELIGIBILITY = "arm_eligibility_rederives_from_the_bound_artifacts"
GATE_LEADING_EDGE = "the_leading_edge_rederives_from_the_bound_arm_ranking"
GATE_ENRICHMENT = "the_enrichment_score_rederives_from_the_bound_arm_ranking"
GATE_CONVERGENCE = "convergence_support_rederives_from_the_bound_masked_signatures"
GATE_RUN_ID = "pathway_run_id_rederives_from_run_binding"

MEMBER_COUNT_MISMATCH = "gene_set_pathway_member_count_mismatch"

# FX:UNMEASURED's genes: readout-universe genes the release never perturbed. Its real
# perturbation-target coverage is 0/6, and no arm can ever rank one of them.
UNMEASURED = "FX:UNMEASURED"


@pytest.fixture
def artifact(synthetic_run):
    """A clean, ADMITTED pathway artifact, and the PINNED bundle on disk it is bound to."""
    from direct import run_screen as rs
    from direct import universe as uni

    args = synthetic_run()
    ctx = rs.prepare(args)
    tu = uni.target_universe(ctx["identities_by_condition"])
    args.gene_sets = write_gene_sets(
        os.path.dirname(args.de_main), UNIVERSE, list(TARGET_GENES),
        ctx["gene_universe"]["sha256"], target_universe_sha256=tu["sha256"])

    # THE HONEST CONTROL. The producer ships the pinned gene-set bytes byte-for-byte inside
    # the bundle (W18, 9d55c66), so the artifact is self-contained: the verifier recounts
    # from the shipped bytes alone, with nothing handed to it out of band.
    res = run_pathway.build_pathway(args)
    out = res["out_dir"]
    assert res["verification"]["verdict"] == verify_pathway.ADMIT, \
        [c["check"] for c in res["verification"]["checks"] if c["status"] == "fail"]
    assert os.path.exists(os.path.join(out, SOURCE_BUNDLE_FILE))
    with open(os.path.join(out, "pathway_provenance.json")) as fh:
        prov = json.load(fh)
    return out, prov, args.gene_sets


def _read(path):
    with open(path) as fh:
        return json.load(fh)


def _write(path, doc):
    with open(path, "w") as fh:
        json.dump(doc, fh)


def verify(out_dir, prov, _gene_sets=None):
    """The verifier loads the pinned release from INSIDE the artifact. Nothing else is needed."""
    return verify_pathway.verify(out_dir=out_dir, provenance=prov)


def shipped_bundle(out_dir):
    return os.path.join(out_dir, SOURCE_BUNDLE_FILE)


def reseal_run_id(out_dir, prov):
    """Recompute the run id from the binding, as an HONEST producer does.

    The run id IS the binding's sha256. A forger who edits the binding and leaves the id
    alone is caught by arithmetic, not by science — so every attack below reseals it too,
    and the recount is left as the only thing that can refuse them.
    """
    full = content_hash(prov["run_binding"])
    prov["pathway_run_id"] = full[:16]
    prov["pathway_run_sha256"] = full
    doc = _read(os.path.join(out_dir, "pathway.json"))
    doc["pathway_run_id"] = full[:16]
    for r in doc["records"]:
        r["pathway_run_id"] = full[:16]          # stripped before records_sha256
    _write(os.path.join(out_dir, "pathway.json"), doc)
    _write(os.path.join(out_dir, "pathway_provenance.json"), prov)
    return prov


def reseal_records(out_dir, prov, mutate):
    """Forge the records and RESEAL ``records_sha256`` honestly, as a real producer would."""
    doc = _read(os.path.join(out_dir, "pathway.json"))
    mutate(doc)
    stripped = [{k: v for k, v in r.items()
                 if k not in ("pathway_run_id", "pathway_method_sha256")}
                for r in doc["records"]]
    doc["records_sha256"] = content_hash(stripped)
    prov = json.loads(json.dumps(prov))
    prov["run_binding"]["records_sha256"] = doc["records_sha256"]
    _write(os.path.join(out_dir, "pathway.json"), doc)
    _write(os.path.join(out_dir, "pathway_provenance.json"), prov)
    return reseal_run_id(out_dir, prov)


def reseal_evidence(out_dir, prov, mutate):
    """Forge the EVIDENCE and reseal its canonical AND raw hashes. The hardest forgery.

    Content-addressing cannot catch this: the attacker owns the directory, so every hash
    inside it can be recomputed. Only the EXTERNAL pinned release can refuse it.
    """
    path = os.path.join(out_dir, "pathway_evidence.json")
    ev = _read(path)
    mutate(ev)
    _write(path, ev)
    prov = json.loads(json.dumps(prov))
    prov["run_binding"]["evidence_artifacts"]["pathway_evidence"]["canonical_sha256"] = \
        content_hash(ev)
    prov["evidence_artifacts"]["pathway_evidence"]["canonical_sha256"] = content_hash(ev)
    prov["evidence_artifacts"]["pathway_evidence"]["raw_sha256"] = file_sha256(path)
    _write(os.path.join(out_dir, "pathway_provenance.json"), prov)
    return reseal_run_id(out_dir, prov)


def failed(report):
    return {c["check"] for c in report["checks"] if c["status"] == verify_pathway.FAIL}


def detail(report, gate):
    return [c["detail"] for c in report["checks"] if c["check"] == gate][0]


def record(doc, set_id):
    return [r for r in doc["records"] if r["set_id"] == set_id][0]


def promote_unmeasured(doc):
    """The audit's exact forgery: a ZERO-coverage pathway, headline-rankable in BOTH arms.

    Every declared number is rewritten so that they all agree with each other. Coverage,
    disposition, arm eligibility, the score and the leading edge are internally perfect.
    """
    r = record(doc, UNMEASURED)
    genes = ["ENSG00000000104", "ENSG00000000105", "ENSG00000000106",
             "ENSG00000000107", "ENSG00000000108", "ENSG00000000109"]
    r["n_genes_in_target_universe"] = 6          # the lie. It is really 0.
    r["coverage"] = 1.0
    r["target_source_coverage"] = 1.0            # the lie. It is really 0.0.
    r["source_coverage"] = 1.0
    r["n_dropped_unmappable"] = 0
    r["global_coverage_disposition"] = "rankable"
    r["global_coverage_policy_passed"] = True
    for e in r["enrichment"].values():
        e["enrichment_value"] = 0.95
        e["n_hits_in_ranking"] = 6               # none of them is in ANY ranking
        e["leading_edge"] = list(genes)          # never perturbed, never ranked
        e["n_leading_edge"] = 6
        e["leading_edge_side"] = "top_leading_edge_at_or_before_the_positive_peak"
        e["arm_evaluable_source_coverage"] = 1.0
        e["global_target_source_coverage"] = 1.0
        e["arm_coverage_disposition"] = "rankable"
        e["arm_headline_rankable"] = True
        e["testable"] = True
        e["arm_undefined_reason"] = None
        e["undefined_reason"] = None
    return genes


# --------------------------------------------------------------------------- #
# 1. THE AUDIT'S ATTACK: the self-consistent, resealed zero-coverage promotion.
# --------------------------------------------------------------------------- #
class TestSelfConsistentZeroCoveragePromotion:

    def test_the_resealed_forgery_is_REJECTED(self, artifact):
        out, prov, gs = artifact
        prov = reseal_records(out, prov, promote_unmeasured)
        assert verify(out, prov)["verdict"] == verify_pathway.REJECT

    def test_it_dies_at_the_TARGET_INTERSECTION_gate(self, artifact):
        out, prov, gs = artifact
        prov = reseal_records(out, prov, promote_unmeasured)
        r = verify(out, prov)
        assert GATE_TARGET_INTERSECTION in failed(r)
        d = detail(r, GATE_TARGET_INTERSECTION)
        assert UNMEASURED in d and MEMBER_COUNT_MISMATCH in d

    def test_the_forged_ranking_hits_die_at_the_RANKING_HIT_gate(self, artifact):
        out, prov, gs = artifact
        prov = reseal_records(out, prov, promote_unmeasured)
        assert GATE_RANKING_HITS in failed(verify(out, prov))

    def test_content_addressing_CANNOT_catch_it_only_the_recount_can(self, artifact):
        # The forgery is internally perfect: every self-hash was resealed honestly, and the
        # record's own arithmetic is consistent with itself. That is the whole point.
        out, prov, gs = artifact
        prov = reseal_records(out, prov, promote_unmeasured)
        f = failed(verify(out, prov))
        assert "records_sha256_recomputes_from_the_emitted_records" not in f
        assert "coverage_and_per_arm_eligibility_rederive_from_the_record" not in f

    def test_the_RANKABILITY_DECISION_is_taken_on_the_RE_DERIVED_counts(self, artifact):
        # Not merely "the declared value disagrees" — the verifier states what the pathway
        # actually is: zero members, zero coverage, descriptive-only, not rankable.
        out, prov, gs = artifact
        prov = reseal_records(out, prov, promote_unmeasured)
        truth = verify(out, prov)["reconstruction"]["rederived"][UNMEASURED]
        assert truth["n_genes_in_target_universe"] == 0
        assert truth["target_source_coverage"] == 0.0
        assert truth["global_coverage_disposition"] == \
            "descriptive_only_low_source_coverage"
        assert truth["global_coverage_policy_passed"] is False
        for arm in ("away_from_A", "toward_B"):
            assert truth["enrichment"][arm]["n_hits_in_ranking"] == 0
            assert truth["enrichment"][arm]["arm_headline_rankable"] is False


# --------------------------------------------------------------------------- #
# 2. THE HARDEST FORGERY: reseal the EVIDENCE TOO. Only the pinned release refuses it.
# --------------------------------------------------------------------------- #
class TestSelfConsistentEvidenceReseal:
    """The attacker owns the directory, so they forge the evidence and re-hash it as well.

    Nothing inside the bundle can catch this — content-addressing proves an artifact is
    internally coherent, never that it is true. The PINNED GENE-SET BUNDLE is external, and
    it is the only thing in the chain the attacker does not own.
    """

    def _forge(self, out, prov, gs):
        genes = None

        def mutate_records(doc):
            nonlocal genes
            genes = promote_unmeasured(doc)

        prov = reseal_records(out, prov, mutate_records)

        def mutate_ev(ev):
            # give FX:UNMEASURED a full membership of real perturbed targets, and put them
            # in both arms' rankings at the top
            real = list(TARGET_GENES[:6])
            ev["membership"][UNMEASURED]["genes_target"] = sorted(real)
            ev["membership"][UNMEASURED]["declared_genes_in_target_universe"] = sorted(real)
            ev["membership"][UNMEASURED]["declared_n_genes_in_target_universe"] = 6
            ev["membership"][UNMEASURED]["n_genes_target"] = 6

        return reseal_evidence(out, prov, mutate_ev), genes

    def test_a_fully_resealed_evidence_forgery_is_STILL_REJECTED(self, artifact):
        out, prov, gs = artifact
        prov, _ = self._forge(out, prov, gs)
        r = verify(out, prov)
        assert r["verdict"] == verify_pathway.REJECT
        # the evidence is internally coherent — its own hashes were resealed
        assert GATE_EVIDENCE_BOUND not in failed(r)
        # ...and the PINNED RELEASE refuses it anyway
        assert GATE_FULL_MEMBERSHIP in failed(r)

    def test_the_counts_still_come_from_the_PINNED_BUNDLE_not_the_forged_evidence(
            self, artifact):
        out, prov, gs = artifact
        prov, _ = self._forge(out, prov, gs)
        r = verify(out, prov)
        assert GATE_TARGET_INTERSECTION in failed(r)
        assert r["reconstruction"]["rederived"][UNMEASURED][
            "n_genes_in_target_universe"] == 0


# --------------------------------------------------------------------------- #
# 3-6. FORGED MEMBERSHIP, RANKING HITS, LEADING EDGE, CONVERGENCE SUPPORT.
# --------------------------------------------------------------------------- #
class TestForgedSourceMembership:
    def test_a_forged_n_source_symbols_is_REJECTED_against_the_pinned_bundle(
            self, artifact):
        out, prov, gs = artifact

        def mutate(doc):
            # FX:SINGLE really has 5 source symbols and 1 target-universe member -> 0.2
            # coverage, descriptive-only. Shrink the DENOMINATOR to 2 and 1/2 clears the bar.
            r = record(doc, "FX:SINGLE")
            r["n_source_symbols"] = 2
            r["n_genes_in_set"] = 2
            r["target_source_coverage"] = 0.5
            r["source_coverage"] = 0.5
            r["n_dropped_unmappable"] = 1
            r["global_coverage_disposition"] = "rankable"
            r["global_coverage_policy_passed"] = True
            for e in r["enrichment"].values():
                e["n_source_symbols"] = 2
                e["global_target_source_coverage"] = 0.5

        prov = reseal_records(out, prov, mutate)
        r = verify(out, prov)
        assert r["verdict"] == verify_pathway.REJECT
        assert GATE_N_SOURCE in failed(r)
        assert MEMBER_COUNT_MISMATCH in detail(r, GATE_N_SOURCE)


class TestForgedRankingHits:
    def test_forged_n_hits_in_ranking_is_REJECTED(self, artifact):
        out, prov, gs = artifact

        def mutate(doc):
            # FX:SINGLE ranks ZERO members. Claim three — exactly the thin-arm bar.
            r = record(doc, "FX:SINGLE")
            r["n_genes_in_target_universe"] = 3
            r["target_source_coverage"] = 0.6
            r["source_coverage"] = 0.6
            r["n_dropped_unmappable"] = 2
            r["global_coverage_disposition"] = "rankable"
            r["global_coverage_policy_passed"] = True
            for e in r["enrichment"].values():
                e["enrichment_value"] = 0.8
                e["n_hits_in_ranking"] = 3
                e["leading_edge"] = ["ENSG00000000203"]
                e["n_leading_edge"] = 1
                e["leading_edge_side"] = \
                    "top_leading_edge_at_or_before_the_positive_peak"
                e["arm_evaluable_source_coverage"] = 0.6
                e["global_target_source_coverage"] = 0.6
                e["arm_coverage_disposition"] = "rankable"
                e["arm_headline_rankable"] = True
                e["testable"] = True
                e["arm_undefined_reason"] = None
                e["undefined_reason"] = None

        prov = reseal_records(out, prov, mutate)
        r = verify(out, prov)
        assert r["verdict"] == verify_pathway.REJECT
        assert GATE_RANKING_HITS in failed(r)


class TestForgedLeadingEdge:
    def test_a_forged_leading_edge_is_REJECTED(self, artifact):
        out, prov, gs = artifact

        def mutate(doc):
            # FX:DIVERGENT/away_from_A really names three members at the bottom. Drop one.
            # Still non-empty, still members-only, still the right side, and the count still
            # agrees with the list: every M1 check passes. Only the RANKING knows better.
            e = record(doc, "FX:DIVERGENT")["enrichment"]["away_from_A"]
            e["leading_edge"] = e["leading_edge"][:-1]
            e["n_leading_edge"] = len(e["leading_edge"])

        prov = reseal_records(out, prov, mutate)
        r = verify(out, prov)
        assert r["verdict"] == verify_pathway.REJECT
        assert GATE_LEADING_EDGE in failed(r)
        assert "a_defined_enrichment_always_names_a_non_empty_edge" not in failed(r)


class TestForgedConvergenceSupport:
    def test_a_forged_support_count_is_REJECTED(self, artifact):
        out, prov, gs = artifact

        def mutate(doc):
            c = record(doc, "FX:CONVERGENT")["convergence"]
            keep = c["supporting_perturbations"][:2]
            c["supporting_perturbations"] = keep
            c["n_supporting_perturbations"] = 2          # the bound signatures support 3
            c["intra_set_components"] = [keep]
            c["n_intra_set_components"] = 1
            c["pairwise_support"] = [p for p in c["pairwise_support"]
                                     if p["target_a"] in keep and p["target_b"] in keep]
            c["n_supportive_pairs"] = len(c["pairwise_support"])

        prov = reseal_records(out, prov, mutate)
        r = verify(out, prov)
        assert r["verdict"] == verify_pathway.REJECT
        assert GATE_CONVERGENCE in failed(r)
        # the B1 membership rules still pass: the lie is arithmetic, not routing
        assert "no_convergence_claim_rests_on_a_non_member" not in failed(r)
        assert "convergence_verdict_follows_the_frozen_rule" not in failed(r)


# --------------------------------------------------------------------------- #
# 7. THE WRONG UNIVERSE (B1). Membership belongs to the PERTURBATION-TARGET universe.
# --------------------------------------------------------------------------- #
class TestWrongUniverse:
    def test_a_target_universe_that_is_really_the_READOUT_universe_is_REJECTED(
            self, artifact):
        out, prov, gs = artifact

        def mutate_ev(ev):
            # Swap the perturbed population for the measured one — the exact B1 bug. The
            # forger reseals the universe's own declared hash too, so the ONLY thing that
            # can refuse this is the universe the PINNED BUNDLE was built against.
            ev["target_universe"] = list(ev["readout_universe"])
            ev["target_universe_sha256"] = content_hash(
                sorted(set(ev["readout_universe"])))

        prov = reseal_evidence(out, prov, mutate_ev)
        prov["run_binding"]["target_universe_sha256"] = content_hash(
            sorted(set(_read(os.path.join(out, "pathway_evidence.json"))
                       ["readout_universe"])))
        prov = reseal_run_id(out, prov)

        r = verify(out, prov)
        assert r["verdict"] == verify_pathway.REJECT
        assert GATE_TARGET_UNIVERSE in failed(r)

    def test_the_clean_artifact_keeps_the_two_universes_apart(self, artifact):
        out, prov, gs = artifact
        r = verify(out, prov)
        assert GATE_TWO_UNIVERSES not in failed(r)
        rec = r["reconstruction"]
        assert rec["target_universe_sha256"] != rec["readout_universe_sha256"]


# --------------------------------------------------------------------------- #
# 8-9. THE PINNED BUNDLE ON DISK. The caller's object is not the subject of verification.
# --------------------------------------------------------------------------- #
class TestAlteredGeneSetBytesWithACleanCallerObject:
    def test_it_is_REJECTED_at_the_RAW_HASH_gate(self, artifact):
        out, prov, gs = artifact
        doc = _read(shipped_bundle(out))
        # Give FX:UNMEASURED a real perturbation target so it would recount as covered.
        # Still valid JSON, still a loadable bundle — different bytes.
        for s in doc["sets"]:
            if s["set_id"] == UNMEASURED:
                s["genes"].append(TARGET_GENES[0])
        _write(shipped_bundle(out), doc)

        r = verify(out, prov)                          # pristine caller provenance
        assert r["verdict"] == verify_pathway.REJECT
        assert GATE_RAW_HASH in failed(r)

    def test_the_ORIGINAL_cache_still_disagrees_with_the_tampered_copy(self, artifact):
        # The optional second opinion: an auditor with their own copy of the release.
        out, prov, gs = artifact
        doc = _read(shipped_bundle(out))
        for s in doc["sets"]:
            if s["set_id"] == UNMEASURED:
                s["genes"].append(TARGET_GENES[0])
        _write(shipped_bundle(out), doc)

        r = verify_pathway.verify(out_dir=out, provenance=prov, gene_sets_path=gs)
        assert r["verdict"] == verify_pathway.REJECT
        assert GATE_SOURCE_CACHE in failed(r)


class TestArbitraryBytesUnderTheExpectedFilename:
    def test_it_is_REJECTED_and_never_parsed_into_a_recount(self, artifact):
        out, prov, _gs = artifact
        with open(shipped_bundle(out), "w") as fh:
            fh.write("not a gene set bundle, not even JSON\n")

        r = verify(out, prov)
        assert r["verdict"] == verify_pathway.REJECT
        assert GATE_BUNDLE_LOADS in failed(r)
        assert r["reconstruction"]["reconstructed"] is False


class TestAMissingOrUnanchoredArtifactRefuses:
    """Fail-closed: what cannot be independently recounted is not admitted."""

    def test_a_deleted_evidence_artifact_is_REJECTED_not_skipped(self, artifact):
        out, prov, gs = artifact
        os.remove(os.path.join(out, "pathway_evidence.json"))
        r = verify(out, prov)
        assert r["verdict"] == verify_pathway.REJECT
        assert GATE_EVIDENCE_PRESENT in failed(r)

    def test_a_deleted_signature_artifact_is_REJECTED(self, artifact):
        out, prov, gs = artifact
        os.remove(os.path.join(out, "pathway_signatures.parquet"))
        r = verify(out, prov)
        assert r["verdict"] == verify_pathway.REJECT
        assert GATE_SIGNATURES_BOUND in failed(r)

    def test_NO_shipped_pinned_bundle_means_NO_admission(self, artifact):
        # Membership that is only what the artifact SAYS it is has not been verified.
        out, prov, _gs = artifact
        os.remove(shipped_bundle(out))
        r = verify(out, prov)
        assert r["verdict"] == verify_pathway.REJECT
        assert GATE_BUNDLE_BOUND in failed(r)

    def test_a_tampered_evidence_artifact_that_is_NOT_resealed_is_REJECTED(self, artifact):
        out, prov, gs = artifact
        path = os.path.join(out, "pathway_evidence.json")
        ev = _read(path)
        ev["arm_rankings"]["away_from_A"].append(
            {"target_id": "ENSG00000000104", "score": 99.0, "rank": 0})
        _write(path, ev)
        r = verify(out, prov)
        assert r["verdict"] == verify_pathway.REJECT
        assert GATE_EVIDENCE_BOUND in failed(r)
        assert GATE_RANKING_IN_UNIVERSE in failed(r)


class TestAStaleOrForgedRunId:
    """The run id IS the binding's sha256. It is recomputed, never read."""

    def test_a_binding_edited_without_reissuing_the_run_id_is_REJECTED(self, artifact):
        # The forger swaps the bound evidence hash to match a forged evidence file and
        # honestly reseals every document INSIDE the bundle — but keeps the run id, because
        # the run id is the name Stage 3 already cites. The binding no longer hashes to it.
        out, prov, _gs = artifact
        stale_id = prov["pathway_run_id"]

        path = os.path.join(out, "pathway_evidence.json")
        ev = _read(path)
        ev["membership"][UNMEASURED]["genes_target"] = sorted(TARGET_GENES[:6])
        _write(path, ev)
        prov["run_binding"]["evidence_artifacts"]["pathway_evidence"][
            "canonical_sha256"] = content_hash(ev)
        prov["evidence_artifacts"]["pathway_evidence"]["canonical_sha256"] = \
            content_hash(ev)
        prov["evidence_artifacts"]["pathway_evidence"]["raw_sha256"] = file_sha256(path)
        _write(os.path.join(out, "pathway_provenance.json"), prov)   # run id left ALONE

        r = verify(out, prov)
        assert r["verdict"] == verify_pathway.REJECT
        assert GATE_RUN_ID in failed(r)
        # the documents inside the bundle are internally perfect; only the id betrays it
        assert GATE_EVIDENCE_BOUND not in failed(r)
        assert prov["pathway_run_id"] == stale_id

    def test_an_INVENTED_run_id_is_REJECTED(self, artifact):
        out, prov, _gs = artifact
        prov["pathway_run_id"] = "0" * 16
        prov["pathway_run_sha256"] = "0" * 64
        doc = _read(os.path.join(out, "pathway.json"))
        for rec in doc["records"]:
            rec["pathway_run_id"] = "0" * 16
        _write(os.path.join(out, "pathway.json"), doc)
        _write(os.path.join(out, "pathway_provenance.json"), prov)

        r = verify(out, prov)
        assert r["verdict"] == verify_pathway.REJECT
        assert GATE_RUN_ID in failed(r)

    def test_the_clean_artifacts_id_DOES_follow_its_binding(self, artifact):
        out, prov, _gs = artifact
        r = verify(out, prov)
        assert GATE_RUN_ID not in failed(r)
        assert prov["pathway_run_id"] == content_hash(prov["run_binding"])[:16]


# --------------------------------------------------------------------------- #
# 10. THE VALID FIXTURE STILL ADMITS — and every firewall is still up.
# --------------------------------------------------------------------------- #
class TestTheValidArtifactAdmits:
    def test_it_admits_with_no_failed_check(self, artifact):
        out, prov, gs = artifact
        r = verify(out, prov)
        assert r["verdict"] == verify_pathway.ADMIT, sorted(failed(r))
        assert r["n_failed"] == 0

    def test_every_recount_gate_actually_RAN(self, artifact):
        out, prov, gs = artifact
        names = {c["check"] for c in verify(out, prov)["checks"]}
        for gate in (GATE_EVIDENCE_PRESENT, GATE_EVIDENCE_BOUND, GATE_SIGNATURES_BOUND,
                     GATE_BUNDLE_BOUND, GATE_BUNDLE_LOADS, GATE_RAW_HASH,
                     GATE_RELEASE_IDENTITY, GATE_FULL_MEMBERSHIP, GATE_TARGET_UNIVERSE,
                     GATE_READOUT_UNIVERSE, GATE_TWO_UNIVERSES, GATE_RANKING_IN_UNIVERSE,
                     GATE_SIGNATURES_IN_UNIVERSE, GATE_N_SOURCE, GATE_TARGET_INTERSECTION,
                     GATE_COVERAGE, GATE_RANKING_HITS, GATE_ARM_ELIGIBILITY,
                     GATE_ENRICHMENT, GATE_LEADING_EDGE, GATE_CONVERGENCE,
                     GATE_RUN_ID):
            assert gate in names, f"gate never ran: {gate}"

    def test_the_report_names_the_release_it_recounted_against(self, artifact):
        # An auditor must be able to compare the release the verifier stood on against the
        # release that was published.
        out, prov, gs = artifact
        rec = verify(out, prov)["reconstruction"]
        assert rec["bundle_anchor"] == "verified_against_the_pinned_release"
        assert rec["membership_source"] == "pinned_gene_set_bundle"
        assert len(rec["gene_set_bundle_sha256"]) == 64
        assert rec["gene_set_release"]["source"] == "fixture"
        assert rec["emitted_membership_form"] == "full_mapped_membership"
        # BUNDLE-RELATIVE. No absolute path may enter the artifact or the report.
        assert rec["gene_set_bundle_path_in_bundle"] == SOURCE_BUNDLE_FILE
        assert not os.path.isabs(rec["gene_set_bundle_path_in_bundle"])
        assert "/" not in json.dumps(rec.get("gene_set_release", {}))

    def test_the_shipped_copy_matches_the_original_source_cache(self, artifact):
        out, prov, gs = artifact
        r = verify_pathway.verify(out_dir=out, provenance=prov, gene_sets_path=gs)
        assert r["verdict"] == verify_pathway.ADMIT
        assert GATE_SOURCE_CACHE not in failed(r)

    def test_the_no_pq_firewall_still_holds(self, artifact):
        out, prov, gs = artifact
        path = os.path.join(out, "pathway.json")
        doc = _read(path)
        doc["records"][0]["empirical_p_value"] = 0.01
        _write(path, doc)
        r = verify(out, prov)
        assert r["verdict"] == verify_pathway.REJECT
        assert "no_forbidden_key_at_any_depth" in failed(r)

    def test_the_arms_stay_independent_and_are_never_combined(self, artifact):
        out, _prov, _gs = artifact
        doc = _read(os.path.join(out, "pathway.json"))
        assert doc["method"]["evidence_lines_are_combined"] is False
        assert doc["method"]["combined_arm_eligibility_permitted"] is False
        # FX:DIVERGENT: one arm defined and rankable, the other undefined. Two verdicts from
        # one record — and no Pareto tier, no concordance class, no combined score anywhere.
        arms = record(doc, "FX:DIVERGENT")["enrichment"]
        assert arms["away_from_A"]["arm_headline_rankable"] is True
        assert arms["toward_B"]["arm_headline_rankable"] is False
        blob = json.dumps(doc).lower()
        for banned in ("pareto", "concordance", "combined_score", "p_value", "q_value",
                       "fdr"):
            assert banned not in blob

    def test_exactly_three_ranked_members_IS_rankable_on_a_REAL_record(self, artifact):
        # The inclusive boundary, on a record that genuinely has 3 hits and 3/5 coverage —
        # not on a forged one.
        out, prov, gs = artifact
        truth = verify(out, prov)["reconstruction"]["rederived"]["FX:CONVERGENT"]
        assert truth["n_source_symbols"] == 5
        assert truth["n_genes_in_target_universe"] == 3
        assert truth["enrichment"]["away_from_A"]["n_hits_in_ranking"] == 3
        assert truth["enrichment"]["away_from_A"]["arm_headline_rankable"] is True
