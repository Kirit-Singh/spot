"""THE RULES, RE-STATED. The verifier's independent implementation of the frozen contract.

Nothing in this module is imported from the lane it checks. Every rule below is written
out again from the frozen contract, in this module's own words, so that an error in the
producer's sign map, key grammar, rank rule or difference cannot hide inside a checker
that reuses it. A verifier that calls ``producer.arm_value`` to check ``producer``'s arm
values has measured nothing.

THE ESTIMAND
------------
    delta_p(X, c)            = panel_mean_p(X, c) - control_mean_p(X, c)
                               (the WITHIN-CONDITION masked program projection)
    base_temporal_delta(...) = delta_p(X, p, to) - delta_p(X, p, from)
    arm_value(change)        = SIGN[change] * base_temporal_delta,
                               SIGN = {increase: +1, decrease: -1}

It is a POPULATION-LEVEL difference-in-differences between two separately-fitted
condition populations. It is not per-cell fate, not lineage tracing, not a rate and not a
slope — and there is no function in this module that could produce one.

WHAT KEYS AN ARM
----------------
    temporal|program_id|desired_change|from_condition|to_condition

The pole (``high|low``) and the role (``away_from_A|toward_B``) are SELECTION metadata
and are never in the key: the same pole is an increase in one role and a decrease in the
other, so a key on the pole would fuse two opposite perturbations. A pole handed in where
a desired change belongs is refused BY NAME.

THE PAIR UNIVERSE
-----------------
Every ORDERED pair of distinct released conditions, both directions, none refused —
derived from the conditions the bound release ships, never a typed-out list. Three
conditions therefore give exactly six ordered pairs, and that "six" is a consequence.
"""
from __future__ import annotations

import math
from typing import Any, Iterable, Optional

# --------------------------------------------------------------------------- #
# The declared estimand. Re-stated, so the artifact's own claim can be checked.
# --------------------------------------------------------------------------- #
ESTIMAND_LEVEL = "population"
ESTIMAND_IS_PER_CELL_FATE = False
ESTIMAND_IS_LINEAGE_TRACED = False
INFERENCE_STATUS = "not_calibrated"

RULES_ID = "spot.stage02.temporal.arm.verifier_rules.v1"

# --------------------------------------------------------------------------- #
# The desired change, and the sign it applies to the ONE base delta.
# --------------------------------------------------------------------------- #
INCREASE = "increase"
DECREASE = "decrease"
DESIRED_CHANGES = (INCREASE, DECREASE)
SIGN: dict[str, int] = {INCREASE: 1, DECREASE: -1}

# Selection metadata. Named here ONLY so that handing one in is a refusal by name.
POLES = ("high", "low")
ROLES = ("away_from_A", "toward_B")

# The frozen (role, pole) -> desired_change mapping, re-derived rather than read. It is
# the join's rule, not the arm's, and it exists here so the join can be checked too.
DESIRED_CHANGE_BY_ROLE_AND_POLE: dict[tuple[str, str], str] = {
    ("away_from_A", "high"): DECREASE,
    ("away_from_A", "low"): INCREASE,
    ("toward_B", "high"): INCREASE,
    ("toward_B", "low"): DECREASE,
}

KIND = "temporal"
KEY_SEP = "|"
KEY_ARITY = 5

# --------------------------------------------------------------------------- #
# The within-condition projection contract (the frozen direct-lane minima).
# --------------------------------------------------------------------------- #
MIN_SURVIVING_PANEL = 1
MIN_SURVIVING_CONTROL = 10

OK = "ok"
INSUFFICIENT_AXIS_COVERAGE = "insufficient_axis_coverage"
MASK_UNRESOLVED = "mask_unresolved"
PROJECTION_STATUSES = (OK, INSUFFICIENT_AXIS_COVERAGE, MASK_UNRESOLVED)

ARM_EVALUABLE = "evaluable"
ARM_EXCLUDED_BASE_QC = "excluded_base_qc"
ARM_INSUFFICIENT_COVERAGE = "insufficient_axis_coverage"
ARM_MASK_UNRESOLVED = "mask_unresolved"

ESTIMATED = "estimated"
ABSENT_AT_FROM = "target_absent_at_from_condition"
ABSENT_AT_TO = "target_absent_at_to_condition"
ABSENT_AT_BOTH = "target_absent_at_both_conditions"
NOT_EVALUABLE_AT_FROM = "arm_not_evaluable_at_from_condition"
NOT_EVALUABLE_AT_TO = "arm_not_evaluable_at_to_condition"
NOT_EVALUABLE_AT_BOTH = "arm_not_evaluable_at_both_conditions"
TEMPORAL_STATUSES = (ESTIMATED, ABSENT_AT_FROM, ABSENT_AT_TO, ABSENT_AT_BOTH,
                     NOT_EVALUABLE_AT_FROM, NOT_EVALUABLE_AT_TO, NOT_EVALUABLE_AT_BOTH)

RANK_DIRECTION = "descending"
RANK_TIE_BREAK = "target_id_ascending"

# --------------------------------------------------------------------------- #
# THE SUGGESTIVE MODULATION ORIENTATION — what an arm value SUGGESTS for drug linkage.
#
# The perturbation is a CRISPRi KNOCKDOWN. So a POSITIVE arm value (the knockdown moved the
# program in the arm's DESIRED direction) SUGGESTS that INHIBITING the target would support
# that change. A NEGATIVE value is OPPOSED: getting the desired change would require
# ACTIVATING the target — the opposite of a knockdown — and this screen cannot speak to
# whether a drug could do that. PHARMACOLOGIC REVERSIBILITY IS NOT ASSUMED, and a verifier
# that let an artifact claim it would be laundering a knockdown into a prescription.
#
# Suggestive, never confirmatory: the value NAMES what it supports; it does not claim it.
# --------------------------------------------------------------------------- #
PERTURBATION_MODALITY = "CRISPRi_knockdown"
MOD_NOT_EVALUABLE = "not_evaluable"
MOD_SUPPORTS_INHIBITION = "supports_target_inhibition"
MOD_OPPOSED_NEEDS_ACTIVATION = "opposed_would_require_target_activation"
MOD_NO_RESPONSE = "no_directional_response"
TARGET_MODULATIONS = (MOD_NOT_EVALUABLE, MOD_SUPPORTS_INHIBITION,
                      MOD_OPPOSED_NEEDS_ACTIVATION, MOD_NO_RESPONSE)
PHARMACOLOGIC_REVERSIBILITY_ASSUMED = False


def target_modulation(arm_value: Any, *, evaluable: bool) -> str:
    """The orientation ONE arm value suggests, from its sign and its evaluability alone.

    Re-derivable from the shipped number, so an orientation cannot be asserted out of step
    with the value it is about. A null or unevaluable arm is ``not_evaluable`` — never a
    direction, because a direction nobody measured is the one a reader would act on.
    """
    v = finite(arm_value)
    if not evaluable or v is None:
        return MOD_NOT_EVALUABLE
    if v > 0:
        return MOD_SUPPORTS_INHIBITION
    if v < 0:
        return MOD_OPPOSED_NEEDS_ACTIVATION
    return MOD_NO_RESPONSE


class RuleViolation(ValueError):
    """The input does not satisfy a stated rule. Refuse; never coerce, never guess."""


# --------------------------------------------------------------------------- #
# Values.
# --------------------------------------------------------------------------- #
def finite(x: Any) -> Optional[float]:
    """A value, or nothing. NaN and inf are not values and never enter a difference."""
    if x is None or isinstance(x, bool):
        return None
    try:
        f = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return f


def validated_change(change: Any) -> str:
    """A real ``increase``/``decrease``. A POLE or a ROLE is refused by name."""
    v = str(change)
    if v in DESIRED_CHANGES:
        return v
    if v in POLES:
        raise RuleViolation(
            f"{v!r} is a POLE, not a desired change. The same pole is an increase in one "
            "role and a decrease in the other, which is exactly why it may not key an arm")
    if v in ROLES:
        raise RuleViolation(
            f"{v!r} is a ROLE, not a desired change. A role is selection metadata; it "
            "chooses an arm and never becomes one")
    raise RuleViolation(f"desired_change must be one of {list(DESIRED_CHANGES)}, got {v!r}")


def desired_change(role: str, pole: str) -> str:
    """The frozen (role, pole) -> desired_change mapping. Four entries, no default."""
    try:
        return DESIRED_CHANGE_BY_ROLE_AND_POLE[(str(role), str(pole))]
    except KeyError:
        raise RuleViolation(
            f"no desired_change for role={role!r} pole={pole!r}; an unknown combination is "
            "refused rather than guessed - a guessed direction is a sign error nobody sees"
        ) from None


def base_temporal_delta(from_delta: Any, to_delta: Any) -> Optional[float]:
    """``delta_p(to) - delta_p(from)``. A missing endpoint yields NO ESTIMATE, never zero.

    Zero is the claim that the program projection did not move; that is a measurement,
    and a gap is not.
    """
    a, b = finite(from_delta), finite(to_delta)
    if a is None or b is None:
        return None
    return b - a


def arm_value(base: Any, change: Any) -> Optional[float]:
    """``SIGN[change] * base``. ``0.0`` never becomes ``-0.0``: the data makes no such
    distinction, and it would print as a different number."""
    sign = SIGN[validated_change(change)]
    b = finite(base)
    if b is None:
        return None
    return 0.0 if b == 0 else sign * b


def projection_delta(panel_mean: Any, control_mean: Any) -> Optional[float]:
    """The WITHIN-CONDITION projection identity: panel mean minus control mean."""
    p, c = finite(panel_mean), finite(control_mean)
    if p is None or c is None:
        return None
    return p - c


def projection_status(n_panel_surviving: Any, n_control_surviving: Any, *,
                      mask_resolved: bool = True) -> str:
    """Which projection status the surviving-gene counts imply, by the frozen minima.

    An unresolved contributor mask is REFUSED, never projected against an empty mask:
    an empty mask is self-fulfilling — it lets the target's own gene score the target.
    """
    if not mask_resolved:
        return MASK_UNRESOLVED
    if n_panel_surviving is None or n_control_surviving is None:
        return MASK_UNRESOLVED
    if (int(n_panel_surviving) < MIN_SURVIVING_PANEL
            or int(n_control_surviving) < MIN_SURVIVING_CONTROL):
        return INSUFFICIENT_AXIS_COVERAGE
    return OK


def arm_state(*, base_state: str, base_passed: bool,
              projection_status: str) -> tuple[str, bool, list[str]]:
    """This program's evaluability at ONE condition, from base QC + its own projection.

    Pole-free by construction, so the ``increase`` and ``decrease`` arms of a program
    SHARE an evaluability — the only coherent answer, because they share the estimate
    they are a sign transform of.
    """
    if not base_passed:
        return ARM_EXCLUDED_BASE_QC, False, [f"base_qc:{base_state}"]
    if projection_status == MASK_UNRESOLVED:
        return ARM_MASK_UNRESOLVED, False, ["arm_mask_unresolved"]
    if projection_status == INSUFFICIENT_AXIS_COVERAGE:
        return ARM_INSUFFICIENT_COVERAGE, False, ["arm_insufficient_axis_coverage"]
    if projection_status != OK:
        return ARM_INSUFFICIENT_COVERAGE, False, [f"arm_projection:{projection_status}"]
    return ARM_EVALUABLE, True, ["arm_evaluable"]


def temporal_status(*, from_present: bool, to_present: bool, from_evaluable: bool,
                    to_evaluable: bool) -> str:
    """Why this (program, target) does or does not have a cross-condition estimate.

    ABSENCE outranks non-evaluability: a target the release never shipped at a condition
    was not REFUSED there, and reporting it as 'not evaluable' would read as a judgement
    the lane never made.
    """
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


# --------------------------------------------------------------------------- #
# The key.
# --------------------------------------------------------------------------- #
def _part(value: Any, what: str) -> str:
    v = str(value)
    if not v or KEY_SEP in v:
        raise RuleViolation(f"{what} {value!r} is empty or contains the key separator "
                            f"{KEY_SEP!r}")
    return v


def arm_key(program_id: str, change: str, from_condition: str, to_condition: str) -> str:
    """``temporal|program|desired_change|from|to`` — an ORDERED pair, never a set."""
    return KEY_SEP.join((KIND, _part(program_id, "program_id"), validated_change(change),
                         _part(from_condition, "from_condition"),
                         _part(to_condition, "to_condition")))


def parse_arm_key(key: str) -> tuple[str, str, str, str]:
    """The four parts of a well-formed key, or a refusal. Never a partial match."""
    parts = str(key).split(KEY_SEP)
    if len(parts) != KEY_ARITY or parts[0] != KIND:
        raise RuleViolation(
            f"{key!r} is not a temporal arm key: it must be exactly "
            f"{KIND}{KEY_SEP}program{KEY_SEP}desired_change{KEY_SEP}from{KEY_SEP}to")
    _, program_id, change, frm, to = parts
    return program_id, validated_change(change), frm, to


def bundle_key(from_condition: str, to_condition: str) -> str:
    """``temporal|from|to`` — the ORDERED-pair scope of one physical bundle."""
    return KEY_SEP.join((KIND, _part(from_condition, "from_condition"),
                         _part(to_condition, "to_condition")))


def base_key(program_id: str, target_id: str) -> str:
    return f"{_part(program_id, 'program_id')}|{_part(target_id, 'target_id')}"


def bundle_dirname(from_condition: str, to_condition: str) -> str:
    """``<from>__to__<to>`` — one directory per ORDERED pair. Reversing it is a new one."""
    return f"{from_condition}__to__{to_condition}"


# --------------------------------------------------------------------------- #
# The pair universe. Derived from the released conditions, never typed out.
# --------------------------------------------------------------------------- #
def ordered_pairs(conditions: Iterable[str]) -> list[tuple[str, str]]:
    """EVERY ordered pair of DISTINCT conditions, both directions, in a stable order.

    The count is a CONSEQUENCE of the release: n conditions give n*(n-1) pairs. A module
    that hard-coded six would keep returning six after the release gained or lost a
    condition, and one that named a specific pair would answer that pair's question under
    every other pair's name.
    """
    conds = [str(c) for c in conditions]
    if len(set(conds)) != len(conds):
        seen, dupes = set(), []
        for c in conds:
            if c in seen:
                dupes.append(c)
            seen.add(c)
        raise RuleViolation(
            f"the released conditions contain duplicates {sorted(set(dupes))}. They are "
            "refused rather than de-duplicated: a duplicate silently decides which of two "
            "condition populations an endpoint was drawn from")
    if len(conds) < 2:
        raise RuleViolation(
            f"{len(conds)} condition(s) cannot make an ordered pair; a condition compared "
            "with itself has a base delta of exactly 0 by construction, which is an "
            "arithmetic identity and not a measurement")
    return [(a, b) for a in conds for b in conds if a != b]


def expected_arm_keys(programs: Iterable[str], from_condition: str,
                      to_condition: str) -> set[str]:
    """Every admitted program x every desired change, for ONE ordered pair."""
    return {arm_key(p, c, from_condition, to_condition)
            for p in programs for c in DESIRED_CHANGES}


# --------------------------------------------------------------------------- #
# The rank.
# --------------------------------------------------------------------------- #
def rank_population(records: list[dict[str, Any]], *, value_key: str = "arm_value",
                    evaluable_key: str = "evaluable") -> dict[str, int]:
    """The frozen rank rule, re-stated: ``{target_id: rank}`` for the ranked population.

    Population : this ONE arm's own evaluable targets with a non-null value.
    Value      : the exact canonical value that is emitted and hashed — never rounded
                 first, because rounding turns distinct scores into an emitted tie and the
                 emitted tie-break then contradicts the rank actually assigned.
    Direction  : descending. Tie-break: ``target_id`` ASCENDING.
    Numbering  : dense 1..n. Everything else has NO rank.

    The two arms of a program are ranked INDEPENDENTLY. The tie-break runs ascending in
    BOTH of them, so the ``decrease`` ranks are not the mirror image of the ``increase``
    ranks and one may never be inferred from the other.
    """
    rankable = [r for r in records
                if bool(r.get(evaluable_key)) and finite(r.get(value_key)) is not None]
    ordered = sorted(rankable, key=lambda r: (-float(r[value_key]), str(r["target_id"])))
    return {str(r["target_id"]): i for i, r in enumerate(ordered, start=1)}
