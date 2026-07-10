# Reproducible cluster -> state-program labeling. Reads the per-cluster panel
# z-scores (cluster_scores.py output) and applies a fixed, confound-aware rule.
# Emits cluster_labels.json (the meta.clusters the overlay consumes). No h5ad load.
#
# Rule (order matters — handles the activation confounds explicitly):
#   1. Cycling   : Cycling z > 1.0  (clear proliferation signal)
#   2. Treg      : the single remaining cluster with the highest Treg z AND
#                  Activated z < 1.0  (Treg-high but not strongly activated —
#                  excludes 8hr-activated clusters where GITR/CCR8 leak up)
#   3. remaining : Rest-dominant -> Naive if Naive z > 0.5 else Memory;
#                  Stim-dominant -> Activated
import os, json
# Data dir holding cluster_scores.json (from cluster_scores.py). Override with SPOT_DATA.
D = os.environ.get("SPOT_DATA", "./spot_scvi/").rstrip("/") + "/"
MARKERS = {"Naive": ["CCR7", "SELL", "TCF7", "LEF1"], "Activated": ["CD69", "CD38", "TNFRSF9", "HLA-DRA"],
           "Cycling": ["MKI67", "TOP2A", "PCNA", "MCM7"], "Memory": ["ITGAL", "ITGA4", "CD58", "S100A4"],
           "Treg": ["FOXP3", "IKZF2", "CTLA4", "IL2RA"]}  # display markers (scoring panel is in cluster_scores.py)

s = json.load(open(D + "cluster_scores.json"))
cls, progs = s["clusters"], s["progs"]
Z = {cl: dict(zip(progs, s["z"][i])) for i, cl in enumerate(cls)}
cond = {int(k): v for k, v in s["cond"].items()}
rest = lambda cl: cond[cl].get("Rest", 0) > 0.5

assign, taken = {}, set()
for cl in cls:                                    # 1. Cycling
    if Z[cl]["Cycling"] > 1.0: assign[cl] = "Cycling"; taken.add(cl)
treg = max((cl for cl in cls if cl not in taken and Z[cl]["Activated"] < 1.0),
           key=lambda cl: Z[cl]["Treg"])          # 2. Treg (one cluster)
assign[treg] = "Treg"; taken.add(treg)
for cl in cls:                                    # 3. remaining
    if cl in taken: continue
    assign[cl] = ("Naive" if Z[cl]["Naive"] > 0.5 else "Memory") if rest(cl) else "Activated"

out = []
for cl in cls:
    p = assign[cl]
    out.append({"id": cl, "pct": s["pct"][str(cl)] if str(cl) in s["pct"] else s["pct"].get(cl),
                "top_program": p, "is_treg_cluster": bool(cl == treg),
                "markers": MARKERS[p], "mean_state_score": round(float(Z[cl][p]), 3)})
json.dump(out, open(D + "cluster_labels.json", "w"), indent=1)
print("assignments:", {cl: assign[cl] for cl in cls})
print("treg_cluster:", treg)
print("wrote cluster_labels.json")
