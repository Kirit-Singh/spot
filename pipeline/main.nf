#!/usr/bin/env nextflow
// spot from-raw Perturb-seq DAG. Invoked by the spot driver only after the
// manifest gate passes. Two libraries: GEX -> STARsolo, GUIDE -> kite/kb; cells
// called once on GEX, guides assigned, cell QC, pseudobulk + DESeq2 vs NTC.
// Every process pins its image by @sha256 from the manifest.
nextflow.enable.dsl = 2

params.manifest = null
params.outdir = 'pipeline/datasets'

process FETCH   { container params.fetch_image;    input: val acc; output: path "*.fastq.gz"; script: "entrypoint.sh ${acc} ." }
process FASTP   { container params.fastp_image;    input: path fq;  output: path "qc/*";        script: "entrypoint.sh ${fq} qc" }
process STARSOLO{ container params.starsolo_image; input: path gex; output: path "counts/*";    script: "STARsolo --soloType CB_UMI_Simple --outSAMtype None ..." }
process GUIDE   { container params.guide_image;    input: path gd;  output: path "guides/*";    script: "kb count --workflow kite ..." }
process CELLQC  { container params.cellqc_image;   input: tuple path(counts), path(guides); output: path "cells/*"; script: "cellqc.py --mixscape ..." }
process DE      { container params.de_image;       input: path cells; output: path "de/*";      script: "de.R --model deseq2 --contrast target_vs_ntc ..." }

workflow {
  gex   = Channel.fromList(params.gex_runs   ?: [])
  guide = Channel.fromList(params.guide_runs ?: [])
  gex_fq   = FASTP(FETCH(gex))
  guide_fq = FASTP(FETCH(guide))
  counts = STARSOLO(gex_fq)     // cells called ONCE here
  gcounts = GUIDE(guide_fq)
  DE(CELLQC(counts.combine(gcounts)))
}
