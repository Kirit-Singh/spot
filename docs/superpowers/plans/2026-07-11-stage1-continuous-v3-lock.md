# Stage-1 Continuous-Scoring v3 — Final Lock Implementation Plan

> **For agentic workers:** Execution is **delegated to the Claude Science specialist on tcefold**
> (91 GB; tcedirector's 31 GB has swap-died on the 396k object). The **lead session plans and
> independently verifies** (generator ≠ verifier). Steps use checkbox (`- [ ]`) tracking. Do not
> touch the frozen v2 artifacts except to mark them superseded.

**Goal:** Re-lock Stage-1 as a frozen, reproducible *measurement* system for continuous
transcriptional programs — with independent per-program control sets — and emit the full 396k score
table + validation battery, without any UI change.

**Architecture:** One deterministic run on all 396,000 NTC cells produces six artifacts (full scores,
40k display overlay, registry, summary, validation, selection). The single score-changing edit is the
control-pool redesign (Task 2); everything else is provenance, artifact, validation, and
reproducibility rigor around it. Stage-2 is **not** re-run here — its v2 artifacts are marked
superseded pending a separate Stage-2 remediation.

**Tech Stack:** Python (scanpy-style vectorized scoring, numpy/scipy/anndata/pandas/pyarrow) in a
pinned conda env on tcefold; content-addressed SHA-256 hashing; deterministic RNG (per-program
streams); the existing hardened static-server + `verify_reproduce.py` gate.

## What "locked" means (non-negotiable framing)
A frozen, reproducible measurement of specified RNA programs. It does **not** mean RNA has confirmed
bona-fide Treg/Th1 identity. A high Treg-like score measures the specified regulatory-associated RNA
program — nothing more. Every artifact carries this framing; no artifact asserts identity, lineage,
protein, cytotoxicity, or suppressive function.

## Global Constraints (every task inherits these)
- **UI unchanged.** No banners, no new caveat blocks, no layout changes, no dropdown/interaction
  changes. All work is in the scorer, registry, validation artifacts, and reproducibility chain. The
  UI consumes the new artifacts without visual redesign.
- **Scoring uses `panel_genes_measured`, never the intended list.** HLA-DRA (absent) and any other
  undetected gene must not contribute; intended vs measured are stored separately.
- **Never invent a statistic; public data only; no p/q/FDR without a calibrated, verified null.**
- **Continuous scores only** — no thresholds, no "high-cell membership", no categorical/argmax calls.
- **No cross-program combination in Stage-1.** A +0.4 change in one program is **not** asserted equal
  to +0.4 in another. `away_from_A` and `toward_B` stay separate; **no `balanced_skew` field is
  emitted at all** (deferred to Stage-2 `run_id`).
- **Median normalization (target ≈ 9,819) then `log1p` is primary**; CP10k is an archived sensitivity
  comparison only — never mixed with or presented as equivalent to the primary. Normalization is part
  of the method hash.
- **Scorer name:** "deterministic expression-bin-matched panel-minus-control score" — **never** "exact
  Scanpy `score_genes` output."
- **396k is authoritative.** All summaries + downstream signatures use all 396,000 cells; the 40k
  overlay is a display-only derived sample.
- **Embedding coordinates are frozen and hashed** (not regenerated identically).
- **New v3 hashes replace v2.** v2 artifacts are preserved as historical records, marked superseded,
  never overwritten or presented as current; downstream use of older registry hashes is prohibited.
- **generator ≠ verifier.** An independent pass that did not generate the artifacts re-derives every
  hash, re-runs the verifier + mutation tests on a clean host, and independently reconstructs controls.
- Modules ≤ 500 lines; every deterministic-logic change ships a regression/mutation test. Environment
  is a conda **environment file**, not a pip package.

## Faulty-assumption ledger (the guardrails this plan enforces)
| Assumption | Verdict | Enforced decision |
|---|---|---|
| Scores are exact Scanpy `score_genes` | False | Custom deterministic Scanpy-style scorer; renamed |
| Masopust supplied the marker panels | False | Masopust = naming framework; add real per-panel provenance |
| All listed markers contributed | False | HLA-DRA absent; store intended vs measured; score measured only |
| Program control sets are independent | False | Rebuild controls excluding the union of all program + activation markers |
| Raw scores across programs are comparable | Unsupported | Keep program arms separate; no equal-change = equal-effect claim |
| Activation regression removes confounding | False | Linear sensitivity analysis only; display-only; never a Stage-2 pole |
| The 40k overlay is the scientific universe | Insufficient | Use all 396k for summaries + signatures |
| All/different timepoints are executable | False | Only same-timepoint contrasts are executable |
| The embedding regenerates identically | False | Freeze + hash the existing coordinates |
| A high Treg-like score establishes Treg identity | False | It measures the specified regulatory-associated RNA program |

---

## File Structure
- **Rewrite** `01_programs/analysis/stage1_pipeline.py` — v3 scorer, control redesign, per-program RNG,
  emit all six artifacts from one 396k run. (Split control-build into `build_controls_v3.py` if the
  file exceeds 500 lines.)
- **New** `01_programs/analysis/build_controls_v3.py` — all-marker-excluded, per-program-seeded control
  builder + a reference reconstruction used by tests.
- **Rewrite** `01_programs/app/data/stage01_program_registry.json` — v3 schema (below).
- **New** `01_programs/app/data/stage01_scores_full.parquet` — 396k barcodes × all primary scores +
  CTL sensitivity + donor + condition; no categorical fields. (Gitignored if >file limit; hashed.)
- **New/rename** `01_programs/app/data/stage01_umap_overlay.json` — 40k display sample, frozen x/y,
  same scores. (Supersedes `stage01_umap_seed.json`/`stage01_cell_records.json`.)
- **New** `01_programs/app/data/stage01_summary.json` — full-396k medians + dispersion by
  program×condition and donor×condition.
- **New** `01_programs/app/data/stage01_validation.json` — sensitivity/stability/redundancy results +
  all input/output hashes + machine-readable pass/fail.
- **New** `01_programs/app/data/stage01_selection.json` — the frozen selection contract (schema below).
- **Rewrite** `01_programs/analysis/verify_reproduce.py` — v3 gate rejecting changes to panels,
  controls, coefficients, roles, coordinates, registry, or full scores.
- **New** `01_programs/analysis/test_mutation_lock.py` — mutation tests proving each protected change fails.
- **New** `01_programs/analysis/environment.yml` — conda env lock.
- **Move** `cluster_scores.py` / `label_clusters.py` / any argmax diagnostics out of the production
  reproduction chain (keep as clearly-labelled non-production diagnostics).
- **Update** app JS to consume the new artifacts (data-plumbing only; **no visual change**) + drop any
  emitted `balanced_skew`.
- **Update** `docs/HANDOVER.md`, `01_programs/README.md`, and mark Stage-2 v2 artifacts superseded.

### Registry v3 — per-program record schema
```
{ "score_field", "program_id", "display_label", "family", "role",
  "panel_genes_intended": [...symbols...],
  "panel_genes_measured": [...symbols actually detected + used...],
  "gene_ids": {symbol: ensembl_id},
  "coverage": { "n_intended", "n_measured", "genes_absent": [...], "in_effect_universe": [...] },
  "selection_rationale": { symbol: "why this gene" },
  "citations": [ "module-specific primary citation(s)" ],
  "control_genes": [...symbols...], "control_bins": { symbol: bin_index },
  "program_seed": <master_seed+program_id derived>, "ctrl_size": 50, "n_bins": 25,
  "normalization": "median_total≈9819 + log1p", "scoring_method": "deterministic expression-bin-matched panel-minus-control",
  "stage2_selectable": true|false, "not_selectable_reason": "<exact reason or null>" }
```

### Selection contract schema (Task 8 output; UI unchanged)
```
{ "A": {"program_id":"treg_like","direction":"high"},
  "B": {"program_id":"th1_like","direction":"high"},
  "analysis_condition": "Stim48hr",
  "combination_policy": "deferred_to_stage2",
  "hashes": {"registry_sha256","method_version","code_sha256","source_h5ad_sha256"} }
```
`contrast_id` = hash of the **biological question** (A, B, directions, analysis_condition) only. Any
combination formula lives in the Stage-2 `run_id`, never here. No `balanced_skew` anywhere in Stage-1.

---

## Task 1: Freeze the program panels with real provenance
**Executor:** CS specialist. **Verifier:** lead. **Files:** registry (panel section), a panel-provenance table.
**Interfaces — Produces:** `panel_genes_intended`, `panel_genes_measured`, `gene_ids`, `coverage`,
`selection_rationale`, `citations` per program.

- [ ] For every program record: intended list, measured list (detected in this Flex dataset **and**
  flagged for effect-universe membership), Ensembl ids, per-gene selection rationale, and
  **module-specific primary citations** (the actual immunology source for each marker set — Masopust is
  the *naming* framework, cited separately).
- [ ] Review every panel, especially the small ones: Th1 (4), Th2 (4), Tfh (3), Th9 (2, currently
  nonselectable), Treg-like (5, in a strongly activated substrate). Record concerns per panel.
- [ ] **Verify (lead):** `panel_genes_measured ⊆ panel_genes_intended`; every measured gene has an id +
  rationale + citation; HLA-DRA appears only in intended, never measured; small panels carry an
  explicit selectability note for Task 8.

## Task 2: Redesign control selection (THE score-changing edit)
**Executor:** CS specialist. **Verifier:** lead. **Files:** `build_controls_v3.py`, registry (controls).
**Interfaces — Consumes:** all measured gene symbols + expression, the union of all program markers, the
activation-predictor markers. **Produces:** per-program `control_genes`, `control_bins`, `program_seed`.

- [ ] Build the control pool once: `all_measured_genes − ∪(every program-marker gene) − activation-sensitivity marker genes`.
- [ ] Per-program **independent RNG stream** seeded by `master_seed + program_id` (a stable hash of the
  program_id — **not** one sequential RNG whose output shifts with program order).
- [ ] Retain expression-bin matching (25 bins) and the frozen `ctrl_size` rule against the pruned pool.
- [ ] Store each control gene, its expression bin, and the program-specific seed in the registry.
- [ ] Add a **reference implementation** that independently reconstructs every control list from
  (pool, bins, seed) for the test in Task 9.
- [ ] **Verify (lead):** no program marker and no activation marker appears in **any** control set (in
  particular CXCR3 is absent from Treg-like controls); permuting program order leaves every control set
  byte-identical; the reference reconstruction matches the emitted controls exactly.

## Task 3: Scoring formula + primary normalization
**Executor:** CS specialist. **Verifier:** lead. **Files:** `stage1_pipeline.py` (scorer).
- [ ] `score(c,p) = mean(log-expr of measured panel genes) − mean(log-expr of frozen matched controls)`.
- [ ] Primary normalization: median total ≈ 9,819 then `log1p`. Archive a **CP10k sensitivity** table
  (Task 7) — never mix or equate. Normalization string enters the method hash.
- [ ] Name the method "deterministic expression-bin-matched panel-minus-control score" everywhere.
- [ ] **Verify (lead):** recompute scores for a random sample of (cell, program) from raw expression +
  stored controls and match the emitted `stage01_scores_full.parquet` to 5 decimals; the method-version
  hash changes vs v2; no string anywhere claims "exact Scanpy output."

## Task 4: Fully specify the activation-adjusted CTL sensitivity lane
**Executor:** CS specialist. **Verifier:** lead. **Files:** registry (actadj), scores table.
- [ ] Record: activation predictor genes, their exact predictor controls, **fit population = all 396k**,
  normalization, regression slope + intercept, residual formula, code hash, method hash.
- [ ] Keep the **raw** CD4 CTL-like score primary; the actadj lane is display/sensitivity-only and
  `stage2_selectable=false` (cannot be a Stage-2 pole).
- [ ] **Verify (lead):** the actadj residual reproduces from the stored slope/intercept + inputs; the
  lane is excluded from every selectable-program path.

## Task 5: Emit the six artifacts from one 396k run
**Executor:** CS specialist. **Verifier:** lead. **Files:** the six data artifacts.
- [ ] Single run emits together: `stage01_scores_full.parquet` (396k; donor, condition, all primary
  scores, CTL sensitivity; **no categorical fields**); `stage01_umap_overlay.json` (40k display sample,
  frozen x/y, same scores); `stage01_program_registry.json` (v3 schema); `stage01_summary.json` (396k
  medians + dispersion by program×condition and donor×condition — **not** estimated from the overlay);
  `stage01_validation.json` (Task 7); `stage01_selection.json` (Task 8 schema).
- [ ] **Verify (lead):** overlay scores equal the full-table scores for the overlay's barcodes; the
  summary is computed from 396k (spot-check two medians against the parquet); no categorical field
  exists in any artifact; selection schema matches exactly.

## Task 6: Freeze + hash the embedding coordinates
**Executor:** CS specialist. **Verifier:** lead.
- [ ] Freeze the existing x/y for the 40k overlay; do not regenerate the UMAP. Hash `barcode+x+y`.
- [ ] **Verify (lead):** the coordinate hash is pinned in the registry and re-derivable.

## Task 7: Validation battery (drives selectability)
**Executor:** CS specialist. **Verifier:** lead. **Files:** `stage01_validation.json`.
- [ ] **Panel robustness** per selectable program: leave-one-marker-out scoring; detection/coverage;
  alternative-control-seed sensitivity; all-marker-excluded control comparison; median-vs-CP10k
  sensitivity; correlation with every other program.
- [ ] **Donor × condition stability** for every donor×condition: measure heterogeneity; confirm no
  program is driven entirely by one donor; the selected condition has usable variation; a program's
  direction is not a pooling artifact. Capture D2's divergent Th1-like behavior explicitly.
- [ ] **Program redundancy:** full program-score correlation matrix within each condition and donor;
  flag Treg-like vs activation, Th1-like vs CTL-like, activation vs checkpoint-high, naïve-like vs
  memory/adhesion, and any correlation introduced by shared controls.
- [ ] **Full ↔ overlay agreement:** the 40k sample preserves donor×condition composition, per-program
  medians, score distributions, and broad program correlations (the 396k artifact stays authoritative).
- [ ] Emit machine-readable pass/fail per check with the thresholds used.
- [ ] **Verify (lead):** re-run two of the sensitivities independently; confirm pass/fail states match.

## Task 8: Decide + freeze selectability and selection rules
**Executor:** lead (from Task 7 results) with CS. **Files:** registry (`stage2_selectable`), selection rules doc.
- [ ] Set `stage2_selectable` + `not_selectable_reason` per program from Task 7. **No panel is
  selectable merely because one marker survives.** Th9 stays nonselectable until sufficiently measurable.
- [ ] Freeze selection rules (no UI change): same condition both poles → executable; different
  conditions → display-only (no Stage-2 selection artifact); all-times → display-only unless a pooled
  estimator is explicitly built; sensitivity fields → never executable; donor selector → display filter
  only (contrast uses all four donors). No cell threshold / membership.
- [ ] **Verify (lead):** every selectable program passes its robustness gate; selection.json emits only
  A, B, directions, one shared condition, `combination_policy: deferred_to_stage2`, and hashes.

## Task 9: Strengthen the verifier + mutation tests + env lock
**Executor:** lead. **Files:** `verify_reproduce.py`, `test_mutation_lock.py`, `environment.yml`.
- [ ] Verifier rejects any change to panels, controls, coefficients, roles, coordinates, registry, or
  full scores; keeps the forbidden-key scan (`p_value/q_value/fdr/perm/null`) and the served-artifact
  stale-string scan; independently reconstructs controls via the Task 2 reference.
- [ ] `test_mutation_lock.py`: mutate one control gene / one panel gene / one coefficient / one
  coordinate / one role each and assert the verifier fails.
- [ ] Move `cluster_scores.py`/`label_clusters.py`/argmax diagnostics out of the production chain
  (clearly labelled non-production).
- [ ] Ship `environment.yml` (conda) — Python is an env, not a pip package.
- [ ] **Verify (lead):** mutation tests fail on tampering and pass clean; the verifier re-derives all
  hashes on a clean checkout.

## Task 10: Independent verification (generator ≠ verifier)
**Executor:** independent pass (lead or a fresh agent that did **not** generate the artifacts).
- [ ] On a clean host: re-derive every hash; re-run the verifier + mutation tests; independently
  reconstruct all control lists; recompute a sample of scores; confirm the six artifacts agree and the
  summary is 396k-based. Emit `verification.json` (machine-readable, all-pass required).

## Task 11: Lock, supersede Stage-2, publish
**Executor:** lead. **Files:** HF revision, tag, Stage-2 markers, HANDOVER.
- [ ] Mark **every** v2 Stage-2 artifact: `superseded`, `incompatible_with_current_stage1`,
  `stage3_eligible=false`. Preserve v2 as historical (never overwrite / never present as current).
- [ ] Publish a **sanitized HF revision** containing only current v3 artifacts. Pin + verify the h5ad
  SHA and the minimal UMAP-seed SHA.
- [ ] Tag the method **`stage1-continuous-v3`**; prohibit downstream use of older registry hashes (the
  verifier rejects them).
- [ ] Update `docs/HANDOVER.md` + `01_programs/README.md` to v3; record the deferred Stage-2 remediation.

---

## Deferred to a separate effort (NOT executed here) — Stage-2 remediation
After Stage-1 v3 locks and v2 Stage-2 is marked superseded, Stage-2 must be fixed **before** re-running:
exact contributing-guide masks; eligible-only candidate ranking; ≥2 evaluated guides for guide
replication; honest donor-support denominators; generic `stage01_selection.json` consumption; a
method/config/input-aware `run_id`; off-axis specificity reporting. Only then: generate a new v3
selection and re-run the direct projection + Perturb2State from scratch. The mask's biological gene
content is scorer-independent, but its emitted artifact + hash are bound to the contrast/run and must
be regenerated + re-pinned at that time.

## Lock sequence (execution order)
1. Freeze panels + citations (T1). 2. Freeze the all-marker-excluded, per-program control algorithm
(T2). 3. Freeze normalization + scoring formula (T3–T4). 4. Rerun all 396k once (T5–T6). 5. Regenerate
registry + full table + summaries + overlay together (T5). 6. Run donor / LOMO / control-seed /
normalization sensitivities (T7). 7. Decide selectability from those results (T8). 8. Run the
strengthened verifier + mutation tests on a clean host (T9–T10). 9. Publish immutable hashes + the
sanitized dataset revision (T11). 10. Tag `stage1-continuous-v3`; prohibit older registry hashes (T11).

## Self-review (spec coverage)
- Panels intended/measured + provenance → T1. Control redesign + per-program RNG + reference test →
  T2/T9. Scorer name + formula + median-primary/CP10k-archive → T3. Actadj full spec → T4. Six
  artifacts from one 396k run → T5. Freeze/hash coordinates → T6. Full validation battery → T7.
  Selectability + frozen selection rules + no-combination → T8. Verifier + mutation tests + env + move
  diagnostics → T9. Independent verification → T10. Supersede Stage-2 + sanitized HF + tag → T11.
  Deferred Stage-2 fixes captured. UI-unchanged constraint carried throughout.
