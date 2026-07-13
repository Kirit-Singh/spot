"""The SELECTION-VIEW MATERIALIZER: a pure projection of the store onto ONE question.

Every test here is GENERIC. The programs, conditions, poles and directions are read out of the
ADMITTED RELEASE and permuted — never written down. A test that only passed for one favoured
pair would have proved nothing about the next one, which is the whole point of a reusable store.

The refusal tests each make a NAMED gate FIRE. A gate nobody has watched fail is a gate nobody
knows is wired.
"""
from __future__ import annotations

import json
import os

import native_aggregate_fixture as NAF
import pytest
import selection_fixture as SF

from druglink import arm_selection as asel
from druglink import artifacts_v2 as av2
from druglink import direction as dr
from druglink import selection_v3 as s3
from druglink import selection_view as sv
from druglink import view_contract as vc
from druglink.hashing import content_hash

from selection_world import (
    TEMPORAL, WITHIN,
    _conditions, _programs, _selection, _verified, _view,
)

# =========================================================================== #
# COVERAGE (a): an arbitrary WITHIN-TIME selection.
# =========================================================================== #
class TestAnArbitraryWithinTimeSelection:

    def test_the_two_direct_arms_are_derived_from_the_selection_not_guessed(self, world):
        programs, conditions = _programs(world), _conditions(world)
        for condition in conditions:                       # EVERY condition, not a favourite
            sel = _verified(world, a=programs[0], b=programs[3], mode=WITHIN,
                            conditions=[condition], a_dir="high", b_dir="low")
            arms = asel.resolve(sel, world["aggregate"], manifest=world["manifest"])
            # away_from_A(high) -> DECREASE; toward_B(low) -> DECREASE. The map, not a guess.
            assert arms.a.arm_key == f"direct|{programs[0]}|decrease|{condition}"
            assert arms.b.arm_key == f"direct|{programs[3]}|decrease|{condition}"
            assert arms.a.lane == "direct" and arms.b.lane == "direct"

    def test_the_view_holds_only_the_selected_arms_and_is_not_empty(self, world):
        programs, conditions = _programs(world), _conditions(world)
        sel = _verified(world, a=programs[1], b=programs[2], mode=WITHIN,
                        conditions=[conditions[0]])
        view = _view(world, sel)

        assert view["tables"]["target_drug_edges"], "a view that proves nothing is not a view"
        assert view["tables"]["candidates"]
        keys = {e["arm_key"] for e in view["tables"]["target_drug_edges"]}
        assert keys == set(view["selected_arms"]["gene_arm_keys"])
        assert view["origin_type"] == dr.ORIGIN_DIRECT_TARGET

    def test_the_pathway_panels_are_condition_matched(self, world):
        programs, conditions = _programs(world), _conditions(world)
        sel = _verified(world, a=programs[1], b=programs[2], mode=WITHIN,
                        conditions=[conditions[2]])
        arms = asel.resolve(sel, world["aggregate"], manifest=world["manifest"])
        assert arms.pathway_context_label == "condition_matched_direct_pathway"
        for key in arms.pathway_arm_keys:
            assert key.split("|")[3] == conditions[2]


# =========================================================================== #
# COVERAGE (b): an arbitrary CROSS-TIME selection (ordered from -> to).
# =========================================================================== #
class TestAnArbitraryCrossTimeSelection:

    def test_the_two_temporal_arms_carry_the_ORDERED_pair(self, world):
        programs, conditions = _programs(world), _conditions(world)
        frm, to = conditions[0], conditions[2]
        sel = _verified(world, a=programs[4], b=programs[7], mode=TEMPORAL,
                        conditions=[frm, to], a_dir="low", b_dir="high")
        arms = asel.resolve(sel, world["aggregate"], manifest=world["manifest"])
        # away_from_A(low) -> INCREASE; toward_B(high) -> INCREASE.
        assert arms.a.arm_key == f"temporal|{programs[4]}|increase|{frm}|{to}"
        assert arms.b.arm_key == f"temporal|{programs[7]}|increase|{frm}|{to}"

    def test_reversing_the_pair_is_a_DIFFERENT_question_and_different_arms(self, world):
        programs, conditions = _programs(world), _conditions(world)
        frm, to = conditions[0], conditions[1]
        fwd = _verified(world, a=programs[4], b=programs[7], mode=TEMPORAL,
                        conditions=[frm, to])
        rev = _verified(world, a=programs[4], b=programs[7], mode=TEMPORAL,
                        conditions=[to, frm])
        a = asel.resolve(fwd, world["aggregate"], manifest=world["manifest"])
        b = asel.resolve(rev, world["aggregate"], manifest=world["manifest"])
        # The DiD changes sign when the pair is reversed: it is not the same measurement.
        assert set(a.gene_arm_keys).isdisjoint(set(b.gene_arm_keys))
        assert fwd.question_id != rev.question_id

    def test_the_view_is_temporal_and_never_reaches_a_same_time_direct_arm(self, world):
        programs, conditions = _programs(world), _conditions(world)
        sel = _verified(world, a=programs[4], b=programs[7], mode=TEMPORAL,
                        conditions=[conditions[0], conditions[1]])
        view = _view(world, sel)
        assert view["tables"]["target_drug_edges"]
        assert view["origin_type"] == dr.ORIGIN_TEMPORAL_CROSS_TIME
        # A cross-time question is NEVER answered with same-time gene ranks.
        assert all(e["lane"] == "temporal" for e in view["tables"]["target_drug_edges"])
        assert view["origin_types_present"] == [dr.ORIGIN_TEMPORAL_CROSS_TIME]

    def test_the_pathway_panels_are_the_ENDPOINTS_A_at_from_and_B_at_to(self, world):
        programs, conditions = _programs(world), _conditions(world)
        frm, to = conditions[0], conditions[2]
        sel = _verified(world, a=programs[4], b=programs[7], mode=TEMPORAL,
                        conditions=[frm, to])
        arms = asel.resolve(sel, world["aggregate"], manifest=world["manifest"])
        assert arms.pathway_context_label == "endpoint_direct_pathway"
        assert all(k.split("|")[3] == frm for k in
                   (a.arm_key for a in arms.pathway_arms[s3.ROLE_A]))
        assert all(k.split("|")[3] == to for k in
                   (a.arm_key for a in arms.pathway_arms[s3.ROLE_B]))


# =========================================================================== #
# COVERAGE (c): SAME PROGRAM / SAME DESIRED CHANGE — the case naive keying destroys.
#
# The two arm keys differ ONLY in their CONTEXT. The release holds SIX temporal arms for every
# (program, desired_change) — one per ordered pair — and they all share the prefix
# `temporal|P|change`. A prefix, a substring, or a "close enough" program+direction match resolves
# all six; taking the first answers a question about a different pair of time points and looks
# exactly like the right answer.
# =========================================================================== #
class TestSameProgramSameDirectionAcrossTimeDoesNotCollapse:

    def test_the_siblings_really_exist_so_a_prefix_match_really_would_collapse(self, world):
        programs, conditions = _programs(world), _conditions(world)
        key = f"temporal|{programs[5]}|decrease|{conditions[0]}|{conditions[1]}"
        siblings = asel.sibling_arm_keys(world["aggregate"], key)
        # Five other ordered pairs, same program, same desired change. This is the hazard.
        assert len(siblings) == 5
        assert all(s.startswith(f"temporal|{programs[5]}|decrease|") for s in siblings)

    def test_same_program_same_change_at_two_different_times_are_TWO_arms(self, world):
        """The two keys differ ONLY in their context — and they are NOT the same arm."""
        programs, conditions = _programs(world), _conditions(world)
        program, change = programs[5], "decrease"
        one = asel.arm_key("temporal", program, change,
                           {"from_condition": conditions[0], "to_condition": conditions[1]})
        two = asel.arm_key("temporal", program, change,
                           {"from_condition": conditions[1], "to_condition": conditions[2]})
        assert one != two
        assert one.split("|")[:3] == two.split("|")[:3]      # identical but for the context
        known = {a.arm_key for a in world["aggregate"].arms}
        assert one in known and two in known                 # both are real, distinct arms

    def test_two_cross_time_questions_on_the_SAME_program_and_change_give_DIFFERENT_views(
            self, world):
        """The selections differ ONLY in their time window. The views must too."""
        programs, conditions = _programs(world), _conditions(world)
        # away_from_A(high) -> decrease ; toward_B(low) -> decrease. SAME desired change, and
        # DIFFERENT programs, so the two arms of each question are distinct.
        early = _verified(world, a=programs[5], b=programs[6], mode=TEMPORAL,
                          conditions=[conditions[0], conditions[1]], a_dir="high", b_dir="low")
        late = _verified(world, a=programs[5], b=programs[6], mode=TEMPORAL,
                         conditions=[conditions[1], conditions[2]], a_dir="high", b_dir="low")
        a_arms = asel.resolve(early, world["aggregate"], manifest=world["manifest"])
        b_arms = asel.resolve(late, world["aggregate"], manifest=world["manifest"])
        assert a_arms.a.desired_change == a_arms.b.desired_change == "decrease"
        assert b_arms.a.desired_change == b_arms.b.desired_change == "decrease"

        v1, v2 = _view(world, early), _view(world, late)
        assert v1["tables"]["target_drug_edges"] and v2["tables"]["target_drug_edges"]
        assert v1["view_id"] != v2["view_id"]
        assert set(v1["selected_arms"]["gene_arm_keys"]).isdisjoint(
            v2["selected_arms"]["gene_arm_keys"])
        # AND neither view leaked a sibling arm that shares its prefix.
        for view in (v1, v2):
            selected = set(view["selected_arms"]["gene_arm_keys"])
            for row in view["tables"]["target_drug_edges"]:
                assert row["arm_key"] in selected

    def test_a_cross_time_view_excludes_the_sibling_arms_that_share_its_prefix(self, world):
        """Exact key equality — proved by the ABSENCE of five real, non-empty sibling arms."""
        programs, conditions = _programs(world), _conditions(world)
        sel = _verified(world, a=programs[5], b=programs[6], mode=TEMPORAL,
                        conditions=[conditions[0], conditions[1]], a_dir="high", b_dir="low")
        view = _view(world, sel)
        selected = set(view["selected_arms"]["gene_arm_keys"])
        siblings = {s for key in selected
                    for s in asel.sibling_arm_keys(world["aggregate"], key)}
        assert siblings, "the hazard must be present for its exclusion to mean anything"

        # Those sibling arms DO carry edges in the GLOBAL store...
        global_keys = {e["arm_key"] for e in world["tables"]["target_drug_edges"]}
        assert siblings & global_keys, "the siblings must be non-empty in the store"
        # ...and NONE of them reached this view.
        for name in ("target_drug_edges", "arm_summaries", "arm_slots"):
            assert not {r["arm_key"] for r in view["tables"][name]} & siblings


# =========================================================================== #
# THE NAMED REFUSALS. Every one fires.
# =========================================================================== #
class TestEveryRefusalIsANamedGateThatFires:

    def test_an_arm_the_aggregate_does_not_have_is_MISMATCHED(self, world):
        conditions = _conditions(world)
        sel = _verified(world, a="PROGRAM_THAT_IS_NOT_IN_THE_RELEASE", b=_programs(world)[1],
                        mode=WITHIN, conditions=[conditions[0]])
        with pytest.raises(asel.ArmSelectionError) as exc:
            asel.resolve(sel, world["aggregate"], manifest=world["manifest"])
        assert asel.GATE_ARM_NOT_IN_AGGREGATE in str(exc.value)

    def test_a_condition_the_release_never_ran_is_MISMATCHED(self, world):
        programs = _programs(world)
        sel = _verified(world, a=programs[0], b=programs[1], mode=WITHIN,
                        conditions=["A_CONDITION_NOBODY_MEASURED"])
        with pytest.raises(asel.ArmSelectionError) as exc:
            asel.resolve(sel, world["aggregate"], manifest=world["manifest"])
        assert asel.GATE_ARM_NOT_IN_AGGREGATE in str(exc.value)

    def test_an_aggregate_that_publishes_NO_role_pole_map_is_refused(self, world):
        """The claim and the code must agree: the map is REQUIRED, not checked-if-present."""
        manifest = {k: v for k, v in world["manifest"].items()
                    if k != "desired_change_by_role_and_pole"}
        with pytest.raises(asel.ArmSelectionError) as exc:
            asel.check_manifest_agrees(manifest)
        assert asel.GATE_PRODUCER_MAP_ABSENT in str(exc.value)

    def test_arm_keys_that_DISAGREE_with_stage1s_own_arms_block_are_refused(self, world):
        """Two lanes, one key, computed with different hands — or a refusal."""
        programs, conditions = _programs(world), _conditions(world)
        def forge(doc):
            doc["arms"]["away_from_A"]["direct_arm_key"] = \
                f"direct|{programs[0]}|increase|{conditions[0]}"   # the OPPOSITE perturbation

        # Forged AND RE-SEALED: every id still recomputes. Only the independent derivation
        # of the arm key can catch this.
        doc = _selection(world, a=programs[0], b=programs[1], mode=WITHIN,
                         conditions=[conditions[0]], mutate=forge)
        s3.verify(doc)                       # the contract is internally FLAWLESS...
        with pytest.raises(asel.ArmSelectionError) as exc:
            asel.resolve(s3.verify(doc), world["aggregate"], manifest=world["manifest"])
        assert asel.GATE_STAGE1_ARMS_DISAGREE in str(exc.value)

    def test_a_MISSING_question_id_is_refused_by_name(self, world):
        doc = _selection(world, a=_programs(world)[0], b=_programs(world)[1],
                         mode=WITHIN, conditions=[_conditions(world)[0]])
        doc.pop("question_id")
        doc["full_contract_content_sha256"] = SF.stage2_content_sha256(
            {k: v for k, v in doc.items() if k != "full_contract_content_sha256"})
        with pytest.raises(s3.SelectionError) as exc:
            s3.verify(doc)
        assert s3.GATE_QUESTION_ID_MISSING in str(exc.value)

    def test_a_question_id_that_does_not_derive_from_the_biology_is_refused(self, world):
        doc = _selection(world, a=_programs(world)[0], b=_programs(world)[1],
                         mode=WITHIN, conditions=[_conditions(world)[0]])
        doc["question_id"] = "0123456789abcdef"
        doc["full_contract_content_sha256"] = SF.stage2_content_sha256(
            {k: v for k, v in doc.items() if k != "full_contract_content_sha256"})
        with pytest.raises(s3.SelectionError) as exc:
            s3.verify(doc)
        assert s3.GATE_QUESTION_ID_NOT_DERIVED in str(exc.value)

    def test_a_bogus_arm_key_is_refused_by_name(self, world):
        for bogus in ("", "direct|prog", "direct|prog|high|Rest",          # a POLE, not a change
                      "temporal|prog|increase|Rest",                       # context arity wrong
                      "nolane|prog|increase|Rest", 42):
            with pytest.raises(asel.ArmSelectionError) as exc:
                asel.parse_arm_key(bogus)
            assert asel.GATE_BOGUS_ARM_KEY in str(exc.value)

    def test_a_key_built_from_a_POLE_instead_of_a_desired_change_is_refused(self, world):
        with pytest.raises(asel.ArmSelectionError) as exc:
            asel.arm_key("direct", "P", "high", {"condition": "Rest"})
        assert asel.GATE_BOGUS_ARM_KEY in str(exc.value)
        assert "POLE" in str(exc.value)

    def test_a_STALE_selection_naming_another_release_is_refused_by_name(self, world):
        programs, conditions = _programs(world), _conditions(world)
        doc = _selection(world, a=programs[0], b=programs[1], mode=WITHIN,
                         conditions=[conditions[0]])
        doc["canonical_content"]["registry_scorer_view_sha256"] = "9" * 64
        doc["selection_id"] = SF.stage2_content_sha256(doc["canonical_content"])[:16]
        doc["full_contract_content_sha256"] = SF.stage2_content_sha256(
            {k: v for k, v in doc.items() if k != "full_contract_content_sha256"})
        with pytest.raises(sv.SelectionViewError) as exc:
            _view(world, s3.verify(doc))
        assert sv.GATE_STALE_SELECTION in str(exc.value)

    def test_a_v2_bundle_built_over_ANOTHER_aggregate_is_refused_by_name(self, world):
        programs, conditions = _programs(world), _conditions(world)
        sel = _verified(world, a=programs[0], b=programs[1], mode=WITHIN,
                        conditions=[conditions[0]])
        document = json.loads(json.dumps(world["document"]))
        document["stage2_aggregate"]["manifest_self_hash"] = "0" * 64
        with pytest.raises(sv.SelectionViewError) as exc:
            _view(world, sel, document=document)
        assert sv.GATE_STALE_BUNDLE in str(exc.value)

    def test_an_aggregate_with_NO_receipt_is_UNADMITTED(self, world):
        with pytest.raises(sv.SelectionViewError) as exc:
            sv.admit_receipt(os.path.join(world["root"], "no_such_receipt.json"),
                             aggregate=world["aggregate"],
                             report_path=world["paths"]["report"])
        assert sv.GATE_NO_RECEIPT in str(exc.value)

    def test_a_receipt_that_binds_OTHER_BYTES_is_UNADMITTED(self, tmp_path, world):
        paths = NAF.build(str(tmp_path / "forged"),
                          mutate_receipt=lambda r: r["aggregate"]["manifest"].update(
                              {"raw_sha256": "0" * 64}))
        with pytest.raises(sv.SelectionViewError) as exc:
            sv.admit_receipt(paths["receipt"], aggregate=NAF.admit(paths),
                             report_path=paths["report"])
        assert sv.GATE_RECEIPT_BINDS_OTHER_BYTES in str(exc.value)

    def test_a_receipt_that_binds_no_BRIDGE_joins_nothing(self, tmp_path):
        paths = NAF.build(str(tmp_path / "nobridge"),
                          mutate_receipt=lambda r: r.pop("bridge"))
        with pytest.raises(sv.SelectionViewError) as exc:
            sv.admit_receipt(paths["receipt"], aggregate=NAF.admit(paths),
                             report_path=paths["report"])
        assert sv.GATE_RECEIPT_BINDS_NO_BRIDGE in str(exc.value)

    def test_a_producer_role_pole_map_we_disagree_with_is_refused(self, world):
        manifest = dict(world["manifest"])
        manifest["desired_change_by_role_and_pole"] = {
            "away_from_A|high": "increase", "away_from_A|low": "decrease",
            "toward_B|high": "decrease", "toward_B|low": "increase"}      # INVERTED
        with pytest.raises(asel.ArmSelectionError) as exc:
            asel.check_manifest_agrees(manifest)
        assert asel.GATE_PRODUCER_MAP_DISAGREES in str(exc.value)

    def test_a_selection_whose_id_does_not_derive_from_its_content_is_refused(self, world):
        doc = _selection(world, a=_programs(world)[0], b=_programs(world)[1],
                         mode=WITHIN, conditions=[_conditions(world)[0]])
        doc["selection_id"] = "dead" * 4
        with pytest.raises(s3.SelectionError) as exc:
            s3.verify(doc)
        assert s3.GATE_SELECTION_ID_NOT_DERIVED in str(exc.value)

    def test_the_condition_arity_is_decided_by_the_MODE(self, world):
        programs, conditions = _programs(world), _conditions(world)
        for mode, conds in ((WITHIN, conditions[:2]), (TEMPORAL, conditions[:1])):
            doc = _selection(world, a=programs[0], b=programs[1], mode=mode, conditions=conds)
            with pytest.raises(s3.SelectionError) as exc:
                s3.verify(doc)
            assert s3.GATE_SELECTION_CONDITIONS in str(exc.value)


# =========================================================================== #
# THE ARCHITECTURAL INVARIANT: the view is a PROJECTION, not a recompute.
# =========================================================================== #
class TestTheViewIsAProjectionAndNotARecompute:

    def test_two_DISJOINT_selections_give_DIFFERENT_non_empty_subsets(self, world):
        programs, conditions = _programs(world), _conditions(world)
        one = _verified(world, a=programs[0], b=programs[1], mode=WITHIN,
                        conditions=[conditions[0]])
        two = _verified(world, a=programs[8], b=programs[9], mode=TEMPORAL,
                        conditions=[conditions[1], conditions[2]])
        v1, v2 = _view(world, one), _view(world, two)

        # NON-EMPTY FIRST. Two empty views are trivially "different" and prove nothing.
        for view in (v1, v2):
            assert view["tables"]["target_drug_edges"]
            assert view["tables"]["candidates"]
            assert view["tables"]["dispositions"]

        assert set(v1["selected_arms"]["gene_arm_keys"]).isdisjoint(
            v2["selected_arms"]["gene_arm_keys"])
        for name in ("target_drug_edges", "arm_summaries"):
            ids = {"target_drug_edges": "edge_id", "arm_summaries": "arm_summary_id"}[name]
            assert {r[ids] for r in v1["tables"][name]} != {r[ids] for r in v2["tables"][name]}

        # NEITHER view holds a row from outside its own selection.
        for view in (v1, v2):
            allowed = set(view["selected_arms"]["gene_arm_keys"])
            assert {e["arm_key"] for e in view["tables"]["target_drug_edges"]} <= allowed

    def test_the_GLOBAL_store_is_byte_identical_after_N_materializations(self, world):
        before_tables = av2.table_content_hashes(world["tables"])
        before_doc = world["document"]["canonical_content_sha256"]
        before_id = world["document"]["bundle_id"]

        programs, conditions = _programs(world), _conditions(world)
        for i, condition in enumerate(conditions):
            _view(world, _verified(world, a=programs[i], b=programs[i + 4], mode=WITHIN,
                                   conditions=[condition]))
        _view(world, _verified(world, a=programs[0], b=programs[1], mode=TEMPORAL,
                               conditions=[conditions[0], conditions[2]]))

        assert av2.table_content_hashes(world["tables"]) == before_tables
        assert world["document"]["canonical_content_sha256"] == before_doc
        assert world["document"]["bundle_id"] == before_id

    def test_materializing_the_SAME_selection_twice_is_byte_identical(self, world):
        programs, conditions = _programs(world), _conditions(world)
        sel = _verified(world, a=programs[3], b=programs[6], mode=WITHIN,
                        conditions=[conditions[1]])
        a, b = _view(world, sel), _view(world, sel)
        assert content_hash(a) == content_hash(b)
        assert a["view_id"] == b["view_id"]

    def test_a_cached_view_is_REGENERABLE_from_the_store(self, world, tmp_path):
        """A cache that cannot be regenerated is not a cache; it is a second source of truth."""
        programs, conditions = _programs(world), _conditions(world)
        sel = _verified(world, a=programs[2], b=programs[5], mode=TEMPORAL,
                        conditions=[conditions[2], conditions[0]])
        cached = tmp_path / f"{sel.selection_id}.json"
        cached.write_text(json.dumps(_view(world, sel), sort_keys=True, separators=(",", ":")))
        raw = cached.read_text()
        cached.unlink()                                     # DISCARD the cache entirely
        regenerated = json.dumps(_view(world, sel), sort_keys=True, separators=(",", ":"))
        assert regenerated == raw

    def test_NO_selection_identity_or_role_ever_reaches_the_GLOBAL_store(self, world):
        vc.check_store_is_selection_independent(world["document"], world["tables"])
        blob = json.dumps({"doc": world["document"], "tables": world["tables"]})
        for leaked in ("away_from_A", "toward_B", "selection_id", "question_id",
                       "selection_role"):
            assert f'"{leaked}"' not in blob, (
                f"{leaked!r} leaked into the GLOBAL store: the release would then hold ONE "
                "question's answer and stop being reusable")
