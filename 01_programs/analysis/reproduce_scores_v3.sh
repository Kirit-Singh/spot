#!/usr/bin/env bash
# reproduce_scores_v3.sh — scoring-tier reproduction for a clean checkout.
# Fetches the pinned public h5ad (verifies its sha256), recomputes the full 396k v3 score
# table from .X, and asserts the frozen canonical hash
#   scores_canonical_content_sha256 = 43c4296d5166740c334441a69df23bb440a073382bbe79628a3bb89e43d51316
# Exit status is 0 iff the hash matches.
#
# Usage:
#   ./reproduce_scores_v3.sh                 # --fetch the pinned h5ad from Hugging Face
#   SPOT_H5AD=/path/ntc_clustered.h5ad ./reproduce_scores_v3.sh   # use a local h5ad
# On the configured compute host: activate the solver-locked environment, then run this script.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA="${HERE}/../app/data"

if [[ -n "${SPOT_H5AD:-}" ]]; then
  H5AD_ARGS=(--h5ad "${SPOT_H5AD}")
else
  H5AD_ARGS=(--h5ad "${HERE}/ntc_clustered.h5ad" --fetch)   # download pinned revision if absent
fi

exec python3 "${HERE}/gen_stage1_scores_v3.py" \
  "${H5AD_ARGS[@]}" \
  --registry "${DATA}/stage01_program_registry_v3.json" \
  --controls "${DATA}/stage01_controls_v3.csv" \
  "$@"
