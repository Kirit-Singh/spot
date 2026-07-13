"""Perturb2State orchestrator (plan §6.2-§6.8). Runs on tcedirector.

Emits under ``<out_root>/<contrast_id>/perturb2state/``:
  target_signatures.parquet, coefficients.parquet, reconstruction_metrics.parquet,
  stability.parquet, model_manifest.json, verification.json.

This module GENERATES artifacts; it does NOT assert its own correctness — the
§6.9 tests and an independent verifier check the numbers (plan §1). Perturb2State
is SECONDARY: nothing here changes the direct Stage-2 ranking (§6.7).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..")))  # analysis/ on path

from direct import io_data  # noqa: E402
from direct.hashing import content_hash, file_sha256, round_float  # noqa: E402

from perturb2state import config as cfg  # noqa: E402
from perturb2state import model_runner, pmatrix, stability  # noqa: E402
from perturb2state import signature_io as sio  # noqa: E402
from perturb2state import universe as U  # noqa: E402


def _ntc_symbols(ntc_path: str) -> list[str]:
    import h5py
    with h5py.File(ntc_path, "r") as f:
        return [x.decode() if isinstance(x, (bytes, bytearray)) else str(x)
                for x in f["var/_index"][:]]


def _de_var(de_main_path: str) -> tuple[list[str], list[str]]:
    """Cheap read of the DE gene axis (Ensembl + symbol) without any layer."""
    import h5py
    with h5py.File(de_main_path, "r") as f:
        ids = [x.decode() if isinstance(x, (bytes, bytearray)) else str(x)
               for x in f["var/gene_ids"][:]]
        names = [x.decode() if isinstance(x, (bytes, bytearray)) else str(x)
                 for x in f["var/gene_name"][:]]
    return ids, names


def _build_or_load_signatures(args, programs, axis, uni, log):
    cache = args.sig_cache
    if cache and os.path.exists(cache) and args.use_cache:
        z = np.load(cache, allow_pickle=True)
        gene_ids = [str(g) for g in z["gene_ids"]]
        sigs = {}
        for k in z.files:
            if "::" in k:
                scope, lane = k.split("::")
                sigs.setdefault(scope, {})[lane] = z[k]
        meta = json.load(open(cache + ".meta.json"))
        log(f"signatures loaded from cache: {len(gene_ids)} genes")
        return {"signatures": sigs, "gene_ids": gene_ids, **meta}, \
            {k: v for k, v in z.items() if "::" in k}
    built = sio.build_all_signatures(args.ntc, cfg.ANALYSIS_CONDITION,
                                     programs, axis, uni)
    log(f"signatures built: n_cells={built['n_cells']} genes={len(built['gene_ids'])}")
    if cache:
        save = {"gene_ids": np.array(built["gene_ids"], dtype=object)}
        for scope, sig in built["signatures"].items():
            for lane in cfg.LANES:
                save[f"{scope}::{lane}"] = sig[lane]
        np.savez(cache, **save)
        json.dump({"n_cells": built["n_cells"],
                   "scoring_symbols_present": built["scoring_symbols_present"],
                   "activation_program_id": built["activation_program_id"],
                   "design_columns": built["design_columns"]},
                  open(cache + ".meta.json", "w"))
    return built, None


def _signature_table(built, hashes) -> pd.DataFrame:
    rows = []
    gene_ids = built["gene_ids"]
    for scope, sig in built["signatures"].items():
        for lane in cfg.LANES:
            vec = sig[lane]
            for g, v in zip(gene_ids, vec):
                rows.append({"donor_scope": scope, "lane": lane,
                             "gene_ensembl": g, "value": round_float(float(v))})
    df = pd.DataFrame(rows)
    return df


def _run_plan(X_by_layer, signatures, gene_ids, coverage_by_layer, log):
    """Execute the frozen run plan; return (coef_records, recon_records)."""
    coef_records, recon_records = [], []

    def do_run(X, sig_vec, lane, tags, coverage_used):
        y = pd.Series(sig_vec, index=gene_ids)
        mid = f"{tags['matrix']}|{tags['layer']}|{tags['config']}|{tags['scope']}|{lane}"
        t = time.time()
        res = model_runner.run_one(X, y, _cfg_by_name[tags["config"]], mid)
        coef_records.extend(model_runner.coef_records(res["coefs"],
                            {**tags, "lane": lane}))
        recon_records.append({**tags, "lane": lane, **res["recon"],
                              "seconds": round(time.time() - t, 1)})
        log(f"run {mid}: {round(time.time()-t,1)}s "
            f"r2={res['recon']['reconstruction_gene_cv_test_r2_mean']}")

    global _cfg_by_name
    _cfg_by_name = {c.name: c for c in cfg.CONFIGS}

    # ---- MAIN grid: all-donor x {zscore,log_fc} x {configs} x {lanes} ----
    for layer in cfg.EFFECT_LAYERS:
        X = X_by_layer[layer]
        for c in cfg.CONFIGS:
            for lane in cfg.LANES:
                do_run(X, signatures["all_donor"][lane], lane,
                       {"matrix": "main", "layer": layer, "config": c.name,
                        "scope": "all_donor"}, coverage_by_layer[layer])

    # ---- LODO: 4 donor-scopes x author layer x pca_off x {lanes} ----
    for d in cfg.DONORS:
        scope = f"lodo_{d}"
        for lane in cfg.LANES:
            do_run(X_by_layer[cfg.AUTHOR_LAYER], signatures[scope][lane], lane,
                   {"matrix": "main", "layer": cfg.AUTHOR_LAYER,
                    "config": "pca_off", "scope": scope}, coverage_by_layer[cfg.AUTHOR_LAYER])

    return coef_records, recon_records


def _sensitivity_runs(args, universe_gene_ids, signatures, mask_by_target,
                      target_order, coef_records, recon_records, log):
    """Guide-specific + donor-pair matrices as sensitivity (plan §6.6)."""
    # Sensitivity is run PER ARM. It used to run on the combined lane only, which meant
    # the guide/donor-pair robustness of the support a consumer reads was never actually
    # measured on the lanes that support is now reported for.
    lanes = list(cfg.ARM_LANES)
    _cfg = {c.name: c for c in cfg.CONFIGS}["pca_off"]

    def run_matrix(mod_load, matrix_tag):
        eff = {t: v for t, v in mod_load["by_target"].items()}
        X, cov = pmatrix.build_masked_X(eff, mod_load["gene_ids"], universe_gene_ids,
                                        target_order, mask_by_target)
        if X.shape[1] == 0:
            log(f"{matrix_tag}: no eligible columns present; skipped")
            return
        for lane in lanes:
            y = pd.Series(signatures["all_donor"][lane], index=universe_gene_ids)
            y = y.reindex(X.index)
            mid = f"{matrix_tag}|{cfg.AUTHOR_LAYER}|pca_off|all_donor|{lane}"
            t = time.time()
            res = model_runner.run_one(X, y, _cfg, mid)
            tags = {"matrix": matrix_tag, "layer": cfg.AUTHOR_LAYER,
                    "config": "pca_off", "scope": "all_donor", "lane": lane}
            coef_records.extend(model_runner.coef_records(res["coefs"], tags))
            recon_records.append({**tags, **res["recon"],
                                  "seconds": round(time.time() - t, 1)})
            log(f"sensitivity {mid}: {round(time.time()-t,1)}s X={X.shape}")

    for m in io_data.list_modalities(args.by_guide):
        if m.startswith("guide_"):
            ml = io_data.load_support_modality(args.by_guide, m,
                                               cfg.ANALYSIS_CONDITION, cfg.AUTHOR_LAYER)
            run_matrix(ml, m)
    for m in io_data.list_modalities(args.by_donors):
        ml = io_data.load_support_modality(args.by_donors, m,
                                           cfg.ANALYSIS_CONDITION, cfg.AUTHOR_LAYER)
        run_matrix(ml, f"donorpair_{m}")


def load_program_registry(path):
    """The Stage-1 programs, and the registry hash a run BINDS.

    ``direct.io_data.load_registry`` returns a FOUR-key dict
    (``programs, file_sha256, declared_sha256, raw``). This used to be unpacked into THREE
    names -- ``programs, reg_sha, reg = ...`` -- which raises ``ValueError: too many values
    to unpack`` on the first line of work ``build()`` does. ``direct.io_data`` changed under
    this lane and nothing caught it, because no test ever called ``build()``. So the load is
    a NAMED function now: the contract it depends on is one a test can reach.

    The bound hash is the DERIVED ``file_sha256``, never the registry's self-declared
    ``registry_sha256``. Per ``direct.trust``: "a file cannot contain its own hash; a
    self-declared hash proves nothing and is trivially forged". ``declared_sha256`` is
    deliberately NOT bound here.
    """
    doc = io_data.load_registry(path)
    return doc["programs"], doc["file_sha256"]


def build(args):
    t0 = time.time()
    def log(msg): print(f"[{round(time.time()-t0,1)}s] {msg}", flush=True)

    programs, reg_sha = load_program_registry(args.registry)
    contrast_id = args.contrast_id
    out_dir = os.path.join(args.out_root, contrast_id, "perturb2state")
    os.makedirs(out_dir, exist_ok=True)
    src_dir = os.path.join(args.out_root, contrast_id)
    axis = json.load(open(os.path.join(src_dir, "axis.json")))
    provenance = json.load(open(os.path.join(src_dir, "provenance.json")))
    mask_sha = provenance["mask_sha256"]

    # Universe from the cheap DE gene axis (no layers) so the memory-heavy
    # signature build runs BEFORE the DE effect layers are loaded.
    de_ids, de_names = _de_var(args.de_main)
    excluded = U.excluded_panel_control(axis)
    uni = U.build_universe(de_ids, de_names, _ntc_symbols(args.ntc), excluded)
    log(f"universe: {uni['n_genes']} genes; excluded {uni['exclusion_counts']}")

    built, _ = _build_or_load_signatures(args, programs, axis, uni, log)
    gene_ids = built["gene_ids"]
    hashes = sio.signature_hashes({"signatures": built["signatures"], "gene_ids": gene_ids})
    if args.stop_after_signatures:
        log(f"signatures cached ({len(gene_ids)} genes); stopping before modeling")
        print(json.dumps({"signatures_cached": True, "n_genes": len(gene_ids),
                          "signature_hashes": hashes}, indent=2))
        return {"signatures_cached": True, "n_genes": len(gene_ids)}

    main = io_data.load_main(args.de_main, cfg.ANALYSIS_CONDITION)
    log(f"DE main loaded: {main['n_targets']} targets, {len(main['gene_ids'])} genes")

    # eligible perturbation columns (direct-screen eligible only, §6.3)
    screen = pd.read_parquet(os.path.join(src_dir, "screen.parquet"))
    elig = screen[screen["eligibility_state"].isin(cfg.ELIGIBLE_STATES)]
    de_targets = set(map(str, main["meta"]["target_ensembl"]))
    target_order = sorted(set(elig["target_ensembl"].astype(str)) & de_targets)
    log(f"eligible perturbation columns: {len(target_order)}")

    masks_df = pd.read_parquet(os.path.join(src_dir, "masks.parquet"))
    mask_by_target = pmatrix.mask_sets_from_parquet(masks_df)

    X_by_layer, coverage_by_layer = {}, {}
    for layer in cfg.EFFECT_LAYERS:
        eff = {str(t): main[layer][i]
               for i, t in enumerate(main["meta"]["target_ensembl"])}
        X, cov = pmatrix.build_masked_X(eff, main["gene_ids"], gene_ids,
                                        target_order, mask_by_target)
        X_by_layer[layer] = X
        coverage_by_layer[layer] = cov
        log(f"X[{layer}] shape {X.shape}")

    coef_records, recon_records = _run_plan(X_by_layer, built["signatures"],
                                            gene_ids, coverage_by_layer, log)
    if not args.skip_sensitivity:
        _sensitivity_runs(args, gene_ids, built["signatures"], mask_by_target,
                          target_order, coef_records, recon_records, log)

    coef_df = pd.DataFrame(coef_records)
    recon_df = pd.DataFrame(recon_records)
    stab_df = stability.compute_stability(coef_df, coverage_by_layer[cfg.AUTHOR_LAYER],
                                          mask_sha)

    created_at = _dt.datetime.now(_dt.timezone.utc).isoformat()
    manifest = _manifest(contrast_id, axis, uni, built, hashes, target_order,
                         recon_df, mask_sha, reg_sha, created_at)
    manifest_sha = content_hash({k: v for k, v in manifest.items()
                                 if k not in ("generated_at",)})
    manifest["model_manifest_sha256"] = manifest_sha
    integ_df = stability.integration_lane(stab_df, manifest_sha)

    # ---- write artifacts ----
    sig_df = _signature_table(built, hashes)
    _wp(sig_df, os.path.join(out_dir, "target_signatures.parquet"))
    _wp(coef_df.sort_values(["lane", "matrix", "layer", "config", "scope",
                             "target_ensembl"]).reset_index(drop=True),
        os.path.join(out_dir, "coefficients.parquet"))
    _wp(recon_df, os.path.join(out_dir, "reconstruction_metrics.parquet"))
    _wp(stab_df, os.path.join(out_dir, "stability.parquet"))
    _wp(integ_df, os.path.join(out_dir, "integration_support_lane.parquet"))
    _wj(os.path.join(out_dir, "model_manifest.json"), manifest)

    verification = _verification(out_dir, contrast_id, manifest_sha, coef_df,
                                 recon_df, stab_df, integ_df, uni, hashes,
                                 target_order, screen)
    _wj(os.path.join(out_dir, "verification.json"), verification)

    log(f"DONE. manifest_sha={manifest_sha}")
    print("TOP_BY_SELECTION:", json.dumps(verification["top_by_selection_frequency"], indent=2))
    return {"out_dir": out_dir, "manifest_sha": manifest_sha,
            "n_targets": len(target_order), "n_runs": int(recon_df.shape[0])}


# --------------------------------------------------------------------------- #
def _manifest(contrast_id, axis, uni, built, hashes, target_order, recon_df,
              mask_sha, reg_sha, created_at):
    import sklearn
    return {
        "schema_version": "spot.stage02_perturb2state_manifest.v1",
        "contrast_id": contrast_id,
        "role": "secondary_reconstruction_support",
        "not_causal_disclaimer": (
            "Perturb2State coefficients are conditional reconstruction weights, "
            "NOT causal effects, treatment effects, p-values, donor validation, "
            "or independent confirmation (plan §6.1)."),
        "upstream_software": {"repository": cfg.P2S_REPO, "commit": cfg.P2S_COMMIT,
                              "license": cfg.P2S_LICENSE, "provenance": cfg.P2S_PROVENANCE},
        "signature_construction": {
            "source_universe": "396k NTC cells (KiritSingh/spot-CD4-Marson : ntc_clustered.h5ad)",
            "condition": cfg.ANALYSIS_CONDITION,
            "model": cfg.SIGNATURE_MODEL,
            "n_score_bins": cfg.N_SCORE_BINS,
            "binning": ("donor-stratified quantile bins of the continuous scores "
                        "(NOT biological thresholds)"),
            "activation_program_id": built["activation_program_id"],
            "activation_collinear_with_pole": False,
            "normalization": cfg.SIGNATURE_NORMALIZATION,
            "design_columns": built["design_columns"],
            "n_cells": built["n_cells"],
            "scoring_symbols_present": built["scoring_symbols_present"],
            "excluded_panel_control_count": uni["exclusion_counts"]["in_excluded_panel_control"],
            "readout_gene_universe_size": uni["n_genes"],
            "universe_sha256": uni["universe_sha256"],
            "lodo_signature_count": len(cfg.DONORS),
            "all_donor_signature_count": 1,
            "signature_hashes": hashes,
        },
        "perturbation_matrix": {
            "layers": cfg.EFFECT_LAYERS, "author_layer": cfg.AUTHOR_LAYER,
            "eligible_states": list(cfg.ELIGIBLE_STATES),
            "n_eligible_perturbations": len(target_order),
            "mask_neutral_value": cfg.MASK_NEUTRAL_VALUE, "mask_sha256": mask_sha},
        "model_config_set": {
            "positive": cfg.POSITIVE,
            "positive_note": "positive=False; a negative coefficient = inverse of the "
                             "measured knockdown = OPPOSED for a CRISPRi hypothesis",
            "configs": [{"name": c.name, "pca_transform": c.pca_transform,
                         "n_pcs": (c.n_pcs if c.pca_transform else None)} for c in cfg.CONFIGS],
            "elastic_net_alphas": cfg.EN_ALPHAS, "elastic_net_l1_ratios": cfg.EN_L1_RATIOS,
            "n_splits": cfg.N_SPLITS, "n_repeats": cfg.N_REPEATS,
            "random_state": cfg.RANDOM_STATE,
            "cv_label": cfg.RECONSTRUCTION_CV_LABEL,
            "coef_sem_semantics": cfg.COEF_SEM_SEMANTICS},
        "stability": {
            "nonzero_tolerance": cfg.NONZERO_TOL,
            "support_rule": {"lanes": list(cfg.SUPPORT_LANES),
                             "reconstruction_diagnostic_lane":
                                 cfg.RECONSTRUCTION_DIAGNOSTIC_LANE,
                             "reconstruction_diagnostic_may_rank_or_gate":
                                 cfg.RECONSTRUCTION_DIAGNOSTIC_IS_RANKING,
                             "min_selection_frequency": cfg.SUPPORT_MIN_SELECTION,
                             "sign_dominance": cfg.SUPPORT_SIGN_DOMINANCE,
                             "status_values": cfg.SUPPORT_STATUS_VALUES,
                             "frozen_before_unblinding": True}},
        "n_model_runs": int(recon_df.shape[0]),
        "program_registry_sha256": reg_sha,
        "software": {"python": sys.version.split()[0], "numpy": np.__version__,
                     "pandas": pd.__version__, "sklearn": sklearn.__version__},
        "generated_by": "02_geneskew/analysis/perturb2state/run_p2s.py",
        "generated_at": created_at,
        "independent_verification": "pending (generator does not verify its own output)",
    }


_FORBIDDEN = {"p_value", "pvalue", "p_val", "pval", "q_value", "qvalue", "qval",
              "padj", "fdr"}


def _verification(out_dir, contrast_id, manifest_sha, coef_df, recon_df, stab_df,
                  integ_df, uni, hashes, target_order, screen):
    from collections import Counter
    support = stab_df[stab_df["lane"].isin(cfg.SUPPORT_LANES)]
    top = support.sort_values(
        ["selection_frequency", "median_coefficient"], ascending=False).head(15)
    sym = dict(zip(screen["target_ensembl"].astype(str), screen["target_symbol"]))
    top_rows = [{"target_ensembl": r["target_ensembl"],
                 "target_symbol": sym.get(r["target_ensembl"]),
                 "selection_frequency": r["selection_frequency"],
                 "median_coefficient": r["median_coefficient"],
                 "positive_frequency": r["positive_frequency"],
                 "negative_frequency": r["negative_frequency"],
                 "support_status": r["support_status"],
                 "coef_sign": int(np.sign(r["median_coefficient"]))}
                for _, r in top.iterrows()]
    forbidden_cols = sorted(set(
        c for df in (coef_df, recon_df, stab_df, integ_df) for c in df.columns
        if c.lower() in _FORBIDDEN))
    # panel/control exclusion proof
    excl = U.excluded_panel_control(json.load(open(os.path.join(
        os.path.dirname(out_dir), "axis.json"))))
    sig_universe = set(uni["gene_ids"])
    panel_control_leak = sorted(sig_universe & excl)
    artifact_sha = {fn: file_sha256(os.path.join(out_dir, fn))
                    for fn in os.listdir(out_dir) if fn != "verification.json"}
    return {
        "schema_version": "spot.stage02_perturb2state_verification.v1",
        "contrast_id": contrast_id,
        "role": "secondary — does not change the direct Stage-2 ranking (§6.7)",
        "generated_by": "02_geneskew/analysis/perturb2state/run_p2s.py",
        "independent_verification": "pending",
        "model_manifest_sha256": manifest_sha,
        "upstream_commit": cfg.P2S_COMMIT,
        "n_model_runs": int(recon_df.shape[0]),
        "n_eligible_perturbations": len(target_order),
        "readout_universe_size": uni["n_genes"],
        "universe_sha256": uni["universe_sha256"],
        "excluded_panel_control_count": uni["exclusion_counts"]["in_excluded_panel_control"],
        "panel_control_genes_leaked_into_universe": panel_control_leak,
        "panel_control_exclusion_ok": panel_control_leak == [],
        "signature_hashes": hashes,
        "lodo_signature_count": len(cfg.DONORS),
        "support_status_counts": dict(Counter(support["support_status"])),
        "forbidden_pq_columns_present": forbidden_cols,
        "no_pq_columns": forbidden_cols == [],
        "coef_sem_emitted_as_pvalue": False,
        "coef_sem_column_name": "coef_fit_variation",
        "reconstruction_cv_label": cfg.RECONSTRUCTION_CV_LABEL,
        "reconstruction_gene_cv_test_r2_mean_by_lane": {
            lane: round(float(recon_df[recon_df["lane"] == lane]
                              ["reconstruction_gene_cv_test_r2_mean"].mean()), 4)
            for lane in cfg.LANES},
        "top_by_selection_frequency": top_rows,
        "artifact_sha256": artifact_sha,
    }


def _wp(df, path):
    df.to_parquet(path, index=False)


def _wj(path, obj):
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True)
        fh.write("\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage-2 secondary Perturb2State")
    ap.add_argument("--registry", required=True)
    ap.add_argument("--de-main", required=True)
    ap.add_argument("--by-guide", required=True)
    ap.add_argument("--by-donors", required=True)
    ap.add_argument("--ntc", required=True)
    ap.add_argument("--out-root", required=True)
    ap.add_argument("--contrast-id", required=True)
    ap.add_argument("--sig-cache", default=None)
    ap.add_argument("--use-cache", action="store_true")
    ap.add_argument("--skip-sensitivity", action="store_true")
    ap.add_argument("--stop-after-signatures", action="store_true")
    args = ap.parse_args(argv)
    result = build(args)
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    main()
