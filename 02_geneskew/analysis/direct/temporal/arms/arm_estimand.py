"""The REUSABLE temporal arm, as arithmetic. Pure; no IO, no data stack, no selection.

THE ESTIMAND, STATED EXACTLY
----------------------------
For a target ``X``, an admitted program ``p`` and a FROZEN ORDERED condition pair
``(from_condition -> to_condition)``:

    delta_p(X, c)  = mean( effect(X, c)[ panel_p   \\ M_X ] )
                   - mean( effect(X, c)[ control_p \\ M_X ] )

    base_temporal_delta(X, p, from -> to) = delta_p(X, to) - delta_p(X, from)

``delta_p`` is EXACTLY the within-condition masked program projection the direct lane
already publishes (``projection.program_delta``): the panel mean minus the control mean,
after that estimate's OWN contributor mask ``M_X`` has removed the target's own gene, its
neighbourhood and its guides' off-target alignments. Nothing is re-fitted, re-scaled or
re-derived here. The within-condition value is already a difference, so the cross-condition
difference of two of them is a DIFFERENCE-IN-DIFFERENCES.

WHAT IT IS: a change in a POPULATION-LEVEL program projection between two condition
populations, each fitted as a SEPARATE cell population.

WHAT IT IS NOT: it is not tracked-cell fate, not lineage tracing, not a per-cell
transition probability, not a rate or a slope, and it is NOT the authors' early/late
cluster classification. No cell is followed from one condition to the next. There is no
function in this module that could produce a rate, and ``TestTheArmIsNotAFateClaim``
exists to keep it that way.

THE TWO ARMS ARE ONE MEASUREMENT
--------------------------------
``increase`` and ``decrease`` are EXACT SIGN TRANSFORMS of the ONE base delta:

    arm_value(X, p, desired_change) = SIGN[desired_change] * base_temporal_delta(X, p)
    SIGN = {increase: +1, decrease: -1}

They are two LOGICAL arms, not two experimental estimates, and they can never disagree
about a magnitude they share.

WHY THIS IS THE FROZEN METHOD, NOT A NEW ONE
--------------------------------------------
The frozen legacy estimator (``estimand.temporal_did``) differences POLE-SIGNED arm
values: ``away_from_A = -sign_A * delta`` and ``toward_B = +sign_B * delta``, with
``POLE_SIGN = {high: +1, low: -1}``. Work the four (role, pole) cases through and every
one collapses to the same identity:

    away_from_A(high): -(+1) * d = -d   desired_change = decrease -> SIGN = -1  ✓
    away_from_A(low) : -(-1) * d = +d   desired_change = increase -> SIGN = +1  ✓
    toward_B(high)   : +(+1) * d = +d   desired_change = increase -> SIGN = +1  ✓
    toward_B(low)    : +(-1) * d = -d   desired_change = decrease -> SIGN = -1  ✓

    ==> legacy_arm_value(role, pole, c) == SIGN[desired_change(role, pole)] * delta_p(c)

and therefore, differencing across the ordered pair,

    ==> legacy temporal_did(role, pole) == SIGN[desired_change] * base_temporal_delta

So this module RE-EXPRESSES the frozen estimand in POLE-FREE coordinates. It does not
invent one. ``test_arm_value_equals_frozen_legacy_did`` asserts the identity for all four
(role, pole) combinations, which is what ties the reusable arm to the method that was
already verified — a producer that merely LOOKED consistent would be a new estimand
wearing the old one's name.
"""
from __future__ import annotations

from typing import Any, Optional

from ... import config as direct_config
from ... import disposition
from ... import projection as proj
from ...arm_keys import DESIRED_CHANGES, SIGN, derive_arm_values, temporal_arm_key
from ...hashing import canonical_num
from . import config, estimand

__all__ = [
    "BASE_FORMULA_ID", "BASE_FORMULA", "ARM_VALUE_FORMULA_ID", "ARM_VALUE_FORMULA",
    "SIGN_TRANSFORM_QUANTITY", "RANK_RULE",
    "base_temporal_delta", "arm_value", "program_evaluability", "project_programs",
    "rank_population", "estimand_block",
]

# --------------------------------------------------------------------------- #
# The formulae, written down where the artifact can carry them verbatim.
# --------------------------------------------------------------------------- #
BASE_FORMULA_ID = "spot.stage02.temporal.arm.base_delta.v1"
BASE_FORMULA = (
    "base_temporal_delta(target, program, from->to) = "
    "delta_p(target, program, to_condition) - delta_p(target, program, from_condition), "
    "where delta_p(X) = mean(panel_p \\ M_X) - mean(control_p \\ M_X) is the "
    "within-condition masked program projection; the difference of two within-condition "
    "differences, i.e. a population-level difference-in-differences")

ARM_VALUE_FORMULA_ID = "spot.stage02.temporal.arm.value_is_a_sign_transform.v1"
ARM_VALUE_FORMULA = (
    "arm_value(desired_change) = SIGN[desired_change] * base_temporal_delta, "
    "SIGN = {increase: +1, decrease: -1}; the two arms are exact sign transforms of ONE "
    "base delta - two LOGICAL arms, never two experimental estimates")

# The quantity ``arm_keys.derive_arm_values`` will apply a sign transform to. Naming it
# here is what makes an attempt to sign-transform an ENRICHMENT arm a loud failure.
SIGN_TRANSFORM_QUANTITY = "temporal_base_delta"

# The frozen rank contract, restated so the bundle can ship it and a verifier can
# re-derive a rank without reading this code. It IS ``projection``'s rule; the population
# is this ONE arm's own admitted+evaluable targets.
RANK_RULE = {
    "rank_population": ("this arm's OWN admitted+evaluable targets with a non-null "
                        "canonical arm_value"),
    "rank_direction": proj.RANK_DIRECTION,
    "rank_tie_break": proj.RANK_TIE_BREAK,
    "rank_null_rule": proj.RANK_NULL_RULE,
    "rank_numbering": "dense 1..n over the ranked population; all other targets null",
    "ranks_are_independent_per_desired_change": True,
    "rank_inferred_from_the_other_arm": False,
}


# --------------------------------------------------------------------------- #
# DESIRED-TARGET MODULATION — what the arm value SUGGESTS for drug linkage.
#
# The perturbation is a CRISPRi KNOCKDOWN. So a POSITIVE arm value (the knockdown moved the
# program in the arm's desired direction) SUGGESTS that INHIBITING the target would support
# that desired change. A NEGATIVE value is OPPOSED: achieving the desired change would
# require ACTIVATING the target — the opposite of a knockdown — and this screen cannot speak
# to whether a drug could do that, so pharmacologic reversibility is NOT assumed. A null or
# unevaluable arm stays ``not_evaluable``.
#
# Every one of these is SUGGESTIVE, never confirmatory (the spot firewall: a druggability
# signal may suggest but never confirm). The value NAMES what it supports; it does not claim
# it.
# --------------------------------------------------------------------------- #
PERTURBATION_MODALITY = "CRISPRi_knockdown"
MODULATION_RULE_ID = "spot.stage02.temporal.arm.desired_target_modulation.v1"

MOD_NOT_EVALUABLE = "not_evaluable"
MOD_SUPPORTS_INHIBITION = "supports_target_inhibition"
MOD_OPPOSED_NEEDS_ACTIVATION = "opposed_would_require_target_activation"
MOD_NO_RESPONSE = "no_directional_response"
TARGET_MODULATIONS = (MOD_NOT_EVALUABLE, MOD_SUPPORTS_INHIBITION,
                      MOD_OPPOSED_NEEDS_ACTIVATION, MOD_NO_RESPONSE)


def target_modulation(arm_value: Optional[float], *, evaluable: bool) -> str:
    """The SUGGESTIVE modulation orientation of one arm value under CRISPRi knockdown.

    Deterministic from the sign of the arm value and the evaluability alone — re-derivable
    by any verifier from the shipped value, so the orientation cannot be asserted out of
    step with the number it is about.
    """
    if not evaluable or arm_value is None:
        return MOD_NOT_EVALUABLE
    if arm_value > 0:
        return MOD_SUPPORTS_INHIBITION
    if arm_value < 0:
        return MOD_OPPOSED_NEEDS_ACTIVATION
    return MOD_NO_RESPONSE


def perturbation_block() -> dict[str, Any]:
    """The modality and the modulation rule, stated ONCE at bundle scope. Suggestive."""
    return {
        "perturbation_modality": PERTURBATION_MODALITY,
        "modulation_rule_id": MODULATION_RULE_ID,
        "positive_response_to_knockdown": MOD_SUPPORTS_INHIBITION,
        "negative_response_to_knockdown": MOD_OPPOSED_NEEDS_ACTIVATION,
        "null_or_unresolved_response": MOD_NOT_EVALUABLE,
        "pharmacologic_reversibility_assumed": False,
        "is_suggestive_not_confirmatory": True,
        "modulations": list(TARGET_MODULATIONS),
    }


def base_temporal_delta(from_delta: Optional[float],
                        to_delta: Optional[float]) -> Optional[float]:
    """``delta_p(to) - delta_p(from)``. POLE-FREE: no role and no pole may reach this.

    A missing endpoint yields NO ESTIMATE, never zero: zero is the claim that the program
    projection did not move, and that is a measurement, not a gap. Delegates to the frozen
    ``estimand.temporal_did`` so there is exactly ONE subtraction in the lane.
    """
    return estimand.temporal_did(from_delta, to_delta)


def arm_value(base: Optional[float], change: str) -> Optional[float]:
    """``SIGN[change] * base``, via the shared sign transform. ``None`` stays ``None``.

    Routed through ``arm_keys.derive_arm_values`` — the same transform the Direct lane
    uses — so the sign rule is stated in exactly one place. ``0.0`` never becomes ``-0.0``.
    """
    if base is None:
        return None
    return derive_arm_values([base], change, quantity=SIGN_TRANSFORM_QUANTITY)[0]


def program_evaluability(*, base_state: str, base_passed: bool,
                         projection_status: str) -> tuple[str, bool, list[str]]:
    """Is this PROGRAM evaluable for this target at this condition, and why not?

    Delegates to the direct lane's ``disposition.arm_state``, which is already POLE-FREE:
    it reads base QC and the program's own projection status, and nothing else. So the
    ``increase`` and ``decrease`` arms of a program SHARE an evaluability — which is the
    only coherent answer, because they share the estimate they are a sign transform of.
    """
    return disposition.arm_state(base_state=base_state, base_passed=base_passed,
                                 projection_status=projection_status)


def project_programs(effect_row, programs: dict[str, dict], gene_index: dict[str, int],
                     mask_set: Optional[set]) -> dict[str, dict]:
    """EVERY admitted program's masked projection for ONE target at ONE condition.

    This is the all-program base pass the pair-bound runner never did: the legacy runner
    projected only the two poles a selection happened to name, so 8 of the 10 programs
    were never computed and a pair could not be a cheap join of cached arms. Same masked
    projection, same minima, same statuses — applied to every admitted program.
    """
    return {
        program_id: proj.program_delta(
            effect_row, prog["panel"], prog["control"], gene_index, mask_set,
            direct_config.MIN_SURVIVING_PANEL, direct_config.MIN_SURVIVING_CONTROL)
        for program_id, prog in sorted(programs.items())
    }


def rank_population(records: list[dict[str, Any]], *, value_key: str = "arm_value",
                    evaluable_key: str = "evaluable",
                    rank_column: str = "rank") -> list[dict[str, Any]]:
    """Rank ONE desired-change arm over ITS OWN population, by the frozen rule.

    Descending on the exact canonical value that is emitted and hashed; ties broken on
    ``target_id`` ascending; dense 1..n; every non-evaluable or null-valued target gets a
    NULL rank. Invariant to input order.

    THE TWO ARMS ARE RANKED INDEPENDENTLY, and the ``decrease`` rank is NOT read off the
    ``increase`` rank in reverse. Under an exact tie the tie-break runs ``target_id``
    ASCENDING in BOTH arms, so the two rank vectors are genuinely not mirror images of
    each other — inferring one from the other would silently reorder tied targets.
    """
    return proj.rank_arm(records, value_key, evaluable_key, rank_column)


def estimand_block() -> dict[str, Any]:
    """WHAT was computed, in the artifact's own words. Ids, enums and formulae only."""
    return {
        "estimator_id": config.ESTIMATOR_ID,
        "estimator_version": config.ESTIMATOR_VERSION,
        "estimand_id": config.ESTIMAND_ID,
        "estimand_level": config.ESTIMAND_LEVEL,
        "estimand_is_per_cell_fate": config.ESTIMAND_IS_PER_CELL_FATE,
        "estimand_is_lineage_traced": config.ESTIMAND_IS_LINEAGE_TRACED,
        # Named so the artifact refuses the misreading in its own bytes rather than in a
        # docstring nobody ships. This estimand is not the authors' early/late call.
        "estimand_is_author_early_late_cluster_class": False,
        "estimand_is_a_rate_or_slope": False,
        "formula_id": config.FORMULA_ID,
        "base_formula_id": BASE_FORMULA_ID,
        "base_formula": BASE_FORMULA,
        "arm_value_formula_id": ARM_VALUE_FORMULA_ID,
        "arm_value_formula": ARM_VALUE_FORMULA,
        "sign_transform_quantity": SIGN_TRANSFORM_QUANTITY,
        "sign_by_desired_change": {c: SIGN[c] for c in DESIRED_CHANGES},
        "arms_are_sign_transforms_of_one_base_delta": True,
        "arms_are_two_experimental_estimates": False,
        "rank_rule": dict(RANK_RULE),
        "inference_status": config.INFERENCE_STATUS,
        "no_pq_reason": config.NO_PQ_REASON,
    }


def canonical(value: Any) -> Any:
    """The canonical emitted number: full float64, non-finite -> null."""
    return canonical_num(value)


def arm_key(program_id: str, change: str, from_condition: str,
            to_condition: str) -> str:
    """``temporal|program_id|desired_change|from|to`` — the ONE key. Never a pole."""
    return temporal_arm_key(program_id, change, from_condition, to_condition)
