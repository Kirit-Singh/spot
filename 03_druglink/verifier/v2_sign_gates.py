"""THE SIGN GATES, re-asserted on the rows the producer actually EMITTED.

Split from :mod:`verifier.v2_sign` (which owns the RULE) at the 500-line gate — the same seam the
producer draws between what the evidence IS and what a row must LOOK like. Imports NOTHING from
``druglink``; re-exported through :mod:`verifier.v2_contract`, so a caller still binds ONE module.

A property checked only inside a reconstruction is a property that refuses every inversion under
ONE name. These run on the emitted bytes and say WHICH inversion was attempted.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

from . import policy
from .v2_sign import (
    EVIDENCE_RELATIONS,
    FIELD_MODALITY,
    FIELD_MODULATION,
    GATE_CLAIMS_EQUIVALENCE,
    GATE_EDGE_SIGN_DISAGREES_WITH_ITS_OWN_ARM_VALUE,
    GATE_MODALITY_NOT_DECLARED,
    GATE_MODULATION_DERIVED_FROM_MODALITY_ALONE,
    GATE_NO_EVIDENCE_RELATION,
    GATE_NON_PHENOCOPY_IN_SUPPORTED_EVIDENCE,
    GATE_SUPPORTED_ON_A_NON_SUPPORTING_SIGN,
    MATCH_STATUSES,
    MODALITY_PERFORMED_ACTION,
    PHENOCOPY_RELATIONS,
    SIGN_EPS,
    SIGN_STATES,
    SIGN_SUPPORTS_DESIRED_CHANGE,
    TARGET_MODULATIONS,
    W3_NAMESPACES,
    W3_REQUIRED_ROW_FIELDS,
    ACTION_PHENOCOPY_EFFECTS,
    EVIDENCE_IS_EQUIVALENCE,
    INVERSE_ACTION,
    MODULATION_FOR,
    PHARMACOLOGIC_REVERSIBILITY_ASSUMED,
    desired_target_modulation,
    observed_sign_state,
    phenocopies,
    phenocopying_actions,
)


def _float_or_none(text: Any) -> Optional[float]:
    if text in (None, ""):
        return None
    try:
        return float(str(text))
    except (TypeError, ValueError):
        return None


def edge_refusals(edge: Mapping[str, Any]) -> list[str]:
    """Every way an inversion could reach a consumer through ONE emitted edge.

    The sign is RE-DERIVED from the edge's own ``arm_value_source_string`` + ``arm_evaluable``
    and compared to what the edge SAYS its sign is: a producer that flipped the state while
    keeping the value it came from is caught here BY NAME, not merely by a hash.
    """
    out: list[str] = []
    eid = edge.get("edge_id")
    modality, sign = edge.get(FIELD_MODALITY), edge.get("observed_sign_state")
    if modality not in MODALITY_PERFORMED_ACTION or sign not in SIGN_STATES:
        return [f"[{GATE_MODALITY_NOT_DECLARED}] edge {eid!r} carries modality={modality!r} / "
                f"sign={sign!r}; both are required and neither is inferred from the other"]

    measured = bool(edge.get("origin_is_measured"))
    if measured:
        derived = observed_sign_state(_float_or_none(edge.get("arm_value_source_string")),
                                      evaluable=bool(edge.get("arm_evaluable")),
                                      origin_is_measured=True, arm_key=str(edge.get("arm_key")))
        if derived != sign:
            out.append(
                f"[{GATE_EDGE_SIGN_DISAGREES_WITH_ITS_OWN_ARM_VALUE}] edge {eid!r} declares "
                f"sign {sign!r}, but its own arm_value "
                f"{edge.get('arm_value_source_string')!r} (evaluable="
                f"{edge.get('arm_evaluable')!r}) re-derives {derived!r}")

    want = desired_target_modulation(str(modality), str(sign))
    if edge.get(FIELD_MODULATION) != want:
        out.append(
            f"[{GATE_MODULATION_DERIVED_FROM_MODALITY_ALONE}] edge {eid!r} declares "
            f"{FIELD_MODULATION}={edge.get(FIELD_MODULATION)!r}, but its own modality "
            f"{modality!r} and observed sign {sign!r} re-derive {want!r}. A modulation fixed by "
            "the MODALITY alone ignores the sign — and on an opposing row it matches inhibitors "
            "to a target the data says inhibition makes WORSE, then ranks it as support")

    phenocopy = phenocopies(edge.get("action_type_source"), str(modality))
    if bool(edge.get("mechanism_phenocopies_modality")) != phenocopy:
        out.append(
            f"[{GATE_NON_PHENOCOPY_IN_SUPPORTED_EVIDENCE}] edge {eid!r} claims "
            f"mechanism_phenocopies_modality={edge.get('mechanism_phenocopies_modality')!r} for "
            f"action {edge.get('action_type_source')!r} against {modality!r}; the restated "
            f"engine says {phenocopy!r}")

    supported = (bool(edge.get("observed_perturbation_support"))
                 or edge.get("directional_evidence_status") == policy.OBSERVED_PERTURBATION
                 or edge.get("stage3_evidence_class") == policy.CLASS_MEASURED)
    if supported and not phenocopy:
        out.append(
            f"[{GATE_NON_PHENOCOPY_IN_SUPPORTED_EVIDENCE}] edge {eid!r} reaches SUPPORTED "
            f"evidence with action_type={edge.get('action_type_source')!r}, which does NOT "
            f"phenocopy the declared {modality!r}. An agonist never phenocopies a knockdown: "
            "promoting it by sign inversion asserts an experiment nobody ran")
    if supported and sign != SIGN_SUPPORTS_DESIRED_CHANGE:
        out.append(
            f"[{GATE_SUPPORTED_ON_A_NON_SUPPORTING_SIGN}] edge {eid!r} claims observed support "
            f"while its sign is {sign!r}; any sign but a supporting one is a drug matched to a "
            "result that did not happen")
    if supported and edge.get("evidence_relation") not in PHENOCOPY_RELATIONS:
        out.append(
            f"[{GATE_NON_PHENOCOPY_IN_SUPPORTED_EVIDENCE}] edge {eid!r} reaches SUPPORTED "
            f"evidence carrying relation {edge.get('evidence_relation')!r}, which is not a "
            "phenocopy relation")
    if edge.get("evidence_relation") not in EVIDENCE_RELATIONS \
            or not str(edge.get("evidence_relation_caveat") or "").strip():
        out.append(
            f"[{GATE_NO_EVIDENCE_RELATION}] edge {eid!r} carries evidence_relation="
            f"{edge.get('evidence_relation')!r} with caveat "
            f"{str(edge.get('evidence_relation_caveat'))[:24]!r}. Stage 4 reads FIELDS, not "
            "docstrings: an edge that does not declare its relation is one a consumer may read "
            "as an equivalence")
    if edge.get("evidence_is_equivalence") is not False:
        out.append(
            f"[{GATE_CLAIMS_EQUIVALENCE}] edge {eid!r} declares evidence_is_equivalence="
            f"{edge.get('evidence_is_equivalence')!r}. A drug acting on the PROTEIN is never the "
            "genetic perturbation of the TRANSCRIPT that was measured")
    return out


def agonists_in_supported_evidence(payload: Any, path: str = "$") -> list[str]:
    """AT ANY DEPTH: nothing that fails to phenocopy its modality wears supported evidence.

    Walked over the WHOLE bundle — document, tables, nested blocks — because the way an agonist
    reaches a consumer is not through the edge builder that already has a gate; it is through a
    summary, a count map, or a candidate field a later writer added and nobody re-checked.
    """
    hits: list[str] = []
    if isinstance(payload, Mapping):
        if payload.get("mechanism_phenocopies_modality") is False:
            if payload.get("observed_perturbation_support") is True:
                hits.append(f"{path}.observed_perturbation_support=true on a non-phenocopying "
                            f"mechanism (action={payload.get('action_type_source')!r})")
            if payload.get("directional_evidence_status") == policy.OBSERVED_PERTURBATION:
                hits.append(f"{path} is an observed_perturbation whose mechanism does NOT "
                            f"phenocopy {payload.get(FIELD_MODALITY)!r}")
            if payload.get("stage3_evidence_class") == policy.CLASS_MEASURED:
                hits.append(f"{path} wears the MEASURED evidence class without phenocopying "
                            f"{payload.get(FIELD_MODALITY)!r}")
        for key, value in payload.items():
            hits += agonists_in_supported_evidence(value, f"{path}.{key}")
    elif isinstance(payload, (list, tuple)):
        for i, value in enumerate(payload):
            hits += agonists_in_supported_evidence(value, f"{path}[{i}]")
    return hits


def semantic_vocabulary() -> dict[str, Any]:
    """The SEMANTIC tables of the sign contract, restated. Compared field-for-field against the
    ``modality_vocabulary`` the bundle publishes — the prose is the producer's, but the TABLES
    that decide a direction must be identical or the two lanes have drifted apart."""
    return {
        "sign_eps": repr(SIGN_EPS),
        "sign_states": list(SIGN_STATES),
        "arm_value_is_pre_oriented_by_stage2": True,
        "w3_required_row_fields": list(W3_REQUIRED_ROW_FIELDS),
        "w3_namespaces": list(W3_NAMESPACES),
        "modality_performed_action": dict(sorted(MODALITY_PERFORMED_ACTION.items())),
        "inverse_action": dict(sorted(INVERSE_ACTION.items())),
        "action_phenocopy_effects": {k: list(v)
                                     for k, v in sorted(ACTION_PHENOCOPY_EFFECTS.items())},
        "phenocopying_actions_by_modality": {
            m: list(phenocopying_actions(m)) for m in sorted(MODALITY_PERFORMED_ACTION)},
        "target_modulations": list(TARGET_MODULATIONS),
        "modulation_for": {f"{m}|{s}": v for (m, s), v in sorted(MODULATION_FOR.items())},
        "match_statuses": list(MATCH_STATUSES),
        "evidence_relations": list(EVIDENCE_RELATIONS),
        "phenocopy_relations": sorted(PHENOCOPY_RELATIONS),
        "evidence_is_equivalence": EVIDENCE_IS_EQUIVALENCE,
        "pharmacologic_reversibility_assumed": PHARMACOLOGIC_REVERSIBILITY_ASSUMED,
    }
