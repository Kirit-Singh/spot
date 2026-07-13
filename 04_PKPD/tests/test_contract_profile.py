"""The v2 profile: what "acquisition-complete" actually requires, checked row by row.

A schema that DECLARES a field and never requires it has not added a rule — it has added a
place to put a null. The audit's whole complaint about Stage 4 was that it could parse cached
bytes and validate a preassembled bundle, but could not show how any of it was obtained. A v2
bundle that validates against the models while leaving every acquisition field empty would
reproduce that complaint exactly, one schema version later.

So `contract_profile.py` is the gate. A v1 bundle passes it trivially and is marked NOT
acquisition-complete. A v2 bundle must actually carry the contract: every source acquired with
a canonical query and an adapter build, every potency bound to an assay record, every exposure
saying what kind of number it is, every fu owned by the candidate that uses it, every derived
ratio naming its inputs.
"""

from __future__ import annotations

import pytest

from analysis.contract_profile import (
    ProfileViolation,
    contract_violations,
    is_acquisition_complete,
)
from analysis.contract_version import ContractVersion
from analysis.pk_records import FractionUnboundRecord, RatioReport


@pytest.fixture
def v1():
    import fixtures as fx
    return fx.stage4_inputs()


@pytest.fixture
def v2():
    import fixtures as fx
    return fx.stage4_inputs_v2()


# ------------------------------------------------------------------------------ v1

def test_a_v1_bundle_satisfies_its_own_contract_and_is_not_acquisition_complete(v1):
    """v1 is a legitimate contract. It is simply not a claim that anything was acquired."""
    assert contract_violations(v1) == []
    assert is_acquisition_complete(v1) is False


def test_a_v1_bundle_may_not_smuggle_v2_rows(v1):
    """Declaring v1 and carrying an acquisition manifest is trying to have it both ways: the
    v1 digest (which does not cover those rows) with the v2 claim."""
    import fixtures as fx
    v1.acquisitions = fx.acquisitions()
    violations = contract_violations(v1)
    assert any(v.code == "v1_bundle_carries_v2_rows" for v in violations), violations


# ------------------------------------------------------------------------------ v2

def test_the_v2_fixture_is_acquisition_complete(v2):
    assert contract_violations(v2) == [], contract_violations(v2)
    assert is_acquisition_complete(v2) is True


def test_v2_requires_an_acquisition_record_for_every_source_that_carries_bytes(v2):
    # W8's record keys on `source_key`, which is its join to the source registry.
    v2.acquisitions = [a for a in v2.acquisitions
                       if a.source_key != "src.fixture.potency"]
    codes = {v.code for v in contract_violations(v2)}
    assert "source_not_acquired" in codes


def test_v2_requires_every_potency_to_carry_its_assay_binding(v2):
    v2.potencies = [p.model_copy(update={"assay_binding": None}) for p in v2.potencies]
    codes = {v.code for v in contract_violations(v2)}
    assert "potency_without_assay_binding" in codes


def test_v2_requires_the_structured_activity_and_document_ids_not_just_an_organism(v2):
    p = v2.potencies[0]
    v2.potencies[0] = p.model_copy(update={
        "assay_binding": p.assay_binding.model_copy(update={"activity_id": None,
                                                            "document_id": None})})
    codes = {v.code for v in contract_violations(v2)}
    assert "potency_assay_binding_incomplete" in codes


def test_v2_requires_every_exposure_to_say_what_kind_of_number_it_is(v2):
    v2.exposures = [m.model_copy(update={"pk_detail": None}) for m in v2.exposures]
    codes = {v.code for v in contract_violations(v2)}
    assert "exposure_without_pk_detail" in codes


def test_v2_requires_every_exposure_to_say_how_it_was_sampled(v2):
    v2.exposures = [m.model_copy(update={"sampling": None}) for m in v2.exposures]
    codes = {v.code for v in contract_violations(v2)}
    assert "exposure_without_sampling_detail" in codes


# ------------------------------------------- fraction unbound: uniqueness and ownership

def test_a_duplicate_fraction_unbound_id_is_refused(v2):
    """Two rows with one id means something downstream gets to PICK, which is how a Kp,uu comes
    out depending on list order."""
    v2.fraction_unbound = list(v2.fraction_unbound) + [v2.fraction_unbound[0]]
    codes = {v.code for v in contract_violations(v2)}
    assert "duplicate_fraction_unbound_id" in codes


def test_two_fu_rows_for_one_moiety_and_matrix_are_refused(v2):
    """One moiety has one fu,plasma in one species. Two would let a reader choose which
    unbound concentration the evidence rests on."""
    dup = v2.fraction_unbound[0].model_copy(update={"fraction_unbound_id": "FU-PLASMA-ALT"})
    v2.fraction_unbound = list(v2.fraction_unbound) + [dup]
    codes = {v.code for v in contract_violations(v2)}
    assert "ambiguous_fraction_unbound_for_moiety_matrix" in codes


def test_an_fu_belonging_to_another_moiety_cannot_be_used(v2):
    """Ownership. A fraction unbound measured for a DIFFERENT molecule is not this molecule's
    fu, and using one would misstate every unbound concentration derived from it."""
    alien = FractionUnboundRecord(
        fraction_unbound_id="FU-ALIEN", candidate_id="FIXTURE-002",
        active_moiety_id="FXM-002", matrix="plasma", value_source_string="0.5",
        method="fixture", species="human", concentration_dependence="independent",
        provenance=v2.fraction_unbound[0].provenance)
    v2.fraction_unbound = list(v2.fraction_unbound) + [alien]
    m = v2.exposures[0]  # FIXTURE-001 / FXM-001
    v2.exposures[0] = m.model_copy(update={
        "binding_state": "free",
        "binding_state_basis": "derived_from_fraction_unbound",
        "unbound_derivation": __import__(
            "analysis.pk_records", fromlist=["UnboundDerivation"]).UnboundDerivation(
                from_measurement_id="EXP-001B", fraction_unbound_id="FU-ALIEN",
                transform="C_free = C_total * fu")})
    codes = {v.code for v in contract_violations(v2)}
    assert "fraction_unbound_moiety_mismatch" in codes


def test_an_unbound_derivation_naming_a_nonexistent_fu_is_refused(v2):
    m = v2.exposures[0]
    v2.exposures[0] = m.model_copy(update={
        "binding_state": "free",
        "binding_state_basis": "derived_from_fraction_unbound",
        "unbound_derivation": __import__(
            "analysis.pk_records", fromlist=["UnboundDerivation"]).UnboundDerivation(
                from_measurement_id="EXP-001B", fraction_unbound_id="FU-DOES-NOT-EXIST",
                transform="C_free = C_total * fu")})
    codes = {v.code for v in contract_violations(v2)}
    assert "unbound_derivation_unbound_fu" in codes


def test_every_fraction_unbound_row_must_rest_on_an_acquired_source(v2):
    """Same rule as every other evidence row: a number that cites a source must cite one that
    exists and whose bytes hash to what the row declares."""
    bad = v2.fraction_unbound[0]
    v2.fraction_unbound = [bad.model_copy(update={
        "provenance": bad.provenance.model_copy(
            update={"source_record_id": "src.DOES_NOT_EXIST"})})]
    codes = {v.code for v in contract_violations(v2)}
    assert "fraction_unbound_source_unbound" in codes


# ------------------------------------------------------- derived ratios name real rows

def test_a_derived_ratio_citing_a_nonexistent_measurement_is_refused(v2):
    m = v2.exposures[0]
    v2.exposures[0] = m.model_copy(update={
        "kp": RatioReport(basis="derived", value_source_string="0.3",
                          derivation_transform="Kp = C_brain / C_plasma",
                          input_measurement_ids=["EXP-GHOST"])})
    codes = {v.code for v in contract_violations(v2)}
    assert "ratio_input_measurement_unbound" in codes


def test_a_paired_plasma_id_must_resolve_to_a_real_plasma_measurement(v2):
    m = v2.exposures[0]
    v2.exposures[0] = m.model_copy(update={"paired_plasma_measurement_id": "EXP-001C"})
    codes = {v.code for v in contract_violations(v2)}
    assert "paired_plasma_is_not_plasma" in codes


def test_a_paired_plasma_id_that_names_nothing_is_refused(v2):
    m = v2.exposures[0]
    v2.exposures[0] = m.model_copy(update={"paired_plasma_measurement_id": "EXP-GHOST"})
    codes = {v.code for v in contract_violations(v2)}
    assert "paired_plasma_unbound" in codes


# --------------------------------------------------------------- violations are typed

def test_a_violation_carries_a_stable_code_and_the_row_it_is_about(v2):
    v2.potencies = [p.model_copy(update={"assay_binding": None}) for p in v2.potencies]
    v = contract_violations(v2)[0]
    assert isinstance(v, ProfileViolation)
    assert v.code and v.row_id and v.detail
    assert v.contract is ContractVersion.V2
