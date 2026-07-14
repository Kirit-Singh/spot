"""Unbound exposure and brain:plasma ratios — where an inference can pass for a measurement.

Grossman 2026 is explicit: total brain-to-plasma ratios can mislead; total AND unbound
concentrations should be measured; the unbound brain-to-plasma ratio (Kp,uu) is the important
one. That makes fu and Kp,uu the two most dangerous numbers in Stage 4, because both are
usually CALCULATED and both look exactly like measurements once written down.

So the contract forces the distinction to be structural:

  * `basis` — `reported` means the SOURCE printed this ratio. `derived` means someone computed
    it, and must say from WHICH measurements and by WHAT transform.
  * `binding_state_basis` — a free concentration that was actually measured, and one obtained
    by multiplying a total concentration by a plasma fu, are not the same evidence. The second
    inherits every assumption in the fu.
  * CSF still cannot supply a brain Kp,uu, however richly it is annotated.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from analysis.evidence_records import EvidenceType, ExposureMeasurement, Provenance
from analysis.pk_records import (
    FractionUnboundRecord,
    RatioReport,
    UnboundDerivation,
)

PROV = Provenance(source_record_id="src.test", access_date="2026-07-11",
                  raw_response_sha256="0" * 64, extraction_transform="table 2")


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


def _fu(**over) -> FractionUnboundRecord:
    base = dict(
        fraction_unbound_id="fu.plasma.M1",
        candidate_id="C1", active_moiety_id="M1", matrix="plasma",
        value_source_string="0.11", method="equilibrium dialysis",
        species="human", concentration_dependence="independent", provenance=PROV,
    )
    base.update(over)
    return FractionUnboundRecord(**base)


# ------------------------------------------------------------------- fraction unbound

def test_a_fraction_unbound_is_a_source_bound_observation_with_its_own_method_and_species():
    fu = _fu()
    assert fu.method == "equilibrium dialysis"
    assert fu.species == "human"
    assert fu.provenance.raw_response_sha256 == "0" * 64


def test_a_fraction_unbound_must_be_a_fraction():
    """fu is bounded by 0 and 1 by definition. A '11' that meant 11% is the classic error,
    and it inflates every unbound concentration derived from it by 100x."""
    with pytest.raises(ValidationError):
        _fu(value_source_string="11")
    with pytest.raises(ValidationError):
        _fu(value_source_string="0")
    with pytest.raises(ValidationError):
        _fu(value_source_string="-0.1")
    assert _fu(value_source_string="1").quantity.decimal == 1


def test_concentration_dependence_is_explicit():
    """A concentration-dependent fu measured at one concentration does not licence an unbound
    conversion at another."""
    assert _fu(concentration_dependence="dependent").concentration_dependence == "dependent"
    assert _fu(concentration_dependence="not_reported").concentration_dependence == "not_reported"
    with pytest.raises(ValidationError):
        _fu(concentration_dependence="probably_fine")


def test_plasma_and_brain_fu_are_different_records():
    """fu,plasma and fu,brain are different numbers and Kp,uu needs both. Collapsing them is
    how a Kp,uu comes out wrong by an order of magnitude."""
    assert _fu(matrix="plasma").matrix == "plasma"
    assert _fu(fraction_unbound_id="fu.brain.M1", matrix="brain").matrix == "brain"


# ------------------------------------------------------- a derived free concentration

def test_a_measured_free_concentration_is_the_default_and_is_the_v1_reading():
    """A v1 row said binding_state='free' and meant 'the source reported a free
    concentration'. That must remain what it means."""
    assert _m().binding_state_basis == "measured"
    assert _m().unbound_derivation is None


def test_a_derived_free_concentration_must_name_its_inputs_and_its_transform():
    """C_free = C_total * fu is an INFERENCE. It inherits every assumption in the fu, and the
    audit requires 'both source-bound inputs and the exact declared transform'."""
    with pytest.raises(ValidationError):
        _m(binding_state_basis="derived_from_fraction_unbound")


def test_a_derived_free_concentration_with_inputs_and_transform_is_legal():
    m = _m(
        binding_state_basis="derived_from_fraction_unbound",
        unbound_derivation=UnboundDerivation(
            from_measurement_id="EXP-TOTAL-1",
            fraction_unbound_id="fu.plasma.M1",
            transform="C_free = C_total * fu_plasma",
        ),
    )
    assert m.unbound_derivation is not None
    assert m.unbound_derivation.transform == "C_free = C_total * fu_plasma"


def test_a_derivation_on_a_total_concentration_is_incoherent():
    """You do not derive an UNBOUND concentration and then call it total."""
    with pytest.raises(ValidationError):
        _m(binding_state="total",
           binding_state_basis="derived_from_fraction_unbound",
           unbound_derivation=UnboundDerivation(
               from_measurement_id="EXP-TOTAL-1",
               fraction_unbound_id="fu.plasma.M1",
               transform="C_free = C_total * fu_plasma"))


def test_a_measured_row_must_not_smuggle_a_derivation():
    with pytest.raises(ValidationError):
        _m(unbound_derivation=UnboundDerivation(
            from_measurement_id="EXP-TOTAL-1",
            fraction_unbound_id="fu.plasma.M1",
            transform="C_free = C_total * fu_plasma"))


# --------------------------------------------------------- reported vs derived ratios

def test_a_reported_ratio_is_the_sources_own_number():
    r = RatioReport(basis="reported", value_source_string="0.32")
    assert r.basis == "reported"
    assert r.derivation_transform is None


def test_a_reported_ratio_may_not_carry_a_derivation_transform():
    """If you computed it, it is not what the source reported. That is the entire
    distinction, and letting both be true at once erases it."""
    with pytest.raises(ValidationError):
        RatioReport(basis="reported", value_source_string="0.32",
                    derivation_transform="Kp = C_brain / C_plasma")


def test_a_derived_ratio_must_declare_its_transform_and_its_inputs():
    with pytest.raises(ValidationError):
        RatioReport(basis="derived", value_source_string="0.32")
    with pytest.raises(ValidationError):
        RatioReport(basis="derived", value_source_string="0.32",
                    derivation_transform="Kp = C_brain / C_plasma")


def test_a_derived_ratio_with_transform_and_inputs_is_legal():
    r = RatioReport(basis="derived", value_source_string="0.32",
                    derivation_transform="Kp = C_brain / C_plasma",
                    input_measurement_ids=["EXP-BRAIN-1", "EXP-PLASMA-1"])
    assert r.input_measurement_ids == ["EXP-BRAIN-1", "EXP-PLASMA-1"]


def test_a_derived_kp_uu_must_also_name_the_fraction_unbound_records_it_used():
    """Kp,uu = (C_brain * fu_brain) / (C_plasma * fu_plasma). Deriving one without naming the
    fu records is asserting an unbound ratio from total concentrations."""
    with pytest.raises(ValidationError):
        RatioReport(ratio_kind="kp_uu_brain", basis="derived", value_source_string="0.32",
                    derivation_transform="Kp,uu = (C_b * fu_b) / (C_p * fu_p)",
                    input_measurement_ids=["EXP-BRAIN-1", "EXP-PLASMA-1"])


def test_a_derived_kp_uu_naming_its_fu_records_is_legal():
    r = RatioReport(ratio_kind="kp_uu_brain", basis="derived", value_source_string="0.32",
                    derivation_transform="Kp,uu = (C_b * fu_b) / (C_p * fu_p)",
                    input_measurement_ids=["EXP-BRAIN-1", "EXP-PLASMA-1"],
                    fraction_unbound_ids=["fu.brain.M1", "fu.plasma.M1"])
    assert r.fraction_unbound_ids == ["fu.brain.M1", "fu.plasma.M1"]


def test_the_measurement_carries_kp_and_kp_uu_as_separate_reported_or_derived_ratios():
    m = _m(
        kp=RatioReport(basis="reported", value_source_string="0.9"),
        kp_uu_brain=RatioReport(basis="derived", ratio_kind="kp_uu_brain",
                                value_source_string="0.32",
                                derivation_transform="Kp,uu = (C_b * fu_b) / (C_p * fu_p)",
                                input_measurement_ids=["EXP-BRAIN-1", "EXP-PLASMA-1"],
                                fraction_unbound_ids=["fu.brain.M1", "fu.plasma.M1"]),
    )
    assert m.kp is not None and m.kp.basis == "reported"
    assert m.kp_uu_brain is not None and m.kp_uu_brain.basis == "derived"


# --------------------------------------------------- the CSF firewall holds against v2

def test_csf_cannot_carry_a_derived_brain_kp_uu_either():
    """The v1 firewall blocked `kp_uu_brain_reported_source_string` on a CSF row. The v2
    structured field must not become a way around it."""
    with pytest.raises(ValidationError):
        _m(matrix="csf", enhancement_context="not_applicable",
           kp_uu_brain=RatioReport(ratio_kind="kp_uu_brain", basis="derived",
                                   value_source_string="0.4",
                                   derivation_transform="Kp,uu = C_csf / (C_p * fu_p)",
                                   input_measurement_ids=["EXP-CSF-1", "EXP-PLASMA-1"],
                                   fraction_unbound_ids=["fu.plasma.M1"]))


def test_csf_cannot_carry_a_reported_brain_kp_uu_via_the_structured_field():
    with pytest.raises(ValidationError):
        _m(matrix="csf", enhancement_context="not_applicable",
           kp_uu_brain=RatioReport(ratio_kind="kp_uu_brain", basis="reported",
                                   value_source_string="0.4"))


def test_the_v1_and_v2_kp_fields_may_not_disagree():
    """Two representations of one number is two chances to state it differently. If a row
    carries both, they must be the same string."""
    with pytest.raises(ValidationError):
        _m(kp_reported_source_string="0.9",
           kp=RatioReport(basis="reported", value_source_string="0.4"))


def test_the_v1_and_v2_kp_fields_agreeing_is_fine():
    m = _m(kp_reported_source_string="0.9",
           kp=RatioReport(basis="reported", value_source_string="0.9"))
    assert m.kp is not None
