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

AND ONE TEST HERE IS AN HONEST ADMISSION: :class:`TestWhatTheContractCheckCannotDo` shows an
attacker who RE-SEALS after mutating is admitted by the contract check, and refused only by the
verifier that holds the store. A document can always be made to agree with itself.
"""
from __future__ import annotations

import copy
import json
import os
import shutil

import pytest

from druglink import artifacts_v2 as av2
from druglink import pathway_context_v2 as pc2
from druglink import view_contract as vc
from druglink import view_projection as vp
from druglink import view_store as vst
from druglink.hashing import content_hash, file_sha256
from verifier import view_projection as vpv

from selection_world import TEMPORAL, WITHIN, _conditions, _programs, _verified, _view

# `pathway_context` is EMPTY BY POLICY — the pathway lane is not admitted, because a gene-set
# enrichment record never sources a drug edge. Its attack is therefore an INSERTED row: bytes
# nobody sealed, which is the same refusal from the other side.
EMPTY_BY_POLICY = "pathway_context"

# A benign, NON-KEY column per projected table: enough to move the table's content hash, never
# the row's own identity. A mutation that changed an id would be caught by something else and
# would prove nothing about the seal.
MUTATED_COLUMN = {
    "arm_slots": "arm_context_sha256",          # the audit's own column
    "target_drug_edges": "arm_rank",
    "arm_summaries": "n_edges",
    "candidates": "identity_status",
    "source_records": "identity_status",
    "dispositions": "reason",
}


def _sel(world):
    programs, conditions = _programs(world), _conditions(world)
    return _verified(world, a=programs[0], b=programs[1], mode=WITHIN,
                     conditions=[conditions[0]])


def _other_sel(world):
    """A DIFFERENT question over the SAME store — the store is reusable, which is the point."""
    programs, conditions = _programs(world), _conditions(world)
    return _verified(world, a=programs[2], b=programs[3], mode=TEMPORAL,
                     conditions=[conditions[0], conditions[2]])


def _honest(world) -> dict:
    return _view(world, _sel(world))


def _mutate(view: dict) -> dict:
    """A deep, independent copy. The attacker edits THIS, after the view was sealed."""
    return copy.deepcopy(view)


def _nonempty(view) -> list[str]:
    return sorted(n for n in vp.SEALED_TABLES if view["tables"][n])


# --------------------------------------------------------------------------- #
class TestTheProjectionIsRealBeforeAnyAttack:
    """Assert the view HAS rows. Otherwise every attack below is vacuous."""

    def test_the_view_projects_SEVEN_tables_and_SIX_of_them_are_NON_EMPTY(self, world):
        view = _honest(world)
        assert sorted(view["tables"]) == sorted(vp.SEALED_TABLES)
        assert len(vp.SEALED_TABLES) == 7
        empty = sorted(n for n in vp.SEALED_TABLES if not view["tables"][n])
        assert empty == [EMPTY_BY_POLICY], (
            "the projection changed shape; the mutation attacks below are only non-vacuous "
            "against tables that HAVE rows")
        assert pc2.PATHWAY_LANE_ADMITTED is False           # WHY pathway_context is empty
        assert _nonempty(view) == sorted(set(vp.SEALED_TABLES) - {EMPTY_BY_POLICY})
        for name in _nonempty(view):
            assert view["tables"][name], f"{name} is empty; its attack would prove nothing"

    def test_the_HONEST_view_is_ADMITTED_by_the_contract_and_by_the_store(self, world):
        view = _honest(world)
        vc.validate(view)
        report = vpv.verify(view, bundle_dir=world["bundle_dir"])
        assert report["verdict"] == "ADMIT"
        assert report["every_projected_row_was_proven_to_be_a_row_the_store_holds"] is True
        assert report["n_tables_verified"] == 7

    def test_the_audits_target_row_and_column_ACTUALLY_EXIST(self, world):
        """The attack below edits a REAL cell of a REAL projected row."""
        view = _honest(world)
        assert view["tables"]["arm_slots"], "the audit's table is empty; its attack proves nothing"
        assert "arm_context_sha256" in view["tables"]["arm_slots"][0]
        assert view["tables"]["arm_slots"][0]["arm_context_sha256"] != "MUTATED"


# --------------------------------------------------------------------------- #
class TestTheReviewersExactAttack:
    """`view["tables"]["arm_slots"][0]["arm_context_sha256"] = "MUTATED"`, after sealing."""

    def test_the_EXACT_reported_mutation_is_now_REFUSED_BY_NAME(self, world):
        view = _mutate(_honest(world))
        view["tables"]["arm_slots"][0]["arm_context_sha256"] = "MUTATED"

        with pytest.raises(vp.ProjectionSealError) as exc:
            vc.validate(view)
        assert vp.GATE_ROWS_ARE_NOT_THE_SEALED_ROWS in str(exc.value)
        assert "arm_slots" in str(exc.value)

    def test_the_STORES_OWN_DIGEST_IS_STILL_HONEST_which_is_why_nothing_else_noticed(self, world):
        """The heart of the defect: the store was never touched, so every OTHER hash still agrees.

        This test would have PASSED before the fix, and that is the point — it documents exactly
        how much of the document remains mutually consistent while the rows are wrong.
        """
        view = _mutate(_honest(world))
        view["tables"]["arm_slots"][0]["arm_context_sha256"] = "MUTATED"

        # The GLOBAL store's eight hashes still re-derive, still match the document, still match
        # the bytes on disk. Nothing about the store is a lie. Nothing about the store is the row.
        recomputed = av2.table_content_hashes(world["tables"])
        assert view["store"]["table_hashes"] == recomputed
        vst.check_store_is_selection_independent(world["document"], world["tables"])

        # And the ROWS the consumer reads are not the rows anybody admitted.
        assert vp.projected_content_hash("arm_slots", view["tables"]["arm_slots"]) \
            != view["projection"]["tables"]["arm_slots"]["content_sha256"]

    def test_the_store_verifier_ALSO_refuses_it_naming_the_CELL(self, world):
        view = _mutate(_honest(world))
        view["tables"]["arm_slots"][0]["arm_context_sha256"] = "MUTATED"
        with pytest.raises((vp.ProjectionSealError, vpv.ProjectionRefusal)) as exc:
            vpv.verify(view, bundle_dir=world["bundle_dir"])
        assert vp.GATE_ROWS_ARE_NOT_THE_SEALED_ROWS in str(exc.value)


# --------------------------------------------------------------------------- #
class TestASingleCellInEveryTable:
    """One cell, one row, each of the SIX non-empty projected tables."""

    @pytest.mark.parametrize("name", sorted(MUTATED_COLUMN))
    def test_a_single_cell_edited_after_sealing_is_REFUSED_BY_NAME(self, world, name):
        view = _mutate(_honest(world))
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
        view = _mutate(_honest(world))
        view["tables"][name].pop(0)
        with pytest.raises(vp.ProjectionSealError) as exc:
            vc.validate(view)
        assert vp.GATE_ROW_COUNT_MOVED in str(exc.value)
        assert name in str(exc.value)

    @pytest.mark.parametrize("name", sorted(vp.SEALED_TABLES))
    def test_a_row_ADDED_after_sealing_is_REFUSED_BY_NAME(self, world, name):
        """Including the EMPTY-by-policy table: an inserted pathway_context row is bytes nobody
        sealed, and a pathway record may never source a drug edge."""
        view = _mutate(_honest(world))
        columns, _ = av2.TABLES[name]
        view["tables"][name].append({c: "INSERTED_BY_AN_ATTACK" for c in columns})

        with pytest.raises(vp.ProjectionSealError) as exc:
            vc.validate(view)
        assert vp.GATE_ROW_COUNT_MOVED in str(exc.value)
        assert name in str(exc.value)

    @pytest.mark.parametrize("name", sorted(MUTATED_COLUMN))
    def test_a_row_the_STORE_DOES_NOT_HOLD_is_REFUSED_even_if_the_seal_agrees(self, world, name):
        """The attacker adds a row AND re-seals. The count agrees, the hash agrees — and the
        store has never heard of the row."""
        view = _mutate(_honest(world))
        columns, keys = av2.TABLES[name]
        forged = dict(view["tables"][name][0])
        for k in keys:
            forged[k] = "FORGED_" + str(forged[k])[:24]
        view["tables"][name].append(forged)
        _reseal(view, world["bundle_dir"])

        vc.validate(view)                        # the DOCUMENT agrees with itself. It always can.
        with pytest.raises(vpv.ProjectionRefusal) as exc:
            vpv.verify(view, bundle_dir=world["bundle_dir"])
        assert vpv.GATE_ROW_IS_NOT_A_STORE_ROW in str(exc.value)


# --------------------------------------------------------------------------- #
def _reseal(view: dict, bundle_dir: str) -> dict:
    """What a forger who UNDERSTOOD the contract check would do: re-seal over the mutated rows,
    re-stamp both receipts, and re-address the document. Every hash agrees again."""
    seal = vp.seal(view_rows={n: view["tables"][n] for n in vp.SEALED_TABLES},
                   arm_evidence=view["arm_evidence"], bundle_dir=bundle_dir)
    view["projection"] = seal
    view["store"]["projection_sha256"] = seal["projection_sha256"]
    view["admission"]["projection_sha256"] = seal["projection_sha256"]
    view.pop("view_id", None)
    view.pop("view_content_sha256", None)
    content = content_hash(view)
    view["view_id"] = content[:16]
    view["view_content_sha256"] = content
    return view


class TestWhatTheContractCheckCannotDo:
    """AN HONEST BOUNDARY. The contract check re-hashes the rows against the seal — so it catches
    an edit. It cannot catch an edit followed by a RE-SEAL: a document can always be made to agree
    with itself. Only a verifier holding the bytes it does not control can refuse that.
    """

    def test_a_RE_SEALED_mutation_is_ADMITTED_by_the_contract_check(self, world):
        view = _mutate(_honest(world))
        view["tables"]["arm_slots"][0]["arm_context_sha256"] = "MUTATED"
        _reseal(view, world["bundle_dir"])
        vc.validate(view)          # ...and this is why the contract check is not the whole gate

    def test_and_the_STORE_HOLDING_verifier_REFUSES_it_naming_the_COLUMN(self, world):
        view = _mutate(_honest(world))
        view["tables"]["arm_slots"][0]["arm_context_sha256"] = "MUTATED"
        _reseal(view, world["bundle_dir"])

        with pytest.raises(vpv.ProjectionRefusal) as exc:
            vpv.verify(view, bundle_dir=world["bundle_dir"])
        assert vpv.GATE_ROW_IS_NOT_A_STORE_ROW in str(exc.value)
        assert "arm_context_sha256" in str(exc.value)

    def test_the_verifier_NEVER_ADOPTS_the_recomputed_value(self, world):
        """A verifier that repairs what it was asked to judge has stopped being a verifier."""
        view = _mutate(_honest(world))
        view["tables"]["arm_slots"][0]["arm_context_sha256"] = "MUTATED"
        with pytest.raises(vp.ProjectionSealError):
            vpv.verify(view, bundle_dir=world["bundle_dir"])
        assert view["tables"]["arm_slots"][0]["arm_context_sha256"] == "MUTATED"   # untouched


# --------------------------------------------------------------------------- #
class TestTheStoreBytesUnderTheProjection:
    """The seal names the RAW BYTES of the store table each subset was drawn from."""

    def _copy(self, world, tmp_path) -> str:
        target = str(tmp_path / "store")
        shutil.copytree(world["bundle_dir"], target)
        return target

    def test_TWO_TABLES_BYTES_SWAPPED_on_disk_is_REFUSED_BY_NAME(self, world, tmp_path):
        """Table A's bytes served as table B. The rows may still parse and the count may still
        fit — and the science would be a different table's."""
        view = _honest(world)
        bundle = self._copy(world, tmp_path)
        a = os.path.join(bundle, "arm_slots.parquet")
        b = os.path.join(bundle, "arm_summaries.parquet")
        a_bytes, b_bytes = open(a, "rb").read(), open(b, "rb").read()
        assert a_bytes != b_bytes, "the swap must actually change the bytes"
        open(a, "wb").write(b_bytes)
        open(b, "wb").write(a_bytes)

        with pytest.raises(vpv.ProjectionRefusal) as exc:
            vpv.verify(view, bundle_dir=bundle)
        assert vpv.GATE_RAW_BYTES_ARE_NOT_THE_STORES in str(exc.value)

    def test_a_MISSING_store_table_is_REFUSED_BY_NAME(self, world, tmp_path):
        view = _honest(world)
        bundle = self._copy(world, tmp_path)
        os.remove(os.path.join(bundle, "candidates.parquet"))

        with pytest.raises(vpv.ProjectionRefusal) as exc:
            vpv.verify(view, bundle_dir=bundle)
        assert vpv.GATE_STORE_TABLE_NOT_ON_DISK in str(exc.value)
        assert "candidates" in str(exc.value)

    def test_NO_STORE_AT_ALL_is_REFUSED_BY_NAME(self, world, tmp_path):
        with pytest.raises(vpv.ProjectionRefusal) as exc:
            vpv.verify(_honest(world), bundle_dir=str(tmp_path / "nothing_here"))
        assert vpv.GATE_NO_STORE in str(exc.value)

    def test_the_raw_bytes_the_seal_names_are_the_STORES_OWN_FILE_BYTES(self, world):
        """The subset has no file of its own; `raw_sha256` is the parquet it was drawn FROM."""
        view = _honest(world)
        for name in vp.SEALED_TABLES:
            path = os.path.join(world["bundle_dir"], f"{name}.parquet")
            assert view["projection"]["tables"][name]["raw_sha256"] == file_sha256(path)


# --------------------------------------------------------------------------- #
class TestAMissingTableAndAnUnsealedTable:

    def test_a_table_DROPPED_from_the_view_is_REFUSED_BY_NAME(self, world):
        view = _mutate(_honest(world))
        del view["tables"]["candidates"]
        with pytest.raises(vp.ProjectionSealError) as exc:
            vp.check(view)                       # the schema ALSO refuses it; the seal names it
        assert vp.GATE_SEALED_TABLE_NOT_PROJECTED in str(exc.value)
        assert "candidates" in str(exc.value)

    def test_a_view_with_NO_SEAL_AT_ALL_is_REFUSED_BY_NAME(self, world):
        """A bare row list is exactly what the defect shipped."""
        view = _mutate(_honest(world))
        del view["projection"]
        with pytest.raises(vp.ProjectionSealError) as exc:
            vp.check(view)
        assert vp.GATE_TABLE_NOT_SEALED in str(exc.value)


# --------------------------------------------------------------------------- #
class TestReorderAndDuplicate:
    """A ROW SET IS A SET; A RANKED PAIR IS NOT. Refuse a reorder only where order is meaning."""

    @pytest.mark.parametrize("name", sorted(MUTATED_COLUMN))
    def test_REORDERING_a_row_set_is_ADMITTED_and_that_is_correct(self, world, name):
        """The view guarantees row order is by CONTENT ID and is not a ranking. Permuting rows
        changes no science, and a refusal that fired on it would teach the next reader to weaken
        the check. The content hash is row-order-invariant, on purpose."""
        view = _mutate(_honest(world))
        rows = view["tables"][name]
        if len(rows) < 2:
            pytest.skip(f"{name} has one row; a reorder is not expressible")
        rows.reverse()
        assert rows != _honest(world)["tables"][name], "the reorder did not reorder anything"

        vc.validate(view)                                  # ADMITTED — a set is a set
        assert view["guarantees"]["row_order_is_by_content_id_and_is_not_a_ranking"] is True

    @pytest.mark.parametrize("name", sorted(MUTATED_COLUMN))
    def test_DUPLICATING_a_row_is_REFUSED_BY_NAME(self, world, name):
        """A set cannot hold the same row twice, and a duplicate double-counts the evidence it
        carries — a consumer counting rows would read one measurement as two."""
        view = _mutate(_honest(world))
        view["tables"][name].append(dict(view["tables"][name][0]))
        with pytest.raises(vp.ProjectionSealError) as exc:
            vc.validate(view)
        assert vp.GATE_DUPLICATE_ROW in str(exc.value)
        assert name in str(exc.value)

    def test_a_duplicate_is_refused_EVEN_IF_THE_ATTACKER_RE_SEALS(self, world):
        """The duplicate gate is STRUCTURAL, not a hash comparison: re-sealing does not buy it."""
        view = _mutate(_honest(world))
        view["tables"]["target_drug_edges"].append(dict(view["tables"]["target_drug_edges"][0]))
        with pytest.raises(vp.ProjectionSealError) as exc:
            _reseal(view, world["bundle_dir"])             # the SEAL itself refuses to be built
        assert vp.GATE_DUPLICATE_ROW in str(exc.value)

    def test_SWAPPING_THE_ARM_POLES_is_REFUSED_because_THIS_order_IS_meaning(self, world):
        """Index 0 is the arm the question moves AWAY FROM; index 1 the arm it moves TOWARD.
        Swap them and the view answers a question nobody asked, with the poles of the one they
        did."""
        view = _mutate(_honest(world))
        assert len(view["arm_evidence"]) == 2
        assert [a["role"] for a in view["arm_evidence"]] == ["away_from_A", "toward_B"]
        view["arm_evidence"].reverse()

        with pytest.raises(vp.ProjectionSealError) as exc:
            vc.validate(view)
        assert vp.GATE_ORDERED_BLOCK_REORDERED in str(exc.value)

    def test_the_view_SAYS_WHICH_of_its_lists_may_be_re_sorted(self, world):
        view = _honest(world)
        meaning = view["projection"]["row_order_carries_meaning"]
        assert meaning["tables"] is False and meaning["arm_evidence"] is True
        assert meaning["tables_reason"] and meaning["arm_evidence_reason"]


# --------------------------------------------------------------------------- #
class TestAStaleReceipt:
    """A receipt is a statement about SPECIFIC BYTES. Lifted from another view, it admits rows it
    never saw — and the rows it travels with were admitted by nobody."""

    def test_a_STORE_RECEIPT_from_another_view_is_REFUSED_BY_NAME(self, world):
        mine, theirs = _honest(world), _view(world, _other_sel(world))
        assert mine["projection"]["projection_sha256"] \
            != theirs["projection"]["projection_sha256"], "the two questions must differ"

        view = _mutate(mine)
        view["store"] = copy.deepcopy(theirs["store"])
        with pytest.raises(vp.ProjectionSealError) as exc:
            vp.check(view)
        assert vp.GATE_STALE_RECEIPT in str(exc.value)
        assert "store" in str(exc.value)

    def test_an_AGGREGATE_RECEIPT_from_another_view_is_REFUSED_BY_NAME(self, world):
        mine, theirs = _honest(world), _view(world, _other_sel(world))
        view = _mutate(mine)
        view["admission"] = copy.deepcopy(theirs["admission"])
        with pytest.raises(vp.ProjectionSealError) as exc:
            vp.check(view)
        assert vp.GATE_STALE_RECEIPT in str(exc.value)
        assert "admission" in str(exc.value)

    def test_BOTH_receipts_bind_the_projection_they_admit(self, world):
        view = _honest(world)
        seal = view["projection"]["projection_sha256"]
        assert view["store"]["projection_sha256"] == seal
        assert view["admission"]["projection_sha256"] == seal

    def test_a_FORGED_SEAL_IDENTITY_is_REFUSED_BY_NAME(self, world):
        """The first thing an attacker who understood the check would rewrite."""
        view = _mutate(_honest(world))
        view["projection"]["projection_sha256"] = "0" * 64
        with pytest.raises(vp.ProjectionSealError) as exc:
            vp.check(view)
        assert vp.GATE_SEAL_IDENTITY in str(exc.value)

    def test_a_VIEW_edited_after_it_was_addressed_is_REFUSED_BY_NAME(self, world):
        view = _mutate(_honest(world))
        view["origin_types_present"] = []
        with pytest.raises(vp.ProjectionSealError) as exc:
            vp.check(view)
        assert vp.GATE_VIEW_IDENTITY in str(exc.value)


# --------------------------------------------------------------------------- #
class TestSchemaSetDrift:
    """`schemas_sha256` is bound EXACTLY. No substring rule, no 'hopeful' pattern."""

    def test_the_seal_binds_the_PINNED_schema_set_and_it_is_the_one_ON_DISK(self, world):
        view = _honest(world)
        assert view["projection"]["schemas_sha256"] == vp.PINNED_SCHEMAS_SHA256
        assert view["projection"]["schemas_sha256"] == vp.bound_schemas_sha256()
        assert view["store"]["schemas_sha256"] == vp.PINNED_SCHEMAS_SHA256

    def test_a_seal_naming_ANOTHER_schema_set_is_REFUSED_BY_NAME(self, world):
        view = _mutate(_honest(world))
        view["projection"]["schemas_sha256"] = "0" * 64
        with pytest.raises(vp.ProjectionSealError) as exc:
            vp.check(view)
        assert vp.GATE_SCHEMA_SET_DRIFT in str(exc.value)

    def test_a_DRIFTED_COLUMN_CONTRACT_is_REFUSED_BY_NAME(self, world):
        view = _mutate(_honest(world))
        view["projection"]["projection_schema_set_sha256"] = "0" * 64
        with pytest.raises(vp.ProjectionSealError) as exc:
            vp.check(view)
        assert vp.GATE_SCHEMA_SET_DRIFT in str(exc.value)

    def test_a_TABLE_sealed_under_a_FOREIGN_schema_id_is_REFUSED_BY_NAME(self, world):
        view = _mutate(_honest(world))
        view["projection"]["tables"]["candidates"]["schema_id"] = "spot.something_else.v1"
        with pytest.raises(vp.ProjectionSealError) as exc:
            vp.check(view)
        assert vp.GATE_SCHEMA_SET_DRIFT in str(exc.value)

    def test_the_verifier_id_is_an_EXACT_CONST_and_never_a_SUBSTRING_RULE(self, world):
        """The retired rule refused every honest report and admitted any forgery that renamed
        itself. A name is not a binding. Its shape may not come back."""
        view = _mutate(_honest(world))
        view["projection"]["projection_verifier_id"] = \
            "spot.some.independent.forgery.that.renamed.itself.v1"
        with pytest.raises(vp.ProjectionSealError) as exc:
            vp.check(view)
        assert vp.GATE_SCHEMA_SET_DRIFT in str(exc.value)


# --------------------------------------------------------------------------- #
class TestNothingTheSealTouchesWasBroken:
    """The seal binds rows. It may not have bought that by weakening anything above it."""

    def test_the_GLOBAL_STORE_stays_SELECTION_INDEPENDENT(self, world):
        """The seal lives in the VIEW. Not one byte of it may reach the reusable store."""
        vst.check_store_is_selection_independent(world["document"], world["tables"])
        blob = json.dumps({"doc": world["document"], "tables": world["tables"]})
        for token in ("projection_sha256", "selection_roles", "away_from_A", "toward_B"):
            assert token not in blob, f"{token!r} leaked into the GLOBAL store"

    def test_the_TYPED_ORIGINS_stay_SEPARATE_through_the_seal(self, world):
        view = _honest(world)
        for candidate in view["tables"]["candidates"]:
            by_origin = candidate["view_arm_keys_by_origin"]
            assert set(by_origin) == {"direct_target", "temporal_cross_time_measured",
                                      "endpoint_pathway_context"}
            # An INFERRED pathway arm never sources a drug edge.
            assert candidate["view_n_edges_by_origin"]["endpoint_pathway_context"] == 0

    def test_DIRECTIONALITY_survives_the_seal(self, world):
        """An inverse-direction hypothesis is never observed support, and is never ranked."""
        view = _honest(world)
        for edge in view["tables"]["target_drug_edges"]:
            if edge["directional_evidence_status"] == "inverse_direction_hypothesis":
                assert not edge["observed_perturbation_support"]

    def test_NO_COMBINED_RANK_and_NO_P_Q_FDR_at_any_depth(self, world):
        view = _honest(world)
        vc.check_browser_safe(view)                # re-asserted on the bytes that actually leave
        assert view["combined_objective_permitted"] is False
        assert view["candidate_rank_permitted"] is False
        assert view["headline_arm_permitted"] is False
        assert view["p_q_fdr_permitted"] is False

    def test_the_VIEW_is_still_a_PURE_QUERY_and_the_store_is_untouched(self, world):
        before = av2.table_content_hashes(world["tables"])
        _honest(world)
        _view(world, _other_sel(world))
        assert av2.table_content_hashes(world["tables"]) == before

    def test_TWO_QUESTIONS_over_ONE_STORE_get_DIFFERENT_seals(self, world):
        """The store is reusable; the projection is not. That is the whole architecture."""
        a, b = _honest(world), _view(world, _other_sel(world))
        assert a["projection"]["projection_sha256"] != b["projection"]["projection_sha256"]
        assert a["store"]["table_hashes"] == b["store"]["table_hashes"]      # ONE store

    def test_the_PUBLISHED_FIXTURE_carries_a_seal_and_is_a_LEGAL_view(self, world):
        from selection_world import FIXTURE_PATH
        with open(FIXTURE_PATH, encoding="utf-8") as fh:
            published = json.load(fh)
        vc.validate(published)
        assert published["projection"]["tables"]["arm_slots"]["row_count"] == 6
        assert published["projection"]["n_tables_sealed"] == 7
