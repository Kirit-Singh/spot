#!/usr/bin/env bash
# fetch stage — download public FASTQ from ENA and verify md5.
# TODO: resolve URLs via the ENA filereport API from the manifest; verify md5.
set -euo pipefail
acc="${1:?accession required}"
outdir="${2:?output dir required}"
mkdir -p "$outdir"
echo "fetch: ${acc} -> ${outdir} (ENA download + md5 verify: TODO)"
