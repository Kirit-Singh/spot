"""An active arm sits in EXACTLY the typed column its evidence state maps to — and in none of the other four.

THE DEFECT THIS REPLACES. The first version asked each column "is your count positive?" So an arm
listed in BOTH `observed_perturbation_arm_keys` AND `opposed_arm_keys`, whose summary reported
`n_observed_perturbation=1, n_opposed=1`, satisfied both questions and was ADMITTED — reported as two
corroborated placements. It is one arm. It cannot simultaneously be a measured perturbation in the
wanted direction and evidence pointing the wrong way; the summary itself calls that state
`conflicting`. Asking "is this column plausible?" five times can never establish that exactly one is
right, and a check that admits a contradiction is not a check.

THE RULE, W16's, not Stage-4's (`candidate_membership.MEMBERSHIP_FOR_STATE`, inverted). The arm's
`arm_evidence_state` is AUTHORITATIVE and maps to exactly one column:

    observed_perturbation          -> observed_perturbation_arm_keys
    inverse_direction_hypothesis   -> inverse_direction_hypothesis_arm_keys
    pathway_hypothesis             -> pathway_hypothesis_arm_keys
    opposed                        -> opposed_arm_keys
    unresolved                     -> unresolved_arm_keys

The arm must be IN that column and ABSENT from the other four. Moving an unchanged arm between
columns changes what the drug is being said to DO while the arm set — and every hash over it — stays
exactly as it was.

CONFLICTING AND NOT_ANNOTATED MAP TO NOTHING, and that is deliberate. Stage 3 preserves a
contradiction rather than resolving it (`workflow.summary_state`: observed AND opposed -> the state
is `conflicting`). There is no honest column for "the sources disagree", so Stage 4 REFUSES such an
arm rather than skipping it. Skipping is how the contradiction got displayed in the first place: an
arm nobody checked is an arm that passes.
"""

from __future__ import annotations

from typing import Any, Container, Iterable, Mapping, Optional

from .arm_key_codec import MembershipError, arm_key_list
from .stage3_receipt import CORROBORATING_TABLES, load_receipt  # noqa: F401

# W16's `MEMBERSHIP_FOR_STATE`, inverted: the ONE column an evidence state belongs in.
COLUMN_FOR_STATE: dict[str, str] = {
    "observed_perturbation": "observed_perturbation_arm_keys",
    "inverse_direction_hypothesis": "inverse_direction_hypothesis_arm_keys",
    "pathway_hypothesis": "pathway_hypothesis_arm_keys",
    "opposed": "opposed_arm_keys",
    "unresolved": "unresolved_arm_keys",
}
TYPED_COLUMNS: tuple[str, ...] = tuple(sorted(COLUMN_FOR_STATE.values()))

# States that map to NO column. Stage 3 PRESERVES a contradiction rather than resolving it, so there
# is no column that honestly holds one — and Stage 4 refuses rather than choosing one for it.
STATES_WITH_NO_TYPED_COLUMN: tuple[str, ...] = ("conflicting", "not_annotated")


def require_receipt(receipt_path: Any, bundle_dir: Any = None,
                    store_dir: Any = None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Delegates to `stage3_receipt.load_receipt`: W16's receipt, READ FROM DISK and re-hashed.

    A dict is refused. The caller is Stage 4, so a receipt it builds in memory is a proof it wrote
    for itself about bytes it never read.
    """
    if isinstance(receipt_path, Mapping):
        raise MembershipError(
            "stage4_stage3_receipt_must_be_read_from_disk",
            "a receipt DICT was supplied instead of a path. Pass the path to W16's receipt on disk "
            "and Stage 4 will read its bytes and re-hash everything it names.",
        )
    return load_receipt(str(receipt_path or ""), str(bundle_dir) if bundle_dir else None,
                        str(store_dir) if store_dir else None)


def assert_typed_placement(candidate: Mapping[str, Any],
                           arm_summaries: Iterable[Mapping[str, Any]],
                           active_arm_keys: Optional[Container[str]] = None) -> dict[str, Any]:
    """Each ACTIVE arm is in exactly the column its `arm_evidence_state` maps to, and nowhere else.

    SCOPED to the arms this selection activated: an inactive arm is never displayed, never hashed,
    and cannot promote anything. Pass `active_arm_keys=None` for the store-wide audit path.
    """
    candidate_id = str(candidate.get("candidate_id") or "")

    # The candidate's typed columns, decoded once. (Stage 3 writes them as JSON strings.)
    placement: dict[str, set[str]] = {
        column: set(arm_key_list(candidate.get(column),
                                 where=f"candidate {candidate_id!r} column {column!r}"))
        for column in TYPED_COLUMNS
    }

    summaries = {
        str(r.get("arm_key")): r for r in arm_summaries
        if str(r.get("candidate_id") or "") == candidate_id
    }

    arms = {a for keys in placement.values() for a in keys}
    if active_arm_keys is not None:
        arms = {a for a in arms if a in active_arm_keys}

    checked = 0
    for arm in sorted(arms):
        summary = summaries.get(arm)
        if summary is None:
            raise MembershipError(
                "stage3_typed_arm_has_no_arm_summary",
                f"candidate {candidate_id!r} publishes arm {arm!r} and no `arm_summaries` row "
                "states the evidence behind it. An arm with no summary is an arm whose evidence "
                "class nothing corroborates.",
                {"candidate_id": candidate_id, "arm_key": arm},
            )

        state = str(summary.get("arm_evidence_state") or "")
        want = COLUMN_FOR_STATE.get(state)
        if want is None:
            here = sorted(c for c in TYPED_COLUMNS if arm in placement[c])
            raise MembershipError(
                "stage3_arm_evidence_state_has_no_typed_column",
                f"candidate {candidate_id!r} arm {arm!r} carries evidence state {state!r}, which "
                f"maps to NO typed column, and the candidate publishes it in {here}. Stage 3 "
                "PRESERVES a contradiction rather than resolving it — `conflicting` means the "
                "sources disagree — and there is no column that honestly holds that. Stage 4 will "
                "not pick one: an arm that is both a measured perturbation and evidence pointing "
                "the wrong way cannot be displayed as either.",
                {"candidate_id": candidate_id, "arm_key": arm, "state": state,
                 "published_in": here, "states_with_no_column": list(STATES_WITH_NO_TYPED_COLUMN)},
            )

        if arm not in placement[want]:
            raise MembershipError(
                "stage3_typed_arm_is_not_in_the_column_its_state_maps_to",
                f"candidate {candidate_id!r} arm {arm!r} carries evidence state {state!r}, so it "
                f"belongs in {want!r} — and it is not there.",
                {"candidate_id": candidate_id, "arm_key": arm, "state": state, "expected": want},
            )

        also = sorted(c for c in TYPED_COLUMNS if c != want and arm in placement[c])
        if also:
            raise MembershipError(
                "stage3_typed_arm_is_in_more_than_one_evidence_class",
                f"candidate {candidate_id!r} arm {arm!r} carries evidence state {state!r} (column "
                f"{want!r}) and is ALSO published in {also}. One arm is in one evidence class. "
                "Listing it in two lets it be read as the strongest of them while the arm set — and "
                "every hash over it — stays exactly as it was.",
                {"candidate_id": candidate_id, "arm_key": arm, "state": state,
                 "expected": want, "also_in": also},
            )
        checked += 1

    return {"candidate_id": candidate_id, "typed_arm_placements_checked": checked}
