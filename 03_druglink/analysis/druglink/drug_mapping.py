"""Did each lever's target reach a drug-mappable entity — and if not, WHY?

Three outcomes, and the difference between the last two matters:

  mapped     the target resolved to at least one exact SINGLE PROTEIN entity carrying
             its accession, so a gene-target drug edge is possible.
  unmapped   nothing matched: the target is still a symbol (not an accession), or no
             public source maps that accession at all.
  refused    entities DID match, but every one was a PROTEIN COMPLEX / FAMILY. A
             complex is not a gene and is never translated into one of its components,
             so the mapping is REFUSED. That is a different fact from "nothing matched",
             and collapsing the two would hide a decision behind an absence.

This is a per-(target, arm, origin) status. It is a workflow state, not an eligibility.
"""
from __future__ import annotations

from typing import Any

from . import workflow as wf


def build(*, levers: list[dict[str, Any]], targets: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per (target, arm, origin) lever, with its mapping status."""
    entities = targets["entities"]
    gene_to_entities = targets["gene_to_entities"]

    rows: list[dict[str, Any]] = []
    for lever in levers:
        gene = lever.get("target_ensembl")
        eids = gene_to_entities.get(gene, []) if gene else []
        single = [e for e in eids
                  if entities[e]["direct_gene_lane_eligible"]]
        non_gene = [e for e in eids
                    if not entities[e]["direct_gene_lane_eligible"]]

        status, reason = wf.drug_mapping_status(
            has_accession=bool(lever.get("gene_target_drug_edge_permitted") and gene),
            n_single_protein_entities=len(single),
            n_non_gene_entities=len(non_gene))

        rows.append({
            "target_ensembl": gene,
            "desired_arm": lever["desired_arm"],
            "origin_type": lever["origin_type"],
            "drug_mapping_status": status,
            "drug_mapping_reason": reason,
            "n_single_protein_entities": len(single),
            "n_non_gene_entities": len(non_gene),
            "source_record_ids": sorted(
                {s for e in eids for s in entities[e]["source_record_ids"]}),
        })
    rows.sort(key=lambda r: (str(r["target_ensembl"]), r["desired_arm"],
                             r["origin_type"]))
    return rows


def dispositions(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A target that reached no drug stays visible, with the reason it did not."""
    return [{
        "subject_kind": "drug_mapping",
        "subject_id": f"{r['target_ensembl']}:{r['desired_arm']}:{r['origin_type']}",
        "state": r["drug_mapping_status"],
        "reason": r["drug_mapping_reason"],
        "detail": (f"single_protein={r['n_single_protein_entities']} "
                   f"non_gene={r['n_non_gene_entities']}"),
        "source_record_id": None,
    } for r in rows if r["drug_mapping_status"] != wf.MAPPED]


def counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {status: sum(1 for r in rows if r["drug_mapping_status"] == status)
            for status in wf.DRUG_MAPPING_STATUSES}
