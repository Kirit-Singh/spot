"""Candidates, summarised per (arm, origin). There is no candidate-level winner.

A candidate is an active moiety. It does NOT have "a" direction, "a" rank or "a" score,
because the two Direct arms are two different questions and a measured target and an
inferred pathway node are two different kinds of evidence. So every candidate carries a
summary for EACH (arm, origin) it touches, and they never merge:

  * a moiety may be an ``observed_perturbation`` on ``away_from_A`` and ``opposed`` on
    ``toward_B``. Both survive. An ``opposed`` edge on one arm NEVER disqualifies the
    other arm.
  * a moiety may be an ``observed_perturbation`` on a measured gene and only a
    ``pathway_hypothesis`` on an inferred node — even the SAME gene. Both survive.

There is no combined, mean, balanced, best-of, primary, headline or overall score or
rank anywhere in this module, and no candidate-level rank field exists to hold one.
Ordering is by ``candidate_id`` (content-derived, stable). The only scientific ordering
that exists is each ARM's own nullable Direct rank, which lives on the edge.

Stage 3 reports workflow STATES (see :mod:`druglink.workflow`). It does not decide
promotion, eligibility or recommendation — that vocabulary is retired.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from . import artifact_class as ac, science_review, workflow as wf
from .armlever import ARMS
from .direction import ORIGIN_DIRECT_TARGET, ORIGIN_PATHWAY_NODE
from .mechanisms import DIRECT_GENE_LANE

ORIGINS = (ORIGIN_DIRECT_TARGET, ORIGIN_PATHWAY_NODE)


def build_arm_summaries(*, edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per (candidate, arm, ORIGIN) that has at least one edge.

    Measured-target evidence and inferred pathway-node evidence get SEPARATE rows and
    are never summed into one state.
    """
    by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    for e in edges:
        if e["active_moiety_id"]:
            by_key.setdefault((e["active_moiety_id"], e["desired_arm"],
                               e["origin_type"]), []).append(e)

    out: list[dict[str, Any]] = []
    for (mid, arm, origin), es in sorted(by_key.items()):
        direct = [e for e in es if e["lane"] == DIRECT_GENE_LANE]
        statuses = {e["directional_evidence_status"] for e in direct}
        out.append({
            "candidate_id": mid,
            "active_moiety_id": mid,
            "desired_arm": arm,
            "origin_type": origin,
            "arm_evidence_state": wf.summary_state(statuses),
            "n_edges": len(es),
            "n_direct_gene_edges": len(direct),
            # Every status is reported, INCLUDING the zeros.
            "n_observed_perturbation": sum(
                1 for e in direct
                if e["directional_evidence_status"] == wf.OBSERVED_PERTURBATION),
            "n_inverse_direction_hypothesis": sum(
                1 for e in direct
                if e["directional_evidence_status"]
                == wf.INVERSE_DIRECTION_HYPOTHESIS),
            "n_pathway_hypothesis": sum(
                1 for e in direct
                if e["directional_evidence_status"] == wf.PATHWAY_HYPOTHESIS),
            "n_opposed": sum(
                1 for e in direct
                if e["directional_evidence_status"] == wf.OPPOSED),
            "n_unresolved": sum(
                1 for e in direct
                if e["directional_evidence_status"] == wf.UNRESOLVED),
            # Only a MEASURED direct target carries observed-perturbation support.
            "observed_perturbation_support": any(
                e["observed_perturbation_support"] for e in direct),
            "edge_ids": sorted(e["edge_id"] for e in es),
            # Each arm's own Direct ranks, verbatim. Not a candidate rank.
            "arm_ranks": sorted({e["arm_rank"] for e in direct
                                 if e["arm_rank"] is not None}),
            "arm_evidence_tiers": sorted({e["arm_evidence_tier"] for e in direct}),
            "target_ensembls": sorted({e["target_ensembl"] for e in direct}),
            "action_conflict": any(e["action_conflict"] for e in es),
        })
    return out


def build(*, artifact_class: str, edges: list[dict[str, Any]],
          moieties: dict[str, dict[str, Any]], arm_summaries: list[dict[str, Any]],
          potency_rows: list[dict[str, Any]],
          reviews: Optional[dict[str, Any]] = None) -> list[dict[str, Any]]:
    ac.require(artifact_class)
    reviews = reviews or {"by_candidate": {}}

    edges_by_moiety: dict[str, list[dict[str, Any]]] = {}
    for e in edges:
        if e["active_moiety_id"]:
            edges_by_moiety.setdefault(e["active_moiety_id"], []).append(e)

    summaries_by_moiety: dict[str, list[dict[str, Any]]] = {}
    for s in arm_summaries:
        summaries_by_moiety.setdefault(s["candidate_id"], []).append(s)

    potency_by_moiety: dict[str, int] = {}
    for p in potency_rows:
        if p["active_moiety_id"]:
            potency_by_moiety[p["active_moiety_id"]] = (
                potency_by_moiety.get(p["active_moiety_id"], 0) + 1)

    out: list[dict[str, Any]] = []
    for mid in sorted(edges_by_moiety):
        moiety = moieties[mid]
        es = edges_by_moiety[mid]
        summaries = summaries_by_moiety.get(mid, [])
        direct = [e for e in es if e["lane"] == DIRECT_GENE_LANE]

        # Measured evidence can ONLY come from a perturbed direct target.
        observed_arms = sorted({s["desired_arm"] for s in summaries
                                if s["arm_evidence_state"] == wf.OBSERVED_PERTURBATION
                                and s["origin_type"] == ORIGIN_DIRECT_TARGET})
        # An inverse-direction hypothesis is a MEASURED-TARGET state (the gene was
        # perturbed; the arm just moved the undesired way). It is never observed support.
        inverse_arms = sorted({s["desired_arm"] for s in summaries
                               if s["arm_evidence_state"]
                               == wf.INVERSE_DIRECTION_HYPOTHESIS
                               and s["origin_type"] == ORIGIN_DIRECT_TARGET})
        pathway_arms = sorted({s["desired_arm"] for s in summaries
                               if s["arm_evidence_state"] == wf.PATHWAY_HYPOTHESIS
                               and s["origin_type"] == ORIGIN_PATHWAY_NODE})
        opposed_arms = sorted({s["desired_arm"] for s in summaries
                               if s["arm_evidence_state"] == wf.OPPOSED})

        statuses = {e["directional_evidence_status"] for e in direct}
        status, reason = wf.stage4_assessment(
            artifact_class=artifact_class,
            identity_status=moiety["identity_status"],
            active_moiety_id=mid,
            directional_statuses=statuses)

        # The exact ARM and MECHANISM behind each inverse-direction hypothesis, kept so
        # a reader never has to guess what the hypothesis actually rests on.
        inverse_edges = [e for e in direct
                         if e["directional_evidence_status"]
                         == wf.INVERSE_DIRECTION_HYPOTHESIS]
        inverse_support = sorted(
            ({"desired_arm": e["desired_arm"],
              "target_ensembl": e["target_ensembl"],
              "action_type_sources": list(e["action_type_sources"]),
              "intervention_effect": e["intervention_effect"],
              "assertion_ids": list(e["assertion_ids"]),
              "arm_rank": e["arm_rank"],
              "arm_evidence_tier": e["arm_evidence_tier"]}
             for e in inverse_edges),
            key=lambda r: (r["desired_arm"], r["target_ensembl"]))

        out.append({
            "candidate_id": mid,
            "active_moiety_id": mid,
            "preferred_name": moiety.get("preferred_name"),
            "identity_status": moiety["identity_status"],
            "identity_conflicts": moiety["identity_conflicts"],
            # Per (arm, origin), never merged. There is no candidate-level direction,
            # and a measurement and an inference never share a cell.
            "arm_evidence_states": [
                {"desired_arm": arm, "origin_type": origin,
                 "arm_evidence_state": next(
                     (s["arm_evidence_state"] for s in summaries
                      if s["desired_arm"] == arm and s["origin_type"] == origin),
                     "not_annotated")}
                for arm in ARMS for origin in ORIGINS],
            "observed_perturbation_arms": observed_arms,
            "inverse_direction_hypothesis_arms": inverse_arms,
            "inverse_direction_support": inverse_support,
            "pathway_hypothesis_arms": pathway_arms,
            "opposed_arms": opposed_arms,
            # A LABEL, not a tier. An inverse hypothesis never shares an evidence class
            # with a measurement, and this class is deliberately unordered.
            "stage3_evidence_classes": sorted(
                {wf.evidence_class(x) for x in statuses}),
            # The disease-context review is an ingestible RESULT, not a one-way flag.
            # With no review supplied, an inverse hypothesis stays PENDING — it never
            # defaults to favourable. A completed result must pay for itself with
            # evidence bindings that RESOLVE in the science registry.
            **science_review.for_candidate(
                reviews, mid,
                has_inverse=wf.INVERSE_DIRECTION_HYPOTHESIS in statuses),
            "form_ids": sorted({e["form_id"] for e in es}),
            "target_ensembls": sorted({e["target_ensembl"] for e in direct}),
            "n_edges": len(es),
            "n_direct_gene_edges": len(direct),
            "development_state_aggregate": moiety["development_state_aggregate"],
            "n_potency_rows": potency_by_moiety.get(mid, 0),
            # Absence of potency is NOT a favourable result.
            "potency_state": ("reported" if potency_by_moiety.get(mid)
                              else "not_evaluated"),
            # An ASSESSMENT is not promotion and not a recommendation.
            "stage4_assessment_status": status,
            "stage4_assessment_reason": reason,
            "source_record_ids": sorted(
                {s for e in es for s in e["source_record_ids"]}
                | set(moiety["source_record_ids"])),
        })
    return out


def order(candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Stable order by candidate_id. NOT a score, NOT a rank, NOT a ranking."""
    return sorted(candidates, key=lambda c: c["candidate_id"])


def not_queued(candidates: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Candidates Stage 4 is NOT asked to assess stay visible as dispositions."""
    return [{
        "subject_kind": "candidate",
        "subject_id": c["candidate_id"],
        "state": wf.NOT_QUEUED,
        "reason": c["stage4_assessment_reason"],
        "detail": f"identity={c['identity_status']}",
        "source_record_id": None,
    } for c in candidates if c["stage4_assessment_status"] == wf.NOT_QUEUED]
