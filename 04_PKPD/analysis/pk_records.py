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

from enum import Enum
from typing import Literal, Optional

from pydantic import Field, model_validator

from .contracts import Strict


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
