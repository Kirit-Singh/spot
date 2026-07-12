# 01_programs — CD4 transcriptional-program scores

Interactive UMAP of CD4⁺ NTC cells carrying **continuous transcriptional-program scores** —
Treg-like, CD4 CTL-like, Th1-like/Th2-like/Th17-like/Tfh-like/Th9-like, plus differentiation
programs — scored from the Marson genome-scale CD4 perturb-seq non-targeting-control (NTC) cells.

> **Exploratory decision-support — not a cell-type classifier.** These are continuous scores, not
> categorical calls: no forced labels, no FDR/p-q, no "cell type", no prevalence. **RNA
> program-compatibility does not demonstrate lineage stability, protein expression, cytotoxicity,
> or suppressive function.** See `REMEDIATION_STATEMENT.md`.

Stage-1 hands Stage-2 a **candidate Treg-like transcriptional program** to study, **not** a
confirmed Treg identity.

## Layout
- `app/` — the workbench (`01_page.html`), the rendered methodology report (`01_notebook.html`),
  and the vcp data-provenance trace (`01_trace.html`). `app/data/` holds the overlay + per-cell
  records the pages render.
- `analysis/` — the reproducible pipeline chain (below), the frozen method spec
  (`STAGE1_REMEDIATION_METHOD.md`), the change report (`STAGE1_REMEDIATION_CHANGES.md`), and the
  Claude Science reviews.
- `inputs/` — pointer to the public CZI dataset (marker panels live in the code).
- `outputs/` — generated intermediates (gitignored).

## What it produces
A 40,000-cell display overlay (`SEED=12345`), each cell carrying **12 continuous program scores**
(`treg_like_score`, `cd4_ctl_like_score` + `_actadj`, `th1_like_score`, …, `diff_*_score`), plus a
`meta.programs[]` contract and frozen per-score display domains (quantiles p02…p99 over the full 396k) that
drive the UI. **No categorical calls and no per-cell/per-cluster biological labels** — the workbench
colours by one selected continuous score at a time (a display-only colour transform; the scores
themselves are the scientific output). Cluster IDs are carried only as numeric technical provenance.
The activation/timepoint and donor structure is reported (not hidden) — see
`analysis/STAGE1_REMEDIATION_CHANGES.md` for donor×condition score distributions.

## Setup & run — reproduce from scratch

### Requirements
A scanpy environment (CPU is fine for the scoring tier). The **tested lock** that reproduced the
frozen per-barcode hashes is `analysis/requirements.txt` — pinned to the exact versions used:
- Python 3.11.15
- `anndata==0.12.19` · `scanpy==1.11.5` · `numpy==2.3.3` · `scipy==1.15.2` · `pandas==2.2.3`, and
  `huggingface_hub==1.23.0` (the `hf` CLI) to fetch the embedded object. (pandas 2.2 and numpy 2.3
  coexist fine — the earlier "numpy<2" note was incorrect.)
- Peak RAM ~**21–25 GB** (loads the full 396k × 18,130 matrix); allow **≥32 GB**. A faithful run
  took ~5 min on a 91 GB host.

### Two tiers — know the boundary
1. **Embedding tier** (raw public data → `ntc_clustered.h5ad`): scVI + Leiden on the NTC CD4 cells.
   GPU-scale (the full source is ~1.84 TB); run **once**, cached. This embedding is **spot-specific
   and paper-inspired, NOT a verbatim reproduction** (scVI architecture matches the authors; the
   Leiden clustering and the seed are spot's; the 396k subset is spot's quota-balanced sample, not
   the authors' NTC weighting). You do not need to re-run it — the object is published.
2. **Scoring tier** (`ntc_clustered.h5ad` → continuous program scores → overlay): deterministic,
   CPU, and **per-barcode reproducible** — this is what runs here.

### Fetch the embedded object (pinned)
Published (**public, MIT**) at
[**KiritSingh/spot-CD4-Marson**](https://huggingface.co/datasets/KiritSingh/spot-CD4-Marson),
superseding revision **`e5fcf98b`**. `ntc_clustered.h5ad` is **3.84 GB** (SHA-256 `2edc6d31…`,
verified by `reproduce.sh`). Fetch:
```bash
export SPOT_DATA=./spot_scvi
hf download KiritSingh/spot-CD4-Marson ntc_clustered.h5ad stage01_umap_seed.json \
    --repo-type dataset --revision e5fcf98b56a9302921d402e97fc5a190bd88f9a6 --local-dir "$SPOT_DATA"
```

### Run the scoring tier
```bash
cd analysis
./reproduce.sh          # pins the HF revision + SHA, runs the chain, writes app/data/ atomically, verifies per-barcode
```
which runs `stage1_pipeline.py` (continuous per-cell program scores; **no FDR/p-q/argmax**; rebuilds
the overlay + 40k records from an explicit whitelist) → `verify_reproduce.py` (the **per-barcode +
schema-contract** gate). The cluster diagnostics (`cluster_scores.py`/`label_clusters.py`) are **not**
part of this chain — the served overlay carries no biological cluster labels.

### Reproducible (per-barcode, deterministic)
`verify_reproduce.py` hashes a **canonical sorted per-barcode table** (barcode, cluster, condition,
donor, the 12 scores) and enforces the schema contract (cell-key whitelist, forbidden retired fields,
`programs[]`/domains, a stale-string scan). Determinism: `SEED=12345`, sorted control indices,
`PYTHONHASHSEED=0`. Frozen reference: `canonical_table_sha256 = 6e1665d1…`,
`barcode_set_sha256 = 1224312e…`, n = 40,000 (unchanged by the schema cleanup).

## The pipeline (analysis/)
- `stage1_pipeline.py` → continuous per-cell program scores (`score_genes` panels; **no null, no
  p/q, no argmax, no categorical call**); CD4 CTL-like reports a raw score + an
  activation-conditioned sensitivity score; **rebuilds the overlay + records from a whitelist**
  (`meta.programs[]`, frozen display domains; no inherited/retired fields).
- `verify_reproduce.py` → the per-barcode canonical-hash + schema-contract gate.
- `cluster_scores.py` / `label_clusters.py` → **optional, non-production** per-cluster diagnostics
  only; not part of the served chain (set `SPOT_RUN_CLUSTER_DIAG=1` to run them for inspection).

Method frozen in `STAGE1_REMEDIATION_METHOD.md`; old-vs-new in `STAGE1_REMEDIATION_CHANGES.md`.

## Provenance
- `app/01_notebook.html` — a **rendered methodology report** of `stage1_pipeline.py` (NOT an
  executed notebook; numeric results come from running the pipeline, not the renderer).
- `app/01_trace.html` — the vcp data-provenance trace.
- `analysis/STAGE1_EXTERNAL_REVIEW_CS.md`, `STAGE1_REMEDIATION_METHOD.md`,
  `STAGE1_REMEDIATION_CHANGES.md` — the reviews, frozen method, and change report.

## Data source
Marson GWCD4i genome-scale CRISPRi perturb-seq (bioRxiv 2025.12.23.696273) — NTC CD4 cells, 4
donors × Rest/Stim8hr/Stim48hr — public on the **CZI Virtual Cells Platform**. Program **naming**
follows Masopust et al., *Guidelines for T cell nomenclature*, Nat Rev Immunol 2026;26:298-313 —
the naming consensus the program labels follow. The gene panels themselves are **curated canonical
markers** (restricted to genes measurable in this dataset), not gene lists taken from that paper.

## Stage-1 v3 T8 production contract (fail-closed) + measurement bundle
The frozen T7b validation (`app/data/stage01_validation.json`, raw SHA-256 `1c14cd28…`) yields
**0 of 33 program×condition pairs passing** the pre-registered Stage-1 production gate. The T8 layer
makes that outcome machine-enforced — via **independent re-derivation**, not trust-by-self-hash —
without altering the immutable validation or any pre-registered gate/panel/score/seed/threshold.

**Separate release statuses** (never conflated): a reproducible *measurement bundle* can be lockable
while *production selection* stays fail-closed and *overlay/app deployment* stays blocked.
- `measurement_bundle_lockable` — **true**: v3 registry (`20f91fdd…`), full 396k×15 scores
  (`de63b496…`, canonical content `43c4296d…`), regenerated `by_program_condition` summary, scoring
  code, independent verifier + mutation suite, and a real Linux solver lock are all present and
  independently verified. This implies **nothing** about selectability or identity.
- `production_stage2_ready` — **false** (0/33). `panel_provenance_status` —
  **`PRIMARY_LOCATORS_VERIFIED_BOUNDED`**: all 53 measured marker-program pairs now carry a bounded
  primary-source locator in the registry `marker_provenance`/`panel_provenance` (18 prior-ledger + 14
  lineage + 21 state/CTL completions, source SHAs pinned and enforced by `verify_stage1_provenance.py`;
  Masopust stays naming-only). This is bounded/association-level provenance, not a scorer change and not
  a production/overlay/app promotion. `overlay_release_ok` — **false** (the built v3 overlay is proven
  `overlay==full` but **not** deployed). `app_deployment_ready` — **false**. The current pointer is
  therefore a **`candidate`**, never `current`/`locked`.

Artifacts (served contracts in `app/data/`):
- `stage01_selectability_v3.json` — 33 records, all `production_selectable=false`, each with the exact
  failing/undefined hard-gate **multiset** (base portability never confers selectability).
- `stage01_validation_semantics.json` — **row-identifiable** interpretation of every one of the 841
  results (`source_result_index` + `source_row_canonical_sha256`), preserving **two dimensions**
  (`metric_predicate_met`/`metric_defined`/`undefined_reason` vs `gate_outcome`/`flagged`); a false
  hard-gate is never reinterpreted as advisory; Th9 zero-IQR / observed-None stay **undefined**.
- `stage01_current.json` — fail-closed `candidate` pointer with the separate statuses above; the v2
  registry is `HISTORICAL_NOT_CURRENT`; the v3 registry is bound for provenance (not a served selectability source).
- `stage01_release_manifest.json` — distinct release gates + raw hashes of every artifact (served,
  analysis, and gitignored release-staging bound by hash).

Code + verification (in `analysis/`):
- `stage1_t8_derive.py` — pure derivation used **only** by the generator `gen_stage1_t8.py`.
- `verify_stage1_t8.py` — **independent** verifier (re-implements the derivation from scratch;
  re-derives the 33 records + 841 semantics rows from the raw validation and **exact-multiset**-compares,
  recomputes all declared counts, checks every cross-pointer). Generator ≠ verifier.
- `test_stage1_t8.py` — mutation/forgery suite: even a **fully-resealed** forgery (self-hashes +
  manifest bookkeeping recomputed) is caught by the independent re-derivation.
- `stage1_t8_preflight.py` — fail-closed selection preflight: verifies the whole bundle **before**
  reading selectability, then requires the complete binding set (validation/gate-spec/input-manifest/
  selectability/current-pointer/method + v3 registry namespace), `namespace=production`, one shared real
  timepoint, allowed direction + selectable primary role, and per-pole `production_selectable`. Every
  current A/B pair is non-executable.
- `stage01_v3_recovery_verification.json` (receipt), `stage01_solver_lock.txt` (conda `--explicit` +
  in-env pip freeze), `stage01_full_release_verification.json` (outer attestation binding code/env/
  inputs/outputs + scope). `stage01_validation_independent_check.json` remains an intentionally **limited**
  sampled observation and is not broadened.
- `reproduce_t8.sh` — regenerates the layer from pinned inputs (gen → independent verify → mutation
  suite → full-release attestation) **without** overwriting historical v2 or deploying the v3 overlay.

The Stage-1 app (`01_page.html`) and the Stage-2 direct CLI (`02_geneskew/analysis/direct/run_screen.py`)
both load this fail-closed contract and **cannot** emit a production selection (0/33) — the app shows a
muted inline reason (no banner, appearance unchanged); the CLI rejects before any computation.

This records only that **no current program-condition pair cleared the frozen production gate** — not
that any program is biologically invalid, nor that panel provenance is confirmed.
