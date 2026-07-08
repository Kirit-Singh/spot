"""Cell QC + guide assignment + mixscape (cellqc stage).

Cells are called once on GEX; guides assigned ambient-aware; doublets removed;
mixscape labels CRISPRi escapers (kept, not dropped). Threshold logic is imported
from spot_pipeline.qc (tested); values come from CLI args (the manifest QC params).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import scanpy as sc
from spot_pipeline.qc import assign_guides, cell_qc_mask


def run(args: argparse.Namespace) -> None:
    adata = sc.read_10x_mtx(args.gex, var_names="gene_symbols")
    adata.var["mito"] = adata.var_names.str.upper().str.startswith("MT-")
    sc.pp.calculate_qc_metrics(adata, qc_vars=["mito"], percent_top=None, inplace=True)

    mask = cell_qc_mask(
        adata.obs["n_genes_by_counts"].to_numpy(),
        adata.obs["total_counts"].to_numpy(),
        adata.obs["pct_counts_mito"].to_numpy(),
        min_genes=args.min_genes,
        min_counts=args.min_counts,
        max_pct_mito=args.max_pct_mito,
        mad_nmads=args.mad_nmads,
    )
    adata = adata[mask].copy()

    sc.pp.scrublet(adata)
    adata = adata[~adata.obs["predicted_doublet"].to_numpy()].copy()

    _assign(adata, args.guides, args.min_guide_umi, flag_multiplets=args.flag_multiplets)
    if args.mixscape:
        _mixscape(adata)

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    adata.write_h5ad(out / "cells.h5ad")


def _assign(adata, guides_path, min_umi, *, flag_multiplets):
    guides = sc.read_h5ad(guides_path)
    guides = guides[guides.obs_names.isin(adata.obs_names)].copy()
    mat = guides.X.toarray() if hasattr(guides.X, "toarray") else np.asarray(guides.X)
    assigned, multiplet = assign_guides(mat, list(guides.var_names), min_umi)
    by_bc = dict(zip(guides.obs_names, assigned, strict=True))
    mult_bc = dict(zip(guides.obs_names, multiplet, strict=True))
    adata.obs["guide"] = [by_bc.get(bc, "unassigned") for bc in adata.obs_names]
    if flag_multiplets:
        adata.obs["guide_multiplet"] = [bool(mult_bc.get(bc, False)) for bc in adata.obs_names]


def _mixscape(adata):
    # Label CRISPRi escapers (non-perturbed cells); keep them, do not drop.
    try:
        import pertpy as pt
    except ImportError:
        adata.obs["mixscape_class"] = "not_run"
        return
    pt.tl.Mixscape().perturbation_signature(adata, pert_key="guide", control="NTC")


def _parse(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="spot cellqc: QC + guide assignment + mixscape")
    p.add_argument("--gex", required=True, help="STARsolo filtered matrix dir")
    p.add_argument("--guides", required=True, help="kite guide counts .h5ad")
    p.add_argument("--outdir", required=True)
    p.add_argument("--min-genes", dest="min_genes", type=int, default=200)
    p.add_argument("--min-counts", dest="min_counts", type=int, default=1000)
    p.add_argument("--max-pct-mito", dest="max_pct_mito", type=float, default=15.0)
    p.add_argument("--mad-nmads", dest="mad_nmads", type=float, default=5.0)
    p.add_argument("--min-guide-umi", dest="min_guide_umi", type=int, default=3)
    p.add_argument("--flag-multiplets", dest="flag_multiplets", action="store_true", default=True)
    p.add_argument("--mixscape", action="store_true", default=True)
    return p.parse_args(argv)


if __name__ == "__main__":
    run(_parse())
