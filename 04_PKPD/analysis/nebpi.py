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
    required: str
    observed: str
    satisfied: bool
    blocking_reason: Optional[str]
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
    context_caveats: list[str]
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
    caveats: list[str] = []

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
        caveats.append(
            "NEBPI is context-dependent (route/formulation/dose/schedule/tumour). Missing: "
            + ", ".join(missing_ctx)
        )

    if pk.blocked_code:
        reason_codes.append(f"pk_not_derivable:{pk.blocked_code}")
    for reduction, name in ((pd, "pd_in_neb"), (rad, "radiographic_response_in_neb")):
        if reduction.state == CONFLICTING:
            reason_codes.append(f"conflicting_observations:{name}")
            caveats.append(
                f"{reduction.n_distinct_rows} distinct observations of {name!r} in this context "
                f"({', '.join(reduction.conflicting_observation_ids)}). Stage 4 has no sourced "
                "rule for aggregating two observations of one criterion, so the criterion is "
                "conflicting and satisfies no Part-II branch."
            )

    potency_ids = {p.potency_id for p in potencies if p.candidate_id == candidate_id}
    if not potency_ids:
        caveats.append(
            "No MEC/potency record for this candidate. Part I grades 'Known MEC (potency)' as "
            "importance A, and the Part-II PK branches are defined relative to it."
        )

    # A PK level exists only if it was actually derived from a bound comparison. For a
    # censored measurement that means a source-declared LOD/LLOQ strictly below the MEC.
    pk_derived = pk_level in DERIVED_LEVELS
    pk_has_potency = bool(pk.potency_id)
    pk_usable = pk_derived and not missing_ctx
    ctx_ok = not missing_ctx

    # --- Part II, sufficiently permeable (OR) ----------------------------------
    proof: list[BranchProof] = []

    pk_therapeutic = pk_usable and pk_level == PkNebLevel.THERAPEUTIC.value
    proof.append(
        BranchProof(
            branch_id="pk_therapeutic_in_neb",
            class_id="sufficiently_permeable",
            required="PK with therapeutic levels in NEB (accounting for potency)",
            observed=pk_level,
            satisfied=pk_therapeutic,
            blocking_reason=None
            if pk_therapeutic
            else _pk_block_reason(pk_level, pk, missing_ctx, PkNebLevel.THERAPEUTIC.value),
            supporting_observation_ids=[pk_obs.observation_id] if pk_obs and pk_therapeutic else [],
        )
    )

    pd_present = ctx_ok and pd_state == ObservationState.OBSERVED_PRESENT.value
    proof.append(
        BranchProof(
            branch_id="pd_in_neb",
            class_id="sufficiently_permeable",
            required="Relevant PD effect in NEB",
            observed=pd_state,
            satisfied=pd_present,
            blocking_reason=None if pd_present else _positive_block_reason(pd_state, missing_ctx),
            supporting_observation_ids=[pd_obs.observation_id] if pd_obs and pd_present else [],
        )
    )

    rad_present = ctx_ok and rad_state == ObservationState.OBSERVED_PRESENT.value
    proof.append(
        BranchProof(
            branch_id="radiographic_response_in_neb",
            class_id="sufficiently_permeable",
            required="Radiographic response in NEB",
            observed=rad_state,
            satisfied=rad_present,
            blocking_reason=None if rad_present else _positive_block_reason(rad_state, missing_ctx),
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
                required=(
                    "Low PK levels in NEB (accounting for potency)"
                    if required_pk == PkNebLevel.LOW.value
                    else "Little to no drug in NEB (accounting for potency)"
                ),
                observed=pk_level,
                satisfied=pk_ok,
                blocking_reason=None
                if pk_ok
                else _pk_block_reason(pk_level, pk, missing_ctx, required_pk),
                supporting_observation_ids=[pk_obs.observation_id] if pk_obs and pk_ok else [],
            )
        )
        proof.append(
            BranchProof(
                branch_id=f"{class_id}::no_relevant_pd_in_neb",
                class_id=class_id,
                required="No relevant PD in NEB (observed absent by an adequate assessment)",
                observed=pd_state,
                satisfied=pd_absent,
                blocking_reason=None if pd_absent else _absence_block_reason(pd_state, "PD in NEB"),
                supporting_observation_ids=[pd_obs.observation_id] if pd_obs and pd_absent else [],
            )
        )
        proof.append(
            BranchProof(
                branch_id=f"{class_id}::no_radiographic_response_in_neb",
                class_id=class_id,
                required="No radiographic response in NEB (observed absent by an adequate assessment)",
                observed=rad_state,
                satisfied=rad_absent,
                blocking_reason=None
                if rad_absent
                else _absence_block_reason(rad_state, "radiographic response in NEB"),
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
        caveats.append(
            "Class rests on an observed PD/radiographic response in NEB rather than on a PK-vs-MEC "
            "comparison. Per the source, that is a qualifying Part-II branch in its own right "
            "(temozolomide is classified this way), but no potency context was supplied."
        )

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
        counterfactual=_counterfactual(status, nebpi_class, pk_level, pd_state, rad_state, pk_has_potency, missing_ctx),
        reason_codes=sorted(set(reason_codes)),
        context_caveats=caveats,
        method_id=method["method_id"],
        method_version=method["method_version"],
        evidence_observation_ids=sorted(o.observation_id for o in obs),
        pk_derivation=pk.as_content(),
    )


def _pk_block_reason(
    pk_level: str,
    pk: "PkDerivation",
    missing_ctx: list[str],
    required: str,
) -> str:
    if pk.blocked_reason:
        return pk.blocked_reason
    if pk_level == PkNebLevel.NOT_EVALUATED.value:
        return "No PK measurement in non-enhancing brain. Absent evidence satisfies no branch."
    if missing_ctx:
        return "Evidence context is incomplete (" + ", ".join(missing_ctx) + ")."
    return f"Derived PK level is {pk_level!r}, not {required!r}."


def _positive_block_reason(state: str, missing_ctx: list[str]) -> str:
    if state == ObservationState.NOT_EVALUATED.value:
        return "Not evaluated in non-enhancing brain."
    if state == ObservationState.OBSERVED_ABSENT.value:
        return "An adequate assessment looked in NEB and found none."
    if state == "absent_claim_inadequate":
        return "An absence was claimed but the assessment was not adequate."
    if state == "conflicting":
        return "Conflicting observations for this context."
    if missing_ctx:
        return "Evidence context is incomplete (" + ", ".join(missing_ctx) + ")."
    return f"State is {state!r}."


def _absence_block_reason(state: str, what: str) -> str:
    if state == ObservationState.NOT_EVALUATED.value:
        return (
            f"{what} was never evaluated. 'Not evaluated' is not 'observed absent' — absent "
            "evidence can never satisfy a 'no effect' conjunct, and therefore can never make a "
            "drug insufficiently permeable or impermeable."
        )
    if state == "absent_claim_inadequate":
        return (
            f"An absence of {what} was claimed, but assessment_adequate was not asserted. An "
            "inadequate look is not evidence of absence."
        )
    if state == ObservationState.OBSERVED_PRESENT.value:
        return f"{what} was observed — this is a qualifying positive, not an absence."
    if state == "conflicting":
        return "Conflicting observations for this context."
    return f"State is {state!r}."


def _counterfactual(
    status: str,
    nebpi_class: Optional[str],
    pk_level: str,
    pd_state: str,
    rad_state: str,
    pk_has_potency: bool,
    missing_ctx: list[str],
) -> dict[str, Any]:
    """Exactly what would have to be observed to change the outcome."""
    cf: dict[str, Any] = {
        "current_status": status,
        "current_class": nebpi_class,
        "observed": {"pk_in_neb": pk_level, "pd_in_neb": pd_state, "radiographic_response_in_neb": rad_state},
    }
    if status == "classified" and nebpi_class == "sufficiently_permeable":
        cf["would_lose_class_if"] = (
            "the qualifying positive branch (therapeutic PK in NEB, relevant PD in NEB, or "
            "radiographic response in NEB) were retracted"
        )
        return cf

    to_sufficient = [
        "observe therapeutic PK in NEB with a bound MEC/potency context",
        "observe a relevant PD effect in NEB",
        "observe a radiographic response in NEB",
    ]
    cf["to_reach_sufficiently_permeable_any_one_of"] = to_sufficient

    blockers: list[str] = []
    if missing_ctx:
        blockers.append("evidence context incomplete: " + ", ".join(missing_ctx))
    if pk_level == PkNebLevel.NOT_EVALUATED.value:
        blockers.append("no PK measured in NEB")
    elif not pk_has_potency:
        blockers.append("PK in NEB has no MEC/potency context bound (Table 2 footnote a)")
    if pd_state != ObservationState.OBSERVED_ABSENT.value:
        blockers.append(f"'No relevant PD in NEB' is not established (state={pd_state})")
    if rad_state != ObservationState.OBSERVED_ABSENT.value:
        blockers.append(f"'No radiographic response in NEB' is not established (state={rad_state})")

    cf["negative_classes_blocked_because"] = blockers
    cf["to_reach_insufficiently_permeable_all_of"] = [
        "observe LOW PK in NEB (below MEC, with potency context)",
        "adequately assess PD in NEB and observe none",
        "adequately assess radiographic response in NEB and observe none",
    ]
    cf["to_reach_impermeable_all_of"] = [
        "observe LITTLE-TO-NO drug in NEB (with potency context)",
        "adequately assess PD in NEB and observe none",
        "adequately assess radiographic response in NEB and observe none",
    ]
    cf["hard_rule"] = "Absent or unknown evidence is never 'impermeable'."
    return cf
