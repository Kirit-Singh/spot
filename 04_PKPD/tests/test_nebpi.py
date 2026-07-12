"""NEBPI Part-II logic (Grossman et al., Neuro-Oncology 2026, doi:10.1093/neuonc/noag051).

The Part-II definitions transcribed independently from Table 2 of the source:

  Sufficiently permeable   = PK with therapeutic levels in NEB(a)  OR  relevant PD
                             effect in NEB  OR  radiographic responses in NEB
  Insufficiently permeable = Low PK levels in NEB(a)  AND  no relevant PD in NEB
                             AND  no radiographic response in NEB
  Impermeable              = Little to no drug in NEB(a)  AND  no relevant PD in NEB
                             AND  no radiographic response in NEB
  (a) = "Accounting for potency."

Part I grades physical characteristics / normal-animal-brain permeability / known MEC /
PK-in-NEB / PD-in-NEB as importance A; CSF levels and responses in enhancing lesions as
C; in-vitro BBB models as D ("graded from A (best) to F (worst)").
"""

from __future__ import annotations

import pytest

from analysis.contracts import EvidenceContext
from analysis.delivery import resolve_delivery_requirement
from analysis.evidence_records import (
    DeliveryAssignment,
    DeliveryBasis,
    DeliveryRequirement,
    EvidenceType,
    ExposureMeasurement,
    NebpiCriterionId,
    NebpiObservation,
    ObservationState,
    PotencyRecord,
    Provenance,
)
from analysis.method_config import load_method_bundle
from analysis.nebpi import evaluate_nebpi

METHOD = load_method_bundle()
NEBPI = METHOD.nebpi
RULES = METHOD.delivery_rules

PROV = Provenance(source_record_id="src.test", access_date="2026-07-11",
                  raw_response_sha256="0" * 64, extraction_transform="test")

POTENCY = PotencyRecord(
    potency_id="POT-1", candidate_id="C1", active_moiety_id="M1", metric="MEC",
    value_source_string="100", units="nM", binding_state="free", assay="test",
    biological_context="GBM_test", evidence_type=EvidenceType.IN_VITRO, provenance=PROV,
)


def measurement(mid: str, conc: str | None, *, context_id: str = "CTX-1",
                detection: str = "quantified", matrix: str = "brain_tissue_non_enhancing",
                enhancement: str = "non_enhancing", binding: str = "free",
                moiety: str = "M1", route: str = "oral", formulation: str = "tablet",
                dose: str = "100 mg", schedule: str = "once daily",
                limit_kind: str | None = None, limit: str | None = None,
                limit_units: str | None = "nM") -> ExposureMeasurement:
    """A real NEB measurement. The PK level is derived from this, never asserted."""
    return ExposureMeasurement(
        measurement_id=mid, candidate_id="C1", active_moiety_id=moiety, context_id=context_id,
        formulation=formulation, route=route, dose=dose, schedule=schedule,
        species_population="adult", matrix=matrix, enhancement_context=enhancement,
        binding_state=binding, concentration_source_string=conc,
        concentration_units="nM" if conc is not None else None,
        detection_status=detection,
        quantitation_limit_kind=limit_kind,
        quantitation_limit_source_string=limit,
        quantitation_limit_units=limit_units if limit is not None else None,
        evidence_type=EvidenceType.HUMAN_CLINICAL, provenance=PROV,
    )


# 500 nM vs MEC 100 nM -> margin 5 -> therapeutic. 40 nM -> margin 0.4 -> low.
THERAPEUTIC = measurement("EXP-THER", "500")
LOW = measurement("EXP-LOW", "40")
# Not detected, by an assay that could see down to 1 nM — a hundredfold below the 100 nM
# MEC. Only THAT makes "little to no drug in NEB" a statement about the drug rather than
# about the assay (Table 2 footnote a).
NONE_DETECTED = measurement("EXP-NONE", None, detection="not_detected",
                            limit_kind="lod", limit="1")
# Same non-detect, from an assay too blunt to exclude the MEC. Bounds nothing.
NONE_DETECTED_BLUNT = measurement("EXP-BLUNT", None, detection="not_detected",
                                  limit_kind="lod", limit="500")
# Not detected, and the source never said how low the assay could see.
NONE_DETECTED_UNBOUNDED = measurement("EXP-UNB", None, detection="not_detected")


def ctx(context_id: str = "CTX-1", **kw) -> EvidenceContext:
    base = dict(context_id=context_id, candidate_id="C1", active_moiety_id="M1", route="oral",
                formulation="tablet", dose="100 mg", schedule="once daily", tumor_context="GBM_test")
    base.update(kw)
    return EvidenceContext(**base)


def obs(criterion: NebpiCriterionId, state: ObservationState, context_id: str = "CTX-1",
        oid: str | None = None, **kw) -> NebpiObservation:
    return NebpiObservation(
        observation_id=oid or f"O-{criterion.value}-{context_id}", candidate_id="C1",
        context_id=context_id, criterion_id=criterion, state=state,
        evidence_type=EvidenceType.HUMAN_CLINICAL, provenance=PROV, **kw,
    )


def delivery(requirement=DeliveryRequirement.LOCAL_CNS, context_id="CTX-1"):
    a = DeliveryAssignment(
        assignment_id=f"DLV-{context_id}", candidate_id="C1", context_id=context_id,
        requirement=requirement,
        basis=DeliveryBasis.MECHANISM_WITH_PHARMACOLOGY_EVIDENCE, assigned_by="reviewer-1",
        rule_id="explicit_assignment_required", rule_version="1.0.0", rationale="test",
        evidence=PROV,
    )
    return resolve_delivery_requirement("C1", context_id, [a], RULES)


def run(observations, context=None, potencies=(POTENCY,), deliv=None, measurements=()):
    context = context or ctx()
    return evaluate_nebpi("C1", context, list(observations), list(potencies),
                          deliv or delivery(context_id=context.context_id), NEBPI,
                          measurements=list(measurements), potency_context_links=[])


# --------------------------------------------------------- what cannot make a class

def test_part_i_criteria_and_importance_match_the_source():
    encoded = {c["criterion_id"]: c["importance"] for c in NEBPI["part_i_criteria"]}
    assert encoded["physical_characteristics"] == "A"
    assert encoded["permeability_normal_animal_brain"] == "A"
    assert encoded["known_mec_potency"] == "A"
    assert encoded["pk_in_neb"] == "A"
    assert encoded["pd_in_neb"] == "A"
    assert encoded["csf_drug_levels"] == "C"
    assert encoded["response_in_enhancing_lesions"] == "C"
    assert encoded["in_vitro_bbb_permeability"] == "D"
    branchable = {c["criterion_id"] for c in NEBPI["part_i_criteria"] if c["can_satisfy_part_ii_branch"]}
    assert branchable == {"pk_in_neb", "pd_in_neb", "radiographic_response_in_neb"}


def test_descriptors_alone_are_not_classifiable():
    """CNS-MPO / physicochemistry is a Part-I input (importance A), not a Part-II branch."""
    r = run([obs(NebpiCriterionId.PHYSICAL_CHARACTERISTICS, ObservationState.OBSERVED_PRESENT)])
    assert r.nebpi_status == "not_classifiable"
    assert r.nebpi_class is None


def test_csf_levels_alone_are_not_classifiable():
    """The blood-CSF barrier is not the BBB. CSF is importance C and satisfies no branch."""
    r = run([obs(NebpiCriterionId.CSF_DRUG_LEVELS, ObservationState.OBSERVED_PRESENT)])
    assert r.nebpi_status == "not_classifiable"
    assert r.nebpi_class is None


def test_enhancing_lesion_response_alone_is_not_classifiable():
    """A response where the BBB is already disrupted says nothing about non-enhancing brain."""
    r = run([obs(NebpiCriterionId.RESPONSE_IN_ENHANCING_LESIONS, ObservationState.OBSERVED_PRESENT)])
    assert r.nebpi_status == "not_classifiable"
    assert r.nebpi_class is None


def test_in_vitro_bbb_and_normal_animal_brain_alone_are_not_classifiable():
    r = run([
        obs(NebpiCriterionId.IN_VITRO_BBB_PERMEABILITY, ObservationState.OBSERVED_PRESENT),
        obs(NebpiCriterionId.PERMEABILITY_NORMAL_ANIMAL_BRAIN, ObservationState.OBSERVED_PRESENT),
    ])
    assert r.nebpi_status == "not_classifiable"


def test_all_insufficient_evidence_types_together_still_not_classifiable():
    r = run([
        obs(NebpiCriterionId.PHYSICAL_CHARACTERISTICS, ObservationState.OBSERVED_PRESENT),
        obs(NebpiCriterionId.PERMEABILITY_NORMAL_ANIMAL_BRAIN, ObservationState.OBSERVED_PRESENT),
        obs(NebpiCriterionId.CSF_DRUG_LEVELS, ObservationState.OBSERVED_PRESENT),
        obs(NebpiCriterionId.RESPONSE_IN_ENHANCING_LESIONS, ObservationState.OBSERVED_PRESENT),
        obs(NebpiCriterionId.IN_VITRO_BBB_PERMEABILITY, ObservationState.OBSERVED_PRESENT),
        obs(NebpiCriterionId.KNOWN_MEC_POTENCY, ObservationState.OBSERVED_PRESENT),
    ])
    assert r.nebpi_status == "not_classifiable"
    assert r.nebpi_class is None


def test_no_evidence_at_all_is_not_classifiable_and_never_impermeable():
    r = run([])
    assert r.nebpi_status == "not_classifiable"
    assert r.nebpi_class is None
    assert r.counterfactual["hard_rule"] == "Absent or unknown evidence is never 'impermeable'."


# ------------------------------------------------ the three qualifying positives (OR)

def test_therapeutic_pk_in_neb_gives_sufficiently_permeable():
    """500 nM measured in NEB against a 100 nM MEC. The level is DERIVED, not asserted."""
    r = run([
        obs(NebpiCriterionId.KNOWN_MEC_POTENCY, ObservationState.OBSERVED_PRESENT),
        obs(NebpiCriterionId.PK_IN_NEB, ObservationState.OBSERVED_PRESENT,
            measurement_id="EXP-THER", potency_id="POT-1"),
    ], measurements=[THERAPEUTIC])
    assert r.nebpi_class == "sufficiently_permeable"
    assert r.nebpi_status == "classified"
    satisfied = [b.branch_id for b in r.branch_proof if b.satisfied]
    assert "pk_therapeutic_in_neb" in satisfied
    assert r.pk_derivation["derived_level"] == "pk_therapeutic_in_neb"
    assert r.pk_derivation["margin_canonical_decimal"] == "5E+0"


def test_pd_in_neb_alone_gives_sufficiently_permeable():
    r = run([obs(NebpiCriterionId.PD_IN_NEB, ObservationState.OBSERVED_PRESENT)])
    assert r.nebpi_class == "sufficiently_permeable"


def test_radiographic_response_in_neb_alone_gives_sufficiently_permeable():
    """The source's temozolomide case: responses in NEB establish the class even though
    brain levels are only ~20% of blood."""
    r = run([obs(NebpiCriterionId.RADIOGRAPHIC_RESPONSE_IN_NEB, ObservationState.OBSERVED_PRESENT)])
    assert r.nebpi_class == "sufficiently_permeable"


def test_qualifying_positive_wins_over_low_pk():
    r = run([
        obs(NebpiCriterionId.KNOWN_MEC_POTENCY, ObservationState.OBSERVED_PRESENT),
        obs(NebpiCriterionId.PK_IN_NEB, ObservationState.OBSERVED_PRESENT,
            measurement_id="EXP-LOW", potency_id="POT-1"),
        obs(NebpiCriterionId.RADIOGRAPHIC_RESPONSE_IN_NEB, ObservationState.OBSERVED_PRESENT),
    ], measurements=[LOW])
    assert r.nebpi_class == "sufficiently_permeable"
    assert r.pk_derivation["derived_level"] == "pk_low_in_neb"


def test_pk_branch_without_potency_context_satisfies_nothing():
    """Table 2 footnote a: every PK branch is a comparison against the MEC.

    A PK observation cannot even be constructed without naming its potency record, and if
    that record does not resolve, the branch is blocked.
    """
    with pytest.raises(ValueError, match="requires BOTH measurement_id and potency_id"):
        obs(NebpiCriterionId.PK_IN_NEB, ObservationState.OBSERVED_PRESENT,
            measurement_id="EXP-THER")

    r = run(
        [obs(NebpiCriterionId.PK_IN_NEB, ObservationState.OBSERVED_PRESENT,
             measurement_id="EXP-THER", potency_id="POT-1")],
        potencies=[], measurements=[THERAPEUTIC],
    )
    assert r.nebpi_status == "not_classifiable"
    assert any(c.startswith("pk_not_derivable:potency_not_found") for c in r.reason_codes)
    blocked = [b for b in r.branch_proof if b.branch_id == "pk_therapeutic_in_neb"]
    assert "does not exist" in blocked[0].blocking_reason


def test_pk_observation_cannot_assert_its_own_level():
    """The audit's attack: state=not_evaluated + pk_level=therapeutic + a nonexistent
    measurement + an IC50 for the wrong moiety still produced sufficiently_permeable."""
    # There is no `pk_level` field to assert any more.
    with pytest.raises(ValueError, match="Extra inputs are not permitted|pk_level"):
        obs(NebpiCriterionId.PK_IN_NEB, ObservationState.OBSERVED_PRESENT,
            measurement_id="EXP-THER", potency_id="POT-1", pk_level="pk_therapeutic_in_neb")
    # A PK row cannot even be not_evaluated: that state is the absence of the row.
    with pytest.raises(ValueError, match="must be observed_present"):
        obs(NebpiCriterionId.PK_IN_NEB, ObservationState.NOT_EVALUATED,
            measurement_id="EXP-THER", potency_id="POT-1")


def test_pk_from_a_nonexistent_measurement_is_not_classifiable():
    r = run([obs(NebpiCriterionId.PK_IN_NEB, ObservationState.OBSERVED_PRESENT,
                 measurement_id="MEASUREMENT-DOES-NOT-EXIST", potency_id="POT-1")])
    assert r.nebpi_status == "not_classifiable"
    assert r.pk_derivation["blocked_code"] == "measurement_not_found"


def test_pk_from_a_non_neb_matrix_is_not_classifiable():
    """A plasma or CSF measurement is not PK in non-enhancing brain, however it is labelled."""
    plasma = measurement("EXP-PLASMA", "500", matrix="plasma", enhancement="not_applicable")
    r = run([obs(NebpiCriterionId.PK_IN_NEB, ObservationState.OBSERVED_PRESENT,
                 measurement_id="EXP-PLASMA", potency_id="POT-1")], measurements=[plasma])
    assert r.nebpi_status == "not_classifiable"
    assert r.pk_derivation["blocked_code"] == "measurement_not_in_neb"


def test_pk_against_an_ic50_for_the_wrong_moiety_is_not_classifiable():
    bad = PotencyRecord(
        potency_id="POT-BAD", candidate_id="C1", active_moiety_id="OTHER-MOIETY",
        metric="IC50", value_source_string="10", units="nM", binding_state="free",
        assay="x", biological_context="OTHER-TUMOR", evidence_type=EvidenceType.IN_VITRO,
        provenance=PROV,
    )
    r = run([obs(NebpiCriterionId.PK_IN_NEB, ObservationState.OBSERVED_PRESENT,
                 measurement_id="EXP-THER", potency_id="POT-BAD")],
            potencies=[bad], measurements=[THERAPEUTIC])
    assert r.nebpi_status == "not_classifiable"
    assert r.nebpi_class is None


# --------------------------------------------------- the two conjunctions (AND, full)

def _absent(criterion, adequate=True):
    return obs(criterion, ObservationState.OBSERVED_ABSENT, assessment_adequate=adequate,
               adequacy_rationale="adequate study")


def test_full_insufficiently_permeable_conjunction():
    r = run([
        obs(NebpiCriterionId.KNOWN_MEC_POTENCY, ObservationState.OBSERVED_PRESENT),
        obs(NebpiCriterionId.PK_IN_NEB, ObservationState.OBSERVED_PRESENT,
            measurement_id="EXP-LOW", potency_id="POT-1"),
        _absent(NebpiCriterionId.PD_IN_NEB),
        _absent(NebpiCriterionId.RADIOGRAPHIC_RESPONSE_IN_NEB),
    ], measurements=[LOW])
    assert r.nebpi_class == "insufficiently_permeable"
    conj = [b for b in r.branch_proof if b.class_id == "insufficiently_permeable"]
    assert len(conj) == 3 and all(b.satisfied for b in conj)


def test_full_impermeable_conjunction():
    """'Little to no drug in NEB' is the SOURCE's detection status, not a threshold
    Stage 4 invented to separate it from 'low'."""
    r = run([
        obs(NebpiCriterionId.KNOWN_MEC_POTENCY, ObservationState.OBSERVED_PRESENT),
        obs(NebpiCriterionId.PK_IN_NEB, ObservationState.OBSERVED_PRESENT,
            measurement_id="EXP-NONE", potency_id="POT-1"),
        _absent(NebpiCriterionId.PD_IN_NEB),
        _absent(NebpiCriterionId.RADIOGRAPHIC_RESPONSE_IN_NEB),
    ], measurements=[NONE_DETECTED])
    assert r.nebpi_class == "impermeable"
    assert r.pk_derivation["detection_status"] == "not_detected"


def test_low_vs_little_to_none_distinguishes_insufficient_from_impermeable():
    """The only difference between the two conjunctions is the PK level."""
    common = [
        obs(NebpiCriterionId.KNOWN_MEC_POTENCY, ObservationState.OBSERVED_PRESENT),
        _absent(NebpiCriterionId.PD_IN_NEB),
        _absent(NebpiCriterionId.RADIOGRAPHIC_RESPONSE_IN_NEB),
    ]
    low = run(common + [obs(NebpiCriterionId.PK_IN_NEB, ObservationState.OBSERVED_PRESENT,
                            measurement_id="EXP-LOW", potency_id="POT-1")],
              measurements=[LOW])
    none = run(common + [obs(NebpiCriterionId.PK_IN_NEB, ObservationState.OBSERVED_PRESENT,
                             measurement_id="EXP-NONE", potency_id="POT-1")],
               measurements=[NONE_DETECTED])
    assert low.nebpi_class == "insufficiently_permeable"
    assert none.nebpi_class == "impermeable"


@pytest.mark.parametrize("missing", ["pd", "rad"])
def test_unknown_evidence_never_completes_a_negative_conjunction(missing):
    """not_evaluated can never satisfy 'no relevant PD' or 'no radiographic response'."""
    rows = [
        obs(NebpiCriterionId.KNOWN_MEC_POTENCY, ObservationState.OBSERVED_PRESENT),
        obs(NebpiCriterionId.PK_IN_NEB, ObservationState.OBSERVED_PRESENT,
            measurement_id="EXP-NONE", potency_id="POT-1"),
    ]
    if missing == "rad":
        rows.append(_absent(NebpiCriterionId.PD_IN_NEB))
    else:
        rows.append(_absent(NebpiCriterionId.RADIOGRAPHIC_RESPONSE_IN_NEB))

    r = run(rows, measurements=[NONE_DETECTED])
    assert r.nebpi_status == "not_classifiable"
    assert r.nebpi_class is None
    blockers = " ".join(r.counterfactual["negative_classes_blocked_because"])
    assert "not established" in blockers


def test_inadequate_absence_claim_does_not_count_as_observed_absent():
    """An inadequate look is not evidence of absence."""
    r = run([
        obs(NebpiCriterionId.KNOWN_MEC_POTENCY, ObservationState.OBSERVED_PRESENT),
        obs(NebpiCriterionId.PK_IN_NEB, ObservationState.OBSERVED_PRESENT,
            measurement_id="EXP-NONE", potency_id="POT-1"),
        _absent(NebpiCriterionId.PD_IN_NEB, adequate=False),
        _absent(NebpiCriterionId.RADIOGRAPHIC_RESPONSE_IN_NEB),
    ], measurements=[NONE_DETECTED])
    assert r.nebpi_status == "not_classifiable"
    proof = {b.branch_id: b for b in r.branch_proof}
    assert "inadequate look is not evidence of absence" in proof["impermeable::no_relevant_pd_in_neb"].blocking_reason


def test_observed_absent_requires_an_adequacy_assertion_at_the_record_level():
    with pytest.raises(ValueError, match="observed_absent requires assessment_adequate"):
        NebpiObservation(
            observation_id="O-1", candidate_id="C1", context_id="CTX-1",
            criterion_id=NebpiCriterionId.PD_IN_NEB, state=ObservationState.OBSERVED_ABSENT,
            evidence_type=EvidenceType.HUMAN_CLINICAL, provenance=PROV,
        )


# ------------------------------------------------------------------ context dependence

def test_same_moiety_different_dose_route_yields_different_evidence_contexts():
    """The source's methotrexate case: impermeable at standard dose for glial neoplasms,
    sufficiently permeable at high-dose IV for PCNSL. Same molecule, different context."""
    standard = ctx("CTX-STD", route="oral", dose="10 mg", schedule="weekly")
    high_iv = ctx("CTX-HD-IV", route="intravenous", dose="3500 mg/m2", schedule="q14d")

    std_meas = measurement("EXP-STD", None, context_id="CTX-STD", detection="not_detected",
                           route="oral", dose="10 mg", schedule="weekly",
                           limit_kind="lod", limit="1")
    r_std = evaluate_nebpi(
        "C1", standard,
        [obs(NebpiCriterionId.KNOWN_MEC_POTENCY, ObservationState.OBSERVED_PRESENT, "CTX-STD",
             oid="O-mec-std"),
         obs(NebpiCriterionId.PK_IN_NEB, ObservationState.OBSERVED_PRESENT, "CTX-STD",
             oid="O-pk-std", measurement_id="EXP-STD", potency_id="POT-1"),
         obs(NebpiCriterionId.PD_IN_NEB, ObservationState.OBSERVED_ABSENT, "CTX-STD",
             oid="O-pd-std", assessment_adequate=True),
         obs(NebpiCriterionId.RADIOGRAPHIC_RESPONSE_IN_NEB, ObservationState.OBSERVED_ABSENT, "CTX-STD",
             oid="O-rad-std", assessment_adequate=True)],
        [POTENCY], delivery(context_id="CTX-STD"), NEBPI,
        measurements=[std_meas], potency_context_links=[],
    )
    r_hd = evaluate_nebpi(
        "C1", high_iv,
        [obs(NebpiCriterionId.RADIOGRAPHIC_RESPONSE_IN_NEB, ObservationState.OBSERVED_PRESENT,
             "CTX-HD-IV", oid="O-rad-hd")],
        [POTENCY], delivery(context_id="CTX-HD-IV"), NEBPI,
        measurements=[], potency_context_links=[],
    )

    assert r_std.nebpi_class == "impermeable"
    assert r_hd.nebpi_class == "sufficiently_permeable"
    assert r_std.context_id != r_hd.context_id


def test_incomplete_context_blocks_classification():
    r = run(
        [obs(NebpiCriterionId.PD_IN_NEB, ObservationState.OBSERVED_PRESENT)],
        context=ctx(dose="unknown", schedule="unknown"),
    )
    assert r.nebpi_status == "not_classifiable"
    assert "context_incomplete" in r.reason_codes


# ------------------------------------------------------------------- the delivery gate

def test_systemic_priming_does_not_use_nebpi_as_a_primary_gate():
    """A systemic-priming agent must not be failed for low direct NEB exposure."""
    d = delivery(DeliveryRequirement.SYSTEMIC_PRIMING)
    r = run([obs(NebpiCriterionId.CSF_DRUG_LEVELS, ObservationState.OBSERVED_PRESENT)], deliv=d)
    assert r.delivery_requirement == "systemic_immune_priming"
    assert r.nebpi_primary_gate is False
    assert r.nebpi_status == "not_classifiable"  # evidence retained, just not a gate


def test_local_cns_engagement_makes_nebpi_a_primary_gate():
    r = run([obs(NebpiCriterionId.PD_IN_NEB, ObservationState.OBSERVED_PRESENT)])
    assert r.nebpi_primary_gate is True


def test_uncertain_delivery_is_not_silently_treated_as_either():
    d = resolve_delivery_requirement("C1", "CTX-1", [], RULES)
    r = run([obs(NebpiCriterionId.PD_IN_NEB, ObservationState.OBSERVED_PRESENT)], deliv=d)
    assert r.delivery_requirement == "delivery_requirement_uncertain"
    assert r.nebpi_primary_gate is None


def test_branch_proof_explains_every_branch_and_offers_a_counterfactual():
    r = run([obs(NebpiCriterionId.CSF_DRUG_LEVELS, ObservationState.OBSERVED_PRESENT)])
    assert len(r.branch_proof) == 9  # 3 positive OR-branches + 2 classes x 3 conjuncts
    assert all(b.blocking_reason for b in r.branch_proof if not b.satisfied)
    cf = r.counterfactual
    assert len(cf["to_reach_sufficiently_permeable_any_one_of"]) == 3
    assert cf["to_reach_impermeable_all_of"] and cf["to_reach_insufficiently_permeable_all_of"]
    assert cf["current_class"] is None


def test_conflicting_pk_observations_are_not_averaged():
    r = run([
        obs(NebpiCriterionId.KNOWN_MEC_POTENCY, ObservationState.OBSERVED_PRESENT),
        obs(NebpiCriterionId.PK_IN_NEB, ObservationState.OBSERVED_PRESENT, oid="O-pk-1",
            measurement_id="EXP-THER", potency_id="POT-1"),
        obs(NebpiCriterionId.PK_IN_NEB, ObservationState.OBSERVED_PRESENT, oid="O-pk-2",
            measurement_id="EXP-NONE", potency_id="POT-1"),
    ], measurements=[THERAPEUTIC, NONE_DETECTED])
    assert r.nebpi_status == "not_classifiable"
    assert r.criterion_states["pk_in_neb"] == "pk_conflicting"
    proof = {b.branch_id: b for b in r.branch_proof}
    assert "does not average" in proof["pk_therapeutic_in_neb"].blocking_reason
