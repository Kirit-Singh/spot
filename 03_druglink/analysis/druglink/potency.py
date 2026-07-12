"""Potency evidence: bound exactly, never transferred, never rounded (finding 7).

Each row binds to:

  * the EXACT source molecule and the FORM it resolves to -- an assay measured on
    a parent can never substantiate an edge on its salt or prodrug. Transfer to
    another form would require an explicit sourced transfer policy; none exists,
    so ``form_binding`` is always ``exact_source_form``;
  * the EXACT source target ENTITY (not a gene). A complex-target assay is one
    association with that entity, and the entity's component genes are recorded
    separately -- we never store "the first Ensembl";
  * the exact assay/activity record: activity_id, assay_id, type, description,
    confidence, species, cell line, document and reference URL.

Values keep their exact source string plus a canonical decimal. 4.0e-7 and 4.9e-7
are different rows with different hashes. A missing relation stays
``not_reported``; it is never invented as "=".
"""
from __future__ import annotations

from typing import Any, Iterable

from . import identity
from .hashing import CanonicalizationError, canonical_decimal, short_id
from .targets import confidence_class

POTENCY_POLICY_VERSION = "stage3-potency-v2"

VALID_RELATIONS = ("=", "<", ">", "<=", ">=", "~")


def build(*, records: Iterable[dict[str, Any]], edges: list[dict[str, Any]],
          graph: dict[str, Any], targets: dict[str, Any]) -> dict[str, Any]:
    edges_by_form_entity: dict[tuple[str, str], list[str]] = {}
    for e in edges:
        edges_by_form_entity.setdefault((e["form_id"], e["target_entity_id"]),
                                        []).append(e["edge_id"])

    rows: dict[str, dict[str, Any]] = {}
    dispositions: list[dict[str, Any]] = []

    for rec in records:
        if rec.get("record_kind") != "potency":
            continue
        form_id = identity.form_for_identifiers(graph, rec["molecule_identifiers"])
        if form_id is None:
            dispositions.append({
                "subject_kind": "potency_row",
                "subject_id": rec.get("activity_id") or rec["source_molecule_id"],
                "state": "unlinked",
                "reason": "potency_molecule_has_no_identity_record",
                "detail": rec["source_molecule_id"],
                "source_record_id": rec["source_record_id"]})
            continue
        eid = targets["by_source_id"].get((rec["source"], rec.get("source_target_id")))
        if eid is None:
            dispositions.append({
                "subject_kind": "potency_row",
                "subject_id": rec.get("activity_id") or rec["source_molecule_id"],
                "state": "unlinked",
                "reason": "potency_target_not_in_any_acquired_target_record",
                "detail": str(rec.get("source_target_id")),
                "source_record_id": rec["source_record_id"]})
            continue

        rel = rec.get("relation_source")
        if rel is not None and rel not in VALID_RELATIONS:
            dispositions.append({
                "subject_kind": "potency_row",
                "subject_id": rec.get("activity_id") or rec["source_molecule_id"],
                "state": "unparsable_relation",
                "reason": "source_relation_outside_the_frozen_vocabulary",
                "detail": str(rel),
                "source_record_id": rec["source_record_id"]})
            rel = None

        value_str = rec.get("value_source_string")
        try:
            canonical = canonical_decimal(value_str) if value_str is not None else None
        except CanonicalizationError:
            canonical = None
            dispositions.append({
                "subject_kind": "potency_row",
                "subject_id": rec.get("activity_id") or rec["source_molecule_id"],
                "state": "unparsable_value",
                "reason": "source_value_is_not_a_decimal",
                "detail": str(value_str),
                "source_record_id": rec["source_record_id"]})

        form = graph["form_index"][form_id]
        row = {
            "form_id": form_id,
            "source_molecule_id": rec["source_molecule_id"],
            "active_moiety_id": form["active_moiety_id"],
            "target_entity_id": eid,
            "source_target_id": rec.get("source_target_id"),
            # Exact-form binding only: the edges of THIS form on THIS entity.
            "edge_ids": sorted(edges_by_form_entity.get((form_id, eid), [])),
            "potency_type": rec["potency_type"],
            "relation": rel,
            "relation_status": "reported" if rel is not None else "not_reported",
            "value_source_string": value_str,
            "value_canonical_decimal": canonical,
            "unit_source": rec.get("unit_source"),
            "form_binding": "exact_source_form",
            "transfer_policy_id": None,
            "activity_id": rec.get("activity_id"),
            "assay_id": rec.get("assay_id"),
            "assay_type": rec.get("assay_type"),
            "assay_description": rec.get("assay_description"),
            "assay_confidence_score": rec.get("assay_confidence_score"),
            "confidence_class": confidence_class(rec.get("assay_confidence_score")),
            "assay_organism": rec.get("assay_organism"),
            "target_organism": rec.get("target_organism"),
            "assay_cell_line": rec.get("assay_cell_line"),
            "document_id": rec.get("document_id"),
            "ref_url": rec.get("ref_url"),
            "source": rec["source"],
            "source_record_id": rec["source_record_id"],
        }
        row["potency_row_id"] = short_id({k: v for k, v in row.items()
                                          if k != "edge_ids"})
        rows[row["potency_row_id"]] = row

    return {"potency_rows": [rows[k] for k in sorted(rows)],
            "dispositions": dispositions}
