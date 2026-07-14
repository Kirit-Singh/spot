"""Exposure: the context a clinical PK number needs before it means anything.

The audit called this a BLOCKER: "the clinical exposure schema is not yet acquisition-complete.
It lacks structured PK metric/statistic/sample-size fields, unbound-fraction inputs, paired
plasma/brain identity, residual-blood correction, and sampling-method details. A literature/FDA
adapter would have to hide load-bearing context in free text."

The rules that carry science here:

  * A `Cmax` and a `Ctrough` are not the same exposure. A `mean` of 12 and one patient's
    individual value are not the same evidence. Neither distinction survives a bare float.
  * A brain-tissue concentration that was not corrected for residual blood may be measuring
    the blood in the tissue. `not_reported` is an honest answer; SILENCE is not.
  * An uncalibrated microdialysate concentration is not a concentration — probe recovery is
    what converts a dialysate number into an interstitial one.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from analysis.evidence_records import EvidenceType, ExposureMeasurement, Provenance
from analysis.pk_records import (
    PkDetail,
    PkMetric,
    ResidualBloodCorrection,
    SamplingDetail,
    SamplingMethod,
    Statistic,
    VariabilityKind,
)

PROV = Provenance(source_record_id="src.test", access_date="2026-07-11",
                  raw_response_sha256="0" * 64, extraction_transform="table 2, row 3")


def _m(**kw) -> ExposureMeasurement:
    base = dict(
        measurement_id="EXP-1", candidate_id="C1", active_moiety_id="M1", context_id="CTX-1",
        formulation="tablet", route="oral", dose="100 mg", schedule="once daily",
        species_population="adult human", matrix="brain_tissue_non_enhancing",
        enhancement_context="non_enhancing", binding_state="free",
        concentration_source_string="250", concentration_units="nM",
        detection_status="quantified",
        evidence_type=EvidenceType.HUMAN_CLINICAL, provenance=PROV,
    )
    base.update(kw)
    return ExposureMeasurement(**base)


def _sampling(**over) -> SamplingDetail:
    base = dict(
        sampling_method=SamplingMethod.RESECTION_HOMOGENATE,
        sample_location="peritumoral non-enhancing white matter",
        time_relative_to_dose="4 h post-dose",
        analytical_method="LC-MS/MS",
        residual_blood_correction=ResidualBloodCorrection.APPLIED,
    )
    base.update(over)
    return SamplingDetail(**base)


# --------------------------------------------------------- v1 rows keep working (req 7)

def test_a_v1_exposure_row_without_the_v2_detail_still_validates():
    m = _m()
    assert m.pk_detail is None
    assert m.sampling is None
    assert m.co_medications == []


# ------------------------------------------------------------------------- PK metric

def test_the_pk_metric_vocabulary_keeps_cmax_ctrough_and_auc_apart():
    assert {v.value for v in PkMetric} == {
        "Cmax", "Ctrough", "Cavg", "AUC", "concentration_at_time", "other",
    }


def test_a_pk_detail_carries_metric_statistic_sample_size_and_variability():
    d = PkDetail(pk_metric=PkMetric.CMAX, statistic=Statistic.GEOMETRIC_MEAN, sample_size=12,
                 variability_kind=VariabilityKind.CV_PERCENT, variability_source_string="34")
    assert (d.pk_metric, d.statistic, d.sample_size) == (
        PkMetric.CMAX, Statistic.GEOMETRIC_MEAN, 12)
    assert d.variability_source_string == "34"


def test_a_declared_variability_must_carry_its_magnitude():
    """`variability_kind=SD` with no number is a label, not a spread."""
    with pytest.raises(ValidationError):
        PkDetail(pk_metric=PkMetric.CMAX, statistic=Statistic.MEAN,
                 variability_kind=VariabilityKind.SD)


def test_variability_not_reported_is_an_honest_state_and_needs_no_magnitude():
    d = PkDetail(pk_metric=PkMetric.CMAX, statistic=Statistic.MEAN,
                 variability_kind=VariabilityKind.NOT_REPORTED)
    assert d.variability_source_string is None


def test_a_summary_statistic_without_a_sample_size_is_allowed_but_an_n_of_zero_is_not():
    """Sources often omit n. They never report n=0 and mean something by it."""
    assert PkDetail(pk_metric=PkMetric.CMAX, statistic=Statistic.MEAN,
                    variability_kind=VariabilityKind.NOT_REPORTED).sample_size is None
    with pytest.raises(ValidationError):
        PkDetail(pk_metric=PkMetric.CMAX, statistic=Statistic.MEAN, sample_size=0,
                 variability_kind=VariabilityKind.NOT_REPORTED)


# ---------------------------------------------------------------- residual blood

def test_residual_blood_correction_is_an_explicit_state_never_an_assumption():
    assert {v.value for v in ResidualBloodCorrection} == {
        "applied", "not_applied", "not_reported", "not_applicable",
    }


def test_a_brain_tissue_sample_must_state_its_residual_blood_correction():
    """Grossman: residual blood contamination in a resected specimen should be assessed. An
    uncorrected tissue concentration may be measuring the blood inside the tissue. Saying
    `not_reported` is honest; saying nothing hides the question."""
    with pytest.raises(ValidationError):
        SamplingDetail(
            sampling_method=SamplingMethod.RESECTION_HOMOGENATE,
            sample_location="non-enhancing white matter",
            time_relative_to_dose="4 h post-dose",
            analytical_method="LC-MS/MS",
            residual_blood_correction=ResidualBloodCorrection.NOT_APPLICABLE,
        )


def test_a_plasma_draw_may_declare_residual_blood_correction_not_applicable():
    d = SamplingDetail(
        sampling_method=SamplingMethod.BLOOD_DRAW, sample_location="peripheral vein",
        time_relative_to_dose="2 h post-dose", analytical_method="LC-MS/MS",
        residual_blood_correction=ResidualBloodCorrection.NOT_APPLICABLE,
    )
    assert d.residual_blood_correction is ResidualBloodCorrection.NOT_APPLICABLE


def test_not_reported_residual_blood_is_legal_and_is_not_the_same_as_applied():
    d = _sampling(residual_blood_correction=ResidualBloodCorrection.NOT_REPORTED)
    assert d.residual_blood_correction is ResidualBloodCorrection.NOT_REPORTED


# ------------------------------------------------------------------- microdialysis

def test_microdialysis_must_state_its_probe_recovery():
    """A dialysate concentration is not an interstitial concentration until it is divided by
    probe recovery. An uncalibrated microdialysis number is not a measurement of the brain."""
    with pytest.raises(ValidationError):
        SamplingDetail(
            sampling_method=SamplingMethod.MICRODIALYSIS,
            sample_location="peritumoral brain",
            time_relative_to_dose="0-6 h",
            analytical_method="LC-MS/MS",
            residual_blood_correction=ResidualBloodCorrection.NOT_APPLICABLE,
        )


def test_microdialysis_with_a_reported_recovery_needs_the_method_and_the_value():
    with pytest.raises(ValidationError):
        SamplingDetail(
            sampling_method=SamplingMethod.MICRODIALYSIS,
            sample_location="peritumoral brain", time_relative_to_dose="0-6 h",
            analytical_method="LC-MS/MS",
            residual_blood_correction=ResidualBloodCorrection.NOT_APPLICABLE,
            microdialysis_recovery_state="reported",
        )


def test_a_calibrated_microdialysis_sample_is_legal():
    d = SamplingDetail(
        sampling_method=SamplingMethod.MICRODIALYSIS,
        sample_location="peritumoral brain", time_relative_to_dose="0-6 h",
        analytical_method="LC-MS/MS",
        residual_blood_correction=ResidualBloodCorrection.NOT_APPLICABLE,
        microdialysis_recovery_state="reported",
        microdialysis_recovery_source_string="0.18",
        microdialysis_recovery_method="retrodialysis by drug loss",
    )
    assert d.microdialysis_recovery_source_string == "0.18"


def test_microdialysis_recovery_may_be_explicitly_not_reported():
    """An honest hole. The number stays usable but the reader can see what is missing."""
    d = SamplingDetail(
        sampling_method=SamplingMethod.MICRODIALYSIS,
        sample_location="peritumoral brain", time_relative_to_dose="0-6 h",
        analytical_method="LC-MS/MS",
        residual_blood_correction=ResidualBloodCorrection.NOT_APPLICABLE,
        microdialysis_recovery_state="not_reported",
    )
    assert d.microdialysis_recovery_state == "not_reported"


# ------------------------------------------------------- the measurement carries them

def test_an_exposure_measurement_carries_its_pk_detail_and_sampling_detail():
    m = _m(
        pk_detail=PkDetail(pk_metric=PkMetric.CMAX, statistic=Statistic.MEDIAN, sample_size=8,
                           variability_kind=VariabilityKind.RANGE,
                           variability_source_string="120-410"),
        sampling=_sampling(),
        co_medications=["dexamethasone 4 mg bid", "levetiracetam"],
        assay_method="LC-MS/MS, validated per FDA BMV",
    )
    assert m.pk_detail is not None and m.pk_detail.pk_metric is PkMetric.CMAX
    assert m.sampling is not None
    assert m.co_medications == ["dexamethasone 4 mg bid", "levetiracetam"]


def test_plasma_and_blood_remain_distinct_matrices():
    """A whole-blood concentration and a plasma concentration differ by the blood:plasma
    ratio. The audit asks for the distinction explicitly; it already exists and must stay."""
    assert _m(matrix="plasma").matrix == "plasma"
    assert _m(matrix="blood").matrix == "blood"


# --------------------------------------------- the CSF firewall is not weakened by v2

def test_a_richer_csf_row_still_cannot_report_a_brain_kp_uu():
    """Grossman: the blood-CSF barrier is not the BBB. Adding sampling detail to a CSF row
    does not turn it into a brain measurement."""
    with pytest.raises(ValidationError):
        _m(matrix="csf", enhancement_context="not_applicable",
           kp_uu_brain_reported_source_string="0.4",
           sampling=SamplingDetail(
               sampling_method=SamplingMethod.CSF_DRAW, sample_location="lumbar CSF",
               time_relative_to_dose="4 h", analytical_method="LC-MS/MS",
               residual_blood_correction=ResidualBloodCorrection.NOT_APPLICABLE))
