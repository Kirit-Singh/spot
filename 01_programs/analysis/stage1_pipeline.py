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
# ## 2. Embedding & clustering (spot-specific, paper-inspired — not a verbatim reproduction)
#
# The embedding uses the authors' published scVI **architecture** values (5000 HVG
# seurat_v3, n_latent=30, n_layers=2, dropout=0.2, NB, batch=donor) on raw counts,
# then a 100-NN UMAP. It is **not a verbatim reproduction**: (i) the executed host
# script did not confirm several of the authors' training settings against their
# notebook (documented in the README); (ii) the **Leiden-0.8 clustering is spot's own**
# (the authors embed but do not cluster the NTC cells); (iii) the subset is spot's
# **quota-balanced** sample (33,000 cells per donor x condition = 396,000), NOT the
# authors' NTC population weighting (~395,030). Percentages below are prevalences in an
# equal-weighted spot sample, not in the source population. Numeric Leiden labels
# (obs `L0.8`) are carried only as technical provenance; the served overlay assigns NO
# biological cluster label and does not depend on the cluster diagnostics.

# %%
cluster = obs["L0.8"].astype(int).values
condv = obs["condition"].astype(str).values
donorv = obs["donor"].astype(str).values
barcodes = obs["barcode"].values
# Numeric Leiden IDs are retained as technical provenance only. The primary reproduction
# chain does NOT depend on cluster_scores.py / label_clusters.py (cluster_labels.json) — no
# per-cluster biological labels enter the served overlay. Those files remain as optional,
# clearly non-production diagnostics.
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
# alongside the raw score (activation regressed out); it is descriptive and feeds no call.

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
    ctrl_symbols = [str(var[i]) for i in ctrl_idx]             # EXACT frozen control genes, index-sorted (deterministic)
    return mean_cols(gl_idx) - mean_cols(ctrl_idx), ctrl_symbols  # sorting makes the summation order reproducible

# EXACT frozen control genes each score_panel() sampled, per score field. Threaded out of
# score_panel WITHOUT changing the scoring math or the RNG draw order (score_panel still
# consumes `rng` in the same FK -> DK -> S_act sequence). Stored in meta.programs[].control_genes.
CONTROL_GENES = {}
def _score_field(name, gl):
    s, ctrl = score_panel(gl, rng)
    CONTROL_GENES[name] = ctrl
    return s

# continuous scores (the shipped scientific outputs)
func_scores = {f"{k}_score": _score_field(f"{k}_score", FUNC[k]) for k in FK}
diff_scores = {f"{k}_score": _score_field(f"{k}_score", DIFF[k]) for k in DK}

# CD4 CTL-like activation-conditioned SENSITIVITY score (descriptive sensitivity lane)
S_act, _ = score_panel([g for g in ["CD69", "CD38", "MKI67", "TNFRSF9", "IL2RA"] if g in v2i], rng)
raw_ctl = func_scores["cd4_ctl_like_score"]
_b = np.polyfit(S_act, raw_ctl, 1)
func_scores["cd4_ctl_like_score_actadj"] = raw_ctl - (_b[0]*S_act + _b[1])
# the actadj sensitivity lane reuses the cd4_ctl_like panel's frozen control set (activation
# is regressed out afterward; no new control draw), so its exact control genes are identical.
CONTROL_GENES["cd4_ctl_like_score_actadj"] = CONTROL_GENES["cd4_ctl_like_score"]

print("emitted continuous program scores:", sorted(list(func_scores) + list(diff_scores)))

# %% [markdown]
# ## 5. Descriptive score summary by donor x condition
#
# Median program score per donor x condition — stratified so the residual
# activation/timepoint association stays visible. No thresholds, no calls.

# %%
df = pd.DataFrame({"donor": donorv, "condition": condv, **{k: v for k, v in func_scores.items()}})
for k in ["treg_like_score", "cd4_ctl_like_score", "th1_like_score"]:
    print(f"\nmedian {k} by donor x condition:")
    print(df.groupby(["condition", "donor"])[k].median().round(3).to_string())

# %% [markdown]
# ## 6. Emit overlay + per-cell records from an explicit WHITELIST
#
# The served overlay is REBUILT here from a whitelist — every `meta` key and every cell key
# is constructed in this block, never inherited from the prior seed JSON (which carried
# retired embedding claims plus the prior seed's inherited per-cell display/QC fields and a
# display-only argmax. Only `x`,`y` (the frozen UMAP coordinates) and the 40,000-cell
# display selection are read from the prior seed; barcode/cluster/condition/donor are its
# identifiers; the 12 continuous scores are this run's outputs. Per-score display domains
# (p02/p50/p98) are frozen ONCE over the full 396k scoring universe and stored in `meta`
# (`programs[].display_domain` and `score_display_domains`); the UI must never recompute
# them under donor/condition filters. `verify_reproduce.py` hashes the per-barcode scores.

# %%
import hashlib
from datetime import datetime
allcols = {**func_scores, **diff_scores}                       # 12 continuous scores over all 396k
b2i = {str(barcodes[i]): i for i in range(N)}

# frozen per-score display domain over the FULL 396k universe. Richer quantiles
# (p02 p10 p25 p50 p75 p90 p95 p98 p99) so the §4.1 sparse-domain transform can pick the
# first upper quantile STRICTLY greater than p50; p02/p50/p98 retained for back-compat.
_DOMAIN_QUANTILES = [2, 10, 25, 50, 75, 90, 95, 98, 99]
def _domain(v):
    p = np.percentile(v, _DOMAIN_QUANTILES)
    return {f"p{q:02d}": round(float(pi), 5) for q, pi in zip(_DOMAIN_QUANTILES, p)}
SCORE_DOMAINS = {k: _domain(allcols[k]) for k in sorted(allcols)}

# programs[] contract — the single source of truth for the UI selector / legend / cards / methods.
# No argmax across fields anywhere; scores are compared only within a field.
DISPLAY_LABEL = {
    "diff_naive_score": "Naïve-like", "diff_activated_score": "Activated",
    "diff_memory_score": "Memory / adhesion-like", "diff_checkpoint_score": "Checkpoint-high",
    "treg_like_score": "Treg-like", "cd4_ctl_like_score": "CD4 CTL-like",
    "th1_like_score": "Th1-like", "th2_like_score": "Th2-like", "th17_like_score": "Th17-like",
    "tfh_like_score": "Tfh-like", "th9_like_score": "Th9-like",
    "cd4_ctl_like_score_actadj": "CD4 CTL-like · activation-adjusted sensitivity",
}
PANEL_OF = {**{f"{k}_score": FUNC[k] for k in FK}, **{f"{k}_score": DIFF[k] for k in DK},
            "cd4_ctl_like_score_actadj": FUNC["cd4_ctl_like"]}
FAMILY_OF = {**{f"{k}_score": "differentiation" for k in DK}, **{f"{k}_score": "functional" for k in FK},
             "cd4_ctl_like_score_actadj": "sensitivity"}
PROGRAM_ORDER = ["diff_naive_score", "diff_activated_score", "diff_memory_score", "diff_checkpoint_score",
                 "treg_like_score", "cd4_ctl_like_score", "th1_like_score", "th2_like_score",
                 "th17_like_score", "tfh_like_score", "th9_like_score", "cd4_ctl_like_score_actadj"]
_METHOD = ("score_genes: panel mean minus expression-bin-matched control mean "
           "(25 bins, ctrl_size 50), SEED=12345")
_SRC = "Masopust et al., Guidelines for T cell nomenclature, Nat Rev Immunol 2026;26:298-313"
programs = [{
    "score_field": k,
    "display_label": DISPLAY_LABEL[k],
    "family": FAMILY_OF[k],
    "panel_genes": PANEL_OF[k],
    "control_genes": CONTROL_GENES[k],   # EXACT frozen control genes score_panel() sampled (symbols)
    "scoring_method": (_METHOD if not k.endswith("_actadj")
                       else "cd4_ctl_like_score with a linear activation score regressed out (descriptive sensitivity lane)"),
    "role": ("sensitivity" if k.endswith("_actadj") else "primary"),
    "display_domain": SCORE_DOMAINS[k],
    "source": _SRC,
} for k in PROGRAM_ORDER]

# rebuild cells from the whitelist: barcode, x, y, numeric cluster (provenance), condition,
# donor, + the 12 frozen continuous scores. Retired fields are simply not carried forward.
CELL_KEYS = ["barcode", "x", "y", "cluster", "condition", "donor"]
prior = json.load(open(D + "stage01_umap_seed.json"))
cells, records = [], {}
for c in prior["cells"]:
    bc = str(c["barcode"]); i = b2i[bc]
    rec = {k: round(float(allcols[k][i]), 5) for k in sorted(allcols)}
    records[bc] = rec
    cell = {"barcode": bc, "x": c["x"], "y": c["y"], "cluster": c["cluster"],
            "condition": c["condition"], "donor": c["donor"]}
    for k in sorted(allcols): cell[k] = rec[k]
    cells.append(cell)

# canonical scientific hashes (identical algorithm to verify_reproduce.py) — stored in meta
# as provenance; verify_reproduce.py independently recomputes and gates them.
def _canon(cells, fields):
    rows = []
    for c in cells:
        row = [str(c["barcode"]), str(c.get("cluster")), str(c.get("condition", "")), str(c.get("donor", ""))]
        row += [f"{round(float(c[f]), 5):.5f}" for f in fields]
        rows.append("\t".join(row))
    rows.sort()
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()
FIELDS = sorted(allcols)
canon_hash = _canon(cells, FIELDS)
bc_hash = hashlib.sha256("\n".join(sorted(c["barcode"] for c in cells)).encode()).hexdigest()

HF_REV = os.environ.get("SPOT_HF_REVISION", "e5fcf98b56a9302921d402e97fc5a190bd88f9a6")
H5AD_SHA = os.environ.get("SPOT_H5AD_SHA256", "2edc6d318415c8b0ee779d707ab86e26ddb6f0274db51ab4a12f21ebfda50e43")

# rebuild meta from a whitelist — no inherited keys, no retired claims
meta_out = {
    "schema_version": "stage1-overlay-v3-schema",
    "method_version": METHOD_VERSION,
    "source": {
        "dataset": "Marson genome-scale CRISPRi perturb-seq, primary human CD4+ T cells (bioRxiv 2025.12.23.696273)",
        "cells": "non-targeting-control (NTC) CD4 T cells, 4 donors × Rest/Stim8hr/Stim48hr",
        "access": "CZI Virtual Cells Platform",
        "hf_repo": "KiritSingh/spot-CD4-Marson",
        "hf_revision": HF_REV,
        "h5ad_sha256": H5AD_SHA,
        "license": "MIT",
    },
    "genome": "GRCh38 (human; 10x Flex probe set)",
    "scoring_universe_n": int(N),
    "display_n": len(cells),
    "design": {
        "donors": sorted(set(map(str, donorv))),
        "conditions": sorted(set(map(str, condv))),
        "subsample": "quota-balanced 33,000 cells per donor×condition (396,000)",
    },
    "embedding": {
        "method": ("scVI (authors' published architecture: 5000 HVG seurat_v3, n_latent=30, "
                   "n_layers=2, dropout=0.2, NB, batch=donor) on raw counts, then a 100-NN UMAP"),
        "clustering": "Leiden-0.8 — spot's own (the authors embed but do not cluster the NTC cells)",
        "faithfulness": ("spot-specific and paper-inspired, NOT a verbatim reproduction; several of "
                         "the authors' training settings were not confirmed against their notebook; the "
                         "396k subset is spot's quota-balanced sample, not the authors' NTC weighting"),
        "cluster_ids": "numeric Leiden IDs retained as technical provenance only — NOT named biological states",
    },
    "score_fields": FIELDS,
    "programs": programs,
    "score_display_domains": SCORE_DOMAINS,
    "verification": {
        "canonical_table_sha256": canon_hash,
        "barcode_set_sha256": bc_hash,
        "round_decimals": 5,
    },
    "methods_and_scope": ("Output: continuous RNA panel-minus-control scores from a four-donor "
                          "in-vitro dataset; protein and functional endpoints were not measured."),
    # noncanonical generation timestamp — NOT part of any hashed table
    "emitted_at": datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z"),
}
overlay = {"meta": meta_out, "cells": cells}
json.dump(overlay, open("stage01_umap_seed.emitted.json", "w"))
json.dump(records, open("stage01_cell_records.emitted.json", "w"))
print(f"emitted {len(cells)} overlay cells + {len(records)} per-cell records (continuous scores only)")
print(f"  canonical_table_sha256 = {canon_hash}")
print(f"  barcode_set_sha256      = {bc_hash}")

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
