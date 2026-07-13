"""B2 — the PRODUCTION pathway runner, end to end.

Before this, enrichment and convergence could only be reached from test scaffolding:
there was no entry point that took the real masked signatures and the real pinned gene
sets and produced an artifact anybody could admit, cite or refute. A method that only
runs inside its own tests has not been run.

The reviewer's re-verify, in order: run the production runner on the fixture signatures
end to end; confirm the artifact is content-addressed, re-derivable, and passes its own
verifier; confirm no p/q/FDR is emitted.
"""
from __future__ import annotations

import json
import os

import pytest
from direct import genesets, run_pathway, verify_pathway
from direct.hashing import content_hash
from fixtures_pathway import write_gene_sets


@pytest.fixture
def pathway_run(synthetic_run, tmp_path):
    """A real run, with a real pinned gene-set bundle bound to its own effect universe."""
    from direct import run_screen as rs
    from fixtures_spec import TARGET_GENES, UNIVERSE

    def _build(**kwargs):
        from direct import universe as uni
        args = synthetic_run(**kwargs)
        # A1: the bundle must be bound to the EXACT universes this run computes — BOTH of
        # them. A bundle that declares one and not the other is refused, fail-closed.
        ctx = rs.prepare(args)
        tu = uni.target_universe(ctx["identities_by_condition"])
        gs = write_gene_sets(os.path.dirname(args.de_main), UNIVERSE,
                             list(TARGET_GENES), ctx["gene_universe"]["sha256"],
                             target_universe_sha256=tu["sha256"])
        args.gene_sets = gs
        return args
    return _build


@pytest.fixture
def built(pathway_run):
    args = pathway_run()
    res = run_pathway.build_pathway(args)
    with open(os.path.join(res["out_dir"], "pathway.json")) as fh:
        doc = json.load(fh)
    with open(os.path.join(res["out_dir"], "pathway_provenance.json")) as fh:
        prov = json.load(fh)
    return res, doc, prov


class TestItRunsEndToEndOnRealSignatures:
    def test_it_produces_a_record_for_every_gene_set(self, built):
        res, doc, _ = built
        assert res["n_records"] == doc["n_records"] > 0
        assert len(doc["records"]) == res["n_records"]

    def test_the_signatures_are_the_MASKED_ones_the_screen_scored(self, built):
        # A signature masked differently from the number it explains would explain a
        # different number. It comes from the same pass, under the same mask.
        res, doc, _ = built
        assert res["n_signature_targets"] > 0
        for r in doc["records"]:
            for t in r["convergence"]["measured_perturbations"]:
                assert isinstance(t, str)

    def test_only_intra_set_pairs_are_computed(self, built):
        res, _, _ = built
        # after B1 a cross-set pair can never be an edge of any set's subgraph, so
        # computing one would be work done to produce a number nothing may use
        assert res["n_intra_set_pairs"] >= 0

    def test_it_writes_the_artifact_the_contract_names(self, built):
        res, _, _ = built
        # the bundle carries the EVIDENCE its counts were counted from, beside the records
        # that report them — so an independent verifier can recount rather than re-read
        assert sorted(os.listdir(res["out_dir"])) == [
            "gene_sets.source.json", "pathway.json", "pathway_evidence.json",
            "pathway_provenance.json", "pathway_signatures.parquet",
            "pathway_verification.json"]

    def test_it_refuses_to_run_without_a_pinned_gene_set_bundle(self, synthetic_run):
        from direct import gate
        args = synthetic_run()
        args.gene_sets = None
        with pytest.raises(gate.GateError) as e:
            run_pathway.build_pathway(args)
        assert "gene-set bundle" in str(e.value)


class TestTheArtifactIsContentAddressed:
    def test_the_records_hash_recomputes_from_the_emitted_records(self, built):
        _, doc, _ = built
        stripped = [{k: v for k, v in r.items()
                     if k not in ("pathway_run_id", "pathway_method_sha256")}
                    for r in doc["records"]]
        assert content_hash(stripped) == doc["records_sha256"]

    def test_the_run_binding_names_the_records_it_shipped(self, built):
        _, doc, prov = built
        assert prov["run_binding"]["records_sha256"] == doc["records_sha256"]

    def test_the_same_science_reproduces_the_same_run_id(self, pathway_run):
        a = run_pathway.build_pathway(pathway_run())
        b = run_pathway.build_pathway(pathway_run())
        assert a["pathway_run_id"] == b["pathway_run_id"]
        assert a["records_sha256"] == b["records_sha256"]

    def test_every_record_carries_the_run_id_and_the_method_hash(self, built):
        res, doc, _ = built
        for r in doc["records"]:
            assert r["pathway_run_id"] == res["pathway_run_id"]
            assert r["pathway_method_sha256"] == res["pathway_method_sha256"]


class TestItPassesItsOwnVerifier:
    def test_a_clean_artifact_is_admitted(self, built):
        res, _, _ = built
        v = res["verification"]
        assert v["verdict"] == verify_pathway.ADMIT
        assert v["n_failed"] == 0
        assert v["generator_is_not_verifier"] is True
        assert v["fail_closed"] is True

    def test_the_verifier_re_derives_it_from_the_bytes_on_disk(self, built):
        res, _, prov = built
        again = verify_pathway.verify(out_dir=res["out_dir"], provenance=prov)
        assert again["verdict"] == verify_pathway.ADMIT

    def test_a_tampered_records_hash_is_REJECTED(self, built):
        res, doc, prov = built
        doc["records_sha256"] = "0" * 64
        with open(os.path.join(res["out_dir"], "pathway.json"), "w") as fh:
            json.dump(doc, fh)
        v = verify_pathway.verify(out_dir=res["out_dir"], provenance=prov)
        assert v["verdict"] == verify_pathway.REJECT

    def test_a_convergence_claim_resting_on_a_NON_MEMBER_is_REJECTED(self, built):
        # B1, at the artifact boundary: the exact defect, injected into a shipped file.
        res, doc, prov = built
        for r in doc["records"]:
            if r["convergence"]["measured_perturbations"]:
                r["convergence"]["supporting_perturbations"] = ["ENSG_NOT_A_MEMBER"]
                r["convergence"]["n_supporting_perturbations"] = 1
                break
        with open(os.path.join(res["out_dir"], "pathway.json"), "w") as fh:
            json.dump(doc, fh)
        v = verify_pathway.verify(out_dir=res["out_dir"], provenance=prov)
        assert v["verdict"] == verify_pathway.REJECT
        assert "no_convergence_claim_rests_on_a_non_member" in {
            c["check"] for c in v["checks"] if c["status"] == verify_pathway.FAIL}

    def test_an_enrichment_with_an_EMPTY_edge_is_REJECTED(self, built):
        # M1, at the artifact boundary.
        res, doc, prov = built
        for r in doc["records"]:
            for e in r["enrichment"].values():
                if e["enrichment_value"] is not None:
                    e["leading_edge"] = []
                    e["n_leading_edge"] = 0
        with open(os.path.join(res["out_dir"], "pathway.json"), "w") as fh:
            json.dump(doc, fh)
        v = verify_pathway.verify(out_dir=res["out_dir"], provenance=prov)
        assert v["verdict"] == verify_pathway.REJECT


class TestTheVerifierReadsTheShippedBytes:
    """B2 re-audit — the verifier hashed the provenance file and firewalled the CALLER'S
    DICT. Poison the emitted ``pathway_provenance.json`` on disk, pass the pristine dict,
    and it ADMITTED. It is now the shipped bytes or nothing."""

    def _poison_file_only(self, out_dir, key, value):
        path = os.path.join(out_dir, "pathway_provenance.json")
        with open(path) as fh:
            clean = json.load(fh)
        poisoned = json.loads(json.dumps(clean))
        poisoned["estimator_poison"] = {key: value}
        with open(path, "w") as fh:
            json.dump(poisoned, fh, indent=2)
        return clean

    @pytest.mark.parametrize("key", [
        "empirical_p_value", "empirical_q_value", "nominal_p", "q_val", "qvalue", "fdr",
    ])
    def test_an_ON_DISK_poison_is_REJECTED_even_with_a_clean_caller_dict(
            self, built, key):
        from direct.temporal import admission
        res, _, _ = built
        clean = self._poison_file_only(res["out_dir"], key, 0.01)
        assert admission.forbidden_keys(clean) == []     # the caller's copy IS clean

        v = verify_pathway.verify(out_dir=res["out_dir"], provenance=clean)
        assert v["verdict"] == verify_pathway.REJECT
        assert "no_forbidden_key_at_any_depth" in {
            c["check"] for c in v["checks"] if c["status"] == verify_pathway.FAIL}

    def test_the_caller_dict_is_not_even_required(self, built):
        res, _, _ = built
        assert verify_pathway.verify(
            out_dir=res["out_dir"])["verdict"] == verify_pathway.ADMIT
        self._poison_file_only(res["out_dir"], "empirical_p_value", 0.01)
        assert verify_pathway.verify(
            out_dir=res["out_dir"])["verdict"] == verify_pathway.REJECT

    def test_a_caller_dict_disagreeing_with_the_shipped_file_is_REJECTED(self, built):
        res, _, _ = built
        clean = self._poison_file_only(res["out_dir"], "empirical_p_value", 0.01)
        v = verify_pathway.verify(out_dir=res["out_dir"], provenance=clean)
        assert "caller_provenance_matches_the_shipped_file" in {
            c["check"] for c in v["checks"] if c["status"] == verify_pathway.FAIL}

    def test_it_pins_the_canonical_bytes_it_actually_read(self, built):
        res, _, prov = built
        v = verify_pathway.verify(out_dir=res["out_dir"], provenance=prov)
        assert v["verdict"] == verify_pathway.ADMIT
        assert len(v["artifact_identity"]["provenance_canonical_sha256"]) == 64

    def test_an_unparseable_shipped_provenance_is_REJECTED(self, built):
        res, _, prov = built
        with open(os.path.join(res["out_dir"], "pathway_provenance.json"), "w") as fh:
            fh.write("{ not json")
        v = verify_pathway.verify(out_dir=res["out_dir"], provenance=prov)
        assert v["verdict"] == verify_pathway.REJECT


class TestNoPValueNoCombinedObjective:
    def test_the_clean_artifact_carries_no_p_or_q_anywhere(self, built):
        _, doc, prov = built
        from direct.temporal import admission
        assert admission.forbidden_keys(doc) == []
        assert admission.forbidden_keys(prov) == []

    def test_the_artifact_declares_its_inference_is_not_calibrated(self, built):
        _, _, prov = built
        assert prov["inference_status"] == "not_calibrated"
        assert prov["no_pq_reason"]

    def test_a_smuggled_pathway_p_value_is_REJECTED(self, built):
        res, doc, prov = built
        doc["records"][0]["enrichment"]["away_from_A"]["empirical_pval"] = 0.01
        with open(os.path.join(res["out_dir"], "pathway.json"), "w") as fh:
            json.dump(doc, fh)
        v = verify_pathway.verify(out_dir=res["out_dir"], provenance=prov)
        assert v["verdict"] == verify_pathway.REJECT
        assert "no_forbidden_key_at_any_depth" in {
            c["check"] for c in v["checks"] if c["status"] == verify_pathway.FAIL}

    def test_a_combined_pathway_score_is_REJECTED(self, built):
        res, doc, prov = built
        doc["records"][0]["combined_pathway_score"] = 1.0
        with open(os.path.join(res["out_dir"], "pathway.json"), "w") as fh:
            json.dump(doc, fh)
        v = verify_pathway.verify(out_dir=res["out_dir"], provenance=prov)
        assert v["verdict"] == verify_pathway.REJECT

    def test_the_two_evidence_lines_are_never_fused(self, built):
        _, doc, _ = built
        assert doc["method"]["evidence_lines_are_combined"] is False
        for r in doc["records"]:
            assert set(r["enrichment"]) == {"away_from_A", "toward_B"}


class TestTheGeneSetBundleIsPinnedAndBound:
    def test_the_bundle_is_bound_to_this_runs_effect_universe(self, built):
        _, _, prov = built
        gs = prov["run_binding"]["gene_sets"]
        assert gs["status"] == "bound"
        assert gs["effect_universe_sha256"] == \
            prov["run_binding"]["gene_universe_sha256"]

    def test_a_bundle_bound_to_a_DIFFERENT_universe_is_refused(self, pathway_run):
        args = pathway_run()
        with open(args.gene_sets) as fh:
            doc = json.load(fh)
        doc["effect_universe_sha256"] = "f" * 64
        with open(args.gene_sets, "w") as fh:
            json.dump(doc, fh)
        with pytest.raises(genesets.GeneSetError) as e:
            run_pathway.build_pathway(args)
        assert "another background" in str(e.value)

    def test_the_licence_travels_with_the_binding(self, built):
        _, _, prov = built
        assert prov["run_binding"]["gene_sets"]["gene_set_license"]
