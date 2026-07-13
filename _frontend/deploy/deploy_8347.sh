#!/usr/bin/env bash
#
# deploy_8347.sh — deterministic, same-origin Stage-1..4 distribution deploy for :8347.
#
# Builds the four downstream React entries + hashed assets, lays them into the AUTHORITATIVE
# Stage-1 app root (spot 01_programs/app) ALONGSIDE the nav-retargeted 01_page.html and the
# git-clean, commit-pinned data/, then mirrors the whole tree to the tcedirector :8347 served
# dir and proves the remote matches the pinned baseline byte-for-byte.
#
# This script NEVER prints GO. A successful run prints "DEPLOYED — ACCEPTANCE PENDING"; only the
# live browser U01–U18 harness may return GO. Every gate below must be green (any failure => NO-GO,
# exit nonzero, nothing further deployed):
#   * UI worktree CLEAN — no modified AND no untracked paths — so the release identity is a real
#     ui_commit; there is NO dirty/untracked override (a stash/tree digest would omit untracked files);
#   * Stage-1 DATA baseline pinned: spot HEAD==9a2f6cf9 (stage1_commit), data git-clean, 22-file
#     digest==edbc8da3, invariant file hashes match, 01_page.html differs from the pin only by
#     CLASSIFIED lines (nav retarget + citation-year fix + 0/33-retirement comments), byte-pinned;
#   * typecheck + lint + full test suite green BEFORE build;
#   * PROVENANCE-HYGIENE: no machine-local/private strings in any served text artifact;
#   * LOCAL data/ preserved byte-for-byte; no dist/data duplicate; public/data not git-tracked;
#   * REMOTE served tree == LOCAL served tree byte-for-byte — EVERY served file (built pages, assets,
#     preserved stage-1 root files AND the 22 data files) is remote-hashed and compared, not just data;
#   * an UNREACHABLE or SKIPPED remote is NEVER a successful deploy.
# Idempotent. Touches ONLY :8347. Never references or mutates :8348.
#
set -euo pipefail

# ─────────────────────────────────────────────────────────────────────────────
# Config + pinned baseline
# ─────────────────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_DIR="$(cd "$FRONTEND_DIR/.." && pwd)"          # UI worktree (branch agent/ui-stage234)
DIST_DIR="$FRONTEND_DIR/dist"
PUBLIC_DIR="$FRONTEND_DIR/public"
# Deployment RECEIPT lives OUTSIDE any git worktree (never dirties the just-deployed commit).
DEPLOY_MANIFEST="${SPOT_DEPLOY_RECEIPT:-$HOME/.spot-runs/spot-8347-deployed_manifest.txt}"
mkdir -p "$(dirname "$DEPLOY_MANIFEST")"

SPOT_REPO="/Users/kiritsingh/spot"                  # authoritative Stage-1 checkout
TARGET_ROOT="$SPOT_REPO/01_programs/app"            # the dir :8347 serves (local)
TARGET_DATA="$TARGET_ROOT/data"
REL_MANIFEST="$TARGET_ROOT/release_manifest.json"   # served; U01 verifies it

# Pinned Stage-1 data baseline (verified reproducible; see coordinator handoff).
# Baseline pinned to the GO Stage-1 contract 539431d (off 184211a): adds the re-synced temporal estimator
# identity (343f20db) + the required biology-only question_id emission + the v3 selection schema update.
# The canonical base (01_programs/app/01_page.html @ 539431d) still carries the five-route nav + sole
# Methods & provenance drawer + hash fallback and is BYTE-IDENTICAL to the served import (both 9fb4f282),
# so the classified 01_page diff below is EMPTY. Only stage01_selection_bundle.json changed under data/, so
# the 22-file digest moves to 9c7b9ec0; the four scorer invariants stay byte-identical (verified).
STAGE1_DATA_COMMIT="539431dd8d87a3d763fb69ab44ed44bc98631d5a"
STAGE1_DATA_DIGEST="9c7b9ec0d623275c9ee8096db8dca63d8e3149ccebf1fa61eb0b4326ca3cfd15"
STAGE1_PAGE_BASE_SHA="9fb4f282b289db9a0642916a139b15a6eac5afb9761e3b5c1ad3a57d1fc57ed1"   # pin:01_page.html base @ 539431d (== import; question_id-emitting page keeps the classified UI + hash fallback)
STAGE1_PAGE_IMPORT_SHA="${STAGE1_PAGE_IMPORT_SHA:-9fb4f282b289db9a0642916a139b15a6eac5afb9761e3b5c1ad3a57d1fc57ed1}"  # nav-retargeted import — byte-identical to the 539431d canonical base
INVARIANTS=(
  "data/stage01_selectability_v3.json:7c326a86"
  "data/stage01_validation.json:1c14cd28"
  "data/stage01_stage2_registry_view.json:d37c1927"   # scorer-view raw
  "data/stage01_release_manifest.json:ad0baf75"        # release-manifest raw
)

# tcedirector :8347 served dir. CONFIRMED SPOT_DIST of the pid listening on :8347.
# TODO(confirm) before each release:  lsof -nP -iTCP:8347 -sTCP:LISTEN -t → /proc/$pid env SPOT_DIST
TCE_HOST="${TCE_HOST:-tcedirector}"
TCE_8347_DIR="${TCE_8347_DIR:-/home/tcelab/spot-dist}"

SKIP_REMOTE="${SKIP_REMOTE:-0}"   # local-only run; explicitly NOT a successful deploy (exits nonzero)
# NO dirty/untracked override exists: the release identity is a clean commit or it is refused ([1/10]).

PAGES=(targets.html pathways.html drugs.html pksafety.html)
STATIC_SVG=(favicon.svg icons.svg)

# Optional admitted downstream results/ staging tree — W1 publishes it AFTER a real, verified run. It
# lives OUTSIDE the git worktree AND OUTSIDE data/, so binding downstream results NEVER perturbs the
# pinned Stage-1 digest. ABSENT (pre-run) → a clean UNBOUND deploy (0 downstream-data files). PRESENT →
# it must be content-addressed by results/current.json (schema spot.ui_results_current.v1) carrying a
# full inventory[] (path + sha256) of EVERY file under it; the deploy re-hashes each file, refuses any
# unlisted file / hash mismatch / missing route manifest / malformed current.json, hygiene-scans every
# result JSON, classifies them `downstream-data`, and remote-byte-verifies them like all served bytes.
RESULTS_SRC="${SPOT_RESULTS_SRC:-}"

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────
say() { printf '%s\n' "$*"; }
hr()  { printf -- '─%.0s' {1..72}; printf '\n'; }
die() { printf 'NO-GO: %s\n' "$*" >&2; exit 1; }

if command -v sha256sum >/dev/null 2>&1; then sha256_of() { sha256sum "$1" | awk '{print $1}'; }
elif command -v shasum >/dev/null 2>&1;  then sha256_of() { shasum -a 256 "$1" | awk '{print $1}'; }
else die "no sha256sum / shasum available"; fi

manifest_of_dir() {  # sorted "<sha256>  <relpath>" for every file under $1
  ( cd "$1" && find . -type f -print0 | LC_ALL=C sort -z | \
      while IFS= read -r -d '' f; do printf '%s  %s\n' "$(sha256_of "$f")" "${f#./}"; done )
}
data_digest_local() {  # the authoritative 22-file digest (coordinator's exact method)
  ( cd "$TARGET_ROOT" && find data -type f | sort | xargs shasum -a 256 | shasum -a 256 ) | awk '{print $1}'
}

# provenance-hygiene: machine-local / private strings that must never reach served bytes.
# ALLOWLIST (disjoint from FORBIDDEN, so never flagged): repo-relative module paths
# (python -m …, analysis.direct.…), env placeholders ($VAR / ${…}), public source URLs
# (reactome.org / geneontology.org / doi.org / biorxiv.org / huggingface.co / fonts.*),
# and 64-hex content hashes.
# NOTE: /home/ is anchored to a non-alphanumeric boundary so a MACHINE path ("/home/tcelab", quoted
# or after =/space) is caught, while a legitimate public URL path (e.g. ncbi.nlm.nih.gov/home/about/
# policies — the char before /home/ is a domain letter) is NOT a false positive. Same for /Users/.
FORBIDDEN='((^|[^A-Za-z0-9])/Users/|(^|[^A-Za-z0-9])/home/|/mnt/tcenas|/mnt/tcefold|/private/tmp/|\.spot-runs|scratchpad/|/worktrees/|\btcedirector\b|\btcefold\b|sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{16,}|xoxb-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{12,}|-----BEGIN |Authorization:[[:space:]]|[Bb]earer [A-Za-z0-9._-]{20,}|fixture://|file://|cs-session[:/]|cs-frame[:/])'
# Regression self-test (runs every deploy): a legit public URL path must NOT match; a machine path
# (quoted, after =/space, OR at the very start of a line) MUST. Guards against re-broadening.
printf '%s\n' 'ncbi.nlm.nih.gov/home/about/policies/' | grep -qE "$FORBIDDEN" && die "hygiene regex FALSE-POSITIVE on the legit NCBI /home/ URL — narrow it"
printf '%s\n' 'open.fda.gov/terms/' | grep -qE "$FORBIDDEN" && die "hygiene regex false-positive on a public URL"
printf '%s\n' 'x="/home/tcelab/spot-dist"' | grep -qE "$FORBIDDEN" || die "hygiene regex MISSES a quoted machine /home path"
printf '%s\n' '/home/tcelab/spot-dist/x' | grep -qE "$FORBIDDEN" || die "hygiene regex MISSES a machine /home path at line start"
printf '%s\n' 'cp /Users/me/secret .' | grep -qE "$FORBIDDEN" || die "hygiene regex MISSES a machine /Users path"
printf '%s\n' '/Users/me/secret' | grep -qE "$FORBIDDEN" || die "hygiene regex MISSES a /Users path at line start"
hygiene_scan() {  # args: files… — token-level (safe for one-line minified bundles), NO-GO on hit
  local hits
  hits="$(grep -RInoE "$FORBIDDEN" "$@" 2>/dev/null | sort -u || true)"
  if [ -n "$hits" ]; then
    say "── provenance-hygiene FAIL: machine-local/private strings in served artifacts ──"
    printf '%s\n' "$hits" | sed 's/^/  /' | head -60
    die "provenance-hygiene: forbidden strings in served bytes (see above)"
  fi
}

# Resolve + content-address-validate the OPTIONAL downstream results/ tree. Populates RESULTS_RELS with
# every result relpath to serve (empty when no tree). FAIL-CLOSED: a present-but-malformed / unmanifested
# / hash-mismatched / partial tree hard-refuses. Absence is the clean pre-run UNBOUND state (no-op).
RESULTS_RELS=()
resolve_results_tree() {
  RESULTS_RELS=()
  if [ -z "$RESULTS_SRC" ]; then
    say "       no downstream results/ tree (SPOT_RESULTS_SRC unset) — clean UNBOUND deploy (0 downstream-data files)"
    return 0
  fi
  [ -d "$RESULTS_SRC" ] || die "SPOT_RESULTS_SRC set but not a directory: $RESULTS_SRC"
  [ -f "$RESULTS_SRC/current.json" ] || die "results tree present but missing results/current.json (content-address pointer)"
  command -v python3 >/dev/null 2>&1 || die "python3 required to validate the downstream results tree"
  # Content-address + inventory-completeness gate (deploy/validate_results_tree.py, unit-tested):
  # emits `OK` + sorted `FILE <rel>` lines, or a single `ERR <reason>`. It exits 0 either way so the
  # shell inspects the verdict — a malformed / unmanifested / mismatched / partial tree hard-refuses.
  local report
  report="$(python3 "$SCRIPT_DIR/validate_results_tree.py" "$RESULTS_SRC")" || die "downstream results validation could not run"
  case "$report" in
    'ERR '*) die "downstream results tree invalid: ${report#ERR }";;
    OK*)     : ;;
    *)       die "downstream results validation produced no verdict";;
  esac
  while IFS= read -r line; do
    case "$line" in 'FILE '*) RESULTS_RELS+=("${line#FILE }");; esac
  done <<< "$report"
  RESULTS_RELS+=("current.json")  # served first by the browser; classified downstream-data too
  say "       downstream results tree OK: ${#RESULTS_RELS[@]} content-addressed file(s), no unlisted files"
}

# ─────────────────────────────────────────────────────────────────────────────
# 0. Preconditions
# ─────────────────────────────────────────────────────────────────────────────
GEN_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
hr; say "spot :8347 deploy — deterministic same-origin distribution"; hr
say "UI worktree  : $REPO_DIR"
say "target root  : $TARGET_ROOT"
say "8347 (tce)   : $TCE_HOST:$TCE_8347_DIR   (SKIP_REMOTE=$SKIP_REMOTE)"
say ""
[ -d "$TARGET_ROOT" ] || die "target root does not exist: $TARGET_ROOT"
[ -d "$TARGET_DATA" ] || die "target data/ does not exist: $TARGET_DATA"
[ -f "$PUBLIC_DIR/01_page.html" ] || die "missing nav-retargeted import: $PUBLIC_DIR/01_page.html"
git -C "$REPO_DIR" ls-files --error-unmatch _frontend/public/data >/dev/null 2>&1 && die "_frontend/public/data is git-tracked — release must carry no bundled data" || true

# ─────────────────────────────────────────────────────────────────────────────
# 1. UI worktree identity — a CLEAN COMMIT is required; no dirty/untracked override
# ─────────────────────────────────────────────────────────────────────────────
# `git status --porcelain` reports BOTH modified and untracked ('??') paths. ANY entry hard-refuses:
# binding a stash/tree digest (the removed ALLOW_DIRTY path) would silently omit untracked candidate
# files from the release identity, so it is not offered. The release identity is the ui_commit.
say "[1/10] UI worktree identity (clean commit required — no dirty/untracked override)"
DIRTY="$(git -C "$REPO_DIR" status --porcelain)"
if [ -n "$DIRTY" ]; then
  printf '%s\n' "$DIRTY" | sed 's/^/         /' >&2
  die "UI worktree not clean (modified or untracked paths above); commit everything before deploy"
fi
UI_COMMIT="$(git -C "$REPO_DIR" rev-parse HEAD)"
SRC_REF="$UI_COMMIT"; SRC_KIND="commit"; SRC_DIRTY="false"
say "       clean; ui_commit = $UI_COMMIT"

# ─────────────────────────────────────────────────────────────────────────────
# 2. Stage-1 DATA baseline pin (commit + digest + invariants + 01_page nav-only diff)
# ─────────────────────────────────────────────────────────────────────────────
say "[2/10] Stage-1 data baseline pin"
HEAD_SPOT="$(git -C "$SPOT_REPO" rev-parse HEAD)"
[ "$HEAD_SPOT" = "$STAGE1_DATA_COMMIT" ] || die "spot HEAD $HEAD_SPOT != pinned data commit $STAGE1_DATA_COMMIT"
[ -z "$(git -C "$SPOT_REPO" status --porcelain 01_programs/app/data)" ] || die "spot 01_programs/app/data is dirty — commit-clean data required"
LOCAL_DIGEST="$(data_digest_local)"
[ "$LOCAL_DIGEST" = "$STAGE1_DATA_DIGEST" ] || die "local data digest $LOCAL_DIGEST != pinned $STAGE1_DATA_DIGEST"
for inv in "${INVARIANTS[@]}"; do
  f="${inv%%:*}"; pre="${inv##*:}"; got="$(sha256_of "$TARGET_ROOT/$f")"
  [ "${got:0:8}" = "$pre" ] || die "invariant $f sha256 ${got:0:8}… != pinned $pre…"
done
# 01_page.html: base pin + import pin (the exact-byte guard) + a CLASSIFIED diff vs the pinned commit.
# At 184211a the canonical base already IS the classified UI (== import, 570a6f07), so this diff is now
# EMPTY; the classification below is retained as a defense that hard-refuses any FUTURE re-divergence.
# The byte pin is authoritative; the diff classification proves the changes are ONLY the intended
# ones, each explicitly allow-listed (never a blanket "any line with href="). Allowed change classes:
#   1. nav retarget  : nstep / nsep / window.location.assign / the 5 page hrefs / old 02_page stage hrefs
#   2. citation fix  : the class="cite" header line (2026→2025 year correction; DOI already correct)
#   3. 0/33 retire   : the two selectability comment lines (retired production-gate number removed)
#   4. methods surface: remove the standalone "/01_notebook.html" drawer link — the header Methods &
#                       provenance slide-out is the ONLY primary methods/provenance UI surface (the
#                       01_notebook.html file remains as an archival/reproducibility artifact, just
#                       not a UI destination). Only the exact "/01_notebook.html" anchor line.
# Anything else is a NON-classified change and hard-refuses.
BASE01="$(mktemp -t spot_base01.XXXXXX)"
git -C "$SPOT_REPO" show "$STAGE1_DATA_COMMIT:01_programs/app/01_page.html" > "$BASE01" || die "cannot read pinned 01_page.html"
[ "$(sha256_of "$BASE01")" = "$STAGE1_PAGE_BASE_SHA" ] || die "pinned base 01_page.html sha != $STAGE1_PAGE_BASE_SHA"
[ "$(sha256_of "$PUBLIC_DIR/01_page.html")" = "$STAGE1_PAGE_IMPORT_SHA" ] || die "import 01_page.html sha != pinned $STAGE1_PAGE_IMPORT_SHA (re-review + update STAGE1_PAGE_IMPORT_SHA)"
NAV_ALLOW='(nstep|nsep|window\.location\.assign|href="(01_page|targets|pathways|drugs|pksafety)\.html"|/02_page\.html#/stage-)'
OFFENDING="$(diff -u "$BASE01" "$PUBLIC_DIR/01_page.html" | grep -E '^[+-]' | grep -vE '^(\+\+\+|---)' \
  | grep -vE "$NAV_ALLOW" \
  | grep -vE 'class="cite"' \
  | grep -vE 'No production/research split|PRODUCTION-selectability flag' \
  | grep -vE 'href="/01_notebook\.html"' || true)"
rm -f "$BASE01"
[ -z "$OFFENDING" ] || { printf '%s\n' "$OFFENDING" | sed 's/^/         /' >&2; die "01_page.html diff vs $STAGE1_DATA_COMMIT touches NON-classified lines (not nav/citation/0-33-retire)"; }
say "       spot@$STAGE1_DATA_COMMIT · data digest $STAGE1_DATA_DIGEST · 22 invariants + classified 01_page diff OK"

# ─────────────────────────────────────────────────────────────────────────────
# 3. Quality gates: typecheck + lint + full test suite
# ─────────────────────────────────────────────────────────────────────────────
say "[3/10] typecheck + lint + full test suite (all must be green)"
( cd "$FRONTEND_DIR" && npm run typecheck ) || die "typecheck failed"
( cd "$FRONTEND_DIR" && npm run lint )      || die "lint failed"
( cd "$FRONTEND_DIR" && npm test )          || die "test suite failed"

# ─────────────────────────────────────────────────────────────────────────────
# 4. Build → dist/
# ─────────────────────────────────────────────────────────────────────────────
say "[4/10] vite build → dist/"
( cd "$FRONTEND_DIR" && npx vite build ) || die "vite build failed"
[ -d "$DIST_DIR/assets" ] || die "build produced no dist/assets/"

# ─────────────────────────────────────────────────────────────────────────────
# 5. Provenance-hygiene scan over every served text artifact (before any copy)
# ─────────────────────────────────────────────────────────────────────────────
say "[5/10] provenance-hygiene scan"
SCAN=("$PUBLIC_DIR/01_page.html")
for f in "${PAGES[@]}" "${STATIC_SVG[@]}"; do [ -f "$DIST_DIR/$f" ] || die "expected built file missing: dist/$f"; SCAN+=("$DIST_DIR/$f"); done
while IFS= read -r -d '' a; do SCAN+=("$a"); done < <(find "$DIST_DIR/assets" -type f -print0)
while IFS= read -r -d '' f; do
  case "$(basename "$f")" in 01_page.html|targets.html|pathways.html|drugs.html|pksafety.html|favicon.svg|icons.svg|release_manifest.json) continue;; esac
  SCAN+=("$f")   # preserved Stage-1 root files: 01_notebook.html / 01_trace.html / index.html
done < <(find "$TARGET_ROOT" -maxdepth 1 -type f -print0)
# Optional downstream results/: validate content-addressing, then hygiene-scan every result JSON too.
resolve_results_tree
if [ "${#RESULTS_RELS[@]}" -gt 0 ]; then
  for rel in "${RESULTS_RELS[@]}"; do SCAN+=("$RESULTS_SRC/$rel"); done
fi
hygiene_scan "${SCAN[@]}"
say "       clean (${#SCAN[@]} served text artifacts scanned)"
# Fixture-leak guard: the BUILT served bundles must carry NO demo/fixture identifier or known fixture
# value. Fixtures are test-only; a served entry that pulls in repository.ts (which imports the
# stage2/3/4 fixtures) — or any fixture module — bundles their distinctive values, which this catches
# (import-graph aware by construction; token set is data-driven from src/fixtures).
command -v node >/dev/null 2>&1 || die "node required for the fixture-leak scan"
node "$SCRIPT_DIR/scan_dist_no_fixtures.mjs" "$DIST_DIR" "$FRONTEND_DIR/src/fixtures" \
  || die "fixture/demo identifiers reachable in a served bundle — fixtures must stay test-only (see above)"
say "       fixture-leak scan clean (served bundles are fixture-free)"

# ─────────────────────────────────────────────────────────────────────────────
# 6. Resolve + validate the EXACT copy set (no dist/data, ever)
# ─────────────────────────────────────────────────────────────────────────────
say "[6/10] resolving copy set"
SRC_FILES=(); DST_RELS=(); DST_CLASS=()
# add_pair SRC DST [CLASS] — CLASS defaults to `built`; downstream results are `downstream-data`.
add_pair() { SRC_FILES+=("$1"); DST_RELS+=("$2"); DST_CLASS+=("${3:-built}"); }
add_pair "$PUBLIC_DIR/01_page.html" "01_page.html"
for f in "${PAGES[@]}" "${STATIC_SVG[@]}"; do add_pair "$DIST_DIR/$f" "$f"; done
while IFS= read -r -d '' a; do add_pair "$a" "assets/${a#"$DIST_DIR/assets/"}"; done < <(find "$DIST_DIR/assets" -type f -print0)
# Optional downstream results/ (validated above) → served under results/, classified downstream-data.
if [ "${#RESULTS_RELS[@]}" -gt 0 ]; then
  for rel in "${RESULTS_RELS[@]}"; do add_pair "$RESULTS_SRC/$rel" "results/$rel" "downstream-data"; done
fi
for i in "${!SRC_FILES[@]}"; do
  case "${SRC_FILES[$i]}" in "$DIST_DIR/data/"*) die "copy set includes dist/data — refusing duplicate data";; esac
  case "${DST_RELS[$i]}"  in data/*|data)        die "copy set targets data/ — refusing to touch preserved data";; esac
done
say "       ${#SRC_FILES[@]} file(s) staged (0 under data/; $((${#RESULTS_RELS[@]})) downstream-data)"

# ─────────────────────────────────────────────────────────────────────────────
# 7. Snapshot LOCAL data/ BEFORE
# ─────────────────────────────────────────────────────────────────────────────
say "[7/10] snapshotting LOCAL data/"
DATA_BEFORE="$(mktemp -t spot_data_before.XXXXXX)"; DATA_AFTER="$(mktemp -t spot_data_after.XXXXXX)"
REL_ENTRIES="$(mktemp -t spot_rel_entries.XXXXXX)"; REMOTE_DATA=""
trap 'rm -f "$DATA_BEFORE" "$DATA_AFTER" "$REL_ENTRIES" ${REMOTE_DATA:+"$REMOTE_DATA"}' EXIT
manifest_of_dir "$TARGET_DATA" > "$DATA_BEFORE"

# ─────────────────────────────────────────────────────────────────────────────
# 8. Copy into TARGET_ROOT (assets/ rebuilt; data/ never written)
# ─────────────────────────────────────────────────────────────────────────────
say "[8/10] laying distribution into target root"
# assets/ and results/ are FULLY deploy-managed → removed then re-laid (atomic publish; never a stale
# bundle). data/ is NEVER touched. When no results tree is staged, results/ is simply absent (unbound).
rm -rf "$TARGET_ROOT/assets" "$TARGET_ROOT/results"
for i in "${!SRC_FILES[@]}"; do dst="$TARGET_ROOT/${DST_RELS[$i]}"; mkdir -p "$(dirname "$dst")"; cp -p "${SRC_FILES[$i]}" "$dst"; done

# ─────────────────────────────────────────────────────────────────────────────
# 9. Verify LOCAL data/ unchanged + digest; emit release manifest (classified) + record
# ─────────────────────────────────────────────────────────────────────────────
say "[9/10] verifying LOCAL data/ + emitting release manifest"
manifest_of_dir "$TARGET_DATA" > "$DATA_AFTER"
diff -q "$DATA_BEFORE" "$DATA_AFTER" >/dev/null || { diff "$DATA_BEFORE" "$DATA_AFTER" || true; die "LOCAL data/ changed during deploy"; }
[ "$(data_digest_local)" = "$STAGE1_DATA_DIGEST" ] || die "LOCAL data digest drifted from pinned $STAGE1_DATA_DIGEST"

# classified entries: path<TAB>sha256<TAB>class — per-file class (built | downstream-data), sorted by path.
: > "$REL_ENTRIES"
for i in "${!DST_RELS[@]}"; do
  printf '%s\t%s\t%s\n' "${DST_RELS[$i]}" "$(sha256_of "$TARGET_ROOT/${DST_RELS[$i]}")" "${DST_CLASS[$i]}"
done | LC_ALL=C sort >> "$REL_ENTRIES"
while IFS= read -r -d '' f; do
  b="$(basename "$f")"
  case "$b" in 01_page.html|targets.html|pathways.html|drugs.html|pksafety.html|favicon.svg|icons.svg|release_manifest.json) continue;; esac
  printf '%s\t%s\tpreserved-stage1\n' "$b" "$(sha256_of "$f")" >> "$REL_ENTRIES"
done < <(find "$TARGET_ROOT" -maxdepth 1 -type f -print0)
while IFS= read -r line; do printf 'data/%s\t%s\tstage1-data\n' "${line#*  }" "${line%%  *}" >> "$REL_ENTRIES"; done < "$DATA_AFTER"

{
  printf '{\n  "release": "spot-8347-same-origin",\n  "commit": "%s",\n  "source_kind": "%s",\n  "dirty": %s,\n' "$SRC_REF" "$SRC_KIND" "$SRC_DIRTY"
  printf '  "stage1_data_commit": "%s",\n  "stage1_data_digest": "%s",\n  "generated_utc": "%s",\n' "$STAGE1_DATA_COMMIT" "$STAGE1_DATA_DIGEST" "$GEN_UTC"
  # Account for the 39th served file (this manifest) NON-recursively: it is self-excluded from files[]
  # (a file cannot contain its own hash), its sha256 is recorded in the external deployed_manifest.txt
  # meta line, and step 10 remote-hashes EVERY served byte — including this manifest — against local.
  printf '  "manifest_self": {"path": "release_manifest.json", "class": "manifest", "accounting": "non-recursive self-exclude; sha256 in external deployed_manifest.txt; remote-verified byte-for-byte in step 10"},\n'
  printf '  "files": [\n'
  awk -F'\t' '{ printf "%s    {\"path\": \"%s\", \"sha256\": \"%s\", \"class\": \"%s\"}", (NR>1?",\n":""), $1, $2, $3 } END { printf "\n" }' "$REL_ENTRIES"
  printf '  ]\n}\n'
} > "$REL_MANIFEST"

{
  printf '# spot :8347 deployed distribution — %s\n# ui-source: %s (%s, dirty=%s)\n# stage1-data: %s digest %s\n' "$GEN_UTC" "$SRC_REF" "$SRC_KIND" "$SRC_DIRTY" "$STAGE1_DATA_COMMIT" "$STAGE1_DATA_DIGEST"
  printf '%s  release_manifest.json  meta\n' "$(sha256_of "$REL_MANIFEST")"
  awk -F'\t' '{ printf "%s  %s  %s\n", $2, $1, $3 }' "$REL_ENTRIES"
} | tee "$DEPLOY_MANIFEST" >/dev/null
hygiene_scan "$REL_MANIFEST" "$DEPLOY_MANIFEST"
say "       release manifest + record emitted ($(wc -l < "$REL_ENTRIES" | tr -d ' ') files: built+preserved-stage1+stage1-data)"

# ─────────────────────────────────────────────────────────────────────────────
# 9b. Served-manifest consistency — refuse to promote a served tree whose Stage-1 gate manifest and
#     deploy-emitted deployment manifest declare a contradictory deployment state (gate says
#     app_deployment_ready/overlay_release_ok=false while release_manifest.json declares the app
#     deployed). Uses the CANONICAL Stage-1 verifier (01_programs/analysis/verify_served_manifests.py,
#     from the reconcile lane) — one owner, one model; the 0/33 gate is decoupled (frozen historical).
#     It never regenerates/flips the attestation; it only FAILS CLOSED on a self-contradicting release.
# ─────────────────────────────────────────────────────────────────────────────
say "[9b/10] verifying served-manifest consistency (canonical verify_served_manifests.py)"
command -v python3 >/dev/null 2>&1 || die "python3 required for the served-manifest consistency check"
VSM="$SPOT_REPO/01_programs/analysis/verify_served_manifests.py"
[ -f "$VSM" ] || die "canonical served-manifest verifier missing at $VSM — the served checkout lacks the release-manifest reconciliation (merge stage1-release-manifest-reconcile) and is NOT promotable"
python3 "$VSM" "$TARGET_DATA/stage01_release_manifest.json" "$TARGET_DATA/stage01_current.json" "$REL_MANIFEST" \
  || die "served Stage-1 manifests declare a contradictory deployment state — reconcile the Stage-1 gate + deployment manifest before promotion (do NOT promote the contradiction)"
say "       served attestation consistent with the deployment manifest"

# ─────────────────────────────────────────────────────────────────────────────
# 10. Remote sync (authoritative data + pages) — prove remote == pinned baseline
# ─────────────────────────────────────────────────────────────────────────────
if [ "$SKIP_REMOTE" = "1" ]; then
  say "[10/10] remote sync SKIPPED (SKIP_REMOTE=1)"
  hr; say "NOT A GO — LOCAL-ONLY deploy; remote :8347 not updated or verified."; hr
  exit 2
fi
say "[10/10] rsync → $TCE_HOST:$TCE_8347_DIR (data synced+pinned, then pages/assets)"
ssh -o BatchMode=yes -o ConnectTimeout=10 "$TCE_HOST" true 2>/dev/null || die "$TCE_HOST unreachable — cannot update/verify :8347; NOT a GO"
rsync -az --delete "$TARGET_DATA/" "$TCE_HOST:$TCE_8347_DIR/data/"          || die "remote data rsync failed"
rsync -az --delete --exclude data "$TARGET_ROOT/" "$TCE_HOST:$TCE_8347_DIR/" || die "remote pages rsync failed"
REMOTE_DIGEST="$(ssh -o BatchMode=yes "$TCE_HOST" "cd '$TCE_8347_DIR' && find data -type f | sort | xargs shasum -a 256 | shasum -a 256" | awk '{print $1}')" || die "remote digest read failed"
if [ "$REMOTE_DIGEST" != "$STAGE1_DATA_DIGEST" ]; then
  REMOTE_DATA="$(mktemp -t spot_data_remote.XXXXXX)"
  ssh -o BatchMode=yes "$TCE_HOST" "cd '$TCE_8347_DIR/data' && find . -type f -print0 | LC_ALL=C sort -z | while IFS= read -r -d '' f; do printf '%s  %s\n' \"\$(sha256sum \"\$f\" | cut -d' ' -f1)\" \"\${f#./}\"; done" > "$REMOTE_DATA" 2>/dev/null || true
  diff "$DATA_AFTER" "$REMOTE_DATA" || true
  die "remote data digest $REMOTE_DIGEST != pinned $STAGE1_DATA_DIGEST"
fi
say "       remote data digest == pinned == $STAGE1_DATA_DIGEST"

# Remote-hash EVERY served file (built pages + assets + preserved stage-1 root + data), not just the
# data digest: the remote served tree must equal the LOCAL served tree byte-for-byte, file-for-file.
# This covers the whole release inventory emitted above, so no served byte goes unverified.
LOCAL_TREE="$(mktemp -t spot_tree_local.XXXXXX)"; REMOTE_TREE="$(mktemp -t spot_tree_remote.XXXXXX)"
manifest_of_dir "$TARGET_ROOT" > "$LOCAL_TREE"
ssh -o BatchMode=yes "$TCE_HOST" "cd '$TCE_8347_DIR' && find . -type f -print0 | LC_ALL=C sort -z | while IFS= read -r -d '' f; do printf '%s  %s\n' \"\$(sha256sum \"\$f\" | cut -d' ' -f1)\" \"\${f#./}\"; done" > "$REMOTE_TREE" || { rm -f "$LOCAL_TREE" "$REMOTE_TREE"; die "remote served-tree hash read failed"; }
if ! diff -q "$LOCAL_TREE" "$REMOTE_TREE" >/dev/null; then
  diff -u "$LOCAL_TREE" "$REMOTE_TREE" | sed 's/^/         /' | head -80 >&2
  rm -f "$LOCAL_TREE" "$REMOTE_TREE"
  die "remote served tree != local served tree (per-file hash mismatch above); NOT deployed cleanly"
fi
N_SERVED="$(wc -l < "$LOCAL_TREE" | tr -d ' ')"
rm -f "$LOCAL_TREE" "$REMOTE_TREE"
say "       remote served tree == local, byte-for-byte ($N_SERVED files remote-hashed + verified)"

# Repo tidiness: the deploy must NOT dirty the just-deployed UI worktree. The receipt lives outside
# the worktree; release_manifest.json + assets land in the SPOT app root (a different repo). If any
# untracked/modified path appears in the UI worktree, the release identity is no longer that commit.
POST_DIRTY="$(git -C "$REPO_DIR" status --porcelain)"
[ -z "$POST_DIRTY" ] || { printf '%s\n' "$POST_DIRTY" | sed 's/^/         /' >&2; die "deploy left the UI worktree dirty/untracked — a receipt/artifact leaked into the source tree"; }
say "       UI worktree still clean after deploy (no leaked receipt/artifact)"

# ─────────────────────────────────────────────────────────────────────────────
# 11. Server: hash/copy the COMMITTED serve_static.py + restart :8347 ONLY, then prove the contract
# ─────────────────────────────────────────────────────────────────────────────
# The static server is infrastructure (not part of the served tree); deploying content alone leaves
# a stale allowlist (e.g. missing .csv). Copy the committed script, verify its remote sha, restart
# the :8347 process only (never :8348), and prove GET/HEAD CSV=200, POST=405, a source ext=404.
say "[11/11] server sync + restart :8347 + prove served contract"
SERVER_SRC="$REPO_DIR/deploy/serve_static.py"   # committed at REPO-ROOT deploy/, not _frontend/deploy/
[ -f "$SERVER_SRC" ] || die "missing committed server script: $SERVER_SRC"
LOCAL_SERVER_SHA="$(sha256_of "$SERVER_SRC")"
scp -q -o BatchMode=yes "$SERVER_SRC" "$TCE_HOST:/home/tcelab/serve_static.py" || die "server scp failed"
REMOTE_SERVER_SHA="$(ssh -o BatchMode=yes "$TCE_HOST" "sha256sum /home/tcelab/serve_static.py | cut -d' ' -f1")" || die "remote server sha read failed"
[ "$REMOTE_SERVER_SHA" = "$LOCAL_SERVER_SHA" ] || die "remote serve_static.py sha $REMOTE_SERVER_SHA != committed $LOCAL_SERVER_SHA"
HARNESS_URL="${SPOT_8347_URL:-http://100.117.50.59:8347}"
URL_8348="${SPOT_8348_URL:-http://100.117.50.59:8348}"
code() { curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$@"; }
# :8348 status BEFORE (listener PID + HTTP status) — must be unchanged after we restart :8347 only.
PRE_8348_PID="$(ssh -o BatchMode=yes "$TCE_HOST" 'lsof -nP -iTCP:8348 -sTCP:LISTEN -t 2>/dev/null | head -1' || true)"
PRE_8348_HTTP="$(code "$URL_8348/" || echo 000)"
# Restart FULLY DETACHED via `setsid -f` (new session + fork) with stdin from /dev/null: in a
# non-interactive SSH shell `nohup … & disown` does NOT release the channel (the backgrounded child's
# parent shell keeps SSH blocked), so the deploy hangs. setsid -f reparents the server to init and
# returns immediately. </dev/null closes the inherited stdin so nothing holds the channel open.
ssh -o BatchMode=yes "$TCE_HOST" "pid=\$(lsof -nP -iTCP:8347 -sTCP:LISTEN -t 2>/dev/null | head -1); [ -n \"\$pid\" ] && kill \"\$pid\"; sleep 1; setsid -f env SPOT_DIST='$TCE_8347_DIR' SPOT_PORT=8347 python3 /home/tcelab/serve_static.py </dev/null >/home/tcelab/spot-static.log 2>&1; sleep 2; lsof -nP -iTCP:8347 -sTCP:LISTEN -t >/dev/null 2>&1" || die "server restart failed (:8347 not listening)"
# Prove the restart left NO lingering restart-shell parent: the listener must be reparented to init.
NEW_PID="$(ssh -o BatchMode=yes "$TCE_HOST" 'lsof -nP -iTCP:8347 -sTCP:LISTEN -t 2>/dev/null | head -1')" || die "cannot read new :8347 pid"
NEW_PPID="$(ssh -o BatchMode=yes "$TCE_HOST" "ps -o ppid= -p $NEW_PID 2>/dev/null | tr -d ' '")" || die "cannot read new :8347 parent"
[ "$NEW_PPID" = 1 ] || die "server not fully detached (:8347 pid $NEW_PID parent $NEW_PPID != init 1) — a restart-shell lingered"
# Prove the served contract on :8347.
gc="$(code "$HARNESS_URL/data/stage01_bins_v3.csv")";        [ "$gc" = 200 ] || die "GET  CSV bins != 200 (got $gc)"
hc="$(code -I "$HARNESS_URL/data/stage01_controls_v3.csv")"; [ "$hc" = 200 ] || die "HEAD CSV controls != 200 (got $hc)"
pc="$(code -X POST -d '' "$HARNESS_URL/targets.html")";      [ "$pc" = 405 ] || die "POST != 405 (got $pc)"
rc="$(code "$HARNESS_URL/rerun")";       case "$rc" in 404|405) ;; *) die "/rerun != 404/405 (got $rc)";; esac
for ext in py sh md; do
  ec="$(code "$HARNESS_URL/serve_static.$ext")";  [ "$ec" = 404 ] || die "source .$ext serve != 404 (got $ec)"
done
# :8348 status AFTER — listener PID and HTTP status must be identical (we never touched it).
POST_8348_PID="$(ssh -o BatchMode=yes "$TCE_HOST" 'lsof -nP -iTCP:8348 -sTCP:LISTEN -t 2>/dev/null | head -1' || true)"
POST_8348_HTTP="$(code "$URL_8348/" || echo 000)"
[ "$PRE_8348_PID" = "$POST_8348_PID" ] || die ":8348 listener PID changed ($PRE_8348_PID -> $POST_8348_PID)"
[ "$PRE_8348_HTTP" = "$POST_8348_HTTP" ] || die ":8348 HTTP status changed ($PRE_8348_HTTP -> $POST_8348_HTTP)"
say "       serve_static.py synced (sha ${LOCAL_SERVER_SHA:0:12}…) + :8347 restarted (setsid, pid $NEW_PID reparented to init — no lingering restart-shell)"
say "       proven: CSV GET/HEAD=200, POST=405, /rerun=$rc, source .py/.sh/.md=404"
say "       :8348 unchanged (pid ${POST_8348_PID:-none}, http $POST_8348_HTTP)"

# ─────────────────────────────────────────────────────────────────────────────
# DEPLOYED — ACCEPTANCE PENDING  (this script NEVER returns GO)
# ─────────────────────────────────────────────────────────────────────────────
hr
say "DEPLOYED — ACCEPTANCE PENDING"
say "  (this script never returns GO; only the live U01–U18 browser harness may)"
say "  ui_commit       : $UI_COMMIT"
say "  stage1_commit   : $STAGE1_DATA_COMMIT · data digest $STAGE1_DATA_DIGEST (local==remote==pinned)"
say "  served (verified): $N_SERVED files remote-hashed == local (built + preserved-stage1 + 22 data)"
say "  release manifest : $REL_MANIFEST  (served for U01)"
say "  :8348           : untouched"
hr
say "Next (REQUIRED before any GO): node _frontend/e2e/u01_u18.mjs http://100.117.50.59:8347"
say "  Only that browser harness returns GO. A deployed-but-unaccepted distribution is NOT a GO."
