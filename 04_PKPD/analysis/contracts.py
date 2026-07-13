"""Stage-4 input contracts.

`Stage3DrugCandidateSet` below is the NORMALIZED, Stage-4-internal candidate set the pipeline
consumes. **It is not Stage 3's wire format**, and nothing here should be read as a description
of what Stage 3 emits. Keeping the two apart is the whole point: Stage 4 never widens these
models to absorb whatever arrives.

Stage 3 has landed and emits its own documents. They reach the shape below through exactly TWO
adapters, one per document family:

    spot.stage03_drug_annotation.v1      -> stage3_annotation.py  (spot.stage34_annotation_adapter.v1)
                                            admission signal: stage4_assessment_status=queued

    spot.stage03_drug_candidate_set.v1   -> stage3_adapter.py     (spot.stage34_adapter.v1)
    spot.stage03_research_annotation.v1     research_only: INSPECTION ONLY, zero candidates
    spot.fixture.stage03_bundle.v1          fixture

Both adapters re-verify Stage-3's canonical/document/table hashes and preserve namespace, source
status and eligibility. Admission takes **two gates**: Stage 4 restates the bundle byte-for-byte,
AND Stage 3's own `verifier.verify_stage3` must pass out-of-process. Schema-valid is not admitted.

Nothing here states Stage 3's internal condition (how many tests it has, whether it is frozen,
what it can produce today). Stage 4 cannot verify those, they drift the moment Stage 3 moves, and
they were being compiled into a SERVED schema. What a release says about its upstream is bound to
the bundle it actually admitted -- see `Stage3Binding` and the v2 `upstream.stage3_admission`
block, which are derived from the bytes, not declared here.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

STAGE3_SCHEMA_ID = "spot.stage03_drug_candidate_set.v1"
STAGE4_METHOD_VERSION = "stage4-evidence-v2"

# Surfaced in manifest.json, scorecards.json and the exported schema.
STAGE3_CONTRACT_STATUS = {
    "status": "reconciled_via_adapter",
    "stage3_implementation_landed": True,
    "internal_form_note": (
        "Stage3DrugCandidateSet is the Stage-4-internal NORMALIZED form, NOT Stage 3's wire "
        "format. Stage 3's real schemas live in 03_druglink/schemas/."
    ),
    # One entry per document Stage 4 actually admits, and the adapter that admits it. This is a
    # statement about STAGE 4's doors -- which Stage 4 can verify -- not about Stage 3's health.
    "adapters": {
        "spot.stage34_annotation_adapter.v1": {
            "module": "analysis/stage3_annotation.py",
            "consumes": ["spot.stage03_drug_annotation.v1"],
            "admission_signal": "stage4_assessment_status=queued",
        },
        "spot.stage34_adapter.v1": {
            "module": "analysis/stage3_adapter.py",
            "consumes": [
                "spot.stage03_drug_candidate_set.v1",
                "spot.stage03_research_annotation.v1",
                "spot.fixture.stage03_bundle.v1",
            ],
            "research_only_note": "a research annotation is INSPECTED, never admitted",
        },
    },
    "admission_gates": [
        "gate 1: Stage 4 restates the bundle byte-for-byte (canonical/document/table hashes)",
        "gate 2: Stage 3's own verifier.verify_stage3 passes out-of-process",
        "schema-valid is NOT admitted; both gates are required",
    ],
    # Deliberately absent: any test count, freeze flag or producible-today claim about Stage 3.
    # They are unverifiable from here, they drift the moment Stage 3 moves, and a served schema
    # is the worst place to freeze them. A run's actual upstream binding is emitted instead.
    "real_result_status": (
        "No selection-specific real run has been admitted in this repo state: every candidate in "
        "the test corpus is a labelled FIXTURE-*. A real Stage-4 result is gated on an "
        "externally admitted real Stage-3 bundle."
    ),
}


# An id that will be used in a filesystem path or a join key. Deliberately strict.
ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
SHA256_PATTERN = r"^[0-9a-f]{64}$"


class Strict(BaseModel):
    """Unknown fields are a rejection, not a warning: an unrecognised field may be a
    field we would have had to reason about."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


class Provenance(Strict):
    """The binding from a number to the response it came from.

    Lives here rather than in `evidence_records` because the PK records need it too, and a
    contract module that has to import the records it constrains is a cycle waiting to happen.
    `evidence_records` re-exports it, so every existing import keeps working.
    """

    source_record_id: str = Field(pattern=ID_PATTERN)
    source_url: Optional[str] = None
    access_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    release_version: Optional[str] = None
    raw_response_sha256: str = Field(pattern=SHA256_PATTERN)
    extraction_transform: str  # exact, deterministic: how the value was taken out


class Namespace(str, Enum):
    """Preserved from Stage 3, never upgraded here.

    `fixture` matches Stage 3's third namespace: a synthetic engine exercise that is not
    evidence about anything and can never become production.
    """

    PRODUCTION = "production"
    RESEARCH_ONLY = "research_only"
    FIXTURE = "fixture"


class AcquisitionStatus(str, Enum):
    """How the bytes behind a source came to exist. Stage 3 uses the same three."""

    ACQUIRED_PUBLIC = "acquired_public"
    SYNTHETIC_FIXTURE = "synthetic_fixture"
    NOT_ACQUIRED = "not_acquired"


class DirectionCompatibility(str, Enum):
    COMPATIBLE = "compatible"
    INCOMPATIBLE = "incompatible"
    UNKNOWN = "unknown"


class SourceRecord(Strict):
    """A source response/document. Every scientific number binds to one.

    A source does not get to *declare* that it is public data. It has to show the
    locator that makes it re-fetchable and the bytes that make it checkable: an
    `acquired_public` record without a URL, a stable record id, a release, a license and
    a byte count is refused. (The audit forged a scored property from a source with none
    of those.) `is_fixture` is derived from `acquisition_status`, never set by hand — so
    relabeling a fixture as public necessarily changes content identity.
    """

    source_record_id: str = Field(pattern=ID_PATTERN)
    source_type: Literal[
        "primary_literature",
        "regulatory_label",
        "public_database",
        "public_api",
        "structure_probe",
        "fixture",
    ]
    source_name: str
    acquisition_status: AcquisitionStatus
    url: Optional[str] = None
    record_id: Optional[str] = None
    access_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    release_version: Optional[str] = None
    license: Optional[str] = None
    raw_sha256: Optional[str] = Field(default=None, pattern=SHA256_PATTERN)
    raw_bytes: Optional[int] = Field(default=None, ge=0)
    raw_media_type: Optional[str] = None

    @property
    def is_fixture(self) -> bool:
        return self.acquisition_status == AcquisitionStatus.SYNTHETIC_FIXTURE

    @property
    def source_class(self) -> str:
        """The provenance class that binds into the artifact id.

        Read through `str()` rather than `.value`: `model_copy(update=...)` bypasses
        validation and can leave a bare string here, and a provenance class that crashes
        on inspection is worse than one that reads plainly. Comparisons elsewhere use the
        enum members, which equal their string values.
        """
        return str(getattr(self.acquisition_status, "value", self.acquisition_status))

    @model_validator(mode="after")
    def _acquisition_evidence(self) -> "SourceRecord":
        st = self.acquisition_status
        if st == AcquisitionStatus.ACQUIRED_PUBLIC:
            missing = [
                f
                for f in ("url", "record_id", "release_version", "license", "raw_sha256")
                if not getattr(self, f)
            ]
            if not self.raw_bytes:
                missing.append("raw_bytes")
            if missing:
                raise ValueError(
                    f"acquired_public source {self.source_record_id!r} is missing {sorted(missing)}. "
                    "A public source must carry the locator that makes it re-fetchable and the "
                    "bytes that make it checkable; it cannot simply declare itself public."
                )
            if self.source_type == "fixture":
                raise ValueError("source_type='fixture' cannot be acquisition_status='acquired_public'")
        elif st == AcquisitionStatus.SYNTHETIC_FIXTURE:
            if not self.raw_sha256:
                raise ValueError("a synthetic fixture must still hash the exact bytes it parsed")
        elif st == AcquisitionStatus.NOT_ACQUIRED:
            if self.raw_sha256 or self.raw_bytes:
                raise ValueError(
                    "not_acquired means there are no bytes; a hash here would be a fiction"
                )
        return self


AdministeredForm = Literal["active_moiety", "salt", "prodrug", "ester", "other"]


class ActiveMoiety(Strict):
    """Identity of what is actually in the body.

    Salt / prodrug / metabolite mapping is explicit or the candidate is rejected: a
    silent salt-vs-moiety mix-up corrupts MW, exposure and every join downstream.
    """

    active_moiety_id: str = Field(pattern=ID_PATTERN)
    active_moiety_name: str
    unii: Optional[str] = Field(default=None, pattern=r"^[A-Z0-9]{10}$")
    inchikey: Optional[str] = Field(default=None, pattern=r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$")
    administered_form: AdministeredForm = "active_moiety"
    administered_form_name: Optional[str] = None
    # Required whenever administered_form != active_moiety.
    maps_to_active_moiety_id: Optional[str] = Field(default=None, pattern=ID_PATTERN)
    mapping_source_record_id: Optional[str] = Field(default=None, pattern=ID_PATTERN)

    @field_validator("maps_to_active_moiety_id")
    @classmethod
    def _no_self_map(cls, v: Optional[str], info) -> Optional[str]:
        return v


class CompoundIds(Strict):
    chembl_id: Optional[str] = None
    pubchem_cid: Optional[str] = None
    drugbank_id: Optional[str] = None
    rxcui: Optional[str] = None


class Stage3Candidate(Strict):
    candidate_id: str = Field(pattern=ID_PATTERN)
    active_moiety: ActiveMoiety
    compound_ids: CompoundIds
    target: str
    mechanism: str
    program_direction: Literal["up", "down", "unspecified"]
    drug_effect_direction: Literal["up", "down", "unspecified"]
    direction_compatibility: DirectionCompatibility
    namespace: Namespace
    stage3_evidence_source_record_ids: list[str] = Field(default_factory=list)


class Stage3Binding(Strict):
    """The exact Stage-3 document this candidate set was adapted from.

    Populated by `stage3_adapter.py` from a real Stage-3 emission. It is None only for
    the engine's own internal fixtures, which are labelled as such.
    """

    stage3_schema_version: str
    stage3_document_id: str
    stage3_namespace: Namespace
    canonical_content_sha256: str = Field(pattern=SHA256_PATTERN)
    document_sha256: str = Field(pattern=SHA256_PATTERN)
    table_hashes: dict[str, str] = Field(default_factory=dict)
    # Stage-3's own method identity — its code tree, adapters, schemas and env lock.
    stage3_method: dict[str, str] = Field(default_factory=dict)
    # Stage-3's upstream selection/run binding (question/selection/run/lever-set).
    stage3_upstream: dict[str, str] = Field(default_factory=dict)
    stage3_source_status: dict[str, int] = Field(default_factory=dict)
    stage3_eligible: bool
    stage4_eligible: bool
    production_candidate: bool
    adapter_id: str
    adapter_version: str
    # Which frozen transcription of Stage-3's table contract reconstructed the content
    # hashes above. Re-transcribe the contract and the scorecard id moves with it.
    stage3_table_contract_version: Optional[str] = None
    stage3_table_contract_sha256: Optional[str] = Field(default=None, pattern=SHA256_PATTERN)


class Stage3DrugCandidateSet(Strict):
    """The NORMALIZED candidate set the Stage-4 pipeline consumes.

    This is a Stage-4-internal form, not a claim about Stage 3's wire format. The only
    supported path from a real Stage-3 emission into this shape is `stage3_adapter.py`,
    which verifies Stage-3's canonical/document/table hashes and carries them here in
    `stage3_binding`. `is_fixture` and `namespace` are propagated from Stage 3 and are
    never widened.
    """

    schema_id: Literal["spot.stage03_drug_candidate_set.v1"]
    stage3_run_id: str = Field(pattern=ID_PATTERN)
    candidate_set_id: str = Field(pattern=ID_PATTERN)
    # sha256 over the canonical content of `candidates`. Recomputed and compared at
    # the firewall: a biology-only id is never trusted as a cache key.
    candidate_rows_sha256: str = Field(pattern=SHA256_PATTERN)
    namespace: Namespace
    stage3_method_version: str
    upstream_contrast_id: Optional[str] = None
    upstream_gene_lever_set_sha256: Optional[str] = Field(default=None, pattern=SHA256_PATTERN)
    candidates: list[Stage3Candidate] = Field(min_length=1)
    is_fixture: bool = False
    stage3_binding: Optional[Stage3Binding] = None


class EvidenceContext(Strict):
    """NEBPI is a property of a CONTEXT, not of a drug.

    Grossman 2026: methotrexate is "impermeable" at standard dose for glial neoplasms
    and "sufficiently permeable" at high-dose IV for PCNSL. Same moiety. So every
    evidence lane is keyed on (candidate, context), and a drug-level class is
    structurally unrepresentable in this engine.
    """

    context_id: str = Field(pattern=ID_PATTERN)
    candidate_id: str = Field(pattern=ID_PATTERN)
    active_moiety_id: str = Field(pattern=ID_PATTERN)
    route: str
    formulation: str
    dose: str
    schedule: str
    tumor_context: str
    population: str = "adult"
    is_fixture: bool = False

    def context_completeness(self) -> list[str]:
        """Which context fields are unknown. Empty list = fully specified."""
        unknown = {"", "unknown", "unspecified", "not_specified"}
        missing = []
        for f in ("route", "formulation", "dose", "schedule", "tumor_context"):
            if str(getattr(self, f)).strip().lower() in unknown:
                missing.append(f)
        return missing
