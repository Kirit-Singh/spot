# inputs — 01_programs

No data is bundled here (repo policy: public data only). This stage's inputs are:

- **Cells:** the Marson GWCD4i genome-scale CD4 perturb-seq, **non-targeting-control (NTC)
  cells only** — public on the CZI Virtual Cell Platform, dataset *"Primary Human CD4+ T
  Cell Perturb-seq"* (namespace `billion-cell-project`; 12 per-donor × per-condition
  splits). Fetch with the `vcp` CLI (`pip install 'vcp-cli[data]'`); see
  `../analysis/reproduce.sh` step 1 and `../app/01_trace.html` for the exact resolution
  and provenance.
- **Embedded object:** `ntc_clustered.h5ad` — the NTC subset embedded with scVI + Leiden
  (the "embedding tier"; see the stage README). This is the starting point for the
  reproducible nomenclature chain and is *not* committed (14 GB). Point `SPOT_DATA` at the
  directory holding it.
- **Marker panels:** the differentiation + function panels (Masopust/Ahmed, Tables 1 & 3)
  live in the code (`../analysis/stage1_pipeline.py`), not as separate files.
