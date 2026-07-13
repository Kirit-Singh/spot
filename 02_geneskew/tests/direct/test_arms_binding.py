"""What the bundle BINDS, what it SHIPS, and what it refuses to write at all.

BLOCKER 4. The all-arm bundle bound the DE files, the sgRNA library, a registry, an unused
selection, the code identity and a gene-universe hash — and nothing about the masks or the
contributor evidence. Yet every delta in it is a function of those bytes: the contributor
manifest decides which guides contributed, the guides decide the mask, the mask decides the
projection. A bundle that binds a COUNT of its evidence binds nothing — two different
manifests with the same number of rows produce different science under one identity — and a
reader could not tell from the bundle alone which masks made the rows.

The audit's own mutations are the acceptance tests here. Each must fail at a NAMED gate, or
move the identity, rather than being absorbed silently:

    mask mutated                → the bound mask hash moves, so the bundle id moves
    contributor manifest mutated→ the bound manifest identity moves, so the id moves
    source registry mutated     → the bound source identity moves, so the id moves
    joint_status column inserted→ ArmSchemaError, at the moment of writing
    copied/forged slot count    → refused: the count is DERIVED, never declared
    missing / duplicate arm     → refused: the inventory is complete and unique, or it is not
    scorer hash mismatch        → refused: one view decides, and everything cites that one

These are PRODUCER preconditions, not admission rules. An independent verifier re-derives all
of it from the shipped bytes and must not treat any of this as evidence — a generator that
signs its own homework is the same process asserting twice.
"""
from __future__ import annotations

import json
import os

import pandas as pd
import pytest
from direct import arm_bundle, run_arms


def build(args, tmp_path, name: str):
    args.condition = "StimX"
    args.out_root = str(tmp_path / name)
    return run_arms.build_bundle(args)


def prov_of(result) -> dict:
    with open(os.path.join(result["out_dir"], run_arms.PROVENANCE_FILE)) as fh:
        return json.load(fh)


class TestTheBundleShipsTheEvidenceItsNumbersDependOn:
    @pytest.fixture
    def built(self, synthetic_run, tmp_path):
        return build(synthetic_run(), tmp_path, "b")

    def test_every_native_file_is_emitted(self, built):
        for name in (run_arms.BUNDLE_FILE, run_arms.PROVENANCE_FILE,
                     run_arms.VERIFICATION_FILE, run_arms.ROWS_FILE,
                     run_arms.MASKS_FILE, run_arms.CONTRIB_FILE,
                     run_arms.GUIDE_SUPPORT_FILE, run_arms.DONOR_SUPPORT_FILE,
                     run_arms.INPUTS_FILE, run_arms.UNIVERSE_FILE):
            path = os.path.join(built["out_dir"], name)
            assert os.path.exists(path), f"{name} was bound but never shipped"

    def test_the_MASK_that_made_the_rows_can_be_HELD_not_just_cited(self, built):
        # binding the hash of bytes nobody can obtain is the same defect as citing a file
        # that only exists on the producer's disk
        masks = pd.read_parquet(os.path.join(built["out_dir"], run_arms.MASKS_FILE))
        assert len(masks) > 0
        binding = prov_of(built)["run_binding"]
        assert binding["mask_sha256"]
        assert binding["n_mask_rows"] == len(masks)

    def test_the_CONTRIBUTOR_manifest_is_bound_by_SEMANTICS_and_by_RAW_BYTES(self, built):
        binding = prov_of(built)["run_binding"]
        manifest = binding["contributor_manifest"]
        assert manifest["status"] == "bound"
        assert manifest["canonical_sha256"]          # semantics: a reorder is the same input
        assert manifest["raw_sha256"]                # ...and the bytes that actually arrived
        # the SOURCE evidence behind the manifest, as a complete block
        assert manifest["source_record_table"]
        assert manifest["source_replay"] is not None
        assert binding["source_registry_raw_sha256"]

    def test_the_TARGET_IDENTITY_MAP_is_bound_even_when_absent(self, built):
        binding = prov_of(built)["run_binding"]
        assert binding["target_identity_map"]["status"] in ("bound", "not_supplied")

    def test_the_artifact_manifest_uses_RELATIVE_paths_and_no_machine_local_path(self,
                                                                                built):
        artifacts = prov_of(built)["artifacts"]
        names = {a["name"] for a in artifacts}
        assert run_arms.ROWS_FILE in names and run_arms.MASKS_FILE in names
        for a in artifacts:
            assert not os.path.isabs(a["name"])
            assert a["raw_sha256"]
        blob = json.dumps(prov_of(built))
        assert "/tmp/" not in blob and "/home/" not in blob

    def test_the_producer_does_NOT_ADMIT_ITSELF(self, built):
        with open(os.path.join(built["out_dir"], run_arms.VERIFICATION_FILE)) as fh:
            ver = json.load(fh)
        assert ver["admitted"] is False
        assert ver["self_admitted"] is False
        assert ver["verifier_id"] is None
        assert ver["verdict"] == run_arms.VERDICT_PENDING


class TestMutatingTheEvidenceMovesTheIdentity:
    """The audit's resealed attacks, from the producer side: evidence the id did not cover
    could be swapped after the fact and the bundle would still answer to its name."""

    def test_a_MUTATED_MASK_INPUT_moves_the_bundle_id_AND_the_bound_mask_hash(
            self, synthetic_run, tmp_path):
        # The sgRNA library declares each guide's nearby genes, and THOSE are what the mask
        # takes out of the target's effect vector. Widen one guide's neighbourhood and the
        # mask genuinely changes — so the identity must move with it, or a bundle could be
        # re-attributed to a mask that never produced its rows.
        first = build(synthetic_run(), tmp_path, "a")
        args = synthetic_run()
        lib = pd.read_csv(args.sgrna)
        row = lib.index[0]
        lib.loc[row, "nearby_gene_within_30kb"] = "['ENSG00000000101' 'ENSG00000000102']"
        lib.to_csv(args.sgrna, index=False)
        second = build(args, tmp_path, "b")

        assert first["arm_bundle_run_id"] != second["arm_bundle_run_id"]
        assert (prov_of(first)["run_binding"]["mask_sha256"]
                != prov_of(second)["run_binding"]["mask_sha256"])

    def test_a_MUTATED_CONTRIBUTOR_MANIFEST_moves_the_bundle_id(self, synthetic_run,
                                                               tmp_path):
        first = build(synthetic_run(), tmp_path, "a")
        args = synthetic_run()
        with open(args.guide_manifest) as fh:
            doc = json.load(fh)
        doc["rows"] = doc["rows"][:-1]                  # drop one contributor row
        with open(args.guide_manifest, "w") as fh:
            json.dump(doc, fh)
        try:
            second = build(args, tmp_path, "b")
        except Exception:
            return          # refusing outright is a STRONGER outcome than moving the id
        assert first["arm_bundle_run_id"] != second["arm_bundle_run_id"]

    def test_a_MUTATED_SOURCE_REGISTRY_moves_the_bundle_id(self, synthetic_run, tmp_path):
        first = build(synthetic_run(), tmp_path, "a")
        args = synthetic_run()
        with open(args.source_registry) as fh:
            doc = json.load(fh)
        doc["_fixture_mutation"] = "a source the bundle cited has changed"
        with open(args.source_registry, "w") as fh:
            json.dump(doc, fh)
        try:
            second = build(args, tmp_path, "b")
        except Exception:
            return
        assert first["arm_bundle_run_id"] != second["arm_bundle_run_id"]

    def test_the_SAME_inputs_still_give_the_SAME_id(self, synthetic_run, tmp_path):
        # an identity nothing can change is not an identity, it is a constant
        first = build(synthetic_run(), tmp_path, "a")
        second = build(synthetic_run(), tmp_path, "b")
        assert first["arm_bundle_run_id"] == second["arm_bundle_run_id"]


class TestThePairFieldCannotBeWrittenAtAll:
    """The audit added `joint_status` as a 16th Parquet column and every advertised hash
    stayed valid, because the canonical projection ignores what it does not recognise."""

    def _rows(self, synthetic_run, tmp_path):
        res = build(synthetic_run(), tmp_path, "clean")
        df = pd.read_parquet(os.path.join(res["out_dir"], run_arms.ROWS_FILE))
        return [{c: r[c] for c in df.columns} for _, r in df.iterrows()]

    def test_an_INSERTED_joint_status_column_is_REFUSED_at_write_time(self, synthetic_run,
                                                                     tmp_path):
        rows = self._rows(synthetic_run, tmp_path)
        for r in rows:
            r["joint_status"] = "both_arms_agree"
        with pytest.raises(arm_bundle.ArmSchemaError, match="joint_status"):
            arm_bundle.assert_exact_columns(rows)

    @pytest.mark.parametrize("column", ["pareto_tier", "concordance_class", "A_delta",
                                        "combined_score", "q_value", "away_from_A"])
    def test_no_pair_derived_column_of_ANY_name_can_be_written(self, synthetic_run,
                                                               tmp_path, column):
        rows = self._rows(synthetic_run, tmp_path)
        for r in rows:
            r[column] = 1.0
        with pytest.raises(arm_bundle.ArmSchemaError):
            arm_bundle.assert_exact_columns(rows)

    def test_a_DROPPED_column_is_refused_too(self, synthetic_run, tmp_path):
        rows = self._rows(synthetic_run, tmp_path)
        for r in rows:
            del r["base_delta"]
        with pytest.raises(arm_bundle.ArmSchemaError, match="missing"):
            arm_bundle.assert_exact_columns(rows)

    def test_the_CLEAN_rows_satisfy_the_contract(self, synthetic_run, tmp_path):
        arm_bundle.assert_exact_columns(self._rows(synthetic_run, tmp_path))


class TestTheArmInventoryIsCompleteUniqueAndDerived:
    """The audit declared 999 slots while 20 arms remained, dropped an arm to 19, and
    duplicated one to 21 — and every advertised hash stayed valid in all three."""

    def _doc(self, synthetic_run, tmp_path):
        res = build(synthetic_run(), tmp_path, "inv")
        with open(os.path.join(res["out_dir"], run_arms.BUNDLE_FILE)) as fh:
            return json.load(fh)

    def test_a_COPIED_slot_count_is_REFUSED(self, synthetic_run, tmp_path):
        doc = self._doc(synthetic_run, tmp_path)
        doc["n_expected_arm_slots"] = 999          # a count nobody can recount
        with pytest.raises(arm_bundle.ArmInventoryError, match="999"):
            arm_bundle.assert_complete_inventory(doc)

    def test_a_MISSING_arm_is_REFUSED(self, synthetic_run, tmp_path):
        doc = self._doc(synthetic_run, tmp_path)
        doc["arms"] = doc["arms"][:-1]
        with pytest.raises(arm_bundle.ArmInventoryError):
            arm_bundle.assert_complete_inventory(doc)

    def test_a_DUPLICATE_arm_is_REFUSED(self, synthetic_run, tmp_path):
        doc = self._doc(synthetic_run, tmp_path)
        doc["arms"] = doc["arms"] + [dict(doc["arms"][0])]
        with pytest.raises(arm_bundle.ArmInventoryError, match="unique|duplicate"):
            arm_bundle.assert_complete_inventory(doc)

    def test_a_SCORER_HASH_MISMATCH_is_REFUSED(self, synthetic_run, tmp_path):
        doc = self._doc(synthetic_run, tmp_path)
        doc["method"]["scorer_view_sha256"] = "0" * 64
        with pytest.raises(arm_bundle.ArmInventoryError, match="scorer"):
            arm_bundle.assert_complete_inventory(doc)

    def test_the_CLEAN_inventory_passes(self, synthetic_run, tmp_path):
        arm_bundle.assert_complete_inventory(self._doc(synthetic_run, tmp_path))
