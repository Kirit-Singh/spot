#!/usr/bin/env bash
#
# Mutation test for the fixture-leak guard (deploy/scan_dist_no_fixtures.mjs). Proves the scanner:
#   (1) PASSES the real built dist (no false positives),
#   (2) REFUSES a token mutation (a served file carrying a fixture identifier),
#   (3) REFUSES an import-graph leak — a bundle that reaches repository.ts (which imports the
#       stage2/3/4 fixtures); esbuild --bundle follows the real import graph, so the fixtures' values
#       land in the output exactly as they would in a served entry that imported repository.ts.
# No production results are written.  Run: bash _frontend/deploy/test_fixture_leak_scan.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FE="$(cd "$HERE/.." && pwd)"
SCANNER="$HERE/scan_dist_no_fixtures.mjs"
FIX="$FE/src/fixtures"
pass=0; fail=0
ok()  { printf 'ok   %s\n' "$1"; pass=$((pass+1)); }
bad() { printf 'FAIL %s\n' "$1"; fail=$((fail+1)); }

# 1. the real built dist must be fixture-free
[ -d "$FE/dist/assets" ] || ( cd "$FE" && npx vite build >/dev/null 2>&1 )
if node "$SCANNER" "$FE/dist" "$FIX" >/dev/null 2>&1; then ok "real dist is fixture-free"; else bad "real dist flagged (unexpected)"; fi

# 2. token mutation → refused
TMP="$(mktemp -d)"; mkdir -p "$TMP/assets"; printf 'const s="GENE_A",t="stage2FixtureRaw";' > "$TMP/assets/leak.js"
if node "$SCANNER" "$TMP" "$FIX" >/dev/null 2>&1; then bad "token mutation NOT caught"; else ok "token mutation caught"; fi
rm -rf "$TMP"

# 3. import-graph mutation (repository.ts → fixtures) → refused
TMP2="$(mktemp -d)"
if ( cd "$FE" && npx -y esbuild src/repository/repository.ts --bundle --format=esm --outfile="$TMP2/entry.js" --log-level=error ) >/dev/null 2>&1; then
  if node "$SCANNER" "$TMP2" "$FIX" >/dev/null 2>&1; then bad "import-graph leak (repository.ts → fixtures) NOT caught"; else ok "import-graph leak caught (repository.ts → fixtures)"; fi
else
  printf 'warn %s\n' "esbuild unavailable — skipped the import-graph bundle case (dist + token cases still ran)"
fi
rm -rf "$TMP2"

printf -- '── %d passed, %d failed ──\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
