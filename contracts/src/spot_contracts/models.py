"""Shared Hit/Evidence vocabulary between Lane A and Lane B.

Data-type-agnostic core: single-cell / genetic / bulk specifics live in values,
never structure. Controlled core + open extension (enum OTHER + companion fields,
x_-prefixed context axes). The contract enforces intra-object / intra-aggregate
coherence so it is a trustworthy seam on its own; cross-hit and graph-level facts
(dataset independence across hits, relative weight ordering, context-match
verdicts, source-column ingestion mapping) live in Lane A.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator

SCHEMA_VERSION = "0.2.0"
PREDICTIVE_WEIGHT_MAX = 0.5


class _Base(BaseModel):
    # Fail loud on unknown/misspelled fields; extension goes through sanctioned
    # carriers (x_ context keys, *_other companions), never arbitrary fields.
    model_config = ConfigDict(extra="forbid")


class Direction(StrEnum):
    UP = "up"
    DOWN = "down"
    NONE = "none"


class IdType(StrEnum):
    GENE = "gene"
    TRANSCRIPT = "transcript"
    PROTEIN = "protein"


class PerturbationType(StrEnum):
    CRISPRI = "CRISPRi"
    CRISPRA = "CRISPRa"
    CRISPRKO = "CRISPRko"
    BASE_EDIT = "base_edit"
    PRIME_EDIT = "prime_edit"
    ORF = "ORF"
    SIRNA = "siRNA"
    CHEMICAL = "chemical"
    OTHER = "other"


class MappingConfidence(StrEnum):
    ONE_TO_ONE = "one_to_one"
    ONE_TO_MANY = "one_to_many"
    MANY_TO_ONE = "many_to_one"
    UNMAPPED = "unmapped"


class AgentType(StrEnum):
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


class Metric(StrEnum):
    LOG2FC = "log2fc"
    LOG10FC = "log10fc"
    LNFC = "lnfc"
    WALD = "wald"
    ZSCORE = "zscore"
    BETA = "beta"
    ODDS_RATIO = "odds_ratio"
    E_DISTANCE = "e_distance"
    AUROC = "auroc"
    SCORE = "score"
    OTHER = "other"


class NType(StrEnum):
    CELLS = "cells"
    REPLICATES = "replicates"
    GUIDES = "guides"
    DONORS = "donors"


class ContextAxis(StrEnum):
    CELL_TYPE = "cell_type"
    STIMULUS = "stimulus"
    TIMEPOINT = "timepoint"
    DISEASE = "disease"
    TISSUE = "tissue"
    POPULATION = "population"


class CheckName(StrEnum):
    MAPPING = "mapping"
    CONTEXT_MATCH = "context_match"
    INDEPENDENCE = "independence"
    METRIC_MATCH = "metric_match"
    DIRECTION_RECONCILED = "direction_reconciled"
    DIRECTION_FDR = "direction_fdr"
    UNITS_RECONCILED = "units_reconciled"
    AMBIENT_QC = "ambient_qc"
    DONOR_CONSISTENCY = "donor_consistency"
    GUIDE_EFFICIENCY = "guide_efficiency"
    OFFTARGET = "offtarget"
    EFFECT_VS_NOISE = "effect_vs_noise"
    OTHER = "other"


SIGNED_METRICS = frozenset(
    {Metric.LOG2FC, Metric.LOG10FC, Metric.LNFC, Metric.WALD, Metric.ZSCORE, Metric.BETA}
)
_CONTEXT_CORE = frozenset(a.value for a in ContextAxis)


def _check_context_keys(context: dict[str, Term]) -> None:
    for key in context:
        if key not in _CONTEXT_CORE and not key.startswith("x_"):
            raise ValueError(f"context key {key!r} is not a core axis; use an x_ prefix")


def _passed_checks(checks: list[Check]) -> set[CheckName]:
    return {c.name for c in checks if c.passed}


class Term(_Base):
    label: str
    ontology_id: str | None = None
    ontology: str | None = None
    version: str | None = None


class Measurement(_Base):
    metric: Metric
    value: float
    direction: Direction
    metric_other: str | None = None
    units: str | None = None
    n: int | None = None
    n_type: NType | None = None
    significant: bool | None = None
    pval_raw: float | None = None
    pval_adj: float | None = None
    pval_adj_method: str | None = None
    test: str | None = None
    stderr: float | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Measurement:
        if self.metric is Metric.OTHER and not self.metric_other:
            raise ValueError("metric=other requires metric_other")
        if self.metric in SIGNED_METRICS:
            want = (
                Direction.UP
                if self.value > 0
                else Direction.DOWN
                if self.value < 0
                else Direction.NONE
            )
            if self.direction is not want:
                raise ValueError(f"direction {self.direction} inconsistent with {self.metric}")
        return self


class Check(_Base):
    name: CheckName
    passed: bool
    name_other: str | None = None
    value: float | None = None
    threshold: float | None = None

    @model_validator(mode="after")
    def _named(self) -> Check:
        if self.name is CheckName.OTHER and not self.name_other:
            raise ValueError("check name=other requires name_other")
        return self


class Provenance(_Base):
    dataset_id: str
    source_tier: SourceTier = SourceTier.PRIMARY
    accession: str | None = None
    upstream_accession: str | None = None
    license: str | None = None
    url: str | None = None
    method: str | None = None
    run_date: str | None = None


class Subject(_Base):
    id: str | None = None
    id_namespace: str = "ensembl"
    id_type: IdType = IdType.GENE
    id_version: str | None = None
    taxon_id: str = "NCBITaxon:9606"
    symbol: str | None = None
    kind: str = "gene"
    perturbation_type: PerturbationType | None = None
    mapping_confidence: MappingConfidence = MappingConfidence.ONE_TO_ONE

    @model_validator(mode="after")
    def _identity(self) -> Subject:
        if self.mapping_confidence is MappingConfidence.UNMAPPED:
            if not self.symbol:
                raise ValueError("unmapped subject requires a symbol")
        elif not self.id:
            raise ValueError("mapped subject requires an id")
        if self.kind == "perturbation" and self.perturbation_type is None:
            raise ValueError("perturbation subject requires perturbation_type")
        return self

    @property
    def join_key(self) -> str:
        base = (self.id or self.symbol or "").split(".")[0]
        return f"{self.taxon_id}:{base}:{self.id_type}"


class Selection(_Base):
    metric: Metric | None = None
    effect_threshold: float | None = None
    fdr_cutoff: float | None = None


class Program(_Base):
    id: str
    name: str
    genes: list[str] = Field(default_factory=list)
    gene_id_type: IdType | None = None
    score_method: str | None = None
    gene_set_version: str | None = None


class Hit(_Base):
    id: str
    subject: Subject
    direction: Direction
    measurement: Measurement
    source_agent: AgentType
    provenance: Provenance
    schema_version: str = SCHEMA_VERSION
    context: dict[str, Term] = Field(default_factory=dict)
    program: Program | None = None
    selection: Selection | None = None
    created_at: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Hit:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version {self.schema_version}")
        _check_context_keys(self.context)
        if self.measurement.direction is not self.direction:
            raise ValueError("hit.direction must equal measurement.direction")
        return self


class Evidence(_Base):
    hit_id: str
    evidence_type: EvidenceType
    verdict: Verdict
    knowledge_level: KnowledgeLevel
    agent_type: AgentType
    direction_agreement: DirectionAgreement
    weight: float = Field(ge=0.0, le=1.0)
    provenance: Provenance
    schema_version: str = SCHEMA_VERSION
    hit_content_hash: str | None = None
    corroborating_hit_ids: list[str] = Field(default_factory=list)
    checks: list[Check] = Field(default_factory=list)
    context: dict[str, Term] = Field(default_factory=dict)
    measurement: Measurement | None = None
    created_at: str | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Evidence:
        if self.schema_version != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version {self.schema_version}")
        _check_context_keys(self.context)
        # Honest-source firewall: a model/prediction may prioritize, never
        # replicate or confirm -- gated on who produced it, not the self-label.
        is_pred = (
            self.agent_type is AgentType.COMPUTATIONAL_MODEL
            or self.knowledge_level is KnowledgeLevel.PREDICTION
            or self.evidence_type is EvidenceType.PREDICTIVE
        )
        if is_pred and self.evidence_type in (EvidenceType.REPLICATION, EvidenceType.CONSISTENCY):
            raise ValueError("model/prediction evidence cannot be replication or consistency")
        if is_pred and self.verdict is Verdict.CONFIRMED:
            raise ValueError("model/prediction evidence cannot have verdict=confirmed")
        if is_pred and self.weight > PREDICTIVE_WEIGHT_MAX:
            raise ValueError(f"model/prediction evidence weight must be <= {PREDICTIVE_WEIGHT_MAX}")
        # verdict <-> direction_agreement / weight coherence
        if (
            self.verdict is Verdict.CONFIRMED
            and self.direction_agreement is not DirectionAgreement.AGREE
        ):
            raise ValueError("confirmed requires direction_agreement=agree")
        if (
            self.verdict is Verdict.CONTRADICTED
            and self.direction_agreement is not DirectionAgreement.DISAGREE
        ):
            raise ValueError("contradicted requires direction_agreement=disagree")
        if self.verdict is Verdict.UNTESTED and self.weight != 0.0:
            raise ValueError("untested evidence must have weight 0")
        # self-corroboration + replication linkage
        if self.hit_id in self.corroborating_hit_ids:
            raise ValueError("evidence cannot corroborate its own hit")
        if self.evidence_type is EvidenceType.REPLICATION and not self.corroborating_hit_ids:
            raise ValueError("replication evidence must link corroborating_hit_ids")
        if (
            self.measurement is not None
            and self.measurement.direction is Direction.NONE
            and self.direction_agreement is not DirectionAgreement.NOT_APPLICABLE
        ):
            raise ValueError("measurement direction=none requires direction_agreement=n/a")
        # A confirmed edge is impossible without its gates (Lane A computes them):
        # metric comparability + direction reconciliation always; independence for
        # replication. This makes 'confirmed' auditable without denormalizing the hit.
        if self.verdict is Verdict.CONFIRMED:
            required = {CheckName.METRIC_MATCH, CheckName.DIRECTION_RECONCILED}
            if self.evidence_type is EvidenceType.REPLICATION:
                required.add(CheckName.INDEPENDENCE)
            missing = required - _passed_checks(self.checks)
            if missing:
                names = ", ".join(sorted(m.value for m in missing))
                raise ValueError(f"confirmed evidence requires passed checks: {names}")
        return self
