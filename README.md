# spot

**spot** turns a T-cell transcriptional program into a testable, brain-penetrant
drug-repurposing hypothesis for glioblastoma — a five-stage workbench you walk end
to end:

`Treg program › skewing genes › drug › brain-penetrance & exposure › trial design`

Each stage locks a choice that feeds the next; the header breadcrumb builds as you go.

**Release status:** Stage 1 implemented · Stage-2 code preliminary and unreleased ·
Stages 3–5 prospective · **MIT** licensed

## The five stages
1. **CD4 programs (UMAP)** — score CD4 cells into **continuous transcriptional-program
   compatibility scores** (Treg-**like**, Th1-**like**, …) from the Marson Perturb-seq NTC
   cells, scored against curated canonical-marker panels named per the T-cell
   nomenclature guidelines. **Exploratory — not
   cell-type calls; RNA compatibility ≠ lineage/protein/function** (see
   `01_programs/REMEDIATION_STATEMENT.md`). Interactive score UMAP.
2. **Skewing genes (preliminary code; no released result)** — project measured
   perturbation effects onto an ordered pair of Stage-1 program axes and keep the two
   effect arms explicit. Direct, temporal and pathway analyses must pass their own
   release contracts before any Stage-2 output is called current.
3. **Drug link (prospective)** — link admitted gene/pathway hypotheses to versioned,
   licensed target–drug evidence. No Stage-3 result or database extract is part of the
   current release.
4. **PK/PD & brain penetrance (prospective)** — evaluate brain exposure and safety from
   separately admitted, source-bound evidence. No Stage-4 result is current.
5. **Trial design (prospective)** — decision-support synopsis; not implemented or a
   clinical recommendation.

## What it is / isn't
spot is **decision-support** — it prioritizes hypotheses and shows its provenance
at every step. It is **not** a trial designer, a PK/tox oracle, or a substitute for
clinical, regulatory, and safety expertise. Brain-penetrance scoring is a *screen*,
not proof of CNS exposure.

## Design
Full design in `docs/superpowers/specs/2026-07-08-spot-v2-gbm-repurposing-design.md`.
Conventions in `CLAUDE.md`.

## Data
The current scientific release is derived from the public Marson GWCD4i CD4
Perturb-seq dataset. Sources mentioned for later stages are design candidates, not
automatically licensed, admitted, queried, or bundled. The public Hugging Face state is
recorded in `release/public_external_artifacts.json`; tracked legacy display artifacts
and their exact sizes/hashes are recorded in
`release/legacy_large_file_exceptions.json`. No hand-maintained aggregate-size claim is
used here.

## License
Code: **MIT** (`LICENSE`). Third-party data & reference sources: **`DATA_LICENSES.md`**.
