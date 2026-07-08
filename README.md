# spot

**spot** turns a T-cell transcriptional program into a testable, brain-penetrant
drug-repurposing hypothesis for glioblastoma — a five-stage workbench you walk end
to end:

`Treg program › skewing genes › drug › brain-penetrance & exposure › trial design`

Each stage locks a choice that feeds the next; the header breadcrumb builds as you go.

**Status:** re-orienting (WIP) · **MIT** licensed

## The five stages
1. **CD4 programs (UMAP)** — score CD4 cells into transcriptional programs (Treg,
   Th1, …) from the Marson Perturb-seq screen, anchored on the T-cell nomenclature
   guidelines and complemented by on-data analysis. Interactive phenotype UMAP.
2. **Skewing genes (heatmap + GO)** — the reproducible gene levers that push cells
   toward/away from a program (v1: knockdowns that *reduce* the Treg program),
   robustness-scored, with GO enrichment.
3. **Drug link** — find drugs that perturb the immune program (reduce the Treg module)
   via target→drug (DGIdb/Open Targets/ChEMBL) + LINCS signature mimicry. (Glioma-cell
   dependency deferred; brain-penetrance/exposure is the filter, next stage.)
4. **PK/PD & brain penetrance** — CNS-MPO / NEBPI (ABTC–FDA neuro-oncology framework)
   + exposure + half-life, plus a **safety/synergy traffic light** vs GBM standard of
   care (TMZ/XRT/dexamethasone/Keppra) and peri-operative bleeding (green/amber/red).
5. **Trial design** — light placeholder for v1 (decision-support synopsis; to refine).

## What it is / isn't
spot is **decision-support** — it prioritizes hypotheses and shows its provenance
at every step. It is **not** a trial designer, a PK/tox oracle, or a substitute for
clinical, regulatory, and safety expertise. Brain-penetrance scoring is a *screen*,
not proof of CNS exposure.

## Design
Full design in `docs/superpowers/specs/2026-07-08-spot-v2-gbm-repurposing-design.md`.
Conventions in `CLAUDE.md`.

## Data
Public datasets only — Marson CD4 Perturb-seq, DepMap/CCLE (expression, DEMETER2,
PRISM), LINCS, Open Targets/ChEMBL/DrugBank. No data bundled in this repo.

## License
Code: **MIT** (`LICENSE`). Third-party data & reference sources: **`DATA_LICENSES.md`**.
