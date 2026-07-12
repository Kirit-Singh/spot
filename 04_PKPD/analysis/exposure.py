"""Exposure vs potency.

The margin is the one number in Stage 4 that combines two measurements, so it is where a
silent category error does the most damage: total tissue concentration over free in-vitro
IC50 is a number that looks fine and means nothing.

Every gate that fails returns status=not_computable with an exact reason. There is no
best-effort margin. The gates the post-build audit defeated, and which are now closed:

  * an IV 999-g measurement was compared against an oral 150-mg context. The measurement
    must now AGREE with the context it names (route, formulation, dose, schedule, moiety).
  * magnitudes were floats on a 10-decimal grid, so 1e-12 and 4e-11 shared an identity.
    They are now exact decimals (`quantity.py`) and the margin is computed in Decimal.
  * a CENSORED measurement (`not_detected` / `below_lloq`) skipped the gates entirely and
    went straight to Grossman's "little to no drug in NEB". A non-detect is a statement
    about the ASSAY, not about the drug: an assay that could not have seen the MEC anyway
    excludes nothing. `compute_censored_bound` therefore puts a censored measurement
    through EXACTLY the same gates as a quantified one and then requires a source-declared
    numeric upper bound strictly below the MEC.

`_shared_gates` is that common path. Neither branch can bypass it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .contracts import EvidenceContext
from .evidence_records import ExposureMeasurement, PotencyContextLink, PotencyRecord
from .quantity import Quantity, UnitError, ratio

# Only a declared target concentration may be the denominator of a margin.
MARGIN_METRICS = ("MEC", "target_concentration")

# The fields on a measurement that must equal the context it claims to belong to. A
# measurement in a different regimen is evidence about a different context.
CONTEXT_FIELDS = ("route", "formulation", "dose", "schedule")

# The source says the drug was looked for and not quantified. These are the only two
# statuses `compute_censored_bound` will act on.
CENSORED_STATUSES = ("not_detected", "below_lloq")


@dataclass(frozen=True)
class MarginResult:
    measurement_id: str
    potency_id: Optional[str]
    candidate_id: str
    context_id: str
    status: str  # "computed" | "not_computable"
    margin: Optional[float]
    margin_canonical_decimal: Optional[str]
    harmonized_units: Optional[str]
    exposure_harmonized: Optional[str]
    potency_harmonized: Optional[str]
    binding_state: Optional[str]
    matrix: Optional[str]
    enhancement_context: Optional[str]
    detection_status: Optional[str]
    reason_code: Optional[str]
    reason: Optional[str]
    transform: Optional[str]
    caveats: list[str]
    potency_context_link_id: Optional[str] = None


def _nc(m: ExposureMeasurement, p: Optional[PotencyRecord], ctx: EvidenceContext,
        code: str, reason: str, caveats: list[str]) -> MarginResult:
    return MarginResult(
        measurement_id=m.measurement_id,
        potency_id=p.potency_id if p else None,
        candidate_id=m.candidate_id,
        context_id=ctx.context_id,
        status="not_computable",
        margin=None,
        margin_canonical_decimal=None,
        harmonized_units=None,
        exposure_harmonized=None,
        potency_harmonized=None,
        binding_state=m.binding_state,
        matrix=m.matrix,
        enhancement_context=m.enhancement_context,
        detection_status=m.detection_status,
        reason_code=code,
        reason=reason,
        transform=None,
        caveats=caveats,
    )


def check_context_agreement(m: ExposureMeasurement, ctx: EvidenceContext) -> list[str]:
    """Which regimen fields disagree between the measurement and the context it names."""
    if m.context_id != ctx.context_id:
        return [f"context_id ({m.context_id!r} != {ctx.context_id!r})"]
    mismatched = []
    for f in CONTEXT_FIELDS:
        if str(getattr(m, f)).strip().lower() != str(getattr(ctx, f)).strip().lower():
            mismatched.append(f"{f} ({getattr(m, f)!r} != {getattr(ctx, f)!r})")
    if m.active_moiety_id != ctx.active_moiety_id:
        mismatched.append(
            f"active_moiety_id ({m.active_moiety_id!r} != {ctx.active_moiety_id!r})"
        )
    return mismatched


def matrix_caveats(m: ExposureMeasurement) -> list[str]:
    """What the MATRIX itself makes this measurement unable to say. Never suppressed.

    These are properties of where the drug was measured, not of the margin: they hold
    whether or not an MEC exists to compare against. The engine used to attach them inside
    the margin gates only, so a CSF measurement with no admissible MEC — exactly the case
    where a reader has least to go on — was emitted with NO caveat at all.
    """
    # CODES, not sentences. The sentence for each is declared in method/stage4_prose_v1.json
    # (and in METHODS.md); a sentence emitted from here would be bound by nothing, and a
    # resealed release could rewrite "CSF is not non-enhancing brain" into its opposite.
    caveats: list[str] = []
    if m.matrix == "csf":
        caveats.append("csf_is_not_non_enhancing_brain")
    if m.enhancement_context == "enhancing":
        caveats.append("measured_in_enhancing_tissue")
    return caveats


@dataclass(frozen=True)
class GateFailure:
    code: str
    reason: str


@dataclass(frozen=True)
class GateResult:
    """The outcome of the gates a usable exposure-vs-potency comparison must pass."""

    failure: Optional[GateFailure]
    potency_context_link_id: Optional[str]
    caveats: list[str]


def _shared_gates(
    m: ExposureMeasurement,
    potency: Optional[PotencyRecord],
    context: EvidenceContext,
    links: list[PotencyContextLink],
) -> GateResult:
    """Every gate that does not depend on WHICH magnitude is being compared.

    A quantified margin and a censored upper bound both run this. The censored branch used
    to skip it entirely, which is how an IC50 from an unrelated disease came to underwrite
    an `impermeable` class.
    """
    caveats = matrix_caveats(m)

    def fail(code: str, reason: str) -> GateResult:
        return GateResult(GateFailure(code, reason), None, caveats)

    # 0. The measurement must actually belong to the context it names.
    disagreements = check_context_agreement(m, context)
    if disagreements:
        return fail("context_disagreement",
                    "the measurement does not match the evidence context it names: "
                    + "; ".join(disagreements))

    if potency is None:
        return fail("no_potency_record",
                    "No MEC/potency record; there is nothing to compare against.")

    # 1. Same molecule, same candidate.
    if m.active_moiety_id != potency.active_moiety_id:
        return fail("active_moiety_mismatch",
                    f"exposure moiety {m.active_moiety_id!r} != potency moiety "
                    f"{potency.active_moiety_id!r}; a salt, prodrug or metabolite is not the "
                    "same molecule.")
    if m.candidate_id != potency.candidate_id:
        return fail("candidate_mismatch",
                    "exposure and potency belong to different candidates.")

    # 2. Is this potency an admissible denominator at all?
    if potency.metric not in MARGIN_METRICS:
        return fail("potency_metric_not_a_target_concentration",
                    f"potency metric is {potency.metric!r}. A margin needs an MEC or a declared "
                    "target concentration; deriving one from an IC50/IC90 requires an unbound "
                    "fraction and a declared transform, and Stage 4 supplies neither silently.")

    # 3. Free vs total.
    if m.binding_state == "unspecified" or potency.binding_state == "unspecified":
        return fail("binding_state_unspecified",
                    "free/total binding state is unspecified on the exposure and/or the potency; "
                    "the comparison would be undefined.")
    if m.binding_state != potency.binding_state:
        return fail("free_total_mismatch",
                    f"exposure is {m.binding_state} and potency is {potency.binding_state}. "
                    "Comparing a total tissue concentration with a free in-vitro potency (or "
                    "vice versa) misstates the margin by the unbound fraction and is refused.")

    # 4. Route / dose / schedule known.
    unknown = {"", "unknown", "unspecified", "not_specified"}
    unknown_fields = [f for f in ("route", "dose", "schedule")
                      if str(getattr(m, f)).strip().lower() in unknown]
    if unknown_fields:
        return fail("dosing_context_unknown",
                    "route/dose/schedule not fully known: " + ", ".join(unknown_fields))

    # 5. Is the potency relevant to THIS biological context?
    # `check_referential_integrity` refuses two links for one (potency, tumour context), so
    # this lookup is unique; sorting makes it order-free regardless.
    link_id: Optional[str] = None
    if potency.biological_context != context.tumor_context:
        matches = sorted(
            (row for row in links
             if row.potency_id == potency.potency_id
             and row.tumor_context == context.tumor_context),
            key=lambda row: row.link_id,
        )
        link = matches[0] if matches else None
        if not link:
            return fail("potency_context_not_relevant",
                        f"potency was measured in {potency.biological_context!r} but the evidence "
                        f"context is {context.tumor_context!r}, and no sourced relevance link "
                        "was supplied.")
        link_id = link.link_id
        caveats.append("potency_applied_via_sourced_relevance_link")

    return GateResult(None, link_id, caveats)


def _unit_family_reason(numerator: Quantity, q_pot: Quantity, what: str) -> str:
    return (f"{what} is {numerator.dimension} ({numerator.unit}) and potency is "
            f"{q_pot.dimension} ({q_pot.unit}). Converting between mass and molar needs "
            "the active moiety's molecular weight and a declared transform; Stage 4 will "
            "not do it implicitly.")


def compute_exposure_margin(
    measurement: ExposureMeasurement,
    potency: Optional[PotencyRecord],
    context: EvidenceContext,
    potency_context_links: Optional[list[PotencyContextLink]] = None,
) -> MarginResult:
    """margin = harmonized exposure / harmonized potency, or an exact refusal."""
    m = measurement
    links = list(potency_context_links or [])

    gates = _shared_gates(m, potency, context, links)
    caveats = gates.caveats
    if gates.failure:
        return _nc(m, potency, context, gates.failure.code, gates.failure.reason, caveats)
    assert potency is not None  # _shared_gates rejects a missing potency
    link_id = gates.potency_context_link_id

    # 6. A concentration that was never quantified has no margin. It may still bound one:
    #    see `compute_censored_bound`, which is what "little to no drug in NEB" rests on.
    q_exp = m.quantity
    if q_exp is None:
        return _nc(m, potency, context, "no_quantified_concentration",
                   f"detection_status={m.detection_status!r}: the source reports no quantified "
                   "concentration, so a numeric margin does not exist.", caveats)

    # 7. Units.
    q_pot = potency.quantity
    if q_exp.dimension != q_pot.dimension:
        return _nc(m, potency, context, "unit_family_mismatch",
                   _unit_family_reason(q_exp, q_pot, "exposure"), caveats)

    try:
        margin_decimal, margin_float = ratio(q_exp, q_pot)
    except (UnitError, ZeroDivisionError) as exc:
        return _nc(m, potency, context, "margin_undefined", str(exc), caveats)

    return MarginResult(
        measurement_id=m.measurement_id,
        potency_id=potency.potency_id,
        candidate_id=m.candidate_id,
        context_id=context.context_id,
        status="computed",
        margin=margin_float,
        margin_canonical_decimal=margin_decimal,
        harmonized_units=q_exp.base_unit(),
        exposure_harmonized=format(q_exp.in_base().normalize(), "E"),
        potency_harmonized=format(q_pot.in_base().normalize(), "E"),
        binding_state=m.binding_state,
        matrix=m.matrix,
        enhancement_context=m.enhancement_context,
        detection_status=m.detection_status,
        reason_code=None,
        reason=None,
        transform=(
            f"margin = ({q_exp.conversion_transform()}) / ({q_pot.conversion_transform()}); "
            f"both {m.binding_state}; potency metric = {potency.metric}"
        ),
        caveats=caveats,
        potency_context_link_id=link_id,
    )


# --------------------------------------------------------------- censored measurements


@dataclass(frozen=True)
class CensoredBoundResult:
    """A non-detect, bounded against the MEC — or an exact refusal to bound it.

    `bound_below_mec` is the whole point. `not_detected` alone says only that the assay
    did not see the drug; if the assay's floor sits above the MEC, a fully therapeutic
    concentration would also have gone unseen. Only `bound < MEC` (STRICT) rules that out.
    """

    measurement_id: str
    potency_id: Optional[str]
    candidate_id: str
    context_id: str
    status: str  # "computed" | "not_computable"
    detection_status: str
    bound_kind: Optional[str]
    bound_source_string: Optional[str]
    bound_units: Optional[str]
    bound_canonical_decimal: Optional[str]
    bound_harmonized: Optional[str]
    mec_harmonized: Optional[str]
    harmonized_units: Optional[str]
    bound_over_mec_canonical_decimal: Optional[str]
    bound_below_mec: Optional[bool]
    binding_state: Optional[str]
    reason_code: Optional[str]
    reason: Optional[str]
    transform: Optional[str]
    caveats: list[str]
    potency_context_link_id: Optional[str] = None


def _censored_nc(m: ExposureMeasurement, p: Optional[PotencyRecord], ctx: EvidenceContext,
                 code: str, reason: str, caveats: list[str]) -> CensoredBoundResult:
    return CensoredBoundResult(
        measurement_id=m.measurement_id,
        potency_id=p.potency_id if p else None,
        candidate_id=m.candidate_id,
        context_id=ctx.context_id,
        status="not_computable",
        detection_status=m.detection_status,
        bound_kind=m.quantitation_limit_kind,
        bound_source_string=m.quantitation_limit_source_string,
        bound_units=m.quantitation_limit_units,
        bound_canonical_decimal=None,
        bound_harmonized=None,
        mec_harmonized=None,
        harmonized_units=None,
        bound_over_mec_canonical_decimal=None,
        bound_below_mec=None,
        binding_state=m.binding_state,
        reason_code=code,
        reason=reason,
        transform=None,
        caveats=caveats,
    )


def compute_censored_bound(
    measurement: ExposureMeasurement,
    potency: Optional[PotencyRecord],
    context: EvidenceContext,
    potency_context_links: Optional[list[PotencyContextLink]] = None,
) -> CensoredBoundResult:
    """Can this non-detect exclude the MEC? -> a bounded answer, or an exact refusal.

    Method: `nebpi_grossman2026_v1.json::censored_pk_policy`.
    """
    m = measurement
    links = list(potency_context_links or [])

    if m.detection_status not in CENSORED_STATUSES:
        return _censored_nc(m, potency, context, "not_a_censored_measurement",
                            f"detection_status={m.detection_status!r} is quantified; a censored "
                            "bound does not apply.", [])

    gates = _shared_gates(m, potency, context, links)
    caveats = gates.caveats
    if gates.failure:
        return _censored_nc(m, potency, context, gates.failure.code, gates.failure.reason, caveats)
    assert potency is not None  # _shared_gates rejects a missing potency

    q_bound = m.quantitation_limit
    if q_bound is None:
        return _censored_nc(
            m, potency, context, "no_source_bound_quantitation_limit",
            f"detection_status={m.detection_status!r} but the source supplies no numeric "
            "LOD/LLOQ with units. A non-detect from an assay of unknown sensitivity bounds "
            "nothing: if the assay floor were above the MEC, a therapeutic concentration "
            "would also have gone undetected. Table 2 footnote (a) applies to the "
            "little-to-none branch too.", caveats)

    q_pot = potency.quantity
    if q_bound.dimension != q_pot.dimension:
        return _censored_nc(m, potency, context, "unit_family_mismatch",
                            _unit_family_reason(q_bound, q_pot, "the quantitation limit"),
                            caveats)

    bound_base = q_bound.in_base()
    mec_base = q_pot.in_base()
    if mec_base == 0:
        return _censored_nc(m, potency, context, "margin_undefined",
                            "the MEC is zero; the bound-vs-MEC comparison is undefined.",
                            caveats)

    # Exact Decimal comparison. STRICT: a bound equal to the MEC excludes nothing, because
    # the true concentration could sit anywhere below the bound — including at the MEC.
    below = bound_base < mec_base
    try:
        ratio_decimal, _ratio_float = ratio(q_bound, q_pot)
    except (UnitError, ZeroDivisionError) as exc:
        return _censored_nc(m, potency, context, "margin_undefined", str(exc), caveats)

    transform = (
        f"upper bound = ({q_bound.conversion_transform()}) [{m.quantitation_limit_kind}, "
        f"{m.binding_state}]; MEC = ({q_pot.conversion_transform()}) "
        f"[{potency.metric}, {potency.binding_state}]; "
        f"bound/MEC = {ratio_decimal}; bound < MEC (strict) = {below}"
    )

    if not below:
        return CensoredBoundResult(
            measurement_id=m.measurement_id, potency_id=potency.potency_id,
            candidate_id=m.candidate_id, context_id=context.context_id,
            status="not_computable", detection_status=m.detection_status,
            bound_kind=m.quantitation_limit_kind,
            bound_source_string=m.quantitation_limit_source_string,
            bound_units=m.quantitation_limit_units,
            bound_canonical_decimal=q_bound.canonical_decimal,
            bound_harmonized=format(bound_base.normalize(), "E"),
            mec_harmonized=format(mec_base.normalize(), "E"),
            harmonized_units=q_bound.base_unit(),
            bound_over_mec_canonical_decimal=ratio_decimal,
            bound_below_mec=False,
            binding_state=m.binding_state,
            reason_code="censored_bound_not_below_mec",
            reason=(
                f"the assay's {m.quantitation_limit_kind} bound "
                f"({q_bound.value_source_string} {q_bound.unit}) is not strictly below the MEC "
                f"({q_pot.value_source_string} {q_pot.unit}). The drug was not detected, but "
                "this assay could not have detected a concentration at the MEC either, so "
                "'little to no drug in NEB' is not established."
            ),
            transform=transform,
            caveats=caveats,
            potency_context_link_id=gates.potency_context_link_id,
        )

    return CensoredBoundResult(
        measurement_id=m.measurement_id, potency_id=potency.potency_id,
        candidate_id=m.candidate_id, context_id=context.context_id,
        status="computed", detection_status=m.detection_status,
        bound_kind=m.quantitation_limit_kind,
        bound_source_string=m.quantitation_limit_source_string,
        bound_units=m.quantitation_limit_units,
        bound_canonical_decimal=q_bound.canonical_decimal,
        bound_harmonized=format(bound_base.normalize(), "E"),
        mec_harmonized=format(mec_base.normalize(), "E"),
        harmonized_units=q_bound.base_unit(),
        bound_over_mec_canonical_decimal=ratio_decimal,
        bound_below_mec=True,
        binding_state=m.binding_state,
        reason_code=None,
        reason=None,
        transform=transform,
        caveats=caveats,
        potency_context_link_id=gates.potency_context_link_id,
    )
