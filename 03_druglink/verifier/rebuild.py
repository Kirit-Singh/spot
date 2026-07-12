"""Independent reconstruction of the identity / mechanism / candidate tables.

Rebuilt from the RE-PARSED raw source bytes plus the arm-levers re-expanded from
Direct's ``screen.parquet`` — never from the bundle's own tables. The bundle is then
compared against this. If the two disagree, verification fails.

The identity, edge and candidate rules are RESTATED here from the specification, the
same way ``verifier/policy.py`` restates the direction rules. This is deliberately a
second implementation: a verifier that imported ``druglink.identity`` could not detect
a bug in ``druglink.identity``.
"""
from __future__ import annotations

from typing import Any, Optional

from . import policy

# Form/moiety identifier priority, restated.
FORM_ID_PRIORITY = (("chembl_id", "CHEMBL"), ("pubchem_cid", "CID"),
                    ("rxcui", "RXCUI"), ("inchikey", "INCHIKEY"), ("unii", "UNII"))
MOIETY_ID_PRIORITY = (("inchikey", "INCHIKEY"), ("chembl_id", "CHEMBL"),
                      ("pubchem_cid", "CID"), ("rxcui", "RXCUI"), ("unii", "UNII"))

REDIRECT_RELATIONS = ("is_salt_of", "is_precise_ingredient_of", "is_prodrug_of")
TERMINAL_RELATIONS = ("is_parent_of_self", "is_active_metabolite_of")


def _pick(ids: dict[str, Any], priority) -> Optional[str]:
    for field, prefix in priority:
        value = ids.get(field)
        if value not in (None, ""):
            return f"{prefix}:{value}"
    return None


def build_forms(molecules: list[dict[str, Any]]) -> dict[str, Any]:
    """Forms, their sourced relations, and the active moiety each resolves to.

    A salt never inherits its parent's identity by assumption: the moiety comes only
    from an explicit, SOURCED relation edge.
    """
    by_chembl: dict[str, dict[str, Any]] = {}
    for mol in molecules:
        ids = {"chembl_id": mol["chembl_id"], "inchikey": mol.get("inchikey"),
               "pubchem_cid": mol.get("pubchem_cid"), "unii": mol.get("unii")}
        form_id = _pick(ids, FORM_ID_PRIORITY)
        by_chembl[mol["chembl_id"]] = {
            "form_id": form_id,
            "identifiers": ids,
            "form_class": mol["form_class"],
            "relation": mol["relation"],
            "relation_target": mol["relation_target"],
            "preferred_name": mol.get("preferred_name"),
            "development_state": mol.get("development_state"),
        }

    def resolve(chembl_id: str, seen: tuple = ()) -> tuple[Optional[str], str]:
        """(terminal chembl_id, status). A cycle or a dead end resolves to nothing."""
        if chembl_id in seen:
            return None, "ambiguous"
        form = by_chembl.get(chembl_id)
        if form is None:
            return None, "unresolved"
        if form["relation"] in REDIRECT_RELATIONS:
            target = form["relation_target"]
            if target == chembl_id:
                return chembl_id, "resolved"
            return resolve(target, seen + (chembl_id,))
        if form["relation"] in TERMINAL_RELATIONS:
            return chembl_id, "resolved"
        return None, "unresolved"

    forms: dict[str, dict[str, Any]] = {}
    for chembl_id, form in by_chembl.items():
        terminal, status = resolve(chembl_id)
        if status == "resolved" and terminal:
            moiety = _pick(by_chembl[terminal]["identifiers"], MOIETY_ID_PRIORITY)
            moiety_id = f"AM:{moiety}" if moiety else None
        else:
            moiety_id = None
        forms[form["form_id"]] = {
            **form,
            "chembl_id": chembl_id,
            "active_moiety_id": moiety_id,
            "identity_status": status if moiety_id else "unresolved",
        }
    return {"forms": forms,
            "form_by_chembl": {c: f["form_id"] for c, f in by_chembl.items()}}


def build_entities(targets: list[dict[str, Any]],
                   gene_maps: list[dict[str, Any]]) -> dict[str, Any]:
    """Target entities and their component genes.

    A PROTEIN COMPLEX / FAMILY is a first-class NON-gene entity. It is never
    translated into one of its component genes, in either arm.
    """
    uniprot_to_gene: dict[str, set[str]] = {}
    for rec in gene_maps:
        uniprot_to_gene.setdefault(rec["uniprot_id"], set()).add(rec["target_ensembl"])

    entities: dict[str, dict[str, Any]] = {}
    for tgt in targets:
        genes: set[str] = set()
        for acc in tgt["accessions"]:
            genes |= uniprot_to_gene.get(acc, set())
        entities[tgt["source_target_id"]] = {
            "source_target_id": tgt["source_target_id"],
            "target_type": tgt["target_type"],
            "is_single_protein": tgt["is_single_protein"],
            "accessions": tgt["accessions"],
            "genes": sorted(genes),
        }
    return entities


def build_edges(*, mechanisms: list[dict[str, Any]], forms: dict[str, Any],
                entities: dict[str, Any],
                arm_levers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One edge per (arm, gene, form, target entity, normalised action).

    Keyed by the ARM. A gene present in both arms yields up to two independent edges,
    and each reads only its OWN arm's desired modulation.
    """
    form_by_chembl = forms["form_by_chembl"]
    form_index = forms["forms"]

    levers = {(r["target_ensembl"], r["desired_arm"],
               r.get("origin_type", policy.ORIGIN_DIRECT_TARGET)): r
              for r in arm_levers if r.get("gene_target_drug_edge_permitted")}

    # Opposite sourced actions on one (form, entity) contradict each other.
    effects: dict[tuple[str, str], set[str]] = {}
    for mech in mechanisms:
        form_id = form_by_chembl.get(mech["source_molecule_id"])
        entity = entities.get(mech["source_target_id"] or "")
        if not form_id or entity is None:
            continue
        effect = policy.intervention_effect(mech["action_type_source"])
        if effect != policy.EFFECT_UNKNOWN:
            effects.setdefault((form_id, entity["source_target_id"]), set()).add(effect)
    reducing = {policy.ABUNDANCE_REDUCTION, policy.FUNCTIONAL_INHIBITION}
    conflicted = {k for k, v in effects.items()
                  if (v & reducing) and (policy.FUNCTIONAL_ACTIVATION in v)}

    grouped: dict[tuple, dict[str, Any]] = {}
    for mech in mechanisms:
        form_id = form_by_chembl.get(mech["source_molecule_id"])
        entity = entities.get(mech["source_target_id"] or "")
        if not form_id or entity is None:
            continue
        for gene in entity["genes"]:
            for arm in policy.ARMS:
                for origin in policy.ORIGINS:
                    lever = levers.get((gene, arm, origin))
                    if lever is None:
                        continue
                    action = policy.normalize_action(mech["action_type_source"])
                    key = (arm, origin, gene, entity["source_target_id"], form_id,
                           action)
                    grouped.setdefault(key, {"effects": set(), "n": 0})
                    grouped[key]["effects"].add(
                        policy.intervention_effect(mech["action_type_source"]))
                    grouped[key]["n"] += 1

    out: list[dict[str, Any]] = []
    for (arm, origin, gene, entity_id, form_id, action), group in sorted(
            grouped.items()):
        lever = levers[(gene, arm, origin)]
        entity = entities[entity_id]
        effects_here = sorted(group["effects"])
        effect = (effects_here[0] if len(effects_here) == 1
                  else policy.EFFECT_UNKNOWN)
        conflict = (form_id, entity_id) in conflicted

        status, reason = policy.directional_evidence(
            modulation=lever["arm_desired_target_modulation"],
            effect=effect,
            arm_evaluable=bool(lever["arm_evaluable"]),
            single_protein=entity["is_single_protein"],
            action_conflict=conflict,
            origin=origin)

        out.append({
            "desired_arm": arm,
            "origin_type": origin,
            "target_ensembl": gene,
            "form_id": form_id,
            "target_entity_id_source": entity_id,
            "action_type_normalized": action,
            "intervention_effect": effect,
            "action_conflict": conflict,
            "directional_evidence_status": status,
            "directional_evidence_reason": reason,
            "observed_perturbation_support":
                policy.observed_perturbation_support(status, origin),
            "stage3_evidence_class": policy.evidence_class(status),
            "active_moiety_id": form_index[form_id]["active_moiety_id"],
            "lane": (policy.DIRECT_GENE_LANE if entity["is_single_protein"]
                     else "non_gene_target_entity"),
        })
    return out


def build_candidates(edges: list[dict[str, Any]],
                     forms: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Per-(candidate, arm) state and PK eligibility, re-derived from the edges."""
    form_index = forms["forms"]
    status_by_moiety: dict[str, str] = {}
    for form in form_index.values():
        if form["active_moiety_id"]:
            status_by_moiety.setdefault(form["active_moiety_id"],
                                        form["identity_status"])

    per_arm: dict[str, dict[tuple[str, str], set[str]]] = {}
    all_classes: dict[str, set[str]] = {}
    for edge in edges:
        moiety = edge["active_moiety_id"]
        if not moiety or edge["lane"] != policy.DIRECT_GENE_LANE:
            continue
        key = (edge["desired_arm"], edge["origin_type"])
        per_arm.setdefault(moiety, {}).setdefault(key, set()).add(
            edge["directional_evidence_status"])
        all_classes.setdefault(moiety, set()).add(
            edge["directional_evidence_status"])

    out: dict[str, dict[str, Any]] = {}
    for moiety, arms in per_arm.items():
        status = status_by_moiety.get(moiety, "unresolved")
        out[moiety] = {
            "arm_states": {key: policy.arm_evidence_state(statuses)
                           for key, statuses in arms.items()},
            "identity_status": status,
            "stage4_assessment_status": policy.stage4_status(
                identity_status=status, moiety_id=moiety,
                statuses=all_classes.get(moiety, set()))[0],
            "stage4_assessment_reason": policy.stage4_status(
                identity_status=status, moiety_id=moiety,
                statuses=all_classes.get(moiety, set()))[1],
            "baseline_review_status": policy.baseline_review_status(
                all_classes.get(moiety, set())),
        }
    return out
