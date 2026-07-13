"""Repository-wide public-release hygiene gates.

Every tracked worktree file is scanned.  When the Git index contains different staged
bytes, those bytes are scanned too.  A narrowly constrained, independently pinned
allowlist exists only for immutable historical/build attestations; it cannot authorize
an arbitrary active source, app, deployment, manifest, contract, or current README.
"""
from __future__ import annotations

from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = ROOT / "release" / "machine_path_allowlist.json"
POLICY = ROOT / "release" / "release_policy.json"
PUBLIC_STATE = ROOT / "release" / "public_external_artifacts.json"
INVENTORY = ROOT / "release" / "legacy_large_file_exceptions.json"

# This pin is deliberately outside release_policy.json.  Updating the policy therefore
# requires a separately visible code review, rather than letting a changed allowlist
# authorize itself by resealing an adjacent JSON file.
RELEASE_POLICY_SHA256 = "84cda99291867d31db84f6a98424dbf9d0863c741f5fed58b8d702f4d2f41a40"

_LOCAL_ROOTS = "|".join(("Users", "home", "mnt", "private", "Volumes"))
_PRIVATE_HOSTS = "|".join(("tce" + "director", "tce" + "fold"))
_SPOT_RUN_COMPONENT = "." + "spot-runs"
MACHINE_PATTERNS = {
    "machine_absolute_path": re.compile(
        r"(?<![A-Za-z0-9_])/(?:" + _LOCAL_ROOTS + r")/"
    ),
    "tilde_local_path": re.compile(r"(?<![A-Za-z0-9_])" + re.escape("~" + "/")),
    "windows_home_path": re.compile(
        r"(?i)(?<![A-Za-z0-9_])[A-Z]:[\\/](?:Users|Documents and Settings)[\\/]"
    ),
    "spot_run_path": re.compile(re.escape(_SPOT_RUN_COMPONENT) + r"[\\/]"),
    "known_private_hostname": re.compile(r"\b(?:" + _PRIVATE_HOSTS + r")\b"),
    "private_ipv4": re.compile(
        r"\b(?:10(?:\.\d{1,3}){3}|192\.168(?:\.\d{1,3}){2}|"
        r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}|"
        r"100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])(?:\.\d{1,3}){2})\b"
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
HISTORICAL_EXACT_PATHS = {
    "01_programs/analysis/REVIEW_MEMO.md",
    "01_programs/analysis/STAGE1_EXTERNAL_REVIEW_CS.md",
    "01_programs/analysis/STAGE1_REMEDIATION_REVIEW_CS.md",
    "docs/HANDOVER_temporal_th1_treg.md",
}
HISTORICAL_PREFIXES = (
    "docs/superpowers/plans/",
    "docs/superpowers/specs/",
)
SOLVER_PATHS = {
    "01_programs/analysis/stage01_solver_lock.txt",
    "01_programs/analysis/requirements.txt",
}
FROZEN_ATTESTATION_PATHS = {
    "01_programs/analysis/gen_full_release_verification.py",
    "01_programs/analysis/stage01_full_release_verification.json",
    "01_programs/analysis/stage1_t8_derive.py",
    "01_programs/analysis/verify_stage1_t8.py",
}
VERIFIER_LITERAL_PATHS = {
    "01_programs/analysis/test_effect_universe_portability.py",
}


def tracked_paths() -> list[str]:
    """Return paths present in the Git index (tracked plus newly staged files)."""
    raw = subprocess.check_output(["git", "ls-files", "-z", "--cached"], cwd=ROOT)
    return [p.decode() for p in raw.split(b"\0") if p]


def staged_paths() -> set[str]:
    raw = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z"],
        cwd=ROOT,
    )
    return {p.decode() for p in raw.split(b"\0") if p}


def decode_text(raw: bytes) -> list[str] | None:
    try:
        return raw.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return None


def text_lines(path: Path) -> list[str] | None:
    try:
        return decode_text(path.read_bytes())
    except OSError:
        return None


def text_snapshots():
    """Yield worktree text and any different staged/index text.

    This prevents a clean worktree copy from masking credentials or local paths that
    have already been staged for publication.
    """
    staged = staged_paths()
    for rel in tracked_paths():
        path = ROOT / rel
        worktree_raw = path.read_bytes() if path.is_file() else b""
        worktree_lines = decode_text(worktree_raw)
        if worktree_lines is not None:
            yield rel, "worktree", worktree_lines
        if rel not in staged:
            continue
        index_raw = subprocess.check_output(["git", "show", f":{rel}"], cwd=ROOT)
        if index_raw != worktree_raw:
            index_lines = decode_text(index_raw)
            if index_lines is not None:
                yield rel, "index", index_lines


def line_digest(line: str) -> str:
    return hashlib.sha256(line.encode("utf-8")).hexdigest()


def machine_kinds(line: str) -> set[str]:
    return {kind for kind, rx in MACHINE_PATTERNS.items() if rx.search(line)}


def secret_kinds(line: str) -> set[str]:
    return {kind for kind, rx in SECRET_PATTERNS.items() if rx.search(line)}


def allowlist_row_is_policy_permitted(row: dict) -> bool:
    """Apply hard-coded path/classification boundaries to an exception row."""
    path = row.get("path", "")
    classification = row.get("classification")
    if classification not in ALLOWED_CLASSIFICATIONS:
        return False
    if classification == "immutable_historical_provenance":
        return path in HISTORICAL_EXACT_PATHS or path.startswith(HISTORICAL_PREFIXES)
    if classification == "solver_or_build_provenance":
        return path in SOLVER_PATHS
    if classification == "frozen_release_attestation":
        return path in FROZEN_ATTESTATION_PATHS
    if classification == "verifier_guard_literal":
        return path in VERIFIER_LITERAL_PATHS
    return False


class AllowlistValidationError(AssertionError):
    """Allowlist rejection whose message never contains attacker-controlled bytes."""


def reject_allowlist_entry(position: int, issue: str) -> None:
    """Raise a fixed-shape error without formatting any rejected-row field."""
    raise AllowlistValidationError(
        f"machine-path allowlist entry {position}: {issue}"
    )


def load_and_validate_allowlist() -> Counter[tuple[str, str]]:
    doc = json.loads(ALLOWLIST.read_text())
    if not isinstance(doc, dict):
        raise AllowlistValidationError("machine-path allowlist document must be an object")
    if doc.get("schema") != "spot.release.machine_path_allowlist.v1":
        raise AllowlistValidationError("machine-path allowlist schema is invalid")
    entries = doc.get("entries")
    if not isinstance(entries, list):
        raise AllowlistValidationError("machine-path allowlist entries must be a list")
    expected: Counter[tuple[str, str]] = Counter()
    for position, row in enumerate(entries, 1):
        if not isinstance(row, dict):
            reject_allowlist_entry(position, "entry must be an object")
        path = row.get("path")
        classification = row.get("classification")
        reason = row.get("reason")
        digest = row.get("line_sha256")
        count = row.get("count", 1)
        if not isinstance(path, str) or not isinstance(classification, str):
            reject_allowlist_entry(position, "path or classification is invalid")
        if not allowlist_row_is_policy_permitted(row):
            reject_allowlist_entry(position, "outside its permitted immutable class")
        if not isinstance(reason, str) or not reason.strip():
            reject_allowlist_entry(position, "reason is missing")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            reject_allowlist_entry(position, "line digest is invalid")
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            reject_allowlist_entry(position, "count is invalid")
        expected[(path, digest)] += count
    return expected


def machine_occurrences(lines_by_path) -> Counter[tuple[str, str]]:
    found: Counter[tuple[str, str]] = Counter()
    for rel, lines in lines_by_path:
        for line in lines:
            if machine_kinds(line):
                found[(rel, line_digest(line))] += 1
    return found


def unallowlisted_machine_findings(snapshots, expected) -> list[str]:
    failures = []
    for rel, source, lines in snapshots:
        occurrences = machine_occurrences([(rel, lines)])
        for key, count in occurrences.items():
            if count > expected[key]:
                failures.append(f"{source}:{key[0]}:{key[1]}:{count}")
    return failures


def secret_findings(snapshots) -> list[str]:
    failures = []
    for rel, source, lines in snapshots:
        for number, line in enumerate(lines, 1):
            for kind in secret_kinds(line):
                failures.append(f"{source}:{rel}:{number}:{kind}")
    return failures


def current_user_facing_paths() -> list[str]:
    paths = []
    for rel in tracked_paths():
        path = Path(rel)
        if rel in {"README.md", "CITATION.cff", "DATA_LICENSES.md", "THIRD_PARTY_NOTICES.md"}:
            paths.append(rel)
        elif path.name == "README.md" and path.parts[0] in {
            "01_programs",
            "02_geneskew",
            "03_druglink",
            "04_PKPD",
        }:
            paths.append(rel)
        elif rel.startswith("01_programs/app/") and path.suffix in {".html", ".json"}:
            paths.append(rel)
        elif rel.startswith("docs/") and not rel.startswith("docs/superpowers/"):
            if path.suffix in {".md", ".html"} and "REVIEW" not in path.name:
                paths.append(rel)
    return sorted(set(paths))


def affirmative_hf_v3_claims(text: str) -> list[str]:
    """Return affirmative claims that the v3/full-score artifact is public on HF."""
    failures = []
    for clause in re.split(r"[\n.!?]+", text):
        lowered = clause.lower()
        mentions_hf = "hugging face" in lowered or "huggingface" in lowered
        mentions_v3 = any(
            marker in lowered
            for marker in ("v3", "396k", "stage01_scores_full", "full-score parquet")
        )
        affirmative = any(word in lowered for word in ("public", "published", "available"))
        negated = any(
            phrase in lowered
            for phrase in (
                "not public",
                "not published",
                "not yet published",
                "not present",
                "unpublished",
                "staged",
                "publication gate",
            )
        )
        if mentions_hf and mentions_v3 and affirmative and not negated:
            failures.append(clause.strip())
    return failures


def test_release_policy_and_reviewed_files_are_independently_pinned():
    assert hashlib.sha256(POLICY.read_bytes()).hexdigest() == RELEASE_POLICY_SHA256
    doc = json.loads(POLICY.read_text())
    assert doc["schema"] == "spot.release.policy.v1"
    assert doc["machine_path_allowlist"]["path"] == ALLOWLIST.relative_to(ROOT).as_posix()
    assert doc["machine_path_allowlist"]["raw_sha256"] == hashlib.sha256(
        ALLOWLIST.read_bytes()
    ).hexdigest()
    assert doc["public_external_artifacts"]["path"] == PUBLIC_STATE.relative_to(ROOT).as_posix()
    assert doc["public_external_artifacts"]["raw_sha256"] == hashlib.sha256(
        PUBLIC_STATE.read_bytes()
    ).hexdigest()


def test_machine_specific_lines_match_constrained_allowlist_exactly():
    expected = load_and_validate_allowlist()
    worktree = []
    snapshots = list(text_snapshots())
    for rel, source, lines in snapshots:
        if source == "worktree":
            worktree.append((rel, lines))
    assert unallowlisted_machine_findings(snapshots, expected) == []
    assert machine_occurrences(worktree) == expected


def test_active_code_cannot_self_authorize_with_resealed_allowlist():
    attack_line = "AUDIT_ACTIVE_LEAK = " + repr("/" + "Users/release-audit/private-runtime")
    attack = {
        "path": "deploy/serve_static.py",
        "line_sha256": line_digest(attack_line),
        "classification": "immutable_historical_provenance",
        "reason": "attempted self-authorization",
    }
    assert machine_kinds(attack_line) == {"machine_absolute_path"}
    assert not allowlist_row_is_policy_permitted(attack)
    assert unallowlisted_machine_findings(
        [(attack["path"], "index", [attack_line])], Counter()
    )


def test_invalid_allowlist_failure_never_echoes_sensitive_payload(tmp_path):
    """Exercise normal pytest rendering, not merely the exception's message."""
    fake = "hf_" + ("A" * 30)
    malicious_allowlist = {
        "schema": "spot.release.machine_path_allowlist.v1",
        "entries": [
            {
                "path": "deploy/serve_static.py",
                "line_sha256": "0" * 64,
                "classification": "immutable_historical_provenance",
                "reason": "invalid row carrying " + fake,
            }
        ],
    }
    allowlist_path = tmp_path / "malicious_allowlist.json"
    allowlist_path.write_text(json.dumps(malicious_allowlist))
    probe_path = tmp_path / "test_allowlist_output_probe.py"
    probe_path.write_text(
        "\n".join(
            (
                "import importlib.util",
                "import os",
                "from pathlib import Path",
                f"SCANNER = Path({str(Path(__file__).resolve())!r})",
                "spec = importlib.util.spec_from_file_location('release_hygiene_probe', SCANNER)",
                "module = importlib.util.module_from_spec(spec)",
                "spec.loader.exec_module(module)",
                "module.ALLOWLIST = Path(os.environ['SPOT_AUDIT_ALLOWLIST'])",
                "def test_invalid_row():",
                "    module.load_and_validate_allowlist()",
                "",
            )
        )
    )
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["SPOT_AUDIT_ALLOWLIST"] = str(allowlist_path)
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            str(probe_path),
        ],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    rendered = result.stdout + result.stderr
    if result.returncode != 1:
        raise AssertionError("invalid allowlist subprocess did not fail at the named gate")
    if fake in rendered:
        raise AssertionError("invalid allowlist failure exposed the sensitive-shaped value")
    if "outside its permitted immutable class" not in rendered:
        raise AssertionError("invalid allowlist subprocess missed the sanitized gate")


def test_no_secret_signatures_in_any_tracked_or_staged_text():
    assert secret_findings(text_snapshots()) == []


def test_secret_scanner_covers_its_own_test_and_allowlist():
    fake = "hf_" + ("A" * 30)
    assert secret_kinds(fake) == {"hugging_face_token"}
    assert secret_findings(
        [("release/machine_path_allowlist.json", "index", [fake])]
    ) == ["index:release/machine_path_allowlist.json:1:hugging_face_token"]
    # Neither path receives a scanner exemption; both occur in text_snapshots().
    scanned = {(rel, source) for rel, source, _ in text_snapshots()}
    assert ("release/test_release_hygiene.py", "worktree") in scanned
    assert ("release/machine_path_allowlist.json", "worktree") in scanned


def test_machine_scanner_catches_bare_private_networks_and_local_path_forms():
    probes = [
        "10." + "23.45.67",
        "172." + "20.45.67",
        "192." + "168.45.67",
        "100." + "117.50.59",
        "~" + "/project/output",
        "/" + "private/tmp/output",
        "/" + "Volumes/data/output",
        "C:" + "\\Users\\person\\output",
        "C:" + "/" + "Users/person/output",
        ("." + "spot-runs") + "/current/output",
    ]
    assert all(machine_kinds(probe) for probe in probes)


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


def test_hf_public_state_is_machine_readable_and_current_docs_do_not_overclaim():
    doc = json.loads(PUBLIC_STATE.read_text())
    assert doc["schema"] == "spot.release.public_external_artifacts.v1"
    assert doc["provider"] == "Hugging Face"
    assert re.fullmatch(r"[0-9a-f]{40}", doc["immutable_revision"])
    by_path = {row["path"]: row for row in doc["artifacts"]}
    assert by_path["ntc_clustered.h5ad"]["public"] is True
    assert by_path["stage01_umap_seed.json"]["public"] is True
    assert by_path["stage01_scores_full.parquet"]["public"] is False
    failures = []
    for rel in current_user_facing_paths():
        lines = text_lines(ROOT / rel)
        if lines is None:
            continue
        claims = affirmative_hf_v3_claims("\n".join(lines))
        failures.extend(f"{rel}:{claim}" for claim in claims)
    assert failures == []


def test_hf_claim_mutation_is_rejected():
    false_claim = "the v3 396k score Parquet is public on Hugging Face."
    assert affirmative_hf_v3_claims(false_claim) == [false_claim[:-1]]


def test_prospective_regulatory_sources_are_not_conflated_or_mislicensed():
    text = (ROOT / "DATA_LICENSES.md").read_text()
    assert "FAERS/openFDA" not in text
    assert "https://open.fda.gov/terms/" in text
    assert "https://clinicaltrials.gov/about-site/terms-conditions" in text
    assert "ClinicalTrials.gov public domain" not in text
    assert "FAERS is signal evidence only" in text


def test_current_and_prospective_stage_claims_are_consistent():
    root = (ROOT / "README.md").read_text()
    cff = (ROOT / "CITATION.cff").read_text()
    stage2 = (ROOT / "02_geneskew" / "README.md").read_text()
    stage3 = (ROOT / "03_druglink" / "README.md").read_text()
    stage4 = (ROOT / "04_PKPD" / "README.md").read_text()
    assert "Stage 1 implemented" in root
    assert "Stage-2 code preliminary and unreleased" in root
    assert "~47 MB" not in root
    cff_flat = " ".join(cff.split())
    assert "implements the Stage-1 transcriptional-program measurement system" in cff_flat
    assert "Stage-2 analysis code is preliminary" in cff_flat
    assert "no production Stage-2 output is admitted or" in stage2
    assert "prospective design only" in stage3
    assert "prospective design only" in stage4
