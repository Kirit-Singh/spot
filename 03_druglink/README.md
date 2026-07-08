# 03_druglink — link immune-program genes to drugs

Find drugs that **perturb the immune program** — reduce the locked Treg module.
Brain-penetrance + exposure are the filter (Stage 04), so this stage does NOT require
glioma-cell activity. **Locks:** the drug.

Runs as a Claude Science **specialist** (project `spot · 03 druglink`): drug-repurposing —
**target → drug** (DGIdb / Open Targets / ChEMBL) + **LINCS** signature mimicry of
"Treg-down" (rank ↑ when both agree). DepMap/CCLE/PRISM glioma-selectivity is deferred as
a later dual-mechanism bonus, never a filter.

- `inputs/`  — the locked gene set from 02
- `analysis/` — CS workbook: target→drug + LINCS queries
- `outputs/` — ranked candidate drugs (immune-perturbation) + provenance
