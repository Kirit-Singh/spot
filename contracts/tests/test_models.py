"""Tests for the shared contract schema (deterministic -> must test)."""

import pytest
from pydantic import ValidationError
from spot_contracts import (
    PREDICTIVE_WEIGHT_MAX,
    AgentType,
    Check,
    CheckName,
    Direction,
    DirectionAgreement,
    Evidence,
    EvidenceType,
    Hit,
    KnowledgeLevel,
    MappingConfidence,
    Measurement,
    Metric,
    PerturbationType,
    Provenance,
    Subject,
    Term,
    Verdict,
)


def _measurement(value: float = 1.7, direction: Direction = Direction.UP) -> Measurement:
    return Measurement(metric=Metric.LOG2FC, value=value, direction=direction, pval_adj=1e-6)


def _subject() -> Subject:
    return Subject(id="ENSG00000134460.13", symbol="IL2RA")


def _gate_checks() -> list[Check]:
    return [
        Check(name=CheckName.METRIC_MATCH, passed=True),
        Check(name=CheckName.DIRECTION_RECONCILED, passed=True),
        Check(name=CheckName.INDEPENDENCE, passed=True),
    ]


def _hit(**kw) -> Hit:
    base = dict(
        id="hit-1",
        subject=_subject(),
        direction=Direction.UP,
        measurement=_measurement(),
        source_agent=AgentType.DATA_ANALYSIS_PIPELINE,
        provenance=Provenance(dataset_id="marson2025_gwcd4"),
        context={"cell_type": Term(label="CD4 T cell", ontology_id="CL:0000624", ontology="CL")},
    )
    base.update(kw)
    return Hit(**base)


def _evidence(**kw) -> Evidence:
    base = dict(
        hit_id="hit-1",
        evidence_type=EvidenceType.REPLICATION,
        verdict=Verdict.CONFIRMED,
        knowledge_level=KnowledgeLevel.STATISTICAL_ASSOCIATION,
        agent_type=AgentType.DATA_ANALYSIS_PIPELINE,
        direction_agreement=DirectionAgreement.AGREE,
        weight=0.8,
        provenance=Provenance(dataset_id="cellxgene-census"),
        corroborating_hit_ids=["hit-2"],
        checks=_gate_checks(),
    )
    base.update(kw)
    return Evidence(**base)


def test_hit_roundtrips_through_json() -> None:
    hit = _hit()
    assert Hit.model_validate_json(hit.model_dump_json()) == hit


def test_evidence_roundtrips_through_json() -> None:
    ev = _evidence()
    assert Evidence.model_validate_json(ev.model_dump_json()) == ev


def test_join_key_strips_version() -> None:
    assert _subject().join_key == "NCBITaxon:9606:ENSG00000134460:gene"


def test_unmapped_subject_requires_symbol() -> None:
    with pytest.raises(ValidationError):
        Subject(mapping_confidence=MappingConfidence.UNMAPPED)


def test_perturbation_subject_requires_type() -> None:
    with pytest.raises(ValidationError):
        Subject(id="ENSG1", kind="perturbation")
    assert Subject(id="ENSG1", kind="perturbation", perturbation_type=PerturbationType.CRISPRI)


def test_context_key_must_be_core_or_extension() -> None:
    with pytest.raises(ValidationError):
        _hit(context={"stim": Term(label="activated")})
    assert _hit(context={"x_donor_state": Term(label="rested")})


def test_hit_direction_must_match_measurement() -> None:
    with pytest.raises(ValidationError):
        _hit(direction=Direction.DOWN)


def test_signed_metric_direction_must_match_sign() -> None:
    with pytest.raises(ValidationError):
        Measurement(metric=Metric.LOG2FC, value=-2.0, direction=Direction.UP)


def test_metric_other_requires_companion() -> None:
    with pytest.raises(ValidationError):
        Measurement(metric=Metric.OTHER, value=1.0, direction=Direction.UP)


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        Term(label="x", bogus_field=1)


def test_schema_version_mismatch_rejected() -> None:
    with pytest.raises(ValidationError):
        _evidence(schema_version="99.0.0")


def test_replication_requires_corroborating() -> None:
    with pytest.raises(ValidationError):
        _evidence(corroborating_hit_ids=[])


def test_evidence_cannot_corroborate_own_hit() -> None:
    with pytest.raises(ValidationError):
        _evidence(corroborating_hit_ids=["hit-1"])


def test_confirmed_requires_agree() -> None:
    with pytest.raises(ValidationError):
        _evidence(direction_agreement=DirectionAgreement.DISAGREE)


def test_untested_requires_zero_weight() -> None:
    with pytest.raises(ValidationError):
        _evidence(
            verdict=Verdict.UNTESTED,
            weight=0.5,
            direction_agreement=DirectionAgreement.NOT_APPLICABLE,
        )


def test_confirmed_requires_gate_checks() -> None:
    # missing the independence check for a replication confirmation
    with pytest.raises(ValidationError):
        _evidence(
            checks=[
                Check(name=CheckName.METRIC_MATCH, passed=True),
                Check(name=CheckName.DIRECTION_RECONCILED, passed=True),
            ]
        )


def test_firewall_blocks_model_labeled_replication() -> None:
    with pytest.raises(ValidationError):
        _evidence(agent_type=AgentType.COMPUTATIONAL_MODEL)


def test_firewall_blocks_prediction_knowledge_level_confirm() -> None:
    with pytest.raises(ValidationError):
        _evidence(
            evidence_type=EvidenceType.GENETIC,
            knowledge_level=KnowledgeLevel.PREDICTION,
        )


def test_predictive_weight_capped() -> None:
    with pytest.raises(ValidationError):
        _evidence(
            evidence_type=EvidenceType.PREDICTIVE,
            verdict=Verdict.INCONCLUSIVE,
            agent_type=AgentType.COMPUTATIONAL_MODEL,
            knowledge_level=KnowledgeLevel.PREDICTION,
            direction_agreement=DirectionAgreement.NOT_APPLICABLE,
            corroborating_hit_ids=[],
            checks=[],
            weight=0.9,
        )


def test_predictive_within_cap_is_allowed() -> None:
    ev = _evidence(
        evidence_type=EvidenceType.PREDICTIVE,
        verdict=Verdict.INCONCLUSIVE,
        agent_type=AgentType.COMPUTATIONAL_MODEL,
        knowledge_level=KnowledgeLevel.PREDICTION,
        direction_agreement=DirectionAgreement.NOT_APPLICABLE,
        corroborating_hit_ids=[],
        checks=[],
        weight=PREDICTIVE_WEIGHT_MAX,
    )
    assert ev.evidence_type is EvidenceType.PREDICTIVE
