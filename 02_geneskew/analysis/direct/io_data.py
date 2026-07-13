"""HDF5 loaders for the pinned DE_stats artifacts (runs on the configured analysis host).

Only ``run_screen`` imports this module; the pure core never touches h5py. All
joins between the main matrix and the guide/donor support matrices are by
stable ID (target Ensembl + condition), never by row position (plan §5.6).
"""
from __future__ import annotations

import json
from typing import Any

import h5py
import numpy as np


def _decode(arr) -> list[str]:
    return [x.decode() if isinstance(x, (bytes, bytearray)) else str(x) for x in arr]


def read_categorical(grp: h5py.Group) -> np.ndarray:
    cats = np.array(_decode(grp["categories"][:]), dtype=object)
    codes = grp["codes"][:]
    out = np.empty(codes.shape, dtype=object)
    valid = codes >= 0
    out[valid] = cats[codes[valid]]
    out[~valid] = None
    return out


def _obs_col(obs: h5py.Group, name: str):
    node = obs[name]
    if isinstance(node, h5py.Group):  # categorical
        return read_categorical(node)
    return node[:]


def load_registry(path: str) -> tuple[dict, str, dict]:
    with open(path) as fh:
        reg = json.load(fh)
    programs = {p["program_id"]: p for p in reg["programs"]}
    return programs, reg["registry_sha256"], reg


def _index_name(df: h5py.Group) -> str:
    return df.attrs.get("_index", "_index")


def load_main(h5ad_path: str, condition: str) -> dict:
    """Load the main DE matrix for one condition.

    Returns gene ids/index, per-target obs, and dense log_fc + zscore rows.
    """
    with h5py.File(h5ad_path, "r") as f:
        gene_ids = _decode(f["var/gene_ids"][:])
        gene_names = _decode(f["var/gene_name"][:])
        obs = f["obs"]
        cond = _obs_col(obs, "culture_condition").astype(object)
        sel = np.where(cond == condition)[0]
        sel = np.sort(sel)
        target_ens = _obs_col(obs, "target_contrast")[sel]
        target_sym = _obs_col(obs, "target_contrast_gene_name")[sel]
        source_row_id = _decode(obs["index"][:])
        source_row_id = np.array(source_row_id, dtype=object)[sel]

        def col(name):
            return _obs_col(obs, name)[sel]

        meta = {
            "target_ensembl": target_ens,
            "target_symbol": target_sym,
            "source_row_id": source_row_id,
            "n_cells_target": col("n_cells_target"),
            "n_guides": col("n_guides"),
            "ontarget_significant": col("ontarget_significant"),
            "ontarget_effect_size": col("ontarget_effect_size"),
            "low_target_gex": col("low_target_gex"),
            "distal_offtarget_flag": col("distal_offtarget_flag"),
            "neighboring_gene_KD": col("neighboring_gene_KD"),
            "single_guide_estimate": col("single_guide_estimate"),
            "target_baseMean": col("target_baseMean"),
            "guide_correlation_all": col("guide_correlation_all"),
            "guide_n_signif_ontarget": col("guide_n_signif_ontarget"),
            "donor_correlation_all_mean": col("donor_correlation_all_mean"),
            "n_downstream": col("n_downstream"),
            "n_total_de_genes": col("n_total_de_genes"),
        }
        log_fc = f["layers/log_fc"][sel, :].astype(np.float64)
        zscore = f["layers/zscore"][sel, :].astype(np.float64)
    gene_index = {g: i for i, g in enumerate(gene_ids)}
    return {
        "gene_ids": gene_ids,
        "gene_names": gene_names,
        "gene_index": gene_index,
        "meta": meta,
        "log_fc": log_fc,
        "zscore": zscore,
        "n_targets": len(sel),
    }


def load_support_modality(h5mu_path: str, modality: str, condition: str,
                          layer: str = "log_fc") -> dict:
    """Load one guide/donor-pair modality for a condition, keyed by target Ensembl.

    Returns gene_ids/index and a dict target_ensembl -> dense effect vector.
    """
    with h5py.File(h5mu_path, "r") as f:
        mod = f[f"mod/{modality}"]
        gene_ids = _decode(mod["var/_index"][:])
        obs = mod["obs"]
        cond = _obs_col(obs, "culture_condition").astype(object)
        sel = np.where(cond == condition)[0]
        sel = np.sort(sel)
        target_ens = _obs_col(obs, "target_contrast")[sel]
        eff = mod[f"layers/{layer}"][sel, :].astype(np.float64)
    gene_index = {g: i for i, g in enumerate(gene_ids)}
    by_target: dict[str, np.ndarray] = {}
    for i, t in enumerate(target_ens):
        if t is not None and t not in by_target:
            by_target[str(t)] = eff[i]
    return {"gene_ids": gene_ids, "gene_index": gene_index, "by_target": by_target}


def list_modalities(h5mu_path: str) -> list[str]:
    with h5py.File(h5mu_path, "r") as f:
        return sorted(f["mod"].keys())


def load_sgrna_rows_by_target(csv_path: str) -> dict[str, list[dict[str, Any]]]:
    """Group sgRNA library rows by intended target Ensembl id."""
    import pandas as pd
    cols = ["sgRNA", "target_gene_id", "target_gene_name",
            "designed_target_gene_id", "distance_to_closest_target_tss",
            "nearby_gene_within_30kb", "other_alignment_chromosome",
            "other_alignment_pos", "nearest_nontarget_gene_id",
            "nearest_nontarget_gene_name", "nearest_nontarget_gene_dist"]
    df = pd.read_csv(csv_path, usecols=cols, low_memory=False)
    out: dict[str, list[dict]] = {}
    for rec in df.to_dict("records"):
        tgt = rec.get("target_gene_id")
        if tgt is None or str(tgt) == "nan":
            continue
        out.setdefault(str(tgt), []).append(rec)
    return out
