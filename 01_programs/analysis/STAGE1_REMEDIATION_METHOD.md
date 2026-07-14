# spot Stage-1 — frozen replacement-method specification (remediation checkpoint, v2)

_Written before the first corrected rerun, for sign-off. Continuous-only design: the shipped
scientific outputs are continuous transcriptional-program scores, with **no categorical calls,
no compatibility flags, no resolution statuses, no random-reference cutoff, and no forced
argmax/top-program**. Names no expected counts or prevalence. Branch `stage1-remediation`._

## 0. Framing

This **withdraws unsupported inference and forced identity**; it does **not** "fix the null" or
complete validation.

- All per-cell inference is **removed**: no permutation null, no empirical p, no BH q, no
  `q < 0.05` gate, no "significant call" language, no significance-based UI filtering or counts.
  (The prior null was also mislabeled: its random panels were drawn **uniformly**, not
  expression-matched, so "size/expression-matched" was false — another reason to drop it, not
  rename it.)
- The shipped scientific outputs for the program axes are **continuous scores only**. No
  categorical winner is assigned or exported for analysis.
- Names are **transcriptional programs**, never cell identities or functions:
  **"Treg-like transcriptional program"** (field `treg_like_score`) and **"CD4 CTL-like
  transcriptional program"** (field `cd4_ctl_like_score`); likewise Th1-like/Th2-like/etc. Never
  emit bare `Treg`, `CTL`, "cell type", or "prevalence".

**Explicit disclaimer (must appear in outputs, card, and UI):** RNA program-compatibility does
**not** demonstrate lineage stability, protein expression, cytotoxicity, or suppressive function.

**Genuinely fixed:** forced Treg assignment removed; no cell/cluster is forced a label;
condition is not an input to any label; all p/q/FDR outputs removed; false reproducibility /
normalization / upstream-faithfulness claims corrected; reproduction verifies real per-barcode
outputs, not aggregate counts.

**Unresolved (documented, not solved):** whether the Treg-like cells are biologically Tregs;
whether the scores are calibrated; activation/timepoint confounding — **removing condition from
a labelling rule does not remove condition-associated biology from expression**, which remains
and is reported; generalization across donors; external / protein / functional validation.

## 1. Forced-maximum audit (every unconditional argmax removed)

| Site | Prior forced decision | Replacement |
|---|---|---|
| `label_clusters.py` | Treg = `max(clusters, key=Treg z)` — one winner, no threshold | **removed**; emit continuous per-program z-scores; no cluster label assigned |
| `label_clusters.py` | Naive/Memory vs Activated from `Rest fraction > 0.5` | **removed**; condition is `dominant_condition`, reported only |
| `label_clusters.py` | (prior draft) `regulatory_like_compatible` flag + `Activated z < 1` veto | **removed** — the veto silently restores mutual exclusivity; activated Treg-like transcription is biologically possible |
| `stage1_pipeline.py:226-227` | function = `Rf.argmax`, kept iff `q < 0.05` | **removed**; emit continuous `<prog>_like_score`; no flag, no status, no p/q |
| `stage1_pipeline.py:233-234` | differentiation = `Rd.argmax`, always assigned | **removed**; emit continuous differentiation scores; no winner |

## 2. Cluster level — `label_clusters.py`

**Emit continuous per-program z-scores only.** No `top_program`, no compatibility flag, no
veto, no threshold. Fields per cluster: `pct`, the five continuous program z-scores
(`naive_like_z`, `activated_z`, `cycling_z`, `adhesion_high_z`, `treg_like_z`),
`dominant_condition` (**reported, never an input**). **This cluster step is a non-production
diagnostic** (`SPOT_RUN_CLUSTER_DIAG=1`): the served overlay does not consume it and emits **no**
cluster label, no per-cluster colour key, and no argmax — cluster IDs survive only as numeric
technical provenance.

**Describe the z-scores honestly:** they are **standardized *within this dataset's* clusters**
(cluster mean minus cross-cluster mean over cross-cluster SD), so they mean **relatively
elevated here**, not an absolute threshold or absolute evidence. No "absolute threshold"
language anywhere.

## 3. Cell level — differentiation (`stage1_pipeline.py`)

Emit continuous `diff_naive_score`, `diff_activated_score`, `diff_memory_score`,
`diff_checkpoint_score` (the existing `score_panel` outputs; the 'X' panel is
"checkpoint-high-activated program", descriptive). **No argmax, no winner, no status.**

## 4. Cell level — function (`stage1_pipeline.py`)

Emit continuous per-program scores only, with the transcriptional-program names:
`th1_like_score`, `th2_like_score`, `th17_like_score`, `tfh_like_score`, `th9_like_score`,
**`treg_like_score`**, **`cd4_ctl_like_score`** (the `score_panel` outputs; scorer unchanged).

- **No permutation null, no p/q, no compatibility flag, no argmax, no `resolution_status`.**
- **Non-detection is descriptive, not a gate.** Drop the hard `CD27==0` / `IFNG==0` filters
  (probe-based Flex dropout makes absence-of-detection weak evidence of absence). Emit
  marker-detection descriptors (`gnly_detected`, `cd27_detected`, `ifng_detected`,
  `gata3_detected`, `ccr4_detected`) alongside the scores for interpretation.
- **CD4 CTL-like activation-conditioning is a descriptive SENSITIVITY score alongside the raw
  score**, never inside any inferential step: emit `cd4_ctl_like_score` (raw, primary) **and**
  `cd4_ctl_like_score_actadj` (activation-regressed residual). Both reported; neither drives a
  call (there are no calls).

## 5. No thresholds, no statuses

There is no per-cell threshold and no `*_compatible` / `*_status` field. The continuous scores
are the outputs. (A **display-only** score slider MAY exist in the demo UI: labelled a *display
filter*, **default off**, **never stored** as a biological call, excluded from exports.)

## 6. Sensitivity / reporting (not gates)

- Raw vs activation-adjusted CD4 CTL-like score, side by side.
- **Score distributions stratified by donor × condition** for every program — the required
  old-vs-new change-report axis; makes the residual activation/timepoint association **visible**
  rather than hidden behind a summary number.

## 7. Reproducibility and verifier (replaces the count-only gate)

- `verify_reproduce.py`: hash a **canonical sorted per-barcode table** — `barcode`, cluster,
  each continuous program score (cluster + differentiation + function), condition, donor,
  `method_version` — **exact** hashing for identifiers, **canonical rounding / numerical
  tolerance** for the float scores (raw float-byte hashes fail across environments). Also
  require: expected nonzero row count; unique-barcode-count == row-count; an exact expected
  **barcode-set hash**; no missing/extra records between overlay and records; schema validation.
  (The served overlay carries **no** display-argmax field; the map colour is a per-cell gradient
  over one selected continuous score, derived in the UI from the frozen per-score display domains,
  and is never hashed. The gate also enforces a cell-key whitelist, forbidden-field rejection, the
  `programs[]`/domain contract, and a stale-string scan over the served artifacts.)
- `stage1_pipeline.py`: regenerate **overlay and `stage01_cell_records.json` together** from one
  canonical per-barcode table; write temp then **atomically replace**; keep the wall-clock
  timestamp **out of the canonical body**.
- `reproduce.sh`: pin the exact **HF revision + downloaded h5ad SHA-256**; write to
  **`app/data/`**; schema-validate before any upload.

## 8. Fields removed / added

**Removed:** all functional p / q / empirical-p / BH outputs; the `q < 0.05` gate; the
permutation null; every categorical `func` / `ds` call; `is_treg_cluster`; the forced
`top_program`; the `regulatory_like_compatible` flag + `Activated z < 1` veto; the `TAU` /
95th-percentile cutoff and all `*_compatible` / `*_status` fields; the hard `CD27==0` /
`IFNG==0` gates; condition-derived labels; "FDR floor", "significant", "real Treg/CTL" language;
the aggregate-count `match_pct` "cell-for-cell" claim.
**Added:** continuous `treg_like_score`, `cd4_ctl_like_score` (+ `_actadj`), `th1_like_score`,
`th2_like_score`, `th17_like_score`, `tfh_like_score`, `th9_like_score`; continuous
differentiation scores; `method_version`. The served overlay is then **rebuilt from an explicit
whitelist**: a clean `meta` carrying the `programs[]` contract (score field, label, family, panel
genes, method, role, source) and **frozen per-score display domains** (p02/p50/p98 over the full
396k), with cells reduced to `barcode, x, y, cluster, condition, donor` + the 12 scores.

**Later removed in the schema cleanup (2026-07):** the per-cell `dominant_program_for_display_only`
argmax, the inherited `treg_score` / `func_margin` / `low_conf` fields, the marker-detection
descriptors, and all retired `meta` (embedding "verbatim-reproduction" claims, `nomen_counts`,
`match_pct`, per-cluster labels). Cluster program z-scores remain a non-production diagnostic only.

## 9. Explicitly NOT specified here

No expected counts, no target prevalence, no desired outcome. The corrected rerun produces
whatever the frozen continuous-score method produces; the old-vs-new change report (§6
donor×condition score distributions + exact per-barcode-join counts and artifact hashes) is
generated **after** the run and is the honest record of what changed.
