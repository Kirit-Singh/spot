# Stage-1 v3 — Hugging Face dataset card & NOTICE (TEMPLATE)

**TEMPLATE ONLY. Nothing here has been uploaded.** This file is the history-preserving card
and NOTICE wording for a *future*, owner-reviewed Stage-1 v3 upload to
[`KiritSingh/spot-CD4-Marson`](https://huggingface.co/datasets/KiritSingh/spot-CD4-Marson).
Every value that a real upload would return (a new revision, a run timestamp, a bundle hash)
is left **pending / null** in the companion manifest and MUST be filled from the actual run —
never fabricated. Do not upload or use credentials from this repo.

## What this dataset is
A **derived NTC-subset embedding** of the Marson genome-scale CD4 perturb-seq data
(non-targeting-control CD4 cells), produced by spot's Stage-1 pipeline. It is
**spot-specific and paper-inspired, not a verbatim reproduction** of the authors' object.

## License & NOTICE
- **License:** MIT. spot redistributes this *derived* subset under MIT with attribution to
  the upstream authors and the CZI Virtual Cells Platform (upstream dataset license confirmed
  MIT from the dataset Croissant metadata across all 12 splits; CZI Acceptable Use Policy
  applies).
- **Attribution:** Zhu, Dann, … Marson 2025; bioRxiv doi:10.64898/2025.12.23.696273.
- **On the upstream MIT notice:** this card does **not** reproduce the upstream MIT license /
  NOTICE text verbatim. If a NOTICE file is included in an upload, copy the upstream text
  **exactly** and only then describe it as verbatim; otherwise state attribution as above
  without a verbatim claim.

## History-preserving revisions
This upload adds the v3 bundle as a **new revision** and keeps prior revisions intact.

| Role | Object | Revision | State |
|---|---|---|---|
| **Immutable source** (unchanged by v3) | `ntc_clustered.h5ad` | `e5fcf98b56a9302921d402e97fc5a190bd88f9a6` | published; SHA-256 `2edc6d318415c8b0ee779d707ab86e26ddb6f0274db51ab4a12f21ebfda50e43` |
| **Historical display** | Stage-1 v2 manifest / display seed | (prior revision) | retained as historical, not deleted |
| **Stage-1 v3 release** | v3 bundle (`stage1-continuous-v3.0.1`) | `stage1_release_hf_revision` = **pending** | not uploaded |

The source `ntc_clustered.h5ad` at revision `e5fcf98b…` is **not modified**; v3 supersedes the
*display / manifest* layer only.

## Reproduce
The v3 scoring tier is reproduced from `01_programs/analysis/reproduce.sh` (pins the HF
revision + SHA, then verifies per-barcode). See `01_programs/README.md`.

## Pending fields (fill from the real upload run; leave null until then)
`stage1_release_hf_revision`, `upload_run_utc`, `uploaded_by`, `returned_commit_sha`,
`bundle_sha256`, `verifier_receipt_sha256` — see `stage1_release_hf_manifest.template.json`.
