"""Content addressing for Stage 3.

Two rules the previous build got wrong, and the reason for each:

1. **Floats are not canonicalisable.** A unit-agnostic rounding rule silently
   collapses 4.0e-7 M and 4.9e-7 M. ``canonical_json`` therefore REJECTS float
   values outright. Every scientific magnitude is carried as an exact source
   string plus a canonical decimal string (:func:`canonical_decimal`), so the
   two potencies above can never hash alike.

2. **Nothing is dropped implicitly.** The old ``canonicalize`` silently deleted
   keys by name, which meant a payload key called ``preferred_name`` vanished
   from an integrity hash. Content dicts are now built explicitly by their
   owners; the only stripping helper is :func:`without`, which the caller must
   name.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence

from .canonical_number import CanonicalNumberError, canonical_number

LOCAL_PATH_RE = re.compile(
    r"(^|[\s\"'=(])(/home/|/Users/|/mnt/|/media/|/root/|/tmp/|/var/folders/"
    r"|/private/var/|[A-Za-z]:\\)")


class CanonicalizationError(TypeError):
    """A value cannot be canonically serialised (floats, NaN, unknown types)."""


def canonical_decimal(value: Any) -> str:
    """Exact decimal string. 4.0e-7 and 4.9e-7 are distinct; 4.0e-7 == 0.00000040.

    Delegates to :mod:`druglink.canonical_number` — there is exactly ONE canonical
    numeric representation in Stage 3, and this is a thin alias onto it.

    A raw float is still refused HERE, deliberately: a caller reaching this function is
    canonicalising a value it already holds as a string, and silently accepting a float
    would let a magnitude enter a hash without its exact source string being kept
    alongside. Callers that legitimately hold a number use ``canonical_number`` directly.
    """
    if value is None:
        return ""
    if isinstance(value, float):
        raise CanonicalizationError(
            "refusing to canonicalise a float; pass the exact source string, or use "
            f"druglink.canonical_number.canonical_number() (got {value!r})")
    try:
        return canonical_number(value)
    except CanonicalNumberError as exc:
        raise CanonicalizationError(str(exc)) from exc


def _reject_floats(node: Any, path: str = "$") -> None:
    if isinstance(node, float):
        raise CanonicalizationError(
            f"float at {path}: Stage-3 canonical content carries exact decimal "
            "strings, never floats")
    if isinstance(node, Mapping):
        for k, v in node.items():
            _reject_floats(v, f"{path}.{k}")
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            _reject_floats(v, f"{path}[{i}]")
    elif not isinstance(node, (str, int, bool, type(None), Decimal)):
        raise CanonicalizationError(f"uncanonicalisable type at {path}: {type(node)}")


def _plain(node: Any) -> Any:
    if isinstance(node, Decimal):
        return format(node.normalize(), "E")
    if isinstance(node, Mapping):
        return {k: _plain(v) for k, v in node.items()}
    if isinstance(node, (list, tuple)):
        return [_plain(v) for v in node]
    return node


def canonical_json(obj: Any) -> str:
    _reject_floats(obj)
    return json.dumps(_plain(obj), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def content_hash(obj: Any) -> str:
    return sha256_hex(canonical_json(obj))


def short_id(obj: Any, n: int = 16) -> str:
    return content_hash(obj)[:n]


def without(mapping: Mapping[str, Any], keys: Iterable[str]) -> dict[str, Any]:
    """Explicitly named exclusion (timestamps, self-hash fields)."""
    drop = set(keys)
    return {k: v for k, v in mapping.items() if k not in drop}


def row_key(row: Mapping[str, Any], keys: Sequence[str]) -> list:
    """Total order in which missing sorts distinctly from any present value."""
    out: list = []
    for k in keys:
        v = row.get(k)
        out.append((0, "") if v is None else (1, canonical_json(v)))
    out.append((1, canonical_json(row)))
    return out


def table_hash(rows: Iterable[Mapping[str, Any]], sort_keys: Sequence[str]) -> str:
    """Row-order-invariant hash over the exact emitted cell values."""
    rows = [dict(r) for r in rows]
    for r in rows:
        _reject_floats(r)
    return sha256_hex(canonical_json(sorted(rows, key=lambda r: row_key(r, sort_keys))))


def file_sha256(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def tree_hash(root: str, suffixes: tuple[str, ...]) -> dict[str, Any]:
    """{tree_sha256, files: [{path, sha256}]} over a source/schema tree."""
    files: list[dict[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for name in sorted(filenames):
            if name.endswith(suffixes):
                full = os.path.join(dirpath, name)
                files.append({"path": os.path.relpath(full, root).replace(os.sep, "/"),
                              "sha256": file_sha256(full)})
    files.sort(key=lambda f: f["path"])
    return {"tree_sha256": content_hash(files), "files": files}


def contains_local_path(obj: Any) -> list[str]:
    hits: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, Mapping):
            for v in node.values():
                walk(v)
        elif isinstance(node, (list, tuple)):
            for v in node:
                walk(v)
        elif isinstance(node, str) and LOCAL_PATH_RE.search(node):
            hits.append(node)

    walk(obj)
    return hits
