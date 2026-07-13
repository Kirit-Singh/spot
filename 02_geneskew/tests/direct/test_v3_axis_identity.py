"""B1 — WHAT MAKES TWO AXES THE SAME AXIS: the (program, direction, condition) tuple.

The v3 bridge had no notion of axis identity at all:

  * ``bind_axis`` keyed selectability as ``program|condition`` — the DIRECTION was not in
    the key, so the "high" and "low" poles of one program produced the same selectability
    record and were indistinguishable in the emitted evidence;
  * nothing refused a DEGENERATE axis. A contract naming the same program in the same
    direction for BOTH poles would have been screened: ``away_from_A`` and ``toward_B``
    would be the two opposite arms of a single axis, perfectly anti-correlated, and the
    convergence between them would be an artefact of the contract rather than a finding.

The rule, stated once: **only an exactly identical (program_id, direction, condition)
tuple is the same axis.** The same program and direction at a DIFFERENT condition is a
DIFFERENT axis — that is the whole premise of the per-condition lane and of the temporal
comparison, and a bridge that collapsed them would refuse the runs the matrix is built on.
"""
from __future__ import annotations

# F811: importing a pytest fixture and then naming it as a test parameter is the fixture
# -reuse idiom, not a redefinition. The alternative is a second GHOST release fixture, and
# two fixtures that must stay in step are worse than one that is shared.
# ruff: noqa: F811
import copy
import os

import pytest
from direct import stage1_v3 as G
from test_cli_v3 import GHOST_A, GHOST_B, v3_run  # noqa: F401  (fixture)
from test_stage1_v3 import SCHEMA_PATH, emit
from test_temporal_v3 import _reseal as reseal
from test_temporal_v3 import v3_contract

pytestmark = pytest.mark.skipif(
    not os.path.exists(SCHEMA_PATH),
    reason="the frozen Stage-1 v3 contract is not on this host")


@pytest.fixture(scope="module")
def schema():
    return G.load_schema(SCHEMA_PATH)


class TestTheIdentityTupleIsAllThree:
    def test_a_pole_identity_names_program_direction_AND_condition(self):
        assert G.pole_identity("P", "high", "Rest") == "P|high|Rest"

    def test_direction_is_part_of_the_identity(self):
        assert G.pole_identity("P", "high", "Rest") != G.pole_identity("P", "low", "Rest")

    def test_condition_is_part_of_the_identity(self):
        assert G.pole_identity("P", "high", "Rest") != \
            G.pole_identity("P", "high", "Stim48hr")

    def test_only_an_EXACTLY_identical_tuple_is_identical(self):
        assert G.pole_identity("P", "high", "Rest") == G.pole_identity("P", "high", "Rest")


class TestTheSameProgramAndDirectionAtDifferentConditionsIsPERMITTED:
    """The per-condition lane runs the SAME axis at Rest, Stim8hr and Stim48hr."""

    def test_both_contracts_ADMIT(self, schema):
        for cond in ("Rest", "Stim8hr", "Stim48hr"):
            bound = G.validate(emit(conditions=[cond]), schema)
            assert bound["conditions"] == [cond]

    def test_they_are_DIFFERENT_biology_and_hash_differently(self, schema):
        rest = G.validate(emit(conditions=["Rest"]), schema)
        stim = G.validate(emit(conditions=["Stim48hr"]), schema)
        assert rest["biology"]["A"] == stim["biology"]["A"]        # same program+direction
        assert rest["selection_biology_sha256"] != stim["selection_biology_sha256"]

    def test_their_pole_identities_differ_only_in_the_condition(self, schema):
        rest = G.validate(emit(conditions=["Rest"]), schema)
        stim = G.validate(emit(conditions=["Stim48hr"]), schema)
        assert G.axis_identity(rest) != G.axis_identity(stim)
        assert [i.rsplit("|", 1)[0] for i in G.axis_identity(rest)] == \
               [i.rsplit("|", 1)[0] for i in G.axis_identity(stim)]

    def test_a_TEMPORAL_contract_carries_the_axis_at_BOTH_conditions(self, schema):
        bound = G.validate(emit(mode=G.MODE_TEMPORAL,
                                conditions=["Rest", "Stim48hr"]), schema)
        ids = G.axis_identity(bound)
        assert "prog_alpha|high|Rest" in ids
        assert "prog_alpha|high|Stim48hr" in ids


class TestADegenerateAxisIsREFUSED:
    """A and B the same program, the same direction, the same condition — one axis."""

    def test_it_is_refused_at_the_NAMED_gate(self, schema):
        doc = emit(a="prog_alpha", dir_a="high", b="prog_alpha", dir_b="high")
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(doc, schema)
        assert exc.value.reason == G.REFUSE_DEGENERATE_AXIS

    def test_it_is_refused_for_a_TEMPORAL_contract_too(self, schema):
        doc = emit(a="prog_alpha", dir_a="low", b="prog_alpha", dir_b="low",
                   mode=G.MODE_TEMPORAL, conditions=["Rest", "Stim48hr"])
        with pytest.raises(G.SelectionV3Error) as exc:
            G.validate(doc, schema)
        assert exc.value.reason == G.REFUSE_DEGENERATE_AXIS

    def test_the_SAME_program_in_OPPOSITE_directions_is_a_real_axis_and_ADMITS(
            self, schema):
        # Not identical: the tuples differ in the direction. Refusing this would be the
        # bridge deciding a biology question the contract is entitled to ask.
        bound = G.validate(emit(a="prog_alpha", dir_a="high",
                                b="prog_alpha", dir_b="low"), schema)
        assert bound["biology"]["A"]["program_id"] == bound["biology"]["B"]["program_id"]
        assert len(set(G.axis_identity(bound))) == 2

    def test_two_different_programs_ADMIT(self, schema):
        bound = G.validate(emit(), schema)
        assert len(set(G.axis_identity(bound))) == 2


def _directed(doc, dir_a, dir_b):
    """The same contract with explicit pole directions, resealed so it stays self-consistent."""
    doc = copy.deepcopy(doc)
    for pole, direction in (("A", dir_a), ("B", dir_b)):
        doc["canonical_content"][pole]["direction"] = direction
        doc["poles"][pole]["direction"] = direction
    return reseal(doc)


class TestTheSelectabilityEvidenceCarriesTheWholeTuple:
    """`bind_axis` keyed selectability on program|condition — the direction was not in it."""

    def _axis(self, v3_run, dir_a, dir_b, b=GHOST_B):
        import json

        from direct import run_screen, stage1_v3
        args, path, doc = v3_run()
        doc = _directed(v3_contract(a=GHOST_A, b=b, mode=stage1_v3.MODE_WITHIN,
                                    conditions=("Rest",)), dir_a, dir_b)
        with open(path, "w") as fh:
            json.dump(doc, fh)
        args.stage1_v3_selection = path
        args.stage1_v3_schema = SCHEMA_PATH
        sel = stage1_v3.load_selection(args, expect_mode=stage1_v3.MODE_WITHIN)
        assert sel is not None, "the v3 contract was not loaded — this tests nothing"
        return run_screen.prepare(args, v3=sel)["axis"]

    def test_the_selectability_key_carries_the_whole_tuple(self, v3_run):
        axis = self._axis(v3_run, "high", "low")
        assert axis["selectability"]["A"]["pole_identities"] == [f"{GHOST_A}|high|Rest"]
        assert axis["selectability"]["B"]["pole_identities"] == [f"{GHOST_B}|low|Rest"]

    def test_the_two_poles_of_ONE_program_are_distinguishable_in_the_evidence(self, v3_run):
        # program|condition alone made these two records byte-identical.
        axis = self._axis(v3_run, "high", "low", b=GHOST_A)
        assert axis["selectability"]["A"]["pole_identities"] != \
            axis["selectability"]["B"]["pole_identities"]
