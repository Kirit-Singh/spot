# Stage-1 Continuous-Scoring v3 — Final Lock Implementation Plan

> **For agentic workers:** Execution is **delegated to the Claude Science specialist on tcefold**
> (91 GB). The **lead session plans and independently verifies** (generator ≠ verifier). Steps use
> checkbox (`- [ ]`) tracking. Do not touch v2 artifacts except to mark them superseded.
>
> **Rev 4 (2026-07-11):** bins frozen to the **÷N** form `bin=floor((rank−1)*25/n_finite)`,
> `n_finite=18,130` (no top clamp; ÷(n−1) rejected); pool terminology split into `assay_present` (18,130)
> / `detected_in_396k` (17,956) / `control_eligible_pool` (17,903 = detected − 53); normalization is
> "target total 9,819 with float roundoff" (matrix hash is the identity check, not exact equality);
> scoring is **chunked on tcefold** (frozen coefficient matrix, backed CSR 10k–25k-cell chunks, RSS
> smoke-test first); proceed-order = regenerate → verify → commit defs+gates → configure+smoke tcefold →
> authorize scoring.
>
> **Rev 3 (2026-07-11):** gates are **pre-registered before scoring**; the input manifest + coordinates
> are pinned **before** control construction; the exact bin formula is frozen (with the corrected
> tcefold audit); keyed-hash encoding/namespace/digest-tie fully specified; the activation-predictor
> draw has a stable program_id; the selection contract is placeholders (not a literal instance);
> "all-marker-excluded comparison" is redefined as a v2→v3 change report; gate metrics carry concrete
> thresholds; raw artifact hashes live in a separate release manifest (no self-referential file hash).
> (Rev 2: coordinates/overlay split; input-normalization language; "program-order-invariant" not
> "independent"; canonical hashing + solver lock; "visual design unchanged".)

**Goal:** Re-lock Stage-1 as a frozen, reproducible *measurement* system for continuous
transcriptional programs — with **program-order-invariant** control draws — emitting the full 396k
score table under **pre-registered** validation gates, without any visual redesign.

**Architecture:** Inputs are pinned first; panels + controls are frozen and independently verified;
gates are authored and committed **before** any scores exist; then one deterministic 396k run emits the
scores + registry + summary + overlay; validation runs separately against the pre-registered gates;
the release bundle + raw-hash manifest is assembled last. The single score-changing edit is the
control-pool redesign (Task 2). Stage-2 is **not** re-run here — its v2 artifacts are marked superseded.

**Tech Stack:** Python (vectorized scoring, numpy/scipy/anndata/pandas/pyarrow) in a **solver-locked**
conda env on tcefold; keyed SHA-256 sampling; raw-file + canonical-content SHA-256; the hardened
static-server + `verify_reproduce.py` gate.

## What "locked" means (non-negotiable framing)
A frozen, reproducible measurement of specified RNA programs. It does **not** mean RNA has confirmed
bona-fide Treg/Th1 identity, nor that the programs are biologically or statistically **independent**.
Removing cross-panel markers from the control pool eliminates *direct* leakage (e.g. CXCR3 raising
Th1-like while mechanically lowering Treg-like) — it does **not** decorrelate the programs; shared
controls and genuine co-expression still correlate them, and that residual correlation is **measured
and reported** (Task 7b), never asserted away.

## Global Constraints (every task inherits these)
- **Gates before scores.** `stage01_gate_spec.json` is authored, reviewed, and committed **before** the
  396k scoring run. Pre-registration is void if any score is seen first.
- **Inputs pinned first.** The h5ad raw + canonical matrix hash, dimensions, `.X` semantics, and
  `stage01_umap_coordinates.json` are pinned **before** control construction.
- **Visual design unchanged; behavior may change where science requires it.** No banners/caveat
  blocks/layout/typography/dropdown-interaction changes. But: (a) `All`/all-times and differing-condition
  contrasts must **fail** the analysis preflight (display-only); (b) the "Programs over time" grid reads
  the **396k summary**, not overlay medians; (c) the hidden `balanced_a_to_b` objective is removed from
  Stage-1 serialization.
- **Input semantics (do not misstate).** The pinned `.X` is **already median-normalized (total ≈ 9,819)
  + `log1p`**; there is **no raw counts layer**. Scores are computed from `.X` — never "from raw
  expression." CP10k is a documented *reconstruction* used only as an archived sensitivity.
- **Scoring uses `panel_genes_measured`, never intended.** HLA-DRA (absent) never contributes.
- **Control draws are "program-order-invariant," not "independent."** Cross-program overlap is allowed
  and measured.
- **No cross-program combination in Stage-1.** No `balanced_skew`/`balanced_a_to_b` anywhere in Stage-1;
  combination is a Stage-2 `run_id` concern.
- **Never invent a statistic; public data only; no p/q/FDR without a calibrated, verified null.**
- **Continuous scores only** — no thresholds/membership/argmax.
- **396k is authoritative;** the 40k overlay is display-only.
- **Scorer name:** "deterministic expression-bin-matched panel-minus-control score" — never "exact
  Scanpy `score_genes` output."
- **Hashing:** every artifact carries a **canonical-content SHA-256** (frozen row/column ordering,
  fixed dtypes, explicit float-rounding, null/negative-zero normalization, timestamps excluded).
  **Raw-file SHA-256s live in `stage01_release_manifest.json`** — a file never contains its own
  raw-file hash (no self-referential hashing).
- **Environment is solver-locked** (explicit Linux conda-lock), not just an `environment.yml`.
- **New v3 hashes replace v2;** v2 preserved in history, marked superseded, never presented as current;
  the gate rejects older registry hashes.
- **generator ≠ verifier.** An independent pass re-derives hashes, re-runs verifier + mutation tests,
  and reconstructs controls.
- Modules ≤ 500 lines; every deterministic-logic change ships a regression/mutation test.

## Faulty-assumption ledger (guardrails enforced)
| Assumption | Verdict | Enforced decision |
|---|---|---|
| Scores are exact Scanpy `score_genes` | False | Custom deterministic scorer; renamed |
| Masopust supplied the marker panels | False | Masopust = naming framework; real per-panel provenance |
| All listed markers contributed | False | HLA-DRA absent; store intended vs measured; score measured only |
| Control sets are independent | False | Program-order-invariant draws excluding all program+activation markers; residual correlation reported |
| Raw scores across programs are comparable | Unsupported | Keep arms separate; no equal-change=equal-effect claim |
| Activation regression removes confounding | False | Linear sensitivity only; display-only; never a pole |
| The 40k overlay is the scientific universe | Insufficient | All 396k for summaries + signatures |
| All/different timepoints are executable | False | Only same-timepoint contrasts executable (preflight enforces) |
| The embedding regenerates identically | False | Freeze + hash existing coordinates (immutable input) |
| A high Treg-like score establishes Treg identity | False | Measures the specified regulatory-associated RNA program |
| Scores come "from raw expression" | False | `.X` is pre-normalized+log1p; no raw layer; input manifest states this |

---

## File Structure
- **Rewrite** `01_programs/analysis/stage1_pipeline.py`; **new** `build_controls_v3.py` (Task 2 frozen
  algorithm + reference reconstruction). Split to keep each ≤500 lines.
- **Immutable input** `stage01_umap_coordinates.json` — barcode + frozen x/y only (pinned FIRST).
- **Generated** `stage01_umap_overlay.json` — 40k = pinned coordinates + v3 scores. **Retire**
  `stage01_umap_seed.json` + `stage01_cell_records.json` from the v3 release (kept in Git/HF history);
  update loader/verifier/notebook/build/smoke/HF manifest.
- **Immutable input** `stage01_input_manifest.json` — matrix semantics (median-norm≈9,819 + log1p, no
  raw layer), h5ad raw + canonical hashes, dimensions, exact CP10k reconstruction recipe. **Pinned FIRST.**
- **Pre-registered** `stage01_gate_spec.json` — concrete metrics + thresholds + strata + consequences,
  authored/committed **before** scoring (Task 7a).
- **Scoring outputs** `stage01_scores_full.parquet` (396k), `stage01_program_registry.json` (v3 schema),
  `stage01_summary.json` (396k medians + dispersion by program×condition and donor×condition).
- **Validation output** `stage01_validation.json` — results keyed to `gate_spec` (separate run, Task 7b).
- **Frozen schema** `stage01_selection_contract.json` — placeholders/rules, not a literal instance. Any
  example is `stage01_selection_demo.json` (explicit demo fixture).
- **Release manifest** `stage01_release_manifest.json` — raw-file SHA-256 of every release artifact
  (avoids self-referential hashing).
- **Rewrite** `verify_reproduce.py`; **new** `test_mutation_lock.py`; **new** `conda-linux-64.lock`.
- **Move** cluster/argmax diagnostics out of the production chain.
- **Update** app JS (plumbing + required behavior; no visual change); `docs/HANDOVER.md`,
  `01_programs/README.md`; mark Stage-2 v2 superseded.

### Registry v3 — per-program record schema
```
{ "score_field","program_id","display_label","family","role",
  "panel_genes_intended":[...], "panel_genes_measured":[...], "gene_ids":{symbol:ensembl},
  "coverage":{"n_intended","n_measured","genes_absent":[...],"in_effect_universe":[...]},
  "selection_rationale":{symbol:"why"}, "citations":["module-specific primary"],
  "marker_bins":{symbol:bin}, "controls_by_bin":{bin:[symbols]}, "candidate_counts":{bin:n},
  "sampling":{"scheme":"keyed_sha256","master_seed":12345,
              "key":"{master_seed}|{program_id}|{bin}|{gene}","encoding":"utf-8",
              "digest_tie":"digest_hex asc, then var_name index asc","rule":"50 lowest per occupied marker bin, no replacement"},
  "pool_sha256","bins_sha256","ctrl_size":50,"n_bins":25,
  "normalization":"median_total≈9819 + log1p (from .X; no raw layer)",
  "scoring_method":"deterministic expression-bin-matched panel-minus-control",
  "coefficients":{...}, "stage2_selectable":true|false, "not_selectable_reason":"<exact or null>" }
```

### Identifier hierarchy
```
question_id / contrast_id : hash(A, B, dir_A, dir_B, analysis_condition)                 # biology only
selection_id              : hash(question_id, registry_sha256, method_version, input_manifest_sha256)
stage2_run_id             : hash(selection_id, stage2_method/config/mask/Perturb2State versions)
```
Never load cached results by the biology-only `contrast_id` alone.

### Selection contract schema (frozen; placeholders — materialized only on "Identify genes")
```
{ "A":{"program_id":"<program_id>","direction":"high|low"},
  "B":{"program_id":"<program_id>","direction":"high|low"},
  "analysis_condition":"<single Stim timepoint>", "combination_policy":"deferred_to_stage2",
  "ids":{"question_id","selection_id"},
  "hashes":{"registry_sha256","method_version","input_manifest_sha256","code_sha256"} }
```
Rules: `A.program_id ≠ B.program_id`; identical `analysis_condition` both poles; no sensitivity field;
no nonselectable program. A literal example lives only in `stage01_selection_demo.json`.

---

## Task 1: Freeze the program panels with real provenance
**Executor:** CS. **Verifier:** lead.
- [ ] Per program: `panel_genes_intended` vs `panel_genes_measured` (detected in the pinned object +
  effect-universe flag), Ensembl ids, per-gene `selection_rationale`, module-specific primary citations
  (Masopust = naming framework only). Flag small panels (Th1=4, Th2=4, Tfh=3, Th9=2, Treg=5).
- [ ] **Verify (lead):** `measured ⊆ intended`; each measured gene has id + rationale + citation;
  HLA-DRA only in `intended`.

## Task 2: Freeze the control algorithm (THE score-changing edit)
**Executor:** CS. **Verifier:** lead. **Prerequisite:** the input h5ad raw + canonical matrix hash and
`var_names` are already pinned (lock step 1 / Task 3 input manifest).
- [ ] **Bins (FROZEN, ÷N form — no top clamp):** binning universe = **all 18,130 finite assay-present
  genes** (in `var_names`) across all 396k cells, before pruning. Per-gene statistic = **mean of `.X`**.
  `rank = scipy.stats.rankdata(mean_X, method="average")` (1-based);
  **`bin = floor((rank − 1) * 25 / n_finite)`, `n_finite = 18,130`.** This maps ranks to bins 0–24 with
  no special top-value clamp (the ÷(n−1) form reaches 25 and needs an exception — **rejected**). Store
  `bins_sha256`. *(Audit: control-eligible bins hold ~716–725 candidates; no hard-fail.)*
- [ ] **Pool (distinct terminology):** `assay_present` = genes in `var_names` (**18,130**);
  `detected_in_396k` = nnz>0 (**17,956**); **`control_eligible_pool` = detected_in_396k − the 53
  program/activation markers = 17,903**. Controls are drawn only from `control_eligible_pool`. The
  **binning universe stays all 18,130 assay-present genes** (undetected genes occupy unused bin 0, so
  this only changes `pool_sha256`, not the draws). Record any **present_but_undetected panel gene
  separately** (e.g. HLA-DRA) — never silently scored. Store `pool_sha256` + per-bin `candidate_counts`.
- [ ] **Draw (keyed SHA-256, frozen):** for each program × each occupied marker bin, `digest =
  SHA-256(UTF-8("12345|" + program_id + "|" + str(bin) + "|" + gene))` per candidate in
  `control_eligible_pool`; sort by **(digest_hex asc, then var_name index asc)**; take the **50 lowest**,
  no replacement. The **activation-predictor** draw uses the stable `program_id = "activation_predictor"`.
- [ ] **Hard-fail** (abort before scoring) if any occupied marker bin has `< 50` eligible candidates —
  never shrink/borrow/reseed.
- [ ] Overlap across programs is allowed and **measured**. Store `marker_bins`, `controls_by_bin`,
  `candidate_counts`, `pool_sha256`, `bins_sha256`, `sampling`. Provide a reference reconstruction.
- [ ] **Verify (lead, independent):** re-derive bins with the exact formula; no program marker/activation
  gene in any control set (CXCR3 absent from Treg-like controls); program-order permutation →
  byte-identical controls; the keyed-hash reference reconstructs every list exactly; hard-fail triggers
  on a synthetically thinned bin. *(If CS implemented a different bin/tie interpretation, regenerate.)*

## Task 3: Input manifest (pinned first) + scoring formula + normalization
**Executor:** CS. **Verifier:** lead.
- [ ] **First (lock step 1):** emit `stage01_input_manifest.json` — `.X` is median-normalized to a
  **target total 9,819 with float roundoff** (observed reconstructed per-cell totals: min 9818.9985536,
  max 9819.0017994, median 9819.0000498; **0/396,000 exactly float64 9819.0** — the **pinned matrix hash,
  not exact equality, is the authoritative identity check**) + `log1p`, **no raw layer**; h5ad raw +
  canonical + var-order + barcode-set hashes; dimensions; exact CP10k reconstruction recipe.
  Normalization string enters `method_version`. Pinned **before** Task 2.
- [ ] **Later (lock step 5):** `score(c,p) = mean(.X over measured panel) − mean(.X over matched
  controls)`; name it the "deterministic expression-bin-matched panel-minus-control score."
- [ ] **Verify (lead):** recompute a random sample of `(cell, program)` scores from `.X` + stored
  controls, match to 5 dp; `method_version` ≠ v2; no "raw expression"/"exact Scanpy" text.

## Task 4: Fully specify the activation-adjusted CTL sensitivity lane
**Executor:** CS. **Verifier:** lead.
- [ ] Record activation predictor genes, their exact predictor controls (drawn under
  `program_id="activation_predictor"`), **fit population = all 396k**, normalization, slope + intercept,
  residual formula, code + method hashes. Raw CD4 CTL-like stays primary; actadj is display/sensitivity-
  only, `stage2_selectable=false`.
- [ ] **Verify (lead):** residual reproduces from stored coefficients; excluded from every selectable path.

## Task 5: The 396k scoring run (AFTER gates are committed)
**Executor:** CS. **Verifier:** lead. **Prerequisite:** inputs pinned (step 1), controls verified (step 3),
`stage01_gate_spec.json` committed (step 4).
- [ ] **Compute (chunked on tcefold — never densify the full matrix):** build a frozen **gene×program
  coefficient matrix** (measured panel = `+1/|panel|`, matched controls = `−1/|controls|`, per program);
  stream **backed CSR row chunks of 10k–25k cells**, multiply each chunk by the coefficient matrix, and
  write the score table deterministically. **Smoke-test one chunk and report peak RSS before the full run.**
- [ ] The scoring run emits together: `stage01_scores_full.parquet` (396k; donor, condition, all primary
  scores, CTL sensitivity; no categorical fields); `stage01_umap_overlay.json` (40k = pinned coordinates
  + same scores); `stage01_program_registry.json` (v3); `stage01_summary.json` (396k medians + dispersion
  by program×condition and donor×condition). `stage01_validation.json` comes from the **separate**
  validation run (Task 7b), not here. The selection contract is a schema (placeholders).
- [ ] **Verify (lead):** overlay scores equal the full-table scores for overlay barcodes; the summary is
  computed from 396k (spot-check two medians); no categorical field; no materialized selection in the
  release (only the contract; any example is the named demo fixture).

## Task 6: Freeze + hash the embedding coordinates (with lock step 1)
**Executor:** CS. **Verifier:** lead.
- [ ] Freeze the existing 40k x/y into `stage01_umap_coordinates.json`; do not regenerate the UMAP.
  Canonical-content hash `barcode+x+y`; record the raw-file SHA in the release manifest.
- [ ] **Verify (lead):** coordinate hash pinned + re-derivable.

## Task 7a: Pre-register the gates (BEFORE scoring)
**Executor:** lead + CS. **Files:** `stage01_gate_spec.json` — committed before any score exists.
Concrete metrics + thresholds (no vague prose), grouped into four categories:
- [ ] **Program-measurement gates** (per primary program): coverage `n_measured ≥ 3` (else
  auto-nonselectable); LOMO stability with **controls held fixed** — removing any single measured
  marker shifts the program's global median by `≤ 0.5 × (cross-cell IQR of the score)`; control-key
  sensitivity — 3 alternative `master_seed`s shift the program median by `≤ 0.10` log-units.
- [ ] **Condition-specific pair/contrast gates** (per A/B at a condition): axis non-degeneracy —
  `|median(A) − median(B)| ≥ 0.20` log-units **or** rank-biserial separation `≥ 0.10`; off-axis
  specificity — the A−B direction is not collinear (`|r| ≥ 0.90`) with a third program's axis (else flag).
- [ ] **Overlay-fidelity gates:** `|overlay median − 396k median| ≤ 0.02` per program; donor×condition
  composition matches 396k within `±1` percentage point; per-program KS distance `≤ 0.03`.
- [ ] **Donor stability (LODO, biological n=4):** the sign of each program's median at the selected
  condition is preserved under all 4 leave-one-donor-out folds; no single donor supplies `> 50%` of the
  program's above-median cells at that condition; D2's divergent Th1-like behavior recorded explicitly.
- [ ] Commit `stage01_gate_spec.json`. **Verify (lead):** thresholds are concrete and committed before
  scoring; every metric names its statistic, stratum, and consequence.

## Task 7b: Run validation against the pre-registered gates (AFTER scoring)
**Executor:** CS. **Verifier:** lead. **Files:** `stage01_validation.json`.
- [ ] Run for **every primary program** (not "selectable" — circular): LOMO (controls fixed),
  detection/coverage, alternative-control-key sensitivity, median-vs-CP10k, correlation with every other
  program (report residual shared-control + co-expression correlation). Donor = **LODO n=4**. Overlay
  fidelity per 7a. Descriptive **v2→v3 change report** replaces the old "all-marker-excluded comparison"
  (v3 is already all-marker-excluded).
- [ ] Emit `stage01_validation.json` with pass/fail per gate keyed to `gate_spec` + all input/output
  canonical hashes.
- [ ] **Verify (lead):** re-run two sensitivities independently; pass/fail states agree.

## Task 8: Selectability + frozen selection rules + identifiers
**Executor:** lead (from 7b) with CS.
- [ ] Set `stage2_selectable` + `not_selectable_reason` per program from 7b gates. No panel selectable on
  one surviving marker. Th9 nonselectable until measurable.
- [ ] Freeze selection rules (visual design unchanged): same condition both poles → executable;
  different/all-times → display-only (no artifact); sensitivity → never executable; donor selector →
  display filter only. No membership/threshold.
- [ ] Freeze the identifier hierarchy + selection-contract schema; selection materialized **only on
  "Identify genes"** with `selection_id` hashes.
- [ ] **Verify (lead):** each selectable program passes its 7a gate; the contract emits only A, B,
  directions, one shared condition, `combination_policy: deferred_to_stage2`, ids, hashes.

## Task 9: App data-plumbing + required behavior (no visual change)
**Executor:** lead. **Files:** `01_programs/app/01_page.html` (JS only).
- [ ] Loader consumes coordinates + overlay + summary + v3 registry (retire seed/cell_records reads).
- [ ] **Remove `balanced_a_to_b`** from serialization; selection payload = two ordered axes + condition,
  materialized on "Identify genes" with `selection_id`.
- [ ] `All`/all-times and differing-condition contrasts **fail** the analysis preflight (display-only).
- [ ] Feed the "Programs over time" grid from `stage01_summary.json` (396k).
- [ ] **UI copy (user-requested, explicit exception to "no visual change"):** rename the contrast
  button "Identify state skews →" → "ID program skew genes →".
- [ ] **Verify (lead, in-browser):** no visual/layout diff (beyond the button copy above); grid numbers
  equal the 396k summary; `All` rejected by preflight; no `balanced_a_to_b` in any payload.

## Task 10: Verifier + mutation tests + canonical hashing + solver lock
**Executor:** lead. **Files:** `verify_reproduce.py`, `test_mutation_lock.py`, `conda-linux-64.lock`.
- [ ] Verifier rejects any change to panels/controls/coefficients/roles/coordinates/registry/full scores;
  enforces canonical-content SHA (frozen ordering/dtype/rounding/neg-zero/no-timestamp) and checks raw
  SHAs against `stage01_release_manifest.json`; keeps forbidden-key + stale-string scans; reconstructs
  controls via the Task 2 reference; **rejects older (v2) registry hashes.**
- [ ] `test_mutation_lock.py`: mutate one control gene / panel gene / coefficient / coordinate / role →
  verifier fails; a v2 hash is rejected.
- [ ] Move cluster/argmax diagnostics out of the production chain. Ship the Linux conda lock.
- [ ] **Verify (lead):** mutation tests fail on tampering, pass clean; verifier re-derives all hashes clean.

## Task 11: Independent verification (generator ≠ verifier)
**Executor:** independent pass. Applied to the **control build before gate authoring** (lock step 3) and
to the **full release** at the end.
- [ ] Re-derive every hash; re-run verifier + mutation tests on a clean host; independently reconstruct
  all control lists via keyed hashing with the exact formula; recompute a score sample; confirm the
  summary is 396k-based and artifacts agree. Emit `verification.json` (all-pass required).

## Task 12: Lock, supersede Stage-2, publish
**Executor:** lead.
- [ ] Mark every v2 Stage-2 artifact `superseded`, `incompatible_with_current_stage1`,
  `stage3_eligible=false`. Preserve v2 in history.
- [ ] Publish a sanitized HF revision with only current v3 artifacts; pin + verify the h5ad SHA and the
  `stage01_umap_coordinates.json` SHA; update the HF manifest.
- [ ] Tag **`stage1-continuous-v3`**; the verifier rejects older registry hashes.
- [ ] Update `docs/HANDOVER.md` + `01_programs/README.md`; record the deferred Stage-2 remediation.

---

## Deferred (NOT executed here) — Stage-2 remediation
After Stage-1 v3 locks and v2 Stage-2 is marked superseded, fix Stage-2 **before** re-running: exact
contributing-guide masks; eligible-only candidate ranking; ≥2 evaluated guides for guide replication;
honest donor-support denominators; generic `stage01_selection_contract.json` consumption; a
method/config/input-aware `run_id`; off-axis specificity reporting. Only then generate a new v3 selection
and re-run direct projection + Perturb2State from scratch.

## Lock sequence (execution order — gates are pre-registered BEFORE scoring)
1. **Pin the input manifest + coordinate input** (T3 input-manifest part + T6) — before any control work.
2. **Freeze panels (T1) and controls (T2, ÷N + `control_eligible_pool`)** against the pinned input.
3. **Regenerate the affected draws, then independently verify controls** (keyed reconstruction, leakage,
   order-invariance; T11 on the control build) — before gates.
4. **Commit exact input/method definitions + `stage01_gate_spec.json`** (concrete thresholds, T7a) —
   before any score exists.
5. **Configure + smoke-test chunked scoring on tcefold** (frozen coefficient matrix, backed CSR chunks
   10k–25k cells; report peak RSS).
6. **Only then authorize the full 396k scoring run** + emit scores/registry/summary/overlay (T3 + T5).
7. **Run validation/sensitivity separately** against the pre-registered gates (T7b) → selectability (T8).
8. **Assemble the release bundle** + `stage01_release_manifest.json`; app plumbing (T9); verifier +
   mutation tests + independent verification on a clean host (T10–T11); publish sanitized HF rev + tag
   `stage1-continuous-v3` (T12).

## Self-review (Rev-3 coverage)
Gates-before-scoring → Global + lock steps 3–5 + T7a/T7b split. Input pinned first → Global + lock step 1
+ T3/T6. Exact bin formula + corrected audit (715–725, terminal 715 marker-occupied) → T2. Keyed-hash
UTF-8/namespace/digest-tie + activation_predictor program_id → T2/registry `sampling`. Selection contract
placeholders + demo fixture → schema + T8. "All-marker-excluded" → v2→v3 change report → T7b. Concrete
gate metrics/thresholds → T7a. Raw hashes in release manifest, no self-referential → Global + File
Structure + T10. "Program-order-invariant" + residual-correlation reporting → Global/T2/T7b.
