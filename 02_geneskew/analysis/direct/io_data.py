"""HDF5 / CSV loaders for the pinned Stage-2 inputs.

Only the orchestrator imports this module; the pure core never touches h5py.
Every join between the main matrix and the guide / donor-pair matrices is by
stable ID (target Ensembl + condition), never by row position.

Each support modality carries its OWN ``n_guides``: a donor-pair fit may have
used a different number of guides than the pooled fit, and each estimate must be
masked with its own contributors.
"""
from __future__ import annotations

import json
from typing import Any, Optional

import h5py
import numpy as np

from .hashing import file_sha256

_MAIN_OBS_FIELDS = (
    "n_cells_target", "n_guides", "ontarget_significant", "ontarget_effect_size",
    "low_target_gex", "distal_offtarget_flag", "neighboring_gene_KD",
    "single_guide_estimate", "target_baseMean", "guide_correlation_all",
    "donor_correlation_all_mean", "n_downstream", "n_total_de_genes",
)


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
    if isinstance(node, h5py.Group):
        return read_categorical(node)
    return node[:]


def load_registry(path: str) -> dict[str, Any]:
    """Load the Stage-1 program registry and BOTH of its candidate hashes."""
    with open(path) as fh:
        reg = json.load(fh)
    programs = {p["program_id"]: p for p in reg.get("programs", [])}
    return {
        "programs": programs,
        "file_sha256": file_sha256(path),
        "declared_sha256": reg.get("registry_sha256"),
        "raw": reg,
    }


def load_main(h5ad_path: str, condition: str) -> dict:
    """Load the pooled DE matrix for one condition (log_fc + zscore, dense)."""
    with h5py.File(h5ad_path, "r") as f:
        gene_ids = _decode(f["var/gene_ids"][:])
        obs = f["obs"]
        cond = _obs_col(obs, "culture_condition").astype(object)
        sel = np.sort(np.where(cond == condition)[0])
        meta = {
            # EXACT obs.target_contrast. Its namespace is decided downstream by the
            # value itself -- never by the release key.
            "target_id": _obs_col(obs, "target_contrast")[sel],
            "target_symbol": _obs_col(obs, "target_contrast_gene_name")[sel],
            # EXACT obs.index: the unique release-estimate key. Never parsed.
            "released_estimate_id": np.array(
                _decode(obs[obs.attrs.get("_index", "index")][:]),
                dtype=object)[sel],
        }
        for name in _MAIN_OBS_FIELDS:
            meta[name] = _obs_col(obs, name)[sel] if name in obs else np.full(len(sel), None)
        log_fc = f["layers/log_fc"][sel, :].astype(np.float64)
        zscore = f["layers/zscore"][sel, :].astype(np.float64)
    return {
        "gene_ids": gene_ids,
        "gene_index": {g: i for i, g in enumerate(gene_ids)},
        "meta": meta,
        "log_fc": log_fc,
        "zscore": zscore,
        "n_targets": int(len(sel)),
    }


def load_main_gene_ids(h5ad_path: str) -> list[str]:
    """The pooled object's gene axis. ``var`` only — no dense layer is touched."""
    with h5py.File(h5ad_path, "r") as f:
        return _decode(f["var/gene_ids"][:])


def load_main_identity_universe(h5ad_path: str) -> dict[str, dict[str, Any]]:
    """The COMPLETE all-condition pooled-main release identity universe. METADATA ONLY.

    Reads obs.index / target_contrast / target_contrast_gene_name / culture_condition
    and NOTHING else — no ``layers``, no dense matrix. This is what the contributor
    manifest's scope universe is matched against (33,983 pooled-main scopes for the
    pinned release), and it is cheap enough to run in preflight, before any effect
    matrix is touched.

    Returns ``{condition -> {target_id -> {released_estimate_id, target_id,
    target_symbol}}}``, ready for ``identity.resolve``.
    """
    with h5py.File(h5ad_path, "r") as f:
        obs = f["obs"]
        cond = _obs_col(obs, "culture_condition").astype(object)
        target = _obs_col(obs, "target_contrast")
        symbol = _obs_col(obs, "target_contrast_gene_name")
        released = np.array(
            _decode(obs[obs.attrs.get("_index", "index")][:]), dtype=object)

    out: dict[str, dict[str, Any]] = {}
    for i in range(len(cond)):
        c = None if cond[i] is None else str(cond[i])
        if c is None:
            continue
        t = str(target[i])
        prior = out.setdefault(c, {}).get(t)
        row = {"released_estimate_id": released[i], "target_id": target[i],
               "target_symbol": symbol[i]}
        # ANY second row for a (condition, target) is fatal — including one whose
        # metadata is identical. A dict assignment would silently collapse it, so the
        # scope universe the manifest is matched against would hold ONE scope while the
        # dense loader still reads BOTH rows and scores both. Identity would then be
        # 1:many, the manifest would be "complete" over a universe smaller than the
        # release, and a dropped scope looks exactly like this. Equality of the two rows
        # is not a defence: two estimates that agree about their metadata are still two
        # estimates.
        if prior is not None:
            raise ValueError(
                f"pooled-main release: condition {c!r} ships {'two identical' if prior == row else 'two different'} "
                f"estimates for target {t!r} ({prior['released_estimate_id']!r} and "
                f"{released[i]!r}); the pooled-main scope universe is not unique per "
                "(condition, target) and cannot be matched against a contributor "
                "manifest")
        out[c][t] = row
    return out


def load_support_identities(h5mu_path: str, modality: str,
                            condition: str) -> dict[str, Any]:
    """One support modality's IDENTITY only: which targets it ships. ACCOUNTING ONLY.

    METADATA ONLY — no ``layers`` and no ``var`` read. Support carries no contributor
    evidence in this pass, so it is never projected and its gene axis never enters a
    score; it is enumerated purely so every released support estimate can be reported
    as explicitly unavailable instead of silently vanishing.

    ``n_guides`` is deliberately NOT read: in this release it is copied pooled metadata
    (59,414/59,414 guide rows; 29,279/29,279 donor rows), not the estimate's own
    contributor count, and reading it as one is the mistake this pass exists to remove.

    A duplicate target within one modality FAILS CLOSED, identical or not. Support is
    unavailable, so these identities are pure accounting — which is exactly why they
    must be counted honestly. Skipping the second row (the old behaviour) UNDERCOUNTS
    the released support estimates, and that count is bound into the support contract
    and into run_id: a run would then declare it had accounted for every released
    support estimate while having quietly dropped some.
    """
    with h5py.File(h5mu_path, "r") as f:
        obs = f[f"mod/{modality}"]["obs"]
        cond = _obs_col(obs, "culture_condition").astype(object)
        sel = np.sort(np.where(cond == condition)[0])
        target_ids = _obs_col(obs, "target_contrast")[sel]
        released_ids = np.array(
            _decode(obs[obs.attrs.get("_index", "index")][:]), dtype=object)[sel]

    by_target: dict[str, dict] = {}
    for i, t in enumerate(target_ids):
        if t is None:
            continue
        key = str(t)
        prior = by_target.get(key)
        row = {"released_estimate_id": str(released_ids[i])}
        if prior is not None:
            raise ValueError(
                f"support modality {modality!r}: condition {condition!r} ships "
                f"{'two identical' if prior == row else 'two different'} estimates for "
                f"target {key!r} ({prior['released_estimate_id']!r} and "
                f"{released_ids[i]!r}); a released support identity is not unique per "
                "(modality, condition, target) and cannot be accounted for")
        by_target[key] = row

    return {"by_target": by_target}


def load_support_modality(h5mu_path: str, modality: str, condition: str,
                          layer: str = "log_fc") -> dict:
    """Load one guide / donor-pair modality for a condition, keyed by target_id.

    ``by_target -> {"effect", "n_guides", "n_cells", "released_estimate_id"}``.

    The DENSE loader — it reads an effect layer. The Direct lane does not use it (support
    carries no contributor evidence there, so it is never projected); Perturb2State does.

    A duplicate ``(modality, condition, target)`` FAILS CLOSED, identical rows included.
    This loader used to keep the first and skip the rest, which is the same defect the
    pooled-main and identity loaders were fixed for, and it is worse here because a
    consumer of ``by_target`` gets an EFFECT VECTOR: silently keeping row 1 means every
    downstream number for that target comes from one arbitrarily-chosen released estimate
    while a second, equally released estimate is discarded without a trace. Two estimates
    that agree about their metadata are still two estimates, and choosing between them by
    file order is not a scientific rule.
    """
    with h5py.File(h5mu_path, "r") as f:
        mod = f[f"mod/{modality}"]
        gene_ids = _decode(mod["var/_index"][:]) if "_index" in mod["var"] \
            else _decode(mod["var/gene_ids"][:])
        obs = mod["obs"]
        cond = _obs_col(obs, "culture_condition").astype(object)
        sel = np.sort(np.where(cond == condition)[0])
        target_ids = _obs_col(obs, "target_contrast")[sel]
        released_ids = np.array(
            _decode(obs[obs.attrs.get("_index", "index")][:]), dtype=object)[sel]
        n_guides = (_obs_col(obs, "n_guides")[sel] if "n_guides" in obs
                    else np.full(len(sel), None))
        n_cells = (_obs_col(obs, "n_cells_target")[sel] if "n_cells_target" in obs
                   else np.full(len(sel), None))
        eff = mod[f"layers/{layer}"][sel, :].astype(np.float64)

    def _num(v):
        try:
            return None if v is None or np.isnan(float(v)) else float(v)
        except (TypeError, ValueError):
            return None

    by_target: dict[str, dict] = {}
    for i, t in enumerate(target_ids):
        if t is None:
            continue
        key = str(t)
        prior = by_target.get(key)
        if prior is not None:
            same = prior["released_estimate_id"] == str(released_ids[i])
            raise ValueError(
                f"support modality {modality!r}: condition {condition!r} ships "
                f"{'two identical' if same else 'two different'} estimates for target "
                f"{key!r} ({prior['released_estimate_id']!r} and {released_ids[i]!r}); "
                "a released support estimate is not unique per (modality, condition, "
                "target), and silently keeping the first would score one released "
                "estimate and discard the other")
        by_target[key] = {"effect": eff[i], "n_guides": _num(n_guides[i]),
                          "n_cells": _num(n_cells[i]),
                          "released_estimate_id": str(released_ids[i])}

    return {"gene_ids": gene_ids,
            "gene_index": {g: i for i, g in enumerate(gene_ids)},
            "by_target": by_target}


def list_modalities(h5mu_path: str) -> list[str]:
    with h5py.File(h5mu_path, "r") as f:
        return sorted(f["mod"].keys())


SGRNA_COLUMNS = [
    "sgRNA", "target_gene_id", "target_gene_name", "designed_target_gene_id",
    "distance_to_closest_target_tss", "nearby_gene_within_30kb",
    "other_alignment_chromosome", "other_alignment_pos",
    "nearest_nontarget_gene_id", "nearest_nontarget_gene_name",
    "nearest_nontarget_gene_dist",
]


def load_sgrna_rows_by_target(csv_path: str) -> dict[str, list[dict[str, Any]]]:
    """Group sgRNA-library rows by intended target Ensembl id."""
    import pandas as pd
    df = pd.read_csv(csv_path, usecols=lambda c: c in SGRNA_COLUMNS, low_memory=False)
    out: dict[str, list[dict]] = {}
    for rec in df.to_dict("records"):
        tgt = rec.get("target_gene_id")
        if tgt is None or str(tgt) in ("nan", ""):
            continue
        out.setdefault(str(tgt), []).append(rec)
    return out


def load_source_registry(path: Optional[str]) -> Optional[dict[str, dict]]:
    """Independently trusted pins for the contributor manifest's sources.

    name -> {"path", "sha256", "revision"}. This registry is the trust anchor: the
    manifest may not vouch for its own sources.
    """
    if not path:
        return None
    with open(path) as fh:
        doc = json.load(fh)
    entries = doc.get("sources", doc)
    return {str(k): v for k, v in entries.items()}


def load_donor_crosswalk(path: Optional[str]) -> Optional[dict[str, str]]:
    """Explicit Stage-1-donor-label -> release-donor-token crosswalk, if supplied."""
    if not path:
        return None
    with open(path) as fh:
        obj = json.load(fh)
    return obj.get("stage1_label_to_release_token", obj)
