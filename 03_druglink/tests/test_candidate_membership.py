"""A true fact under a false heading is the worst thing this pipeline can emit.

The store is global and selection-independent, and must stay so. But nothing forced a consumer to
PROVE that a candidate it loaded has evidence in the arms the active selection names. A real drug,
with real edges and real provenance, could be rendered as the answer to a question it has nothing to
do with — passing the schema, the columns and the seal on the way.

THESE TESTS RUN AGAINST THE REAL PUBLISHED VIEW, not a shape I imagined. The first version of this
contract was written against fields I ASSUMED (`all_arm_keys`, `view_arm_keys`) and was dangerously
wrong: it fell back to the candidate\'s GLOBAL `arm_keys` (180 arms in the published fixture, against
2 shown), so every reusable candidate looked like it carried 178 foreign arms. A check that fires on
every honest input is not a check; it is an outage. `test_the_published_view_is_ADMITTED` is the
guard against that, and it is the first test in the file for a reason.

NO PATHWAY COUNT IS PINNED. Zero pathway output is a fail-closed state pending W18, not a result.
"""
from __future__ import annotations

import copy
import json
import os

import pytest

from druglink import candidate_membership as cm
from druglink import view_contract as vc

FIXTURE = os.path.join(os.path.dirname(__file__), "..", "selection_view.fixture.v1.json")


@pytest.fixture(scope="module")
def view():
    with open(FIXTURE, encoding="utf-8") as fh:
        return json.load(fh)


def _cands(v):
    return v["tables"]["candidates"]


# --------------------------------------------------------------------------- #
# THE HONEST WORLD. If this fails, every refusal below is vacuous.
# --------------------------------------------------------------------------- #
def test_the_published_view_is_ADMITTED(view):
    """The real artifact must pass. My first version rejected it on every candidate."""
    cm.check_view_membership(view)


def test_the_full_view_contract_still_admits_it(view):
    """The membership check is INTEGRATED into view_contract.validate — not a parallel checker."""
    vc.validate(copy.deepcopy(view))


def test_non_vacuity(view):
    assert _cands(view), "no candidates: every assertion below would prove nothing"
    assert cm.selected_gene_arm_keys(view["selected_arms"])


# --------------------------------------------------------------------------- #
# THE REAL SHAPES. Global membership is NOT the view\'s membership.
# --------------------------------------------------------------------------- #
def test_global_arm_keys_are_NOT_the_views_arm_keys(view):
    """The trap that made the first version reject everything."""
    c = _cands(view)[0]
    glob = cm.global_arm_keys(c)
    shown = cm.shown_arm_keys(c)
    assert len(glob) > len(shown), (
        "the published fixture must have a candidate whose GLOBAL membership exceeds what this "
        "view shows — otherwise the trap this test guards is not even expressible here")
    assert shown < glob


def test_shown_equals_global_INTERSECT_selected(view):
    """The invariant, verified against the real artifact."""
    selected = cm.selected_gene_arm_keys(view["selected_arms"])
    for c in _cands(view):
        assert cm.shown_arm_keys(c) == (cm.global_arm_keys(c) & selected)


def test_a_candidate_shared_across_selections_is_NOT_falsely_rejected(view):
    """A candidate with evidence in 180 arms shown under a 2-arm question is the NORMAL case. The
    store exists to be reused; a contract that rejected it would be an outage."""
    c = _cands(view)[0]
    assert len(cm.global_arm_keys(c)) > len(cm.selected_gene_arm_keys(view["selected_arms"]))
    cm.check_view_membership(view)          # must NOT raise


# --------------------------------------------------------------------------- #
# THE ATTACKS. Each must fail at a NAMED gate.
# --------------------------------------------------------------------------- #
def test_a_FOREIGN_arm_added_to_a_shown_candidate_is_REFUSED(view):
    bad = copy.deepcopy(view)
    c = _cands(bad)[0]
    origin = sorted(c["view_arm_keys_by_origin"])[0]
    c["view_arm_keys_by_origin"][origin] = (
        list(c["view_arm_keys_by_origin"][origin]) + ["direct|NOT_IN_THIS_QUESTION|increase|Rest"])
    with pytest.raises(cm.MembershipError) as exc:
        cm.check_view_membership(bad)
    assert exc.value.gate == cm.GATE_FOREIGN_ARM


def test_DROPPING_an_arm_the_selection_gives_it_is_REFUSED(view):
    bad = copy.deepcopy(view)
    c = _cands(bad)[0]
    for origin, keys in c["view_arm_keys_by_origin"].items():
        if keys:
            c["view_arm_keys_by_origin"][origin] = keys[:-1]
            break
    with pytest.raises(cm.MembershipError) as exc:
        cm.check_view_membership(bad)
    assert exc.value.gate == cm.GATE_ARM_DROPPED


def test_a_candidate_with_NO_evidence_in_the_selection_is_REFUSED(view):
    """The core defect: a real drug shown under a question it has no evidence in."""
    bad = copy.deepcopy(view)
    cid = _cands(bad)[0]["candidate_id"]
    # DELETE THE EVIDENCE, not the claim. The gate re-derives from the view's own rows, so editing
    # the candidate's self-description proves nothing — this is the probe that defeated the
    # previous version of this gate, and it must now fail closed.
    for table in ("target_drug_edges", "arm_summaries"):
        bad["tables"][table] = [r for r in bad["tables"][table]
                                if r.get("candidate_id") != cid]
    with pytest.raises(cm.MembershipError) as exc:
        cm.check_view_membership(bad)
    assert exc.value.gate == cm.GATE_CANDIDATE_NOT_IN_SELECTION


def test_SWAPPING_the_selections_condition_while_keeping_the_rows_is_REFUSED(view):
    """The rows stay; the question changes. Every other hash still checks out — because none of
    them was ABOUT the membership."""
    bad = copy.deepcopy(view)
    bad["selected_arms"]["gene_arm_keys"] = [
        k.replace("Rest", "Stim8hr") for k in bad["selected_arms"]["gene_arm_keys"]]
    with pytest.raises(cm.MembershipError) as exc:
        cm.check_view_membership(bad)
    assert exc.value.gate in (cm.GATE_CANDIDATE_NOT_IN_SELECTION, cm.GATE_FOREIGN_ARM)


def test_a_view_naming_NO_selected_arms_can_show_NOTHING(view):
    bad = copy.deepcopy(view)
    bad["selected_arms"]["gene_arm_keys"] = []
    with pytest.raises(cm.MembershipError) as exc:
        cm.check_view_membership(bad)
    assert exc.value.gate == cm.GATE_NO_SELECTED_ARMS


def test_a_PREFIX_match_cannot_make_a_candidate_displayable(view):
    """Two arms differing ONLY in the context tail must never be equated."""
    sel = sorted(cm.selected_gene_arm_keys(view["selected_arms"]))[0]
    stem = sel.rsplit("|", 1)[0]
    other = stem + "|A_DIFFERENT_CONTEXT"
    assert other.startswith(stem)                      # they really do share a prefix
    fake = {"candidate_id": "AM:X", "arm_keys": [other],
            "view_arm_keys_by_origin": {"direct_target": [other]}}
    assert cm.displayable(fake, selected_arms=view["selected_arms"]) is False


# --------------------------------------------------------------------------- #
# The rule is PUBLISHED, and it is GENERIC.
# --------------------------------------------------------------------------- #
def test_the_rule_is_published_with_the_REAL_field_names():
    v = cm.vocabularies()
    assert v["selected_arms_field"] == "gene_arm_keys"
    assert v["shown_arms_field"] == "view_arm_keys_by_origin"
    assert v["global_arms_field"] == "arm_keys"
    assert v["match_rule"] == "exact_string_equality_on_the_whole_arm_key"
    assert v["prefix_match_permitted"] is False
    assert v["shown_equals_global_intersect_selected"] is True


def test_the_contract_hardcodes_no_program_or_condition():
    """AST, not grep: a DOCSTRING may name Rest/Stim48hr to EXPLAIN the prefix trap. Only a literal
    in executable code would actually hard-code a selection. Docstrings are excluded by NODE
    IDENTITY — ast.get_docstring() returns a CLEANED string that no longer equals the raw constant,
    so a value-based exclusion silently keeps the docstring in (my first version failed on exactly
    that)."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(cm))
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
            f"{token!r} is hard-coded in executable code: {offending[:2]}. The contract must hold "
            "for ANY selection — no program, condition or question is privileged.")


def test_pathway_context_never_promotes_a_candidate_into_a_question():
    """Pathway CONTEXTUALISES a measured edge; it never grants membership. Asserts the RULE, not a
    count — zero pathway output is a fail-closed state pending W18, not a result."""
    assert cm.vocabularies()["pathway_context_never_promotes_a_candidate_into_a_question"] is True
    ctx = [{"arm_key": "pathway|P|increase|Rest|GO-BP", "candidate_id": "AM:X"}]
    truth = cm.derive("AM:X",
                      edges=[{"candidate_id": "AM:X", "arm_key": "direct|P|increase|Rest"}],
                      arm_summaries=[], pathway_context=ctx)
    assert "pathway|P|increase|Rest|GO-BP" not in truth["arm_keys"]
    assert truth["pathway_context_arm_keys"] == []
