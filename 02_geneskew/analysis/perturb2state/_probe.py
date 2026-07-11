"""One-off probe: build universe + signatures (cache), time one model fit."""
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))  # analysis/ on path

from direct import io_data                       # noqa: E402
import perturb2state.config as cfg               # noqa: E402
from perturb2state import universe as U          # noqa: E402
from perturb2state import signature_io as sio    # noqa: E402
from perturb2state import pmatrix, model_runner  # noqa: E402

NTC = os.path.expanduser("~/spot_stage2/work/ntc_clustered.h5ad")
DE = "/home/tcelab/datasets/marson2025_gwcd4_perturbseq/GWCD4i.DE_stats.h5ad"
REG = os.path.expanduser("~/spot_stage2/reg/stage01_program_registry.json")
OUT = os.path.expanduser("~/spot_stage2/outputs/26b866f2ad813d71")
CACHE = os.path.expanduser("~/spot_stage2/work/sig_cache.npz")


def main():
    t0 = time.time()
    programs, reg_sha, reg = io_data.load_registry(REG)
    axis = json.load(open(os.path.join(OUT, "axis.json")))
    print("registry+axis loaded", round(time.time() - t0, 1))

    main = io_data.load_main(DE, cfg.ANALYSIS_CONDITION)
    print("DE main loaded", round(time.time() - t0, 1), "targets", main["n_targets"])

    import h5py
    with h5py.File(NTC, "r") as f:
        ntc_syms = [x.decode() if isinstance(x, bytes) else str(x)
                    for x in f["var/_index"][:]]
    excluded = U.excluded_panel_control(axis)
    uni = U.build_universe(main["gene_ids"], main["gene_names"], ntc_syms, excluded)
    print("universe", uni["n_genes"], "excl", uni["exclusion_counts"],
          "sha", uni["universe_sha256"][:12], round(time.time() - t0, 1))

    built = sio.build_all_signatures(NTC, cfg.ANALYSIS_CONDITION, programs, axis, uni)
    print("signatures built; n_cells", built["n_cells"], "n_genes",
          len(built["gene_ids"]), "design", built["design_columns"],
          round(time.time() - t0, 1))
    hashes = sio.signature_hashes(built)
    print("sig hashes sample", {k: v[:10] for k, v in list(hashes.items())[:3]})

    # cache signatures
    save = {"gene_ids": np.array(built["gene_ids"], dtype=object)}
    for scope, sig in built["signatures"].items():
        for lane in cfg.LANES:
            save[f"{scope}::{lane}"] = sig[lane]
    np.savez(CACHE, **save)
    print("cached", CACHE)

    # eligible targets
    screen = pd.read_parquet(os.path.join(OUT, "screen.parquet"))
    elig = screen[screen["eligibility_state"].isin(cfg.ELIGIBLE_STATES)]
    targets = sorted(set(elig["target_ensembl"].astype(str)) &
                     set(main["meta"]["target_ensembl"].astype(str)))
    print("eligible targets", len(targets))

    masks_df = pd.read_parquet(os.path.join(OUT, "masks.parquet"))
    mask_by_target = pmatrix.mask_sets_from_parquet(masks_df)

    eff = {str(t): main["zscore"][i] for i, t in enumerate(main["meta"]["target_ensembl"])}
    X, cov = pmatrix.build_masked_X(eff, main["gene_ids"], built["gene_ids"],
                                    targets, mask_by_target)
    print("X shape", X.shape, round(time.time() - t0, 1))

    y = pd.Series(built["signatures"]["all_donor"]["combined_A_to_B"],
                  index=built["gene_ids"])
    tf = time.time()
    res = model_runner.run_one(X, y, cfg.CONFIGS[0], "probe_combined_all")
    print("ONE FIT seconds", round(time.time() - tf, 1))
    print("recon", res["recon"])
    c = res["coefs"]["coef_mean"].sort_values()
    print("n nonzero", int((res["coefs"]["coef_mean"].abs() > cfg.NONZERO_TOL).sum()),
          "of", len(c))
    print("top +", c.tail(5).round(4).to_dict())
    print("top -", c.head(5).round(4).to_dict())


if __name__ == "__main__":
    main()
