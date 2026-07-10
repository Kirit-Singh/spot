# spot Stage-2 addendum — perturbations for DEFINING states, and the GBM tumor-context cross-reference

_Design memo, companion to `STAGE2_PLAN.md`. No heavy compute. Two extensions:
(A) using the ~3,341-knockdown screen to help **define** the states/programs, not
only to score skew against a pre-defined axis; (B) the glioma-resource map for
druggable-target discovery — what's reachable via a CS connector vs a network grant
vs local NAS, and the concrete cross-reference logic + funnel placement._

_Catalog / access facts this memo is grounded on (checked this session):_
- _Only `marson2025_gwcd4_perturbseq` + `spot_scvi` are mounted under `/mnt/tcenas`. **The GBM NAS datasets are not currently granted** — a `request_host_access` to the GBM NAS path is prerequisite to the "load from NAS" column below._
- _Connectors present: cBioPortal (`mcp-cancer-models`), Open Targets/CIViC/ClinGen (`mcp-clinical-genomics`), ChEMBL (`mcp-chembl`), PubChem/BindingDB/ChEBI (`mcp-chemistry`), HPA/STRING/InterPro (`mcp-protein-annotation`), GTEx (`mcp-expression`), ClinicalTrials.gov (`mcp-clinical-trials`), BioMart (`mcp-biomart`), MyGene/Reactome (`mcp-genes-ontologies`), OpenAlex/bioRxiv (`mcp-literature`/`mcp-biorxiv`), ENCODE/JASPAR (`mcp-regulation`), GWAS/eQTL (`mcp-human-genetics`)._
- _**No DepMap connector exists** (confirmed by search) — DepMap needs a network grant. CELLxGENE and GEO are on the sandbox allowlist; Synapse / Broad Single Cell Portal / cgga.org.cn / glioblastoma.alleninstitute.org / depmap.org are not (need grants)._

---

## PART A — Letting perturbations DEFINE the states, not just score skew

### A.0 The distinction that makes this worth doing

NTC-only clustering (Stage-1) defines states by **co-expression covariance in
unperturbed cells** — what varies together across the natural population. The screen
offers a second, independent notion: **causal/regulatory covariance** — what changes
together when you push the system. These are not the same object, and the second sees
things the first structurally cannot:

- Co-expression can be driven by a shared upstream driver, cell cycle, ambient RNA, or
  batch — genes that *travel together* without being *co-regulated*. Perturbation
  response separates co-expressed-but-independently-regulated modules from genuinely
  co-controlled ones.
- The arbiter of a **state boundary** can become regulatory coherence: two NTC clusters
  that respond identically to the same regulators arguably form one regulatory state;
  one NTC program that splits under perturbation into two independently-controlled
  halves is two modules. This is the deepest "define states" contribution — using
  causality to adjudicate boundaries co-expression drew.

So the value is real, but it is bounded by two facts about *this* screen (both carried
from `STAGE2_PLAN.md` R1/R4): `DE_stats` is **whole-condition pseudobulk** (the
perturbation response is the bulk activated response, not the induced-Treg subset), and
the substrate is a **Th0 polyclonal** context where ~82% of NTC cells make no functional
call. Both cap the power, and both decide where the perturbation-defined view helps vs
where it is circular or underpowered.

### A.1 Perturbation covariance → data-driven gene modules

**Method.** Form the perturbation × gene response matrix from `DE_stats` (rows =
perturbations, columns = 10,282 genes, values = z-scores). Two clusterings:
- **Gene modules** = cluster genes by how they co-respond *across perturbations*
  (correlate columns). Genes that move coherently under many different KDs are
  causally coupled — a regulatory module, not merely a co-expression module. (This is
  the standard genome-scale Perturb-seq construction — correlating perturbation-response
  profiles to recover modules — the Replogle-style analysis.)
- **Perturbation modules** = cluster the KDs by effect similarity → groups of regulators
  with shared downstream consequence. (The Marson paper's *own* clustering is of the
  3,341 perturbations — Stage-1's notebook already noted the paper defines no cell-state
  taxonomy, only a perturbation one. Reusing/reconciling with that clustering is a free
  external cross-check.)

**Where it genuinely improves on NTC-only.** It nominates the *regulators* that maintain
each module — for our question, find the module containing FOXP3/CTLA4/CCR8 and read off
which KDs perturb it coherently. That is a mechanistic, causal anchor a co-expression
program cannot provide. Registered as `method="perturbation_covariance"` programs in
`stage02_programs.json`, these sit alongside the NTC-NMF and marker-anchor programs and
give the axis a regulator-anchored interpretation.

**Where circular / underpowered.**
- **Circular** if the same perturbations both define a module and are then ranked against
  it. Discovery and scoring must be separated (define modules → score on independent
  footing, or hold out perturbations/donors).
- **Underpowered** because the matrix is whole-condition pseudobulk: modules recovered
  are **activation-response modules**, dominated by the majority population; an
  induced-Treg-specific module is swamped unless built from **cell-state-resolved DE**
  (the expensive path). And the matrix is sparse/noisy — many KDs have no on-target
  effect (A1BG) or ~zero trans-effects — so build modules on the **powered subset**
  (`ontarget_significant`, meaningful `n_downstream`) and on hit genes, not the full
  3,341 × 10,282.

### A.2 Defining axis ENDPOINTS by perturbation

**Idea.** Instead of poles set by marker panels, define the induced-Treg pole as "where
FOXP3-KD moves you *away from*" and the Th1 pole by the inflammatory regulators' KD
effects — a **functional/causal** endpoint (the state is what removing its master
regulator dismantles).

**Where it improves.** A causal endpoint is a stronger claim than a static marker list:
FOXP3-KD's transcriptomic consequence *is* the operational definition of "loss of the
induced-Treg program." When it agrees with the marker/NTC axis, that agreement is
real corroboration from an independent modality.

**Where circular — the sharpest risk in this memo.** If you *define* the axis as the
direction of FOXP3-KD's effect and then *rank* FOXP3-KD as your top hit, that is
trivially circular; more subtly, any KD resembling the anchor set wins by construction.
**Do not define the axis geometry from the perturbations you will score.** The clean
design: keep the axis geometry from the **NTC state contrast** (independent data,
`STAGE2_PLAN.md` §1.2), and use a **small, pre-specified set of master-regulator
anchors** (FOXP3 for the Treg pole; TBX21/STAT1 for the Th1 pole) only to **orient and
validate** the axis sign — which is exactly the FOXP3-KD-positive positive control
already in `STAGE2_PLAN.md` §2.6, now stated as a definition-level guardrail rather than
a definition. If a fully perturbation-defined endpoint is wanted, it must be
cross-validated (endpoints from one donor/perturbation split, scoring on the other).

**Where underpowered.** In a Th0 context most KDs are null, so the count of KDs that
actually move cells between induced-Treg and Th1 is small — endpoints defined by a
handful of regulators are high-variance. Perturbation-defined endpoints are therefore
best as **anchors that must agree with the NTC axis**, not a standalone geometry.

### A.3 Testing whether the Stage-1 clusters are perturbation-COHERENT

**This is the most defensible and least circular use, and it targets the review's
biggest open question — what the "Treg" cluster *is*.** A real regulatory state should
be perturbation-coherent: knocking down its master regulator should selectively move
*that* cluster, and the KDs that shift its program should form a coherent group. Test:
does FOXP3 (and IL2–STAT5 / TGFβ-SMAD) KD selectively deplete/shift the induced-Treg
cluster at the cell level? If a specific regulator KD selectively collapses it, it is a
real regulatory state; if no specific KD selectively moves it and only broad activation
KDs do, it is closer to an activation-timepoint compartment. This uses an orthogonal
axis (causal perturbation) to test a definition made from independent data (NTC
co-expression) — no circularity.

**Where underpowered.** It needs **cell-state-resolved, per-KD composition** (the
expensive cell-level load, `STAGE2_PLAN.md` §2.7), and per-(KD × cluster × condition)
cell counts get thin fast for a 6.3% cluster across 3,341 KDs. So cluster-coherence
testing is powered for the **master-regulator anchors and abundant perturbations**, not
screen-wide. Report the anchors explicitly; declare "insufficient power" for the rest.

### A.4 Net recommendation for Part A (folds into `define_programs.py`)

Add a **three-tier** perturbation-informed layer to program definition, each tier on its
correct footing:
1. **Discovery** — perturbation-covariance gene modules (A.1) on the powered subset →
   register as candidate programs; nominate the regulators maintaining the induced-Treg
   program.
2. **Anchoring (validate, don't define)** — master-regulator KDs (FOXP3; TBX21/STAT1)
   must agree in sign with the NTC-derived axis (A.2). Concordance = confidence;
   discordance = flag. Axis geometry stays on NTC.
3. **Coherence test** — cell-level, for anchors + abundant KDs: does the regulator KD
   selectively move the induced-Treg cluster (A.3)? This is the causal test of the
   cluster's reality.

**Data/connectors:** entirely internal — `DE_stats.h5ad` (+ `by_guide`/`by_donors` for
the discovery/held-out splits), `pseudobulk_merged.h5ad`, and the cell-level
guide-assigned files for tier 3; MyGene/BioMart for ID harmonization; the Marson paper's
own perturbation clustering as an external cross-check. No new external connector needed.
**New program-registry fields:** `regulator_anchors`, `anchor_sign_concordance`,
`cluster_coherence_verdict`, each with its power tier.

---

## PART B — Glioma resources for druggable targets (tumor-intrinsic + microenvironment)

### B.1 Resource → access map (concrete to the catalog)

**Reachable NOW via a CS connector (no grant):**
- **TCGA-GBM & TCGA-LGG** — `mcp-cancer-models` (cBioPortal): mutations, copy-number,
  clinical/survival, study membership. The bulk somatic + outcome backbone.
- **Open Targets** — `mcp-clinical-genomics` (`open_targets_disease_targets`,
  `open_targets_disease_drugs`, `open_targets_drug`, `open_targets_graphql`): GBM
  disease→target associations, **tractability buckets** (small-molecule / antibody /
  PROTAC / other), known drugs. The druggability spine.
- **ChEMBL** — `mcp-chembl`: target bioactivities, mechanism of action, **ADMET**
  (incl. CNS flags) for existing chemistry against a candidate.
- **Human Protein Atlas** — `mcp-protein-annotation` (`get_protein_atlas_gene`): brain
  regional expression, subcellular location, and the **Pathology atlas** glioma
  prognostic association.
- **GTEx** — `mcp-expression`: **normal-brain** expression baseline → CNS safety window.
- **STRING** — `mcp-protein-annotation`: pathway partners / co-functional expansion.
- **PubChem / BindingDB / ChEBI** — `mcp-chemistry`: physicochemistry for a
  **BBB / CNS-MPO** heuristic (MW, TPSA, cLogP/cLogD, HBD, pKa) and measured affinities.
- **ClinicalTrials.gov** — `mcp-clinical-trials`: existing GBM programs on a target/drug.
- **CIViC / ClinGen** — `mcp-clinical-genomics`: clinical actionability/validity.
- **BioMart / MyGene / Reactome** — id harmonization + pathway context.

**Need a NETWORK GRANT (public download, no connector):**
- **DepMap glioma lines** — `depmap.org` / figshare release CSVs (Chronos gene-effect,
  expression, lineage annotations). **No connector exists** — this is the central
  dependency axis and must be grant-loaded once and cached as an artifact.
- **GLASS (longitudinal)** — Synapse (`synapse.org`) / glass-consortium; paired
  primary→recurrent trajectories. Grant (+ possibly Synapse credentials). Some GLASS
  lives in cBioPortal, but the paired longitudinal matrices are via Synapse.
- **CGGA** — `cgga.org.cn`: RNA-seq + clinical (adds an independent, IDH/1p19q-annotated
  cohort, complementary to TCGA). Grant.
- **Ivy GAP** — `glioblastoma.alleninstitute.org`: anatomic-structure RNA-seq
  (pseudopalisading necrosis, microvascular proliferation, cellular tumor, infiltrating
  edge) → spatial/regional context. Grant.

**Single-cell atlases — mixed:**
- **CELLxGENE is allowlisted** → **GBmap** (integrated GBM scRNA atlas; malignant + TME
  compartments: TAM/myeloid, T-cells, oligodendrocyte, endothelial, etc.) is reachable
  via `cellxgene-census` without an extra grant.
- **GEO is allowlisted** → **Neftel 2019** (GSE131928; the 4 malignant meta-states
  MES-like / AC-like / OPC-like / NPC-like) can be pulled from GEO; the Broad Single Cell
  Portal mirror would need a grant.
- Other atlases via Zenodo/Broad SCP need grants.

**Load from local NAS (preferred for the big/static resources):**
- **Not yet accessible** — only the perturb-seq dir is mounted. Once a
  `request_host_access` grant is made to the GBM NAS path, prefer NAS for the heavy
  objects (single-cell atlas `.h5ad`s, and any local GLASS/CGGA/Ivy-GAP downloads): it
  avoids the DepMap-sized network grants and keeps large loads local. **Recommended
  division of labor:** NAS for big static matrices; connectors for live queryable
  knowledge (TCGA via cBioPortal, Open Targets, ChEMBL, HPA, GTEx, trials); network
  grant reserved for DepMap (no connector, essential) + anything not on NAS.

### B.2 The cross-reference logic — a candidate × evidence-axis scorecard

A candidate enters from the T-cell funnel: gene **X** whose KD skews induced-Treg → Th1
(Stage-2 output). The GBM question is *is X a druggable driver of the transcriptional
changes, tumor-intrinsic or in the microenvironment?* Join on the gene (HGNC/Ensembl,
BioMart-harmonized) and build a multi-axis scorecard — an **intersection, not a single
score**, because different targets win on different axes:

1. **Glioma dependency** — DepMap glioma-lineage Chronos. *Selective* dependency in
   glioma lines (vs pan-essential). Note the sign flip from Stage-1/2: in the tumor we
   *want* dependency, but still separate selective from common-essential. → grant.
2. **Tumor expression + malignant-state / TME specificity** — where does X live in GBM?
   - Bulk: TCGA-GBM/LGG (cBioPortal) + CGGA — expression, subtype/IDH, survival; HPA
     Pathology for prognostic direction.
   - Single-cell: **Neftel** malignant states (is X a MES-like driver?) and **GBmap**
     TME compartments (is X in TAMs? endothelium? tumor-infiltrating T/Treg?). This is
     what splits **tumor-intrinsic** from **microenvironment**.
3. **Longitudinal alteration** — GLASS paired primary→recurrent: is X gained/lost at
   recurrence (progression / treatment-escape relevance)? A recurrence-gained target is
   more compelling for recurrent GBM. → grant.
4. **Regional/anatomic niche** — Ivy GAP: is X enriched in aggressive niches
   (pseudopalisading / microvascular proliferation)? Spatial corroboration of MES-like.
   → grant.
5. **Druggability + brain penetrance** — Open Targets tractability + known drugs;
   ChEMBL mechanisms/ADMET; PubChem/BindingDB → CNS-MPO/BBB heuristic; ClinicalTrials.
   **Brain penetrance is the GBM-specific gate** — a strong target that can't cross the
   BBB is deprioritized (or flagged for a delivery route: intrathecal / convection /
   focused-ultrasound). → connectors.
6. **Normal-brain safety** — GTEx brain + HPA: high normal neuron/glia expression = CNS
   tox risk; defines the therapeutic window. → connectors.

**Two mechanistic branches, kept explicit (the user's tumor-intrinsic + microenvironment):**
- **Tumor-intrinsic:** X drives a malignant state (MES-like) — DepMap dependency +
  malignant-cell expression + GLASS progression + Ivy-GAP niche. Direct anti-tumor.
- **Microenvironment / immune:** X shapes the immunosuppressive TME (TAMs, tumor Tregs,
  endothelium) — **this is where the T-cell funnel and the tumor context converge**: a
  target that reverses induced-Treg in vitro may modulate tumor Tregs/TAMs in the GBM
  TME. DepMap is uninformative here (immune context); the single-cell atlases + expression
  carry the evidence. Tag every candidate with which branch its evidence supports.

**Program-level bridge (pays off the reusable-program design).** Because Stage-2 programs
are portable signed vectors, project the **induced-Treg→Th1 axis itself** onto GBM data:
onto GBmap/Neftel (does the induced-Treg program mark tumor Tregs? does the inflammatory
program mark a TME/malignant state?) and onto TCGA/CGGA bulk (does the axis track subtype
or survival?). This tests whether the *program* — not just individual genes — is
GBM-relevant, and reuses the exact projection primitive from `STAGE2_PLAN.md` §2.1 across
the tumor boundary.

### B.3 Funnel placement + concrete artifact

**Recommendation: a NEW tumor-context step, distinct from druglink.** Rationale: the
tumor-context question (does the target matter in GBM, and in which compartment) is a
*biological* gate that must precede narrowing to chemistry. Proposed funnel:

- `01_cd4_programs` (Stage-1, done) → `02_skew_scoring` (Stage-2 plan) →
  **`03_tumor_context` (new)** — the B.2 scorecard: dependency + malignant-state/TME
  expression + longitudinal + regional + normal-brain safety, plus the program-level
  projection → **`04_druglink`** — tractability + brain-penetrance + trials + chemistry,
  applied to the survivors of 03 (druglink naturally owns axis 5's chemistry half).

Keeping `03_tumor_context` separate from `04_druglink` prevents a brain-penetrant but
GBM-irrelevant target from surviving, and a GBM-critical but not-yet-drugged target from
being dropped prematurely.

**Concrete artifacts** (mirror the Stage-1/2 chain exactly):
- `tumor_context_pipeline.py` — `# %%` provenance notebook (same style as
  `stage1_pipeline.py`), emitting the scorecard.
- `stage03_tumor_context.json` / `.csv` — one row per T-cell candidate gene; columns =
  the six evidence axes with **explicit provenance per cell** (which resource, which
  value/version), the **mechanistic-branch tag** (tumor-intrinsic / TME-immune / both),
  a per-axis power/coverage flag, and a combined tier that does **not** collapse the axes
  prematurely.
- `program_in_gbm.json` — the induced-Treg→Th1 program projected onto GBM single-cell +
  bulk (the B.2 program bridge).
- `verify_reproduce_stage3.py` + extended `reproduce.sh` steps + reused
  `render_notebook.py` — same determinism/gate discipline as Stages 1–2.
- **Shared into `spotlib`:** the gene-scorecard join/harmonization and the program
  projection helper (already shared from Stage-2). **Stage-3-specific:** the DepMap
  loader, the GBM single-cell state/compartment scoring, the GLASS longitudinal delta,
  and the CNS-MPO/BBB heuristic.

### B.4 Biggest risks for Part B
- **Context transfer (largest).** A CD4-in-vitro target need not act the same way in the
  GBM TME; the TME-immune branch is a *hypothesis-generating* bridge, not proof. State it.
- **DepMap context gap.** Glioma *cell lines* ≠ GBM in situ (no TME, culture-adapted);
  dependency is a proxy, strongest for tumor-intrinsic candidates.
- **Access + provenance.** DepMap/GLASS/CGGA/Ivy-GAP need grants; the NAS GBM data needs
  a host grant before use. Pin dataset versions in the scorecard provenance — glioma
  resources update, and an unversioned join is not reproducible.
- **Cohort/subtype confounds.** IDH-mutant vs wildtype, primary vs recurrent, adult vs
  pediatric differ profoundly — stratify (don't pool) TCGA/CGGA/GLASS by subtype.
- **BBB heuristic is a filter, not truth.** CNS-MPO/physicochemistry predicts penetrance
  imperfectly; use it to rank/flag, not to hard-exclude, and note delivery-route escapes.
