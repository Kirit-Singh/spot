# Claude Science review — spot Stage-1 remediation + corrected Stage-2 plan (2026-07-10)

_Independent CS audit of the four remediation docs, all four Stage-1 code files, and the
Stage-2 plan, checked against the actual data (`GWCD4i.DE_stats.h5ad`, the suppl tables, the
cell-level h5ads, the served `spot_scvi/` dir). Verbatim verdict below, followed by a
reconciliation note on what was fixed in response._

---

## Bottom line (reviewer)

The **code** does what the remediation says: `label_clusters.py` and `stage1_pipeline.py` are
genuinely continuous-only — the forced Treg pick and the permutation/p/q/argmax apparatus are gone,
and condition is not an input to any label. The **Stage-2 plan** is the strongest document of the
set; nearly every quantitative claim verifies exactly against the released files, and it consumes a
continuous program (not a hard Treg identity) correctly.

Three things undercut the package as a *lockable* unit (none cosmetic):
1. The two "after-the-run" documents disagreed on the canonical hash.
2. The "396,000 per-cell records" claim is not what the shipped code produces (it writes 40,000).
3. The reviewer could not corroborate the corrected rerun from what was mounted (served data dir
   still held old forced-label artifacts; the review folder shipped code, not the emitted outputs).

## (a) Does the code withdraw the forced label + invalid inference? — **Yes, sound.**
`label_clusters.py` emits continuous `program_scores_within_dataset_z`, `dominant_condition`
(reported, never gates), `display_markers`. No `is_treg_cluster`, no forced label, no activation
veto. `stage1_pipeline.py` emits the 12 continuous scores + `cd4_ctl_like_score_actadj`; no
permutation null, no p, no BH q, no `q<0.05` gate, no non-detection hard gates. The **one residual
argmax** — `dominant_program_for_display_only` — is properly quarantined (excluded from records and
from the hashed table, labelled display-only), but its safety lives in the frontend, not the data:
the value still rides inside every overlay cell, so a consumer that reads it as a call reintroduces
a forced label. Clean pass on the code.

## (b) Per-barcode verifier + determinism — **sound.**
`score_panel` sorts `gl_idx` and `ctrl_idx` before summation (removes hash-randomized set-iteration
order); `PYTHONHASHSEED=0` is redundant belt-and-suspenders. Seeded `default_rng(12345)` over a
sorted candidate index → reproduces across environments. The verifier hashes a canonically-sorted
per-barcode table with rounded floats, checks nonzero cardinality, unique-barcodes==rows, exact
barcode-set hash, `method_version`, overlay⊆records, and equality to a frozen REFERENCE. **Caveats:**
(i) it verifies the **40,000-cell overlay**, not the full 396k universe; (ii) the schema type-check
samples only the first 200 cells.

## (c) Retraction statement — **accurate + well-bounded, but one overclaim + one inconsistency.**
Right: the unresolved section (n=4, D2 diverges, activation/timepoint confound remains in
expression, no protein/suppression/cytotoxicity/external validation) is honest and correctly
humble. **Overclaim:** "verifies the full barcode-indexed output" — it covers the 40k overlay.
**Inconsistency:** `canonical_table_sha256` was `6e1665d1…` in the statement + `verify_reproduce.py`
REFERENCE but `869bba84…` in `CHANGES.md` — both cannot describe the same run. **Completion-state:**
the served `/mnt/tcenas/models/spot_scvi/` still held old forced-label artifacts
(`is_treg_cluster`, `top_program`, `nomen_counts`), timestamped before the corrected code — so the
reviewer could not locate the frozen corrected run on the mounted disk.

## (d) Corrected Stage-2 consumes the program correctly — **yes, impressive factual grounding.**
Re-verified directly against `GWCD4i.DE_stats.h5ad`: 33,983 target×condition rows, 11,526 unique
targets; layer set + shapes; 3,341 rows pass the coverage gate = 1,860 genes; FOXP3 Stim48 = 4/3 DE
/ 1,360 cells; **Stim48 `ontarget_significant` = 7,195** (the plan correctly sourced the h5ad; the
suppl **CSV** gives 7,193); off-target flags booleans; `by_donors.h5mu` six 2-vs-2 pair matrices,
n=4; all four Stim48 samples in run R2 (no within-Stim48 run confound); cell-level `guide_type`
has a real `non-targeting` category; no NTC row in `DE_stats`; `ntc_clustered.h5ad` `.obsm`/`.uns`
empty (no saved scVI model → §5's pseudobulk premise holds). It consumes a **program direction**
(A = activation-induced regulatory-like at Stim48, a_down sole primary), not a Treg identity; the
prior defects are all correctly disposed of. **Still weak:** (i) §6 mislabels the B pole as CD4
CTL-like where §4 defines it Th1-like; (ii) §3 requires full-universe membership "not the 40k
display sample," but Stage-1 currently emits only the 40k overlay — a cross-stage handoff gap;
(iii) `stage01_selection.json` is still unbuilt (a labelled Stage-2 prerequisite); (iv)
essentiality/CEGv2 + GO sources still unresolved (deferred).

---

## Reconciliation — what was fixed in response (2026-07-10)

The reviewer's three "undercut" items resolve into **two real doc defects** and **one review-scope
artifact**. Fixed on branch `stage1-remediation`:

1. **Canonical-hash disagreement (real).** `CHANGES.md` carried the stale pre-determinism-fix hash
   `869bba84…`. The correct, frozen hash is **`6e1665d1…`** — confirmed by running
   `verify_reproduce.py` against the committed `01_programs/app/data/` (see below). `CHANGES.md`
   updated to `6e1665d1…`; now agrees with the statement + the REFERENCE.
2. **"396,000 records" (real).** The code writes **40,000** (the overlay's barcodes; scores are
   computed over the full 396k in memory but only the 40k display sample is emitted/hashed).
   `CHANGES.md` §2 + §3 corrected to 40,000; the statement's "full barcode-indexed output" →
   "40,000-cell overlay's per-barcode output."
3. **"Cannot corroborate the corrected rerun" (review-scope artifact, not a repo defect).** The
   reviewer saw only the staged code + the stale `/mnt/tcenas/.../spot_scvi` workdir, **not** the
   repo's committed outputs. The committed `01_programs/app/data/stage01_umap_seed.json` **is** the
   corrected continuous output (40,000 cells, 12 continuous scores, **zero** forbidden fields — no
   `func`/`ds`/`top_program`/`is_treg_cluster`/`nomen_counts`), and `verify_reproduce.py` passes
   against it: _"OK — 40000 cells; per-barcode table verified (hash 6e1665d1…); overlay↔records
   agree; schema + barcode-set intact."_ The stale `spot_scvi` workdir is an old scoring intermediate,
   not the served workbench; a deployment-hygiene cleanup, tracked separately, not a PR blocker.
4. **Stage-2 §6 B-pole mislabel (real).** `b_up (B / CD4 CTL-like increase)` → `b_up (B / Th1-like
   increase)`, consistent with §4/§8's `B = inflammatory / Th1-like`.

**Documented, not "fixed" (out of scope / correctly deferred):** the 40k-overlay-vs-full-universe
handoff gap and the unbuilt `stage01_selection.json` are **Stage-2 implementation prerequisites** —
carried as explicit open items in `STAGE1_EXTERNAL_REVIEW_HANDOFF.md` for the external reviewer and
the Stage-2 build, since Stage-2 implementation is intentionally not started. The residual
display-only argmax (frontend-guaranteed), the 200-cell schema sample, and the essentiality/GO
`unresolved` holes are likewise carried as documented limitations.
