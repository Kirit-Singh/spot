"""The temporal reusable-arm estimator identity — GENERIC and self-contained.

This is the production temporal lane's own method identity, owned by the ``arms``
subpackage. It carries ONLY what the reusable-arm producer binds: WHICH estimand this is
(a population-level difference-in-differences on program projections), and the fact that
it has no calibrated null. It deliberately does NOT carry the retired fixed-pair method
material — no reliability floor, no batch/confound policy, no display policy — because the
reusable-arm lane emits none of those. The estimand, stated once:

    base_temporal_delta(program, target, from -> to)
        = arm_value(to) - arm_value(from)

a difference of two within-condition masked program projections, each already a
panel-minus-control difference. It is a difference-in-differences at the POPULATION level:
NOT lineage tracing, NOT fate mapping, NOT a per-cell transition, NOT a rate. No function
here or anywhere in this subpackage produces a slope, a velocity or an elapsed time.
"""
from __future__ import annotations

from typing import Any

from ...hashing import content_hash

# --------------------------------------------------------------------------- #
# Estimator identity — bound into the temporal method block and every arm bundle.
# --------------------------------------------------------------------------- #
ESTIMATOR_ID = "spot.stage02.temporal_cross_condition.v1"
ESTIMATOR_VERSION = "stage2-temporal-cross-condition-v1-did-on-program-projections"
FORMULA_ID = "spot.stage02.temporal.formula.cross_condition_did.v1"
FORMULA_EXPR = "temporal_did(arm) = arm_value(arm, to_cond) - arm_value(arm, from_cond)"

ESTIMAND_ID = "spot.stage02.temporal.estimand.population_program_projection_shift.v1"
ESTIMAND_LEVEL = "population"
ESTIMAND_IS_PER_CELL_FATE = False
ESTIMAND_IS_LINEAGE_TRACED = False
NOT_A_FATE_CLAIM_RULE_ID = "spot.stage02.temporal.rule.not_lineage_or_fate.v1"

# No calibrated null for this projection -> no p, no q, ever.
INFERENCE_STATUS = "not_calibrated"
NO_PQ_REASON = "no_calibrated_null_for_this_cross_condition_projection"

# The GENERIC method identity block, hashed into the temporal method sha the Stage-1 v3
# bridge admits. It names the estimand and its inference status and NOTHING host- or
# run-specific, so the identity is reproducible and a contract admitted against it cannot
# be executed by a different estimand. It carries no batch policy and no code-tree hash:
# the retired fixed-pair lane owned those, and it is gone.
TEMPORAL_METHOD = {
    "method_identity_id": "spot.stage02.temporal.arm.method_identity.v1",
    "estimator_id": ESTIMATOR_ID,
    "estimator_version": ESTIMATOR_VERSION,
    "formula_id": FORMULA_ID,
    "formula_expr": FORMULA_EXPR,
    "estimand_id": ESTIMAND_ID,
    "estimand_level": ESTIMAND_LEVEL,
    "estimand_is_per_cell_fate": ESTIMAND_IS_PER_CELL_FATE,
    "estimand_is_lineage_traced": ESTIMAND_IS_LINEAGE_TRACED,
    "not_a_fate_claim_rule_id": NOT_A_FATE_CLAIM_RULE_ID,
    "inference_status": INFERENCE_STATUS,
    "no_pq_reason": NO_PQ_REASON,
}


def method_sha256() -> str:
    """The content hash of the generic temporal method identity. Reproducible: no host,
    no path, no timestamp, no batch policy, no code-tree hash — only what the estimand IS."""
    return content_hash(TEMPORAL_METHOD)


def method_identity() -> dict[str, Any]:
    """The identity block plus its own hash, for a caller that wants both."""
    return {**TEMPORAL_METHOD, "method_sha256": method_sha256()}
