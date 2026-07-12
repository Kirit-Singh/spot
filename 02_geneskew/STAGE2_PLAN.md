# spot Stage-2 — gene-lever screen for a Stage-1-selected transcriptional-program contrast

_Design/planning memo. Not implemented. Rewritten 2026-07-10 after verifying every retained
number against the released `GWCD4i.DE_stats.h5ad`, the authors' pinned code, and the scLDM-CD4
model card. Supersedes the prior consolidated plan and both prior Claude reviews
(`STAGE2_REVIEW.md`, `STAGE2_REVIEW_R2.md`), whose load-bearing claims — a `3,341`-knockdown
screen, an NTC-guide null from `DE_stats`, an in-project `CEGv2.txt`, a scLDM lane "conditioned
on A", and a cross-timepoint Treg→Th1 "transition" default — were found factually wrong (§18
disposition table)._

---

## 1. Executive decision and scope

Stage-2 takes an ordered **A→B transcriptional-program contrast** chosen by a human in Stage-1
and produces a **ranked table of gene levers** — knockdowns whose *measured* transcriptional
effect aligns with the A→B program direction — surrounded by power, off-target, replication,
and cell-level gates. It is exploratory decision-support that **nominates** levers for
downstream evaluation. It does **not** confirm a biological transition, and it stops at the
ranked hypothesis: drug, GBM, PK and safety evidence are Stages 3–4.

**Sound core retained (implementation corrected):** (1) a human selects an ordered A→B contrast;
(2) Stage-2 represents it as a signed, versioned program vector; (3) a cheap primary screen
projects *measured* perturbation effects onto that program; (4) results decompose into
movement away-from-A and toward-B; (5) power/off-target/breadth/guide/donor/cell-level gates
surround the ranking; (6) every result carries provenance and stays decision-support; (7)
model-based evidence may suggest, never confirm; (8) Stage-2 ends at a ranked gene-lever
hypothesis.

**Data substrate (verified this session).** The authors' released `GWCD4i.DE_stats.h5ad`
(10,282-gene universe) holds **33,983 target×condition DE summary rows** across **11,526
unique targets**. The effect vectors are the DESeq2 knockdown-vs-pooled-NTC contrast per
target — but **`X` is empty (`encoding-type: null`); the vectors live in `layers/`**:
`log_fc` (the primary `d_{X,g}`), `lfcSE` (the **standard error** of `log_fc`), `zscore`
(`log_fc/lfcSE`, the z-score sensitivity), plus `p_value`, `adj_p_value`, `baseMean`,
each 33,983×10,282. (The contrast is *against* the pooled NTC, so there is no
NTC self-vs-self row — hence §9's null construction.) `GWCD4i.DE_stats.by_guide.h5mu` holds
per-guide matrices; `GWCD4i.DE_stats.by_donors.h5mu` holds **six leave-two-in donor-pair
matrices over the 4 donors** (~4,880×10,273 each; note the 10,273 vs 10,282 gene mismatch,
§13), not per-donor vectors. The cell-level substrate is the twelve
`Dx_<cond>.assigned_guide.h5ad` files (~1.7 TB total).

## 2. What Stage-2 can and cannot claim

**Allowed wording:** *aligns with*, *shifts the measured program*, *regulatory-down*,
*inflammatory-up*, *population redistribution*, *within-dataset replicated*, *cell-level
supported*, *suggestive candidate*, *requires external validation*.

**Forbidden from this one cross-sectional in-vitro dataset:** *proves transition*, *causes
Treg-to-Th1 conversion*, *bona fide / natural / tumor Treg target*, *confirmed target*,
*validated drug target*, *GBM efficacy*, *independent confirmation from scLDM or Perturb2State*.

This is one 4-donor, cross-sectional, in-vitro Perturb-seq dataset with no protein, suppression,
cytotoxicity, or external-cohort measurement in scope. It cannot establish natural-Treg identity,
suppressive function, prevalence, GBM relevance, or generalizability.

## 3. Stage-1 selection contract (unimplemented prerequisite)

**Current reality:** the Stage-1 workbench's population pickers + "identify genes" button only
change tabs; they **serialize nothing**. There is no selection artifact today. Stage-2 depends
on one, so building it is a **Stage-1 prerequisite**, not an existing input.

Specify a versioned **`stage01_selection.json`** carrying at least: schema version;
`contrast_id`; dataset identifier + immutable artifact hash; Stage-1 method/code hash; ordered
A and B population definitions; direction/sign convention; the named condition/timepoint for
each population; **full-population membership hashes or barcodes** (over the frozen full-cell
universe, not the 40k display sample); counts by donor and condition; overlap count + overlap
policy; current donor/condition filters; creation timestamp (noncanonical metadata);
`validation_status` + refusal reasons.

**Reject or explicitly handle:** A == B; overlapping A/B; empty populations; populations that
exist only in the 40,000-cell display sample; inadequate donor representation; timepoints
incompatible with a causal/skew reading (§4). Stage-2 must **not** consume per-cell functional
calls unless those calls exist over the frozen full-cell universe.

## 4. Valid contrast, and axis gates (all start `not_evaluated`)

**Primary default is same-timepoint (Stim48):**
- **A** = activation-induced **FOXP3⁺ regulatory-like** cells/program at Stim48 (never "natural
  Treg", "bona fide Treg", or "tumor Treg" — Stage-1 established induced FOXP3⁺CTLA4⁺ at 48 h,
  not natural Tregs).
- **B** = inflammatory / **Th1-like** cells/program at Stim48.

**One-sided is the HEADLINE, not a fallback (CS review R3).** B's sparsity/donor-stability at
Stim48 is **not measurable from the released files** — the `Dx_Stim48hr.assigned_guide.h5ad`
obs carry no cluster/leiden/celltype/program label, so B cannot be counted until Stage-1
actually clusters the cells (`not_evaluated`). B is also anchored on a *weak pole* — these are
in-vitro anti-CD3/CD28 activations with no Th1-polarizing cytokines, so a canonical Th1 program
is a *prior* to be minority/poorly-polarized at 48 h (a prior, not a measurement — but it
points the same way as the missing labels), and the two-pole `total_skew` inherits that noise.
So: **run both unconditionally, report the one-sided "regulatory-program reduction at Stim48"
as the headline statistic, and let `total_skew` drive ranking only when the G-sep and G-frac
gates on B actually pass.** Stage-2 must not manufacture a two-pole transition when B is
unrepresented.

**Batch structure (verified in `sample_metadata.suppl_table.csv`).** All four Stim48 samples
are in run **R2**, so within Stim48 there is **no run/donor confound** — good for `~ donor +
state`. By contrast the cross-timepoint **48h→8h** comparison is **batch-confounded** (donors
have their 8 h in R1 but their 48 h in R2), so it may be retained **only** as an explicitly
descriptive, batch-confounded sensitivity analysis; it cannot support "transition", "fate
conversion", or causal Treg→Th1 wording.

**Axis gates (evaluated at run time; until then `not_evaluated` — do not pre-declare
"passes"):** (G-sep) A/B separability — significant separating genes; held-out-donor A-vs-B
classifier; count surviving the axis-construction stability rule (§5). (G-frac) **separate A
and B fractions** of the scored condition, each with a named denominator (see §13 — there is no
single `a_union_b_fraction`). (G-sign) sign-validation state per contrast — the sign is
mathematically fixed by the A/B labeling; whether it is *behaviorally* validated depends on an
executed positive control, which most contrasts will not have. (G-breadth) broad-axis flag —
whether the axis overlaps a proliferation/translation direction such that specificity heuristics
degrade. Every gate value is `not_evaluated` until an executed result fills it.

## 5. Same-timepoint program construction (the A→B axis)

**Primary method: donor-paired raw-count pseudobulk.** Do **not** depend on a saved Stage-1
scVI checkpoint — none exists in the repo (`run_scvi_embedding.py` is absent; the shipped h5ad
has empty `.uns`/`.obsm`).

1. NTC reference cells from one common condition (default Stim48).
2. Define high-confidence A and B populations symmetrically.
3. Aggregate **raw integer counts** by donor×state.
4. Fit a paired donor-aware DE design, e.g. `~ donor + state`.
5. Use **shrunk log-fold-change** as the biological weight: `w_g = shrunk logFC(B vs A)`
   (positive `w_g` = B-associated; negative = A-associated).
6. Require adequate expression + directional stability under **leave-one-donor-out (LODO)**.
7. Remove unstable / near-zero genes by preregistered rules.
8. L2-normalize the final vector.
9. Save stable Ensembl IDs, display symbols, annotation release, gene universe, preprocessing,
   software versions, and input hashes.

**Circularity control.** If markers define A/B, separate: **anchor genes** (used to select
high-confidence cells), **readout genes** (used to estimate/validate the broader axis), and
**anchor-only explanatory scores**. Do **not** present scVI-vs-DESeq2 sign agreement *on the
same cells* as independent replication; scVI may be a sensitivity analysis only if an audited,
saved, pinned model later exists.

## 6. Primary target-masked measured-effect screen

For perturbation X, use its **measured** effect vector in the condition where A exists —
the **`layers['log_fc']`** row (`d_{X,g}`; `X` is empty). Use **`layers['zscore']`**
(`log_fc/lfcSE`) **only** as a sensitivity analysis — it mixes effect magnitude with
precision/sample size (`lfcSE` alone is the standard error, not a score).

**Target mask (before any projection).** Define `M_X` = the intended target X **plus its
guides' off-target genes**. Note the DE_stats `neighboring_gene_KD` (2,619 True) and
`distal_offtarget_flag` (433 True) obs fields are **booleans** — they flag *that* a row has
such an effect, **not which genes** to mask. The off-target gene identities live in
`sgrna_library_metadata.suppl_table.csv` (`nearby_gene_within_2/10/20/30kb`,
`nearest_within2kb_nontarget_gene_id/name`, `nearest_nontarget_gene_id/name`), so `M_X` is
built by **joining the sgRNA library to X's guides** — the neighborhood window (2/10/20/30 kb)
is a prospectively-frozen choice. Compute scores **only on genes not in `M_X`**; because the
"unmasked score is self-fulfilling" safeguard rests entirely on masking the right genes, this
join is load-bearing, not cosmetic. For **FOXP3 KD, FOXP3 itself is masked** — direct FOXP3
repression is QC only, not skew evidence.

**Primary endpoint — `a_down` only.** To avoid three adaptively-selectable outcomes, the **sole
primary endpoint is `a_down`** (reduction of the A / Treg-like program — the measurable pole).
`b_up` (B / Th1-like increase) and `total_skew` (full A→B alignment) are **secondary /
descriptive**: B may be sparse and is not well estimated until it is measured, so they never drive
ranking on their own.

**Score equations (target-masked, coverage-gated).** With the frozen axis weight vector `w`:
(i) split into `w_full`, `w_Adown` (A-associated / negative-`w` coordinates), `w_Bup`
(B-associated); (ii) **remove `M_X`** (target + off-target genes) from each; (iii) **renormalize
each retained vector to unit L2 *separately***; (iv) `a_down(X) = ŵ_Adown · d_X`,
`b_up(X) = ŵ_Bup · d_X`, `total_skew(X) = ŵ_full · d_X`. Report the **retained squared-weight
coverage** (`Σw²_retained / Σw²_total`) for each and **refuse a score whose coverage falls below a
prospectively-frozen threshold** (mask removed too much of the axis). The pseudo-NTC null (§9) is
computed with the **identical target-specific mask and renormalization**, so observed and null
share the same transformation. Report the descriptive class per row (*A-down* · *A-down + B-up* ·
*B-up only* · *broad/non-specific* · *unsupported/underpowered*) — but rank on `a_down`.

**Composition confound is present at the screen stage (say so here, not only in §10).** Even
with a correct target mask, `total_skew` is computed on **whole-condition bulk** KD-vs-NTC
vectors, so a KD that shifts *population composition* (kills activated cells, stalls
proliferation) moves the bulk vector along the axis with **zero cell-intrinsic reprogramming**.
The primary ranked table therefore mixes intrinsic reprogramming with composition shift;
`screen_only` hits **must not** be read as intrinsic until §10 (viability/UMI/cycle) separates
them. §10 is doing load-bearing deconfounding that the ranked table's framing must advertise.

**FOXP3-KD caveat (verified) — sign control stays `not_evaluated` until the projection is run.**
The released FOXP3 Stim48 row has `ontarget_significant = True` with **n_total_de_genes = 4,
n_downstream = 3** (n_cells = 1,360) — but that is a *whole-transcriptome* DE count, **not** its
target-masked projection onto the A→B axis, which has not been computed. So **do not pre-conclude
FOXP3-KD is "too quiet"**: its sign-control status is `not_evaluated` until the masked projection
exists. When (and only when) that projection is computed and found underpowered, the sign is
reported as mathematically-fixed-but-unvalidated (`sign_validated = false`), surfaced wherever a
hit is reported, with no substitute control invented to manufacture validation. FOXP3-KD is
QC context, **not** an
automatic pass/fail gate.

## 7. Eligibility and power gates (pre-outcome only)

**Do not describe `3,341` as the number of gene knockdowns or the multiplicity family.**
Verified counts in `DE_stats`: 33,983 target×condition rows; 11,526 unique targets; **11,281
Stim48 rows**; the `3,341` figure is the count of rows that *already* passed the authors'
**outcome** filter (`n_total_de_genes > 75` and `n_cells_target > 50`), representing **1,860
genes** — an ascertainment on effect size, not an eligibility criterion.

**Eligibility uses only pre-outcome criteria:** target measurable; adequate target-cell count;
adequate donor coverage; preferably ≥2 guides; detectable on-target repression; no disqualifying
off-target evidence. **Never** select targets because they already produced many DE genes. Emit
the **actual tested family size at run time** and correct multiplicity over that family (§9).
**Neither 11,281 nor 7,195 is "the correction family."** In Stim48, the *source's* observed
`ontarget_significant == True` holds for **7,195** rows (`low_target_gex` for 2,431;
`n_cells_target > 50` for 11,146) — but 7,195 is just *the source's own observed on-target test
count*, **not** the pre-outcome eligible family. The **actual tested family only exists after all
frozen Stage-2 design filters run** (target measurable + adequate cells/donors + guides +
detectable repression + no disqualifying off-target), and its size is emitted at run time. And in
the **default no-p/q lane there is no multiplicity correction at all**, so no "correction family"
is claimed; the family size is reported for transparency only. 11,281 must never read as a
multiplicity denominator anywhere.

Gate on `DE_stats.obs`: `ontarget_significant == False` → "**no statistically detectable
on-target repression under the source analysis**" (not "the gene wasn't knocked down");
`low_target_gex`, small `n_cells_target`, `single_guide_estimate` → **insufficient-power tier**,
reported separately, never mixed into ranked hits.

## 8. Guide and donor replication (direct, along the axis)

Generic whole-transcriptome guide/donor correlations (`guide_correlation_*`,
`donor_correlation_*`) are **supplementary QC**, not replication. Require **direct target-masked
projections** onto the A→B axis computed on: guide 1; guide 2 (`by_guide.h5mu`); the donor-pair
effect matrices (`by_donors.h5mu`).

**Be honest about the released granularity (CS review R3):** `by_donors.h5mu` ships **six
leave-two-in donor-*pair* matrices over 4 donors total** (~4,880×10,273 each), **not** per-donor
vectors — true leave-one-donor-out on the DE side is **not** in the released files (it would
require recomputing from cells). The six pair matrices **overlap** (each donor appears in several
pairs), so they are **not six independent replicates**: analyze the **three complementary
2-vs-2 splits** and retain **effective donor n = 4**. Report **donor-pair *discordance*** (sign
disagreement across the complementary splits), not a "donor-reversal flag" that implies
independent donor votes, and do not present this as higher-resolution LODO than the release
supports.

Record: guide-specific `a_down` (+ secondary `b_up`/`total_skew`); guide sign agreement; the
three complementary split scores; **donor-pair discordance**; pair-level rank stability;
missingness and effective replicate count (n = 4).

## 9. Significance / null policy

This is the null for the **skew/axis-projection statistic** — a weighted sum across genes.
`DE_stats` already ships **per-gene** DE significance (`layers['p_value']`, `layers['adj_p_value']`,
both 33,983×10,282), but **those per-gene q-values do not calibrate the projection score**; §9
concerns the skew statistic specifically, not the per-gene DE. `GWCD4i.DE_stats.h5ad` contains
**no per-NTC-guide DE vectors** (verified — no NTC target in the table; the only control-string
target `KNTC1` is a real kinetochore gene), so raw NTC expression **cannot** be projected as if
it were a target-vs-NTC DE statistic. Choose **one honest state** and label it:

- **(A) Calibrated inferential null:** construct many **pseudo-target groups from NTC guides**
  (the cell-level `guide_type` field has a real `non-targeting` category, so this is available;
  matched on guide count, cell count, donor/run, condition; pseudo-target guides removed from
  the control pool). **Cross-fit the NTC cells: the NTC used to build the A→B axis must be a
  *disjoint* split from the NTC used to build the pseudo-target null** — reusing the same NTC
  cells for both makes the null optimistic even with a frozen axis. Then **rerun the identical
  upstream DE model**; **project the pseudo-target vectors onto the *same frozen A→B axis*,
  under the identical target-mask + renormalization (§6) — permute only the target vectors,
  never re-estimate the axis per pseudo-target** (re-estimating conflates axis-estimation noise
  into the null);
  validate null-p calibration + tail behavior; freeze and hash the null artifact; account for
  **all interactively attempted contrasts**.
- **(B) Hackathon default:** report effect sizes, guide/donor stability, and uncertainty; **do
  not emit p/q**; mark significance `not_calibrated`.

**No undefined "parametric fallback."** Any parametric model requires a named distribution,
fitting procedure, calibration diagnostics, and refusal rule fixed **before** inspecting
attractive hits.

## 10. Cell-level within-dataset support (before the Stage-3 handoff)

Cell-level analysis happens **before** the final handoff, not after a count-only verifier. Using
real **Stim48 guide-assigned cells**: (1) freeze the target-masked regulatory-like and
inflammatory-like scorers; (2) score real perturbed cells; (3) aggregate by
target×guide×donor×library; (4) compare with contemporaneous NTC guides; (5) model continuous
regulatory and inflammatory scores; (6) separately model A-like / B-like population fractions;
(7) report cell recovery, UMI depth, stress/apoptosis, and cell-cycle/proliferation outcomes.

A lower A-like fraction may reflect death, proliferation, activation delay, or guide recovery —
**do not call UMAP displacement a transition or fate conversion.** Status terms: `screen_only`,
`within_dataset_replicated`, `cell_level_supported`, `underpowered`, `confounded`. **Never
`confirmed`** — one in-vitro dataset cannot independently confirm the hypothesis. Emit separate
artifacts: full measured-effect screen · within-dataset-replicated shortlist · cell-level-
supported shortlist · explicit `external_validation_needed` state.

## 11. Secondary lane — Perturb2State (cited upstream, secondary)

Perturb2State is **pre-existing upstream MIT software** (authors' pinned repo
`emdann/pert2state_model@2c2e309`; notebook `4_polarization_signatures/pert2state_polarization`).
It solves approximately `desired_state_signature(gene) ≈ perturbation_effect_matrix(gene×target)
· coefficients(target)`. Use it **separately** for a regulatory-down signature and an
inflammatory-up signature, as a **stability** lane only.

Safeguards: mask each KD's intended target + flagged off-target coordinates; repeat across guide
matrices; repeat across LODO-derived state signatures; vary regularization within a preregistered
range; report nonzero/sign-selection frequency + rank stability. **Do not** treat coefficient
magnitude or SEM as a causal effect, inferential SE, p-value, or q-value; acknowledge that
correlated KDs substitute for one another, and that gene-fold CV is not donor or external
validation. Output is a `perturb2state_support` / stability field; it **cannot rescue** a target
that fails direct measured guide/donor/cell evidence.

**Hackathon provenance:** Perturb2State is upstream; spot's new work is the selected contrast,
the primary target-masked screen, the stability application, the validation, the UI, and the
analysis produced during the event. **Do not present the authors' existing Th1/Th2 result as a
new spot finding.**

## 12. Optional / deferred appendix — scLDM-CD4 (no training)

**Remove scLDM training or fine-tuning from the executable v1 plan.** The released scLDM-CD4
conditions **only** on `donor_id`, `guide_target_ensembl`, `experimental_perturbation_time_point`
(verified in the pinned config) — it has **no Stage-1 regulatory-state condition**. Adding a
post-KD state label would condition on the outcome and could not identify a transition from an
unobserved pre-KD state.

If retained at all, it is a **bounded model-QC appendix**: pin code/checkpoint/config hashes
(`czbiohub-chi/scldm_cd4@cf9034a`, weights `biohub/scldm_cd4`); run only on a **preregistered set
of measured held-out KDs and NTCs**; compare against a simple measured-effect / shrinkage
baseline; use target-masked program effects; retain **only** if it adds held-out predictive
value; **never** derive biological p-values from synthetic-cell counts; **never** promote a
model-only candidate; do not use unseen condition combinations or multi-KD generation. An optional
frozen-encoder linear readout may be mentioned, but must beat simple program scores on held-out
donors to justify inclusion.

## 13. Output schemas and Stage-3 handoff

Organize all artifacts by immutable `contrast_id` / `run_id` — **static filenames must not
overwrite different contrasts.** Schemas are contrast-parameterized and generic (no hard-coded
`foxp3_logfc` / `ctla4_logfc`; use generic anchor-effect mappings). Use **separate A and B
fractions with named conditions and denominators** — remove any singular `a_union_b_fraction`.

**`stage02_programs/<contrast_id>.json`** — program/contrast/run IDs; immutable
selection/input/method hashes; stable Ensembl IDs + annotation release; weights; sign convention;
gene universe; preprocessing/scaling contract; reference means/SDs if portability requires;
missing/duplicate-gene policy — **resolved on a named common gene set** (the main `DE_stats`
universe is 10,282 genes but the `by_donors` pair matrices are 10,273; project everything on the
explicit intersection, recorded by hash); gene-coverage threshold; anchor definitions; donor
stability; axis gate results (`not_evaluated` until run); status fields.

**`stage02_screen/<contrast_id>.parquet`** — one record per eligible target×condition: contrast +
program IDs; target identifiers; condition; target-masked `a_down` / `b_up` / `total_skew`;
effect-size + z-score sensitivity; guide-specific results; donor / donor-pair results; on-target
evidence; source off-target flags; cells/guides/donors; breadth + essentiality flags; uncertainty;
p/q **only if calibrated** with exact correction-family / null provenance; status + limitations;
**desired pharmacological modulation** (e.g. inhibition when a CRISPRi-positive result implies
inhibition is desired). Generic `anchor_effects: {anchor_gene: logFC}` replaces hard-coded FOXP3/
CTLA4 fields.

**`stage02_cell_support/<contrast_id>.parquet`** — continuous regulatory / inflammatory effects;
abundance effects; guide/donor/library estimates; uncertainty; recovery/UMI/cycle/stress outcomes;
power status; within-dataset support verdict; `external_validation_required` flag.

**Handoff to Stage-3:** the ranked gene-lever table + the portable program vector. Everything
tumor-context, druggability, brain-penetrance, and safety is Stage-3/4 (unchanged), designed only
enough here to shape the handoff.

## 14. Reproducibility and input manifest

Specify: an **immutable input manifest** (public URL, S3/version identifier, content length,
downloaded SHA-256 for each input h5ad/h5mu); **pinned upstream code commits**
(`emdann/GWT_perturbseq_analysis_2025@848d62f`, `emdann/pert2state_model@2c2e309`,
`czbiohub-chi/scldm_cd4@cf9034a`); a pinned environment/lockfile; deterministic seeds **only where
sampling is actually used**; **canonical outputs excluding wall-clock timestamps**; **exact
full-record verification** (not top-N) — full program-weight verification, schema validation,
duplicate/missing-record checks, a numerical-tolerance policy; small fixture tests; a full-run
integration verification.

**Do not claim:** that a saved Stage-1 scVI model exists; that `run_scvi_embedding.py` exists; that
the current renderer executes a notebook; that top-N / FOXP3-rank verification establishes full
reproduction. A rendered static report is a **provenance report**, not an executed notebook, unless
generated from a genuinely executed notebook/workflow.

## 15. UI execution contract

After the user clicks **"identify genes"**: (1) validate A/B (§3–4); (2) serialize
`stage01_selection.json`; (3) compute/retrieve `contrast_id`; (4) load a pinned cached Stage-2
result when available, else submit a **reproducible backend job**; (5) display the **full** screened
table; (6) clearly distinguish `screen_only` vs `within_dataset_replicated` vs
`cell_level_supported`; (7) preserve the selection across refresh/share; (8) **never show a gene as
"identified" when only navigation changed.** For the hackathon, precomputing all valid
same-timepoint picker combinations is acceptable **iff** every result maps to the identical locked
contrast and reproducible pipeline.

## 16. Risks and the external-validation boundary

- **One dataset, cross-sectional, in-vitro, 4 donors.** Cannot establish natural-Treg identity,
  suppressive function, prevalence, or GBM relevance. Every hit is a *suggestive lever requiring
  external validation*.
- **Whole-condition ascertainment (R1).** Effect vectors are the condition's bulk response; the
  A-like subset is small — quantified per contrast by the separate A/B fractions (§4, §13) and
  gated by §10 cell-level support.
- **Off-target / masking (R2).** A KD's own on/near/off-target genes must be masked or the score is
  self-fulfilling; relies on the source off-target flags being complete.
- **No calibrated null by default (R3).** Without §9(A), significance is `not_calibrated`; ranking
  is by effect size + stability, not p/q.
- **Correlated regulators (R4).** In Perturb2State and in co-functional modules, correlated KDs
  substitute for one another — coefficient selection is not causal attribution.
- **GO / essentiality unresolved (R5).** See §17 unresolved decisions.

## 17. Three-day execution order (engineering estimates, not measured runtimes)

**Day 1:** selection schema + a valid same-timepoint default; NTC donor-paired axis; target-masked
measured-effect screen over **all eligible Stim48 rows**; direct guide/donor projections;
preliminary UI output.
**Day 2:** cell-level narrow extraction + guide×donor×library aggregation; regulatory/inflammatory
continuous-score and abundance models; recovery/cycle/stress checks; Perturb2State stability lane.
**Day 3:** null calibration **if feasible**, else explicitly withhold q-values; LODO + axis
sensitivity; exact artifact verifier; documentation, provenance, UI, demo.

The **1.7-TB cell-level pass is I/O-bound** and may require a shortlist if a one-pass extraction
cannot finish; if shortlist-only confirmation is used, acknowledge ascertainment and do **not**
call the full screen cell-supported.

## 17b. Temporal cross-condition estimator (implemented — full method: `STAGE2_TEMPORAL_METHOD.md`)

The descriptive cross-timepoint lane §18 reserved ("48→8h only as descriptive sensitivity"), now
with an explicit estimand, an explicit confound policy and an independent verifier.
`estimator_id: spot.stage02.temporal_cross_condition.v1`; `inference_status: not_calibrated`.

**Estimand.** For a target and an **ordered** condition pair, per arm independently:
`temporal_did(arm) = arm_value(arm, to_cond) − arm_value(arm, from_cond)`, where `arm_value` is
**exactly** the within-condition arm value from §6 — the same masked program projection, computed
by the same code path (`run_screen.condition_rows`). The within-condition value is already a
difference (panel mean − control mean after `M_X`), so this is a **difference-in-differences on
program projections**.

It is a **population-level** change in a program projection between two condition populations. It
is explicitly **not** lineage tracing, **not** fate mapping, **not** a per-cell transition
probability and **not** a rate — the release fits each condition as a separate cell population.
No rate, velocity or slope is emitted, and no function exists that could produce one. Both arms
stay separate: **no combined temporal objective, no headline temporal rank.**

**Coverage.** All **six directed comparisons** over {Rest, Stim8hr, Stim48hr}, both directions.
**None is refused** — a confounded pair is flagged and badged, never withheld.

**Batch policy** (locked from the `20260712T021343Z` batch diagnostic; verdict MODERATE; hashes
pinned in `analysis/direct/temporal/batch_policy.v1.json`). Batch is perfectly aliased with donor
(R1={D1,D2}, R2={D3,D4} in Rest/Stim8hr; Stim48hr is R2-only). The **additive** batch effect is
negligible (0.12–0.42 % of variance), sign-inconsistent, and **cancels in the DiD** — **no
correction is applied**. The flag is **derived, not declared**: a pair is
`batch_partially_confounded` exactly when some donor sits in a different replicate at the two
endpoints. This reproduces the locked verdict without naming a condition:

- **Rest ↔ Stim8hr — CLEAN.** Identical composition; batch cancels; no flag.
- **Any Stim48hr pair — `batch_partially_confounded`.** D1,D2 flip R1→R2; D3,D4 do not.

A **pure batch effect is not identifiable** (aliased with donor; no R1 Stim48hr exists) — it can
only be bounded, never measured. Every record carries that note.

**Reliability threshold.** The interaction noise floor is 0.6×–2.0× the temporal signal, so
per-target Stim48hr calls are fragile. Per arm, from that arm's own program:
`|temporal_did| ≥ k × interaction_std(program)`, **k = 2.0** (frozen before any result), with
`interaction_std` the diagnostic's per-program batch-aligned split value (≈0.16 `diff_naive`,
0.08 `diff_memory`, 0.47 `diff_checkpoint`, 0.76 `cd4_ctl_like`). The badge is a **precision
statement, not a significance test**; the exact threshold, k and ratio ship on every record. An
unmeasured floor yields `interaction_floor_unavailable_for_program` — never a pass by default.
Extra-caution: `th17_like`, `th2_like`, `tfh_like` (sparse panels, r≈0–0.15); `th9_like` listed
though non-selectable.

**Display policy — METHODS-ONLY.** These are machine fields for provenance. The UI renders **no
inline batch flag and no reliability badge**, applies **no hard filter**, and shows **all
comparisons plainly**. The 48-hour confound and the precision limitation are documented **once**
(here / `STAGE2_TEMPORAL_METHOD.md`) and surfaced via the **methods/provenance drawer** — never as
a per-comparison caveat in the main canvas. The policy is bound into the method hash.

**Additivity.** `code_tree_sha256` lists only the `.py` files directly in the direct package, so
the `temporal` subpackage is invisible to it and the dependency is one-way. **No temporal code can
move a within-condition score, rank, tier or `run_id`** — enforced structurally and numerically
against a golden screen hash captured before any temporal code existed.

## 18. Unresolved preregistration decisions, and the prior-defect disposition

**Preregistration still required (record the choice before inspecting hits):** exact
A/B high-confidence definitions + anchor/readout split; the axis stability thresholds and
near-zero-gene rule; the eligibility thresholds (cell/donor/guide minima) and the multiplicity
family; whether §9(A) or §9(B); the cell-level power thresholds and status cutoffs; the
Perturb2State regularization range and stability cutoffs; whether the scLDM appendix runs at all;
the GO input/background/database-version, or its removal; the essentiality-list source, license,
version, and SHA-256, or its removal.

**Disposition of prior defects** (verified against code/data this session):

| Prior claim / defect | Disposition |
|---|---|
| Default `induced-Treg(48h) → Th1(8h)` sold as a transition | **closed (§17b, implemented)** — same-timepoint default stands; the cross-timepoint lane ships as an explicit **population-level difference-in-differences on program projections**, `inference_status: not_calibrated`, declared **not** lineage/fate/rate, with a derived batch-confound flag and a per-program reliability floor |
| "natural / tumor Treg" language | **plan corrected; impl. pending** — "activation-induced FOXP3⁺ regulatory-like" only |
| `~3,341` gene knockdowns / screen family | **plan corrected; impl. pending** — 3,341 is a post-hoc outcome filter (1,860 genes); family is the 11,281 Stim48 rows under pre-outcome eligibility |
| NTC-guide empirical null from `DE_stats` | **plan corrected; impl. pending** — DE_stats has no NTC-guide DE vectors; §9(A) rerun-the-model or §9(B) `not_calibrated`; no undefined parametric fallback |
| Self-target contribution to KD score | **plan corrected; impl. pending** — target + off-target mask `M_X`; FOXP3 masked in its own KD |
| FOXP3-KD as automatic sign gate | **plan corrected; impl. pending** — FOXP3 Stim48 has 4 DE / 3 downstream; QC only |
| `condition on A` / scLDM state-conditioning | **plan corrected; impl. pending** — model conditions only on donor/guide/timepoint; scLDM demoted to optional QC appendix, no training |
| `CEGv2.txt` "already in-project" | **plan corrected; impl. pending** — absent from repo; essentiality **unresolved** (§17) pending a pinned, licensed source |
| `a_union_b_fraction` | **plan corrected; impl. pending** — separate A/B fractions with named denominators |
| Hard-coded `foxp3_logfc`/`ctla4_logfc` in a "generic" schema | **plan corrected; impl. pending** — generic `anchor_effects` mapping |
| Stage-1 selection "artifact" that doesn't exist | **plan corrected; impl. pending** — declared an unimplemented prerequisite (`stage01_selection.json`) |
| Saved scVI checkpoint / `run_scvi_embedding.py` dependency | **plan corrected; impl. pending** — primary axis is donor-paired pseudobulk; no scVI dependency |
| Cell-level support after the verifier | **plan corrected; impl. pending** — moved before the Stage-3 handoff |
| GO enrichment promised in README | **deferred/unresolved** — specify (§13/§17) or remove from README |
| Tumor-context / druggability / brain-penetrance | **deferred with explicit boundary** — Stages 3–4 |
| External biological confirmation | **unresolved by design** — requires an independent dataset / protein / suppression / cytotoxicity assay |

**Retained statistics, each with provenance (verified 2026-07-10 from
`GWCD4i.DE_stats.h5ad` unless noted):** 33,983 target×condition rows; 11,526 unique targets;
11,281 Stim48 rows (Rest 11,287 / Stim8hr 11,415); 3,341 rows pass `n_total_de_genes>75 &
n_cells_target>50` = 1,860 genes; 10,282-gene DE universe; FOXP3 Stim48 = 4 total / 3 downstream
DE genes (1,360 cells); Stim48 `ontarget_significant` = 7,195 (source's observed test, **not** an
eligibility family, §7); off-target flags `neighboring_gene_KD` = 2,619 / `distal_offtarget_flag`
= 433 (booleans, §6); `by_donors` = six 2-vs-2 pair matrices, 10,273 genes, n = 4 donors (§8); all
four Stim48 samples in run R2 (from `sample_metadata.suppl_table.csv`, §4). Every figure above
carries its source and denominator; no other quantitative claim is asserted as a Stage-2 result.
