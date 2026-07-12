"""Mechanism assertions and ARM-KEYED target-drug edges.

Every source statement survives as its own ``mechanism_assertion`` row, with the
source ``action_type`` retained VERBATIM. Assertions are never merged into a
"strongest" claim.

Edges are keyed by the ARM, not by the gene:

    (desired_arm, target_ensembl, form_id, target_entity_id, normalized action)

That is the whole point. A drug can be loss-of-function-like for ``away_from_A`` and
simultaneously ``opposed`` on ``toward_B`` — because a target can carry
``A_desired_target_modulation=decrease`` and ``B_desired_target_modulation=increase``.
BOTH edges are emitted. The old gene-keyed edge had nowhere to put that, and a
gene-keyed lever dict silently kept whichever row happened to be last.

Grouping is by FORM, never by moiety, so evidence on a prodrug is never silently
attributed to its active metabolite.

Conflicts are preserved, not resolved:

  * two sources disagreeing about DIRECTNESS -> ``directness_state=conflicting``;
    both assertions stay. The strongest claim does not win.
  * two sources asserting OPPOSITE intervention effects (an inhibitor and an agonist)
    on the same form+target -> both edges are flagged ``action_conflict`` and both
    translate to ``unknown``. A drug cannot be simultaneously supported and opposed
    on one target, and we do not choose for it.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from . import identity
from .armlever import ARMS
from .direction import (intervention_effect, normalize_action_type, translate,
                        ABUNDANCE_REDUCTION, FUNCTIONAL_ACTIVATION,
                        FUNCTIONAL_INHIBITION, ORIGIN_DIRECT_TARGET,
                        ORIGIN_PATHWAY_NODE)
from .hashing import short_id

DIRECT_GENE_LANE = "direct_gene_mechanism"
NON_GENE_LANE = "non_gene_target_entity"

# Effects that point in opposite directions. Two of these on one (form, target) is a
# source-level contradiction, not a tie to break.
_REDUCING = frozenset({ABUNDANCE_REDUCTION, FUNCTIONAL_INHIBITION})
_INCREASING = frozenset({FUNCTIONAL_ACTIVATION})


def _assertion_directness(entity: dict[str, Any], flag: Optional[int]) -> str:
    if not entity["direct_gene_lane_eligible"]:
        return "complex_or_family_target"
    if flag == 1:
        return "direct_single_protein"
    if flag == 0:
        return "indirect"
    return "unknown"


def build_assertions(*, records: Iterable[dict[str, Any]], graph: dict[str, Any],
                     targets: dict[str, Any]) -> dict[str, Any]:
    """One row per source mechanism statement. ``action_type_source`` is verbatim."""
    assertions: list[dict[str, Any]] = []
    dispositions: list[dict[str, Any]] = []

    for rec in records:
        if rec.get("record_kind") != "mechanism":
            continue
        form_id = identity.form_for_identifiers(graph, rec["molecule_identifiers"])
        if form_id is None:
            dispositions.append({
                "subject_kind": "drug_form",
                "subject_id": rec["source_molecule_id"],
                "state": "not_in_identity_graph",
                "reason": "mechanism_molecule_has_no_identity_record",
                "detail": f"{rec['source']} mechanism on {rec['source_molecule_id']}",
                "source_record_id": rec["source_record_id"]})
            continue
        eid = targets["by_source_id"].get((rec["source"], rec.get("source_target_id")))
        if eid is None:
            dispositions.append({
                "subject_kind": "target_entity",
                "subject_id": str(rec.get("source_target_id")),
                "state": "unknown_target_entity",
                "reason": "mechanism_target_not_in_any_acquired_target_record",
                "detail": f"{rec['source']} {rec.get('source_target_id')}",
                "source_record_id": rec["source_record_id"]})
            continue

        entity = targets["entities"][eid]
        action_source = rec.get("action_type_source")
        effect, effect_reason = intervention_effect(action_source)
        row = {
            "source": rec["source"],
            "source_record_id": rec["source_record_id"],
            "source_record_row_id": rec.get("source_row_id"),
            "source_molecule_id": rec["source_molecule_id"],
            "form_id": form_id,
            "target_entity_id": eid,
            # Verbatim, exactly as the source wrote it.
            "action_type_source": action_source,
            "action_type_normalized": normalize_action_type(action_source),
            "intervention_effect": effect,
            "intervention_effect_reason": effect_reason,
            "mechanism_of_action_text": rec.get("mechanism_of_action_text"),
            "direct_interaction_flag": rec.get("direct_interaction_flag"),
            "directness_class": _assertion_directness(
                entity, rec.get("direct_interaction_flag")),
            "mechanism_refs": list(rec.get("mechanism_refs") or []),
            "ref_urls": list(rec.get("ref_urls") or []),
        }
        row["assertion_id"] = short_id(row)
        assertions.append(row)

    assertions.sort(key=lambda a: a["assertion_id"])
    return {"assertions": assertions, "dispositions": dispositions}


def _action_conflicts(assertions: list[dict[str, Any]]) -> set[tuple[str, str]]:
    """(form, target entity) pairs carrying opposite sourced intervention effects."""
    effects: dict[tuple[str, str], set[str]] = {}
    for a in assertions:
        if a["intervention_effect"] in (_REDUCING | _INCREASING):
            effects.setdefault((a["form_id"], a["target_entity_id"]), set()).add(
                a["intervention_effect"])
    return {k for k, v in effects.items()
            if (v & _REDUCING) and (v & _INCREASING)}


def build_edges(*, assertions: list[dict[str, Any]],
                arm_lever_index: dict[tuple[str, str, str], dict[str, Any]],
                graph: dict[str, Any], targets: dict[str, Any],
                modality: str) -> dict[str, Any]:
    """One edge per (ARM, ORIGIN, gene, form, target entity, action).

    ``arm_lever_index`` is keyed by ``(target_ensembl, desired_arm, origin_type)`` —
    never by gene alone, and never by gene+arm alone. A gene present in both arms
    produces up to two independent edges; a gene that is BOTH a measured direct target
    AND an inferred pathway node produces SEPARATE edges for each origin, because a
    measurement and an inference are not the same evidence and may never be merged.
    Each edge reads ONLY its own arm's value, rank, tier, support and desired
    modulation.
    """
    entity_genes = targets["entity_genes"]
    conflicted = _action_conflicts(assertions)

    origins = (ORIGIN_DIRECT_TARGET, ORIGIN_PATHWAY_NODE)
    grouped: dict[tuple, dict[str, Any]] = {}
    for a in assertions:
        eid = a["target_entity_id"]
        for gene in entity_genes.get(eid, []):
            for arm in ARMS:
                for origin in origins:
                    lever = arm_lever_index.get((gene, arm, origin))
                    if lever is None:
                        continue      # not a lever we hold: nothing to translate
                    key = (arm, origin, gene, a["form_id"], eid,
                           a["action_type_normalized"])
                    g = grouped.setdefault(key, {
                        "desired_arm": arm,
                        "origin_type": origin,
                        "target_ensembl": gene,
                        "form_id": a["form_id"],
                        "target_entity_id": eid,
                        "action_type_normalized": a["action_type_normalized"],
                        "action_type_sources": set(),
                        "intervention_effects": set(),
                        "intervention_effect_reasons": set(),
                        "directness_classes": set(),
                        "assertion_ids": set(),
                        "source_record_ids": set(),
                    })
                    if a["action_type_source"] is not None:
                        g["action_type_sources"].add(a["action_type_source"])
                    g["intervention_effects"].add(a["intervention_effect"])
                    g["intervention_effect_reasons"].add(
                        a["intervention_effect_reason"])
                    g["directness_classes"].add(a["directness_class"])
                    g["assertion_ids"].add(a["assertion_id"])
                    g["source_record_ids"].add(a["source_record_id"])

    forms = graph["form_index"]
    edges: list[dict[str, Any]] = []
    dispositions: list[dict[str, Any]] = []

    for key in sorted(grouped):
        g = grouped[key]
        arm, gene, origin = g["desired_arm"], g["target_ensembl"], g["origin_type"]
        lever = arm_lever_index[(gene, arm, origin)]
        entity = targets["entities"][g["target_entity_id"]]
        form = forms[g["form_id"]]

        classes = sorted(g["directness_classes"])
        directness_state = classes[0] if len(classes) == 1 else "conflicting"

        effects = sorted(g["intervention_effects"])
        effect = effects[0] if len(effects) == 1 else "unknown"
        action_conflict = (g["form_id"], g["target_entity_id"]) in conflicted

        is_single_protein = bool(entity["direct_gene_lane_eligible"])
        cls = translate(
            desired_modulation=lever["arm_desired_target_modulation"],
            effect=effect,
            arm_evaluable=bool(lever["arm_evaluable"]),
            target_entity_is_single_protein=is_single_protein,
            action_conflict=action_conflict,
            origin_type=origin)

        # UniProt component of this single-protein entity, for provenance only.
        uniprot = next((c["uniprot_id"] for c in targets["components"]
                        if c["target_entity_id"] == g["target_entity_id"]
                        and c["target_ensembl"] == gene), None)

        edge = {
            # ---- the arm this edge belongs to; it reads no other arm's field ----
            "desired_arm": arm,
            "origin_type": origin,
            "source_lever_key": lever.get("arm_lever_key")
                                or lever.get("pathway_node_key"),
            "target_ensembl": gene,
            "target_symbol": lever.get("target_symbol"),
            "arm_rank": lever["arm_rank"],
            "arm_value_source_string": lever["arm_value_source_string"],
            "arm_value_canonical_decimal": lever["arm_value_canonical_decimal"],
            "arm_evaluable": bool(lever["arm_evaluable"]),
            "arm_state": lever["arm_state"],
            "arm_evidence_tier": lever["arm_evidence_tier"],
            "arm_support_state": lever["arm_support_state"],
            "arm_desired_target_modulation": lever["arm_desired_target_modulation"],
            "arm_direction_measured": bool(lever.get("arm_direction_measured")),
            # ---- what the drug is and does ----
            "target_entity_id": g["target_entity_id"],
            "target_entity_class": entity["target_entity_class"],
            "uniprot_id": uniprot,
            "form_id": g["form_id"],
            "active_moiety_id": form["active_moiety_id"],
            "action_type_sources": sorted(g["action_type_sources"]),
            "action_type_normalized": g["action_type_normalized"],
            "intervention_effect": effect,
            "intervention_effect_reason": "; ".join(
                sorted(g["intervention_effect_reasons"])),
            "directness_state": directness_state,
            "directness_classes": classes,
            "action_conflict": action_conflict,
            "n_assertions": len(g["assertion_ids"]),
            "assertion_ids": sorted(g["assertion_ids"]),
            "lane": DIRECT_GENE_LANE if is_single_protein else NON_GENE_LANE,
            # ---- what the SCREEN did (kept separate from what the DRUG does) ----
            "perturbation_modality": modality,
            "observed_target_abundance_direction": "decrease",
            "source_record_ids": sorted(g["source_record_ids"]),
            **cls,
        }
        edge["edge_id"] = short_id(edge_content(edge))
        edges.append(edge)

        if edge["lane"] == NON_GENE_LANE:
            dispositions.append({
                "subject_kind": "target_entity",
                "subject_id": g["target_entity_id"],
                "state": NON_GENE_LANE,
                "reason": "mechanism_on_complex_or_family_cannot_translate_to_a_gene",
                "detail": f"{entity['source_target_id']} ({entity['target_type']}) "
                          f"contains {gene}",
                "source_record_id": edge["source_record_ids"][0]})

    edges.sort(key=lambda e: e["edge_id"])
    return {"edges": edges, "dispositions": dispositions}


def edge_content(e: dict[str, Any]) -> dict[str, Any]:
    """The scientific content of an edge (no display labels)."""
    return {
        "desired_arm": e["desired_arm"],
        "origin_type": e["origin_type"],
        "source_lever_key": e["source_lever_key"],
        "target_ensembl": e["target_ensembl"],
        "target_entity_id": e["target_entity_id"],
        "form_id": e["form_id"],
        "active_moiety_id": e["active_moiety_id"],
        "action_type_normalized": e["action_type_normalized"],
        "action_type_sources": sorted(e["action_type_sources"]),
        "intervention_effect": e["intervention_effect"],
        "directness_state": e["directness_state"],
        "directness_classes": sorted(e["directness_classes"]),
        "lane": e["lane"],
        "perturbation_modality": e["perturbation_modality"],
        "arm_desired_target_modulation": e["arm_desired_target_modulation"],
        "arm_rank": e["arm_rank"],
        "arm_value_canonical_decimal": e["arm_value_canonical_decimal"],
        "arm_evidence_tier": e["arm_evidence_tier"],
        "directional_evidence_status": e["directional_evidence_status"],
        "directional_evidence_reason": e["directional_evidence_reason"],
        "observed_perturbation_support": e["observed_perturbation_support"],
        "stage3_evidence_class": e["stage3_evidence_class"],
        "action_conflict": e["action_conflict"],
        "assertion_ids": sorted(e["assertion_ids"]),
        "source_record_ids": sorted(e["source_record_ids"]),
    }
