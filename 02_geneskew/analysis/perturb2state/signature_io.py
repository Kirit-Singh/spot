"""IO-heavy broad target-signature construction from the 396k NTC cells.

Runs on the configured analysis host. Reads the median-normalised log1p NTC expression matrix
(var index = symbols), reproduces the frozen Stage-1 A/B/activation scores,
standardises them within donor, builds donor-stratified pseudobulk quantile
bins, and fits the per-gene donor-aware WLS to produce the away/toward/combined
target signatures for the all-donor scope and the four LODO scopes (plan §6.2).

The heavy read is isolated here; all numeric logic lives in ``signature.py``.
"""
from __future__ import annotations

import numpy as np

from . import config, signature
from direct.hashing import content_hash, round_float


def _symbol_cols(symbols: list[str], want: list[str]) -> list[int]:
    idx = {s: i for i, s in enumerate(symbols)}
    return [idx[s] for s in want if s in idx]


def _decode_cat(grp) -> np.ndarray:
    import h5py
    cats = np.array([x.decode() if isinstance(x, (bytes, bytearray)) else str(x)
                     for x in grp["categories"][:]], dtype=object)
    codes = grp["codes"][:]
    out = np.empty(codes.shape, dtype=object)
    valid = codes >= 0
    out[valid] = cats[codes[valid]]
    out[~valid] = None
    return out


def _load_stim_matrix(ntc_path: str, condition: str, want_symbols: list[str],
                      chunk: int = 20000):
    """Memory-safe dense load of the wanted symbols in one condition.

    Reads the CSR in contiguous row blocks (never the whole 396k matrix at once)
    and keeps only the requested columns. Returns (expr [cells x present],
    donors, present_symbols) with rows ordered as in the file.
    """
    import h5py
    from scipy import sparse

    with h5py.File(ntc_path, "r") as f:
        var_syms = [x.decode() if isinstance(x, (bytes, bytearray)) else str(x)
                    for x in f["var/_index"][:]]
        sym_to_col = {s: i for i, s in enumerate(var_syms)}
        present = [s for s in want_symbols if s in sym_to_col]
        col_idx = np.array([sym_to_col[s] for s in present], dtype=np.int64)

        cond = _decode_cat(f["obs/condition"]).astype(object)
        donor_all = _decode_cat(f["obs/donor"]).astype(object)
        row_mask = cond == condition
        sel_rows = np.where(row_mask)[0]
        donors = donor_all[sel_rows]

        Xg = f["X"]
        n_cols = int(Xg.attrs["shape"][1])
        indptr = Xg["indptr"][:]
        data_ds, ind_ds = Xg["data"], Xg["indices"]

        expr = np.zeros((sel_rows.shape[0], col_idx.shape[0]), dtype=np.float32)
        out_pos = {int(r): k for k, r in enumerate(sel_rows)}
        n_all = indptr.shape[0] - 1
        for b0 in range(0, n_all, chunk):
            b1 = min(b0 + chunk, n_all)
            block = [r for r in range(b0, b1) if row_mask[r]]
            if not block:
                continue
            s, e = int(indptr[b0]), int(indptr[b1])
            d = data_ds[s:e]
            idx = ind_ds[s:e]
            local_indptr = indptr[b0:b1 + 1] - s
            m = sparse.csr_matrix((d, idx, local_indptr), shape=(b1 - b0, n_cols))
            sub = m[:, col_idx].toarray().astype(np.float32)
            for local_r in range(b1 - b0):
                gr = b0 + local_r
                if row_mask[gr]:
                    expr[out_pos[gr]] = sub[local_r]
    return expr, donors, present


def build_all_signatures(ntc_path: str, condition: str, programs: dict,
                         axis: dict, universe: dict) -> dict:
    """Construct away/toward/combined signatures for all-donor + 4 LODO scopes."""
    a_prog = programs[axis["A"]["program_id"]]
    b_prog = programs[axis["B"]["program_id"]]
    act_prog = programs[config.ACTIVATION_PROGRAM_ID]

    score_syms = sorted(set(
        list(a_prog["panel_symbols"]) + list(a_prog["control_symbols"]) +
        list(b_prog["panel_symbols"]) + list(b_prog["control_symbols"]) +
        list(act_prog["panel_symbols"]) + list(act_prog["control_symbols"])))
    universe_syms = list(universe["symbols"])
    want = sorted(set(score_syms) | set(universe_syms))

    expr, donors, present = _load_stim_matrix(ntc_path, condition, want)
    sym_to_col = {s: i for i, s in enumerate(present)}

    def cols(symbols):
        return [sym_to_col[s] for s in symbols if s in sym_to_col]

    score_a = signature.program_score(expr, cols(a_prog["panel_symbols"]),
                                       cols(a_prog["control_symbols"]))
    score_b = signature.program_score(expr, cols(b_prog["panel_symbols"]),
                                       cols(b_prog["control_symbols"]))
    score_act = signature.program_score(expr, cols(act_prog["panel_symbols"]),
                                        cols(act_prog["control_symbols"]))

    sign_a = 1 if axis["A"]["direction"] == "high" else -1
    sign_b = 1 if axis["B"]["direction"] == "high" else -1
    z_a = sign_a * signature.within_donor_z(score_a, donors)
    z_b = sign_b * signature.within_donor_z(score_b, donors)
    z_act = signature.within_donor_z(score_act, donors)

    # Expression restricted to the readout universe, ordered as universe gene_ids.
    # Keep float32 and free the full matrix immediately (peak-memory control: a
    # float64 copy here doubled RAM and previously thrashed the 31 GB host).
    uni_cols = [sym_to_col[s] for s in universe_syms if s in sym_to_col]
    kept_gene_ids = [g for g, s in zip(universe["gene_ids"], universe_syms)
                     if s in sym_to_col]
    expr_uni = np.ascontiguousarray(expr[:, uni_cols], dtype=np.float32)
    del expr

    scopes = {"all_donor": None}
    for d in config.DONORS:
        scopes[f"lodo_{d}"] = d

    out_signatures: dict[str, dict] = {}
    for scope, drop in scopes.items():
        if drop is None:
            m = slice(None)                      # all-donor: no copy
        else:
            m = donors != drop
        pb = signature.build_pseudobulk(z_a[m], z_b[m], z_act[m], donors[m],
                                        expr_uni[m], config.N_SCORE_BINS)
        sig = signature.build_signature_frame(pb, kept_gene_ids)
        out_signatures[scope] = sig

    return {
        "signatures": out_signatures,
        "gene_ids": kept_gene_ids,
        "n_cells": int(donors.shape[0]),
        "scoring_symbols_present": {
            "A_panel": cols(a_prog["panel_symbols"]) and len(cols(a_prog["panel_symbols"])),
            "A_control": len(cols(a_prog["control_symbols"])),
            "B_panel": len(cols(b_prog["panel_symbols"])),
            "B_control": len(cols(b_prog["control_symbols"])),
            "activation_panel": len(cols(act_prog["panel_symbols"])),
            "activation_control": len(cols(act_prog["control_symbols"])),
        },
        "activation_program_id": config.ACTIVATION_PROGRAM_ID,
        "design_columns": out_signatures["all_donor"]["design_columns"],
    }


def signature_hashes(built: dict) -> dict:
    """Hash each (scope, lane) signature over the ordered gene universe (§6.2.10)."""
    hashes = {}
    gene_ids = built["gene_ids"]
    for scope, sig in built["signatures"].items():
        for lane in config.LANES:
            vec = sig[lane]
            payload = {"gene_ids": gene_ids,
                       "values": [round_float(float(v)) for v in vec]}
            hashes[f"{scope}::{lane}"] = content_hash(payload)
    return hashes
