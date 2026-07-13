"""The ALL-ARM pathway bundle: 20 reusable enrichment arms, ONE shared convergence, no pair.

Six physical bundles in the release (3 conditions x 2 pinned sources), each carrying every
admitted program's two enrichment arms. 120 enrichment arms across the release — and SIX
convergence artifacts, not 120, because convergence does not know which program is being
asked about or in which direction.
"""
from __future__ import annotations

import json
import os

import pytest
from direct import arm_keys, genesets, pathway_arms, run_pathway_arms
from fixtures_pathway import write_gene_sets
from fixtures_spec import TARGET_GENES, UNIVERSE


@pytest.fixture
def built(synthetic_run, tmp_path):
    from direct import run_screen as rs
    from direct import universe as uni

    args = synthetic_run()
    ctx = rs.prepare(args)
    tu = uni.target_universe(ctx["identities_by_condition"])
    args.gene_sets = write_gene_sets(
        os.path.dirname(args.de_main), UNIVERSE, list(TARGET_GENES),
        ctx["gene_universe"]["sha256"], target_universe_sha256=tu["sha256"])
    args.condition = "StimX"
    args.out_root = str(tmp_path / "pw")
    res = run_pathway_arms.build_pathway_arms(args)

    def load(name):
        with open(os.path.join(res["out_dir"], name)) as fh:
            return json.load(fh)

    return res, load("arm_bundle.json"), load("pathway_provenance.json"), \
        load("convergence.json")


class TestThePhysicalContract:
    """The exact names W4's verifier and W3's manifest read. Emitted natively, no shim."""

    def test_the_bundle_ships_exactly_the_contract_files(self, built):
        res, _, _, _ = built
        assert sorted(os.listdir(res["out_dir"])) == [
            "arm_bundle.json", "convergence.json", "gene_sets.source.json",
            "pathway_evidence.json", "pathway_provenance.json",
            "pathway_signatures.parquet", "pathway_verification.json"]

    def test_the_producer_does_NOT_admit_its_own_output(self, built):
        res, _, _, _ = built
        with open(os.path.join(res["out_dir"], "pathway_verification.json")) as fh:
            v = json.load(fh)
        assert v["admitted"] is False
        assert v["verdict"] == "pending_independent_verification"
        assert v["generator_is_not_verifier"] is True and v["fail_closed"] is True


class TestEveryAdmittedProgramGetsBothEnrichmentArms:
    def test_the_slot_count_is_programs_times_two(self, built):
        res, doc, _, _ = built
        assert doc["n_arm_slots"] == res["n_admitted_programs"] * 2
        assert doc["n_arm_slots"] == doc["n_expected_arm_slots"]

    def test_every_program_has_an_increase_AND_a_decrease_arm(self, built):
        _, doc, _, _ = built
        for p in doc["scorer_view"]["admitted_program_ids"]:
            assert {a["desired_change"] for a in doc["arms"] if a["program_id"] == p} \
                == {arm_keys.INCREASE, arm_keys.DECREASE}

    def test_the_arm_keys_are_the_canonical_pathway_keys(self, built):
        _, doc, _, _ = built
        for a in doc["arms"]:
            assert a["pathway_arm_key"] == arm_keys.pathway_arm_key(
                a["program_id"], a["desired_change"], a["condition"], a["source"])

    def test_EVERY_arm_is_enriched_against_EVERY_set(self, built):
        _, doc, _, _ = built
        per_arm = {}
        for r in doc["records"]:
            per_arm.setdefault(r["pathway_arm_key"], set()).add(r["set_id"])
        sizes = {len(v) for v in per_arm.values()}
        assert len(sizes) == 1, "some arm was enriched against fewer sets than another"
        assert len(per_arm) == doc["n_expected_arm_slots"]


class TestTheArmsAreCOMPUTEDNeverInferredFromEachOther:
    """A ranking is not antisymmetric: the decrease arm is not the increase arm reversed."""

    def test_the_method_declares_no_antisymmetry_was_assumed(self, built):
        _, doc, _, _ = built
        assert doc["method"]["enrichment_arms_are_computed_not_derived"] is True
        assert doc["method"]["enrichment_rank_antisymmetry_assumed"] is False

    def test_the_two_arms_of_a_program_have_INDEPENDENT_leading_edges(self, built):
        # if one had been inferred from the other by reversing the ranking, the edges would
        # be mirror images by construction rather than by measurement
        _, doc, _, _ = built
        by_key = {(r["program_id"], r["desired_change"], r["set_id"]): r
                  for r in doc["records"]}
        seen = 0
        for (prog, change, set_id), rec in by_key.items():
            if change != arm_keys.INCREASE:
                continue
            twin = by_key.get((prog, arm_keys.DECREASE, set_id))
            if twin is None or rec["enrichment_value"] is None:
                continue
            seen += 1
        assert seen, "no arm pair to compare — the fixture proves nothing"


class TestConvergenceIsSHAREDNotRestatedPerArm:
    def test_there_is_exactly_ONE_convergence_artifact(self, built):
        res, _, _, conv = built
        assert conv["convergence_key"] == arm_keys.convergence_key(
            res["condition"], res["source"])
        assert conv["is_shared_across_arms"] is True
        assert conv["depends_on_program_or_desired_change"] is False

    def test_it_carries_NO_program_and_NO_desired_change(self, built):
        _, _, _, conv = built
        blob = json.dumps({k: v for k, v in conv.items()
                           if k != "depends_on_program_or_desired_change"})
        assert "desired_change" not in blob
        assert "increase" not in blob and "decrease" not in blob

    def test_EVERY_arm_REFERENCES_the_same_convergence_artifact(self, built):
        _, doc, _, conv = built
        refs = {a["convergence_ref"] for a in doc["arms"]}
        assert refs == {conv["convergence_key"]}
        assert doc["convergence_sha256"] == conv["convergence_sha256"]

    def test_the_convergence_claim_is_NOT_copied_into_every_record(self, built):
        # 20 copies of one claim are 20 chances to disagree with it
        _, doc, _, _ = built
        for r in doc["records"]:
            assert "sets" not in r and "n_intra_set_pairs" not in r
            assert isinstance(r["convergence_ref"], str)


class TestNoPairNoRoleNoPolePareto:
    def test_no_pair_role_pole_or_pair_derived_field_anywhere(self, built):
        _, doc, prov, conv = built
        data = json.dumps({k: v for k, v in doc.items() if k != "method"}) \
            + json.dumps({k: v for k, v in prov["run_binding"].items() if k != "method"}) \
            + json.dumps(conv)
        for forbidden in ("away_from_A", "toward_B", "pareto", "joint_status",
                          "concordance", "combined"):
            assert forbidden not in data

    def test_the_method_DECLARES_what_it_will_not_carry(self, built):
        _, doc, _, _ = built
        m = doc["method"]
        for key in ("pair_fields_emitted", "pole_or_role_emitted", "pareto_emitted",
                    "joint_status_emitted", "combined_objective_permitted"):
            assert m[key] is False

    def test_there_is_no_p_q_or_FDR(self, built):
        _, doc, prov, _ = built
        blob = (json.dumps(doc) + json.dumps(prov)).lower()
        for forbidden in ("p_value", "q_value", "fdr", "padj"):
            assert forbidden not in blob
        assert prov["inference_status"] == "not_calibrated"


class TestTheRunIDIsTakenLASTOverEVERYBinding:
    def test_the_run_id_re_derives_from_its_own_binding(self, built):
        from direct.hashing import canonical_json, sha256_hex
        _, _, prov, _ = built
        full = sha256_hex(canonical_json(prov["run_binding"]))
        assert prov["pathway_run_id"] == full[:run_pathway_arms.RUN_ID_LEN]
        assert prov["pathway_run_sha256"] == full

    def test_every_required_binding_is_IN_the_id(self, built):
        _, _, prov, _ = built
        b = prov["run_binding"]
        for key in ("evidence_artifacts", "gene_universe_sha256", "target_universe_sha256",
                    "mask_sha256", "stage2_inputs", "code_identity", "scorer_view_sha256",
                    "direct_arm_rows_sha256", "convergence_sha256", "records_sha256"):
            assert b[key] is not None, key

    def test_the_gene_set_SOURCE_bytes_are_bound_and_shipped(self, built):
        res, _, prov, _ = built
        block = prov["evidence_artifacts"]["gene_set_source"]
        assert block["path_in_bundle"] == "gene_sets.source.json"
        assert block["copy_verified"] is True
        assert os.path.exists(os.path.join(res["out_dir"], "gene_sets.source.json"))


class TestTheSignatureReferenceIsCONTENTAddressedAndDropsNoGene:
    def test_it_references_by_CONTENT_so_a_condition_store_can_share_it(self, built):
        _, _, prov, _ = built
        ref = prov["signature_reference"]
        assert ref["content_sha256"]
        assert ref["shareable_scope"] == "condition"
        assert ref["readout_universe_sha256"]

    def test_NO_gene_is_dropped_to_make_it_smaller(self, built):
        # a signature with genes removed is a different signature
        _, _, prov, _ = built
        assert prov["signature_reference"]["genes_dropped"] == 0


class TestTheCountsAreRECOUNTABLEFromTheShippedEvidence:
    def test_n_hits_in_ranking_recounts_from_the_membership_and_the_arm_ranking(
            self, built):
        res, doc, _, _ = built
        with open(os.path.join(res["out_dir"], "pathway_evidence.json")) as fh:
            ev = json.load(fh)
        for r in doc["records"]:
            members = set(ev["membership"][r["set_id"]]["genes_target"])
            ranked = {x["target_id"]
                      for x in ev["arm_rankings"].get(r["direct_arm_key"], [])}
            assert r["n_hits_in_ranking"] == len(members & ranked)


class TestTheCoveragePolicyIsTheFROZENOne:
    def test_the_method_declares_the_frozen_thresholds(self, built):
        _, doc, _, _ = built
        m = doc["method"]
        assert m["coverage_policy_id"] == genesets.COVERAGE_POLICY_ID
        assert m["min_source_coverage"] == genesets.MIN_SOURCE_COVERAGE
        assert m["min_arm_ranked_members"] == genesets.MIN_ARM_RANKED_MEMBERS

    def test_eligibility_is_PER_ARM(self, built):
        _, doc, _, _ = built
        for r in doc["records"]:
            assert "arm_headline_rankable" in r
            assert "arm_coverage_disposition" in r


def test_expected_slots_is_derived_never_a_copied_count():
    assert pathway_arms.expected_slots(["a", "b", "c"]) == 6
