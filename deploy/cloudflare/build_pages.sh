#!/usr/bin/env bash
# Deterministic Cloudflare Pages assembler. It never deploys and never mutates
# 01_programs/app. The Pages project publishes only dist/cloudflare-pages.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"
APP="$REPO/01_programs/app"
FRONTEND="$REPO/_frontend"
UI_DIST="$FRONTEND/dist"
OUT="${1:-$REPO/dist/cloudflare-pages}"
ALLOWLIST="$HERE/stage1_data.allowlist"
STATIC="$HERE/static"
RESULTS_SRC="${SPOT_RESULTS_SRC:-$REPO/public_release/results}"

die() { printf 'Pages build refused: %s\n' "$*" >&2; exit 1; }

case "$OUT" in "$REPO"|"$APP"|"$FRONTEND") die "unsafe output directory: $OUT";; esac
[ -f "$APP/index.html" ] || die "reviewer landing is missing"
[ -f "$ALLOWLIST" ] || die "Stage-1 data allowlist is missing"

if [ "${CF_PAGES:-0}" = "1" ] && [ -n "$(git -C "$REPO" status --porcelain)" ]; then
  die "Cloudflare build checkout is dirty"
fi

if [ "${SPOT_SKIP_FRONTEND_GATES:-0}" != "1" ]; then
  if [ "${SPOT_SKIP_NPM_CI:-0}" != "1" ]; then
    npm ci --prefix "$FRONTEND"
  fi
  npm run typecheck --prefix "$FRONTEND"
  npm run lint --prefix "$FRONTEND"
  npm test --prefix "$FRONTEND"
fi
npm run build --prefix "$FRONTEND"

for file in targets.html pathways.html drugs.html pksafety.html favicon.svg icons.svg; do
  [ -f "$UI_DIST/$file" ] || die "Vite output missing $file"
done
[ -d "$UI_DIST/assets" ] || die "Vite output missing assets/"

# Programs is canonical at /programs.html. Prefer the renamed UI entry when the
# UI-route change is integrated; until then, adapt the admitted legacy Vite entry
# at the packaging boundary. The historical URL is handled by authenticated
# middleware and is deliberately not emitted as a second static page.
if [ -f "$UI_DIST/programs.html" ]; then
  PROGRAMS_SOURCE="$UI_DIST/programs.html"
elif [ -f "$UI_DIST/01_page.html" ]; then
  PROGRAMS_SOURCE="$UI_DIST/01_page.html"
else
  die "Vite output missing programs.html"
fi

rm -rf "$OUT"
mkdir -p "$OUT/data" "$OUT/assets"

# Public landing + admitted pages. The Vite index is intentionally never copied.
cp -p "$APP/index.html" "$OUT/index.html"
cp -p "$PROGRAMS_SOURCE" "$OUT/programs.html"
cp -p "$APP/01_notebook.html" "$OUT/01_notebook.html"
cp -p "$APP/01_trace.html" "$OUT/01_trace.html"
for file in targets.html pathways.html drugs.html pksafety.html favicon.svg icons.svg; do
  cp -p "$UI_DIST/$file" "$OUT/$file"
done
while IFS= read -r -d '' asset; do
  rel="${asset#"$UI_DIST/assets/"}"
  mkdir -p "$OUT/assets/$(dirname "$rel")"
  cp -p "$asset" "$OUT/assets/$rel"
done < <(find "$UI_DIST/assets" -type f -print0)

# Stage-1 data is copied from a reviewable exact allowlist, never from Vite's
# ignored public/data directory and never by recursively publishing the repo.
while IFS= read -r file || [ -n "$file" ]; do
  [ -n "$file" ] || continue
  case "$file" in */*|.*) die "illegal Stage-1 allowlist entry: $file";; esac
  [ -f "$APP/data/$file" ] || die "allowlisted Stage-1 artifact missing: $file"
  cp -p "$APP/data/$file" "$OUT/data/$file"
done < "$ALLOWLIST"

# Downstream results are optional on previews but mandatory on the production
# branch. They must already be compact, admitted, and content-addressed.
require_results="${SPOT_REQUIRE_RESULTS:-0}"
if [ "${CF_PAGES_BRANCH:-}" = "main" ]; then require_results=1; fi
if [ -d "$RESULTS_SRC" ]; then
  report="$(python3 "$FRONTEND/deploy/validate_results_tree.py" "$RESULTS_SRC")"
  case "$report" in OK*) :;; *) die "downstream results validation failed: $report";; esac
  mkdir -p "$OUT/results"
  while IFS= read -r line; do
    case "$line" in
      'FILE '*) rel="${line#FILE }"; mkdir -p "$OUT/results/$(dirname "$rel")"; cp -p "$RESULTS_SRC/$rel" "$OUT/results/$rel";;
    esac
  done <<< "$report"
  cp -p "$RESULTS_SRC/current.json" "$OUT/results/current.json"
elif [ "$require_results" = "1" ]; then
  die "production requires an admitted public_release/results tree"
fi

cp -p "$STATIC/_routes.json" "$OUT/_routes.json"
cp -p "$STATIC/_headers" "$OUT/_headers"
cp -p "$STATIC/404.html" "$OUT/404.html"
cmp -s "$APP/index.html" "$OUT/index.html" || die "landing changed during assembly"

commit="${CF_PAGES_COMMIT_SHA:-$(git -C "$REPO" rev-parse HEAD)}"
node "$HERE/finalize_pages_dist.mjs" "$OUT" "$commit"
