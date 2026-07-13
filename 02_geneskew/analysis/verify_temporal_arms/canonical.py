"""The verifier's OWN canonical form. Re-implemented, never imported.

A verifier that hashed with the producer's serialiser could not catch a producer whose
serialiser was wrong: the two would agree on a broken canonical form and both call it
correct. So the canonical bytes are re-derived here, from the written-down contract:

    sorted keys, compact separators, ASCII-escaped, NaN and infinity REFUSED

and the content address of a document is the sha256 of exactly those bytes. The two
implementations agreeing is then a real, independent measurement, and
``test_the_two_canonical_forms_agree`` is what makes it one.

``canonical_num`` is the scientific value as EMITTED: full float64, never display-rounded
— a value rounded before it is ranked turns two distinct scores into an emitted tie, and
the emitted tie-break then disagrees with the rank that was actually assigned.
Non-finite values are not measurements and become null.
"""
from __future__ import annotations

import hashlib
import json
import math
from typing import Any


def canonical_json(obj: Any) -> str:
    """Sorted keys, compact separators, ASCII. NaN/inf are REFUSED, never emitted."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def content_hash(obj: Any) -> str:
    """The sha256 of the canonical form of the PARSED content. 'Is this the same claim?'"""
    return sha256_hex(canonical_json(obj))


def file_sha256(path: str, chunk: int = 1 << 20) -> str:
    """The sha256 of the bytes ON DISK. 'Are these the bytes that were admitted?'"""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def canonical_num(x: Any) -> Any:
    """The canonical scientific value: full float64; non-finite -> null."""
    if x is None:
        return None
    if isinstance(x, bool):
        return None
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(xf) or math.isinf(xf):
        return None
    return xf
