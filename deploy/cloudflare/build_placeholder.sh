#!/usr/bin/env bash
# Deterministic Cloudflare Pages PLACEHOLDER assembler. It never deploys, never
# runs the Vite scientific build, and structurally cannot include Stage-1..4
# data, downstream results, or the reviewer secret: it copies only the frozen
# landing, the deliberately-labelled placeholder page, and the static control
# files, then reuses the hardened finalize_pages_dist.mjs. The full-site
# assembler in build_pages.sh remains a separate build lane.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
APP="$REPO/01_programs/app"
FRONTEND="$REPO/_frontend"
STATIC="$HERE/static"
OUT="${1:-$REPO/dist/cloudflare-placeholder}"

die() { printf 'Placeholder build refused: %s\n' "$*" >&2; exit 1; }

case "$OUT" in "$REPO"|"$APP"|"$FRONTEND") die "unsafe output directory: $OUT";; esac
[ -f "$APP/index.html" ] || die "reviewer landing is missing"
[ -f "$STATIC/placeholder.html" ] || die "placeholder page is missing"

if [ "${CF_PAGES:-0}" = "1" ] && [ -n "$(git -C "$REPO" status --porcelain)" ]; then
  die "Cloudflare build checkout is dirty"
fi

# The functions gate that protects this output is validated here. The Vite
# scientific build is deliberately never run and no app bundle is produced.
if [ "${SPOT_SKIP_FRONTEND_GATES:-0}" != "1" ]; then
  if [ "${SPOT_SKIP_NPM_CI:-0}" != "1" ]; then
    npm ci --prefix "$FRONTEND"
  fi
  npm run typecheck --prefix "$FRONTEND"
  npm run lint --prefix "$FRONTEND"
  npm test --prefix "$FRONTEND"
fi

rm -rf "$OUT"
mkdir -p "$OUT"

# The reviewer landing ships as landing.html — its own control surface, served at "/" by the
# root Function. It is deliberately NOT index.html: in the full release index.html is an
# admitted, hash-bound app artifact, and the placeholder uses the same serving model so the
# two builds never diverge. No app bundle, no Stage-1 data, no downstream results are copied.
cp -p "$APP/index.html" "$OUT/landing.html"
cp -p "$STATIC/placeholder.html" "$OUT/programs.html"
cp -p "$STATIC/_routes.json" "$OUT/_routes.json"
cp -p "$STATIC/_headers" "$OUT/_headers"
cp -p "$STATIC/404.html" "$OUT/404.html"
cmp -s "$APP/index.html" "$OUT/landing.html" || die "landing changed during assembly"

commit="${CF_PAGES_COMMIT_SHA:-$(git -C "$REPO" rev-parse HEAD)}"
node "$HERE/finalize_pages_dist.mjs" "$OUT" "$commit"

# Fail closed: the served tree must be exactly the approved placeholder set.
expected="$(printf '%s\n' \
  404.html _headers _routes.json landing.html programs.html site_release_manifest.json | sort)"
actual="$(cd "$OUT" && find . -type f | sed 's|^\./||' | sort)"
[ "$expected" = "$actual" ] || die "unexpected files in placeholder output: $actual"
