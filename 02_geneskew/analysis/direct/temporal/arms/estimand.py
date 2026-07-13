"""The temporal cross-condition estimand, as arithmetic. Pure; no IO, no data stack.

ONE subtraction, and deliberately nothing else:

    temporal_did(arm) = arm_value(arm, to_cond) - arm_value(arm, from_cond)

Both inputs are within-condition arm values produced by the unchanged direct machinery.
This module never re-projects, re-scales, re-weights or re-fits anything, and it holds no
function that could turn the difference into a rate, a slope or a trajectory — see
``config`` for why that absence is the point. Relocated verbatim into the ``arms``
subpackage when the fixed-pair flat lane was retired; the reliability floor that used to
live beside it was fixed-pair material and did not come with it (the reusable-arm lane
emits no reliability badge).
"""
from __future__ import annotations

from typing import Any, Optional

# --------------------------------------------------------------------------- #
# What happened to this comparison, for this target, on this arm.
# --------------------------------------------------------------------------- #
ESTIMATED = "estimated"
# ABSENCE outranks non-evaluability: a target the release never shipped at a condition
# was not REFUSED there, and reporting it as "not evaluable" would read as a judgement the
# lane never made.
ABSENT_AT_FROM = "target_absent_at_from_condition"
ABSENT_AT_TO = "target_absent_at_to_condition"
ABSENT_AT_BOTH = "target_absent_at_both_conditions"
NOT_EVALUABLE_AT_FROM = "arm_not_evaluable_at_from_condition"
NOT_EVALUABLE_AT_TO = "arm_not_evaluable_at_to_condition"
NOT_EVALUABLE_AT_BOTH = "arm_not_evaluable_at_both_conditions"
TEMPORAL_STATUSES = (ESTIMATED, ABSENT_AT_FROM, ABSENT_AT_TO, ABSENT_AT_BOTH,
                     NOT_EVALUABLE_AT_FROM, NOT_EVALUABLE_AT_TO, NOT_EVALUABLE_AT_BOTH)


def _finite(v: Any) -> Optional[float]:
    """A value, or nothing. NaN and inf are not values and never enter a difference."""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def temporal_did(from_value: Optional[float],
                 to_value: Optional[float]) -> Optional[float]:
    """``to - from``, or None when either endpoint has no value.

    A missing endpoint yields NO ESTIMATE. It never yields zero: zero is the claim that the
    program projection did not move, and that is a measurement, not a gap.
    """
    a, b = _finite(from_value), _finite(to_value)
    if a is None or b is None:
        return None
    return b - a


def temporal_status(*, from_present: bool, to_present: bool,
                    from_evaluable: bool, to_evaluable: bool) -> str:
    """Why this arm does or does not have a cross-condition estimate."""
    if not from_present and not to_present:
        return ABSENT_AT_BOTH
    if not from_present:
        return ABSENT_AT_FROM
    if not to_present:
        return ABSENT_AT_TO
    if not from_evaluable and not to_evaluable:
        return NOT_EVALUABLE_AT_BOTH
    if not from_evaluable:
        return NOT_EVALUABLE_AT_FROM
    if not to_evaluable:
        return NOT_EVALUABLE_AT_TO
    return ESTIMATED
