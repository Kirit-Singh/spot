#!/usr/bin/env bash
# Deployment smoke test for the spot static server.
# Forbidden paths (source/scripts/logs/mutation) MUST 404/405/410.
# Application pages + verified artifacts MUST 200.
# Usage: deploy/smoke_test.sh [base_url]   (default http://localhost:8347)
set -uo pipefail
BASE="${1:-http://localhost:8347}"
fail=0

check() {  # method path want-csv
  local code
  code=$(curl -s -o /dev/null -w "%{http_code}" -X "$1" --max-time 10 "$BASE$2")
  if [[ ",$3," == *",$code,"* ]]; then printf '  ok   %-5s %-32s -> %s\n' "$1" "$2" "$code"
  else printf '  FAIL %-5s %-32s -> %s (want %s)\n' "$1" "$2" "$code" "$3"; fail=1; fi
}

echo "== forbidden paths (source / scripts / logs / mutation) =="
for p in /serve.py /serve_static.py /stage1_pipeline.py /verify_reproduce.py \
         /render_notebook.py /reproduce.sh /cluster_scores.py /label_clusters.py \
         /scan.py /serve.log /start_server.sh /STAGE2_PLAN.md /REVIEW_MEMO.md \
         /rerun/log /../serve.py /.claude/config; do
  check GET "$p" 404,410
done
check POST /rerun 404,405,410
check PUT  /programs.html 404,405,410

echo "== application pages + verified artifacts (must 200) =="
for p in / /programs.html /01_notebook.html /01_trace.html \
         /data/stage01_umap_seed.json /data/stage01_cell_records.json; do
  check GET "$p" 200
done

[[ $fail -eq 0 ]] && echo "SMOKE TEST PASSED" || echo "SMOKE TEST FAILED"
exit $fail
