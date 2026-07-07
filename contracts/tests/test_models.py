"""Tests for the shared contract schema (deterministic -> must test)."""

import pytest
from pydantic import ValidationError
from spot_contracts import (
    AgentType,
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
    Provenance,
    Subject,
    Term,
    Verdict,
)


def _measurement(value: float = 1.7, direction: Direction = Direction.UP) -> Measurement:
    return Measurement(metric=Metric.LOG2FC, value=value, direction=direction, pval_adj=1e-6)


def _subject() -> Subject:
    return Subject(id="ENSG00000134460.13", symbol="IL2RA")


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


def test_context_key_must_be_core_or_extension() -> None:
    with pytest.raises(ValidationError):
        _hit(context={"stim": Term(label="activated")})
    assert _hit(context={"x_donor_state": Term(label="rested")})


def test_hit_direction_must_match_measurement() -> None:
    with pytest.raises(ValidationError):
        _hit(direction=Direction.DOWN)  # measurement says up


def test_signed_metric_direction_must_match_sign() -> None:
    with pytest.raises(ValidationError):
        Measurement(metric=Metric.LOG2FC, value=-2.0, direction=Direction.UP)


def test_metric_other_requires_companion() -> None:
    with pytest.raises(ValidationError):
        Measurement(metric=Metric.OTHER, value=1.0, direction=Direction.UP)


def test_replication_requires_corroborating() -> None:
    with pytest.raises(ValidationError):
        _evidence(corroborating_hit_ids=[])


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


def test_predictive_cannot_be_confirmed() -> None:
    with pytest.raises(ValidationError):
        _evidence(
            evidence_type=EvidenceType.PREDICTIVE,
            agent_type=AgentType.COMPUTATIONAL_MODEL,
            corroborating_hit_ids=[],
        )


def test_predictive_untested_is_allowed() -> None:
    ev = _evidence(
        evidence_type=EvidenceType.PREDICTIVE,
        verdict=Verdict.UNTESTED,
        agent_type=AgentType.COMPUTATIONAL_MODEL,
        weight=0.0,
        direction_agreement=DirectionAgreement.NOT_APPLICABLE,
        corroborating_hit_ids=[],
    )
    assert ev.evidence_type is EvidenceType.PREDICTIVE


def test_check_name_other_requires_companion() -> None:
    with pytest.raises(ValidationError):
        _evidence(checks=[{"name": CheckName.OTHER, "passed": True}])
