# 01_programs — CD4 transcriptional-program scores

Interactive UMAP of CD4⁺ NTC cells carrying **continuous transcriptional-program scores** —
Treg-like, CD4 CTL-like, Th1-like/Th2-like/Th17-like/Tfh-like/Th9-like, plus differentiation
programs — scored from the Marson genome-scale CD4 perturb-seq non-targeting-control (NTC) cells.

> **Exploratory decision-support — not a cell-type classifier.** These are continuous scores, not
> categorical calls: no forced labels, no FDR/p-q, no "cell type", no prevalence. **RNA
> program-compatibility does not demonstrate lineage stability, protein expression, cytotoxicity,
> or suppressive function.** See `REMEDIATION_STATEMENT.md`.

Stage-1 hands Stage-2 a **candidate Treg-like transcriptional program** to study, **not** a
confirmed Treg identity.

## Layout
- `app/` — the workbench (`01_page.html`), the rendered methodology report (`01_notebook.html`),
  and the vcp data-provenance trace (`01_trace.html`). `app/data/` holds the overlay + per-cell
  records the pages render.
- `analysis/` — the reproducible pipeline chain (below), the frozen method spec
  (`STAGE1_REMEDIATION_METHOD.md`), the change report (`STAGE1_REMEDIATION_CHANGES.md`), and the
  Claude Science reviews.
- `inputs/` — pointer to the public CZI dataset (marker panels live in the code).
- `outputs/` — generated intermediates (gitignored).

## What it produces
A 40,000-cell display overlay (`SEED=12345`), each cell carrying **12 continuous program scores**
(`treg_like_score`, `cd4_ctl_like_score` + `_actadj`, `th1_like_score`, …, `diff_*_score`) plus a
display-only colour key. **No categorical calls.** The activation/timepoint and donor structure is
reported (not hidden) — see `analysis/STAGE1_REMEDIATION_CHANGES.md` for donor×condition score
distributions.

## Setup & run — reproduce from scratch

### Requirements
A scanpy environment (CPU is fine for the scoring tier):
- Python 3.11
- `anndata==0.12` · `scanpy==1.11` · **`numpy<2` (e.g. `1.26`)** · `scipy==1.15` · `pandas==2.2`
  (note: `pandas==2.2` requires `numpy<2` — do not pin `numpy>=2.3`), and `huggingface_hub`
  (the `hf` CLI) to fetch the embedded object.
- Peak RAM ~**21–25 GB** (loads the full 396k × 18,130 matrix); allow **≥32 GB**. Not the earlier
  "~3 min on any CPU" — a faithful run took ~5 min on a 91 GB host.

### Two tiers — know the boundary
1. **Embedding tier** (raw public data → `ntc_clustered.h5ad`): scVI + Leiden on the NTC CD4 cells.
   GPU-scale (the full source is ~1.84 TB); run **once**, cached. This embedding is **spot-specific
   and paper-inspired, NOT a verbatim reproduction** (scVI architecture matches the authors; the
   Leiden clustering and the seed are spot's; the 396k subset is spot's quota-balanced sample, not
   the authors' NTC weighting). You do not need to re-run it — the object is published.
2. **Scoring tier** (`ntc_clustered.h5ad` → continuous program scores → overlay): deterministic,
   CPU, and **per-barcode reproducible** — this is what runs here.

### Fetch the embedded object (pinned)
Published (**public, MIT**) at
[**KiritSingh/spot-CD4-Marson**](https://huggingface.co/datasets/KiritSingh/spot-CD4-Marson),
superseding revision **`e5fcf98b`**. `ntc_clustered.h5ad` is **3.84 GB** (SHA-256 `2edc6d31…`,
verified by `reproduce.sh`). Fetch:
```bash
export SPOT_DATA=./spot_scvi
hf download KiritSingh/spot-CD4-Marson ntc_clustered.h5ad stage01_umap_seed.json \
    --repo-type dataset --revision e5fcf98b56a9302921d402e97fc5a190bd88f9a6 --local-dir "$SPOT_DATA"
```

### Run the scoring tier
```bash
cd analysis
./reproduce.sh          # pins the HF revision + SHA, runs the chain, writes app/data/ atomically, verifies per-barcode
```
which runs `cluster_scores.py` → `label_clusters.py` (continuous per-cluster z-scores, **no forced
label**) → `stage1_pipeline.py` (continuous per-cell program scores; **no FDR/p-q/argmax**; emits
overlay + 40k records together) → `verify_reproduce.py` (the **per-barcode** gate).

### Reproducible (per-barcode, deterministic)
`verify_reproduce.py` hashes a **canonical sorted per-barcode table** (barcode, cluster, condition,
donor, the 12 scores) — not aggregate counts (the old count-only gate let a zero-cell overlay pass).
Determinism: `SEED=12345`, sorted control indices, `PYTHONHASHSEED=0`. Frozen reference:
`canonical_table_sha256 = 6e1665d1…`, `barcode_set_sha256 = 1224312e…`, n = 40,000.

## The pipeline (analysis/)
- `cluster_scores.py` → per-cluster panel z-scores (one object load).
- `label_clusters.py` → continuous per-cluster program z-scores + a **display-only** colour key
  (excluded from records/analysis). **No forced label**; condition reported, never an input.
- `stage1_pipeline.py` → continuous per-cell program scores (`score_genes` panels; **no null, no
  p/q, no argmax, no categorical call**); CD4 CTL-like reports a raw score + an
  activation-conditioned sensitivity score; emits the overlay + records.
- `verify_reproduce.py` → the per-barcode canonical-hash gate.

Method frozen in `STAGE1_REMEDIATION_METHOD.md`; old-vs-new in `STAGE1_REMEDIATION_CHANGES.md`.

## Provenance
- `app/01_notebook.html` — a **rendered methodology report** of `stage1_pipeline.py` (NOT an
  executed notebook; numeric results come from running the pipeline, not the renderer).
- `app/01_trace.html` — the vcp data-provenance trace.
- `analysis/STAGE1_EXTERNAL_REVIEW_CS.md`, `STAGE1_REMEDIATION_METHOD.md`,
  `STAGE1_REMEDIATION_CHANGES.md` — the reviews, frozen method, and change report.

## Data source
Marson GWCD4i genome-scale CRISPRi perturb-seq (bioRxiv 2025.12.23.696273) — NTC CD4 cells, 4
donors × Rest/Stim8hr/Stim48hr — public on the **CZI Virtual Cells Platform**. Program panels are
sourced from Masopust et al., *Guidelines for T cell nomenclature*, Nat Rev Immunol
2026;26:298-313 — used as a **panel source**, not as functional confirmation.
