"""Repository-wide public-release hygiene gates.

Machine-specific strings are refused unless an exact line hash is reviewed as immutable
historical/build provenance. The test and allowlist files are excluded because they
necessarily contain the detector expressions; all other tracked text is scanned.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = ROOT / "release" / "machine_path_allowlist.json"
INVENTORY = ROOT / "release" / "legacy_large_file_exceptions.json"
SCANNER_IMPLEMENTATION = {
    "release/machine_path_allowlist.json",
    "release/test_release_hygiene.py",
}
MACHINE_PATTERNS = {
    "machine_absolute_path": re.compile(r"(?<![A-Za-z0-9_])/(?:Users|home|mnt)/"),
    "known_private_hostname": re.compile(r"\b(?:tcedirector|tcefold)\b"),
    "private_ipv4": re.compile(
        r"\b100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])(?:\.\d{1,3}){2}\b|"
        r"(?:https?|ssh)://(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|"
        r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})\b"
    ),
}
SECRET_PATTERNS = {
    "hugging_face_token": re.compile(r"\bhf_[A-Za-z0-9]{20,}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    "openai_style_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "bearer_token": re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{20,}={0,2}\b", re.I),
}
ALLOWED_CLASSIFICATIONS = {
    "immutable_historical_provenance",
    "solver_or_build_provenance",
    "frozen_release_attestation",
    "verifier_guard_literal",
}


def tracked_paths() -> list[str]:
    raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT)
    return [p.decode() for p in raw.split(b"\0") if p]


def text_lines(path: Path) -> list[str] | None:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return None


def line_digest(line: str) -> str:
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


def machine_occurrences() -> Counter[tuple[str, str]]:
    found: Counter[tuple[str, str]] = Counter()
    for rel in tracked_paths():
        if rel in SCANNER_IMPLEMENTATION:
            continue
        lines = text_lines(ROOT / rel)
        if lines is None:
            continue
        for line in lines:
            if any(rx.search(line) for rx in MACHINE_PATTERNS.values()):
                found[(rel, line_digest(line))] += 1
    return found


def test_machine_specific_lines_match_narrow_allowlist_exactly():
    doc = json.loads(ALLOWLIST.read_text())
    assert doc["schema"] == "spot.release.machine_path_allowlist.v1"
    expected: Counter[tuple[str, str]] = Counter()
    for row in doc["entries"]:
        assert row["classification"] in ALLOWED_CLASSIFICATIONS
        assert row["reason"].strip()
        assert len(row["line_sha256"]) == 64
        expected[(row["path"], row["line_sha256"])] += int(row.get("count", 1))
    assert machine_occurrences() == expected


def test_no_tracked_secret_signatures():
    failures = []
    for rel in tracked_paths():
        if rel in SCANNER_IMPLEMENTATION:
            continue
        lines = text_lines(ROOT / rel)
        if lines is None:
            continue
        for number, line in enumerate(lines, 1):
            for kind, rx in SECRET_PATTERNS.items():
                if rx.search(line):
                    failures.append(f"{rel}:{number}:{kind}")
    assert failures == []


def test_legacy_large_file_inventory_is_complete_and_exact():
    doc = json.loads(INVENTORY.read_text())
    threshold = int(doc["policy_threshold_bytes"])
    rows = {row["path"]: row for row in doc["entries"]}
    actual = {}
    for rel in tracked_paths():
        path = ROOT / rel
        if path.is_file() and path.stat().st_size > threshold:
            actual[rel] = {
                "size_bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
    assert set(rows) == set(actual)
    for rel, values in actual.items():
        assert rows[rel]["size_bytes"] == values["size_bytes"]
        assert rows[rel]["sha256"] == values["sha256"]
        assert rows[rel]["role"].strip()
        assert rows[rel]["retirement_condition"].strip()


def test_hf_checklist_does_not_claim_staged_v3_is_public():
    text = (ROOT / "docs" / "HF_SUPERSEDING_RELEASE_CHECKLIST.md").read_text()
    assert "stage01_scores_full.parquet`: **not present**" in text
    assert "publication gate**, not a publication record" in text.lower()
