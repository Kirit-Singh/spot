"""The v2 CANDIDATE layer: stable active moieties, summarised per reusable ARM and ORIGIN.

The EDGE layer lives in :mod:`druglink.edges_v2` (one reusable arm x one typed origin x one
typed target x one source assertion) and its names are re-exported here, so a consumer binds
ONE module — the same front-door idiom ``universe_rows`` uses for ``universe_edges``.

A candidate is an active moiety. It does NOT have "a" direction, "a" rank or "a" score:

  * the three typed origins answer three different questions — a same-condition measured
    effect, a cross-time difference-in-differences, and an inference about a gene nobody
    perturbed — so every candidate carries a summary for EACH (arm, origin) it touches, and
    they never merge;
  * a moiety may be an ``observed_perturbation`` on one reusable arm and ``opposed`` on
    another. Both survive. An opposed edge on one arm never disqualifies another arm;
  * a moiety may be an ``observed_perturbation`` on a measured target and only a
    ``pathway_hypothesis`` on an inferred node — even the SAME gene. Both survive.

**THERE IS NO WINNER.** No combined, mean, balanced, best-of, primary, headline or overall
score; no candidate-level rank; and no cross-origin numeric total — the candidate row carries
per-origin count MAPS, and a map is not a sum. There is nowhere to put one. Ordering is by
``candidate_id``, which is a content hash: stable, and not a ranking.

Stage 3 reports workflow STATES (:mod:`druglink.workflow`). It decides no promotion, no
eligibility and no recommendation; that vocabulary is retired.
"""
from __future__ import annotations

from typing import Any, Mapping, Sequence

from . import artifact_class as ac
from . import direction as dr
from . import modality_v2 as mv2
from . import stage2_aggregate as sa
from . import universe_rows as ur
from . import workflow as wf
from .hashing import short_id
from .edge_build_v2 import build_edges, dedup, disposition, n_ranked  # noqa: F401
from .edges_v2 import (  # noqa: F401  (the one front door: re-exported for consumers)
    ARM_IDENTITY_COLUMNS,
    DISPOSITION_COLUMNS,
    DISPOSITION_KEY,
    EDGE_COLUMNS,
    EDGE_KEY,
    GATE_ABSENCE_NOT_STATED,
    GATE_NO_SOURCE_LOCATOR,
    GATE_NO_SOURCE_RELEASE,
    GATE_INFERRED_ORIGIN_HAS_A_RANK,
    GATE_INFERRED_ORIGIN_HAS_SUPPORT,
    GATE_MEASURED_ORIGIN_NOT_MEASURED,
    GATE_STAGE2_ADMISSION_NOT_CARRIED,
    STATE_PATHWAY_IS_TYPED_CONTEXT,
    GATE_ORIGIN_LANE_DISAGREE,
    GATE_ROLE_IN_A_REUSABLE_ARM,
    GATE_UNKNOWN_LANE,
    GATE_UNKNOWN_MODULATION,
    GATE_UNTYPED_TARGET,
    MISSINGNESS_STATES,
    NO_DRUG_EVIDENCE,
    NOT_STATED,
    ORIGIN_FOR_LANE,
    SELECTION_ROLES,
    SOURCE_RECORD_COLUMNS,
    SOURCE_RECORD_KEY,
    STATE_NO_DRUG_EVIDENCE,
    STATE_NON_RANKABLE,
    STATE_NOT_IN_UNIVERSE,
    STATE_UNSUPPORTED_NAMESPACE,
    STATED,
    UPSTREAM_COLUMNS,
    V2_ORIGINS,
    AssertionV2Error,
    CandidatesV2Error,
    arm_identity,
    check_edges,
    identity_status,
    moiety_id,
    stated,
    upstream,
)

CANDIDATES_V2_POLICY_VERSION = "stage3-candidates-v2-reusable-arms"

GATE_CANDIDATE_ID_NOT_STABLE = "a_candidate_id_is_not_the_same_identity_in_every_table"

STATE_NOT_QUEUED = wf.NOT_QUEUED
DISPOSITION_STATES = (STATE_NOT_IN_UNIVERSE, STATE_NO_DRUG_EVIDENCE,
                      STATE_UNSUPPORTED_NAMESPACE, STATE_NON_RANKABLE, STATE_NOT_QUEUED,
                      STATE_PATHWAY_IS_TYPED_CONTEXT)

# EVERY arm slot the release resolved — INCLUDING the ones no drug evidence reached.
#
# Without this table, "this arm had no drug evidence" and "this arm never ran" are the same
# silence. Zero coverage that nobody can see is the defect this project keeps finding, so an
# arm with no edges is emitted with n_edges=0 and an evidence state that SAYS SO by name.
ARM_SLOT_COLUMNS: tuple[str, ...] = (
    ("arm_slot_id",)
    + ARM_IDENTITY_COLUMNS
    + ("origin_type", "origin_is_measured", "condition_pair_is_ordered",
       # `n_records` counts ROWS; `n_ranked` counts NON-NULL RANKS. Stage 2 RETAINS every
       # target with rank:null when it is not rankable, so "in the ranking" is NOT "in the
       # rows" — and a hit count taken from rows would inflate by exactly the targets the arm
       # could NOT evaluate, the ones least entitled to support a claim.
       "n_records", "n_ranked", "n_targets", "n_targets_in_admitted_universe",
       "n_source_assertions", "n_rankable_assertions", "n_edges",
       "arm_evidence_state", "directional_evidence_statuses", "target_ids")
    + UPSTREAM_COLUMNS
)
ARM_SLOT_KEY: tuple[str, ...] = ("arm_slot_id",)

ARM_SUMMARY_COLUMNS: tuple[str, ...] = (
    ("arm_summary_id", "candidate_id", "active_moiety_id")
    + ARM_IDENTITY_COLUMNS
    + ("origin_type", "arm_evidence_state", "n_edges",
       "n_observed_perturbation", "n_inverse_direction_hypothesis",
       "n_pathway_hypothesis", "n_opposed", "n_unresolved",
       "observed_perturbation_support", "stage3_evidence_classes",
    # PHENOCOPY, NOT EQUIVALENCE — carried on the CANDIDATE too, because Stage 4 reads the
    # candidate row and must never mistake a putative phenocopy for an equivalence.
    "evidence_relations", "evidence_is_equivalence", "evidence_relation_caveat",
    # WHICH sourced mechanisms actually phenocopy the declared modulation, and which do not.
    # An incompatible mechanism is VISIBLE here with its reason — never silently dropped.
    "mechanism_match_statuses", "n_edges_by_mechanism_match",
    "observed_perturbation_modalities", "observed_sign_states", "desired_target_modulations",
       "edge_ids", "arm_ranks", "target_ids")
)
ARM_SUMMARY_KEY: tuple[str, ...] = ("arm_summary_id",)

# NOTE what a candidate does NOT have: a rank, a score, a winner, or any scalar total across
# origins. Counts are per-origin MAPS — a map is not a sum, and there is nowhere to put one.
CANDIDATE_COLUMNS: tuple[str, ...] = (
    "candidate_id", "active_moiety_id", "preferred_name", "identity_status",
    "molecule_chembl_ids", "inchikey", "molecule_types",
    "n_edges_by_origin", "n_arm_summaries_by_origin",
    "arm_keys", "origin_types", "lanes", "program_ids", "target_ids",
    "observed_perturbation_arm_keys", "inverse_direction_hypothesis_arm_keys",
    "pathway_hypothesis_arm_keys", "opposed_arm_keys", "unresolved_arm_keys",
    "observed_perturbation_support", "stage3_evidence_classes",
    # PHENOCOPY, NOT EQUIVALENCE — carried on the CANDIDATE too, because Stage 4 reads the
    # candidate row and must never mistake a putative phenocopy for an equivalence.
    "evidence_relations", "evidence_is_equivalence", "evidence_relation_caveat",
    # WHICH sourced mechanisms actually phenocopy the declared modulation, and which do not.
    # An incompatible mechanism is VISIBLE here with its reason — never silently dropped.
    "mechanism_match_statuses", "n_edges_by_mechanism_match",
    "observed_perturbation_modalities", "observed_sign_states", "desired_target_modulations",
    # CONTEXT only, and absent is SAID rather than left null: a candidate whose sources state
    # no max_phase carries not_stated_by_source, never a 0 and never a silent gap.
    "max_phase_sources", "max_phase_status", "max_phase_is_context_only",
    "source_locators", "source_releases", "source_licenses",
    "stage4_assessment_status", "stage4_assessment_reason",
    "source_record_ids",
)
CANDIDATE_KEY: tuple[str, ...] = ("candidate_id",)


# --------------------------------------------------------------------------- #
# Arm slots. ALL of them — the silent ones above all.
# --------------------------------------------------------------------------- #
def build_arm_slots(aggregate: sa.AdmittedAggregate, store: ur.AdmittedStore, *,
                    edges: Sequence[Mapping[str, Any]],
                    source_records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """One row per arm slot the release resolved. An arm with ZERO drug evidence is HERE.

    A missing row would make "no drug evidence reached this arm" indistinguishable from "this
    arm never ran" — and a consumer counting rows would report the second as the first.
    """
    by_arm: dict[str, list[Mapping[str, Any]]] = {}
    for edge in edges:
        by_arm.setdefault(str(edge["arm_key"]), []).append(edge)

    # The store's assertions, indexed by the typed identity they were joined on. Counted from
    # what was actually emitted, so an arm's coverage is never re-queried into existence.
    by_target: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for rec in source_records:
        by_target.setdefault((str(rec["target_id"]),
                              str(rec["target_id_namespace"])), []).append(rec)

    out: list[dict[str, Any]] = []
    for arm in aggregate.arms:
        mine = by_arm.get(arm.arm_key, [])
        # A RECORD WITH NO TARGET NAMES NO TARGET. `str(None)` is the string "None", and a
        # pathway record legitimately carries no target_id — it is a gene-set enrichment. Left
        # unguarded, every pathway arm slot reported one target, called "None", in a namespace
        # called "None": an invented identity, in a table whose whole job is to say honestly what
        # each arm covered. A measured record with no target is refused upstream by
        # `typed_identity`, so nothing real is lost here.
        targets = sorted({(str(r["target_id"]), str(r.get("target_id_namespace")))
                          for r in arm.records if r.get("target_id")})
        in_universe = [t for t in targets if store.row_for(t[0], t[1]) is not None]
        assertions = [a for t in in_universe for a in by_target.get(t, ())]
        statuses = {str(e["directional_evidence_status"]) for e in mine}
        origin = ORIGIN_FOR_LANE[arm.lane]
        row = {
            **arm_identity(arm),
            "origin_type": origin,
            "origin_is_measured": origin in dr.MEASURED_ORIGINS,
            # Rest->Stim48hr is not Stim48hr->Rest: the DiD changes sign.
            "condition_pair_is_ordered": arm.lane == sa.LANE_TEMPORAL,
            "n_records": len(arm.records),
            # NON-NULL RANKS, never len(records). See ARM_SLOT_COLUMNS.
            "n_ranked": n_ranked(arm.records),
            "n_targets": len(targets),
            "n_targets_in_admitted_universe": len(in_universe),
            "n_source_assertions": len(assertions),
            "n_rankable_assertions": sum(
                1 for a in assertions if a.get("general_gene_rankable") is True),
            "n_edges": len(mine),
            # NAMED, not merely zero: an arm that no drug evidence reached SAYS SO.
            "arm_evidence_state": wf.summary_state(statuses) if mine else NO_DRUG_EVIDENCE,
            "directional_evidence_statuses": sorted(statuses),
            "target_ids": sorted({t for t, _ns in targets}),
            **upstream(arm, store),
        }
        row["arm_slot_id"] = short_id(
            {k: row.get(k) for k in ARM_SLOT_COLUMNS if k != "arm_slot_id"})
        out.append(row)
    return sorted(out, key=lambda r: str(r["arm_slot_id"]))


# --------------------------------------------------------------------------- #
# Summaries. Per (candidate, reusable arm, origin) — and never across origins.
# --------------------------------------------------------------------------- #
def build_arm_summaries(edges: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """One row per (candidate, ARM, ORIGIN) with at least one edge. Nothing is pooled."""
    grouped: dict[tuple[str, str, str], list[Mapping[str, Any]]] = {}
    for edge in edges:
        grouped.setdefault((str(edge["active_moiety_id"]), str(edge["arm_key"]),
                            str(edge["origin_type"])), []).append(edge)

    out: list[dict[str, Any]] = []
    for (mid, _arm_key, origin), group in sorted(grouped.items()):
        statuses = [str(e["directional_evidence_status"]) for e in group]
        row = {c: group[0].get(c) for c in ARM_IDENTITY_COLUMNS}
        row.update({
            "candidate_id": mid, "active_moiety_id": mid, "origin_type": origin,
            # A contradiction between sources is PRESERVED, never resolved by preferring the
            # favourable one.
            "arm_evidence_state": wf.summary_state(set(statuses)),
            "n_edges": len(group),
            "n_observed_perturbation": statuses.count(wf.OBSERVED_PERTURBATION),
            "n_inverse_direction_hypothesis": statuses.count(
                wf.INVERSE_DIRECTION_HYPOTHESIS),
            "n_pathway_hypothesis": statuses.count(wf.PATHWAY_HYPOTHESIS),
            "n_opposed": statuses.count(wf.OPPOSED),
            "n_unresolved": statuses.count(wf.UNRESOLVED),
            "observed_perturbation_support": any(
                bool(e["observed_perturbation_support"]) for e in group),
            "stage3_evidence_classes": sorted({str(e["stage3_evidence_class"])
                                               for e in group}),
            "edge_ids": sorted(str(e["edge_id"]) for e in group),
            # Each arm's OWN nullable rank, verbatim. Stage 3 never alters or invents one, and
            # an inferred origin contributes none — nobody perturbed it.
            "arm_ranks": sorted({int(e["arm_rank"]) for e in group
                                 if e["arm_rank"] is not None}),
            "target_ids": sorted({str(e["target_id"]) for e in group}),
        })
        row["arm_summary_id"] = short_id(
            {k: row.get(k) for k in ARM_SUMMARY_COLUMNS if k != "arm_summary_id"})
        out.append(row)
    return out


def _keys_with_state(summaries: Sequence[Mapping[str, Any]], state: str) -> list[str]:
    return sorted({str(s["arm_key"]) for s in summaries
                   if s["arm_evidence_state"] == state})


def _moiety_identity_status(sources: Sequence[Mapping[str, Any]]) -> str:
    if not sources:
        return "unresolved"
    statuses = {identity_status(s) for s in sources}
    if statuses == {"resolved"}:
        return "resolved"
    if "resolved" in statuses:
        return "ambiguous"
    return sorted(statuses)[0]


def build_candidates(*, artifact_class: str, edges: Sequence[Mapping[str, Any]],
                     arm_summaries: Sequence[Mapping[str, Any]],
                     source_records: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Stable active-moiety candidates with per-arm/per-origin summaries. NO winner."""
    ac.require(artifact_class)
    by_moiety: dict[str, list[Mapping[str, Any]]] = {}
    for edge in edges:
        by_moiety.setdefault(str(edge["active_moiety_id"]), []).append(edge)
    summaries_by: dict[str, list[Mapping[str, Any]]] = {}
    for summary in arm_summaries:
        summaries_by.setdefault(str(summary["candidate_id"]), []).append(summary)
    sources_by: dict[str, list[Mapping[str, Any]]] = {}
    for record in source_records:
        sources_by.setdefault(str(record["active_moiety_id"]), []).append(record)

    out: list[dict[str, Any]] = []
    for mid in sorted(by_moiety):
        group = by_moiety[mid]
        summaries = summaries_by.get(mid, [])
        sources = sources_by.get(mid, [])
        status_set = {str(e["directional_evidence_status"]) for e in group}
        identity = _moiety_identity_status(sources)
        phases = sorted({str(s["max_phase_source"]) for s in sources
                         if s.get("max_phase_source") is not None})
        # An ASSESSMENT is not promotion and not a recommendation. A fixture is never queued.
        stage4, reason = wf.stage4_assessment(
            artifact_class=artifact_class, identity_status=identity,
            active_moiety_id=mid, directional_statuses=status_set)
        out.append({
            "candidate_id": mid,
            "active_moiety_id": mid,
            "preferred_name": next((s.get("pref_name") for s in sources
                                    if s.get("pref_name")), None),
            "identity_status": identity,
            "molecule_chembl_ids": sorted({str(s["molecule_chembl_id"]) for s in sources
                                           if s.get("molecule_chembl_id")}),
            "inchikey": next((s.get("inchikey") for s in sources if s.get("inchikey")), None),
            "molecule_types": sorted({str(s["molecule_type"]) for s in sources
                                      if s.get("molecule_type")}),
            # PER-ORIGIN maps, deliberately. A scalar total across origins would sum a measured
            # effect, a cross-time DiD and an inference into a number with no estimand.
            "n_edges_by_origin": {o: sum(1 for e in group if e["origin_type"] == o)
                                  for o in V2_ORIGINS},
            "n_arm_summaries_by_origin": {
                o: sum(1 for s in summaries if s["origin_type"] == o) for o in V2_ORIGINS},
            "arm_keys": sorted({str(e["arm_key"]) for e in group}),
            "origin_types": sorted({str(e["origin_type"]) for e in group}),
            "lanes": sorted({str(e["lane"]) for e in group}),
            "program_ids": sorted({str(e["program_id"]) for e in group}),
            "target_ids": sorted({str(e["target_id"]) for e in group}),
            "observed_perturbation_arm_keys": _keys_with_state(
                summaries, wf.OBSERVED_PERTURBATION),
            # A labelled HYPOTHESIS — never observed gain of function, never observed support.
            "inverse_direction_hypothesis_arm_keys": _keys_with_state(
                summaries, wf.INVERSE_DIRECTION_HYPOTHESIS),
            "pathway_hypothesis_arm_keys": _keys_with_state(summaries, wf.PATHWAY_HYPOTHESIS),
            "opposed_arm_keys": _keys_with_state(summaries, wf.OPPOSED),
            "unresolved_arm_keys": _keys_with_state(summaries, wf.UNRESOLVED),
            # Only a MEASURED origin in a MEASURED status. An inference never carries it.
            "observed_perturbation_support": any(
                bool(e["observed_perturbation_support"]) for e in group),
            # A LABEL, not a tier, and deliberately unordered.
            "stage3_evidence_classes": sorted({str(e["stage3_evidence_class"])
                                               for e in group}),
            "evidence_relations": sorted({str(e["evidence_relation"]) for e in group}),
            "evidence_is_equivalence": mv2.EVIDENCE_IS_EQUIVALENCE,
            "evidence_relation_caveat": mv2.PHENOCOPY_CAVEAT,
            "mechanism_match_statuses": sorted({str(e["mechanism_match_status"])
                                                for e in group}),
            "n_edges_by_mechanism_match": {
                m: sum(1 for e in group if e["mechanism_match_status"] == m)
                for m in mv2.MATCH_STATUSES},
            "observed_perturbation_modalities": sorted(
                {str(e["observed_perturbation_modality"]) for e in group}),
            "observed_sign_states": sorted({str(e["observed_sign_state"]) for e in group}),
            "desired_target_modulations": sorted({str(e["desired_target_modulation"])
                                                  for e in group}),
            # CONTEXT only. It may never gate or rank, and the row says so.
            "max_phase_sources": phases,
            "max_phase_status": STATED if phases else NOT_STATED,
            "max_phase_is_context_only": True,
            # Every ChEMBL row this candidate stands on, addressable, with the exact release
            # and licence it was drawn under. Stage 4 can reopen any of them.
            "source_locators": sorted({str(s["source_locator"]) for s in sources
                                       if s.get("source_locator")}),
            "source_releases": sorted({str(s["source_release"]) for s in sources
                                       if s.get("source_release")}),
            "source_licenses": sorted({str(s["source_license"]) for s in sources
                                       if s.get("source_license")}),
            "stage4_assessment_status": stage4,
            "stage4_assessment_reason": reason,
            "source_record_ids": sorted({str(s["source_record_id"]) for s in sources}),
        })
    return out


def not_queued_dispositions(candidates: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """A candidate Stage 4 is NOT asked to assess stays VISIBLE, with its reason."""
    return [disposition(
        subject_kind="candidate", subject_id=str(c["candidate_id"]),
        candidate_id=str(c["candidate_id"]),
        state=STATE_NOT_QUEUED, reason=str(c["stage4_assessment_reason"]),
        detail=f"identity={c['identity_status']}")
        for c in candidates if c["stage4_assessment_status"] == wf.NOT_QUEUED]


def check_candidate_identity(tables: Mapping[str, list[dict[str, Any]]]) -> None:
    """ONE candidate_id, byte-identical in every table that references a candidate.

    Stage 4 joins on it. An id regenerated per table is not an identity — it is a coincidence
    that holds until the day two tables disagree, and then silently joins the wrong rows.
    """
    known = {str(c["candidate_id"]) for c in tables.get("candidates", [])}
    for name, rows in (("target_drug_edges", tables.get("target_drug_edges", [])),
                       ("arm_summaries", tables.get("arm_summaries", [])),
                       ("source_records", tables.get("source_records", []))):
        for row in rows:
            cid, mid = row.get("candidate_id"), row.get("active_moiety_id")
            if cid != mid:
                raise CandidatesV2Error(
                    GATE_CANDIDATE_ID_NOT_STABLE,
                    f"{name}: candidate_id={cid!r} is not the active_moiety_id={mid!r} it must "
                    "be. The candidate IS the active moiety, and its id is computed once")
            if name != "source_records" and str(cid) not in known:
                raise CandidatesV2Error(
                    GATE_CANDIDATE_ID_NOT_STABLE,
                    f"{name} references candidate_id={cid!r}, which is in no candidate row. A "
                    "reference nobody can resolve is a join that silently drops")


def build(*, artifact_class: str, aggregate: sa.AdmittedAggregate,
          store: ur.AdmittedStore) -> dict[str, list[dict[str, Any]]]:
    """The whole selection-independent v2 evidence set. SEVEN scientific tables, no winner.

    arm_slots, target_drug_edges, pathway_context, arm_summaries, candidates, source_records,
    dispositions — and :mod:`druglink.bundle_v2` adds the EIGHTH, ``provenance``, for the
    EIGHT the bundle ships. (This said "six ... the seventh" while building seven; a consumer
    binding the stated count would have missed a whole table.)
    """
    ac.require(artifact_class)
    built = build_edges(aggregate, store)
    edges = built["target_drug_edges"]
    arm_summaries = build_arm_summaries(edges)
    candidates = build_candidates(
        artifact_class=artifact_class, edges=edges, arm_summaries=arm_summaries,
        source_records=built["source_records"])
    dispositions = dedup(
        built["dispositions"] + not_queued_dispositions(candidates), "disposition_id")
    tables = {
        # EVERY arm slot, including the ones nothing reached.
        "arm_slots": build_arm_slots(aggregate, store, edges=edges,
                                     source_records=built["source_records"]),
        "target_drug_edges": edges,
        # The pathway CONTEXTUALIZES a measured edge; it never sources one. Members with no
        # measured support are carried here with stated missingness, and earn no edge.
        "pathway_context": built["pathway_context"],
        "arm_summaries": arm_summaries,
        "candidates": candidates,
        "source_records": built["source_records"],
        "dispositions": dispositions,
    }
    check_candidate_identity(tables)
    return tables


def vocabularies() -> dict[str, Any]:
    """The v2 candidate vocabulary, hashed into the v2 bundle id."""
    return {
        "candidates_v2_policy_version": CANDIDATES_V2_POLICY_VERSION,
        "origin_types": list(V2_ORIGINS),
        "origin_for_lane": dict(sorted(ORIGIN_FOR_LANE.items())),
        "measured_origins": sorted(dr.MEASURED_ORIGINS & set(V2_ORIGINS)),
        "inferred_origins": sorted(dr.INFERRED_ORIGINS & set(V2_ORIGINS)),
        "disposition_states": list(DISPOSITION_STATES),
        "missingness_states": list(MISSINGNESS_STATES),
        "absence_is_stated_never_omitted": True,
        "a_null_is_never_a_zero": True,
        "candidate_id_is_the_active_moiety_id": True,
        "arm_key_fields": list(ARM_IDENTITY_COLUMNS),
        "selection_roles_are_assigned_at_join_time_not_in_this_bundle": True,
        "direct_and_temporal_are_distinct_estimands_never_fused": True,
        "inferred_origin_can_never_carry_observed_support": True,
        "pathway_direction_is_never_inherited_from_set_membership": True,
        "combined_objective_permitted": False,
        "headline_arm_permitted": False,
        "candidate_rank_permitted": False,
    }
