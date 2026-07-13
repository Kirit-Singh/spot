"""The shared re-derivations: Stage-2's content-hash rule, and how a gate is recorded.

Two modules re-read the release (:mod:`verifier.v2_reconstruct`, :mod:`verifier.v2_bundles`) and
both need these. They live here so neither imports the other.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from . import canon
from .report import Report

SELF_HASH_EXCLUDED = ("created_at", "manifest_sha256", "path")


def _gate(rep: Report, gate: str, sentence: str, ok: Any, detail: str = "") -> bool:
    return rep.check(f"[{gate}] {sentence}", ok, detail)


def stage2_content_sha256(obj: Any) -> str:
    """Stage-2's content hash: keys SORTED, array order PRESERVED, no NaN.

    RESTATED from Stage-2's written spec, never imported: a verifier that borrows the producer's
    hasher cannot disagree with it.
    """
    return canon.sha256_hex(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                       ensure_ascii=True, allow_nan=False))


def manifest_self_hash(manifest: dict[str, Any]) -> str:
    """The producer's SEMANTIC self-hash, re-derived from the manifest's own content."""
    return stage2_content_sha256(
        {k: v for k, v in manifest.items() if k not in SELF_HASH_EXCLUDED})


def _load_json(rep: Report, path: str, what: str, gate: str) -> Optional[tuple[Any, str]]:
    if not path or not os.path.isfile(path):
        _gate(rep, gate, f"the {what} is on disk (there is no fixture fallback)", False,
              f"not found: {path!r}")
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError) as exc:
        _gate(rep, gate, f"the {what} is readable JSON", False, str(exc))
        return None
    return doc, canon.file_sha256(path)
