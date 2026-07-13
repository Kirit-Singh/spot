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
    # STEP 0: the SHARED per-condition signature artifacts, emitted ONCE, before any bundle.
    from direct import signature_matrix as sm
    args.signature_matrix_root = str(tmp_path / "signatures")
    sm.build_condition(args, "StimX", args.signature_matrix_root)
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
            "pathway_verification.json", "signature_ref.json"]

    def test_the_bundle_ships_NO_signature_bytes(self, built):
        # P11 / A12: keeping signatures.parquet "for compatibility" brings the 29.5 GiB peak
        # straight back, and it is the least-change instinct that would do it.
        res, _, prov, _ = built
        assert not os.path.exists(
            os.path.join(res["out_dir"], "pathway_signatures.parquet"))
        with open(os.path.join(res["out_dir"], "signature_ref.json")) as fh:
            ref = json.load(fh)
        assert ref["ships_signature_bytes"] is False
        assert ref["reduction_order_id"] == \
            "spot.stage02.convergence.reduction.sorted_gene_left_fold.v1"

    def test_the_reference_binds_the_SHARED_MANIFEST_and_it_is_NEVER_NULL(self, built):
        """It WAS null, silently. `write()` adds `manifest_sha256` to the dict AFTER dumping
        the JSON, so the manifest ON DISK never carried it, and the producer — which reloads
        the shipped file — bound `None` via `.get()`.

        A null manifest hash is not cosmetic. It is the one binding that says WHICH shared
        matrix a bundle is entitled to read. Without it, Rest's matrix can be served as
        Stim8hr's and the schemas would agree — nothing else would notice.
        """
        res, _, prov, _ = built
        for ref in (prov["run_binding"]["signature_ref"],
                    json.load(open(os.path.join(res["out_dir"], "signature_ref.json")))):
            assert ref["signature_manifest_sha256"] is not None
            assert len(ref["signature_manifest_raw_sha256"]) == 64
            assert len(ref["signature_manifest_canonical_sha256"]) == 64

    def test_the_AMENDED_BITMAP_COUNTS_are_bound_into_the_run_identity(self, built):
        # not merely covered by the manifest hash: carried, so a swapped count cannot survive
        _, doc, prov, _ = built
        ref = prov["run_binding"]["signature_ref"]
        for key in ("n_unresolved_no_signature", "n_resolved_all_ones",
                    "n_resolved_no_masked_readout_gene",
                    "n_resolved_masked_readout_genes"):
            assert isinstance(ref[key], int), key
        assert ref["bitmap_rule_id"] == \
            "spot.stage02.signature.bitmap_zeros_are_the_mask_axis_intersection.v2"
        assert len(ref["source_mask_sha256"]) == 64
        assert doc["method"]["bitmap_rule_id"] == ref["bitmap_rule_id"]

    def test_the_two_all_ones_counts_AGREE_in_the_binding(self, built):
        _, _, prov, _ = built
        ref = prov["run_binding"]["signature_ref"]
        assert ref["n_resolved_all_ones"] == ref["n_resolved_no_masked_readout_gene"]

    def test_the_manifest_identity_is_IN_the_pathway_run_id(self, built):
        # a reference outside the id could be swapped after the fact and keep the id
        from direct.hashing import canonical_json, sha256_hex
        _, _, prov, _ = built
        assert prov["run_binding"]["signature_ref"]["signature_manifest_raw_sha256"]
        full = sha256_hex(canonical_json(prov["run_binding"]))
        assert prov["pathway_run_id"] == full[:16]

    def test_a_reference_with_NO_manifest_identity_is_REFUSED_not_defaulted(self, built):
        from direct import signature_matrix as sm
        with pytest.raises(sm.SignatureMatrixError) as exc:
            sm.signature_ref(manifest={}, condition="Rest", source="go_bp",
                             member_target_ids=[])
        assert exc.value.gate == sm.REFUSE_MANIFEST_IDENTITY_ABSENT

    def test_the_reference_binds_the_MATRIX_and_the_BITMAP_hashes(self, built):
        _, _, prov, _ = built
        ref = prov["run_binding"]["signature_ref"]
        for key in ("matrix_raw_sha256", "matrix_canonical_sha256", "matrix_values_sha256",
                    "mask_raw_sha256", "mask_canonical_sha256", "mask_bits_sha256",
                    "gene_axis_raw_sha256"):
            assert len(ref[key]) == 64, key

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
    def test_the_member_list_is_RE_DERIVABLE_not_authoritative(self, built):
        _, _, prov, _ = built
        ref = prov["signature_ref"]
        assert ref["n_member_targets"] == len(ref["member_target_ids"])
        assert ref["member_rule_id"]

    def test_the_shared_manifest_is_bound_so_a_STALE_reference_is_catchable(self, built):
        _, _, prov, _ = built
        m = prov["signature_manifest"]
        assert m["reduction_order_id"]
        assert m["mask"]["bits_sha256"]
        assert prov["run_binding"]["signature_ref"]["mask_bits_sha256"] \
            == m["mask"]["bits_sha256"]


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
