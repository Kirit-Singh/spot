"""A true fact under a false heading is the worst thing this pipeline can emit.

The global Stage-3 store is selection-independent, and must stay so. But nothing forced a consumer
to PROVE that a candidate it loaded has evidence in the arms the active selection actually names.
So a real drug — real edges, real provenance, every hash checking out — could be rendered as the
answer to a question it has no evidence in. Nothing crashes. Nothing fails a schema. Every check it
passes makes it more convincing.

These tests make the membership contract fire from every direction. Each attack must fail at a
NAMED gate, and the honest world must be ADMITTED first — otherwise every refusal below is vacuous.

NO PATHWAY COUNT IS PINNED HERE. Zero pathway output is a fail-closed state pending W18, not a
result, and nothing in this file encodes an expectation of it.
"""
from __future__ import annotations

import pytest

from druglink import candidate_membership as cm
from druglink import workflow as wf

# Two arms that differ ONLY in the context tail. This is the pair a prefix match destroys.
ARM_REST = "direct|treg_like|decrease|Rest"
ARM_S48 = "direct|treg_like|decrease|Stim48hr"
ARM_OTHER = "direct|th1_like|increase|Rest"

CID = "AM:INCHIKEY:AAAAAAAAAAAAAAAAAAAAAAAAAA-N"
OTHER_CID = "AM:INCHIKEY:BBBBBBBBBBBBBBBBBBBBBBBBBB-N"


def _edge(cid=CID, arm=ARM_REST):
    return {"candidate_id": cid, "active_moiety_id": cid, "arm_key": arm}


def _summary(cid=CID, arm=ARM_REST, state=wf.OBSERVED_PERTURBATION):
    return {"candidate_id": cid, "active_moiety_id": cid, "arm_key": arm,
            "arm_evidence_state": state}


def _candidate(cid=CID, arms=(ARM_REST,), **over):
    row = {
        "candidate_id": cid, "active_moiety_id": cid,
        "arm_keys": sorted(arms),
        "observed_perturbation_arm_keys": sorted(arms),
        "inverse_direction_hypothesis_arm_keys": [],
        "pathway_hypothesis_arm_keys": [],
        "opposed_arm_keys": [],
        "unresolved_arm_keys": [],
    }
    row.update(over)
    return row


@pytest.fixture
def world():
    """One candidate with evidence in ONE arm (Rest). Non-vacuous: it really has an edge."""
    edges = [_edge()]
    summaries = [_summary()]
    cands = [_candidate()]
    assert edges and summaries and cands
    return {"edges": edges, "arm_summaries": summaries, "candidates": cands}


# --------------------------------------------------------------------------- #
# The honest world is admitted. Everything below depends on this.
# --------------------------------------------------------------------------- #
def test_the_honest_world_is_ADMITTED(world):
    cm.check_published_membership(world["candidates"][0], edges=world["edges"],
                                  arm_summaries=world["arm_summaries"])
    cm.check_displayed(world["candidates"], selected_arm_keys=[ARM_REST],
                       edges=world["edges"], arm_summaries=world["arm_summaries"])


def test_membership_is_RE_DERIVED_from_the_evidence_not_read_from_the_candidate(world):
    truth = cm.derive(CID, edges=world["edges"], arm_summaries=world["arm_summaries"])
    assert truth["arm_keys"] == [ARM_REST]
    assert truth["observed_perturbation_arm_keys"] == [ARM_REST]


# --------------------------------------------------------------------------- #
# (1) THE CORE DEFECT: a global candidate displayed under a question it has no evidence in.
# --------------------------------------------------------------------------- #
def test_a_candidate_with_NO_evidence_in_the_selection_is_REFUSED(world):
    """The drug is real. Its edges are real. It simply has nothing to do with THIS question."""
    with pytest.raises(cm.MembershipError) as exc:
        cm.check_displayed(world["candidates"], selected_arm_keys=[ARM_OTHER],
                           edges=world["edges"], arm_summaries=world["arm_summaries"])
    assert exc.value.gate == cm.GATE_CANDIDATE_NOT_IN_SELECTION


def test_displayable_is_False_for_a_question_the_candidate_has_no_evidence_in(world):
    assert cm.displayable(world["candidates"][0], selected_arm_keys=[ARM_REST],
                          edges=world["edges"], arm_summaries=world["arm_summaries"]) is True
    assert cm.displayable(world["candidates"][0], selected_arm_keys=[ARM_OTHER],
                          edges=world["edges"], arm_summaries=world["arm_summaries"]) is False


# --------------------------------------------------------------------------- #
# (2) EXACT KEYS ONLY. The same program+direction at two times differ ONLY in the tail.
# --------------------------------------------------------------------------- #
def test_a_PREFIX_match_does_not_make_a_candidate_displayable(world):
    """`direct|treg_like|decrease|Rest` and `…|Stim48hr` share every field but the condition. A
    prefix match equates them, and the user is shown a drug from Rest under a Stim48hr question."""
    assert ARM_S48.startswith(ARM_REST.rsplit("|", 1)[0])      # they really do share a prefix
    assert cm.displayable(world["candidates"][0], selected_arm_keys=[ARM_S48],
                          edges=world["edges"], arm_summaries=world["arm_summaries"]) is False
    with pytest.raises(cm.MembershipError) as exc:
        cm.check_displayed(world["candidates"], selected_arm_keys=[ARM_S48],
                           edges=world["edges"], arm_summaries=world["arm_summaries"])
    assert exc.value.gate == cm.GATE_CANDIDATE_NOT_IN_SELECTION


def test_the_same_DISPLAY_NAME_with_a_different_full_arm_key_is_REFUSED(world):
    """Two arms may share a label. The FULL key is the identity; a name is not a binding."""
    same_name_other_key = dict(world["candidates"][0],
                               preferred_name="TREG DECREASE",
                               view_arm_keys=[ARM_S48])          # a DIFFERENT arm, same label
    with pytest.raises(cm.MembershipError) as exc:
        cm.check_displayed([same_name_other_key], selected_arm_keys=[ARM_REST],
                           edges=world["edges"], arm_summaries=world["arm_summaries"])
    assert exc.value.gate == cm.GATE_FOREIGN_ARM


def test_the_rule_is_PUBLISHED_as_exact_equality():
    v = cm.vocabularies()
    assert v["match_rule"] == "exact_string_equality_on_the_whole_arm_key"
    assert v["prefix_match_permitted"] is False
    assert v["display_name_match_permitted"] is False


# --------------------------------------------------------------------------- #
# (3) MUTATIONS: a foreign arm added; a real arm dropped.
# --------------------------------------------------------------------------- #
def test_ADDING_a_FOREIGN_arm_to_a_displayed_candidate_is_REFUSED(world):
    shown = dict(world["candidates"][0], view_arm_keys=[ARM_REST, ARM_OTHER])
    with pytest.raises(cm.MembershipError) as exc:
        cm.check_displayed([shown], selected_arm_keys=[ARM_REST],
                           edges=world["edges"], arm_summaries=world["arm_summaries"])
    assert exc.value.gate == cm.GATE_FOREIGN_ARM


def test_DROPPING_an_arm_the_evidence_gives_it_is_REFUSED(world):
    """A dropped arm is indistinguishable from evidence nobody found."""
    edges = [_edge(arm=ARM_REST), _edge(arm=ARM_S48)]
    summaries = [_summary(arm=ARM_REST), _summary(arm=ARM_S48)]
    shown = dict(_candidate(arms=(ARM_REST, ARM_S48)), view_arm_keys=[ARM_REST])
    with pytest.raises(cm.MembershipError) as exc:
        cm.check_displayed([shown], selected_arm_keys=[ARM_REST, ARM_S48],
                           edges=edges, arm_summaries=summaries)
    assert exc.value.gate == cm.GATE_ARM_DROPPED


def test_a_WIDENED_published_membership_is_REFUSED(world):
    """The candidate CLAIMS an arm its evidence does not give it — which is how it becomes
    displayable under a question it never touched."""
    lying = _candidate(arms=(ARM_REST, ARM_OTHER))
    with pytest.raises(cm.MembershipError) as exc:
        cm.check_published_membership(lying, edges=world["edges"],
                                      arm_summaries=world["arm_summaries"])
    assert exc.value.gate == cm.GATE_MEMBERSHIP_NOT_REDERIVED
    assert ARM_OTHER in str(exc.value)


def test_a_NARROWED_published_membership_is_REFUSED():
    """Real evidence vanishing from a question it belongs to. Just as silent, just as wrong."""
    edges = [_edge(arm=ARM_REST), _edge(arm=ARM_S48)]
    summaries = [_summary(arm=ARM_REST), _summary(arm=ARM_S48)]
    with pytest.raises(cm.MembershipError) as exc:
        cm.check_published_membership(_candidate(arms=(ARM_REST,)), edges=edges,
                                      arm_summaries=summaries)
    assert exc.value.gate == cm.GATE_MEMBERSHIP_NOT_REDERIVED


# --------------------------------------------------------------------------- #
# (4) THE VIEW BINDS ITS QUESTION AND THE MEMBERSHIP OF WHAT IT SHOWS.
# --------------------------------------------------------------------------- #
def _view(world, *, arms=(ARM_REST,), **over):
    v = {
        "selection": {"selection_id": "7a77f6b314b9c0f3",
                      "question_id": "3203d63970720d4f",
                      "analysis_mode": "within_condition"},
        "selected_arms": {"all_arm_keys": list(arms)},
        "tables": {"candidates": world["candidates"]},
    }
    v.update(over)
    return v


def test_a_view_that_names_its_question_and_its_arms_is_ADMITTED(world):
    cm.check_view_binding(_view(world), edges=world["edges"],
                          arm_summaries=world["arm_summaries"])


@pytest.mark.parametrize("field", cm.REQUIRED_VIEW_IDENTITY)
def test_a_view_missing_any_part_of_its_selection_identity_is_REFUSED(world, field):
    v = _view(world)
    v["selection"].pop(field)
    with pytest.raises(cm.MembershipError) as exc:
        cm.check_view_binding(v, edges=world["edges"], arm_summaries=world["arm_summaries"])
    assert exc.value.gate == cm.GATE_SELECTION_IDENTITY


def test_SWAPPING_the_condition_while_keeping_the_rows_is_REFUSED(world):
    """The rows stay. The question changes. Every other hash still checks out — because none of
    them was ABOUT the membership."""
    with pytest.raises(cm.MembershipError) as exc:
        cm.check_view_binding(_view(world, arms=(ARM_S48,)), edges=world["edges"],
                              arm_summaries=world["arm_summaries"])
    assert exc.value.gate == cm.GATE_CANDIDATE_NOT_IN_SELECTION


def test_a_view_binding_a_membership_hash_it_does_not_produce_is_REFUSED(world):
    v = _view(world, candidate_membership_sha256="0" * 64)
    with pytest.raises(cm.MembershipError) as exc:
        cm.check_view_binding(v, edges=world["edges"], arm_summaries=world["arm_summaries"])
    assert exc.value.gate == cm.GATE_MEMBERSHIP_HASH


def test_the_membership_hash_is_DETERMINISTIC_and_moves_when_membership_moves(world):
    a = cm.membership_sha256(world["candidates"], edges=world["edges"],
                             arm_summaries=world["arm_summaries"])
    b = cm.membership_sha256(world["candidates"], edges=world["edges"],
                             arm_summaries=world["arm_summaries"])
    assert a == b == cm.membership_sha256(list(reversed(world["candidates"])),
                                          edges=world["edges"],
                                          arm_summaries=world["arm_summaries"])
    moved = cm.membership_sha256(
        world["candidates"], edges=world["edges"] + [_edge(arm=ARM_OTHER)],
        arm_summaries=world["arm_summaries"] + [_summary(arm=ARM_OTHER)])
    assert moved != a, "the hash must move when the membership does, or it binds nothing"


def test_an_EMPTY_selection_can_display_NOTHING(world):
    with pytest.raises(cm.MembershipError) as exc:
        cm.check_displayed(world["candidates"], selected_arm_keys=[],
                           edges=world["edges"], arm_summaries=world["arm_summaries"])
    assert exc.value.gate == cm.GATE_CANDIDATE_NOT_IN_SELECTION


# --------------------------------------------------------------------------- #
# GENERIC. No program, condition or selection is hard-coded anywhere.
# --------------------------------------------------------------------------- #
def test_the_contract_hardcodes_no_program_or_condition():
    """AST, not grep: a DOCSTRING may name Rest/Stim48hr to EXPLAIN the prefix trap (this module's
    does). Only a literal in executable code would actually hard-code a selection."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(cm))
    # Exclude docstrings by NODE IDENTITY, not by value: ast.get_docstring() returns a CLEANED
    # string that no longer equals the raw Constant, so a value-based exclusion silently keeps the
    # docstring in — and this module's docstring names Rest/Stim48hr precisely to EXPLAIN the
    # prefix trap. (That near-miss is the same shape as everything else this file guards.)
    doc_nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            first = node.body[0] if node.body else None
            if (isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
                    and isinstance(first.value.value, str)):
                doc_nodes.add(id(first.value))
    literals = [n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)
                and id(n) not in doc_nodes]
    names = [n.id for n in ast.walk(tree) if isinstance(n, ast.Name)]

    for token in ("treg", "th1", "rest", "stim48hr", "stim8hr"):
        offending = [x for x in literals + names if token in str(x).lower()]
        assert not offending, (
            f"{token!r} is hard-coded in executable code: {offending[:2]}. The contract must "
            "hold for ANY selection — no program, condition or question is privileged.")


def test_pathway_membership_never_promotes_a_candidate_into_a_question(world):
    """Pathway CONTEXTUALISES a measured edge; it never grants membership. (This asserts the RULE,
    not a count — zero pathway output is a fail-closed state pending W18, not a result.)"""
    assert cm.vocabularies()["pathway_membership_never_promotes_a_candidate_into_a_question"] is True
    ctx = [{"arm_key": ARM_OTHER, "candidate_id": CID}]     # context in an arm it has NO edge in
    truth = cm.derive(CID, edges=world["edges"], arm_summaries=world["arm_summaries"],
                      pathway_context=ctx)
    assert ARM_OTHER not in truth["pathway_context_arm_keys"]
    assert ARM_OTHER not in truth["arm_keys"]
