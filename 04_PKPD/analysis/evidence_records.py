"""Evidence input records — one row per actual observation.

Nothing here is derived, imputed or summarized. Each record is a single observation
bound to one public source response, and every lane keeps its rows separate rather
than collapsing heterogeneous assays into a boolean.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import Field, model_validator

from .assay_records import POINT_ESTIMATE_RELATIONS, AssayBinding, Relation
from .contracts import ID_PATTERN, Provenance, Strict
from .evidence_types import EvidenceType
from .pk_records import PkDetail, RatioReport, SamplingDetail, UnboundDerivation
from .quantity import CNS_MPO_DIMENSIONS, Quantity, validate_domain

# `Provenance` now lives in `contracts` (the PK records need it too, and a contract module
# that imports the records it constrains is a cycle). Re-exported here so every existing
# `from .evidence_records import Provenance` keeps working.
__all__ = ["Provenance"]


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
    """MEC / potency, with the biological context that makes it comparable.

    `metric` keeps MEC, IC50, IC90, EC50 and Ki DISTINCT, and no transform between them is
    supplied: deriving an MEC from an IC50 needs an unbound fraction and a declared PD model,
    and Stage 4 supplies neither silently. A richer assay binding makes an IC50 better
    documented; it does not make it a minimum effective concentration.

    `relation` is the v2 addition that changes conclusions. A source that says `IC50 > 10000
    nM` is saying the assay ran OUT OF RANGE, not that the effect occurs at 10 uM. Only `=` is
    a point estimate, and only a point estimate may be the denominator of an exposure margin.
    It defaults to `=` because that is exactly how a v1 row's bare magnitude was already read —
    so v1 rows keep their meaning rather than silently acquiring a new one.
    """

    potency_id: str = Field(pattern=ID_PATTERN)
    candidate_id: str = Field(pattern=ID_PATTERN)
    active_moiety_id: str = Field(pattern=ID_PATTERN)
    metric: Literal["MEC", "IC50", "IC90", "EC50", "Ki", "target_concentration"]
    relation: Relation = Relation.EQ
    value_source_string: str
    units: str
    binding_state: Literal["free", "total", "unspecified"]
    assay: str
    biological_context: str  # the tumour/model the potency was actually measured against
    evidence_type: EvidenceType
    # v2: the structured activity/assay/target/document identity. Optional on the model so a
    # v1 bundle stays valid; REQUIRED by the v2 acquisition profile (`contract_profile.py`).
    assay_binding: Optional[AssayBinding] = None
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

    @property
    def is_point_estimate(self) -> bool:
        """`>`/`<`/`~` are bounds and approximations, not magnitudes to divide by."""
        return self.relation in POINT_ESTIMATE_RELATIONS

    @property
    def is_target_concentration(self) -> bool:
        """Whether this is an admissible denominator for an exposure margin at all."""
        return self.metric in ("MEC", "target_concentration")


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
    # --- v2: the context a clinical PK number needs before it means anything. Optional on the
    # model so a v1 bundle stays valid; REQUIRED by the v2 profile (`contract_profile.py`).
    # WHICH exposure (Cmax vs Ctrough), over how many subjects, with what spread.
    pk_detail: Optional[PkDetail] = None
    # How/where/when the sample was taken; residual-blood correction; probe recovery.
    sampling: Optional[SamplingDetail] = None
    # A brain concentration under dexamethasone + an enzyme-inducing antiseizure drug is not
    # the same exposure as one without them. GBM patients are rarely on neither.
    co_medications: list[str] = Field(default_factory=list)
    assay_method: Optional[str] = None
    # The plasma measurement this brain/CSF sample is paired with. Every ratio needs one, and
    # integrity checks that it resolves to a real PLASMA row of the same moiety and context.
    paired_plasma_measurement_id: Optional[str] = Field(default=None, pattern=ID_PATTERN)
    # Was this free concentration MEASURED, or obtained by multiplying a total by an fu? The
    # two are not the same evidence: the second inherits every assumption in the fu. `measured`
    # is the default because that is what a v1 `binding_state="free"` row already meant.
    binding_state_basis: Literal["measured", "derived_from_fraction_unbound"] = "measured"
    unbound_derivation: Optional[UnboundDerivation] = None
    # Kp / Kp,uu as structured reported-or-derived ratios. The v1 `*_reported_source_string`
    # fields remain the REPORTED lane (their names say so); these supersede them and can also
    # express a derivation.
    kp: Optional[RatioReport] = None
    kp_uu_brain: Optional[RatioReport] = None
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
        self._check_unbound_derivation()
        self._check_ratios()
        return self

    def _check_unbound_derivation(self) -> None:
        derived = self.binding_state_basis == "derived_from_fraction_unbound"
        if derived and self.unbound_derivation is None:
            raise ValueError(
                "binding_state_basis='derived_from_fraction_unbound' requires unbound_derivation: "
                "C_free = C_total * fu is an INFERENCE, and the audit requires both the "
                "source-bound inputs and the exact declared transform. Without them a calculated "
                "free concentration is indistinguishable from a measured one."
            )
        if derived and self.binding_state != "free":
            raise ValueError(
                f"binding_state is {self.binding_state!r} but the row claims to have DERIVED an "
                "unbound concentration. You do not derive a free concentration and then call it "
                "total."
            )
        if not derived and self.unbound_derivation is not None:
            raise ValueError(
                "unbound_derivation is set but binding_state_basis says the value was measured. "
                "A row cannot be both a measurement and a calculation."
            )

    def _check_ratios(self) -> None:
        # The v1 firewall blocked a CSF row from reporting a brain Kp,uu. The v2 structured
        # field must not become a way around it: the blood-CSF barrier is still not the BBB,
        # however richly the row is annotated, and a DERIVED ratio is if anything worse.
        if self.matrix == "csf" and self.kp_uu_brain is not None:
            raise ValueError(
                "a CSF measurement must not carry a brain Kp,uu, reported or derived. Grossman "
                "2026 is explicit that the blood-CSF barrier is not the BBB, so a CSF-derived "
                "Kp,uu,brain is not an observation — it is an inference, and Stage 4 refuses it."
            )
        # One number, one value. Two representations are two chances to state it differently.
        for v1, v2, name in ((self.kp_reported_source_string, self.kp, "kp"),
                             (self.kp_uu_brain_reported_source_string, self.kp_uu_brain,
                              "kp_uu_brain")):
            if v1 is not None and v2 is not None and v2.value_source_string != v1:
                raise ValueError(
                    f"{name}: the v1 reported string ({v1!r}) and the v2 ratio "
                    f"({v2.value_source_string!r}) disagree. One measurement has one value."
                )

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


# The NEBPI and label/safety records live in `nebpi_records.py` and `safety_records.py` (the
# 500-line rule). They are part of the same contract, so they are re-exported here and every
# existing import keeps working.
from .nebpi_records import (  # noqa: E402,F401
    NebpiCriterionId,
    NebpiObservation,
    ObservationState,
    PkNebLevel,
    PotencyContextLink,
    SearchManifest,
)
from .safety_records import (  # noqa: E402,F401
    EvidenceState,
    FindingType,
    GbmScenario,
    InteractionType,
    LabelIdentity,
    SafetyEvidenceRecord,
)
