#!/usr/bin/env bash
# Guide-capture counting (kite): protospacer match, Hamming<=1, per cell barcode.
set -euo pipefail
r1="${1:?R1 required}"; r2="${2:?R2 required}"; index="${3:?kite index}"
t2g="${4:?guide t2g}"; outdir="${5:?output dir}"; chem="${6:-10xv3}"
mkdir -p "$outdir"
kb count --workflow kite -i "$index" -g "$t2g" -x "$chem" \
  -o "$outdir" --h5ad -t "${THREADS:-8}" "$r1" "$r2"
