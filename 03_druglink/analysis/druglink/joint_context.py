"""Stage-2 joint context: carried verbatim, never used to infer drug direction.

Stage 2 describes how the two arms relate. Stage 3 accepts that description as CONTEXT
and republishes it unchanged, so a reader can see what Stage 2 said about the joint
picture — without Stage 3 ever acting on it.

The canonical Stage-2 types (per the Direct schema review):

  joint_status              enum: both_arms | away_from_A_only | toward_B_only |
                                  opposed | not_evaluable
  pareto_tier               a POSITIVE INTEGER starting at 1, or NULL when the target is
                            not jointly evaluable. It is a RANK-LIKE TIER LABEL, not a
                            score — tier 1 is not "twice as good" as tier 2, and it is
                            not a weighted sum of the two arms.
  joint_ordering_method_id  string

``pareto_tier`` is numeric and that is CORRECT. An earlier revision of this module
refused every numeric joint field; that was wrong, and it would have rejected the real
Stage-2 contract. What remains refused is a **numeric combined objective** — a
``combined_score``, a ``balanced_skew``, or any weighted sum of the arms — because that
is a hidden ranking, not a tier label (see ``armlever.BANNED_OBJECTIVE_COLUMNS``, which
is checked on load and is fatal).

Two rules make "context, not direction" structural rather than aspirational:

  1. **The direction engine cannot see it.** ``druglink.direction.translate()`` takes only
     the arm's own desired modulation, the drug's intervention effect, the origin type
     and the target-entity class. There is no parameter through which a joint status or a
     Pareto tier could arrive, so no future edit can quietly start ranking on one.

  2. **Stage 3 never rewrites it.** Direct's ranks, Direct's arm evidence tiers and
     Stage-2's Pareto tiers are upstream facts. Stage 3 republishes them verbatim and
     changes none of them — not even for an inverse-direction hypothesis.

Direct v5 does not currently emit any of these. Absent is recorded as ``not_provided`` —
an absent field is never a favourable one, and nothing is invented to fill it.
"""
from __future__ import annotations

from typing import Any, Optional

JOINT_CONTEXT_POLICY_VERSION = "stage3-joint-context-v2-typed-pareto-tier"

JOINT_STATUS = "joint_status"
PARETO_TIER = "pareto_tier"
JOINT_ORDERING_METHOD_ID = "joint_ordering_method_id"
ACCEPTED_FIELDS = (JOINT_STATUS, PARETO_TIER, JOINT_ORDERING_METHOD_ID)

# The canonical Stage-2 joint_status enum.
JOINT_STATUS_VALUES = ("both_arms", "away_from_A_only", "toward_B_only", "opposed",
                       "not_evaluable")

NOT_PROVIDED = "not_provided"


class JointContextError(ValueError):
    """Stage-2 joint context is malformed, or is a combined score in disguise."""


def _joint_status(value: Any) -> Optional[str]:
    if value is None:
        return None
    if value not in JOINT_STATUS_VALUES:
        raise JointContextError(
            f"joint_status={value!r} is not one of {list(JOINT_STATUS_VALUES)}. It is a "
            "closed enum; Stage 3 refuses an unrecognised joint status rather than "
            "guessing what it meant.")
    return str(value)


def _pareto_tier(value: Any) -> Optional[int]:
    """A POSITIVE INTEGER from 1, or NULL when not jointly evaluable.

    Numeric is correct here: a Pareto tier is a rank-like tier LABEL, not a score. It is
    carried verbatim and never used to order, filter, gate or weight anything in Stage 3.
    """
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise JointContextError(
            f"pareto_tier={value!r} must be a positive integer (from 1) or null. A "
            "float, a string or a boolean is not a Pareto tier.")
    if value < 1:
        raise JointContextError(
            f"pareto_tier={value!r} must start at 1. Null means 'not jointly "
            "evaluable'; 0 and negatives are not tiers.")
    return int(value)


def _method_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    if not isinstance(value, str):
        raise JointContextError(
            f"joint_ordering_method_id={value!r} must be a string.")
    return value


_READERS = {JOINT_STATUS: _joint_status, PARETO_TIER: _pareto_tier,
            JOINT_ORDERING_METHOD_ID: _method_id}


def from_screen_row(row: dict[str, Any]) -> dict[str, Any]:
    """The joint context a single Direct screen row carries, if any."""
    return {field: _READERS[field](row.get(field)) for field in ACCEPTED_FIELDS}


def from_provenance(provenance: dict[str, Any]) -> dict[str, Any]:
    """The run-level joint context Stage 2 declared, if any.

    Read from ``stage2_joint_ordering`` or the provenance top level. Absent is recorded
    as ``not_provided``.
    """
    block = provenance.get("stage2_joint_ordering") or {}
    out: dict[str, Any] = {
        "joint_context_policy_version": JOINT_CONTEXT_POLICY_VERSION,
        "joint_status_values": list(JOINT_STATUS_VALUES),
        "pareto_tier_rule": "positive_integer_from_1_or_null_when_not_jointly_evaluable",
        "pareto_tier_is_a_tier_label_not_a_score": True,
        "used_to_infer_drug_direction": False,
        "used_to_rank_or_filter_arms": False,
        "rewritten_by_stage3": False,
    }
    provided = False
    for field in ACCEPTED_FIELDS:
        value = _READERS[field](block.get(field, provenance.get(field)))
        out[field] = value if value is not None else NOT_PROVIDED
        provided = provided or value is not None
    out["stage2_joint_context"] = "provided" if provided else NOT_PROVIDED
    return out


def vocabularies() -> dict[str, Any]:
    return {
        "joint_context_policy_version": JOINT_CONTEXT_POLICY_VERSION,
        "accepted_fields": list(ACCEPTED_FIELDS),
        "joint_status_values": list(JOINT_STATUS_VALUES),
        "pareto_tier_is_a_positive_integer_or_null": True,
        "pareto_tier_is_a_tier_label_not_a_combined_score": True,
        "joint_context_never_infers_drug_direction": True,
        "joint_context_is_never_rewritten_by_stage3": True,
        "numeric_combined_objectives_remain_refused": True,
    }
