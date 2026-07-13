"""THE VIEW MUST BE A PROJECTION OF BYTES IT CHECKED — every attack here once SUCCEEDED.

The defect (independent audit, NO-GO): ``materialize`` copied ``document["table_hashes"]`` into
the view and never re-derived it, and never called the store's selection-independence check. So:

    build a v2 document -> mutate a SELECTED edge's arm_rank to 999 -> materialize -> ADMITTED,

emitting a view built over the MUTATED rows while publishing the digest of the rows it was NOT
over. A hash you copy is not a hash you checked. It is the same defect Stage 3 shipped and fixed
earlier this round (an admission that carried a verdict and a verifier name but never hashed the
bundle it admitted), one level up.

EVERY TEST HERE IS NON-VACUOUS BY CONSTRUCTION. An empty store leaks nothing and mutates to
nothing, so :class:`TestTheStoreIsRealBeforeAnyAttack` asserts the rows exist FIRST — otherwise
each attack below would "pass" against a store with nothing in it to attack.
"""
from __future__ import annotations

import json
import os
import shutil

import pandas as pd
import pytest

from druglink import artifacts_v2 as av2
from druglink import pathway_context_v2 as pc2
from druglink import view_contract as vc
from druglink import view_store as vst

from selection_world import TEMPORAL, WITHIN, _conditions, _programs, _verified, _view

# `pathway_context` is EMPTY BY POLICY (the pathway lane is not admitted: a gene-set enrichment
# record never sources a drug edge). Its attack is therefore an INSERTED row — bytes nobody
# hashed — which is the same refusal from the other side.
EMPTY_BY_POLICY = "pathway_context"


def _sel(world):
    programs, conditions = _programs(world), _conditions(world)
    return _verified(world, a=programs[0], b=programs[1], mode=WITHIN,
                     conditions=[conditions[0]])


def _tables(world) -> dict[str, list[dict]]:
    """A deep, independent copy of the store's rows — the caller mutates THIS, never the world."""
    return {name: [dict(r) for r in rows] for name, rows in world["tables"].items()}


# A benign, non-key column per table: enough to move the table's content hash, and never the
# row's own id. A mutation that changed an id would be caught by something else, and would
# prove nothing about the hash the view republishes.
MUTATED_COLUMN = {
    "arm_slots": "n_edges",
    "target_drug_edges": "arm_rank",
    "arm_summaries": "n_edges",
    "candidates": "identity_status",
    "source_records": "identity_status",
    "dispositions": "reason",
    "provenance": "detail",
}


class TestTheStoreIsRealBeforeAnyAttack:
    """Assert the store HAS rows. Otherwise every attack below is vacuous."""

    def test_the_store_has_all_EIGHT_tables_and_seven_of_them_are_NON_EMPTY(self, world):
        assert sorted(world["tables"]) == sorted(av2.SCIENTIFIC_TABLES)
        assert len(av2.SCIENTIFIC_TABLES) == 8
        empty = sorted(n for n in av2.SCIENTIFIC_TABLES if not world["tables"][n])
        assert empty == [EMPTY_BY_POLICY], (
            "the sealed store changed shape; the mutation attacks below are only non-vacuous "
            "against tables that HAVE rows")
        assert pc2.PATHWAY_LANE_ADMITTED is False       # WHY pathway_context is empty
        for name in av2.SCIENTIFIC_TABLES:
            if name != EMPTY_BY_POLICY:
                assert world["tables"][name], f"{name} is empty; its attack would prove nothing"

    def test_the_honest_store_MATERIALIZES_and_the_view_is_not_empty(self, world):
        view = _view(world, _sel(world))
        vc.validate(view)
        assert view["tables"]["target_drug_edges"], "a view that proves nothing is not a view"

    def test_the_honest_store_passes_the_selection_independence_scan(self, world):
        vst.check_store_is_selection_independent(world["document"], world["tables"])


class TestTheAuditsExactAttack:
    """Mutate a SELECTED edge's arm_rank to 999 AFTER the document was built."""

    def test_a_selected_edges_arm_rank_mutated_to_999_is_REFUSED_BY_NAME(self, world):
        sel = _sel(world)
        honest = _view(world, sel)
        target = honest["tables"]["target_drug_edges"][0]["edge_id"]

        tables = _tables(world)
        hit = next(e for e in tables["target_drug_edges"] if e["edge_id"] == target)
        assert hit["arm_rank"] != 999                   # the attack CHANGES something
        hit["arm_rank"] = 999                           # ...after the document was addressed

        with pytest.raises(vst.StoreIdentityError) as exc:
            _view(world, sel, tables=tables)
        assert vst.GATE_TABLES_ARE_NOT_THE_HASHED_BYTES in str(exc.value)
        assert "target_drug_edges" in str(exc.value)

    def test_the_mutated_row_WOULD_have_reached_the_view_so_the_gate_is_load_bearing(self, world):
        """Non-vacuity: the row the attack edits is one this question actually projects."""
        sel = _sel(world)
        honest = _view(world, sel)
        edge = honest["tables"]["target_drug_edges"][0]
        assert edge["arm_key"] in honest["selected_arms"]["gene_arm_keys"]
        assert edge["arm_rank"] != 999


class TestEveryOneOfTheEightTables:
    """A mutation in ANY of the eight moves that table's hash — and each refuses by name."""

    @pytest.mark.parametrize("name", sorted(av2.SCIENTIFIC_TABLES))
    def test_a_mutated_row_in_this_table_is_REFUSED_BY_NAME(self, world, name):
        tables = _tables(world)
        if name == EMPTY_BY_POLICY:
            columns, _ = av2.TABLES[name]
            tables[name].append({c: "INSERTED_BY_AN_ATTACK" for c in columns})
        else:
            column = MUTATED_COLUMN[name]
            assert column in av2.TABLES[name][0], f"{column!r} is not a {name} column"
            tables[name][0][column] = 999 if isinstance(
                tables[name][0][column], int) else "MUTATED_AFTER_THE_DOCUMENT_WAS_ADDRESSED"

        assert av2.table_content_hash(name, tables[name]) \
            != world["document"]["table_hashes"][name], "the attack did not move the hash"

        with pytest.raises(vst.StoreIdentityError) as exc:
            _view(world, _sel(world), tables=tables)
        assert vst.GATE_TABLES_ARE_NOT_THE_HASHED_BYTES in str(exc.value)
        assert name in str(exc.value)

    @pytest.mark.parametrize("name", sorted(av2.SCIENTIFIC_TABLES))
    def test_a_table_DROPPED_from_the_store_in_hand_is_REFUSED(self, world, name):
        tables = _tables(world)
        del tables[name]
        with pytest.raises(vst.StoreIdentityError) as exc:
            _view(world, _sel(world), tables=tables)
        assert vst.GATE_TABLE_HASHES_INCOMPLETE in str(exc.value)


class TestTheDocumentNamesBytesThatAreNotOnDisk:
    """The document is honest, the rows in hand are honest — and the STORE is not."""

    def _copy(self, world, tmp_path) -> str:
        target = str(tmp_path / "store")
        shutil.copytree(world["bundle_dir"], target)
        return target

    def test_a_parquet_MUTATED_on_disk_is_REFUSED_BY_NAME(self, world, tmp_path):
        bundle = self._copy(world, tmp_path)
        path = os.path.join(bundle, "arm_slots.parquet")
        frame = pd.read_parquet(path)
        frame.loc[0, "n_edges"] = 999
        frame.to_parquet(path, index=False)

        with pytest.raises(vst.StoreIdentityError) as exc:
            _view(world, _sel(world), bundle_dir=bundle)
        assert vst.GATE_STORE_ON_DISK_DIFFERS in str(exc.value)
        assert "arm_slots" in str(exc.value)

    def test_a_row_DELETED_on_disk_is_REFUSED_BY_NAME(self, world, tmp_path):
        bundle = self._copy(world, tmp_path)
        path = os.path.join(bundle, "target_drug_edges.parquet")
        frame = pd.read_parquet(path)
        frame.iloc[1:].to_parquet(path, index=False)     # a row nobody will miss

        with pytest.raises(vst.StoreIdentityError) as exc:
            _view(world, _sel(world), bundle_dir=bundle)
        assert vst.GATE_STORE_ON_DISK_DIFFERS in str(exc.value)

    def test_a_table_that_is_NOT_ON_DISK_AT_ALL_is_REFUSED(self, world, tmp_path):
        bundle = self._copy(world, tmp_path)
        os.remove(os.path.join(bundle, "provenance.parquet"))
        with pytest.raises(vst.StoreIdentityError) as exc:
            _view(world, _sel(world), bundle_dir=bundle)
        assert vst.GATE_STORE_ON_DISK_DIFFERS in str(exc.value)

    def test_NO_STORE_ON_DISK_AT_ALL_is_REFUSED(self, world, tmp_path):
        with pytest.raises(vst.StoreIdentityError) as exc:
            _view(world, _sel(world), bundle_dir=str(tmp_path / "nothing_here"))
        assert vst.GATE_NO_STORE_ON_DISK in str(exc.value)

    def test_a_MANIFEST_that_binds_another_document_is_REFUSED(self, world, tmp_path):
        bundle = self._copy(world, tmp_path)
        path = os.path.join(bundle, "manifest.json")
        with open(path, encoding="utf-8") as fh:
            manifest = json.load(fh)
        manifest["document_sha256"] = "0" * 64
        manifest["manifest_sha256"] = vst.content_hash(
            vst.without(manifest, ("manifest_sha256", "created_at")))   # a CONSISTENT forgery
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(manifest, fh)

        with pytest.raises(vst.StoreIdentityError) as exc:
            _view(world, _sel(world), bundle_dir=bundle)
        assert vst.GATE_MANIFEST_BINDS_OTHER_BYTES in str(exc.value)

    def test_a_DOCUMENT_edited_after_it_was_addressed_is_REFUSED(self, world):
        document = json.loads(json.dumps(world["document"]))
        document["table_hashes"]["candidates"] = "0" * 64     # bytes nobody holds
        with pytest.raises(vst.StoreIdentityError) as exc:
            _view(world, _sel(world), document=document)
        assert vst.GATE_DOCUMENT_IDENTITY in str(exc.value)


class TestASelectionsIdentityMayNotLeakIntoTheGlobalStore:
    """A leak is SILENT: everything still verifies, reproduces and looks right — while the store
    has quietly become the answer to ONE question, and every other question is wrong or a re-run.
    """

    def test_a_selection_id_at_the_TOP_LEVEL_of_the_document_is_REFUSED(self, world):
        document = json.loads(json.dumps(world["document"]))
        document["selection_id"] = "7a77f6b314b9c0f3"
        with pytest.raises(vst.StoreIdentityError) as exc:
            _view(world, _sel(world), document=document)
        assert vst.GATE_SELECTION_IN_THE_STORE in str(exc.value)

    def test_a_question_id_NESTED_several_levels_deep_is_REFUSED(self, world):
        document = json.loads(json.dumps(world["document"]))
        document["method"]["stage2_topology"]["provenance"] = {
            "upstream": [{"context": {"question_id": "3203d63970720d4f"}}]}
        with pytest.raises(vst.StoreIdentityError) as exc:
            _view(world, _sel(world), document=document)
        assert vst.GATE_SELECTION_IN_THE_STORE in str(exc.value)
        assert "question_id" in str(exc.value)

    def test_an_A_B_ROLE_leaked_as_a_KEY_and_not_a_value_is_REFUSED(self, world):
        document = json.loads(json.dumps(world["document"]))
        document["universe_store"]["away_from_A_arm_keys"] = []      # empty! the KEY is the leak
        with pytest.raises(vst.StoreIdentityError) as exc:
            _view(world, _sel(world), document=document)
        assert vst.GATE_ROLE_IN_THE_STORE in str(exc.value)

    def test_a_ROLE_leaked_into_a_TABLE_ROWS_VALUE_is_REFUSED(self, world):
        tables = _tables(world)
        tables["target_drug_edges"][0]["directional_evidence_status"] = "toward_B"
        with pytest.raises(vst.StoreIdentityError) as exc:
            _view(world, _sel(world), tables=tables)
        assert vst.GATE_ROLE_IN_THE_STORE in str(exc.value)

    def test_a_ROLE_leaked_into_a_TABLE_ROWS_COLUMN_is_REFUSED(self, world):
        tables = _tables(world)
        tables["arm_slots"][0]["selection_roles"] = ["away_from_A"]
        with pytest.raises(vst.StoreIdentityError) as exc:
            _view(world, _sel(world), tables=tables)
        assert vst.GATE_ROLE_IN_THE_STORE in str(exc.value)

    def test_a_selection_id_in_a_TABLE_ROWS_VALUE_is_REFUSED(self, world):
        tables = _tables(world)
        tables["dispositions"][0]["reason"] = "kept for selection_id=7a77f6b314b9c0f3"
        with pytest.raises(vst.StoreIdentityError) as exc:
            _view(world, _sel(world), tables=tables)
        assert vst.GATE_SELECTION_IN_THE_STORE in str(exc.value)

    def test_an_A_B_ASSIGNMENT_that_never_says_ROLE_is_still_a_ROLE_and_is_REFUSED(self, world):
        """`a_arm_key` names ONE question's pole as surely as `away_from_A` does. A scan that only
        knew the word "role" would wave it through — and the store would hold an answer."""
        document = json.loads(json.dumps(world["document"]))
        document["stage2_aggregate"]["a_arm_key"] = "direct|FIXTURE_PROG_00|decrease|Rest"
        with pytest.raises(vst.StoreIdentityError) as exc:
            _view(world, _sel(world), document=document)
        assert vst.GATE_ROLE_IN_THE_STORE in str(exc.value)

    def test_a_NEGATIVE_DECLARATION_that_FLIPPED_is_REFUSED(self, world):
        """`selection_roles_assigned: false` is a promise. Flipped, it is the leak announcing
        itself — and an allow-list that only matched the KEY would wave it through."""
        document = json.loads(json.dumps(world["document"]))
        document["selection_roles_assigned"] = True
        with pytest.raises(vst.StoreIdentityError) as exc:
            _view(world, _sel(world), document=document)
        assert vst.GATE_ROLE_IN_THE_STORE in str(exc.value)


class TestTheViewNamesTheBytesItIsAProjectionOf:

    def test_the_view_binds_the_store_the_document_and_the_manifest_by_identity(self, world):
        view = _view(world, _sel(world))
        store, document = view["store"], world["document"]

        assert store["bundle_id"] == document["bundle_id"]
        assert store["canonical_content_sha256"] == document["canonical_content_sha256"]
        assert store["document_sha256"] == document["document_sha256"]
        with open(os.path.join(world["bundle_dir"], "manifest.json"), encoding="utf-8") as fh:
            assert store["store_manifest_sha256"] == json.load(fh)["manifest_sha256"]
        assert store["store_identity_verifier_id"] == vst.STORE_IDENTITY_VERIFIER_ID
        assert store["store_identity_checks"] == vst.checks()

    def test_the_views_eight_table_hashes_are_RE_DERIVED_from_the_rows_it_projected(self, world):
        view = _view(world, _sel(world))
        recomputed = av2.table_content_hashes(world["tables"])       # by OUR hands, not the doc's
        assert sorted(recomputed) == sorted(av2.SCIENTIFIC_TABLES)
        assert view["store"]["table_hashes"] == recomputed
        assert view["store"]["table_hashes"] == world["document"]["table_hashes"]
        assert view["store"]["n_tables_verified"] == 8
        assert view["store"]["table_hashes_are_re_derived_not_copied"] is True

    def test_the_view_still_names_the_tables_it_does_NOT_project(self, world):
        """`provenance` is not projected — and it IS hashed. A table the view does not show is
        still a table the store holds, and a store is verified whole or not at all."""
        view = _view(world, _sel(world))
        assert "provenance" not in view["tables"]
        assert "provenance" in view["store"]["table_hashes"]

    def test_the_view_carries_NO_path_to_the_store_it_verified(self, world):
        """The bytes are named by HASH. A path is a fact about the host, not about the science."""
        view = _view(world, _sel(world))
        assert world["bundle_dir"] not in json.dumps(view)
        vc.check_browser_safe(view)                  # and the local-path firewall agrees


class TestTheGuaranteesTheViewPublishes:

    def test_the_view_promises_it_re_derived_the_stores_hashes(self, world):
        programs, conditions = _programs(world), _conditions(world)
        view = _view(world, _verified(world, a=programs[2], b=programs[3], mode=TEMPORAL,
                                      conditions=[conditions[0], conditions[2]]))
        assert view["guarantees"][
            "the_stores_eight_table_hashes_are_re_derived_before_projection_never_copied"] is True
        assert view["guarantees"][
            "the_global_store_carries_no_selection_identity_at_any_depth"] is True
