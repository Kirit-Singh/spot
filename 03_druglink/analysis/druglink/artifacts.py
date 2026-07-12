"""The Stage-3 bundle: normalized tables, content hashes, atomic directory binding.

Output root by artifact class:

  analysis  <output_root>/s3_<id>/            a real computation over real inputs
  fixture   <output_root>/fixtures_only/fx_<id>/   synthetic; never reaches Stage 4

The bundle is written to a temporary sibling and moved into place only once the
manifest is complete, so a run can never half-replace an earlier one. If the target
directory already exists, its manifest must match byte for byte or the write is
refused.

Table identity is the row-order-invariant CONTENT hash, so permuting rows cannot
change an ID. File digests are recorded too and the verifier checks both — a
display-only column tampered with in the parquet is caught by the file hash even
though it is excluded from the content hash.

The arm-lever column list is DERIVED from :mod:`druglink.armlever`'s constants
rather than restated, so the table and the expansion cannot drift apart.
"""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from typing import Any, Iterable, Optional

import pandas as pd

from . import artifact_class as ac
from .armlever import (CROSS_ARM_COLUMNS, IMMUTABLE_KEY, JOINT_CONTEXT_COLUMNS,
                       POLE_SUFFIXES, SHARED_COLUMNS)
from .hashing import content_hash, file_sha256, table_hash

MANIFEST_SCHEMA = "spot.stage03_manifest.v1"

# Display-only columns: excluded from CONTENT hashes (and so from the bundle ID),
# but still covered by the file hash the verifier checks.
DISPLAY_COLUMNS = frozenset({"preferred_name", "target_symbol"})

ARM_LEVER_COLUMNS: tuple[str, ...] = (
    ("direct_run_id", "desired_arm", "origin_type")
    + SHARED_COLUMNS
    + ("arm_value_source_string", "arm_value_canonical_decimal",
       "arm_delta_source_string", "arm_delta_canonical_decimal",
       "arm_rank", "arm_evaluable", "target_identity_state",
       "gene_target_drug_edge_permitted", "arm_direction_measured")
    + tuple(f"arm_{s}" for s in POLE_SUFFIXES if s not in ("delta", "evaluable"))
    + ("arm_lever_key", "arm_lever_id")
)

TABLES: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "arm_levers": (ARM_LEVER_COLUMNS, IMMUTABLE_KEY),
    "cross_arm": (
        ("direct_run_id", "released_estimate_id", "target_id",
         "target_id_namespace", "target_ensembl", "condition")
        + CROSS_ARM_COLUMNS + JOINT_CONTEXT_COLUMNS + ("descriptive_only",),
        ("target_id", "released_estimate_id")),
    "source_records": (
        ("source_record_id", "artifact_class", "source", "adapter", "adapter_version",
         "adapter_status", "source_release", "source_endpoint", "retrieval_url",
         "query_canonical", "license", "attribution", "acquisition_status",
         "raw_sha256", "raw_bytes", "raw_media_type", "access_record_sha256",
         "parse_status", "parse_detail"),
        ("source_record_id",)),
    "target_entities": (
        ("target_entity_id", "source", "source_target_id", "target_type",
         "target_entity_class", "organism", "direct_gene_lane_eligible",
         "component_rule", "source_record_ids"),
        ("target_entity_id",)),
    "target_entity_components": (
        ("target_entity_id", "uniprot_id", "target_ensembl", "component_role",
         "component_relationship", "source_record_id"),
        ("target_entity_id", "uniprot_id")),
    "drug_forms": (
        ("form_id", "preferred_name", "form_class", "moiety_assignment_status",
         "active_moiety_id", "ingredient_form_ids", "n_ingredients", "route",
         "route_status", "formulation", "formulation_status", "development_states",
         "identity_conflicts", "source_record_ids"),
        ("form_id",)),
    "drug_identifiers": (
        ("form_id", "id_type", "id_value", "source", "source_record_id"),
        ("form_id", "id_type", "id_value", "source_record_id")),
    "drug_form_relations": (
        ("from_form_id", "relation", "to_form_id", "source", "source_record_id"),
        ("from_form_id", "relation", "to_form_id", "source_record_id")),
    "active_moieties": (
        ("active_moiety_id", "preferred_name", "moiety_inchikey", "moiety_chembl_id",
         "moiety_pubchem_cid", "moiety_rxcui", "moiety_unii", "identity_status",
         "identity_conflicts", "form_ids", "development_states",
         "development_state_aggregate", "source_record_ids"),
        ("active_moiety_id",)),
    "mechanism_assertions": (
        ("assertion_id", "source", "source_record_id", "source_record_row_id",
         "source_molecule_id", "form_id", "target_entity_id", "action_type_source",
         "action_type_normalized", "intervention_effect",
         "intervention_effect_reason", "mechanism_of_action_text",
         "direct_interaction_flag", "directness_class", "mechanism_refs", "ref_urls"),
        ("assertion_id",)),
    "pathway_nodes": (
        ("pathway_node_id", "pathway_node_key", "direct_run_id", "pathway_id",
         "target_ensembl", "target_id", "target_id_namespace", "target_symbol",
         "desired_arm", "origin_type", "arm_desired_target_modulation",
         "arm_evaluable", "arm_state", "arm_evidence_tier", "arm_support_state",
         "evidence_status", "programmatic_evidence_method_id",
         "programmatic_statistic_name", "programmatic_enrichment_value",
         "programmatic_rounding_rule_id", "programmatic_rounding_rule",
         "programmatic_inference_status",
         "pathway_record_id", "gene_set_release_id", "gene_set_sha256",
         "universe_id", "universe_sha256",
         "science_evidence_refs", "n_science_evidence_refs",
         "n_contributing_perturbations",
         "contributing_perturbations", "target_identity_state",
         "gene_target_drug_edge_permitted", "arm_direction_measured"),
        ("pathway_node_id",)),
    "pathways": (
        ("direct_run_id", "pathway_id", "pathway_record_id", "pathway_source",
         "pathway_source_release", "pathway_source_sha256",
         "computed_enrichment_method_id", "computed_statistic_name",
         "computed_enrichment_value", "computed_rounding_rule_id",
         "computed_rounding_rule", "computed_inference_status", "gene_set_release_id",
         "gene_set_sha256", "universe_id", "universe_sha256",
         "science_evidence_refs", "n_science_evidence_refs", "n_nodes"),
        ("pathway_id",)),
    "target_drug_edges": (
        ("edge_id", "desired_arm", "origin_type", "source_lever_key", "target_ensembl",
         "target_symbol", "arm_rank", "arm_value_source_string",
         "arm_value_canonical_decimal", "arm_evaluable", "arm_state",
         "arm_evidence_tier", "arm_support_state", "arm_desired_target_modulation",
         "arm_direction_measured", "target_entity_id", "target_entity_class",
         "uniprot_id", "form_id", "active_moiety_id", "action_type_sources",
         "action_type_normalized", "intervention_effect",
         "intervention_effect_reason", "directness_state", "directness_classes",
         "action_conflict", "n_assertions", "assertion_ids", "lane",
         "perturbation_modality", "observed_target_abundance_direction",
         "directional_evidence_status", "directional_evidence_reason",
         "observed_perturbation_support", "stage3_evidence_class",
         "source_record_ids"),
        ("edge_id",)),
    "candidate_arm_summaries": (
        ("candidate_id", "active_moiety_id", "desired_arm", "origin_type",
         "arm_evidence_state", "n_edges", "n_direct_gene_edges",
         "n_observed_perturbation", "n_inverse_direction_hypothesis",
         "n_pathway_hypothesis", "n_opposed", "n_unresolved",
         "observed_perturbation_support", "edge_ids", "arm_ranks",
         "arm_evidence_tiers", "target_ensembls", "action_conflict"),
        ("candidate_id", "desired_arm", "origin_type")),
    "potency_evidence": (
        ("potency_row_id", "form_id", "source_molecule_id", "active_moiety_id",
         "target_entity_id", "source_target_id", "edge_ids", "potency_type",
         "relation", "relation_status", "value_source_string",
         "value_canonical_decimal", "unit_source", "form_binding",
         "transfer_policy_id", "activity_id", "assay_id", "assay_type",
         "assay_description", "assay_confidence_score", "confidence_class",
         "assay_organism", "target_organism", "assay_cell_line", "document_id",
         "ref_url", "source", "source_record_id"),
        ("potency_row_id",)),
    "drug_mapping": (
        ("target_ensembl", "desired_arm", "origin_type", "drug_mapping_status",
         "drug_mapping_reason", "n_single_protein_entities",
         "n_non_gene_entities", "source_record_ids"),
        ("target_ensembl", "desired_arm", "origin_type")),
    "dispositions": (
        ("disposition_id", "subject_kind", "subject_id", "state", "reason", "detail",
         "source_record_id"),
        ("disposition_id",)),
    "candidates": (
        ("candidate_id", "active_moiety_id", "preferred_name", "identity_status",
         "identity_conflicts", "arm_evidence_states", "observed_perturbation_arms",
         "inverse_direction_hypothesis_arms", "inverse_direction_support",
         "pathway_hypothesis_arms", "opposed_arms", "stage3_evidence_classes",
         "disease_context_review_status", "disease_context_review_result",
         "disease_context_review_reason", "disease_context_review_evidence_refs",
         "disease_context_reviewed_by", "form_ids", "target_ensembls",
         "n_edges", "n_direct_gene_edges", "development_state_aggregate",
         "n_potency_rows", "potency_state", "stage4_assessment_status",
         "stage4_assessment_reason", "source_record_ids"),
        ("candidate_id",)),
}


class ArtifactError(RuntimeError):
    """A bundle could not be bound atomically to its directory."""


def project(name: str, rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    cols, _ = TABLES[name]
    return [{c: r.get(c) for c in cols} for r in rows]


def table_content_hash(name: str, rows: Iterable[dict[str, Any]]) -> str:
    cols, sort_keys = TABLES[name]
    content_cols = [c for c in cols if c not in DISPLAY_COLUMNS]
    keys = tuple(k for k in sort_keys if k in content_cols) or (content_cols[0],)
    return table_hash([{c: r.get(c) for c in content_cols} for r in rows], keys)


def table_content_hashes(tables: dict[str, list[dict[str, Any]]]) -> dict[str, str]:
    return {name: table_content_hash(name, tables.get(name, []))
            for name in sorted(TABLES)}


def _frame(name: str, rows: list[dict[str, Any]]) -> pd.DataFrame:
    cols, _ = TABLES[name]
    if not rows:
        return pd.DataFrame({c: pd.Series(dtype="object") for c in cols})
    frame = pd.DataFrame(project(name, rows), columns=list(cols))
    # A nullable rank must survive the round trip as NULL, never as a float NaN: a
    # consumer that calls int() on NaN crashes, and one that coerces it invents a
    # rank for a target that has none.
    for col in ("arm_rank",):
        if col in frame.columns:
            frame[col] = pd.array(
                [None if v is None or pd.isna(v) else int(v) for v in frame[col]],
                dtype="Int64")
    return frame


def write_json(path: str, doc: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True, ensure_ascii=True)
        fh.write("\n")


def bundle_dir(output_root: str, artifact_class: str, doc_id: str) -> str:
    sub = ac.OUTPUT_SUBDIR[artifact_class]
    return (os.path.join(output_root, sub, doc_id) if sub
            else os.path.join(output_root, doc_id))


def write_bundle(*, output_root: str, artifact_class: str,
                 document: dict[str, Any], doc_id: str,
                 tables: dict[str, list[dict[str, Any]]],
                 created_at: Optional[str] = None) -> str:
    ac.check_no_retired_keys(document)
    target = bundle_dir(output_root, artifact_class, doc_id)
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    staging = tempfile.mkdtemp(prefix=".stage3_staging_",
                               dir=os.path.dirname(target) or ".")
    try:
        files: list[dict[str, Any]] = []
        for name in sorted(TABLES):
            rows = tables.get(name, [])
            fname = f"{name}.parquet"
            _frame(name, rows).to_parquet(os.path.join(staging, fname), index=False)
            files.append({
                "file": fname, "n_rows": len(rows),
                "content_sha256": table_content_hash(name, rows),
                "file_sha256": file_sha256(os.path.join(staging, fname)),
            })

        doc_name = ac.OUTPUT_DOC[artifact_class]
        write_json(os.path.join(staging, doc_name), document)
        files.append({
            "file": doc_name,
            "n_rows": len(document["candidates"]),
            "content_sha256": document["canonical_content_sha256"],
            "file_sha256": file_sha256(os.path.join(staging, doc_name)),
        })

        manifest = {
            "schema_version": MANIFEST_SCHEMA,
            "artifact_class": artifact_class,
            "bundle_id": doc_id,
            "document_file": doc_name,
            "document_sha256": document["document_sha256"],
            "canonical_content_sha256": document["canonical_content_sha256"],
            "upstream": document["upstream"],
            "method": document["method"],
            "acquisition": document["acquisition"],
            "pathway_hypotheses": document["pathway_hypotheses"],
            "stage2_joint_context": document["stage2_joint_context"],
            "data_status": document["data_status"],
            "inference_status": document["inference_status"],
            "deferred_lanes": document["deferred_lanes"],
            "table_hashes": document["table_hashes"],
            "counts": document["counts"],
            "files": sorted(files, key=lambda f: f["file"]),
            "created_at": created_at,
        }
        manifest["manifest_sha256"] = content_hash(
            {k: v for k, v in manifest.items()
             if k not in ("manifest_sha256", "created_at")})
        write_json(os.path.join(staging, "manifest.json"), manifest)

        if os.path.exists(target):
            _refuse_unless_identical(target, manifest)
            shutil.rmtree(staging)
            return target
        os.rename(staging, target)      # atomic bind of directory <-> manifest
        return target
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def _refuse_unless_identical(target: str, manifest: dict[str, Any]) -> None:
    existing_path = os.path.join(target, "manifest.json")
    if not os.path.exists(existing_path):
        raise ArtifactError(
            f"refusing to write into {os.path.basename(target)}: it exists but has "
            "no manifest")
    with open(existing_path, "r", encoding="utf-8") as fh:
        existing = json.load(fh)
    if existing.get("manifest_sha256") != manifest["manifest_sha256"]:
        raise ArtifactError(
            f"refusing to overwrite {os.path.basename(target)}: an existing bundle "
            f"with the same ID has different content "
            f"({existing.get('manifest_sha256')} != {manifest['manifest_sha256']})")
