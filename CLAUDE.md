# CLAUDE.md

**spot** — a five-stage workbench that turns a T-cell transcriptional program into a
testable, brain-penetrant drug-repurposing hypothesis for glioblastoma:
`Treg program › skewing genes › drug › brain-penetrance/exposure › trial design`.
Each stage is a **Claude Science specialist** (a CS project with tailored agent-context
+ database access), embedded in its tab; spot is the funnel shell that carries the
locked artifact between stages. Design:
`docs/superpowers/specs/2026-07-08-spot-v2-gbm-repurposing-design.md`.

## Repo layout
Five stage folders, each `inputs/ outputs/ analysis/ + README`:
- `01_phenotypes/` — CD4 programs → interactive UMAP (single-cell immunology)
- `02_geneskew/` — genes that skew toward/away a program + GO (perturbation genomics)
- `03_druglink/` — genes → immune-perturbing drugs via target→drug + LINCS (drug repurposing)
- `04_PKPD/` — brain-penetrance (CNS-MPO/NEBPI) + exposure + safety + synergy (neuro-onc)
- `05_trial/` — trial-design synopsis (v1 placeholder; clinical decision-support)

`_frontend/` the 5-tab shell (React+Vite+TS+Tailwind). `_requirements/` repo envs.
`CLAUDE.md LICENSE README.md` at root. `outputs/` is gitignored (generated artifacts).

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
- **Never invent a statistic** — every number comes from a real tool/DB (scanpy / DESeq2
  / DepMap / LINCS / ChEMBL) with provenance (source + method + exact stat).
- **Firewall:** predictive / druggable / brain-penetrance signals may *suggest* but never
  *confirm* — keep them flagged as suggestive.
- **Adversarially falsify** before trusting — cross-condition/donor/guide reproducibility
  (the robustness composite).
- **Public data only**; nothing bundled in the repo.
- **Honest boundaries:** spot is decision-support — not a trial designer, a PK/tox oracle,
  or a substitute for clinical/regulatory/safety expertise. BBB scoring is a screen, not
  proof of CNS exposure. One in-vitro CD4 dataset needs cross-confirmation.

## Claude Science specialists
Each stage = one CS project with tailored agent-context (domain + permitted databases /
skills). CS calls DBs where possible; heavy compute → tcefold via SSH. The paper is the
*reference*, CS *complements* it (tag genes 'paper' vs 'CS-complement'). Each specialist
writes its locked artifact + provenance to the stage `outputs/`.

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
