"""The perturbation matrix: genes x eligible targets, with contributor-specific masks.

Re-implemented rather than imported from the frozen v1 lane. It is ~40 lines of pure
numerics, and importing them would tie a new lane to a package that also carries a lane
vocabulary that hard-raises on v2's arm keys, a config whose seed and grid v2 must own, and
an entrypoint that is already dead. A frozen lane you depend on can never be retired.

MASKING
-------
A target's own intended-target and off-target coordinates are set to the neutral value —
they are not dropped. Dropping them would change the gene axis per column and the columns
would no longer be comparable; zeroing them says "this perturbation has nothing to say
about this gene" while keeping every column on the one universe.

A masked coordinate is NEUTRAL, not absent, and an absent target is ABSENT — never a
column of zeros. A column of zeros is a perturbation that measurably did nothing, which is
a different and much stronger claim than one that was never measured.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

import numpy as np
import pandas as pd

from . import config


class MatrixError(ValueError):
    """The perturbation matrix cannot be built. Refuse; never pad with zeros."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


def build_masked_x(*, effect_by_target: dict[str, np.ndarray],
                   effect_gene_ids: Iterable[str],
                   universe_gene_ids: Iterable[str],
                   target_order: Iterable[str],
                   mask_by_target: Optional[dict[str, set]] = None,
                   ) -> tuple[pd.DataFrame, dict[str, Any]]:
    """``X`` (universe genes x targets) and what masking cost each column."""
    effect_gene_ids = list(effect_gene_ids)
    universe_gene_ids = list(universe_gene_ids)
    target_order = list(target_order)
    mask_by_target = mask_by_target or {}

    missing = [t for t in target_order if t not in effect_by_target]
    if missing:
        raise MatrixError(
            "target_has_no_effect_vector",
            f"{len(missing)} requested target(s) have no effect vector (e.g. "
            f"{missing[:3]}). A target that was never measured is ABSENT — it does not "
            "become a column of zeros, which would claim it measurably did nothing")

    row_of = {g: i for i, g in enumerate(effect_gene_ids)}
    absent = [g for g in universe_gene_ids if g not in row_of]
    if absent:
        raise MatrixError(
            "universe_gene_not_in_effect_matrix",
            f"{len(absent)} universe gene(s) are not in the effect matrix (e.g. "
            f"{absent[:3]}); the readout universe must be a subset of what was measured")

    take = np.asarray([row_of[g] for g in universe_gene_ids], dtype=int)

    cols, coverage = {}, {}
    for t in target_order:
        v = np.asarray(effect_by_target[t], dtype=float)
        if v.shape[0] != len(effect_gene_ids):
            raise MatrixError(
                "effect_vector_length_disagreement",
                f"target {t!r} has {v.shape[0]} effect value(s) for "
                f"{len(effect_gene_ids)} gene(s)")
        col = v[take].copy()
        masked = mask_by_target.get(t, set())
        hit = np.asarray([g in masked for g in universe_gene_ids], dtype=bool)
        col[hit] = config.MASK_NEUTRAL_VALUE
        cols[t] = col
        n_masked = int(hit.sum())
        coverage[t] = {
            "target_id": t,
            "n_universe": len(universe_gene_ids),
            "n_masked": n_masked,
            "n_retained": len(universe_gene_ids) - n_masked,
        }

    x = pd.DataFrame(cols, index=pd.Index(universe_gene_ids, name="gene_id"),
                     columns=target_order)
    return x, coverage


def mask_sets(mask_rows: Iterable[dict]) -> dict[str, set]:
    """Per-target masked-gene sets, from the Direct lane's own mask rows.

    Masks are selected by the target they belong to and NEVER unioned across targets: a
    union would mask a gene for a perturbation that has no reason to mask it, and the
    reconstruction would be denied evidence nothing said to withhold.
    """
    out: dict[str, set] = {}
    for r in mask_rows:
        out.setdefault(str(r["target_id"]), set()).add(str(r["gene_id"]))
    return out
