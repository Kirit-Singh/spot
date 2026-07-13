#!/usr/bin/env bash
# One-command handoff to the final UI / Cloudflare deploy lane.
#
#   deploy/handoff_release.sh <staging-dir>
#
# Independently RE-VERIFIES an assembled staging dir (generator != verifier): re-hashes every
# staged file against MANIFEST.json and re-derives manifest_content_sha256 from the bytes on
# disk. On success it prints the exact deploy command for the UI/Cloudflare lane.
# It NEVER uploads, deploys, or reads credentials. Non-zero exit => do not deploy.
set -euo pipefail

STAGING="${1:-}"
if [[ -z "$STAGING" ]]; then
  echo "usage: deploy/handoff_release.sh <staging-dir>" >&2
  exit 64
fi
REPO="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST="$STAGING/MANIFEST.json"

if [[ ! -f "$MANIFEST" ]]; then
  echo "REFUSED: no MANIFEST.json in $STAGING (assemble_release.py did not complete)" >&2
  exit 2
fi

SEAL_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

python3 - "$STAGING" "$SEAL_UTC" <<'PY'
import hashlib, json, os, sys

staging, seal_utc = sys.argv[1], sys.argv[2]
with open(os.path.join(staging, "MANIFEST.json"), encoding="utf-8") as fh:
    m = json.load(fh)

problems = []
if m.get("uploaded") is not False:
    problems.append("manifest does not declare uploaded=false")

for lane, info in sorted((m.get("lanes") or {}).items()):
    if info.get("status") != "ADMIT":
        problems.append(f"lane {lane} is not ADMIT")

def sha256(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

files = m.get("files") or []
if not files:
    problems.append("manifest lists no files")
for rec in files:
    p = os.path.join(staging, rec["path"])
    if not os.path.isfile(p):
        problems.append(f"missing staged file: {rec['path']}")
        continue
    actual = sha256(p)
    if actual != rec["sha256"]:
        problems.append(f"sha256 drift: {rec['path']} manifest={rec['sha256']} on-disk={actual}")
    if os.path.getsize(p) != rec.get("size"):
        problems.append(f"size drift: {rec['path']}")

# re-derive the content address from the manifest's own content
# (must mirror assemble_release.assemble() exactly: release_id, lanes, routes, files)
content = {"release_id": m.get("release_id"), "lanes": m.get("lanes"), "routes": m.get("routes") or {},
           "files": [{k: r[k] for k in ("path", "sha256", "size", "lane", "role")} for r in files]}
blob = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
rederived = hashlib.sha256(blob.encode("utf-8")).hexdigest()
if rederived != m.get("manifest_content_sha256"):
    problems.append(f"manifest_content_sha256 drift: manifest={m.get('manifest_content_sha256')} rederived={rederived}")

if problems:
    print("REFUSED — staging dir failed independent re-verification:", file=sys.stderr)
    for p in problems:
        print("  - " + p, file=sys.stderr)
    raise SystemExit(2)

print(f"re-verified {len(files)} files; manifest_content_sha256 = {rederived}")
print("lanes: " + ", ".join(f"{k}={v['status']}" for k, v in sorted(m["lanes"].items())))

# SEAL: only written after the bytes were independently re-verified above. It is a seal on the
# CONTENT, not a publication -- uploaded stays false and nothing leaves this machine.
seal = {
    "schema_id": "spot.release_seal.v1",
    "sealed": True,
    "seal_utc": seal_utc,
    "sealed_by": "deploy/handoff_release.sh (independent re-verification; generator != verifier)",
    "release_id": m.get("release_id"),
    "manifest_content_sha256": rederived,
    "verified_file_count": len(files),
    "lanes": {k: v["status"] for k, v in sorted(m["lanes"].items())},
    "routes": m.get("routes") or {},
    "uploaded": False,
}
with open(os.path.join(staging, "SEAL.json"), "w", encoding="utf-8") as fh:
    json.dump(seal, fh, indent=2, sort_keys=True, ensure_ascii=True)
    fh.write("\n")
print(f"sealed -> SEAL.json ({seal_utc}); uploaded=false")
PY

cat <<EOF

HANDOFF -> UI / Cloudflare deploy lane (nothing has been uploaded)
  release staging : $STAGING
  manifest        : $MANIFEST
  UI dist build   : $REPO/deploy/build_dist.sh <dist-dir>

The deploy lane owns publication. It consumes the re-verified staging dir above; the
Cloudflare publish step (site mode, secrets, DNS) is gated and is NOT run from here.
EOF
