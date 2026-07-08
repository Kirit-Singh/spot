# 04_PKPD — brain penetrance, exposure, safety, synergy

Score each drug for CNS delivery + druggability. **Locks:** the brain-penetrance /
exposure score.

Runs as a Claude Science **specialist** (project `spot · 04 PKPD`): neuro-oncology
PK/PD — **CNS-MPO / NEBPI** (Grossman et al., Neuro-Oncology 2026): ClogP, ClogD,
TPSA, MW, HBD, pKa + P-gp/BCRP efflux, potency-adjusted → sufficiently /
insufficiently / impermeable. Exposure + half-life (ChEMBL/DrugBank). Safety
(FAERS/SIDER) + synergy (DrugComb + GBM standard-of-care).

- `inputs/`  — the locked drug(s) from 03
- `analysis/` — CS workbook: descriptor calc + DB queries
- `outputs/` — per-drug score card (NEBPI + exposure + half-life + safety + synergy)
