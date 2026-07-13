# 01_programs — CD4 transcriptional-program scores

Interactive UMAP of CD4⁺ non-targeting-control (NTC) cells carrying **continuous
transcriptional-program scores** — Treg-like, CD4 CTL-like, Th1/Th2/Th17/Tfh/Th9-like, plus
differentiation programs — scored from the Marson genome-scale CD4 perturb-seq NTC cells.

> **Exploratory decision-support — not a cell-type classifier.** Continuous scores, not
> categorical calls: no forced labels, no FDR/p-q, no "cell type", no prevalence. **RNA
> program-compatibility does not demonstrate lineage, protein expression, or function.** See
> `REMEDIATION_STATEMENT.md`.

Stage-1 hands Stage-2 a **generic selection contract**: any two of the continuous programs, in
independent directions (`high`/`low`), at the same or different timepoints — **not** a fixed
biological pair. `Treg-like → Th1-like` is a labelled demo default only.

## Layout
- `app/` — the workbench (`01_page.html`), the rendered methodology report (`01_notebook.html`),
  the vcp provenance trace (`01_trace.html`), and `app/data/` (the overlay + per-cell records).
- `analysis/` — the reproducible pipeline, the frozen method spec (`STAGE1_REMEDIATION_METHOD.md`),
  the change report (`STAGE1_REMEDIATION_CHANGES.md`), and the verifiers.
- `inputs/` — pointer to the public CZI dataset (marker panels live in the code).
- `outputs/` — generated intermediates (gitignored).

## What it produces
A 40,000-cell display overlay (`SEED=12345`), each cell carrying **12 continuous program scores**
plus a `meta.programs[]` contract and frozen per-score display domains that drive the UI. **No
categorical calls and no per-cell/per-cluster biological labels** — the workbench colours by one
selected score at a time (display-only). Cluster IDs are carried only as numeric technical
provenance; donor × condition structure is reported, not hidden (see `STAGE1_REMEDIATION_CHANGES.md`).

## Reproduce — scoring tier (deterministic, per-barcode)
Requirements: a scanpy environment (CPU is fine). The tested lock is `analysis/requirements.txt`
(Python 3.11.15; `anndata==0.12.19` · `scanpy==1.11.5` · `numpy==2.3.3` · `scipy==1.15.2` ·
`pandas==2.2.3` · `huggingface_hub==1.23.0`). Peak RAM ~21–25 GB (loads the full 396k × 18,130
matrix); allow ≥32 GB.

Two tiers: the **embedding tier** (raw public data → `ntc_clustered.h5ad`: scVI + Leiden, GPU-scale,
run once, cached — spot-specific and paper-inspired, **not** a verbatim reproduction) and the
**scoring tier** (`ntc_clustered.h5ad` → continuous scores → overlay: deterministic, CPU,
per-barcode reproducible). Only the scoring tier runs here; the source object is published.

```bash
export SPOT_DATA=./spot_scvi
hf download KiritSingh/spot-CD4-Marson ntc_clustered.h5ad \
    --repo-type dataset --revision e5fcf98b56a9302921d402e97fc5a190bd88f9a6 --local-dir "$SPOT_DATA"
cd analysis && ./reproduce.sh    # pins the HF revision + SHA, runs the chain, writes app/data/ atomically, verifies per-barcode
```
`reproduce.sh` runs `stage1_pipeline.py` (continuous per-cell scores; **no FDR/p-q/argmax**;
rebuilds the overlay from an explicit whitelist) → `verify_reproduce.py` (the per-barcode +
schema-contract gate). Source object `ntc_clustered.h5ad`: 3.84 GB, SHA-256 `2edc6d31…`, HF
revision `e5fcf98b…` (dataset **MIT**). The published revision still carries the historical v2
display seed; a history-preserving v3 revision is prepared and pending owner-reviewed upload
(source object unchanged) — see `hf_release/`.

## Pipeline (analysis/)
- `stage1_pipeline.py` → continuous per-cell scores (`score_genes` panels; no null/p/q/argmax);
  rebuilds the overlay + records from a whitelist.
- `verify_reproduce.py` → per-barcode canonical-hash + schema-contract gate.
- `cluster_scores.py` / `label_clusters.py` → optional, non-production diagnostics only (set
  `SPOT_RUN_CLUSTER_DIAG=1`); not part of the served chain.

## Provenance & verification
Prefer running the verifiers (expect exit 0) over trusting any hash copied into a doc — provenance
edits legitimately re-derive a registry's self/raw hash without changing the science.
- `verify_stage1_provenance.py`, `verify_stage1_t8.py` — re-derive the marker provenance and the
  measurement bundle from raw inputs; mutation/forgery suites included.
- `stage2_bridge/verify_selection_contract.py` — independent semantic verifier of an emitted
  `spot.stage01_selection.v3` contract.
- `stage2_bridge/protected_hashes.py`, `stage01_full_release_verification.json` — the protected
  baseline and the outer attestation.
- `app/01_notebook.html` (rendered report, not an executed notebook) and `app/01_trace.html` (vcp trace).

Frozen, citation-invariant scientific identities (cite these, not the registry self/raw hash):
scores canonical `43c4296d…`, frozen T7b validation raw `1c14cd28…`, scorer projection `008c1da1…`,
scorer VIEW canonical `5d1d8c36…`. The full binding set is re-derived by the verifiers above.

## Data source & naming
Marson GWCD4i genome-scale CRISPRi perturb-seq (bioRxiv 2025.12.23.696273) — NTC CD4 cells, 4
donors × Rest/Stim8hr/Stim48hr — public on the **CZI Virtual Cells Platform**. Program **naming**
follows Masopust et al., *Guidelines for T cell nomenclature*, Nat Rev Immunol 2026;26:298-313; the
gene panels are **curated canonical markers** (restricted to genes measurable in this dataset), not
lists taken from that paper.

## The v3 selection contract (Stage-1 → Stage-2)
Any supported `(program A, direction A, program B, direction B, condition/mode)` yields the same
typed `spot.stage01_selection.v3` contract: a typed `execution_status`, an `analysis_mode`
(`within_condition` | `temporal_cross_condition`), two ordered separate poles A/B (**no** combined
objective — that is Stage-2's), and two independent per-program arms keyed by the perturbation's
**desired change** (`increase|decrease`), never the pole. `selection_id = sha256(canonical_content)[:16]`
binds the executable scorer VIEW (`app/data/stage01_stage2_registry_view.json`), so a display/citation
edit never moves it. Schema + materializer + verifier live in `analysis/stage2_bridge/`; see
`schemas/README.md` for the authoritative contract definition.
