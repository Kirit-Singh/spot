# %% [markdown]
# # spot Stage-1 CD4 transcriptional-program scoring — reproducible pipeline
#
# Continuous per-cell scoring of the Marson non-targeting-control (NTC) CD4 T cells
# against descriptive transcriptional-program panels. **This is exploratory
# decision-support, not a cell-type classifier.** It emits continuous program scores
# only — no categorical calls, no FDR, no "cell type", no prevalence.
#
# **RNA program-compatibility does not demonstrate lineage stability, protein
# expression, cytotoxicity, or suppressive function.** The programs are named
# "-like transcriptional program" (e.g. Treg-like, CD4 CTL-like) throughout.
#
# **Sources**
# - Cells & design: Marson *Genome-scale perturb-seq in primary human CD4+ T cells*,
#   bioRxiv 2025.12.23.696273 (CRISPRi; 4 donors; Rest/Stim8hr/Stim48hr).
# - Data access: **CZI Virtual Cell Platform**. The embedded, clustered object is
#   redistributed on Hugging Face (public, MIT).
# - Panels: Masopust et al. *Guidelines for T cell nomenclature*, Nat Rev Immunol
#   2026;26:298-313, used as a **panel source**, not as functional confirmation.
#
# Method is frozen in `STAGE1_REMEDIATION_METHOD.md`. `SEED` fixes the control-set
# sampling in `score_genes` so the run is deterministic; `verify_reproduce.py` gates
# the emitted per-barcode scores.

# %%
import os, anndata as ad, numpy as np, scipy.sparse as sp, pandas as pd, json
import warnings; warnings.filterwarnings("ignore")

D = os.environ.get("SPOT_DATA", "./spot_scvi/").rstrip("/") + "/"
SEED = 12345
METHOD_VERSION = "stage1-continuous-v2"
rng = np.random.default_rng(SEED)

# %% [markdown]
# ## 1. Data
#
# The embedded object `ntc_clustered.h5ad` is fetched from the public HF dataset. `.X`
# is the authors' default-median `normalize_total()` + `log1p` on raw counts (used
# only as the scoring matrix; scVI trains on raw counts). NB: alternative
# normalizations (e.g. CP10k, target_sum=1e4) are **not** call-invariant — changing
# the target sum changes `log1p(alpha*x)` and shifts panel-minus-control scores; median
# normalization is frozen as part of the method and any alternative is a sensitivity
# analysis, not an identity.

# %%
a = ad.read_h5ad(D + "ntc_clustered.h5ad", backed="r")
obs = a.obs
N = a.n_obs
print(f"cells: {N:,}  |  genes: {a.shape[1]:,}  |  all NTC: {(obs['perturbed_gene_name']=='NTC').all()}")
print("condition balance:"); print(obs["condition"].value_counts().to_string())
print(f"donors: {sorted(obs['donor'].unique())}")

# %% [markdown]
# ## 2. Embedding & clustering (spot-specific, paper-inspired — NOT paper-exact)
#
# The embedding uses the authors' published scVI **architecture** values (5000 HVG
# seurat_v3, n_latent=30, n_layers=2, dropout=0.2, NB, batch=donor) on raw counts,
# then a 100-NN UMAP. It is **not a verbatim reproduction**: (i) the executed host
# script did not confirm several of the authors' training settings against their
# notebook (documented in the README); (ii) the **Leiden-0.8 clustering is spot's own**
# (the authors embed but do not cluster the NTC cells); (iii) the subset is spot's
# **quota-balanced** sample (33,000 cells per donor x condition = 396,000), NOT the
# authors' NTC population weighting (~395,030). Percentages below are prevalences in an
# equal-weighted spot sample, not in the source population. We load the precomputed
# Leiden labels (obs `L0.8`); per-cluster continuous program z-scores are the output of
# `cluster_scores.py` -> `label_clusters.py` (cluster_labels.json), which assigns NO
# forced cluster label.

# %%
cluster = obs["L0.8"].astype(int).values
condv = obs["condition"].astype(str).values
donorv = obs["donor"].astype(str).values
barcodes = obs["barcode"].values
meta = json.load(open(D + "stage01_umap_seed.json"))["meta"]
_lab = D + "cluster_labels.json"
if os.path.exists(_lab):
    meta["clusters"] = json.load(open(_lab))
# display-only colour key per cluster (NOT a call; excluded from exported records)
cl_display = {c["id"]: c.get("dominant_program_for_display_only") for c in meta["clusters"]}
print("Leiden clusters:", sorted(np.unique(cluster)))

# %% [markdown]
# ## 3. Transcriptional-program panels (Masopust et al. panels, descriptive)
#
# Human marker panels restricted to genes measurable in this probe-based (10x Flex)
# dataset. These score descriptive transcriptional programs; they are NOT functional
# assays. Marker non-detection is reported descriptively, never used as a hard gate
# (Flex dropout makes absence-of-detection weak evidence of absence).

# %%
FUNC = {
    "th1_like":     ["CXCR3", "TBX21", "IFNG", "IL12RB2"],
    "th2_like":     ["PTGDR2", "IL4", "IL5", "IL13"],
    "th17_like":    ["CCR6", "RORC", "IL17A", "IL17F", "IL23R", "KLRB1"],
    "tfh_like":     ["CXCR5", "BCL6", "IL21"],
    "treg_like":    ["FOXP3", "IKZF2", "CTLA4", "CCR8", "TNFRSF18"],
    "cd4_ctl_like": ["GNLY", "PRF1", "GZMH", "KLRD1", "GZMB", "NKG7"],
    "th9_like":     ["IL9", "SPI1"],
}
DIFF = {
    "diff_naive":      ["CCR7", "SELL", "TCF7", "LEF1", "IL7R", "MAL"],
    "diff_activated":  ["CD69", "IL2RA", "CD38", "MKI67", "HLA-DRA", "TNFRSF9"],
    "diff_memory":     ["ITGAL", "FAS", "CD58", "ITGA4", "S100A4", "CD27"],
    "diff_checkpoint": ["PDCD1", "TOX", "HAVCR2", "LAG3", "TIGIT", "ENTPD1"],
}
FK, DK = list(FUNC), list(DIFF)
vs = set(a.var_names)

# %% [markdown]
# ## 4. Continuous program scoring (no inference)
#
# Per-cell scores use `sc.tl.score_genes` (panel mean minus expression-bin-matched
# control mean, 25 bins, ctrl_size 50), reimplemented vectorized. **These are the only
# scientific outputs on the program axes: continuous scores.** No permutation null, no
# p/q, no FDR, no argmax, no categorical call. The prior permutation "null" is removed
# (its random panels were drawn uniformly, not expression-matched, so it was mislabeled
# as well as unsupported).
#
# For CD4 CTL-like, an activation-conditioned **sensitivity** score is reported
# alongside the raw score (activation regressed out); it is descriptive, drives nothing.

# %%
Xf = a.to_memory().X.tocsc()
var = np.array(a.var_names); v2i = {g: i for i, g in enumerate(var)}
N_BINS, CTRL_SIZE = 25, 50
obs_avg = pd.Series(np.asarray(Xf.mean(0)).ravel(), index=var)
obs_avg = obs_avg[np.isfinite(obs_avg)]
obs_cut = (obs_avg.rank(method="min") // int(round(len(obs_avg)/(N_BINS-1)))).astype(int)

def mean_cols(idx):
    return np.zeros(N) if len(idx) == 0 else np.asarray(Xf[:, idx].sum(1)).ravel()/len(idx)

def score_panel(gl, rng):
    gl = [g for g in gl if g in v2i]
    gl_idx = np.sort(np.array([v2i[g] for g in gl]))            # sorted -> deterministic float summation
    ctrl = set()
    for c in np.unique(obs_cut.loc[gl]):
        cand = obs_cut.index[obs_cut.values == c].values
        ctrl.update(rng.choice(cand, CTRL_SIZE, replace=False) if len(cand) > CTRL_SIZE else cand)
    ctrl -= set(gl)
    ctrl_idx = np.sort(np.array([v2i[g] for g in ctrl]))        # SORT: set-iteration order is hash-randomized;
    return mean_cols(gl_idx) - mean_cols(ctrl_idx)              # sorting makes the summation order reproducible

# continuous scores (the shipped scientific outputs)
func_scores = {f"{k}_score": score_panel(FUNC[k], rng) for k in FK}
diff_scores = {f"{k}_score": score_panel(DIFF[k], rng) for k in DK}

# CD4 CTL-like activation-conditioned SENSITIVITY score (descriptive; drives nothing)
S_act = score_panel([g for g in ["CD69", "CD38", "MKI67", "TNFRSF9", "IL2RA"] if g in v2i], rng)
raw_ctl = func_scores["cd4_ctl_like_score"]
_b = np.polyfit(S_act, raw_ctl, 1)
func_scores["cd4_ctl_like_score_actadj"] = raw_ctl - (_b[0]*S_act + _b[1])

# marker-detection descriptors (descriptive, not gates)
def det(g):
    if g not in vs: return np.zeros(N, bool)
    v = a[:, [g]].to_memory().X; v = v.toarray() if sp.issparse(v) else np.asarray(v)
    return (v.ravel() > 0)
marker_det = {f"{g.lower()}_detected": det(g) for g in ["GNLY", "CD27", "IFNG", "GATA3", "CCR4"]}

print("emitted continuous program scores:", sorted(list(func_scores) + list(diff_scores)))

# %% [markdown]
# ## 5. Descriptive score summary by donor x condition
#
# Median program score per donor x condition — the honest, stratified view that keeps
# the residual activation/timepoint association visible instead of hiding it behind a
# single number. No thresholds, no calls.

# %%
df = pd.DataFrame({"donor": donorv, "condition": condv, **{k: v for k, v in func_scores.items()}})
for k in ["treg_like_score", "cd4_ctl_like_score", "th1_like_score"]:
    print(f"\nmedian {k} by donor x condition:")
    print(df.groupby(["condition", "donor"])[k].median().round(3).to_string())

# %% [markdown]
# ## 6. Emit overlay + per-cell records together
#
# One canonical per-barcode table drives BOTH `stage01_umap_seed.json` (the 40k display
# overlay, carrying continuous scores + a display-only colour key) and
# `stage01_cell_records.json` (the exported per-cell records: continuous scores only, no
# display key). The wall-clock timestamp is kept out of the canonical body (separate
# `meta.emitted_at`). `verify_reproduce.py` hashes the per-barcode scores.

# %%
allcols = {**func_scores, **diff_scores}
b2i = {str(barcodes[i]): i for i in range(N)}
overlay = json.load(open(D + "stage01_umap_seed.json"))
overlay["meta"]["clusters"] = meta["clusters"]
# records = the OVERLAY's cells only (matches the overlay set exactly), scores + marker
# detections; no display key, no call. Keyed by barcode.
records = {}
for c in overlay["cells"]:
    bc = str(c["barcode"]); i = b2i[bc]
    rec = {k: round(float(allcols[k][i]), 5) for k in allcols}
    for mk, mv in marker_det.items():
        rec[mk] = bool(mv[i])
    records[bc] = rec
    for k in allcols: c[k] = rec[k]
    # DISPLAY-ONLY colour key: the cell's own top program score (excluded from records/analysis)
    c["dominant_program_for_display_only"] = max(
        (k for k in func_scores if k.endswith("_score") and not k.endswith("_actadj")),
        key=lambda k: rec[k])
    # remove retired categorical fields if present
    c.pop("func", None); c.pop("ds", None); c.pop("funcc", None); c.pop("dsc", None)
    c.pop("top_program", None)
overlay["meta"].pop("nomen_counts", None); overlay["meta"].pop("nomen_method", None)
overlay["meta"]["method_version"] = METHOD_VERSION
overlay["meta"]["score_fields"] = sorted(allcols)

from datetime import datetime
overlay["meta"]["emitted_at"] = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
json.dump(overlay, open("stage01_umap_seed.emitted.json", "w"))
# records: continuous scores + marker detections only, keyed by barcode (no display key)
json.dump(records, open("stage01_cell_records.emitted.json", "w"))
print(f"emitted {len(overlay['cells'])} overlay cells + {len(records)} per-cell records")

# %% [markdown]
# ## Summary
#
# - 396k quota-balanced NTC CD4 cells; continuous transcriptional-program scores only.
# - No categorical calls, no FDR, no "cell type", no prevalence.
# - The Treg-like program is a candidate transcriptional program for downstream study,
#   NOT a confirmed Treg identity; RNA compatibility shows neither suppressive function
#   nor protein expression. External / protein / functional validation remains required.
#
# ## Reproduce
#
# ```bash
# ./reproduce.sh   # fetch the pinned HF revision + hash, run this pipeline, verify per-barcode
# ```
