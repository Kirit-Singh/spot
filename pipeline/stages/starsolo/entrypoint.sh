#!/usr/bin/env bash
# STARsolo GEX: align + count; cells called here (EmptyDrops_CR). No BAM.
set -euo pipefail
r1="${1:?R1 required}"; r2="${2:?R2 required}"; index="${3:?STAR index dir}"
whitelist="${4:?barcode whitelist}"; outdir="${5:?output dir}"; umilen="${6:-12}"
mkdir -p "$outdir"
STAR --runMode alignReads --genomeDir "$index" \
  --readFilesIn "$r2" "$r1" --readFilesCommand zcat \
  --soloType CB_UMI_Simple --soloCBwhitelist "$whitelist" \
  --soloCBstart 1 --soloCBlen 16 --soloUMIstart 17 --soloUMIlen "$umilen" \
  --soloFeatures Gene GeneFull \
  --soloCBmatchWLtype 1MM_multi_Nbase_pseudocounts --soloUMIdedup 1MM_CR \
  --soloCellFilter EmptyDrops_CR \
  --outSAMtype None --runThreadN "${THREADS:-8}" \
  --outFileNamePrefix "$outdir/"
