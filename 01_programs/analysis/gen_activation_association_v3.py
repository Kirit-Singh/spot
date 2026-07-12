#!/usr/bin/env python3
"""gen_activation_association_v3.py — activation association for EVERY program x condition/donor.

External review S1-M4: the UI named activation as a confound only for Treg-like and CD4 CTL-like, but the
association is broader (checkpoint is in fact the strongest). This computes, from the frozen 396k v3 score
parquet, the Spearman rho of every program score against ``diff_activated_score`` — pooled, and per
condition x donor (the within-stratum association that pooled timepoint structure can mask). It is purely
DESCRIPTIVE: no p, q, FDR or calibrated null (consistent with the Stage-1 firewall). The pooled CD4-CTL
activation-adjusted residual (``cd4_ctl_like_score_actadj``) IS included; the activation axis
``diff_activated_score`` is the reference and is not self-correlated.

Emits ``stage01_activation_association_v1.json`` (schema spot.stage01_activation_association.v1).
Run on tcefold (has the parquet + pyarrow):
    python gen_activation_association_v3.py --parquet /home/tcelab/cs_scratch/stage01_scores_full.parquet \
        --out stage01_activation_association_v1.json
"""
from __future__ import annotations

import argparse
import hashlib
import json

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

ACT = "diff_activated_score"


def _rho(x, y):
    if len(x) < 3:
        return None
    return round(float(spearmanr(x, y).statistic), 6)


def compute(df: pd.DataFrame) -> dict:
    meta = {"barcode", "donor", "condition"}
    # every program score + the CD4-CTL activation-adjusted residual (…_actadj), excluding the activation
    # axis itself (ACT) and the id/metadata columns. NB: the residual ends in `_actadj`, not `_score`, so a
    # `_score` suffix filter would silently drop it (external review S1-M4 re-audit).
    fields = [c for c in df.columns if c not in meta and c != ACT]
    conds = sorted(map(str, df["condition"].unique()))
    donors = sorted(map(str, df["donor"].unique()))
    a_all = df[ACT].to_numpy()
    cond_arr = df["condition"].to_numpy().astype(str)
    donor_arr = df["donor"].to_numpy().astype(str)
    out = {
        "schema": "spot.stage01_activation_association.v1",
        "estimand": "spearman_rho_vs_diff_activated_score",
        "inference_status": "descriptive_only_no_p_q_fdr",
        "note_scope": "association is confounded by timepoint structure; a residual is a sensitivity check, not deconfounding",
        "n_cells": int(len(df)),
        "conditions": conds,
        "donors": donors,
        "programs": {},
    }
    for f in fields:
        x = df[f].to_numpy()
        rec = {"pooled_rho": _rho(x, a_all), "by_condition": {}}
        for c in conds:
            mc = cond_arr == c
            byd = {}
            for d in donors:
                md = mc & (donor_arr == d)
                r = _rho(x[md], a_all[md]) if md.sum() > 2 else None
                if r is not None:
                    byd[d] = r
            rec["by_condition"][c] = {
                "donor_rho": byd,
                "max_abs_donor_rho": round(max((abs(v) for v in byd.values()), default=0.0), 6),
            }
        rec["max_abs_donor_rho_any_condition"] = round(
            max((v["max_abs_donor_rho"] for v in rec["by_condition"].values()), default=0.0), 6)
        out["programs"][f] = rec
    out["pooled_ranking"] = [[f, out["programs"][f]["pooled_rho"]]
                             for f in sorted(fields, key=lambda f: -abs(out["programs"][f]["pooled_rho"] or 0))]
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parquet", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args(argv)
    out = compute(pd.read_parquet(args.parquet))
    txt = json.dumps(out, indent=1, ensure_ascii=True, sort_keys=False)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(txt)
        print("wrote", args.out)
    print("pooled activation association (|rho| desc):")
    for f, r in out["pooled_ranking"]:
        print(f"  {f:30s} pooled_rho={r:+.4f}  max_abs_donor_rho={out['programs'][f]['max_abs_donor_rho_any_condition']:+.4f}")
    print("content_sha256:", hashlib.sha256(txt.encode()).hexdigest())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
