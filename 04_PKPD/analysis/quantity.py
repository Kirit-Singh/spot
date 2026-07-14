"""Exact scientific magnitudes: a source string, a unit, and a canonical decimal.

Two failures this module exists to prevent, both found by the post-build audit:

  * A universal 10-decimal float grid collapsed 1e-12 and 4e-11 to the same identity.
    Concentrations differing by 40x hashed alike. So a magnitude is never a float in
    canonical content: it is an exact ``Decimal`` string, the way the source printed it.
  * ``MW = 0.6 kg_per_mol`` was read as 0.6 g/mol and scored a perfect 1.0. So units are
    a closed registry per physical dimension, with explicit declared conversions; an
    unrecognised or dimensionally-wrong unit is a rejection, never a reinterpretation.

This mirrors Stage 3's rule (``druglink/hashing.py``: "Floats are not canonicalisable"),
which keeps the two stages' content addressing compatible.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from typing import Optional


class UnitError(ValueError):
    """The unit is unknown, or wrong for this quantity's dimension."""


class QuantityError(ValueError):
    """The value cannot be represented as an exact decimal."""


# dimension -> base unit
BASE_UNIT = {
    "molar": "nM",
    "mass_per_volume": "ng/mL",
    "mass_per_mass": "ng/g",
    "molar_mass": "g/mol",
    "polar_surface_area": "A^2",
    "log10": "log10",
    "count": "count",
    "pka": "pka",
    "ratio": "ratio",
}

# unit token -> (dimension, exact multiplier to the base unit)
UNIT_REGISTRY: dict[str, tuple[str, Decimal]] = {
    # amount concentration
    "pM": ("molar", Decimal("0.001")),
    "nM": ("molar", Decimal(1)),
    "uM": ("molar", Decimal(1000)),
    "µM": ("molar", Decimal(1000)),
    "mM": ("molar", Decimal(1_000_000)),
    "M": ("molar", Decimal(1_000_000_000)),
    # mass concentration
    "ng/mL": ("mass_per_volume", Decimal(1)),
    "ug/mL": ("mass_per_volume", Decimal(1000)),
    "µg/mL": ("mass_per_volume", Decimal(1000)),
    "mg/L": ("mass_per_volume", Decimal(1000)),
    "mg/mL": ("mass_per_volume", Decimal(1_000_000)),
    "ug/L": ("mass_per_volume", Decimal(1)),
    "µg/L": ("mass_per_volume", Decimal(1)),
    "g/L": ("mass_per_volume", Decimal(1_000_000)),
    # tissue mass/mass
    "ng/g": ("mass_per_mass", Decimal(1)),
    "ug/g": ("mass_per_mass", Decimal(1000)),
    "µg/g": ("mass_per_mass", Decimal(1000)),
    # molar mass — kg/mol is a REAL unit and converts explicitly; it is never read as g/mol
    "g/mol": ("molar_mass", Decimal(1)),
    "g_per_mol": ("molar_mass", Decimal(1)),
    "Da": ("molar_mass", Decimal(1)),
    "kg/mol": ("molar_mass", Decimal(1000)),
    "kg_per_mol": ("molar_mass", Decimal(1000)),
    "kDa": ("molar_mass", Decimal(1000)),
    # topological polar surface area
    "A^2": ("polar_surface_area", Decimal(1)),
    "angstrom_squared": ("polar_surface_area", Decimal(1)),
    "nm^2": ("polar_surface_area", Decimal(100)),
    # dimensionless
    "log10": ("log10", Decimal(1)),
    "dimensionless_log10": ("log10", Decimal(1)),
    "count": ("count", Decimal(1)),
    "pka": ("pka", Decimal(1)),
    "pka_units": ("pka", Decimal(1)),
    "ratio": ("ratio", Decimal(1)),
}


def canonical_decimal(value_source_string: str) -> str:
    """Exact decimal string. ``1e-12`` and ``4e-11`` never normalise to the same text."""
    if isinstance(value_source_string, float):
        raise QuantityError(
            "refusing a float: pass the exact source string, so that two distinct "
            f"magnitudes can never share an identity (got {value_source_string!r})"
        )
    try:
        d = Decimal(str(value_source_string).strip())
    except (InvalidOperation, ValueError) as exc:
        raise QuantityError(f"not a decimal: {value_source_string!r}") from exc
    if not d.is_finite():
        raise QuantityError(f"non-finite magnitude: {value_source_string!r}")
    return format(d.normalize(), "E")


@dataclass(frozen=True)
class Quantity:
    """One magnitude, exactly as sourced, plus its canonical form."""

    value_source_string: str
    unit: str
    canonical_decimal: str
    dimension: str

    @classmethod
    def parse(cls, value_source_string: str, unit: str,
              expected_dimension: Optional[str] = None) -> "Quantity":
        if unit not in UNIT_REGISTRY:
            raise UnitError(
                f"unsupported unit {unit!r}. Stage 4 will not guess at a unit it does not "
                f"know; supported: {', '.join(sorted(UNIT_REGISTRY))}"
            )
        dimension, _factor = UNIT_REGISTRY[unit]
        if expected_dimension and dimension != expected_dimension:
            raise UnitError(
                f"unit {unit!r} is {dimension!r}, but a {expected_dimension!r} quantity was "
                "expected. Stage 4 rejects a dimensionally incompatible unit rather than "
                "reinterpreting it."
            )
        return cls(
            value_source_string=str(value_source_string).strip(),
            unit=unit,
            canonical_decimal=canonical_decimal(value_source_string),
            dimension=dimension,
        )

    @property
    def decimal(self) -> Decimal:
        return Decimal(self.canonical_decimal)

    def in_base(self) -> Decimal:
        """Exact value in this dimension's base unit."""
        _dim, factor = UNIT_REGISTRY[self.unit]
        return self.decimal * factor

    def base_unit(self) -> str:
        return BASE_UNIT[self.dimension]

    def as_float(self) -> float:
        """For the published CNS-MPO piecewise functions, which are defined on reals.

        Identity is never taken from this value — only from ``canonical_decimal``.
        """
        return float(self.decimal)

    def content(self) -> dict[str, str]:
        """What goes into canonical content and the artifact tables."""
        return {
            "value_source_string": self.value_source_string,
            "value_canonical_decimal": self.canonical_decimal,
            "unit": self.unit,
            "dimension": self.dimension,
        }

    def conversion_transform(self) -> str:
        _dim, factor = UNIT_REGISTRY[self.unit]
        return (
            f"{self.value_source_string} {self.unit} x {factor} = "
            f"{self.in_base()} {self.base_unit()}"
        )


def ratio(numerator: Quantity, denominator: Quantity, precision: int = 12) -> tuple[str, float]:
    """Exact-as-possible ratio of two same-dimension quantities.

    -> (canonical decimal string, float for display). Division can be non-terminating,
    so the precision is declared rather than implied.
    """
    if numerator.dimension != denominator.dimension:
        raise UnitError(
            f"cannot divide {numerator.dimension!r} by {denominator.dimension!r}"
        )
    den = denominator.in_base()
    if den == 0:
        raise QuantityError("denominator is zero")
    with localcontext() as ctx:
        ctx.prec = precision + 6
        q = numerator.in_base() / den
        q = q.quantize(Decimal(1).scaleb(-precision))
    return format(q.normalize(), "E"), float(q)


# The unit each CNS-MPO input must be expressed in (dimension-checked, not name-checked).
CNS_MPO_DIMENSIONS: dict[str, str] = {
    "clogp": "log10",
    "clogd_74": "log10",
    "mw": "molar_mass",
    "tpsa": "polar_surface_area",
    "hbd": "count",
    "pka_most_basic": "pka",
}


def validate_domain(property_id: str, q: Quantity) -> None:
    """Physical domain checks. A negative MW is not a low score; it is a bad record."""
    v = q.in_base()
    if property_id == "mw" and v <= 0:
        raise QuantityError(f"MW must be positive (got {v} {q.base_unit()})")
    if property_id == "tpsa" and v < 0:
        raise QuantityError(f"TPSA must be non-negative (got {v} {q.base_unit()})")
    if property_id == "hbd":
        if v < 0:
            raise QuantityError(f"HBD must be non-negative (got {v})")
        if v != v.to_integral_value():
            raise QuantityError(f"HBD is a count of donors and must be an integer (got {v})")
