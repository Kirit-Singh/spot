"""THE JOINT ORDERING, RESTATED — part of the STANDALONE verifier.

INDEPENDENCE RULE (test-enforced): imports nothing from the generator.

The Pareto tier is the one emitted field a downstream consumer has an obvious motive to
rewrite. It is the closest thing the screen has to a headline ordering, and a tier is a
small integer sitting in a parquet column: nudging a target from tier 3 to tier 1 costs
one cell edit, breaks no arithmetic, contradicts no other column, and moves that target
to the front of every UI that reads the frontier.

Nothing else in the lane can see that. The arm scores stay right. The arm ranks stay
right. The hashes stay right, because the tier is not what the arm ranks were derived
from. So the tier is RE-DERIVED here, from the emitted arm values, by a rule written out
from the spec rather than imported — and compared. A tier that does not follow from the
two arm values it claims to summarise was not computed from them.

The rule, restated:

    dominates(X, Y)  <->  X.away >= Y.away  and  X.toward >= Y.toward
                          and (X.away > Y.away or X.toward > Y.toward)

    tier 1 = non-dominated among the jointly evaluable. Peel it, repeat.
    not jointly evaluable -> null. Not tier 0, not last, not a sentinel.

``joint_status`` is re-derived from the arm directions INDEPENDENTLY of the tier, for the
same reason the generator derives it that way: if the status were read off the tier, the
two would agree by construction and neither would be evidence about the other.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verify_rules as R  # noqa: E402

# The frozen vocabulary, RESTATED (never imported from the generator).
METHOD_ID = "spot.stage02.pareto.two_arm.v1"
OBJECTIVE_ORIENTATION = "larger_is_favorable"

JOINT_BOTH = "both_arms"
JOINT_AWAY_ONLY = "away_from_A_only"
JOINT_TOWARD_ONLY = "toward_B_only"
JOINT_OPPOSED = "opposed"
JOINT_NOT_EVALUABLE = "not_evaluable"
JOINT_STATUSES = (JOINT_BOTH, JOINT_AWAY_ONLY, JOINT_TOWARD_ONLY, JOINT_OPPOSED,
                  JOINT_NOT_EVALUABLE)

TIER_COLUMN = "pareto_tier"
STATUS_COLUMN = "joint_status"
METHOD_COLUMN = "joint_ordering_method_id"

SIGN_EPS = 1e-9          # restated; the same tolerance the arm directions use


def _finite(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def jointly_evaluable(row) -> bool:
    for arm in R.ARMS:
        if not bool(row.get(f"{R.POLE[arm]}_evaluable")):
            return False
        if _finite(row.get(arm)) is None:
            return False
    return True


def joint_status(row, eps: float = SIGN_EPS) -> str:
    """From the ARM DIRECTIONS and evaluability. Never from the tier."""
    favorable, opposing = {}, {}
    for arm in R.ARMS:
        evaluable = bool(row.get(f"{R.POLE[arm]}_evaluable"))
        value = _finite(row.get(arm))
        favorable[arm] = evaluable and value is not None and value > eps
        opposing[arm] = evaluable and value is not None and value < -eps

    a, b = R.ARM_A, R.ARM_B
    if (favorable[a] and opposing[b]) or (favorable[b] and opposing[a]):
        return JOINT_OPPOSED
    if favorable[a] and favorable[b]:
        return JOINT_BOTH
    if favorable[a]:
        return JOINT_AWAY_ONLY
    if favorable[b]:
        return JOINT_TOWARD_ONLY
    return JOINT_NOT_EVALUABLE


def _dominates(x, y) -> bool:
    return (all(_finite(x[arm]) >= _finite(y[arm]) for arm in R.ARMS)
            and any(_finite(x[arm]) > _finite(y[arm]) for arm in R.ARMS))


def derive_tiers(rows) -> dict:
    """target_id -> tier (or None). Re-derived from the EMITTED arm values."""
    pool = [r for r in rows if jointly_evaluable(r)]
    out = {r["target_id"]: None for r in rows}

    tier, remaining = 1, list(pool)
    while remaining:
        frontier = [x for x in remaining
                    if not any(_dominates(y, x) for y in remaining if y is not x)]
        if not frontier:
            frontier = list(remaining)
        for r in frontier:
            out[r["target_id"]] = tier
        survivors = {id(r) for r in frontier}
        remaining = [r for r in remaining if id(r) not in survivors]
        tier += 1
    return out


def check_joint_ordering(emitted_rows, rep):
    """The emitted tier and status must FOLLOW from the emitted arm values.

    ``emitted_rows`` are read from screen.parquet — not from the reconstruction — on
    purpose. The point is not "did the generator compute its own rule correctly"; it is
    "does the SHIPPED table's tier follow from the SHIPPED table's arm values". A tier
    rewritten after emission is exactly the attack, and it leaves the reconstruction
    untouched.
    """
    derived = derive_tiers(emitted_rows)

    bad_tier = sorted(r["target_id"] for r in emitted_rows
                      if r.get(TIER_COLUMN) != derived[r["target_id"]])
    rep.check("every pareto_tier re-derives from the EMITTED arm values",
              not bad_tier,
              f"{len(bad_tier)} target(s) carry a tier that does not follow from their "
              f"two arm scores (first: {bad_tier[0] if bad_tier else None}); a tier "
              "rewritten after emission changes what the frontier says while leaving "
              "every score, rank and hash intact")

    bad_status = sorted(r["target_id"] for r in emitted_rows
                        if r.get(STATUS_COLUMN) != joint_status(r))
    rep.check("every joint_status re-derives from the ARM DIRECTIONS",
              not bad_status,
              f"{len(bad_status)} target(s) (first: "
              f"{bad_status[0] if bad_status else None})")

    rep.check("no scope that is not jointly evaluable carries a tier",
              all(r.get(TIER_COLUMN) is None for r in emitted_rows
                  if not jointly_evaluable(r)),
              "a target that cannot be compared on both arms was given a frontier "
              "position anyway")
    rep.check("the joint ordering names the pre-registered method id",
              {r.get(METHOD_COLUMN) for r in emitted_rows} <= {METHOD_ID},
              f"expected {METHOD_ID!r}")

    tiers = [t for t in derived.values() if t is not None]
    rep.check("the frontier is dense from tier 1 (no empty tier)",
              not tiers or set(tiers) == set(range(1, max(tiers) + 1)),
              f"tiers present: {sorted(set(tiers))}")
