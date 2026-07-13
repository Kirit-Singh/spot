#!/usr/bin/env python3
"""Fail-closed final public-release assembler.

Takes the EXACT admitted Stage1..Stage4 artifact paths + verifier receipts (via a release
spec), copies ONLY allowlisted public files into an EXTERNAL staging directory, and emits a
content-addressed manifest.

Fail-closed by construction:
  * every one of stage1..stage4 must be present in the spec AND status == "ADMIT";
  * every declared artifact + receipt must exist; a declared expected_sha256 must match the
    bytes on disk (no hash is ever invented — the manifest records only measured hashes);
  * a receipt must be non-empty valid JSON, must carry a positive verdict, and must not carry
    a negative one;
  * every source file is scanned for secrets and machine-local paths BEFORE anything is
    copied, so a refusal writes nothing at all;
  * the staging directory must be absolute, OUTSIDE the repo, and empty.

Any failure => nothing is staged, no manifest, exit 2. This tool NEVER uploads and never
reads credentials.

Usage:
  python3 deploy/assemble_release.py --spec <spec.json> --staging-dir <abs dir outside repo>
                                     [--run-utc <ISO8601Z>] [--lenient-receipt]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

REQUIRED_LANES = ("stage1", "stage2", "stage3", "stage4")
ADMIT = "ADMIT"

# Repo-relative public files that always ship with a release. Each is scanned like any other
# file; a missing entry is a refusal (the allowlist is a policy, not a best-effort glob).
REPO_PUBLIC_ALLOWLIST = [
    "README.md",
    "LICENSE",
    "DATA_LICENSES.md",
    "schemas/README.md",
    "schemas/source_license_inventory.json",
    "schemas/paper_concordance_run_receipt.schema.json",
    "01_programs/README.md",
    "02_geneskew/README.md",
    "03_druglink/README.md",
    "04_PKPD/README.md",
    "05_trial/README.md",
    "01_programs/hf_release/STAGE1_V3_DATASET_CARD.template.md",
    "01_programs/hf_release/stage1_release_hf_manifest.template.json",
    "docs/PUBLIC_PACKAGING_CHECKLIST.md",
    "docs/history/README.md",
]

# Never stage these, whatever a spec says.
DENY_EXTENSIONS = {".env", ".pem", ".key", ".p12", ".pfx", ".crt", ".h5ad", ".h5mu", ".pyc"}
DENY_BASENAMES = {".env", ".npmrc", ".netrc", "id_rsa", "id_ed25519", "credentials"}

SECRET_PATTERNS = [
    ("hf_token", re.compile(r"\bhf_[A-Za-z0-9]{34,}")),
    ("aws_akia", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("generic_key", re.compile(r"(?:api[_-]?key|secret[_-]?key|access[_-]?token)\s*[=:]\s*[\"']?[A-Za-z0-9_\-]{20,}", re.I)),
    ("bearer", re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}")),
    ("openai", re.compile(r"\bsk-[A-Za-z0-9]{20,}")),
    ("github_pat", re.compile(r"\bghp_[A-Za-z0-9]{36,}")),
    ("slack", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}")),
]

MACHINE_PATTERNS = [
    ("users_path", re.compile(r"/Users/[A-Za-z0-9._-]+")),
    ("home_path", re.compile(r"/home/[A-Za-z0-9._-]+")),
    ("host_tcedirector", re.compile(r"\btcedirector:")),
    ("host_tcefold", re.compile(r"\btcefold:")),
    ("nas_path", re.compile(r"/mnt/tcenas")),
]

# Only these keys are read as a verdict, so an unrelated boolean or a "failure_scenario"
# string cannot flip the decision. Values are matched case-insensitively, exactly.
VERDICT_KEYS = {"verdict", "status", "result", "decision", "admitted", "verify_ok", "verified", "outcome"}
POSITIVE_VERDICTS = {"admit", "admitted", "pass", "passed", "verified", "verify_ok", "ok", "accept", "accepted", "green"}
NEGATIVE_VERDICTS = {"refuse", "refused", "reject", "rejected", "fail", "failed", "no-go", "nogo", "blocked", "deny", "denied", "error"}


class Refusal(Exception):
    """Fail-closed refusal. Nothing has been staged when this is raised."""


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def canonical_sha256(obj) -> str:
    blob = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _iter_items(obj):
    """Yield every (key, value) pair anywhere in a nested JSON structure."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k, v
            yield from _iter_items(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_items(v)


def receipt_verdict(path: str) -> tuple[str, dict]:
    """Return ('admit'|'refuse'|'unknown', parsed).

    Only *verdict-like keys* are consulted, so an unrelated boolean or a field such as
    "failure_scenario" cannot flip the decision. Fail-closed: unparseable/empty => Refusal;
    an explicit negative wins over a positive; no verdict at all => 'unknown'.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            parsed = json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Refusal(f"receipt is not readable/valid JSON: {os.path.basename(path)} ({exc.__class__.__name__})")
    if not parsed:
        raise Refusal(f"receipt is empty: {os.path.basename(path)}")

    positive = negative = False
    for key, value in _iter_items(parsed):
        if str(key).strip().lower() not in VERDICT_KEYS:
            continue
        if isinstance(value, bool):
            positive |= value
            negative |= not value
        elif isinstance(value, str):
            val = value.strip().lower()
            if val in NEGATIVE_VERDICTS:
                negative = True
            elif val in POSITIVE_VERDICTS:
                positive = True
    if negative:
        return "refuse", parsed
    if positive:
        return "admit", parsed
    return "unknown", parsed


def scan_text(path: str) -> list[str]:
    """Secret + machine-local-path scan. Binary files are hashed but not text-scanned."""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except (UnicodeDecodeError, OSError):
        return []  # binary / unreadable-as-text: no text scan (still hashed + deny-listed)
    issues = []
    for i, line in enumerate(lines, 1):
        for name, pat in SECRET_PATTERNS:
            if pat.search(line):
                issues.append(f"{os.path.basename(path)}:{i}: secret pattern {name}")
        # an official URL may legitimately contain /home/ etc; a machine path is never a URL
        stripped = re.sub(r"https?://\S+", "", line)
        for name, pat in MACHINE_PATTERNS:
            if pat.search(stripped):
                issues.append(f"{os.path.basename(path)}:{i}: machine-local path {name}")
    return issues


def check_deny(path: str) -> list[str]:
    base = os.path.basename(path)
    ext = os.path.splitext(base)[1].lower()
    out = []
    if ext in DENY_EXTENSIONS:
        out.append(f"{base}: denied extension {ext}")
    if base.lower() in DENY_BASENAMES:
        out.append(f"{base}: denied filename")
    return out


def _plan_file(src: str, dst: str, lane: str, role: str, expected: str | None, problems: list[str]) -> dict | None:
    if not os.path.isfile(src):
        problems.append(f"[{lane}/{role}] missing file: {dst}")
        return None
    problems.extend(f"[{lane}/{role}] {p}" for p in check_deny(src))
    problems.extend(f"[{lane}/{role}] {p}" for p in scan_text(src))
    actual = sha256_file(src)
    if expected is not None and expected != actual:
        # never invent or "fix" a hash — the mismatch is the refusal
        problems.append(f"[{lane}/{role}] sha256 mismatch for {dst}: expected {expected}, on disk {actual}")
    return {"src": src, "path": dst, "sha256": actual, "size": os.path.getsize(src), "lane": lane, "role": role}


def plan(spec: dict, lenient_receipt: bool = False) -> tuple[list[dict], dict]:
    """Validate everything and build the copy plan. Raises Refusal; stages nothing."""
    problems: list[str] = []
    files: list[dict] = []
    lanes_out: dict = {}

    lanes = spec.get("lanes")
    if not isinstance(lanes, dict):
        raise Refusal("spec has no 'lanes' object")

    for lane in REQUIRED_LANES:
        entry = lanes.get(lane)
        if not isinstance(entry, dict):
            problems.append(f"[{lane}] lane missing from spec (all of {', '.join(REQUIRED_LANES)} are required)")
            continue
        status = entry.get("status")
        if status != ADMIT:
            problems.append(f"[{lane}] status is {status!r}, required {ADMIT!r}")
            continue

        receipt = entry.get("receipt") or {}
        r_src, r_dst = receipt.get("src"), receipt.get("dst") or f"lanes/{lane}/receipt.json"
        if not r_src:
            problems.append(f"[{lane}] no verifier receipt declared")
            receipt_sha = None
        elif not os.path.isfile(r_src):
            problems.append(f"[{lane}] verifier receipt missing: {r_dst}")
            receipt_sha = None
        else:
            try:
                verdict, _ = receipt_verdict(r_src)
            except Refusal as exc:
                problems.append(f"[{lane}] {exc}")
                verdict = "refuse"
            if verdict == "refuse":
                problems.append(f"[{lane}] verifier receipt carries a negative/unusable verdict")
            elif verdict == "unknown" and not lenient_receipt:
                problems.append(f"[{lane}] verifier receipt carries no positive verdict "
                                f"(expected one of: {', '.join(sorted(POSITIVE_VERDICTS))})")
            rec = _plan_file(r_src, r_dst, lane, "receipt", receipt.get("expected_sha256"), problems)
            receipt_sha = rec["sha256"] if rec else None
            if rec:
                files.append(rec)

        artifacts = entry.get("artifacts") or []
        if not artifacts:
            problems.append(f"[{lane}] no artifacts declared")
        for a in artifacts:
            src, dst = a.get("src"), a.get("dst")
            if not src or not dst:
                problems.append(f"[{lane}] artifact needs both 'src' and 'dst'")
                continue
            rec = _plan_file(src, os.path.join("lanes", lane, dst) if not dst.startswith("lanes/") else dst,
                             lane, "artifact", a.get("expected_sha256"), problems)
            if rec:
                files.append(rec)

        lanes_out[lane] = {"status": ADMIT, "receipt_sha256": receipt_sha, "artifact_count": len(artifacts)}

    # repo public allowlist — policy, so a missing entry is a refusal
    for rel in REPO_PUBLIC_ALLOWLIST:
        src = os.path.join(REPO, rel)
        rec = _plan_file(src, os.path.join("public", rel), "repo", "public", None, problems)
        if rec:
            files.append(rec)

    if problems:
        raise Refusal("release REFUSED — nothing staged:\n  - " + "\n  - ".join(problems))
    return files, lanes_out


def check_staging_dir(staging: str) -> str:
    if not os.path.isabs(staging):
        raise Refusal(f"--staging-dir must be an absolute path (got {staging!r})")
    real = os.path.realpath(staging)
    if real == os.path.realpath(REPO) or real.startswith(os.path.realpath(REPO) + os.sep):
        raise Refusal("--staging-dir must be OUTSIDE the repo (never stage a release inside the working tree)")
    if os.path.exists(real) and os.listdir(real):
        raise Refusal(f"--staging-dir already exists and is not empty: {real} (pick a fresh dir; this tool never deletes)")
    return real


def assemble(spec_path: str, staging: str, run_utc: str | None = None,
             lenient_receipt: bool = False) -> dict:
    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)

    files, lanes_out = plan(spec, lenient_receipt=lenient_receipt)   # refuses before any write
    real = check_staging_dir(staging)

    for rec in files:
        dst = os.path.join(real, rec["path"])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(rec["src"], dst)
        staged = sha256_file(dst)
        if staged != rec["sha256"]:      # copy integrity
            raise Refusal(f"staged copy hash differs from source for {rec['path']}")

    # manifest records only measured hashes and staging-relative paths (never a source machine path)
    entries = sorted(({k: r[k] for k in ("path", "sha256", "size", "lane", "role")} for r in files),
                     key=lambda r: r["path"])
    content = {"release_id": spec.get("release_id"), "lanes": lanes_out, "files": entries}
    manifest = {
        "schema_id": "spot.public_release_manifest.v1",
        "release_id": spec.get("release_id"),
        "generator": "deploy/assemble_release.py",
        "created_utc": run_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lanes": lanes_out,
        "file_count": len(entries),
        "files": entries,
        "manifest_content_sha256": canonical_sha256(content),
        "uploaded": False,
    }
    with open(os.path.join(real, "MANIFEST.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True, ensure_ascii=True)
        fh.write("\n")

    handoff = {
        "schema_id": "spot.deploy_handoff.v1",
        "staging_dir": real,
        "manifest": "MANIFEST.json",
        "manifest_content_sha256": manifest["manifest_content_sha256"],
        "file_count": len(entries),
        "lanes": {k: v["status"] for k, v in lanes_out.items()},
        "uploaded": False,
        "next_command": f"deploy/handoff_release.sh {real}",
    }
    with open(os.path.join(real, "DEPLOY_HANDOFF.json"), "w", encoding="utf-8") as fh:
        json.dump(handoff, fh, indent=2, sort_keys=True, ensure_ascii=True)
        fh.write("\n")
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed public-release assembler (never uploads).")
    ap.add_argument("--spec", required=True, help="release spec JSON (exact admitted paths + receipts)")
    ap.add_argument("--staging-dir", required=True, help="absolute staging dir OUTSIDE the repo")
    ap.add_argument("--run-utc", default=None, help="ISO-8601 UTC stamp for the manifest (default: now)")
    ap.add_argument("--lenient-receipt", action="store_true",
                    help="accept a receipt with no explicit positive verdict (still refuses on a negative one)")
    args = ap.parse_args(argv)
    try:
        m = assemble(args.spec, args.staging_dir, args.run_utc, args.lenient_receipt)
    except Refusal as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    except (OSError, json.JSONDecodeError) as exc:
        print(f"REFUSED: could not read spec: {exc}", file=sys.stderr)
        return 2
    staged_dir = os.path.realpath(args.staging_dir)
    lanes = ", ".join(f"{name}={info['status']}" for name, info in sorted(m["lanes"].items()))
    print(f"staged {m['file_count']} files -> {staged_dir}")
    print(f"manifest_content_sha256 = {m['manifest_content_sha256']}")
    print(f"lanes: {lanes}")
    print("NOT uploaded. Hand off with one command:")
    print(f"  deploy/handoff_release.sh {staged_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
