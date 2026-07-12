"""CNS-MPO (Wager et al. 2010, v1) — the published desirability functions, exactly.

Six equally weighted properties, each transformed to T0 in [0,1]; the score is their
SUM, range 0-6. Monotonic-decreasing for ClogP, ClogD, MW, HBD, pKa; a hump for TPSA.
Inflection points come from method/cns_mpo_wager2010_v1.json, which is bound to the
published Table 1 — they are not literals in this file, so changing them changes the
method hash and the scorecard_set_id.

What this score is NOT (all four are enforced by the callers and by tests):
measured brain permeability, a probability, an NEBPI class, or a reason to impute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .canonical import round_half_up
from .properties import CNS_MPO_PROPERTIES, MissingInput, PropertySelection


def monotonic_decreasing(x: float, x1: float, x2: float) -> float:
    """1.0 at x <= x1, linear down to 0.0 at x >= x2 (Wager Figure 3A)."""
    if x2 <= x1:
        raise ValueError(f"invalid inflection points: x1={x1} x2={x2}")
    if x <= x1:
        return 1.0
    if x >= x2:
        return 0.0
    return (x2 - x) / (x2 - x1)


def hump(x: float, x1: float, x2: float, x3: float, x4: float) -> float:
    """0.0 at x <= x1, up to 1.0 on [x2, x3], back to 0.0 at x >= x4 (Figure 3B)."""
    if not (x1 < x2 <= x3 < x4):
        raise ValueError(f"invalid hump inflection points: {x1}, {x2}, {x3}, {x4}")
    if x <= x1 or x >= x4:
        return 0.0
    if x < x2:
        return (x - x1) / (x2 - x1)
    if x <= x3:
        return 1.0
    return (x4 - x) / (x4 - x3)


def desirability(property_id: str, value: float, method: dict[str, Any]) -> float:
    """Apply the published transform for one property."""
    spec = next(p for p in method["properties"] if p["property_id"] == property_id)
    ip = spec["inflection_points"]
    if spec["transform"] == "monotonic_decreasing":
        t0 = monotonic_decreasing(value, ip["x1"], ip["x2"])
    elif spec["transform"] == "hump":
        t0 = hump(value, ip["x1"], ip["x2"], ip["x3"], ip["x4"])
    else:
        raise ValueError(f"unknown transform {spec['transform']!r} for {property_id!r}")
    # The published functions are bounded [0,1] by construction; clamp defensively so
    # a future parameter edit can never leak a component outside the published range.
    return min(1.0, max(0.0, t0))


@dataclass
class CnsMpoResult:
    candidate_id: str
    active_moiety_id: str
    status: str  # "complete" | "incomplete"
    components: dict[str, Optional[float]]
    property_values: dict[str, Optional[float]]
    total_raw: Optional[float]
    total_published: Optional[float]
    missing_inputs: list[MissingInput]
    input_provenance: list[dict[str, Any]]
    method_id: str
    method_version: str
    interpretation_guard: str = (
        "CNS-MPO is a physicochemical design-space desirability score (Wager 2010). It is not "
        "measured brain permeability, not a probability of CNS exposure, and not an NEBPI class. "
        "It cannot satisfy any NEBPI Part-II branch."
    )
    warnings: list[str] = field(default_factory=list)


def score_cns_mpo(
    candidate_id: str,
    active_moiety_id: str,
    selection: PropertySelection,
    method: dict[str, Any],
) -> CnsMpoResult:
    """Score one candidate. Incomplete inputs -> status=incomplete, total=None.

    There is no partial total: summing five of six components would silently report a
    lower score for a compound whose sixth property is simply unknown.
    """
    components: dict[str, Optional[float]] = {p: None for p in CNS_MPO_PROPERTIES}
    values: dict[str, Optional[float]] = {p: None for p in CNS_MPO_PROPERTIES}
    provenance: list[dict[str, Any]] = []

    for prop, acc in selection.accepted.items():
        # The published functions are defined on the property's BASE unit: 0.6 kg/mol is
        # 600 g/mol, not 0.6. The conversion is explicit and declared, never a reading.
        base_value = acc.value_in_base_units
        values[prop] = base_value
        components[prop] = desirability(prop, base_value, method)
        # ONE ENTRY PER CONTRIBUTING ROW. A value corroborated by two agreeing sources has
        # two provenance entries, not a silently chosen one — every source the component
        # rests on is named.
        for c in acc.contributions:
            provenance.append(
                {
                    "property_record_id": c.property_record_id,
                    "property_id": prop,
                    "value_source_string": acc.quantity.value_source_string,
                    "value_canonical_decimal": acc.quantity.canonical_decimal,
                    "value_in_base_units": base_value,
                    "units": acc.units,
                    "base_units": acc.quantity.base_unit(),
                    "unit_conversion": acc.quantity.conversion_transform(),
                    "determination": c.determination,
                    "calculator_id": acc.calculator_id,
                    "method": c.method,
                    "software_version": c.software_version,
                    "database_version": c.database_version,
                    "method_conformance": acc.conformance,
                    "source_record_id": c.source_record_id,
                    "access_date": c.access_date,
                    "raw_response_sha256": c.raw_response_sha256,
                    "extraction_transform": c.extraction_transform,
                    "component_score_t0": components[prop],
                }
            )
    provenance.sort(key=lambda r: (r["property_id"], r["property_record_id"]))

    # One warning per (property, calculator), not per contributing row: two agreeing rows
    # from the same deviating calculator are one deviation, stated once.
    warnings = sorted(
        {
            f"{p['property_id']}: sourced from {p['calculator_id']!r}, which is a documented "
            "deviation from the calculator used in the published method"
            for p in provenance
            if p["method_conformance"] == "documented_deviation"
        }
    )

    if not selection.is_complete:
        return CnsMpoResult(
            candidate_id=candidate_id,
            active_moiety_id=active_moiety_id,
            status="incomplete",
            components=components,
            property_values=values,
            total_raw=None,
            total_published=None,
            missing_inputs=sorted(selection.missing, key=lambda m: m.property_id),
            input_provenance=provenance,
            method_id=method["method_id"],
            method_version=method["method_version"],
            warnings=warnings,
        )

    # selection.is_complete guarantees all six components are present.
    scored: list[float] = [float(t0) for t0 in (components[p] for p in CNS_MPO_PROPERTIES) if t0 is not None]
    total_raw = sum(scored)
    decimals = method["total"]["publication_rounding"]["decimals"]
    return CnsMpoResult(
        candidate_id=candidate_id,
        active_moiety_id=active_moiety_id,
        status="complete",
        components=components,
        property_values=values,
        total_raw=total_raw,
        total_published=round_half_up(total_raw, decimals),
        missing_inputs=[],
        input_provenance=provenance,
        method_id=method["method_id"],
        method_version=method["method_version"],
        warnings=warnings,
    )
