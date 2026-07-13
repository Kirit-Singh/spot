"""The context a clinical PK number needs before it means anything.

The audit called the gap a BLOCKER: the exposure schema "lacks structured PK metric/statistic/
sample-size fields, unbound-fraction inputs, paired plasma/brain identity, residual-blood
correction, and sampling-method details. A literature/FDA adapter would have to hide
load-bearing context in free text."

Three of these change what a number MEANS, not merely how well it is documented:

`pk_metric` / `statistic` — a Cmax and a Ctrough are different exposures; a geometric mean of
twelve patients and one patient's individual value are different evidence. A bare float carries
neither distinction, and an exposure margin computed against the wrong one is simply wrong.

`residual_blood_correction` — a resected brain specimen contains blood, and blood contains
drug. An uncorrected tissue concentration may be measuring the vasculature rather than the
parenchyma, which is exactly the error Grossman warns about. `not_reported` is an honest
answer. Silence is not an answer at all, so the state is required and has no default.

`microdialysis_recovery` — a dialysate concentration is not an interstitial concentration
until it is divided by probe recovery. An uncalibrated microdialysis number is not a
measurement of the brain, and the recovery is what makes it one.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Literal, Optional

from pydantic import Field, model_validator

from .contracts import ID_PATTERN, Provenance, Strict
from .quantity import Quantity


class PkMetric(str, Enum):
    """WHICH exposure. These are not interchangeable and never sum."""

    CMAX = "Cmax"
    CTROUGH = "Ctrough"
    CAVG = "Cavg"
    AUC = "AUC"
    CONCENTRATION_AT_TIME = "concentration_at_time"
    OTHER = "other"


class Statistic(str, Enum):
    """WHOSE exposure: a cohort summary, or one person's measurement."""

    MEAN = "mean"
    MEDIAN = "median"
    GEOMETRIC_MEAN = "geometric_mean"
    INDIVIDUAL = "individual"
    RANGE = "range"
    OTHER = "other"


class VariabilityKind(str, Enum):
    SD = "sd"
    CV_PERCENT = "cv_percent"
    RANGE = "range"
    IQR = "iqr"
    CI95 = "ci95"
    NOT_REPORTED = "not_reported"


class SamplingMethod(str, Enum):
    RESECTION_HOMOGENATE = "resection_homogenate"
    MICRODIALYSIS = "microdialysis"
    PET = "pet"
    CSF_DRAW = "csf_draw"
    BLOOD_DRAW = "blood_draw"
    OTHER = "other"


class ResidualBloodCorrection(str, Enum):
    """Explicit, and with no default: silence is not one of the four answers.

    `not_applicable` is for a sample that is not tissue (a plasma draw, a CSF draw). A tissue
    sample that claims it must say so and be refused: the whole point of the field is that the
    question was ASKED of every tissue concentration.
    """

    APPLIED = "applied"
    NOT_APPLIED = "not_applied"
    NOT_REPORTED = "not_reported"
    NOT_APPLICABLE = "not_applicable"


# Sampling methods that produce a TISSUE concentration, where residual blood is a real
# confound and `not_applicable` would be a false answer.
TISSUE_SAMPLING = (SamplingMethod.RESECTION_HOMOGENATE,)


class PkDetail(Strict):
    """What kind of exposure number this is, over how many subjects, with what spread."""

    pk_metric: PkMetric
    statistic: Statistic
    # Sources often omit n. None means "the source did not say"; 0 is not a cohort.
    sample_size: Optional[int] = Field(default=None, ge=1)
    variability_kind: VariabilityKind
    # The exact string the source printed, like every other magnitude in this engine.
    variability_source_string: Optional[str] = None
    variability_units: Optional[str] = None

    @model_validator(mode="after")
    def _variability_has_a_magnitude(self) -> "PkDetail":
        if self.variability_kind != VariabilityKind.NOT_REPORTED:
            if not self.variability_source_string:
                raise ValueError(
                    f"variability_kind={self.variability_kind.value!r} without a magnitude is a "
                    "label, not a spread. Either carry the number the source printed, or say "
                    "not_reported."
                )
        return self


class SamplingDetail(Strict):
    """How, where and when the sample was taken — and what was done to it afterwards."""

    sampling_method: SamplingMethod
    sample_location: str = Field(min_length=1)
    time_relative_to_dose: str = Field(min_length=1)
    analytical_method: str = Field(min_length=1)
    steady_state: Optional[bool] = None

    # No default. A tissue concentration that never states this is refused.
    residual_blood_correction: ResidualBloodCorrection

    microdialysis_recovery_state: Optional[
        Literal["reported", "not_reported"]
    ] = None
    microdialysis_recovery_source_string: Optional[str] = None
    microdialysis_recovery_method: Optional[str] = None

    @model_validator(mode="after")
    def _rules(self) -> "SamplingDetail":
        if (self.sampling_method in TISSUE_SAMPLING
                and self.residual_blood_correction == ResidualBloodCorrection.NOT_APPLICABLE):
            raise ValueError(
                f"sampling_method={self.sampling_method.value!r} is a TISSUE sample, so residual "
                "blood is not 'not_applicable' — a resected specimen contains blood and blood "
                "contains drug. Say applied, not_applied, or not_reported."
            )
        if self.sampling_method == SamplingMethod.MICRODIALYSIS:
            if self.microdialysis_recovery_state is None:
                raise ValueError(
                    "a microdialysis sample must state its probe recovery. A dialysate "
                    "concentration is not an interstitial concentration until it is divided by "
                    "recovery, so an uncalibrated microdialysis number is not a measurement of "
                    "the brain. 'not_reported' is an honest answer; omitting the question is not."
                )
            if self.microdialysis_recovery_state == "reported" and not (
                    self.microdialysis_recovery_source_string
                    and self.microdialysis_recovery_method):
                raise ValueError(
                    "microdialysis_recovery_state='reported' requires BOTH the recovery value "
                    "the source printed and the method it was determined by (retrodialysis, "
                    "zero-net-flux, ...). A recovery with no method is not reproducible."
                )
        elif self.microdialysis_recovery_state is not None:
            raise ValueError(
                f"microdialysis_recovery_state is meaningless for "
                f"sampling_method={self.sampling_method.value!r}"
            )
        return self


# ------------------------------------------------- fraction unbound and brain:plasma ratios
#
# Grossman 2026: total brain-to-plasma ratios can mislead; total AND unbound concentrations
# should be measured; the unbound brain-to-plasma ratio is the important one. That makes fu and
# Kp,uu the two most dangerous numbers in Stage 4 — both are usually CALCULATED, and once
# written down both look exactly like measurements. The contract makes the difference
# structural rather than a matter of care.


class FractionUnboundRecord(Strict):
    """One measured fraction unbound. Its own row, its own source, its own method.

    fu,plasma and fu,brain are different numbers and Kp,uu needs both. This is a lane rather
    than a field on the exposure row because an fu IS an observation — with a species, a
    method and a source of its own — and burying it inside a concentration would be exactly
    the "load-bearing context hidden in free text" the audit refused.
    """

    fraction_unbound_id: str = Field(pattern=ID_PATTERN)
    candidate_id: str = Field(pattern=ID_PATTERN)
    active_moiety_id: str = Field(pattern=ID_PATTERN)
    matrix: Literal["plasma", "blood", "brain", "csf"]
    # Exact source string. fu is a fraction: 0 < fu <= 1. An "11" that meant 11% inflates every
    # unbound concentration derived from it by a hundredfold.
    value_source_string: str
    method: str = Field(min_length=1)
    species: str = Field(min_length=1)
    # A concentration-DEPENDENT fu measured at one concentration does not licence an unbound
    # conversion at another.
    concentration_dependence: Literal["independent", "dependent", "not_reported"]
    provenance: Provenance

    @model_validator(mode="after")
    def _is_a_fraction(self) -> "FractionUnboundRecord":
        q = self.quantity
        if not (Decimal(0) < q.decimal <= Decimal(1)):
            raise ValueError(
                f"fraction unbound must satisfy 0 < fu <= 1 (got {self.value_source_string!r}). "
                "A percentage written as a fraction is the classic error and it misstates every "
                "unbound concentration derived from it by a factor of 100."
            )
        return self

    @property
    def quantity(self) -> Quantity:
        return Quantity.parse(self.value_source_string, "ratio")


class UnboundDerivation(Strict):
    """C_free = C_total * fu — an INFERENCE, declared as one.

    A free concentration the source MEASURED and a free concentration obtained by multiplying a
    total by a plasma fu are not the same evidence: the second inherits every assumption in the
    fu (species, method, concentration dependence, matrix). The audit requires "both source-bound
    inputs and the exact declared transform", so both are mandatory here.
    """

    from_measurement_id: str = Field(pattern=ID_PATTERN)
    fraction_unbound_id: str = Field(pattern=ID_PATTERN)
    transform: str = Field(min_length=1)


class RatioReport(Strict):
    """A Kp or Kp,uu — and whether the SOURCE said it or someone worked it out.

    `reported` is the source's own number. `derived` is a calculation, and a calculation must
    name the measurements it divided and the transform it used, or it cannot be checked and
    cannot be distinguished from an assertion.
    """

    ratio_kind: Literal["kp", "kp_uu_brain"] = "kp"
    basis: Literal["reported", "derived"]
    value_source_string: str
    derivation_transform: Optional[str] = None
    input_measurement_ids: list[str] = Field(default_factory=list)
    # Kp,uu = (C_brain * fu_brain) / (C_plasma * fu_plasma). Deriving one without naming the fu
    # records is asserting an UNBOUND ratio from TOTAL concentrations.
    fraction_unbound_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _rules(self) -> "RatioReport":
        if self.basis == "reported":
            if self.derivation_transform or self.input_measurement_ids or self.fraction_unbound_ids:
                raise ValueError(
                    "a 'reported' ratio is the number the SOURCE printed. If it was computed "
                    "from other rows it is 'derived' — letting a row be both erases the only "
                    "distinction that matters here."
                )
            return self
        if not self.derivation_transform:
            raise ValueError(
                "a derived ratio must declare the exact transform it was computed by. A ratio "
                "whose derivation is unstated cannot be reproduced or refuted."
            )
        if not self.input_measurement_ids:
            raise ValueError(
                "a derived ratio must name the measurements it was derived FROM. Otherwise it "
                "is indistinguishable from a number someone typed in."
            )
        if self.ratio_kind == "kp_uu_brain" and not self.fraction_unbound_ids:
            raise ValueError(
                "a derived Kp,uu must name the fraction-unbound records it used. Kp,uu = "
                "(C_brain * fu_brain) / (C_plasma * fu_plasma); deriving it without naming the "
                "fu records is asserting an UNBOUND ratio from TOTAL concentrations, which is "
                "the specific error Grossman 2026 warns about."
            )
        return self
