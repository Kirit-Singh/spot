"""THE SELECTION VIEW: a PURE PROJECTION of the admitted v2 store onto ONE question.

    materialize(admitted store, verified selection) -> view          (a pure function)

The Stage-3 v2 store is deliberately SELECTION-INDEPENDENT: every arm, every edge, every
candidate, every disposition, and it re-ranks nothing. That is what makes it reusable. But the
USER-FACING RESULT must be SELECTION-SPECIFIC — a user asked ONE question, and must see the
answer to THAT question and no other.

This module is the seam, and it is a QUERY, not an artifact.

WHAT A VIEW IS NOT
------------------
* **It is not written back.** Nothing here mutates, re-ranks, re-scores or re-orders the global
  store. A materializer that writes back is not a view; it is a recompute, and the second
  question would then be answered over a store the first question had already edited.
* **It is not a release artifact.** No file in the global release represents one selection. If
  the release held one question's answer, the store would stop being reusable and every OTHER
  question would be either wrong or a re-run — the same failure as writing an A/B role into an
  arm, one level up.
* **It invents nothing.** No candidate, no rank, no score, no edge. It FILTERS rows the store
  already contains and ANNOTATES them with the role THIS question gives them.

A cached view is permitted, but it is a CACHE: keyed by ``selection_id``, regenerable from the
store at any time, and discardable without loss. A cache that cannot be regenerated from the
store is not a cache — it is a second source of truth, and it will drift.

THE ROLE IS ASSIGNED HERE, AND ONLY HERE
----------------------------------------
``away_from_A`` / ``toward_B`` are properties of the SELECTION, never of an arm. An arm is A in
one question and B in another. The role is stamped onto the PROJECTED ROW at join time and it
never travels back into the store.

WHAT SURVIVES THE PROJECTION
----------------------------
* the three typed origins stay SEPARATE — ``direct_target`` and ``temporal_cross_time_measured``
  are both MEASURED and are DISTINCT estimands, never fused; ``endpoint_pathway_context`` is
  INFERRED and was never measured. The per-origin arm maps are what keeps them separable;
* ``inverse_direction_hypothesis`` stays HYPOTHESIS-ONLY: queued for a look, never observed
  support, never promoted, never ranked as evidence;
* pathway is CONTEXT. It never sources a drug edge;
* MISSINGNESS IS STATED. A null rank stays null — never 0, never last, never "best". An arm that
  no drug evidence reached SAYS SO, by name;
* FILTERED-OUT ROWS ARE COUNTED. A dropped row and a row nobody found look identical, so every
  table reports what it left behind rather than quietly shrinking.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from . import arm_selection as asel
from . import direction as dr
from . import pathway_context_v2 as pc2
from . import selection_v3 as s3
from . import stage2_aggregate as sa
from . import view_projection as vp
from . import view_store as vst
from . import workflow as wf
from .hashing import content_hash
from .selection_admission import (  # noqa: F401  (ADMISSION lives next door; the view is still
    GATE_NO_RECEIPT,                #  the one front door — every name below stays importable
    GATE_RECEIPT_BINDS_NO_BRIDGE,   #  from `druglink.selection_view`, where callers expect it)
    GATE_RECEIPT_BINDS_OTHER_BYTES,
    GATE_STALE_BUNDLE,
    GATE_STALE_SELECTION,
    RECEIPT_SCHEMA,
    SelectionViewError,
    admit_receipt,
    check_not_stale,
)
from .view_store import (  # noqa: F401  (one front door for the projection's refusals)
    StoreIdentityError,
    ViewRefusal,
)

VIEW_SCHEMA = "spot.stage03_selection_view.v1"
VIEW_METHOD_ID = "spot.stage03.selection_view.projection.v1"

# The tables the view PROJECTS, and the column each is filtered on. `provenance` is deliberately
# ABSENT: it describes the GLOBAL bundle, not this question, and the view binds the bundle by id
# so a reader can open it. Copying it in would duplicate a global fact into every view.
PROJECTED_TABLES = ("arm_slots", "target_drug_edges", "arm_summaries", "candidates",
                    "pathway_context", "source_records", "dispositions")

# The fields whose absence is a STATED value rather than a silence.
STATE_NO_DRUG_EVIDENCE = "target_carries_no_source_drug_assertion"

# --------------------------------------------------------------------------- #
# THE PROJECTION. Filter + annotate. Nothing else.
# (ADMISSION — the receipt gates and the staleness gates that run BEFORE a single row is
#  filtered — is :mod:`druglink.selection_admission`, re-exported above.)
# --------------------------------------------------------------------------- #
def _rows(tables: Mapping[str, Sequence[Mapping[str, Any]]], name: str) -> list[dict[str, Any]]:
    return [dict(r) for r in tables.get(name, ())]


def _origin_of(arms: asel.SelectedArms) -> str:
    """The GENE arms' typed origin. DERIVED from their lane, never declared by a row."""
    return {sa.LANE_DIRECT: dr.ORIGIN_DIRECT_TARGET,
            sa.LANE_TEMPORAL: dr.ORIGIN_TEMPORAL_CROSS_TIME}[arms.a.lane]


def _selected_targets(aggregate: sa.AdmittedAggregate,
                      keys: Sequence[str]) -> set[tuple[str, str]]:
    """The typed targets the SELECTED arms actually measured. Read from the arms' own records."""
    wanted = set(keys)
    return {(str(rec.get("target_id")), str(rec.get("target_id_namespace")))
            for arm in aggregate.arms if arm.arm_key in wanted for rec in arm.records}


def _annotate(row: Mapping[str, Any], arms: asel.SelectedArms) -> dict[str, Any]:
    """Stamp EVERY role THIS question gives the row's arm. Join time, and nowhere else.

    A LIST, not a single value: one reusable arm can carry BOTH roles (away_from_A(high) and
    toward_B(low) are both `decrease`), and a scalar here would silently report only the first —
    turning a question whose two poles share an arm into one that looks single-poled.
    """
    return dict(row, selection_roles=arms.roles_of(str(row.get("arm_key"))))


def _candidate_arm_maps(candidate_id: str, edges: Sequence[Mapping[str, Any]],
                        contexts: Sequence[Mapping[str, Any]],
                        arms: asel.SelectedArms) -> dict[str, Any]:
    """WHICH arm each piece of this candidate's evidence came from, PER TYPED ORIGIN.

    This map is the whole reason the three origins stay separable. Collapse it and a measured
    lever and a pathway context member become the same row — which is the single distinction the
    whole stage is built to protect. It is DERIVED by filtering the view's own rows; nothing is
    recomputed and nothing is invented.

    EVERY FIELD HERE IS ``view_``-PREFIXED, AND THAT IS NOT COSMETIC. The store's candidate row
    already carries GLOBAL counts (``n_edges_by_origin``, ``observed_perturbation_support``…)
    computed over every arm in the release. Writing this question's narrower counts under those
    same names would silently REPLACE a global fact with a local one, and no consumer could tell
    which it was holding. Both travel, side by side, and the prefix says which is which.
    """
    mine = [e for e in edges if str(e.get("candidate_id")) == candidate_id]
    by_origin: dict[str, list[str]] = {o: [] for o in dr.V2_ORIGIN_TYPES}
    for edge in mine:
        by_origin[str(edge["origin_type"])].append(str(edge["arm_key"]))

    # INFERRED context membership, kept in its OWN slot. A pathway arm sources no edge, so this
    # can never come from the edge table: it comes from the pathway CONTEXT rows for the targets
    # this candidate's measured edges actually touched.
    targets = {(str(e.get("target_id")), str(e.get("target_id_namespace"))) for e in mine}
    by_origin[dr.ORIGIN_ENDPOINT_PATHWAY] = [
        str(c["arm_key"]) for c in contexts
        if (str(c.get("target_id")), str(c.get("target_id_namespace"))) in targets]

    return {
        "view_arm_keys_by_origin": {o: sorted(set(v)) for o, v in sorted(by_origin.items())},
        "view_n_edges_by_origin": {o: sum(1 for e in mine if e["origin_type"] == o)
                                   for o in dr.V2_ORIGIN_TYPES},
        "view_roles": sorted({r for e in mine for r in arms.roles_of(str(e["arm_key"]))}),
        "view_edge_ids": sorted(str(e["edge_id"]) for e in mine),
        # A LABEL, not a tier, and deliberately unordered. An inverse-direction hypothesis never
        # shares a tier with a measurement.
        "view_stage3_evidence_classes": sorted({str(e["stage3_evidence_class"]) for e in mine}),
        "view_directional_evidence_statuses": sorted(
            {str(e["directional_evidence_status"]) for e in mine}),
        # Only a MEASURED origin in a MEASURED status. An inference never carries it.
        "view_observed_perturbation_support": any(
            bool(e.get("observed_perturbation_support")) for e in mine),
        # Every arm rank, VERBATIM and nullable. A null rank is a STATE — never 0, never last.
        "view_arm_ranks": [{"arm_key": str(e["arm_key"]), "edge_id": str(e["edge_id"]),
                            "arm_rank": e.get("arm_rank"),
                            "arm_rank_status": e.get("arm_rank_status")}
                           for e in sorted(mine, key=lambda e: str(e["edge_id"]))],
    }


def _counts(name: str, store_rows: Sequence[Any], view_rows: Sequence[Any]) -> dict[str, Any]:
    """What the filter LEFT BEHIND. A dropped row and a row nobody found look identical."""
    return {"table": name, "n_in_store": len(store_rows), "n_in_view": len(view_rows),
            "n_filtered_out": len(store_rows) - len(view_rows)}


def materialize(*, selection: s3.VerifiedSelection, aggregate: sa.AdmittedAggregate,
                document: Mapping[str, Any], tables: Mapping[str, Sequence[Mapping[str, Any]]],
                manifest: Mapping[str, Any], admission: Mapping[str, Any], bundle_dir: str,
                arms: Optional[asel.SelectedArms] = None) -> dict[str, Any]:
    """The view. A pure function of (admitted store, verified selection). Writes NOTHING.

    FAIL CLOSED FIRST, PROJECT SECOND. Before a single row is filtered, TWO refusals run and
    neither can admit what the other would refuse:

    * the QUESTION must be about the release in hand (:func:`check_not_stale`);
    * the BYTES must be the ones the document's hashes NAME — all eight tables re-derived from
      the rows in hand AND re-read from the store on disk, and the store must carry no
      selection's identity at any depth (:func:`druglink.view_store.bind`).

    The ``store`` block that comes back is what the view PUBLISHES: every hash in it was
    re-derived here. Copying ``document["table_hashes"]`` would let the view be built over
    MUTATED rows while publishing the digest of the rows it is NOT over — a hash you copy is not
    a hash you checked.
    """
    check_not_stale(selection, aggregate=aggregate, manifest=manifest, document=document)
    store_identity = vst.bind(document=document, tables=tables, aggregate=aggregate,
                              bundle_dir=bundle_dir)
    arms = arms or asel.resolve(selection, aggregate, manifest=manifest)

    gene_keys = set(arms.gene_arm_keys)
    pathway_keys = set(arms.pathway_arm_keys)
    all_keys = gene_keys | pathway_keys
    origin = _origin_of(arms)

    store = {name: _rows(tables, name) for name in PROJECTED_TABLES}

    # --- the rows THIS question is about. EXACT key equality; never a prefix. -------------- #
    edges = sorted((_annotate(e, arms) for e in store["target_drug_edges"]
                    if str(e.get("arm_key")) in gene_keys),
                   key=lambda e: str(e["edge_id"]))
    contexts = sorted((_annotate(c, arms) for c in store["pathway_context"]
                       if str(c.get("arm_key")) in pathway_keys),
                      key=lambda c: str(c["pathway_context_id"]))
    slots = sorted((_annotate(s, arms) for s in store["arm_slots"]
                    if str(s.get("arm_key")) in all_keys),
                   key=lambda s: str(s["arm_slot_id"]))
    summaries = sorted((_annotate(s, arms) for s in store["arm_summaries"]
                        if str(s.get("arm_key")) in gene_keys),
                       key=lambda s: str(s["arm_summary_id"]))

    in_view = {str(e["candidate_id"]) for e in edges}
    candidates = sorted(
        (dict(c, **_candidate_arm_maps(str(c["candidate_id"]), edges, contexts, arms))
         for c in store["candidates"] if str(c["candidate_id"]) in in_view),
        key=lambda c: str(c["candidate_id"]))

    record_ids = {str(e["source_record_id"]) for e in edges}
    sources = sorted((dict(r) for r in store["source_records"]
                      if str(r.get("source_record_id")) in record_ids),
                     key=lambda r: str(r["source_record_id"]))

    # Every ABSENCE this question is entitled to see: the arms it selected, the candidates it
    # surfaced, and the targets its arms actually measured. A disposition about some other arm
    # is not this question's business — and it is COUNTED, not vanished.
    targets = _selected_targets(aggregate, sorted(gene_keys))
    dispositions = sorted(
        (_annotate(d, arms) for d in store["dispositions"]
         if str(d.get("arm_key")) in all_keys
         or str(d.get("candidate_id")) in in_view
         or (d.get("target_id") is not None
             and (str(d["target_id"]), str(d.get("target_id_namespace"))) in targets)),
        key=lambda d: str(d["disposition_id"]))

    view_rows = {"arm_slots": slots, "target_drug_edges": edges, "arm_summaries": summaries,
                 "candidates": candidates, "pathway_context": contexts,
                 "source_records": sources, "dispositions": dispositions}

    # --- what each SELECTED arm actually found, said by NAME ------------------------------- #
    by_key = {str(s["arm_key"]): s for s in slots}
    arm_evidence = []
    for arm in (arms.a, arms.b):
        slot = by_key.get(arm.arm_key, {})
        arm_evidence.append({
            **arm.binding(),
            "origin_type": origin,
            "origin_is_measured": True,
            "arm_slot_id": slot.get("arm_slot_id"),
            "n_edges": slot.get("n_edges", 0),
            "n_records": slot.get("n_records", 0),
            # A count of RANKS, never of rows: Stage 2 RETAINS every unrankable target with
            # rank:null, so "in the ranking" is not "in the rows".
            "n_ranked": slot.get("n_ranked", 0),
            "n_targets_in_admitted_universe": slot.get("n_targets_in_admitted_universe", 0),
            # NAMED, not merely zero. "No drug evidence reached this arm" and "this arm never
            # ran" are different facts, and a bare 0 would make them one silence.
            "arm_evidence_state": slot.get("arm_evidence_state", STATE_NO_DRUG_EVIDENCE),
            "directional_evidence_statuses": slot.get("directional_evidence_statuses", []),
        })

    return _document(selection=selection, arms=arms, document=document,
                     admission=admission, origin=origin, view_rows=view_rows, store=store,
                     arm_evidence=arm_evidence, store_identity=store_identity,
                     bundle_dir=bundle_dir)


def _document(*, selection: s3.VerifiedSelection, arms: asel.SelectedArms,
              document: Mapping[str, Any],
              admission: Mapping[str, Any], origin: str,
              view_rows: Mapping[str, list[dict[str, Any]]],
              store: Mapping[str, list[dict[str, Any]]],
              arm_evidence: list[dict[str, Any]],
              store_identity: Mapping[str, Any], bundle_dir: str) -> dict[str, Any]:
    """The view document. Content-addressed; no paths, no clock, no re-ranking.

    THE PROJECTED ROWS ARE SEALED HERE. The ``store`` block above names the GLOBAL store; it says
    NOTHING about the SUBSET this question ships, and Stage 4 reads the subset. So every projected
    table gets an identity of its own (:mod:`druglink.view_projection`) — and the two receipts,
    ``store`` and ``admission``, are stamped with the seal, so a receipt lifted from another view
    cannot travel with rows it never admitted.
    """
    seal = vp.seal(view_rows=view_rows, arm_evidence=arm_evidence, bundle_dir=bundle_dir)
    view: dict[str, Any] = {
        "schema_version": VIEW_SCHEMA,
        "artifact_class": document.get("artifact_class"),
        "view_method_id": VIEW_METHOD_ID,

        # --- WHAT QUESTION THIS IS ---------------------------------------------------- #
        "selection": selection.binding(),
        "selected_arms": arms.binding(),

        # --- EXACTLY WHICH BYTES THIS IS A PROJECTION OF ------------------------------- #
        # Every hash here was RE-DERIVED by `view_store.bind` from the rows in hand and the
        # store on disk, and PROVEN equal to what the document declares. None of it is copied.
        "store": {**dict(store_identity),
                  "selection_view_vocabulary_digest": content_hash(vocabularies()),
                  "projection_sha256": seal["projection_sha256"]},
        "admission": {**dict(admission), "projection_sha256": seal["projection_sha256"]},

        # --- EXACTLY WHICH ROWS THIS QUESTION SHIPS ------------------------------------ #
        # The identity of the PROJECTION itself, per table: the raw bytes of the store table it
        # was drawn from, the canonical content of the rows it actually carries, the row count
        # and the column contract. Without it the tables are a bare row list, and a cell edited
        # after sealing reaches Stage 4 with every other hash in the document still agreeing.
        "projection": seal,

        # --- THE ANSWER --------------------------------------------------------------- #
        "origin_type": origin,
        "origin_types_present": sorted({str(e["origin_type"])
                                        for e in view_rows["target_drug_edges"]}),
        "arm_evidence": arm_evidence,
        "tables": {name: rows for name, rows in sorted(view_rows.items())},
        "counts": [_counts(name, store[name], view_rows[name])
                   for name in sorted(view_rows)],

        # --- WHAT THE VIEW IS, AND WHAT IT IS NOT ------------------------------------- #
        "guarantees": guarantees(),
        "missingness": missingness(view_rows),
        "inference_status": "not_calibrated",
        "combined_objective_permitted": False,
        "candidate_rank_permitted": False,
        "headline_arm_permitted": False,
        "p_q_fdr_permitted": False,
    }
    # The SAME canonicalisation the verifier applies. A projected table is a ROW SET, so a
    # permutation must not move the id — but the id used to be hashed over the raw document, in
    # which tables are ORDERED lists. Emit and verify now agree on what the identity is over.
    view["view_content_sha256"] = content_hash(vp.identity_content(view))
    view["view_id"] = view["view_content_sha256"][:16]
    return view


def guarantees() -> dict[str, Any]:
    """What a consumer may rely on. Bound into the view id, so revoking one moves every id."""
    return {
        "the_view_is_a_pure_function_of_the_admitted_store_and_the_selection": True,
        "the_view_never_re_ranks_or_re_orders_the_store": True,
        "the_view_never_promotes_an_evidence_class": True,
        "the_view_never_writes_back_to_the_store": True,
        "the_view_is_not_a_release_artifact_and_no_release_holds_one_selection": True,
        "the_view_only_filters_and_annotates_rows_the_store_already_contains": True,
        "roles_are_assigned_at_join_time_never_stored_on_an_arm": True,
        "arm_keys_are_matched_by_exact_string_equality_never_by_prefix": True,
        "direct_and_temporal_are_distinct_estimands_never_fused": True,
        "a_pathway_record_never_sources_a_drug_edge": True,
        "an_inverse_direction_hypothesis_is_never_observed_support_and_is_never_promoted": True,
        "a_null_rank_is_never_a_zero_and_never_sorts_as_best": True,
        "filtered_out_rows_are_reported_as_counts_never_silently_dropped": True,
        "a_cached_view_is_regenerable_from_the_store_and_discardable": True,
        "row_order_is_by_content_id_and_is_not_a_ranking": True,
        # THE TWO REFUSALS THAT RUN BEFORE A SINGLE ROW IS PROJECTED. Named here because a
        # consumer must be able to tell a view that CHECKED its store from one that merely
        # republished the store's own claims about itself.
        "the_stores_eight_table_hashes_are_re_derived_before_projection_never_copied": True,
        "the_global_store_carries_no_selection_identity_at_any_depth": True,
        # THE PROJECTION ITSELF IS SEALED. The promises above are about the GLOBAL store; these
        # are about the ROWS THIS VIEW SHIPS, which is what a consumer actually reads.
        **vp.guarantees(),
    }


def missingness(view_rows: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    """Every absence in this view, as a STATED reason. Never a bare null, never a silent 0."""
    edges = view_rows["target_drug_edges"]
    return {
        "arms_with_no_drug_evidence": sorted(
            str(s["arm_key"]) for s in view_rows["arm_slots"]
            if not s.get("n_edges")),
        "n_edges_with_a_null_rank": sum(1 for e in edges if e.get("arm_rank") is None),
        "null_rank_meaning": ("the source RETAINED this target and did not rank it; it is "
                              "unranked, which is a state — it is not rank 0 and it is not last"),
        "pathway_lane_admitted": pc2.PATHWAY_LANE_ADMITTED,
        "pathway_context_absence_reason": (
            None if pc2.PATHWAY_LANE_ADMITTED else pc2.PATHWAY_LANE_NOT_ADMITTED_REASON),
        "hypothesis_only_statuses": sorted(wf.HYPOTHESIS_ONLY),
        "hypothesis_only_meaning": (
            "queued for a LOOK and never promoted: an inverse-direction hypothesis rests on the "
            "untested inverse of a deleterious result, and CRISPRi never tested activation"),
    }


def vocabularies() -> dict[str, Any]:
    """The projection vocabulary, hashed into every view id."""
    return {
        "view_schema": VIEW_SCHEMA,
        "view_method_id": VIEW_METHOD_ID,
        "projected_tables": list(PROJECTED_TABLES),
        "origin_types": list(dr.V2_ORIGIN_TYPES),
        "measured_origins": sorted(dr.MEASURED_ORIGINS & set(dr.V2_ORIGIN_TYPES)),
        "inferred_origins": sorted(dr.INFERRED_ORIGINS & set(dr.V2_ORIGIN_TYPES)),
        "selection": s3.vocabularies(),
        "arm_selection": asel.vocabularies(),
        "projection": vp.vocabularies(),
        **guarantees(),
    }
