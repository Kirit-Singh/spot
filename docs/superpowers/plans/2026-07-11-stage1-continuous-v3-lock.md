# Stage-1 Continuous-Scoring v3 — Final Lock Implementation Plan

> **For agentic workers:** Execution is **delegated to the Claude Science specialist on tcefold**
> (91 GB; tcedirector's 31 GB has swap-died on the 396k object). The **lead session plans and
> independently verifies** (generator ≠ verifier). Steps use checkbox (`- [ ]`) tracking. Do not
> touch the frozen v2 artifacts except to mark them superseded.
>
> **Rev 2 (conditional approval, 2026-07-11):** frozen control algorithm (keyed SHA-256 draws),
> coordinates/overlay split, input-normalization language corrected, gates pre-registered, identifier
> hierarchy fixed, `balanced_a_to_b` removed from serialization, "program-order-invariant" not
> "independent", canonical-content hashing + real solver lock, "visual design unchanged" (behavior may).

**Goal:** Re-lock Stage-1 as a frozen, reproducible *measurement* system for continuous
transcriptional programs — with **program-order-invariant** control draws — and emit the full 396k
score table + pre-registered validation battery, without any visual redesign.

**Architecture:** One deterministic run on all 396,000 NTC cells produces the release artifacts (full
scores, immutable coordinates + generated 40k overlay, registry, summary, validation, input manifest,
selection contract). The single score-changing edit is the control-pool redesign (Task 2); everything
else is provenance, artifact, validation, and reproducibility rigor around it. Stage-2 is **not**
re-run here — its v2 artifacts are marked superseded pending a separate Stage-2 remediation.

**Tech Stack:** Python (vectorized scoring, numpy/scipy/anndata/pandas/pyarrow) in a **solver-locked**
conda env on tcefold; keyed SHA-256 sampling; raw-file + canonical-content SHA-256 hashing; the
existing hardened static-server + `verify_reproduce.py` gate.

## What "locked" means (non-negotiable framing)
A frozen, reproducible measurement of specified RNA programs. It does **not** mean RNA has confirmed
bona-fide Treg/Th1 identity, nor that the programs are biologically or statistically **independent**.
Removing cross-panel markers from the control pool eliminates *direct* leakage (e.g. CXCR3 raising
Th1-like while mechanically lowering Treg-like) — it does **not** decorrelate the programs; shared
controls and genuine co-expression still correlate them, and that residual correlation is **measured
and reported** (Task 7), never asserted away. A high Treg-like score measures the specified
regulatory-associated RNA program — nothing more.

## Global Constraints (every task inherits these)
- **Visual design unchanged; behavior may change where science requires it.** No banners, no new
  caveat blocks, no layout/typography/dropdown-interaction changes. But scientifically necessary
  behavior **must** change: (a) `All`/all-times and differing-condition contrasts must **fail** the
  analysis preflight (display-only, no selection artifact); (b) the "Programs over time" grid must read
  the **396k summary**, not overlay-derived medians; (c) the hidden `balanced_a_to_b` objective is
  removed from Stage-1 serialization.
- **Input semantics (do not misstate).** The pinned `.X` is **already median-normalized (target total
  ≈ 9,819) and `log1p`-transformed**; there is **no raw counts layer** in the object. Scores are
  computed from `.X` — never described as "from raw expression." CP10k is a documented *reconstruction*
  used only as an archived sensitivity, never mixed with or equated to the primary. An **immutable
  input manifest** records matrix semantics, hashes, dimensions, and the exact CP10k reconstruction.
- **Scoring uses `panel_genes_measured`, never intended.** HLA-DRA (absent) and any undetected gene
  never contribute; intended vs measured are stored separately.
- **Control draws are "program-order-invariant," not "independent."** Cross-program control overlap is
  **allowed and measured**. The draw is deterministic and independent of program iteration order.
- **No cross-program combination in Stage-1.** A +0.4 change in one program is not asserted equal to
  +0.4 in another. `away_from_A` and `toward_B` stay separate; **no `balanced_skew` / `balanced_a_to_b`
  is emitted anywhere in Stage-1** (any combination is a Stage-2 `run_id` concern).
- **Never invent a statistic; public data only; no p/q/FDR without a calibrated, verified null.**
- **Continuous scores only** — no thresholds, no membership, no argmax/categorical calls.
- **396k is authoritative.** All summaries + downstream signatures use all 396,000 cells; the 40k
  overlay is a display-only derived sample.
- **Scorer name:** "deterministic expression-bin-matched panel-minus-control score" — never "exact
  Scanpy `score_genes` output."
- **Embedding coordinates are frozen and hashed** in a minimal immutable input, not regenerated.
- **Hashing:** every artifact carries a **raw-file SHA-256** *and* a **canonical-content SHA-256**
  (frozen row/column ordering, fixed dtypes, explicit float-rounding rule, null / negative-zero
  normalization, timestamp fields excluded from the canonical hash).
- **Environment is solver-locked:** an explicit Linux conda-lock (or package URL/build/hash lock), not
  just an `environment.yml`.
- **New v3 hashes replace v2.** v2 artifacts are preserved in Git/HF history, marked superseded, never
  overwritten or presented as current; downstream use of older registry hashes is rejected by the gate.
- **generator ≠ verifier.** An independent pass re-derives every hash, re-runs verifier + mutation
  tests on a clean host, and independently reconstructs controls.
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
- **Rewrite** `01_programs/analysis/stage1_pipeline.py` — v3 scorer, control redesign, emit release
  artifacts from one 396k run. Split control build into `build_controls_v3.py` (≤500 lines each).
- **New** `01_programs/analysis/build_controls_v3.py` — frozen control algorithm (Task 2) + reference
  reconstruction used by the mutation test.
- **New immutable input** `01_programs/app/data/stage01_umap_coordinates.json` — barcode + frozen x/y
  **only** (no scores). The minimal, pinned coordinate input.
- **New generated** `01_programs/app/data/stage01_umap_overlay.json` — 40k display artifact: coordinates
  **plus** v3 scores. **Retire** `stage01_umap_seed.json` + `stage01_cell_records.json` from the v3
  release (preserved in Git/HF history). Update loader, verifier, notebook, build script, smoke tests,
  HF manifest.
- **New** `01_programs/app/data/stage01_input_manifest.json` — immutable: matrix semantics
  (median-norm total≈9,819 + log1p, no raw layer), h5ad raw + canonical hashes, dimensions, exact CP10k
  reconstruction recipe.
- **New** `01_programs/app/data/stage01_gate_spec.json` — **pre-registered** validation gates
  (committed before v3 results): every metric, alternative seed, stratum, threshold, consequence, and
  gate category.
- **New** `01_programs/app/data/stage01_scores_full.parquet` — 396k barcodes × all primary scores + CTL
  sensitivity + donor + condition; no categorical fields. (Gitignored if oversize; both hashes pinned.)
- **New** `01_programs/app/data/stage01_summary.json` — full-396k medians + dispersion by
  program×condition and donor×condition (the app grid's data source).
- **New** `01_programs/app/data/stage01_validation.json` — results keyed to `gate_spec`, machine-readable
  pass/fail + all input/output hashes.
- **New** `01_programs/app/data/stage01_program_registry.json` — v3 schema (below).
- **New** `01_programs/app/data/stage01_selection_contract.json` — the **frozen selection schema**, not a
  materialized Treg→Th1 selection. Any bundled example is `stage01_selection_demo.json`, explicitly a
  **demo fixture**, never presented as the Stage-1 output.
- **Rewrite** `01_programs/analysis/verify_reproduce.py` — v3 gate (below) + canonical-content hashing.
- **New** `01_programs/analysis/test_mutation_lock.py` — mutation tests proving protected changes fail.
- **New** `01_programs/analysis/conda-linux-64.lock` (+ `environment.yml`) — real solver lock.
- **Move** `cluster_scores.py`/`label_clusters.py`/argmax diagnostics out of the production chain.
- **Update** app JS (data-plumbing + required behavior; **no visual change**): consume
  coordinates+overlay+summary, drop `balanced_a_to_b` serialization, make `All`/differing-condition fail
  the analysis preflight, feed the grid from `stage01_summary.json`.
- **Update** `docs/HANDOVER.md`, `01_programs/README.md`; mark Stage-2 v2 artifacts superseded.

### Registry v3 — per-program record schema
```
{ "score_field", "program_id", "display_label", "family", "role",
  "panel_genes_intended": [...symbols...],
  "panel_genes_measured": [...symbols detected + used...],
  "gene_ids": {symbol: ensembl_id},
  "coverage": {"n_intended","n_measured","genes_absent":[...],"in_effect_universe":[...]},
  "selection_rationale": {symbol: "why this gene"},
  "citations": ["module-specific primary citation(s)"],
  "marker_bins": {symbol: bin_index},
  "controls_by_bin": {bin_index: [control symbols]},
  "candidate_counts": {bin_index: n_eligible_in_pool},
  "sampling": {"scheme":"keyed_sha256","master_seed":12345,
               "key":"master_seed|program_id|bin|gene","rule":"50 lowest hashes per occupied marker bin, no replacement"},
  "pool_sha256", "bins_sha256",
  "ctrl_size": 50, "n_bins": 25,
  "normalization": "median_total≈9819 + log1p (from .X; no raw layer)",
  "scoring_method": "deterministic expression-bin-matched panel-minus-control",
  "coefficients": {...any stored fit coeffs...},
  "stage2_selectable": true|false, "not_selectable_reason": "<exact reason or null>" }
```

### Identifier hierarchy (fixes cache-key ambiguity)
```
question_id / contrast_id : hash(A, B, dir_A, dir_B, analysis_condition)         # biology only
selection_id              : hash(question_id, registry_sha256, method_version, input_manifest_sha256)
stage2_run_id             : hash(selection_id, stage2_method/config/mask/Perturb2State versions)
```
**Never** load cached results using the biology-only `contrast_id` alone — results are keyed by
`selection_id` (Stage-1 inputs) or `stage2_run_id` (Stage-2 method).

### Selection contract schema (frozen; materialized only on "Identify genes")
```
{ "A": {"program_id":"treg_like","direction":"high"},
  "B": {"program_id":"th1_like","direction":"high"},
  "analysis_condition": "Stim48hr",
  "combination_policy": "deferred_to_stage2",
  "ids": {"question_id","selection_id"},
  "hashes": {"registry_sha256","method_version","input_manifest_sha256","code_sha256"} }
```
Stage-1 emits the **two ordered axes only**; Stage-2 owns any combination.

---

## Task 1: Freeze the program panels with real provenance
**Executor:** CS specialist. **Verifier:** lead.
- [ ] Per program: `panel_genes_intended`, `panel_genes_measured` (detected here + effect-universe
  flag), Ensembl ids, per-gene `selection_rationale`, and **module-specific primary citations**
  (Masopust cited only as the naming framework).
- [ ] Review small panels — Th1 (4), Th2 (4), Tfh (3), Th9 (2, nonselectable), Treg-like (5, activated
  substrate) — record concerns for Task 8.
- [ ] **Verify (lead):** `measured ⊆ intended`; every measured gene has id + rationale + citation;
  HLA-DRA appears only in `intended`.

## Task 2: Freeze the control algorithm (THE score-changing edit)
**Executor:** CS specialist. **Verifier:** lead. **Files:** `build_controls_v3.py`, registry (controls).
Frozen, fully specified — no ambiguity permitted:
- [ ] **Bins:** compute expression bins on **all finite genes in the pinned `.X` across all 396k
  cells, before any marker pruning.** Bin statistic = per-gene **mean of `.X`** (log-normalized).
  Ranking uses `scipy.stats.rankdata(..., method="average")` on the mean vector; bin index =
  `floor(rank_fraction * 25)` clamped to `[0,24]`; document the exact tie/edge rule. Store `bins_sha256`.
- [ ] **Pool:** `candidate_pool = all measured genes − ∪(every program-marker gene) − activation-predictor
  marker genes`. Store `pool_sha256` and per-bin `candidate_counts`.
- [ ] **Draw (keyed SHA-256, platform-independent — preferred over NumPy RNG):** for each program, for
  each **occupied marker bin**, hash every eligible candidate as
  `sha256("12345|{program_id}|{bin}|{gene}")`, sort ascending, take the **50 lowest** (no replacement).
  Candidate identity + ordering come from the pinned H5AD `var_names`.
- [ ] **Hard-fail:** if any occupied marker bin has `< ctrl_size (50)` eligible candidates, **abort
  before scoring** — never silently shrink, borrow an adjacent bin, or reseed. (Checked on tcefold:
  18,130 measured − 53 excluded = 18,077 candidates; occupied marker bins hold 745–755 each, so 50 is
  comfortable; the 11-gene terminal bin holds no marker.)
- [ ] Overlap across programs is **allowed and measured** (report in Task 7). Name these
  **program-order-invariant draws**, not independent control sets.
- [ ] Store `marker_bins`, `controls_by_bin`, `candidate_counts`, `pool_sha256`, `bins_sha256`, and the
  `sampling` block in the registry. Provide a reference reconstruction from `(pool, bins, key rule)`.
- [ ] **Verify (lead):** no program marker and no activation marker is in any control set (CXCR3 absent
  from Treg-like controls); permuting program order → byte-identical controls; the keyed-hash reference
  reconstructs every list exactly; hard-fail triggers on a synthetically thinned bin.

## Task 3: Scoring formula, normalization, input manifest
**Executor:** CS specialist. **Verifier:** lead.
- [ ] `score(c,p) = mean(.X over measured panel genes) − mean(.X over matched controls)`. Name it the
  "deterministic expression-bin-matched panel-minus-control score."
- [ ] Emit `stage01_input_manifest.json`: `.X` is median-normalized (total≈9,819) + `log1p`, **no raw
  layer**; h5ad raw + canonical hashes; dimensions; the exact CP10k reconstruction recipe (archived
  sensitivity only). Normalization string enters `method_version`.
- [ ] **Verify (lead):** recompute a random sample of `(cell, program)` scores from `.X` + stored
  controls, match `stage01_scores_full.parquet` to 5 dp; `method_version` differs from v2; no text
  claims "raw expression" or "exact Scanpy output."

## Task 4: Fully specify the activation-adjusted CTL sensitivity lane
**Executor:** CS specialist. **Verifier:** lead.
- [ ] Record: activation predictor genes, their exact predictor controls, **fit population = all 396k**,
  normalization, regression slope + intercept, residual formula, code hash, method hash.
- [ ] Raw CD4 CTL-like stays primary; actadj is display/sensitivity-only, `stage2_selectable=false`.
- [ ] **Verify (lead):** residual reproduces from stored slope/intercept + inputs; excluded from every
  selectable-program path.

## Task 5: Emit the release artifacts from one 396k run
**Executor:** CS specialist. **Verifier:** lead.
- [ ] One run emits together: `stage01_scores_full.parquet` (396k; donor, condition, all primary
  scores, CTL sensitivity; **no categorical fields**); `stage01_umap_coordinates.json` (immutable
  barcode+x/y); `stage01_umap_overlay.json` (40k = coordinates + same scores); `stage01_program_registry.json`
  (v3); `stage01_summary.json` (396k medians + dispersion by program×condition and donor×condition);
  `stage01_input_manifest.json`; `stage01_gate_spec.json` (Task 7, pre-registered); `stage01_validation.json`
  (Task 7); `stage01_selection_contract.json` (schema only).
- [ ] **Verify (lead):** overlay scores equal the full-table scores for overlay barcodes; the summary is
  computed from 396k (spot-check two medians against the parquet); no categorical field anywhere; no
  materialized Treg→Th1 selection in the release (only the contract; any example is a named demo fixture).

## Task 6: Freeze + hash the embedding coordinates
**Executor:** CS specialist. **Verifier:** lead.
- [ ] Freeze the existing 40k x/y into `stage01_umap_coordinates.json`; do not regenerate the UMAP.
  Hash `barcode+x+y` (canonical-content SHA).
- [ ] **Verify (lead):** coordinate hash pinned in the registry + manifest and re-derivable.

## Task 7: Pre-registered validation battery (drives selectability)
**Executor:** CS specialist. **Verifier:** lead. **Files:** `stage01_gate_spec.json`, `stage01_validation.json`.
- [ ] **Author + commit `stage01_gate_spec.json` BEFORE running v3 validation** — every metric,
  alternative seed, stratum, threshold, and consequence, grouped into: **(i) program-measurement gates;
  (ii) condition-specific pair/contrast gates; (iii) overlay-fidelity gates; (iv) descriptive
  sensitivities** (CP10k, v2-vs-v3 change) that inform but do not gate.
- [ ] Run validation for **every primary program** (not "selectable programs" — that is circular):
  leave-one-marker-out (**holding the frozen controls fixed**), detection/coverage, alternative-control-key
  sensitivity, all-marker-excluded control comparison, median-vs-CP10k, and correlation with every other
  program (report residual shared-control + co-expression correlation).
- [ ] **Donor = leave-one-donor-out sensitivity at biological n=4** (not 396k independent replicates):
  heterogeneity measured; no program driven entirely by one donor; selected condition has usable
  variation; direction not a pooling artifact; D2's divergent Th1-like behavior captured explicitly.
- [ ] **Overlay-fidelity:** 40k preserves donor×condition composition, per-program medians,
  distributions, and broad correlations vs the 396k table.
- [ ] Emit `stage01_validation.json` with pass/fail per gate keyed to `gate_spec`.
- [ ] **Verify (lead):** two sensitivities re-run independently match; pass/fail states agree.

## Task 8: Selectability + frozen selection rules + identifier hierarchy
**Executor:** lead (from Task 7) with CS.
- [ ] Set `stage2_selectable` + `not_selectable_reason` per program from Task 7. **No panel selectable
  merely because one marker survives.** Th9 stays nonselectable until measurable.
- [ ] Freeze selection rules (visual design unchanged): same condition both poles → executable; different
  conditions / all-times → display-only (no selection artifact); sensitivity fields → never executable;
  donor selector → display filter only (contrast uses all four donors). No membership/threshold.
- [ ] Freeze the identifier hierarchy (`question_id`/`selection_id`/`run_id`) and the selection contract
  schema. Selection is materialized **only on "Identify genes"** with the full `selection_id` hashes.
- [ ] **Verify (lead):** every selectable program passes its gate; the contract emits only A, B,
  directions, one shared condition, `combination_policy: deferred_to_stage2`, ids, and hashes.

## Task 9: App data-plumbing + scientifically-required behavior (no visual change)
**Executor:** lead. **Files:** `01_programs/app/01_page.html` (JS only).
- [ ] Loader consumes `stage01_umap_coordinates.json` + `stage01_umap_overlay.json` + `stage01_summary.json`
  + v3 registry (retire seed/cell_records reads).
- [ ] **Remove `balanced_a_to_b`** from Stage-1 serialization; the selection payload carries the two
  ordered axes + condition only, materialized on "Identify genes" with `selection_id`.
- [ ] Make `All`/all-times and differing-condition contrasts **fail** the analysis preflight (display-only).
- [ ] Feed the "Programs over time" grid from `stage01_summary.json` (396k), not overlay medians.
- [ ] **Verify (lead):** in-browser — no visual/layout diff; grid numbers equal the 396k summary; `All`
  is rejected by preflight; no `balanced_a_to_b` in any emitted payload; map + gradient unchanged.

## Task 10: Verifier + mutation tests + canonical hashing + solver lock
**Executor:** lead. **Files:** `verify_reproduce.py`, `test_mutation_lock.py`, `conda-linux-64.lock`.
- [ ] Verifier rejects any change to panels, controls, coefficients, roles, coordinates, registry, or
  full scores; enforces raw-file + canonical-content SHA (frozen ordering/dtypes/rounding/neg-zero/no
  timestamps); keeps forbidden-key + stale-string scans; independently reconstructs controls via the
  Task 2 reference; **rejects older (v2) registry hashes.**
- [ ] `test_mutation_lock.py`: mutate one control gene / panel gene / coefficient / coordinate / role
  each → assert the verifier fails; assert a v2 hash is rejected.
- [ ] Move cluster/argmax diagnostics out of the production chain (labelled non-production).
- [ ] Ship a real **Linux conda lock** (not just `environment.yml`).
- [ ] **Verify (lead):** mutation tests fail on tampering, pass clean; verifier re-derives all hashes on
  a clean checkout.

## Task 11: Independent verification (generator ≠ verifier)
**Executor:** independent pass (lead or a fresh agent that did not generate the artifacts).
- [ ] On a clean host: re-derive every hash; re-run verifier + mutation tests; independently reconstruct
  all control lists via keyed hashing; recompute a score sample; confirm the summary is 396k-based and
  the six+ artifacts agree. Emit `verification.json` (all-pass required).

## Task 12: Lock, supersede Stage-2, publish
**Executor:** lead.
- [ ] Mark every v2 Stage-2 artifact `superseded`, `incompatible_with_current_stage1`,
  `stage3_eligible=false`. Preserve v2 in history; never overwrite or present as current.
- [ ] Publish a **sanitized HF revision** with only current v3 artifacts; pin + verify the h5ad SHA and
  the `stage01_umap_coordinates.json` SHA; update the HF manifest.
- [ ] Tag **`stage1-continuous-v3`**; the verifier rejects older registry hashes downstream.
- [ ] Update `docs/HANDOVER.md` + `01_programs/README.md` to v3; record the deferred Stage-2 remediation.

---

## Deferred to a separate effort (NOT executed here) — Stage-2 remediation
After Stage-1 v3 locks and v2 Stage-2 is marked superseded, fix Stage-2 **before** re-running: exact
contributing-guide masks; eligible-only candidate ranking; ≥2 evaluated guides for guide replication;
honest donor-support denominators; generic `stage01_selection_contract.json` consumption; a
method/config/input-aware `run_id`; off-axis specificity reporting. Only then generate a new v3
selection and re-run direct projection + Perturb2State from scratch. The mask's biological gene content
is scorer-independent, but its emitted artifact + hash bind to the contrast/run and are regenerated +
re-pinned then.

## Lock sequence (execution order)
1. Freeze panels + citations (T1). 2. Freeze the control algorithm — keyed draws, hard-fail (T2).
3. Freeze normalization + scoring + input manifest (T3–T4). 4. Rerun 396k once (T5–T6). 5. Regenerate
registry + full table + summary + coordinates + overlay together (T5). 6. Author gates, then run
sensitivities (T7). 7. Decide selectability + freeze ids/selection (T8). 8. App plumbing/behavior (T9).
9. Verifier + mutation tests on a clean host (T10–T11). 10. Publish immutable hashes + sanitized HF rev;
tag `stage1-continuous-v3` (T12).

## Self-review (spec coverage)
Filenames split (coords vs overlay) + retirements → File Structure/T5–T6. Hard-fail bins + frozen keyed
algorithm → T2. Static-selection removal + selection-on-click + demo-fixture naming → T5/T8/T9.
Identifier hierarchy → schema + T8. `balanced_a_to_b` removed from serialization → T9. Gates pre-registered,
every primary program, four categories, LOMO-controls-fixed, LODO n=4 → T7. Normalization/input language
corrected + input manifest → T3. Raw-file + canonical-content hashing + solver lock → Global/T10.
"Visual design unchanged" + `All` preflight + 396k-summary grid → Global/T9. "Program-order-invariant"
not "independent" + residual-correlation reporting → Global/T2/T7.
