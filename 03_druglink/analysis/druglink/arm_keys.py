"""THE REUSABLE ARM KEY: the algebra, and the four-entry map that gives it its sign.

Split from :mod:`druglink.arm_selection` at the 500-line gate — the same seam the lane already
draws between what a ROW is and how a SET of them is assembled. ``arm_selection`` re-exports every
name here, so a consumer still binds ONE module.

    lane|program_id|desired_change|<context…>

THE KEY IS NEVER A POLE AND NEVER A ROLE
----------------------------------------
    away_from_A(high) -> DECREASE the program        toward_B(high) -> INCREASE it
    away_from_A(low)  -> INCREASE the program        toward_B(low)  -> DECREASE it

The same pole means OPPOSITE perturbations depending on the role it plays. An arm keyed on
``high`` would fuse ``away_from_A(high)`` and ``toward_B(high)`` — two opposite perturbations —
under one key, and split the two arms that are bit-identical. So the arm keys on the DESIRED
CHANGE, and the pole and the role stay behind in the SELECTION, as properties of the QUESTION.

That is what makes an arm reusable: it is A in one question and B in another.

THE CONTEXT IS PART OF THE KEY, AND IT IS LOAD-BEARING
------------------------------------------------------
``temporal|P|decrease|Rest|Stim8hr`` and ``temporal|P|decrease|Stim8hr|Stim48hr`` are DIFFERENT
arms over different time windows. They share the whole prefix ``temporal|P|decrease`` and differ
ONLY in their context — and the release holds SIX of them for every (program, desired_change). So
an arm cannot be identified by a prefix, a substring, or a "close enough" program+direction match:
those resolve six arms, and taking the first answers a question about different time points while
looking exactly like the right answer.

Every lookup is EXACT STRING EQUALITY on the full key. :func:`sibling_arm_keys` exists so a test
can prove the siblings are really there, and really excluded.
"""
from __future__ import annotations

from typing import Any, Mapping

from . import join_semantics as js
from . import selection_v3 as s3
from . import stage2_aggregate as sa

# THE FROZEN MAP. Four entries, no default. An unknown combination is refused, never guessed —
# a guessed direction is a sign error nobody sees.
DESIRED_CHANGE_BY_ROLE_AND_POLE: dict[tuple[str, str], str] = {
    (s3.ROLE_A, s3.POLE_HIGH): "decrease",
    (s3.ROLE_A, s3.POLE_LOW): "increase",
    (s3.ROLE_B, s3.POLE_HIGH): "increase",
    (s3.ROLE_B, s3.POLE_LOW): "decrease",
}
MAPPING_RULE_ID = "spot.stage02.arm.desired_change_from_role_and_pole.v1"
ARM_KEY_RULE_ID = "spot.stage02.arm.reusable_key.desired_change.v1"

# The GENE lane each mode reads. This table is the only place that decides, so it cannot be
# quietly bypassed: a cross-time question answered on same-time Direct ranks would return
# numbers that look exactly like an answer.
GENE_LANE_FOR_MODE = {
    s3.MODE_WITHIN: sa.LANE_DIRECT,
    s3.MODE_TEMPORAL: sa.LANE_TEMPORAL,
}
PATHWAY_CONTEXT_LABEL = {
    s3.MODE_WITHIN: js.PATHWAY_CONTEXT[js.WITHIN_CONDITION],
    s3.MODE_TEMPORAL: js.PATHWAY_CONTEXT[js.TEMPORAL_CROSS_CONDITION],
}

# How many key parts each lane's context contributes. A key with the wrong arity is BOGUS.
CONTEXT_ARITY = {sa.LANE_DIRECT: 1, sa.LANE_TEMPORAL: 2, sa.LANE_PATHWAY: 2}

GATE_UNKNOWN_ROLE_OR_POLE = "no_desired_change_is_defined_for_this_role_and_pole"
GATE_BOGUS_ARM_KEY = "the_arm_key_is_not_a_parseable_stage2_reusable_arm_key"
GATE_ARM_KEY_MISSING = "the_selection_resolves_no_arm_key_for_a_role"
GATE_ARM_NOT_IN_AGGREGATE = "the_selection_names_an_arm_the_admitted_aggregate_does_not_have"
GATE_PRODUCER_MAP_ABSENT = \
    "the_aggregate_publishes_no_role_and_pole_map_for_stage3_to_check_itself_against"
GATE_PRODUCER_MAP_DISAGREES = \
    "the_aggregate_publishes_a_role_and_pole_map_stage3_does_not_agree_with"
GATE_STAGE1_ARMS_DISAGREE = \
    "the_arm_keys_stage3_derives_are_not_the_arm_keys_the_selection_declares"


class ArmSelectionError(ValueError):
    """A named, fail-closed refusal. No arm is guessed and no view is produced."""

    def __init__(self, gate: str, message: str) -> None:
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


def _refuse(gate: str, message: str) -> None:
    raise ArmSelectionError(gate, message)


# --------------------------------------------------------------------------- #
# 1. The key. Stage-2's rule, restated.
# --------------------------------------------------------------------------- #
def desired_change(role: str, pole: str) -> str:
    """(role, pole) -> the perturbation's DESIRED CHANGE. No default; an unknown pair refuses."""
    try:
        return DESIRED_CHANGE_BY_ROLE_AND_POLE[(str(role), str(pole))]
    except KeyError:
        _refuse(GATE_UNKNOWN_ROLE_OR_POLE,
                f"no desired_change for role={role!r} pole={pole!r}; the map is exactly "
                f"{sorted(DESIRED_CHANGE_BY_ROLE_AND_POLE)}. An unknown combination is refused "
                "rather than guessed — a guessed direction is a sign error nobody sees.")
    raise AssertionError("unreachable")            # pragma: no cover


def _part(value: Any, what: str) -> str:
    text = str(value)
    if not text or "|" in text:
        _refuse(GATE_BOGUS_ARM_KEY,
                f"{what} {value!r} is empty or contains the key separator '|'; a key part that "
                "carries the separator makes the key ambiguous to parse and to match.")
    return text


def arm_key(lane: str, program_id: str, change: str, context: Mapping[str, Any]) -> str:
    """``lane|program_id|desired_change|<context…>`` — Stage-2's canonical reusable key."""
    if lane == sa.LANE_DIRECT:
        tail = [_part(context.get("condition"), "condition")]
    elif lane == sa.LANE_TEMPORAL:
        tail = [_part(context.get("from_condition"), "from_condition"),
                _part(context.get("to_condition"), "to_condition")]
    elif lane == sa.LANE_PATHWAY:
        tail = [_part(context.get("condition"), "condition"),
                _part(context.get("pathway_source"), "pathway_source")]
    else:
        _refuse(GATE_BOGUS_ARM_KEY, f"unknown lane {lane!r}; the lanes are {list(sa.LANES)}")
    if str(change) not in sa.DESIRED_CHANGES:
        hint = (" — that is a POLE, not a desired change; the same pole is an increase in one "
                "role and a decrease in the other, which is exactly why it may not key an arm"
                if str(change) in s3.POLES else "")
        _refuse(GATE_BOGUS_ARM_KEY,
                f"desired_change must be one of {list(sa.DESIRED_CHANGES)}, got {change!r}{hint}")
    return "|".join([lane, _part(program_id, "program_id"), str(change)] + tail)


def parse_arm_key(key: Any) -> dict[str, Any]:
    """An arm key -> its parts, or a NAMED refusal. Never a best-effort partial parse."""
    if not isinstance(key, str) or not key:
        _refuse(GATE_BOGUS_ARM_KEY, f"an arm key must be a non-empty string; got {key!r}")
    parts = key.split("|")
    if len(parts) < 4:
        _refuse(GATE_BOGUS_ARM_KEY,
                f"the arm key {key!r} has {len(parts)} part(s); a reusable key is "
                "lane|program_id|desired_change|<context…> and carries at least four.")
    lane, program_id, change = parts[0], parts[1], parts[2]
    tail = parts[3:]
    if lane not in CONTEXT_ARITY:
        _refuse(GATE_BOGUS_ARM_KEY,
                f"the arm key {key!r} names lane {lane!r}; the lanes are {list(sa.LANES)}")
    if change not in sa.DESIRED_CHANGES:
        _refuse(GATE_BOGUS_ARM_KEY,
                f"the arm key {key!r} names desired_change {change!r}; it is exactly "
                f"{list(sa.DESIRED_CHANGES)}. A pole in this slot would key two opposite "
                "perturbations to one arm.")
    if len(tail) != CONTEXT_ARITY[lane]:
        _refuse(GATE_BOGUS_ARM_KEY,
                f"the arm key {key!r} carries {len(tail)} context part(s); a {lane!r} arm's "
                f"context is exactly {CONTEXT_ARITY[lane]}. A key missing its context does not "
                "identify an arm — it identifies a whole family of them.")
    if lane == sa.LANE_DIRECT:
        context = {"condition": tail[0]}
    elif lane == sa.LANE_TEMPORAL:
        context = {"from_condition": tail[0], "to_condition": tail[1]}
    else:
        context = {"condition": tail[0], "pathway_source": tail[1]}
    return {"arm_key": key, "lane": lane, "program_id": program_id,
            "desired_change": change, "context": context}


def sibling_arm_keys(aggregate: sa.AdmittedAggregate, key: str) -> list[str]:
    """Every OTHER arm sharing this key's ``lane|program_id|desired_change`` prefix.

    They exist — six per (temporal program, desired_change), three per Direct one — and they are
    exactly what a prefix or substring match would sweep in. Exposed so a test can prove they are
    present in the store and ABSENT from the view.
    """
    prefix = "|".join(key.split("|")[:3]) + "|"
    return sorted(a.arm_key for a in aggregate.arms
                  if a.arm_key.startswith(prefix) and a.arm_key != key)


# --------------------------------------------------------------------------- #
# 2. The selected arms. Derived per role, independently, context and all.
# --------------------------------------------------------------------------- #
