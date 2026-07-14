#!/usr/bin/env bash
#
# Focused test for deploy/validate_results_tree.py — the content-address gate the :8347 deploy runs
# over the OPTIONAL downstream results/ tree. Proves a well-formed tree passes and every failure mode
# (unlisted file, hash mismatch, partial/missing file, malformed or wrong-schema pointer, missing
# inventory, non-inventoried route manifest, data/-escaping path) is refused. No network, no deploy.
#
# Run: bash _frontend/deploy/test_results_copyset.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VALIDATOR="$HERE/validate_results_tree.py"
sha() { shasum -a 256 "$1" | awk '{print $1}'; }
HEX64="$(printf 'a%.0s' {1..64})"
pass=0; fail=0

check() {  # name  expected(OK|ERR)  root
  local name="$1" expect="$2" root="$3" out verdict
  out="$(python3 "$VALIDATOR" "$root" 2>&1 || true)"
  verdict="$(printf '%s\n' "$out" | head -1 | awk '{print $1}')"
  if [ "$verdict" = "$expect" ]; then printf 'ok   %-38s (%s)\n' "$name" "$verdict"; pass=$((pass+1));
  else printf 'FAIL %-38s — expected %s got: %s\n' "$name" "$expect" "$out"; fail=$((fail+1)); fi
}

build_valid() {  # write a well-formed 2-file results tree into $1
  local r="$1"; mkdir -p "$r/manifests"
  printf '{"schema_version":"spot.ui_release_manifest.v1"}' > "$r/manifests/targets.ui_release.json"
  printf '{"candidates":[]}' > "$r/stage02.ui.json"
  local mh sh; mh="$(sha "$r/manifests/targets.ui_release.json")"; sh="$(sha "$r/stage02.ui.json")"
  cat > "$r/current.json" <<JSON
{ "schema":"spot.ui_results_current.v1",
  "stage1_binding":{"release_method_version":"stage1-continuous-v3.0.1","registry_scorer_view_sha256":"$HEX64"},
  "routes":{"targets":{"manifest_path":"manifests/targets.ui_release.json","content_hash":"$mh","projection_path":null,"projection_content_hash":null}},
  "inventory":[{"path":"manifests/targets.ui_release.json","sha256":"$mh"},{"path":"stage02.ui.json","sha256":"$sh"}] }
JSON
}
edit_current() { python3 - "$1" "$2" <<'PY'
import json, sys
path, expr = sys.argv[1], sys.argv[2]
d = json.load(open(path)); exec(expr); json.dump(d, open(path, 'w'))
PY
}

R="$(mktemp -d)"; build_valid "$R"; check "valid tree" OK "$R"; rm -rf "$R"
R="$(mktemp -d)"; build_valid "$R"; printf 'x' > "$R/extra.json"; check "unlisted file" ERR "$R"; rm -rf "$R"
R="$(mktemp -d)"; build_valid "$R"; printf 'TAMPERED' > "$R/stage02.ui.json"; check "hash mismatch" ERR "$R"; rm -rf "$R"
R="$(mktemp -d)"; build_valid "$R"; rm "$R/stage02.ui.json"; check "partial tree (missing file)" ERR "$R"; rm -rf "$R"
R="$(mktemp -d)"; build_valid "$R"; printf '{ not json' > "$R/current.json"; check "malformed current.json" ERR "$R"; rm -rf "$R"
R="$(mktemp -d)"; mkdir -p "$R"; printf '{"schema":"x"}' > "$R/current.json"; check "wrong schema" ERR "$R"; rm -rf "$R"
R="$(mktemp -d)"; build_valid "$R"; edit_current "$R/current.json" "d['routes']['targets']['manifest_path']='manifests/missing.json'"; check "route manifest not inventoried" ERR "$R"; rm -rf "$R"
R="$(mktemp -d)"; build_valid "$R"; edit_current "$R/current.json" "d['inventory'].append({'path':'data/x.json','sha256':'$HEX64'})"; check "inventory path under data/" ERR "$R"; rm -rf "$R"
R="$(mktemp -d)"; build_valid "$R"; edit_current "$R/current.json" "d.pop('inventory')"; check "no inventory[]" ERR "$R"; rm -rf "$R"
R="$(mktemp -d)"; check "missing current.json" ERR "$R"; rm -rf "$R"

printf -- '── %d passed, %d failed ──\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
