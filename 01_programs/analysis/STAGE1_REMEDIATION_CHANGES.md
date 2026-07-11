# spot Stage-1 — remediation change report (old vs new)

_Generated after the corrected continuous-score rerun (branch `stage1-remediation`,
method `stage1-continuous-v2`, SEED=12345, run on the pinned object
SHA-256 `2edc6d31…`). This is the honest record of what changed; it precedes any
outward-facing publication._

## 1. What changed, structurally

The Stage-1 outputs change from **forced categorical calls behind an invalid FDR** to
**continuous transcriptional-program scores with no categorical calls**. Nothing is
"renamed" — the inference and the forced labels are **withdrawn**.

| | Previous artifact | Superseding artifact |
|---|---|---|
| Cluster label | forced argmax → exactly one "Treg" cluster; Naive/Memory from Rest-fraction (condition leak) | continuous per-cluster program z-scores; **no forced label**; condition reported only; a `dominant_program_for_display_only` colour key excluded from analysis/exports |
| Per-cell function | `argmax` kept iff permutation-FDR `q<0.05`; hard `CD27==0`/`IFNG==0` gates | continuous `*_like_score` per program; **no p/q, no FDR, no argmax, no call**; non-detection is a descriptive marker field |
| Per-cell differentiation | `argmax`, always assigned | continuous `diff_*_score`; **no winner** |
| Naming | "Treg", "CD4-CTL" (identity) | "Treg-like / CD4 CTL-like transcriptional program" (`treg_like_score`, `cd4_ctl_like_score`) |
| Verifier | aggregate `nomen_counts` overlap (a zero-cell overlay passed at "100%") | **per-barcode canonical sorted-table hash** + barcode-set + overlay↔records + schema |

## 2. Exact counts

**Retracted (previous 40,000-cell overlay — these categorical "calls" no longer exist):**
- function: `—` 33,004 · Th1 4,550 · Treg 1,051 · Th2 528 · CD4-CTL 573 · Tfh 236 · Th9 40 · Th17 18
- differentiation: N 6,409 · A 21,072 · M 10,871 · checkpoint-high 1,648

**Superseding (this run):** **no categorical calls emitted.** 40,000 overlay cells + 396,000
per-cell records, each carrying **12 continuous scores**: `treg_like_score`, `cd4_ctl_like_score`
(+ `cd4_ctl_like_score_actadj`), `th1_like_score`, `th2_like_score`, `th17_like_score`,
`tfh_like_score`, `th9_like_score`, `diff_naive_score`, `diff_activated_score`,
`diff_memory_score`, `diff_checkpoint_score`.

**Per-barcode reproducibility (frozen gate):**
- `n_cells` = 40,000; overlay↔records agree; schema + barcode-set intact.
- `barcode_set_sha256` = `1224312e52231f4b2e07c192b39c6f9c69dd6e2d5b8bd64d936c17a9b2435a93`
- `canonical_table_sha256` = `869bba8437e4ec34bf0754b8a9f49328956ec42d790fbd35fbb3cfd8e55268ea`

## 3. Donor × condition score medians (the residual confound, made visible)

Median score across the 396,000 balanced cells. The point of showing this stratified is that
**removing condition from a labelling rule does not remove condition-associated biology from
expression** — the association is real, reported, not solved.

**`treg_like_score`** — higher at Stim48hr than Rest (consistent with an activation-*induced*
program at 48 h), with clear donor spread:
| | D1 | D2 | D3 | D4 |
|---|---|---|---|---|
| Rest | −0.211 | −0.212 | −0.163 | −0.198 |
| Stim8hr | −0.046 | 0.076 | 0.081 | −0.009 |
| Stim48hr | 0.011 | 0.148 | 0.010 | −0.005 |

**`cd4_ctl_like_score`** — **peaks at Stim8hr** (activation-driven), strong donor variation
(D3/D4 ≈ 0.69/0.62). This is the activation confound in plain sight — the "cytotoxic-like"
program tracks activation timing, not a stable CD4-CTL lineage:
| | D1 | D2 | D3 | D4 |
|---|---|---|---|---|
| Rest | −0.075 | −0.207 | 0.052 | −0.067 |
| Stim8hr | 0.308 | 0.321 | 0.693 | 0.619 |
| Stim48hr | −0.007 | 0.217 | 0.217 | 0.141 |

**`th1_like_score`** — highest at Stim8hr for D1/D3/D4 (≈0.46) but **donor D2 is negative
everywhere** — a single-donor divergence that any downstream use must respect (n=4):
| | D1 | D2 | D3 | D4 |
|---|---|---|---|---|
| Rest | −0.350 | −0.675 | −0.335 | −0.386 |
| Stim8hr | 0.462 | −0.243 | 0.451 | 0.473 |
| Stim48hr | −0.101 | −0.499 | −0.259 | −0.277 |

## 4. What this run does and does not establish

**Does:** removes forced identity and invalid inference; emits reproducible, per-barcode-verified
continuous program scores; makes the activation/timepoint and donor structure visible.

**Does not:** demonstrate that Treg-like cells are Tregs (or CD4 CTL-like cells are cytotoxic);
calibrate the scores; remove the activation/timepoint confound (§3); establish cross-donor
generalization (n=4, D2 diverges); or provide any protein / suppression / cytotoxicity / external
validation. Stage-1 is an **exploratory program-scoring workbench**, not a Treg/CTL classifier.
