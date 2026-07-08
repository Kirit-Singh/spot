# pipeline/ — from-raw Perturb-seq ingest (Lane upstream of A/B)

Takes a public single-cell **Perturb-seq** dataset from **raw FASTQ** to the
matrices + DE that Discovery and the Evidence graph consume. Its own top-level
lane (different compute profile + cadence); it terminates at the `contracts/`
seam, emitting `Evidence`-compatible DE rows + the perturbation landscape.

## The DAG (Perturb-seq = TWO libraries)
```
fetch (SRA/ENA)  ->  fastp (read QC)
        |-- GEX   :  STARsolo (align+count, splice-aware)   -> cells x genes
        |-- GUIDE :  kite/kb (protospacer match, Hamming<=1) -> cells x guides
                  \\-- reconcile barcodes: cells called ONCE on GEX;
                       guides assigned to those cells (ambient-threshold, not argmax)
        ->  cell QC (rapids-singlecell/GPU or scanpy/CPU): empty-drop, doublet, ambient,
            mixscape (flag CRISPRi escapers -- label, never silently drop)
        ->  pseudobulk by target vs NTC  ->  DE (DESeq2/edgeR-QLF)
        ->  outputs: DE table + perturbation landscape  ->  contracts/ -> Evidence + Discovery
```

## Principles
- **Containerized stages, docker-only host (tcefold).** The image IS the environment; every
  stage pinned by `@sha256:` digest. Open-source tools only (STARsolo, kb-python, fastp,
  samtools, rapids-singlecell) -- never Cell Ranger.
- **Manifest is the gate.** `contracts.DatasetManifest` must validate before analysis:
  accessions + per-FASTQ md5, chemistry/whitelist, reference build + checksums, guide library
  + NTCs, pinned image digests, DE params, seeds. Given only the manifest, reproduce byte-for-byte.
- **Never invent a statistic.** DE emits computed stats only; under-powered targets
  (< min_cells_per_perturbation) emit "insufficient power", not a fabricated p-value.
- **From-raw, no backfill.** Recompute deterministically; delete raw FASTQ after counts
  validate (re-fetchable via manifest accessions+md5).

## Orchestration
Nextflow-in-container (content-addressed `-resume`, retry, resource caps) invoked by spot's
own driver only after the manifest gate passes. The STAR index is a shared content-addressed
artifact (genome+GTF+STAR version+sjdbOverhang), built once, mounted read-only; cap concurrent
STAR at 1-2 (91 GB RAM); GPU (3x 3090) only for the cell-QC stage, one dataset/sample per card.

## Testing (real-data-free in CI)
Tiny subsampled FASTQ (`seqtk`) + a mini reference (chr21 / target-gene mini-genome) + a mini
guide library; valid AND invalid fixture manifests for the gate; per-stage golden-value tests;
a fast end-to-end on the subsample; `fetch` mocked to serve the fixture; GPU stages fall back to
scanpy (CPU) so cell-QC is CI-testable.

## Compute (tcefold)
24c / 91 GB RAM / 3x RTX 3090 / 4.1 TB. STARsolo/kb/DESeq2 = CPU/RAM; GPU only for
rapids-singlecell. `--outSAMtype None` (no BAM); keep FASTQ compressed; retain sparse mtx +
cell metadata + guide assignments + DE tables + logs.

## Layout
`_template/dataset/` skeleton every dataset scaffolds from (raw/qc/counts/cells/de/outputs/logs
+ manifest.yaml); `stages/` per-stage Dockerfiles + entrypoints; `datasets/<id>/` actual runs
(gitignored -- data). Manifest schema: `contracts/src/spot_contracts/manifest.py`.

Status: foundation (manifest contract + gate + structure). Stage images + Nextflow + fixtures
land next.
