#!/usr/bin/env python3
"""Build the Stage-1 program registry (spot.stage01_program_registry.v1).

Joins two provenance-pinned inputs — never invents an ID or a statistic:

  1. The served Stage-1 overlay meta (`app/data/stage01_umap_seed.json`), which carries,
     per program, the frozen marker panel AND the EXACT control genes that
     `score_panel()` sampled at SEED=12345 (threaded out of the deterministic pipeline),
     plus the richer display quantiles over the full 396k universe.
  2. The Stage-2 perturbation-effect universe crosswalk
     (`effect_universe_gwcd4i.json`, 10,282 genes from GWCD4i.DE_stats.h5ad var:
     gene_name symbols + gene_ids Ensembl).

For every program it emits §4.4 fields: stable program_id, score_field, display_label,
family, role, stage2_selectable (+ reason), panel/control symbols and their Ensembl IDs
(null where the gene is absent from the effect universe — never fabricated), score_genes
coefficients, seed, scoring method + per-program method_hash, source expression universe
id/hash, display-transform metadata (the richer quantiles + the §4.1 sparse transform),
panel/control coverage counts in the 10,282-gene effect universe, and the Masopust
citation. A top-level registry_sha256 hashes the ordered scientific content (no timestamp).

Th9 rule (§4.4): if IL9 AND SPI1 are both absent from the effect universe ->
stage2_selectable=false, reason=no_panel_genes_in_effect_universe. role=sensitivity ->
stage2_selectable=false (single-program display only).
"""
import os, json, hashlib
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
OVERLAY = os.path.join(HERE, "..", "app", "data", "stage01_umap_seed.json")
EFFECT = os.path.join(HERE, "effect_universe_gwcd4i.json")
OUT = os.path.join(HERE, "..", "app", "data", "stage01_program_registry.json")
SCORING_VARS = os.environ.get("SPOT_SCORING_VARS")  # optional: json {"var_names":[...]} for panel_genes_measured

SCHEMA_VERSION = "spot.stage01_program_registry.v1"
SEED = 12345
TH9_PANEL_MIN = ("IL9", "SPI1")            # the Th9 marker panel checked against the effect universe
UPPER_Q = ["p75", "p90", "p95", "p98", "p99"]  # §4.1: first upper quantile strictly > p50


def _canon_bytes(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _sha(obj):
    return hashlib.sha256(_canon_bytes(obj)).hexdigest()


def _slug(score_field):
    # stable program_id: drop the "_score" token (keeps the "_actadj" sensitivity suffix)
    return score_field.replace("_score", "", 1)


def _display_transform(domain):
    p50 = domain.get("p50")
    anchor = next((q for q in UPPER_Q if domain.get(q) is not None and domain[q] > p50), None)
    return {
        "transform": "sparse_aware_quantile_v1",
        "selection_rule": ("p50 maps to 0.5; upper anchor = first stored quantile in "
                           "[p75,p90,p95,p98,p99] strictly greater than p50; monotonic; "
                           "degenerate when no upper tail exists"),
        "quantiles": domain,
        "upper_anchor_quantile": anchor,
        "display_status": "ok" if anchor is not None else "degenerate",
    }


def build():
    overlay = json.load(open(OVERLAY))
    meta = overlay["meta"]
    programs_in = meta["programs"]
    domains = meta["score_display_domains"]
    src = meta["source"]

    eff = json.load(open(EFFECT))
    s2e = eff["symbol_to_ensembl"]
    eff_set = set(s2e)

    scoring_var_set = None
    if SCORING_VARS and os.path.exists(SCORING_VARS):
        scoring_var_set = set(json.load(open(SCORING_VARS))["var_names"])

    src_universe = {
        "id": f"{src['hf_repo']} : ntc_clustered.h5ad",
        "hf_repo": src["hf_repo"],
        "hf_revision": src["hf_revision"],
        "h5ad_sha256": src["h5ad_sha256"],
        "n_cells": int(meta["scoring_universe_n"]),
        "license": src.get("license"),
    }
    effect_universe = {
        "id": "marson2025_gwcd4_perturbseq : GWCD4i.DE_stats.h5ad",
        "dataset": eff["provenance"]["dataset"],
        "n_genes": eff["provenance"]["n_genes"],
        "carries_ensembl": True,
        "ensembl_source": "GWCD4i.DE_stats.h5ad var: gene_ids (Ensembl) + gene_name (symbol)",
        "symbols_sha256": eff["symbols_sha256"],
    }

    th9_panel_absent = all(g not in eff_set for g in TH9_PANEL_MIN)

    entries = []
    for p in programs_in:
        sf = p["score_field"]
        panel = list(p["panel_genes"])
        ctrl = list(p["control_genes"])
        role = p["role"]
        domain = domains[sf]

        panel_present = [g for g in panel if g in eff_set]
        panel_absent = [g for g in panel if g not in eff_set]
        ctrl_present = [g for g in ctrl if g in eff_set]

        panel_measured = ([g for g in panel if g in scoring_var_set]
                          if scoring_var_set is not None else None)
        n_panel_w = len(panel_measured) if panel_measured is not None else None

        if role == "sensitivity":
            stage2_selectable = False
            reason = "role_sensitivity_display_only"
        elif len(panel_present) == 0:
            stage2_selectable = False
            reason = "no_panel_genes_in_effect_universe"
        else:
            stage2_selectable = True
            reason = None

        method_hash = _sha({
            "scoring_method": p["scoring_method"], "seed": SEED,
            "panel_genes": panel, "control_genes": ctrl,
        })

        entries.append({
            "program_id": _slug(sf),
            "score_field": sf,
            "display_label": p["display_label"],
            "family": p["family"],
            "role": role,
            "stage2_selectable": stage2_selectable,
            "stage2_unavailable_reason": reason,
            "panel_symbols": panel,
            "panel_ensembl": [s2e.get(g) for g in panel],
            "panel_genes_measured": panel_measured,
            "control_symbols": ctrl,
            "control_ensembl": [s2e.get(g) for g in ctrl],
            "panel_coefficient": (round(1.0 / n_panel_w, 8) if n_panel_w else None),
            "control_coefficient": (round(-1.0 / len(ctrl), 8) if ctrl else None),
            "coefficient_scheme": "score_genes uniform: +1/n_panel_measured per panel gene, -1/n_control per control gene",
            "seed": SEED,
            "scoring_method": p["scoring_method"],
            "method_hash": method_hash,
            "source_expression_universe_id": src_universe["id"],
            "source_expression_universe_hash": src_universe["h5ad_sha256"],
            "display_transform": _display_transform(domain),
            "panel_coverage": {
                "in_effect_universe": len(panel_present), "total": len(panel),
                "genes_present": panel_present, "genes_absent": panel_absent,
            },
            "control_coverage": {
                "in_effect_universe": len(ctrl_present), "total": len(ctrl),
            },
            "source_citation": p["source"],
        })

    registry = {
        "schema_version": SCHEMA_VERSION,
        "seed": SEED,
        "method_version": meta["method_version"] if "method_version" in meta else None,
        "th9_panel_genes_checked": list(TH9_PANEL_MIN),
        "th9_panel_absent_from_effect_universe": th9_panel_absent,
        "source_expression_universe": src_universe,
        "effect_universe": effect_universe,
        "programs": entries,
    }
    # registry_sha256 hashes the ordered scientific content only (excludes created_at + itself)
    registry["registry_sha256"] = _sha(registry)
    registry["created_at"] = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")

    json.dump(registry, open(OUT, "w"), indent=2)
    return registry


if __name__ == "__main__":
    r = build()
    print(f"wrote {OUT}")
    print(f"  programs: {len(r['programs'])}")
    print(f"  registry_sha256: {r['registry_sha256']}")
    for e in r["programs"]:
        print(f"  {e['program_id']:26s} ctrl={len(e['control_symbols']):3d} "
              f"panel_cov={e['panel_coverage']['in_effect_universe']}/{e['panel_coverage']['total']} "
              f"ctrl_cov={e['control_coverage']['in_effect_universe']}/{e['control_coverage']['total']} "
              f"stage2={e['stage2_selectable']}")
