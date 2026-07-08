# 02_geneskew — genes that skew toward / away from a program

Rank gene knockdowns by how much they push cells toward/away from a program
(v1: knockdowns that **reduce** the Treg module), robustness-scored, with GO
enrichment. **Locks:** the gene / program of interest.

Runs as a Claude Science **specialist** (project `spot · 02 geneskew`): perturbation
genomics — the reproducibility composite (cross-condition/donor/guide, clean).

- `inputs/`  — the locked program from 01; Marson DE_stats / pseudobulk
- `analysis/` — CS workbook: lever ranking + GO
- `outputs/` — ranked lever gene set + program-skewing heatmap + GO terms
