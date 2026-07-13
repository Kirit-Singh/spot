"""Thin IO. Everything scientific happens elsewhere; this module only reads bytes.

The CELL matrix is loaded from a prepared ``.npz`` — barcodes, donors, per-program Stage-1
scores, and the readout expression block. The preparation step (h5ad -> npz) runs ON TCEFOLD
and is part of the runbook, for two reasons:

  * tcedirector reads ``GWCD4i.DE_stats.h5ad`` NON-DETERMINISTICALLY — stable mtime and
    size, differing sha256 on re-read. tcefold is stable at the pin. A run whose inputs
    hash differently on two reads cannot be content-addressed at all;
  * the NAS is seek-bound; a live stream is not a reproducible input.

STAGE-1 SCORES ARE READ BY BARCODE, NEVER RECOMPUTED. A recomputed score is a different
score wearing the released one's name — and it would agree with the released one closely
enough that nobody would check.
"""
from __future__ import annotations

import os
from typing import Any

import numpy as np
import pandas as pd
from direct.hashing import file_sha256


class InputError(ValueError):
    """An input is missing or does not say what it must. Refuse; never infer."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


def load_cells(path: str) -> dict[str, Any]:
    """Barcodes, donors, per-program scores and the expression block, from a prepared npz.

    Required arrays: ``barcodes``, ``donors``, ``gene_ids``, ``expr`` (cells x genes), and
    ``score__<program_id>`` for every program the run needs.
    """
    if not os.path.exists(path):
        raise InputError("cells_not_found", f"the prepared cell matrix {path!r} is missing")

    z = np.load(path, allow_pickle=False)
    for req in ("barcodes", "donors", "gene_ids", "expr"):
        if req not in z:
            raise InputError(
                "cells_missing_array",
                f"the prepared cell matrix has no {req!r} array; it carries {sorted(z)}")

    scores = {k[len("score__"):]: np.asarray(z[k], dtype=float)
              for k in z.files if k.startswith("score__")}
    if not scores:
        raise InputError(
            "cells_carry_no_stage1_scores",
            "the prepared cell matrix carries no 'score__<program_id>' array. Stage-1 v3 "
            "scores are READ BY BARCODE and never recomputed here — a recomputed score is a "
            "different score wearing the released one's name")

    expr = np.asarray(z["expr"], dtype=float)
    barcodes = [str(b) for b in z["barcodes"]]
    if expr.shape[0] != len(barcodes):
        raise InputError(
            "cell_axis_disagreement",
            f"expr has {expr.shape[0]} row(s) for {len(barcodes)} barcode(s)")

    return {
        "barcodes": barcodes,
        "donors": np.asarray([str(d) for d in z["donors"]]),
        "gene_ids": [str(g) for g in z["gene_ids"]],
        "expr": expr,
        "scores": scores,
        "n_cells": len(barcodes),
        "sha256": file_sha256(path),
    }


def load_effects(path: str) -> dict[str, Any]:
    """The per-target effect vectors, long-format: target_id, gene_id, <layer...>."""
    df = pd.read_parquet(path)
    for col in ("target_id", "gene_id"):
        if col not in df.columns:
            raise InputError("effects_missing_column",
                             f"the effect table has no {col!r} column")
    layers = [c for c in df.columns if c not in ("target_id", "gene_id")]
    if not layers:
        raise InputError("effects_carry_no_layer",
                         "the effect table carries no effect layer column")

    gene_ids = sorted(df["gene_id"].astype(str).unique())
    row_of = {g: i for i, g in enumerate(gene_ids)}
    by_layer: dict[str, dict[str, np.ndarray]] = {}
    for layer in layers:
        per_target: dict[str, np.ndarray] = {}
        for t, g in df.groupby("target_id"):
            v = np.zeros(len(gene_ids), dtype=float)
            v[[row_of[str(x)] for x in g["gene_id"]]] = g[layer].to_numpy(dtype=float)
            per_target[str(t)] = v
        by_layer[str(layer)] = per_target

    return {"gene_ids": gene_ids, "by_layer": by_layer, "layers": sorted(by_layer),
            "targets": sorted(df["target_id"].astype(str).unique()),
            "sha256": file_sha256(path)}


def load_masks(path: str) -> dict[str, Any]:
    """The Direct lane's own contributor-specific masks. Selected by target, NEVER unioned."""
    df = pd.read_parquet(path)
    for col in ("target_id", "gene_id"):
        if col not in df.columns:
            raise InputError("masks_missing_column",
                             f"the mask table has no {col!r} column")
    rows = df[["target_id", "gene_id"]].astype(str).to_dict("records")
    return {"rows": rows, "sha256": file_sha256(path)}


def load_eligible(path: str) -> dict[str, Any]:
    """Only direct-screen ELIGIBLE targets become perturbation columns."""
    from . import config

    df = pd.read_parquet(path)
    for col in ("target_id", "state"):
        if col not in df.columns:
            raise InputError("eligible_missing_column",
                             f"the eligibility table has no {col!r} column")
    keep = df[df["state"].astype(str).isin(config.ELIGIBLE_STATES)]
    targets = sorted(keep["target_id"].astype(str).unique())
    if not targets:
        raise InputError(
            "no_eligible_target",
            f"no target is in an eligible state {list(config.ELIGIBLE_STATES)}, so there is "
            "no perturbation matrix to reconstruct from. P2S cannot admit or rescue a "
            "target the Direct screen found ineligible")
    return {"targets": targets, "n_eligible": len(targets),
            "target_gene_ids": sorted(
                keep["target_ensembl"].astype(str).unique().tolist())
            if "target_ensembl" in keep.columns else [],
            "sha256": file_sha256(path)}
