"""Evidence input records — one row per actual observation.

Nothing here is derived, imputed or summarized. Each record is a single observation
bound to one public source response, and every lane keeps its rows separate rather
than collapsing heterogeneous assays into a boolean.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import Field, model_validator

from .contracts import ID_PATTERN, SHA256_PATTERN, Strict
from .quantity import CNS_MPO_DIMENSIONS, Quantity, validate_domain


# --------------------------------------------------------------------------- shared

class Provenance(Strict):
    """The binding from a number to the response it came from."""

    source_record_id: str = Field(pattern=ID_PATTERN)
    source_url: Optional[str] = None
    access_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    release_version: Optional[str] = None
    raw_response_sha256: str = Field(pattern=SHA256_PATTERN)
    extraction_transform: str  # exact, deterministic: how the value was taken out


class EvidenceType(str, Enum):
    IN_VITRO = "in_vitro"
    IN_VIVO_ANIMAL = "in_vivo_animal"
    HUMAN_CLINICAL = "human_clinical"
    IN_SILICO = "in_silico"
    LABEL = "label"


# ------------------------------------------------------------------ CNS-MPO inputs

PropertyId = Literal["clogp", "clogd_74", "mw", "tpsa", "hbd", "pka_most_basic"]


class PropertyRecord(Strict):
    """One of the six CNS-MPO inputs, for one active moiety.

    The calculator is part of the record, not an afterthought: two ClogD values from two
    packages are two different numbers, and mixing them silently would make the score
    untraceable.

    The magnitude is an exact source string plus a declared unit -- never a bare float.
    `MW = 0.6 kg_per_mol` is 600 g/mol, not 0.6; the audit found it scoring a perfect
    1.0. The unit must match the property's physical dimension or the record is refused.

    `property_record_id` identifies the ROW, and `property_id` names which of the six
    CNS-MPO inputs it carries. They are not the same thing: the audit supplied two agreeing
    ClogP rows with different provenance, the selector took `rows[0]`, and one
    scorecard_set_id then carried two different provenance chains depending on list order.
    A row without an identity cannot be deduplicated, sorted or bound, so it has one.
    """

    property_record_id: str = Field(pattern=ID_PATTERN)
    candidate_id: str = Field(pattern=ID_PATTERN)
    active_moiety_id: str = Field(pattern=ID_PATTERN)
    property_id: PropertyId
    value_source_string: str
    units: str
    determination: Literal["experimental", "predicted"]
    calculator_id: str
    method: str
    software_version: Optional[str] = None
    database_version: Optional[str] = None
    provenance: Provenance

    @model_validator(mode="after")
    def _units_and_domain(self) -> "PropertyRecord":
        q = Quantity.parse(self.value_source_string, self.units,
                           expected_dimension=CNS_MPO_DIMENSIONS[self.property_id])
        validate_domain(self.property_id, q)
        return self

    @property
    def quantity(self) -> Quantity:
        return Quantity.parse(self.value_source_string, self.units,
                              expected_dimension=CNS_MPO_DIMENSIONS[self.property_id])


class PotencyRecord(Strict):
    """MEC / potency, with the biological context that makes it comparable."""

    potency_id: str = Field(pattern=ID_PATTERN)
    candidate_id: str = Field(pattern=ID_PATTERN)
    active_moiety_id: str = Field(pattern=ID_PATTERN)
    metric: Literal["MEC", "IC50", "IC90", "EC50", "Ki", "target_concentration"]
    value_source_string: str
    units: str
    binding_state: Literal["free", "total", "unspecified"]
    assay: str
    biological_context: str  # the tumour/model the potency was actually measured against
    evidence_type: EvidenceType
    provenance: Provenance

    @model_validator(mode="after")
    def _positive_concentration(self) -> "PotencyRecord":
        q = self.quantity
        if q.decimal <= 0:
            raise ValueError(f"potency must be positive (got {self.value_source_string})")
        return self

    @property
    def quantity(self) -> Quantity:
        return Quantity.parse(self.value_source_string, self.units)


# --------------------------------------------------------------------- transporters


class TransporterObservation(Strict):
    """One transporter observation. Never collapsed into 'is a P-gp substrate: true'."""

    observation_id: str = Field(pattern=ID_PATTERN)
    candidate_id: str = Field(pattern=ID_PATTERN)
    active_moiety_id: str = Field(pattern=ID_PATTERN)
    transporter: str  # e.g. ABCB1_Pgp, ABCG2_BCRP
    transporter_gene: Optional[str] = None
    interaction: Literal["substrate", "inhibitor", "inducer", "not_a_substrate", "inconclusive"]
    assay: str  # e.g. MDCK-MDR1 bidirectional efflux ratio
    species: str  # e.g. human, mouse, canine_cell_line
    biological_system: str  # e.g. MDCKII-MDR1 monolayer
    concentration: Optional[float] = None
    concentration_units: Optional[str] = None
    result_metric: Optional[str] = None  # e.g. efflux_ratio
    result_value: Optional[float] = None
    result_units: Optional[str] = None
    direction: Optional[Literal["efflux", "uptake", "none", "not_applicable"]] = None
    evidence_type: EvidenceType
    provenance: Provenance

    @model_validator(mode="after")
    def _units_with_values(self) -> "TransporterObservation":
        if self.concentration is not None and not self.concentration_units:
            raise ValueError("concentration without units")
        if self.result_value is not None and not self.result_metric:
            raise ValueError("result_value without result_metric")
        return self


# ------------------------------------------------------------------------ exposure


class ExposureMeasurement(Strict):
    """One actual measured exposure. Kp / Kp,uu only when the source reports them."""

    measurement_id: str = Field(pattern=ID_PATTERN)
    candidate_id: str = Field(pattern=ID_PATTERN)
    active_moiety_id: str = Field(pattern=ID_PATTERN)
    context_id: str = Field(pattern=ID_PATTERN)
    formulation: str
    route: str
    dose: str
    schedule: str
    species_population: str
    matrix: Literal[
        "plasma",
        "blood",
        "csf",
        "brain_tissue_non_enhancing",
        "brain_tissue_enhancing",
        "brain_tissue_unspecified",
        "normal_animal_brain",
        "tumor_tissue_unspecified",
        "microdialysate_brain_isf",
    ]
    enhancement_context: Literal["non_enhancing", "enhancing", "not_applicable", "unknown"]
    binding_state: Literal["free", "total", "unspecified"]
    # Exact source string + declared unit. Never a float: 1e-12 and 4e-11 must not share
    # an identity, and the audit showed they did under a universal rounding grid.
    concentration_source_string: Optional[str] = None
    concentration_units: Optional[str] = None
    # What the SOURCE said about detectability. This is what separates Grossman's
    # "low PK levels in NEB" from "little to no drug in NEB" -- Stage 4 does not invent a
    # threshold to tell them apart.
    detection_status: Literal["quantified", "below_lloq", "not_detected"] = "quantified"
    # The assay's numeric ceiling on a censored result, as the SOURCE reported it. A
    # non-detect is a statement about the assay, not about the drug: without knowing how
    # low the assay could see, "not detected" cannot establish that the MEC was not
    # reached. Table 2 footnote (a) -- "Accounting for potency" -- is attached to the
    # little-to-none branch too, so this bound is what makes that branch checkable.
    quantitation_limit_kind: Optional[Literal["lod", "lloq"]] = None
    quantitation_limit_source_string: Optional[str] = None
    quantitation_limit_units: Optional[str] = None
    timepoint: Optional[str] = None
    # Only when the SOURCE reports them. Never derived here, and never from CSF.
    kp_reported_source_string: Optional[str] = None
    kp_uu_brain_reported_source_string: Optional[str] = None
    evidence_type: EvidenceType
    provenance: Provenance

    @model_validator(mode="after")
    def _rules(self) -> "ExposureMeasurement":
        if self.concentration_source_string is not None and not self.concentration_units:
            raise ValueError("concentration without units")
        if self.concentration_source_string is not None:
            Quantity.parse(self.concentration_source_string, self.concentration_units or "")
        if self.detection_status == "quantified" and self.concentration_source_string is None:
            raise ValueError("detection_status='quantified' requires a concentration")
        if self.matrix == "csf" and self.kp_uu_brain_reported_source_string is not None:
            # Grossman 2026: the blood-CSF barrier is not the BBB. A CSF-derived
            # Kp,uu,brain is not an observation, it is an inference we refuse.
            raise ValueError("kp_uu_brain_reported must not be set on a CSF measurement")
        self._check_quantitation_limit()
        return self

    def _check_quantitation_limit(self) -> None:
        parts = (self.quantitation_limit_kind, self.quantitation_limit_source_string,
                 self.quantitation_limit_units)
        if any(p is not None for p in parts) and not all(p is not None for p in parts):
            raise ValueError(
                "a quantitation limit needs all three of kind, source string and units: a "
                "magnitude without a unit, or a unit without a kind, is not a bound"
            )
        if self.quantitation_limit_source_string is None:
            return
        q = Quantity.parse(self.quantitation_limit_source_string,
                           self.quantitation_limit_units or "")
        if q.decimal <= 0:
            raise ValueError(
                f"a quantitation limit must be positive (got {self.quantitation_limit_source_string})"
            )
        if self.detection_status == "below_lloq" and self.quantitation_limit_kind != "lloq":
            # A below_lloq value may still lie ABOVE the LOD, so an LOD is not an upper
            # bound on it. Only the LLOQ bounds it.
            raise ValueError(
                "detection_status='below_lloq' must be bounded by an 'lloq', not an "
                f"{self.quantitation_limit_kind!r}: the true value may lie between the LOD "
                "and the LLOQ, so an LOD does not bound it from above"
            )

    @property
    def quantity(self) -> Optional[Quantity]:
        if self.concentration_source_string is None or not self.concentration_units:
            return None
        return Quantity.parse(self.concentration_source_string, self.concentration_units)

    @property
    def quantitation_limit(self) -> Optional[Quantity]:
        """The source-declared upper bound on a censored result, or None."""
        if self.quantitation_limit_source_string is None or not self.quantitation_limit_units:
            return None
        return Quantity.parse(self.quantitation_limit_source_string,
                              self.quantitation_limit_units)


# ------------------------------------------------------------------------ delivery


class DeliveryRequirement(str, Enum):
    LOCAL_CNS = "local_CNS_target_engagement_required"
    SYSTEMIC_PRIMING = "systemic_immune_priming"
    UNCERTAIN = "delivery_requirement_uncertain"


class DeliveryBasis(str, Enum):
    """What the assignment actually rests on.

    `target_biology_only` exists so that the commonest bad inference — "the target is
    an immune gene, therefore the drug works by systemic priming" — has to be declared
    out loud, and can then be refused.
    """

    TARGET_BIOLOGY_ONLY = "target_biology_only"
    MECHANISM_WITH_PHARMACOLOGY_EVIDENCE = "mechanism_with_pharmacology_evidence"
    CLINICAL_EVIDENCE = "clinical_evidence"
    EXPERT_REVIEW = "expert_review"


class DeliveryAssignment(Strict):
    """Who said so, on what rule, on what evidence.

    Two audit findings are answered here.

    `assignment_id` — the row had no identity, so the reducer could only take `mine[0]`.
    Two assignments for one (candidate, context) then produced `local_CNS` or `uncertain`
    purely on list order, under ONE scorecard_set_id.

    `evidence` — the binding used to be a bare (source id, sha256) string pair that
    nothing resolved. An assignment citing `src.DOES_NOT_EXIST` with an invented hash was
    accepted and set the NEBPI primary gate. It is now the same `Provenance` contract every
    other evidence row carries, so it goes through the one source-registry binding pass and
    an unknown/unacquired/hash-mismatched source is refused before anything is classified.
    """

    assignment_id: str = Field(pattern=ID_PATTERN)
    candidate_id: str = Field(pattern=ID_PATTERN)
    context_id: str = Field(pattern=ID_PATTERN)
    requirement: DeliveryRequirement
    basis: DeliveryBasis
    assigned_by: str  # a named human reviewer or a named rule id — never a model
    rule_id: str
    rule_version: str
    rationale: str
    # Absent is legal and means "unevidenced" -> the assignment is downgraded to uncertain.
    # Present means it MUST resolve to acquired bytes in the source registry.
    evidence: Optional[Provenance] = None


# --------------------------------------------------------------------------- NEBPI


class NebpiCriterionId(str, Enum):
    PHYSICAL_CHARACTERISTICS = "physical_characteristics"
    PERMEABILITY_NORMAL_ANIMAL_BRAIN = "permeability_normal_animal_brain"
    KNOWN_MEC_POTENCY = "known_mec_potency"
    PK_IN_NEB = "pk_in_neb"
    PD_IN_NEB = "pd_in_neb"
    CSF_DRUG_LEVELS = "csf_drug_levels"
    RESPONSE_IN_ENHANCING_LESIONS = "response_in_enhancing_lesions"
    IN_VITRO_BBB_PERMEABILITY = "in_vitro_bbb_permeability"
    RADIOGRAPHIC_RESPONSE_IN_NEB = "radiographic_response_in_neb"


class ObservationState(str, Enum):
    OBSERVED_PRESENT = "observed_present"
    OBSERVED_ABSENT = "observed_absent"
    NOT_EVALUATED = "not_evaluated"


class PkNebLevel(str, Enum):
    """Graded relative to the MEC — 'accounting for potency' (Table 2 footnote a)."""

    THERAPEUTIC = "pk_therapeutic_in_neb"
    LOW = "pk_low_in_neb"
    LITTLE_TO_NONE = "pk_little_to_none_in_neb"
    NOT_EVALUATED = "pk_not_evaluated"


class NebpiObservation(Strict):
    """One NEBPI criterion observation in one evidence context.

    A PK-in-NEB observation is NOT a free categorical assertion. The audit produced
    `sufficiently_permeable` from `state=not_evaluated` + `pk_level=therapeutic` + a
    measurement id that did not exist + an IC50 for the wrong moiety in the wrong tumour.
    So `pk_level` is gone as an input: a PK observation must NAME the measurement and the
    potency record it rests on, and `nebpi.py` DERIVES the Grossman PK level from that
    bound concentration-versus-MEC comparison. An observation cannot assert its own
    conclusion.
    """

    observation_id: str = Field(pattern=ID_PATTERN)
    candidate_id: str = Field(pattern=ID_PATTERN)
    context_id: str = Field(pattern=ID_PATTERN)
    criterion_id: NebpiCriterionId
    state: ObservationState
    # An "observed_absent" claim is only usable if an adequate assessment was made.
    assessment_adequate: Optional[bool] = None
    adequacy_rationale: Optional[str] = None
    # Required for pk_in_neb: the measurement, and the MEC it is compared against
    # (Table 2 footnote a, "Accounting for potency").
    potency_id: Optional[str] = Field(default=None, pattern=ID_PATTERN)
    measurement_id: Optional[str] = Field(default=None, pattern=ID_PATTERN)
    evidence_type: EvidenceType
    provenance: Provenance

    @model_validator(mode="after")
    def _rules(self) -> "NebpiObservation":
        if self.criterion_id == NebpiCriterionId.PK_IN_NEB:
            if self.state != ObservationState.OBSERVED_PRESENT:
                raise ValueError(
                    "a pk_in_neb observation records a measurement that was actually made, so "
                    "its state must be observed_present. 'No PK was measured in NEB' is the "
                    "absence of this row; 'drug was looked for and not found' is a measurement "
                    "with detection_status=not_detected."
                )
            if not self.measurement_id or not self.potency_id:
                raise ValueError(
                    "pk_in_neb requires BOTH measurement_id and potency_id: the Grossman PK "
                    "level is derived from the measured NEB concentration against the MEC, "
                    "never asserted"
                )
        elif self.measurement_id or self.potency_id:
            raise ValueError(
                f"{self.criterion_id.value} must not carry a measurement/potency link; only "
                "pk_in_neb is a concentration-vs-MEC comparison"
            )
        if self.state == ObservationState.OBSERVED_ABSENT and self.assessment_adequate is None:
            raise ValueError(
                "observed_absent requires assessment_adequate: absence of evidence is not "
                "evidence of absence unless an adequate assessment looked for it"
            )
        return self


class PotencyContextLink(Strict):
    """The ONLY way a potency measured in one biological context may be used in another.

    Previously an untyped dict that never entered the id: the audit turned a margin from
    not_computable into computed without changing the scorecard id. It is now a first
    class, source-bound evidence row like any other.
    """

    link_id: str = Field(pattern=ID_PATTERN)
    potency_id: str = Field(pattern=ID_PATTERN)
    tumor_context: str
    rationale: str
    provenance: Provenance


class SearchManifest(Strict):
    """A reproducible negative search. Without one, absence stays `not_evaluated`.

    `no_evidence_found` is a claim about a search that was actually run, so it has to
    carry the query that was run, against which endpoint, at which release, and the hash
    of the response that came back empty. A list of source *names* is not a search.

    The audit appended a SECOND manifest with the same `search_id`, an invented endpoint
    and an invented response hash, and the pipeline kept both and kept the safety row. The
    manifest is now source-bound like every other evidence row: `provenance` names the
    registered source record whose acquired bytes ARE the empty response, and
    `response_sha256` is that binding's hash rather than a number the caller may assert.
    A caller-authored negative-search claim cannot pass as sourced evidence.
    """

    search_id: str = Field(pattern=ID_PATTERN)
    source: str
    endpoint: str
    query_canonical: str
    search_scope: str
    executed_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    source_release: Optional[str] = None
    n_results: int = Field(ge=0)
    provenance: Provenance

    @property
    def response_sha256(self) -> str:
        """The hash of the response that came back empty — the source binding's hash."""
        return self.provenance.raw_response_sha256

    @model_validator(mode="after")
    def _empty_means_empty(self) -> "SearchManifest":
        if self.n_results != 0:
            raise ValueError(
                "a search manifest backing 'no_evidence_found' must have returned 0 results; "
                f"this one returned {self.n_results}"
            )
        return self


# ---------------------------------------------------------------------- label/safety


class EvidenceState(str, Enum):
    LABEL_SUPPORTED = "label_supported"
    LITERATURE_SUPPORTED = "literature_supported"
    SIGNAL_ONLY = "signal_only"
    NO_EVIDENCE_FOUND = "no_evidence_found"
    NOT_EVALUATED = "not_evaluated"


class FindingType(str, Enum):
    BOXED_WARNING = "boxed_warning"
    CONTRAINDICATION = "contraindication"
    WARNING_PRECAUTION = "warning_precaution"
    LABELED_INTERACTION = "labeled_interaction"
    ADVERSE_REACTION = "adverse_reaction"


class GbmScenario(str, Enum):
    TEMOZOLOMIDE = "temozolomide"
    RADIATION = "radiation"
    CORTICOSTEROID_EXPOSURE = "corticosteroid_exposure"
    ANTISEIZURE_THERAPY = "antiseizure_therapy"
    PERIOPERATIVE_SETTING = "perioperative_setting"


class InteractionType(str, Enum):
    PK_INTERACTION = "pk_interaction"
    OVERLAPPING_TOXICITY = "overlapping_toxicity"
    MARROW_EFFECTS = "marrow_effects"
    INFECTION_LIABILITY = "infection_liability"
    IMMUNE_ACTIVATION_AUTOIMMUNITY = "immune_activation_autoimmunity"
    BLEEDING = "bleeding"
    QT_CARDIAC = "qt_cardiac"
    MECHANISTIC_ANTAGONISM = "mechanistic_antagonism"


class LabelIdentity(Strict):
    """Exactly which label version an assertion came from."""

    label_source: Literal["dailymed_spl", "openfda_label", "ema_label"]
    setid: Optional[str] = None
    application_number: Optional[str] = None
    product_identity: str
    label_version: Optional[str] = None
    effective_date: Optional[str] = None
    labeled_section_code: Optional[str] = None
    labeled_section_name: Optional[str] = None
    code_system: Optional[str] = None


class SafetyEvidenceRecord(Strict):
    """One row per finding. Never a summary, never a memory of a label."""

    evidence_id: str = Field(pattern=ID_PATTERN)
    candidate_id: str = Field(pattern=ID_PATTERN)
    active_moiety_id: str = Field(pattern=ID_PATTERN)
    evidence_state: EvidenceState
    finding_type: Optional[FindingType] = None
    finding_text: Optional[str] = None
    gbm_scenario: Optional[GbmScenario] = None
    interaction_type: Optional[InteractionType] = None
    label_identity: Optional[LabelIdentity] = None
    searched_sources: list[str] = Field(default_factory=list)
    # Required for no_evidence_found: the reproducible search behind the claim.
    search_id: Optional[str] = Field(default=None, pattern=ID_PATTERN)
    provenance: Optional[Provenance] = None

    @model_validator(mode="after")
    def _rules(self) -> "SafetyEvidenceRecord":
        if self.evidence_state == EvidenceState.LABEL_SUPPORTED:
            if self.label_identity is None or self.provenance is None:
                raise ValueError("label_supported requires label_identity and provenance")
            if self.finding_type is None or not self.finding_text:
                raise ValueError("label_supported requires finding_type and finding_text")
        if self.evidence_state == EvidenceState.LITERATURE_SUPPORTED and self.provenance is None:
            raise ValueError("literature_supported requires provenance")
        if self.evidence_state == EvidenceState.NO_EVIDENCE_FOUND:
            if not self.searched_sources:
                raise ValueError(
                    "no_evidence_found requires searched_sources: it is a claim about the "
                    "search, and without them it is indistinguishable from not_evaluated"
                )
            if not self.search_id:
                raise ValueError(
                    "no_evidence_found requires search_id -> a SearchManifest (query, endpoint, "
                    "release, scope, response hash). An unreproducible negative search is not "
                    "evidence of anything and must stay not_evaluated."
                )
        if self.evidence_state != EvidenceState.NO_EVIDENCE_FOUND and self.search_id:
            raise ValueError("search_id is only meaningful for no_evidence_found")
        return self
