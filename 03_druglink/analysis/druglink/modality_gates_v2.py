"""THE SIGN GATES, re-asserted on the rows the producer actually EMITTED.

Split from :mod:`druglink.modality_v2` at the 500-line gate — the same seam the lane already
draws between what the evidence IS (the rule) and what a row must LOOK like (the refusals).
Re-exported from ``modality_v2``, so a consumer still binds ONE module.

A property checked only inside the builder is a property the next writer can drop. These run on
the emitted bytes.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from . import workflow as wf
from .modality_rule import (
    EVIDENCE_RELATIONS,
    GATE_CLAIMS_EQUIVALENCE,
    GATE_MODALITY_NOT_DECLARED,
    GATE_MODULATION_DERIVED_FROM_MODALITY_ALONE,
    GATE_NO_EVIDENCE_RELATION,
    GATE_NON_PHENOCOPY_IN_SUPPORTED_EVIDENCE,
    GATE_SUPPORTED_ON_A_NON_SUPPORTING_SIGN,
    MODALITY_PERFORMED_ACTION,
    PHENOCOPY_RELATIONS,
    SIGN_STATES,
    SIGN_SUPPORTS_DESIRED_CHANGE,
    ModalityError,
    desired_target_modulation,
)


# --------------------------------------------------------------------------- #
# 4. The gates, re-asserted ON THE EMITTED ROWS. A property nobody re-checks on the bytes is a
#    property the next writer can drop.
# --------------------------------------------------------------------------- #
def check_edge_relation(edge: Mapping[str, Any]) -> None:
    """Every edge DECLARES its relation to the perturbation, and never claims equivalence."""
    relation = edge.get("evidence_relation")
    if relation not in EVIDENCE_RELATIONS:
        raise ModalityError(
            GATE_NO_EVIDENCE_RELATION,
            f"edge {edge.get('edge_id')!r} carries evidence_relation={relation!r}. Stage 4 reads "
            f"FIELDS, not docstrings: known relations are {list(EVIDENCE_RELATIONS)}, and an "
            "edge that does not declare its relation is one a consumer may read as an "
            "equivalence")
    if edge.get("evidence_is_equivalence") is not False:
        raise ModalityError(
            GATE_CLAIMS_EQUIVALENCE,
            f"edge {edge.get('edge_id')!r} declares evidence_is_equivalence="
            f"{edge.get('evidence_is_equivalence')!r}. A drug acting on the PROTEIN is not the "
            "genetic perturbation of the TRANSCRIPT that was measured. This lane may SUGGEST; "
            "it may never CONFIRM")
    if not str(edge.get("evidence_relation_caveat") or "").strip():
        raise ModalityError(
            GATE_NO_EVIDENCE_RELATION,
            f"edge {edge.get('edge_id')!r} carries no caveat; the label without the caveat is a "
            "token a reader can ignore")


def check_sign_rule(edge: Mapping[str, Any]) -> None:
    """THE DEFECT, REFUSED ON THE BYTES. Three ways an inversion could reach a consumer.

    1. The modulation was derived from the MODALITY ALONE — the exact old rule. It shows up as a
       modulation that does not re-derive from this row's own (modality, sign).
    2. A mechanism that does NOT phenocopy the modality reached SUPPORTED evidence — an agonist
       promoted by sign inversion, which is the one thing this lane must never emit.
    3. An edge claims observed support on a row whose sign does not support the desired change.
    """
    modality = edge.get("observed_perturbation_modality")
    sign = edge.get("observed_sign_state")
    if modality not in MODALITY_PERFORMED_ACTION or sign not in SIGN_STATES:
        raise ModalityError(
            GATE_MODALITY_NOT_DECLARED,
            f"edge {edge.get('edge_id')!r} carries modality={modality!r} / sign={sign!r}. Both "
            "are required, and neither is ever inferred from the other")

    want = desired_target_modulation(str(modality), str(sign))
    if edge.get("desired_target_modulation") != want:
        raise ModalityError(
            GATE_MODULATION_DERIVED_FROM_MODALITY_ALONE,
            f"edge {edge.get('edge_id')!r} declares desired_target_modulation="
            f"{edge.get('desired_target_modulation')!r}, but its own modality {modality!r} and "
            f"observed sign {sign!r} re-derive {want!r}. A modulation fixed by the MODALITY "
            "alone ignores the sign — and on an opposing row it matches inhibitors to a target "
            "the data says inhibition makes WORSE, then ranks it as supported evidence")

    supported = (bool(edge.get("observed_perturbation_support"))
                 or edge.get("directional_evidence_status") == wf.OBSERVED_PERTURBATION
                 or edge.get("stage3_evidence_class") == wf.CLASS_MEASURED)
    if supported and not edge.get("mechanism_phenocopies_modality"):
        raise ModalityError(
            GATE_NON_PHENOCOPY_IN_SUPPORTED_EVIDENCE,
            f"edge {edge.get('edge_id')!r} reaches SUPPORTED evidence with "
            f"action_type={edge.get('action_type_source')!r}, which does NOT phenocopy the "
            f"declared {modality!r}. An agonist never phenocopies a knockdown: on an opposing "
            "row it is the UNTESTED INVERSE of a deleterious result, and promoting it from sign "
            "inversion alone asserts an experiment nobody ran")
    if supported and sign != SIGN_SUPPORTS_DESIRED_CHANGE:
        raise ModalityError(
            GATE_SUPPORTED_ON_A_NON_SUPPORTING_SIGN,
            f"edge {edge.get('edge_id')!r} claims observed support while its sign is {sign!r}. "
            "Support means the perturbation moved the program the way THIS arm wants; any other "
            "sign is a drug matched to a result that did not happen")
    if supported and edge.get("evidence_relation") not in PHENOCOPY_RELATIONS:
        raise ModalityError(
            GATE_NON_PHENOCOPY_IN_SUPPORTED_EVIDENCE,
            f"edge {edge.get('edge_id')!r} reaches SUPPORTED evidence carrying relation "
            f"{edge.get('evidence_relation')!r}, which is not a phenocopy relation")


def check_edges(edges: Iterable[Mapping[str, Any]]) -> None:
    """Both gates, over every emitted edge."""
    for edge in edges:
        check_edge_relation(edge)
        check_sign_rule(edge)


def check_no_agonist_supported(payload: Any) -> None:
    """AT ANY DEPTH: nothing that fails to phenocopy its modality wears supported evidence.

    Walked over the WHOLE bundle — document, tables, nested blocks — because the way an agonist
    reaches a consumer is not through the edge builder that has a gate; it is through a summary,
    a count map, or a candidate field that a later writer added and nobody re-checked.
    """
    def walk(node: Any, path: str = "$") -> None:
        if isinstance(node, Mapping):
            if node.get("mechanism_phenocopies_modality") is False:
                for field in ("observed_perturbation_support",):
                    if node.get(field) is True:
                        raise ModalityError(
                            GATE_NON_PHENOCOPY_IN_SUPPORTED_EVIDENCE,
                            f"{path}.{field} is true on a row whose mechanism does NOT "
                            f"phenocopy its declared modality (action="
                            f"{node.get('action_type_source')!r}). An agonist is never promoted "
                            "to supported evidence by sign inversion")
                if node.get("directional_evidence_status") == wf.OBSERVED_PERTURBATION:
                    raise ModalityError(
                        GATE_NON_PHENOCOPY_IN_SUPPORTED_EVIDENCE,
                        f"{path} is an observed_perturbation whose mechanism does NOT phenocopy "
                        f"its declared modality (action={node.get('action_type_source')!r})")
            for key, value in node.items():
                walk(value, f"{path}.{key}")
        elif isinstance(node, (list, tuple)):
            for i, value in enumerate(node):
                walk(value, f"{path}[{i}]")

    walk(payload)


