#!/usr/bin/env bash
# Reproduce the Stage-1 v3.0.1 T8 production layer from pinned inputs, WITHOUT overwriting historical v2.
#
# Local, deterministic, no heavy compute (runs anywhere with python3):
#   1. gen_stage1_t8.py                 -> selectability, semantics, current(candidate), release manifest
#   2. verify_stage1_t8.py              -> INDEPENDENT verifier (re-derives from raw validation; fail-closed)
#   3. pytest test_stage1_t8.py         -> mutation / forgery suite (naive + fully-resealed attacks)
#   4. gen_full_release_verification.py -> outer full-release attestation binding code/env/inputs/outputs
#
# Heavy step (configured compute host + solver-locked environment; needs the pinned 396k parquet + frozen coordinates) —
# run once to (re)generate the recovered/built v3 artifacts + receipt into _t8_staging/:
#   scp _t8_staging/dcompute_tcefold.py + registry_v3 + coords + controls/bins + summary_candidate  "${SPOT_COMPUTE_HOST}:${SPOT_RUN_ROOT}/spot_t8_dcompute/"
#   ssh "${SPOT_COMPUTE_HOST}" '"${SPOT_PYTHON}" "${SPOT_RUN_ROOT}/spot_t8_dcompute/dcompute_tcefold.py"'
#   -> reproduces scores_canonical_content_sha256 43c4296d, builds the v3 overlay (proves overlay==full),
#      regenerates the by_program_condition summary, verifies controls+coefficients; emit receipt.json.
#   Then capture the solver lock from the configured environment (+ in-environment pip freeze).
#
# This never writes the v2 registry / v2 overlay and never deploys the v3 overlay (overlay_release_ok=false).
set -euo pipefail
cd "$(dirname "$0")"
echo "[1/8] integrate primary-source provenance"; python3 gen_stage1_provenance.py
echo "[2/8] independent provenance verifier";     python3 verify_stage1_provenance.py
echo "[3/8] generate T8 layer";                   python3 gen_stage1_t8.py
echo "[4/8] independent T8 verifier";             python3 verify_stage1_t8.py
echo "[5/8] regenerate v3 selection bundle (browser v3-contract constants)"; python3 stage2_bridge/gen_selection_bundle.py
echo "[6/8] protected-baseline gate (Stage-2 view + scorer-projection + no Tier-2 leak)"; python3 stage2_bridge/protected_hashes.py
echo "[7/8] mutation / forgery suites";           python3 -m pytest test_stage1_t8.py test_stage1_provenance.py stage2_bridge/tests -q
echo "[8/8] full-release attestation";            python3 gen_full_release_verification.py
echo "OK: Stage-1 v3 T8 layer reproduced (historical v2 untouched; v3 overlay not deployed; provenance bounded)."
