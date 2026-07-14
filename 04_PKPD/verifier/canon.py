"""Independent canonicalisation. Deliberately NOT analysis.canonical.

The verifier reimplements content addressing and the published transforms from the
written contract, so that a bug — or a tamper — in the generator cannot validate itself.
If the two implementations ever disagree, the verifier fails. That is the point.

Nothing in `verifier/` may import `analysis/`.
"""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any, Mapping, Sequence


class VerifierCanonError(TypeError):
    pass


def _check(node: Any, path: str = "$") -> None:
    if isinstance(node, float):
        raise VerifierCanonError(f"float in identity content at {path}")
    if isinstance(node, Mapping):
        for k, v in node.items():
            _check(v, f"{path}.{k}")
    elif isinstance(node, (list, tuple)):
        for i, v in enumerate(node):
            _check(v, f"{path}[{i}]")


def cjson_strict(obj: Any) -> str:
    _check(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)


NON_CANONICAL_KEYS = {
    "created_at", "generated_at", "run_started_utc", "run_finished_utc",
    "display_label", "display_text", "local_cache_path", "cache_path", "output_dir",
    "host", "notes",
}


def _strip(obj: Any) -> Any:
    """The float-tolerant path the generator uses for table/document content hashes."""
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if k not in NON_CANONICAL_KEYS}
    if isinstance(obj, (list, tuple)):
        return [_strip(v) for v in obj]
    if isinstance(obj, float):
        r = round(float(obj), 10)
        return 0.0 if r == 0 else r
    return obj


def cjson(obj: Any) -> str:
    return json.dumps(_strip(obj), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def chash(obj: Any) -> str:
    return sha256_hex(cjson(obj))


def chash_strict(obj: Any) -> str:
    return sha256_hex(cjson_strict(obj))


def file_sha256(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


# --------------------------------------------------------------------------- quantities
# Reimplemented from the written unit contract, not imported.

_UNITS: dict[str, tuple[str, Decimal]] = {
    "pM": ("molar", Decimal("0.001")), "nM": ("molar", Decimal(1)),
    "uM": ("molar", Decimal(1000)), "µM": ("molar", Decimal(1000)),
    "mM": ("molar", Decimal(1_000_000)), "M": ("molar", Decimal(1_000_000_000)),
    "ng/mL": ("mass_per_volume", Decimal(1)), "ug/mL": ("mass_per_volume", Decimal(1000)),
    "µg/mL": ("mass_per_volume", Decimal(1000)), "mg/L": ("mass_per_volume", Decimal(1000)),
    "mg/mL": ("mass_per_volume", Decimal(1_000_000)), "ug/L": ("mass_per_volume", Decimal(1)),
    "µg/L": ("mass_per_volume", Decimal(1)), "g/L": ("mass_per_volume", Decimal(1_000_000)),
    "ng/g": ("mass_per_mass", Decimal(1)), "ug/g": ("mass_per_mass", Decimal(1000)),
    "µg/g": ("mass_per_mass", Decimal(1000)),
    "g/mol": ("molar_mass", Decimal(1)), "g_per_mol": ("molar_mass", Decimal(1)),
    "Da": ("molar_mass", Decimal(1)), "kg/mol": ("molar_mass", Decimal(1000)),
    "kg_per_mol": ("molar_mass", Decimal(1000)), "kDa": ("molar_mass", Decimal(1000)),
    "A^2": ("polar_surface_area", Decimal(1)),
    "angstrom_squared": ("polar_surface_area", Decimal(1)),
    "nm^2": ("polar_surface_area", Decimal(100)),
    "log10": ("log10", Decimal(1)), "dimensionless_log10": ("log10", Decimal(1)),
    "count": ("count", Decimal(1)), "pka": ("pka", Decimal(1)),
    "pka_units": ("pka", Decimal(1)), "ratio": ("ratio", Decimal(1)),
}


def dimension(unit: str) -> str:
    if unit not in _UNITS:
        raise VerifierCanonError(f"unsupported unit {unit!r}")
    return _UNITS[unit][0]


def to_base(value_source_string: str, unit: str) -> Decimal:
    if unit not in _UNITS:
        raise VerifierCanonError(f"unsupported unit {unit!r}")
    try:
        d = Decimal(str(value_source_string).strip())
    except InvalidOperation as exc:
        raise VerifierCanonError(f"not a decimal: {value_source_string!r}") from exc
    return d * _UNITS[unit][1]


def canonical_decimal(value_source_string: str) -> str:
    return format(Decimal(str(value_source_string).strip()).normalize(), "E")


def ratio_decimal(num: Decimal, den: Decimal, precision: int = 12) -> str:
    with localcontext() as ctx:
        ctx.prec = precision + 6
        q = (num / den).quantize(Decimal(1).scaleb(-precision))
    return format(q.normalize(), "E")


# ------------------------------------------------------- published CNS-MPO transforms
# Wager 2010 Table 1, reimplemented from the paper, not imported from the scorer.

def monotonic_decreasing(x: float, x1: float, x2: float) -> float:
    if x <= x1:
        return 1.0
    if x >= x2:
        return 0.0
    return (x2 - x) / (x2 - x1)


def hump(x: float, x1: float, x2: float, x3: float, x4: float) -> float:
    if x <= x1 or x >= x4:
        return 0.0
    if x < x2:
        return (x - x1) / (x2 - x1)
    if x <= x3:
        return 1.0
    return (x4 - x) / (x4 - x3)


def desirability(spec: dict[str, Any], value: float) -> float:
    ip = spec["inflection_points"]
    if spec["transform"] == "monotonic_decreasing":
        t0 = monotonic_decreasing(value, ip["x1"], ip["x2"])
    elif spec["transform"] == "hump":
        t0 = hump(value, ip["x1"], ip["x2"], ip["x3"], ip["x4"])
    else:
        raise VerifierCanonError(f"unknown transform {spec['transform']!r}")
    return min(1.0, max(0.0, t0))


def round_half_up(x: float, decimals: int) -> float:
    from decimal import ROUND_HALF_UP

    q = Decimal(1).scaleb(-decimals)
    return float(Decimal(repr(float(x))).quantize(q, rounding=ROUND_HALF_UP))


def row_key(row: Mapping[str, Any], keys: Sequence[str]) -> tuple:
    return tuple("" if row.get(k) is None else str(row[k]) for k in keys)
