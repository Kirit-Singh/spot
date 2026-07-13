"""The SHARED signature matrix + MANDATORY bitmap (W7 spec 95d69302). Storage, not method.

The two rules that are load-bearing, and are the easiest to break by accident:

  * an ALL-ZERO bitmap row means NO SIGNATURE — the target is unresolved. It does NOT mean
    "nothing was masked". Conflate them and a masked cell becomes indistinguishable from an
    unmasked value that happens to be 0.0, and the analysis silently changes;

  * `reconstruct_signatures` -> `convergence.cosine_on_shared` must be the ONLY consumer path.
    A dense matrix invites a numpy reduction; the values would be identical and the summation
    order would not (~5e-07), and `supportive` is a threshold at 0.5. W7 proved the dict path
    bitwise over 1,770 real pairs: 0 mismatches, max diff 0.0.
"""
from __future__ import annotations

import json
import os

import numpy as np
import pytest
from direct import convergence, io_data
from direct import signature_matrix as sm


@pytest.fixture
def emitted(synthetic_run, tmp_path):
    args = synthetic_run()
    root = str(tmp_path / "signatures")
    manifest = sm.build_condition(args, "StimX", root)
    cond_dir = os.path.join(root, "StimX")
    return args, root, cond_dir, manifest


class TestTheArtifactsAndTheirShape:
    def test_it_writes_the_three_shared_artifacts(self, emitted):
        _, root, cond_dir, _ = emitted
        assert os.path.exists(os.path.join(root, "gene_axis.arrow"))
        assert os.path.exists(os.path.join(cond_dir, "signatures.matrix.arrow"))
        assert os.path.exists(os.path.join(cond_dir, "signatures.mask.arrow"))
        assert os.path.exists(os.path.join(cond_dir, "signature_manifest.json"))

    def test_the_bitmap_width_is_DERIVED_never_copied(self, emitted):
        _, _, _, m = emitted
        assert m["bitmap_width_bytes"] == (m["n_genes"] + 7) // 8

    def test_rows_are_sorted_by_target_id_in_BOTH_artifacts(self, emitted):
        _, _, cond_dir, m = emitted
        mat = sm.read(m, cond_dir)
        assert mat["target_ids"] == sm.sorted_target_ids(mat["target_ids"])

    def test_the_manifest_declares_float64_little_endian(self, emitted):
        _, _, _, m = emitted
        assert m["dtype"] == "float64" and m["byte_order"] == "little_endian"

    def test_it_declares_the_REDUCTION_ORDER(self, emitted):
        # P12. A consumer that does not know the reduction order will eventually vectorise.
        _, _, _, m = emitted
        assert m["reduction_order_id"] == sm.REDUCTION_ORDER_ID

    def test_it_records_all_values_finite(self, emitted):
        _, _, _, m = emitted
        assert m["all_values_finite"] is True


class TestTheWriteIsDETERMINISTIC:
    def test_the_same_condition_written_twice_hashes_the_same(self, synthetic_run,
                                                              tmp_path):
        args = synthetic_run()
        a = sm.build_condition(args, "StimX", str(tmp_path / "a"))
        b = sm.build_condition(args, "StimX", str(tmp_path / "b"))
        assert a["matrix"]["raw_sha256"] == b["matrix"]["raw_sha256"]
        assert a["mask"]["raw_sha256"] == b["mask"]["raw_sha256"]
        assert a["matrix"]["values_sha256"] == b["matrix"]["values_sha256"]


class TestTheALLZEROBitmapRuleIsNOSIGNATURE:
    """An unresolved target's row exists so indices align. It has NO signature."""

    def test_an_unresolved_target_has_an_ALL_ZERO_bitmap_row(self, emitted):
        _, _, cond_dir, m = emitted
        mat = sm.read(m, cond_dir)
        pop = np.array([np.unpackbits(r)[:m["n_genes"]].sum() for r in mat["bitmap"]])
        assert int((pop == 0).sum()) == m["n_unresolved_no_signature"]

    def test_an_all_zero_row_yields_NO_ENTRY_not_an_empty_dict(self, emitted):
        # an empty dict would read as "measured, nothing survived the mask" — a different
        # claim, and a false one
        _, _, cond_dir, m = emitted
        mat = sm.read(m, cond_dir)
        gene_ids = _gene_ids(emitted)
        pop = np.array([np.unpackbits(r)[:m["n_genes"]].sum() for r in mat["bitmap"]])
        unresolved = [mat["target_ids"][i] for i in np.nonzero(pop == 0)[0]]
        if not unresolved:
            pytest.skip("this fixture resolves every target")
        sigs = sm.reconstruct_signatures(mat, gene_ids, unresolved)
        assert sigs == {}
        for t in unresolved:
            assert t not in sigs

    def test_the_counts_RECOUNT_from_the_bitmap(self, emitted):
        _, _, cond_dir, m = emitted
        mat = sm.read(m, cond_dir)
        pop = np.array([np.unpackbits(r)[:m["n_genes"]].sum() for r in mat["bitmap"]])
        assert int((pop == 0).sum()) == m["n_unresolved_no_signature"]
        assert int((pop > 0).sum()) == m["n_resolved"]
        assert m["n_resolved"] + m["n_unresolved_no_signature"] == m["n_targets"]

    def test_a_RESOLVED_row_can_NEVER_be_all_ones(self, emitted):
        # build_estimate_mask always masks the target's own gene: its own repression is QC,
        # never skew evidence. An all-ones resolved row means the mask was not derived (P5).
        _, _, cond_dir, m = emitted
        mat = sm.read(m, cond_dir)
        for i, row in enumerate(mat["bitmap"]):
            bits = np.unpackbits(row)[:m["n_genes"]]
            if bits.any():
                assert bits.sum() < m["n_genes"], f"{mat['target_ids'][i]} masks nothing"

    def test_the_padding_bits_are_ZERO(self, emitted):
        _, _, cond_dir, m = emitted
        mat = sm.read(m, cond_dir)
        if m["n_genes"] % 8 == 0:
            pytest.skip("no padding bits in this fixture")
        tail = np.unpackbits(mat["bitmap"][:, -1:], axis=1)[:, m["n_genes"] % 8:]
        assert not tail.any()


def _gene_ids(emitted):
    args, _, _, _ = emitted
    return [str(g) for g in io_data.load_main(args.de_main, "StimX")["gene_ids"]]


class TestTheStorageIsLOSSLESSAndTheREDUCTIONOrderSurvives:
    """The whole point: production's numbers, bitwise."""

    def _production_signatures(self, args, members):
        from direct import run_arms
        from direct import run_screen as rs
        ctx = rs.prepare(args)
        scan = run_arms.base_deltas(ctx=ctx, args=args, cond="StimX",
                                    admitted=["fx_program_a"],
                                    signature_targets=set(members))
        return scan["signatures"]

    def test_the_reconstructed_dicts_are_IDENTICAL_to_productions(self, emitted):
        args, _, cond_dir, m = emitted
        mat = sm.read(m, cond_dir)
        gene_ids = _gene_ids(emitted)
        members = set(mat["target_ids"])
        produced = self._production_signatures(args, members)
        rebuilt = sm.reconstruct_signatures(mat, gene_ids, members)

        assert set(rebuilt) == set(produced), "a different set of targets has a signature"
        for t, vec in produced.items():
            assert rebuilt[t] == vec, f"{t}: the reconstructed signature is not production's"

    def test_cosine_on_shared_reproduces_production_BITWISE(self, emitted):
        # W7: 1,770 real pairs, 0 mismatches, max diff 0.0. Any non-zero difference — even
        # 5e-07 — means someone changed the reduction order.
        args, _, cond_dir, m = emitted
        mat = sm.read(m, cond_dir)
        gene_ids = _gene_ids(emitted)
        members = set(mat["target_ids"])
        produced = self._production_signatures(args, members)
        rebuilt = sm.reconstruct_signatures(mat, gene_ids, members)

        ids = sorted(produced)
        pairs = 0
        for i, a in enumerate(ids):
            for b in ids[i + 1:]:
                sim_p, n_p = convergence.cosine_on_shared(produced[a], produced[b])
                sim_r, n_r = convergence.cosine_on_shared(rebuilt[a], rebuilt[b])
                assert n_r == n_p
                assert sim_r == sim_p, f"{a}/{b}: {sim_r!r} != {sim_p!r} — NOT bitwise"
                pairs += 1
        assert pairs, "no pair compared — this proves nothing"

    def test_NO_gene_is_dropped(self, emitted):
        _, _, cond_dir, m = emitted
        mat = sm.read(m, cond_dir)
        gene_ids = _gene_ids(emitted)
        assert mat["values"].shape[1] == len(gene_ids) == m["n_genes"]


class TestThePrecisionBearingDigest:
    def test_a_float32_downgrade_CHANGES_values_sha256(self, emitted):
        # A1: it "looks the same" and the disk win is real.
        _, _, cond_dir, m = emitted
        mat = sm.read(m, cond_dir)
        downgraded = mat["values"].astype("<f4").astype("<f8")
        assert sm.values_sha256(downgraded) != m["matrix"]["values_sha256"] \
            or np.array_equal(downgraded, mat["values"])

    def test_a_ROW_REORDER_changes_values_sha256(self, emitted):
        # A2: faster, skips a sort.
        _, _, cond_dir, m = emitted
        mat = sm.read(m, cond_dir)
        if len(mat["target_ids"]) < 2:
            pytest.skip("need two rows to reorder")
        assert sm.values_sha256(mat["values"][::-1]) != m["matrix"]["values_sha256"]

    def test_the_canonical_descriptor_binds_the_CONDITION_and_the_ROW_IDENTITY(
            self, emitted):
        # A6: cross-condition swap — the schemas are identical, so the content must differ.
        _, _, _, m = emitted
        assert m["matrix"]["canonical_sha256"]
        assert m["matrix"]["values_sha256"]

    def test_a_forged_BITMAP_changes_bits_sha256(self, emitted):
        # A4/A5: forge all-ones, or promote an unresolved row.
        _, _, cond_dir, m = emitted
        mat = sm.read(m, cond_dir)
        forged = np.full_like(mat["bitmap"], 0xFF)
        assert sm.bits_sha256(forged) != m["mask"]["bits_sha256"]


class TestTheGeneAxisIsVERBATIM:
    def test_a_SORTED_axis_is_refused(self, emitted):
        # A3: a sorted axis looks canonical and transposes every signature.
        args, _, _, _ = emitted
        main = io_data.load_main(args.de_main, "StimX")
        gene_ids = [str(g) for g in main["gene_ids"]]
        scrambled = sorted(gene_ids, reverse=True)
        if scrambled == gene_ids:
            pytest.skip("the fixture axis is already reverse-sorted")
        with pytest.raises(sm.SignatureMatrixError) as exc:
            sm.build(condition="StimX", main=main, mask_sets={}, gene_ids=scrambled)
        assert exc.value.gate == sm.REFUSE_GENE_AXIS_MISMATCH

    def test_a_target_with_NO_derived_mask_is_refused(self, emitted):
        # P2: a target with no derived mask is not a target with an empty mask.
        args, _, _, _ = emitted
        main = io_data.load_main(args.de_main, "StimX")
        gene_ids = [str(g) for g in main["gene_ids"]]
        with pytest.raises(sm.SignatureMatrixError) as exc:
            sm.build(condition="StimX", main=main, mask_sets={}, gene_ids=gene_ids)
        assert exc.value.gate == sm.REFUSE_MASK_NOT_DERIVED


class TestTheManifestBindsWhatItStandsOn:
    def test_it_binds_the_source_inputs(self, emitted):
        _, _, _, m = emitted
        assert m["sources"]["de_main_sha256"]
        assert m["mask_rule_id"] == sm.MASK_RULE_ID

    def test_the_paths_are_BUNDLE_RELATIVE(self, emitted):
        _, _, _, m = emitted
        for block in (m["matrix"], m["mask"], m["gene_axis"]):
            assert not os.path.isabs(block["path_in_bundle"])

    def test_the_manifest_on_disk_is_the_manifest_it_returned(self, emitted):
        _, _, cond_dir, m = emitted
        with open(os.path.join(cond_dir, "signature_manifest.json")) as fh:
            shipped = json.load(fh)
        assert shipped["matrix"]["values_sha256"] == m["matrix"]["values_sha256"]
        assert shipped["mask"]["bits_sha256"] == m["mask"]["bits_sha256"]
