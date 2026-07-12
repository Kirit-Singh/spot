"""Derive the Grossman PK-in-NEB level. Never assert it.

Table 2 footnote (a) — "Accounting for potency" — is attached to ALL THREE PK branches:

    therapeutic     measured NEB concentration reaches the MEC
    low             measurably present in NEB, below the MEC
    little to none  the drug is not there in any amount that could matter

The third one is the trap. `not_detected` is a statement about the ASSAY, not about the
drug. An assay whose floor sits above the MEC would also fail to see a fully therapeutic
concentration, so a bare non-detect establishes nothing — and the first implementation let
exactly that manufacture an `impermeable` class, with an IC50 from an unrelated disease
standing in for the MEC. A censored measurement now runs the SAME gates as a quantified
one and must additionally carry a source-declared numeric LOD/LLOQ that is STRICTLY below
the MEC.

Method: `nebpi_grossman2026_v1.json::censored_pk_policy`.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from .contracts import EvidenceContext
from .evidence_records import (
    ExposureMeasurement,
    NebpiCriterionId,
    NebpiObservation,
    PkNebLevel,
    PotencyContextLink,
    PotencyRecord,
)
from .exposure import CENSORED_STATUSES, compute_censored_bound, compute_exposure_margin
from .nebpi_reduce import CONFLICTING, reduce_criterion

# The matrices that ARE non-enhancing brain. A plasma or CSF measurement is not NEB PK,
# however it is labelled: Grossman is explicit that the blood-CSF barrier is not the BBB.
NEB_MATRICES = ("brain_tissue_non_enhancing", "microdialysate_brain_isf")

# Not a PkNebLevel: it is the refusal to have one, and it satisfies no branch.
PK_CONFLICTING = "pk_conflicting"

# The levels that a bound comparison actually produced. Anything else satisfies nothing.
DERIVED_LEVELS = (
    PkNebLevel.THERAPEUTIC.value,
    PkNebLevel.LOW.value,
    PkNebLevel.LITTLE_TO_NONE.value,
)


@dataclass
class PkDerivation:
    """How the Grossman PK level was DERIVED — never asserted."""

    level: str
    observation: Optional[NebpiObservation]
    measurement_id: Optional[str] = None
    potency_id: Optional[str] = None
    margin: Optional[float] = None
    margin_canonical_decimal: Optional[str] = None
    detection_status: Optional[str] = None
    transform: Optional[str] = None
    blocked_reason: Optional[str] = None
    blocked_code: Optional[str] = None
    # The censored branch: what bounded the non-detect, and whether it cleared the MEC.
    censored_bound_kind: Optional[str] = None
    censored_bound_source_string: Optional[str] = None
    censored_bound_units: Optional[str] = None
    censored_bound_canonical_decimal: Optional[str] = None
    censored_bound_over_mec_canonical_decimal: Optional[str] = None
    censored_bound_below_mec: Optional[bool] = None

    def as_content(self) -> dict[str, Any]:
        """What the scorecard and the nebpi_decisions table carry."""
        return {
            "derived_level": self.level,
            "measurement_id": self.measurement_id,
            "potency_id": self.potency_id,
            "margin_canonical_decimal": self.margin_canonical_decimal,
            "detection_status": self.detection_status,
            "transform": self.transform,
            "blocked_code": self.blocked_code,
            "blocked_reason": self.blocked_reason,
            "censored_bound_kind": self.censored_bound_kind,
            "censored_bound_source_string": self.censored_bound_source_string,
            "censored_bound_units": self.censored_bound_units,
            "censored_bound_canonical_decimal": self.censored_bound_canonical_decimal,
            "censored_bound_over_mec_canonical_decimal":
                self.censored_bound_over_mec_canonical_decimal,
            "censored_bound_below_mec": self.censored_bound_below_mec,
            "note": (
                "The PK level is derived from the bound measurement-vs-MEC comparison; no "
                "evidence row may assert it. A censored measurement additionally requires a "
                "source-declared LOD/LLOQ strictly below the MEC."
            ),
        }


def _blocked(level: str, o: Optional[NebpiObservation], code: str, reason: str,
             **kw: Any) -> PkDerivation:
    return PkDerivation(level, o, blocked_code=code, blocked_reason=reason, **kw)


def derive_pk_level(
    obs: list[NebpiObservation],
    context: EvidenceContext,
    measurements: list[ExposureMeasurement],
    potencies: list[PotencyRecord],
    links: list[PotencyContextLink],
) -> PkDerivation:
    """Resolve the named measurement and the named MEC, then read the level off the comparison.

        not detected / below LLOQ, bound STRICTLY below the MEC -> little to no drug in NEB
        quantified, margin >= 1                                 -> therapeutic
        quantified, margin <  1                                 -> low

    Everything else is `pk_not_evaluated` with an exact reason. The detected/not-detected
    split is the SOURCE's statement; the MEC comparison is what makes it mean something.
    """
    reduction = reduce_criterion(obs, NebpiCriterionId.PK_IN_NEB)
    if reduction.state == CONFLICTING:
        return _blocked(
            PK_CONFLICTING, None, "conflicting_pk_observations",
            "More than one distinct PK-in-NEB observation for this context "
            f"({', '.join(reduction.conflicting_observation_ids)}). Stage 4 does not average "
            "or choose between them.",
        )
    o = reduction.row
    if o is None:
        return PkDerivation(PkNebLevel.NOT_EVALUATED.value, None)

    by_m = {m.measurement_id: m for m in measurements}
    by_p = {p.potency_id: p for p in potencies}

    m = by_m.get(o.measurement_id or "")
    if m is None:
        return _blocked(PkNebLevel.NOT_EVALUATED.value, o, "measurement_not_found",
                        f"PK observation names measurement {o.measurement_id!r}, which does "
                        "not exist.")
    p = by_p.get(o.potency_id or "")
    if p is None:
        return _blocked(PkNebLevel.NOT_EVALUATED.value, o, "potency_not_found",
                        f"PK observation names potency {o.potency_id!r}, which does not exist.")

    if m.candidate_id != o.candidate_id or m.context_id != o.context_id:
        return _blocked(PkNebLevel.NOT_EVALUATED.value, o, "measurement_context_mismatch",
                        f"measurement {m.measurement_id!r} belongs to {m.candidate_id!r}/"
                        f"{m.context_id!r}, not to this observation's {o.candidate_id!r}/"
                        f"{o.context_id!r}.")
    if m.active_moiety_id != context.active_moiety_id:
        return _blocked(PkNebLevel.NOT_EVALUATED.value, o, "measurement_moiety_mismatch",
                        f"measurement moiety {m.active_moiety_id!r} is not the context's "
                        f"{context.active_moiety_id!r}.")
    if m.matrix not in NEB_MATRICES or m.enhancement_context != "non_enhancing":
        return _blocked(PkNebLevel.NOT_EVALUATED.value, o, "measurement_not_in_neb",
                        f"measurement matrix is {m.matrix!r} / {m.enhancement_context!r}: this "
                        "is not a non-enhancing-brain measurement, so it cannot establish PK "
                        "in NEB.")

    if m.detection_status in CENSORED_STATUSES:
        return _censored(o, m, p, context, links)
    return _quantified(o, m, p, context, links)


def _censored(o: NebpiObservation, m: ExposureMeasurement, p: PotencyRecord,
              context: EvidenceContext, links: list[PotencyContextLink]) -> PkDerivation:
    """"Little to no drug in NEB" — only if the assay could actually have seen the MEC."""
    bound = compute_censored_bound(m, p, context, links)
    common: dict[str, Any] = {
        "measurement_id": m.measurement_id,
        "potency_id": p.potency_id,
        "detection_status": m.detection_status,
        "censored_bound_kind": bound.bound_kind,
        "censored_bound_source_string": bound.bound_source_string,
        "censored_bound_units": bound.bound_units,
        "censored_bound_canonical_decimal": bound.bound_canonical_decimal,
        "censored_bound_over_mec_canonical_decimal": bound.bound_over_mec_canonical_decimal,
        "censored_bound_below_mec": bound.bound_below_mec,
    }
    if bound.status != "computed":
        return _blocked(
            PkNebLevel.NOT_EVALUATED.value, o,
            bound.reason_code or "censored_bound_not_computable",
            f"the non-detect could not be bounded against the MEC: {bound.reason}",
            **common,
        )
    return PkDerivation(PkNebLevel.LITTLE_TO_NONE.value, o, transform=bound.transform, **common)


def _quantified(o: NebpiObservation, m: ExposureMeasurement, p: PotencyRecord,
                context: EvidenceContext, links: list[PotencyContextLink]) -> PkDerivation:
    margin = compute_exposure_margin(m, p, context, links)
    if margin.status != "computed":
        return _blocked(PkNebLevel.NOT_EVALUATED.value, o,
                        margin.reason_code or "margin_not_computable",
                        f"the concentration-vs-MEC comparison is not computable: {margin.reason}",
                        measurement_id=m.measurement_id, potency_id=p.potency_id,
                        detection_status=m.detection_status)

    # Decided on the exact decimal, never the display float.
    value = Decimal(margin.margin_canonical_decimal or "0")
    level = (PkNebLevel.THERAPEUTIC.value if value >= Decimal(1) else PkNebLevel.LOW.value)
    return PkDerivation(level, o, measurement_id=m.measurement_id, potency_id=p.potency_id,
                        margin=margin.margin,
                        margin_canonical_decimal=margin.margin_canonical_decimal,
                        detection_status=m.detection_status, transform=margin.transform)
