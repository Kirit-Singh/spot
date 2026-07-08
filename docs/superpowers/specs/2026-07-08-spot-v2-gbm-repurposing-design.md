# spot v2 — GBM Immune-Repurposing Workbench — Design

**Date:** 2026-07-08 · **Status:** design (fuller reset; supersedes 2026-07-07-spot-design.md)

## Goal
Re-orient spot from a general cross-dataset evidence graph into a focused, staged
**workbench that turns a CD4 T-cell transcriptional program into a testable GBM
drug-repurposing hypothesis**, end to end. v1 target: **reduce the Treg program**
(release immunosuppression) in **glioblastoma (GBM)**.

## The pivot
Replace the typed-edge *evidence graph* spine with a **5-stage selection funnel**
and a **progressive locking header**:

`TReg › Program / genes of interest › Drug › Brain-penetrance / exposure › Trial design`

Each stage locks a choice that feeds the next; the header breadcrumb builds as the
user advances. The frontend is redone as **5 tabs**, one per stage.

## Scope — fuller reset (kept vs rebuilt)
**Rebuilt:** frontend (Cytoscape graph → 5-tab funnel); data model (typed-edge
contract → staged-selection funnel of locked artifacts).
**Kept, re-oriented to feed the tabs:** ingest pipeline (`pipeline/`) + the
downloaded Marson data; robustness scoring (`spot_pipeline.qc` + CS composite) for
stage-2 gene ranking; the Claude Science analyses (phenotyping, robustness); the
provenance discipline + the "predictive/druggable can *suggest* but never
*confirm*" firewall.

## Stages
### 1 — CD4 programs (tab: UMAP)
- **Method:** marker-module scoring, **paper-anchored + CS-complemented**. Modules
  from the T-cell nomenclature guidelines (Masopust 2026, Tables 1/3/5):
  TH1/2/9/17 / Tfh / **Treg** (tTreg/pTreg/eTreg) / CD4-CTL x differentiation
  (Naive/Activated/Effector/Memory/Exhausted). scanpy `score_genes` per cell;
  markers->genes with a provenance dict; CS flags where the paper is insufficient
  and adds genes (tagged 'paper' vs 'CS-complement').
- **Output:** per-cell module scores + a 2D **UMAP embedding** (portable table:
  umap_x/y, module scores, donor, condition) -> the interactive UMAP.
- **Reality gate:** does this in-vitro CD4 screen have a Treg compartment large
  enough to trust? (CS phenotyping answers this; if too sparse, confirm against an
  external tumor-Treg dataset before trusting stage 2.)

### 2 — Skewing genes (tab: heatmap + GO)
- **Method:** rank knockdowns by how much they **reduce the Treg module**
  (favorable = down-Treg), using the robustness composite so levers are
  reproducible (cross-condition/donor/guide, clean). GO enrichment on the levers.
- **Output:** a ranked, robustness-scored **lever gene set** + program-skewing
  heatmap + GO terms. The locked "genes/program of interest."

### 3 — Drug link (tab: drug matrix)
- **Method — DepMap/CCLE glioma-selective + LINCS cross-check:**
  - Glioma-selective **expression** diff (glioma CCLE vs other, t-test) [Ghandi 2019]
  - Glioma-selective **dependency** — DEMETER2 combined RNAi (Broad/Novartis/
    Marcotte), glioma vs other (t-test) [McFarland 2018]
  - **Drug sensitivity** — PRISM Repurposing Primary Screen 19Q4: glioma-line
    viability (log FC vs DMSO), Pearson -> drug-drug sensitivity matrix [Corsello 2020]
  - **LINCS mimicry** (cross-validation): drugs whose L1000 signature reproduces
    "Treg-down"; rank higher when a drug appears in both.
- **The bridge (design decision + refine-point):** the target comes from the
  *immune* analysis (Treg silencers in CD4); DepMap/PRISM supplies *glioma-context*
  druggability + a direct anti-glioma bonus if the drug also hits glioma cells.
  Primary mechanism = immune (Treg reduction in the TME); direct anti-tumor
  activity is additive. OPEN: how strictly to require glioma-cell dependency for an
  immune target.
- **Output:** ranked **candidate drugs** with mimicry-union-target provenance.

### 4 — PK/PD + brain penetrance (tab)
- **Method — Grossman/ABTC-FDA neuro-oncology framework (Neuro-Oncology 2026):**
  - Physicochemical **CNS-MPO** (Wager) from 6 RDKit descriptors: ClogP, ClogD(7.4),
    TPSA, MW, HBD, pKa; plus **P-gp/BCRP efflux liability**. Target =
    non-enhancing-brain (NEB) permeability, not just enhancing tumor.
  - **Delivery-Potency-Efficacy:** combine penetrance with potency (IC50/IC90 vs
    required unbound tumor conc) — high potency can offset low penetrance.
  - **NEBPI** 3-category output: sufficiently / insufficiently / impermeable.
  - **Exposure & half-life** from ChEMBL/DrugBank/labels.
- **Safety & synergism:** FAERS/SIDER/DrugBank (adverse events, contraindications,
  black-box) + DrugComb + synergy with GBM standard of care (temozolomide/RT/
  checkpoint).
- **Output:** per-drug NEBPI + exposure + half-life + safety + synergy score card.

### 5 — Trial design (tab)
- **Method:** synthesize a **trial-rationale synopsis** — setting (adjuvant vs
  neoadjuvant), population (newly-diagnosed vs recurrent; MGMT status), dosing (from
  PK/PD), endpoints with **Treg-program reduction as the PD biomarker**, +
  precedents from ClinicalTrials.gov. OPEN: adjuvant-vs-neoadjuvant logic depth.
- **Honest boundary:** a decision-support synopsis for clinical/regulatory/safety
  experts — NOT an actual trial design. No autonomous trial generation.

## Frontend
5 tabs (one per stage) + progressive header breadcrumb that fills as each stage
locks. Carry the existing light palette/tokens. Tab1 interactive UMAP; tab2
heatmap+GO; tab3 drug-drug sensitivity matrix; tab4 drug score cards; tab5 trial
synopsis. A tab reads the locked artifact from the prior stage; nothing downstream
unlocks until the prior stage is locked.

## Data model — staged selection funnel
Replace the typed-edge evidence graph with a linear funnel of locked artifacts:
`ProgramSelection -> GeneLeverSet -> DrugCandidateSet -> DrugScoreCard -> TrialSynopsis`
Each carries provenance (source, method, exact stat) + a firewall flag
(predictive/druggable/penetrance = suggestive, never confirmatory). Persisted so a
run is reproducible + shareable.

## Honest boundaries
- One in-vitro CD4 dataset defines the program — disease/location-agnostic; hits
  need cross-dataset confirmation before trust (esp. sparse Tregs).
- BBB screening != PK/tox truth — CNS-MPO/NEBPI is a *prioritization* screen (the
  paper is explicit there is no formal "brain-permeable" definition); real PK/tox/
  IND work is downstream and human.
- Trial = decision-support, not an autonomous designer.

## Non-goals (YAGNI, v1)
Pluggable multi-indication (GBM only; clean seams for later); de-novo program
discovery (marker backbone now, data-driven factorization later as validation);
actual PK simulation / tox prediction (score with published descriptors, do not
simulate).

## Open items to refine
1. Stage-3 bridge: strictness of glioma-cell dependency for an immune target.
2. Stage-5 trial-design depth (adjuvant vs neoadjuvant).
3. Home for safety/synergy (stage-4 sub-panel vs own view).

## Data sources
Marson CD4 Perturb-seq; T-cell nomenclature (Masopust 2026); DepMap/CCLE
(expression, DEMETER2, PRISM 19Q4); LINCS L1000; ChEMBL/DrugBank/FAERS/SIDER/
DrugComb; ClinicalTrials.gov; brain-penetrance per Grossman et al., Neuro-Oncology
2026 (NEBPI/CNS-MPO). Public only.

## Architecture — Claude Science specialists per tab (added 2026-07-08)
Each stage runs as a dedicated **Claude Science specialist**: a CS project with a
tailored agent-context (domain expertise + permitted databases/skills), embedded in
that tab's frame. CS calls the databases (DepMap/LINCS/ChEMBL/FAERS/DrugComb/
ClinicalTrials.gov) where possible; spot is the funnel shell that carries the locked
artifact between specialists and renders their outputs. If CS cannot be iframed
(login / X-Frame-Options), fallback: the specialist writes its artifact to the
stage's `outputs/`, and the tab renders that + an "open in CS" link.

Specialists (one per stage folder): 01 single-cell immunology · 02 perturbation
genomics · 03 cancer pharmacogenomics · 04 neuro-oncology PK/PD · 05 clinical-trial
decision-support.

## Repo layout (v2)
`01_phenotypes/ 02_geneskew/ 03_druglink/ 04_PKPD/ 05_trial/` — each with
`inputs/ outputs/ analysis/ + README.md`. `_frontend/` (tab shell). `_requirements/`
(repo environments). `CLAUDE.md`, `LICENSE`, `README.md` at root. Old evidence-graph
code (api/contracts/core/pipeline) removed — recoverable via git history if a stage
needs it.

## Compute (added 2026-07-08)
Claude Science runs on tcedirector and SSHes into **tcefold** for heavy per-stage jobs
(more cores/RAM, GPU/AVX2) — this relieves the tcedirector ceiling (~31 GB RAM, slow
NAS reads) that bottlenecks cell-level phenotyping. NAS (`/mnt/tcenas/datasets`) is
shared by both hosts but slow; iterative work copies/subsamples to local disk.
