# 01_phenotypes — CD4 transcriptional programs (UMAP)

Score CD4 cells into modular transcriptional programs (Treg, Th1, …) and render an
interactive phenotype UMAP. **Locks:** the selected program (v1: Treg).

Runs as a Claude Science **specialist** (project `spot · 01 phenotypes`): single-cell
immunology — scanpy `score_genes`, paper-anchored to the T-cell nomenclature
guidelines (Masopust 2026, Tables 1/3/5) and complemented on-data.

- `inputs/`  — Marson CD4 Perturb-seq (cell-level h5ad on the NAS); marker tables
- `analysis/` — the CS workbook: module signatures + provenance, UMAP embedding
- `outputs/` — per-cell module scores, UMAP coords (portable table), Treg reality-check
