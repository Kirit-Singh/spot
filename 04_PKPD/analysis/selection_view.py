"""A scorecard set answers ONE selection question, or it answers none.

The end-to-end audit's finding: Stage 4 materialized every queued candidate in the Stage-3 bundle
and called the result a scorecard set. That is a **global candidate display** — a catalogue of
whatever Stage 3 happened to queue — and it is not the answer to anything.

The difference matters scientifically, not just administratively. A candidate is queued because it
moved SOME arm of SOME question at SOME analysis condition. Display it beside a candidate selected
for a different arm, and a reader compares two numbers that were never comparable: the CNS-MPO is
computed identically, the NEBPI class is derived identically, and the two rows still mean different
things. Nothing in the artifact would say so, and every hash would be self-consistent.

THE ARCHITECTURE — and I got this wrong on the first pass, so it is worth stating precisely.

Filtering at ADMISSION is the obvious fix and it is the wrong one. It makes the release a singleton
selection and throws away the reason the store exists: acquiring a public label and a PubChem record
is the expensive, network-bound part of Stage 4, and it is **selection-independent**. The same bytes
answer every selection over the same candidate. Filter at admission and a second question means a
second full acquisition of evidence Stage 4 already holds.

So:

  * the STORE is GLOBAL — the whole admitted Stage-3 candidate universe, acquired once, reusable;
  * SELECTION IS A PROJECTION — `select()` below is a deterministic function of (the store, a
    verified active selection, Stage-3 arm membership) -> the relevant scorecards;
  * candidate -> arm provenance is PRESERVED on every candidate, so a browser can filter ANY
    selection without a rerun;
  * the global release and `current.json` are NOT a singleton selection.

The selection view itself:

    selection_id · question_id · analysis_mode · analysis_condition · the exact selected arms

None of this is invented. Stage 3's bundle already states all of it (`upstream.direct_selection_id`,
`upstream.direct_question_id`, `upstream.direct_lane`, `upstream.direct_analysis_condition`,
`desired_arms`), and it states it TWICE — once in the Direct binding and once in
`upstream.stage1_selection`, which is what makes a stale id detectable rather than merely absent.
Stage 4 checks the two against each other and refuses when they disagree.

WHAT IS REFUSED, each by name:

    selection_view_absent          a bundle that names no selection: an unfiltered global set
    selected_arms_empty            a selection that selected nothing is not a selection
    selection_id_mismatch          the Direct binding and Stage 1's contract name different runs
    question_id_mismatch           ...the same, for the question
    mixed_candidate_set            two views projected into one table: it answers neither
    stale_selection_view_id        the run was bound to a view this bundle is not

**v2 is NOT guessed.** W16 has not published the v2 selection-view shape. `stage3_v2_seam.py`
refuses every v2 bundle, and the exact v2 field names must be coordinated before this binding is
extended. What is here is read from the v1 contract that exists.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from .firewall import Rejection

SELECTION_VIEW_SCHEMA = "spot.stage04_selection_view.v1"
SELECTION_PROJECTION_SCHEMA = "spot.stage04_selection_projection.v1"

# Every candidate column that can place a candidate on an arm. A candidate is IN the view when any
# of these intersects the selected arms — and the columns are enumerated rather than guessed,
# because a column added later that nobody added here would silently widen the view.
ARM_COLUMNS = (
    "observed_perturbation_arms",
    "inverse_direction_hypothesis_arms",
    "pathway_hypothesis_arms",
    "opposed_arms",
)


class SelectionViewError(Rejection):
    """The release cannot say which question it answers, or answers more than one."""


@dataclass(frozen=True)
class SelectionView:
    """The one question this scorecard set answers, and the exact arms it answers it for."""

    selection_id: str
    question_id: str
    analysis_mode: str            # Stage 2's lane: research_only | production | ...
    analysis_condition: str       # the analysis condition the arms were measured at
    selected_arms: tuple[str, ...]
    stage1_contract_sha256: Optional[str]

    @property
    def stage3_selection_view_id(self) -> str:
        """Content-addressed. Change any bound field and the id moves — which is what makes a
        stale binding detectable instead of merely wrong."""
        payload = json.dumps({
            "schema": SELECTION_VIEW_SCHEMA,
            "selection_id": self.selection_id,
            "question_id": self.question_id,
            "analysis_mode": self.analysis_mode,
            "analysis_condition": self.analysis_condition,
            "selected_arms": sorted(self.selected_arms),
            "stage1_contract_sha256": self.stage1_contract_sha256,
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    def as_document(self) -> dict[str, Any]:
        """Browser-safe projection: ids, arms and the view id. No candidate, no score, no rank —
        this says WHICH QUESTION was asked, never what the answer was."""
        return {
            "schema_id": SELECTION_VIEW_SCHEMA,
            "stage3_selection_view_id": self.stage3_selection_view_id,
            "selection_id": self.selection_id,
            "question_id": self.question_id,
            "analysis_mode": self.analysis_mode,
            "analysis_condition": self.analysis_condition,
            "selected_arms": sorted(self.selected_arms),
            "stage1_contract_sha256": self.stage1_contract_sha256,
            "scope_note": (
                "This scorecard set answers exactly this selection. Candidates outside these arms "
                "are not in it, and are not comparable to the ones that are."
            ),
            "is_ranking": False,
        }


def bind_selection_view(doc: dict[str, Any]) -> SelectionView:
    """Read the selection this bundle was produced for. Refuse an unfiltered or inconsistent one."""
    upstream = doc.get("upstream") or {}
    selection_id = upstream.get("direct_selection_id")
    question_id = upstream.get("direct_question_id")
    arms = tuple(doc.get("desired_arms") or ())

    if not selection_id or not question_id:
        raise SelectionViewError(
            "selection_view_absent",
            "this Stage-3 bundle names no selection (`upstream.direct_selection_id` / "
            "`direct_question_id`), so a Stage-4 release built from it would be a GLOBAL candidate "
            "display — a catalogue of whatever Stage 3 queued — and not the answer to any "
            "question. Candidates selected for different questions are not comparable, and "
            "nothing in the artifact would say so.",
        )

    if not arms:
        raise SelectionViewError(
            "selected_arms_empty",
            "the bundle selects no arms (`desired_arms` is empty). A selection that selected "
            "nothing is not a selection, and every queued candidate would fall into the release "
            "unfiltered.",
        )

    # Stage 3 states the selection TWICE — the Direct binding and Stage 1's own contract. That
    # redundancy is the only thing that makes a STALE id detectable rather than merely absent: a
    # bundle rebuilt against a new selection while carrying an old Direct binding disagrees with
    # itself, and self-consistency is exactly what a stale bundle would otherwise have.
    stage1 = upstream.get("stage1_selection") or {}
    s1_selection, s1_question = stage1.get("selection_id"), stage1.get("question_id")

    if s1_selection and s1_selection != selection_id:
        raise SelectionViewError(
            "selection_id_mismatch",
            f"the Direct binding names selection {selection_id!r} and Stage 1's contract names "
            f"{s1_selection!r}. The bundle disagrees with itself about which selection it answers, "
            "so one of the two is stale and Stage 4 cannot tell which.",
        )
    if s1_question and s1_question != question_id:
        raise SelectionViewError(
            "question_id_mismatch",
            f"the Direct binding names question {question_id!r} and Stage 1's contract names "
            f"{s1_question!r}. The bundle disagrees with itself about which question it answers.",
        )

    return SelectionView(
        selection_id=str(selection_id),
        question_id=str(question_id),
        analysis_mode=str(upstream.get("direct_lane") or "unstated"),
        analysis_condition=str(upstream.get("direct_analysis_condition") or "unstated"),
        selected_arms=arms,
        stage1_contract_sha256=stage1.get("contract_sha256"),
    )


def candidate_arms(row: dict[str, Any]) -> set[str]:
    """Every arm this candidate is placed on, from the columns that can place it on one."""
    out: set[str] = set()
    for col in ARM_COLUMNS:
        value = row.get(col) or []
        if isinstance(value, str):
            value = [value]
        out |= {str(a) for a in value if a}
    return out


def in_view(row: dict[str, Any], view: SelectionView) -> bool:
    """Is this candidate on one of the selected arms? A pure predicate — it refuses nothing.

    A candidate OUTSIDE the view is not an error. It is a real candidate, honestly acquired, that
    simply does not answer THIS question. It stays in the global store — the next selection may be
    exactly about it — and it is left out of this projection.
    """
    return bool(candidate_arms(row) & set(view.selected_arms))


def select(rows: Iterable[dict[str, Any]], view: SelectionView) -> dict[str, Any]:
    """THE deterministic selection-view function: (global store, verified selection) -> projection.

    Returns the candidates that answer this question, the ones that do not, and the view they were
    judged against — so the exclusion is auditable rather than invisible. Nothing is mutated and
    nothing is dropped: the store is unchanged and remains reusable for the next selection.

    Deterministic: sorted by candidate_id, so the same store and the same view always produce the
    same projection, byte for byte.
    """
    rows = list(rows)
    included = sorted((r for r in rows if in_view(r, view)),
                      key=lambda r: str(r.get("candidate_id")))
    excluded = sorted((r for r in rows if not in_view(r, view)),
                      key=lambda r: str(r.get("candidate_id")))

    return {
        "schema_id": SELECTION_PROJECTION_SCHEMA,
        "selection_view": view.as_document(),
        "candidate_ids": [str(r.get("candidate_id")) for r in included],
        "included": included,
        # Named, not hidden. A candidate Stage 3 queued and this projection left out is a fact a
        # reader may need — and an empty `included` with a full `excluded` is the signature of a
        # selection nobody's candidates answer, which is a finding, not an empty page.
        "excluded_candidate_ids": [str(r.get("candidate_id")) for r in excluded],
        "n_in_store": len(rows),
        "n_in_view": len(included),
    }


def assert_not_mixed(views: Iterable[SelectionView]) -> SelectionView:
    """One release, one view. A scorecard set assembled from two selections answers neither."""
    distinct = {v.stage3_selection_view_id: v for v in views}
    if not distinct:
        raise SelectionViewError(
            "selection_view_absent",
            "no selection view was bound; a release cannot say which question it answers.")
    if len(distinct) > 1:
        raise SelectionViewError(
            "mixed_candidate_set",
            f"this release binds {len(distinct)} selection views "
            f"({sorted(distinct)}). A scorecard set assembled from two selections answers "
            "neither, and a reader comparing across them is comparing candidates that were never "
            "selected for the same question.",
        )
    return next(iter(distinct.values()))


def assert_view_is_current(view: SelectionView, expected_view_id: Optional[str]) -> None:
    """The run was bound to a view. This bundle must BE that view."""
    if expected_view_id is None or expected_view_id == view.stage3_selection_view_id:
        return
    raise SelectionViewError(
        "stale_selection_view_id",
        f"this run was bound to selection view {expected_view_id!r}, and the bundle presents "
        f"{view.stage3_selection_view_id!r}. The upstream selection moved after the run was "
        "bound: the evidence was acquired for one question and is being scored against another.",
    )
