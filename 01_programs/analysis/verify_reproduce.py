#!/usr/bin/env python3
"""Reproducibility gate for the spot Stage-1 overlay.

This is now a genuine gate: stage1_pipeline.py *emits* the overlay
(data/stage01_umap_seed.json) from its own deterministic scoring, and this
script asserts that emitted overlay holds the exact per-cell nomenclature counts
— differentiation (ds) AND function (func) — from the reference run, exiting
nonzero on any drift. Because the pipeline writes the file this checks (rather
than reading a hand-placed one), a re-run that scored differently would change
the file and be caught here.
"""
import json, sys

# Reference = the counts the deterministic (SEED=12345) pipeline emits.
REFERENCE = {
    "nomen_counts.ds": {
        "N": 6409, "A": 21072, "M": 10871, "checkpoint-high activated": 1648,
    },
    "nomen_counts.func": {  # 33004/40000 = 82.5% no-call; Th1 4550 = 11.4%; CD4-CTL 573 = 1.4% (activation-conditioned); Treg 1051 = 2.6%
        "—": 33004, "Th1": 4550, "Treg": 1051, "Th2": 528, "CD4-CTL": 573,
        "Tfh": 236, "Th9": 40, "Th17": 18,
    },
    "n_total_cells": 396000,
    "n_shown": 40000,
}
OVERLAY = "data/stage01_umap_seed.json"


def get(d, path):
    for k in path.split("."):
        d = d[k]
    return d


def overlap(got, ref):
    """Distributional agreement between two count dicts, as a cell count."""
    return sum(min(got.get(k, 0), ref.get(k, 0)) for k in set(got) | set(ref))


def main():
    overlay = json.load(open(OVERLAY))
    meta = overlay["meta"]
    drift = []
    for path, expected in REFERENCE.items():
        got = get(meta, path)
        if got != expected:
            drift.append(f"  {path}: got {got!r} != reference {expected!r}")

    # Genuine % match: min-overlap over the differentiation + function
    # distributions, averaged. 100% exactly when both match cell-for-cell.
    n = REFERENCE["n_shown"]
    ds_ov = overlap(meta["nomen_counts"]["ds"], REFERENCE["nomen_counts.ds"])
    fn_ov = overlap(meta["nomen_counts"]["func"], REFERENCE["nomen_counts.func"])
    match_pct = round(100.0 * (ds_ov + fn_ov) / (2 * n), 1)

    if drift:
        print("DRIFT — emitted overlay does NOT match the reference (match %.1f%%):" % match_pct,
              file=sys.stderr)
        print("\n".join(drift), file=sys.stderr)
        sys.exit(1)

    # Stamp the verified match into the overlay so the workbench can show it.
    meta["match_pct"] = match_pct
    json.dump(overlay, open(OVERLAY, "w"))
    print("OK — emitted overlay matches the reference "
          "(differentiation + function intact, match %.1f%%)." % match_pct)


if __name__ == "__main__":
    main()
