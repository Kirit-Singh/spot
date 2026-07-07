"""Shared Hit/Evidence vocabulary between Lane A and Lane B.

Data-type-agnostic by design: single-cell / genetic / bulk specifics live in the
values (ontology ids, metric names, context axes), never in the structure.
Core fields only. Extension points: ECO evidence codes, InfoRes provenance
chains, standard errors / CIs, a full build manifest.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator

SCHEMA_VERSION = "0.1.0"


class Direction(StrEnum):
    UP = "up"
    DOWN = "down"
    NONE = "none"


class PerturbationType(StrEnum):
    CRISPRI = "CRISPRi"
    CRISPRA = "CRISPRa"
    CRISPRKO = "CRISPRko"
    ORF = "ORF"
    SIRNA = "siRNA"
    CHEMICAL = "chemical"


class MappingConfidence(StrEnum):
    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    UNMAPPED = "unmapped"


class AgentType(StrEnum):
    # Who produced the finding/evidence (Biolink-aligned).
    DATA_ANALYSIS_PIPELINE = "data_analysis_pipeline"
    COMPUTATIONAL_MODEL = "computational_model"
    MANUAL_AGENT = "manual_agent"


class EvidenceType(StrEnum):
    REPLICATION = "replication"
    CONSISTENCY = "consistency"
    GENETIC = "genetic"
    PREDICTIVE = "predictive"


class KnowledgeLevel(StrEnum):
    STATISTICAL_ASSOCIATION = "statistical_association"
    OBSERVATION = "observation"
    PREDICTION = "prediction"
    KNOWLEDGE_ASSERTION = "knowledge_assertion"


class Verdict(StrEnum):
    CONFIRMED = "confirmed"
    CONTRADICTED = "contradicted"
    INCONCLUSIVE = "inconclusive"
    UNTESTED = "untested"
    CONTEXT_SPECIFIC = "context_specific"


class DirectionAgreement(StrEnum):
    AGREE = "agree"
    DISAGREE = "disagree"
    NOT_APPLICABLE = "n/a"


class SourceTier(StrEnum):
    PRIMARY = "primary"
    AGGREGATOR = "aggregator"
    INFERRED = "inferred"


class Term(BaseModel):
    # One ontology-typed context axis; ontology_id is the join key.
    label: str
    ontology_id: str | None = None
    ontology: str | None = None
    version: str | None = None


class Measurement(BaseModel):
    # Generic method-tagged number; metric is open across data types.
    metric: str
    value: float
    direction: Direction
    units: str | None = None
    log_base: float | None = None
    pval_adj: float | None = None
    n: int | None = None


class Check(BaseModel):
    # One structured gate result (keeps the why, not just a label).
    name: str
    passed: bool
    value: float | None = None
    threshold: float | None = None


class Provenance(BaseModel):
    dataset_id: str
    source_tier: SourceTier = SourceTier.PRIMARY
    accession: str | None = None
    url: str | None = None
    method: str | None = None
    run_date: str | None = None


class Subject(BaseModel):
    # What the hit is about; id_namespace keeps it open beyond genes.
    id: str
    id_namespace: str = "ensembl"
    symbol: str | None = None
    kind: str = "gene"
    perturbation_type: PerturbationType | None = None
    mapping_confidence: MappingConfidence = MappingConfidence.ONE_TO_ONE


class Program(BaseModel):
    # A frozen gene program/signature (avoids marker-choice roulette).
    id: str
    name: str
    genes: list[str] = Field(default_factory=list)
    score_method: str | None = None
    gene_set_version: str | None = None


class Hit(BaseModel):
    # Candidate finding: produced by Lane B or Lane A discovery; consumed by A.
    id: str
    schema_version: str = SCHEMA_VERSION
    subject: Subject
    direction: Direction
    context: dict[str, Term] = Field(default_factory=dict)
    measurement: Measurement
    source_agent: AgentType
    provenance: Provenance
    program: Program | None = None


class Evidence(BaseModel):
    # One confirmation attempt against one dataset; the graph draws one edge each.
    hit_id: str
    schema_version: str = SCHEMA_VERSION
    dataset_id: str
    evidence_type: EvidenceType
    verdict: Verdict
    knowledge_level: KnowledgeLevel
    agent_type: AgentType
    direction_agreement: DirectionAgreement
    weight: float = Field(ge=0.0, le=1.0)
    provenance: Provenance
    checks: list[Check] = Field(default_factory=list)
    measurement: Measurement | None = None

    @model_validator(mode="after")
    def _predictions_cannot_confirm(self) -> Evidence:
        # A model prediction may prioritize, but never counts as confirmation.
        if self.evidence_type is EvidenceType.PREDICTIVE and self.verdict is Verdict.CONFIRMED:
            raise ValueError("predictive evidence cannot have verdict=confirmed")
        return self
