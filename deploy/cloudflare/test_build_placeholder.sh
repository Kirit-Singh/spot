#!/usr/bin/env bash
# Contract for the placeholder-only Pages distribution. It proves the exact
# publish inventory, deterministic manifest, landing/placeholder parity, and
# that no Stage-1..4 data, results, scientific pages, or reviewer secret can
# reach the served output. It never deploys.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
A="$(mktemp -d -t spot-placeholder-a.XXXXXX)"
B="$(mktemp -d -t spot-placeholder-b.XXXXXX)"
trap 'rm -rf "$A" "$B"' EXIT

SPOT_SKIP_FRONTEND_GATES=1 bash "$HERE/build_placeholder.sh" "$A"
SPOT_SKIP_FRONTEND_GATES=1 bash "$HERE/build_placeholder.sh" "$B"

# Deterministic: identical inputs at the same commit produce byte-identical manifests.
cmp "$A/site_release_manifest.json" "$B/site_release_manifest.json"

# Exact publish inventory — nothing more, nothing less.
expected="$(printf '%s\n' \
  01_page.html \
  404.html \
  _headers \
  _routes.json \
  index.html \
  site_release_manifest.json | sort)"
actual="$(cd "$A" && find . -type f | sed 's|^\./||' | sort)"
if [ "$expected" != "$actual" ]; then
  echo 'placeholder inventory drifted from the approved set' >&2
  diff <(printf '%s\n' "$expected") <(printf '%s\n' "$actual") >&2 || true
  exit 1
fi

# The landing and the placeholder page are copied byte-for-byte from their sources.
cmp "$REPO/01_programs/app/index.html" "$A/index.html"
cmp "$REPO/deploy/cloudflare/static/placeholder.html" "$A/01_page.html"

# The post-auth page is deliberately labelled and claims nothing scientific.
grep -q 'being assembled' "$A/01_page.html"
grep -qi 'placeholder' "$A/01_page.html"

# No Stage-1..4 data, results, hashed assets, or scientific pages are ever present.
for forbidden in data results assets targets.html pathways.html drugs.html \
    pksafety.html 01_notebook.html 01_trace.html functions; do
  if [ -e "$A/$forbidden" ]; then
    echo "forbidden scientific artifact present in placeholder output: $forbidden" >&2
    exit 1
  fi
done

# Reviewer secret binding names never appear in served bytes.
if rg -n 'ACCESS_CODE|SESSION_SIGNING_KEY' "$A" >/dev/null; then
  echo 'secret binding names leaked into placeholder output' >&2
  exit 1
fi

# No scientific vocabulary reaches the served bytes.
if rg -in 'treg|glioblastoma|glioma|umap|ensg|lincs|chembl|depmap|foxp3|tbx21|p-value|q-value|\bfdr\b|enrichment|penetrance|biomarker|clinical|\bgene\b|\bdrug\b|pathway|perturbation|transcript|dependency|log_fc|stage0[1-4]' "$A" >/dev/null; then
  echo 'scientific vocabulary leaked into placeholder output' >&2
  rg -in 'treg|glioblastoma|glioma|umap|ensg|lincs|chembl|depmap|foxp3|tbx21|p-value|q-value|\bfdr\b|enrichment|penetrance|biomarker|clinical|\bgene\b|\bdrug\b|pathway|perturbation|transcript|dependency|log_fc|stage0[1-4]' "$A" >&2 || true
  exit 1
fi

# Every asset routes through the fail-closed Function; no exclusions.
python3 - "$A/_routes.json" <<'PY'
import json, sys
routes = json.load(open(sys.argv[1]))
assert routes == {"version": 1, "include": ["/*"], "exclude": []}, routes
PY

echo 'Cloudflare Pages placeholder build contract passed'
