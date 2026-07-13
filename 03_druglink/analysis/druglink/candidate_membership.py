"""A candidate may be SHOWN for a question only if its evidence lives in that question's arms.

THE DEFECT. The Stage-3 store is global and selection-independent, and must stay so. But nothing
forced a consumer to PROVE that a candidate it loaded has evidence in the arms the active selection
actually names. A real drug — real edges, real provenance, every hash checking out — could be
rendered as the answer to a question it has no evidence in. Nothing crashes, nothing fails a schema:
a TRUE FACT UNDER A FALSE HEADING, where every check it passes makes it more convincing.

THE REAL FIELDS. This module was first written against fields I assumed and it was dangerously
wrong — the audit caught it. The shapes below are the ones the v2 view actually publishes, read off
a real artifact, not inferred:

  selected_arms.gene_arm_keys              list[str]                 the gene arms the question names
  selected_arms.pathway_context_arm_keys   {role: list[str]}         pathway CONTEXT arms, per role
  candidate.arm_keys                       list[str]  GLOBAL         every arm the candidate has an
                                                                     edge in, across the whole store
  candidate.view_arm_keys_by_origin        {origin: list[str]}       the arms THIS VIEW shows it in

`arm_keys` is GLOBAL — in the published fixture it holds 180 arms while the view shows 2. Reading it
as the view's arms (as my first version did, by falling back to it) makes every candidate look like
it carries 178 foreign arms, and REJECTS EXACTLY THE CANDIDATES THE STORE EXISTS TO REUSE. A check
that fires on every honest input is not a check; it is an outage.

THE INVARIANT, verified against the published view:

    flatten(view_arm_keys_by_origin)  ==  arm_keys  ∩  selected gene arms

It is decidable from the VIEW ALONE, which is what a static browser has. The producer/verifier side
additionally RE-DERIVES the membership from the rows that carry the evidence (`target_drug_edges`,
`arm_summaries`, and exactly-matched `pathway_context`) and requires the published lists to equal it:
a published list a consumer trusts is a CLAIM; a list re-derived from the evidence is a FACT.

EXACT STRING EQUALITY on the WHOLE arm key. Never a prefix — `direct|X|decrease|Rest` and
`…|Stim48hr` differ ONLY in the context tail, and a prefix match shows a drug from one condition
under a question about another. Never a display name — two arms can share a label; the full key is
the identity, and a name is not a binding.

PATHWAY CONTEXTUALISES, IT NEVER PROMOTES. A pathway context arm never grants a candidate membership
of a question. Zero pathway output is a FAIL-CLOSED STATE pending W18 — not a result — and no count
here encodes an expectation of it.
"""
from __future__ import annotations

import json
from typing import Any, Iterable, Mapping, Sequence

from . import direction as dr
from . import workflow as wf

# v2, NOT v1. The rule changed MATERIALLY — from comparing the candidate's claims against each
# other, to RE-DERIVING membership from target_drug_edges; plus a typed pathway-context domain,
# typed evidence-state columns, bidirectional edge<->summary reconciliation, and ordered roles and
# endpoints. A v1 id on v2 semantics would let a receipt for the old, weaker rule pass for the new
# one — which is precisely how a weakened gate travels under a trusted name.
MEMBERSHIP_SCHEMA = "spot.stage03_candidate_membership.v2"
MEMBERSHIP_RULE_ID = "spot.stage03.candidate_membership.evidence_rederived.v2"
MEMBERSHIP_VERIFIER_ID = "spot.stage03.candidate_membership.verifier.v2"
RETIRED_MEMBERSHIP_IDS = frozenset({
    "spot.stage03_candidate_membership.v1",
    "spot.stage03.candidate_membership.exact_arm_key.v1",
    "spot.stage03.candidate_membership.verifier.v1",
})

# TWO DOMAINS, NEVER MIXED. Membership is decided by the GENE origins; the pathway origin is
# CONTEXT and is checked against the selection's context arms alone.
GENE_ORIGINS: frozenset[str] = frozenset({dr.ORIGIN_DIRECT_TARGET,
                                          dr.ORIGIN_TEMPORAL_CROSS_TIME})
PATHWAY_ORIGIN: str = dr.ORIGIN_ENDPOINT_PATHWAY

# The typed membership lists a candidate publishes, and the arm_summaries state each is derived
# from. EXISTING v2 names — the stale v1 `*_arms` names are NOT revived.
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
    "a_candidate_is_shown_for_a_selection_it_has_no_evidence_in"
GATE_FOREIGN_ARM = "a_shown_candidate_carries_an_arm_the_selection_does_not_name"
GATE_ARM_DROPPED = "a_shown_candidate_lost_an_arm_the_selection_gives_it"
GATE_NO_SELECTED_ARMS = "the_view_names_no_selected_arm_keys_so_nothing_can_belong_to_it"
GATE_SUMMARY_WITHOUT_AN_EDGE = \
    "an_arm_summary_claims_an_arm_no_target_drug_edge_supports"
GATE_EDGE_WITHOUT_A_SUMMARY = \
    "a_target_drug_edge_has_no_arm_summary_reconciling_it"
GATE_SUMMARY_DOES_NOT_RECONCILE = \
    "an_arm_summary_does_not_reconcile_with_the_edges_it_summarises"
GATE_TYPED_STATE_NOT_THE_EVIDENCE = \
    "an_arms_typed_evidence_state_is_not_the_state_its_edges_carry"
GATE_ROLE_ON_A_ROW_NOT_THE_SELECTIONS = \
    "a_row_carries_selection_roles_that_are_not_the_roles_this_selection_assigns_its_arm"
GATE_STALE_VOCABULARY = \
    "the_view_was_sealed_under_a_membership_rule_that_is_not_the_one_now_in_force"
GATE_TYPED_COLUMN_WRONG = \
    "an_active_arm_is_not_in_exactly_the_typed_column_its_edges_evidence_state_maps_to"
GATE_DUPLICATE_SUMMARY = "two_arm_summaries_claim_one_candidate_and_arm"
GATE_SUMMARY_STATE_NOT_THE_AGGREGATE = \
    "an_arm_summarys_state_is_not_the_aggregate_of_the_states_its_edges_carry"
GATE_CONFLICTING_HAS_NO_TYPED_COLUMN = \
    "an_arms_edges_contradict_each_other_and_a_contradiction_has_no_typed_column"
GATE_SUMMARY_FIELD_NOT_THE_EDGES = \
    "an_arm_summary_serves_a_field_its_own_edges_do_not_produce"
GATE_FOREIGN_PATHWAY_CONTEXT = \
    "a_shown_candidate_carries_pathway_context_the_selection_does_not_name"
GATE_ROLE_NOT_THE_SELECTIONS = \
    "a_shown_candidates_roles_are_not_the_roles_this_selection_assigns_its_arms"
GATE_ENDPOINTS_NOT_THE_SELECTIONS = \
    "the_selections_ordered_endpoints_are_not_the_ordered_contexts_of_its_arms"


class MembershipError(ValueError):
    """The candidate/selection membership contract is not satisfied. Refuse; never repair."""

    def __init__(self, gate: str, message: str) -> None:
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


def _refuse(gate: str, message: str) -> None:
    raise MembershipError(gate, message)


def _keys(values: Iterable[Any]) -> frozenset[str]:
    return frozenset(str(v) for v in values)


# --------------------------------------------------------------------------- #
# The REAL shapes. Read from the artifact; never guessed, never defaulted.
# --------------------------------------------------------------------------- #
def selected_gene_arm_keys(selected_arms: Mapping[str, Any]) -> frozenset[str]:
    """The GENE arms the question names. These, and only these, decide membership."""
    return _keys(selected_arms.get("gene_arm_keys") or [])


def selected_pathway_arm_keys(selected_arms: Mapping[str, Any]) -> frozenset[str]:
    """The pathway CONTEXT arms, flattened across roles. Context — never membership."""
    per_role = selected_arms.get("pathway_context_arm_keys") or {}
    return _keys(k for keys in per_role.values() for k in (keys or []))


def shown_arm_keys(candidate: Mapping[str, Any]) -> frozenset[str]:
    """The arms THIS VIEW shows the candidate in — `view_arm_keys_by_origin`, flattened.

    NOT `arm_keys`: that is the candidate's GLOBAL membership across the whole store, and reading
    it here is what made the first version reject every reusable candidate.
    """
    by_origin = candidate.get("view_arm_keys_by_origin") or {}
    return _keys(k for keys in by_origin.values() for k in (keys or []))


def global_arm_keys(candidate: Mapping[str, Any]) -> frozenset[str]:
    return _keys(candidate.get("arm_keys") or [])


# --------------------------------------------------------------------------- #
# 1. RE-DERIVE FROM THE VIEW'S OWN EVIDENCE ROWS. The candidate's claims are what is CHECKED.
#
# The view SHIPS its evidence: target_drug_edges and arm_summaries, each keyed by candidate_id +
# arm_key + origin_type. So a browser can re-derive membership with no store at all — and MUST.
#
# The first integrated version READ `arm_keys` and `view_arm_keys_by_origin` and compared them to
# each other. Both are the candidate's OWN CLAIMS. A probe deleted every edge and summary for a
# shown candidate and the gate still admitted its two claimed arms — while the published vocabulary
# said membership was "rederived from evidence, never read from the candidate". That field was a
# lie, and a lie in a published field is worse than no field.
# --------------------------------------------------------------------------- #
def _rows_for(rows: Iterable[Mapping[str, Any]], cid: str) -> list[Mapping[str, Any]]:
    return [r for r in rows if str(r.get("candidate_id")) == cid]


def derive_from_view(view: Mapping[str, Any], cid: str) -> dict[str, frozenset[str]]:
    """What the VIEW'S OWN ROWS say this candidate's arms are. Nothing is read from the candidate."""
    tables = view.get("tables") or {}
    edges = _rows_for(tables.get("target_drug_edges") or [], cid)
    summaries = _rows_for(tables.get("arm_summaries") or [], cid)
    # `pathway_context` is deliberately NOT read here. It was fetched into a local and then never
    # used, which is the shape of a check somebody meant to add — and the only thing it could have
    # added is a pathway-sourced membership, which is precisely what this function must refuse to
    # grant. Context annotates a candidate the edges already support; it never contributes one.

    # MEMBERSHIP COMES FROM THE EDGES. ONLY THE EDGES.
    #
    # This unioned edges with arm_summaries, so deleting every real target_drug_edge while leaving
    # ONE STALE SUMMARY still granted membership. A summary SUMMARISES an edge; it is not evidence
    # in its own right, and it must never be able to conjure a membership the edges do not support.
    gene = _keys(r["arm_key"] for r in edges
                 if str(r.get("origin_type")) in GENE_ORIGINS)

    # Summaries are REDUNDANT CONSISTENCY EVIDENCE: they must reconcile exactly with the edges, and
    # a summary for an arm no edge supports is a refusal — never a promotion.
    summary_arms = _keys(r["arm_key"] for r in summaries
                         if str(r.get("origin_type")) in GENE_ORIGINS)
    orphan = summary_arms - gene
    if orphan:
        _refuse(GATE_SUMMARY_WITHOUT_AN_EDGE,
                f"candidate {cid!r} has arm_summaries for {sorted(orphan)!r} that NO "
                "target_drug_edge supports. A summary summarises an edge; it can never be the "
                "evidence that an edge does not exist.")

    # PATHWAY CONTEXT IS KEYED BY TARGET, NOT BY CANDIDATE.
    #
    # `_rows_for(pathway_context, cid)` therefore matched NOTHING, `truth["pathway"]` was always
    # empty, and the old `shown_pathway <= truth | selected` allowance let ANY SELECTED context arm
    # be claimed with no supporting evidence whatever. The join is on the exact typed target:
    #
    #     candidate's targets := {(target_id, target_id_namespace)} from ITS OWN drug edges
    #     pathway context     := context rows on THOSE targets, by exact pair
    #
    # A context row for a target this candidate has no edge in is somebody else's context.
    targets = {(str(e.get("target_id")), str(e.get("target_id_namespace"))) for e in edges}
    pathway = _keys(
        c["arm_key"] for c in (view.get("tables") or {}).get("pathway_context") or []
        if (str(c.get("target_id")), str(c.get("target_id_namespace"))) in targets)
    return {"gene": gene, "pathway": pathway}


def roles_of(selected_arms: Mapping[str, Any], arm_key: str) -> frozenset[str]:
    """The role(s) the SELECTION assigns this arm. One arm may carry BOTH — that is the reusable
    design working, not a degenerate question."""
    arms = selected_arms.get("arms") or {}
    return frozenset(str(a.get("role")) for a in arms.values()
                     if str(a.get("arm_key")) == str(arm_key) and a.get("role"))


def check_view_membership(view: Mapping[str, Any]) -> None:
    """Every shown candidate has evidence — IN THIS VIEW'S OWN ROWS — in this question's arms.

    THIS HELPER IS NEVER SUFFICIENT ADMISSION ON ITS OWN. It proves membership and coherence; it
    does not prove the bytes. A consumer must admit the FULL hash-bound view (schema + rows + the
    projection seal, i.e. `view_contract.validate`) and the verifier receipt that names this gate.
    """
    selected_arms = view.get("selected_arms") or {}
    selected_gene = selected_gene_arm_keys(selected_arms)
    selected_pathway = selected_pathway_arm_keys(selected_arms)
    if not selected_gene:
        _refuse(GATE_NO_SELECTED_ARMS,
                "the view names no gene arm keys, so nothing it shows can be proved to belong to "
                "it. Displaying anything here would be displaying it under no question at all")

    check_vocabulary_is_current(view)
    _check_selection_coherence(view, selected_arms)

    for cand in ((view.get("tables") or {}).get("candidates") or []):
        cid = str(cand.get("candidate_id"))
        truth = derive_from_view(view, cid)

        # MEMBERSHIP is decided by GENE arms only. Pathway CONTEXTUALISES; it never promotes.
        belongs = truth["gene"] & selected_gene
        if not belongs:
            _refuse(GATE_CANDIDATE_NOT_IN_SELECTION,
                    f"candidate {cid!r} is shown for a selection naming {sorted(selected_gene)!r}, "
                    f"but the view's OWN evidence rows give it gene arms {sorted(truth['gene'])!r}. "
                    "The drug may be real — it is being shown as an answer to a question it has no "
                    "evidence in.")

        _reconcile(view, cid, selected_arms)
        _check_typed_columns(view, cand, cid)

        by_origin = cand.get("view_arm_keys_by_origin") or {}
        shown_gene = _keys(k for o, ks in by_origin.items() if str(o) in GENE_ORIGINS
                           for k in (ks or []))
        shown_pathway = _keys(k for o, ks in by_origin.items() if str(o) == PATHWAY_ORIGIN
                              for k in (ks or []))

        # The candidate's CLAIMS must equal what the rows produce, in this selection.
        if shown_gene != belongs:
            extra, missing = sorted(shown_gene - belongs), sorted(belongs - shown_gene)
            _refuse(GATE_FOREIGN_ARM if extra else GATE_ARM_DROPPED,
                    f"candidate {cid!r} claims gene arms {sorted(shown_gene)!r} in this view, but "
                    f"its evidence rows give it {sorted(belongs)!r} (extra={extra!r}, "
                    f"missing={missing!r}). A claim a consumer trusts is not a fact.")

        published = global_arm_keys(cand)
        if not (belongs <= published):
            _refuse(GATE_MEMBERSHIP_NOT_REDERIVED,
                    f"candidate {cid!r} has evidence in {sorted(belongs - published)!r}, which its "
                    "own published arm_keys do not contain")

        # PATHWAY CONTEXT: a SEPARATE domain, checked against the selection's CONTEXT arms — never
        # against the gene arms. A candidate legitimately carrying a selected Reactome/GO context
        # arm alongside its gene arm must NOT be refused for it.
        foreign_ctx = shown_pathway - selected_pathway
        if foreign_ctx:
            _refuse(GATE_FOREIGN_PATHWAY_CONTEXT,
                    f"candidate {cid!r} is shown with pathway context arm(s) "
                    f"{sorted(foreign_ctx)!r} that this selection does not name. Context is matched "
                    "against pathway_context_arm_keys, exactly — never against the gene arms.")
        # EXACT EQUALITY, not containment: the shown context must be precisely the context this
        # candidate's own targets support, intersected with what the selection names. Containment
        # (`<=`) let a selected-but-unsupported context arm be claimed for free.
        derived_ctx = truth["pathway"] & selected_pathway
        if shown_pathway != derived_ctx:
            _refuse(GATE_FOREIGN_PATHWAY_CONTEXT,
                    f"candidate {cid!r} shows pathway context {sorted(shown_pathway)!r}, but its "
                    f"own targets support {sorted(derived_ctx)!r} of the context arms this "
                    "selection names. Context is joined on the EXACT typed target, never claimed.")

        # ROLES are ASSIGNED BY THE SELECTION, at join time, to the arms actually shown.
        expected = frozenset(r for k in shown_gene for r in roles_of(selected_arms, k))
        claimed = _keys(cand.get("view_roles") or [])
        if claimed != expected:
            _refuse(GATE_ROLE_NOT_THE_SELECTIONS,
                    f"candidate {cid!r} claims roles {sorted(claimed)!r}, but the arms it is shown "
                    f"in are assigned {sorted(expected)!r} by this selection. A role is a property "
                    "of the QUESTION, assigned at join time — never a property the candidate "
                    "carries with it.")


# The typed column an arm belongs in, given the state its EDGES carry.
#
# This map was DECLARED and NEVER USED — so an active arm could be moved from
# `observed_perturbation_arm_keys` to `inverse_direction_hypothesis_arm_keys` and the gate admitted
# it. A dead map that looks like a check is worse than no map: it makes the reader believe the
# column is verified. `_check_typed_columns` now uses it.
STATE_TO_FIELD: dict[str, str] = {state: field for field, state in MEMBERSHIP_FOR_STATE.items()}

# Identity/context a summary SERVES and must therefore re-derive from its edges. A field a consumer
# trusts and nobody re-derives is a field a forger owns.
SUMMARY_FIELDS_FROM_EDGES: tuple[str, ...] = (
    "origin_type", "origin_is_measured", "lane", "program_id", "desired_change",
    "context", "from_condition", "to_condition", "condition",
    "arm_context_sha256", "target_id", "target_id_namespace",
    "active_moiety_id", "pathway_source",
)
# PLURAL AGGREGATES a summary serves. Each has an EXPLICIT derivation from the edge group — the
# singular-field sweep did not cover them, so `target_ids=[WRONG]` sailed through. A finite,
# enumerated list; "every field" is a claim only if the list is checked.
#
#   field                     <- derivation from the candidate's edges IN THIS ARM
AGGREGATE_FROM_EDGES: dict[str, str] = {
    "target_ids": "sorted unique edge.target_id",
    "arm_ranks": "sorted unique edge.arm_rank (nulls dropped; a null rank is a STATE, never a 0)",
    "stage3_evidence_classes": "sorted unique edge.stage3_evidence_class",
    "active_moiety_id": "the single edge.active_moiety_id (they are one candidate)",
    "pathway_source": "the single edge.pathway_source",
}
# NON-AUTHORITATIVE: a content-addressed id of the summary itself. It is not derivable from the
# edges and it is NOT trusted — it is simply never read as evidence.
SUMMARY_SELF_ID_FIELDS: frozenset[str] = frozenset({"arm_summary_id"})

STATE_TO_COUNT: dict[str, str] = {
    wf.OBSERVED_PERTURBATION: "n_observed_perturbation",
    wf.INVERSE_DIRECTION_HYPOTHESIS: "n_inverse_direction_hypothesis",
    wf.OPPOSED: "n_opposed",
    wf.PATHWAY_HYPOTHESIS: "n_pathway_hypothesis",
    wf.UNRESOLVED: "n_unresolved",
}


def _check_typed_columns(view: Mapping[str, Any], cand: Mapping[str, Any], cid: str) -> None:
    """Each active arm sits in EXACTLY the typed column its edges' evidence state maps to — and in
    none of the other four. Moving an unchanged arm between columns changes what the drug is being
    said to DO, while the arm set and every hash stay exactly as they were."""
    edges = _rows_for((view.get("tables") or {}).get("target_drug_edges") or [], cid)
    by_arm: dict[str, set[str]] = {}
    for e in edges:
        by_arm.setdefault(str(e["arm_key"]), set()).add(str(e.get("directional_evidence_status")))

    for arm, states in sorted(by_arm.items()):
        state = wf.summary_state(states)
        want = STATE_TO_FIELD.get(state)
        if want is None:
            # NEVER SILENTLY SKIP. `if want is None: continue` is how `conflicting` walked through:
            # the aggregate state has no typed column, so the arm was checked against nothing at
            # all. A contradiction is PRESERVED, not resolved (workflow.summary_state says so) —
            # and it has no clean column to sit in, so it cannot be displayed as one. FAIL CLOSED.
            _refuse(GATE_CONFLICTING_HAS_NO_TYPED_COLUMN,
                    f"candidate {cid!r} arm {arm!r}: its edges carry {sorted(states)!r}, which "
                    f"aggregate to {state!r} — a state with NO typed column. A contradiction "
                    "between sources is a finding in its own right; it must not be shown as a "
                    "clean membership, and it must not be silently skipped because the map has no "
                    "entry for it.")
        for field in TYPED_MEMBERSHIP_FIELDS:
            present = arm in _keys(cand.get(field) or [])
            if field == want and not present:
                _refuse(GATE_TYPED_COLUMN_WRONG,
                        f"candidate {cid!r} arm {arm!r} carries edge state {state!r}, so it belongs "
                        f"in {want!r} — and it is not there.")
            if field != want and present:
                _refuse(GATE_TYPED_COLUMN_WRONG,
                        f"candidate {cid!r} arm {arm!r} carries edge state {state!r} (column "
                        f"{want!r}), but it is ALSO listed in {field!r}. Moving an unchanged arm "
                        "between typed columns changes what the drug is said to DO, while the arm "
                        "set and every hash stay exactly as they were.")


def check_vocabulary_is_current(view: Mapping[str, Any]) -> None:
    """The view must have been sealed under the rule NOW IN FORCE.

    The published fixture carried `selection_view_vocabulary_digest` from an OLDER rule and
    `validate` passed — so a view sealed under a weaker membership rule was indistinguishable from
    one sealed under this one. Binding the rule into the identity is worthless if nobody checks the
    binding.
    """
    from . import selection_view as sv
    from .hashing import content_hash

    # ONE PATH, THE PRODUCER'S. `view.store.selection_view_vocabulary_digest` is where the producer
    # writes it. Reading `admission` or the top level with a fallback would (a) invent a
    # schema-invalid field and (b) let the REAL digest stay stale in `store` while a fresh copy
    # elsewhere satisfied the check — a fallback that reads whichever copy agrees with you is not a
    # check at all.
    claimed = (view.get("store") or {}).get("selection_view_vocabulary_digest")
    if claimed is None:
        _refuse(GATE_STALE_VOCABULARY,
                "the view carries no store.selection_view_vocabulary_digest, so it cannot be shown "
                "to have been sealed under the membership rule now in force")
    current = content_hash(sv.vocabularies())
    if str(claimed) != current:
        _refuse(GATE_STALE_VOCABULARY,
                f"the view was sealed under vocabulary {str(claimed)[:16]}…, but the rule now in "
                f"force hashes to {current[:16]}…. A view sealed under a WEAKER membership rule "
                "must not be indistinguishable from one sealed under this one.")


def _reconcile(view: Mapping[str, Any], cid: str, selected_arms: Mapping[str, Any]) -> None:
    """EDGES ARE THE TRUTH. Summaries reconcile with them, bidirectionally and exactly.

    Deleting every summary once still ADMITTED: presence was checked one way only. And a wrong
    `selection_roles` on an edge OR a summary sailed through, because nothing re-derived them.
    """
    tables = view.get("tables") or {}
    edges = _rows_for(tables.get("target_drug_edges") or [], cid)
    summaries = _rows_for(tables.get("arm_summaries") or [], cid)

    by_arm: dict[str, list[Mapping[str, Any]]] = {}
    for e in edges:
        by_arm.setdefault(str(e["arm_key"]), []).append(e)
    sum_by_arm: dict[str, list[Mapping[str, Any]]] = {}
    for r in summaries:
        sum_by_arm.setdefault(str(r["arm_key"]), []).append(r)

    # EVERY EDGE'S ARM MUST HAVE A SUMMARY. (Deleting all summaries used to pass.)
    for arm, group in sorted(by_arm.items()):
        rows = sum_by_arm.get(arm)
        if not rows:
            _refuse(GATE_EDGE_WITHOUT_A_SUMMARY,
                    f"candidate {cid!r} has {len(group)} edge(s) in {arm!r} and NO arm_summary "
                    "reconciling them. Presence was checked in one direction only, so deleting "
                    "every summary passed.")
        if len(rows) != 1:
            _refuse(GATE_DUPLICATE_SUMMARY,
                    f"candidate {cid!r} arm {arm!r} has {len(rows)} arm_summaries. Exactly one "
                    "summary summarises one arm; two let a consumer pick whichever agrees with it.")
        summary = rows[0]

        # THE TYPED STATE IS THE EVIDENCE'S, not the summary's claim.
        states = {str(e.get("directional_evidence_status")) for e in group}
        claimed_state = str(summary.get("arm_evidence_state"))
        aggregate = wf.summary_state(states)

        # EXACT EQUALITY WITH THE AGGREGATE — not membership of the state set.
        #
        # `claimed_state in states` was the hole. Duplicate an OPPOSED edge as OBSERVED, update the
        # summary's edge_ids and n_edges so it reconciles, and leave the claimed state as
        # `opposed`: the real aggregate is now `conflicting` (the sources CONTRADICT each other),
        # but `opposed` is still A MEMBER of {observed, opposed}, so it passed. A contradiction was
        # displayed as a clean, one-sided finding.
        if claimed_state != aggregate:
            _refuse(GATE_SUMMARY_STATE_NOT_THE_AGGREGATE,
                    f"candidate {cid!r} arm {arm!r}: the summary says {claimed_state!r}, but its "
                    f"edges carry {sorted(states)!r}, which aggregate to {aggregate!r}. A summary "
                    "state that is merely ONE OF the states its edges carry lets a contradiction "
                    "be shown as a clean finding.")

        # EVERY FIELD THE SUMMARY SERVES IS RE-DERIVED FROM ITS EDGES.
        #
        # Reconciliation checked state, edge_ids/count and roles — so `origin_type` could be flipped
        # from `temporal_cross_time_measured` to `endpoint_pathway_context` and it was ADMITTED.
        # Downstream READS SUMMARIES. A field a consumer trusts and nobody re-derives is a field a
        # forger owns. If a field cannot be re-derived from the edges, it does not belong on a
        # served summary at all.
        for field in SUMMARY_FIELDS_FROM_EDGES:
            if field not in summary:
                continue
            values = {json.dumps(e.get(field), sort_keys=True) for e in group if field in e}
            if len(values) == 1:
                want = json.loads(next(iter(values)))
                if summary.get(field) != want:
                    _refuse(GATE_SUMMARY_FIELD_NOT_THE_EDGES,
                            f"candidate {cid!r} arm {arm!r}: the summary serves {field}="
                            f"{summary.get(field)!r}, but its edges carry {want!r}.")

        # PLURAL AGGREGATES — the ones the singular sweep missed.
        if "target_ids" in summary:
            want = sorted({str(e["target_id"]) for e in group if e.get("target_id") is not None})
            if sorted(str(x) for x in (summary.get("target_ids") or [])) != want:
                _refuse(GATE_SUMMARY_FIELD_NOT_THE_EDGES,
                        f"candidate {cid!r} arm {arm!r}: the summary serves target_ids="
                        f"{summary.get('target_ids')!r}; its edges name {want!r}.")
        if "arm_ranks" in summary:
            want_r = sorted({e["arm_rank"] for e in group if e.get("arm_rank") is not None})
            if sorted(x for x in (summary.get("arm_ranks") or []) if x is not None) != want_r:
                _refuse(GATE_SUMMARY_FIELD_NOT_THE_EDGES,
                        f"candidate {cid!r} arm {arm!r}: the summary serves arm_ranks="
                        f"{summary.get('arm_ranks')!r}; its edges give {want_r!r}. (A null rank is "
                        "a STATE and is dropped, never coerced to 0.)")
        if "stage3_evidence_classes" in summary:
            want_c = sorted({str(e["stage3_evidence_class"]) for e in group
                             if e.get("stage3_evidence_class") is not None})
            if sorted(str(x) for x in (summary.get("stage3_evidence_classes") or [])) != want_c:
                _refuse(GATE_SUMMARY_FIELD_NOT_THE_EDGES,
                        f"candidate {cid!r} arm {arm!r}: the summary serves "
                        f"stage3_evidence_classes={summary.get('stage3_evidence_classes')!r}; its "
                        f"edges give {want_c!r}.")

        # The per-state COUNTS are the edges', not the summary's word for them.
        for st, field in sorted(STATE_TO_COUNT.items()):
            if field in summary:
                want = sum(1 for e in group
                           if str(e.get("directional_evidence_status")) == st)
                if int(summary.get(field) or 0) != want:
                    _refuse(GATE_SUMMARY_FIELD_NOT_THE_EDGES,
                            f"candidate {cid!r} arm {arm!r}: the summary says {field}="
                            f"{summary.get(field)!r}; its edges give {want}.")
        if "observed_perturbation_support" in summary:
            want_support = wf.OBSERVED_PERTURBATION in states
            if bool(summary.get("observed_perturbation_support")) is not want_support:
                _refuse(GATE_SUMMARY_FIELD_NOT_THE_EDGES,
                        f"candidate {cid!r} arm {arm!r}: the summary claims "
                        f"observed_perturbation_support={summary.get('observed_perturbation_support')!r}, "
                        f"but its edges carry {sorted(states)!r}.")

        edge_ids = {str(e.get("edge_id")) for e in group}
        claimed_ids = {str(x) for x in (summary.get("edge_ids") or [])}
        if claimed_ids != edge_ids or int(summary.get("n_edges") or -1) != len(edge_ids):
            _refuse(GATE_SUMMARY_DOES_NOT_RECONCILE,
                    f"candidate {cid!r} arm {arm!r}: the summary names edge_ids "
                    f"{sorted(claimed_ids)!r} / n_edges={summary.get('n_edges')!r}, but the edges "
                    f"present are {sorted(edge_ids)!r}.")

    # AND EVERY ROW'S selection_roles ARE THE SELECTION'S, RE-DERIVED. Never the row's word.
    for row in list(edges) + list(summaries):
        arm = str(row.get("arm_key"))
        expected = roles_of(selected_arms, arm)
        claimed = _keys(row.get("selection_roles") or [])
        if claimed != expected:
            _refuse(GATE_ROLE_ON_A_ROW_NOT_THE_SELECTIONS,
                    f"candidate {cid!r}: a row in {arm!r} claims roles {sorted(claimed)!r}, but "
                    f"this selection assigns that arm {sorted(expected)!r}. A role is a property "
                    "of the QUESTION, assigned at join time.")


def _check_selection_coherence(view: Mapping[str, Any],
                               selected_arms: Mapping[str, Any]) -> None:
    """The ORDERED endpoints of the question must be the ordered contexts of its arms.

    Reversing `conditions` turns "away from A at Rest, toward B at Stim48hr" into its opposite. The
    rows do not move, every hash still checks out — and the answer now points the other way.
    """
    selection = view.get("selection") or {}
    arms = selected_arms.get("arms") or {}
    conditions = [str(c) for c in (selection.get("conditions") or [])]
    if not conditions or not arms:
        return

    a_ctx = (arms.get("A") or {}).get("context") or {}
    b_ctx = (arms.get("B") or {}).get("context") or {}
    a_end = str(a_ctx.get("from_condition") or a_ctx.get("condition") or "")
    b_end = str(b_ctx.get("to_condition") or b_ctx.get("condition") or "")

    if a_end and a_end != conditions[0]:
        _refuse(GATE_ENDPOINTS_NOT_THE_SELECTIONS,
                f"the selection's first condition is {conditions[0]!r}, but pole A's arm is at "
                f"{a_end!r}. Reversing the endpoints reverses the question while every row and "
                "every hash stays exactly as it was.")
    if b_end and b_end != conditions[-1]:
        _refuse(GATE_ENDPOINTS_NOT_THE_SELECTIONS,
                f"the selection's last condition is {conditions[-1]!r}, but pole B's arm is at "
                f"{b_end!r}.")


def displayable(candidate: Mapping[str, Any], *, selected_arms: Mapping[str, Any]) -> bool:
    """May this candidate be shown? Exact intersection on the GENE arms. (A convenience for a
    consumer that has already ADMITTED the full view; it is not admission.)"""
    return bool(global_arm_keys(candidate) & selected_gene_arm_keys(selected_arms))


# 2. PRODUCER / VERIFIER: re-derive the membership from the rows that carry the evidence.
# --------------------------------------------------------------------------- #
def derive(candidate_id: str, *, edges: Sequence[Mapping[str, Any]],
           arm_summaries: Sequence[Mapping[str, Any]],
           pathway_context: Sequence[Mapping[str, Any]] = ()) -> dict[str, list[str]]:
    """Every typed membership this candidate's EVIDENCE gives it. Nothing is read from the
    candidate row — that row is the thing being checked."""
    cid = str(candidate_id)
    mine_edges = [e for e in edges if str(e.get("candidate_id")) == cid]
    mine_summaries = [s for s in arm_summaries if str(s.get("candidate_id")) == cid]

    out: dict[str, list[str]] = {
        "arm_keys": sorted({str(e["arm_key"]) for e in mine_edges}),
    }
    for field, state in sorted(MEMBERSHIP_FOR_STATE.items()):
        out[field] = sorted({str(s["arm_key"]) for s in mine_summaries
                             if str(s.get("arm_evidence_state")) == state})

    # Pathway context is matched by EXACT arm key against arms the candidate actually has an edge
    # in. It contextualises a MEASURED edge and never grants membership of a question.
    measured = set(out["arm_keys"])
    out["pathway_context_arm_keys"] = sorted(
        {str(p["arm_key"]) for p in pathway_context if str(p.get("arm_key")) in measured})
    return out


def check_published_membership(candidate: Mapping[str, Any], *,
                               edges: Sequence[Mapping[str, Any]],
                               arm_summaries: Sequence[Mapping[str, Any]],
                               pathway_context: Sequence[Mapping[str, Any]] = ()) -> None:
    """The candidate's PUBLISHED lists must equal what the evidence produces.

    A widened list is how a candidate becomes displayable under a question it never touched. A
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
                    f"candidate {cid!r}: {field} publishes {len(published)} arm(s), but its "
                    f"evidence produces {len(truth[field])} (extra={extra[:2]!r}, "
                    f"missing={missing[:2]!r}). A published list a consumer trusts is a CLAIM; a "
                    "list re-derived from the rows that carry the evidence is a FACT.")


def vocabularies() -> dict[str, Any]:
    """Published, because Stage 4 and the UI read FIELDS, not source."""
    return {
        "membership_rule_id": MEMBERSHIP_RULE_ID,
        "typed_membership_fields": list(TYPED_MEMBERSHIP_FIELDS),
        "selected_arms_field": "gene_arm_keys",
        "pathway_context_field": "pathway_context_arm_keys",
        "shown_arms_field": "view_arm_keys_by_origin",
        "global_arms_field": "arm_keys",
        "match_rule": "exact_string_equality_on_the_whole_arm_key",
        "prefix_match_permitted": False,
        "display_name_match_permitted": False,
        "shown_equals_global_intersect_selected": True,
        # TRUE, and now actually true on the PRODUCTION path: check_view_membership re-derives
        # from the view's own target_drug_edges + arm_summaries. It was published as True while the
        # gate read only the candidate's claims — a lie in a published field, and worse than no
        # field, because a consumer reads fields.
        "membership_is_rederived_from_target_drug_edges_only": True,
        "edge_summary_reconciliation_is_bidirectional_and_exact": True,
        "typed_evidence_state_comes_from_the_edges_not_the_summary": True,
        "selection_roles_are_rederived_on_every_row": True,
        "retired_membership_ids": sorted(RETIRED_MEMBERSHIP_IDS),
        "arm_summaries_reconcile_but_never_promote_membership": True,
        "roles_are_assigned_by_the_selection_at_join_time": True,
        "ordered_endpoints_must_match_the_arms_contexts": True,
        "pathway_context_never_promotes_a_candidate_into_a_question": True,
        "pathway_context_is_checked_against_pathway_context_arm_keys_not_gene_arms": True,
        "global_store_stays_global_display_is_a_projection": True,
        # THIS HELPER IS NEVER SUFFICIENT ADMISSION. It proves membership and coherence, not bytes.
        "this_gate_alone_is_not_admission": True,
        "admission_requires_the_full_hash_bound_view_and_a_receipt_naming_this_gate": True,
        "membership_schema": MEMBERSHIP_SCHEMA,
        "membership_verifier_id": MEMBERSHIP_VERIFIER_ID,
    }
