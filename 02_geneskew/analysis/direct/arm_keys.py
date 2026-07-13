"""The canonical REUSABLE-ARM key: keyed on desired_change, never on the pole or the role.

THE CORRECTION (ROUND4_ADDENDUM fd59ecb6, Rule 2). The same pole means OPPOSITE
perturbations depending on the role it is playing:

    away_from_A(high) -> DECREASE the program        toward_B(high) -> INCREASE it
    away_from_A(low)  -> INCREASE the program        toward_B(low)  -> DECREASE it

So a cached arm keyed on ``high`` would fuse two opposite perturbations under one key, and a
UI joining two arms would serve one of them as the other — silently, and with values that
look entirely reasonable. The reusable arm therefore keys on the perturbation's DESIRED
CHANGE: what it is trying to do to the program. The pole (``high|low``) and the role
(``away_from_A|toward_B``) stay behind in the SELECTION contract as metadata, and neither
may alter a cached arm's values.

WHY THIS MAKES A PAIR CHEAP
---------------------------
An arm is reusable across every pair that names it. A pair becomes a JOIN of two
independently-verified arms — away_from_A(program A) + toward_B(program B) — rather than a
rerun. There is NO combined, balanced or weighted score at the join: the two arms are
reported side by side, exactly as within a single run.

THE TWO ARMS ARE ONE MEASUREMENT — WHERE THE EFFECT IS SIGNED
------------------------------------------------------------
``increase`` and ``decrease`` of a program in a context are EXACT SIGN TRANSFORMS of ONE
base effect — two logical arms, not two experimental estimates. The base is computed once
per (program, context) and both arms are derived from it, so they cannot disagree about the
magnitude of an effect they share. This is what ``derive_arm_values`` is for, and it applies
to the SIGNED base deltas: the Direct and temporal arms.

...AND WHERE IT IS NOT: PATHWAY ENRICHMENT IS COMPUTED, NEVER INFERRED
---------------------------------------------------------------------
Enrichment is computed over a RANKED LIST, and a ranking is not antisymmetric: the pathways
enriched at the top of a ranking are not the mirror image of those at the bottom. All 120
enrichment arms are therefore COMPUTED. ``derive_arm_values`` must never be used to infer
one enrichment arm from the other — ``EnrichmentAntisymmetryError`` exists to make that a
loud failure rather than a plausible-looking table.

Transcriptional convergence, by contrast, depends only on the masked perturbation signatures
for a ``(condition, source)`` — not on which program or which desired change is being asked
about. So each of the 6 pathway bundles emits ONE independently-verified convergence
artifact, REFERENCED by its 20 enrichment arms. The same convergence claim is not restated
20 times: 20 copies of one claim are 20 chances to disagree, and a reader cannot tell which
copy was checked.
"""
from __future__ import annotations

from typing import Any, Iterable

# ---- the roles (selection metadata — NEVER part of an arm key) ----
ROLE_AWAY = "away_from_A"
ROLE_TOWARD = "toward_B"
ROLES = (ROLE_AWAY, ROLE_TOWARD)

# ---- the poles (selection metadata — NEVER part of an arm key) ----
POLE_HIGH = "high"
POLE_LOW = "low"
POLES = (POLE_HIGH, POLE_LOW)

# ---- the desired change: THE arm key component ----
INCREASE = "increase"
DECREASE = "decrease"
DESIRED_CHANGES = (INCREASE, DECREASE)

# THE FROZEN MAPPING. Stated once, here. The verifier RE-DERIVES it rather than reading it.
DESIRED_CHANGE_BY_ROLE_AND_POLE: dict[tuple[str, str], str] = {
    (ROLE_AWAY, POLE_HIGH): DECREASE,
    (ROLE_AWAY, POLE_LOW): INCREASE,
    (ROLE_TOWARD, POLE_HIGH): INCREASE,
    (ROLE_TOWARD, POLE_LOW): DECREASE,
}

MAPPING_RULE_ID = "spot.stage02.arm.desired_change_from_role_and_pole.v1"
MAPPING_RULE = (
    "desired_change = increase when (role, pole) is (toward_B, high) or (away_from_A, low); "
    "decrease when (role, pole) is (away_from_A, high) or (toward_B, low)")

ARM_KEY_RULE_ID = "spot.stage02.arm.reusable_key.desired_change.v1"
ARM_KEY_RULE = (
    "direct|program|desired_change|condition ; "
    "pathway|program|desired_change|condition|source ; "
    "temporal|program|desired_change|from|to — the pole and the role are NEVER in the key")

# The sign each desired change applies to the ONE base effect.
SIGN: dict[str, int] = {INCREASE: 1, DECREASE: -1}

KIND_DIRECT = "direct"
KIND_PATHWAY = "pathway"
KIND_TEMPORAL = "temporal"
KIND_CONVERGENCE = "convergence"

# Convergence is a property of the (condition, source) — NOT of a program or a desired
# change. One artifact per pathway bundle, referenced by its 20 enrichment arms.
CONVERGENCE_SCOPE = ("condition", "source")
CONVERGENCE_IS_SHARED_ACROSS_ARMS = True

# Enrichment arms are COMPUTED. A ranking is not antisymmetric, so one arm may never be
# inferred from the other.
ENRICHMENT_ARMS_ARE_COMPUTED_NOT_DERIVED = True
SIGN_TRANSFORM_APPLIES_TO = ("direct_base_delta", "temporal_base_delta")


class ArmError(ValueError):
    """The arm key or its mapping is not usable. Refuse; never guess."""


class EnrichmentAntisymmetryError(ArmError):
    """Someone tried to INFER one enrichment arm from the other.

    Enrichment is computed over a ranked list, and reversing a ranking does not reflect a
    pathway's enrichment about the origin. An arm inferred this way would be a table of
    plausible numbers that nobody measured.
    """


def desired_change(role: str, pole: str) -> str:
    """The FROZEN role x pole -> desired_change mapping. Four entries, no default."""
    try:
        return DESIRED_CHANGE_BY_ROLE_AND_POLE[(str(role), str(pole))]
    except KeyError:
        raise ArmError(
            f"no desired_change for role={role!r} pole={pole!r}; the mapping is exactly "
            f"{sorted(DESIRED_CHANGE_BY_ROLE_AND_POLE)} and an unknown combination is "
            "refused rather than guessed — a guessed direction is a sign error nobody sees"
        ) from None


def _change(value: str) -> str:
    """A desired_change, or a refusal. Catches a pole handed in where a change belongs."""
    v = str(value)
    if v not in DESIRED_CHANGES:
        hint = (" — that is a POLE, not a desired change; the same pole is an increase in "
                "one role and a decrease in the other, which is exactly why it may not key "
                "an arm") if v in POLES else ""
        raise ArmError(f"desired_change must be one of {list(DESIRED_CHANGES)}, got "
                       f"{value!r}{hint}")
    return v


def _part(value: str, what: str) -> str:
    v = str(value)
    if not v or "|" in v:
        raise ArmError(f"{what} {value!r} is empty or contains the key separator '|'")
    return v


def direct_arm_key(program_id: str, change: str, condition: str) -> str:
    """``direct|program|desired_change|condition``."""
    return "|".join((KIND_DIRECT, _part(program_id, "program_id"), _change(change),
                     _part(condition, "condition")))


def pathway_arm_key(program_id: str, change: str, condition: str, source: str) -> str:
    """``pathway|program|desired_change|condition|source``."""
    return "|".join((KIND_PATHWAY, _part(program_id, "program_id"), _change(change),
                     _part(condition, "condition"), _part(source, "source")))


def temporal_arm_key(program_id: str, change: str, from_condition: str,
                     to_condition: str) -> str:
    """``temporal|program|desired_change|from|to`` — an ORDERED pair, never a set."""
    return "|".join((KIND_TEMPORAL, _part(program_id, "program_id"), _change(change),
                     _part(from_condition, "from_condition"),
                     _part(to_condition, "to_condition")))


def convergence_key(condition: str, source: str) -> str:
    """``convergence|condition|source`` — SHARED by that bundle's 20 enrichment arms.

    Deliberately carries NO program and NO desired_change: convergence depends only on the
    masked perturbation signatures for the (condition, source), so a per-arm copy would be
    the same claim restated 20 times — and 20 copies of one claim are 20 chances to disagree
    about it, with no way for a reader to tell which copy was the one that got checked.
    """
    return "|".join((KIND_CONVERGENCE, _part(condition, "condition"),
                     _part(source, "source")))


def derive_arm_values(base: Iterable[float], change: str, *,
                      quantity: str = "direct_base_delta") -> list[float]:
    """The arm's values, as an EXACT sign transform of the ONE base effect.

    ``increase`` is the base; ``decrease`` is its negation. Not a re-estimate — a transform,
    so the two arms of a program in a context can never disagree about a magnitude they
    share. ``0.0`` negates to ``0.0``, never ``-0.0``: a sign on a zero is a distinction the
    data does not make, and it would print as a different number.

    ONLY for the SIGNED base deltas. Enrichment is computed over a ranked list and is not
    antisymmetric, so inferring one enrichment arm from the other is refused by name.
    """
    if quantity not in SIGN_TRANSFORM_APPLIES_TO:
        raise EnrichmentAntisymmetryError(
            f"a sign transform is not defined for {quantity!r}; it applies to "
            f"{list(SIGN_TRANSFORM_APPLIES_TO)}. Enrichment is computed over a RANKED LIST "
            "and reversing a ranking does not mirror a pathway's enrichment — all 120 "
            "enrichment arms are COMPUTED, and an inferred one would be a table of "
            "plausible numbers nobody measured")
    sign = SIGN[_change(change)]
    return [(0.0 if v == 0 else sign * float(v)) for v in base]


def mapping_block() -> dict[str, Any]:
    """The mapping and the key rule, for a method/provenance block. Ids and enums only."""
    return {
        "mapping_rule_id": MAPPING_RULE_ID,
        "mapping_rule": MAPPING_RULE,
        "arm_key_rule_id": ARM_KEY_RULE_ID,
        "arm_key_rule": ARM_KEY_RULE,
        "desired_changes": list(DESIRED_CHANGES),
        "roles": list(ROLES),
        "poles": list(POLES),
        "arm_key_carries_pole_or_role": False,
        "arms_are_sign_transforms_of_one_base_effect": True,
        "sign_transform_applies_to": list(SIGN_TRANSFORM_APPLIES_TO),
        "enrichment_arms_are_computed_not_derived":
            ENRICHMENT_ARMS_ARE_COMPUTED_NOT_DERIVED,
        "enrichment_rank_antisymmetry_assumed": False,
        "convergence_scope": list(CONVERGENCE_SCOPE),
        "convergence_is_shared_across_arms": CONVERGENCE_IS_SHARED_ACROSS_ARMS,
        "combined_arm_score_permitted": False,
        "desired_change_by_role_and_pole": {
            f"{role}|{pole}": change
            for (role, pole), change in sorted(DESIRED_CHANGE_BY_ROLE_AND_POLE.items())
        },
    }
