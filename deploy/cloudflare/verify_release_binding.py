#!/usr/bin/env python3
"""Release-binding gate for the canonical full-app Cloudflare Pages distribution.

Binds every packaged app byte to the INDEPENDENTLY APPROVED :8347 release manifest and
refuses anything that is not an admitted artifact. It is fail-closed in every direction:
an unlisted file, a drifted hash, a manifest entry that was not packaged, a not-yet-admitted
Stage-1 gate, un-parked Reactome release metadata, a fixture-classed artifact, or a
placeholder route each REFUSE the release.

generator != verifier: this re-derives every hash from the packaged bytes and re-reads the
deployment signal from the manifests. It never trusts a self-declared "ok" flag, and it never
regenerates or repairs the distribution.

Usage:
  verify_release_binding.py <dist> --approved <release_manifest.json>
      [--stage1-gate <stage01_release_manifest.json>]
      [--parked <reactome_parked.allowlist>]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

# Pages control files are gate infrastructure, not admitted app artifacts. They are the ONLY
# packaged paths permitted to be absent from the approved release manifest.
CONTROL_FILES = frozenset({"_headers", "_routes.json", "404.html", "site_release_manifest.json"})

# A GO-BP-only release must not ship Reactome release metadata, coverage text, or download
# provenance. Only explicitly PARKED license/history files may mention it.
REACTOME = re.compile(rb"reactome", re.IGNORECASE)

# The app labels artifact provenance with a typed class. A fixture- or demo-classed artifact
# must never reach production.
FIXTURE_ID = re.compile(rb"\b(?:fixture|demo)\s*:\s*stage0[1-4]\b", re.IGNORECASE)

# The placeholder ROUTE is identified by its machine marker, not by prose.
PLACEHOLDER_ROUTE = re.compile(rb"data-placeholder\s*=\s*[\"']true[\"']", re.IGNORECASE)

# Separately: interim copy that is true only while the workbench is unreleased. It is not a
# placeholder route, but it must not survive into the full release, so it is reported on its
# own rather than conflated with one.
INTERIM_COPY = re.compile(rb"being assembled|limited to reviewers while the work is in progress", re.IGNORECASE)

TEXT_SUFFIXES = frozenset({".css", ".csv", ".html", ".js", ".json", ".svg", ".map", ".txt"})


class Refusal(Exception):
    """A release-blocking finding. Every one is fatal; none is a warning."""


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path, label: str) -> dict:
    if not path.is_file():
        raise Refusal(f"{label} is missing: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise Refusal(f"{label} is not valid JSON: {path} ({exc})") from exc


def approved_index(manifest: dict, path: Path) -> dict[str, str]:
    """path -> sha256 for every admitted artifact. Refuses a manifest that is not hash-bound."""
    files = manifest.get("files")
    if not isinstance(files, list) or not files:
        raise Refusal(f"approved manifest carries no files[]: {path}")
    index: dict[str, str] = {}
    for entry in files:
        rel = entry.get("path")
        digest = entry.get("sha256") or entry.get("raw_sha256")
        if not isinstance(rel, str) or not re.fullmatch(r"[0-9a-f]{64}", digest or ""):
            raise Refusal(f"approved manifest entry is not hash-bound: {entry!r}")
        if rel in index:
            raise Refusal(f"approved manifest lists {rel} twice")
        index[rel] = digest
    return index


def check_stage1_gate(gate: dict, path: Path) -> None:
    """The Stage-1 release manifest must itself ADMIT deployment. This is the independent
    approval the whole release hangs on, so it is read, never assumed."""
    gates = gate.get("release_gates")
    if not isinstance(gates, dict):
        raise Refusal(f"Stage-1 gate manifest carries no release_gates: {path}")
    if gates.get("app_deployment_ready") is not True:
        raise Refusal(
            "Stage-1 gate refuses deployment: release_gates.app_deployment_ready is "
            f"{gates.get('app_deployment_ready')!r} (must be true)"
        )
    if gates.get("overlay_release_ok") is False:
        raise Refusal("Stage-1 gate refuses deployment: release_gates.overlay_release_ok is false")
    reasons = gate.get("not_lockable_reason_codes") or []
    if reasons:
        raise Refusal(f"Stage-1 release is not lockable: {reasons}")
    missing = gate.get("missing_required_artifacts") or []
    if missing:
        raise Refusal(f"Stage-1 release is missing required artifacts: {missing}")


def load_parked(path: Path | None) -> set[str]:
    """Explicitly parked license/history paths that MAY mention Reactome. Anything else may not."""
    if path is None:
        return set()
    if not path.is_file():
        raise Refusal(f"parked allowlist is missing: {path}")
    parked: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = line.split("#", 1)[0].strip()
        if entry:
            parked.add(entry)
    return parked


def packaged_files(dist: Path) -> list[str]:
    out = []
    for item in sorted(dist.rglob("*")):
        if item.is_symlink():
            raise Refusal(f"symlink refused in distribution: {item.relative_to(dist)}")
        if item.is_file():
            out.append(item.relative_to(dist).as_posix())
    if not out:
        raise Refusal(f"distribution is empty: {dist}")
    return out


def verify(dist: Path, approved_path: Path, gate_path: Path | None, parked_path: Path | None) -> list[str]:
    findings: list[str] = []
    approved = approved_index(load_json(approved_path, "approved release manifest"), approved_path)
    parked = load_parked(parked_path)

    # 1. The Stage-1 gate must admit deployment before anything is packaged at all.
    gate_file = gate_path or (dist / "data" / "stage01_release_manifest.json")
    try:
        check_stage1_gate(load_json(gate_file, "Stage-1 gate manifest"), gate_file)
    except Refusal as exc:
        findings.append(f"GATE: {exc}")

    packaged = packaged_files(dist)

    # 2. Every packaged app byte must be an admitted artifact at its admitted hash.
    for rel in packaged:
        if rel in CONTROL_FILES:
            continue
        expected = approved.get(rel)
        if expected is None:
            findings.append(f"UNLISTED: {rel} is packaged but not in the approved release manifest")
            continue
        actual = sha256_of(dist / rel)
        if actual != expected:
            findings.append(f"DRIFT: {rel} sha256 {actual[:12]} != admitted {expected[:12]}")

    # 3. Every admitted artifact must actually be packaged (no silent truncation).
    for rel in sorted(approved):
        if rel not in packaged:
            findings.append(f"MISSING: admitted artifact {rel} was not packaged")

    # 4. Content refusals over the served bytes.
    for rel in packaged:
        if Path(rel).suffix.lower() not in TEXT_SUFFIXES:
            continue
        blob = (dist / rel).read_bytes()
        if REACTOME.search(blob) and rel not in parked:
            findings.append(
                f"REACTOME: {rel} carries Reactome release metadata/text and is not an "
                "explicitly parked license/history file (release is GO-BP-only)"
            )
        if FIXTURE_ID.search(blob):
            findings.append(f"FIXTURE: {rel} carries a fixture/demo-classed artifact id")
        if PLACEHOLDER_ROUTE.search(blob):
            findings.append(f"PLACEHOLDER: {rel} is a placeholder route (data-placeholder marker)")
        if INTERIM_COPY.search(blob):
            findings.append(
                f"INTERIM_COPY: {rel} still says the workbench is being assembled / reviewer-limited; "
                "that copy is false once the full app is released"
            )

    # 5. Control files must be exactly the expected set — no more, no fewer.
    present_control = {rel for rel in packaged if rel in CONTROL_FILES}
    for rel in sorted(CONTROL_FILES - present_control):
        findings.append(f"CONTROL: required Pages control file {rel} is absent")

    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("dist", type=Path)
    parser.add_argument("--approved", type=Path, required=True)
    parser.add_argument("--stage1-gate", type=Path, default=None)
    parser.add_argument("--parked", type=Path, default=None)
    args = parser.parse_args(argv)

    try:
        findings = verify(args.dist, args.approved, args.stage1_gate, args.parked)
    except Refusal as exc:
        print(f"RELEASE REFUSED: {exc}", file=sys.stderr)
        return 2

    if findings:
        print(f"RELEASE REFUSED — {len(findings)} blocking finding(s):", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        return 1

    print("Release binding verified: every packaged byte matches the approved release manifest.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
