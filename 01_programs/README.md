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
(`treg_like_score`, `cd4_ctl_like_score` + `_actadj`, `th1_like_score`, …, `diff_*_score`), plus a
`meta.programs[]` contract and frozen per-score display domains (p02/p50/p98 over the full 396k) that
drive the UI. **No categorical calls and no per-cell/per-cluster biological labels** — the workbench
colours by one selected continuous score at a time (a display-only colour transform; the scores
themselves are the scientific output). Cluster IDs are carried only as numeric technical provenance.
The activation/timepoint and donor structure is reported (not hidden) — see
`analysis/STAGE1_REMEDIATION_CHANGES.md` for donor×condition score distributions.

## Setup & run — reproduce from scratch

### Requirements
A scanpy environment (CPU is fine for the scoring tier). The **tested lock** that reproduced the
frozen per-barcode hashes is `analysis/requirements.txt` — pinned to the exact versions used:
- Python 3.11.15
- `anndata==0.12.19` · `scanpy==1.11.5` · `numpy==2.3.3` · `scipy==1.15.2` · `pandas==2.2.3`, and
  `huggingface_hub==1.23.0` (the `hf` CLI) to fetch the embedded object. (pandas 2.2 and numpy 2.3
  coexist fine — the earlier "numpy<2" note was incorrect.)
- Peak RAM ~**21–25 GB** (loads the full 396k × 18,130 matrix); allow **≥32 GB**. A faithful run
  took ~5 min on a 91 GB host.

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
which runs `stage1_pipeline.py` (continuous per-cell program scores; **no FDR/p-q/argmax**; rebuilds
the overlay + 40k records from an explicit whitelist) → `verify_reproduce.py` (the **per-barcode +
schema-contract** gate). The cluster diagnostics (`cluster_scores.py`/`label_clusters.py`) are **not**
part of this chain — the served overlay carries no biological cluster labels.

### Reproducible (per-barcode, deterministic)
`verify_reproduce.py` hashes a **canonical sorted per-barcode table** (barcode, cluster, condition,
donor, the 12 scores) and enforces the schema contract (cell-key whitelist, forbidden retired fields,
`programs[]`/domains, a stale-string scan). Determinism: `SEED=12345`, sorted control indices,
`PYTHONHASHSEED=0`. Frozen reference: `canonical_table_sha256 = 6e1665d1…`,
`barcode_set_sha256 = 1224312e…`, n = 40,000 (unchanged by the schema cleanup).

## The pipeline (analysis/)
- `stage1_pipeline.py` → continuous per-cell program scores (`score_genes` panels; **no null, no
  p/q, no argmax, no categorical call**); CD4 CTL-like reports a raw score + an
  activation-conditioned sensitivity score; **rebuilds the overlay + records from a whitelist**
  (`meta.programs[]`, frozen display domains; no inherited/retired fields).
- `verify_reproduce.py` → the per-barcode canonical-hash + schema-contract gate.
- `cluster_scores.py` / `label_clusters.py` → **optional, non-production** per-cluster diagnostics
  only; not part of the served chain (set `SPOT_RUN_CLUSTER_DIAG=1` to run them for inspection).

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
