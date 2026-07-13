"""Read-only, provenance-bound Marson concordance check for the CURRENT Stage-2 estimands.

Reads the PINNED DE object (fail-closed on sha256), the RELEASED program registry, and the
FROZEN paper sign-control spec; recomputes our released estimand with the RELEASED projection
code (02_geneskew/analysis/direct/projection.py) and emits a typed concordance artifact.

Alters nothing: no score, no rank, no Stage-2 output is written or changed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

import h5py
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stage2_estimand_concordance as sc          # noqa: E402
import projection                                  # released Direct projection  # noqa: E402

MIN_SURVIVING_PANEL = 1      # 02_geneskew/analysis/direct/config.py
MIN_SURVIVING_CONTROL = 10   # 02_geneskew/analysis/direct/config.py


def sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


class DE:
    """Read-only reader over the pinned DE object."""

    def __init__(self, path: str):
        self.f = h5py.File(path, "r")
        names = self.f["var/gene_name"]
        cats = names["categories"][:] if isinstance(names, h5py.Group) else names[:]
        codes = names["codes"][:] if isinstance(names, h5py.Group) else None
        cats = [c.decode() if isinstance(c, bytes) else str(c) for c in cats]
        syms = [cats[i] for i in codes] if codes is not None else cats
        self.gene_index = {s: i for i, s in enumerate(syms)}
        idx = self.f["obs/index"][:]   # obs.attrs["_index"] == "index"
        self.rowkey = {(k.decode() if isinstance(k, bytes) else str(k)): i
                       for i, k in enumerate(idx)}
        # obs index is "{ENSG}_{condition}"; map symbol->ENSG from obs categoricals
        g = self.f["obs/target_contrast_gene_name"]
        gc = [c.decode() if isinstance(c, bytes) else str(c) for c in g["categories"][:]]
        gcodes = g["codes"][:]
        t = self.f["obs/target_contrast"]
        tc = [c.decode() if isinstance(c, bytes) else str(c) for c in t["categories"][:]]
        tcodes = t["codes"][:]
        self.sym2ensg = {}
        for i in range(len(gcodes)):
            self.sym2ensg.setdefault(gc[gcodes[i]], tc[tcodes[i]])

    def row(self, symbol: str, condition: str):
        ensg = self.sym2ensg.get(symbol)
        if ensg is None:
            return None, None
        r = self.rowkey.get(f"{ensg}_{condition}")
        if r is None:
            return ensg, None
        return ensg, self.f["layers/log_fc"][r, :].astype(np.float64)

    def close(self):
        self.f.close()


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--de", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--registry", required=True)
    ap.add_argument("--pdf-sha256", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    spec = json.load(open(a.spec))
    de_sha = sha256(a.de)
    pin = spec["source"]["de_object"]["sha256"]
    if de_sha != pin:
        print(f"FAIL: DE sha {de_sha} != spec pin {pin}", file=sys.stderr)
        return 2
    reg_raw = json.load(open(a.registry))
    registry = reg_raw if isinstance(reg_raw, list) else (
        reg_raw.get("programs") or reg_raw.get("registry"))

    de = DE(a.de)
    conditions = spec["conditions"]
    results = []
    for ctrl in spec["controls"]:
        kind = ctrl.get("kind", "directional")
        pairs = ctrl.get("divergent") or ([{"cytokine": ctrl["cytokine"],
                                            "expected_log_fc_sign": ctrl["expected_log_fc_sign"]}]
                                          if kind != "broad_effect" else [])
        rec = {"control_id": ctrl["id"], "kind": kind, "source": ctrl.get("source"),
               "regulators": ctrl["regulators"], "comparisons": [],
               # a DIVERGENT control spans two cytokines whose comparability DIFFERS (e.g.
               # NFKB2: IL10 is in no panel, but IL21 is a tfh_like panel member). A single
               # control-level tier would silently hide that, so tiers are per-cytokine.
               "comparability_by_cytokine": {}}
        if kind == "broad_effect":
            rec["comparability_by_cytokine"] = {
                "*": sc.comparability(None, registry, kind="broad_effect")}
            results.append(rec)
            continue
        for pair in pairs:
            cyto, expected = pair["cytokine"], pair["expected_log_fc_sign"]
            cmp_ = sc.comparability(cyto, registry)
            for reg_sym in ctrl["regulators"]:
                for cond in conditions:
                    ensg, row = de.row(reg_sym, cond)
                    if row is None:
                        continue
                    col = de.gene_index.get(cyto)
                    lfc = float(row[col]) if col is not None else None
                    entry = {"regulator": reg_sym, "regulator_ensembl": ensg,
                             "cytokine": cyto, "condition": cond,
                             # TIER 1: the ONE legitimate verdict — same released quantity
                             "shared_substrate": sc.substrate_verdict(expected, lfc),
                             # TIER 2: our RELEASED estimand, descriptive only
                             "stage2_projection": []}
                    for pid in cmp_["programs"]:
                        prog = next(p for p in registry if p["program_id"] == pid)
                        d = projection.program_delta(
                            row, prog["panel_symbols"], prog["control_symbols"],
                            de.gene_index, {reg_sym}, MIN_SURVIVING_PANEL,
                            MIN_SURVIVING_CONTROL)
                        entry["stage2_projection"].append(sc.projection_observation(
                            pid, d["delta"], d["status"], d["n_panel_surviving"],
                            d["n_control_surviving"]))
                    rec["comparisons"].append(entry)
            rec["comparability_by_cytokine"][cyto] = cmp_
        results.append(rec)
    de.close()

    artifact = {
        "artifact_id": "spot.stage02.marson_concordance.v1",
        "classification": sc.CLASSIFICATION,
        "read_only": True, "alters_scores_or_ranks": False,
        "inputs": {
            "preprint_pdf_sha256": a.pdf_sha256,
            "preprint_doi": spec["source"]["preprint"]["doi"],
            "de_object_sha256": de_sha, "de_matches_pin": True,
            "authors_code_commit": spec["source"]["authors_code_commit"],
            "spec_sha256": sha256(a.spec), "registry_sha256": sha256(a.registry),
        },
        "estimands": {
            "paper": {"quantity": "per-cytokine log2FC on regulator knockdown",
                      "modality": sc.PAPER_MODALITY, "inference": sc.PAPER_INFERENCE},
            "stage2_released": {"quantity": sc.ESTIMAND_FORMULA,
                                "modality": sc.OUR_MODALITY, "inference": sc.OUR_INFERENCE},
            "note": ("both are functions of the SAME released per-gene log2FC, so the substrate "
                     "is shared; a program delta is NOT a per-cytokine effect and the two are "
                     "never equated"),
        },
        "dataset_scope": {
            "cells": "blood-derived primary human CD4+ T cells (CRISPRi Perturb-seq)",
            "axes": "4 healthy human donors x 3 stimulation conditions (Rest / Stim8hr / Stim48hr)",
            "multi_tissue": False,
            "locator": "preprint p.4 (12 pools, four healthy human donors, 3 stimulation conditions; Suppl. Fig 1A)",
            "hpa": ("Human Protein Atlas is LINK-OUT context only; no HPA value is incorporated "
                    "into any score or rank"),
        },
        "protein_vs_mrna": {
            "our_analysis": "mRNA only",
            "paper_protein_validation": ("arrayed knockdown measured by bulk RNAseq AND "
                                         "intracellular protein staining / flow cytometry "
                                         "(p.11, Fig 2E-2F)"),
            "documented_exception": ("NFKB2 -> IL10: 'protein level changes did not mirror the "
                                     "transcriptional phenotype' (p.11)"),
            "comparable_here": False,
            "tier": sc.TIER_PROTEIN_MODALITY,
        },
        "results": results,
    }
    json.dump(artifact, open(a.out, "w"), indent=2, sort_keys=True)
    tiers = {}
    for r in results:
        for cyto, c in r.get("comparability_by_cytokine", {}).items():
            t = c["tier"]
            tiers[t] = tiers.get(t, 0) + 1

    # Condition-stratified, because the paper's directional claims are RE-STIMULATION-specific
    # ("positive regulators ... were more readily identified following re-stimulation", p.9).
    # A Rest-condition sign mismatch is therefore NOT a discordance, and a pooled ratio would
    # misrepresent it.
    by_cond: dict[str, dict[str, int]] = {}
    for r in results:
        for c in r.get("comparisons", []):
            cond = c["condition"]
            b = by_cond.setdefault(cond, {"n": 0, "concordant": 0})
            b["n"] += 1
            b["concordant"] += 1 if c["shared_substrate"]["concordant"] else 0
    summary = {
        "shared_substrate_by_condition": by_cond,
        "paper_claim_is_condition_specific": {
            "statement": ("the paper identifies positive regulators (knockdown log2FC < 0) "
                          "mainly FOLLOWING RE-STIMULATION, so a Rest-condition sign mismatch "
                          "is not evidence of discordance"),
            "locator": "preprint p.9 (Figure 2A, Suppl. Figure 10)"},
        "condition_aware_result_reference": {
            "lane": "02_geneskew/paper_concordance (sign-control lane)",
            "result": ("10/10 directional controls concordant at a condition where the effect "
                       "is significant; broad effect confirmed"),
            "note": ("that lane consults paper FDR ONLY inside provenance_diagnostics; this "
                     "artifact draws no inference and displays no p/q")},
        "no_pooled_ratio_reported": ("a single pooled concordance ratio across all conditions "
                                     "is deliberately NOT emitted: it would mix conditions in "
                                     "which the paper makes no directional claim"),
    }
    artifact["summary"] = summary
    json.dump(artifact, open(a.out, "w"), indent=2, sort_keys=True)
    print(json.dumps({"out": a.out, "de_matches_pin": True, "tiers": tiers,
                      "shared_substrate_by_condition": by_cond}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
