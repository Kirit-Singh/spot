# 01_programs — CD4 transcriptional-program scores

Interactive UMAP of CD4⁺ NTC cells carrying **continuous transcriptional-program scores** —
Treg-like, CD4 CTL-like, Th1-like/Th2-like/Th17-like/Tfh-like/Th9-like, plus differentiation
programs — scored from the Marson genome-scale CD4 perturb-seq non-targeting-control (NTC) cells.

> **Exploratory decision-support — not a cell-type classifier.** These are continuous scores, not
> categorical calls: no forced labels, no FDR/p-q, no "cell type", no prevalence. **RNA
> program-compatibility does not demonstrate lineage stability, protein expression, cytotoxicity,
> or suppressive function.** See `REMEDIATION_STATEMENT.md`.

Stage-1 hands Stage-2 a **generic v3 selection contract** — any two of the continuous programs,
independent directions (`high`/`low`), at the same or different timepoints — **not** a fixed
biological pair and **not** a confirmed cell identity. Treg-like → Th1-like is a labelled demo
default only.

## Layout
- `app/` — the workbench (`programs.html`), the rendered methodology report (`01_notebook.html`),
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
The source object `ntc_clustered.h5ad` (**3.84 GB**, SHA-256 `2edc6d31…`, verified by `reproduce.sh`) is
published (**public**; dataset **MIT** per the CZI source page) at
[**KiritSingh/spot-CD4-Marson**](https://huggingface.co/datasets/KiritSingh/spot-CD4-Marson), revision
`e5fcf98b56a9302921d402e97fc5a190bd88f9a6`. Fetch:
```bash
export SPOT_DATA=./spot_scvi
hf download KiritSingh/spot-CD4-Marson ntc_clustered.h5ad \
    --repo-type dataset --revision e5fcf98b56a9302921d402e97fc5a190bd88f9a6 --local-dir "$SPOT_DATA"
```
> The **current public release** is `stage1-continuous-v3.0.1` at immutable HF revision
> [`8bf04b6c503aa6c6dd2ed8447a2cec55fd56bb6c`](https://huggingface.co/datasets/KiritSingh/spot-CD4-Marson/tree/8bf04b6c503aa6c6dd2ed8447a2cec55fd56bb6c)
> and tag `stage1-continuous-v3.0.1`. Historical v2 is preserved at tag
> `stage1-continuous-v2` / revision `e5fcf98b…`. The scoring source H5AD is byte-unchanged, so
> reproduction intentionally continues to fetch its original immutable input revision above.
> The candidate and final anonymous re-download checks are recorded in
> [`analysis/HF_PUBLICATION_RECEIPT.json`](analysis/HF_PUBLICATION_RECEIPT.json).

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

## Stage-1 v3 generic selection contract + measurement bundle
Stage-1 is a **continuous measurement system + generic selector**. There is **no production/research
split and no 0-of-33 gate** anywhere in the active contract. Any supported (program A, direction A,
program B, direction B, condition/mode) yields the **same typed** `spot.stage01_selection.v3` contract:
- `execution_status` — `ready` | `refused` | `awaiting_estimator`;
- `analysis_mode` — `within_condition` | `temporal_cross_condition` (same or different timepoints);
- two **ordered, separate poles** A/B — **no combined/balanced objective** (that belongs to Stage-2);
- two **independent per-program arms** (`away_from_A` on A, `toward_B` on B) keyed by the perturbation's
  **desired change** (`increase|decrease`), never the pole `high|low` — joined by the UI with no combined
  score. Refuse only an exactly-identical `(program, pole, condition)` tuple.

`selection_id = sha256(canonical_content)[:16]` binds the executable **scorer VIEW**
(`app/data/stage01_stage2_registry_view.json`, canonical `5d1d8c36…`), so a display/citation edit never
moves it. Constants: `dataset_id=marson2025_gwcd4_perturbseq`, `source_h5ad_sha256=2edc6d31…`,
`source_hf_revision=e5fcf98b…`, `stage1_method_version=stage1-continuous-v3.0.1`. Treg-like → Th1-like is
a **labelled demo default only**, never canonical.

**Frozen scientific identities** (stable, citation-invariant — cite these, not the registry self/raw
hash, which legitimately re-derives on provenance edits): scores canonical content `43c4296d…`, frozen
T7b validation raw `1c14cd28…`, scorer projection `008c1da1…`, scorer VIEW canonical `5d1d8c36…`. The
current registry self/raw and the full binding set are re-derived and checked by
`verify_stage1_provenance.py` (do not hard-code them here).

**Measurement bundle** (present + independently verified): the v3 registry, full 396k×15 scores
(canonical `43c4296d…`), regenerated `by_program_condition` summary, activation-association table,
scoring code, independent verifier + mutation suite, and a Linux solver lock. The current pointer is a
**`candidate`** (the built v3 overlay is proven `overlay==full` but **not** deployed).

Served/analysis artifacts:
- `stage01_stage2_registry_view.json` — the executable scorer VIEW `selection_id` binds (canonical
  `5d1d8c36…`); excludes display labels / citations / provenance.
- `stage01_selectability_v3.json` (raw `7c326a86…`) — the frozen within-condition LOMO validation kept
  **only as historical provenance** (`active_gate:false`); it is **not** a selection gate. Arm eligibility
  uses the existing frozen **base portability** from the validation (Th9-like is non-portable).
- `stage01_validation.json` (raw `1c14cd28…`) — the immutable frozen T7b validation, referenced for
  provenance; never re-interpreted.
- `stage01_current.json` — the `candidate` pointer; the v2 registry is `HISTORICAL_NOT_CURRENT`.
- `stage01_release_manifest.json` — release gates + raw hashes of every bound artifact.

Code + verification (in `analysis/`, generator ≠ verifier throughout):
- `stage2_bridge/emit_selection_contract.py` — the deterministic **materializer** `build_contract` for
  ANY pair; `stage2_bridge/arm_keys.py` is the single source of truth for the desired_change arm keying.
- `verify_selection_contract.py` — independent semantic verifier of an emitted v3 contract (re-derives
  `selection_id`, the estimator/mode/execution tuple, and the arm identity from local frozen rules).
- `verify_stage1_provenance.py`, `verify_stage1_t8.py` — independent re-derivation of the marker
  provenance and the measurement bundle from the raw inputs; mutation/forgery suites catch even a
  fully-resealed forgery.
- `stage01_solver_lock.txt`, `stage01_full_release_verification.json` — the environment lock and the
  outer attestation binding code/env/inputs/outputs + scope.
- `reproduce_t8.sh` — regenerates the whole layer from pinned inputs (gen → independent verify → mutation
  suite → attestation) **without** overwriting historical v2 or deploying the v3 overlay. Prefer running
  it (**expect exit 0**) over trusting any hard-coded count/hash in this file.

This records a reproducible measurement + a generic, verifiable selection contract — **not** that any
program is a confirmed cell identity, nor that panel provenance is clinically confirmed.
