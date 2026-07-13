"""THE REAL CELLS: the pinned Marson matrix, joined to Stage-1's scores BY BARCODE.

THREE THINGS THIS MODULE REFUSES TO DO
--------------------------------------
  * **recompute a Stage-1 score.** They are READ, by barcode, from the authoritative full
    table. A recomputed score is a different score wearing the released one's name — and it
    would agree with the released one closely enough that nobody would ever check;
  * **guess a gene.** The cell matrix is keyed on SYMBOLS and the readout universe is
    ENSEMBL. A symbol naming more than one Ensembl id is DROPPED with a named reason, never
    resolved by picking one. The crosswalk is the DE readout's own ``gene_name -> gene_ids``;
  * **impute a cell.** A cell with no score row is a REFUSAL, not a zero. An absent score is
    not a score of zero, and a barcode that joined to nothing is a barcode that means nothing.

MEMORY
------
``.X`` is CSR float32, 396,000 x 18,130 (~1.6e9 nonzeros). It is read in ROW CHUNKS and
densified only over the cells of ONE condition and the genes of the readout universe — never
the whole cohort at once. The NAS is seek-bound and the host RAM is tight; a full densify
would be ~29 GB before anything useful happened.
"""
from __future__ import annotations

from typing import Any, Optional

import h5py
import numpy as np
import pandas as pd

from . import config, stage1_canonical
from . import disposition as D

CHUNK_ROWS = 20_000


def _decode(a) -> list[str]:
    return [x.decode() if isinstance(x, bytes) else str(x) for x in a]


def read_obs_column(obs: h5py.Group, name: str) -> np.ndarray:
    """An obs column, categorical or plain. AnnData stores strings either way."""
    node = obs[name]
    if isinstance(node, h5py.Group):                      # categorical
        cats = _decode(node["categories"][:])
        codes = node["codes"][:]
        return np.asarray([cats[c] if c >= 0 else None for c in codes], dtype=object)
    return np.asarray(_decode(node[:]), dtype=object)


def load_scores(path: str, condition: str, program_ids: list[str]) -> dict[str, Any]:
    """Stage-1's FULL by-barcode score table, for one condition. READ, never recomputed.

    Gated on BOTH hashes: the raw sha256 pins the bytes, and the CANONICAL score hash
    (re-derived here) pins the science those bytes encode in Stage-1's frozen form. A
    re-rounded or re-ordered table would pass a raw check it happened to match and fail this.
    """
    df = pd.read_parquet(path)
    canonical = stage1_canonical.verify(df)          # REFUSES on a canonical mismatch

    for col in ("barcode", "donor", "condition"):
        if col not in df.columns:
            raise D.RefusalError(
                D.REFUSE_PROGRAM_SET_MISMATCH,
                f"the Stage-1 score table has no {col!r} column; it is not the authoritative "
                "by-barcode table")

    # THE ADMITTED PROGRAMS must all be scored. A program the release admits but Stage-1
    # never scored cannot carry an arm, and silently dropping it would shrink the release.
    want = {p: f"{p}{config.SCORE_FIELD_SUFFIX}" for p in program_ids}
    missing = sorted(p for p, c in want.items() if c not in df.columns)
    if missing:
        raise D.RefusalError(
            D.REFUSE_PROGRAM_SET_MISMATCH,
            f"the Stage-1 score table scores no column for admitted program(s) {missing}. "
            f"It carries {sorted(c for c in df.columns if c.endswith(config.SCORE_FIELD_SUFFIX))}")

    dup = df["barcode"].duplicated()
    if dup.any():
        examples = df.loc[dup, "barcode"].head(3).tolist()
        raise D.RefusalError(
            D.REFUSE_DUPLICATE_BARCODE,
            f"{int(dup.sum())} duplicate barcode(s) in the Stage-1 score table (e.g. "
            f"{examples}). A barcode that names two score rows names neither: the join would "
            "silently pick one, and which one it picked would depend on row order")

    n_all = len(df)
    sub = df[df["condition"].astype(str) == condition]
    if sub.empty:
        raise D.RefusalError(
            D.REFUSE_CONDITION_MISMATCH,
            f"the Stage-1 score table has no cell at condition {condition!r}; it carries "
            f"{sorted(df['condition'].astype(str).unique())}")

    return {
        "by_barcode": sub.set_index("barcode"),
        "score_columns": want,
        "n_rows_all_conditions": n_all,
        "n_rows_condition": len(sub),
        "conditions_present": sorted(df["condition"].astype(str).unique().tolist()),
        "canonical": canonical,
    }


def crosswalk_symbols(*, cell_symbols: list[str], readout_gene_ids: list[str],
                      readout_symbols: list[str]) -> dict[str, Any]:
    """SYMBOL -> ENSEMBL, using the DE readout's OWN pairing. Ambiguity is dropped, not guessed.

    The readout is the authority here: it is the namespace the arms are computed in, so a
    symbol that it does not name is not a readout gene at all, whatever the cell matrix calls
    it.
    """
    by_symbol: dict[str, set] = {}
    for ens, sym in zip(readout_gene_ids, readout_symbols):
        if sym:
            by_symbol.setdefault(str(sym), set()).add(str(ens))

    resolved: dict[str, str] = {}
    ambiguous: list[str] = []
    absent: list[str] = []

    for sym in cell_symbols:
        ids = by_symbol.get(str(sym))
        if not ids:
            absent.append(sym)
        elif len(ids) > 1:
            # NEVER guessed. Picking one would attach this cell's expression to a gene
            # nobody chose, and the number would look entirely reasonable.
            ambiguous.append(sym)
        else:
            resolved[sym] = next(iter(ids))

    if not resolved:
        raise D.RefusalError(
            D.REFUSE_NAMESPACE_DRIFT,
            f"not one of the {len(cell_symbols)} cell-matrix symbols resolves to an Ensembl "
            f"id in the DE readout ({len(readout_gene_ids)} genes). The two files are not "
            "describing the same genes, and a run across them would be reconstructing one "
            "organism's expression from another's perturbations")

    return {
        "symbol_to_ensembl": resolved,
        "n_cell_symbols": len(cell_symbols),
        "n_resolved": len(resolved),
        "n_ambiguous_dropped": len(ambiguous),
        "n_absent_from_readout": len(absent),
        "ambiguous_examples": sorted(ambiguous)[:5],
        "namespace_rule_id": config.NAMESPACE_RULE_ID,
        "ambiguous_symbols_are_dropped_never_guessed": True,
    }


def _read_csr_rows(x: h5py.Group, rows: np.ndarray, cols: np.ndarray,
                   n_genes: int) -> np.ndarray:
    """Densify SELECTED rows over SELECTED columns, in chunks. Never the whole cohort."""
    indptr = x["indptr"][:]
    data, indices = x["data"], x["indices"]

    keep = np.full(n_genes, -1, dtype=np.int64)
    keep[cols] = np.arange(len(cols), dtype=np.int64)

    out = np.zeros((len(rows), len(cols)), dtype=np.float32)
    order = np.argsort(rows)
    rows_sorted = rows[order]

    for start in range(0, len(rows_sorted), CHUNK_ROWS):
        block = rows_sorted[start:start + CHUNK_ROWS]
        lo, hi = int(indptr[block.min()]), int(indptr[block.max() + 1])
        d = data[lo:hi]
        ix = indices[lo:hi]
        for k, r in enumerate(block):
            s, e = int(indptr[r]) - lo, int(indptr[r + 1]) - lo
            gi = keep[ix[s:e]]
            hit = gi >= 0
            out[order[start + k], gi[hit]] = d[s:e][hit]
    return out


def build(*, ntc_path: str, scores_path: str, condition: str, program_ids: list[str],
          readout_gene_ids: list[str], readout_symbols: list[str],
          max_cells: Optional[int] = None, seed: int = 42) -> dict[str, Any]:
    """The prepared cell block: barcodes, donors, Ensembl gene ids, expr, and READ scores."""
    scores = load_scores(scores_path, condition, program_ids)
    by_barcode = scores["by_barcode"]

    with h5py.File(ntc_path, "r") as f:
        obs = f["obs"]
        cond = read_obs_column(obs, "condition").astype(str)
        sel = np.where(cond == condition)[0]
        if sel.size == 0:
            raise D.RefusalError(
                D.REFUSE_CONDITION_MISMATCH,
                f"the cell matrix has no cell at condition {condition!r}; it carries "
                f"{sorted(set(cond.tolist()))}")

        barcodes = read_obs_column(obs, "barcode").astype(str)[sel]
        donors = read_obs_column(obs, "donor").astype(str)[sel]
        cell_symbols = _decode(f["var"][f["var"].attrs.get("_index", "_index")][:])

        # THE JOIN. Every selected cell must carry a Stage-1 score row.
        have = by_barcode.index
        missing_mask = ~pd.Index(barcodes).isin(have)
        n_missing = int(missing_mask.sum())
        if n_missing:
            raise D.RefusalError(
                D.REFUSE_MISSING_BARCODE,
                f"{n_missing} of {len(barcodes)} cell(s) at {condition!r} have no Stage-1 "
                f"score row (e.g. {barcodes[missing_mask][:2].tolist()}). An absent score is "
                "not a score of zero, and this lane never recomputes one")

        if pd.Index(barcodes).duplicated().any():
            raise D.RefusalError(
                D.REFUSE_DUPLICATE_BARCODE,
                "the cell matrix carries a duplicate barcode at this condition")

        # a DETERMINISTIC, donor-balanced subsample — for the SMOKE only, and recorded.
        subsample = {"applied": False, "n_requested": None, "seed": None, "rule": None}
        if max_cells is not None and max_cells < len(sel):
            rng = np.random.default_rng(seed)
            picks: list[int] = []
            per = max(1, max_cells // max(1, len(set(donors.tolist()))))
            for d in sorted(set(donors.tolist())):
                idx = np.where(donors == d)[0]
                picks += rng.choice(idx, size=min(per, len(idx)), replace=False).tolist()
            take = np.sort(np.asarray(picks[:max_cells], dtype=int))
            sel, barcodes, donors = sel[take], barcodes[take], donors[take]
            subsample = {"applied": True, "n_requested": int(max_cells), "seed": int(seed),
                         "rule": "donor-balanced, seeded, without replacement"}

        xw = crosswalk_symbols(cell_symbols=cell_symbols,
                               readout_gene_ids=readout_gene_ids,
                               readout_symbols=readout_symbols)
        mapping = xw["symbol_to_ensembl"]

        # the readout universe, in the ONE canonical order, restricted to what the cells have
        sym_of_col = {i: s for i, s in enumerate(cell_symbols) if s in mapping}
        pairs = sorted(((mapping[s], i) for i, s in sym_of_col.items()))
        gene_ids = [ens for ens, _ in pairs]
        cols = np.asarray([i for _, i in pairs], dtype=np.int64)

        expr = _read_csr_rows(f["X"], np.asarray(sel, dtype=np.int64), cols,
                              n_genes=len(cell_symbols))

    aligned = by_barcode.loc[barcodes]
    score_arrays = {p: aligned[c].to_numpy(dtype=float)
                    for p, c in scores["score_columns"].items()}

    return {
        "barcodes": barcodes,
        "donors": donors,
        "gene_ids": gene_ids,                      # ENSEMBL, canonical order
        "expr": expr,                              # float32, cells x readout genes
        "scores": score_arrays,                    # READ by barcode
        "crosswalk": xw,
        "subsample": subsample,
        "join": {
            "n_cells_at_condition": int(len(barcodes)),
            "n_score_rows_at_condition": int(scores["n_rows_condition"]),
            "n_score_rows_all_conditions": int(scores["n_rows_all_conditions"]),
            "n_cells_without_a_score_row": 0,      # a nonzero here is a refusal, above
            "join_key": "barcode",
            "scores_are_read_not_recomputed": True,
        },
        "dims": {"n_cells": int(len(barcodes)), "n_genes": int(len(gene_ids)),
                 "n_donors": int(len(set(donors.tolist())))},
        "donors_present": sorted(set(donors.tolist())),
        "conditions_present": scores["conditions_present"],
        "canonical": scores["canonical"],
    }
