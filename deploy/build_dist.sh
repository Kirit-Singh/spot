#!/usr/bin/env bash
# Build the spot public distribution from an EXPLICIT allowlist.
# Serves rendered application HTML + verified derived display artifacts only —
# never source, scripts, logs, manifests-with-local-paths, or the repo root.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DIST="${1:-$REPO/dist}"
APP="$REPO/01_programs/app"

rm -rf "$DIST"
mkdir -p "$DIST/data"

# Allowlisted rendered pages
cp "$APP/index.html"       "$DIST/index.html"
cp "$APP/01_page.html"     "$DIST/01_page.html"
cp "$APP/01_notebook.html" "$DIST/01_notebook.html"
cp "$APP/01_trace.html"    "$DIST/01_trace.html"

# Verified derived display artifacts (must pass the Stage-1 verifier before deploy)
cp "$APP/data/stage01_umap_seed.json"    "$DIST/data/stage01_umap_seed.json"
cp "$APP/data/stage01_cell_records.json" "$DIST/data/stage01_cell_records.json"

echo "built dist at $DIST:"
find "$DIST" -type f | sort | sed "s#^$DIST/#  #"
