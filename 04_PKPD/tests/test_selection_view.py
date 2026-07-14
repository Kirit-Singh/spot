"""A scorecard set answers ONE selection question, or it answers none.

The end-to-end audit's finding: Stage 4 materialized every queued candidate in the Stage-3 bundle
and called the result a scorecard set. That is a GLOBAL CANDIDATE DISPLAY — a catalogue of whatever
Stage 3 happened to queue — and it is not the answer to anything.

Why it is a scientific defect and not a UI one: a candidate is queued because it moved SOME arm of
SOME question at SOME analysis condition. Put it beside a candidate selected for a different arm
and a reader compares two numbers that were never comparable. The CNS-MPO was computed identically.
The NEBPI class was derived identically. The two rows still mean different things — and nothing in
the artifact says so, while every hash stays self-consistent.

The attacks below are the two that a green suite would never surface on its own:

  * WITHIN-TIME — a candidate at the SAME analysis condition, on an arm nobody selected. Every
    number about it is real. It simply does not answer this question.
  * CROSS-TIME  — a candidate whose arm was measured at a DIFFERENT analysis condition. The arm
    name can even MATCH. `away_from_A` at StimX and `away_from_A` at Stim48 are not the same arm,
    and a name collision is the easiest way for one to be read as the other.
"""

from __future__ import annotations

import json

import pytest

from analysis.selection_view import (
    SelectionView,
    SelectionViewError,
    in_view,
    assert_not_mixed,
    assert_view_is_current,
    bind_selection_view,
    candidate_arms,
    select,
)
from analysis.stage3_annotation import adapt_annotation_bundle
from test_stage3_handoff_and_integrity import PINNED_ANNOTATION_BUNDLE


def _doc(bundle=PINNED_ANNOTATION_BUNDLE):
    import os
    with open(os.path.join(bundle, "drug_annotation.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _view(**over):
    base = dict(selection_id="sel-1", question_id="q-1", analysis_mode="research_only",
                analysis_condition="StimX", selected_arms=("away_from_A", "toward_B"),
                stage1_contract_sha256="a" * 64)
    base.update(over)
    return SelectionView(**base)


def _candidate(cid="AM:X", **arms):
    row = {"candidate_id": cid, "observed_perturbation_arms": [],
           "inverse_direction_hypothesis_arms": [], "pathway_hypothesis_arms": [],
           "opposed_arms": []}
    row.update(arms)
    return row


# --------------------------------------------------------------- the binding is REAL, not guessed

def test_the_real_bundle_binds_a_selection_view():
    """Every field is read from the contract that exists. Nothing about v2 is invented — W16 has
    not published that shape, and `stage3_v2_seam.py` refuses v2 bundles until it does."""
    view = bind_selection_view(_doc())

    assert view.question_id == "rq_b760ca49d4ab59bc8d2d668efc61e6de"
    assert view.selection_id == "rq_43d32f0d13d6b71b1ec4e078b8955462"
    assert view.analysis_mode == "research_only"
    assert view.analysis_condition == "StimX"
    assert set(view.selected_arms) == {"away_from_A", "toward_B"}
    assert len(view.stage3_selection_view_id) == 16


def test_the_view_id_is_CONTENT_ADDRESSED():
    """Change any bound field and the id moves. That is what makes a STALE binding detectable
    rather than merely wrong — a stale bundle is otherwise perfectly self-consistent."""
    base = _view()
    assert _view().stage3_selection_view_id == base.stage3_selection_view_id

    for changed in (_view(question_id="q-2"), _view(selection_id="sel-2"),
                    _view(analysis_condition="Stim48"), _view(analysis_mode="production"),
                    _view(selected_arms=("away_from_A",))):
        assert changed.stage3_selection_view_id != base.stage3_selection_view_id


def test_admission_admits_the_GLOBAL_universe_and_does_NOT_filter():
    """The architecture correction, as a test.

    Filtering at admission is the obvious fix and it is the WRONG one: it makes the release a
    singleton selection and throws away the reason the store exists. Acquiring a public label is
    the expensive, network-bound part of Stage 4, and it is selection-INDEPENDENT — the same bytes
    answer every selection over the same candidate. Filter here and a second question means a
    second full acquisition of evidence Stage 4 already holds.
    """
    admission = adapt_annotation_bundle(PINNED_ANNOTATION_BUNDLE)

    assert admission.admitted_as_candidates == 7, "the global universe was filtered at admission"
    assert admission.selection_view is not None, "the view must be BOUND (it is just not applied)"
    assert admission.selection_view.analysis_condition == "StimX"


# ------------------------------------------------------------- an unfiltered bundle is REFUSED

def test_a_bundle_that_names_NO_selection_is_refused_as_a_global_display():
    """The audit's finding, as a rule. A release built from this would be a catalogue."""
    doc = _doc()
    doc["upstream"] = {k: v for k, v in doc["upstream"].items()
                       if k not in ("direct_selection_id", "direct_question_id")}

    with pytest.raises(SelectionViewError) as exc:
        bind_selection_view(doc)
    assert exc.value.code == "selection_view_absent"
    assert "global candidate display" in str(exc.value).lower()


def test_a_bundle_that_selects_NO_ARMS_is_refused():
    """A selection that selected nothing is not a selection: every queued candidate would fall
    into the release unfiltered."""
    doc = _doc()
    doc["desired_arms"] = []

    with pytest.raises(SelectionViewError) as exc:
        bind_selection_view(doc)
    assert exc.value.code == "selected_arms_empty"


# --------------------------------------------------------- the bundle must agree with ITSELF

@pytest.mark.parametrize("field,code", [("selection_id", "selection_id_mismatch"),
                                        ("question_id", "question_id_mismatch")])
def test_a_bundle_that_disagrees_with_its_own_stage1_contract_is_REFUSED(field, code):
    """Stage 3 states the selection TWICE — the Direct binding and Stage 1's own contract. That
    redundancy is the only thing that makes a STALE id detectable rather than merely absent: a
    bundle rebuilt against a new selection while carrying an old Direct binding disagrees with
    itself, and self-consistency is exactly what a stale bundle would otherwise have."""
    doc = _doc()
    doc["upstream"]["stage1_selection"][field] = "rq_SOMETHING_ELSE"

    with pytest.raises(SelectionViewError) as exc:
        bind_selection_view(doc)
    assert exc.value.code == code
    assert "disagrees with itself" in str(exc.value)


def test_a_STALE_view_id_is_refused_when_the_run_was_bound_to_another():
    """The evidence was acquired for one question and is being scored against another."""
    view = _view()
    assert_view_is_current(view, view.stage3_selection_view_id)      # the same view: fine
    assert_view_is_current(view, None)                              # nothing bound yet: fine

    with pytest.raises(SelectionViewError) as exc:
        assert_view_is_current(view, "0000000000000000")
    assert exc.value.code == "stale_selection_view_id"


# ------------------------------------------------------- THE ATTACKS: within-time and cross-time

def test_WITHIN_TIME_a_candidate_on_an_UNSELECTED_arm_is_EXCLUDED_from_the_projection():
    """Same analysis condition. Every number about this candidate is real — it simply does not
    answer THIS question, so it is left OUT OF THE PROJECTION and kept IN THE STORE. The next
    selection may be exactly about it, and re-acquiring its evidence would be waste."""
    view = _view()
    inside = _candidate("AM:IN", observed_perturbation_arms=["away_from_A"])
    intruder = _candidate("AM:WITHIN_TIME", observed_perturbation_arms=["toward_A"])

    assert candidate_arms(intruder) == {"toward_A"}
    assert in_view(intruder, view) is False

    proj = select([inside, intruder], view)
    assert proj["candidate_ids"] == ["AM:IN"]
    assert proj["excluded_candidate_ids"] == ["AM:WITHIN_TIME"], (
        "the excluded candidate must be NAMED, not silently vanish")
    assert proj["n_in_store"] == 2 and proj["n_in_view"] == 1


def test_CROSS_TIME_an_arm_with_the_SAME_NAME_at_another_condition_is_a_different_arm():
    """The nastiest one. `away_from_A` at StimX and `away_from_A` at Stim48 are NOT the same arm —
    a name collision is the easiest way for one to be read as the other, and the arm string alone
    cannot tell them apart.

    So the analysis CONDITION is bound into the view id. A release built at StimX and a bundle
    built at Stim48 produce different view ids, and the stale-view gate refuses the mismatch — even
    though every arm name matches perfectly.
    """
    stimx = _view(analysis_condition="StimX")
    stim48 = _view(analysis_condition="Stim48")

    # identical arms, identical question, identical selection...
    assert stimx.selected_arms == stim48.selected_arms
    assert stimx.question_id == stim48.question_id

    # ...and still not the same view.
    assert stimx.stage3_selection_view_id != stim48.stage3_selection_view_id

    with pytest.raises(SelectionViewError) as exc:
        assert_view_is_current(stim48, stimx.stage3_selection_view_id)
    assert exc.value.code == "stale_selection_view_id"
    assert "acquired for one question" in str(exc.value)


def test_a_MIXED_candidate_set_answers_neither_question():
    """One release, one view."""
    with pytest.raises(SelectionViewError) as exc:
        assert_not_mixed([_view(), _view(question_id="q-2")])
    assert exc.value.code == "mixed_candidate_set"
    assert "answers neither" in str(exc.value)

    # one view, many times over, is still one view
    assert assert_not_mixed([_view(), _view()]).question_id == "q-1"


def test_a_candidate_is_in_view_via_ANY_arm_column_never_only_the_obvious_one():
    """A candidate can be placed on an arm by any of four columns. Reading only the obvious one
    would silently narrow the view and drop real candidates."""
    view = _view()
    for col in ("observed_perturbation_arms", "inverse_direction_hypothesis_arms",
                "pathway_hypothesis_arms", "opposed_arms"):
        assert in_view(_candidate("AM:VIA_" + col, **{col: ["toward_B"]}), view) is True

    proj = select([_candidate("A", observed_perturbation_arms=["away_from_A"]),
                   _candidate("B", pathway_hypothesis_arms=["toward_B"])], view)
    assert proj["n_in_view"] == 2


def test_select_is_DETERMINISTIC_and_mutates_nothing():
    """The same store and the same view produce the same projection, byte for byte — and the store
    is untouched, so the next selection sees exactly what this one saw."""
    view = _view()
    store = [_candidate("B", observed_perturbation_arms=["away_from_A"]),
             _candidate("A", pathway_hypothesis_arms=["toward_B"]),
             _candidate("C", observed_perturbation_arms=["toward_A"])]
    before = json.dumps(store, sort_keys=True)

    first, second = select(store, view), select(store, view)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["candidate_ids"] == ["A", "B"], "the projection must be sorted, not arrival-ordered"
    assert json.dumps(store, sort_keys=True) == before, "select() mutated the global store"


# -------------------------------------------------------------- the browser-safe projection

def test_the_projection_says_WHICH_QUESTION_and_never_the_answer():
    """W12 renders this. It carries ids, arms and the view id — no candidate, no score, no rank.
    A projection that leaked a score would let a browser display a ranking Stage 4 refuses to
    emit."""
    doc = _view().as_document()

    assert doc["schema_id"] == "spot.stage04_selection_view.v1"
    assert doc["is_ranking"] is False
    assert doc["question_id"] and doc["selection_id"] and doc["selected_arms"]
    assert "not comparable" in doc["scope_note"]

    # Leaked DATA, not leaked words: the scope note legitimately says the word "candidates" in
    # order to warn about them. What must never appear is a candidate, a score, or a rank.
    keys = set(doc)
    for leaked in ("candidates", "candidate_id", "scorecards", "cns_mpo", "nebpi",
                   "score", "rank", "overall_rank", "p_value"):
        assert leaked not in keys, f"the browser projection carries a {leaked!r} field"

    values = json.dumps([v for k, v in doc.items() if k != "scope_note"]).lower()
    for leaked in ("am:chembl", "cns_mpo", "nebpi", "p_value"):
        assert leaked not in values, f"the browser projection leaks {leaked!r} in a value"
