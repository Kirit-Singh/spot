# Per-cluster continuous transcriptional-program scores. Reads the per-cluster panel
# z-scores (cluster_scores.py output) and emits cluster_labels.json for the overlay.
# No h5ad load.
#
# CORRECTED (2026-07 remediation, v2 — continuous-only). Per the frozen method spec
# (STAGE1_REMEDIATION_METHOD.md):
#   * NO forced label. The prior rule assigned exactly one cluster "Treg" via an
#     unconditional argmax; that is removed. No cluster is assigned a scientific label.
#   * NO condition input. The prior rule split Naive/Memory vs Activated on the Rest
#     fraction (>0.5), leaking the design variable into a "transcriptional" label. Removed.
#     Condition is REPORTED (dominant_condition), never used to decide anything. NB: removing
#     condition from a rule does not remove condition-associated biology from expression —
#     substantial activation/timepoint association remains and is a documented limitation.
#   * NO compatibility flag, NO activation veto, NO threshold. Activated Treg-like transcription
#     is biologically possible, so an "Activated z < 1" veto would falsely restore mutual
#     exclusivity; it is removed.
#
# The per-cluster z-scores are STANDARDIZED WITHIN THIS DATASET'S CLUSTERS (cluster mean minus
# cross-cluster mean over cross-cluster SD). They mean "relatively elevated here", NOT an
# absolute threshold or absolute evidence. Program names are descriptive transcriptional
# programs, never validated cell types.
import os, json
D = os.environ.get("SPOT_DATA", "./spot_scvi/").rstrip("/") + "/"

# Descriptive program names + display markers. NOT lineage identities.
PROG_KEY = {"Naive": "naive_like", "Activated": "activated", "Cycling": "cycling",
            "Memory": "adhesion_high", "Treg": "treg_like"}
DISPLAY_MARKERS = {"naive_like": ["CCR7", "SELL", "TCF7", "LEF1"],
                   "activated": ["CD69", "CD38", "TNFRSF9", "HLA-DRA"],
                   "cycling": ["MKI67", "TOP2A", "PCNA", "MCM7"],
                   "adhesion_high": ["ITGAL", "ITGA4", "CD58", "S100A4"],
                   "treg_like": ["FOXP3", "IKZF2", "CTLA4", "IL2RA"]}

s = json.load(open(D + "cluster_scores.json"))
cls, progs = s["clusters"], s["progs"]
Z = {cl: dict(zip(progs, s["z"][i])) for i, cl in enumerate(cls)}
cond = {int(k): v for k, v in s["cond"].items()}  # REPORTED only, never an input

out = []
for cl in cls:
    z = Z[cl]
    scores = {PROG_KEY[p]: round(float(z[p]), 3) for p in ["Naive", "Activated", "Cycling", "Memory", "Treg"] if p in z}
    dom_cond = max(cond[cl], key=cond[cl].get) if cl in cond and cond[cl] else None
    # DISPLAY-ONLY colour key (argmax of the within-dataset z-scores). Excluded from analysis and
    # from the exported per-cell records; not a biological call. Never used as evidence.
    dom_display = max(scores, key=scores.get) if scores else None
    out.append({
        "id": cl,
        "pct": s["pct"][str(cl)] if str(cl) in s["pct"] else s["pct"].get(cl),
        "program_scores_within_dataset_z": scores,   # continuous; relative within this dataset
        "dominant_program_for_display_only": dom_display,  # colour key ONLY; not analysis/export
        "dominant_condition": dom_cond,               # reported; NOT an input to any label
        "display_markers": DISPLAY_MARKERS.get(dom_display, []),
    })

json.dump(out, open(D + "cluster_labels.json", "w"), indent=1)
print("wrote cluster_labels.json — continuous per-cluster program z-scores (no forced label).")
print("dominant_program_for_display_only (colour key only, not a call):",
      {c["id"]: c["dominant_program_for_display_only"] for c in out})
