# 01_programs — CD4 transcriptional programs

Interactive UMAP of CD4 transcriptional **state programs** (Naïve / Activated / Cycling /
Resting / Treg) plus per-cell **Masopust/Ahmed** differentiation + function calls, scored
from the Marson genome-scale CD4 perturb-seq non-targeting-control (NTC) cells.
**Locks:** the Treg program — the Stage-2 target.

## Layout
- `app/` — the workbench (`01_page.html`), the executable provenance notebook
  (`01_notebook.html`), and the vcp data-provenance trace (`01_trace.html`).
  `app/data/` holds the overlay + per-cell records the pages render.
- `analysis/` — the reproducible pipeline chain (below), the Claude Science review
  (`REVIEW_MEMO.md`), and the vcp re-verification record.
- `inputs/` — pointer to the public CZI dataset (marker panels live in the code).
- `outputs/` — generated intermediates (gitignored).

## What it produces
The deployed overlay (40,000 painted cells, `SEED=12345`): **~82.5% no functional call**
(expected for a Th0 polyclonal stim), **Th1** the only coherent activated skew (8 hr),
**Treg** the discrete Stage-2 target (a whole-transcriptome Leiden cluster, not the
per-cell FDR call), and CD4-CTL scored on its full cytotoxic panel with the activation
component regressed out.

## Setup & run — reproduce from scratch

### Requirements
A standard scanpy environment (CPU is fine for the steps below):
- Python 3.11
- `anndata==0.12` · `scanpy==1.11` · `numpy==2.3` · `scipy==1.15` · `pandas==2.2`
- `huggingface_hub` (the `hf` CLI) to fetch the embedded object — `pip install -U huggingface_hub`

### Two reproducibility tiers — know the boundary
1. **Embedding tier** (raw public data → `ntc_clustered.h5ad`): fetch the NTC CD4 cells
   from the CZI *"Primary Human CD4+ T Cell Perturb-seq"* dataset and run scVI + Leiden.
   This is **GPU-scale and large** — the full dataset is ~1.84 TB. Run **once**, cached as
   `ntc_clustered.h5ad` (18,130 genes × 396k cells, `obs['L0.8']` Leiden clusters). You do
   **not** need to re-run it: the embedded object is published (below).
2. **Nomenclature tier** (`ntc_clustered.h5ad` → labels → per-cell calls → overlay):
   deterministic, CPU, ~3 min, and **byte-reproducible** — this is what runs here.

### Fetch the embedded object
The embedded object (`ntc_clustered.h5ad`, 3.86 GB) + the UMAP positions template are
published (**public, MIT**) in the Hugging Face dataset
[**KiritSingh/spot-CD4-Marson**](https://huggingface.co/datasets/KiritSingh/spot-CD4-Marson)
— no account needed. `reproduce.sh` fetches both into `$SPOT_DATA` automatically, or pull
them manually:

```bash
export SPOT_DATA=./spot_scvi
hf download KiritSingh/spot-CD4-Marson ntc_clustered.h5ad stage01_umap_seed.json \
    --repo-type dataset --local-dir "$SPOT_DATA"
```

### Run the nomenclature tier
```bash
cd analysis
python cluster_scores.py           # per-cluster confound-aware z-scores -> $SPOT_DATA/cluster_scores.json
python label_clusters.py           # fixed rule                          -> $SPOT_DATA/cluster_labels.json
python stage1_pipeline.py          # per-cell scoring + emit stage01_umap_seed.emitted.json
python verify_reproduce.py         # asserts emitted counts == committed REFERENCE (100% match or exit 1)
```

Or just `./reproduce.sh`, which fetches the object (step above), runs the whole chain, and
re-renders the notebook. All paths are env-configurable via `SPOT_DATA`; no machine-specific
paths.

### Verified reproducible
A **blind clean-room run** — fresh working dir, only these scripts + the cached
`ntc_clustered.h5ad`, no cached intermediates — regenerates the labels, per-cell calls,
and overlay **byte-identical** to the committed reference (82.5% no-call, Th1 4550,
Treg 1051, CD4-CTL 573, …). The committed `app/data/` overlay is therefore a *reproducible
artifact*, not a hand-placed file.

## The pipeline (analysis/)
- `cluster_scores.py` → per-cluster panel z-scores (one 14 GB load).
- `label_clusters.py` → the fixed, confound-aware rule → `cluster_labels.json`
  (Cycling if proliferation clear; Treg = the one Treg-high, not-strongly-activated
  cluster; rest → Naïve/Memory if resting else Activated).
- `stage1_pipeline.py` → per-cell Masopust/Ahmed calls behind a 500-permutation FDR floor
  (`SEED=12345`); CD25/IL2RA dropped from Treg, CD4-CTL activation-conditioned; emits the
  overlay. Confound handling and the two validation checks are documented inline and
  rendered in `01_notebook.html`.
- `verify_reproduce.py` → the gate: emitted counts must equal the committed reference.

## Provenance
- `app/01_notebook.html` — every code cell + captured output (auto-rendered from
  `stage1_pipeline.py`).
- `app/01_trace.html` — the vcp data-provenance trace (independently re-verified end to
  end: fresh `vcp-cli` install + S3 range-read + gate re-run).
- `analysis/REVIEW_MEMO.md` — Claude Science scientific review + follow-up checks.

## Data source
Marson GWCD4i genome-scale CRISPRi perturb-seq (bioRxiv 2025.12.23.696273) — NTC CD4
cells, 4 donors × Rest/Stim8hr/Stim48hr — public on the CZI Virtual Cell Platform.
Nomenclature: Masopust/Ahmed, *Guidelines for T cell nomenclature*, Nat Rev Immunol
2026;26:298-313.
