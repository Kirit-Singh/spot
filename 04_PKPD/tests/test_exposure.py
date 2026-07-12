"""Exposure margins: every gate that must block one, and why."""

from __future__ import annotations

import pytest

from analysis.contracts import EvidenceContext
from pydantic import ValidationError

from analysis.evidence_records import (
    EvidenceType,
    ExposureMeasurement,
    PotencyContextLink,
    PotencyRecord,
    Provenance,
)
from analysis.exposure import compute_exposure_margin

PROV = Provenance(source_record_id="src.test", access_date="2026-07-11",
                  raw_response_sha256="0" * 64, extraction_transform="test")

CTX = EvidenceContext(context_id="CTX-1", candidate_id="C1", active_moiety_id="M1", route="oral",
                      formulation="tablet", dose="100 mg", schedule="once daily",
                      tumor_context="GBM_test")


def measurement(**kw) -> ExposureMeasurement:
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


def potency(**kw) -> PotencyRecord:
    base = dict(
        potency_id="POT-1", candidate_id="C1", active_moiety_id="M1", metric="MEC",
        value_source_string="100", units="nM", binding_state="free", assay="viability",
        biological_context="GBM_test", evidence_type=EvidenceType.IN_VITRO, provenance=PROV,
    )
    base.update(kw)
    return PotencyRecord(**base)


def link(**kw) -> PotencyContextLink:
    base = dict(link_id="LNK-1", potency_id="POT-1", tumor_context="GBM_test",
                rationale="sourced relevance review", provenance=PROV)
    base.update(kw)
    return PotencyContextLink(**base)


def test_margin_is_computed_when_everything_lines_up():
    r = compute_exposure_margin(measurement(), potency(), CTX)
    assert r.status == "computed"
    assert r.margin == pytest.approx(2.5)
    assert r.margin_canonical_decimal == "2.5E+0"
    assert r.harmonized_units == "nM"
    assert "250 nM" in r.transform and "100 nM" in r.transform


def test_tiny_distinct_concentrations_do_not_collapse():
    """1e-12 and 4e-11 are different concentrations. A 10-decimal float grid made them
    the same; exact decimals keep them apart."""
    a = measurement(measurement_id="EXP-A", concentration_source_string="1e-12", concentration_units="M")
    b = measurement(measurement_id="EXP-B", concentration_source_string="4e-11", concentration_units="M")
    ma = compute_exposure_margin(a, potency(), CTX)
    mb = compute_exposure_margin(b, potency(), CTX)
    assert ma.status == mb.status == "computed"
    assert ma.margin_canonical_decimal != mb.margin_canonical_decimal
    assert a.quantity.canonical_decimal != b.quantity.canonical_decimal


def test_total_tissue_against_free_potency_is_refused():
    """The silent category error this gate exists for."""
    r = compute_exposure_margin(measurement(binding_state="total"), potency(binding_state="free"), CTX)
    assert r.status == "not_computable"
    assert r.reason_code == "free_total_mismatch"
    assert r.margin is None


def test_unspecified_binding_state_is_refused():
    r = compute_exposure_margin(measurement(binding_state="unspecified"), potency(), CTX)
    assert r.reason_code == "binding_state_unspecified"


def test_unit_family_mismatch_blocks_the_margin():
    """ng/mL vs nM needs a molecular weight and a declared transform. Not implicit."""
    r = compute_exposure_margin(measurement(concentration_units="ng/mL"), potency(units="nM"), CTX)
    assert r.status == "not_computable"
    assert r.reason_code == "unit_family_mismatch"


def test_an_ic50_is_not_an_admissible_margin_denominator():
    r = compute_exposure_margin(measurement(), potency(metric="IC50"), CTX)
    assert r.status == "not_computable"
    assert r.reason_code == "potency_metric_not_a_target_concentration"


def test_units_are_harmonized_within_a_family():
    r = compute_exposure_margin(
        measurement(concentration_source_string="0.25", concentration_units="uM"), potency(), CTX)
    assert r.status == "computed"
    assert r.margin == pytest.approx(2.5)


def test_unrecognized_units_are_refused():
    """An unknown unit cannot even become a record."""
    with pytest.raises(ValidationError, match="unsupported unit"):
        measurement(concentration_units="squiggles")


def test_salt_prodrug_or_metabolite_mismatch_blocks_the_join():
    """The potency is for a different molecule than the exposure."""
    r = compute_exposure_margin(measurement(), potency(active_moiety_id="M1-HCl"), CTX)
    assert r.status == "not_computable"
    assert r.reason_code == "active_moiety_mismatch"
    assert "not the same molecule" in r.reason


def test_a_measurement_for_another_moiety_never_reaches_the_potency_gate():
    """It is stopped earlier still: it does not belong to this context at all."""
    r = compute_exposure_margin(measurement(active_moiety_id="M1-HCl"), potency(), CTX)
    assert r.status == "not_computable"
    assert r.reason_code == "context_disagreement"
    assert "active_moiety_id" in r.reason


def test_unknown_route_dose_or_schedule_blocks_the_margin():
    """The measurement and its context agree — they agree that the regimen is unknown."""
    for field in ("route", "dose", "schedule"):
        ctx = CTX.model_copy(update={field: "unknown"})
        r = compute_exposure_margin(measurement(**{field: "unknown"}), potency(), ctx)
        assert r.reason_code == "dosing_context_unknown", field


def test_potency_from_an_irrelevant_biological_context_is_refused():
    r = compute_exposure_margin(measurement(), potency(biological_context="breast_cancer_line"), CTX)
    assert r.status == "not_computable"
    assert r.reason_code == "potency_context_not_relevant"


def test_cross_context_potency_needs_an_explicit_sourced_link():
    r = compute_exposure_margin(measurement(), potency(biological_context="glioma_line_x"), CTX,
                                [link()])
    assert r.status == "computed"
    assert r.potency_context_link_id == "LNK-1"
    assert "potency_applied_via_sourced_relevance_link" in r.caveats


def test_csf_measurement_is_flagged_as_not_neb():
    r = compute_exposure_margin(measurement(matrix="csf", enhancement_context="not_applicable"), potency(), CTX)
    assert "csf_is_not_non_enhancing_brain" in r.caveats
    # the SENTENCE for the code is method data (method/stage4_prose_v1.json), so it is bound
    # into the release identity rather than typed into the engine
    from analysis.method_config import load_method_bundle
    text = load_method_bundle().prose["exposure"]["caveat_codes"]["csf_is_not_non_enhancing_brain"]
    assert "cannot satisfy an NEBPI branch" in text


def test_kp_uu_brain_can_never_be_attached_to_a_csf_measurement():
    """Kp,uu,brain is never inferred from CSF — the record itself refuses to exist."""
    with pytest.raises(ValidationError, match="must not be set on a CSF measurement"):
        measurement(matrix="csf", enhancement_context="not_applicable",
                    kp_uu_brain_reported_source_string="0.3")


def test_kp_values_are_carried_only_when_the_source_reports_them():
    m = measurement(kp_reported_source_string="0.2", kp_uu_brain_reported_source_string="0.05")
    assert m.kp_reported_source_string == "0.2"
    assert m.kp_uu_brain_reported_source_string == "0.05"
    assert measurement().kp_reported_source_string is None


def test_a_measurement_must_agree_with_the_context_it_names():
    """The audit compared an IV 999-g measurement against an oral 150-mg context."""
    r = compute_exposure_margin(
        measurement(route="intravenous", dose="999 g"), potency(), CTX)
    assert r.status == "not_computable"
    assert r.reason_code == "context_disagreement"
    assert "route" in r.reason and "dose" in r.reason


def test_an_undetected_concentration_has_no_margin_but_is_still_an_observation():
    m = measurement(concentration_source_string=None, concentration_units=None,
                    detection_status="not_detected")
    r = compute_exposure_margin(m, potency(), CTX)
    assert r.status == "not_computable"
    assert r.reason_code == "no_quantified_concentration"
    assert r.detection_status == "not_detected"


def test_enhancing_tissue_measurement_is_flagged():
    r = compute_exposure_margin(
        measurement(matrix="brain_tissue_enhancing", enhancement_context="enhancing"), potency(), CTX
    )
    assert "measured_in_enhancing_tissue" in r.caveats


def test_no_potency_record_means_no_margin():
    r = compute_exposure_margin(measurement(), None, CTX)
    assert r.status == "not_computable"
    assert r.reason_code == "no_potency_record"


def test_concentration_without_units_is_impossible_at_the_record_level():
    with pytest.raises(ValidationError, match="concentration without units"):
        measurement(concentration_units=None)
