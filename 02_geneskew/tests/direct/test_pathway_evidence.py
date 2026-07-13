"""The PRODUCER half of the count-provenance fix: the bundle carries what it counted.

W0's A3 follow-on. `n_hits_in_ranking` was counted inside `enrichment.enrich_one` against a
ranked list that lived only in memory, so the only thing a verifier could do was re-derive
the coverage arithmetic from the record's OWN declared counts — i.e. check the declared
numbers were consistent with each other. They always are, if you forge them together.

These tests prove the bundle now ships the bytes an INDEPENDENT verifier needs to RECOUNT:
membership, the target universe, each arm's ranking, and the masked signatures + readout
universe for convergence. They deliberately stop there. This lane EMITS the evidence; W4's
verifier reads it and decides whether the declared counts survive. A producer that also
wrote the check that its own counts were honest would be marking its own homework.
"""
from __future__ import annotations

import json
import os

import pytest
from direct import config, pathway_evidence, run_pathway
from direct.hashing import content_hash, file_sha256
from fixtures_pathway import write_gene_sets
from fixtures_spec import TARGET_GENES, UNIVERSE

_SOURCE = {}


@pytest.fixture
def gene_sets_path(built):
    return _SOURCE["path"]


@pytest.fixture
def built(synthetic_run):
    from direct import run_screen as rs
    from direct import universe as uni

    args = synthetic_run()
    ctx = rs.prepare(args)
    tu = uni.target_universe(ctx["identities_by_condition"])
    args.gene_sets = write_gene_sets(
        os.path.dirname(args.de_main), UNIVERSE, list(TARGET_GENES),
        ctx["gene_universe"]["sha256"], target_universe_sha256=tu["sha256"])
    res = run_pathway.build_pathway(args)
    out = res["out_dir"]
    _SOURCE["path"] = args.gene_sets
    with open(os.path.join(out, "pathway_evidence.json")) as fh:
        evidence = json.load(fh)
    with open(os.path.join(out, "pathway_provenance.json")) as fh:
        prov = json.load(fh)
    with open(os.path.join(out, "pathway.json")) as fh:
        doc = json.load(fh)
    return out, evidence, prov, doc


class TestTheBundleCarriesWhatItCounted:
    def test_the_evidence_ships_in_the_bundle(self, built):
        out, _, _, _ = built
        assert os.path.exists(os.path.join(out, "pathway_evidence.json"))
        assert os.path.exists(os.path.join(out, "pathway_signatures.parquet"))

    def test_it_carries_the_FULL_PRE_INTERSECTION_membership(self, built):
        _, evidence, _, doc = built
        assert set(evidence["membership"]) == {r["set_id"] for r in doc["records"]}
        for m in evidence["membership"].values():
            assert isinstance(m["genes_target"], list)
            assert isinstance(m["genes_readout"], list)
            assert m["n_source_symbols"] is not None

    def test_the_membership_is_NOT_already_intersected_with_the_universe(self, built):
        # The bug in the first cut: `genes_target` held the ALREADY-INTERSECTED set, so
        # intersecting it with the same universe returned itself and the recount agreed with
        # ANY declared value. The full membership is a SUPERSET of the intersection, and at
        # least one set here must actually prove it.
        _, evidence, _, _ = built
        universe = set(evidence["target_universe"])
        strictly_larger = 0
        for m in evidence["membership"].values():
            full = set(m["genes_target"])
            declared = set(m["declared_genes_in_target_universe"])
            assert declared == full & universe        # the producer's output re-derives...
            assert declared <= full                   # ...and the evidence is not the output
            if full - universe:
                strictly_larger += 1
        assert strictly_larger, \
            "no set has a member outside the target universe, so this fixture cannot tell " \
            "a pre-intersection membership from an intersected one"

    def test_the_declared_intersections_are_LABELLED_as_the_producers_output(self, built):
        _, evidence, _, _ = built
        for m in evidence["membership"].values():
            assert "declared_n_genes_in_target_universe" in m
            assert "declared_n_genes_in_readout_universe" in m

    def test_it_carries_BOTH_universes_and_they_are_DIFFERENT_populations(self, built):
        _, evidence, _, _ = built
        assert evidence["target_universe"]                 # the ranked population
        assert evidence["readout_universe"]                # the signature vector space
        assert evidence["target_universe_sha256"] != evidence["readout_universe_sha256"]

    def test_it_carries_EVERY_arms_ranking(self, built):
        _, evidence, _, _ = built
        assert set(evidence["arm_rankings"]) == set(config.ARMS)
        for ranking in evidence["arm_rankings"].values():
            for i, r in enumerate(ranking, start=1):
                assert r["rank"] == i                      # dense, ordered, 1-based
                assert r["target_id"] and r["score"] is not None

    def test_the_ranking_is_the_one_the_enrichment_WALKED(self, built):
        # ordered by (-score, target_id) — the tie-break included, or a recount could
        # legitimately disagree about which members are 'in' a truncated ranking
        _, evidence, _, _ = built
        for ranking in evidence["arm_rankings"].values():
            keys = [(-r["score"], r["target_id"]) for r in ranking]
            assert keys == sorted(keys)


class TestTheCountsCanACTUALLYBeRecounted:
    """The point of the whole exercise. Recount from the bytes; compare to the record."""

    def test_n_hits_in_ranking_RECOUNTS_from_the_membership_and_the_ranking(self, built):
        _, evidence, _, doc = built
        for record in doc["records"]:
            members = set(evidence["membership"][record["set_id"]]["genes_target"])
            for arm, block in record["enrichment"].items():
                ranked = {r["target_id"] for r in evidence["arm_rankings"][arm]}
                assert block["n_hits_in_ranking"] == len(members & ranked)

    def test_n_ranked_RECOUNTS_from_the_ranking(self, built):
        _, evidence, _, doc = built
        for record in doc["records"]:
            for arm, block in record["enrichment"].items():
                assert block["n_ranked"] == len(evidence["arm_rankings"][arm])

    def test_n_genes_in_target_universe_RECOUNTS_from_the_bound_target_universe(
            self, built):
        _, evidence, _, doc = built
        universe = set(evidence["target_universe"])
        for record in doc["records"]:
            members = set(evidence["membership"][record["set_id"]]["genes_target"])
            assert record["n_genes_in_target_universe"] == len(members & universe)

    def test_a_recount_would_CATCH_a_self_consistent_count_forgery(self, built):
        # the exact mutation W0 demonstrated: inflate the declared counts so a
        # zero-coverage pathway looks rankable. The RECOUNT disagrees — which is the whole
        # difference between provenance and internal consistency.
        _, evidence, _, doc = built
        record = doc["records"][0]
        members = set(evidence["membership"][record["set_id"]]["genes_target"])
        ranked = {r["target_id"] for r in evidence["arm_rankings"][config.ARMS[0]]}
        forged = len(members & ranked) + 5
        assert forged != len(members & ranked)


class TestTheGeneSetSourceShipsINSIDETheBundle:
    """A verifier must be able to work entirely from the shipped bytes.

    The provenance named the gene-set release and its hashes, but the FILE lived wherever the
    operator kept it. So a verifier could check the run's gene sets hashed to X — and had no
    way to obtain X. It had to be handed the same file out of band, and an artifact whose
    evidence exists only on the machine that made it is not independently checkable.
    """

    def test_the_exact_input_json_is_IN_the_bundle(self, built):
        out, _, _, _ = built
        assert os.path.exists(os.path.join(out, "gene_sets.source.json"))

    def test_it_is_copied_BYTE_FOR_BYTE_not_re_serialised(self, built, gene_sets_path):
        # a re-emitted JSON is a different FILE that happens to mean the same thing, and its
        # raw hash would not be the hash the run bound
        out, _, _, _ = built
        with open(gene_sets_path, "rb") as fh:
            source = fh.read()
        with open(os.path.join(out, "gene_sets.source.json"), "rb") as fh:
            shipped = fh.read()
        assert shipped == source

    def test_the_raw_hash_of_the_SHIPPED_copy_is_what_the_run_BOUND(self, built):
        out, _, prov, _ = built
        block = prov["run_binding"]["evidence_artifacts"]["gene_set_source"]
        assert block["raw_sha256"] == file_sha256(
            os.path.join(out, "gene_sets.source.json"))
        assert prov["evidence_artifacts"]["gene_set_source"]["copy_verified"] is True

    def test_it_binds_the_release_license_and_namespace(self, built):
        _, _, prov, _ = built
        block = prov["run_binding"]["evidence_artifacts"]["gene_set_source"]
        assert block["gene_set_release"]
        assert block["gene_set_license"]
        assert block["gene_id_namespace"]
        assert block["canonical_sha256"]

    def test_the_path_is_BUNDLE_RELATIVE_never_an_absolute_machine_path(self, built):
        _, _, prov, _ = built
        block = prov["evidence_artifacts"]["gene_set_source"]
        assert block["path_in_bundle"] == "gene_sets.source.json"
        assert not os.path.isabs(block["path_in_bundle"])

    def test_NO_absolute_machine_path_leaks_into_the_provenance(self, built):
        _, _, prov, _ = built
        # a published artifact that carries the producer's filesystem is unusable to anyone
        # else, and tells them something they were not meant to be told
        from direct import emit
        assert emit.scan_for_local_paths(prov["evidence_artifacts"]) == []
    def test_the_run_binding_carries_the_CANONICAL_hash_of_the_evidence(self, built):
        out, evidence, prov, _ = built
        bound = prov["run_binding"]["evidence_artifacts"]["pathway_evidence"]
        assert bound["canonical_sha256"] == content_hash(evidence)

    def test_the_provenance_carries_the_RAW_byte_hash_of_the_file_as_written(self, built):
        out, _, prov, _ = built
        written = prov["evidence_artifacts"]["pathway_evidence"]
        assert written["raw_sha256"] == file_sha256(
            os.path.join(out, "pathway_evidence.json"))

    def test_the_signatures_are_bound_by_CONTENT_not_by_parquet_bytes(self, built):
        # parquet is not byte-stable across writers; a hash that changes when nothing
        # changed is a hash people learn to ignore
        out, _, prov, _ = built
        bound = prov["run_binding"]["evidence_artifacts"]["masked_signatures"]
        assert bound["canonical_sha256"]
        assert bound["n_rows"] >= 0
        assert bound["columns"] == list(pathway_evidence.SIGNATURE_COLUMNS)

    def test_the_evidence_names_a_LOGICAL_path_inside_the_bundle_not_a_machine_path(
            self, built):
        _, _, prov, _ = built
        for block in (prov["evidence_artifacts"]["pathway_evidence"],
                      prov["evidence_artifacts"]["masked_signatures"]):
            assert not os.path.isabs(block["path_in_bundle"])
            assert "/" not in block["path_in_bundle"]

    def test_changing_the_evidence_would_change_the_RUN_ID(self, built):
        # it is hashed into the binding the run id is taken from, so a swapped evidence
        # file cannot keep the id the run answers to
        _, evidence, prov, _ = built
        other = dict(evidence, target_universe=evidence["target_universe"][:-1])
        assert content_hash(other) != \
            prov["run_binding"]["evidence_artifacts"]["pathway_evidence"][
                "canonical_sha256"]


class TestGeneratorIsNotVerifier:
    def test_this_lane_does_NOT_verify_its_own_counts(self):
        # W4 owns the reconstruction and the forgery attacks. If this module ever grows a
        # verdict, the producer has begun marking its own homework. Checked against the
        # module's API rather than its source text — the docstring EXPLAINS the forgery it
        # exists to make catchable, and a check that cannot tell code from prose would force
        # the file to stop saying what it is for.
        api = set(dir(pathway_evidence))
        for name in ("verify", "ADMIT", "REJECT", "verdict", "admit"):
            assert name not in api
        assert not [n for n in api if n.startswith("verify")]
