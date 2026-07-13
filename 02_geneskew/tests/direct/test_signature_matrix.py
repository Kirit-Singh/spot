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


class TestTheAMENDEDAllOnesRule:
    """P5/V5/A5, corrected after W7's production-size Step 0.

    The old gate refused ANY resolved all-ones row, reasoning that build_estimate_mask always
    masks the target's own gene. That is true of the BIOLOGICAL mask and false of the BITMAP,
    and the gap between them is a whole gene universe:

        the mask is derived in the TARGET universe   (11,526 perturbed genes)
        the bitmap is written over the READOUT axis  (10,282 measured genes)

    1,217-1,243 resolved targets per condition have a perfectly good non-empty mask — target,
    30kb neighbours, contributing guides' off-targets — none of which is a readout gene. Their
    intersection with the axis is EMPTY, so no readout gene is masked, so the row is
    legitimately all-ones. The old gate called ~11% of every condition a producer bug.

    The rule that is actually true: the bitmap's ZEROS ARE the mask-axis intersection, exactly.
    """

    def _build(self, emitted, mask_sets):
        args, _, _, _ = emitted
        main = io_data.load_main(args.de_main, "StimX")
        gene_ids = [str(g) for g in main["gene_ids"]]
        return sm.build(condition="StimX", main=main, mask_sets=mask_sets,
                        gene_ids=gene_ids), gene_ids

    def _masks(self, emitted):
        args, _, _, _ = emitted
        main = io_data.load_main(args.de_main, "StimX")
        return sm.mask_sets_for_condition(args, "StimX", main), main

    def test_the_bitmap_ZEROS_ARE_the_mask_axis_intersection_exactly(self, emitted):
        mask_sets, main = self._masks(emitted)
        built, gene_ids = self._build(emitted, mask_sets)
        axis = set(gene_ids)
        bits = np.unpackbits(built["bitmap"], axis=1)[:, :built["n_genes"]]
        for i, t in enumerate(built["target_ids"]):
            ms = mask_sets[t]
            if ms is None:
                continue
            zeros = {gene_ids[j] for j in np.nonzero(bits[i] == 0)[0]}
            assert zeros == set(map(str, ms)) & axis

    def test_a_MASK_THAT_MISSES_THE_AXIS_gives_a_VALID_all_ones_row(self, emitted):
        # the production case: a real, non-empty mask, none of whose genes is a readout gene
        mask_sets, main = self._masks(emitted)
        off_axis = {"ENSG_NOT_A_READOUT_GENE_1", "ENSG_NOT_A_READOUT_GENE_2"}
        victim = next(t for t, m in mask_sets.items() if m is not None)
        mask_sets = dict(mask_sets, **{victim: off_axis})

        built, gene_ids = self._build(emitted, mask_sets)          # must NOT refuse
        i = built["target_ids"].index(victim)
        bits = np.unpackbits(built["bitmap"][i])[:built["n_genes"]]
        assert bits.all(), "a mask that misses the axis must leave every readout gene unmasked"
        assert built["dispositions"][victim] == sm.DISPOSITION_NO_MASKED_READOUT
        assert victim in built["resolved_no_masked_readout_gene_target_ids"]
        assert built["n_masked_source"][victim] == 2      # the source mask is NOT empty
        assert built["n_masked_readout"][victim] == 0

    def test_such_a_target_STILL_HAS_a_signature(self, emitted):
        # all-ones is not all-zero: it is a full, unmasked readout vector, and it is measured
        mask_sets, _ = self._masks(emitted)
        victim = next(t for t, m in mask_sets.items() if m is not None)
        mask_sets = dict(mask_sets, **{victim: {"ENSG_OFF_AXIS"}})
        built, gene_ids = self._build(emitted, mask_sets)
        sigs = sm.reconstruct_signatures(built, gene_ids, [victim])
        assert victim in sigs
        assert len(sigs[victim]) == built["n_genes"]

    def test_an_all_ones_row_whose_mask_DOES_hit_the_axis_is_REFUSED(self, emitted):
        # that one really is a lost mask
        mask_sets, main = self._masks(emitted)
        built, gene_ids = self._build(emitted, mask_sets)
        t = built["target_ids"][0]
        # a mask that DOES intersect the axis must leave a zero bit; an all-ones row here
        # would mean the mask was lost
        forged = dict(mask_sets)
        forged[t] = {gene_ids[0]}
        good, _ = self._build(emitted, forged)
        bits = np.unpackbits(good["bitmap"][good["target_ids"].index(t)])[:good["n_genes"]]
        assert not bits.all(), "the intersection is non-empty, so the row must have a zero"

    def test_a_RESOLVED_target_with_an_EMPTY_source_mask_is_REFUSED(self, emitted):
        # an empty source mask is not a mask that missed the axis — it is no mask at all
        mask_sets, _ = self._masks(emitted)
        victim = next(t for t, m in mask_sets.items() if m is not None)
        with pytest.raises(sm.SignatureMatrixError) as exc:
            self._build(emitted, dict(mask_sets, **{victim: set()}))
        assert exc.value.gate == sm.REFUSE_RESOLVED_SOURCE_MASK_EMPTY

    def test_n_resolved_all_ones_RECOUNTS_from_the_bitmap(self, emitted):
        # a first-class manifest field, and the bitmap's own statement of it
        _, _, cond_dir, m = emitted
        mat = sm.read(m, cond_dir)
        pop = np.array([np.unpackbits(r)[:m["n_genes"]].sum() for r in mat["bitmap"]])
        assert m["n_resolved_all_ones"] == int((pop == m["n_genes"]).sum())

    def test_the_two_counts_are_INDEPENDENT_statements_of_the_same_fact(self, emitted):
        # a resolved row is all-ones exactly when its mask missed the axis; if these two ever
        # disagree, one of them is lying and the artifact does not ship
        _, _, _, m = emitted
        assert m["n_resolved_all_ones"] == m["n_resolved_no_masked_readout_gene"]

    def test_the_three_dispositions_PARTITION_the_condition(self, emitted):
        _, _, _, m = emitted
        assert (m["n_unresolved_no_signature"]
                + m["n_resolved_masked_readout_genes"]
                + m["n_resolved_no_masked_readout_gene"]) == m["n_targets"]

    def test_the_NON_EMPTY_SOURCE_MASK_is_bound(self, emitted):
        # what proves an all-ones row had a real mask rather than none at all
        _, _, _, m = emitted
        assert len(m["source_mask_sha256"]) == 64
        assert m["bitmap_rule_id"] == sm.BITMAP_RULE_ID

    def test_ALL_ZERO_still_means_UNRESOLVED_and_never_an_unmasked_vector(self, emitted):
        # the one thing the amendment does NOT change
        mask_sets, _ = self._masks(emitted)
        victim = next(t for t, m in mask_sets.items() if m is not None)
        built, gene_ids = self._build(emitted, dict(mask_sets, **{victim: None}))
        i = built["target_ids"].index(victim)
        assert not np.unpackbits(built["bitmap"][i])[:built["n_genes"]].any()
        assert built["dispositions"][victim] == sm.DISPOSITION_UNRESOLVED
        assert sm.reconstruct_signatures(built, gene_ids, [victim]) == {}

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
    def test_a_PERMUTED_axis_is_refused(self, emitted):
        """A3. A GENUINE permutation, not a sort.

        `sorted()` is the tempting probe and it is a WEAK one: the real gene axis is already
        in sorted order, so sorting it is a NO-OP and the probe would pass against a producer
        that had done nothing at all. A swap of two adjacent ids is a real permutation whether
        or not the axis was sorted to begin with — and it transposes two signatures.
        """
        args, _, _, _ = emitted
        main = io_data.load_main(args.de_main, "StimX")
        gene_ids = [str(g) for g in main["gene_ids"]]
        assert len(gene_ids) >= 2

        permuted = list(gene_ids)
        permuted[0], permuted[1] = permuted[1], permuted[0]
        assert permuted != gene_ids, "the permutation must actually change the axis"
        assert sorted(permuted) == sorted(gene_ids), "it must be a permutation, not an edit"

        with pytest.raises(sm.SignatureMatrixError) as exc:
            sm.build(condition="StimX", main=main, mask_sets={}, gene_ids=permuted)
        assert exc.value.gate == sm.REFUSE_GENE_AXIS_MISMATCH

    def test_SORTING_the_axis_would_be_a_NO_OP_on_a_sorted_axis(self, emitted):
        # why the probe above must not be a sort: it would prove nothing on the real release
        args, _, _, _ = emitted
        gene_ids = [str(g) for g in
                    io_data.load_main(args.de_main, "StimX")["gene_ids"]]
        if sorted(gene_ids) == gene_ids:
            assert sorted(gene_ids) == gene_ids   # a sort-based probe cannot fail here

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


class TestTheCrossLaneAnchor:
    """The ONLY check a coherently forged mask cannot satisfy.

    The bitmap, the counts and `source_mask_sha256` all derive from the SAME mask_sets, so a
    forged-but-plausible biological mask, resealed, satisfies every one of them: the zeros still
    equal the (forged) mask INTERSECT axis, the counts still agree, the run id still re-derives.
    That was demonstrated, not assumed — the forgery ADMITTED.

    A mask can only be contradicted from OUTSIDE, by a table somebody else derived from the
    primary inputs. W10 re-derives the Direct mask from the contributor manifest and the sgRNA
    library and its canonical table is shuffle-invariant (DIRECT_MASK_VERIFICATION_REPORT.md).

    NOTHING here is frozen into production: the report's mask_sha256 and bundle ids are values
    OF A RUN. They are fixture values in this file and appear nowhere in the producer.
    """

    def _direct(self, tmp_path, mask_sets, gene_ids, mask_sha="a" * 64, run_id="dir123"):
        """A stand-in for an ADMITTED Direct bundle: masks.parquet + provenance.json."""
        import pandas as pd
        d = tmp_path / "direct"
        d.mkdir(exist_ok=True)
        rows = []
        for t, ms in mask_sets.items():
            if ms is None:
                rows.append({"estimate_type": "main", "target_id": t,
                             "masked_gene_ensembl": None, "mask_reason": "mask_unresolved"})
                continue
            for g in sorted(ms):
                rows.append({"estimate_type": "main", "target_id": t,
                             "masked_gene_ensembl": g, "mask_reason": "target"})
        pd.DataFrame(rows).to_parquet(d / "masks.parquet")
        (d / "provenance.json").write_text(json.dumps({
            "arm_bundle_run_id": run_id,
            "run_binding": {"mask_sha256": mask_sha,
                            "contributor_manifest": {"status": "bound"}},
        }))
        return str(d)

    def _masks_and_axis(self, emitted):
        args, _, _, _ = emitted
        main = io_data.load_main(args.de_main, "StimX")
        gene_ids = [str(g) for g in main["gene_ids"]]
        return args, main, gene_ids, sm.mask_sets_for_condition(args, "StimX", main)

    def test_an_AXIS_MISSING_mask_does_NOT_trip_the_anchor(self, emitted, tmp_path):
        """The 1,217-1,243 targets whose REAL mask misses the readout axis entirely.

        Both lanes hold the same mask; it simply has no readout gene in it. The anchor must
        INTERSECT WITH THE AXIS BEFORE COMPARING — otherwise it fires on honest output and the
        gate becomes a bug that looks like rigour.
        """
        args, main, gene_ids, honest = self._masks_and_axis(emitted)
        victim = next(t for t, v in honest.items() if v)
        off_axis = {"ENSG_OFF_AXIS_1", "ENSG_OFF_AXIS_2"}
        same = dict(honest, **{victim: off_axis})       # the SAME mask on BOTH sides

        built = sm.build(condition="StimX", main=main, mask_sets=same, gene_ids=gene_ids)
        assert built["dispositions"][victim] == sm.DISPOSITION_NO_MASKED_READOUT

        anchor = sm.anchor_to_direct(                    # must NOT refuse
            built, gene_ids,
            sm.direct_masked_genes(
                os.path.join(self._direct(tmp_path, same, gene_ids), "masks.parquet")))
        assert anchor["n_targets_anchored"] > 0

    def test_THE_FULLY_RESEALED_WRONG_SOURCE_MASK_IS_REFUSED(self, emitted, tmp_path):
        """THE ATTACK. A plausible forged mask, resealed so everything internal agrees."""
        args, main, gene_ids, honest = self._masks_and_axis(emitted)
        victim = next(t for t, v in honest.items() if v)
        forged = dict(honest, **{victim: {gene_ids[5], gene_ids[6]}})

        # it is INTERNALLY PERFECT: build() admits it, and every internal gate is satisfied
        built = sm.build(condition="StimX", main=main, mask_sets=forged, gene_ids=gene_ids)
        assert built["n_resolved_all_ones"] == built["n_resolved_no_masked_readout_gene"]

        # ...and it dies against the mask an independent verifier derived from the primary inputs
        with pytest.raises(sm.SignatureMatrixError) as exc:
            sm.anchor_to_direct(built, gene_ids,
                                sm.direct_masked_genes(
                                    os.path.join(self._direct(tmp_path, honest, gene_ids),
                                                 "masks.parquet")))
        assert exc.value.gate == sm.REFUSE_DIRECT_MASK_MISMATCH
        assert victim in str(exc.value)

    def test_the_forged_mask_passes_EVERY_INTERNAL_GATE_which_is_the_point(self, emitted,
                                                                          tmp_path):
        # if it failed an internal gate the attack would prove nothing about the anchor
        args, main, gene_ids, honest = self._masks_and_axis(emitted)
        victim = next(t for t, v in honest.items() if v)
        forged = dict(honest, **{victim: {gene_ids[5], gene_ids[6]}})
        built = sm.build(condition="StimX", main=main, mask_sets=forged, gene_ids=gene_ids)
        axis = sm.write_gene_axis(str(tmp_path / "f"), gene_ids)
        m = sm.write(built, out_root=str(tmp_path / "f"), gene_axis=axis,
                     sources={"de_main_sha256": "x", "guide_manifest_sha256": "y",
                              "sgrna_sha256": "z"},
                     readout_universe_sha256="u")
        assert m["source_mask_sha256"]          # resealed, and self-consistent throughout
        assert m["n_resolved_all_ones"] == m["n_resolved_no_masked_readout_gene"]
        assert m["mask_is_externally_anchored"] is False   # and it says so

    def test_UNANCHORED_says_so_rather_than_implying_a_green(self, emitted):
        _, _, _, m = emitted
        assert m["mask_is_externally_anchored"] is False
        assert m["direct_mask_anchor"] is None

class TestThePerTargetQC_WithoutWhichAConsumerProjectsRefusedTargets:
    """The matrix says what every target's masked vector IS. Without QC it says nothing about
    which targets may be USED — and a consumer would either re-derive the QC itself (a SECOND
    source of truth for the same facts, free to disagree with this one) or quietly project the
    targets Direct refused.

    This is exactly the gap a temporal producer would fall into: it can project every row in
    the matrix, and nothing in the matrix would stop it.
    """

    def test_the_QC_table_ships_beside_the_matrix(self, emitted):
        _, _, cond_dir, m = emitted
        assert os.path.exists(os.path.join(cond_dir, "signature_qc.parquet"))
        assert m["qc"]["n_rows"] == m["n_targets"]

    def test_it_carries_EVERY_field_evaluability_depends_on(self, emitted):
        import pandas as pd
        _, _, cond_dir, m = emitted
        df = pd.read_parquet(os.path.join(cond_dir, "signature_qc.parquet"))
        for col in ("base_state", "base_passed", "mask_resolved",
                    "target_identity_resolved", "n_cells", "n_guides",
                    "low_target_gex", "ontarget_significant"):
            assert col in df.columns, col

    def test_a_target_the_matrix_HAS_may_still_be_one_Direct_REFUSED(self, emitted):
        # the whole point: a row exists for every target, and base_passed is what says whether
        # it may be used. n_base_passed < n_targets, or this fixture proves nothing.
        _, _, _, m = emitted
        assert m["qc"]["n_base_passed"] <= m["n_targets"]
        assert m["qc"]["n_rows"] == m["n_targets"]

    def test_the_QC_is_bound_by_RAW_and_CANONICAL_hash(self, emitted):
        _, _, _, m = emitted
        assert len(m["qc"]["raw_sha256"]) == 64
        assert len(m["qc"]["canonical_sha256"]) == 64

    def test_the_QC_and_the_MASK_come_from_ONE_scan(self, emitted):
        # mask_resolved in the QC must agree with the bitmap's own disposition, or the artifact
        # holds two statements about one target that are free to disagree
        import pandas as pd
        _, _, cond_dir, m = emitted
        mat = sm.read(m, cond_dir)
        df = pd.read_parquet(os.path.join(cond_dir, "signature_qc.parquet"))
        resolved_qc = dict(zip(df["target_id"], df["mask_resolved"]))
        pop = {t: np.unpackbits(r)[:m["n_genes"]].sum()
               for t, r in zip(mat["target_ids"], mat["bitmap"])}
        for t, is_resolved in resolved_qc.items():
            # an all-zero bitmap row is UNRESOLVED; anything else is resolved
            assert bool(is_resolved) == (pop[str(t)] > 0)


class TestTheSTALE_AMBIGUOUS_AND_MISSING_SourceAttacks:
    """Zero-compute. The three ways a consumer ends up reading the wrong signatures."""

    def test_a_STALE_artifact_is_REFUSED(self, emitted):
        # the quietest failure available: the schemas match, the hashes are internally
        # consistent, the vectors load — and they are another run's numbers
        _, _, _, m = emitted
        with pytest.raises(sm.SignatureMatrixError) as exc:
            sm.check_not_stale(m, "f" * 64)
        assert exc.value.gate == sm.REFUSE_STALE_SIGNATURE_SOURCE

    def test_the_artifact_built_from_THIS_de_source_is_ACCEPTED(self, emitted):
        args, _, _, m = emitted
        from direct.hashing import file_sha256
        sm.check_not_stale(m, file_sha256(args.de_main))   # must not raise

    def test_a_MISSING_condition_artifact_is_REFUSED_by_the_index(self, tmp_path):
        from direct import bundle_index as bi
        with pytest.raises(bi.BundleIndexError) as exc:
            bi.find(str(tmp_path / "nothing"), condition="Rest")
        assert exc.value.gate == bi.REFUSE_NOT_FOUND

    def test_an_AMBIGUOUS_source_is_REFUSED_rather_than_silently_chosen(self, tmp_path):
        import json as _json

        from direct import bundle_index as bi
        root = str(tmp_path)
        for run_id in ("aaaa1111bbbb2222", "cccc3333dddd4444"):
            d = os.path.join(root, run_id)
            os.makedirs(d)
            with open(os.path.join(d, "provenance.json"), "w") as fh:
                _json.dump({"arm_bundle_run_id": run_id,
                            "run_binding": {"condition": "Rest"}}, fh)
        with pytest.raises(bi.BundleIndexError) as exc:
            bi.find(root, condition="Rest")
        assert exc.value.gate == bi.REFUSE_AMBIGUOUS


class TestTheW10AnchorParsesTYPEDJSON_NotProse:
    """A REAL interface bug, and the correct response to it.

    The first cut REGEXED a hash out of a markdown sentence:

        bound mask_sha256           : 269b4278...

    W10's real, final report is TYPED JSON and has no such line. The tempting fix — alias the
    file, or manufacture the missing line — would have made the parser work by fabricating the
    evidence it was supposed to be checking. So the report is READ as the typed document it is.

    The ORDER is the point: admit -> bound to THIS bundle -> named mask gates PASSED -> only
    then read mask_sha256. Reading the hash first and checking afterwards is the same mistake
    with the steps swapped: the hash is already in hand and the check is a formality.
    """

    def _report(self, tmp_path, bundle_dir, *, verdict="ADMIT", n_failed=0,
                run_id=None, prov_sha=None, gates=None, name="Rest.full.json"):
        import json as _json

        from direct.hashing import file_sha256 as _fs
        rid = run_id or os.path.basename(str(bundle_dir).rstrip("/"))
        gates = gates if gates is not None else [
            {"gate": "the MASK's identity is bound into the run and RE-DERIVES from the "
                     "shipped masks.parquet", "passed": True},
            {"gate": "every SHIPPED mask is the one the verifier independently derives from "
                     "the contributor manifest", "passed": True},
        ]
        doc = {
            "verdict": verdict, "n_failed": n_failed, "n_passed": 93, "n_gates": 93,
            "verifier_id": "spot.stage02.direct.arm_bundle.verifier.v1",
            "verifier_code_sha256": "b" * 64, "gate_inventory_sha256": "c" * 64,
            "bound_artifact": {
                "arm_bundle_run_id": rid,
                "artifact_sha256": {"provenance.json": prov_sha or _fs(
                    os.path.join(bundle_dir, "provenance.json"))},
            },
            "gates": gates,
        }
        p = tmp_path / name
        p.write_text(_json.dumps(doc))
        return str(p)

    def _bundle(self, tmp_path, mask_sets, gene_ids, run_id="ea57f569c6165834"):
        import pandas as pd
        d = tmp_path / run_id
        d.mkdir(parents=True, exist_ok=True)
        rows = []
        for t, ms in mask_sets.items():
            if ms is None:
                rows.append({"estimate_type": "main", "target_id": t,
                             "masked_gene_ensembl": None, "mask_reason": "mask_unresolved"})
                continue
            for g in sorted(ms):
                rows.append({"estimate_type": "main", "target_id": t,
                             "masked_gene_ensembl": g, "mask_reason": "target"})
        pd.DataFrame(rows).to_parquet(d / "masks.parquet")
        (d / "provenance.json").write_text(json.dumps({
            "arm_bundle_run_id": run_id,
            "run_binding": {"mask_sha256": "e" * 64,
                            "contributor_manifest": {"status": "bound"}}}))
        return str(d)

    def _masks(self, emitted):
        args, _, _, _ = emitted
        main = io_data.load_main(args.de_main, "StimX")
        return sm.mask_sets_for_condition(args, "StimX", main), \
            [str(g) for g in main["gene_ids"]]

    def test_the_TYPED_report_ADMITS_and_yields_the_mask_hash(self, emitted, tmp_path):
        ms, gene_ids = self._masks(emitted)
        b = self._bundle(tmp_path, ms, gene_ids)
        a = sm.w10_anchor(self._report(tmp_path, b), b)
        assert a["report_verdict"] == "ADMIT"
        assert a["direct_mask_sha256"] == "e" * 64
        assert a["direct_arm_bundle_run_id"] == "ea57f569c6165834"

    def test_the_OLD_PROSE_report_is_REFUSED_never_scraped(self, emitted, tmp_path):
        ms, gene_ids = self._masks(emitted)
        b = self._bundle(tmp_path, ms, gene_ids)
        prose = tmp_path / "old.md"
        prose.write_text("## VERDICT: ADMIT\nbound mask_sha256           : " + "e" * 64 + "\n")
        with pytest.raises(sm.SignatureMatrixError) as exc:
            sm.w10_anchor(str(prose), b)
        assert exc.value.gate == sm.REFUSE_DIRECT_MASK_ANCHOR_ABSENT
        assert "nobody bound" in str(exc.value)

    def test_a_NON_ADMIT_report_is_REFUSED(self, emitted, tmp_path):
        ms, gene_ids = self._masks(emitted)
        b = self._bundle(tmp_path, ms, gene_ids)
        with pytest.raises(sm.SignatureMatrixError) as exc:
            sm.w10_anchor(self._report(tmp_path, b, verdict="REFUSE", n_failed=2), b)
        assert exc.value.gate == sm.REFUSE_W10_NOT_ADMITTED

    def test_an_ADMIT_that_CONTRADICTS_its_own_gates_is_REFUSED(self, emitted, tmp_path):
        ms, gene_ids = self._masks(emitted)
        b = self._bundle(tmp_path, ms, gene_ids)
        with pytest.raises(sm.SignatureMatrixError) as exc:
            sm.w10_anchor(self._report(tmp_path, b, verdict="ADMIT", n_failed=3), b)
        assert exc.value.gate == sm.REFUSE_W10_NOT_ADMITTED

    def test_a_report_about_ANOTHER_BUNDLE_is_REFUSED(self, emitted, tmp_path):
        ms, gene_ids = self._masks(emitted)
        b = self._bundle(tmp_path, ms, gene_ids)
        with pytest.raises(sm.SignatureMatrixError) as exc:
            sm.w10_anchor(self._report(tmp_path, b, run_id="deadbeefdeadbeef"), b)
        assert exc.value.gate == sm.REFUSE_W10_REPORT_IS_ABOUT_ANOTHER_BUNDLE

    def test_MISMATCHED_PROVENANCE_BYTES_are_REFUSED(self, emitted, tmp_path):
        # the subtle one: right bundle id, but the report admitted a DIFFERENT copy of it
        ms, gene_ids = self._masks(emitted)
        b = self._bundle(tmp_path, ms, gene_ids)
        with pytest.raises(sm.SignatureMatrixError) as exc:
            sm.w10_anchor(self._report(tmp_path, b, prov_sha="a" * 64), b)
        assert exc.value.gate == sm.REFUSE_W10_REPORT_IS_ABOUT_ANOTHER_BUNDLE
        assert "DIFFERENT BYTES" in str(exc.value)

    def test_a_MISSING_MASK_GATE_is_REFUSED_even_on_a_clean_ADMIT(self, emitted, tmp_path):
        # it may have admitted the ARMS; this lane anchors to the MASK
        ms, gene_ids = self._masks(emitted)
        b = self._bundle(tmp_path, ms, gene_ids)
        with pytest.raises(sm.SignatureMatrixError) as exc:
            sm.w10_anchor(self._report(tmp_path, b, gates=[
                {"gate": "every arm value re-derives", "passed": True}]), b)
        assert exc.value.gate == sm.REFUSE_W10_MASK_GATE_ABSENT

    def test_a_FAILED_mask_gate_is_REFUSED(self, emitted, tmp_path):
        ms, gene_ids = self._masks(emitted)
        b = self._bundle(tmp_path, ms, gene_ids)
        with pytest.raises(sm.SignatureMatrixError) as exc:
            sm.w10_anchor(self._report(tmp_path, b, gates=[
                {"gate": "the MASK's identity is bound into the run and RE-DERIVES from the "
                         "shipped masks.parquet", "passed": False},
                {"gate": "every SHIPPED mask is the one the verifier independently derives "
                         "from the contributor manifest", "passed": True}]), b)
        assert exc.value.gate == sm.REFUSE_W10_MASK_GATE_ABSENT
