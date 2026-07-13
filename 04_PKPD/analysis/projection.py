"""The browser projection — `spot.stage04_browser_projection.v1`.

The store is GLOBAL and selection-independent: the whole admitted Stage-3 candidate universe,
acquired once. Selection is a PROJECTION over it. So the browser needs two things Stage 4 was not
giving it, and this module gives both.

**1. Candidate → arm membership, in the release.**
The native scorecards carry `candidate_id`, `active_moiety`, `lanes`… and NOT the arms the
candidate sits on. Stage 3 knows them; Stage 4 dropped them at the `Stage3Candidate` boundary. So a
browser wanting to answer a different selection had no way to filter — it would need a full rerun,
which means re-acquiring public evidence Stage 4 already holds. Arm membership travels with the
candidate here, and every selection becomes a client-side filter.

**2. The nested shape, PRESERVED. Nothing stringified.**
`active_moiety`, `compound_ids`, `production_eligible` and every lane are OBJECTS, and
`provenance_chain` is a list of objects. Flattening them into strings for a UI is not a formatting
choice — it is destruction of evidence:

  * a nested `null` means NOT EVALUATED, and `str(None)` is the string `"None"`, which is a value;
  * `{"status": "incomplete", "total": null}` stringified reads as a score;
  * a lane object's own missing-value semantics — the whole point of this stage — collapse into
    prose the browser then has to parse back, badly.

So the projection copies the native objects through, verbatim, and a test asserts no leaf was turned
into a string and no `null` was turned into anything else. **Missing stays missing, nested.**

The projection carries no ranking and no combined score, and the engine's firewall still applies to
it: what a browser cannot receive, a browser cannot render.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, Iterable, Optional

from .selection_view import SelectionView, candidate_arms, in_view

BROWSER_PROJECTION_SCHEMA = "spot.stage04_browser_projection.v1"

# Copied through as OBJECTS, never flattened. Each is a shape whose nesting carries meaning.
NESTED_CANDIDATE_FIELDS = (
    "active_moiety",        # object: id, name, unii, inchikey, administered form…
    "compound_ids",         # object: chembl_id, pubchem_cid, rxcui… (a null is "no such id")
    "production_eligible",  # object: {eligible: bool, reasons: [...]} — never a bare bool
    "lanes",                # object of lane objects, each with its own missing-value semantics
    "provenance_chain",     # list of objects: field -> source hash -> transform
    "mechanism",
    "target",
    "direction_compatibility",
)


def _arm_membership(queued: Any) -> dict[str, Any]:
    """Stage 3's arm placement for one candidate, carried whole.

    All four columns, not just the obvious one: a candidate can be placed on an arm by an observed
    perturbation, an inverse-direction hypothesis, a pathway hypothesis, or by being opposed. They
    are DIFFERENT claims and they are kept apart — an observed knockdown direction and a proposed
    inverse-direction hypothesis are not the same evidence, and merging them into one arm list
    would be the fusion Stage 3 refuses to make.
    """
    row = {
        "observed_perturbation_arms": list(getattr(queued, "observed_perturbation_arms", []) or []),
        "inverse_direction_hypothesis_arms": list(
            getattr(queued, "inverse_direction_hypothesis_arms", []) or []),
        "pathway_hypothesis_arms": list(getattr(queued, "pathway_hypothesis_arms", []) or []),
        "opposed_arms": list(getattr(queued, "opposed_arms", []) or []),
    }
    row["arms"] = sorted(candidate_arms(row))
    # `ArmEvidence` is a frozen dataclass, not a pydantic model. Carried as an OBJECT either way:
    # its per-arm evidence state is exactly the nested meaning that must not be flattened.
    row["arm_evidence_states"] = [
        e if isinstance(e, dict) else asdict(e)
        for e in (getattr(queued, "arm_evidence_states", []) or [])
    ]
    return row


def build_projection(scorecards: dict[str, Any],
                     queued: Iterable[Any],
                     view: Optional[SelectionView] = None) -> dict[str, Any]:
    """The global store + arm provenance + (optionally) the active selection's membership.

    `view` does NOT filter the projection. Every candidate in the store is present, with its arms,
    so the browser can answer ANY selection without a rerun. When a view is supplied, each candidate
    is additionally flagged `in_active_view`, and the active view is named — a convenience, never a
    gate.
    """
    arms_by_candidate = {q.candidate_id: _arm_membership(q) for q in queued}

    candidates = []
    for native in scorecards.get("candidates", []):
        cid = native.get("candidate_id")
        membership = arms_by_candidate.get(cid, {"arms": []})

        # The native objects, COPIED THROUGH. Not stringified, not flattened, not re-rounded. A
        # nested null is NOT_EVALUATED and it stays a null.
        row: dict[str, Any] = {"candidate_id": cid}
        for field in NESTED_CANDIDATE_FIELDS:
            if field in native:
                row[field] = native[field]

        row["stage3_arm_membership"] = membership
        if view is not None:
            row["in_active_view"] = in_view(membership, view)
        candidates.append(row)

    doc: dict[str, Any] = {
        "schema_id": BROWSER_PROJECTION_SCHEMA,
        "scorecard_set_id": scorecards.get("scorecard_set_id"),
        "upstream": scorecards.get("upstream"),
        # The GLOBAL store. Not a singleton selection.
        "store_is_selection_independent": True,
        "candidates": sorted(candidates, key=lambda c: str(c.get("candidate_id"))),
        "ordering": scorecards.get("ordering"),
        "guards": scorecards.get("guards"),
        "is_ranking": False,
    }
    if view is not None:
        doc["active_selection_view"] = view.as_document()
        doc["active_view_candidate_ids"] = [
            c["candidate_id"] for c in doc["candidates"] if c.get("in_active_view")]
    return doc
