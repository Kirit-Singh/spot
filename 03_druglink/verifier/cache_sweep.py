"""Sweep the extracted cache: every JSON parses, and no public artifact leaks a path or token.

The real cache at ``/home/tcelab/.cache/spot-stage3-universe`` is QUARANTINED: three source
provenance files are malformed from unescaped quoted ETags, and they contain local paths.
Both halves of that are exactly what this module refuses.

WHY A MALFORMED FILE MUST *FAIL*, NOT BE SKIPPED
------------------------------------------------
An ETag is served quoted — ``ETag: "abc123"`` — and writing it into JSON without escaping
produces ``"etag": ""abc123""``, which is not JSON. The tempting handling is
``try: json.load(...) except: continue`` — skip the bad file, verify the rest, report green.
Then the verifier's green means *"every file I could read was fine"*, which is not a
statement about the cache at all: the files it could not read are precisely the ones nobody
checked.

So an unparseable file is a **named refusal**, and the refusal says which file and where the
parse died. A verifier that skips what it cannot read is a verifier that cannot find
anything.

WHY THE PATH SCAN IS RECURSIVE AND COVERS EVERY FILE
----------------------------------------------------
``/home/tcelab/...`` inside a published artifact leaks the machine, the user and the layout,
and it makes the artifact unreproducible anywhere else — a consumer cannot resolve a path
that only existed on the producer's disk. Provenance is the file type most likely to carry
one, because it is written by code that has the path in hand.

Tokens are worse: a bearer token or API key in a public artifact is a credential leak, and a
cache is exactly the kind of by-product nobody re-reads before publishing.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

from .report import Report
from . import policy

# Anything that names a machine, a user or a local layout.
LOCAL_PATH_RE = policy.LOCAL_PATH_RE

# Credential shapes. Deliberately broad: a false positive costs a look, a miss costs a key.
TOKEN_PATTERNS = (
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}"), "github_token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "github_pat"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}"), "openai_key"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "aws_access_key"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}"), "slack_token"),
    (re.compile(r"(?i)\b(authorization|bearer)\s*[:=]\s*\S+"), "authorization_header"),
    (re.compile(r"(?i)\b(api[_-]?key|secret|password|passwd|token)\s*[\"']?\s*[:=]\s*"
                r"[\"']?[A-Za-z0-9/\+_-]{12,}"), "credential_like"),
)

# ETags arrive QUOTED from the server. They must be stored escaped, or as the bare value.
QUOTED_ETAG_RE = re.compile(r'"etag"\s*:\s*""')


class CacheSweepError(ValueError):
    """The cache cannot be admitted."""


PUBLIC_SUFFIXES = (".json", ".md", ".txt", ".yaml", ".yml", ".csv")


def _walk(root: str, suffixes: tuple[str, ...] = PUBLIC_SUFFIXES) -> list[str]:
    out = []
    for dirpath, _, files in os.walk(root):
        for name in sorted(files):
            if name.endswith(suffixes):
                out.append(os.path.join(dirpath, name))
    return sorted(out)


def parse_all_json(root: str) -> tuple[dict[str, Any], list[str]]:
    """Parse EVERY json file under root. Returns (parsed, failures).

    A file that will not parse is a failure, never a skip.
    """
    parsed: dict[str, Any] = {}
    failures: list[str] = []
    for path in _walk(root, (".json",)):
        rel = os.path.relpath(path, root)
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = fh.read()
        except OSError as exc:
            failures.append(f"{rel}: unreadable ({exc.__class__.__name__})")
            continue
        try:
            parsed[rel] = json.loads(raw)
        except json.JSONDecodeError as exc:
            hint = ""
            if QUOTED_ETAG_RE.search(raw):
                hint = (" — an UNESCAPED QUOTED ETag: the server sends ETag: \"abc\", and "
                        "writing it raw produces \"etag\": \"\"abc\"\", which is not JSON")
            failures.append(
                f"{rel}: not JSON at line {exc.lineno} col {exc.colno} ({exc.msg}){hint}")
    return parsed, failures


def check_every_json_parses(rep: Report, root: str) -> dict[str, Any]:
    """A verifier that skips what it cannot read cannot find anything."""
    parsed, failures = parse_all_json(root)

    rep.check(
        "EVERY json artifact in the cache parses (an unparseable file is a named refusal, "
        "never a skip — 'every file I could read was fine' is not a statement about the "
        "cache)",
        not failures, "; ".join(failures[:3]))

    rep.check("the cache contains at least one json artifact to verify",
              bool(parsed) or bool(failures), f"no json under {root}")
    return parsed


def leaks_in(obj: Any, path: str = "$") -> list[str]:
    """Machine-local paths at ANY depth, JSON-path'd so the leak can be found."""
    hits: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            hits += leaks_in(value, f"{path}.{key}")
    elif isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            hits += leaks_in(item, f"{path}[{i}]")
    elif isinstance(obj, str) and LOCAL_PATH_RE.search(obj):
        hits.append(f"{path} = {obj[:60]!r}")
    return hits


def tokens_in(obj: Any, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            hits += tokens_in(value, f"{path}.{key}")
    elif isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            hits += tokens_in(item, f"{path}[{i}]")
    elif isinstance(obj, str):
        for pattern, label in TOKEN_PATTERNS:
            if pattern.search(obj):
                hits.append(f"{path}: {label}")
                break
    return hits


def check_no_machine_paths(rep: Report, parsed: dict[str, Any]) -> None:
    """A published artifact may not name the machine it was built on."""
    leaks: list[str] = []
    for rel, doc in sorted(parsed.items()):
        for hit in leaks_in(doc):
            leaks.append(f"{rel}{hit[1:]}")

    rep.check(
        "no public cache artifact leaks a machine-local path (a /home/... path names the "
        "machine, the user and the layout, and a consumer cannot resolve a path that only "
        "existed on the producer's disk)",
        not leaks, "; ".join(leaks[:3]))


def check_no_tokens(rep: Report, parsed: dict[str, Any]) -> None:
    """A cache is exactly the by-product nobody re-reads before publishing."""
    hits: list[str] = []
    for rel, doc in sorted(parsed.items()):
        for hit in tokens_in(doc):
            hits.append(f"{rel}{hit[1:]}")

    rep.check("no public cache artifact carries a token, key or authorization header",
              not hits, "; ".join(hits[:3]))


def check_etags_are_stored_safely(rep: Report, parsed: dict[str, Any]) -> None:
    """The bug that quarantined the cache, refused at the source."""
    bad = []
    for rel, doc in sorted(parsed.items()):
        for hit in _etag_hits(doc):
            bad.append(f"{rel}{hit[1:]}")
    rep.check(
        "every recorded ETag is stored as a clean string (servers send it QUOTED; writing "
        "the raw value into JSON is what produced the malformed provenance files)",
        not bad, "; ".join(bad[:3]))


def _etag_hits(obj: Any, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key.lower() == "etag" and isinstance(value, str):
                if value.startswith('"') or value.endswith('"') or '\\"' in value:
                    hits.append(f"{path}.{key} = {value[:40]!r}")
            hits += _etag_hits(value, f"{path}.{key}")
    elif isinstance(obj, (list, tuple)):
        for i, item in enumerate(obj):
            hits += _etag_hits(item, f"{path}[{i}]")
    return hits


def sweep(rep: Report, root: str) -> Optional[dict[str, Any]]:
    """The full cache sweep. Runs BEFORE any content check — an unparseable or leaking
    cache is refused before its contents are even considered."""
    if not os.path.isdir(root):
        rep.check(f"the cache root exists ({root})", False, "not a directory")
        return None

    parsed = check_every_json_parses(rep, root)
    check_no_machine_paths(rep, parsed)
    check_no_tokens(rep, parsed)
    check_etags_are_stored_safely(rep, parsed)
    return parsed


def check_no_machine_paths_in_ANY_public_text(rep: Report, root: str) -> None:
    """Not just JSON. A committed HANDOFF.md leaked `/home/tcelab/.cache/...` and my
    JSON-only sweep sailed straight past it.

    The leak does not care what extension it is written under, so neither does the scan.
    """
    leaks = []
    for path in _walk(root):
        rel = os.path.relpath(path, root)
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh, 1):
                    if LOCAL_PATH_RE.search(line):
                        leaks.append(f"{rel}:{i}")
                        break
        except OSError:
            continue
    rep.check(
        "no PUBLIC text artifact of any type (.json/.md/.txt/...) leaks a machine-local "
        "path — a JSON-only scan misses a committed HANDOFF.md, and the leak does not care "
        "what extension it was written under",
        not leaks, "; ".join(leaks[:4]))
