# 03_druglink — link immune-program genes to drugs

**Status:** prospective design only. No Stage-3 database acquisition, ranked drug result,
or production output is admitted in the current release.

The planned stage links an admitted Stage-2 gene/pathway hypothesis to drugs with explicit
direction, identity, version, license and evidence provenance. Brain penetrance and exposure
remain separate Stage-4 questions. **Proposed lock:** a drug hypothesis, only after its
contract and sources pass release verification.

DGIdb, Open Targets, ChEMBL, LINCS and disease-context resources are candidate sources,
not current bundled data. Each requires source-specific admission and a pinned release;
mention here is not a license or evidence claim.

- `inputs/`  — the locked gene set from 02
- `analysis/` — CS workbook: target→drug + LINCS queries
- `outputs/` — ranked candidate drugs (immune-perturbation) + provenance
