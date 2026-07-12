"""Workflow-state checks: statuses, the retired vocabulary, Stage-2 joint context.

Split out of :mod:`verifier.checks` to keep both modules small. Every rule here is
RESTATED in :mod:`verifier.policy` and re-derived — never read back from the bundle.
"""
from __future__ import annotations

from typing import Any

from . import policy
from .report import Report


# --------------------------------------------------------------------------- #
# 4. Research eligibility is not promotion eligibility.
# --------------------------------------------------------------------------- #
def check_workflow(rep: Report, *, doc: dict[str, Any], artifact_class: str,
                      candidates: list[dict[str, Any]],
                      edges: list[dict[str, Any]],
                      moieties: list[dict[str, Any]]) -> None:
    # The RETIRED promotion/eligibility vocabulary may not appear ANYWHERE.
    retired = policy.retired_keys_in(doc)
    rep.check("the document carries NO retired promotion/eligibility field at any "
              "depth (production_candidate / production_promotion_eligible / "
              "may_write_production_pointer / production_pointer_written / "
              "research_pk_annotation_eligible / namespace)",
              not retired, str(retired[:5]))
    retired_rows = sorted({k for c in candidates for k in c
                           if k in policy.RETIRED_KEYS})
    rep.check("no candidate row carries a retired promotion/eligibility field",
              not retired_rows, str(retired_rows))
    rep.check("no promotion-pointer FILE key exists in the document",
              not policy.production_pointer_keys_in(doc))

    # Stage-2 joint context is republished, but never used to infer direction.
    joint = doc.get("stage2_joint_context") or {}
    rep.check("Stage-2 joint context is declared as CONTEXT, never as direction",
              joint.get("used_to_infer_drug_direction") is False
              and joint.get("used_to_rank_or_filter_arms") is False,
              str(joint))
    # pareto_tier IS numeric — a positive-integer tier LABEL from 1, or null. That is
    # the canonical Stage-2 type and is NOT a combined score. What stays refused is a
    # numeric combined objective (combined_score / balanced_skew / a weighted sum), and
    # those are caught by the banned-key/column checks.
    tier = joint.get("pareto_tier")
    rep.check("pareto_tier is a positive integer from 1, or absent/null",
              tier in (None, "not_provided")
              or (isinstance(tier, int) and not isinstance(tier, bool) and tier >= 1),
              f"pareto_tier={tier!r}")
    jstatus = joint.get("joint_status")
    rep.check("joint_status is one of the canonical Stage-2 enum values",
              jstatus in (None, "not_provided") or jstatus in policy.JOINT_STATUS_VALUES,
              f"joint_status={jstatus!r}")
    method = joint.get("joint_ordering_method_id")
    rep.check("joint_ordering_method_id is a string", isinstance(method, (str, type(None))),
              f"joint_ordering_method_id={method!r}")
    rep.check("Stage 3 never rewrites Direct ranks or Stage-2 Pareto tiers",
              joint.get("rewritten_by_stage3") in (False, None))

    status = {m["active_moiety_id"]: m["identity_status"] for m in moieties}
    by_moiety: dict[str, set[str]] = {}
    for e in edges:
        if e["lane"] == policy.DIRECT_GENE_LANE:
            by_moiety.setdefault(e["active_moiety_id"], set()).add(
                e["directional_evidence_status"])

    bad = []
    for c in candidates:
        want, want_reason = policy.stage4_status(
            identity_status=status.get(c["active_moiety_id"], "unresolved"),
            moiety_id=c["active_moiety_id"],
            statuses=by_moiety.get(c["active_moiety_id"], set()))
        if artifact_class == "fixture":
            want = policy.NOT_QUEUED       # a fixture never reaches Stage 4
        if c["stage4_assessment_status"] != want:
            bad.append(f"{c['candidate_id']}: emitted "
                       f"{c['stage4_assessment_status']}, want {want}")
        # A candidate queued ON an inverse-direction hypothesis must SAY so.
        if (want == policy.QUEUED and want_reason == policy.REASON_QUEUED_INVERSE
                and artifact_class != "fixture"
                and c["stage4_assessment_reason"] != policy.REASON_QUEUED_INVERSE):
            bad.append(f"{c['candidate_id']}: queued on an inverse-direction "
                       f"hypothesis but reason is {c['stage4_assessment_reason']!r}")
    rep.check("stage4_assessment_status re-derives from identity + directional "
              "evidence (an assessment is not promotion and not a recommendation)",
              not bad, "; ".join(bad[:3]))

    # An inverse hypothesis awaits a Claude Science disease-context review. Un-reviewed,
    # it is PENDING and stays pending — Stage 3 never judges it, and never lets the
    # absence of a review read as a favourable one.
    review_bad = [
        c["candidate_id"] for c in candidates
        if c["disease_context_review_status"] != policy.REVIEW_COMPLETED
        and c["disease_context_review_status"] != policy.baseline_review_status(
            by_moiety.get(c["active_moiety_id"], set()))]
    rep.check("every un-reviewed inverse-direction candidate is PENDING a Claude Science "
              "disease-context review (Stage 3 flags, it does not judge)",
              not review_bad, f"{len(review_bad)} candidate(s)")

    # A result outside the closed enum, or a result on a review that is not completed.
    result_bad = [
        c["candidate_id"] for c in candidates
        if (c["disease_context_review_status"] == policy.REVIEW_COMPLETED)
        != (c["disease_context_review_result"] in policy.REVIEW_RESULTS)]
    rep.check("a review result exists if and ONLY if the review is completed (a pending "
              "review has no verdict to drift)", not result_bad,
              f"{len(result_bad)} candidate(s)")

    # A candidate supported on one arm and opposed on the other keeps BOTH edges, and
    # a measured target and an inferred pathway node never share a cell.
    per_arm: dict[str, dict[tuple[str, str], set[str]]] = {}
    for e in edges:
        if e["lane"] == policy.DIRECT_GENE_LANE:
            per_arm.setdefault(e["active_moiety_id"], {}).setdefault(
                (e["desired_arm"], e["origin_type"]), set()).add(
                    e["directional_evidence_status"])
    state_bad = []
    for c in candidates:
        arms = {(a["desired_arm"], a["origin_type"]): a["arm_evidence_state"]
                for a in c["arm_evidence_states"]}
        for key, statuses in per_arm.get(c["candidate_id"], {}).items():
            want = policy.arm_evidence_state(statuses)
            if arms.get(key) != want:
                state_bad.append(f"{c['candidate_id']}/{key}: {arms.get(key)} != {want}")
    rep.check("each candidate's per-(arm, origin) state re-derives from that arm's own "
              "edges (a conflict is preserved, never resolved into a winner)",
              not state_bad, "; ".join(state_bad[:3]))

    # Measured evidence can ONLY come from a perturbed direct target.
    liars = [e["edge_id"] for e in edges
             if e["observed_perturbation_support"]
             and e["origin_type"] != policy.ORIGIN_DIRECT_TARGET]
    rep.check("no pathway node carries MEASURED evidence (it was never perturbed)",
              not liars, f"{len(liars)} edge(s)")
