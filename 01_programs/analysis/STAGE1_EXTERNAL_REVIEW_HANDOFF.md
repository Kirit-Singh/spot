# spot Stage-1 (+ Stage-2 plan) — external adversarial review handoff

**Purpose.** You are an independent, adversarial senior computational immunologist / stats
reviewer. Decide whether spot **Stage-1** (the *continuous-score remediation*) is sound and
lockable as an **exploratory** artifact, and whether the **Stage-2 plan** is methodologically
safe to implement. Try to break it. Reproduce every load-bearing number yourself.

## What this is
An exploratory CD4 transcriptional-program **scoring** workbench: CD4⁺ NTC cells from the Marson
genome-scale CRISPRi Perturb-seq carry **continuous `*_like_score` fields** (Treg-like, CD4
CTL-like, Th1/Th2/Th17/Tfh/Th9-like, differentiation programs). **No categorical calls, no
cell-type labels, no FDR/p/q, no prevalence.** RNA program-compatibility ≠ lineage / protein /
function. Stage-2 consumes a *candidate* program, not a confirmed identity.

## Read these (current system)
- `01_programs/REMEDIATION_STATEMENT.md` — the retraction + fixed-vs-unresolved split + exact IDs.
- `01_programs/analysis/STAGE1_REMEDIATION_METHOD.md` — frozen method spec (continuous v2).
- `01_programs/analysis/STAGE1_REMEDIATION_CHANGES.md` — old→new + donor×condition distributions.
- `01_programs/analysis/{cluster_scores,label_clusters,stage1_pipeline,verify_reproduce}.py`,
  `reproduce.sh` — the deterministic chain.
- `02_geneskew/STAGE2_PLAN.md` — the corrected Stage-2 plan (a_down-only primary; no q-family).
- `01_programs/app/programs.html` — the workbench UI (margin-gated display colouring; scores primary).

**Ignore `01_programs/analysis/REVIEW_MEMO.md` as a description of the current system** — it is the
*prior* external review that reviewed the now-**withdrawn categorical pipeline** (FDR / functional
calls / "Treg cluster") and triggered this remediation. Kept for provenance only.

An **internal Claude Science audit** of this remediation is in
`01_programs/analysis/STAGE1_REMEDIATION_REVIEW_CS.md` — it verified the code is continuous-only and
the Stage-2 numbers against the real `DE_stats.h5ad`, and flagged doc defects (hash disagreement,
a 396k-vs-40k records overclaim, a Stage-2 B-pole mislabel) that are **now fixed**; its "cannot
corroborate the rerun" item was a review-scope artifact (it saw staged code + a stale workdir, not
the committed `app/data/`, which passes `verify_reproduce.py` at hash `6e1665d1…`). Read it for the
known-limitations list; you are the independent check on all of it.

## What was remediated (so you know what changed)
- Forced argmax labels + permutation-FDR/q gate → **removed**; continuous scores only.
- "Preregistered" → "**prospectively frozen**"; "paper-exact embedding" → "**paper-inspired,
  spot-specific**" (scVI arch matches authors; Leiden + seed + 396k subset are spot's).
- Retracted the false CP10k↔median byte-invariance claim and the aggregate-count repro gate.
- Reproducibility is now **per-barcode** (canonical sorted table SHA-256), deterministic
  (`SEED=12345`, sorted control indices, `PYTHONHASHSEED=0`).
- CD4 CTL-like carries a raw score **and** an activation-conditioned `_actadj` sensitivity score.

## Reproduce (per-barcode, deterministic)
```
cd 01_programs/analysis && ./reproduce.sh
```
Pins HF `KiritSingh/spot-CD4-Marson` @ `e5fcf98b56a9302921d402e97fc5a190bd88f9a6`;
`ntc_clustered.h5ad` SHA-256 `2edc6d31…50e43`; frozen output
`canonical_table_sha256 = 6e1665d1…ed2755`, `barcode_set_sha256 = 1224312e…435a93`, n = 40,000.
Peak RAM ~21–25 GB; **`numpy<2`** (pandas 2.2). Confirm the hash matches — a mismatch is a fail.

## Pressure-test these open questions (author-flagged, unresolved)
1. **Activation/timepoint confound.** Scores are not activation-matched; condition is reported but
   remains in expression. Is any program score separable from generic Stim activation?
2. **CD4 CTL-like vs Th1-like co-location.** Panels are gene-disjoint (Th1 = CXCR3/TBX21/IFNG/
   IL12RB2; CTL = GNLY/PRF1/GZMH/KLRD1/GZMB/NKG7), yet the high cells co-locate on the fixed scVI
   UMAP. Author's position: expected biology (CD4 CTL is a Th1-lineage cytotoxic effector state),
   left as-is with `_actadj` as the de-confounder. **Do you agree, or should CTL be forced discrete
   (and how, without a CTL-conditioned sub-embedding)?**
3. **Display colouring.** The map colour is a display-only argmax, margin-gated to "mixed" when the
   top-two scores are close. Author is considering making a **continuous single-program gradient**
   the primary view instead. Is the gated-argmax honest enough, or is the gradient necessary?
4. **Cross-donor generalization.** n=4 donors; D2 diverges. Is anything donor-driven?
5. **Embedding provenance.** Spot's Leiden/seed/subset ≠ authors'. Does that bias the scores?
6. **GO enrichment** is unresolved (specified/pinned or omitted, never promised) — Stage-2 plan.
7. **Stage-2 plan.** a_down-only primary endpoint; `layers['log_fc']`; masked/renormalized score +
   coverage gate; cross-fit NTC null; donor-pair discordance (n=4); 7,195 not a correction family;
   scLDM/Perturb2State secondary only (no training). Any latent q-value / circularity / leakage?
8. **40k-overlay-vs-full-universe handoff (known open, Stage-2-implementation-gated).** Stage-1
   currently emits + hashes scores for the **40,000-cell display overlay** only (the 396k are scored
   in memory, then discarded at the emit loop). Stage-2 §3 requires membership over the **frozen
   full-cell universe, not the 40k display sample**. These do not yet meet: either Stage-1 must emit
   full-universe scores or Stage-2's input contract changes. `stage01_selection.json` (Stage-2's
   single input) is **not built** — Stage-2 implementation is intentionally not started. Is emitting
   the full 396k the right fix, or should Stage-2 consume the overlay? (Display-only argmax
   `dominant_program_for_display_only` still travels inside each overlay cell — its "not a call"
   guarantee lives in the frontend; the verifier's schema type-check samples only the first 200
   cells. Both are documented limitations.)

## Deliverable
A verdict (lockable-as-exploratory: yes/no) with the specific defects that would block it, each
tied to a reproduced number or a concrete failing scenario. Distinguish **must-fix-before-lock**
from **document-as-limitation**.

## Exact identifiers
PR: https://github.com/Kirit-Singh/spot/pull/16 · branch `stage1-remediation`.
HF v3.0.1 release revision `8bf04b6c…`; historical v2 is retained at tag
`stage1-continuous-v2` / revision `e5fcf98b…`.
Hashes as above. Code `MIT`; data licenses in `DATA_LICENSES.md`.
