"""Tests for the shared contract schema (deterministic -> must test)."""

import pytest
from pydantic import ValidationError
from spot_contracts import (
    AgentType,
    Direction,
    DirectionAgreement,
    Evidence,
    EvidenceType,
    Hit,
    KnowledgeLevel,
    Measurement,
    Provenance,
    Subject,
    Term,
    Verdict,
)


def _hit() -> Hit:
    return Hit(
        id="hit-1",
        subject=Subject(id="ENSG00000134460", symbol="IL2RA"),
        direction=Direction.UP,
        context={
            "cell_type": Term(
                label="CD4-positive T cell",
                ontology_id="CL:0000624",
                ontology="CL",
            )
        },
        measurement=Measurement(
            metric="log2FC", value=1.7, direction=Direction.UP, units="log2", pval_adj=1e-6
        ),
        source_agent=AgentType.DATA_ANALYSIS_PIPELINE,
        provenance=Provenance(dataset_id="marson2025_gwcd4"),
    )


def _evidence(
    evidence_type: EvidenceType = EvidenceType.REPLICATION,
    verdict: Verdict = Verdict.CONFIRMED,
    agent: AgentType = AgentType.DATA_ANALYSIS_PIPELINE,
) -> Evidence:
    return Evidence(
        hit_id="hit-1",
        dataset_id="cellxgene-census",
        evidence_type=evidence_type,
        verdict=verdict,
        knowledge_level=KnowledgeLevel.STATISTICAL_ASSOCIATION,
        agent_type=agent,
        direction_agreement=DirectionAgreement.AGREE,
        weight=0.8,
        provenance=Provenance(dataset_id="cellxgene-census"),
    )


def test_hit_roundtrips_through_json() -> None:
    hit = _hit()
    assert Hit.model_validate_json(hit.model_dump_json()) == hit


def test_evidence_roundtrips_through_json() -> None:
    ev = _evidence()
    assert Evidence.model_validate_json(ev.model_dump_json()) == ev


def test_weight_out_of_bounds_rejected() -> None:
    payload = {**_evidence().model_dump(), "weight": 1.5}
    with pytest.raises(ValidationError):
        Evidence.model_validate(payload)


def test_predictive_evidence_cannot_be_confirmed() -> None:
    with pytest.raises(ValidationError):
        _evidence(
            evidence_type=EvidenceType.PREDICTIVE,
            verdict=Verdict.CONFIRMED,
            agent=AgentType.COMPUTATIONAL_MODEL,
        )


def test_predictive_untested_is_allowed() -> None:
    ev = _evidence(
        evidence_type=EvidenceType.PREDICTIVE,
        verdict=Verdict.UNTESTED,
        agent=AgentType.COMPUTATIONAL_MODEL,
    )
    assert ev.evidence_type is EvidenceType.PREDICTIVE
