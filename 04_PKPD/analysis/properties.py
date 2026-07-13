"""Calculator policy for the six CNS-MPO inputs.

Wager et al. computed ClogP with BioByte and ClogD(7.4) and pKa with ACD/Labs. RDKit
implements neither a pH-dependent logD nor pKa at all, so an "RDKit ClogD" is not a
worse estimate — it is a fabricated quantity. This module makes that a mechanical
rejection rather than a matter of care.

Policy is data (method/calculator_policy_v1.json), so a change to it changes the
method hash and therefore the scorecard_set_id.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Any

from .canonical import strict_content_sha256
from .evidence_records import PropertyRecord
from .quantity import Quantity, QuantityError, UnitError

CNS_MPO_PROPERTIES = ("clogp", "clogd_74", "mw", "tpsa", "hbd", "pka_most_basic")

REDUCTION_POLICY_ID = "property_evidence_reduction_v1"


@dataclass(frozen=True)
class PropertyContribution:
    """One input row that stands behind an accepted property value.

    There may be more than one. The audit supplied two ClogP rows agreeing on calculator
    and value but citing different sources, `select_properties` took `usable[0]`, and one
    `scorecard_set_id` then carried two different provenance chains depending on list
    order. No row is chosen now: every agreeing row is kept, sorted by its content hash,
    and every one of them is emitted and appears in the provenance chain.
    """

    property_record_id: str
    determination: str
    method: str
    software_version: str | None
    database_version: str | None
    source_record_id: str
    # Optional for the same reason `Provenance.access_date` is: a reused upstream response
    # has no Stage-4 access date, and an invented one is a fabricated provenance claim.
    access_date: Optional[str]
    raw_response_sha256: str
    extraction_transform: str


@dataclass(frozen=True)
class AcceptedProperty:
    property_id: str
    quantity: Quantity          # exact decimal + declared unit, never a bare float
    calculator_id: str
    conformance: str
    # Every agreeing input row behind this value, in a stable order. Never one of them.
    contributions: tuple[PropertyContribution, ...]

    @property
    def value_in_base_units(self) -> float:
        """The value the published transform is evaluated on. 0.6 kg/mol is 600 g/mol."""
        return float(self.quantity.in_base())

    @property
    def units(self) -> str:
        return self.quantity.unit


@dataclass(frozen=True)
class MissingInput:
    property_id: str
    reason_code: str
    detail: str


@dataclass
class PropertySelection:
    accepted: dict[str, AcceptedProperty] = field(default_factory=dict)
    missing: list[MissingInput] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return len(self.accepted) == len(CNS_MPO_PROPERTIES) and not self.missing


def _policy_for(policy: dict[str, Any], property_id: str) -> dict[str, Any]:
    props = policy.get("properties", {})
    if property_id not in props:
        raise KeyError(f"calculator policy has no entry for property {property_id!r}")
    return props[property_id]


def check_calculator(policy: dict[str, Any], property_id: str, calculator_id: str,
                     record: PropertyRecord | None = None) -> tuple[bool, str, str]:
    """-> (allowed, conformance, reason).

    Forbidden beats unlisted: a forbidden tool gets the explicit "this tool does not
    implement this quantity" reason. And the policy's `requires` list is ENFORCED —
    the audit accepted a BioByte ClogP whose required software_version was null.
    """
    entry = _policy_for(policy, property_id)
    for f in entry.get("forbidden", []):
        if f["calculator_id"] == calculator_id or calculator_id.startswith(f["calculator_id"] + "_"):
            return False, "forbidden", f["reason"]
    for a in entry.get("allowed", []):
        if a["calculator_id"] != calculator_id:
            continue
        if record is not None:
            missing = [
                req for req in a.get("requires", [])
                if not (getattr(record, req, None)
                        or (req == "source_record_id" and record.provenance.source_record_id))
            ]
            if missing:
                return (
                    False,
                    "requirements_unmet",
                    f"calculator {calculator_id!r} requires {sorted(missing)} for {property_id!r}, "
                    "and the policy is not advisory: an unversioned calculator is an "
                    "unreproducible one",
                )
        return True, a["conformance"], ""
    return (
        False,
        "unlisted",
        f"calculator {calculator_id!r} is not an allowed source for {property_id!r}; "
        "allowed: " + ", ".join(a["calculator_id"] for a in entry.get("allowed", [])),
    )


def property_content(r: PropertyRecord) -> dict[str, Any]:
    """The whole row, flat. The unit of identity — nothing less is a duplicate."""
    p = r.provenance
    return {
        "property_record_id": r.property_record_id,
        "candidate_id": r.candidate_id,
        "active_moiety_id": r.active_moiety_id,
        "property_id": r.property_id,
        "value_source_string": r.value_source_string,
        "units": r.units,
        "determination": r.determination,
        "calculator_id": r.calculator_id,
        "method": r.method,
        "software_version": r.software_version,
        "database_version": r.database_version,
        "source_record_id": p.source_record_id,
        "source_url": p.source_url,
        "access_date": p.access_date,
        "release_version": p.release_version,
        "raw_response_sha256": p.raw_response_sha256,
        "extraction_transform": p.extraction_transform,
    }


def property_identity(r: PropertyRecord) -> str:
    """sha256 of the canonical whole row. Order-free, stable across a round trip."""
    return strict_content_sha256(property_content(r))


def distinct_rows(rows: list[PropertyRecord]) -> list[PropertyRecord]:
    """Collapse byte-identical duplicates; keep every genuinely distinct row, sorted."""
    by_identity: dict[str, PropertyRecord] = {}
    for row in rows:
        by_identity.setdefault(property_identity(row), row)
    return [by_identity[k] for k in sorted(by_identity)]


def _contribution(r: PropertyRecord) -> PropertyContribution:
    p = r.provenance
    return PropertyContribution(
        property_record_id=r.property_record_id,
        determination=r.determination,
        method=r.method,
        software_version=r.software_version,
        database_version=r.database_version,
        source_record_id=p.source_record_id,
        access_date=p.access_date,
        raw_response_sha256=p.raw_response_sha256,
        extraction_transform=p.extraction_transform,
    )


def select_properties(records: list[PropertyRecord], policy: dict[str, Any]) -> PropertySelection:
    """Pick the six inputs for ONE candidate. No imputation, no silent tie-breaks.

    The reduction is permutation-invariant. Byte-identical rows collapse (they are the
    same record); every other row is kept. Rows that AGREE on what determines the score —
    the calculator and the exact value in base units — are all bound to the accepted
    property together. Rows that disagree are ambiguous, and Stage 4 refuses rather than
    choosing.
    """
    sel = PropertySelection()
    by_prop: dict[str, list[PropertyRecord]] = {p: [] for p in CNS_MPO_PROPERTIES}
    for r in records:
        by_prop[r.property_id].append(r)

    for prop in CNS_MPO_PROPERTIES:
        rows = distinct_rows(by_prop[prop])
        if not rows:
            sel.missing.append(MissingInput(prop, "absent", "no property record supplied"))
            continue

        usable: list[tuple[PropertyRecord, str, Quantity]] = []
        blocked: list[str] = []
        for r in rows:
            allowed, conformance, reason = check_calculator(policy, prop, r.calculator_id, r)
            if not allowed:
                blocked.append(f"{r.calculator_id}: {reason}")
                continue
            try:
                q = r.quantity
            except (UnitError, QuantityError) as exc:  # pragma: no cover - record-level guard
                blocked.append(f"{r.calculator_id}: {exc}")
                continue
            usable.append((r, conformance, q))

        if not usable:
            code = "disallowed_calculator" if blocked else "absent"
            sel.missing.append(
                MissingInput(prop, code, "; ".join(sorted(blocked)) or "no usable property record")
            )
            continue

        # More than one usable record: only acceptable if they agree on calculator AND the
        # exact value in base units. Otherwise we would be choosing, and choosing silently
        # is the failure mode this whole module exists to prevent.
        distinct = {(r.calculator_id, str(q.in_base())) for r, _c, q in usable}
        if len(distinct) > 1:
            sel.missing.append(
                MissingInput(
                    prop,
                    "ambiguous_multiple_sources",
                    "conflicting property records: "
                    + "; ".join(sorted(f"{c}={v}" for c, v in distinct))
                    + " — Stage 4 will not pick one",
                )
            )
            continue

        # They agree on the score. Bind ALL of them: the value is corroborated by every
        # one of these rows, and dropping the others would hide sources the score rests on.
        _r, conformance, q = usable[0]
        sel.accepted[prop] = AcceptedProperty(
            property_id=prop,
            quantity=q,
            calculator_id=_r.calculator_id,
            conformance=conformance,
            contributions=tuple(
                sorted((_contribution(r) for r, _c, _q in usable),
                       key=lambda c: c.property_record_id)
            ),
        )
    return sel


def cross_candidate_calculator_mixing(
    selections: dict[str, PropertySelection], prose: dict[str, Any]
) -> dict[str, Any]:
    """Two candidates scored with two different ClogD packages are not comparable on
    ClogD. We do not silently rank them against each other."""
    per_prop: dict[str, set[str]] = {p: set() for p in CNS_MPO_PROPERTIES}
    for sel in selections.values():
        for prop, acc in sel.accepted.items():
            per_prop[prop].add(acc.calculator_id)

    mixed = {p: sorted(c) for p, c in per_prop.items() if len(c) > 1}
    return {
        "calculator_mixed_across_candidates": bool(mixed),
        "mixed_properties": mixed,
        "not_comparable_properties": sorted(mixed),
        # Both sentences are declared in method/stage4_prose_v1.json, never typed here.
        "note": (prose["set_level"]["calculator_mixing_present"] if mixed
                 else prose["set_level"]["calculator_mixing_none"]),
    }
