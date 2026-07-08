#!/usr/bin/env bash
# fastp stage — read QC / adapter trim with parameters from the manifest.
# TODO: fastp --in1 R1 --in2 R2 --json/--html reports into outdir.
set -euo pipefail
r1="${1:?R1 required}"
r2="${2:?R2 required}"
outdir="${3:?output dir required}"
mkdir -p "$outdir"
echo "fastp: ${r1} ${r2} -> ${outdir} (fastp QC/trim: TODO)"
