"""Canonical JSON + SHA-256 helpers — byte-identical to the three consumers.

These reproduce, exactly:
  * Direct  `analysis/direct/hashing.py`  `canonical_json` / `content_hash` / `file_sha256`
  * Direct  `analysis/direct/trust.py`    `canonical_content_sha256` (self-hash-field strip)
  * the browser `programs.html` `canonicalJSON` / `sha256hex`

Any drift here silently breaks the registry binding, so this module is deliberately
tiny and has a dedicated equality test against known-frozen values.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

# Direct trust.py SELF_HASH_FIELDS — a document never attests to itself, so these
# field names are stripped (recursively) before the canonical content hash.
SELF_HASH_FIELDS = ("registry_sha256", "self_sha256", "sha256")


def canonical_json(obj: Any) -> str:
    """json.dumps(obj, sort_keys=True, separators=(",",":"), ensure_ascii=True, allow_nan=False)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def sha256_hex(data: "bytes | str") -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def content_hash(obj: Any) -> str:
    """SHA-256 of the canonical JSON form of ``obj`` (Direct hashing.content_hash)."""
    return sha256_hex(canonical_json(obj))


def file_sha256(path: str) -> str:
    """Raw byte SHA-256 of a file (Direct hashing.file_sha256)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _strip_self_hash(v: Any) -> Any:
    """Direct trust.canonical_content_sha256_payload — recursive self-hash strip."""
    if isinstance(v, dict):
        return {k: _strip_self_hash(x) for k, x in v.items() if k not in SELF_HASH_FIELDS}
    if isinstance(v, list):
        return [_strip_self_hash(x) for x in v]
    return v


def canonical_content_sha256(doc: Any) -> str:
    """Direct trust.canonical_content_sha256 — strip self-hash fields, then content_hash.

    This is the value Direct's ``_verify_artifact`` independently derives for a JSON
    artifact and the value ``bind_release`` binds ``hashes.registry_sha256`` to.
    """
    if isinstance(doc, dict):
        stripped = {k: _strip_self_hash(v) for k, v in doc.items() if k not in SELF_HASH_FIELDS}
        return content_hash(stripped)
    return content_hash(doc)


def dumps_indent1(obj: Any) -> str:
    """Serialize a served JSON artifact the way the Stage-1 generators do:
    indent=1, ensure_ascii=True, sort_keys=False, no trailing newline. The *raw*
    sha256 of this string is what the frontend and the release manifest pin."""
    return json.dumps(obj, indent=1, ensure_ascii=True, sort_keys=False)
