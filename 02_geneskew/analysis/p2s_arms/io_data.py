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
from typing import Any, Optional

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

    condition = str(z["condition"]) if "condition" in z.files else None
    return {
        "barcodes": barcodes,
        "donors": np.asarray([str(d) for d in z["donors"]]),
        "gene_ids": [str(g) for g in z["gene_ids"]],
        "expr": expr,
        "scores": scores,
        "condition": condition,
        "n_cells": len(barcodes),
        "sha256": file_sha256(path),
    }


def load_effects(path: str) -> dict[str, Any]:
    """The per-target effect layers, as a MATRIX container (targets x genes), not long rows.

    WHY NOT LONG FORMAT. One condition of the real readout is ~11,300 eligible targets x
    10,282 readout genes = ~116 MILLION cells. As a long parquet that is ~116M rows of
    (target_id, gene_id, zscore, log_fc) — gigabytes of repeated string keys to express a
    dense rectangle, and a groupby over it to get back the rectangle we started with.

    So the container IS the rectangle: two float32 (targets x genes) planes plus their axes.
    """
    if not os.path.exists(path):
        raise InputError("effects_not_found", f"the effect matrix {path!r} is missing")

    z = np.load(path, allow_pickle=False)
    for req in ("target_ids", "gene_ids", "zscore", "log_fc"):
        if req not in z:
            raise InputError(
                "effects_missing_array",
                f"the effect matrix has no {req!r} array; it carries {sorted(z.files)}")

    targets = [str(t) for t in z["target_ids"]]
    gene_ids = [str(g) for g in z["gene_ids"]]
    layers: dict[str, dict[str, np.ndarray]] = {}
    for layer in ("zscore", "log_fc"):
        m = z[layer]
        if m.shape != (len(targets), len(gene_ids)):
            raise InputError(
                "effects_shape_disagreement",
                f"layer {layer!r} is {m.shape}, not "
                f"({len(targets)}, {len(gene_ids)}) = (targets, genes)")
        layers[layer] = {t: m[i] for i, t in enumerate(targets)}

    return {"gene_ids": gene_ids, "by_layer": layers, "layers": sorted(layers),
            "targets": targets, "sha256": file_sha256(path)}


def load_masks(path: str) -> dict[str, Any]:
    """The Direct lane's own contributor-specific masks. Selected by target, NEVER unioned."""
    df = pd.read_parquet(path)
    for col in ("target_id", "gene_id"):
        if col not in df.columns:
            raise InputError("masks_missing_column",
                             f"the mask table has no {col!r} column")
    rows = df[["target_id", "gene_id"]].astype(str).to_dict("records")
    return {"rows": rows, "sha256": file_sha256(path)}


def load_eligible(path: str, *, arm_key: Optional[str] = None) -> dict[str, Any]:
    """The targets EVALUABLE on this ARM. Eligibility is arm-specific, not a global set.

    The prepared table is arm-keyed. When an ``arm_key`` is given (production always gives
    one — the arm being fitted), only that arm's evaluable targets become columns. A target
    evaluable for another program's arm is not evaluable for this one.
    """
    df = pd.read_parquet(path)
    if "target_id" not in df.columns:
        raise InputError("eligible_missing_column",
                         "the eligibility table has no 'target_id' column")

    if arm_key is not None:
        # NO GLOBAL FALLBACK. When an arm is being fitted, the table MUST carry both the
        # arm_key and the evaluable flag: a missing column would silently widen the
        # perturbation set to every arm's targets — precisely the arm-specificity this lane
        # exists to preserve. So the columns are required, not opportunistically used.
        for col in ("arm_key", "evaluable"):
            if col not in df.columns:
                raise InputError(
                    "eligible_missing_column",
                    f"the eligibility table has no {col!r} column, so this arm's evaluable "
                    "set cannot be told apart from another's. This lane never falls back to "
                    "the global target set")
        df = df[df["arm_key"].astype(str) == str(arm_key)]
        if df.empty:
            raise InputError(
                "no_eligible_target",
                f"the eligibility table carries no row for {arm_key!r}. Eligibility is "
                "arm-specific, and an arm absent from the table is not the same as an arm "
                "whose whole target set is evaluable")
        df = df[df["evaluable"].astype(bool)]
    elif "evaluable" in df.columns:
        df = df[df["evaluable"].astype(bool)]

    targets = sorted(df["target_id"].astype(str).unique())
    if not targets:
        raise InputError(
            "no_eligible_target",
            f"no target is EVALUABLE on {arm_key!r} (eligibility is arm-specific), so there "
            "is no perturbation matrix to reconstruct from. P2S cannot admit or rescue a "
            "target the Direct screen found ineligible")
    return {"targets": targets, "n_eligible": len(targets),
            "arm_key": arm_key,
            "target_gene_ids": sorted(
                df["target_ensembl"].astype(str).unique().tolist())
            if "target_ensembl" in df.columns else [],
            "sha256": file_sha256(path)}
