"""THE PROJECTED ROWS ARE WHAT STAGE 4 READS — and until this suite, NOTHING BOUND THEM.

The defect (reproduced by an independent reviewer, and real):

    view["tables"]["arm_slots"][0]["arm_context_sha256"] = "MUTATED"   # AFTER the view was sealed
    view_contract.validate(view)                                       # ...ADMITTED.

Every hash in the document stayed mutually consistent, because the view's ``store.table_hashes``
describe the GLOBAL STORE — all eight tables, every row in the release — and the store had not
been touched. The rows a consumer READS had been. The schema typed the tables as
``{"items": {"type": "object"}}``: it never looked at a single cell.

This is the mirror of the defect closed one level up in ``view_store`` (a hash you COPY is not a
hash you CHECKED). There, the view republished the STORE's claims about itself. Here, the view
republished NOTHING AT ALL about the rows it actually shipped.

EVERY TEST HERE IS NON-VACUOUS BY CONSTRUCTION. An empty projection mutates to nothing, so
:class:`TestTheProjectionIsRealBeforeAnyAttack` asserts the rows EXIST first — otherwise every
attack below would "pass" against a view with nothing in it to attack.

This suite is what the CONTRACT refuses, with the bytes alone, anywhere they travel. What only a
verifier HOLDING THE STORE can refuse — a re-sealed forgery, swapped table bytes — is in
``test_selection_view_projection_store.py``, and the boundary between them is stated there rather
than implied.
"""
from __future__ import annotations

import json

import pytest

from druglink import artifacts_v2 as av2
from druglink import pathway_context_v2 as pc2
from druglink import view_contract as vc
from druglink import view_projection as vp
from druglink import view_store as vst
from druglink.hashing import file_sha256
from verifier import view_projection as vpv

import os

from projection_attacks import (
    EMPTY_BY_POLICY,
    MUTATED_COLUMN,
    honest,
    mutate,
    other_sel,
    reseal,
)
from selection_world import _view


class TestTheProjectionIsRealBeforeAnyAttack:
    """Assert the view HAS rows. Otherwise every attack below is vacuous."""

    def test_the_view_projects_SEVEN_tables_and_SIX_of_them_are_NON_EMPTY(self, world):
        view = honest(world)
        assert sorted(view["tables"]) == sorted(vp.SEALED_TABLES)
        assert len(vp.SEALED_TABLES) == 7
        empty = sorted(n for n in vp.SEALED_TABLES if not view["tables"][n])
        assert empty == [EMPTY_BY_POLICY], (
            "the projection changed shape; the mutation attacks below are only non-vacuous "
            "against tables that HAVE rows")
        assert pc2.PATHWAY_LANE_ADMITTED is False           # WHY pathway_context is empty
        for name in sorted(set(vp.SEALED_TABLES) - {EMPTY_BY_POLICY}):
            assert view["tables"][name], f"{name} is empty; its attack would prove nothing"

    def test_the_HONEST_view_is_ADMITTED_by_the_contract_and_by_the_store(self, world):
        view = honest(world)
        vc.validate(view)
        report = vpv.verify(view, bundle_dir=world["bundle_dir"])
        assert report["verdict"] == "ADMIT"
        assert report["every_projected_row_was_proven_to_be_a_row_the_store_holds"] is True
        assert report["n_tables_verified"] == 7

    def test_the_reviewers_target_row_and_column_ACTUALLY_EXIST(self, world):
        """The attack below edits a REAL cell of a REAL projected row."""
        view = honest(world)
        assert view["tables"]["arm_slots"], "the table is empty; the attack would prove nothing"
        assert "arm_context_sha256" in view["tables"]["arm_slots"][0]
        assert view["tables"]["arm_slots"][0]["arm_context_sha256"] != "MUTATED"


class TestTheReviewersExactAttack:
    """`view["tables"]["arm_slots"][0]["arm_context_sha256"] = "MUTATED"`, after sealing."""

    def test_the_EXACT_reported_mutation_is_now_REFUSED_BY_NAME(self, world):
        view = mutate(honest(world))
        view["tables"]["arm_slots"][0]["arm_context_sha256"] = "MUTATED"

        with pytest.raises(vp.ProjectionSealError) as exc:
            vc.validate(view)
        assert vp.GATE_ROWS_ARE_NOT_THE_SEALED_ROWS in str(exc.value)
        assert "arm_slots" in str(exc.value)

    def test_the_STORES_OWN_DIGEST_IS_STILL_HONEST_which_is_why_nothing_else_noticed(self, world):
        """The heart of the defect: the store was never touched, so every OTHER hash still agrees.

        Documents exactly how much of the document stays mutually consistent while the rows a
        consumer reads are wrong — which is why no other check in the stack could see it.
        """
        view = mutate(honest(world))
        view["tables"]["arm_slots"][0]["arm_context_sha256"] = "MUTATED"

        # The GLOBAL store's eight hashes still re-derive, still match the document, still match
        # the bytes on disk. Nothing about the store is a lie. Nothing about the store is the row.
        assert view["store"]["table_hashes"] == av2.table_content_hashes(world["tables"])
        vst.check_store_is_selection_independent(world["document"], world["tables"])

        # And the ROWS the consumer reads are not the rows anybody admitted.
        assert vp.projected_content_hash("arm_slots", view["tables"]["arm_slots"]) \
            != view["projection"]["tables"]["arm_slots"]["content_sha256"]


class TestASingleCellInEveryTable:
    """One cell, one row, in each of the SIX non-empty projected tables."""

    @pytest.mark.parametrize("name", sorted(MUTATED_COLUMN))
    def test_a_single_cell_edited_after_sealing_is_REFUSED_BY_NAME(self, world, name):
        view = mutate(honest(world))
        rows = view["tables"][name]
        assert rows, f"{name} is empty; this attack would prove nothing"

        column = MUTATED_COLUMN[name]
        assert column in rows[0], f"{column!r} is not a projected {name} column"
        before = rows[0][column]
        rows[0][column] = 999 if isinstance(before, int) and not isinstance(before, bool) \
            else "MUTATED_AFTER_THE_VIEW_WAS_SEALED"
        assert rows[0][column] != before, "the attack did not change anything"

        with pytest.raises(vp.ProjectionSealError) as exc:
            vc.validate(view)
        assert vp.GATE_ROWS_ARE_NOT_THE_SEALED_ROWS in str(exc.value)
        assert name in str(exc.value)

    @pytest.mark.parametrize("name", sorted(MUTATED_COLUMN))
    def test_a_row_DELETED_after_sealing_is_REFUSED_BY_NAME(self, world, name):
        view = mutate(honest(world))
        view["tables"][name].pop(0)
        with pytest.raises(vp.ProjectionSealError) as exc:
            vc.validate(view)
        assert vp.GATE_ROW_COUNT_MOVED in str(exc.value)
        assert name in str(exc.value)

    @pytest.mark.parametrize("name", sorted(vp.SEALED_TABLES))
    def test_a_row_ADDED_after_sealing_is_REFUSED_BY_NAME(self, world, name):
        """Including the EMPTY-by-policy table: an inserted `pathway_context` row is bytes nobody
        sealed — and a pathway record may never source a drug edge."""
        view = mutate(honest(world))
        columns, _ = av2.TABLES[name]
        view["tables"][name].append({c: "INSERTED_BY_AN_ATTACK" for c in columns})

        with pytest.raises(vp.ProjectionSealError) as exc:
            vc.validate(view)
        assert vp.GATE_ROW_COUNT_MOVED in str(exc.value)
        assert name in str(exc.value)


class TestAMissingTableAndAnUnsealedTable:

    def test_a_table_DROPPED_from_the_view_is_REFUSED_BY_NAME(self, world):
        view = mutate(honest(world))
        del view["tables"]["candidates"]
        with pytest.raises(vp.ProjectionSealError) as exc:
            vp.check(view)                       # the schema ALSO refuses it; the seal NAMES it
        assert vp.GATE_SEALED_TABLE_NOT_PROJECTED in str(exc.value)
        assert "candidates" in str(exc.value)

    def test_a_view_with_NO_SEAL_AT_ALL_is_REFUSED_BY_NAME(self, world):
        """A bare row list is exactly what the defect shipped."""
        view = mutate(honest(world))
        del view["projection"]
        with pytest.raises(vp.ProjectionSealError) as exc:
            vp.check(view)
        assert vp.GATE_TABLE_NOT_SEALED in str(exc.value)


class TestReorderAndDuplicate:
    """A ROW SET IS A SET; THE ARM PAIR IS NOT. Refuse a reorder only where order is meaning."""

    @pytest.mark.parametrize("name", sorted(MUTATED_COLUMN))
    def test_REORDERING_a_row_set_is_ADMITTED_and_that_is_CORRECT(self, world, name):
        """The view guarantees row order is by CONTENT ID and is not a ranking. Permuting rows
        changes no science, and a refusal that fired on it would be teaching the next reader to
        weaken the check. The content hash is row-order-invariant, on purpose."""
        view = mutate(honest(world))
        rows = view["tables"][name]
        if len(rows) < 2:
            pytest.skip(f"{name} has one row; a reorder is not expressible")
        rows.reverse()
        assert rows != honest(world)["tables"][name], "the reorder did not reorder anything"

        vc.validate(view)                                  # ADMITTED — a set is a set
        assert view["guarantees"]["row_order_is_by_content_id_and_is_not_a_ranking"] is True

    @pytest.mark.parametrize("name", sorted(MUTATED_COLUMN))
    def test_DUPLICATING_a_row_is_REFUSED_BY_NAME(self, world, name):
        """A set cannot hold the same row twice, and a duplicate double-counts the evidence it
        carries — a consumer counting rows would read one measurement as two."""
        view = mutate(honest(world))
        view["tables"][name].append(dict(view["tables"][name][0]))
        with pytest.raises(vp.ProjectionSealError) as exc:
            vc.validate(view)
        assert vp.GATE_DUPLICATE_ROW in str(exc.value)
        assert name in str(exc.value)

    def test_a_duplicate_is_refused_EVEN_IF_THE_ATTACKER_RE_SEALS(self, world):
        """The duplicate gate is STRUCTURAL, not a hash comparison: a re-seal does not buy it.
        The SEAL ITSELF refuses to be built over a doubled row."""
        view = mutate(honest(world))
        view["tables"]["target_drug_edges"].append(dict(view["tables"]["target_drug_edges"][0]))
        with pytest.raises(vp.ProjectionSealError) as exc:
            reseal(view, world["bundle_dir"])
        assert vp.GATE_DUPLICATE_ROW in str(exc.value)

    def test_SWAPPING_THE_ARM_POLES_is_REFUSED_because_THIS_order_IS_meaning(self, world):
        """Index 0 is the arm the question moves AWAY FROM; index 1 the arm it moves TOWARD.
        Swap them and the view answers a question nobody asked — with the poles of the one they
        did."""
        view = mutate(honest(world))
        assert len(view["arm_evidence"]) == 2
        assert [a["role"] for a in view["arm_evidence"]] == ["away_from_A", "toward_B"]
        view["arm_evidence"].reverse()

        with pytest.raises(vp.ProjectionSealError) as exc:
            vc.validate(view)
        assert vp.GATE_ORDERED_BLOCK_REORDERED in str(exc.value)

    def test_the_view_SAYS_WHICH_of_its_lists_may_be_re_sorted(self, world):
        meaning = honest(world)["projection"]["row_order_carries_meaning"]
        assert meaning["tables"] is False and meaning["arm_evidence"] is True
        assert meaning["tables_reason"] and meaning["arm_evidence_reason"]


class TestAStaleReceipt:
    """A receipt is a statement about SPECIFIC BYTES. Lifted from another view it admits rows it
    never saw — and the rows it travels with were admitted by nobody."""

    def test_a_STORE_RECEIPT_from_another_view_is_REFUSED_BY_NAME(self, world):
        mine, theirs = honest(world), _view(world, other_sel(world))
        assert mine["projection"]["projection_sha256"] \
            != theirs["projection"]["projection_sha256"], "the two questions must differ"

        view = mutate(mine)
        view["store"] = mutate(theirs)["store"]
        with pytest.raises(vp.ProjectionSealError) as exc:
            vp.check(view)
        assert vp.GATE_STALE_RECEIPT in str(exc.value)
        assert "store" in str(exc.value)

    def test_an_AGGREGATE_RECEIPT_from_another_view_is_REFUSED_BY_NAME(self, world):
        view = mutate(honest(world))
        view["admission"] = mutate(_view(world, other_sel(world)))["admission"]
        with pytest.raises(vp.ProjectionSealError) as exc:
            vp.check(view)
        assert vp.GATE_STALE_RECEIPT in str(exc.value)
        assert "admission" in str(exc.value)

    def test_BOTH_receipts_bind_the_projection_they_admit(self, world):
        view = honest(world)
        seal = view["projection"]["projection_sha256"]
        assert view["store"]["projection_sha256"] == seal
        assert view["admission"]["projection_sha256"] == seal

    def test_a_FORGED_SEAL_IDENTITY_is_REFUSED_BY_NAME(self, world):
        """The first thing an attacker who understood the check would rewrite."""
        view = mutate(honest(world))
        view["projection"]["projection_sha256"] = "0" * 64
        with pytest.raises(vp.ProjectionSealError) as exc:
            vp.check(view)
        assert vp.GATE_SEAL_IDENTITY in str(exc.value)

    def test_a_VIEW_edited_after_it_was_addressed_is_REFUSED_BY_NAME(self, world):
        view = mutate(honest(world))
        view["origin_types_present"] = []
        with pytest.raises(vp.ProjectionSealError) as exc:
            vp.check(view)
        assert vp.GATE_VIEW_IDENTITY in str(exc.value)


class TestSchemaSetDrift:
    """`schemas_sha256` is bound EXACTLY. No substring rule, no 'hopeful' pattern."""

    def test_the_seal_binds_the_PINNED_schema_set_and_it_is_the_one_ON_DISK(self, world):
        view = honest(world)
        assert view["projection"]["schemas_sha256"] == vp.PINNED_SCHEMAS_SHA256
        assert view["projection"]["schemas_sha256"] == vp.bound_schemas_sha256()
        assert view["store"]["schemas_sha256"] == vp.PINNED_SCHEMAS_SHA256

    @pytest.mark.parametrize("field", ["schemas_sha256", "projection_schema_set_sha256"])
    def test_a_seal_naming_ANOTHER_schema_set_is_REFUSED_BY_NAME(self, world, field):
        view = mutate(honest(world))
        view["projection"][field] = "0" * 64
        with pytest.raises(vp.ProjectionSealError) as exc:
            vp.check(view)
        assert vp.GATE_SCHEMA_SET_DRIFT in str(exc.value)

    def test_a_TABLE_sealed_under_a_FOREIGN_schema_id_is_REFUSED_BY_NAME(self, world):
        view = mutate(honest(world))
        view["projection"]["tables"]["candidates"]["schema_id"] = "spot.something_else.v1"
        with pytest.raises(vp.ProjectionSealError) as exc:
            vp.check(view)
        assert vp.GATE_SCHEMA_SET_DRIFT in str(exc.value)

    def test_the_verifier_id_is_an_EXACT_CONST_and_never_a_SUBSTRING_RULE(self, world):
        """The retired rule refused every honest report and admitted any forgery that renamed
        itself '…independent…'. A name is not a binding. Its SHAPE may not come back."""
        view = mutate(honest(world))
        view["projection"]["projection_verifier_id"] = \
            "spot.some.independent.forgery.that.renamed.itself.v1"
        with pytest.raises(vp.ProjectionSealError) as exc:
            vp.check(view)
        assert vp.GATE_SCHEMA_SET_DRIFT in str(exc.value)


class TestWhatTheSealBindsAndPublishes:

    def test_every_projected_table_carries_RAW_and_CANONICAL_and_COUNT_and_SCHEMA(self, world):
        view = honest(world)
        for name in vp.SEALED_TABLES:
            sealed = view["projection"]["tables"][name]
            assert sorted(sealed) == ["content_sha256", "raw_sha256", "row_count", "schema_id"]
            # RAW: the STORE table's file bytes — the subset has no file of its own.
            assert sealed["raw_sha256"] == file_sha256(
                os.path.join(world["bundle_dir"], f"{name}.parquet"))
            # CANONICAL: the ROWS THIS VIEW SHIPS.
            assert sealed["content_sha256"] == vp.projected_content_hash(
                name, view["tables"][name])
            assert sealed["row_count"] == len(view["tables"][name])
            assert sealed["schema_id"] == vp.table_schema_id(name)

    def test_the_seal_names_the_gates_a_BARE_CONTRACT_CHECK_could_not_run(self, world):
        """A consumer must be able to tell a contract check from a full verification."""
        view = honest(world)
        assert view["projection"]["projection_checks"] == vp.checks()
        assert view["projection"]["projection_disk_checks"] == vp.disk_checks()
        assert vp.GATE_ROW_IS_NOT_A_STORE_ROW in view["projection"]["projection_disk_checks"]
        assert vp.GATE_ROW_IS_NOT_A_STORE_ROW not in view["projection"]["projection_checks"]

    def test_the_PUBLISHED_FIXTURE_carries_a_seal_and_is_a_LEGAL_view(self, world):
        from selection_world import FIXTURE_PATH
        with open(FIXTURE_PATH, encoding="utf-8") as fh:
            published = json.load(fh)
        vc.validate(published)
        assert published["projection"]["n_tables_sealed"] == 7
        assert published["projection"]["tables"]["arm_slots"]["row_count"] == 6
