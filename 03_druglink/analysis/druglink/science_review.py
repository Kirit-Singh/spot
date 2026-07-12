"""The disease-context review: an ingestible RESULT, not a pending flag.

Stage 3 used to carry a one-way flag — ``pending_claude_science_plausibility_review``.
It could be set, and nothing could ever be done with it: there was no shape for a
COMPLETED review to arrive in, so a review that had actually been done had nowhere to
land. A flag that can only ever say "not yet" is not a contract.

A completed review now arrives as a typed result:

    review_result ∈ {supportive, contradictory, mixed, insufficient}

and it must PAY for the claim. ``supportive`` / ``contradictory`` / ``mixed`` are
substantive findings, so each must carry Claude Science evidence bindings — the typed
``{science_evidence_id, science_evidence_sha256, record_type}`` triples — and **every
one of them must resolve and re-hash in the registry** (``druglink.science_registry``).

The failure modes this closes, and how:

  * **A review that cites nothing.** ``supportive`` with zero bindings would be an
    opinion wearing the costume of a finding. It is DOWNGRADED to ``insufficient``, with
    a reason code. It is never favourable by default.
  * **A review whose evidence does not resolve.** A dangling or altered record is a
    typed REFUSAL — the review is not accepted at all. Silently keeping the favourable
    verdict while dropping the evidence is exactly the failure this exists to prevent.
  * **A pending review drifting favourable.** ``pending`` has no ``review_result``, and
    there is no code path that gives it one. It stays pending.

``insufficient`` is a real, sayable outcome. It is not a failure of the reviewer and it
is not a soft yes.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from . import science_registry as sr

REVIEW_SCHEMA = "spot.stage03_disease_context_review.v1"
REVIEW_POLICY_VERSION = "stage3-disease-context-review-v1-result-not-a-flag"

# review_status (closed)
PENDING = "pending"
COMPLETED = "completed"
NOT_REQUIRED = "not_required"
REVIEW_STATUSES = (PENDING, COMPLETED, NOT_REQUIRED)

# review_result (closed). Only ever set when review_status == completed.
SUPPORTIVE = "supportive"
CONTRADICTORY = "contradictory"
MIXED = "mixed"
INSUFFICIENT = "insufficient"
REVIEW_RESULTS = (SUPPORTIVE, CONTRADICTORY, MIXED, INSUFFICIENT)

# The substantive findings. Each must be paid for with resolvable evidence bindings.
SUBSTANTIVE_RESULTS = frozenset({SUPPORTIVE, CONTRADICTORY, MIXED})

# Compact reason codes.
REASON_COMPLETED = "completed_with_resolved_evidence_bindings"
REASON_DOWNGRADED_NO_BINDINGS = "downgraded_to_insufficient_no_evidence_bindings"
REASON_PENDING = "awaiting_claude_science_disease_context_review"
REASON_NOT_REQUIRED = "no_inverse_direction_hypothesis_to_review"
REVIEW_REASONS = (REASON_COMPLETED, REASON_DOWNGRADED_NO_BINDINGS, REASON_PENDING,
                  REASON_NOT_REQUIRED)

NOT_PROVIDED = {"disease_context_review": "not_provided", "n_reviews": 0}


class ReviewError(ValueError):
    """A disease-context review is malformed, or claims more than its evidence pays for."""


def load(path: Optional[str], *, artifact_class: str, direct,
         science_registry_root: Optional[str] = None) -> dict[str, Any]:
    """Admit a disease-context review document, or record an explicitly absent lane."""
    if not path:
        return {"by_candidate": {}, "ref": dict(NOT_PROVIDED)}
    with open(path, "r", encoding="utf-8") as fh:
        doc = json.load(fh)
    return admit(doc, artifact_class=artifact_class, direct=direct,
                 science_registry_root=science_registry_root)


def admit(doc: dict[str, Any], *, artifact_class: str, direct,
          science_registry_root: Optional[str] = None) -> dict[str, Any]:
    if not isinstance(doc, dict):
        raise ReviewError("the disease-context review must be a JSON object")
    if doc.get("schema_version") != REVIEW_SCHEMA:
        raise ReviewError(
            f"disease-context review schema_version={doc.get('schema_version')!r}; "
            f"Stage 3 consumes {REVIEW_SCHEMA!r}")
    if doc.get("artifact_class") != artifact_class:
        raise ReviewError(
            f"{artifact_class} refuses a review declaring "
            f"artifact_class={doc.get('artifact_class')!r}")
    if doc.get("direct_run_id") != direct.run_id:
        raise ReviewError(
            f"the review was written against Direct run {doc.get('direct_run_id')!r}, "
            f"but this run admitted {direct.run_id!r}; it reviews a different question")

    by_candidate: dict[str, dict[str, Any]] = {}
    n_downgraded = 0

    for review in doc.get("reviews") or []:
        candidate_id = str(review.get("candidate_id") or "")
        if not candidate_id:
            raise ReviewError("every review must name a candidate_id")
        if candidate_id in by_candidate:
            raise ReviewError(
                f"duplicate review for candidate {candidate_id!r}. Two verdicts for one "
                "candidate is not a review, it is a choice — and Stage 3 does not make "
                "it.")

        status = review.get("review_status")
        if status not in REVIEW_STATUSES:
            raise ReviewError(
                f"{candidate_id}: review_status must be one of {list(REVIEW_STATUSES)}; "
                f"got {status!r}")

        if status != COMPLETED:
            # A pending review carries no result, and there is no path that gives it one.
            if review.get("review_result") is not None:
                raise ReviewError(
                    f"{candidate_id}: review_status={status!r} carries a review_result. "
                    "Only a COMPLETED review has a result; a pending review that "
                    "declares one is claiming a finding it has not made.")
            by_candidate[candidate_id] = {
                "disease_context_review_status": status,
                "disease_context_review_result": None,
                "disease_context_review_reason": REASON_PENDING,
                "disease_context_review_evidence_refs": [],
                "disease_context_reviewed_by": None,
            }
            continue

        result = review.get("review_result")
        if result not in REVIEW_RESULTS:
            raise ReviewError(
                f"{candidate_id}: a COMPLETED review must carry review_result in "
                f"{list(REVIEW_RESULTS)}; got {result!r}")

        where = f"review[{candidate_id}]"
        refs = sr.check_refs(where, review.get("review_evidence_refs"))
        # A dangling or ALTERED record is a typed refusal. The favourable verdict is not
        # quietly kept while the evidence under it is dropped.
        sr.resolve_all(science_registry_root, refs, where=where)

        reason = REASON_COMPLETED
        if result in SUBSTANTIVE_RESULTS and not refs:
            # A substantive finding that cites nothing is an opinion. Downgrade it —
            # never favourable by default.
            result = INSUFFICIENT
            reason = REASON_DOWNGRADED_NO_BINDINGS
            n_downgraded += 1

        by_candidate[candidate_id] = {
            "disease_context_review_status": COMPLETED,
            "disease_context_review_result": result,
            "disease_context_review_reason": reason,
            "disease_context_review_evidence_refs": refs,
            "disease_context_reviewed_by": _reviewed_by(candidate_id, review),
        }

    ref = {
        "disease_context_review": "provided",
        "review_policy_version": REVIEW_POLICY_VERSION,
        "review_document_sha256": sr.canonical_sha256(doc),
        "n_reviews": len(by_candidate),
        "n_completed": sum(1 for r in by_candidate.values()
                           if r["disease_context_review_status"] == COMPLETED),
        "n_downgraded_to_insufficient": n_downgraded,
        "evidence_bindings_are_resolved_and_rehashed": True,
        "a_substantive_result_requires_resolvable_evidence": True,
        "a_pending_review_can_never_become_favourable": True,
    }
    return {"by_candidate": by_candidate, "ref": ref}


def _reviewed_by(candidate_id: str, review: dict[str, Any]) -> dict[str, str]:
    who = review.get("reviewed_by") or {}
    for field in ("session_id", "model_id", "method_id"):
        if not who.get(field):
            raise ReviewError(
                f"{candidate_id}: a COMPLETED review must state reviewed_by.{field}. A "
                "verdict nobody can be attributed to is not a review.")
    return {f: str(who[f]) for f in ("session_id", "model_id", "method_id")}


def for_candidate(reviews: dict[str, Any], candidate_id: str,
                  has_inverse: bool) -> dict[str, Any]:
    """The review block a candidate carries.

    With no supplied review, a candidate carrying an inverse-direction hypothesis is
    PENDING — and stays pending. It never defaults to favourable, and never to
    ``not_required``.
    """
    supplied = (reviews.get("by_candidate") or {}).get(candidate_id)
    if supplied is not None:
        return dict(supplied)
    if has_inverse:
        return {
            "disease_context_review_status": PENDING,
            "disease_context_review_result": None,
            "disease_context_review_reason": REASON_PENDING,
            "disease_context_review_evidence_refs": [],
            "disease_context_reviewed_by": None,
        }
    return {
        "disease_context_review_status": NOT_REQUIRED,
        "disease_context_review_result": None,
        "disease_context_review_reason": REASON_NOT_REQUIRED,
        "disease_context_review_evidence_refs": [],
        "disease_context_reviewed_by": None,
    }


def vocabularies() -> dict[str, Any]:
    return {
        "review_policy_version": REVIEW_POLICY_VERSION,
        "review_schema": REVIEW_SCHEMA,
        "review_statuses": list(REVIEW_STATUSES),
        "review_results": list(REVIEW_RESULTS),
        "substantive_results": sorted(SUBSTANTIVE_RESULTS),
        "review_reasons": list(REVIEW_REASONS),
        "a_substantive_result_requires_resolvable_evidence_bindings": True,
        "a_result_that_cites_nothing_is_downgraded_to_insufficient": True,
        "a_pending_review_can_never_become_favourable": True,
        "unresolvable_evidence_is_a_typed_refusal_not_a_warning": True,
    }
