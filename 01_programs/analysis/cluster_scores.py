# Score each Leiden-0.8 cluster against confound-aware state panels; dump the
# per-cluster z-score matrix + condition mix so the assignment rule can be tuned
# offline (one 14GB load). Confound handling matches the pipeline's marker drops.
import os, anndata as ad, scanpy as sc, numpy as np, json
from collections import Counter
# Data dir holding ntc_clustered.h5ad. Override with SPOT_DATA; defaults to ./spot_scvi/.
D = os.environ.get("SPOT_DATA", "./spot_scvi/").rstrip("/") + "/"
PANELS = {
    "Naive":     ["CCR7", "SELL", "TCF7", "LEF1"],
    "Activated": ["CD69", "CD38", "TNFRSF9", "HLA-DRA"],       # MKI67 (cycling) & IL2RA (shared) excluded
    "Cycling":   ["MKI67", "TOP2A", "PCNA", "MCM7"],
    "Memory":    ["ITGAL", "ITGA4", "CD58", "S100A4"],         # FAS dropped (activation-induced)
    "Treg":      ["FOXP3", "IKZF2", "CCR8", "TNFRSF18"],       # IL2RA/CTLA4 dropped (activation-shared)
}
print("loading …", flush=True)
a = ad.read_h5ad(D + "ntc_clustered.h5ad")
cluster = a.obs["L0.8"].astype(int).values
cond = a.obs["condition"].astype(str).values
vs = set(a.var_names); progs = list(PANELS)
for p in progs:
    sc.tl.score_genes(a, [g for g in PANELS[p] if g in vs], score_name="s_" + p, use_raw=False, random_state=0)
cls = sorted(set(int(x) for x in cluster))
mat = np.zeros((len(cls), len(progs))); condfrac = {}
for i, cl in enumerate(cls):
    m = cluster == cl; n = int(m.sum())
    for j, p in enumerate(progs):
        mat[i, j] = a.obs["s_" + p].values[m].mean()
    cc = Counter(cond[m]); condfrac[cl] = {k: round(v / n, 3) for k, v in cc.items()}
z = (mat - mat.mean(0)) / (mat.std(0) + 1e-9)
dump = {"clusters": cls, "progs": progs, "z": z.tolist(), "cond": condfrac,
        "pct": {cl: round(100 * (cluster == cl).sum() / len(cluster), 1) for cl in cls}}
json.dump(dump, open(D + "cluster_scores.json", "w"), indent=1)
print("dumped cluster_scores.json", flush=True)
for i, cl in enumerate(cls):
    print(cl, {p: round(z[i, j], 2) for j, p in enumerate(progs)}, "cond", condfrac[cl], flush=True)
