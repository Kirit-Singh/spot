"""The synthetic builders, re-exported from the shipped ``p2s_arms.synthetic`` module.

They live in the PACKAGE, not here, because W16 needs the same builders to produce the UI
fixture as the tests use to certify it, and the preparation lane needs the same Marson-shaped
inputs. One copy: the bytes the UI is built against are the bytes these tests admit.
"""
from __future__ import annotations

from p2s_arms.synthetic import (  # noqa: F401
    ACTIVATION,
    CELL_SYMBOLS,
    CONDITION,
    CONTRIBUTOR,
    CONTRIBUTOR_WEIGHT,
    DONORS,
    OPPONENT,
    OPPONENT_WEIGHT,
    PROGRAM,
    REAL_P2S_LOCK,
    REAL_SOLVER_LOCK,
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
    write_de_readout,
    write_full_bundle,
    write_ntc_h5ad,
    write_p2s_runtime_lock,
    write_solver_lock,
    write_stage1_scores,
    write_w10_report,
)
