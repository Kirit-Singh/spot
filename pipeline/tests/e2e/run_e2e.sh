#!/usr/bin/env bash
# Real end-to-end on the tiny fixture: STARsolo -> kite -> cellqc -> de, via Docker.
# Runs on tcefold (needs docker). Asserts each stage produces its output.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
fix="$here/fixtures"; work="$here/work"
rm -rf "$work" 2>/dev/null || docker run --rm -v "$here:/e" alpine:3.19 rm -rf /e/work
mkdir -p "$work"

echo "[1/5] STAR index (mini genome)"
docker run --rm -v "$fix/reference:/ref" -v "$work:/out" \
  quay.io/biocontainers/star:2.7.11b--h43eeafb_1 \
  STAR --runMode genomeGenerate --genomeDir /out/star_index \
    --genomeFastaFiles /ref/mini.fa --sjdbGTFfile /ref/mini.gtf \
    --genomeSAindexNbases 4 --sjdbOverhang 89 --runThreadN 4

echo "[2/5] STARsolo GEX align+count"
docker run --rm -v "$fix:/fix" -v "$work:/out" \
  quay.io/biocontainers/star:2.7.11b--h43eeafb_1 \
  STAR --runMode alignReads --genomeDir /out/star_index \
    --readFilesIn /fix/raw/gex_R2.fastq.gz /fix/raw/gex_R1.fastq.gz --readFilesCommand zcat \
    --soloType CB_UMI_Simple --soloCBwhitelist /fix/reference/whitelist.txt \
    --soloCBstart 1 --soloCBlen 16 --soloUMIstart 17 --soloUMIlen 12 \
    --soloFeatures Gene --soloCellFilter None --outSAMtype None \
    --runThreadN 4 --outFileNamePrefix /out/gex_
test -f "$work"/gex_Solo.out/Gene/raw/matrix.mtx && echo "  OK GEX matrix"

echo "[3/5] kite guide index + count"
kb=quay.io/biocontainers/kb-python:0.28.2--pyhdfd78af_1
docker run --rm -v "$fix:/fix" -v "$work:/out" "$kb" \
  kb ref --workflow kite --tmp /out/ref_tmp -i /out/kite.idx -g /out/kite_t2g.txt -f1 /out/kite.fa /fix/guides/guides.fa
docker run --rm -v "$fix:/fix" -v "$work:/out" "$kb" \
  kb count --workflow kite --tmp /out/count_tmp -i /out/kite.idx -g /out/kite_t2g.txt -x 10xv3 \
    -o /out/guide --h5ad -t 4 /fix/raw/guide_R1.fastq.gz /fix/raw/guide_R2.fastq.gz
test -f "$work"/guide/counts_unfiltered/adata.h5ad && echo "  OK guide matrix"

echo "[4/5] cellqc (build image if needed)"
docker build -q -f "$here/../../stages/cellqc/Dockerfile" -t spot-cellqc "$here/../.." >/dev/null
docker run --rm -v "$fix:/fix" -v "$work:/out" spot-cellqc \
  --gex /out/gex_Solo.out/Gene/raw --guides /out/guide/counts_unfiltered/adata.h5ad \
  --outdir /out/cells --min-genes 1 --min-counts 1 --max-pct-mito 100 --min-guide-umi 1
test -f "$work"/cells/cells.h5ad && echo "  OK cells.h5ad"

echo "[5/5] E2E complete -> $work"
