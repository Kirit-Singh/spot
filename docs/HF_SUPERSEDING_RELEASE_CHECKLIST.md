# Hugging Face superseding-release checklist

This is a **publication gate**, not a publication record. No upload is authorized or
performed by this checklist.

## Current public state

- Repository: `KiritSingh/spot-CD4-Marson`
- Immutable public revision: `e5fcf98b56a9302921d402e97fc5a190bd88f9a6`
- Public revision inspected: 2026-07-13
- Scientific files present:
  - `ntc_clustered.h5ad` — source object; manifest SHA-256
    `2edc6d318415c8b0ee779d707ab86e26ddb6f0274db51ab4a12f21ebfda50e43`
  - `stage01_umap_seed.json` — historical v2 40k display seed
- v3 `stage01_scores_full.parquet`: **not present**; current Git release status is
  `release_staging_not_served`.
- The public revision's `LICENSE` infers a copyright holder for the upstream dataset.
  The official Virtual Cells record declares MIT but supplies no copyright notice, so a
  superseding revision must not repeat that inference.

## Preconditions for a superseding revision

- [ ] Freeze the exact Git commit, solver lock and clean-tree status.
- [ ] Regenerate the v3 bundle from the public H5AD using the committed reproduction
      command; independently verify all protected scientific hashes.
- [ ] Include the complete current v3 artifact inventory, including the authoritative
      396k score Parquet, registry, input/release manifests, summary, frozen coordinates,
      display overlay, validation/activation artifacts and selection contract.
- [ ] Compute and record raw-file and canonical-content SHA-256 values, sizes, schemas,
      dimensions, identifier namespaces, normalization and missing-value semantics.
- [ ] Replace the external `LICENSE`/`NOTICE` with wording that preserves the official
      dataset's MIT declaration but does not invent an upstream copyright holder.
- [ ] Update the dataset card to distinguish the original CZI data, spot-derived v2
      history and current v3 outputs; preserve all prior revisions.
- [ ] Run a field-level privacy review: permit only public coded donor/library IDs and
      barcodes already present in the source; reject added demographics and local paths.
- [ ] Run repository secret/path scans and external-bundle scans on the exact upload
      directory.
- [ ] Download the proposed revision into a clean directory by immutable revision and
      re-hash every file; run the public reproduction/verifier commands there.
- [ ] Record the resulting immutable HF revision in Git only after the upload and
      clean-room verification succeed.

## Publication boundary

Until every precondition passes and an immutable superseding revision exists, public
documentation must describe the v3 full-score artifact as staged, not published. Never
silently replace or delete the historical v2 revision.
