"""The DERIVED v2 tables: arm slots, arm summaries, candidates. Imports NOTHING from ``druglink``.

Split from :mod:`verifier.v2_rebuild` (which owns the EDGE and the orchestration) at the 500-line
gate — the same seam the producer draws between ``edges_v2`` and ``candidates_v2``.

Everything here is a function of the EDGES, which were themselves classified from a sign this
verifier re-derived. Nothing here reads a verdict off the bundle.

EVERY ARM SLOT IS EMITTED, INCLUDING THE SILENT ONES. An arm no drug evidence reached carries
``n_edges=0`` and an evidence state that NAMES the absence — because "this arm had no drug
evidence" and "this arm never ran" are different facts, and a missing row makes them one silence.
"""
from __future__ import annotations

from typing import Any

from . import canon, policy
from . import v2_admission as v2
from . import v2_contract as C
from . import v2_sign as S
from . import v2_store as vs
from . import v2_tables as T


def _short(row: dict[str, Any], columns: tuple[str, ...], id_column: str) -> str:
    return canon.short({k: row.get(k) for k in columns if k != id_column})


def arm_context_sha256(arm: dict[str, Any]) -> str:
    return canon.chash({
        "lane": arm["lane"], "condition": arm.get("condition"),
        "from_condition": arm.get("from_condition"),
        "to_condition": arm.get("to_condition"),
        "pathway_source": arm.get("pathway_source")})


def arm_identity(arm: dict[str, Any]) -> dict[str, Any]:
    """arm_key | lane | program_id | desired_change | context. NO role, NO pole, NO score."""
    return {
        "arm_key": arm["arm_key"], "lane": arm["lane"], "program_id": arm["program_id"],
        "desired_change": arm["desired_change"], "condition": arm.get("condition"),
        "from_condition": arm.get("from_condition"), "to_condition": arm.get("to_condition"),
        "pathway_source": arm.get("pathway_source"),
        "arm_context_sha256": arm_context_sha256(arm),
    }


def upstream(arm: dict[str, Any], store: dict[str, Any]) -> dict[str, Any]:
    """Every identity the row stands on — including the Stage-2 verifier that ADMITTED it.

    The verifier id and verdict are read under the keys Stage-2's loader actually emits. Reading a
    key nobody emits yields None on BOTH sides of the seam, and two lanes agreeing on None is a
    binding nobody has.
    """
    prov = arm["provenance"]
    return {
        "stage2_manifest_raw_sha256": prov.get("manifest_raw_sha256"),
        "stage2_manifest_canonical_sha256": prov.get("manifest_canonical_sha256"),
        "stage2_manifest_self_hash": prov.get("manifest_self_hash"),
        "stage2_aggregate_verifier_id": prov.get("aggregate_verifier_id"),
        "stage2_aggregate_verdict": prov.get("aggregate_verdict"),
        "stage1_release_sha256": prov.get("stage1_release_sha256"),
        "bundle_key": arm["bundle_key"],
        "bundle_raw_sha256": arm["bundle_raw_sha256"],
        "bundle_canonical_sha256": arm["bundle_canonical_sha256"],
        "ranking_raw_sha256": arm["ranking"].get("raw_sha256"),
        "ranking_canonical_sha256": arm["ranking"].get("canonical_sha256"),
        "universe_store_id": store["store_id"],
        "typed_universe_sha256": store["typed_universe_sha256"],
    }


def disposition(**row: Any) -> dict[str, Any]:
    """Every ABSENCE, NAMED: a target nobody looked up, a target with no drug evidence, an
    assertion that may never rank, and a lane nobody admitted are FOUR different facts."""
    full = {c: row.get(c) for c in T.DISPOSITION_COLUMNS if c != "disposition_id"}
    return {"disposition_id": canon.short(full), **full}


def n_ranked(records: list[dict[str, Any]]) -> int:
    """A count of RANKS, never a count of ROWS. Stage 2 RETAINS unrankable targets with a null
    rank, so "in the ranking" is NOT "in the rows" — and a count from rows inflates every hit by
    exactly the targets the arm could NOT evaluate."""
    return sum(1 for r in records if r.get("rank") is not None)


def arm_slots(arms: list[dict[str, Any]], store: dict[str, Any],
               edges: list[dict[str, Any]],
               records: dict[tuple[str, str], list[dict[str, Any]]]) -> list[dict[str, Any]]:
    by_arm: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        by_arm.setdefault(str(edge["arm_key"]), []).append(edge)

    out: list[dict[str, Any]] = []
    for arm in arms:
        mine = by_arm.get(arm["arm_key"], [])
        targets = sorted({(str(r.get("target_id")), str(r.get("target_id_namespace")))
                          for r in arm["records"]})
        in_universe = [t for t in targets if (t[1], t[0]) in store["index"]]
        assertions = [a for t in in_universe for a in records.get(t, ())]
        statuses = {str(e["directional_evidence_status"]) for e in mine}
        origin = C.ORIGIN_FOR_LANE[arm["lane"]]
        row = {
            **arm_identity(arm),
            "origin_type": origin,
            "origin_is_measured": origin in v2.MEASURED_ORIGINS,
            "condition_pair_is_ordered": arm["lane"] == C.LANE_TEMPORAL,
            "n_records": len(arm["records"]),
            # NON-NULL RANKS, never len(records).
            "n_ranked": n_ranked(arm["records"]),
            "n_targets": len(targets),
            "n_targets_in_admitted_universe": len(in_universe),
            "n_source_assertions": len(assertions),
            "n_rankable_assertions": sum(
                1 for a in assertions if a.get("general_gene_rankable") is True),
            "n_edges": len(mine),
            # NAMED, not merely zero.
            "arm_evidence_state": (C.summary_state(statuses) if mine
                                   else T.NO_DRUG_EVIDENCE),
            "directional_evidence_statuses": sorted(statuses),
            "target_ids": sorted({t for t, _ns in targets}),
            **upstream(arm, store),
        }
        row["arm_slot_id"] = _short(row, T.ARM_SLOT_COLUMNS, "arm_slot_id")
        out.append(row)
    return sorted(out, key=lambda r: str(r["arm_slot_id"]))


def arm_summaries(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per (candidate, ARM, ORIGIN). Nothing is pooled: a contradiction is PRESERVED."""
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for edge in edges:
        grouped.setdefault((str(edge["active_moiety_id"]), str(edge["arm_key"]),
                            str(edge["origin_type"])), []).append(edge)

    out: list[dict[str, Any]] = []
    for (mid, _arm_key, origin), group in sorted(grouped.items()):
        statuses = [str(e["directional_evidence_status"]) for e in group]
        row = {c: group[0].get(c) for c in T.ARM_IDENTITY_COLUMNS}
        row.update({
            "candidate_id": mid, "active_moiety_id": mid, "origin_type": origin,
            "arm_evidence_state": C.summary_state(set(statuses)),
            "n_edges": len(group),
            "n_observed_perturbation": statuses.count(policy.OBSERVED_PERTURBATION),
            "n_inverse_direction_hypothesis": statuses.count(
                policy.INVERSE_DIRECTION_HYPOTHESIS),
            "n_pathway_hypothesis": statuses.count(policy.PATHWAY_HYPOTHESIS),
            "n_opposed": statuses.count(policy.OPPOSED),
            "n_unresolved": statuses.count(policy.UNRESOLVED),
            "observed_perturbation_support": any(
                bool(e["observed_perturbation_support"]) for e in group),
            "stage3_evidence_classes": sorted({str(e["stage3_evidence_class"])
                                               for e in group}),
            "evidence_relations": sorted({str(e["evidence_relation"]) for e in group}),
            "evidence_is_equivalence": S.EVIDENCE_IS_EQUIVALENCE,
            "evidence_relation_caveat": S.PHENOCOPY_CAVEAT,
            "mechanism_match_statuses": sorted({str(e["mechanism_match_status"])
                                                for e in group}),
            "n_edges_by_mechanism_match": {
                m: sum(1 for e in group if e["mechanism_match_status"] == m)
                for m in S.MATCH_STATUSES},
            "observed_perturbation_modalities": sorted(
                {str(e["observed_perturbation_modality"]) for e in group}),
            "observed_sign_states": sorted({str(e["observed_sign_state"]) for e in group}),
            "desired_target_modulations": sorted({str(e["desired_target_modulation"])
                                                  for e in group}),
            "edge_ids": sorted(str(e["edge_id"]) for e in group),
            "arm_ranks": sorted({int(e["arm_rank"]) for e in group
                                 if e["arm_rank"] is not None}),
            "target_ids": sorted({str(e["target_id"]) for e in group}),
        })
        row["arm_summary_id"] = _short(row, T.ARM_SUMMARY_COLUMNS, "arm_summary_id")
        out.append(row)
    return out


def _keys_with_state(summaries: list[dict[str, Any]], state: str) -> list[str]:
    return sorted({str(s["arm_key"]) for s in summaries
                   if s["arm_evidence_state"] == state})


def _identity_status(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return "unresolved"
    statuses = {vs.identity_status(s) for s in sources}
    if statuses == {"resolved"}:
        return "resolved"
    if "resolved" in statuses:
        return "ambiguous"
    return sorted(statuses)[0]


def candidates(*, artifact_class: str, edges: list[dict[str, Any]],
                summaries: list[dict[str, Any]],
                source_records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable active-moiety candidates. NO winner, NO rank, NO cross-origin total."""
    by_moiety: dict[str, list[dict[str, Any]]] = {}
    for edge in edges:
        by_moiety.setdefault(str(edge["active_moiety_id"]), []).append(edge)
    summaries_by: dict[str, list[dict[str, Any]]] = {}
    for summary in summaries:
        summaries_by.setdefault(str(summary["candidate_id"]), []).append(summary)
    sources_by: dict[str, list[dict[str, Any]]] = {}
    for record in sorted(source_records, key=lambda r: str(r["source_record_id"])):
        sources_by.setdefault(str(record["active_moiety_id"]), []).append(record)

    out: list[dict[str, Any]] = []
    for mid in sorted(by_moiety):
        group = by_moiety[mid]
        mine = summaries_by.get(mid, [])
        sources = sources_by.get(mid, [])
        identity = _identity_status(sources)
        phases = sorted({str(s["max_phase_source"]) for s in sources
                         if s.get("max_phase_source") is not None})
        stage4, reason = C.stage4_assessment(
            artifact_class=artifact_class, identity_status=identity, active_moiety_id=mid,
            directional_statuses={str(e["directional_evidence_status"]) for e in group})
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
            # PER-ORIGIN maps. A scalar total across origins would sum a measured effect, a
            # cross-time DiD and an inference into a number with no estimand.
            "n_edges_by_origin": {o: sum(1 for e in group if e["origin_type"] == o)
                                  for o in v2.ORIGINS},
            "n_arm_summaries_by_origin": {
                o: sum(1 for s in mine if s["origin_type"] == o) for o in v2.ORIGINS},
            "arm_keys": sorted({str(e["arm_key"]) for e in group}),
            "origin_types": sorted({str(e["origin_type"]) for e in group}),
            "lanes": sorted({str(e["lane"]) for e in group}),
            "program_ids": sorted({str(e["program_id"]) for e in group}),
            "target_ids": sorted({str(e["target_id"]) for e in group}),
            "observed_perturbation_arm_keys": _keys_with_state(
                mine, policy.OBSERVED_PERTURBATION),
            "inverse_direction_hypothesis_arm_keys": _keys_with_state(
                mine, policy.INVERSE_DIRECTION_HYPOTHESIS),
            "pathway_hypothesis_arm_keys": _keys_with_state(mine, policy.PATHWAY_HYPOTHESIS),
            "opposed_arm_keys": _keys_with_state(mine, policy.OPPOSED),
            "unresolved_arm_keys": _keys_with_state(mine, policy.UNRESOLVED),
            "observed_perturbation_support": any(
                bool(e["observed_perturbation_support"]) for e in group),
            "stage3_evidence_classes": sorted({str(e["stage3_evidence_class"])
                                               for e in group}),
            "evidence_relations": sorted({str(e["evidence_relation"]) for e in group}),
            "evidence_is_equivalence": S.EVIDENCE_IS_EQUIVALENCE,
            "evidence_relation_caveat": S.PHENOCOPY_CAVEAT,
            "mechanism_match_statuses": sorted({str(e["mechanism_match_status"])
                                                for e in group}),
            "n_edges_by_mechanism_match": {
                m: sum(1 for e in group if e["mechanism_match_status"] == m)
                for m in S.MATCH_STATUSES},
            "observed_perturbation_modalities": sorted(
                {str(e["observed_perturbation_modality"]) for e in group}),
            "observed_sign_states": sorted({str(e["observed_sign_state"]) for e in group}),
            "desired_target_modulations": sorted({str(e["desired_target_modulation"])
                                                  for e in group}),
            "max_phase_sources": phases,
            "max_phase_status": T.STATED if phases else T.NOT_STATED,
            "max_phase_is_context_only": True,
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


