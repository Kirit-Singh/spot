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
from .arm_key_codec import MembershipError
from .stage3_receipt import canonical_sha256, emitted_receipt
from .stage3_v2_membership import STORE_ROW
from .typed_membership import assert_typed_placement, require_receipt
from .stage3_v2_membership import project as project_membership

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


def build_v2_projection(scorecards: dict[str, Any],
                        store_candidates: Iterable[dict[str, Any]],
                        stage3_selection_view: dict[str, Any],
                        row_kind: str = STORE_ROW,
                        *,
                        stage3_receipt_path: Optional[str] = None,
                        stage3_bundle_dir: Optional[str] = None,
                        stage3_store_dir: Optional[str] = None,
                        arm_summaries: Optional[Iterable[dict[str, Any]]] = None,
                        ) -> dict[str, Any]:
    """THE NATIVE-v2 CONSUMER. The browser projection, filtered and flagged by VERIFIED membership.

    `build_projection` below is the v1 path: it reads `*_arms` and flags `in_active_view` from a
    Stage-4-side `SelectionView`. Stage 3 v2 emits `*_arm_keys` and its own selection view, and the
    membership claim on every displayed row must be RE-DERIVED from the store rather than believed.
    This is that entry point — `stage3_v2_membership.project` is wired in here, not left as a module
    nobody calls, because a gate with no caller is a gate that never runs.

    The store stays GLOBAL: `membership` reports out-of-view candidates rather than dropping them,
    and each displayed row carries the `membership_sha256` it was displayed UNDER. Re-point the
    projection at another selection and every hash moves.

    Native v2 ADMISSION remains closed (`stage3_v2_seam` is unpinned); this is the projection seam,
    ready for W16's pin.
    """
    # THE RECEIPT, first. Stage 4 does not re-verify Stage 3 — Stage 3's own verifier does, out of
    # process — but it will not display rows from a bundle whose verification it cannot NAME. The
    # receipt VALUES are W16's; the requirement is Stage 4's, and it is not skippable.
    receipt, bound_view = require_receipt(stage3_receipt_path, stage3_bundle_dir, stage3_store_dir)

    # EVERYTHING PROJECTED COMES FROM THE RECEIPT-LOADED VIEW. Nothing comes from the caller.
    #
    # THE ATTACK THIS CLOSES. The receipt was loaded, every hash was recomputed from disk — and then
    # the projection went ahead and used the `stage3_selection_view` the CALLER passed in. Changing
    # one field of that copy (`selection.question_id` -> "FORGED_QUESTION_ID") while the on-disk
    # receipt and view stayed untouched was ADMITTED, and the forged question was emitted into the
    # document. The receipt bound bytes that nobody then used: verification of one object, display
    # of another.
    bound_tables = bound_view.get("tables") or {}

    # A caller MAY pass its copies — they must be canonically IDENTICAL to the bound bytes. Anything
    # else is refused by name rather than silently preferred.
    _assert_is_the_bound_copy("stage3_selection_view", stage3_selection_view, bound_view)
    stage3_selection_view = bound_view

    bound_candidates = list(bound_tables.get("candidates") or [])
    _assert_is_the_bound_copy("store_candidates", list(store_candidates or []), bound_candidates)

    stage3_rows = bound_candidates
    scorecard_rows = list(scorecards.get("candidates", []))
    summaries = list(bound_tables.get("arm_summaries") or [])
    if arm_summaries is not None:
        _assert_is_the_bound_copy("arm_summaries", list(arm_summaries), summaries)

    # A dict join SILENTLY COLLAPSES a duplicate id — the second row overwrites the first and the
    # count still looks right. Uniqueness is asserted on BOTH sides before anything is joined.
    _assert_unique_ids(stage3_rows, "stage3", "stage3_candidate_ids_are_not_unique")
    _assert_unique_ids(scorecard_rows, "stage4 scorecard",
                       "stage4_scorecard_candidate_ids_are_not_unique")

    # EVERY typed arm placement is corroborated against `arm_summaries` — the independent, per-arm
    # statement of the same fact. Moving an arm between typed columns leaves the union identical, so
    # every set-based check passes; the counts, computed from the edges, do not.
    if not summaries:
        raise MembershipError(
            "stage4_projection_carries_no_arm_summaries",
            "no `arm_summaries` were supplied, so no typed arm placement can be corroborated. "
            "Without them an OPPOSED arm renamed into `observed_perturbation_arm_keys` keeps the "
            "same union and passes every set-based check in this module.",
        )
    membership = project_membership(stage3_rows, stage3_selection_view, row_kind)

    # SCOPED to the arms this selection actually activated. An inactive arm is never displayed,
    # never hashed and cannot promote anything, and corroborating all ~180 global arms per candidate
    # would be paid on every render.
    active: dict[str, set[str]] = {
        r["candidate_id"]: {k for keys in r["arm_keys_by_column"].values() for k in keys}
        for r in membership["displayed"] + membership["out_of_view"]
    }
    typed_checked = sum(
        assert_typed_placement(c, summaries,
                               active.get(str(c.get("candidate_id")), set())
                               )["typed_arm_placements_checked"]
        for c in stage3_rows)
    by_candidate = {r["candidate_id"]: r
                    for r in membership["displayed"] + membership["out_of_view"]}

    # Every Stage-4 scorecard candidate must resolve EXACTLY ONCE to an ADMITTED Stage-3 candidate.
    # A scorecard row with no Stage-3 candidate is a drug Stage 4 scored that the admitted universe
    # never contained — the projection would display evidence about a candidate no upstream stage
    # ever admitted, and `.get()` returning None would render it as merely "out of view".
    foreign = sorted(str(c.get("candidate_id")) for c in scorecard_rows
                     if c.get("candidate_id") not in by_candidate)
    if foreign:
        raise MembershipError(
            "stage4_scorecard_candidate_is_not_in_the_admitted_stage3_universe",
            f"{len(foreign)} Stage-4 scorecard candidate(s) do not appear in the admitted Stage-3 "
            f"candidate set: {foreign[:5]}. A candidate Stage 4 scored that Stage 3 never admitted "
            "is not 'out of view' — it is evidence about a drug that entered the pipeline from "
            "somewhere else, and out_of_view is permitted ONLY for a candidate that exists upstream.",
            {"foreign_candidate_ids": foreign[:10]},
        )

    displayed_ids = {r["candidate_id"] for r in membership["displayed"]}
    candidates = []
    for native in scorecard_rows:
        cid = native.get("candidate_id")
        row: dict[str, Any] = {"candidate_id": cid}
        for field in NESTED_CANDIDATE_FIELDS:
            if field in native:
                row[field] = native[field]

        hit = by_candidate[cid]                      # resolves, or we refused above
        row["in_active_view"] = cid in displayed_ids
        # The membership a row was DISPLAYED under, bound into the row itself.
        row["stage3_v2_membership"] = hit
        candidates.append(row)

    _reconcile(len(scorecard_rows), candidates, displayed_ids)

    doc = {
        "schema_id": BROWSER_PROJECTION_SCHEMA,
        "scorecard_set_id": scorecards.get("scorecard_set_id"),
        "stage3_v2_selection": membership["selection"],
        "stage3_v2_membership_contract": membership["contract"],
        # The CLEAN receipt: authoritative fields and bound identities only. Not the view, not the
        # table rows, and no internal handle — a Stage-4 artifact carrying a copy of Stage 3's whole
        # view would be a second, unverified copy of it wearing Stage 3's identity.
        "stage3_receipt": emitted_receipt(receipt, bound_view),
        "typed_arm_placements_corroborated": typed_checked,
        "candidates": candidates,
        "counts": {
            # The rows came from the selection VIEW, which Stage 3 already filtered to this
            # selection. Naming them `n_stage3_admitted` and flagging the store "global and not
            # filtered" was a claim about bytes Stage 4 never loaded: the global store is the
            # universe of ALL candidates, and this is a projection of one selection's slice of it.
            "n_stage3_view_candidates": len(stage3_rows),
            "n_stage4_scorecards": len(scorecard_rows),
            "n_displayed": sum(1 for c in candidates if c["in_active_view"]),
            "n_out_of_view": sum(1 for c in candidates if not c["in_active_view"]),
        },
        "source_is_selection_view": True,
        # Only a run that actually LOADS and HASHES the global store may claim to have projected it.
        "store_is_global_and_was_not_filtered": bool(stage3_store_dir),
    }
    return doc


def _assert_is_the_bound_copy(name: str, supplied: Any, bound: Any) -> None:
    """A caller copy is permitted only if it is canonically IDENTICAL to the hash-bound bytes.

    Not "close", not "a superset", not "the same ids" — identical under the canonical form the
    receipt hashes. One changed field is the whole attack: it is what turns a verified document into
    a decoration beside the one actually rendered.
    """
    if supplied is None or supplied == []:
        return
    if canonical_sha256(supplied) != canonical_sha256(bound):
        raise MembershipError(
            "stage4_caller_copy_is_not_the_hash_bound_artifact",
            f"the {name} passed in by the caller is not the {name} the receipt binds. Stage 4 "
            "projects the RECEIPT-LOADED bytes; a caller copy that differs by even one field means "
            "one document was verified and another was displayed — which is the whole of the "
            "attack, not a detail of it.",
            {"artifact": name},
        )


def _assert_unique_ids(rows: list[dict[str, Any]], side: str, code: str) -> None:
    """Duplicate ids are refused BEFORE the join, not discovered after it.

    A dict join is silent about duplicates: `{r["candidate_id"]: r for r in rows}` keeps the LAST
    row and drops the rest, with no error and no count anomaly on the surviving side. Two different
    candidates sharing an id would have one of them quietly replaced by the other's evidence.
    """
    seen: set[str] = set()
    dupes: set[str] = set()
    for row in rows:
        cid = str(row.get("candidate_id") or "")
        if not cid:
            raise MembershipError(
                code, f"a {side} candidate row carries no candidate_id, so it can be joined to "
                      "nothing and would be silently dropped by a dict join.")
        (dupes if cid in seen else seen).add(cid)

    if dupes:
        raise MembershipError(
            code,
            f"{len(dupes)} duplicate {side} candidate id(s): {sorted(dupes)[:5]}. A dict join keeps "
            "the LAST row and silently discards the rest — two different candidates sharing an id "
            "means one of them is displayed carrying the other's evidence, and no count anywhere "
            "would look wrong.",
            {"duplicate_candidate_ids": sorted(dupes)[:10]},
        )


def _reconcile(n_scorecards: int, candidates: list[dict[str, Any]],
               displayed_ids: set[str]) -> None:
    """displayed + out_of_view must equal the input, EXACTLY. Counted, not assumed.

    Every row that went in comes out as exactly one of the two. A row that is neither has vanished,
    and a vanished row and a row that never existed look identical in the emitted document.
    """
    n_in = sum(1 for c in candidates if c["in_active_view"])
    n_out = len(candidates) - n_in

    if len(candidates) != n_scorecards or n_in + n_out != n_scorecards:
        raise MembershipError(
            "stage4_projection_counts_do_not_reconcile",
            f"{n_scorecards} scorecard candidate(s) went in and {n_in} displayed + {n_out} "
            f"out-of-view = {len(candidates)} came out. Every row must be exactly one of the two: a "
            "row that is neither has silently vanished, and a vanished row is indistinguishable "
            "from a row that never existed.",
            {"n_in": n_scorecards, "n_displayed": n_in, "n_out_of_view": n_out},
        )


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
