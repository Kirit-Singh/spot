#!/usr/bin/env python3
"""Fail-closed final public-release assembler.

Takes the EXACT admitted Stage1..Stage4 artifact paths + verifier receipts (via a release
spec), copies ONLY allowlisted public files into an EXTERNAL staging directory, and emits a
content-addressed manifest. Optionally stages a prebuilt UI dist (Cloudflare) and checks the
HF packaging. It NEVER uploads and never reads credentials.

Fail-closed by construction:
  * every one of stage1..stage4 must be present in the spec AND status == "ADMIT";
  * every declared artifact + receipt must exist; a declared expected_sha256 must match the
    bytes on disk (no hash is ever invented — the manifest records only measured hashes);
  * a receipt must be non-empty valid JSON, must carry a positive verdict, must not carry a
    negative one, and must not CONTRADICT ITS OWN BODY (a verdict of "admit" alongside
    failures / self_hash_agrees=false is a refusal);
  * a receipt that NAMES the bytes it judged (subject.*_raw_sha256) binds those bytes: the
    artifact staged for that lane must hash to exactly what the receipt judged. This is what
    stops an altered artifact being paired with its original receipt;
  * every source file is scanned for secrets and machine-local paths BEFORE anything is
    copied, so a refusal writes nothing at all;
  * the staging directory must be absolute, OUTSIDE the repo, and empty.

Usage:
  python3 deploy/assemble_release.py --spec <spec.json> --staging-dir <abs dir outside repo>
                                     [--dry-run] [--run-utc <ISO8601Z>] [--lenient-receipt]
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
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")

REPO_PUBLIC_ALLOWLIST = [
    "README.md",
    "LICENSE",
    "DATA_LICENSES.md",
    "schemas/README.md",
    "schemas/source_license_inventory.json",
    "schemas/artifact_provenance.json",
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

DENY_EXTENSIONS = {".env", ".pem", ".key", ".p12", ".pfx", ".crt", ".h5ad", ".h5mu", ".pyc"}
DENY_BASENAMES = {".env", ".npmrc", ".netrc", "id_rsa", "id_ed25519", "credentials"}

# Internal / non-public classes that never reach a public release, whatever a spec says.
# Checked on BOTH the source path (prefetch-only + cache + private logs + build junk) and the
# destination path (nothing internal-looking may land in the public tree).
#
# Deliberately NOT excluded by path: build-staging dirs (e.g. _t8_staging) and OS temp dirs.
# A legitimate produced artifact (the Stage-1 scores parquet) lives under a staging dir, and a
# real run stages from a temp dir — excluding those by name would refuse real results.
EXCLUDE_PATTERNS = [
    ("cache_or_prefetch", re.compile(r"(^|/)(\.?cache|prefetch|[A-Za-z0-9_.-]*_cache)(/|$)", re.I)),
    ("private_log", re.compile(r"(^|/)logs?(/|$)|\.log$", re.I)),
    ("build_junk", re.compile(r"(^|/)(__pycache__|\.ipynb_checkpoints)(/|$)", re.I)),
    ("vcs", re.compile(r"(^|/)\.git(/|$)", re.I)),
    ("dataset_prefetch", re.compile(r"(^|/)pipeline/datasets(/|$)", re.I)),
]

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
# "pending" / "pending_independent_verification" are the PRODUCER's own honest pre-admission
# states (02_geneskew verify_release_envelope). They are explicitly NOT an admission, so they are
# NEGATIVE, not merely "unknown" — otherwise --lenient-receipt would let a producer's unverified
# artifact into a public release. A consumed artifact must be INDEPENDENTLY admitted.
NEGATIVE_VERDICTS = {"refuse", "refused", "reject", "rejected", "fail", "failed", "no-go", "nogo",
                     "blocked", "deny", "denied", "error", "pending", "pending_independent_verification"}

# ---- GO-BP-only critical path. Reactome is PARKED: not required, and never advertised in the
# deployable UI bundle. (genesets.py KNOWN_SOURCES = reactome | go_bp | fixture.)
PATHWAY_COLLECTIONS_ALLOWED = {"go_bp"}
PATHWAY_COLLECTIONS_PARKED = {"reactome"}
PARKED_IN_DIST = ("reactome",)
# genesets.py: GO-BP must name a DATED release, and the gene-set bytes must hash to their pin.
DATED_RELEASE = re.compile(r"\d{4}-\d{2}(-\d{2})?")
GENESET_SOURCE_KEYS = {"source", "geneset_source", "collection", "pathway_collection"}
GENESET_RELEASE_KEYS = {"release_id", "geneset_release_id"}
GENESET_PIN_KEYS = {"geneset_sha256", "gmt_sha256", "source_sha256", "geneset_raw_sha256",
                    "geneset_bundle_sha256", "geneset_cache_sha256"}

# THE authoritative pinned Ensembl-keyed GO-BP gene-set bundle. A pathway artifact must bind to
# exactly these bytes. The bundle lives on the run host under the operator's runs root
# ($SPOT_RUNS/direct-candidate-20260713T171655Z/inputs/geneset-cache-ensembl/); that absolute host
# path is deliberately NOT tracked here — the bundle's identity is its SHA-256, not its location.
GO_BP_GENESET_FILE = "go_bp_ensembl.genesets.json"
GO_BP_GENESET_SHA256 = "4f8b124432e9c1f75f4780b233bd55a29b04150e36d71e04d183d85e5914d2a6"

# A lane whose artifact shape is not fixed here: the public filename is taken from the receipt's
# own subject, so Stage-3/4 shapes are DISCOVERED from their final receipts, never guessed.
SUBJECT_FILE_KEYS = {"projection_file", "artifact_file", "subject_file", "filename", "file"}

# An UNADMITTED producer output is EXCLUDED from a public release, not merely labelled pending.
# The producer runs name themselves (…-unadmitted); an admitted artifact never comes from one.
UNADMITTED_PATH = re.compile(r"(^|[/_-])unadmitted([/_.-]|$)", re.I)
# A fixture/demo may never be labelled production, nor enter a public release.
FIXTURE_PATH = re.compile(r"(^|/)(fixtures?|demo)(/|$)|(^|[/_-])fixture([/_.-]|$)", re.I)
FIXTURE_FLAG_KEYS = {"is_fixture", "is_demo"}
PRODUCTION = "production"

# A receipt that NAMES the bytes it judged (e.g. the Stage-2 display projection's
# subject.projection_raw_sha256, recomputed by the verifier from the file on disk).
SUBJECT_HASH_KEYS = {"projection_raw_sha256", "raw_sha256", "artifact_raw_sha256", "artifact_sha256"}
# Body fields that must not contradict an "admit" verdict.
MUST_BE_TRUE = {"self_hash_agrees", "rebuilt_from_admitted_native_bytes", "generator_is_not_verifier"}
MUST_BE_EMPTY = {"failures"}
MUST_BE_ZERO = {"n_failed"}


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


def load_receipt(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as fh:
            parsed = json.load(fh)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise Refusal(f"receipt is not readable/valid JSON: {os.path.basename(path)} ({exc.__class__.__name__})")
    if not parsed:
        raise Refusal(f"receipt is empty: {os.path.basename(path)}")
    return parsed


def receipt_verdict(parsed: dict) -> str:
    """'admit' | 'refuse' | 'unknown' — only verdict-like KEYS are consulted."""
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
        return "refuse"
    if positive:
        return "admit"
    return "unknown"


def receipt_self_contradictions(parsed: dict) -> list[str]:
    """A verdict is not allowed to contradict the receipt's own body."""
    bad = []
    for key, value in _iter_items(parsed):
        k = str(key).strip().lower()
        if k in MUST_BE_TRUE and value is False:
            bad.append(f"receipt says {k}=false but claims admit")
        elif k in MUST_BE_EMPTY and isinstance(value, list) and value:
            bad.append(f"receipt lists {len(value)} {k} but claims admit")
        elif k in MUST_BE_ZERO and isinstance(value, int) and not isinstance(value, bool) and value > 0:
            bad.append(f"receipt says {k}={value} but claims admit")
    return bad


def receipt_subject_hashes(parsed: dict) -> set[str]:
    """The exact artifact bytes this receipt says it judged (recomputed by that verifier)."""
    out = set()
    for key, value in _iter_items(parsed):
        if str(key).strip().lower() in SUBJECT_HASH_KEYS and isinstance(value, str) and HEX64.match(value.strip().lower()):
            out.add(value.strip().lower())
    return out


def scan_text(path: str) -> list[str]:
    """Secret + machine-local-path scan. Binary files are hashed but not text-scanned."""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.readlines()
    except (UnicodeDecodeError, OSError):
        return []
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


def check_pathway_artifact(src: str, declared: str) -> list[str]:
    """GO-BP-only critical path, with the gene-set pin actually verified.

    genesets.py pins BOTH the release id and the raw sha256 of the GMT, because "Reactome"/"GO"
    is not a version: an enrichment computed against one release is not comparable with another.
    So a pathway artifact must name a DATED GO-BP release and carry a 64-hex byte pin. Reactome is
    PARKED: it is not required and must not appear.
    """
    out: list[str] = []
    d = str(declared).strip().lower()
    if d in PATHWAY_COLLECTIONS_PARKED:
        return [f"pathway_collection {d!r} is PARKED — the GO-BP-only critical path does not "
                f"require or advertise it (allowed: {sorted(PATHWAY_COLLECTIONS_ALLOWED)})"]
    if d not in PATHWAY_COLLECTIONS_ALLOWED:
        return [f"pathway_collection {d!r} is not on the critical path "
                f"(allowed: {sorted(PATHWAY_COLLECTIONS_ALLOWED)})"]
    try:
        doc = json.load(open(src, encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"pathway artifact is not readable/valid JSON ({exc.__class__.__name__})"]

    for parked in PATHWAY_COLLECTIONS_PARKED:
        if parked in json.dumps(doc).lower():
            out.append(f"pathway artifact names {parked!r}, which is PARKED and must not reach "
                       f"the deployable bundle")
    sources = {str(v).strip().lower() for k, v in _iter_items(doc)
               if str(k).strip().lower() in GENESET_SOURCE_KEYS and isinstance(v, str)}
    sources &= (PATHWAY_COLLECTIONS_ALLOWED | PATHWAY_COLLECTIONS_PARKED)
    if sources and not sources <= PATHWAY_COLLECTIONS_ALLOWED:
        out.append(f"pathway artifact declares gene-set source(s) {sorted(sources)}; only go_bp is admitted")

    releases = [v for k, v in _iter_items(doc)
                if str(k).strip().lower() in GENESET_RELEASE_KEYS and isinstance(v, str)]
    if not releases:
        out.append("pathway artifact names no gene-set release_id — GO-BP must name a DATED release "
                   "(an enrichment that names no release cannot be reproduced or contested)")
    for r in releases:
        if not DATED_RELEASE.search(r):
            out.append(f"GO-BP release_id {r!r} is not dated (YYYY-MM or YYYY-MM-DD)")

    pins = {p.strip().lower() for k, p in _iter_items(doc)
            if str(k).strip().lower() in GENESET_PIN_KEYS and isinstance(p, str)}
    hexpins = {p for p in pins if HEX64.match(p)}
    if not hexpins:
        out.append("pathway artifact carries no 64-hex gene-set byte pin "
                   f"(one of {sorted(GENESET_PIN_KEYS)}); the gene-set bytes must hash to their pin")
    elif GO_BP_GENESET_SHA256 not in hexpins:
        # byte verification against THE authoritative pinned Ensembl-keyed GO-BP bundle
        out.append(f"pathway artifact does not bind the authoritative GO-BP gene-set bundle "
                   f"({GO_BP_GENESET_FILE} sha256 {GO_BP_GENESET_SHA256[:16]}…); it pins "
                   f"{sorted(h[:16] + '…' for h in hexpins)}")
    return out


def check_source_topology(src: str, lane_declares_go_bp_pathway: bool) -> list[str]:
    """The released source list must be DERIVED from the admitted topology, never asserted.

    The UI packager hard-codes PATHWAY_SOURCES = ['reactome','go_bp'] and requires an exact match,
    so the envelope it emits names Reactome as a released AND active pathway source. The formal
    release is GO-BP-only, so any envelope that:
      * lists a PARKED source in pathway_sources, or
      * names a parked/unknown source as active_pathway_source, or
      * claims an active source while no admitted GO-BP pathway artifact is staged
    is refused. While the pathway lane is unadmitted the active source must be null (or an explicit
    awaiting-admission marker) — never Reactome.
    """
    try:
        doc = json.load(open(src, encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []      # not a JSON envelope; other gates cover it
    out: list[str] = []
    name = os.path.basename(src)

    for key, value in _iter_items(doc):
        k = str(key).strip().lower()
        if k in ("pathway_sources", "sources") and isinstance(value, list):
            listed = {str(v).strip().lower() for v in value if isinstance(v, str)}
            parked = listed & PATHWAY_COLLECTIONS_PARKED
            if parked:
                out.append(f"{name}: {k} lists PARKED source(s) {sorted(parked)} — the formal release "
                           f"is GO-BP-only; Reactome is parked history/license only")
            unknown = listed - PATHWAY_COLLECTIONS_ALLOWED - PATHWAY_COLLECTIONS_PARKED
            if k == "pathway_sources" and unknown:
                out.append(f"{name}: pathway_sources names unknown source(s) {sorted(unknown)}")
        elif k == "active_pathway_source":
            if value is None:
                continue                                   # unadmitted -> null is correct
            active = str(value).strip().lower()
            if active in PATHWAY_COLLECTIONS_PARKED:
                out.append(f"{name}: active_pathway_source is {active!r} — a PARKED source may never "
                           f"be active. While the pathway lane is unadmitted this must be null "
                           f"(or an explicit go_bp awaiting-admission marker).")
            elif active.startswith("go_bp") and active != "go_bp":
                continue                                   # e.g. "go_bp:awaiting_admission"
            elif active not in PATHWAY_COLLECTIONS_ALLOWED:
                out.append(f"{name}: active_pathway_source {active!r} is not an admitted source "
                           f"(allowed: {sorted(PATHWAY_COLLECTIONS_ALLOWED)}, or null while unadmitted)")
            elif not lane_declares_go_bp_pathway:
                out.append(f"{name}: active_pathway_source is 'go_bp' but no admitted GO-BP pathway "
                           f"artifact is staged for this lane — the active source must be DERIVED "
                           f"from the admitted topology, not asserted. Use null while unadmitted.")
    return out


def receipt_subject_files(parsed: dict) -> set[str]:
    """The artifact filename(s) a receipt says it judged — how Stage-3/4 shapes are discovered."""
    out = set()
    for key, value in _iter_items(parsed):
        if str(key).strip().lower() in SUBJECT_FILE_KEYS and isinstance(value, str):
            name = os.path.basename(value.strip())
            if name and name not in (".", "..") and "/" not in name and "\\" not in name:
                out.add(name)
    return out


def check_admitted_provenance(src: str, dst: str) -> list[str]:
    """Refuse an UNADMITTED producer output, and refuse a fixture/demo labelled production."""
    out: list[str] = []
    name = os.path.basename(dst)
    path = src.replace(os.sep, "/")
    if UNADMITTED_PATH.search(path):
        out.append(f"{name}: comes from an UNADMITTED producer run — an unadmitted output is "
                   f"EXCLUDED from a public release, not merely labelled pending")
    if FIXTURE_PATH.search(path):
        out.append(f"{name}: is a fixture/demo path — a fixture may never enter a public release")
    try:
        doc = json.load(open(src, encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return out
    for key, value in _iter_items(doc):
        k = str(key).strip().lower()
        if k in FIXTURE_FLAG_KEYS and value is True:
            out.append(f"{name}: declares {k}=true — a fixture/demo may never be released as production")
        elif k == "namespace" and isinstance(value, str) and value.strip().lower() != PRODUCTION:
            out.append(f"{name}: declares namespace={value!r}, not {PRODUCTION!r} — a non-production "
                       f"artifact may not be labelled production")
        elif k in GENESET_SOURCE_KEYS and isinstance(value, str) and value.strip().lower() == "fixture":
            out.append(f"{name}: gene-set source is 'fixture' — a fixture collection is not releasable")
    return out


def check_excluded(src: str, dst: str) -> list[str]:
    """Prefetch-only / cache / private-log / build-junk paths never reach a public release."""
    out = []
    for label, path in (("source", src.replace(os.sep, "/")), ("release", dst.replace(os.sep, "/"))):
        for name, pat in EXCLUDE_PATTERNS:
            if pat.search(path):
                out.append(f"{os.path.basename(dst)}: excluded {name} on the {label} path "
                           f"(prefetch-only/cache/private logs are never published)")
    return out


def _plan_file(src, dst, lane, role, expected, problems) -> dict | None:
    if not src:
        problems.append(f"[{lane}/{role}] no source path supplied for {dst} (slot still pending)")
        return None
    if not os.path.isfile(src):
        problems.append(f"[{lane}/{role}] missing file: {dst}")
        return None
    problems.extend(f"[{lane}/{role}] {p}" for p in check_deny(src))
    problems.extend(f"[{lane}/{role}] {p}" for p in check_excluded(src, dst))
    if lane != "repo":                       # the repo's own public docs are not producer outputs
        problems.extend(f"[{lane}/{role}] {p}" for p in check_admitted_provenance(src, dst))
    problems.extend(f"[{lane}/{role}] {p}" for p in scan_text(src))
    actual = sha256_file(src)
    if expected is not None and expected != actual:
        problems.append(f"[{lane}/{role}] sha256 mismatch for {dst}: expected {expected}, on disk {actual}")
    return {"src": src, "path": dst, "sha256": actual, "size": os.path.getsize(src), "lane": lane, "role": role}


def check_hf_package(hf: dict, problems: list[str]) -> dict:
    """HF packaging must be publishable without PRETENDING to be published."""
    out = {"card": None, "manifest": None, "immutable_source_revision": None,
           "stage1_release_hf_revision": None}
    card, man = hf.get("card"), hf.get("manifest")
    for label, p in (("card", card), ("manifest", man)):
        if not p or not os.path.isfile(p):
            problems.append(f"[hf/{label}] missing file: {p}")
    if not man or not os.path.isfile(man):
        return out
    try:
        doc = json.load(open(man, encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        problems.append(f"[hf/manifest] not valid JSON ({exc.__class__.__name__})")
        return out

    src_rev = (doc.get("immutable_source") or {}).get("hf_revision")
    if not (isinstance(src_rev, str) and HEX40.match(src_rev)):
        problems.append("[hf] immutable_source.hf_revision must be a 40-hex revision (the source object is fixed)")
    out["immutable_source_revision"] = src_rev

    rel_rev = (doc.get("stage1_v3_release") or {}).get("stage1_release_hf_revision")
    if rel_rev is not None and not (isinstance(rel_rev, str) and HEX40.match(rel_rev)):
        problems.append(f"[hf] stage1_release_hf_revision is {rel_rev!r} — must be null (not yet uploaded) "
                        "or a real 40-hex revision returned by an actual upload. Never a placeholder.")
    out["stage1_release_hf_revision"] = rel_rev
    if doc.get("status") not in (None, "TEMPLATE_ONLY_NOT_UPLOADED") and rel_rev is None:
        problems.append("[hf] manifest claims a non-template status without a returned revision")
    out["card"], out["manifest"] = os.path.basename(card or ""), os.path.basename(man)
    return out


def plan(spec: dict, lenient_receipt: bool = False) -> tuple[list[dict], dict, dict]:
    """Validate everything and build the copy plan. Raises Refusal; stages nothing."""
    problems: list[str] = []
    files: list[dict] = []
    lanes_out: dict = {}
    lane_hashes: dict[str, set] = {}

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
            problems.append(f"[{lane}] status is {status!r}, required {ADMIT!r} "
                            f"(no upload until every production receipt admits)")
            continue

        subject_hashes: set[str] = set()
        subject_files: set[str] = set()
        receipt = entry.get("receipt") or {}
        r_src = receipt.get("src")
        r_dst = receipt.get("dst") or f"lanes/{lane}/receipt.json"
        receipt_sha = None
        if not r_src:
            problems.append(f"[{lane}] no verifier receipt declared")
        elif not os.path.isfile(r_src):
            problems.append(f"[{lane}] verifier receipt missing: {r_dst}")
        else:
            try:
                parsed = load_receipt(r_src)
                verdict = receipt_verdict(parsed)
                if verdict == "refuse":
                    problems.append(f"[{lane}] verifier receipt carries a negative verdict")
                elif verdict == "unknown" and not lenient_receipt:
                    problems.append(f"[{lane}] verifier receipt carries no positive verdict "
                                    f"(one of: {', '.join(sorted(POSITIVE_VERDICTS))})")
                for c in receipt_self_contradictions(parsed):
                    problems.append(f"[{lane}] {c}")
                subject_hashes = receipt_subject_hashes(parsed)
                subject_files = receipt_subject_files(parsed)
            except Refusal as exc:
                problems.append(f"[{lane}] {exc}")
            rec = _plan_file(r_src, r_dst, lane, "receipt", receipt.get("expected_sha256"), problems)
            if rec:
                files.append(rec)
                receipt_sha = rec["sha256"]

        artifacts = entry.get("artifacts") or []
        if not artifacts:
            problems.append(f"[{lane}] no artifacts declared")
        # the released source list is DERIVED from the admitted topology, never asserted
        declares_go_bp = any(str(a.get("pathway_collection", "")).strip().lower() == "go_bp"
                             for a in artifacts)
        staged_hashes = set()
        for a in artifacts:
            dst = a.get("dst")
            if a.get("dst_from_receipt"):
                # shape DISCOVERED from the final receipt, never guessed here
                if len(subject_files) != 1:
                    problems.append(
                        f"[{lane}] dst_from_receipt: the receipt must name exactly ONE subject file "
                        f"to take the public shape from (found {sorted(subject_files) or 'none'})")
                    continue
                if not a.get("bound_by_receipt"):
                    problems.append(f"[{lane}] dst_from_receipt requires bound_by_receipt: a shape "
                                    f"taken from a receipt must also be bound to the bytes it judged")
                    continue
                dst = next(iter(subject_files))
            if not dst:
                problems.append(f"[{lane}] artifact needs a 'dst' (or dst_from_receipt to take it "
                                f"from the receipt's subject)")
                continue
            dst = dst if dst.startswith("lanes/") else os.path.join("lanes", lane, dst)
            rec = _plan_file(a.get("src"), dst, lane, "artifact", a.get("expected_sha256"), problems)
            if not rec:
                continue
            staged_hashes.add(rec["sha256"])
            problems.extend(f"[{lane}] {p}" for p in check_source_topology(a["src"], declares_go_bp))
            if a.get("pathway_collection"):
                problems.extend(f"[{lane}] {p}" for p in
                                check_pathway_artifact(a["src"], a["pathway_collection"]))
            if a.get("bound_by_receipt") and rec["sha256"] not in subject_hashes:
                problems.append(
                    f"[{lane}] {os.path.basename(dst)} is declared bound_by_receipt but the receipt "
                    f"does not name these bytes (on disk {rec['sha256'][:16]}…). An altered artifact "
                    f"paired with its original receipt is exactly what this refuses.")
            rec["receipt_bound"] = bool(a.get("bound_by_receipt"))
            files.append(rec)

        # every byte the receipt says it judged must actually be staged for this lane
        for missing in sorted(subject_hashes - staged_hashes):
            problems.append(f"[{lane}] the receipt judged bytes {missing[:16]}… that are not staged "
                            f"for this lane (the receipt's subject is absent)")

        lanes_out[lane] = {"status": ADMIT, "receipt_sha256": receipt_sha,
                           "artifact_count": len(artifacts), "route": entry.get("route")}
        lane_hashes[lane] = staged_hashes

    # ---- a lane may consume ONLY independently admitted upstream artifacts, named by hash.
    # Stage-3/4 read Stage-2's arms; naming the upstream lane is not enough — an unnamed or
    # unmatched hash means the consumer rests on bytes nobody admitted.
    for lane in REQUIRED_LANES:
        entry = lanes.get(lane)
        if not isinstance(entry, dict) or entry.get("status") != ADMIT:
            continue
        for c in entry.get("consumes") or []:
            up = c.get("lane")
            sha = c.get("artifact_sha256")
            if up not in REQUIRED_LANES:
                problems.append(f"[{lane}] consumes unknown lane {up!r}")
                continue
            if lanes.get(up, {}).get("status") != ADMIT:
                problems.append(f"[{lane}] consumes {up} which is not ADMIT — a consumer may only "
                                f"rest on an independently admitted lane")
                continue
            if not sha:
                problems.append(f"[{lane}] consumes an artifact from {up} with no artifact_sha256 "
                                f"— a consumed artifact must be named by the bytes it is")
            elif sha not in lane_hashes.get(up, set()):
                problems.append(f"[{lane}] consumes {str(sha)[:16]}… from {up}, which is not among "
                                f"that lane's admitted staged artifacts")

    # optional prebuilt UI dist (Cloudflare)
    dist = spec.get("dist") or {}
    dist_out = None
    if dist.get("src"):
        root = dist["src"]
        if not os.path.isdir(root):
            problems.append(f"[dist] not a directory: {root}")
        else:
            found = []
            for base, _, names in os.walk(root):
                for n in sorted(names):
                    p = os.path.join(base, n)
                    rel = os.path.relpath(p, root)
                    rec = _plan_file(p, os.path.join("dist", rel), "dist", "dist", None, problems)
                    if rec:
                        # the deployable UI bundle must not require OR advertise a parked source
                        try:
                            text = open(p, encoding="utf-8").read().lower()
                        except (UnicodeDecodeError, OSError):
                            text = ""
                        for parked in PARKED_IN_DIST:
                            if parked in text:
                                problems.append(f"[dist] {rel} advertises the PARKED source "
                                                f"{parked!r}; the deployable UI bundle is GO-BP-only")
                        # deployable current/release metadata may never NAME Reactome, and may not
                        # assert an active source the admitted topology does not support.
                        for issue in check_source_topology(p, False):
                            problems.append(f"[dist] {issue}")
                        found.append(rec)
            if not found:
                problems.append(f"[dist] directory is empty: {root}")
            files.extend(found)
            dist_out = {"file_count": len(found)}

    # optional HF packaging checks
    hf_out = check_hf_package(spec["hf"], problems) if spec.get("hf") else None

    # repo public allowlist — policy, so a missing entry is a refusal
    for rel in REPO_PUBLIC_ALLOWLIST:
        rec = _plan_file(os.path.join(REPO, rel), os.path.join("public", rel), "repo", "public", None, problems)
        if rec:
            files.append(rec)

    if problems:
        raise Refusal("release REFUSED — nothing staged:\n  - " + "\n  - ".join(problems))
    return files, lanes_out, {"dist": dist_out, "hf": hf_out}


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
             lenient_receipt: bool = False, dry_run: bool = False) -> dict:
    with open(spec_path, encoding="utf-8") as fh:
        spec = json.load(fh)

    files, lanes_out, extra = plan(spec, lenient_receipt=lenient_receipt)   # refuses before any write
    if dry_run:
        return {"dry_run": True, "would_stage": len(files), "lanes": lanes_out,
                "files": [{k: r[k] for k in ("path", "sha256", "size", "lane", "role")} for r in files],
                **extra}

    real = check_staging_dir(staging)
    for rec in files:
        dst = os.path.join(real, rec["path"])
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(rec["src"], dst)
        if sha256_file(dst) != rec["sha256"]:
            raise Refusal(f"staged copy hash differs from source for {rec['path']}")

    entries = sorted(({k: r[k] for k in ("path", "sha256", "size", "lane", "role")} for r in files),
                     key=lambda r: r["path"])
    routes = {k: v["route"] for k, v in lanes_out.items() if v.get("route")}
    content = {"release_id": spec.get("release_id"), "lanes": lanes_out, "routes": routes, "files": entries}
    manifest = {
        "schema_id": "spot.public_release_manifest.v1",
        "release_id": spec.get("release_id"),
        "generator": "deploy/assemble_release.py",
        "created_utc": run_utc or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lanes": lanes_out,
        "routes": routes,
        "dist": extra.get("dist"),
        "hf": extra.get("hf"),
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
        "routes": routes,
        "cloudflare": {"dist_dir": "dist", **(extra.get("dist") or {})} if extra.get("dist") else None,
        "hf": extra.get("hf"),
        "uploaded": False,
        "next_command": f"deploy/handoff_release.sh {real}",
    }
    with open(os.path.join(real, "DEPLOY_HANDOFF.json"), "w", encoding="utf-8") as fh:
        json.dump(handoff, fh, indent=2, sort_keys=True, ensure_ascii=True)
        fh.write("\n")
    return manifest


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Fail-closed public-release assembler (never uploads).")
    ap.add_argument("--spec", required=True)
    ap.add_argument("--staging-dir", required=True, help="absolute staging dir OUTSIDE the repo")
    ap.add_argument("--dry-run", action="store_true", help="validate + print the inventory; copy nothing")
    ap.add_argument("--run-utc", default=None)
    ap.add_argument("--lenient-receipt", action="store_true",
                    help="accept a receipt with no explicit positive verdict (a negative still refuses)")
    args = ap.parse_args(argv)
    try:
        m = assemble(args.spec, args.staging_dir, args.run_utc, args.lenient_receipt, args.dry_run)
    except Refusal as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 2
    except (OSError, json.JSONDecodeError) as exc:
        print(f"REFUSED: could not read spec: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(f"DRY RUN — would stage {m['would_stage']} files (nothing written)")
        for r in m["files"]:
            print(f"  {r['sha256'][:16]}…  {r['lane']:<7} {r['path']}")
        print("all lanes ADMIT; a real run would emit MANIFEST.json + DEPLOY_HANDOFF.json")
        return 0

    staged_dir = os.path.realpath(args.staging_dir)
    lanes = ", ".join(f"{n}={i['status']}" for n, i in sorted(m["lanes"].items()))
    print(f"staged {m['file_count']} files -> {staged_dir}")
    print(f"manifest_content_sha256 = {m['manifest_content_sha256']}")
    print(f"lanes: {lanes}")
    print("NOT uploaded. Hand off with one command:")
    print(f"  deploy/handoff_release.sh {staged_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
