# spot Stage-2 — primary architecture: gene-skew scoring for a Stage-1-selected A→B contrast

_Shipped default contrast: induced-Treg(48h) → inflammatory Th1(8h)._

_Consolidated design memo — the single primary architecture for Stage-2. Supersedes
the earlier `STAGE2_PLAN.md` + `STAGE2_ADDENDUM.md`: folds in the perturbation-defines-
states layer (former addendum Part A), incorporates the Claude Science review
(`STAGE2_REVIEW.md`, 2026-07-10), and scopes the tumor-context / druggability /
brain-penetrance evidence out to Stages 3–4 (former addendum Part B, deferred below).
No heavy compute run. Grounded in the Stage-1 chain (`stage1_pipeline.py`,
`cluster_scores.py`, `label_clusters.py`, `verify_reproduce.py`, `reproduce.sh`), the
Stage-1 review (`REVIEW_MEMO.md`), and the Marson dataset under
`/mnt/tcenas/datasets/raw/public/marson2025_gwcd4_perturbseq/`._

---

## 0. What Stage-2 is — and where it stops

**The states Stage-2 skews between are not hardcoded — they are chosen in Stage-1.**
The Stage-1 workbench's two population pickers (source *"cells…"* = **A**, target
*"state…"* = **B**) plus the **"identify genes"** action define an **A→B contrast**,
and that selected contrast — the two population definitions, keyed on `obs['L0.8']` /
`obs['barcode']` — is the **locked artifact Stage-1 hands to Stage-2**. Stage-2 is the
general engine that, for *whatever* A→B the selector picks, finds the **perturbations
(gene knockdowns) that drive that transition**. The **shipped default** — the
biologically motivated contrast for GBM — is **induced-Treg(48h) → inflammatory
Th1(8h)**, the worked example throughout; substitute the selected A/B for any other.

That default came out of Stage-1: the "Treg" cluster is **activation-induced FOXP3⁺
regulatory-like cells at 48 h**, not natural Tregs (FOXP3⁺CTLA4⁺ rises ~26× Rest→48 h
while Helios/IKZF2 stays flat — Follow-up 1 in `REVIEW_MEMO.md`), and the only coherent
inflammatory effector skew in the reference is **Th1, best expressed in the 8 h-activated
compartment** (32.2% of it). Stage-2 turns to the **perturbation** arm — ~3,341 gene
knockdowns (CRISPRi), across Rest/Stim8hr/Stim48hr, 4 donors — and asks, for the selected
contrast: *which knockdowns push cells off state A toward state B?* For the default:
*which knockdowns de-repress the inflammatory Th1 program and reverse induced-FOXP3?*

**Scope boundary (hard).** Stage-2's deliverable is a **ranked, gated candidate-gene
table** — genes whose knockdown skews the selected contrast, with direction, specificity,
power, reproducibility, and significance. **Stage-2 stops there.** Whether a candidate is
a glioma dependency, where it sits in the tumor (malignant cell vs immune
microenvironment), how it changes at recurrence, whether it is druggable, brain-penetrant,
or safe in normal brain — all of that is **downstream (Stages 3–4)**, designed in §4 so
the Stage-2 output is shaped for the handoff, but **not computed here**.

The engine rests on one directional object — a signed **A→B program axis** in gene space
(default induced-Treg → Th1) — and one cheap primary metric: the **projection of each
perturbation's genome-wide DE vector onto that axis**. Everything else is axis-quality
gating, de-confounding, power gating, and reproducibility scaffolding around those two.

---

## 1. Defining the selected A→B axis (and letting perturbations sharpen it)

### 1.1 What a "program" is, so it is reusable across stages

A **program** is a named, signed, weighted vector over a fixed gene universe, plus its
provenance. Nothing more. Stage-1's marker panels are the degenerate case (binary,
hand-curated); Stage-2 generalizes to data-derived continuous weights but keeps the same
primitive, so any stage can load a program and **project new data onto it** by a dot
product. Registry entry (schema in §5):

```
program_id, display_name, method, gene_universe_id,
weights: { gene_symbol: signed_weight },   # sign convention explicit
provenance: { source_cells, contrast, params, seed, code_hash },
sign_convention: "positive = <state B>, negative = <state A>"   # recorded from the selection
```

The primitive is already parameterized — the sign convention is filled from *which*
population was picked as A vs B, not hardcoded. This is what makes a program reusable and
portable across the embedding, the cell set, and (in §4) the tumor boundary.

### 1.2 Defining the axis — methods and recommendation

**The central design question is how to define the selected A→B axis** (default
induced-Treg → Th1). Four primitives, with tradeoffs:

1. **Marker panels (Masopust et al.), Stage-1 style.** Interpretable, cross-stage stable,
   tiny — but sparse and 3′-dropout-sensitive (FOXP3 detected in only 27.5% of
   cluster-Tregs). Good as an **anchor / sanity readout**, too thin to be the sole axis.
2. **NMF on the reference.** Unsupervised, coherent additive co-expression programs — but
   factors need not align with the A↔B contrast and drift with k/initialization. Best to
   **discover and register reusable programs**, not to define the directional metric.
3. **scVI/scANVI Bayesian DE.** The Stage-1 scVI model exists (`/mnt/tcenas/models/spot_scvi`);
   DE between the A and B cell groups gives a **batch-corrected, donor-aware** signed
   effect per gene. Strong (handles the 4-donor structure as the embedding did), but
   model-tied and less transparent than a plain contrast.
4. **Pseudobulk cluster-contrast DE (DESeq2/edgeR, donor covariate).** Signed logFC
   between the two states on the reference cells, donor-controlled. Most transparent and
   most directly "the axis we want"; costs a heavy cell-level load.

**Recommendation — layered: primary axis + anchors + discovery.**

- **Primary axis** = the signed **state-A vs state-B** contrast (default induced-Treg-48h
  vs Th1-8h), computed on the reference cells, **donor-controlled**. Compute two ways —
  scVI DE (3) and pseudobulk DESeq2 (4) — and keep the axis only on genes where the two
  **agree in sign** (a cheap robustness gate + an honest weight vector). Sign:
  **positive = state B (default Th1-inflammatory), negative = state A (default
  induced-Treg)** — set per-run from the selection.
- **Anchor programs** = interpretable panels reused verbatim: *induced-Treg* {FOXP3,
  CTLA4, CCR8, TNFRSF18, IKZF2} and *Th1-inflammatory* {TBX21, CXCR3, IFNG, IL12RB2,
  STAT1/IFN-response}. Orthogonal, human-readable; lets us report "reverse-FOXP3"
  separately from "de-repress-Th1."
- **Discovery programs (optional)** = NMF factors, registered by id, to interpret *what
  else* moves and seed later stages.

**Why the axis lives in the DE gene universe.** The perturbation scoring (§2) works in the
`DE_stats` 10,282-gene space, so the axis must be **restricted to the intersection** of
the reference universe (18,130) and the DE universe (10,282), and the load-bearing genes
(FOXP3, CTLA4, CXCR3, TBX21, IFNG) must survive that intersection with measurable baseline
(risk R3).

**A confound baked into the default poles (do not leave implicit — CS review).** The
default poles live at **different timepoints**: A = induced-Treg at **48h**, B = Th1 at
**8h**. So the axis conflates a *fate* difference (Treg vs Th1) with an *activation-
duration* difference (48h vs 8h) — and perturbations are then scored on their **Stim48hr**
DE. A knockdown that merely makes 48h cells look transcriptionally *younger* (more
8h-like, less activation-matured) will project positive with no real Th1 skew.
Mitigations, in preference order: (a) define both poles at a **common timepoint** where
the states co-exist — **but this may not be available**: whether induced-Treg and Th1
co-occur in usable numbers at a single timepoint is an empirical question, and if they do
not, only the partial fixes below remain; (b) regress an explicit **activation-duration /
kinetics axis** out of the primary axis `w` — **note this direction is largely collinear
with G4's proliferation/translation axis for this default** (8h→48h activation *is*
substantially a proliferation/metabolic ramp), so project **one combined nuisance
direction, not two**: R2b and G4 are near-duplicate operations here, and running both
risks over-projecting away the real Treg-vs-Th1 signal; (c) at minimum, verify top hits
are not merely shifting cells along the 8h↔48h activation trajectory. Tracked as risk R2b.

### 1.3 Axis-level gates — what makes the engine *general*, not just general-shaped (CS review)

The projection δ·ŵ is always computable, but its *meaning* is contrast-dependent. The
Stage-1-tuned validators do not automatically transfer to an arbitrary user-picked A/B.
**Before any perturbation is scored, gate the axis itself** — the axis-level analogue of
the per-perturbation power tiers in §2.3:

- **G1 · Separability.** Number of genes significantly separating A from B; cross-validated
  A-vs-B classifier accuracy on **held-out reference cells**; how many genes survive the
  two-method (scVI ∩ DESeq2) sign-agreement filter. If A and B are barely separable, `w`
  is noise — emit **"contrast underpowered as an axis"** and refuse the screen, rather
  than silently ranking against a poorly-conditioned direction. (The default is a large,
  well-separated contrast and passes trivially; a user picking two nearby substates is the
  failure mode this catches.)
- **G2 · Proxy quality = the A and B fractions (generalizes R1).** The cheap screen
  measures a *whole-condition* shift as a proxy for the A→B skew; the proxy is only as
  good as how represented A and B each are in the **scored condition**. Compute and report
  the **A fraction and the B fraction separately, over the named condition(s) they are
  scored in** — not a single merged A∪B number; **warn (or refuse the cheap lane)** when
  either is low. This matters acutely for the default: the screen scores **Stim48hr**,
  where A (induced-Treg) is ~6.3% but B (Th1, best expressed at 8h) is **barely present**
  — so a single "A∪B ≈ 6.3%" number is really just the A fraction, and the B side of the
  A→B skew is under-represented exactly where the perturbation effect is measured (this is
  the G2×R2b interaction). R1 bites hard here, and the compositional confirmation (§2.7)
  is not optional for the shortlist.
- **G3 · Sign-validation state.** The default has a beautiful sign anchor (FOXP3-KD →
  strongly positive, §2.6). An arbitrary contrast may have **no canonical master-regulator
  knockdown** to orient it — the sign is then mathematically fixed by the A/B labeling but
  its *behavioral validation* is absent. Carry an explicit **`sign_validated: true|false`**
  per contrast; when false, say so wherever a hit is reported. The default earns a
  validated sign; a generic contrast often will not, and that changes how much trust the
  ranking earns.
- **G4 · Broad-axis warning for cosine-specificity.** §2.2's cosine defense assumes the
  axis is a *focused* effector direction largely orthogonal to housekeeping/ribosomal/
  cell-cycle space. For a broad, metabolically-loaded contrast (the obvious example:
  anything resembling Rest vs Stim), `w` loads on exactly the genes a pan-essential
  knockdown moves — so a sledgehammer scores **high** cosine and the specificity guard
  **inverts into a confound**. Flag when the axis has large overlap with a proliferation/
  translation reference direction, and project that direction out of `w` (or report it
  alongside) so the sledgehammer signal has somewhere to go that isn't `w`. **For the
  shipped default this proliferation direction is largely collinear with R2b's kinetics
  axis** — project **one combined** nuisance direction, not both, or you over-project.

### 1.4 Letting perturbations *define/sharpen* the states (former addendum Part A)

Stage-1 defines states by **co-expression covariance in unperturbed cells** (what varies
together naturally). The screen offers a second, independent notion — **causal/regulatory
covariance** (what changes together when you push the system) — which separates
co-expressed-but-independently-regulated modules from genuinely co-controlled ones, and
can adjudicate a state *boundary* by regulatory coherence. Value is real but bounded by
two facts about *this* screen: `DE_stats` is **whole-condition pseudobulk** (R1) and the
substrate is a **Th0 polyclonal** context where ~82% of NTC cells make no functional call.
Add a **three-tier** perturbation-informed layer to `define_programs.py`, each on its
correct footing:

1. **Discovery** — cluster genes by how they co-respond across knockdowns (the
   Replogle-style perturbation-covariance construction) on the **powered subset**
   (`ontarget_significant`, meaningful `n_downstream`). Nominates the *regulators*
   maintaining the state A program (find the module containing FOXP3/CTLA4/CCR8; read off
   which KDs perturb it coherently). Registered as `method="perturbation_covariance"`.
2. **Anchoring (validate, don't define)** — a small, pre-specified set of master-regulator
   KDs (FOXP3 for the induced-Treg pole; TBX21/STAT1 for Th1) must **agree in sign** with
   the NTC-derived axis. Concordance = confidence; discordance = flag. **Axis geometry
   stays on the reference contrast** — the sharpest circularity risk in this memo is
   defining the axis from the perturbations you then score, so don't.
3. **Coherence test** — cell-level, for anchors + abundant KDs: does the master-regulator
   KD *selectively* move the state-A cluster? This is the **causal test of the cluster's
   reality** (Stage-1's biggest open question — is the "Treg" cluster a regulatory state or
   just an activation-timepoint compartment?), and it is the least circular use because it
   tests a co-expression definition with an orthogonal causal axis. Underpowered
   screen-wide (thin per-KD×cluster×condition counts for a 6.3% cluster) — report the
   anchors, declare "insufficient power" for the rest.

**New program-registry fields:** `regulator_anchors`, `anchor_sign_concordance`,
`cluster_coherence_verdict`, each with its power tier. Entirely internal data
(`DE_stats.h5ad`, `by_guide`/`by_donors`, cell-level guide-assigned files for tier 3);
the Marson paper's own perturbation clustering is a free external cross-check.

---

## 2. Scoring the skew induced by each knockdown

### 2.1 Primary metric — a directional program-shift on the DE vector

For each perturbation *X* in a condition, `DE_stats` gives a genome-wide signed effect
vector **δ_X** (`zscore` = logFC/lfcSE default; logFC as sensitivity) over the shared gene
universe. With unit-normalized axis **ŵ** (§1.2):

- **SkewScore(X) = δ_X · ŵ** — projection onto the A→B axis. **Positive = the knockdown
  pushes the transcriptome toward state B / away from state A** (default: toward
  Th1-inflammatory, away from induced-Treg).
- **Decompose** into a **B-up component** (projection onto the B anchor) and an **A-down
  component** (projection onto the A anchor, sign-flipped; plus, called out separately, the
  **FOXP3 and CTLA4 logFC** for the default). Distinguishes a knockdown that only
  de-represses B from one that actually reverses the A program.

Primary screen runs in the condition where state A exists (default **Stim48hr**); other
conditions are scored as specificity context (a real hit should act where A is present).

### 2.2 Specific program-shifters vs essential-gene sledgehammers

- **Cosine, not just dot product.** A pan-essential KD produces a huge broad δ_X that
  projects onto everything. Report **specificity = cos(δ_X, ŵ) = SkewScore / ‖δ_X‖**. A
  specific shifter has high cosine; a sledgehammer has high ‖δ_X‖ but low cosine — *for a
  focused axis*. **Caveat (G4):** this discriminator weakens or inverts as the axis
  broadens; carry the G4 flag and the proliferation-axis projection so cosine is not
  trusted blindly for broad contrasts.
- **Breadth covariate.** Carry `n_total_de_genes`, `n_downstream`, `n_up/n_down` as an
  explicit breadth flag; broad-footprint KDs get a **"broad-DE-footprint" tag**.
- **Housekeeping/essential annotation (in Stage-2, no grant needed).** Tag
  ribosomal/spliceosomal targets, and flag **core-essential** membership against the **Hart
  Core Essential Genes v2 list (`CEGv2.txt`, 684 genes, already in-project — static, no
  DepMap grant or network access)** — emitted as a `core_essential` flag. This is an
  independent, always-available backstop to the cosine/breadth filter, and it is
  load-bearing precisely because **G4 shows the cosine guard can invert** for broad axes.
  Only the quantitative, glioma-**selective** Chronos dependency is deferred to Stage-3
  (§4) — the flat common-essential separation, which the project's principles make a
  first-class Stage-2 duty, is done here.

### 2.3 Power gating — say "insufficient power" out loud

Never rank a knockdown the data cannot support. Gate on `DE_stats.obs`:

- `ontarget_significant == False` / `ontarget_effect_category == "no on-target KD"` → **the
  gene wasn't knocked down**; excluded, reported as "no on-target KD," not a null result.
- `low_target_gex == True`, small `n_cells_target`, `single_guide_estimate == True` →
  **insufficient power** tier, reported separately, never mixed into ranked hits.

Mirrors the Stage-1 discipline (the permutation-FDR floor that killed the Th2 artifact).

### 2.4 Reproducibility of a hit (built into the dataset)

- **Cross-guide agreement** — the skew must hold for both guides (`guide_correlation_signif`,
  or recompute SkewScore on `by_guide` and require concordant sign).
- **Cross-donor agreement** — replicate across donor pairs (`donor_correlation_hits_*`, or
  SkewScore on `by_donors`). A one-donor hit is demoted.

### 2.5 Significance, not just ranking (3,341-way multiplicity)

Build an **empirical null** for SkewScore from the **NTC guides**: their projection
distribution is the "no real perturbation" null. Per-perturbation empirical p = tail
probability against the NTC null, BH-adjusted. Two constraints from the review: the null
must be **recomputed per contrast** (its variance depends on ŵ's direction — you cannot
cache one null across selections), and the achievable BH-adjusted tail is bounded by the
number of NTC pseudobulks — **check n_NTC actually supports the 3,341-way multiplicity**,
and fall back to a **parametric fit** of the NTC projection if the pure empirical tail is
too coarse.

### 2.6 Sign bookkeeping and positive controls

These are **CRISPRi knockdowns** (target repressed), so a top positive hit is a gene that
**normally maintains state A / represses state B**. For the default:

- **FOXP3 knockdown** should score strongly positive (reverses induced-FOXP3) — the
  canonical positive control that fixes the sign. **First gate before any ranking is
  trusted.**
- Knockdowns of the induction axis (TGFβ/SMAD, IL2–STAT5 nodes) are expected supporting
  positives; **NTC guides** score ≈ 0 (negative control; also the §2.5 null).

**General case (G3):** for a non-default A/B, pick the control whose KD is expected to
drive B; if none exists, set `sign_validated=false` and report the sign as
mathematically-determined-but-behaviorally-unvalidated. Do not paper over the absence.

### 2.7 Two scoring views — cheap primary, expensive confirmatory

1. **Transcriptional-shift (primary, cheap):** the §2.1 projection on `DE_stats`. All 3,341
   perturbations in minutes, no cell load. This is the screen.
2. **Compositional-shift (confirmatory, expensive, shortlist only):** for top hits, go to
   the cell-level guide-assigned files and test whether KD of *X* actually **moves cells
   out of the state-A cluster** toward the state-B region in the scVI embedding (a change
   in neighborhood composition, not just mean expression). The direct phenotype, but a
   heavy load (12 × ~150 GB) — reserved for a shortlist (the "run heavy once" discipline).
   **Given G2 (low A∪B fraction for the default), this confirmation is load-bearing, not
   optional.**

### 2.8 Lane C — scLDM-CD4 in-silico skew (parameterized prioritizer, generator-not-evaluator)

A model-based lane runs the **same A→B selection** through a generative model of this exact
system: **scLDM-CD4 v0.1** (CZ Biohub Chicago) — a transformer autoencoder (15.2M params)
that learns a latent CD4 cell-state representation, plus a conditional flow-matching
Diffusion Transformer (44.3M params) that generates perturbed latent profiles conditioned
on perturbation identity + context (donor, timepoint) with classifier-free guidance.
Trained — per the **scLDM-CD4 model card** (the source of the figures below, not the Zhu
preprint itself) — on **~14.5M cells** on a fixed **3,699-HVG** panel, derived from the
Marson Perturb-seq raw data of **Zhu et al. 2025** (bioRxiv 2025.12.23.696273; the
*training-data* source). The released checkpoint's **15.2M-param autoencoder / 44.3M-param
flow-matching** sizes are likewise the model card's. Model = Dibaeinia et al. 2026,
building on scLDM (Palla et al. 2025, arXiv 2511.02986). **License: MIT** (code
`github.com/czbiohub-chi/scldm_cd4`, weights `hf.co/biohub/scldm_cd4` — LICENSE verified),
so usable/redistributable under the public-only rule.

**How the flow actually works (corrected — CS review).** The OT coupling is
**noise→data**, *not* control→perturbed and *not* A→B. The model gives **conditional
distributions**; it does **not** "transport A into B." So an in-silico A→B skew must be
**constructed as a counterfactual difference**: **condition on the A/source context** (its
donor/timepoint), **generate under knockdown vs under control, take the difference vector,
and project it onto the A→B axis.** There is no "B-context conditional" in this operation
— the model is conditioned on the *source*, and B enters only as the axis the difference
is projected onto. This is **conditional counterfactual generation**, and the resulting
in-silico skew is a **difference of two generated conditionals** — i.e. it retains a
mean-shift character and does not magically transcend the measured lane's limits.

**How it plugs into the parameterized axis.** A documented use case is *in-silico ranking
of candidate perturbations toward a desired transcriptomic effect*; here the desired
outcome is the selected target B, so the model is parameterized by the **same A→B
selection** as the measured lanes:

- **In-silico SkewScore.** For each knockdown, generate KD-vs-control **conditioned on the
  A/source context**, take the difference vector, and **project it onto the A→B axis** —
  the same signed, directional object as the measured lane. (Ranking by "closeness to B"
  alone is a *different, one-sided* quantity, so don't; match the measured score.)
- **Concordance is a QC gate, not a hit signal (reframed — CS review).** Concordance with
  the measured DE on single-gene KDs is *largely circular* as evidence (R9), but *very*
  useful as **model validation**: before trusting scLDM as a prioritizer at all, confirm
  it reproduces the measured positive control (does model-generated FOXP3-KD move toward
  loss-of-induced-Treg?) and a held-out set of measured KDs. Passing that gate is a
  *precondition for use*; it is not evidence harvested from the model.
- **Where it legitimately adds reach (bounded).** The vendor-claimed reach is **donor /
  timepoint interpolation** where empirical data are thin, and prioritization ahead of the
  expensive §2.7 confirmation. Combination-KD generation *is* a listed capability but is
  squarely the **out-of-distribution regime** the model itself flags as least reliable —
  use only with the firewall and label as **untested extrapolation**, never as a strength.
- **Give the lane its own null.** Generate under NTC/scrambled conditioning (or label
  permutation) so a `model_only` call means "beyond the model's own noise," not merely
  "high on an unnormalized list" — restoring symmetry with Lane A's §2.5 null.

**Firewall (load-bearing).** scLDM is **not independent evidence** — a learned compression
of the *same* measurements, so it **inherits the same confounds** (R1 whole-condition
structure, R2 mean-shift assumption, the R2b activation confound, and the 6.3%-subset
sparsity) — it cannot supply resolution the training data did not contain, and is weakest
exactly on the rare induced-Treg subset we most care about. **Measured DE stays ground
truth; scLDM proposes and prioritizes.** Honor its constraints: **flow-matching** model for
generation (autoencoder is inference/encoding only); **HVG-coverage check** — verify the
load-bearing axis genes (FOXP3, CTLA4, IFNG…) are in the model's 3,699-HVG panel, or the
lane literally cannot represent the contrast (R3 redux, R9b); **no CPU inference** (tested
on A100/H100/A6000) → a **remote-GPU job** to provision (§7 step 2b). Kept strictly
`suggestive` / `CS-complement`, **never in the confirmed set**.

---

## 3. What Stage-2 outputs — the handoff

Stage-2's deliverable, and the boundary of its responsibility:

- **`stage02_programs.json`** — the program registry (§1.1 schema): the A→B axis + anchors
  + NMF/perturbation-covariance discovery programs, each a signed weight vector over the
  named gene universe, with provenance. *The cross-stage-reusable artifact.*
- **`stage02_perturbation_scores.json`** — one record per perturbation × condition:
  `{target_gene, ensembl_id, condition, skew_score, b_up, a_down, foxp3_logfc, ctla4_logfc,
  cosine_specificity, breadth (n_total_de_genes), power_tier, ontarget_effect,
  guide_concordance, donor_concordance, emp_p, q, rank, insilico_skew, insilico_rank,
  insilico_null_p (Lane C, §2.8; null if not run), flags:[sledgehammer | core_essential |
  underpowered | no_ontarget_kd | broad_axis | sign_unvalidated | model_only]}`.
- **Axis-quality record** (§1.3) — per contrast: `separability`, `a_union_b_fraction`,
  `sign_validated`, `broad_axis_flag`. Ships with the scores so a consumer knows how much
  the ranking earned.
- **Overlay JSON** for the frontend — mirrors `stage01_umap_seed.json`: ranked knockdowns
  with the two-axis (skew vs specificity) coordinates, decomposition, flags, `nomen_counts`-
  style summaries, `emitted_at`.

**The ranked candidate-gene table is the input to Stage-3.** Nothing tumor-, drug-, or
brain-related is computed in Stage-2.

---

## 4. Deferred downstream — Stages 3–4 (former addendum Part B, scoped)

A Stage-2 candidate is gene **X** whose KD skews the selected contrast. The GBM question —
*is X a druggable driver of transcriptional/fate changes, tumor-intrinsic or in the
microenvironment?* — is answered by a **per-gene, multi-axis scorecard** (an
*intersection*, not one collapsed score, because targets win on different axes). The six
evidence types and **where each lives**:

| # | Evidence axis | Resource(s) | Stage |
|---|---|---|---|
| 1 | **Glioma dependency** — *selective*, not pan-essential (the flat core-essential tag is done in Stage-2 via CEGv2, §2.2) | DepMap glioma-lineage Chronos | **03** |
| 2 | **Tumor expression + malignant-state / TME compartment** (cancer cell vs immune microenv.) | TCGA-GBM/LGG + CGGA (bulk); Neftel malignant states + GBmap TME (single-cell); HPA Pathology | **03** |
| 3 | **Longitudinal change at recurrence** | GLASS paired primary→recurrent | **03** |
| 4 | **Druggability / tractability + known drugs** | Open Targets tractability, ChEMBL MoA | **03 (druglink)** |
| 5 | **Brain penetrance** (CNS-MPO / BBB) | PubChem/BindingDB physchem → CNS-MPO heuristic | **04 (PK/PD)** |
| 6 | **Normal-brain safety window** | GTEx brain + HPA | **04 (PK/PD)** |
| 7 | **Peripheral-tolerance / autoimmune risk** — reversing Treg / de-repressing Th1 is *mechanistically the direction of autoimmune liability* (the checkpoint-inhibitor irAE neighbor) | literature + immune-branch reasoning (qualitative) | **04 (safety)** |

**Stage mapping (per user direction — druggable = 03, brain-penetrant = 04).** Axes 1–3
are **tumor-context target validation** and axis 4 is **druggability** → **Stage-3
(`03_druglink`)**; axes 5–7 are **exposure + safety** → **Stage-4 (`04_PKPD`)**. **Within
Stage-3, the tumor-context relevance filter (axes 1–3) runs and *gates before* tractability
scoring (axis 4)** — a candidate cannot survive on druggability alone. This preserves the
former addendum's "relevance before chemistry" discipline as an explicit **intra-stage
ordering**, now that tumor-context is folded into druglink rather than a separate stage
(the addendum floated a separate `03_tumor_context`; folded into `03_druglink`'s front half
rather than renumber the locked 01→05 architecture). Keeping 03 ahead of 04 likewise
prevents a brain-penetrant-but-GBM-irrelevant target from surviving, and a GBM-critical-
but-not-yet-drugged target from being dropped prematurely.

**Two mechanistic branches, tagged on every candidate:** **tumor-intrinsic** (X drives a
malignant state, e.g. MES-like — DepMap dependency + malignant-cell expression + GLASS
progression) vs **microenvironment/immune** (X shapes the immunosuppressive TME — TAMs,
tumor Tregs, endothelium — *where the T-cell funnel and tumor context converge*; DepMap is
uninformative here, the single-cell atlases carry it). The **autoimmune-risk axis (7)** is
tied to this immune branch: the Stage-2 mechanism (reverse Treg / de-repress Th1) is the
systemic direction of broken peripheral tolerance, so a candidate strong on the immune
branch must carry that liability flag forward.

**Program-level bridge (pays off the reusable-program design).** Because Stage-2 programs
are portable signed vectors, Stage-3 can project the **A→B axis itself** onto GBM data
(GBmap/Neftel: does the induced-Treg program mark tumor Tregs? does the inflammatory
program mark a TME/malignant state?; TCGA/CGGA: does the axis track subtype/survival?) —
testing whether the *program*, not just individual genes, is GBM-relevant, reusing the §2.1
projection primitive across the tumor boundary.

**Access map (settle before Stage-3 executes).** Reachable **now via CS connectors**:
TCGA/LGG (cBioPortal `mcp-cancer-models`), Open Targets (`mcp-clinical-genomics`), ChEMBL,
HPA/STRING (`mcp-protein-annotation`), GTEx (`mcp-expression`), PubChem/BindingDB
(`mcp-chemistry`), ClinicalTrials, BioMart/MyGene/Reactome. **Allowlisted:** GBmap
(CELLxGENE census), Neftel GSE131928 (GEO). **Need a network grant (no connector):**
**DepMap** (central dependency axis — `depmap.org`/figshare, load once + cache), GLASS
(Synapse), CGGA, Ivy GAP. **NAS:** only the perturb-seq dir is mounted today — a
`request_host_access` to the GBM NAS path is prerequisite to loading the big static atlases
locally. Recommended division: NAS for big static matrices; connectors for live queryable
knowledge; the network grant reserved for DepMap + anything not on NAS. **This is a hard
Stage-3 dependency (risk carried forward), not a Stage-2 blocker.**

_Full Stage-3/4 detail (the scorecard columns, provenance-per-cell, subtype stratification,
CNS-MPO formulation) is developed in those stages' own plans; captured here only enough to
shape the Stage-2 handoff._

---

## 5. Reusable-artifact chain — mirroring Stage-1

### 5.1 The chain, one file per role

| Stage-1 file | Stage-2 analogue | role |
|---|---|---|
| `run_scvi_embedding.py` (heavy, cached) | *(reused as-is — Stage-2 does not re-embed)* | GPU embedding, run once |
| `cluster_scores.py` (one 14 GB load → JSON) | `define_programs.py` (one heavy load → `stage02_programs.json`) | build axis + anchors + discovery/perturbation-covariance programs; run axis-quality gates (§1.3); the single expensive load |
| `label_clusters.py` (no load → JSON) | `score_perturbations.py` (no cell load; programs + `DE_stats` → `stage02_perturbation_scores.json`) | fixed scoring/gating rule; ranked table |
| *(new, optional)* | `score_perturbations_insilico.py` (Lane C, §2.8) | scLDM in-silico skew + own null + concordance-QC gate; remote GPU |
| `stage1_pipeline.py` (`# %%` notebook) | `stage2_pipeline.py` (`# %%` notebook, emits overlay) | narrative provenance notebook + emit |
| `verify_reproduce.py` (gate on counts) | `verify_reproduce_stage2.py` (gate on top-N hits + positive-control score + axis-quality record) | reproducibility gate |
| `reproduce.sh` | extend with `[6..]` Stage-2 steps | one-command regeneration |
| `render_notebook.py` | reused as-is | notebook → HTML |

**Determinism, reused verbatim:** a fixed `SEED` for the NTC-null and any sampling; a
committed `REFERENCE` block in `verify_reproduce_stage2.py` (top-N hit ids, FOXP3-KD rank,
NTC≈0 check, axis-quality numbers) that the pipeline's emitted values must match, exiting
nonzero on drift — the gate philosophy that caught the Stage-1 Th2 artifact.

### 5.2 Shared vs Stage-2-specific

**Shared → a small `spotlib` common module:** the vectorized `score_genes` +
permutation-FDR machinery; gene-ID/symbol harmonization (GRCh38; MyGene `mcp-genes-
ontologies`); the program registry read/write + **projection** helpers; `render_notebook.py`,
the `reproduce.sh` skeleton, the `verify_reproduce` gate pattern; and the scVI embedding +
Stage-1 `cluster_labels.json` (consumed, not recomputed).

**Stage-2-specific:** the selection-parameterized **A→B axis definition** + **axis-quality
gates**; the perturbation-covariance / define-states layer (§1.4); the **projection +
de-confounding + power gating** rule; the **NTC-guide null**; the optional **scLDM lane**;
and all Stage-2 emitted JSON.

### 5.3 The explicit cross-stage dependency

Stage-2's most important input is **the A→B contrast selected in the Stage-1 workbench**
(the two population pickers → "identify genes"). The population definitions — for the
default, the induced-Treg-48h cluster and the Th1-8h region — are defined in Stage-1
(`cluster_labels.json` + `stage01_umap_seed.json`, keyed on `obs['L0.8']`/`obs['barcode']`);
Stage-2 reads that **selected (A, B) pair** (two population masks + a sign convention) as
an explicit serialized artifact, so both the measured lanes and the scLDM lane are
parameterized by the *identical* contrast. A hard, version-pinned dependency in
`reproduce.sh` (Stage-2 runs *after* the Stage-1 gate), so the chain tells one story end to
end and the handoff is explicit and gated.

---

## 6. Risks and assumptions (ordered by bite)

**R1 — `DE_stats` is whole-condition pseudobulk, not cell-state-resolved. (Largest.)** Each
KD's Stim48hr DE is across *all* cells in the condition, dominated by the bulk activated
population, not the induced-Treg subset (~6.3%). The primary metric is a proxy;
**quantified per contrast by G2 (A∪B fraction)** and confirmed on the shortlist by §2.7.
State it wherever a hit is reported.

**R2 — axis defined on reference cells, applied to perturbed-cell DE.** Projecting δ onto a
reference-derived axis assumes the co-expression structure is stable under perturbation —
fine for a mean-shift reading, mis-scored for a KD that *reshapes* the program (sharper near
strong regulatory hubs). The anchor decomposition (§2.1) partly guards it.

**R2b — the default poles are at different timepoints (48h vs 8h).** The axis conflates fate
with activation-duration; a KD that just makes cells "younger/8h-like" scores positive
spuriously. Mitigations in §1.2 — but note two traps: the preferred common-timepoint fix
**may not exist in the data** (do Treg and Th1 co-occur at one timepoint?), and the
kinetics-axis fix is **collinear with G4's proliferation projection for this default**, so
project one combined nuisance direction, not two. Also interacts with G2 (the B side is
barely present in the scored 48h condition).

**R3 — gene-space mismatch and FOXP3 dropout.** The axis must be restricted to the 10,282-gene
DE universe with the load-bearing genes surviving at measurable baseline; FOXP3 has real 3′
dropout, so verify presence + baseMean before trusting the FOXP3-down component.

**R4 — CRISPRi knockdown is partial/variable.** Many rows have no on-target KD (A1BG). The
§2.3 power gate is load-bearing, not optional.

**R5 — essential-gene sledgehammers.** Three guards: §2.2 cosine + breadth, the **in-Stage-2
CEGv2 core-essential flag** (§2.2, static, no grant), and Stage-3 glioma-*selective* DepMap.
**Cosine can invert for broad axes (G4)** — do not trust it alone; the CEGv2 flag is the
always-available backstop. Residual risk for genes both essential *and* genuinely regulatory.

**R6 — multiplicity across 3,341 perturbations.** The NTC-guide null + BH (§2.5), recomputed
per contrast, with a parametric fallback if n_NTC can't support the tail.

**R7 — sign bookkeeping / general sign-validation.** FOXP3-KD-positive + NTC≈0 fix the sign
for the default; an arbitrary contrast may have no such anchor → `sign_validated=false`,
reported (G3).

**R8 — circularity in the define-states layer (§1.4).** Defining the axis from the
perturbations you then score is trivially circular; keep axis geometry on the reference
contrast and use master-regulator KDs only to validate the sign.

**R9 — scLDM is not independent (Lane C).** Trained on the same data → concordance is partly
tautological (a QC gate, not confirmation), and it **inherits R1/R2/R2b + subset-sparsity**,
weakest exactly on the rare subset. Kept `suggestive`/`CS-complement`, never confirmed.

**R9b — scLDM gene-space + OOD.** The model lives in a 3,699-HVG panel ≠ the 10,282 DE
universe — verify axis genes survive its HVGs, or the lane can't represent the contrast.
Combination-KD generation is OOD (least reliable); use only flagged as extrapolation.

**R10 (carried to Stage-3) — DepMap access + context gap.** No DepMap connector (network
grant needed); glioma cell lines ≠ GBM in situ. A hard Stage-3 dependency, not a Stage-2
blocker.

---

## 7. Suggested execution order (when we run)

1. **`define_programs.py`** — build the axis (scVI DE ∩ pseudobulk DESeq2) for the selected
   A/B; run **axis-quality gates G1–G4** (separability, A∪B fraction, sign-validation,
   broad-axis) and refuse/flag as needed; build anchors + the perturbation-covariance /
   define-states layer (§1.4); emit `stage02_programs.json` + the axis-quality record.
   Verify load-bearing genes present + powered (R3).
2. **`score_perturbations.py`** — project every `DE_stats` vector; gate power (R4); tag
   sledgehammers with the G4 broad-axis caveat + the **CEGv2 core-essential flag** (§2.2,
   R5); NTC-null p/q recomputed per contrast (R6); check positive-control sign + NTC≈0 or
   set `sign_validated=false` (R7); emit `stage02_perturbation_scores.json`.
   - **2b (optional, Lane C, §2.8):** `score_perturbations_insilico.py` — remote GPU; first
     pass the **model-QC gate** (reproduce FOXP3-KD + held-out KDs) and the **HVG-coverage
     check** (R9b); then in-silico skew anchored on A, with its own null; model-only
     surfaces tagged `model_only`/`CS-complement` (R9).
3. **`stage2_pipeline.py`** — narrative notebook, emit overlay; `verify_reproduce_stage2.py`
   gate; extend `reproduce.sh`; render HTML.
4. **Shortlist → compositional confirmation** on cell-level files (R1/§2.7) — load-bearing
   for the default given the low A∪B fraction.
5. **Hand the ranked candidate-gene table to Stage-3** (§3/§4) — tumor-context +
   druggability (03) then brain-penetrance + safety (04); settle DepMap/NAS access first
   (R10).
