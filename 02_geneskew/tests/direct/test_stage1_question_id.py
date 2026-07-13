"""THE CONTRACT'S question_id — re-derived, enforced, and never substituted.

WHAT WAS WRONG
--------------
Stage-2 read the v3 contract's `question_id` NOWHERE. `as_selection` set

    question_id = bound["selection_biology_sha256"]

so the identifier that says WHICH BIOLOGICAL QUESTION was asked was silently replaced by
Stage-2's own key, and the contract's own field was never checked against anything at all.
Consequences, both real:

  * a contract could carry ANY question_id — or one belonging to a DIFFERENT question — and
    Stage-2 would admit it, because it never looked;
  * the question_id that travelled downstream to Stage-3 was not the one Stage-1 minted. The
    two stages named the same question differently, and no artifact recorded that they had.

The recipe is Stage-1's, published in the schema and in the producer (539431dd):

    question_id = sha256(canonical_json({
        "A": {program_id, direction, condition: conditions[0]},
        "B": {program_id, direction, condition: conditions[-1]},
        "analysis_mode": mode}))[:16]

THREE INDEPENDENT IMPLEMENTATIONS AGREE HERE, ON PURPOSE
--------------------------------------------------------
  1. the GATE (``stage1_v3.derive_question_id``) — the code under test;
  2. ``fixtures_stage1_contract.independent_question_id`` — a literal re-implementation;
  3. ``jq -cS | sha256sum`` — out of process, in another language entirely.

and, as ground truth, the ids in STAGE-1'S OWN emitted fixtures, computed by Stage-1's code
before any of this existed. A test in which the gate agrees only with itself proves nothing.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess

import fixtures_stage1_contract as S1
import pytest
from direct import stage1_v3 as G
from direct.hashing import content_hash
from test_stage1_v3 import SCHEMA_PATH, emit, reseal

pytestmark = pytest.mark.skipif(
    not os.path.exists(SCHEMA_PATH), reason="the pinned v3 schema is not present")


@pytest.fixture(scope="module")
def schema():
    return G.load_schema(SCHEMA_PATH)


def _resealed(doc):
    """Reseal the full-contract hash ONLY — the id under attack is left exactly as written.

    Every forgery below is sealed this way, so the content-hash gate passes and the
    question_id gate is the one that has to catch it. A sloppy forger who never reseals is
    caught earlier, by the content hash — that is defence in depth, not this test.
    """
    payload = {k: v for k, v in doc.items() if k != "full_contract_content_sha256"}
    doc["full_contract_content_sha256"] = content_hash(payload)
    return doc


# --------------------------------------------------------------------------- #
# 1. THE RULE IS THE ONE STAGE-1 PUBLISHED.
# --------------------------------------------------------------------------- #
class TestTheRuleIsTheOnePublished:
    def test_the_module_publishes_the_derivation_rule(self):
        assert G.QUESTION_ID_RULE_ID.startswith("spot.stage01.question_id.")
        assert G.QUESTION_ID_LEN == 16
        assert "analysis_mode" in G.QUESTION_ID_RULE

    def test_the_pinned_schema_is_the_REPAIRED_one_not_the_stale_one(self):
        assert G.SCHEMA_SHA256 == S1.SCHEMA_SHA256
        assert G.SCHEMA_SHA256 != S1.STALE_SCHEMA_SHA256
        assert G.STAGE1_CONTRACT_COMMIT == S1.STAGE1_COMMIT

    def test_the_gate_agrees_with_an_INDEPENDENT_implementation_of_the_recipe(self):
        for mode, conds in ((G.MODE_WITHIN, ["Stim48hr"]),
                            (G.MODE_TEMPORAL, ["Stim8hr", "Stim48hr"])):
            doc = emit(a="p_one", dir_a="high", b="p_two", dir_b="low",
                       mode=mode, conditions=conds)
            assert G.derive_question_id(doc) == S1.independent_question_id(
                "p_one", "high", "p_two", "low", conds, mode)

    @pytest.mark.skipif(not shutil.which("jq"), reason="jq is not installed")
    def test_the_derivation_is_BYTE_IDENTICAL_to_the_jq_recipe(self, tmp_path):
        """A THIRD implementation, out of process and in another language."""
        doc = emit(mode=G.MODE_TEMPORAL, conditions=["Stim8hr", "Stim48hr"])
        path = os.path.join(str(tmp_path), "contract.json")
        with open(path, "w") as fh:
            json.dump(doc, fh, indent=2)

        # the biology-only content, assembled by jq straight from the contract's own fields
        prog = ('{A: {program_id: .canonical_content.A.program_id, '
                'direction: .canonical_content.A.direction, '
                'condition: .canonical_content.conditions[0]}, '
                'B: {program_id: .canonical_content.B.program_id, '
                'direction: .canonical_content.B.direction, '
                'condition: .canonical_content.conditions[-1]}, '
                'analysis_mode: .canonical_content.analysis_mode}')
        piped = subprocess.run(f"jq -cS '{prog}' {path} | tr -d '\\n' | sha256sum",
                               shell=True, capture_output=True, text=True, check=True)
        from_jq = piped.stdout.split()[0]

        assert G.derive_question_id(doc) == from_jq[:16]
        assert doc["question_id"] == from_jq[:16]


# --------------------------------------------------------------------------- #
# 2. STAGE-1'S OWN FIXTURES. Ground truth: their ids were computed by ITS code.
# --------------------------------------------------------------------------- #
class TestTheProducersOwnContractsREDERIVE:
    """The only check here that could not have been faked by agreeing with ourselves."""

    @pytest.mark.parametrize("name", ["within_ready", "within_refused", "temporal_ready"])
    def test_the_gate_REDERIVES_the_id_stage1_actually_minted(self, name):
        doc = S1.producer_fixture(name)
        assert G.derive_question_id(doc) == doc["question_id"]
        assert len(doc["question_id"]) == 16

    @pytest.mark.parametrize("name", ["within_ready", "temporal_ready"])
    def test_the_producers_READY_contracts_are_ADMITTED_whole(self, schema, name):
        bound = G.validate(S1.producer_fixture(name), schema)
        assert bound["question_id"] == bound["question_id_rederived"]
        assert bound["execution_status"] == G.EXECUTION_READY

    def test_the_producers_REFUSED_contract_is_refused_for_its_POLE_not_its_id(self, schema):
        """It is a well-formed contract that refuses cleanly — its id still re-derives."""
        doc = S1.producer_fixture("within_refused")
        assert G.derive_question_id(doc) == doc["question_id"]
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(doc, schema)
        assert exc.value.reason == G.REFUSE_POLE_UNAVAILABLE


# --------------------------------------------------------------------------- #
# 3. THE POSITIVES. What the consumer must ACCEPT — including the one it used to refuse.
# --------------------------------------------------------------------------- #
class TestTheContractsThatMustBeACCEPTED:
    def test_a_WITHIN_condition_selection_admits_and_binds_its_question_id(self, schema):
        bound = G.validate(emit(conditions=["Stim48hr"]), schema)
        assert bound["question_id"] == bound["question_id_rederived"]
        assert bound["endpoints"]["A"]["condition"] == "Stim48hr"
        assert bound["endpoints"]["B"]["condition"] == "Stim48hr"

    def test_a_TEMPORAL_selection_admits_and_its_endpoints_are_FROM_and_TO(self, schema):
        bound = G.validate(emit(mode=G.MODE_TEMPORAL,
                                conditions=["Stim8hr", "Stim48hr"]), schema)
        assert bound["endpoints"]["A"]["condition"] == "Stim8hr"     # from
        assert bound["endpoints"]["B"]["condition"] == "Stim48hr"    # to
        assert bound["question_id"] == bound["question_id_rederived"]

    def test_the_SAME_program_and_direction_at_DIFFERENT_times_is_ACCEPTED(self, schema):
        """THE REGRESSION. The stale consumer refused this as a degenerate axis.

        It is the comparison the temporal estimator exists to make, and Stage-1 emits it:
        one program, one direction, asked at two timepoints. The endpoints differ, so the
        poles differ, so it is two axes and not one.
        """
        bound = G.validate(emit(a="prog_alpha", dir_a="high",
                                b="prog_alpha", dir_b="high",
                                mode=G.MODE_TEMPORAL,
                                conditions=["Stim8hr", "Stim48hr"]), schema)
        assert bound["endpoints"]["A"] != bound["endpoints"]["B"]
        assert bound["question_id"] == bound["question_id_rederived"]

    def test_the_same_QUESTION_at_different_times_gets_DIFFERENT_question_ids(self, schema):
        """The condition is IN the id: two timepoints are two questions, not one."""
        early = G.validate(emit(mode=G.MODE_TEMPORAL,
                                conditions=["Rest", "Stim8hr"]), schema)
        late = G.validate(emit(mode=G.MODE_TEMPORAL,
                               conditions=["Rest", "Stim48hr"]), schema)
        assert early["question_id"] != late["question_id"]

    def test_the_question_id_is_STABLE_across_a_method_or_source_revision(self, schema):
        """The whole point of a biology-only id: the science did not change, so it must not.

        `selection_id` binds the scorer view and the source, so it MOVES. `question_id` binds
        neither, so it must NOT — that is exactly what makes them two different identifiers,
        and why one may never stand in for the other.
        """
        base = emit()
        revised = copy.deepcopy(base)
        revised["canonical_content"]["registry_scorer_view_sha256"] = "b" * 64
        revised["canonical_content"]["source_h5ad_sha256"] = "c" * 64
        revised = reseal(revised)

        a, b = G.validate(base, schema), G.validate(revised, schema)
        assert a["question_id"] == b["question_id"]            # the QUESTION is the same
        assert a["selection_id"] != b["selection_id"]          # the CONTRACT is not


# --------------------------------------------------------------------------- #
# 4. THE ATTACKS.
# --------------------------------------------------------------------------- #
class TestAForgedQuestionIdIsREFUSED:
    def test_a_MISMATCHED_question_id_is_refused(self, schema):
        doc = _resealed(emit(**{"question_id": "0123456789abcdef"}))
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(doc, schema)
        assert exc.value.reason == G.REFUSE_QUESTION_ID

    def test_an_id_SPOOFED_from_another_question_is_refused(self, schema):
        """THE ATTACK the check exists for: move a good id onto a different biology.

        The id is a real, honestly-earned question_id — it just belongs to a DIFFERENT
        question. Nothing about it looks wrong; only re-deriving it catches this.
        """
        honest = emit(a="prog_alpha", dir_a="high", b="prog_beta", dir_b="low")
        forged = emit(a="A_DIFFERENT_PROGRAM", dir_a="high", b="prog_beta", dir_b="low",
                      **{"question_id": honest["question_id"]})
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(_resealed(forged), schema)
        assert exc.value.reason == G.REFUSE_QUESTION_ID

    def test_an_id_carried_across_a_TIME_swap_is_refused(self, schema):
        """The condition is part of the question. A Stim8hr id may not ride a Stim48hr run."""
        early = emit(mode=G.MODE_TEMPORAL, conditions=["Rest", "Stim8hr"])
        forged = emit(mode=G.MODE_TEMPORAL, conditions=["Rest", "Stim48hr"],
                      **{"question_id": early["question_id"]})
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(_resealed(forged), schema)
        assert exc.value.reason == G.REFUSE_QUESTION_ID

    @pytest.mark.parametrize("bad", [None, "", "not-hex", "abc", "A" * 16, "a" * 64])
    def test_a_NULL_or_MALFORMED_question_id_never_admits(self, schema, bad):
        """Null included: an absent id must never be read as 'no id was required'."""
        doc = _resealed(emit(**{"question_id": bad}))
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(doc, schema)
        # the schema refuses the shape; the gate refuses the value. Either is fail-closed,
        # and NEITHER admits.
        assert exc.value.reason in (G.REFUSE_SCHEMA, G.REFUSE_QUESTION_ID)

    def test_a_MISSING_question_id_is_refused_by_the_schema(self, schema):
        doc = emit()
        del doc["question_id"]
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(_resealed(doc), schema)
        assert exc.value.reason == G.REFUSE_SCHEMA


class TestTheStaleSchemaIsREFUSED:
    def test_the_STALE_schema_bytes_are_refused_by_the_pin(self, tmp_path):
        """The exact staleness this repair fixes: the pre-repair schema no longer validates.

        It is not merely 'a different schema' — it is the one Stage-2 was ACTUALLY pinning,
        and it has no question_id, no arms and no estimator block. A contract checked against
        it was checked against nothing that matters here.
        """
        stale = os.path.join(str(tmp_path), "stale.schema.json")
        with open(stale, "w") as fh:
            json.dump({"type": "object"}, fh)         # any bytes but the pinned ones
        with pytest.raises(G.SelectionV3Error) as exc:
            G.load_schema(stale)
        assert exc.value.reason == G.REFUSE_SCHEMA_PIN

    def test_the_retired_pin_is_named_as_RETIRED_not_deleted(self):
        assert G.RETIRED_SCHEMA_SHA256.startswith("RETIRED:")
        assert S1.STALE_SCHEMA_SHA256 in G.RETIRED_SCHEMA_SHA256


class TestTheImpossibleTuplesAreREFUSED:
    def test_an_IDENTICAL_endpoint_on_both_poles_is_refused(self, schema):
        doc = emit(a="prog_alpha", dir_a="high", b="prog_alpha", dir_b="high",
                   conditions=["Rest"])
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(doc, schema)
        assert exc.value.reason == G.REFUSE_DEGENERATE_AXIS

    def test_a_TEMPORAL_contract_comparing_a_condition_with_ITSELF_is_refused(self, schema):
        doc = emit(mode=G.MODE_TEMPORAL, conditions=["Stim48hr", "Stim48hr"])
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(doc, schema)
        assert exc.value.reason == G.REFUSE_DUPLICATE_ENDPOINT

    @pytest.mark.parametrize("field, value", [
        ("estimator_id", "within_condition_v1"),
        ("analysis_mode", "within_condition"),
        ("n_conditions", 1),
    ])
    def test_an_ESTIMATOR_BLOCK_that_contradicts_the_contract_is_refused(
            self, schema, field, value):
        """The block was carried and never read: it could say anything.

        A contract routing as temporal at the top level while its bound estimator block said
        within-condition would have been admitted — and whichever block a reader consulted
        decided what they believed had been measured.
        """
        doc = emit(mode=G.MODE_TEMPORAL, conditions=["Stim8hr", "Stim48hr"])
        doc["estimator"][field] = value
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(_resealed(doc), schema)
        assert exc.value.reason in (G.REFUSE_SCHEMA, G.REFUSE_ESTIMATOR_INCOHERENT)


# --------------------------------------------------------------------------- #
# 5. BOTH IDS TRAVEL, AND NEITHER MAY IMPERSONATE THE OTHER.
# --------------------------------------------------------------------------- #
class TestBothIdentifiersAreBoundDownstream:
    def test_the_question_id_is_NOT_the_biology_hash_it_was_substituted_with(self, schema):
        """THE DEFECT, stated as a test. `as_selection` set question_id = biology sha256."""
        bound = G.validate(emit(), schema)
        sel = G.as_selection(bound, emit(), lane="production")
        assert sel.question_id == bound["question_id"]
        assert sel.question_id != bound["selection_biology_sha256"]
        assert len(sel.question_id) == 16
        assert len(bound["selection_biology_sha256"]) == 64

    def test_all_THREE_identities_are_carried_and_all_THREE_are_distinct(self, schema):
        bound = G.validate(emit(), schema)
        ids = {bound["question_id"],                 # WHICH biological question
               bound["selection_id"],                # WHICH contract asked it
               bound["selection_biology_sha256"]}    # Stage-2's OWN key
        assert len(ids) == 3

    def test_the_selection_id_still_binds_the_METHOD_and_the_INPUTS(self, schema):
        """Distinct, and distinct FOR A REASON: selection_id moves when the method does."""
        base = G.validate(emit(), schema)
        revised = copy.deepcopy(emit())
        revised["canonical_content"]["stage1_method_version"] = G.STAGE1_METHOD_VERSION
        revised["canonical_content"]["source_hf_revision"] = "rev2"
        revised = G.validate(reseal(revised), schema)
        assert revised["question_id"] == base["question_id"]
        assert revised["selection_id"] != base["selection_id"]

    def test_the_run_binding_block_carries_BOTH_ids(self, schema):
        doc = emit()
        sel = G.as_selection(G.validate(doc, schema), doc, lane="production")
        block = G.binding_block(sel)
        assert block["question_id"] == sel.question_id
        assert block["selection_id"] == sel.selection_id
        assert block["question_id_rule_id"] == G.QUESTION_ID_RULE_ID
        assert block["endpoints"]["A"]["condition"] == "Rest"

    def test_a_TEMPORAL_run_binding_names_the_ORDER_it_was_asked_in(self, schema):
        doc = emit(mode=G.MODE_TEMPORAL, conditions=["Stim8hr", "Stim48hr"])
        sel = G.as_selection(G.validate(doc, schema), doc, lane="production")
        block = G.binding_block(sel)
        assert (block["from_condition"], block["to_condition"]) == ("Stim8hr", "Stim48hr")
        assert block["endpoints"]["A"]["condition"] == "Stim8hr"
        assert block["endpoints"]["B"]["condition"] == "Stim48hr"
