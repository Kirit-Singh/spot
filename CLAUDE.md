# CLAUDE.md

**spot** — a public-data decision-support workbench connecting continuous CD4
transcriptional programs to perturbation targets, pathways, drug links, and PK/safety
evidence. Four stages are implemented across five pages; Stage 5 remains an unimplemented
placeholder. Claude Code / Claude Science sessions are part of the development workflow,
not agents embedded in the deployed static app.

## Repo layout
Stage folders and the shared frontend:
- `01_programs/` — CD4 programs → interactive UMAP (single-cell immunology)
- `02_geneskew/` — genes that skew toward/away a program + GO (perturbation genomics)
- `03_druglink/` — genes → public target-to-drug evidence
- `04_PKPD/` — separate PK, CNS-exposure and safety evidence lanes
- `05_trial/` — unimplemented placeholder

`_frontend/` is the five-page UI (React+Vite+TS+Tailwind). `_requirements/` contains
repo environments. Generated analytical outputs remain outside Git unless deliberately
packaged as a bounded, licensed display artifact.

## Compute
- **Claude Science** runs on **tcedirector** (dev host) and is the per-stage analytical
  engine. It **SSHes into `tcefold`** for heavy jobs — more cores/RAM + GPU/AVX2 — when a
  stage outgrows tcedirector (e.g. loading cell-level h5ad past ~31 GB RAM, GPU UMAP).
- The **NAS** (`/mnt/tcenas/datasets`, NFS, shared by both hosts) is slow (~35 MB/s,
  seek-bound) — copy/subsample to local disk for iterative work; never depend on a live
  NFS stream. Big processed files live local on tcedirector (`~/datasets/…`); raw
  cell-level on the NAS.
- The Mac is a thin SSH client.

## Data rules
- **Never invent a statistic** — every number comes from a real tool or registered public
  source with provenance (source + method + exact value/statistic).
- **Firewall:** predictive / druggable / brain-penetrance signals may *suggest* but never
  *confirm* — keep them flagged as suggestive.
- **Adversarially falsify** before trusting — cross-condition/donor/guide reproducibility
  (the robustness composite).
- **Public data only**; raw source matrices/responses are not bundled. The repo does track a
  bounded set of derived display artifacts under the source-specific terms in
  `DATA_LICENSES.md`.
- **Honest boundaries:** spot is decision-support — not a trial designer, a PK/tox oracle,
  or a substitute for clinical/regulatory/safety expertise. BBB scoring is a screen, not
  proof of CNS exposure. One in vitro CD4 dataset needs cross-confirmation.

## Analytical development workflow
Claude Science projects may be used as domain-specific development workers with permitted
public databases and tcefold compute. Their output is never itself a scientific source:
every claim must resolve to a public locator or a reproducible calculation and pass an
independent verification gate before it can enter a release artifact.

**Working method (token-efficient):** delegate the actual analytical work — data
reads, DB calls, computation — to the CS specialists (their tokens are separate); the
orchestrating session coordinates the frontend, provenance and independent review. Keep the
orchestrating context lean.

## Engineering conventions
- Small modules, one purpose each; **≤500 lines/file**.
- **Tests** on deterministic logic (scoring, verdicts, parsers, gene-ID/ontology
  harmonization); thin IO/glue smoke-or-skip; every bugfix ships a regression test.
- **Efficiency:** vectorize (no Python loops over cells/genes); subsample/stream — never
  hold a full cohort in memory (slow NAS + tight RAM).
- **Small chunk by small chunk:** each with a clear success metric, green before commit.
- **generator ≠ evaluator:** an independent verify gate on every change + every claim.
- **Env:** `_frontend` deps via `package-lock.json`; repo envs pinned in `_requirements/`;
  CS manages its own conda envs per specialist.

## File & folder hygiene
- **Minimal files** — add only when working code requires it, never speculatively.
- **Simple, clean folders** — flat + obvious; avoid deep nesting / one-file folders.
- **Explain before reorganizing** — say what and why first, get a nod; never silent.
