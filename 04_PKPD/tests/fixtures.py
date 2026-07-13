"""Fixture Stage-4 inputs. FIXTURES ONLY — no real drug, study or measurement.

Every candidate is named FIXTURE-*, every moiety FXM-*, and the candidate set carries
namespace=fixture. Nothing here is evidence about anything; it exists to drive the engine
through its branches. The cached "responses" are hashed as real bytes so the provenance
chain and the mutation tests are exercised for real.

After the post-build audit the evidence must be COHERENT: a PK-in-NEB observation names a
real measurement in a real non-enhancing-brain matrix and a real MEC, and the Grossman PK
level is derived from that comparison rather than asserted.
"""

from __future__ import annotations

import json
import os
from typing import Any

from analysis.canonical import canonical_json, sha256_bytes
from analysis.acquisition_records import (EvidenceObservationState, ReviewStatus,
                                          SourceAcquisitionRecord)
from analysis.assay_records import AssayBinding, Relation
from analysis.contract_version import ContractVersion
from analysis.organ_system import LabelRef, extract_organ_system
from analysis.pk_records import (
    FractionUnboundRecord,
    PkDetail,
    PkMetric,
    ResidualBloodCorrection,
    SamplingDetail,
    SamplingMethod,
    Statistic,
    VariabilityKind,
)
from analysis.contracts import EvidenceContext, SourceRecord, Stage3DrugCandidateSet
from analysis.evidence_records import (
    DeliveryAssignment,
    DeliveryBasis,
    DeliveryRequirement,
    EvidenceState,
    EvidenceType,
    ExposureMeasurement,
    GbmScenario,
    InteractionType,
    LabelIdentity,
    NebpiCriterionId,
    NebpiObservation,
    ObservationState,
    PotencyContextLink,
    PotencyRecord,
    PropertyRecord,
    Provenance,
    SafetyEvidenceRecord,
    SearchManifest,
    TransporterObservation,
)
from analysis.firewall import validate_stage3_candidate_set
from analysis.label_adapters import parse_dailymed_spl, parse_openfda_label
from analysis.pipeline import Stage4Inputs
from analysis.safety import safety_rows_from_label

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
ACCESS_DATE = "2026-07-11"


def fixture_bytes(name: str) -> bytes:
    with open(os.path.join(FIXTURE_DIR, name), "rb") as fh:
        return fh.read()


def cached_response_bytes(source_id: str) -> bytes:
    """The exact bytes a parser would be handed for this fixture source."""
    doc = json.loads(fixture_bytes("cached_responses.json").decode("utf-8"))
    return canonical_json(doc["responses"][source_id]).encode("utf-8")


def _sha(source_id: str) -> str:
    return sha256_bytes(cached_response_bytes(source_id))


def load_candidate_set() -> Stage3DrugCandidateSet:
    raw = json.loads(fixture_bytes("stage3_candidate_set.json").decode("utf-8"))
    payload = {k: v for k, v in raw.items() if not k.startswith("_")}
    return validate_stage3_candidate_set(payload)


def _prov(source_id: str, transform: str) -> Provenance:
    return Provenance(
        source_record_id=source_id,
        access_date=ACCESS_DATE,
        raw_response_sha256=_sha(source_id),
        extraction_transform=transform,
    )


def source_registry() -> dict[str, SourceRecord]:
    ids = [
        "src.fixture.stage3",
        "src.fixture.moiety_map",
        "src.fixture.props.biobyte",
        "src.fixture.props.acd",
        "src.fixture.props.pubchem",
        "src.fixture.props.rdkit",
        "src.fixture.potency",
        "src.fixture.transporter",
        "src.fixture.exposure",
        "src.fixture.nebpi",
        "src.fixture.delivery",
        "src.fixture.fu",
    ]
    reg = {
        sid: SourceRecord(
            source_record_id=sid,
            source_type="fixture",
            source_name=f"FIXTURE cached response ({sid})",
            acquisition_status="synthetic_fixture",
            access_date=ACCESS_DATE,
            raw_sha256=_sha(sid),
            raw_bytes=len(cached_response_bytes(sid)),
        )
        for sid in ids
    }
    for sid, fname in (
        ("src.fixture.label.dailymed", "dailymed_spl_fixture.xml"),
        ("src.fixture.label.openfda", "openfda_label_fixture.json"),
    ):
        raw = fixture_bytes(fname)
        reg[sid] = SourceRecord(
            source_record_id=sid,
            source_type="fixture",
            source_name=f"FIXTURE label response ({fname})",
            acquisition_status="synthetic_fixture",
            access_date=ACCESS_DATE,
            raw_sha256=sha256_bytes(raw),
            raw_bytes=len(raw),
        )
    return reg


def contexts() -> list[EvidenceContext]:
    return [
        EvidenceContext(context_id="CTX-001A", candidate_id="FIXTURE-001", active_moiety_id="FXM-001",
                        route="oral", formulation="tablet", dose="150 mg", schedule="once daily",
                        tumor_context="GBM_fixture", is_fixture=True),
        # Same moiety, different route/dose: a different NEBPI evidence context, and a
        # different class (cf. the source's methotrexate example).
        EvidenceContext(context_id="CTX-001B", candidate_id="FIXTURE-001", active_moiety_id="FXM-001",
                        route="intravenous", formulation="solution", dose="3000 mg/m2", schedule="q14d",
                        tumor_context="GBM_fixture", is_fixture=True),
        EvidenceContext(context_id="CTX-002", candidate_id="FIXTURE-002", active_moiety_id="FXM-002",
                        route="intravenous", formulation="solution", dose="10 mg/kg", schedule="q21d",
                        tumor_context="GBM_fixture", is_fixture=True),
        EvidenceContext(context_id="CTX-003", candidate_id="FIXTURE-003", active_moiety_id="FXM-003",
                        route="oral", formulation="capsule", dose="50 mg", schedule="twice daily",
                        tumor_context="GBM_fixture", is_fixture=True),
        EvidenceContext(context_id="CTX-004", candidate_id="FIXTURE-004", active_moiety_id="FXM-004",
                        route="oral", formulation="tablet", dose="20 mg", schedule="once daily",
                        tumor_context="GBM_fixture", is_fixture=True),
    ]


def _p(cand: str, moiety: str, prop: str, value: str, units: str, calc: str, method: str,
       source: str, version: str | None = "fixture-1.0",
       determination: str = "predicted") -> PropertyRecord:
    return PropertyRecord(
        property_record_id=f"PRP-{cand}-{prop}-{calc}",
        candidate_id=cand, active_moiety_id=moiety, property_id=prop,
        value_source_string=value, units=units,
        determination=determination, calculator_id=calc, method=method, software_version=version,
        provenance=_prov(source, f"read {prop} for {moiety} from the cached {calc} response"),
    )


def properties() -> list[PropertyRecord]:
    return [
        # FIXTURE-001: all six, published-method calculators -> complete.
        _p("FIXTURE-001", "FXM-001", "clogp", "2.5", "dimensionless_log10", "biobyte_clogp", "BioByte CLOGP", "src.fixture.props.biobyte"),
        _p("FIXTURE-001", "FXM-001", "clogd_74", "1.8", "dimensionless_log10", "acd_labs", "ACD/Labs LogD pH 7.4", "src.fixture.props.acd"),
        _p("FIXTURE-001", "FXM-001", "mw", "342.4", "g_per_mol", "pubchem_molecular_weight", "PubChem MolecularWeight", "src.fixture.props.pubchem"),
        _p("FIXTURE-001", "FXM-001", "tpsa", "65.0", "angstrom_squared", "pubchem_tpsa", "Ertl TPSA", "src.fixture.props.pubchem"),
        _p("FIXTURE-001", "FXM-001", "hbd", "1", "count", "pubchem_hbond_donor_count", "PubChem HBondDonorCount", "src.fixture.props.pubchem"),
        _p("FIXTURE-001", "FXM-001", "pka_most_basic", "7.2", "pka_units", "acd_labs", "ACD/Labs most basic pKa", "src.fixture.props.acd"),
        # FIXTURE-002 is an antibody: only MW exists -> incomplete, total null. The honest
        # outcome, not a reason to impute the other five.
        _p("FIXTURE-002", "FXM-002", "mw", "145000", "g_per_mol", "pubchem_molecular_weight", "PubChem MolecularWeight", "src.fixture.props.pubchem"),
        # FIXTURE-003: five of six; no pKa -> incomplete.
        _p("FIXTURE-003", "FXM-003", "clogp", "3.4", "dimensionless_log10", "biobyte_clogp", "BioByte CLOGP", "src.fixture.props.pubchem"),
        _p("FIXTURE-003", "FXM-003", "clogd_74", "3.0", "dimensionless_log10", "acd_labs", "ACD/Labs LogD pH 7.4", "src.fixture.props.acd"),
        _p("FIXTURE-003", "FXM-003", "mw", "410.5", "g_per_mol", "pubchem_molecular_weight", "PubChem MolecularWeight", "src.fixture.props.pubchem"),
        _p("FIXTURE-003", "FXM-003", "tpsa", "95.0", "angstrom_squared", "pubchem_tpsa", "Ertl TPSA", "src.fixture.props.pubchem"),
        _p("FIXTURE-003", "FXM-003", "hbd", "2", "count", "pubchem_hbond_donor_count", "PubChem HBondDonorCount", "src.fixture.props.pubchem"),
        # FIXTURE-004: ClogD offered by RDKit -> forbidden by policy -> incomplete.
        _p("FIXTURE-004", "FXM-004", "clogp", "3.8", "dimensionless_log10", "biobyte_clogp", "BioByte CLOGP", "src.fixture.props.biobyte"),
        _p("FIXTURE-004", "FXM-004", "clogd_74", "2.2", "dimensionless_log10", "rdkit", "RDKit (no logD implementation)", "src.fixture.props.rdkit"),
        _p("FIXTURE-004", "FXM-004", "mw", "298.3", "g_per_mol", "pubchem_molecular_weight", "PubChem MolecularWeight", "src.fixture.props.pubchem"),
        _p("FIXTURE-004", "FXM-004", "tpsa", "45.0", "angstrom_squared", "pubchem_tpsa", "Ertl TPSA", "src.fixture.props.pubchem"),
        _p("FIXTURE-004", "FXM-004", "hbd", "1", "count", "pubchem_hbond_donor_count", "PubChem HBondDonorCount", "src.fixture.props.pubchem"),
        _p("FIXTURE-004", "FXM-004", "pka_most_basic", "9.0", "pka_units", "acd_labs", "ACD/Labs most basic pKa", "src.fixture.props.acd"),
    ]


def potencies() -> list[PotencyRecord]:
    prov = _prov("src.fixture.potency", "read potency record from the cached fixture study")
    return [
        PotencyRecord(potency_id="POT-001", candidate_id="FIXTURE-001", active_moiety_id="FXM-001",
                      metric="MEC", value_source_string="100", units="nM", binding_state="free",
                      assay="fixture cell viability", biological_context="GBM_fixture",
                      evidence_type=EvidenceType.IN_VITRO, provenance=prov),
        # An IC50 is not an MEC: it cannot be a margin denominator without a declared
        # transform, so FIXTURE-003 gets no margin.
        PotencyRecord(potency_id="POT-003", candidate_id="FIXTURE-003", active_moiety_id="FXM-003",
                      metric="IC50", value_source_string="50", units="nM", binding_state="free",
                      assay="fixture enzyme assay", biological_context="GBM_fixture",
                      evidence_type=EvidenceType.IN_VITRO, provenance=prov),
    ]


def potency_context_links() -> list[PotencyContextLink]:
    """None in the base fixture: every potency is already in its own tumour context."""
    return []


def transporters() -> list[TransporterObservation]:
    prov = _prov("src.fixture.transporter", "read transporter assay result from the cached response")
    return [
        TransporterObservation(observation_id="TRP-001", candidate_id="FIXTURE-001", active_moiety_id="FXM-001",
                               transporter="ABCB1_Pgp", transporter_gene="ABCB1", interaction="substrate",
                               assay="MDCKII-MDR1 bidirectional permeability", species="human",
                               biological_system="MDCKII-MDR1 monolayer", concentration=1.0,
                               concentration_units="uM", result_metric="efflux_ratio", result_value=4.2,
                               result_units="ratio", direction="efflux", evidence_type=EvidenceType.IN_VITRO,
                               provenance=prov),
        TransporterObservation(observation_id="TRP-002", candidate_id="FIXTURE-001", active_moiety_id="FXM-001",
                               transporter="ABCG2_BCRP", transporter_gene="ABCG2", interaction="not_a_substrate",
                               assay="Caco-2 bidirectional permeability", species="human",
                               biological_system="Caco-2 monolayer", concentration=1.0,
                               concentration_units="uM", result_metric="efflux_ratio", result_value=1.1,
                               result_units="ratio", direction="none", evidence_type=EvidenceType.IN_VITRO,
                               provenance=prov),
        # A second P-gp observation that disagrees with the first. Two assays, two systems:
        # the lane reports both and marks the state ambiguous rather than picking a winner.
        TransporterObservation(observation_id="TRP-003", candidate_id="FIXTURE-001", active_moiety_id="FXM-001",
                               transporter="ABCB1_Pgp", transporter_gene="Abcb1a/b", interaction="inconclusive",
                               assay="Abcb1a/b knockout mouse brain Kp", species="mouse",
                               biological_system="in vivo mouse brain", evidence_type=EvidenceType.IN_VIVO_ANIMAL,
                               provenance=prov),
    ]


def exposures() -> list[ExposureMeasurement]:
    prov = _prov("src.fixture.exposure", "read concentration from the cached fixture PK study")
    common: dict[str, Any] = dict(evidence_type=EvidenceType.HUMAN_CLINICAL, provenance=prov,
                                  species_population="adult human (fixture)")
    return [
        # 40 nM free vs MEC 100 nM free -> margin 0.4 -> DERIVED level: low PK in NEB.
        ExposureMeasurement(measurement_id="EXP-001A", candidate_id="FIXTURE-001", active_moiety_id="FXM-001",
                            context_id="CTX-001A", formulation="tablet", route="oral", dose="150 mg",
                            schedule="once daily", matrix="brain_tissue_non_enhancing",
                            enhancement_context="non_enhancing", binding_state="free",
                            concentration_source_string="40", concentration_units="nM",
                            detection_status="quantified", timepoint="4 h post-dose", **common),
        # Total tissue concentration against a free MEC: refused, not silently divided.
        ExposureMeasurement(measurement_id="EXP-001B", candidate_id="FIXTURE-001", active_moiety_id="FXM-001",
                            context_id="CTX-001A", formulation="tablet", route="oral", dose="150 mg",
                            schedule="once daily", matrix="brain_tissue_non_enhancing",
                            enhancement_context="non_enhancing", binding_state="total",
                            concentration_source_string="900", concentration_units="nM",
                            detection_status="quantified", timepoint="4 h post-dose", **common),
        # 5000 nM free vs MEC 100 nM -> margin 50 -> DERIVED level: therapeutic in NEB.
        ExposureMeasurement(measurement_id="EXP-001C", candidate_id="FIXTURE-001", active_moiety_id="FXM-001",
                            context_id="CTX-001B", formulation="solution", route="intravenous",
                            dose="3000 mg/m2", schedule="q14d", matrix="brain_tissue_non_enhancing",
                            enhancement_context="non_enhancing", binding_state="free",
                            concentration_source_string="5000", concentration_units="nM",
                            detection_status="quantified", timepoint="6 h post-infusion", **common),
        ExposureMeasurement(measurement_id="EXP-002", candidate_id="FIXTURE-002", active_moiety_id="FXM-002",
                            context_id="CTX-002", formulation="solution", route="intravenous", dose="10 mg/kg",
                            schedule="q21d", matrix="plasma", enhancement_context="not_applicable",
                            binding_state="free", concentration_source_string="1200",
                            concentration_units="nM", detection_status="quantified",
                            timepoint="trough", **common),
        ExposureMeasurement(measurement_id="EXP-003", candidate_id="FIXTURE-003", active_moiety_id="FXM-003",
                            context_id="CTX-003", formulation="capsule", route="oral", dose="50 mg",
                            schedule="twice daily", matrix="csf", enhancement_context="not_applicable",
                            binding_state="free", concentration_source_string="30",
                            concentration_units="nM", detection_status="quantified",
                            timepoint="steady state", **common),
    ]


def _delivery_evidence() -> Provenance:
    return _prov("src.fixture.delivery",
                 "read the delivery-requirement assignment from the cached review record")


def delivery_assignments() -> list[DeliveryAssignment]:
    return [
        DeliveryAssignment(assignment_id="DLV-001A", candidate_id="FIXTURE-001", context_id="CTX-001A",
                           requirement=DeliveryRequirement.LOCAL_CNS,
                           basis=DeliveryBasis.MECHANISM_WITH_PHARMACOLOGY_EVIDENCE,
                           assigned_by="fixture-reviewer-01", rule_id="explicit_assignment_required",
                           rule_version="1.0.0",
                           rationale="FIXTURE: the effect requires target engagement in brain parenchyma.",
                           evidence=_delivery_evidence()),
        DeliveryAssignment(assignment_id="DLV-001B", candidate_id="FIXTURE-001", context_id="CTX-001B",
                           requirement=DeliveryRequirement.LOCAL_CNS,
                           basis=DeliveryBasis.MECHANISM_WITH_PHARMACOLOGY_EVIDENCE,
                           assigned_by="fixture-reviewer-01", rule_id="explicit_assignment_required",
                           rule_version="1.0.0",
                           rationale="FIXTURE: same mechanism, high-dose IV context.",
                           evidence=_delivery_evidence()),
        DeliveryAssignment(assignment_id="DLV-002", candidate_id="FIXTURE-002", context_id="CTX-002",
                           requirement=DeliveryRequirement.SYSTEMIC_PRIMING,
                           basis=DeliveryBasis.CLINICAL_EVIDENCE,
                           assigned_by="fixture-reviewer-01", rule_id="explicit_assignment_required",
                           rule_version="1.0.0",
                           rationale="FIXTURE: primes lymphocytes peripherally; they then traffic to brain.",
                           evidence=_delivery_evidence()),
        # The bad inference, declared out loud so the engine can refuse it: an immune target
        # is not evidence of systemic priming. This must land as uncertain.
        DeliveryAssignment(assignment_id="DLV-003", candidate_id="FIXTURE-003", context_id="CTX-003",
                           requirement=DeliveryRequirement.SYSTEMIC_PRIMING,
                           basis=DeliveryBasis.TARGET_BIOLOGY_ONLY,
                           assigned_by="fixture-reviewer-02", rule_id="explicit_assignment_required",
                           rule_version="1.0.0",
                           rationale="FIXTURE: the upstream target is immune-related.",
                           evidence=_delivery_evidence()),
    ]


def _nobs(oid: str, cand: str, ctx: str, crit: NebpiCriterionId, state: ObservationState,
          etype: EvidenceType = EvidenceType.HUMAN_CLINICAL, **kw: Any) -> NebpiObservation:
    return NebpiObservation(
        observation_id=oid, candidate_id=cand, context_id=ctx, criterion_id=crit, state=state,
        evidence_type=etype,
        provenance=_prov("src.fixture.nebpi", f"read {crit.value} observation from the cached study"),
        **kw,
    )


def nebpi_observations() -> list[NebpiObservation]:
    C = NebpiCriterionId
    S = ObservationState
    return [
        # FIXTURE-001 @ standard oral dose. The PK row NAMES its measurement and its MEC;
        # the engine derives "low" from 40 nM vs 100 nM. Adequate assessments found no PD
        # and no radiographic response -> the full insufficiently-permeable conjunction.
        _nobs("NEB-001A-1", "FIXTURE-001", "CTX-001A", C.PHYSICAL_CHARACTERISTICS, S.OBSERVED_PRESENT, EvidenceType.IN_SILICO),
        _nobs("NEB-001A-2", "FIXTURE-001", "CTX-001A", C.PERMEABILITY_NORMAL_ANIMAL_BRAIN, S.OBSERVED_PRESENT, EvidenceType.IN_VIVO_ANIMAL),
        _nobs("NEB-001A-3", "FIXTURE-001", "CTX-001A", C.KNOWN_MEC_POTENCY, S.OBSERVED_PRESENT, EvidenceType.IN_VITRO),
        _nobs("NEB-001A-4", "FIXTURE-001", "CTX-001A", C.PK_IN_NEB, S.OBSERVED_PRESENT,
              measurement_id="EXP-001A", potency_id="POT-001"),
        _nobs("NEB-001A-5", "FIXTURE-001", "CTX-001A", C.PD_IN_NEB, S.OBSERVED_ABSENT,
              assessment_adequate=True, adequacy_rationale="FIXTURE: powered PD study in NEB tissue."),
        _nobs("NEB-001A-6", "FIXTURE-001", "CTX-001A", C.RADIOGRAPHIC_RESPONSE_IN_NEB, S.OBSERVED_ABSENT,
              assessment_adequate=True, adequacy_rationale="FIXTURE: protocol-defined NEB response assessment."),

        # FIXTURE-001 @ high-dose IV: 5000 nM vs 100 nM -> therapeutic -> sufficiently
        # permeable. Same active moiety as above. The class belongs to the context.
        _nobs("NEB-001B-1", "FIXTURE-001", "CTX-001B", C.KNOWN_MEC_POTENCY, S.OBSERVED_PRESENT, EvidenceType.IN_VITRO),
        _nobs("NEB-001B-2", "FIXTURE-001", "CTX-001B", C.PK_IN_NEB, S.OBSERVED_PRESENT,
              measurement_id="EXP-001C", potency_id="POT-001"),

        # FIXTURE-002: systemic priming. NEB evidence retained, but not a primary gate.
        _nobs("NEB-002-1", "FIXTURE-002", "CTX-002", C.CSF_DRUG_LEVELS, S.OBSERVED_PRESENT),

        # FIXTURE-003: descriptors + CSF + in-vitro BBB + enhancing-lesion response only.
        # None can satisfy a Part-II branch -> not_classifiable.
        _nobs("NEB-003-1", "FIXTURE-003", "CTX-003", C.PHYSICAL_CHARACTERISTICS, S.OBSERVED_PRESENT, EvidenceType.IN_SILICO),
        _nobs("NEB-003-2", "FIXTURE-003", "CTX-003", C.CSF_DRUG_LEVELS, S.OBSERVED_PRESENT),
        _nobs("NEB-003-3", "FIXTURE-003", "CTX-003", C.IN_VITRO_BBB_PERMEABILITY, S.OBSERVED_PRESENT, EvidenceType.IN_VITRO),
        _nobs("NEB-003-4", "FIXTURE-003", "CTX-003", C.RESPONSE_IN_ENHANCING_LESIONS, S.OBSERVED_PRESENT),
        # FIXTURE-004: no NEBPI evidence at all -> not_classifiable, never "impermeable".
    ]


def search_manifests() -> list[SearchManifest]:
    """The reproducible negative search behind the one no_evidence_found row.

    The response hash is the SOURCE BINDING's hash: the bytes searched are the registered
    `src.fixture.label.dailymed` response, so the negative is checkable against the same
    document the positive findings came from rather than being asserted by the caller.
    """
    return [
        SearchManifest(
            search_id="SRCH-001-periop-bleed",
            source="dailymed_spl",
            endpoint="/dailymed/services/v2/spls/{setid}.xml",
            query_canonical="setid=ffffffff-0000-4000-8000-fixturespl001; sections=34066-1,34070-3,43685-7,34073-7,34084-4; terms=bleed|haemorrhage|hemorrhage",
            search_scope="all labelled sections of the cited SPL version",
            executed_date=ACCESS_DATE,
            source_release="FIXTURE SPL v7 (effective 2026-04-01)",
            n_results=0,
            provenance=_prov_label(
                "src.fixture.label.dailymed", "dailymed_spl_fixture.xml",
                "search every labelled section of the cited SPL for bleeding terms; 0 hits"),
        ),
    ]


def safety_records() -> list[SafetyEvidenceRecord]:
    spl = parse_dailymed_spl(fixture_bytes("dailymed_spl_fixture.xml"))
    of = parse_openfda_label(fixture_bytes("openfda_label_fixture.json"))[0]

    # The label must prove it is this moiety's label (UNII), not merely be handed to it.
    rows = safety_rows_from_label(spl, "FIXTURE-001", "FXM-001", "src.fixture.label.dailymed",
                                  ACCESS_DATE,
                                  "parse SPL sections 34066-1/34070-3/43685-7/34073-7/34084-4",
                                  expected_unii="ZZZZZZZZ99", expected_moiety_name="FIXTURIB")
    rows += safety_rows_from_label(of, "FIXTURE-002", "FXM-002", "src.fixture.label.openfda",
                                   ACCESS_DATE, "parse openFDA label fields",
                                   expected_unii="YYYYYYYY88", expected_moiety_name="FIXTURIMAB")

    prov_dm = _prov_label("src.fixture.label.dailymed", "dailymed_spl_fixture.xml",
                          "map the labeled boxed-warning section onto the named GBM scenario")
    prov_of = _prov_label("src.fixture.label.openfda", "openfda_label_fixture.json",
                          "map the labeled warnings section onto the named GBM scenario")

    rows += [
        SafetyEvidenceRecord(
            evidence_id="SCN-001-tmz-marrow", candidate_id="FIXTURE-001", active_moiety_id="FXM-001",
            evidence_state=EvidenceState.LABEL_SUPPORTED, finding_type="boxed_warning",
            finding_text="FIXTURE: Severe myelosuppression, including neutropenia and thrombocytopenia, has occurred in fixture subjects receiving FIXTURIB.",
            gbm_scenario=GbmScenario.TEMOZOLOMIDE, interaction_type=InteractionType.MARROW_EFFECTS,
            label_identity=_label_identity(spl, "34066-1", "Boxed Warning section"), provenance=prov_dm),
        SafetyEvidenceRecord(
            evidence_id="SCN-001-asm-pk", candidate_id="FIXTURE-001", active_moiety_id="FXM-001",
            evidence_state=EvidenceState.LABEL_SUPPORTED, finding_type="labeled_interaction",
            finding_text="FIXTURE: Concomitant use with strong fixture CYP3A4 inducers decreases fixturib exposure.",
            gbm_scenario=GbmScenario.ANTISEIZURE_THERAPY, interaction_type=InteractionType.PK_INTERACTION,
            label_identity=_label_identity(spl, "34073-7", "DRUG INTERACTIONS SECTION"), provenance=prov_dm),
        # Searched and found nothing — and it says exactly which search. This is NOT
        # "no bleeding risk".
        SafetyEvidenceRecord(
            evidence_id="SCN-001-periop-bleed", candidate_id="FIXTURE-001", active_moiety_id="FXM-001",
            evidence_state=EvidenceState.NO_EVIDENCE_FOUND,
            gbm_scenario=GbmScenario.PERIOPERATIVE_SETTING, interaction_type=InteractionType.BLEEDING,
            searched_sources=["src.fixture.label.dailymed"],
            search_id="SRCH-001-periop-bleed"),
        SafetyEvidenceRecord(
            evidence_id="SCN-002-steroid-antag", candidate_id="FIXTURE-002", active_moiety_id="FXM-002",
            evidence_state=EvidenceState.LABEL_SUPPORTED, finding_type="warning_precaution",
            finding_text="FIXTURE: Systemic corticosteroids may blunt the fixture pharmacodynamic effect of FIXTURIMAB.",
            gbm_scenario=GbmScenario.CORTICOSTEROID_EXPOSURE, interaction_type=InteractionType.MECHANISTIC_ANTAGONISM,
            label_identity=_label_identity(of, "warnings_and_cautions", "warnings_and_cautions"), provenance=prov_of),
        SafetyEvidenceRecord(
            evidence_id="SCN-002-rt-immune", candidate_id="FIXTURE-002", active_moiety_id="FXM-002",
            evidence_state=EvidenceState.LABEL_SUPPORTED, finding_type="warning_precaution",
            finding_text="FIXTURE: Immune-mediated fixture pneumonitis has been reported.",
            gbm_scenario=GbmScenario.RADIATION, interaction_type=InteractionType.IMMUNE_ACTIVATION_AUTOIMMUNITY,
            label_identity=_label_identity(of, "warnings_and_cautions", "warnings_and_cautions"), provenance=prov_of),
    ]
    return rows


def _label_identity(parsed: Any, section_code: str, section_name: str) -> LabelIdentity:
    return LabelIdentity(
        label_source=parsed.label_source, setid=parsed.setid,
        application_number=parsed.application_number, product_identity=parsed.product_identity,
        label_version=parsed.label_version, effective_date=parsed.effective_date,
        labeled_section_code=section_code, labeled_section_name=section_name,
        code_system="2.16.840.1.113883.6.1" if parsed.label_source == "dailymed_spl" else "openfda_field",
    )


def _prov_label(source_id: str, filename: str, transform: str) -> Provenance:
    return Provenance(
        source_record_id=source_id, access_date=ACCESS_DATE,
        raw_response_sha256=sha256_bytes(fixture_bytes(filename)), extraction_transform=transform,
    )


# --------------------------------------------------------------------------- v2 lanes
# Labelled synthetic, like every other fixture here: these exercise the acquisition-complete
# contract end-to-end (and give the resealed-cell sweep a row of every new bound column to
# mutate) without pretending any of it was fetched.


def fraction_unbound() -> list[FractionUnboundRecord]:
    """fu,plasma and fu,brain. Kp,uu needs BOTH -- deriving one from a single fu is asserting
    an unbound ratio from total concentrations."""
    prov = _prov("src.fixture.fu", "read fu from the cached fixture protein-binding study")
    return [
        FractionUnboundRecord(
            fraction_unbound_id="FU-PLASMA-001", candidate_id="FIXTURE-001",
            active_moiety_id="FXM-001", matrix="plasma", value_source_string="0.12",
            method="equilibrium dialysis (fixture)", species="human",
            concentration_dependence="independent", provenance=prov),
        FractionUnboundRecord(
            fraction_unbound_id="FU-BRAIN-001", candidate_id="FIXTURE-001",
            active_moiety_id="FXM-001", matrix="brain", value_source_string="0.04",
            method="brain homogenate binding (fixture)", species="human",
            concentration_dependence="not_reported", provenance=prov),
    ]


def acquisitions() -> list[SourceAcquisitionRecord]:
    """One acquisition record per fixture source that carries bytes.

    The three interesting states are all present: an `observed` fetch, a
    `not_found_after_reproducible_search` bound to the negative-search manifest, and a
    `conflicting` one -- so the sweep exercises the fields each state requires.
    """
    reg = source_registry()

    def acq(sid: str, **over) -> SourceAcquisitionRecord:
        base: dict[str, Any] = dict(
            acquisition_id=f"ACQ-{sid.split('.')[-1].upper()}",
            source_record_id=sid,
            request_url=f"https://fixture.invalid/{sid}",
            canonical_query=f"GET /fixture/{sid}",
            accessed_at_utc="2026-07-11T09:15:00Z",
            http_status=200,
            raw_media_type="application/json",
            response_headers={"content-type": "application/json", "etag": f'W/"{sid}"'},
            release_or_last_updated="fixture-release-1",
            license_or_terms_url="https://fixture.invalid/terms",
            raw_bytes=reg[sid].raw_bytes,
            raw_sha256=reg[sid].raw_sha256,
            content_sha256=reg[sid].raw_sha256,
            extraction_transform="fixture extraction",
            adapter_id="fixture_adapter",
            adapter_code_sha256=sha256_bytes(f"FIXTURE adapter build for {sid}".encode()),
            review_status=ReviewStatus.HUMAN_REVIEWED,
            observation_state=EvidenceObservationState.OBSERVED,
            # The fixture query matches exactly one record by its own id. It is not a
            # `limit=1` truncation of a larger match, and it says so.
            # selection.py's vocabulary: matched on an identity PIN, and the source's own
            # total agrees with what arrived -- so the result set is complete and the
            # uniqueness was actually PROVEN rather than assumed.
            selection_disposition="exactly_one",
            selection_pin="the fixture source_record_id",
            match_total_reported=1,
            records_returned=1,
            result_set_complete=True,
        )
        base.update(over)
        return SourceAcquisitionRecord(**base)

    # EVERY source that carries bytes needs one: under v2 a byte with no canonical query,
    # access time, terms URL and adapter build is a byte nobody can get again. The special
    # states are attached to the two label sources.
    special = {
        # "We ran this exact query against this release and it came back empty" -- bound to the
        # manifest AND to the bytes that came back empty. Not the same claim as "nobody looked".
        "src.fixture.label.openfda": dict(
            observation_state=EvidenceObservationState.NOT_FOUND_AFTER_SEARCH,
            search_id="SRCH-001-periop-bleed"),
        # The sources disagree, and the disagreement is stated rather than silently resolved.
        "src.fixture.label.dailymed": dict(
            observation_state=EvidenceObservationState.CONFLICTING,
            conflict_note=("FIXTURE: the cached SPL and the cached openFDA record give "
                           "different effective dates for the same setid."),
            content_sha256=sha256_bytes(b"FIXTURE normalised dailymed content"),
            content_hash_rule=("sha256 over the SPL with the volatile <effectiveTime> stamp "
                               "blanked (fixture rule)."),
            review_status=ReviewStatus.DISPUTED),
        "src.fixture.transporter": dict(
            license_exception_note="FIXTURE: third-party rights may attach to some rows."),
    }
    return [acq(sid, **special.get(sid, {}))
            for sid, rec in sorted(reg.items()) if rec.raw_sha256]


def stage4_inputs_v2() -> Stage4Inputs:
    """The SAME evidence, spoken in the v2 contract.

    Every v1 row here gains the v2 fields the acquisition profile requires, and the two v2-only
    lanes (fraction unbound, source acquisition) are populated. This is what an
    acquisition-complete bundle looks like; `contract_profile.py` refuses one that is missing
    any of it.

    The v1 fixture set (`stage4_inputs`) is deliberately NOT touched: it is frozen evidence and
    its digest is pinned.
    """
    inputs = stage4_inputs()
    inputs.contract_version = ContractVersion.V2
    inputs.potencies = [_v2_potency(p) for p in inputs.potencies]
    inputs.exposures = [_v2_exposure(m) for m in inputs.exposures]
    inputs.safety_records = [_v2_safety(r) for r in inputs.safety_records]
    inputs.fraction_unbound = fraction_unbound()
    inputs.acquisitions = acquisitions()
    return inputs


def _v2_potency(p: PotencyRecord) -> PotencyRecord:
    return PotencyRecord(**{
        **p.model_dump(),
        "relation": Relation.EQ,
        "assay_binding": AssayBinding(
            activity_id=f"FIXTURE_ACT_{p.potency_id}",
            assay_id=f"FIXTURE_ASSAY_{p.potency_id}",
            target_id="FIXTURE_TGT_1",
            document_id=f"FIXTURE_DOC_{p.potency_id}",
            assay_type="F",
            assay_description="FIXTURE functional viability assay",
            experimental_system="patient_derived_gbm_line (fixture)",
            target_organism="Homo sapiens",
            target_uniprot_accession="P00000",
            confidence_score=9,
            validity_comment=None,
        ),
    })


def _v2_exposure(m: ExposureMeasurement) -> ExposureMeasurement:
    tissue = m.matrix.startswith("brain_tissue") or m.matrix == "normal_animal_brain"
    method = SamplingMethod.RESECTION_HOMOGENATE if tissue else (
        SamplingMethod.CSF_DRAW if m.matrix == "csf" else SamplingMethod.BLOOD_DRAW)
    return ExposureMeasurement(**{
        **m.model_dump(),
        "pk_detail": PkDetail(
            pk_metric=PkMetric.CONCENTRATION_AT_TIME, statistic=Statistic.MEDIAN,
            sample_size=9, variability_kind=VariabilityKind.RANGE,
            variability_source_string="FIXTURE range", variability_units="nM"),
        "sampling": SamplingDetail(
            sampling_method=method,
            sample_location="FIXTURE sample location",
            time_relative_to_dose=m.timepoint or "FIXTURE time",
            analytical_method="LC-MS/MS (fixture)",
            steady_state=True,
            residual_blood_correction=(ResidualBloodCorrection.APPLIED if tissue
                                       else ResidualBloodCorrection.NOT_APPLICABLE)),
        "co_medications": ["dexamethasone (fixture)"],
        "assay_method": "LC-MS/MS (fixture)",
        # The plasma row every brain/CSF sample is paired with.
        "paired_plasma_measurement_id": ("EXP-002" if m.measurement_id != "EXP-002" else None),
        "binding_state_basis": "measured",
    })


def _v2_safety(r: SafetyEvidenceRecord) -> SafetyEvidenceRecord:
    """The organ system comes from ACQUISITION's extractor, not from this fixture's opinion.

    No public source in the Stage-4 ledger currently carries an organ-system field, so every
    real extraction returns `unspecified` / `not_evaluated` — WITH the record and bytes it
    looked at. That is the honest answer, and it is the one the fixture carries: inventing a
    classification here would be the exact inference the field forbids.
    """
    d = r.model_dump()
    li = r.label_identity
    d["organ_system_evidence"] = extract_organ_system(
        LabelRef(
            source_record_id=(r.provenance.source_record_id if r.provenance
                              else "src.fixture.label.dailymed"),
            setid=(li.setid if li else None),
            label_version=(li.label_version if li else None),
            raw_response_sha256=(r.provenance.raw_response_sha256 if r.provenance else None),
            structured={},
        ),
        source_key="dailymed",
    )
    return SafetyEvidenceRecord(**d)


def stage4_inputs() -> Stage4Inputs:
    return Stage4Inputs(
        candidate_set=load_candidate_set(),
        contexts=contexts(),
        sources=source_registry(),
        properties=properties(),
        potencies=potencies(),
        potency_context_links=potency_context_links(),
        transporters=transporters(),
        exposures=exposures(),
        delivery_assignments=delivery_assignments(),
        nebpi_observations=nebpi_observations(),
        safety_records=safety_records(),
        search_manifests=search_manifests(),
        config={"fixture_run": True},
    )
