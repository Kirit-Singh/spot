# External-reviewer prompt — dataset decomposition for a Th1↔Treg fate question

_Grounded in the spot Stages 1–2 build (branch `stage1-remediation`, PR #16). Hand this to an
independent senior computational immunologist / single-cell methods reviewer._

---

You are an independent senior computational immunologist and single-cell/perturbation-genomics
methodologist. Your job is **not** to run the analysis — it is to critically decide **how (and whether)
this dataset can be decomposed** to answer a specific biological question **without overclaiming**, and
to specify what would make each claim defensible.

## The biological goal (as posed by the product owner)
"See how CD4 T cells move from a **Th1-like** state at **8 hr** to a **Treg-like** state at **48 hr**,
and reverse-engineer the transcriptional changes that influence those fates."

## The dataset (be rigorous about what it is and isn't)
- **Marson GWCD4i genome-scale CRISPRi Perturb-seq** in primary human CD4⁺ T cells (bioRxiv
  2025.12.23.696273; "Zhu et al. 2026"). 10x Flex (probe-based 3′). Public via the CZI Virtual Cells
  Platform; the embedded NTC object is redistributed at Hugging Face `KiritSingh/spot-CD4-Marson`
  @ `e5fcf98b…` (`ntc_clustered.h5ad` SHA-256 `2edc6d31…`).
- **Design:** 4 donors × {Rest, Stim8hr, Stim48hr}. spot uses a quota-balanced **396,000-cell NTC**
  subset (33k per donor×condition) for the program landscape; a **40,000-cell** display overlay
  (frozen `canonical_table_sha256=6e1665d1…`, `barcode_set_sha256=1224312e…`).
- **Perturbation data:** `GWCD4i.DE_stats.h5ad` (per target×condition differential-expression effects;
  `layers['log_fc']`, `layers['zscore']`; **10,282-gene** effect universe), plus per-guide and
  per-donor-pair (`by_guide.h5mu`, `by_donors.h5mu`).
- **CRITICAL CONSTRAINTS:** this is a **cross-sectional snapshot**, **NOT lineage-traced** — cells at
  8 hr and 48 hr are different cells, not the same cells followed over time. Timepoint is confounded
  with polyclonal activation state. Probe-based 3′ chemistry means gene dropout (e.g. FOXP3 captured in
  a minority of Treg-like cells). n=4 donors; donor D2 diverges.

## What spot has already built (grounding — use it, critique it)
- **Stage 1 (live):** continuous **RNA program-compatibility scores** per cell (Treg-like, Th1-like,
  Th2/Th17/Tfh/Th9-like, differentiation programs) via `score_genes` (panel mean − expression-bin-matched
  control mean, SEED=12345). **No categorical cell-type/fate calls, no p/q.** A frozen `program_registry`
  (`registry_sha256=1ac9f6b2…`) carries the exact panel + control genes. Th9 is `stage2_selectable=false`
  (IL9/SPI1 absent from the effect universe). Live at http://100.117.50.59:8347/.
- **Stage 2 (direct primary):** a **target-masked DE-space projection** of each measured CRISPRi
  knockdown onto the frozen Th1-like/Treg-like scorers → `away_from_A`, `toward_b`, `balanced_skew`;
  every target emitted with full disposition; **no p/q** (`inference_status=not_calibrated`); mask
  `dc3c6512…`; default contrast `26b866f2ad813d71` (treg_like-high → th1_like-high, Stim48hr, all donors).
- **Stage 2 (Perturb2State secondary):** pinned upstream `emdann/pert2state_model` @ `2c2e3095…` (MIT);
  a broad 396k-NTC target signature + LODO/config stability; a **strictly secondary** support lane
  (`model_manifest_sha256=67682f8e…`); coefficients are reconstruction weights, never causal/validation/p.
- Full provenance + hashes in `docs/HANDOVER.md`; the assignment in `docs/spot_buildout_plan.md`.

## What we need from you
1. **Feasibility verdict, stated plainly.** Can the *fate-transition* question ("cells move Th1@8hr →
   Treg@48hr") be answered with this data? Address head-on: the absence of lineage tracing, the
   cross-sectional design, and the activation⇄timepoint confound. Say clearly which claims are
   **not supportable** without orthogonal data (and what that orthogonal data would be — e.g. lineage
   barcoding, protein/functional readouts, an actual time-course of the same cells).
2. **A dataset-decomposition plan** that answers the *defensible* reformulation — (a) how the
   **Th1-like↔Treg-like continuous balance differs across the 8 hr→48 hr window** (per donor,
   cross-sectionally, distributions not fates); and (b) which **gene perturbations causally shift the
   axis toward Treg-like / away from Th1-like** (the genuinely reverse-engineerable part). Specify the
   subsets, comparisons, axes, covariate handling (donor, activation, dropout), and how to keep
   descriptive vs causal vs speculative strictly separated.
3. **Methods judgment.** For pseudotime / RNA velocity / trajectory / fate-probability models on THIS
   data: warranted or not? Under exactly what caveats, and what would each add beyond the perturbation
   levers? If you'd run one, specify the design that would make it hypothesis-generating rather than
   fate-asserting, and the validation it would still require.
4. **Guardrails (non-negotiable, matching this project's remediation).** No fate/lineage/cell-type
   claims inferred from RNA scores; continuous scores, not categorical calls; no biological p/q without
   a calibrated, verified null; public data only; every number traceable to a named source + method +
   hash. Flag anywhere the proposed plan risks re-introducing an overclaim.
5. **Deliverable.** A short written plan: the honest reformulation of the question; the decomposition
   (subsets/comparisons/methods) with covariates and confounds; an explicit table of
   **answerable now / answerable-with-stated-caveats / not-answerable-without-orthogonal-data**; and the
   single most informative next analysis to run against the existing Stage-1 scores + Stage-2 levers.

Assume you can inspect the repo, the live app, and the artifact hashes above. Reproduce or challenge any
number you rely on. Be adversarial about the fate framing specifically.
