"""Re-derive the run's IDENTITY from the release alone.

The re-audit's finding, in one line: **the standalone verifier never recomputed
`evidence_inputs_sha256` from the emitted tables.** It checked that a digest was *declared*,
so a resealed release could rewrite a negative search's scope, source, execution date and
extraction transform — keep the `scorecard_set_id` — and still pass 193/193.

This module closes that. From the release directory and the method files ONLY, it:

  1. reads every evidence-input table back out of the parquet,
  2. projects each row onto the bound column set (restated below, independently),
  3. recomputes the canonical digest over those rows,
  4. recomputes the source-registry digest from `source_catalog.parquet`,
  5. recomputes the method-file hashes from `method/`,
  6. re-derives `scorecard_set_id = short_id(chash(scorecard_set_id_inputs))`,

and requires the answers to equal what the manifest declares — and the id to equal the
directory the release is sitting in. So a tampered bound column either fails the digest, or,
if the tamperer also rewrites the digest and the id key, moves the identity. There is no
third outcome.

It imports NOTHING from `analysis/`. The column sets below are a deliberate independent
restatement of `analysis/evidence_inputs.py`; a drift between the two fails a test, which is
the correct failure — a verifier that imported the generator's declaration would be checking
the generator against itself.
"""

from __future__ import annotations

import hashlib
import os
from decimal import Decimal
from typing import Any

import pyarrow.parquet as pq

from . import canon

# The BOUND columns of every evidence-input table: the full consumed row, including the
# complete provenance binding. Restated from the Stage-4 contract, not imported from it.
INPUT_COLUMNS_V1: dict[str, tuple[str, ...]] = {
    "contexts": (
        "context_id", "candidate_id", "active_moiety_id", "route", "formulation", "dose",
        "schedule", "tumor_context", "population", "is_fixture",
    ),
    "property_evidence": (
        "property_record_id", "candidate_id", "active_moiety_id", "property_id",
        "value_source_string", "units", "determination", "calculator_id", "method",
        "software_version", "database_version",
        "source_record_id", "source_url", "access_date", "release_version",
        "raw_response_sha256", "extraction_transform",
    ),
    "potency_evidence": (
        "potency_id", "candidate_id", "active_moiety_id", "metric", "value_source_string",
        "units", "binding_state", "assay", "biological_context", "evidence_type",
        "source_record_id", "source_url", "access_date", "release_version",
        "raw_response_sha256", "extraction_transform",
    ),
    "potency_context_links": (
        "link_id", "potency_id", "tumor_context", "rationale",
        "source_record_id", "source_url", "access_date", "release_version",
        "raw_response_sha256", "extraction_transform",
    ),
    "transporter_evidence": (
        "observation_id", "candidate_id", "active_moiety_id", "transporter",
        "transporter_gene", "interaction", "assay", "species", "biological_system",
        "concentration", "concentration_units", "result_metric", "result_value",
        "result_units", "direction", "evidence_type",
        "source_record_id", "source_url", "access_date", "release_version",
        "raw_response_sha256", "extraction_transform",
    ),
    "exposure_evidence": (
        "measurement_id", "candidate_id", "active_moiety_id", "context_id", "formulation",
        "route", "dose", "schedule", "species_population", "matrix", "enhancement_context",
        "binding_state", "concentration_source_string", "concentration_units",
        "detection_status", "quantitation_limit_kind", "quantitation_limit_source_string",
        "quantitation_limit_units", "timepoint", "kp_reported_source_string",
        "kp_uu_brain_reported_source_string", "evidence_type",
        "source_record_id", "source_url", "access_date", "release_version",
        "raw_response_sha256", "extraction_transform",
    ),
    "delivery_assignments": (
        "assignment_id", "candidate_id", "context_id", "requirement", "basis", "assigned_by",
        "rule_id", "rule_version", "rationale",
        "evidence_source_record_id", "evidence_source_url", "evidence_access_date",
        "evidence_release_version", "evidence_sha256", "evidence_extraction_transform",
    ),
    "nebpi_observations": (
        "observation_id", "candidate_id", "context_id", "criterion_id", "state",
        "assessment_adequate", "adequacy_rationale", "measurement_id", "potency_id",
        "evidence_type",
        "source_record_id", "source_url", "access_date", "release_version",
        "raw_response_sha256", "extraction_transform",
    ),
    "safety_evidence": (
        "evidence_id", "candidate_id", "active_moiety_id", "evidence_state", "finding_type",
        "finding_text", "gbm_scenario", "interaction_type", "label_source", "setid",
        "application_number", "product_identity", "label_version", "effective_date",
        "labeled_section_code", "labeled_section_name", "code_system",
        "labeled_subsection_code", "labeled_subsection_name", "searched_sources",
        "search_id",
        "source_record_id", "source_url", "access_date", "release_version",
        "raw_response_sha256", "extraction_transform",
    ),
    "search_manifests": (
        "search_id", "source", "endpoint", "query_canonical", "search_scope",
        "executed_date", "source_release", "n_results",
        "source_record_id", "source_url", "access_date", "release_version",
        "response_sha256", "extraction_transform",
    ),
}

# The provenance-class fields of a source record that feed `source_registry_sha256`.
SOURCE_REGISTRY_FIELDS = (
    ("source_type", "source_type"),
    ("acquisition_status", "acquisition_status"),
    ("url", "url"),
    ("record_id", "record_id"),
    ("release_version", "release_version"),
    ("license", "license"),
    ("raw_sha256", "raw_sha256"),
    ("raw_bytes", "raw_bytes"),
    ("raw_media_type", "raw_media_type"),
)

# logical method key -> the file on disk. Keyed as the engine keys it, so the recomputed
# map is comparable cell for cell with the one bound into the id.
METHOD_FILES_V1 = {
    "cns_mpo": "cns_mpo_wager2010_v1.json",
    "nebpi": "nebpi_grossman2026_v1.json",
    "calculator_policy": "calculator_policy_v1.json",
    "delivery_rules": "delivery_rules_v1.json",
    "safety_taxonomy": "safety_taxonomy_v1.json",
    "sources": "sources.json",
    "prose": "stage4_prose_v1.json",
}


# ---------------------------------------------------------------- contract v2 (restated)
# v1 above is FROZEN. v2 APPENDS to it. This is a deliberate independent restatement of
# `analysis/evidence_inputs.py` -- a verifier that imported the generator's column set would be
# checking the generator against itself -- and a drift between the two fails a test.
#
# The version comes from the RELEASE, not from this code: a release that does not declare one
# is a v1 release (it was written before the field existed), and demanding v2 columns of it is
# how a historical artifact becomes unverifiable.

V2_ADDED_COLUMNS: dict[str, tuple[str, ...]] = {
    "potency_evidence": (
        "relation", "assay_activity_id", "assay_assay_id", "assay_target_id",
        "assay_document_id", "assay_type", "assay_description",
        "assay_experimental_system", "assay_target_organism",
        "assay_target_uniprot_accession", "assay_confidence_score",
        "assay_validity_comment",
    ),
    "exposure_evidence": (
        "pk_metric", "pk_statistic", "pk_sample_size", "pk_variability_kind",
        "pk_variability_source_string", "pk_variability_units",
        "sampling_method", "sample_location", "time_relative_to_dose", "analytical_method",
        "steady_state", "residual_blood_correction", "microdialysis_recovery_state",
        "microdialysis_recovery_source_string", "microdialysis_recovery_method",
        "co_medications", "assay_method", "paired_plasma_measurement_id",
        "binding_state_basis", "unbound_from_measurement_id", "unbound_fraction_unbound_id",
        "unbound_transform",
        "kp_basis", "kp_value_source_string", "kp_derivation_transform",
        "kp_input_measurement_ids", "kp_fraction_unbound_ids",
        "kp_uu_basis", "kp_uu_value_source_string", "kp_uu_derivation_transform",
        "kp_uu_input_measurement_ids", "kp_uu_fraction_unbound_ids",
    ),
    "safety_evidence": (
        "organ_system", "organ_system_value_kind", "organ_system_evidence_state",
        "organ_system_source_key", "organ_system_source_record_id", "organ_system_setid",
        "organ_system_label_version", "organ_system_raw_response_sha256",
        "organ_system_section_code", "organ_system_subsection_code",
        "organ_system_code_system", "organ_system_locator",
        "organ_system_extraction_transform", "organ_system_reason",
    ),
}

V2_ONLY_COLUMNS: dict[str, tuple[str, ...]] = {
    "fraction_unbound": (
        "fraction_unbound_id", "candidate_id", "active_moiety_id", "matrix",
        "value_source_string", "method", "species", "concentration_dependence",
        "source_record_id", "source_url", "access_date", "release_version",
        "raw_response_sha256", "extraction_transform",
    ),
    "source_acquisition": (
        # W8's `AcquisitionRecord`, field for field (`analysis/acquisition.py`). Not a second
        # declaration of the same evidence -- a rival record was exactly the duplication this
        # lane was told not to create, and the two would have drifted.
        "acquisition_record_id", "source_key", "source_name", "source_type", "origin",
        "stable_record_id", "url", "canonical_query", "canonical_query_sha256",
        "accessed_at_utc", "access_date", "http_status", "raw_media_type",
        "response_headers_json", "release_or_last_updated", "license", "license_or_terms_url",
        "license_status", "redistribution", "raw_bytes", "raw_sha256", "content_sha256",
        "content_hash_rule", "cache_relpath", "extraction_transform", "adapter_code_sha256",
        "review_status", "evidence_state", "stage3_source_record_id", "note",
    ),
}

INPUT_COLUMNS_V2: dict[str, tuple[str, ...]] = {
    **{t: cols + V2_ADDED_COLUMNS.get(t, ()) for t, cols in INPUT_COLUMNS_V1.items()},
    **V2_ONLY_COLUMNS,
}

# v2 method content lives in NEW files. Editing a v1 method file, or adding one to METHOD_FILES_V1,
# would change the hashes every release ever emitted bound into its id.
METHOD_FILES_V2 = {
    **METHOD_FILES_V1,
    "nebpi_source_framing": "nebpi_source_framing_v2.json",
    "safety_taxonomy_v2": "safety_taxonomy_v2.json",
}

INPUT_COLUMNS = {"v1": INPUT_COLUMNS_V1, "v2": INPUT_COLUMNS_V2}
METHOD_FILES = {"v1": METHOD_FILES_V1, "v2": METHOD_FILES_V2}


def contract_version(manifest: dict) -> str:
    """Absent means v1 -- a release written before the field existed IS a v1 release."""
    return manifest.get("evidence_contract_version") or "v1"


def input_columns(version: str = "v1") -> dict[str, tuple[str, ...]]:
    return INPUT_COLUMNS[version]


def _no_floats(node: Any) -> Any:
    """A float in identity content is a bug; make it exact and explicit, as the engine does."""
    if isinstance(node, float):
        return format(Decimal(repr(node)).normalize(), "E")
    if isinstance(node, dict):
        return {k: _no_floats(v) for k, v in node.items()}
    if isinstance(node, (list, tuple)):
        return [_no_floats(v) for v in node]
    return node


def evidence_inputs_digest(tables: dict[str, list[dict]], version: str = "v1") -> str:
    """The canonical digest over every bound evidence-input row in the release.

    Row order is irrelevant (rows are sorted by their own content hash), so a permuted
    release hashes identically — and a single changed bound cell does not.
    """
    payload: dict[str, list[Any]] = {}
    columns = input_columns(version)
    for table in sorted(columns):
        cols = columns[table]
        rows = [_no_floats({c: r.get(c) for c in cols}) for r in tables.get(table, [])]
        rows.sort(key=canon.chash_strict)
        payload[table] = rows
    return canon.chash_strict(payload)


def source_registry_digest(tables: dict[str, list[dict]]) -> str:
    payload = {}
    for row in tables.get("source_catalog", []):
        payload[row["source_record_id"]] = {
            key: row.get(col) for key, col in SOURCE_REGISTRY_FIELDS
        }
    return canon.chash_strict(dict(sorted(payload.items())))


def method_file_sha256(method_dir: str, version: str = "v1") -> dict[str, str]:
    out = {}
    for key, name in METHOD_FILES[version].items():
        path = os.path.join(method_dir, name)
        if os.path.exists(path):
            with open(path, "rb") as fh:
                out[key] = hashlib.sha256(fh.read()).hexdigest()
    return dict(sorted(out.items()))


# The candidate row, reassembled from `drug_forms.parquet` into the exact nested shape the
# Stage-3 row hash is taken over. The release carries the WHOLE row (it used to carry a lossy
# projection), so this hash can be recomputed and compared with the one bound into the id.
def candidate_rows_sha256(tables: dict[str, list[dict]]) -> str:
    rows = []
    for f in tables.get("drug_forms", []):
        rows.append({
            "candidate_id": f["candidate_id"],
            "active_moiety": {
                "active_moiety_id": f["active_moiety_id"],
                "active_moiety_name": f["active_moiety_name"],
                "unii": f["unii"],
                "inchikey": f["inchikey"],
                "administered_form": f["administered_form"],
                "administered_form_name": f["administered_form_name"],
                "maps_to_active_moiety_id": f["maps_to_active_moiety_id"],
                "mapping_source_record_id": f["mapping_source_record_id"],
            },
            "compound_ids": {
                "chembl_id": f["chembl_id"], "pubchem_cid": f["pubchem_cid"],
                "drugbank_id": f["drugbank_id"], "rxcui": f["rxcui"],
            },
            "target": f["target"],
            "mechanism": f["mechanism"],
            "program_direction": f["program_direction"],
            "drug_effect_direction": f["drug_effect_direction"],
            "direction_compatibility": f["direction_compatibility"],
            "namespace": f["namespace"],
            "stage3_evidence_source_record_ids": list(
                f["stage3_evidence_source_record_ids"] or []),
        })
    rows.sort(key=lambda r: r["candidate_id"])
    return canon.chash_strict(rows)


def rederive_scorecard_set_id(id_key: dict[str, Any]) -> str:
    """short_id(chash_strict(key)) — the generator's rule, restated."""
    return canon.chash_strict(id_key)[:16]


def load_input_tables(out_dir: str, version: str = "v1") -> dict[str, list[dict]]:
    tables: dict[str, list[dict]] = {}
    for table in list(input_columns(version)) + ["source_catalog", "drug_forms"]:
        path = os.path.join(out_dir, f"{table}.parquet")
        if os.path.exists(path):
            tables[table] = pq.read_table(path).to_pylist()
    return tables
