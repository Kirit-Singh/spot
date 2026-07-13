# spot Stage-1→Stage-4 buildout — assignment brief (verbatim)

_This document reproduces, word for word, the implementation assignment as provided. It is the authoritative reference for the buildout plan._

---

You are the lead implementation agent for spot, a staged workbench that turns a selected CD4 transcriptional-program contrast into a directionally coherent, brain-delivery-aware drug-repurposing hypothesis for glioblastoma.

Work autonomously from the current head of PR #16 / branch stage1-remediation. Commit 905535c is the reviewed substantive Stage-1 baseline, but later cosmetic UI commits may exist. Preserve those later changes unless they conflict with a correctness requirement below. Do not reset, discard, amend or rewrite history.

Your assignment is to:

1. repair the unsafe live Stage-1 serving boundary;
2. correct the remaining substantive Stage-1 display and handoff defects;
3. implement the Stage-2 direct perturbation analysis;
4. implement Perturb2State as a required Stage-2 secondary analysis;
5. implement executable Stage-3 and Stage-4 vertical slices;
6. integrate the stages into one clean workbench;
7. run an independent adversarial verification;
8. commit, push and deploy only after every applicable gate passes.

Do not return another feasibility discussion or planning memo. Inspect the real files, implement working code, run the available real analyses, generate the derived artifacts, test them, and verify the deployed pages.

===============================================================================
1. NONNEGOTIABLE PRODUCT AND SCIENCE RULES
===============================================================================

- Never invent a statistic. Every displayed number must trace to:
  - a named source;
  - an exact source version/release;
  - a method;
  - a denominator and units where applicable;
  - an immutable artifact or response hash.

- Use public data only.

- Do not bundle proprietary or account-restricted databases.

- Do not use DrugBank, SIDER or DrugComb in the default redistributable path.

- ChEMBL derivatives must carry the required CC BY-SA attribution.

- Open Targets, ChEMBL, LINCS, CELLxGENE, DailyMed, Drugs@FDA, PubChem and public primary literature are acceptable when pinned and attributed.

- Do not train, fine-tune or deploy scLDM or another generative/local foundation model in this pass.

- Perturb2State is required, but it remains secondary to the direct measured perturbation analysis.

- Do not treat model predictions, druggability, signature matching, physicochemical properties or CNS-MPO as biological confirmation.

- Do not emit biological p/q values unless a corresponding null has actually been calibrated and verified. The default Stage-2 path emits no p/q values.

- Do not call a Perturb2State coefficient a causal effect, p-value, inferential standard error or independent validation.

- Do not create forced categorical T-cell labels.

- Preserve Stage 1’s continuous-score design.

- Do not add warning banners, caveat banners, apology copy or repeated editorial prose to the product pages.

- Encode scientific boundaries through:
  - accurate nouns such as Treg-like and Th1-like;
  - typed fields such as measured, predicted, matched, opposed, unknown, underpowered, not_evaluated and not_classifiable;
  - compact evidence-status chips;
  - a single Methods & provenance drawer per stage.

- Do not use red/amber/green as “unsafe/caution/safe.”

- Missing evidence must be missing or not_evaluated, never zero and never safe.

- Keep modules focused and preferably under 500 lines.

- Every reproduced bug must receive a regression test.

- A generator must not verify its own outputs. Independent verification is required.

===============================================================================
2. MULTI-AGENT EXECUTION
===============================================================================

Spawn separate agents. Run them concurrently only when their write scopes do not overlap. If concurrency is limited, schedule them in waves.

Agent A — live_stage1_agent

Owns:

- 01_programs/
- the public-distribution build for Stage 1;
- the Stage-1 live-server replacement.

Responsibilities:

- live deployment repair;
- Stage-1 display correctness;
- program registry;
- Stage-1 selection contract;
- Stage-1 verifier updates.

Agent B — stage2_primary_agent

Owns:

- 02_geneskew/analysis/, except analysis/perturb2state/;
- primary Stage-2 schemas and artifacts;
- primary Stage-2 tests.

Responsibilities:

- target-masked direct program projections;
- eligibility and evidence tiers;
- guide/donor/cell support;
- gene-lever handoff.

Agent C — stage2_perturb2state_agent

Owns:

- 02_geneskew/analysis/perturb2state/;
- Perturb2State-specific tests;
- Perturb2State-specific derived artifacts.

Responsibilities:

- broad target-signature construction;
- pinned Perturb2State execution;
- LODO/configuration/guide stability;
- Perturb2State verification.

Agent D — stage3_agent

Owns:

- 03_druglink/.

Responsibilities:

- target-to-drug mechanisms;
- direction matching;
- GBM immune-context analysis;
- LINCS support;
- DrugCandidateSet.

Agent E — stage4_agent

Owns:

- 04_PKPD/.

Responsibilities:

- drug identity and active-moiety resolution;
- CNS-MPO;
- direct delivery/exposure evidence;
- NEBPI;
- label-based safety and treatment scenarios;
- scorecard set.

Agent F — integration_frontend_agent

Owns:

- _frontend/;
- shared frontend assets;
- shared navigation and cross-stage state;
- public distribution assembly after stage owners finish.

This agent must not silently rewrite the Stage-1 scientific behavior.

Agent G — adversarial_qa_agent

Initially read-only.

Responsibilities:

- independently reproduce formulas and hashes;
- attempt to break schemas and referential integrity;
- test the deployed pages;
- report concrete failures to the owning agents;
- rerun verification after fixes.

The lead agent owns:

- root README.md;
- CLAUDE.md;
- DATA_LICENSES.md;
- the superseded design specification;
- shared schema placement;
- conflict resolution;
- final integration, commits, push and deployment.

Agents must communicate their artifact contracts before integration. Do not allow two agents to edit the same file concurrently.

===============================================================================
3. WAVE 0 — REPAIR THE LIVE SERVER BEFORE ANALYSIS
===============================================================================

The current live host at:

  `http://<SPOT_HOST>:8347/`

has an unsafe serving boundary.

Verified defects include:

- GET /serve.py exposes the server implementation and machine-local paths.
- GET /stage1_pipeline.py exposes the withdrawn forced-label/permutation pipeline.
- GET /verify_reproduce.py exposes the rejected aggregate-count verifier.
- GET /render_notebook.py and /reproduce.sh expose stale code.
- GET /rerun/log returns withdrawn permutation-FDR, forced-call and prevalence output marked successful.
- unauthenticated POST /rerun can run the obsolete pipeline and overwrite only the displayed overlay.

Do not invoke POST /rerun.

Replace the current service before continuing public deployment:

1. Stop the obsolete serve.py process.

2. Create a repo-owned public distribution directory from an explicit allowlist.

3. Serve only:
   - rendered application HTML/CSS/JS;
   - explicitly approved assets;
   - verified derived display artifacts.

4. Do not serve the repository root.

5. Do not serve:
   - Python source;
   - shell scripts;
   - logs;
   - manifests containing local paths;
   - SSH configuration;
   - environment files;
   - NAS or home-directory paths.

6. Remove the Stage-1 rerun client and hidden rerun UI.

7. Remove all public mutation endpoints.

8. Require these responses:

   GET  /rerun/log          → 404 or 410
   POST /rerun              → 404, 405 or 410
   GET  /serve.py           → 404
   GET  /stage1_pipeline.py → 404
   GET  /verify_reproduce.py→ 404
   GET  /reproduce.sh       → 404

9. Source links should point to immutable GitHub commits rather than public copies of executable files.

10. Add a deployment smoke test for the forbidden paths.

11. If a read-only API is later required, it must:
    - accept only validated parameters;
    - read pinned immutable artifacts;
    - perform no shell/SSH execution;
    - perform no filesystem mutation;
    - expose no local paths;
    - return deterministic content keyed by canonical IDs.

Do not redeploy until the current Stage-1 overlay/records verifier passes.

===============================================================================
4. STAGE 1 — CORRECT DISPLAY AND EMIT THE ANALYSIS CONTRACT
===============================================================================

Keep the current visual direction. Ignore ongoing cosmetic choices unless they create a correctness or accessibility failure.

4.1 Sparse display-domain correction

The existing Th9 domain is:

  p02 = -0.01897
  p50 = 0
  p98 = 0

The current fallback maps zero to maximum intensity. In the 40,000-cell display sample, 24,523 cells have th9_like_score == 0.

Replace the fallback with a sparse-aware transform that:

- always maps p50 to 0.5;
- remains monotonic;
- selects the first stored upper quantile strictly greater than p50;
- uses quantiles computed once over the full 396,000-cell universe;
- records the chosen transform and quantiles in metadata;
- returns display_status=degenerate when no usable upper tail exists;
- renders a degenerate field neutrally.

Add regression tests for:

- p02 < p50 < p98;
- p02 < p50 == p98;
- all tied values;
- monotonicity;
- p50 mapping exactly to 0.5;
- low-direction inversion.

4.2 Continuous A/B rendering

Remove the pa >= pb winner-take-all hue assignment.

Use continuous bivariate rendering:

- A color contribution proportional to pa;
- B color contribution proportional to pb;
- co-high cells visibly blend both colors;
- opacity based on max(pa,pb);
- low/low cells remain neutral;
- no A-or-B categorical assignment.

The compact legend must state the actual encoding. This is a legend, not a warning banner.

In contrast mode:

- the right rail must show the active A and B fields;
- hover and cell-detail views must show both A and B values;
- display the scopes and directions;
- display the actual blended color;
- hide or disable the unrelated single-program Color by control.

When contrast mode is cleared, restore the ordinary single-program gradient.

4.3 Display and analysis scopes

Separate:

- display filters;
- analysis condition;
- analysis donor scope.

Use one shared analysis-condition selector for an executable Stage-2 request.

“All conditions” may remain a display option but cannot define an executable Stage-2 contrast.

The primary analysis donor scope is all four donors.

If display filters exclude the selected analysis condition, automatically show the union of the selected axis scope or provide a concise functional state such as:

  Display filter excludes selected analysis condition

Do not use a banner.

4.4 Program registry

Emit:

  stage01_program_registry.json

For each program include:

- schema_version;
- stable program_id;
- score_field;
- display_label;
- family;
- role=primary|sensitivity;
- stage2_selectable;
- panel symbols;
- stable panel Ensembl IDs;
- exact sampled score_genes control symbols;
- exact sampled control Ensembl IDs;
- panel coefficients;
- control coefficients;
- seed;
- scoring method;
- method hash;
- source expression universe;
- source-universe hash;
- display-transform metadata;
- panel/control coverage in the Stage-2 perturbation-effect universe;
- source citation.

The exact frozen control genes are required. Listing only the marker panel is insufficient.

Exclude role=sensitivity fields from the primary A/B selector. Keep them in the single-program Color by selector.

Verify every panel against the released 10,282-gene perturbation-effect universe.

In particular, verify whether IL9 and SPI1 are absent. If both remain absent, Th9 may stay visible in Stage 1 but must have:

  stage2_selectable=false
  stage2_unavailable_reason=no_panel_genes_in_effect_universe

4.5 Stage-1 selection artifact

Emit:

  spot.stage01_selection.v1

Required fields:

- schema_version;
- canonical contrast_id;
- objective;
- one analysis condition;
- donor_scope=all;
- A program ID;
- A score field;
- A direction;
- B program ID;
- B score field;
- B direction;
- Stage-1 method version;
- program-registry hash;
- dataset ID;
- pinned Hugging Face revision;
- source h5ad SHA-256;
- Stage-1 code commit;
- validation status;
- validation reasons;
- noncanonical created_at timestamp.

Supported objectives:

- balanced_a_to_b;
- away_from_a.

contrast_id must hash canonical scientific content only. Exclude timestamps, display labels and UI ordering.

Preflight must reject:

- A == B with identical direction;
- sensitivity fields as primary axes;
- All conditions;
- different A/B analysis conditions;
- incomplete program registry;
- inadequate Stage-2 gene coverage;
- unknown dataset/method hashes.

4.6 Identify genes behavior

Enable Identify genes only after preflight passes.

On click:

1. canonicalize the selection;
2. compute contrast_id;
3. persist or download the exact selection artifact;
4. load a verified immutable cached Stage-2 result, or invoke a pure read-only analysis service over pinned base artifacts;
5. navigate to Stage 2 with contrast_id;
6. never imply a gene was identified when only navigation occurred.

4.7 Page structure

Add:

- standards doctype;
- html lang;
- viewport metadata;
- keyboard and focus behavior;
- accessible labels;
- usable navigation at 390 CSS pixels;
- responsive plot/control spacing;
- an explicit SVG width/height where needed;
- favicon or data favicon.

Remove duplicated editorial scope paragraphs from the page and notebook. Retain one factual scope sentence in Methods & provenance.

===============================================================================
5. STAGE 2 PRIMARY — DIRECT MEASURED PERTURBATION SCREEN
===============================================================================

Rewrite STAGE2_PLAN.md so it describes the implemented method.

Do not construct thresholded A/B cell populations for the primary screen.

The primary method projects the dataset’s measured CRISPRi effects onto the exact frozen continuous Stage-1 scorers.

5.1 Inputs

Use:

- stage01_selection.json;
- stage01_program_registry.json;
- GWCD4i.DE_stats.h5ad;
- GWCD4i.DE_stats.by_guide.h5mu;
- GWCD4i.DE_stats.by_donors.h5mu;
- sgRNA library metadata;
- pseudobulk metadata needed to resolve exact guide membership;
- immutable input_manifest.json.

Pin:

- public URL/version;
- file size;
- SHA-256;
- upstream code commit;
- gene annotation release;
- environment lock;
- software versions.

5.2 Measured effect matrix

For each target-condition row X use:

  GWCD4i.DE_stats.h5ad layers['log_fc']

Never use .X, which is empty.

Use layers['zscore'] only as a precision-weighted sensitivity analysis.

5.3 Exact program projection

For program p:

- P_p = frozen panel genes;
- C_p = exact frozen score_genes controls;
- M_X = target-specific intended-target/off-target mask;
- d_X,g = measured log fold-change.

Compute:

  delta_p(X) =
      mean over P_p minus M_X of d_X,g
      -
      mean over C_p minus M_X of d_X,g

Recompute the panel and control means separately after masking.

Do not simply delete coordinates and L2-renormalize one mixed vector.

Call delta_p a:

  DE-space program projection

Do not call it an exact predicted change in the per-cell Stage-1 score.

Let:

  s = +1 for a high pole
  s = -1 for a low pole

Then:

  away_from_a = -s_A * delta_A
  toward_b    =  s_B * delta_B
  balanced_skew = (away_from_a + toward_b) / 2

For balanced_a_to_b:

- aligned_both requires away_from_a > 0 and toward_b > 0;
- aligned_both ranks before one-sided or opposed results;
- within a tier rank deterministically by:
  1. balanced_skew;
  2. min(away_from_a, toward_b);
  3. stable target ID.

For away_from_a:

- rank by away_from_a;
- retain toward_b as secondary context;
- this objective must be selected before execution;
- do not invoke it adaptively after seeing B results.

5.4 Target and off-target mask

Freeze one conservative guide-specific mask policy before inspecting ranks.

Use a 30-kb neighborhood unless the real sgRNA metadata demonstrates that another already-defined upstream window is the correct reproducible choice.

For each target-condition row:

1. resolve exact contributing guide IDs;
2. join guide IDs to sgRNA metadata;
3. mask the intended target;
4. mask all named genes within the frozen neighborhood;
5. mask resolved alternate-alignment/off-target genes;
6. intersect with the named DE gene universe;
7. emit every sorted mask row;
8. compute a mask SHA-256.

Do not use neighboring_gene_KD or distal_offtarget_flag as gene identities; they are booleans.

Emit:

  masks.parquet

Fields include:

- contrast_id;
- target ID;
- condition;
- guide ID;
- masked gene ID/symbol;
- mask reason;
- distance where available;
- source row hash.

If too little panel/control weight survives, return:

  insufficient_axis_coverage

Do not emit a numeric projection in that case.

5.5 Eligibility and evidence tiers

Emit every target in the selected condition, including excluded targets.

Do not silently remove failures.

Separate:

- source QC;
- Stage-2 projection;
- replication support.

Source fields such as on-target significance are source QC outcomes, not Stage-2 significance.

Use explicit states such as:

- eligible_two_guide;
- eligible_single_guide;
- underpowered_cells;
- low_target_expression;
- no_detectable_source_on_target_repression;
- unresolved_mask;
- insufficient_axis_coverage;
- unavailable_in_condition.

Freeze operational thresholds before viewing Stage-2 target ranks.

Report the full evaluated family size but do not call it a multiplicity family when no p/q values are emitted.

Set:

  inference_status=not_calibrated

Do not emit Stage-2 p/q columns.

5.6 Guide and donor support

Apply the identical target-masked projection to:

- each guide-specific effect vector;
- available donor-pair matrices.

Join by stable IDs, never row position.

The donor artifact contains six overlapping donor-pair matrices over four donors. Treat these as overlapping sensitivity estimates.

Report:

- guide-specific away-A/toward-B/balanced effects;
- guide sign agreement;
- complementary donor-pair effects;
- donor-pair discordance;
- missingness;
- effective donor n=4;
- main versus guide/donor rank stability.

Do not call the six matrices six independent replicates.

5.7 Cell-level support

After the complete direct screen, perform a narrow extraction for the shortlist.

Use selected-condition guide-assigned cells and contemporaneous NTC guides.

Extract only:

- shortlisted targeting cells;
- matched NTC cells;
- A/B panel and control genes;
- frozen QC/stress/proliferation genes;
- target, guide, donor, lane and cell-QC metadata.

Compute the same frozen normalization and program scores.

Aggregate by:

  target × guide × donor × lane

Compare against donor/lane-matched NTC.

Emit:

- away-from-A effect;
- toward-B effect;
- combined effect;
- guide signs;
- donor signs;
- cell recovery;
- total UMI;
- detected genes;
- mitochondrial fraction;
- stress score;
- proliferation/cycle score;
- missingness.

Do not manufacture A-like/B-like fractions.

Use states such as:

- screen_only;
- guide_supported;
- donor_supported;
- cell_level_supported;
- underpowered;
- composition_or_viability_confounded.

===============================================================================
6. STAGE 2 SECONDARY — REQUIRED PERTURB2STATE
===============================================================================

Perturb2State is required.

Pin exactly:

  repository: emdann/pert2state_model
  commit: 2c2e30959ffafadecc6af5d4d7b5bde868ab5313
  license: MIT

Record that Perturb2State is pre-existing upstream software.

spot’s work is:

- the Stage-1-selected contrast;
- broad target-signature construction;
- masking;
- stability design;
- real execution;
- verification;
- UI integration.

6.1 Perturb2State question

The direct screen asks:

  Does this individual measured knockdown move away from A and toward B?

Perturb2State asks:

  Can a sparse weighted combination of measured knockdown signatures reconstruct the desired broader expression signature, and which perturbations contribute consistently?

Perturb2State coefficients are conditional reconstruction weights.

They are not:

- causal effects;
- individual treatment effects;
- biological p-values;
- donor validation;
- independent confirmation;
- proof that one knockdown creates a cell state.

6.2 Broad target-signature construction

Do not use only the sparse Stage-1 panel/control vector as y.

Construct a broader transcriptomic target signature from the full 396,000 NTC cells in the selected condition.

1. Standardize selected A and B scores within donor.

2. Define:

     z_A = +z(score_A) for A-high
           -z(score_A) for A-low

     z_B = +z(score_B) for B-high
           -z(score_B) for B-low

3. Create donor-stratified pseudobulk quantile bins from the continuous scores.

4. Do not create biological cell-type thresholds.

5. Fit, for each readout gene, a donor-aware continuous model such as:

     mean_expression_g ~ z_A + z_B + activation_score + donor

6. For the default Treg-like→Th1-like contrast:

     desired_away_A,g = -beta_A,g
     desired_toward_B,g = +beta_B,g

7. If activation is itself one selected pole, do not add a collinear activation covariate. Record the exact design.

8. Exclude from the readout/evaluation universe:

   - exact A panel genes;
   - exact A control genes;
   - exact B panel genes;
   - exact B control genes;
   - unresolved duplicates;
   - genes absent from the perturbation matrix.

9. The excluded genes may define A/B scores but cannot improve reconstruction metrics.

10. Construct and hash:

    - away_from_A target signature;
    - toward_B target signature;
    - combined_A_to_B target signature.

11. Normalize away-A and toward-B separately before forming the combined signature.

12. Repeat target-signature construction leave-one-donor-out:

    - four LODO signatures;
    - one all-donor signature.

Emit:

  target_signatures.parquet
  target_signature_manifest.json

Include:

- coefficients;
- design matrix;
- donor scope;
- binning method;
- excluded genes;
- normalization;
- gene universe/hash;
- software versions;
- input hashes.

6.3 Perturbation matrix

Use a genes × eligible-perturbations matrix.

Run two frozen lanes:

1. Author-compatible lane:

     DE_stats.layers['zscore']

2. Effect-magnitude sensitivity:

     DE_stats.layers['log_fc']

For every perturbation column:

- apply the identical intended-target/off-target mask;
- replace masked coordinates with the neutral value zero before model scaling;
- record mask hash;
- report retained target-signature coverage.

Use an exact, ordered gene intersection between X and y.

Hash the gene universe.

6.4 Model configurations

Use:

  Perturb2StateModel

Set:

  positive=False

A negative coefficient therefore represents use of the inverse of the measured knockdown signature. For a CRISPRi/inhibition hypothesis, that is opposed rather than supportive.

Freeze a bounded configuration set before viewing target identities:

- PCA off;
- PCA on with prospectively chosen component counts supported by matrix dimensions;
- a small fixed Elastic Net parameter grid;
- fixed seeds;
- repeated gene-fold cross-validation.

Do not choose configurations based on attractive gene names.

Fit separately for:

- away_from_A;
- toward_B;
- combined_A_to_B.

6.5 Evaluation semantics

The package’s built-in cross-validation splits genes.

Label those metrics:

  reconstruction_gene_cv

Do not call them:

- donor CV;
- guide validation;
- perturbation holdout;
- external validation.

Do not interpret get_coefs().coef_sem as inferential uncertainty. It is variation across overlapping model fits.

6.6 Stability analysis

Repeat Perturb2State across:

- all-donor target signature;
- four LODO target signatures;
- z-score effects;
- logFC effects;
- frozen PCA/configuration set;
- guide-specific effect matrices where available;
- donor-pair effect matrices as sensitivity estimates.

For every target emit:

- coefficient per run;
- nonzero-selection frequency;
- positive-coefficient frequency;
- negative-coefficient frequency;
- median coefficient;
- coefficient range;
- rank range;
- LODO sign agreement;
- guide sign agreement;
- donor-pair sensitivity;
- zscore/logFC agreement;
- mask hash;
- target-signature coverage;
- reconstruction metrics.

Freeze the numerical nonzero tolerance before inspecting target identities.

If a categorical support field is desired, freeze its rule before unblinding. Always retain the underlying frequencies and signs.

6.7 Integration policy

The primary direct ranking must remain unchanged when Perturb2State is added.

Perturb2State must not:

- replace the direct ranking;
- rescue an ineligible target;
- rescue a directly opposed target;
- turn a screen-only target into a validated target;
- emit biological p/q values;
- determine desired pharmacological direction by itself.

It may add a required visible secondary support lane:

- perturb2state_selection_frequency;
- perturb2state_positive_frequency;
- perturb2state_negative_frequency;
- perturb2state_lodo_sign_agreement;
- perturb2state_guide_agreement;
- perturb2state_logfc_zscore_agreement;
- perturb2state_support_status;
- perturb2state_model_manifest_sha256.

A human may filter for concordance between the direct screen and Perturb2State.

6.8 Perturb2State outputs

Emit:

02_geneskew/outputs/<contrast_id>/perturb2state/
  target_signatures.parquet
  coefficients.parquet
  reconstruction_metrics.parquet
  stability.parquet
  model_manifest.json
  verification.json

6.9 Perturb2State tests

Add tests proving:

- deterministic outputs under fixed seeds;
- gene-order invariance;
- target-order invariance;
- intended-target masking;
- off-target masking;
- excluded Stage-1 panel/control genes cannot enter evaluation;
- synthetic known contributors can be recovered;
- a reversed contributor receives a negative coefficient;
- shuffled target signatures lose reconstruction performance;
- coefficient SEM is never emitted as a p-value;
- gene-fold CV is never labelled donor validation;
- an ineligible direct-screen target cannot enter the locked set because of Perturb2State;
- direct Stage-2 ranks are identical with and without Perturb2State;
- UI values match full artifacts.

===============================================================================
7. STAGE 2 OUTPUT AND UI
===============================================================================

Emit:

02_geneskew/outputs/<contrast_id>/
  axis.json
  masks.parquet
  screen.parquet
  guide_support.parquet
  donor_support.parquet
  cell_support.parquet
  perturb2state/
  gene_lever_set.json
  provenance.json
  verification.json

screen.parquet must include:

- contrast/run IDs;
- target Ensembl ID/symbol;
- condition;
- stable source-row ID;
- eligibility state/reasons;
- cells/donors/guides;
- source on-target QC;
- source off-target flags;
- mask hash/count;
- A panel/control coverage;
- B panel/control coverage;
- delta_A;
- away_from_A;
- delta_B;
- toward_B;
- balanced_skew;
- direction class;
- z-score sensitivity fields;
- guide/donor/cell-support states;
- Perturb2State summary fields;
- evidence tier;
- desired_target_modulation;
- inference_status.

Stage-2 UI:

- locked contrast and condition;
- full ranked table;
- away-A/toward-B/balanced decomposition;
- guide/donor/cell-support columns;
- Perturb2State selection frequency;
- Perturb2State coefficient direction;
- evidence-tier filters;
- target-detail panel;
- mask details;
- guide/donor effects;
- Perturb2State coefficient distribution;
- LODO/configuration stability;
- source-linked provenance;
- full artifact downloads.

Perturb2State Methods text should be one concise factual sentence:

  Perturb2State fits sparse combinations of measured knockdown signatures to the desired broader expression signature; coefficients are reconstruction weights.

Do not add a banner.

The user action is:

  Lock selected genes for Drug link

That produces gene_lever_set.json.

Each selected target must include:

- target ID/symbol;
- CRISPRi modality;
- observed genetic direction;
- desired_target_modulation;
- direct component scores;
- evidence tier;
- guide/donor/cell support;
- Perturb2State summary;
- mask hash;
- artifact hashes;
- portable desired-signature reference.

===============================================================================
8. STAGE 3 — DIRECTIONAL GENE-TO-DRUG LINK
===============================================================================

Consume gene_lever_set.json generically.

Do not hard-code Treg-down.

8.1 Public sources

Use pinned public sources:

- Open Targets data release/download;
- ChEMBL release/API status;
- PubChem identity/property APIs;
- UniProt/Ensembl mappings;
- optional DGIdb only after exact license/version verification;
- public LINCS GEO releases;
- public GBM single-cell data, preferably GBmap/CELLxGENE.

Cache exact raw responses or release subsets with:

- query;
- release/version;
- retrieval date;
- license;
- SHA-256.

8.2 Directionality

CRISPRi-positive evidence usually proposes reduced target abundance.

Every target–drug edge must include:

- genetic perturbation modality;
- observed genetic direction;
- desired_target_modulation;
- drug action type;
- pharmacologic_effect=decrease|increase|unknown;
- mechanism_direction_match=matched|opposed|unknown.

Examples:

- CRISPRi knockdown favorable + inhibitor → matched;
- CRISPRi knockdown favorable + agonist → opposed;
- binder with unclear functional action → unknown.

Opposed and unknown mechanisms remain visible but cannot enter the primary locked candidate set.

8.3 Drug identity

Canonicalize by active moiety.

Store:

- parent InChIKey;
- ChEMBL molecule ID;
- PubChem CID;
- RxCUI where available;
- salt relationship;
- prodrug relationship;
- active metabolite relationship;
- formulation/route where relevant.

Do not treat salts, parents, prodrugs and active metabolites as interchangeable.

8.4 Mechanism evidence

For every edge store:

- target Ensembl ID;
- UniProt ID;
- ChEMBL target ID;
- drug ID;
- action type;
- directness;
- target type;
- species;
- assay;
- potency value;
- potency relation;
- potency unit;
- assay confidence;
- source document;
- source row/response hash.

Do not globally average heterogeneous potencies.

8.5 GBM immune context

Build an external disease-context lane using public GBM single-cell data.

The question is:

  Is the target and selected program present in GBM-infiltrating T cells across patients?

Use patient/sample as the replicate, not pooled cells.

Separate:

- CD4/Treg-like immune compartment;
- other immune;
- malignant;
- stromal.

Emit:

- dataset/collection/version;
- patient count;
- cell count;
- target-detection summaries by patient;
- target-expression summaries by patient;
- portable program-score coverage;
- program-score behavior;
- compartment;
- supported;
- conflicting;
- not_detected_with_power;
- not_evaluated.

DepMap may remain an optional tumor-intrinsic branch. It must not gate an immune mechanism.

8.6 LINCS lane

Use the exact portable desired Stage-2 signature.

Do not use a generic Treg-down label.

For every signature retain:

- LINCS signature ID;
- compound identity;
- cell context;
- dose;
- time;
- replicate count;
- gene coverage;
- aggregation method;
- source accession/hash.

Freeze aggregation before results.

Never select each drug’s best signature.

Label nonimmune cell-line evidence:

  context_mismatched

LINCS cannot rescue an opposed direct mechanism.

Signature-only candidates may be shown in a separate secondary lane but cannot be silently treated as direction-matched direct mechanisms.

8.7 Stage-3 ranking

Use a versioned lexicographic rank tuple, not a hidden weighted score:

1. mechanism direction matched;
2. Stage-2 evidence tier;
3. direct curated mechanism evidence;
4. GBM immune-context state;
5. Perturb2State concordance;
6. LINCS context/replicate state;
7. development/approval state;
8. canonical active-moiety ID tie-break.

Missing values are not zero.

Stage 3 locks a DrugCandidateSet, not one drug.

8.8 Stage-3 artifacts

Emit:

03_druglink/outputs/<candidate_set_id>/
  target_drug_edges.parquet
  gbm_context.parquet
  lincs_support.parquet
  drug_candidates.parquet
  drug_candidate_set.json
  manifest.json
  verification.json

8.9 Stage-3 UI

Show an expandable evidence-chain table:

  CRISPRi lever
    → desired modulation
    → drug mechanism
    → direction match
    → GBM T-cell context
    → Perturb2State support
    → LINCS support

Primary columns:

- drug;
- lever;
- action;
- direction match;
- directness;
- Stage-2 tier;
- GBM immune context;
- Perturb2State support;
- LINCS context;
- development state;
- evidence tier.

Opposed/unknown mechanisms remain inspectable but cannot be locked.

The user action is:

  Lock candidate set

===============================================================================
9. STAGE 4 — DELIVERY, EXPOSURE AND TREATMENT-CONTEXT EVIDENCE
===============================================================================

Consume the complete DrugCandidateSet.

9.1 Delivery hypothesis

Every candidate must inherit one of:

- local_CNS_target_engagement_required;
- systemic_immune_priming;
- delivery_requirement_uncertain.

Do not assume every immune mechanism requires equivalent free drug concentration inside non-enhancing brain.

9.2 Keep evidence lanes separate

Do not collapse these into one opaque clinical score:

1. CNS-MPO predictive screen;
2. transporter/efflux evidence;
3. measured plasma exposure;
4. CSF exposure;
5. normal-brain or non-enhancing-brain exposure;
6. enhancing-tumor exposure;
7. unbound exposure versus relevant potency/MEC;
8. NEBPI criterion-level evidence;
9. route/dose/formulation-specific half-life;
10. label-based safety and interactions;
11. treatment-scenario evidence.

9.3 CNS-MPO

Implement the published Wager CNS-MPO function exactly.

Inputs:

- ClogP;
- ClogD at pH 7.4;
- molecular weight;
- TPSA;
- H-bond donors;
- most-basic pKa.

For every input store:

- value;
- units;
- experimental or predicted;
- source;
- method;
- version;
- response hash.

Do not impute missing values.

Do not let RDKit stand in for experimental or validated pKa/logD.

Use:

  cns_mpo_status=computed|incomplete

CNS-MPO is a predictive physicochemical screen. It is not measured BBB delivery.

Add golden tests from published examples.

9.4 Transporters

Store P-gp/BCRP evidence with:

- transporter;
- substrate/inhibitor state;
- assay;
- species;
- system;
- concentration;
- source;
- result;
- evidence type.

Do not merge heterogeneous transporter assays into one unsupported boolean.

9.5 Exposure

Store one row per actual measurement:

- active moiety;
- formulation;
- route;
- dose;
- population/species;
- matrix;
- total or unbound;
- concentration;
- units;
- timepoint;
- Kp when reported;
- Kp,uu,brain when genuinely reported;
- study/source;
- evidence hash.

Calculate an exposure margin only when:

- active moiety matches;
- free/total state is compatible;
- units are harmonized;
- biological potency context is relevant;
- route and dose are known.

9.6 NEBPI

Do not calculate NEBPI from CNS-MPO or descriptors.

NEBPI classification requires criterion-level evidence such as:

- therapeutic PK in non-enhancing brain;
- relevant PD in non-enhancing brain;
- radiographic response in non-enhancing disease.

If these data are absent:

  nebpi_status=not_classifiable

Do not classify absent evidence as impermeable.

Apply NEBPI as a primary gate only for:

  local_CNS_target_engagement_required

For systemic_immune_priming, retain delivery evidence without pretending direct brain concentration is the same mechanistic requirement.

9.7 Safety and treatment scenarios

Use current:

- DailyMed SPL labels;
- Drugs@FDA labels;
- EMA labels where relevant;
- primary PK/DDI literature.

Store:

- SPL setid;
- label version;
- exact section;
- boxed warning;
- contraindication;
- warning/precaution;
- labeled interaction.

Separate scenarios:

- temozolomide;
- radiation;
- corticosteroid exposure;
- antiseizure therapy;
- perioperative setting.

Separate:

- pharmacokinetic interaction;
- overlapping toxicity;
- marrow effects;
- infection liability;
- immune activation/autoimmunity liability;
- bleeding;
- QT/cardiac effects;
- mechanistic antagonism.

FAERS may appear only as:

  signal_only

FAERS cannot establish causality, incidence, safety or contraindication.

Do not use a clinical green/amber/red traffic light.

Use evidence states:

- label_supported;
- literature_supported;
- signal_only;
- no_evidence_found;
- not_evaluated.

no_evidence_found must not render as safe.

9.8 Stage-4 artifacts

Emit:

04_PKPD/outputs/<scorecard_set_id>/
  delivery_evidence.parquet
  transporter_evidence.parquet
  safety_evidence.parquet
  scorecards.json
  manifest.json
  verification.json
  selection.json

9.9 Stage-4 UI

Compare all candidates side by side.

Show separate panels for:

- direct CNS/NEB evidence;
- CNS-MPO;
- transporter evidence;
- exposure/potency compatibility;
- half-life by route/dose;
- label warnings;
- named treatment scenarios.

Do not collapse these into one untraceable score.

The final lock records:

- active moiety;
- formulation;
- route;
- candidate-set ID;
- scorecard hash;
- evidence-manifest hash.

===============================================================================
10. CLEAN CROSS-STAGE FRONTEND
===============================================================================

Maintain one coherent spine:

Stage 1 — select an ordered continuous program contrast
Stage 2 — identify measured genetic levers and Perturb2State support
Stage 3 — identify direction-compatible drug candidates
Stage 4 — compare delivery, exposure and treatment-context evidence

Keep the established light palette and typography.

Do not rewrite Stage 1 into React merely for architectural uniformity unless its existing behavior and tests remain intact.

Prefer the shortest working integration path:

- retain the existing Stage-1 static application;
- build Stage-2/3/4 pages around immutable artifacts;
- assemble an explicit public distribution;
- use shared design tokens/assets;
- use URL/canonical IDs for cross-stage navigation;
- use local client state only for human selections;
- never mutate scientific source artifacts from the public browser.

Recommended visual forms:

- Stage 1: UMAP and continuous/bivariate program display;
- Stage 2: ranked table plus target detail;
- Stage 3: evidence-chain table plus candidate detail;
- Stage 4: candidate comparison matrix plus scorecard detail.

Do not add decorative Sankeys or dashboards that obscure evidence.

Every stage must show:

- locked upstream artifact;
- current artifact ID;
- source-linked values;
- compact evidence states;
- expandable provenance;
- complete artifact download;
- human lock action.

===============================================================================
11. SHARED ARTIFACT CONTRACT
===============================================================================

Create versioned schemas for:

- spot.stage01_selection.v1;
- spot.stage01_program_registry.v1;
- spot.stage02_axis.v1;
- spot.stage02_gene_lever_set.v1;
- spot.stage03_drug_candidate_set.v1;
- spot.stage04_scorecard_set.v1.

All scientific identifiers must be content-addressed.

Canonical hashes must:

- use stable key ordering;
- use stable row ordering;
- define float rounding/tolerance;
- exclude timestamps;
- exclude display-only labels;
- exclude machine-local paths.

Cross-stage referential integrity must require:

- Stage 2 references the exact Stage-1 contrast and registry;
- Stage 3 references the exact Stage-2 lever set and desired signature;
- Stage 4 references the exact Stage-3 candidate set;
- every rendered page references the exact artifact it displays.

===============================================================================
12. DOCUMENTATION AND HACKATHON PROVENANCE
===============================================================================

Update root and stage documentation to match the implementation.

Remove stale claims including:

- hard-coded Treg-down where the implementation is generic;
- Stage 3 locking one drug;
- CNS-MPO producing NEBPI;
- green=safe traffic lights;
- DrugBank/SIDER/DrugComb as default sources;
- scLDM training/fine-tuning;
- Perturb2State as independent validation.

Record clearly in provenance—not as a UI banner—that:

- Perturb2State is upstream MIT software by the dataset authors;
- spot’s use, target signatures, stability analysis, integration and results were produced during the event;
- the authors’ existing Th1/Th2 result is not a new spot result.

Update DATA_LICENSES.md using current primary-source terms.

===============================================================================
13. VERIFICATION GATE
===============================================================================

Before committing or deploying, require:

Stage 1:

- 40,000-cell overlay/records agreement;
- canonical per-barcode verification;
- schema whitelist;
- no retired categorical fields;
- sparse-domain tests;
- A/B bivariate-render tests;
- valid selection and program-registry hashes.

Stage 2 primary:

- direct-formula unit tests;
- target-mask tests;
- guide-join tests;
- gene-universe intersection tests;
- row-order invariance;
- complete target disposition;
- no p/q columns;
- deterministic ranking;
- full-record artifact verification.

Perturb2State:

- pinned upstream commit;
- deterministic seeds;
- target-signature hashes;
- panel/control exclusion;
- target/off-target masking;
- shuffled-signature negative control;
- synthetic contributor recovery;
- reversed-sign negative control;
- LODO execution;
- guide/configuration stability;
- zscore/logFC comparison;
- primary-rank invariance;
- no coefficient SEM presented as inference.

Stage 3:

- Ensembl/UniProt/ChEMBL mapping fixtures;
- drug parent/salt/prodrug fixtures;
- direction-mapping tests;
- opposed mechanisms cannot rank as matched;
- heterogeneous potency values remain separate;
- patient-level GBM aggregation;
- deterministic candidate ranking;
- source-response hashes.

Stage 4:

- CNS-MPO golden examples;
- missing CNS-MPO input returns incomplete;
- descriptors alone return NEBPI not_classifiable;
- unit-conversion tests;
- free/total exposure compatibility;
- active-moiety matching;
- label version/section capture;
- FAERS absence never becomes safe;
- deterministic scorecards.

Frontend/live:

- frontend tests;
- typecheck;
- lint;
- production build;
- 390px mobile test;
- desktop interaction test;
- keyboard/focus test;
- displayed counts match artifacts;
- source links resolve;
- no JavaScript exceptions;
- no forbidden public paths;
- no mutation endpoint;
- no machine-local path strings;
- no stale forced-label/FDR strings.

Repository:

- git diff --check;
- no unrelated changes;
- no untracked sensitive files;
- no proprietary data;
- license manifest complete;
- generated files trace to their generators.

After integration, adversarial_qa_agent must independently attempt to falsify:

- all formulas;
- all ranks;
- all evidence-status transitions;
- all cross-stage IDs;
- all displayed values;
- all public endpoint restrictions.

Route reproduced defects back to the owning agent. Rerun the complete gate after every fix.

===============================================================================
14. COMMIT, PUSH AND DEPLOY
===============================================================================

Only after every applicable gate passes:

1. create small intentional commits by stage;
2. do not rewrite history;
3. push the current branch;
4. build the immutable public distribution;
5. deploy the verified distribution;
6. run live endpoint and browser smoke tests;
7. compare deployed bytes/hashes to the committed build.

Do not silently replace the Hugging Face dataset.

If Stage-1 data artifacts change and a Hugging Face update is actually required:

- create a superseding revision;
- preserve history;
- upload only after manifest and hashes pass;
- point the app at the exact immutable revision.

Do not publish a remediation statement or add public editorial copy.

Final handoff must report:

- commit SHA(s);
- PR URL;
- live URL;
- Stage-1 artifact hashes;
- Stage-2 contrast/run IDs;
- Perturb2State model commit and artifact hashes;
- Stage-3 candidate-set ID;
- Stage-4 scorecard-set ID;
- exact tests executed and results;
- public source releases used;
- remaining fields that are genuinely not_evaluated;
- anything that could not be verified and the precise reason.

The task is complete only when the clean Stage-1→Stage-2→Stage-3→Stage-4 path works from the user’s selection through the rendered, provenance-linked artifacts. ultracode and use claude science reviews, but poll consistently to ensure tasks dont get stuck
