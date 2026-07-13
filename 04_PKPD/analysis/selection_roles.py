"""The ORDERED, per-role arms of a selection — because a set of arm keys is symmetric.

THE DEFECT THIS EXISTS TO CLOSE. `SelectionBinding` bound `selected_arm_keys` as a frozenset. A set
has no order and no labels, so:

    A = away_from_A(arm_1)   B = toward_B(arm_2)      -- the question actually asked
    A = away_from_A(arm_2)   B = toward_B(arm_1)      -- the arms SWAPPED
    A = toward_B(arm_1)      B = away_from_A(arm_2)   -- the ROLES swapped

all produce `{arm_1, arm_2}`. Identical set, identical binding, identical `membership_sha256`. Yet
the second asks the OPPOSITE biological question — it looks for drugs that push *toward* the program
we wanted to move away from. The hash that exists to make a swapped selection detectable was blind
to the one swap that inverts the meaning of the result.

An arm's identity is therefore an ORDERED RECORD, not a member of a set:

    slot   A | B            which pole of the question
    role   away_from_A | toward_B | …   what the slot MEANS (Stage 3 assigns it; Stage 4 never does)
    arm_key + lane + program_id + desired_change + ordered context

and the arm_key is CROSS-CHECKED against its own fields, because a record whose parts disagree with
its key is a record where somebody edited one and not the other.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .arm_key_codec import MembershipError

# Stage 2's arm-key grammar, which Stage 3 carries verbatim:
#     lane | program_id | desired_change | condition                 (within-condition)
#     lane | program_id | desired_change | from_condition | to_condition   (cross-condition)
ARM_KEY_SEPARATOR = "|"

# The EXACT slot -> role mapping. Stage 3 assigns roles; Stage 4 pins which slot may carry which,
# because "A" and "B" are only labels until something says what they MEAN. If A ever carried
# `toward_B`, every downstream reading of the result would be inverted while every hash still agreed.
ROLE_BY_SLOT: dict[str, str] = {"A": "away_from_A", "B": "toward_B"}

# How many ORDERED conditions an arm in this mode must carry. A within-condition arm is measured AT a
# condition; a cross-condition arm is measured BETWEEN two, in a DIRECTION. An unknown mode is
# refused rather than guessed: guessing the arity would mean guessing whether time has a direction.
CONTEXT_ARITY: dict[str, int] = {
    "direct_within_condition": 1,
    "temporal_cross_condition": 2,
}

# The canonical derivation. `desired_change` is NOT read and trusted — it is DERIVED from the role
# and the pole's direction, and the row's own value must reproduce it:
#
#     toward a pole that is HIGH   -> increase        away from a pole that is HIGH -> decrease
#     toward a pole that is LOW    -> decrease        away from a pole that is LOW  -> increase
#
# A row whose desired_change disagrees points the drug search the WRONG WAY: it would look for
# compounds that push toward the program the question wanted to move away from, and every hash in
# the chain would still agree.
DESIRED_CHANGE: dict[tuple[str, str], str] = {
    ("toward", "high"): "increase",
    ("toward", "low"): "decrease",
    ("away", "high"): "decrease",
    ("away", "low"): "increase",
}


@dataclass(frozen=True)
class RoleArm:
    """One pole of the question: which slot, what it MEANS, and exactly which arm fills it."""

    slot: str                       # "A" | "B" — the pole
    role: str                       # "away_from_A" | "toward_B" | … — Stage 3's semantics
    arm_key: str
    lane: str
    program_id: str
    desired_change: str
    context: tuple[str, ...]        # ORDERED: (condition,) or (from_condition, to_condition)

    def identity(self) -> dict[str, Any]:
        return {
            "slot": self.slot,
            "role": self.role,
            "arm_key": self.arm_key,
            "lane": self.lane,
            "program_id": self.program_id,
            "desired_change": self.desired_change,
            "context": list(self.context),
        }

    def canonical_arm_key(self) -> str:
        """Rebuild the key from the parts. If it does not reproduce, the record is inconsistent."""
        return ARM_KEY_SEPARATOR.join(
            (self.lane, self.program_id, self.desired_change, *self.context))


def role_arms(view: Mapping[str, Any]) -> tuple[RoleArm, ...]:
    """Stage 3's `selected_arms.arms` + `selection.{roles,poles,conditions}` -> ordered RoleArms.

    Every field is READ from Stage 3 and CROSS-CHECKED against Stage 3's other statements of the
    same fact. Stage 4 assigns no role and infers no pole: a role Stage 4 invented would be a
    biological claim Stage 4 is not entitled to make.
    """
    selection = view.get("selection") or {}
    selected = view.get("selected_arms") or {}
    arms = selected.get("arms") or {}

    if not arms:
        raise MembershipError(
            "stage3_selection_names_no_role_arms",
            "the selection view carries no `selected_arms.arms`. Without the per-role arms the "
            "selection is only a SET of keys — and a set cannot tell an A/B swap from the question "
            "it inverts.",
        )

    declared_roles = selection.get("roles") or {}
    poles = selection.get("poles") or {}
    out: list[RoleArm] = []

    mode = str(selection.get("analysis_mode") or "")
    if mode not in CONTEXT_ARITY:
        raise MembershipError(
            "stage3_unknown_analysis_mode",
            f"analysis_mode {mode!r} is not one of {sorted(CONTEXT_ARITY)}. Stage 4 will not guess "
            "how many ordered conditions an arm in this mode carries — that would be guessing "
            "whether the arm has a DIRECTION in time.",
        )

    # EVERY cross-statement is MANDATORY. A check that only runs when a field happens to be present
    # is not a check — it is an invitation to delete the field. Deleting `arms.B`, `roles.B`,
    # `poles.B` or emptying `conditions` each removed one whole side of the question while leaving
    # every remaining field internally consistent, and the binding was admitted.
    for name, block in (("selected_arms.arms", arms), ("selection.roles", declared_roles),
                        ("selection.poles", poles)):
        _assert_exact_slots(name, block)

    conditions = _conditions(selection, mode)

    for slot in sorted(arms):                       # ORDERED, deterministically, by slot
        arm = arms[slot]
        if not isinstance(arm, Mapping):
            raise MembershipError(
                "stage3_role_arm_is_not_a_record",
                f"selected_arms.arms[{slot!r}] is not a record.")

        role = str(arm.get("role") or "")
        arm_key = str(arm.get("arm_key") or "")
        if not role or not arm_key:
            raise MembershipError(
                "stage3_role_arm_is_incomplete",
                f"selected_arms.arms[{slot!r}] must name both its `role` and its `arm_key`. A slot "
                "with no role has no meaning, and a slot with no arm has no evidence.",
            )

        # The slot's role is PINNED, not merely read: A is away_from_A and B is toward_B. If A ever
        # carried toward_B, every downstream reading would be inverted and every hash would agree.
        expected_role = ROLE_BY_SLOT.get(str(slot))
        if expected_role is None:
            raise MembershipError(
                "stage3_unknown_selection_slot",
                f"slot {slot!r} is not one of {sorted(ROLE_BY_SLOT)}. A question has two poles.",
            )
        if role != expected_role:
            raise MembershipError(
                "stage3_role_is_not_the_role_of_its_slot",
                f"slot {slot!r} carries role {role!r}; slot {slot!r} is {expected_role!r}. Swapping "
                "the roles asks the OPPOSITE question — it searches for drugs that push TOWARD the "
                "program the question wanted to move AWAY from — and a set of arm keys cannot tell "
                "the two apart.",
            )

        # Stage 3 states each slot's role TWICE — on the arm and in `selection.roles`. When the two
        # disagree, somebody edited one of them, and Stage 4 will not choose the one it prefers.
        if slot in declared_roles and str(declared_roles[slot]) != role:
            raise MembershipError(
                "stage3_selection_contradicts_itself_about_a_role",
                f"slot {slot!r}: the arm says role {role!r} and `selection.roles` says "
                f"{str(declared_roles[slot])!r}. The selection disagrees with itself about what "
                "this pole MEANS — and the two roles ask opposite questions.",
            )

        context = _context(arm)
        record = RoleArm(
            slot=str(slot), role=role, arm_key=arm_key,
            lane=str(arm.get("lane") or ""), program_id=str(arm.get("program_id") or ""),
            desired_change=str(arm.get("desired_change") or ""), context=context,
        )
        _assert_key_reproduces(record)
        _assert_context_is_ordered(record, mode, conditions)
        _assert_pole_agrees(record, arm, poles.get(slot), conditions)
        out.append(record)

    return tuple(out)


def _assert_context_is_ordered(arm: RoleArm, mode: str, conditions: list[str]) -> None:
    """The context is ORDERED and must match the mode and the selection's ordered conditions.

    Set membership is not enough. `Rest -> Stim48hr` and `Stim48hr -> Rest` contain the same two
    conditions and describe OPPOSITE directions of time: one asks what happens as cells activate,
    the other what happens as they return to rest. A membership check that only asked "are both of
    these conditions declared?" would accept the reversal, and every hash would agree.
    """
    arity = CONTEXT_ARITY[mode]
    if len(arm.context) != arity:
        raise MembershipError(
            "stage3_role_arm_context_does_not_match_the_analysis_mode",
            f"slot {arm.slot!r} carries {len(arm.context)} condition(s) {list(arm.context)} and "
            f"analysis_mode {mode!r} requires exactly {arity}. A within-condition arm is measured "
            "AT a condition; a cross-condition arm is measured BETWEEN two, in a direction.",
        )
    expected = (conditions[0],) if arity == 1 else (conditions[0], conditions[-1])
    if arm.context != expected:
        raise MembershipError(
            "stage3_role_arm_context_is_not_the_selection_ordered_conditions",
            f"slot {arm.slot!r} is measured over {list(arm.context)} and the selection declares the "
            f"ordered conditions {list(expected)}. These are not the same arm: reversing the "
            "endpoints reverses the direction of time, and the two ask opposite questions while "
            "containing exactly the same conditions.",
        )


def _assert_pole_agrees(arm: RoleArm, raw: Mapping[str, Any], pole: Any,
                        conditions: list[str]) -> None:
    """The pole restates the program, the direction and the condition — and `desired_change` is
    DERIVED from role + direction rather than taken on the row's word."""
    if not isinstance(pole, Mapping):
        return

    declared_program = str(pole.get("program_id") or "")
    if declared_program and declared_program != arm.program_id:
        raise MembershipError(
            "stage3_selection_contradicts_itself_about_a_pole",
            f"slot {arm.slot!r}: the arm is on program {arm.program_id!r} and `selection.poles` "
            f"says the pole is {declared_program!r}. The selection names one program and selects "
            "another.",
        )

    # The pole's CONDITION: A sits at the first declared condition, B at the last.
    declared_condition = str(pole.get("condition") or "")
    if declared_condition and conditions:
        expected = conditions[0] if arm.slot == "A" else conditions[-1]
        if declared_condition != expected:
            raise MembershipError(
                "stage3_pole_condition_is_not_its_ordered_condition",
                f"pole {arm.slot!r} is declared at {declared_condition!r}; the selection's ordered "
                f"conditions put slot {arm.slot!r} at {expected!r}. Swapping which pole sits at "
                "which condition swaps the question without changing a single arm key.",
            )

    # The DIRECTION, stated twice: on the arm (`pole`) and in `selection.poles` (`direction`).
    direction = str(pole.get("direction") or "")
    arm_direction = str(raw.get("pole") or "")
    if direction and arm_direction and direction != arm_direction:
        raise MembershipError(
            "stage3_selection_contradicts_itself_about_a_pole_direction",
            f"slot {arm.slot!r}: the arm says the pole is {arm_direction!r} and `selection.poles` "
            f"says {direction!r}. High and low are opposite ends of the program.",
        )

    # `desired_change` is DERIVED, never trusted.
    if not direction:
        return
    orientation = "toward" if arm.role.startswith("toward") else "away"
    expected_change = DESIRED_CHANGE.get((orientation, direction))
    if expected_change is None:
        raise MembershipError(
            "stage3_unknown_pole_direction",
            f"slot {arm.slot!r}: pole direction {direction!r} is not high or low.",
        )
    if arm.desired_change != expected_change:
        raise MembershipError(
            "stage3_desired_change_does_not_follow_from_role_and_pole",
            f"slot {arm.slot!r}: role {arm.role!r} on a {direction!r} pole means the program must "
            f"{expected_change!r}, and the arm says {arm.desired_change!r}. This is the sign of the "
            "whole search: the wrong value points Stage 4 at drugs that push the program the WAY "
            "THE QUESTION WANTED TO AVOID, and every hash in the chain still agrees.",
        )


def _assert_exact_slots(name: str, block: Any) -> None:
    """The key set must be EXACTLY {A, B}. Not "at least", not "whichever are present".

    A question has two poles. With `poles.B` deleted, the A side still validates perfectly — same
    role, same program, same direction, same condition — and Stage 4 would bind a "selection" that
    states only half of what it is contrasting. Every deletion below was admitted before this check:

        selected_arms.arms.B    the arm that fills the other pole
        selection.roles.B       what the other pole MEANS
        selection.poles.B       which program and direction the other pole IS
    """
    if not isinstance(block, Mapping):
        raise MembershipError(
            "stage3_selection_block_is_not_a_record",
            f"{name} is not a record, so its slots cannot be checked.")

    slots = set(block)
    expected = set(ROLE_BY_SLOT)
    if slots != expected:
        missing, extra = sorted(expected - slots), sorted(slots - expected)
        raise MembershipError(
            "stage3_selection_does_not_state_both_poles",
            f"{name} carries slots {sorted(slots)} and a question has exactly {sorted(expected)}"
            + (f"; missing {missing}" if missing else "")
            + (f"; unexpected {extra}" if extra else "")
            + ". A selection missing one pole still validates on the pole it kept — every field on "
              "the surviving side stays internally consistent — and it silently becomes a different "
              "question: one with nothing to contrast against.",
        )


def _conditions(selection: Mapping[str, Any], mode: str) -> list[str]:
    """The ordered conditions: NON-EMPTY, exact arity for the mode, and DISTINCT when ordered.

    `conditions: []` disabled every ordered check downstream — each one began "if not conditions:
    return" — so an empty list did not fail, it merely turned the checks off. A guard that can be
    switched off by deleting its input is not a guard.
    """
    conditions = [str(c) for c in (selection.get("conditions") or ())]
    arity = CONTEXT_ARITY[mode]

    if not conditions:
        raise MembershipError(
            "stage3_selection_states_no_conditions",
            "the selection declares no `conditions`. An empty list does not fail the ordered "
            "checks — it TURNS THEM OFF, because each one is a comparison against a list that is "
            "no longer there. A selection with no conditions is measured nowhere.",
        )
    if len(conditions) != arity:
        raise MembershipError(
            "stage3_selection_conditions_do_not_match_the_analysis_mode",
            f"analysis_mode {mode!r} requires exactly {arity} condition(s) and the selection "
            f"declares {len(conditions)}: {conditions}. A within-condition question is asked AT one "
            "condition; a cross-condition question is asked BETWEEN two, in order.",
        )
    if arity == 2 and conditions[0] == conditions[1]:
        raise MembershipError(
            "stage3_cross_condition_endpoints_are_the_same_condition",
            f"the selection contrasts {conditions[0]!r} with itself. A cross-condition arm measures "
            "CHANGE between two endpoints; between one endpoint and itself there is no change to "
            "measure.",
        )
    return conditions


def _context(arm: Mapping[str, Any]) -> tuple[str, ...]:
    """The ORDERED context. `Rest -> Stim48hr` and `Stim48hr -> Rest` are opposite directions of
    time, and an unordered context cannot tell them apart."""
    ctx = arm.get("context") or {}
    if isinstance(ctx, Mapping):
        frm, to = ctx.get("from_condition"), ctx.get("to_condition")
        if frm and to:
            return (str(frm), str(to))
        if ctx.get("condition"):
            return (str(ctx["condition"]),)
    if arm.get("condition"):
        return (str(arm["condition"]),)
    raise MembershipError(
        "stage3_role_arm_has_no_context",
        "a role arm states no condition and no from/to context. An arm with no context is an arm "
        "measured nowhere.",
    )


def _assert_key_reproduces(arm: RoleArm) -> None:
    """The arm_key must REBUILD from the arm's own fields.

    The key is the identity Stage 4 matches on; the fields are what the row says it means. If they
    disagree, the row is internally inconsistent — and Stage 4 would be matching on one while
    displaying the other.
    """
    if not (arm.lane and arm.program_id and arm.desired_change):
        raise MembershipError(
            "stage3_role_arm_is_incomplete",
            f"slot {arm.slot!r} ({arm.arm_key!r}) does not state its lane, program_id and "
            "desired_change, so its arm_key cannot be independently reproduced.",
        )
    rebuilt = arm.canonical_arm_key()
    if rebuilt != arm.arm_key:
        raise MembershipError(
            "stage3_role_arm_key_does_not_reproduce_from_its_fields",
            f"slot {arm.slot!r} declares arm_key {arm.arm_key!r}, and its own "
            f"lane/program/desired_change/context rebuild to {rebuilt!r}. The row disagrees with "
            "itself about which arm it is, so Stage 4 would match on one and display the other.",
        )


