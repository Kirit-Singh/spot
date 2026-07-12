"""Synthetic h5ad / h5mu / CSV writers for the direct-lane fixtures.

Structurally faithful to the release: categorical obs, ``layers/log_fc``, guide
slots WITHOUT sgRNA identity, six overlapping donor-pair modalities, and a donor
object whose gene universe is deliberately SMALLER than the pooled one.
"""
from __future__ import annotations

from typing import Optional, Sequence

import h5py
import numpy as np
from fixtures_spec import (
    A_PANEL,
    B_PANEL,
    CONDITION,
    DONOR_PAIRS,
    DONOR_UNIVERSE,
    SYMBOL_TARGETS,
    UNIVERSE,
    TargetSpec,
)


def _write_categorical(obs: h5py.Group, name: str, values: list[str]) -> None:
    cats = sorted(set(values))
    codes = np.array([cats.index(v) for v in values], dtype=np.int8)
    grp = obs.create_group(name)
    grp.create_dataset("categories", data=np.array(cats, dtype="S64"))
    grp.create_dataset("codes", data=codes)


def _scope_rows(specs: list[TargetSpec], conditions: Sequence[str],
                present: Optional[list[str]] = None) -> list[tuple[TargetSpec, str]]:
    """The released (target, condition) scopes this object ships, in emission order.

    Condition-major, so a single-condition object is byte-for-byte what it always was.
    """
    return [(s, c) for c in conditions for s in specs
            if present is None or s.target in present]


def _write_obs(grp: h5py.Group, specs: list[TargetSpec], n_guides_by_target=None,
               present: Optional[list[str]] = None,
               conditions: Sequence[str] = (CONDITION,)) -> None:
    rows = _scope_rows(specs, conditions, present)
    obs = grp.create_group("obs")
    obs.attrs["_index"] = "target_condition"
    obs.create_dataset("target_condition",
                       data=np.array([s.released_estimate_id_at(c) for s, c in rows],
                                     dtype="S64"))
    _write_categorical(obs, "culture_condition", [c for _, c in rows])
    _write_categorical(obs, "target_contrast", [s.target for s, _ in rows])
    # the spec owns the released identity; obs publishes it
    _write_categorical(obs, "target_contrast_gene_name",
                       [s.target_symbol for s, _ in rows])

    def ng(s: TargetSpec) -> float:
        if n_guides_by_target is not None:
            return n_guides_by_target.get(s.target, np.nan)
        return np.nan if s.n_guides is None else s.n_guides

    numeric = {
        "n_cells_target": [s.n_cells for s, _ in rows],
        "n_guides": [ng(s) for s, _ in rows],
        "ontarget_effect_size": [-1.0] * len(rows),
        "target_baseMean": [100.0] * len(rows),
        "guide_correlation_all": [0.5] * len(rows),
        "donor_correlation_all_mean": [0.5] * len(rows),
        "n_downstream": [10.0] * len(rows),
        "n_total_de_genes": [20.0] * len(rows),
    }
    for name, vals in numeric.items():
        obs.create_dataset(name, data=np.array(vals, dtype=np.float64))
    booleans = {
        "ontarget_significant": [s.ontarget_significant for s, _ in rows],
        "low_target_gex": [s.low_target_gex for s, _ in rows],
        "distal_offtarget_flag": [False] * len(rows),
        "neighboring_gene_KD": [True] * len(rows),
        "single_guide_estimate": [(s.n_guides or 0) <= 1 for s, _ in rows],
    }
    for name, vals in booleans.items():
        obs.create_dataset(name, data=np.array(vals, dtype=bool))


def _effect_matrix(rows: list[tuple[TargetSpec, str]], a_values: list[float],
                   b_values: list[float], genes: list[str] = None) -> np.ndarray:
    """A-panel genes carry a_effect, B-panel genes b_effect, everything else 0."""
    genes = genes or UNIVERSE
    mat = np.zeros((len(rows), len(genes)), dtype=np.float64)
    idx = {g: i for i, g in enumerate(genes)}
    for r, (a, b) in enumerate(zip(a_values, b_values)):
        for g in A_PANEL:
            mat[r, idx[g]] = a
        for g in B_PANEL:
            mat[r, idx[g]] = b
    return mat


def _write_main(path: str, specs: list[TargetSpec],
                conditions: Sequence[str] = (CONDITION,)) -> None:
    with h5py.File(path, "w") as f:
        var = f.create_group("var")
        var.create_dataset("gene_ids", data=np.array(UNIVERSE, dtype="S64"))
        var.create_dataset("gene_name", data=np.array(UNIVERSE, dtype="S64"))
        _write_obs(f, specs, conditions=conditions)
        rows = _scope_rows(specs, conditions)
        # THE TEMPORAL SIGNAL: each scope carries its OWN condition's effect.
        mat = _effect_matrix(rows, [s.effects_at(c)[0] for s, c in rows],
                             [s.effects_at(c)[1] for s, c in rows])
        layers = f.create_group("layers")
        layers.create_dataset("log_fc", data=mat)
        layers.create_dataset("zscore", data=mat * 2.0)


def _write_modality(f: h5py.File, name: str, specs: list[TargetSpec],
                    values: dict[str, float], n_guides: dict[str, float],
                    genes: list[str],
                    conditions: Sequence[str] = (CONDITION,)) -> None:
    present = [s.target for s in specs if s.target in values]
    rows = _scope_rows(specs, conditions, present)
    mod = f.create_group(f"mod/{name}")
    var = mod.create_group("var")
    var.create_dataset("_index", data=np.array(genes, dtype="S64"))
    _write_obs(mod, specs, n_guides_by_target=n_guides, present=present,
               conditions=conditions)
    mat = _effect_matrix(rows, [values[s.target] for s, _ in rows],
                         [s.effects_at(c)[1] for s, c in rows], genes=genes)
    mod.create_group("layers").create_dataset("log_fc", data=mat)


def _write_by_guide(path: str, specs: list[TargetSpec],
                    conditions: Sequence[str] = (CONDITION,)) -> None:
    with h5py.File(path, "w") as f:
        for slot in ("guide_1", "guide_2"):
            values = {s.target: s.guide_slot_effects[slot] for s in specs
                      if slot in s.guide_slot_effects}
            ng = {s.target: s.guide_slot_n_guides.get(
                slot, np.nan if s.n_guides is None else s.n_guides)
                for s in specs}
            _write_modality(f, slot, specs, values, ng, UNIVERSE,
                            conditions=conditions)


def _write_by_donors(path: str, specs: list[TargetSpec],
                     conditions: Sequence[str] = (CONDITION,)) -> None:
    with h5py.File(path, "w") as f:
        for pair in DONOR_PAIRS:
            values = {s.target: s.donor_pair_effects[pair] for s in specs
                      if pair in s.donor_pair_effects}
            ng = {s.target: s.donor_pair_n_guides.get(
                pair, np.nan if s.n_guides is None else s.n_guides)
                for s in specs}
            # deliberately a SMALLER gene universe than the pooled object
            _write_modality(f, pair, specs, values, ng, DONOR_UNIVERSE,
                            conditions=conditions)


def _write_sgrna(path: str, specs: list[TargetSpec]) -> None:
    """The sgRNA library is keyed by Ensembl gene id. A symbol-namespace target has
    no Ensembl id, so it simply has no library rows -- exactly as in the release."""
    import pandas as pd
    rows = []
    for s in specs:
        if s.target in SYMBOL_TARGETS:
            continue
        for g in s.lib_guides:
            neighbors = s.guide_neighbors.get(g, [])
            rows.append({
                "sgRNA": g,
                "target_gene_id": s.target,
                "target_gene_name": f"SYM{s.target[-2:]}",
                "designed_target_gene_id": s.target,
                "distance_to_closest_target_tss": 50.0,
                "nearby_gene_within_30kb": str([s.target] + neighbors).replace(",", ""),
                "other_alignment_chromosome": None,
                "other_alignment_pos": None,
                "nearest_nontarget_gene_id": None,
                "nearest_nontarget_gene_name": None,
                "nearest_nontarget_gene_dist": None,
            })
    pd.DataFrame(rows).to_csv(path, index=False)


