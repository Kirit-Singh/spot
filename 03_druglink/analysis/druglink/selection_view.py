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

import json
import os
from typing import Any, Mapping, Optional, Sequence

from . import arm_selection as asel
from . import direction as dr
from . import pathway_context_v2 as pc2
from . import selection_v3 as s3
from . import stage2_aggregate as sa
from . import workflow as wf
from .hashing import content_hash, file_sha256, without

VIEW_SCHEMA = "spot.stage03_selection_view.v1"
VIEW_METHOD_ID = "spot.stage03.selection_view.projection.v1"
RECEIPT_SCHEMA = "spot.stage02_stage3_receipt.v1"

# The tables the view PROJECTS, and the column each is filtered on. `provenance` is deliberately
# ABSENT: it describes the GLOBAL bundle, not this question, and the view binds the bundle by id
# so a reader can open it. Copying it in would duplicate a global fact into every view.
PROJECTED_TABLES = ("arm_slots", "target_drug_edges", "arm_summaries", "candidates",
                    "pathway_context", "source_records", "dispositions")

# The fields whose absence is a STATED value rather than a silence.
STATE_NO_DRUG_EVIDENCE = "target_carries_no_source_drug_assertion"

GATE_NO_RECEIPT = "the_stage2_aggregate_was_not_admitted_by_a_receipt"
GATE_RECEIPT_BINDS_OTHER_BYTES = \
    "the_receipt_binds_bytes_that_are_not_the_aggregate_presented"
GATE_RECEIPT_BINDS_NO_BRIDGE = "the_receipt_binds_no_bridge_so_it_joins_nothing"
GATE_STALE_SELECTION = \
    "the_selection_was_minted_against_a_different_stage1_release_than_the_aggregate"
GATE_STALE_BUNDLE = "the_v2_bundle_was_not_built_over_the_aggregate_presented"


class SelectionViewError(ValueError):
    """A named, fail-closed refusal. No view is produced and nothing is written."""

    def __init__(self, gate: str, message: str) -> None:
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


def _refuse(gate: str, message: str) -> None:
    raise SelectionViewError(gate, message)


# --------------------------------------------------------------------------- #
# 1. ADMISSION. The receipt is the JOIN, and it must be about THESE bytes.
# --------------------------------------------------------------------------- #
def admit_receipt(receipt_path: str, *, aggregate: sa.AdmittedAggregate,
                  report_path: str) -> dict[str, Any]:
    """The W3 receipt, re-opened and REQUIRED to bind the aggregate in hand.

    The aggregate report names a verdict; the RECEIPT names the BYTES. An ADMIT that binds no
    bytes is an opinion about some other artifact, and a receipt over a DIFFERENT aggregate is a
    handoff for a release nobody cleared — which looks exactly like one that was.
    """
    if not receipt_path or not os.path.isfile(receipt_path):
        _refuse(GATE_NO_RECEIPT,
                f"no Stage-2 -> Stage-3 receipt at {receipt_path!r}. There is no fixture "
                "fallback and no 'admitted by default': a store whose admission nobody can read "
                "is a store nobody admitted, and a view over it would carry the authority of an "
                "admission that does not exist.")
    try:
        with open(receipt_path, "r", encoding="utf-8") as fh:
            receipt = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        _refuse(GATE_NO_RECEIPT, f"the receipt at {receipt_path!r} is not readable JSON: {exc}")

    if not isinstance(receipt, dict) or receipt.get("schema_version") != RECEIPT_SCHEMA:
        _refuse(GATE_NO_RECEIPT,
                f"the receipt declares schema_version="
                f"{(receipt or {}).get('schema_version') if isinstance(receipt, dict) else None!r}"
                f"; the native join is {RECEIPT_SCHEMA!r}. A document W3 never emitted is not "
                "evidence W3 admitted anything.")

    agg = receipt.get("aggregate") or {}
    manifest = agg.get("manifest") or {}
    report = agg.get("report") or {}
    report_raw = file_sha256(report_path) if os.path.isfile(report_path) else None

    if (manifest.get("raw_sha256") != aggregate.manifest_raw_sha256
            or manifest.get("canonical_sha256") != aggregate.manifest_canonical_sha256
            or report.get("raw_sha256") != report_raw):
        _refuse(GATE_RECEIPT_BINDS_OTHER_BYTES,
                f"the receipt binds manifest raw={str(manifest.get('raw_sha256'))[:16]}… / "
                f"canonical={str(manifest.get('canonical_sha256'))[:16]}… and report "
                f"raw={str(report.get('raw_sha256'))[:16]}…, but the aggregate presented hashes "
                f"to raw={aggregate.manifest_raw_sha256[:16]}… / "
                f"canonical={aggregate.manifest_canonical_sha256[:16]}… and its report to "
                f"{str(report_raw)[:16]}…. Raw AND canonical are both required: raw alone would "
                "miss a re-serialisation that changes meaning, canonical alone would let the "
                "shipped file differ from what was judged.")

    bridge = receipt.get("bridge") or {}
    if not (bridge.get("raw_sha256") and bridge.get("canonical_sha256")):
        _refuse(GATE_RECEIPT_BINDS_NO_BRIDGE,
                "the receipt binds no bridge by raw AND canonical hash. The receipt IS the join: "
                "the bridge report returns a verdict but names no bytes, so a receipt that binds "
                "only the aggregate would let an ADMIT travel with a handoff it was never about.")

    return {"receipt_schema": RECEIPT_SCHEMA,
            "aggregate_manifest_raw_sha256": str(manifest["raw_sha256"]),
            "aggregate_manifest_canonical_sha256": str(manifest["canonical_sha256"]),
            "aggregate_report_raw_sha256": str(report["raw_sha256"]),
            "bridge_raw_sha256": str(bridge["raw_sha256"]),
            "bridge_canonical_sha256": str(bridge["canonical_sha256"]),
            "aggregate_verifier_id": aggregate.verifier_id,
            "aggregate_verdict": aggregate.verdict}


def check_not_stale(selection: s3.VerifiedSelection, *, aggregate: sa.AdmittedAggregate,
                    manifest: Mapping[str, Any],
                    document: Mapping[str, Any]) -> None:
    """The question, the release and the bundle must all be about the SAME science."""
    release = manifest.get("stage1_v3_release") or {}
    pinned = release.get("registry_scorer_view_canonical_sha256")
    if pinned and selection.registry_scorer_view_sha256 \
            and str(pinned) != selection.registry_scorer_view_sha256:
        _refuse(GATE_STALE_SELECTION,
                f"the selection was minted against Stage-1 scorer view "
                f"{selection.registry_scorer_view_sha256[:16]}…, but the aggregate was computed "
                f"against {str(pinned)[:16]}…. The programs the question names are not the "
                "programs these arms were measured on. A STALE selection projected onto a newer "
                "release returns arms that are real, ranked and about something else.")

    bound = (document.get("stage2_aggregate") or {}).get("manifest_self_hash")
    if str(bound) != aggregate.manifest_self_hash:
        _refuse(GATE_STALE_BUNDLE,
                f"the v2 bundle was built over aggregate {str(bound)[:16]}…, but the aggregate "
                f"presented semantically hashes to {aggregate.manifest_self_hash[:16]}…. The "
                "arms the view would filter are not the arms the bundle's edges were built from, "
                "so every row would be joined against a release it did not come from.")


# --------------------------------------------------------------------------- #
# 2. THE PROJECTION. Filter + annotate. Nothing else.
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
                manifest: Mapping[str, Any], admission: Mapping[str, Any],
                arms: Optional[asel.SelectedArms] = None) -> dict[str, Any]:
    """The view. A pure function of (admitted store, verified selection). Writes NOTHING."""
    check_not_stale(selection, aggregate=aggregate, manifest=manifest, document=document)
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

    return _document(selection=selection, arms=arms, aggregate=aggregate, document=document,
                     admission=admission, origin=origin, view_rows=view_rows, store=store,
                     arm_evidence=arm_evidence)


def _document(*, selection: s3.VerifiedSelection, arms: asel.SelectedArms,
              aggregate: sa.AdmittedAggregate, document: Mapping[str, Any],
              admission: Mapping[str, Any], origin: str,
              view_rows: Mapping[str, list[dict[str, Any]]],
              store: Mapping[str, list[dict[str, Any]]],
              arm_evidence: list[dict[str, Any]]) -> dict[str, Any]:
    """The view document. Content-addressed; no paths, no clock, no re-ranking."""
    method = document.get("method") or {}
    view: dict[str, Any] = {
        "schema_version": VIEW_SCHEMA,
        "artifact_class": document.get("artifact_class"),
        "view_method_id": VIEW_METHOD_ID,

        # --- WHAT QUESTION THIS IS ---------------------------------------------------- #
        "selection": selection.binding(),
        "selected_arms": arms.binding(),

        # --- WHAT STORE IT WAS PROJECTED FROM ----------------------------------------- #
        "store": {
            "bundle_id": document.get("bundle_id"),
            "bundle_schema": document.get("schema_version"),
            "canonical_content_sha256": document.get("canonical_content_sha256"),
            "table_hashes": dict(document.get("table_hashes") or {}),
            "stage2_manifest_self_hash": aggregate.manifest_self_hash,
            "stage2_manifest_raw_sha256": aggregate.manifest_raw_sha256,
            "stage2_manifest_canonical_sha256": aggregate.manifest_canonical_sha256,
            "stage1_release_sha256": aggregate.stage1_release_sha256,
            "universe_store_id": (document.get("universe_store") or {}).get("store_id"),
            "method_sha256": content_hash(method),
            "code_tree_sha256": method.get("code_tree_sha256"),
            "schemas_sha256": method.get("schemas_sha256"),
            "direction_vocabulary_digest": method.get("direction_vocabulary_digest"),
            "selection_view_vocabulary_digest": content_hash(vocabularies()),
        },
        "admission": dict(admission),

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
    view["view_id"] = content_hash(view)[:16]
    view["view_content_sha256"] = content_hash(without(view, ("view_id",)))
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
        **guarantees(),
    }
