"""NEBPI observations, potency-context links and negative-search manifests.

Split out of `evidence_records.py` to keep both under the repo's 500-line rule. They are part of
the same contract, so `evidence_records` re-exports them and every existing import keeps working.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import Field, model_validator

from .contracts import ID_PATTERN, Provenance, Strict
from .evidence_types import EvidenceType


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
