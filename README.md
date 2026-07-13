# spot

**spot** is a five-stage workbench for drug-repurposing hypotheses in glioblastoma. You
pick a transcriptional-program contrast in CD4 T cells, find the gene levers that move it,
annotate drugs that act in the compatible direction, and screen those drugs for brain
exposure and safety. Each stage locks a typed, content-addressed artifact that the next
stage reads.

```
program contrast  ›  gene levers  ›  direction-compatible drugs  ›  brain PK / safety  ›  trial synopsis
```

The program contrast is **generic**: any two continuous CD4 program scores in either
direction (e.g. Treg-like → Th1-like is only a labelled demo default). There is no fixed
biological axis and no confirmed cell identity anywhere in the contract.

**Status:** work in progress · **MIT** licensed.

## The five stages
1. **CD4 programs** (`01_programs/`) — continuous per-cell transcriptional-program scores
   over the Marson CD4 perturb-seq NTC cells; a generic selector emits
   `spot.stage01_selection.v3` for any (program A, direction A, program B, direction B,
   condition/mode). Exploratory — continuous scores, **not** cell-type calls.
2. **Gene skew** (`02_geneskew/`) — ranks gene knockdowns by their measured effect on the
   Stage-1 contrast, keeping **Direct, temporal, and pathway** origins typed and separate;
   robustness-gated. Output is a *suggestive* lever hypothesis needing external validation.
3. **Drug link** (`03_druglink/`) — maps verified Stage-2 levers/pathway nodes to
   **direction-compatible** drug annotations (target → drug over ChEMBL / UniProt / Open
   Targets). Direction-aware annotation, no ranking claim.
4. **PK/PD & brain penetrance** (`04_PKPD/`) — scores each drug for CNS delivery (CNS-MPO /
   NEBPI), exposure, and safety as **separate evidence lanes** — no composite score,
   ranking, or recommendation.
5. **Trial design** (`05_trial/`) — a v1 placeholder decision-support synopsis.

## Public inputs
Public data only; no third-party source matrices are bundled. The small **derived display
artifacts** the Stage-1 workbench renders are tracked (`01_programs/app/data/`). The full
Stage-1 source table is published on Hugging Face (`KiritSingh/spot-CD4-Marson`, MIT). Every
queried source and its license is recorded in `DATA_LICENSES.md`.

## Outputs
Each stage writes one typed, content-addressed artifact plus its provenance. The cross-stage
contracts and their verifiers are defined in `schemas/README.md`; each stage README names its
own current schema and entry point.

## Reproduce
Stage-1 scoring tier (deterministic, per-barcode reproducible):
```bash
cd 01_programs/analysis && ./reproduce.sh   # pins the HF revision + SHA, then per-barcode verify
```
Stage-2 runs from `02_geneskew/analysis/` (`direct/run_screen.py`, `perturb2state/run_p2s.py`)
as a Claude Science specialist over the authors' released `GWCD4i.DE_stats`. Stages 3–4 are
specified but not yet implemented in this repo. See each stage README for the exact entry point.

## Provenance
Every number comes from a real tool or database with source + method + exact statistic —
none are invented. Predictive, druggable, and brain-penetrance signals are kept **suggestive**,
never confirmatory. The adversarial-falsification and remediation record is preserved under
`docs/history/`.

## Limitations
spot is **decision-support**, not a trial designer, a PK/tox oracle, or a substitute for
clinical, regulatory, and safety expertise. RNA program-compatibility does not demonstrate
lineage, protein expression, or function. Brain-penetrance scoring is a *screen*, not proof
of CNS exposure. Stage 1 rests on one in-vitro CD4 dataset that needs cross-confirmation.

## License
Code: **MIT** (`LICENSE`). Third-party data & reference sources: **`DATA_LICENSES.md`**.
Design: `docs/superpowers/specs/2026-07-08-spot-v2-gbm-repurposing-design.md`; conventions: `CLAUDE.md`.
