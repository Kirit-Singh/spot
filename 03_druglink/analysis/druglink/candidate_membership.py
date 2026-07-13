"""A candidate may be DISPLAYED for a question only if it has evidence IN THAT QUESTION'S ARMS.

THE DEFECT THIS CLOSES
----------------------
The Stage-3 store is global and selection-independent, and it must stay that way. But a consumer
could load ANY candidate out of it and render it under ANY selection, because nothing made the
consumer PROVE the candidate has evidence in the arms that selection actually names.

Nothing crashes. Nothing fails a schema. The drug is real, its edges are real, its provenance is
real — and it is being shown as an answer to a question it has no evidence in. That is the worst
kind of wrong this pipeline can produce: not a broken number, but a true fact placed under a false
heading, where every check it passes makes it more convincing.

WHAT IS RE-DERIVED, AND WHAT IS NEVER TRUSTED
---------------------------------------------
A candidate row already PUBLISHES its typed memberships (``arm_keys``,
``observed_perturbation_arm_keys``, ``inverse_direction_hypothesis_arm_keys``,
``pathway_hypothesis_arm_keys``, ``opposed_arm_keys``, ``unresolved_arm_keys``). This module does
NOT read them as evidence. It RE-DERIVES all of them from the rows that actually carry the
evidence — ``target_drug_edges`` and ``arm_summaries``, and for pathway context the matched
``pathway_context`` rows — and then REQUIRES the published lists to equal what it re-derived.

A published list a consumer trusts is a claim. A list re-derived from the evidence is a fact. The
difference is the whole point: a candidate whose published `arm_keys` were widened by one entry
would otherwise be displayable under a question it never touched.

EXACT STRING EQUALITY. NOTHING ELSE.
------------------------------------
An arm key is ``lane|program_id|desired_change|context``. Membership is decided by EXACT equality
on the WHOLE key.

  * NEVER a prefix match — the same program and the same direction at two different times differ
    ONLY in the context tail. A prefix match silently equates them, and the user is shown a drug
    from Rest under a question about Stim48hr.
  * NEVER a display name — two arms can share a label and be different arms. The full key is the
    identity; a name is not a binding.
  * NEVER an inferred/normalised key — if the two strings differ, they are two arms.

PATHWAY. Pathway context arms are matched EXACTLY like gene arms, and pathway membership never
promotes a candidate into a question: it is context on a MEASURED edge. Zero pathway output is a
FAIL-CLOSED STATE pending W18, not a result — no count in this module encodes an expectation of it.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from . import workflow as wf
from .hashing import canonical_json, content_hash

MEMBERSHIP_SCHEMA = "spot.stage03_candidate_membership.v1"
MEMBERSHIP_RULE_ID = "spot.stage03.candidate_membership.exact_arm_key.v1"

# The typed membership lists a candidate row publishes, and the evidence state each is derived
# from. Names are the EXISTING v2 ones — the stale v1 `*_arms` names are NOT revived.
MEMBERSHIP_FOR_STATE: dict[str, str] = {
    "observed_perturbation_arm_keys": wf.OBSERVED_PERTURBATION,
    "inverse_direction_hypothesis_arm_keys": wf.INVERSE_DIRECTION_HYPOTHESIS,
    "pathway_hypothesis_arm_keys": wf.PATHWAY_HYPOTHESIS,
    "opposed_arm_keys": wf.OPPOSED,
    "unresolved_arm_keys": wf.UNRESOLVED,
}
TYPED_MEMBERSHIP_FIELDS: tuple[str, ...] = tuple(sorted(MEMBERSHIP_FOR_STATE))
ALL_MEMBERSHIP_FIELDS: tuple[str, ...] = ("arm_keys",) + TYPED_MEMBERSHIP_FIELDS

GATE_MEMBERSHIP_NOT_REDERIVED = \
    "a_candidates_published_arm_membership_is_not_what_the_evidence_produces"
GATE_CANDIDATE_NOT_IN_SELECTION = \
    "a_candidate_is_displayed_for_a_selection_it_has_no_evidence_in"
GATE_FOREIGN_ARM = "a_displayed_candidate_carries_an_arm_the_selection_does_not_name"
GATE_ARM_DROPPED = "a_displayed_candidate_lost_an_arm_the_evidence_gives_it"
GATE_SELECTION_IDENTITY = "the_view_does_not_carry_the_selection_identity_it_claims"
GATE_NOT_EXACT_KEY = "an_arm_key_was_matched_by_something_other_than_exact_string_equality"
GATE_MEMBERSHIP_HASH = "the_candidate_membership_projection_is_not_the_one_the_view_binds"


class MembershipError(ValueError):
    """The candidate/selection membership contract is not satisfied. Refuse; never repair."""

    def __init__(self, gate: str, message: str) -> None:
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


def _refuse(gate: str, message: str) -> None:
    raise MembershipError(gate, message)


# --------------------------------------------------------------------------- #
# 1. RE-DERIVE. The evidence rows decide; the candidate's own claim is checked against them.
# --------------------------------------------------------------------------- #
def derive(candidate_id: str, *, edges: Sequence[Mapping[str, Any]],
           arm_summaries: Sequence[Mapping[str, Any]],
           pathway_context: Sequence[Mapping[str, Any]] = ()) -> dict[str, list[str]]:
    """Every typed arm membership this candidate's EVIDENCE gives it. Nothing is read from the
    candidate row — that row is the thing being checked."""
    cid = str(candidate_id)
    mine_edges = [e for e in edges if str(e.get("candidate_id")) == cid]
    mine_summaries = [s for s in arm_summaries if str(s.get("candidate_id")) == cid]

    out: dict[str, list[str]] = {
        # every arm any edge of this candidate came from
        "arm_keys": sorted({str(e["arm_key"]) for e in mine_edges}),
    }
    for field, state in sorted(MEMBERSHIP_FOR_STATE.items()):
        out[field] = sorted({str(s["arm_key"]) for s in mine_summaries
                             if str(s.get("arm_evidence_state")) == state})

    # PATHWAY CONTEXT: matched by EXACT arm key, and it contextualises — it never grants a
    # candidate membership of a question. A pathway context row whose arm the candidate has no
    # measured edge in adds nothing here, deliberately.
    measured = set(out["arm_keys"])
    out["pathway_context_arm_keys"] = sorted(
        {str(p["arm_key"]) for p in pathway_context
         if str(p.get("arm_key")) in measured})
    return out


def check_published_membership(candidate: Mapping[str, Any], *,
                               edges: Sequence[Mapping[str, Any]],
                               arm_summaries: Sequence[Mapping[str, Any]],
                               pathway_context: Sequence[Mapping[str, Any]] = ()) -> None:
    """The candidate's PUBLISHED lists must equal what the evidence produces.

    A widened list is how a candidate becomes displayable under a question it never touched; a
    narrowed one is how real evidence disappears from a question it belongs to. Both are silent.
    """
    cid = str(candidate.get("candidate_id"))
    truth = derive(cid, edges=edges, arm_summaries=arm_summaries,
                   pathway_context=pathway_context)
    for field in ALL_MEMBERSHIP_FIELDS:
        published = sorted(str(k) for k in (candidate.get(field) or []))
        if published != truth[field]:
            extra = sorted(set(published) - set(truth[field]))
            missing = sorted(set(truth[field]) - set(published))
            _refuse(GATE_MEMBERSHIP_NOT_REDERIVED,
                    f"candidate {cid!r}: {field} publishes {published!r}, but its evidence "
                    f"produces {truth[field]!r} (extra={extra!r}, missing={missing!r}). A "
                    "published list a consumer trusts is a CLAIM; a list re-derived from the "
                    "rows that carry the evidence is a FACT.")


# --------------------------------------------------------------------------- #
# 2. THE PROJECTION. Canonical, hashable, and bound to the view.
# --------------------------------------------------------------------------- #
def projection(candidates: Sequence[Mapping[str, Any]], *,
               edges: Sequence[Mapping[str, Any]],
               arm_summaries: Sequence[Mapping[str, Any]],
               pathway_context: Sequence[Mapping[str, Any]] = ()) -> dict[str, Any]:
    """The canonical candidate->arm membership map, re-derived. Deterministic and order-free."""
    by_candidate = {
        str(c["candidate_id"]): derive(str(c["candidate_id"]), edges=edges,
                                       arm_summaries=arm_summaries,
                                       pathway_context=pathway_context)
        for c in candidates}
    doc = {
        "schema_version": MEMBERSHIP_SCHEMA,
        "rule_id": MEMBERSHIP_RULE_ID,
        "match_rule": "exact_string_equality_on_the_whole_arm_key",
        "membership_is_evidence_not_a_claim": True,
        "by_candidate": {k: by_candidate[k] for k in sorted(by_candidate)},
    }
    doc["membership_sha256"] = content_hash(doc)
    return doc


def membership_sha256(candidates: Sequence[Mapping[str, Any]], *,
                      edges: Sequence[Mapping[str, Any]],
                      arm_summaries: Sequence[Mapping[str, Any]],
                      pathway_context: Sequence[Mapping[str, Any]] = ()) -> str:
    return projection(candidates, edges=edges, arm_summaries=arm_summaries,
                      pathway_context=pathway_context)["membership_sha256"]


# --------------------------------------------------------------------------- #
# 3. THE FILTER RULE. What a consumer may display, and what it may not.
# --------------------------------------------------------------------------- #
def _exact(keys: Iterable[str]) -> frozenset[str]:
    return frozenset(str(k) for k in keys)


def displayable(candidate: Mapping[str, Any], *, selected_arm_keys: Iterable[str],
                edges: Sequence[Mapping[str, Any]],
                arm_summaries: Sequence[Mapping[str, Any]],
                pathway_context: Sequence[Mapping[str, Any]] = ()) -> bool:
    """May this candidate be shown for a selection naming EXACTLY these arm keys?

    Only if its RE-DERIVED arms intersect them, by exact string equality on the whole key.
    """
    truth = derive(str(candidate.get("candidate_id")), edges=edges,
                   arm_summaries=arm_summaries, pathway_context=pathway_context)
    return bool(_exact(truth["arm_keys"]) & _exact(selected_arm_keys))


def check_displayed(candidates: Sequence[Mapping[str, Any]], *,
                    selected_arm_keys: Iterable[str],
                    edges: Sequence[Mapping[str, Any]],
                    arm_summaries: Sequence[Mapping[str, Any]],
                    pathway_context: Sequence[Mapping[str, Any]] = ()) -> None:
    """Every displayed candidate has evidence in the selection's OWN arms — and only those."""
    selected = _exact(selected_arm_keys)
    if not selected:
        _refuse(GATE_CANDIDATE_NOT_IN_SELECTION,
                "the selection names no arm keys, so no candidate can be shown to have evidence "
                "in it. Displaying anything here would be displaying it under no question at all")

    for cand in candidates:
        cid = str(cand.get("candidate_id"))
        truth = derive(cid, edges=edges, arm_summaries=arm_summaries,
                       pathway_context=pathway_context)
        mine = _exact(truth["arm_keys"])

        if not (mine & selected):
            _refuse(GATE_CANDIDATE_NOT_IN_SELECTION,
                    f"candidate {cid!r} is displayed for a selection naming "
                    f"{sorted(selected)!r}, but its evidence lives in {sorted(mine)!r}. The drug "
                    "is real and its edges are real — and it is being shown as an answer to a "
                    "question it has no evidence in.")

        shown = _exact(cand.get("view_arm_keys") or truth["arm_keys"])
        foreign = shown - selected
        if foreign:
            _refuse(GATE_FOREIGN_ARM,
                    f"candidate {cid!r} is shown carrying arm(s) {sorted(foreign)!r} that this "
                    f"selection does not name. Exact keys only: a prefix or a display name would "
                    "equate two arms that differ only in their context tail.")

        dropped = (mine & selected) - shown
        if dropped:
            _refuse(GATE_ARM_DROPPED,
                    f"candidate {cid!r} is shown without arm(s) {sorted(dropped)!r} that its own "
                    "evidence gives it in this selection. A dropped arm is indistinguishable "
                    "from evidence nobody found.")


# --------------------------------------------------------------------------- #
# 4. THE VIEW BINDS ITS QUESTION, AND THE MEMBERSHIP OF WHAT IT SHOWS.
# --------------------------------------------------------------------------- #
REQUIRED_VIEW_IDENTITY: tuple[str, ...] = (
    "selection_id", "question_id", "analysis_mode",
)


def check_view_binding(view: Mapping[str, Any], *,
                       edges: Sequence[Mapping[str, Any]],
                       arm_summaries: Sequence[Mapping[str, Any]],
                       pathway_context: Sequence[Mapping[str, Any]] = ()) -> None:
    """The view names its question, names the arms, and binds the membership of what it shows.

    A view that swapped its condition or its view hash while keeping the same candidate rows would
    otherwise render one question's drugs under another question's heading, and every hash it
    published would still check out — because none of them was ABOUT the membership.
    """
    selection = view.get("selection") or {}
    for field in REQUIRED_VIEW_IDENTITY:
        if not selection.get(field):
            _refuse(GATE_SELECTION_IDENTITY,
                    f"the view carries no {field}. A view that cannot name its own question "
                    "cannot be checked against one")

    arms = view.get("selected_arms") or {}
    keys = arms.get("all_arm_keys") or arms.get("arm_keys") or []
    if not keys:
        _refuse(GATE_SELECTION_IDENTITY,
                "the view names no selected arm keys, so nothing it shows can be proved to "
                "belong to it")

    tables = view.get("tables") or {}
    shown = tables.get("candidates") or []
    check_displayed(shown, selected_arm_keys=keys, edges=edges,
                    arm_summaries=arm_summaries, pathway_context=pathway_context)

    claimed = view.get("candidate_membership_sha256")
    if claimed is not None:
        actual = membership_sha256(shown, edges=edges, arm_summaries=arm_summaries,
                                   pathway_context=pathway_context)
        if claimed != actual:
            _refuse(GATE_MEMBERSHIP_HASH,
                    f"the view binds candidate_membership_sha256={str(claimed)[:16]}…, but the "
                    f"membership its own rows produce hashes to {actual[:16]}…. A hash you copy "
                    "is not a hash you checked.")


def vocabularies() -> dict[str, Any]:
    """Published, because Stage 4 and the UI read FIELDS, not source."""
    return {
        "membership_schema": MEMBERSHIP_SCHEMA,
        "membership_rule_id": MEMBERSHIP_RULE_ID,
        "typed_membership_fields": list(TYPED_MEMBERSHIP_FIELDS),
        "match_rule": "exact_string_equality_on_the_whole_arm_key",
        "prefix_match_permitted": False,
        "display_name_match_permitted": False,
        "membership_is_rederived_from_evidence_never_read_from_the_candidate": True,
        "pathway_membership_never_promotes_a_candidate_into_a_question": True,
        "global_store_stays_global_display_is_a_projection": True,
    }


def canonical(doc: Mapping[str, Any]) -> str:
    return canonical_json(doc)
