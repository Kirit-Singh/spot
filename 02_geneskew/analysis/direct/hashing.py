"""Canonical hashing utilities (shared artifact contract, plan §11).

Canonical hashes MUST: use stable key ordering, define float
rounding/tolerance, exclude timestamps / display-only labels / machine-local
paths. Callers are responsible for stripping non-canonical fields before
hashing; these helpers only guarantee deterministic serialisation.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any

# Frozen float rounding for every emitted / hashed scientific number.
FLOAT_DECIMALS = 6


def round_float(x: Any) -> Any:
    """Round a float to the frozen tolerance; pass through None/NaN as None."""
    if x is None:
        return None
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return x
    if math.isnan(xf):
        return None
    if math.isinf(xf):
        return None
    return round(xf, FLOAT_DECIMALS)


def canonical_json(obj: Any) -> str:
    """Serialise with sorted keys and compact separators (stable ordering)."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def content_hash(obj: Any) -> str:
    """SHA-256 of the canonical JSON form of ``obj``."""
    return sha256_hex(canonical_json(obj))


def file_sha256(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()
