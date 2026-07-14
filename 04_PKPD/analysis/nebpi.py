"""NEBPI — Non-Enhancing Brain Permeability Index (Grossman et al., Neuro-Oncology 2026).

A criterion-level evidence model, not a score. Four things it will not do:

  * It will not let descriptors, in-vitro BBB models, CSF levels, normal-animal-brain
    permeability or responses in enhancing lesions produce a Part-II class. Those are
    Part-I inputs (importance A/C/D); they satisfy no Part-II branch.
  * It will not read "we have no data" as "impermeable". Only an *adequate assessment
    that looked and found nothing* (observed_absent) can satisfy "No relevant PD in
    NEB" / "No radiographic response in NEB".
  * It will not let the ORDER of the evidence list decide anything. Every criterion is
    reduced by `nebpi_reduce.reduce_criterion`, a function of the SET of rows: two
    distinct rows for one criterion are `conflicting` and satisfy nothing. The class,
    the branch proof, criterion_states and the emitted bytes are invariant under every
    permutation of the observation list.
  * It will not emit a drug-level class. A class belongs to a (moiety x route x dose x
    schedule x tumour) context — the source's own methotrexate example flips class on
    exactly those axes.

Class definitions and all branch logic come from method/nebpi_grossman2026_v1.json.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .contracts import EvidenceContext
from .delivery import DeliveryResult
from .evidence_records import (
    ExposureMeasurement,
    NebpiCriterionId,
    NebpiObservation,
    ObservationState,
    PkNebLevel,
    PotencyContextLink,
    PotencyRecord,
)
from .nebpi_pk import DERIVED_LEVELS, NEB_MATRICES, PkDerivation, derive_pk_level
from .nebpi_reduce import CONFLICTING, reduce_criterion

# The three Part-II qualifying positives (Table 2, "Sufficiently permeable" OR-branches).
POSITIVE_BRANCHES = ("pk_therapeutic_in_neb", "pd_in_neb", "radiographic_response_in_neb")

__all__ = [
    "BranchProof",
    "NebpiResult",
    "NEB_MATRICES",
    "POSITIVE_BRANCHES",
    "PkDerivation",
    "derive_pk_level",
    "evaluate_nebpi",
]


@dataclass
class BranchProof:
    branch_id: str
    class_id: str
    # `required` is the branch's requirement TEXT, read from method/stage4_prose_v1.json —
    # never typed here. `blocking_code` replaces what used to be a free sentence: a resealed
    # release could rewrite "an adequate assessment looked and found none" into its opposite
    # while the machine state beside it stayed honest, and nothing would notice.
    required: str
    observed: str
    satisfied: bool
    blocking_code: Optional[str]
    supporting_observation_ids: list[str] = field(default_factory=list)


@dataclass
class NebpiResult:
    candidate_id: str
    context_id: str
    nebpi_status: str  # "classified" | "not_classifiable"
    nebpi_class: Optional[str]
    nebpi_primary_gate: Optional[bool]
    delivery_requirement: str
    criterion_states: dict[str, str]
    # Which observations backed EACH criterion. Without this the criterion table could only
    # say "not_evaluated" without being able to show what was (or was not) looked at.
    criterion_observation_ids: dict[str, list[str]]
    branch_proof: list[BranchProof]
    counterfactual: dict[str, Any]
    reason_codes: list[str]
    context_caveats: list[dict[str, Any]]
    method_id: str
    method_version: str
    evidence_observation_ids: list[str]
    pk_derivation: Optional[dict[str, Any]] = None


def evaluate_nebpi(
    candidate_id: str,
    context: EvidenceContext,
    observations: list[NebpiObservation],
    potencies: list[PotencyRecord],
    delivery: DeliveryResult,
    method: dict[str, Any],
    measurements: Optional[list[ExposureMeasurement]] = None,
    potency_context_links: Optional[list[PotencyContextLink]] = None,
) -> NebpiResult:
    obs = [o for o in observations if o.candidate_id == candidate_id and o.context_id == context.context_id]
    reason_codes: list[str] = []
    caveats: list[dict[str, Any]] = []

    pk = derive_pk_level(obs, context, list(measurements or []),
                         [p for p in potencies if p.candidate_id == candidate_id],
                         list(potency_context_links or []))
    pk_level, pk_obs = pk.level, pk.observation

    # ONE reducer, for the branch logic and for criterion_states alike. There is no
    # last-row-wins path left: a criterion with two distinct rows is `conflicting`
    # everywhere it appears, whatever order they arrived in.
    pd = reduce_criterion(obs, NebpiCriterionId.PD_IN_NEB)
    rad = reduce_criterion(obs, NebpiCriterionId.RADIOGRAPHIC_RESPONSE_IN_NEB)
    pd_state, pd_obs = pd.state, pd.row
    rad_state, rad_obs = rad.state, rad.row

    criterion_states: dict[str, str] = {}
    criterion_observation_ids: dict[str, list[str]] = {}
    for spec in method["part_i_criteria"]:
        cid = spec["criterion_id"]
        criterion_states[cid] = reduce_criterion(obs, NebpiCriterionId(cid)).state
        criterion_observation_ids[cid] = sorted(
            o.observation_id for o in obs if o.criterion_id.value == cid)
    # The PK criterion state is the DERIVED level, not anything the row asserted.
    criterion_states[NebpiCriterionId.PK_IN_NEB.value] = pk_level

    # --- context gates ---------------------------------------------------------
    missing_ctx = context.context_completeness()
    if missing_ctx:
        reason_codes.append("context_incomplete")
        # A CODE plus the bound slot, not a sentence. The sentence is in the prose catalog and
        # in METHODS.md; a free sentence here would be bound by nothing.
        caveats.append({"code": "context_incomplete", "missing_context_fields": missing_ctx})

    if pk.blocked_code:
        reason_codes.append(f"pk_not_derivable:{pk.blocked_code}")
    for reduction, name in ((pd, "pd_in_neb"), (rad, "radiographic_response_in_neb")):
        if reduction.state == CONFLICTING:
            reason_codes.append(f"conflicting_observations:{name}")
            caveats.append({
                "code": "conflicting_observations",
                "criterion_id": name,
                "n_distinct_rows": reduction.n_distinct_rows,
                "observation_ids": list(reduction.conflicting_observation_ids),
            })

    potency_ids = {p.potency_id for p in potencies if p.candidate_id == candidate_id}
    if not potency_ids:
        caveats.append({"code": "no_potency_context"})

    # A PK level exists only if it was actually derived from a bound comparison. For a
    # censored measurement that means a source-declared LOD/LLOQ strictly below the MEC.
    pk_derived = pk_level in DERIVED_LEVELS
    pk_has_potency = bool(pk.potency_id)
    pk_usable = pk_derived and not missing_ctx
    ctx_ok = not missing_ctx

    # Every requirement SENTENCE comes from method/stage4_prose_v1.json, never from a literal
    # in this file: a sentence that lives only in the emitter is bound by nothing.
    prose = method["prose"]
    req = prose["nebpi"]["branch_requirements"]

    # Every requirement SENTENCE comes from method/stage4_prose_v1.json, never a literal here:
    # a sentence that lives only in the emitter is bound by nothing.
    prose = method["prose"]
    req = prose["nebpi"]["branch_requirements"]

    # --- Part II, sufficiently permeable (OR) ----------------------------------
    proof: list[BranchProof] = []

    pk_therapeutic = pk_usable and pk_level == PkNebLevel.THERAPEUTIC.value
    proof.append(
        BranchProof(
            branch_id="pk_therapeutic_in_neb",
            class_id="sufficiently_permeable",
            required=req["pk_therapeutic_in_neb"],
            observed=pk_level,
            satisfied=pk_therapeutic,
            blocking_code=None
            if pk_therapeutic
            else _pk_block_code(pk_level, pk, missing_ctx, PkNebLevel.THERAPEUTIC.value),
            supporting_observation_ids=[pk_obs.observation_id] if pk_obs and pk_therapeutic else [],
        )
    )

    pd_present = ctx_ok and pd_state == ObservationState.OBSERVED_PRESENT.value
    proof.append(
        BranchProof(
            branch_id="pd_in_neb",
            class_id="sufficiently_permeable",
            required=req["pd_in_neb"],
            observed=pd_state,
            satisfied=pd_present,
            blocking_code=None if pd_present else _positive_block_code(pd_state, missing_ctx),
            supporting_observation_ids=[pd_obs.observation_id] if pd_obs and pd_present else [],
        )
    )

    rad_present = ctx_ok and rad_state == ObservationState.OBSERVED_PRESENT.value
    proof.append(
        BranchProof(
            branch_id="radiographic_response_in_neb",
            class_id="sufficiently_permeable",
            required=req["radiographic_response_in_neb"],
            observed=rad_state,
            satisfied=rad_present,
            blocking_code=None if rad_present else _positive_block_code(rad_state, missing_ctx),
            supporting_observation_ids=[rad_obs.observation_id] if rad_obs and rad_present else [],
        )
    )

    sufficient = pk_therapeutic or pd_present or rad_present

    # --- Part II, the two conjunctions ------------------------------------------
    pd_absent = pd_state == ObservationState.OBSERVED_ABSENT.value
    rad_absent = rad_state == ObservationState.OBSERVED_ABSENT.value

    for class_id, required_pk in (
        ("insufficiently_permeable", PkNebLevel.LOW.value),
        ("impermeable", PkNebLevel.LITTLE_TO_NONE.value),
    ):
        pk_ok = pk_usable and pk_level == required_pk
        proof.append(
            BranchProof(
                branch_id=f"{class_id}::{required_pk}",
                class_id=class_id,
                required=req[f"{class_id}::{required_pk}"],
                observed=pk_level,
                satisfied=pk_ok,
                blocking_code=None
                if pk_ok
                else _pk_block_code(pk_level, pk, missing_ctx, required_pk),
                supporting_observation_ids=[pk_obs.observation_id] if pk_obs and pk_ok else [],
            )
        )
        proof.append(
            BranchProof(
                branch_id=f"{class_id}::no_relevant_pd_in_neb",
                class_id=class_id,
                required=req[f"{class_id}::no_relevant_pd_in_neb"],
                observed=pd_state,
                satisfied=pd_absent,
                blocking_code=None if pd_absent else _absence_block_code(pd_state),
                supporting_observation_ids=[pd_obs.observation_id] if pd_obs and pd_absent else [],
            )
        )
        proof.append(
            BranchProof(
                branch_id=f"{class_id}::no_radiographic_response_in_neb",
                class_id=class_id,
                required=req[f"{class_id}::no_radiographic_response_in_neb"],
                observed=rad_state,
                satisfied=rad_absent,
                blocking_code=None if rad_absent else _absence_block_code(rad_state),
                supporting_observation_ids=[rad_obs.observation_id] if rad_obs and rad_absent else [],
            )
        )

    insufficient = pk_usable and pk_level == PkNebLevel.LOW.value and pd_absent and rad_absent
    impermeable = pk_usable and pk_level == PkNebLevel.LITTLE_TO_NONE.value and pd_absent and rad_absent

    # --- resolve ----------------------------------------------------------------
    if sufficient:
        nebpi_class: Optional[str] = "sufficiently_permeable"
        status = "classified"
    elif insufficient:
        nebpi_class, status = "insufficiently_permeable", "classified"
    elif impermeable:
        nebpi_class, status = "impermeable", "classified"
    else:
        nebpi_class, status = None, "not_classifiable"
        reason_codes.append("no_complete_part_ii_logic")

    if nebpi_class == "sufficiently_permeable" and not pk_has_potency and (pd_present or rad_present):
        caveats.append({"code": "class_rests_on_pd_or_radiographic_without_potency_context"})

    return NebpiResult(
        candidate_id=candidate_id,
        context_id=context.context_id,
        nebpi_status=status,
        nebpi_class=nebpi_class,
        nebpi_primary_gate=delivery.nebpi_primary_gate,
        delivery_requirement=delivery.requirement,
        criterion_states=dict(sorted(criterion_states.items())),
        criterion_observation_ids=dict(sorted(criterion_observation_ids.items())),
        branch_proof=proof,
        counterfactual=_counterfactual(status, nebpi_class, pk_level, pd_state, rad_state,
                                       pk_has_potency, missing_ctx, prose),
        reason_codes=sorted(set(reason_codes)),
        context_caveats=caveats,
        method_id=method["method_id"],
        method_version=method["method_version"],
        evidence_observation_ids=sorted(o.observation_id for o in obs),
        pk_derivation=pk.as_content(),
    )


def _pk_block_code(
    pk_level: str,
    pk: "PkDerivation",
    missing_ctx: list[str],
    required: str,
) -> str:
    """Why this PK branch did not fire — as a CODE, declared in the prose catalog."""
    if pk.blocked_code:
        return "pk_not_derivable"
    if pk_level == PkNebLevel.NOT_EVALUATED.value:
        return "pk_not_derivable"
    if missing_ctx:
        return "context_incomplete"
    return "pk_level_is_not_the_required_level"


def _positive_block_code(state: str, missing_ctx: list[str]) -> str:
    if state == "absent_claim_inadequate":
        return "absence_claim_inadequate"
    if state == CONFLICTING:
        return "conflicting_observations"
    if missing_ctx:
        return "context_incomplete"
    return "state_is_not_observed_present"


def _absence_block_code(state: str) -> str:
    """Why a 'no effect' conjunct did not fire. `not_evaluated` is NOT `observed_absent`."""
    if state == "absent_claim_inadequate":
        return "absence_claim_inadequate"
    if state == CONFLICTING:
        return "conflicting_observations"
    return "state_is_not_observed_absent"


def _counterfactual(
    status: str,
    nebpi_class: Optional[str],
    pk_level: str,
    pd_state: str,
    rad_state: str,
    pk_has_potency: bool,
    missing_ctx: list[str],
    prose: dict[str, Any],
) -> dict[str, Any]:
    """Exactly what would have to be observed to change the outcome.

    Every SENTENCE here comes from method/stage4_prose_v1.json; every explanation of WHY a
    negative class is blocked is a CODE plus its bound slots. The interpolated sentences this
    used to emit were bound by nothing — a resealed release could rewrite "'No relevant PD in
    NEB' is not established" into its opposite and every hash in the release would still agree.
    """
    texts = prose["nebpi"]["counterfactual"]
    cf: dict[str, Any] = {
        "current_status": status,
        "current_class": nebpi_class,
        "observed": {"pk_in_neb": pk_level, "pd_in_neb": pd_state,
                     "radiographic_response_in_neb": rad_state},
    }
    if status == "classified" and nebpi_class == "sufficiently_permeable":
        cf["would_lose_class_if"] = texts["would_lose_class_if"]
        return cf

    cf["to_reach_sufficiently_permeable_any_one_of"] = list(
        texts["to_reach_sufficiently_permeable_any_one_of"])

    blockers: list[dict[str, Any]] = []
    if missing_ctx:
        blockers.append({"code": "context_incomplete",
                         "missing_context_fields": list(missing_ctx)})
    if pk_level == PkNebLevel.NOT_EVALUATED.value:
        blockers.append({"code": "pk_not_measured_in_neb"})
    elif not pk_has_potency:
        blockers.append({"code": "pk_has_no_potency_context"})
    if pd_state != ObservationState.OBSERVED_ABSENT.value:
        blockers.append({"code": "pd_absence_not_established", "state": pd_state})
    if rad_state != ObservationState.OBSERVED_ABSENT.value:
        blockers.append({"code": "radiographic_absence_not_established", "state": rad_state})

    cf["negative_classes_blocked_because"] = blockers
    cf["to_reach_insufficiently_permeable_all_of"] = list(
        texts["to_reach_insufficiently_permeable_all_of"])
    cf["to_reach_impermeable_all_of"] = list(texts["to_reach_impermeable_all_of"])
    cf["hard_rule"] = texts["hard_rule"]
    return cf
