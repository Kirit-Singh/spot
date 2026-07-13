"""CLEARLY SYNTHETIC, Marson-SHAPED inputs for the preparation lane.

Tiny, but structurally REAL: CSR float32 storage, AnnData's categorical obs groups, the real
obs/var layout, the real barcode format, SYMBOLS in the cell matrix and ENSEMBL in the DE
readout. Only the numbers are made up.

That distinction is the whole value. A fixture that wrote a plain byte obs column instead of
a categorical would compare bytes to str, select zero rows, and "prove" the loader works.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from . import config as _cfg
from .synthetic import DONORS

# --------------------------------------------------------------------------- #
# A tiny but STRUCTURALLY REAL Marson-shaped cell matrix + Stage-1 score table.
#
# The shapes, the CSR storage, the obs/var layout and the barcode format are the real ones —
# only the numbers are synthetic. The preparation lane is exercised against the layout it
# will actually meet, not against a shape invented to make it pass.
# --------------------------------------------------------------------------- #
CELL_SYMBOLS = ["GENE_A", "GENE_B", "GENE_C", "GENE_D", "AMBIG", "ONLY_IN_CELLS"]


def _barcode(donor: str, cond: str, i: int) -> str:
    return f"{donor}_{cond}_{i:016d}-1_CD4i_R1L01_CD4i_R1_{donor}_{cond}_CD4i_R1_Ultima"


def write_ntc_h5ad(path: str, *, conditions=("Rest", "Stim48hr"), n_per: int = 60,
                   symbols=None, seed: int = 5) -> str:
    """A CSR float32 h5ad with obs/barcode, obs/donor, obs/condition and SYMBOL var index."""
    import h5py
    from scipy import sparse

    symbols = list(symbols or CELL_SYMBOLS)
    rng = np.random.default_rng(seed)
    barcodes, donors, conds = [], [], []
    for c in conditions:
        for i in range(n_per):
            d = DONORS[i % len(DONORS)]
            barcodes.append(_barcode(d, c, i))
            donors.append(d)
            conds.append(c)

    x = rng.random((len(barcodes), len(symbols))).astype(np.float32)
    x[x < 0.25] = 0.0
    csr = sparse.csr_matrix(x)

    with h5py.File(path, "w") as f:
        g = f.create_group("X")
        g.create_dataset("data", data=csr.data)
        g.create_dataset("indices", data=csr.indices)
        g.create_dataset("indptr", data=csr.indptr)
        obs = f.create_group("obs")
        obs.attrs["_index"] = "_index"
        for name, vals in (("_index", barcodes), ("barcode", barcodes),
                           ("donor", donors), ("condition", conds)):
            obs.create_dataset(name, data=np.asarray(vals, dtype="S200"))
        var = f.create_group("var")
        var.attrs["_index"] = "_index"
        var.create_dataset("_index", data=np.asarray(symbols, dtype="S64"))
    return path


def write_stage1_scores(path: str, ntc_path: str, program_ids, *,
                        drop_barcodes: int = 0, duplicate: bool = False,
                        omit_program: Optional[str] = None, seed: int = 6) -> str:
    """The authoritative by-barcode score table, in Stage-1's own column convention."""
    import h5py

    rng = np.random.default_rng(seed)
    with h5py.File(ntc_path, "r") as f:
        obs = f["obs"]
        bc = [b.decode() for b in obs["barcode"][:]]
        dn = [b.decode() for b in obs["donor"][:]]
        cd = [b.decode() for b in obs["condition"][:]]

    rows = []
    for b, d, c in zip(bc, dn, cd):
        r = {"barcode": b, "donor": d, "condition": c}
        for p in program_ids:
            if p == omit_program:
                continue
            r[f"{p}{_cfg.SCORE_FIELD_SUFFIX}"] = float(rng.normal())
        rows.append(r)

    if drop_barcodes:
        # from the TAIL. Dropping from the head would only lose cells of the FIRST condition,
        # and a test on any other condition would join cleanly and prove nothing.
        rows = rows[:-drop_barcodes]
    if duplicate and rows:
        rows.append(dict(rows[0]))

    pd.DataFrame(rows).to_parquet(path, index=False)
    return path


def write_de_readout(path: str, targets, *, conditions=("Rest", "Stim48hr"),
                     gene_ids=None, symbols=None, seed: int = 8) -> str:
    """A DE h5ad with var/gene_ids (ENSEMBL) + var/gene_name (SYMBOL) and the two layers."""
    import h5py

    gene_ids = list(gene_ids or [f"ENSG{i:011d}" for i in range(len(CELL_SYMBOLS) - 1)])
    symbols = list(symbols or CELL_SYMBOLS[:len(gene_ids)])
    rng = np.random.default_rng(seed)

    obs_t, obs_c = [], []
    for c in conditions:
        for t in targets:
            obs_t.append(t)
            obs_c.append(c)
    n = len(obs_t)

    with h5py.File(path, "w") as f:
        var = f.create_group("var")
        var.attrs["_index"] = "_index"
        var.create_dataset("_index", data=np.asarray(gene_ids, dtype="S64"))
        var.create_dataset("gene_ids", data=np.asarray(gene_ids, dtype="S64"))
        var.create_dataset("gene_name", data=np.asarray(symbols, dtype="S64"))
        obs = f.create_group("obs")
        obs.attrs["_index"] = "_index"
        obs.create_dataset("_index",
                           data=np.asarray([f"{t}|{c}" for t, c in zip(obs_t, obs_c)],
                                           dtype="S80"))

        # AnnData stores a string obs column as a CATEGORICAL group ({categories, codes}),
        # and `direct.io_data.load_main` reads it as one. A fixture that wrote a plain byte
        # dataset would compare bytes to str, select zero rows, and "prove" the loader works.
        def _categorical(name, values):
            cats = sorted(set(values))
            code = {v: i for i, v in enumerate(cats)}
            g = obs.create_group(name)
            g.create_dataset("categories", data=np.asarray(cats, dtype="S64"))
            g.create_dataset("codes", data=np.asarray([code[v] for v in values],
                                                      dtype=np.int32))

        _categorical("target_contrast", obs_t)
        _categorical("target_contrast_gene_name", obs_t)
        _categorical("culture_condition", obs_c)
        layers = f.create_group("layers")
        layers.create_dataset("zscore", data=rng.normal(size=(n, len(gene_ids))))
        layers.create_dataset("log_fc", data=rng.normal(size=(n, len(gene_ids))) * 0.8)
    return path
