#!/usr/bin/env bash
# Reproduce the spot Stage-1 CD4 transcriptional-program SCORES from a pinned public input.
# Continuous-score remediation (v2): no forced labels, no FDR/p/q, no "cell type" calls.
# Deterministic (SEED fixed in stage1_pipeline.py). Every score the map shows is the output
# of this chain — nothing hand-placed.
#
# Chain:
#   1. Fetch the embedded object at a PINNED HF revision and VERIFY its SHA-256.
#   2. Score  per-cluster continuous program z-scores (cluster_scores.py -> label_clusters.py;
#             NO forced cluster label).
#   3. Per-cell continuous program scores + emit overlay AND per-cell records together
#             (stage1_pipeline.py).
#   4. Stage  the emitted artifacts ATOMICALLY into app/data/.
#   5. Verify a per-barcode canonical hash (verify_reproduce.py) — not aggregate counts.
#   6. Render the provenance report (a rendered report, NOT an executed notebook).
#
# Requires a scanpy env + the `hf` CLI (pip install -U huggingface_hub). The embedded object
# is fetched from the public HF dataset (MIT); no account needed.
set -euo pipefail
export PYTHONHASHSEED=0          # deterministic set iteration (belt-and-suspenders; scores also sort control idx)
export SPOT_DATA="${SPOT_DATA:-./spot_scvi/}"
APP_DATA="${SPOT_APP_DATA:-../app/data}"    # the SERVED path; artifacts are staged here
HF_REPO="${SPOT_HF_REPO:-KiritSingh/spot-CD4-Marson}"
# PINNED input revision + content hash (the embedding object is immutable; the superseding
# remediation revision does not change the h5ad content). Override only to reproduce a different pin.
HF_REVISION="${SPOT_HF_REVISION:-<PIN_AFTER_SUPERSEDE>}"
H5AD_SHA256="${SPOT_H5AD_SHA256:-2edc6d318415c8b0ee779d707ab86e26ddb6f0274db51ab4a12f21ebfda50e43}"
echo "using SPOT_DATA=$SPOT_DATA  APP_DATA=$APP_DATA  HF_REPO=$HF_REPO@$HF_REVISION"

echo "[1/6] Fetch the embedded object at the pinned revision + verify SHA-256 ..."
if [ ! -f "$SPOT_DATA/ntc_clustered.h5ad" ]; then
  hf download "$HF_REPO" ntc_clustered.h5ad stage01_umap_seed.json \
      --repo-type dataset --revision "$HF_REVISION" --local-dir "$SPOT_DATA" \
    || { echo "  x fetch failed — install the HF client: pip install -U huggingface_hub"; exit 1; }
fi
GOT=$(shasum -a 256 "$SPOT_DATA/ntc_clustered.h5ad" 2>/dev/null | awk '{print $1}' \
      || sha256sum "$SPOT_DATA/ntc_clustered.h5ad" | awk '{print $1}')
if [ "$GOT" != "$H5AD_SHA256" ]; then
  echo "  x SHA-256 mismatch: got $GOT expected $H5AD_SHA256 — refusing to proceed on an unpinned object." >&2
  exit 1
fi
echo "  ok: h5ad SHA-256 verified."

echo "[2/6] Per-cluster continuous program z-scores (no forced label) ..."
python3 cluster_scores.py
python3 label_clusters.py

echo "[3/6] Per-cell continuous scores + emit overlay AND records together ..."
python3 stage1_pipeline.py    # writes stage01_umap_seed.emitted.json + stage01_cell_records.emitted.json

echo "[4/6] Stage artifacts atomically into $APP_DATA ..."
mkdir -p "$APP_DATA"
cp stage01_umap_seed.emitted.json "$APP_DATA/.stage01_umap_seed.json.tmp"
cp stage01_cell_records.emitted.json "$APP_DATA/.stage01_cell_records.json.tmp"
mv -f "$APP_DATA/.stage01_umap_seed.json.tmp"   "$APP_DATA/stage01_umap_seed.json"
mv -f "$APP_DATA/.stage01_cell_records.json.tmp" "$APP_DATA/stage01_cell_records.json"

echo "[5/6] Per-barcode reproducibility gate (canonical sorted table, not aggregate counts) ..."
( cd "$APP_DATA/.." && python3 "$(pwd)/../01_programs/analysis/verify_reproduce.py" ) \
  || ( cd "$(dirname "$APP_DATA")" && python3 "$OLDPWD/verify_reproduce.py" )

echo "[6/6] Render the provenance report (rendered report, NOT an executed notebook) ..."
python3 render_notebook.py stage1_pipeline.py "$APP_DATA/../01_notebook.html"

echo "OK — Stage-1 continuous-score chain regenerated from the pinned input and per-barcode-verified."
