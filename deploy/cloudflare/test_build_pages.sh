#!/usr/bin/env bash
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
A="$(mktemp -d -t spot-pages-a.XXXXXX)"
B="$(mktemp -d -t spot-pages-b.XXXXXX)"
trap 'rm -rf "$A" "$B"' EXIT

SPOT_SKIP_NPM_CI=1 SPOT_SKIP_FRONTEND_GATES=1 bash "$HERE/build_pages.sh" "$A"
SPOT_SKIP_NPM_CI=1 SPOT_SKIP_FRONTEND_GATES=1 bash "$HERE/build_pages.sh" "$B"

cmp "$A/site_release_manifest.json" "$B/site_release_manifest.json"
cmp "$REPO/01_programs/app/index.html" "$A/index.html"
[ "$(find "$A/data" -type f | wc -l | tr -d ' ')" = "22" ]
[ ! -e "$A/data/.gitkeep" ]
[ -f "$A/01_page.html" ]
[ -f "$A/targets.html" ]
[ -f "$A/pathways.html" ]
[ -f "$A/drugs.html" ]
[ -f "$A/pksafety.html" ]
[ -f "$A/_routes.json" ]
[ -f "$A/_headers" ]
[ -f "$A/404.html" ]
[ ! -e "$A/functions" ]

python3 - "$A/_routes.json" <<'PY'
import json, sys
routes = json.load(open(sys.argv[1]))
assert routes == {"version": 1, "include": ["/*"], "exclude": []}
PY

if rg -n 'ACCESS_CODE|SESSION_SIGNING_KEY' "$A" >/dev/null; then
  echo 'secret binding names leaked into static output' >&2
  exit 1
fi

echo 'Cloudflare Pages build contract passed'
