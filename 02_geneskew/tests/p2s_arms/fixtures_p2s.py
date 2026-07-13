"""The synthetic builders, re-exported from the shipped ``p2s_arms.synthetic`` module.

They live in the PACKAGE, not here, because W16 needs the same builders to produce the UI
fixture as the tests use to certify it. One copy: the bundle the UI is built against is the
bundle these tests admit.
"""
from __future__ import annotations

from p2s_arms.synthetic import (  # noqa: F401
    ACTIVATION,
    CONDITION,
    CONTRIBUTOR,
    CONTRIBUTOR_WEIGHT,
    DONORS,
    OPPONENT,
    OPPONENT_WEIGHT,
    PROGRAM,
    UPSTREAM_OBSERVED,
    base_deltas,
    gene_ids,
    linear_fit,
    make_cells,
    make_effects,
    make_eligible,
    make_masks,
    make_release,
    run_producer,
    target_ids,
    write_arm_bundle,
)
