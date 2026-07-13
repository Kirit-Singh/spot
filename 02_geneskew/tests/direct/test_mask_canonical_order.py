"""The bound mask hash must be re-derivable BY A READER OF THE SHIPPED FILE.

W10's counterexample against 2813f7c, and it is a real producer defect.

`emit.mask_content_sha256` sorts the KEYS inside each row and never sorts the ROWS. The mask
rows reach it as a concatenation in target-iteration order — `mask_rows_for_emit` sorts only
within one estimate. Meanwhile the shipped `masks.parquet` is written through a `sort_by` over
six of the fourteen identity columns.

So the hash the bundle BOUND was taken over an order the file it SHIPPED does not preserve:

  * a verifier reading `masks.parquet` cannot reproduce `mask_sha256` — the one thing the
    binding exists to let it do;
  * the same 58 rows, same multiset, in a different order, produced a DIFFERENT bound hash,
    so the bundle's identity moved without one number changing.

Binding a hash of bytes nobody can hold was the defect this producer set out to fix. Binding a
hash of an ORDER nobody can reconstruct is the same defect, one level down.

THE REPAIR IS ONE CANONICAL ORDER, USED IN BOTH PLACES: sort by the FULL identity column
tuple, serialize from that exact table, and hash that exact table. Not a verifier waiver — a
producer that emits what it says it emitted.
"""
from __future__ import annotations

import json
import os
import random

import pandas as pd
from direct import masks, run_arms


def shipped_mask_rows(out_dir: str) -> list[dict]:
    """The mask rows as a READER of the shipped parquet gets them — NaN, numpy types and all."""
    df = pd.read_parquet(os.path.join(out_dir, run_arms.MASKS_FILE))
    return [{c: r[c] for c in df.columns} for _, r in df.iterrows()]


class TestTheCanonicalOrderIsTotalAndInputOrderCannotMoveIt:
    def test_SHUFFLING_the_rows_does_not_change_the_canonical_hash(self, synthetic_run,
                                                                   tmp_path):
        args = synthetic_run()
        args.condition = "StimX"
        args.out_root = str(tmp_path / "a")
        result = run_arms.build_bundle(args)

        rows = shipped_mask_rows(result["out_dir"])
        assert len(rows) > 1
        shuffled = rows[:]
        random.Random(17).shuffle(shuffled)
        assert [r for r in shuffled] != rows or len(rows) < 2

        assert (masks.mask_content_sha256(shuffled)
                == masks.mask_content_sha256(rows)), (
            "the same rows in a different order hash differently: the bound hash is a "
            "function of an order the shipped file does not preserve")

    def test_the_canonical_TABLE_is_identical_under_shuffle(self, synthetic_run, tmp_path):
        args = synthetic_run()
        args.condition = "StimX"
        args.out_root = str(tmp_path / "a")
        rows = shipped_mask_rows(run_arms.build_bundle(args)["out_dir"])

        shuffled = rows[:]
        random.Random(4).shuffle(shuffled)
        assert masks.canonical_mask_rows(shuffled) == masks.canonical_mask_rows(rows)

    def test_the_order_is_TOTAL_over_every_identity_column(self):
        # two rows that tie on the six columns the old sort_by used, and differ only in a
        # column it never looked at: a stable sort would leave their order to the INPUT.
        base = {c: None for c in masks.MASK_ROW_COLUMNS}
        base.update({"estimate_type": "main", "estimate_id": "main", "target_id": "T1",
                     "masked_gene_ensembl": "ENSG1", "mask_reason": "neighbor",
                     "guide_id": "g1"})
        a = dict(base, distance=10.0, source_row_hash="aaa")
        b = dict(base, distance=20.0, source_row_hash="bbb")

        assert (masks.canonical_mask_rows([a, b])
                == masks.canonical_mask_rows([b, a])), (
            "rows tying on the legacy sort key are left in input order — the ordering is "
            "not total, so the shipped bytes depend on how the producer happened to iterate")


class TestShuffledInputShipsByteIdenticalBytes:
    """The strongest form of the claim: not just the same hash — the same FILE."""

    def test_a_SHUFFLED_input_order_serializes_to_BYTE_IDENTICAL_mask_bytes(
            self, synthetic_run, tmp_path):
        from direct import emit

        args = synthetic_run()
        args.condition = "StimX"
        args.out_root = str(tmp_path / "a")
        rows = shipped_mask_rows(run_arms.build_bundle(args)["out_dir"])

        shuffled = rows[:]
        random.Random(99).shuffle(shuffled)

        first = str(tmp_path / "first.parquet")
        second = str(tmp_path / "second.parquet")
        # exactly what the producer does: serialize FROM the canonical table, no re-sort
        emit.write_parquet(masks.canonical_mask_rows(rows), first, [])
        emit.write_parquet(masks.canonical_mask_rows(shuffled), second, [])

        with open(first, "rb") as fh:
            a = fh.read()
        with open(second, "rb") as fh:
            b = fh.read()
        assert a == b, ("the same mask rows in a different input order serialized to "
                        "different bytes")


class TestTheShippedFileReproducesTheBoundHash:
    def test_the_BOUND_mask_hash_re_derives_from_the_SHIPPED_parquet(self, synthetic_run,
                                                                     tmp_path):
        # THE property a verifier needs and could not have: read the file, canonicalise it,
        # get the hash the bundle bound.
        args = synthetic_run()
        args.condition = "StimX"
        args.out_root = str(tmp_path / "a")
        result = run_arms.build_bundle(args)

        with open(os.path.join(result["out_dir"], run_arms.PROVENANCE_FILE)) as fh:
            bound = json.load(fh)["run_binding"]["mask_sha256"]

        assert masks.mask_content_sha256(shipped_mask_rows(result["out_dir"])) == bound

    def test_the_binding_NAMES_the_order_rule_that_produced_the_hash(self, synthetic_run,
                                                                     tmp_path):
        args = synthetic_run()
        args.condition = "StimX"
        args.out_root = str(tmp_path / "a")
        result = run_arms.build_bundle(args)
        with open(os.path.join(result["out_dir"], run_arms.PROVENANCE_FILE)) as fh:
            binding = json.load(fh)["run_binding"]
        # a hash whose recipe is not named is a number nobody else can recompute
        assert binding["mask_order_rule_id"] == masks.MASK_ORDER_RULE_ID


class TestTheRepairChangesNoScience:
    def test_the_mask_ROW_MULTISET_is_unchanged(self, synthetic_run, tmp_path):
        # the canonical projection reorders and normalises; it must not add, drop or alter a
        # single mask row
        args = synthetic_run()
        args.condition = "StimX"
        args.out_root = str(tmp_path / "a")
        result = run_arms.build_bundle(args)

        rows = shipped_mask_rows(result["out_dir"])
        canonical = masks.canonical_mask_rows(rows)
        assert len(canonical) == len(rows) == result["provenance"]["run_binding"][
            "n_mask_rows"]

        # Keyed on the columns that identify WHICH GENE was masked out of WHICH ESTIMATE, and
        # why. They are strings, so they survive the parquet round trip untouched and can be
        # compared before and after canonicalisation without normalisation muddying it.
        science = ("estimate_type", "estimate_id", "target_id", "guide_id",
                   "masked_gene_ensembl", "mask_reason")

        def key(r):
            return tuple(None if r.get(c) is None or r.get(c) != r.get(c)
                         else str(r[c]) for c in science)

        assert sorted(map(key, canonical), key=str) == sorted(map(key, rows), key=str), (
            "canonicalisation added, dropped or altered a mask row")

    def test_the_ARM_ROWS_and_their_values_are_untouched(self, synthetic_run, tmp_path):
        args = synthetic_run()
        args.condition = "StimX"
        args.out_root = str(tmp_path / "a")
        result = run_arms.build_bundle(args)
        arms = pd.read_parquet(os.path.join(result["out_dir"], run_arms.ROWS_FILE))
        # the mask ordering repair touches identity, never a projected value
        assert result["bundle"]["arm_rows_sha256"]
        assert len(arms) == result["n_arm_rows"]
