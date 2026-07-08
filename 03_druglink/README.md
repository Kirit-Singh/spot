# 03_druglink — link genes to drugs

Connect the locked genes to compounds. **Locks:** the drug.

Runs as a Claude Science **specialist** (project `spot · 03 druglink`): cancer
pharmacogenomics — DepMap/CCLE glioma-selective **expression** + **DEMETER2**
dependency + **PRISM 19Q4** drug sensitivity (drug-drug matrix), cross-checked
against **LINCS** signature mimicry (rank ↑ when a drug appears in both).

- `inputs/`  — the locked gene set from 02
- `analysis/` — CS workbook: DepMap/PRISM/LINCS queries + matrix
- `outputs/` — ranked candidate drugs (mimicry ∪ target) + provenance
