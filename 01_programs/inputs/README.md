# inputs — 01_programs

No data is bundled here (repo policy: public data only). This stage's inputs are:

- **Cells (original source):** the Marson GWCD4i genome-scale CD4 perturb-seq,
  **non-targeting-control (NTC) cells only** — public on the CZI Virtual Cells Platform,
  dataset *"Primary Human CD4+ T Cell Perturb-seq"* (namespace `billion-cell-project`; 12
  per-donor × per-condition splits). The VCP path documents where the cells *come from*
  (see `../app/01_trace.html` for the resolution + one-split range-read). **Reproduction
  does not go through VCP** — it fetches the pinned embedded object from Hugging Face.
- **Embedded object (what reproduction fetches):** `ntc_clustered.h5ad` — the NTC subset
  embedded with scVI + Leiden (the "embedding tier"; see the stage README). `reproduce.sh`
  fetches it from Hugging Face at the pinned revision and verifies its SHA-256; it is *not*
  committed to the repo (**~3.84 GB**). Point `SPOT_DATA` at the directory holding it.
- **Marker panels:** the differentiation + function panels live in the code
  (`../analysis/stage1_pipeline.py`), not as separate files. They are **separately curated + cited**
  (per-marker primary provenance in the v3 registry `marker_provenance`); Masopust et al. is a
  **naming framework only**, never the panel source.
