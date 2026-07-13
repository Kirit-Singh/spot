"""Stage-2 primary orchestrator: build the direct measured perturbation screen.

Runs on the configured analysis host (reads the pinned DE_stats artifacts). Emits, under
``<out_root>/<contrast_id>/``: axis.json, stage01_selection.json,
input_manifest.json, masks.parquet, screen.parquet, guide_support.parquet,
donor_support.parquet, cell_support.parquet (stub), provenance.json,
verification.json.

This module GENERATES artifacts and their invariant manifest; it does NOT
assert its own correctness — an independent pass (tests + a separate verifier)
checks the emitted numbers (plan §1, §13).
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
from typing import Any, Optional

import numpy as np
import pandas as pd

from . import config, disposition
from .contrast import build_axis, build_stage01_selection, contrast_identifiers
from .hashing import content_hash, file_sha256, round_float
from . import io_data
from .masks import build_target_masks, fallback_self_mask, mask_rows_for_emit
from . import projection as proj

SCHEMA_SCREEN = "spot.stage02_screen.v1"


# --------------------------------------------------------------------------- #
# Projection helper reused across main / guide / donor lanes.
# --------------------------------------------------------------------------- #
def _project(effect_row, gene_index, prog_a, prog_b, mask_set):
    da = proj.program_delta(effect_row, prog_a["panel"], prog_a["control"],
                            gene_index, mask_set, config.MIN_SURVIVING_PANEL,
                            config.MIN_SURVIVING_CONTROL)
    db = proj.program_delta(effect_row, prog_b["panel"], prog_b["control"],
                            gene_index, mask_set, config.MIN_SURVIVING_PANEL,
                            config.MIN_SURVIVING_CONTROL)
    ax = proj.axis_scores(da["delta"], db["delta"], prog_a["sign"], prog_b["sign"])
    ok = da["status"] == proj.OK and db["status"] == proj.OK
    return da, db, ax, ok


def _programs(registry_programs, contrast):
    a = registry_programs[contrast.a.program_id]
    b = registry_programs[contrast.b.program_id]
    return (
        {"panel": a["panel_ensembl"], "control": a["control_ensembl"],
         "sign": contrast.a.sign},
        {"panel": b["panel_ensembl"], "control": b["control_ensembl"],
         "sign": contrast.b.sign},
    )


# --------------------------------------------------------------------------- #
# Support lanes.
# --------------------------------------------------------------------------- #
def _lane_balanced(mod, target, prog_a, prog_b, mask_set):
    row = mod["by_target"].get(target)  # stable-ID join (never row position)
    if row is None:
        return None
    return proj.project_balanced(row, prog_a, prog_b, mod["gene_index"], mask_set,
                                 config.MIN_SURVIVING_PANEL, config.MIN_SURVIVING_CONTROL)


def compute_guide_support(by_guide_path, condition, targets, masks, prog_a, prog_b):
    mods = [m for m in io_data.list_modalities(by_guide_path) if m.startswith("guide_")]
    loaded = {m: io_data.load_support_modality(by_guide_path, m, condition)
              for m in sorted(mods)}
    per_target: dict[str, list[Optional[float]]] = {}
    rows: list[dict] = []
    for t in targets:
        mask_set = masks[t]["gene_set"]
        vals: list[Optional[float]] = []
        for m in sorted(loaded):
            b = _lane_balanced(loaded[m], t, prog_a, prog_b, mask_set)
            vals.append(b)
            rows.append({"target_ensembl": t, "guide_slot": m,
                         "balanced_skew": round_float(b),
                         "present": b is not None})
        per_target[t] = vals
    return per_target, rows, sorted(loaded)


def compute_donor_support(by_donors_path, condition, targets, masks, prog_a, prog_b):
    mods = io_data.list_modalities(by_donors_path)
    loaded = {m: io_data.load_support_modality(by_donors_path, m, condition)
              for m in sorted(mods)}
    per_target: dict[str, list[Optional[float]]] = {}
    rows: list[dict] = []
    for t in targets:
        mask_set = masks[t]["gene_set"]
        vals: list[Optional[float]] = []
        for m in sorted(loaded):
            b = _lane_balanced(loaded[m], t, prog_a, prog_b, mask_set)
            vals.append(b)
            rows.append({"target_ensembl": t, "donor_pair": m,
                         "balanced_skew": round_float(b),
                         "present": b is not None})
        per_target[t] = vals
    return per_target, rows, sorted(loaded)


# --------------------------------------------------------------------------- #
# Main build.
# --------------------------------------------------------------------------- #
def build_screen(args) -> dict:
    programs, registry_sha, reg = io_data.load_registry(args.registry)
    contrast = config.DEFAULT_CONTRAST
    contrast_id, canonical_sha, _ = contrast_identifiers(contrast, registry_sha)
    created_at = _dt.datetime.now(_dt.timezone.utc).isoformat()

    prog_a, prog_b = _programs(programs, contrast)
    main = io_data.load_main(args.de_main, contrast.analysis_condition)
    gene_index = main["gene_index"]
    universe = main["gene_ids"]
    meta = main["meta"]
    targets = [str(t) for t in meta["target_ensembl"]]

    sgrna_by_target = io_data.load_sgrna_rows_by_target(args.sgrna)
    target_masks: dict[str, dict] = {}
    for t in targets:
        if t in sgrna_by_target:
            target_masks[t] = build_target_masks(
                {t: sgrna_by_target[t]}, config.MASK_NEIGHBORHOOD_COLUMN)[t]
            target_masks[t]["resolved"] = True
        else:
            fm = fallback_self_mask(t)
            fm["resolved"] = False
            target_masks[t] = fm

    # ---- support lanes (log_fc) ----
    guide_bal, guide_rows, guide_mods = compute_guide_support(
        args.by_guide, contrast.analysis_condition, targets, target_masks,
        prog_a, prog_b)
    donor_bal, donor_rows, donor_mods = compute_donor_support(
        args.by_donors, contrast.analysis_condition, targets, target_masks,
        prog_a, prog_b)

    # ---- main per-target rows ----
    screen_rows: list[dict] = []
    mask_emit: list[dict] = []
    for i, t in enumerate(targets):
        mask = target_masks[t]
        mask_set = mask["gene_set"]
        mask_emit.extend(mask_rows_for_emit(t, contrast.analysis_condition,
                                            contrast_id, mask, universe))
        da, db, ax, ok = _project(main["log_fc"][i], gene_index, prog_a, prog_b, mask_set)
        zda, zdb, zax, zok = _project(main["zscore"][i], gene_index, prog_a, prog_b, mask_set)

        proj_status = da["status"] if da["status"] != proj.OK else db["status"]
        n_cells = _f(meta["n_cells_target"][i])
        n_guides = _f(meta["n_guides"][i])
        elig, reasons = disposition.classify_eligibility(
            row_present=True, projection_status=proj_status,
            mask_resolved=mask["resolved"], n_cells=n_cells,
            low_target_gex=_b(meta["low_target_gex"][i]),
            ontarget_significant=_b(meta["ontarget_significant"][i]),
            n_guides=n_guides)

        g = disposition.guide_support_state(ax["balanced_skew"], guide_bal[t])
        d = disposition.donor_support_state(ax["balanced_skew"], donor_bal[t],
                                            len(donor_mods))
        dclass = proj.direction_class(ax["away_from_A"], ax["toward_b"])
        supp = disposition.support_state(projection_ok=ok,
                                         guide_agree=g["guide_sign_agreement"],
                                         donor_agree=d["donor_pair_agreement"])
        tier = disposition.evidence_tier(
            eligibility_state=elig, projection_ok=ok, direction_class=dclass,
            guide_agree=g["guide_sign_agreement"],
            donor_agree=d["donor_pair_agreement"])

        screen_rows.append({
            "schema_version": SCHEMA_SCREEN,
            "contrast_id": contrast_id,
            "run_id": contrast_id,
            "target_ensembl": t,
            "target_symbol": _s(meta["target_symbol"][i]),
            "condition": contrast.analysis_condition,
            "source_row_id": _s(meta["source_row_id"][i]),
            # source QC (separate from Stage-2 projection)
            "n_cells_target": n_cells,
            "n_donors_effective": 4,
            "n_guides": n_guides,
            "qc_ontarget_significant": _b(meta["ontarget_significant"][i]),
            "qc_ontarget_effect_size": round_float(_f(meta["ontarget_effect_size"][i])),
            "qc_low_target_expression": _b(meta["low_target_gex"][i]),
            "qc_target_baseMean": round_float(_f(meta["target_baseMean"][i])),
            "source_distal_offtarget_flag": _b(meta["distal_offtarget_flag"][i]),
            "source_neighboring_gene_KD": _b(meta["neighboring_gene_KD"][i]),
            "source_guide_correlation_all": round_float(_f(meta["guide_correlation_all"][i])),
            "source_donor_correlation_all_mean": round_float(_f(meta["donor_correlation_all_mean"][i])),
            # mask
            "mask_gene_count": len([m for m in mask["entries"]
                                    if m["masked_gene_ensembl"] in set(universe)]),
            "mask_resolved": mask["resolved"],
            "mask_guide_ids": ";".join(mask["guide_ids"]),
            # coverage after masking
            "A_panel_surviving": da["n_panel_surviving"],
            "A_control_surviving": da["n_control_surviving"],
            "B_panel_surviving": db["n_panel_surviving"],
            "B_control_surviving": db["n_control_surviving"],
            # projection (log_fc primary)
            "delta_A": round_float(da["delta"]),
            "away_from_A": round_float(ax["away_from_A"]),
            "delta_B": round_float(db["delta"]),
            "toward_b": round_float(ax["toward_b"]),
            "balanced_skew": round_float(ax["balanced_skew"]),
            "direction_class": dclass,
            # zscore precision-weighted sensitivity lane
            "delta_A_zscore": round_float(zda["delta"]),
            "away_from_A_zscore": round_float(zax["away_from_A"]),
            "delta_B_zscore": round_float(zdb["delta"]),
            "toward_b_zscore": round_float(zax["toward_b"]),
            "balanced_skew_zscore": round_float(zax["balanced_skew"]),
            # support
            "guide_sign_agreement": g["guide_sign_agreement"],
            "n_guides_evaluated": g["n_guides_evaluated"],
            "n_guides_concordant": g["n_guides_concordant"],
            "donor_pair_agreement": d["donor_pair_agreement"],
            "n_donor_pairs_evaluated": d["n_donor_pairs_evaluated"],
            "n_donor_pairs_concordant": d["n_donor_pairs_concordant"],
            "n_donor_pairs_discordant": d["n_donor_pairs_discordant"],
            "n_donor_pairs_missing": d["n_donor_pairs_missing"],
            "support_state": supp,
            "cell_level_support_state": "screen_only",  # cell-level deferred (stub)
            # disposition
            "eligibility_state": elig,
            "eligibility_reasons": ";".join(reasons),
            "evidence_tier": tier,
            "desired_target_modulation": disposition.desired_target_modulation(ax["balanced_skew"]),
            "observed_genetic_direction": config.CRISPRI_MODALITY,
            "crispri_modality": config.CRISPRI_MODALITY,
            "inference_status": config.INFERENCE_STATUS,
        })

    ordered = proj.rank_rows(screen_rows, contrast.objective)

    # ---- assemble outputs ----
    out_dir = os.path.join(args.out_root, contrast_id)
    os.makedirs(out_dir, exist_ok=True)
    axis = build_axis(contrast, registry_sha, programs)
    selection = build_stage01_selection(contrast, registry_sha, created_at)
    manifest = _input_manifest(args, reg)

    screen_df = pd.DataFrame(ordered)
    masks_df = pd.DataFrame(mask_emit).sort_values(
        ["target_ensembl", "masked_gene_ensembl", "mask_reason", "guide_id"],
        na_position="last").reset_index(drop=True)
    guide_df = pd.DataFrame(guide_rows).sort_values(
        ["target_ensembl", "guide_slot"]).reset_index(drop=True)
    donor_df = pd.DataFrame(donor_rows).sort_values(
        ["target_ensembl", "donor_pair"]).reset_index(drop=True)
    cell_df = _cell_support_stub(ordered, contrast_id)

    _write_parquet(masks_df, os.path.join(out_dir, "masks.parquet"))
    _write_parquet(screen_df, os.path.join(out_dir, "screen.parquet"))
    _write_parquet(guide_df, os.path.join(out_dir, "guide_support.parquet"))
    _write_parquet(donor_df, os.path.join(out_dir, "donor_support.parquet"))
    _write_parquet(cell_df, os.path.join(out_dir, "cell_support.parquet"))
    _write_json(os.path.join(out_dir, "axis.json"), axis)
    _write_json(os.path.join(out_dir, "stage01_selection.json"), selection)
    _write_json(os.path.join(out_dir, "input_manifest.json"), manifest)

    mask_sha = content_hash(mask_emit)
    provenance = _provenance(contrast, contrast_id, canonical_sha, registry_sha,
                             manifest, mask_sha, created_at, guide_mods, donor_mods,
                             programs)
    _write_json(os.path.join(out_dir, "provenance.json"), provenance)

    verification = _verification(out_dir, contrast_id, canonical_sha, ordered,
                                 mask_sha, screen_df)
    _write_json(os.path.join(out_dir, "verification.json"), verification)

    return {"contrast_id": contrast_id, "out_dir": out_dir,
            "n_rows": len(ordered), "mask_sha": mask_sha,
            "verification": verification}


# --------------------------------------------------------------------------- #
# Small helpers.
# --------------------------------------------------------------------------- #
def _f(v):
    if v is None:
        return None
    try:
        fv = float(v)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(fv) else fv


def _b(v):
    if v is None:
        return None
    if isinstance(v, (bool, np.bool_)):
        return bool(v)
    return bool(v)


def _s(v):
    return None if v is None else str(v)


def _write_parquet(df: pd.DataFrame, path: str):
    df.to_parquet(path, index=False)


def _write_json(path: str, obj: Any):
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True)
        fh.write("\n")


def _cell_support_stub(rows, contrast_id):
    # Cell-level extraction deferred this pass (plan §5.7 allows a screen_only stub).
    return pd.DataFrame([{
        "contrast_id": contrast_id,
        "target_ensembl": r["target_ensembl"],
        "condition": r["condition"],
        "cell_level_support_state": "screen_only",
        "reason": "cell_level_extraction_deferred",
        "away_from_A_cell": None, "toward_b_cell": None,
        "combined_effect_cell": None,
    } for r in rows])


def _input_manifest(args, reg):
    files = {
        "GWCD4i.DE_stats.h5ad": args.de_main,
        "GWCD4i.DE_stats.by_guide.h5mu": args.by_guide,
        "GWCD4i.DE_stats.by_donors.h5mu": args.by_donors,
        "sgrna_library_metadata.suppl_table.csv": args.sgrna,
    }
    precomp = {}
    if args.input_sha256:
        for line in open(args.input_sha256):
            line = line.strip()
            if not line:
                continue
            sha, name = line.split()[0], line.split()[-1]
            precomp[os.path.basename(name)] = sha
    entries = []
    for name, path in files.items():
        sha = precomp.get(name) or file_sha256(path)
        entries.append({
            "name": name,
            "size_bytes": os.path.getsize(path),
            "sha256": sha,
            "basename_on_host": os.path.basename(path),
        })
    return {
        "schema_version": "spot.stage02_input_manifest.v1",
        "dataset_id": config.DATASET_ID,
        "dataset_description": reg["effect_universe"]["dataset"],
        "public_source": "bioRxiv 2025.12.23.696273 (Marson lab genome-scale GWCD4i perturb-seq)",
        "hf_repo": config.SOURCE_HF_REPO,
        "hf_revision": config.SOURCE_HF_REVISION,
        "gene_annotation": "Ensembl gene_ids carried in DE_stats var (GRCh38)",
        "effect_universe_id": config.EFFECT_UNIVERSE_ID,
        "n_effect_genes": reg["effect_universe"]["n_genes"],
        "software": _software_versions(),
        "files": entries,
    }


def _software_versions():
    import sys
    import anndata
    import h5py
    import scipy
    vers = {"python": sys.version.split()[0], "numpy": np.__version__,
            "pandas": pd.__version__, "h5py": h5py.__version__,
            "scipy": scipy.__version__, "anndata": anndata.__version__}
    try:
        import pyarrow
        vers["pyarrow"] = pyarrow.__version__
    except Exception:
        pass
    return vers


def _provenance(contrast, contrast_id, canonical_sha, registry_sha, manifest,
                mask_sha, created_at, guide_mods, donor_mods, programs):
    a = programs[contrast.a.program_id]
    b = programs[contrast.b.program_id]
    return {
        "schema_version": "spot.stage02_provenance.v1",
        "contrast_id": contrast_id,
        "canonical_contrast_sha256": canonical_sha,
        "program_registry_sha256": registry_sha,
        "method": {
            "name": "direct measured perturbation screen — target-masked DE-space program projection",
            "formula": "delta_p(X) = mean_{P_p \\ M_X} d - mean_{C_p \\ M_X} d (panel and control means recomputed separately after masking; no L2 renormalisation)",
            "effect_layer_primary": "log_fc",
            "effect_layer_sensitivity": "zscore",
            "away_from_A": "-sign_A * delta_A",
            "toward_b": "sign_B * delta_B",
            "balanced_skew": "(away_from_A + toward_b) / 2",
            "objective": contrast.objective,
            "not_an_exact_per_cell_stage1_score": True,
        },
        "frozen_thresholds": {
            "analysis_condition": contrast.analysis_condition,
            "donor_scope": contrast.donor_scope,
            "mask_window_kb": config.MASK_WINDOW_KB,
            "mask_neighborhood_column": config.MASK_NEIGHBORHOOD_COLUMN,
            "min_surviving_panel": config.MIN_SURVIVING_PANEL,
            "min_surviving_control": config.MIN_SURVIVING_CONTROL,
            "n_cells_min": config.N_CELLS_MIN,
            "float_decimals": 6,
        },
        "axis": {
            "A": {"program_id": contrast.a.program_id, "score_field": contrast.a.score_field,
                  "direction": contrast.a.direction, "sign": contrast.a.sign,
                  "panel_ensembl": a["panel_ensembl"], "control_ensembl": a["control_ensembl"]},
            "B": {"program_id": contrast.b.program_id, "score_field": contrast.b.score_field,
                  "direction": contrast.b.direction, "sign": contrast.b.sign,
                  "panel_ensembl": b["panel_ensembl"], "control_ensembl": b["control_ensembl"]},
        },
        "mask_sha256": mask_sha,
        "guide_modalities": guide_mods,
        "donor_pair_modalities": donor_mods,
        "donor_pairs_are_overlapping_sensitivity_estimates_not_replicates": True,
        "cell_level_support": "deferred_stub_screen_only",
        "inference_status": config.INFERENCE_STATUS,
        "no_pq_emitted_reason": "no calibrated null exists for this projection",
        "input_manifest": manifest,
        "generated_by": "02_geneskew/analysis/direct/run_screen.py",
        "generated_at": created_at,
        "independent_verification": "pending (generator does not verify its own output)",
    }


_FORBIDDEN_COLS = {"p_value", "pvalue", "p_val", "pval", "q_value", "qvalue",
                   "q_val", "qval", "padj", "adj_p_value", "fdr"}


def _verification(out_dir, contrast_id, canonical_sha, ordered, mask_sha, screen_df):
    from collections import Counter
    elig = Counter(r["eligibility_state"] for r in ordered)
    tier = Counter(r["evidence_tier"] for r in ordered)
    dclass = Counter(r["direction_class"] for r in ordered)
    projected = sum(1 for r in ordered if r["balanced_skew"] is not None)
    cols = list(screen_df.columns)
    forbidden = sorted(c for c in cols if c.lower() in _FORBIDDEN_COLS)
    artifact_sha = {}
    for fn in ["axis.json", "stage01_selection.json", "masks.parquet",
               "screen.parquet", "guide_support.parquet", "donor_support.parquet",
               "cell_support.parquet", "input_manifest.json"]:
        p = os.path.join(out_dir, fn)
        if os.path.exists(p):
            artifact_sha[fn] = file_sha256(p)
    top10 = [{"rank": r["rank"], "target_symbol": r["target_symbol"],
              "target_ensembl": r["target_ensembl"],
              "away_from_A": r["away_from_A"], "toward_b": r["toward_b"],
              "balanced_skew": r["balanced_skew"], "evidence_tier": r["evidence_tier"]}
             for r in ordered[:10]]
    return {
        "schema_version": "spot.stage02_verification.v1",
        "contrast_id": contrast_id,
        "canonical_contrast_sha256": canonical_sha,
        "generated_by": "02_geneskew/analysis/direct/run_screen.py",
        "independent_verification": "pending",
        "row_count": len(ordered),
        "family_size_evaluated": projected,
        "family_size_note": "count of targets with a computed projection; reported family size, NOT a called multiplicity family (no p/q emitted)",
        "eligibility_state_counts": dict(elig),
        "evidence_tier_counts": dict(tier),
        "direction_class_counts": dict(dclass),
        "complete_disposition": len(ordered) == screen_df.shape[0],
        "forbidden_pq_columns_present": forbidden,
        "no_pq_columns": forbidden == [],
        "inference_status": config.INFERENCE_STATUS,
        "mask_sha256": mask_sha,
        "ranking": {
            "objective": "balanced_a_to_b",
            "tie_break": ["direction_class_tier", "balanced_skew_desc",
                          "min(away_from_A,toward_b)_desc", "target_ensembl_asc"],
            "deterministic": True,
        },
        "artifact_sha256": artifact_sha,
        "top10_balanced_a_to_b": top10,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage-2 primary direct screen")
    ap.add_argument("--registry", required=True)
    ap.add_argument("--de-main", required=True)
    ap.add_argument("--by-guide", required=True)
    ap.add_argument("--by-donors", required=True)
    ap.add_argument("--sgrna", required=True)
    ap.add_argument("--out-root", required=True)
    ap.add_argument("--input-sha256", default=None)
    args = ap.parse_args(argv)
    result = build_screen(args)
    print(json.dumps({k: v for k, v in result.items() if k != "verification"},
                     indent=2))
    v = result["verification"]
    print("TOP10:", json.dumps(v["top10_balanced_a_to_b"], indent=2))
    print("DISPOSITION:", json.dumps(v["eligibility_state_counts"], indent=2))
    print("NO_PQ:", v["no_pq_columns"])
    return result


if __name__ == "__main__":
    main()
