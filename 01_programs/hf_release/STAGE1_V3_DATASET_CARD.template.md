# Stage-1 v3 — Hugging Face dataset card (TEMPLATE)

**TEMPLATE ONLY — nothing has been uploaded.** The block below is the card body; on upload it
becomes `README.md` in [`KiritSingh/spot-CD4-Marson`](https://huggingface.co/datasets/KiritSingh/spot-CD4-Marson).
Every value a real upload returns (revision, run timestamp, bundle hash) stays **null/pending**
here and must be filled from the actual run — never fabricated. No token appears in this repo.

Pending fields live in `stage1_release_hf_manifest.template.json`; per-artifact provenance and
rerun slots live in `schemas/artifact_provenance.json`.

---

```yaml
---
license: mit
language: [en]
tags: [single-cell, perturb-seq, CD4-T-cells, transcriptional-programs, glioblastoma]
pretty_name: spot CD4 transcriptional-program scores (Marson NTC subset)
size_categories: [100K<n<1M]
---
```

# spot — CD4 transcriptional-program scores (Marson NTC subset)

A **derived** non-targeting-control (NTC) subset of the Marson genome-scale CD4 perturb-seq data,
plus the continuous transcriptional-program scores spot's Stage-1 pipeline computes over it.

**This is not a cell-type classifier.** The scores are continuous program-compatibility values —
no categorical calls, no FDR/p-q, no prevalence. RNA program-compatibility does not demonstrate
lineage, protein expression, or function.

## Contents
| File | What it is |
|---|---|
| `ntc_clustered.h5ad` | the immutable source object (scVI + Leiden embedding of the NTC CD4 cells) |
| Stage-1 v3 bundle | the continuous program scores + display overlay and their provenance |

The embedding is **spot-specific and paper-inspired, not a verbatim reproduction** of the authors'
object: the scVI architecture follows the authors; the Leiden clustering, the seed, and the
396k quota-balanced subset are spot's.

## Revisions (history-preserving)
| Role | Revision | State |
|---|---|---|
| **Immutable source** — `ntc_clustered.h5ad` | `e5fcf98b56a9302921d402e97fc5a190bd88f9a6` | published; SHA-256 `2edc6d318415c8b0ee779d707ab86e26ddb6f0274db51ab4a12f21ebfda50e43` |
| Historical display | prior Stage-1 v2 manifest / display seed | retained, not deleted |
| **Stage-1 v3** (`stage1-continuous-v3.0.1`) | `stage1_release_hf_revision` = **pending** | not uploaded |

The source object at `e5fcf98b…` is **not modified**; v3 supersedes the display/manifest layer only.

## Reproduce
```bash
export SPOT_DATA=./spot_scvi
hf download KiritSingh/spot-CD4-Marson ntc_clustered.h5ad \
    --repo-type dataset --revision e5fcf98b56a9302921d402e97fc5a190bd88f9a6 --local-dir "$SPOT_DATA"
cd 01_programs/analysis && ./reproduce.sh    # pins the revision + SHA, then verifies per-barcode
```

## License & attribution
**MIT.** Upstream dataset is MIT (confirmed from the CZI Croissant metadata across all 12 splits);
the CZI Virtual Cells Platform Acceptable Use Policy applies. This card does **not** reproduce the
upstream MIT/NOTICE text verbatim — if a NOTICE file is ever included, copy the upstream text
*exactly* and only then call it verbatim.

Cite: Zhu, Dann, … Marson 2025; bioRxiv [doi:10.64898/2025.12.23.696273](https://doi.org/10.64898/2025.12.23.696273).
Program naming follows Masopust et al., *Nat Rev Immunol* 2026 (CC BY 4.0). Full source licenses:
`schemas/source_license_inventory.json`.

## Limitations
Decision-support only. One in-vitro CD4 dataset; needs cross-confirmation. Program scores are
suggestive, never confirmatory of identity or function.
