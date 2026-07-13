"""THE WHOLE TUPLE SPACE: every valid selection admits, every impossible one refuses.

The consumer's job is to be GENERIC. It is handed (program A, direction A, program B,
direction B, condition(s), mode) and it must not care which biology that names — a gate with a
program in it does something different for the next program, which is the one nobody checks.

The stale consumer was NOT generic. It refused every tuple whose two poles shared a
(program, direction) — in every mode — so a whole plane of the space (the same program asked
at two timepoints, which is what the temporal estimator is FOR) was rejected outright, and no
test noticed because no test walked the space.

So this file walks it. Not a sample of hand-picked tuples: the ENUMERATED cross-product, twice
— over synthetic programs (exhaustive) and over the ten programs the AUTHORITATIVE release
actually admits (read from its selector, never retyped). For each tuple the rule is stated
independently of the gate, and the gate must agree:

    within_condition   : ADMITS unless the two endpoints are identical
                         (same program AND same direction AND same condition)
    temporal           : ADMITS whenever the two conditions differ — the endpoints
                         disambiguate the poles, whatever the programs and directions say

and every id it hands out must be re-derivable and unique to its tuple.
"""
from __future__ import annotations

import itertools

import fixtures_stage1_contract as S1
import pytest
from direct import stage1_v3 as G
from direct.hashing import content_hash
from test_stage1_v3 import SCHEMA_PATH, emit

pytestmark = pytest.mark.skipif(
    not SCHEMA_PATH, reason="the pinned v3 schema is not present")

PROGRAMS = ("p_alpha", "p_beta", "p_gamma")
DIRECTIONS = ("high", "low")
CONDITIONS = ("Rest", "Stim8hr", "Stim48hr")


@pytest.fixture(scope="module")
def schema():
    return G.load_schema(SCHEMA_PATH)


def _resealed(doc):
    payload = {k: v for k, v in doc.items() if k != "full_contract_content_sha256"}
    doc["full_contract_content_sha256"] = content_hash(payload)
    return doc


def within_tuples(programs=PROGRAMS):
    for a, da, b, db, c in itertools.product(programs, DIRECTIONS, programs, DIRECTIONS,
                                             CONDITIONS):
        yield a, da, b, db, [c]


def temporal_tuples(programs=PROGRAMS):
    for a, da, b, db in itertools.product(programs, DIRECTIONS, programs, DIRECTIONS):
        for c0, c1 in itertools.permutations(CONDITIONS, 2):     # ORDERED, distinct
            yield a, da, b, db, [c0, c1]


def is_degenerate(a, da, b, db, conds):
    """The rule, stated WITHOUT the gate: identical endpoints, and nothing else."""
    return (a, da, conds[0]) == (b, db, conds[-1])


def build(a, da, b, db, conds):
    mode = G.MODE_WITHIN if len(conds) == 1 else G.MODE_TEMPORAL
    return emit(a=a, dir_a=da, b=b, dir_b=db, mode=mode, conditions=conds)


# --------------------------------------------------------------------------- #
# 1. EVERY VALID TUPLE ADMITS. Exhaustively, over the enumerated space.
# --------------------------------------------------------------------------- #
class TestEveryValidTupleADMITS:
    def test_the_WITHIN_condition_space_is_exhaustively_walked(self, schema):
        admitted = refused = 0
        for a, da, b, db, conds in within_tuples():
            doc = build(a, da, b, db, conds)
            if is_degenerate(a, da, b, db, conds):
                with pytest.raises(G.SelectionV3Error) as exc:
                    G.validate(doc, schema)
                assert exc.value.reason == G.REFUSE_DEGENERATE_AXIS
                refused += 1
            else:
                bound = G.validate(doc, schema)
                assert bound["execution_status"] == G.EXECUTION_READY
                assert bound["question_id"] == bound["question_id_rederived"]
                admitted += 1
        # 3 programs x 2 dirs x 3 programs x 2 dirs x 3 conditions = 108; the degenerate ones
        # are exactly (same program, same direction) x 3 conditions = 3 x 2 x 3 = 18.
        assert (admitted, refused) == (90, 18)

    def test_the_TEMPORAL_space_is_exhaustively_walked(self, schema):
        admitted = 0
        for a, da, b, db, conds in temporal_tuples():
            bound = G.validate(build(a, da, b, db, conds), schema)
            assert bound["execution_status"] == G.EXECUTION_READY
            assert bound["endpoints"]["A"]["condition"] == conds[0]
            assert bound["endpoints"]["B"]["condition"] == conds[-1]
            admitted += 1
        # NOTHING in the temporal space is degenerate: the two conditions differ, so the two
        # endpoints differ, whatever the programs and directions are. 36 pole combos x 6
        # ordered condition pairs.
        assert admitted == 216

    def test_the_same_program_and_direction_at_two_times_admits_for_EVERY_pair(self, schema):
        """The plane the stale consumer refused, walked end to end."""
        n = 0
        for p, d in itertools.product(PROGRAMS, DIRECTIONS):
            for c0, c1 in itertools.permutations(CONDITIONS, 2):
                bound = G.validate(build(p, d, p, d, [c0, c1]), schema)
                assert bound["endpoints"]["A"] != bound["endpoints"]["B"]
                n += 1
        assert n == 36

    def test_the_space_is_walked_over_the_REAL_admitted_programs_too(self, schema):
        """Generic over the biology the AUTHORITATIVE release actually ships."""
        sel = S1.release_selector()
        programs = list(sel["admitted_programs"])
        assert len(programs) == 10 and sorted(sel["conditions"]) == sorted(CONDITIONS)
        assert tuple(sel["directions"]) == DIRECTIONS

        n = 0
        for a, b in itertools.product(programs, programs):
            for c in CONDITIONS:
                doc = build(a, "high", b, "low", [c])       # never degenerate: dirs differ
                bound = G.validate(doc, schema)
                assert bound["execution_status"] == G.EXECUTION_READY
                n += 1
        assert n == 300     # 10 x 10 x 3


# --------------------------------------------------------------------------- #
# 2. EVERY ID IS EARNED, AND UNIQUE TO ITS TUPLE.
# --------------------------------------------------------------------------- #
class TestEveryAdmittedTupleGetsItsOWNId:
    def test_no_two_distinct_questions_SHARE_a_question_id(self, schema):
        """Injective over the whole space — a collision would silently fuse two questions."""
        seen: dict[str, tuple] = {}
        for tup in itertools.chain(within_tuples(), temporal_tuples()):
            a, da, b, db, conds = tup
            if is_degenerate(*tup):
                continue
            qid = G.validate(build(*tup), schema)["question_id"]
            assert qid not in seen or seen[qid] == tup, \
                f"question_id {qid} collides: {seen.get(qid)} vs {tup}"
            seen[qid] = tup
        assert len(seen) == 90 + 216

    def test_the_ORDER_of_a_temporal_pair_changes_the_question(self, schema):
        """Rest->Stim48hr is not Stim48hr->Rest. An id that ignored order would fuse them."""
        fwd = G.validate(build("p_alpha", "high", "p_beta", "low",
                               ["Rest", "Stim48hr"]), schema)
        rev = G.validate(build("p_alpha", "high", "p_beta", "low",
                               ["Stim48hr", "Rest"]), schema)
        assert fwd["question_id"] != rev["question_id"]


# --------------------------------------------------------------------------- #
# 3. EVERY IMPOSSIBLE TUPLE REFUSES — by NAME.
# --------------------------------------------------------------------------- #
class TestEveryImpossibleTupleREFUSES:
    """A tuple Stage-1 could not have produced. Each one is refused, and each by its own
    typed reason — a gate that failed with one generic reason could not be branched on."""

    def test_an_identical_endpoint_is_refused(self, schema):
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(build("p_alpha", "high", "p_alpha", "high", ["Rest"]), schema)
        assert exc.value.reason == G.REFUSE_DEGENERATE_AXIS

    @pytest.mark.parametrize("cond", CONDITIONS)
    def test_a_temporal_pair_of_one_condition_with_ITSELF_is_refused(self, schema, cond):
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(emit(mode=G.MODE_TEMPORAL, conditions=[cond, cond]), schema)
        assert exc.value.reason == G.REFUSE_DUPLICATE_ENDPOINT

    @pytest.mark.parametrize("mode, conds", [
        (G.MODE_WITHIN, ["Rest", "Stim8hr"]),          # a within estimate spans one condition
        (G.MODE_TEMPORAL, ["Rest"]),                   # a cross estimate compares two
    ])
    def test_a_condition_count_that_contradicts_the_mode_is_refused(self, schema, mode,
                                                                    conds):
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(emit(mode=mode, conditions=conds), schema)
        assert exc.value.reason == G.REFUSE_CONDITIONS

    @pytest.mark.parametrize("value", [
        "higher",          # not in the direction enum
        "HIGH",            # enums are exact; a case fold is a different value
        "",
    ])
    def test_a_DIRECTION_outside_the_ENUM_is_refused_by_the_pinned_schema(self, schema,
                                                                          value):
        doc = emit()
        doc["canonical_content"]["A"]["direction"] = value
        doc["poles"]["A"]["direction"] = value
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(_resealed(doc), schema)
        assert exc.value.reason == G.REFUSE_SCHEMA

    @pytest.mark.parametrize("program", ["", "NOT_A_PROGRAM", "p_alpha_v2"])
    def test_a_PROGRAM_outside_the_effect_universe_is_refused_THERE_not_by_the_schema(
            self, schema, program):
        """WHERE a program id is policed, stated honestly.

        `program_id` is a free string in the v3 schema — it is NOT an enum, and the gate is
        generic by design: it does not carry a program list, because a gate with a program in
        it does something different for the next program. The universe is what decides, and it
        refuses by name. Asserting a schema refusal here would have been a test agreeing with
        a check that does not exist.
        """
        universe = {"p_alpha", "p_beta", "p_gamma"}
        doc = build(program, "high", "p_beta", "low", ["Rest"])
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(doc, schema, effect_universe_programs=universe)
        assert exc.value.reason == G.REFUSE_POLE_NOT_IN_UNIVERSE

    def test_a_program_INSIDE_the_universe_still_admits(self, schema):
        bound = G.validate(build("p_alpha", "high", "p_beta", "low", ["Rest"]), schema,
                           effect_universe_programs={"p_alpha", "p_beta", "p_gamma"})
        assert bound["execution_status"] == G.EXECUTION_READY

    @pytest.mark.parametrize("cond", ["Stim24hr", "rest", "", "Stim48"])
    def test_a_condition_outside_the_ENUM_is_refused(self, schema, cond):
        """The release ships three conditions. A fourth is not a condition."""
        doc = emit(conditions=[cond])
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(_resealed(doc), schema)
        assert exc.value.reason == G.REFUSE_SCHEMA

    @pytest.mark.parametrize("mode", ["cross_condition", "within", "", "temporal"])
    def test_an_analysis_mode_outside_the_ENUM_is_refused(self, schema, mode):
        doc = emit()
        doc["analysis_mode"] = mode
        doc["canonical_content"]["analysis_mode"] = mode
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(_resealed(doc), schema)
        assert exc.value.reason == G.REFUSE_SCHEMA

    def test_a_mode_that_BORROWS_the_other_estimator_is_refused(self, schema):
        doc = emit(mode=G.MODE_TEMPORAL, conditions=["Rest", "Stim48hr"],
                   estimator_id=G.ESTIMATOR_WITHIN)
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(_resealed(doc), schema)
        assert exc.value.reason == G.REFUSE_SCHEMA        # the f810 schema carries the rule

    def test_an_estimator_block_contradicting_its_contract_is_refused(self, schema):
        doc = emit(mode=G.MODE_TEMPORAL, conditions=["Rest", "Stim48hr"])
        doc["estimator"]["n_conditions"] = 1
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(_resealed(doc), schema)
        assert exc.value.reason == G.REFUSE_ESTIMATOR_INCOHERENT

    def test_an_estimator_naming_a_method_with_no_identity_is_refused(self, schema):
        doc = emit(mode=G.MODE_TEMPORAL, conditions=["Rest", "Stim48hr"])
        doc["estimator"].pop("method_sha256")
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(_resealed(doc), schema)
        assert exc.value.reason == G.REFUSE_METHOD_IDENTITY_MISSING

    def test_EVERY_impossible_tuple_above_refuses_with_a_TYPED_reason(self, schema):
        """No refusal is a sentence: each is a constant a caller can branch on."""
        typed = {v for k, v in vars(G).items() if k.startswith("REFUSE_")}
        for reason in (G.REFUSE_DEGENERATE_AXIS, G.REFUSE_DUPLICATE_ENDPOINT,
                       G.REFUSE_CONDITIONS, G.REFUSE_SCHEMA,
                       G.REFUSE_ESTIMATOR_INCOHERENT, G.REFUSE_METHOD_IDENTITY_MISSING):
            assert reason in typed
            assert " " not in reason        # a typed reason, never prose
