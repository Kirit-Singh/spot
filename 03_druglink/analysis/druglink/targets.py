"""Target entities: a complex or a family is NOT a gene (audit finding 6).

A ChEMBL target is a source ENTITY, not a gene. Only ``SINGLE PROTEIN`` carries
gene identity and may enter the direct gene mechanism lane. Complexes, complex
groups and families are kept as first-class entities with component/member roles;
because no frozen component-specific translation rule exists, a drug acting on
such an entity has ``translation_support=target_entity_not_a_gene`` and can never
be ``matched`` on one of its components.

Assay confidence follows ChEMBL's documented scale: 9 = direct single protein,
8 = HOMOLOGOUS single protein (a different protein in another species -- never
"direct curated"), <= 7 = lower confidence.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from .hashing import short_id

TARGET_POLICY_VERSION = "stage3-targets-v1"

ENTITY_CLASS = {
    "SINGLE PROTEIN": "single_protein",
    "PROTEIN COMPLEX": "protein_complex",
    "PROTEIN COMPLEX GROUP": "protein_complex_group",
    "PROTEIN FAMILY": "protein_family",
    "CHIMERIC PROTEIN": "other_non_gene_entity",
    "PROTEIN-PROTEIN INTERACTION": "other_non_gene_entity",
    "SELECTIVITY GROUP": "other_non_gene_entity",
}
COMPONENT_ROLE = {
    "single_protein": "single_protein",
    "protein_complex": "complex_component",
    "protein_complex_group": "complex_component",
    "protein_family": "family_member",
    "other_non_gene_entity": "complex_component",
}

CONFIDENCE_CLASS = {
    9: "direct_single_protein",
    8: "homologous_single_protein",
}


def confidence_class(score: Optional[int]) -> str:
    if score is None:
        return "not_reported"
    return CONFIDENCE_CLASS.get(int(score), "lower_confidence")


def entity_class(target_type: str) -> str:
    return ENTITY_CLASS.get(target_type, "other_non_gene_entity")


def target_entity_id(source: str, source_target_id: str) -> str:
    return short_id({"source": source, "source_target_id": source_target_id})


class TargetIdentityConflict(ValueError):
    """One UniProt accession, two different genes. Stage 3 refuses to pick one.

    This used to be ``uniprot_to_gene[acc] = gene`` — last write wins. Whichever record
    happened to be parsed last silently became the truth, so the identity of a drug target
    depended on the ORDER the public responses arrived in. Reverse the pages and the answer
    changes, with no error, no disposition and nothing in the bundle to say a choice was
    ever made.

    There is no safe tie-break here. Picking the first, the last, the lowest-sorting, or
    the "reviewed" one all invent a resolution the sources did not agree on. A conflicting
    accession is a named refusal.
    """


def resolve_uniprot_to_gene(recs: list[dict[str, Any]]) -> dict[str, str]:
    """UniProt -> Ensembl, FAIL-CLOSED on disagreement.

    A gene legitimately has several accessions (many-to-one is normal and fine). An
    accession mapping to two DIFFERENT genes is not — it is a contradiction in the
    evidence, and Stage 3 will not silently resolve it.
    """
    seen: dict[str, dict[str, list[str]]] = {}
    for r in recs:
        if r.get("record_kind") != "gene_map":
            continue
        acc, gene = r["uniprot_id"], r["target_ensembl"]
        by_gene = seen.setdefault(acc, {})
        by_gene.setdefault(gene, []).append(r.get("source_record_id", "?"))

    conflicts = {acc: genes for acc, genes in seen.items() if len(genes) > 1}
    if conflicts:
        detail = "; ".join(
            f"{acc} -> {sorted(genes)} (records {sorted(rid for g in genes.values()
                                                        for rid in g)})"
            for acc, genes in sorted(conflicts.items()))
        raise TargetIdentityConflict(
            f"{len(conflicts)} UniProt accession(s) map to MORE THAN ONE gene: {detail}. "
            "Stage 3 will not pick one: last-write-wins would make a drug target's "
            "identity depend on the order the public pages happened to arrive in. Resolve "
            "the conflict upstream, or exclude the accession — do not let it be decided by "
            "parse order.")

    return {acc: next(iter(genes)) for acc, genes in seen.items()}


def build(records: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Return {entities, components, by_source_id, gene_to_entities, dispositions}."""
    recs = list(records)
    uniprot_to_gene = resolve_uniprot_to_gene(recs)

    entities: dict[str, dict[str, Any]] = {}
    components: list[dict[str, Any]] = []
    dispositions: list[dict[str, Any]] = []

    for r in recs:
        if r.get("record_kind") != "target_entity":
            continue
        eid = target_entity_id(r["source"], r["source_target_id"])
        klass = entity_class(r["target_type"])
        is_gene = klass == "single_protein"
        e = entities.setdefault(eid, {
            "target_entity_id": eid,
            "source": r["source"],
            "source_target_id": r["source_target_id"],
            "target_type": r["target_type"],
            "target_entity_class": klass,
            "organism": r.get("organism"),
            "direct_gene_lane_eligible": is_gene,
            "component_rule": ("single_protein_identity" if is_gene
                               else "no_frozen_component_rule_translation_unknown"),
            "source_record_ids": set(),
        })
        e["source_record_ids"].add(r["source_record_id"])
        if not is_gene:
            dispositions.append({
                "subject_kind": "target_entity", "subject_id": eid,
                "state": klass,
                "reason": "non_gene_target_entity_no_frozen_component_rule",
                "detail": f"{r['source_target_id']} is a {r['target_type']}",
                "source_record_id": r["source_record_id"],
            })
        for c in r["components"]:
            components.append({
                "target_entity_id": eid,
                "uniprot_id": c["uniprot_id"],
                "target_ensembl": uniprot_to_gene.get(c["uniprot_id"]),
                "component_role": COMPONENT_ROLE[klass],
                "component_relationship": c.get("component_relationship"),
                "source_record_id": r["source_record_id"],
            })

    gene_to_entities: dict[str, list[str]] = {}
    for c in components:
        if c["target_ensembl"]:
            gene_to_entities.setdefault(c["target_ensembl"], []).append(
                c["target_entity_id"])

    return {
        "entities": {eid: {**e, "source_record_ids": sorted(e["source_record_ids"])}
                     for eid, e in entities.items()},
        "components": sorted(components, key=lambda c: (c["target_entity_id"],
                                                        c["uniprot_id"])),
        "by_source_id": {(e["source"], e["source_target_id"]): eid
                         for eid, e in entities.items()},
        "gene_to_entities": {g: sorted(set(v)) for g, v in gene_to_entities.items()},
        "entity_genes": _entity_genes(components),
        "dispositions": dispositions,
    }


def _entity_genes(components: list[dict[str, Any]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for c in components:
        if c["target_ensembl"]:
            out.setdefault(c["target_entity_id"], []).append(c["target_ensembl"])
    return {k: sorted(set(v)) for k, v in out.items()}
