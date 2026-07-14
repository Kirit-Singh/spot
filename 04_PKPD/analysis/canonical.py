"""Canonical serialization + hashing for Stage 4.

Every Stage-4 hash is taken over *canonical content*: stable key order, stable row
order, exact decimal magnitudes, and NO timestamps / display-only labels / machine-local
paths. This is the repo-wide rule (schemas/README.md §11) and it is what makes a rerun
reproduce the same identifiers on a different machine at a different time.

**Scientific magnitudes are never floats here.** The previous build rounded every float
to a universal 10-decimal grid before hashing, which gave `1e-12` and `4e-11` the same
identity. `strict_canonical_json` therefore REJECTS floats outright: a magnitude enters
canonical content as an exact decimal string (see `quantity.py`). This is the same rule
Stage 3 adopted (`druglink/hashing.py`), so the two stages address content compatibly.

`canonical_json` (float-tolerant) remains for non-identity uses — display payloads and
derived lanes that are reconstructed and compared numerically, not hashed for identity.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

# Only used by the float-tolerant path. Identity content must not contain floats at all.
FLOAT_HASH_DECIMALS = 10

# Keys excluded from canonical content wherever they appear: they are display-only,
# machine-local, or wall-clock, and none of them is a scientific claim.
NON_CANONICAL_KEYS = frozenset(
    {
        "created_at",
        "generated_at",
        "run_started_utc",
        "run_finished_utc",
        "display_label",
        "display_text",
        "local_cache_path",
        "cache_path",
        "output_dir",
        "host",
        "notes",
    }
)

# A machine-local path is not content: it does not exist on the reviewer's machine and
# cannot be re-verified. Same guard as Stage 3's LOCAL_PATH_RE.
LOCAL_PATH_RE = re.compile(
    r"(^|[\s\"'=(])(/home/|/Users/|/mnt/|/media/|/root/|/tmp/|/var/folders/"
    r"|/private/var/|[A-Za-z]:\\)"
)


class CanonicalizationError(ValueError):
    """A value cannot be represented in canonical content."""


def canonical_float(x: float) -> float:
    """Round a float for the float-tolerant path. NaN/Inf are never hashable content."""
    if not isinstance(x, (int, float)) or isinstance(x, bool):
        raise CanonicalizationError(f"not a number: {x!r}")
    v = float(x)
    if math.isnan(v) or math.isinf(v):
        raise CanonicalizationError(f"non-finite value cannot be canonical content: {v!r}")
    r = round(v, FLOAT_HASH_DECIMALS)
    return 0.0 if r == 0 else r  # collapse -0.0


def round_half_up(x: float, decimals: int) -> float:
    """Publication rounding (ROUND_HALF_UP), not banker's rounding.

    A frozen implementation rule, not a rule Wager et al. published: their printed tables
    are consistent with it, but the paper does not name a rounding mode.
    """
    q = Decimal(1).scaleb(-decimals)
    return float(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))


def strip_non_canonical(obj: Any) -> Any:
    """Recursively drop NON_CANONICAL_KEYS and canonicalize floats (tolerant path)."""
    if isinstance(obj, dict):
        return {
            k: strip_non_canonical(v)
            for k, v in obj.items()
            if k not in NON_CANONICAL_KEYS
        }
    if isinstance(obj, (list, tuple)):
        return [strip_non_canonical(v) for v in obj]
    if isinstance(obj, bool) or obj is None or isinstance(obj, (str, int)):
        return obj
    if isinstance(obj, float):
        return canonical_float(obj)
    if isinstance(obj, Decimal):
        return format(obj.normalize(), "E")
    raise CanonicalizationError(f"unsupported type in canonical content: {type(obj).__name__}")


def canonical_json(obj: Any) -> str:
    """Deterministic JSON, float-tolerant. NOT for identity over scientific magnitudes."""
    return json.dumps(
        strip_non_canonical(obj),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def _reject_floats_and_paths(node: Any, path: str = "$") -> None:
    if isinstance(node, float):
        raise CanonicalizationError(
            f"float at {path}: identity content carries exact decimal strings, never floats "
            "(a universal rounding grid collapses distinct magnitudes)"
        )
    if isinstance(node, str) and LOCAL_PATH_RE.search(node):
        raise CanonicalizationError(
            f"machine-local path at {path}: {node!r}. A local path is not content — it "
            "cannot be re-verified on the reviewer's machine."
        )
    if isinstance(node, dict):
        for k, v in node.items():
            _reject_floats_and_paths(v, f"{path}.{k}")
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            _reject_floats_and_paths(v, f"{path}[{i}]")


def strict_canonical_json(obj: Any) -> str:
    """Identity serialization: no floats, no machine-local paths, no dropped keys.

    Nothing is stripped implicitly here — the caller builds the content object and owns
    exactly what it contains.
    """
    _reject_floats_and_paths(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)


def strict_content_sha256(obj: Any) -> str:
    """SHA-256 over strict identity content."""
    return hashlib.sha256(strict_canonical_json(obj).encode("utf-8")).hexdigest()


def content_sha256(obj: Any) -> str:
    """SHA-256 over float-tolerant canonical content (derived lanes, table rows)."""
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def short_id(hexdigest: str, n: int = 16) -> str:
    """Repo convention (schemas/README.md): identifiers are the first 16 hex chars."""
    return hexdigest[:n]
