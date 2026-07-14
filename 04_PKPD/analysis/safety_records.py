"""Label and safety evidence records.

Split out of `evidence_records.py` to keep both under the repo's 500-line rule. These are the
rows that say what a LABEL states — never what someone remembers a label stating, and never a
summary. `no_evidence_found` is a claim about a SEARCH, and it carries the search that was run.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import Field, model_validator

from .contracts import ID_PATTERN, Provenance, Strict
from .organ_system import UNSPECIFIED, OrganSystemEvidence

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
    # The nested subsection the sentence was actually read from (a real label puts its warnings
    # in `<component><section>` subsections, not on the coded section itself). The safety TYPE
    # still comes from the ancestor LOINC section; this says WHERE inside it. None for a
    # finding taken from the coded section's own direct text.
    labeled_subsection_code: Optional[str] = None
    labeled_subsection_name: Optional[str] = None


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
    # v2. WHICH organ system, in ACQUISITION's own evidence shape (`organ_system.py`): the
    # value verbatim, its `value_kind` (a controlled term or the source's own), its
    # `evidence_state`, and the exact record + locator it was read from. Never inferred from
    # target biology, gene expression, mechanism or drug class -- `refuse_inferred_organ_system`
    # makes that path raise rather than exist.
    #
    # Optional on the model so a v1 row is untouched; the v2 profile is what requires it.
    organ_system_evidence: Optional[OrganSystemEvidence] = None
    provenance: Optional[Provenance] = None

    @property
    def organ_system(self) -> str:
        """Unknown stays `unspecified`. There is no third answer."""
        if self.organ_system_evidence is None:
            return UNSPECIFIED
        return self.organ_system_evidence.organ_system

    @model_validator(mode="after")
    def _rules(self) -> "SafetyEvidenceRecord":
        self._check_organ_system()
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

    def _check_organ_system(self) -> None:
        e = self.organ_system_evidence
        if e is None or e.organ_system == UNSPECIFIED:
            return

        # The forbidden inference, in the shape it would actually take: a value with no source
        # behind it. Acquisition never produces one (an absent field yields `unspecified` /
        # `not_evaluated`), so a row that has one did not get it from a source.
        if e.evidence_state != "observed":
            raise ValueError(
                f"organ_system={e.organ_system!r} with evidence_state={e.evidence_state!r}. A "
                "value that was not observed in a source can only have been inferred from the "
                "target, the mechanism or the drug class -- which is not an observation of "
                "tissue specificity. When the source is silent the answer is 'unspecified'."
            )
        if not (e.source_record_id and e.locator):
            raise ValueError(
                f"organ_system={e.organ_system!r} must name the record it was read from and the "
                "exact place in it. 'It's in the label somewhere' is not a locator: a reviewer "
                "has to be able to go and read the sentence."
            )
        # An organ system is a property of a FINDING. Where nobody looked, or the search came
        # back empty, there is no finding to classify.
        if self.evidence_state in (EvidenceState.NOT_EVALUATED, EvidenceState.NO_EVIDENCE_FOUND):
            raise ValueError(
                f"evidence_state={self.evidence_state.value!r} carries "
                f"organ_system={e.organ_system!r}. There is no finding here to classify."
            )
