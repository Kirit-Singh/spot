"""Independent canonicalisation. Deliberately NOT druglink.hashing.

The verifier reimplements content addressing from the written contract so that a
bug (or a tampering) in the generator's hashing cannot validate itself. If these
two implementations ever disagree, the verifier fails -- which is the point.
"""
from __future__ import annotations

import hashlib
import json
import os
from decimal import Decimal
from typing import Any, Iterable, Mapping, Sequence


class VerifierCanonError(TypeError):
    pass


def _check(node: Any, path: str = "$") -> None:
    if isinstance(node, float):
        raise VerifierCanonError(f"float in canonical content at {path}")
    if isinstance(node, Mapping):
        for k, v in node.items():
            _check(v, f"{path}.{k}")
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            _check(v, f"{path}[{i}]")


def cjson(obj: Any) -> str:
    _check(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def chash(obj: Any) -> str:
    return sha256_hex(cjson(obj))


def short(obj: Any, n: int = 16) -> str:
    return chash(obj)[:n]


def decimal_str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        raise VerifierCanonError("float value in a potency row")
    return format(Decimal(str(value).strip()).normalize(), "E")


def table_hash(rows: Iterable[Mapping[str, Any]], sort_keys: Sequence[str]) -> str:
    rows = [dict(r) for r in rows]
    for r in rows:
        _check(r)

    def key(row: Mapping[str, Any]):
        out: list = []
        for k in sort_keys:
            v = row.get(k)
            out.append((0, "") if v is None else (1, cjson(v)))
        out.append((1, cjson(row)))
        return out

    return sha256_hex(cjson(sorted(rows, key=key)))


def file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def tree_hash(root: str, suffixes: tuple[str, ...]) -> str:
    files: list[dict[str, str]] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for name in sorted(filenames):
            if name.endswith(suffixes):
                full = os.path.join(dirpath, name)
                files.append({"path": os.path.relpath(full, root).replace(os.sep, "/"),
                              "sha256": file_sha256(full)})
    files.sort(key=lambda f: f["path"])
    return chash(files)


def without(mapping: Mapping[str, Any], keys: Iterable[str]) -> dict[str, Any]:
    drop = set(keys)
    return {k: v for k, v in mapping.items() if k not in drop}
