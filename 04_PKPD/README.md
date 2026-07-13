# 04_PKPD — brain penetrance, exposure, safety, synergy

**Status:** prospective design only. No Stage-4 PK, safety or clinical decision-support
result is admitted in the current release.

The planned stage organizes source-bound evidence for CNS delivery, exposure and safety.
**Proposed lock:** a brain-exposure evidence assessment, not proof of permeability or a
clinical safety determination.

Candidate fields include physicochemical descriptors, transporter evidence, measured
exposure and half-life. Any NEBPI-based implementation must cite and encode the exact
published method; candidate databases are not treated as current merely because they are
named in a design document.

The proposed safety lane would present evidence and unresolved conflicts against relevant
concomitants. It must not convert spontaneous-report signals or database labels into
"safe," incidence, causality or a hard contraindication.

- `inputs/`  — the locked drug(s) from 03
- `analysis/` — CS workbook: descriptor calc + DB queries
- `outputs/` — per-drug score card (NEBPI + exposure + half-life + safety traffic light)
