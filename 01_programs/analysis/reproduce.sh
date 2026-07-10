#!/usr/bin/env bash
# Reproduce the spot Stage-1 CD4 nomenclature map, end to end, from the public
# CZI dataset. Deterministic (SEED fixed in stage1_pipeline.py). Every label the
# map shows is the output of a script in this chain — nothing is hand-placed.
#
# The full chain, front to back:
#   1. Fetch      the Marson GWCD4i NTC CD4 dataset from the CZI Virtual Cell Platform.
#   2. Embed+cluster  scVI (5000 HVG, n_latent=30, batch=donor) -> 100-NN UMAP ->
#                     Leiden-0.8 (13 clusters). GPU-scale; run once, cached in the
#                     object as obs['L0.8'] (run_scvi.py). Not re-run here.
#   3. Label      each Leiden cluster -> a state program (Naive/Activated/Cycling/
#                 Memory/Treg) by a fixed, confound-aware marker rule:
#                   cluster_scores.py  -> per-cluster panel z-scores (loads the object)
#                   label_clusters.py  -> the rule -> cluster_labels.json
#                 (Cycling if proliferation clear; Treg = the one Treg-high but
#                  not-strongly-activated cluster; rest -> Naive/Memory if resting,
#                  else Activated. IL2RA/CD25, GZMB, FAS, MKI67 dropped as
#                  activation-confounded.) Reproduces the deployed labels exactly.
#   4. Per-cell   score each cell on the Masopust et al. differentiation + function
#                 panels behind a permutation-FDR floor, read the labels from
#                 cluster_labels.json, and EMIT stage01_umap_seed.emitted.json
#                 (stage1_pipeline.py); we then stage that to data/stage01_umap_seed.json.
#   5. Verify     the staged overlay must match the committed reference.
#
# Requires: a scanpy env + the `hf` CLI (huggingface_hub) — pip install -U huggingface_hub.
# The embedded object is fetched from the public HF dataset (step 1); no account needed.
set -euo pipefail
# Dir holding ntc_clustered.h5ad + stage01_umap_seed.json. Set SPOT_DATA to override.
export SPOT_DATA="${SPOT_DATA:-./spot_scvi/}"
echo "using SPOT_DATA=$SPOT_DATA"

echo "[1/5] Ensure the embedded Step-2 object is present in $SPOT_DATA ..."
HF_REPO="${SPOT_HF_REPO:-KiritSingh/spot-CD4-Marson}"
if [ ! -f "$SPOT_DATA/ntc_clustered.h5ad" ]; then
  echo "  fetching ntc_clustered.h5ad + stage01_umap_seed.json from HF dataset $HF_REPO (public, MIT) ..."
  hf download "$HF_REPO" ntc_clustered.h5ad stage01_umap_seed.json \
      --repo-type dataset --local-dir "$SPOT_DATA" \
    || { echo "  x fetch failed — install the HF client: pip install -U huggingface_hub"; exit 1; }
fi
# (The upstream 'embedding tier' that PRODUCES ntc_clustered.h5ad -- raw CZI download via
#  the vcp CLI + scVI/Leiden, GPU-scale / ~1.84 TB -- is documented in the README; not here.)

echo "[2/5] Label clusters (confound-aware marker rule -> cluster_labels.json) ..."
python3 cluster_scores.py       # per-cluster panel z-scores (one object load)
python3 label_clusters.py       # the rule -> cluster_labels.json (reproduces deployed labels)

echo "[3/5] Per-cell scoring + EMIT the overlay (reads cluster_labels.json) ..."
python3 stage1_pipeline.py
# stage the emitted overlay to the served path so the gate below checks exactly what we just emitted
mkdir -p data && cp stage01_umap_seed.emitted.json data/stage01_umap_seed.json

echo "[4/5] Gate: the staged overlay must match the committed reference ..."
python3 verify_reproduce.py

echo "[5/5] Re-render the provenance notebook (auto from stage1_pipeline.py) ..."
python3 render_notebook.py stage1_pipeline.py 01_notebook.html

echo "OK - full chain regenerated (labels from label_clusters.py) and matches the reference."
