"""THE JOINT ORDERING: a Pareto frontier over the two arms. Pre-registered, frozen.

This rule is written down BEFORE any real ranking has been looked at. That is not a
formality — a joint ordering chosen after seeing which targets it promotes is not a
method, it is a preference with a method's paperwork.

WHY PARETO AND NOT A SCORE
--------------------------
Stage-1 asks an ordered pair of questions: move AWAY from A, and TOWARD B. Any single
number that answers both — a weighted sum, a mean, a balanced skew, a "combined score" —
has to decide, silently and in advance, how much of one is worth how much of the other.
Nobody has that exchange rate. Inventing one lets a target that moves hard away from A
while actively OPPOSING B outrank a target that genuinely moves toward B, and it makes
the second dropdown decorative. That objective is retired and stays retired.

Dominance needs no exchange rate. Target X dominates Y iff X is at least as good on BOTH
arms and strictly better on at least one:

    dominates(X, Y)  <->  X.away >= Y.away  and  X.toward >= Y.toward
                          and (X.away > Y.away or X.toward > Y.toward)

Both objectives are oriented LARGER = FAVORABLE already, by construction of the arm
formulas, so no re-orientation happens here and no sign is flipped.

    tier 1 = the non-dominated frontier.
    Remove it, and the frontier of what remains is tier 2. Repeat.

A tier is an ORDER, not a score. It has no units, it cannot be averaged, and two targets
in the same tier are not tied — they are INCOMPARABLE, which is a different and more
honest thing. Both arm values ship alongside, always, so the components are never erased.

WHAT IS AND IS NOT IN THE FRONTIER
----------------------------------
Only targets evaluable on BOTH arms can be compared on both, so only they are tiered.
Everything else gets ``pareto_tier = null`` — not tier 0, not last place, not a sentinel
integer that sorts somewhere. It is absent, and the schema says so.

``joint_status`` is derived INDEPENDENTLY of the tier, from each arm's own evaluability
and direction. A tier says where a target sits among its comparable peers; a joint status
says what the two arms actually SAY. Deriving one from the other would make the pair
circular and destroy the only cross-check they offer.
"""
from __future__ import annotations

from typing import Any, Optional

from . import config

METHOD_ID = "spot.stage02.pareto.two_arm.v1"

# Both arms are already oriented larger = favorable. Stated, not assumed.
OBJECTIVE_ORIENTATION = "larger_is_favorable"
OBJECTIVES = tuple(config.ARMS)          # (away_from_A, toward_B)

# The joint-status vocabulary. FROZEN — derived from arm direction + evaluability, never
# from the tier.
JOINT_BOTH = "both_arms"
JOINT_AWAY_ONLY = "away_from_A_only"
JOINT_TOWARD_ONLY = "toward_B_only"
JOINT_OPPOSED = "opposed"
JOINT_NOT_EVALUABLE = "not_evaluable"
JOINT_STATUSES = (JOINT_BOTH, JOINT_AWAY_ONLY, JOINT_TOWARD_ONLY, JOINT_OPPOSED,
                  JOINT_NOT_EVALUABLE)

# What each of the two non-obvious labels is RESERVED for (M4). Stated here because the
# difference between them is the difference between "we measured this and it moved the
# wrong way" and "we could not measure this" — and a reader who confuses the two will
# throw away a real negative result.
OPPOSED_MEANS = (
    "at least one EVALUABLE arm moved below -sign_eps: the target was measured and it "
    "moves undesirably. Includes the bidirectional case (one arm favourable, the other "
    "opposing), which is the same finding stated more strongly.")
NOT_EVALUABLE_MEANS = (
    "no directional claim can be made: an arm that could not be scored (missing, "
    "non-finite, or not evaluable), or two arms that are both neutral — inside the sign "
    "tolerance, pointing nowhere. It is NOT the bucket for an arm that opposed.")

# Emitted columns. A tier and a label — no combined magnitude anywhere, by construction:
# there is no field here a consumer could sort as a score.
TIER_COLUMN = "pareto_tier"
STATUS_COLUMN = "joint_status"
METHOD_COLUMN = "joint_ordering_method_id"
JOINT_COLUMNS = (TIER_COLUMN, STATUS_COLUMN, METHOD_COLUMN)

# Display order is the stable target id, and ONLY the stable target id. Ordering the
# emitted table by tier would make the tier a headline rank in everything but name.
DISPLAY_ORDER = "target_id_ascending"
DISPLAY_ORDER_IS_A_RANK = False


def _finite(v: Any) -> Optional[float]:
    """A score, or nothing. NaN and inf are not scores and are never compared."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def jointly_evaluable(row: dict[str, Any]) -> bool:
    """Comparable on BOTH arms — the only targets a joint ordering can speak about."""
    for arm in config.ARMS:
        if not bool(row.get(f"{config.ARM_POLE[arm]}_evaluable")):
            return False
        if _finite(row.get(arm)) is None:
            return False
    return True


def joint_status(row: dict[str, Any], eps: float = config.SIGN_EPS) -> str:
    """What the TWO ARMS SAY, from their own evaluability and direction.

    Independent of the tier on purpose. An arm is FAVORABLE when it is evaluable and its
    value exceeds the sign tolerance; OPPOSING when it is evaluable and its value falls
    below the negative tolerance. Between those it has no direction, and no direction is
    not a weak yes.

    ``opposed`` is the label for ANY evaluable arm that moved the wrong way (M4). It used
    to be reachable only when one arm was favourable AND the other opposed, so a target
    whose arms were both scored and both moved undesirably — or moved undesirably on one
    arm and nowhere on the other — fell through to ``not_evaluable``. That is a false
    statement about the measurement: both arms WERE evaluated, and what they said was
    "the wrong way". Merging that into the missing-data bucket buries a real negative
    result exactly where nobody looks.

    ``not_evaluable`` now means what it says, and only that: an arm that could not be
    scored (missing / non-finite / not evaluable), or two arms that both sat inside the
    sign tolerance and therefore pointed nowhere. It does NOT mean the target was
    dropped: every target is emitted, and both raw arm values and both evaluability
    flags travel with this label.
    """
    favorable, opposing = {}, {}
    for arm in config.ARMS:
        evaluable = bool(row.get(f"{config.ARM_POLE[arm]}_evaluable"))
        value = _finite(row.get(arm))
        favorable[arm] = evaluable and value is not None and value > eps
        opposing[arm] = evaluable and value is not None and value < -eps

    a, b = config.ARM_A, config.ARM_B
    # the two FAVOURABLE-side labels first: they are the more specific claims
    if favorable[a] and favorable[b]:
        return JOINT_BOTH
    # any evaluable arm pointing the wrong way makes the target opposed — including the
    # bidirectional case (one arm favourable, the other opposing), which is the same
    # finding stated more strongly
    if opposing[a] or opposing[b]:
        return JOINT_OPPOSED
    if favorable[a]:
        return JOINT_AWAY_ONLY
    if favorable[b]:
        return JOINT_TOWARD_ONLY
    return JOINT_NOT_EVALUABLE


def dominates(x: dict[str, Any], y: dict[str, Any]) -> bool:
    """X is at least as good on BOTH arms and strictly better on at least one.

    Compared on the exact canonical float64 that is emitted — never a rounded value.
    Rounding first would turn distinct scores into an emitted tie, and the emitted tie
    would then contradict the tier actually assigned.

    Two exactly-equal points do not dominate each other, so they land in the same tier.
    That is not a tie broken silently: it is INCOMPARABILITY, and it is the answer.
    """
    at_least_as_good = all(
        _finite(x[arm]) >= _finite(y[arm]) for arm in config.ARMS)  # type: ignore[operator]
    strictly_better = any(
        _finite(x[arm]) > _finite(y[arm]) for arm in config.ARMS)   # type: ignore[operator]
    return at_least_as_good and strictly_better


def assign_tiers(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Peel non-dominated frontiers: tier 1, remove, repeat. Others get null.

    Invariant to input row order: the frontier of a set is a property of the set, and
    the tier integers are assigned by peeling, not by position. The row-permutation test
    is what holds this honest.
    """
    pool = [r for r in rows if jointly_evaluable(r)]
    tiered: dict[int, int] = {}                   # id(row) -> tier

    tier = 1
    remaining = list(pool)
    while remaining:
        frontier = [x for x in remaining
                    if not any(dominates(y, x) for y in remaining if y is not x)]
        # A finite set always has at least one non-dominated point, so this terminates.
        # If it somehow did not, tiering everything left beats looping forever.
        if not frontier:
            frontier = list(remaining)
        for r in frontier:
            tiered[id(r)] = tier
        survivors = {id(r) for r in frontier}
        remaining = [r for r in remaining if id(r) not in survivors]
        tier += 1

    for r in rows:
        r[TIER_COLUMN] = tiered.get(id(r))        # None wherever not jointly evaluable
        r[STATUS_COLUMN] = joint_status(r)
        r[METHOD_COLUMN] = METHOD_ID
    return rows


def n_tiers(rows: list[dict[str, Any]]) -> int:
    tiers = [r[TIER_COLUMN] for r in rows if r.get(TIER_COLUMN) is not None]
    return max(tiers) if tiers else 0


def summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """What the joint ordering did, as counts and ids. No combined magnitude anywhere."""
    from collections import Counter

    return {
        "joint_ordering_method_id": METHOD_ID,
        "objectives": list(OBJECTIVES),
        "objective_orientation": OBJECTIVE_ORIENTATION,
        "n_jointly_evaluable": sum(1 for r in rows if jointly_evaluable(r)),
        "n_tiers": n_tiers(rows),
        "n_in_tier_1": sum(1 for r in rows if r.get(TIER_COLUMN) == 1),
        "tier_is_a_score": False,
        "combined_objective_permitted": config.COMBINED_OBJECTIVE_PERMITTED,
        "display_order": DISPLAY_ORDER,
        "display_order_is_a_rank": DISPLAY_ORDER_IS_A_RANK,
        "joint_status_counts": dict(Counter(r.get(STATUS_COLUMN) for r in rows)),
        "joint_status_derived_from_tier": False,
    }
