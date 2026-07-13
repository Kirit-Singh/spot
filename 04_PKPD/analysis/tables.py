"""Parquet evidence tables — fixed column order, fixed dtypes, fixed row order.

Two hashes per table, for two different questions:

  content_sha256  hash of the canonical rows. Writer-independent and machine-
                  independent: this is the scientific identity of the table.
  file_sha256     hash of the parquet bytes. Detects tampering with the file on disk,
                  but is a function of the pyarrow version, so it is recorded next to
                  the environment lock rather than used as the scientific identity.
"""

from __future__ import annotations

import os
from typing import Any

import pyarrow as pa

from .contract_version import ContractVersion
import pyarrow.parquet as pq

from .canonical import content_sha256, sha256_file

_STR = pa.string()
_F64 = pa.float64()
_BOOL = pa.bool_()
# The inner field must be named "element": that is what parquet round-trips it as, and
# the declared dtype has to survive a write/read cycle for verification to compare them.
_LIST_STR = pa.list_(pa.field("element", pa.string()))

DELIVERY_SCHEMA = pa.schema(
    [
        ("candidate_id", _STR),
        ("context_id", _STR),
        ("active_moiety_id", _STR),
        ("delivery_requirement", _STR),
        ("nebpi_primary_gate", _BOOL),
        ("basis", _STR),
        ("assigned_by", _STR),
        ("rule_id", _STR),
        ("rule_version", _STR),
        ("rationale", _STR),
        ("reason_code", _STR),
        ("downgraded_from", _STR),
        # Which input assignment this decision reduced to — and, when it reduced to none of
        # them, exactly which rows were in conflict.
        ("assignment_id", _STR),
        ("conflicting_assignment_ids", _LIST_STR),
        ("evidence_source_record_id", _STR),
        ("evidence_sha256", _STR),
    ]
)

# The delivery ASSIGNMENT rows the decision above is reduced from. Emitted so the
# independent verifier re-runs the reducer on the same rows instead of trusting the
# generator's reduced output — the audit changed `local_CNS` to `uncertain` by reordering
# these, and nothing downstream could see it.
DELIVERY_ASSIGNMENT_SCHEMA = pa.schema([
    ("assignment_id", _STR), ("candidate_id", _STR), ("context_id", _STR),
    ("requirement", _STR), ("basis", _STR), ("assigned_by", _STR),
    ("rule_id", _STR), ("rule_version", _STR), ("rationale", _STR),
    ("evidence_source_record_id", _STR), ("evidence_source_url", _STR),
    ("evidence_access_date", _STR), ("evidence_release_version", _STR),
    ("evidence_sha256", _STR), ("evidence_extraction_transform", _STR),
])

TRANSPORTER_SCHEMA = pa.schema(
    [
        ("observation_id", _STR),
        ("candidate_id", _STR),
        ("active_moiety_id", _STR),
        ("transporter", _STR),
        ("transporter_gene", _STR),
        ("interaction", _STR),
        ("assay", _STR),
        ("species", _STR),
        ("biological_system", _STR),
        ("concentration", _F64),
        ("concentration_units", _STR),
        ("result_metric", _STR),
        ("result_value", _F64),
        ("result_units", _STR),
        ("direction", _STR),
        ("evidence_type", _STR),
        ("source_record_id", _STR),
        ("source_url", _STR),
        ("access_date", _STR),
        ("release_version", _STR),
        ("raw_response_sha256", _STR),
        ("extraction_transform", _STR),
    ]
)

EXPOSURE_SCHEMA = pa.schema(
    [
        ("measurement_id", _STR),
        ("candidate_id", _STR),
        ("active_moiety_id", _STR),
        ("context_id", _STR),
        ("formulation", _STR),
        ("route", _STR),
        ("dose", _STR),
        ("schedule", _STR),
        ("species_population", _STR),
        ("matrix", _STR),
        ("enhancement_context", _STR),
        ("binding_state", _STR),
        ("detection_status", _STR),
        # Exact magnitude first; the float is display only and never an identity.
        ("concentration_source_string", _STR),
        ("concentration_canonical_decimal", _STR),
        ("concentration_units", _STR),
        # The assay's numeric ceiling on a censored result. Without it a non-detect
        # cannot bound anything against the MEC.
        ("quantitation_limit_kind", _STR),
        ("quantitation_limit_source_string", _STR),
        ("quantitation_limit_canonical_decimal", _STR),
        ("quantitation_limit_units", _STR),
        ("timepoint", _STR),
        ("kp_reported_source_string", _STR),
        ("kp_uu_brain_reported_source_string", _STR),
        ("evidence_type", _STR),
        ("margin_status", _STR),
        ("margin", _F64),
        ("margin_canonical_decimal", _STR),
        ("margin_reason_code", _STR),
        ("harmonized_units", _STR),
        ("exposure_harmonized", _STR),
        ("potency_harmonized", _STR),
        ("potency_id", _STR),
        ("potency_context_link_id", _STR),
        ("margin_transform", _STR),
        ("caveats", _LIST_STR),
        ("source_record_id", _STR),
        ("source_url", _STR),
        ("access_date", _STR),
        ("release_version", _STR),
        ("raw_response_sha256", _STR),
        ("extraction_transform", _STR),
    ]
)

SAFETY_SCHEMA = pa.schema(
    [
        ("evidence_id", _STR),
        ("candidate_id", _STR),
        ("active_moiety_id", _STR),
        ("evidence_state", _STR),
        ("renders_as_safe", _BOOL),
        ("evidence_state_display", _STR),
        ("finding_type", _STR),
        ("finding_text", _STR),
        ("gbm_scenario", _STR),
        ("interaction_type", _STR),
        ("label_source", _STR),
        ("setid", _STR),
        ("application_number", _STR),
        ("product_identity", _STR),
        ("label_version", _STR),
        ("effective_date", _STR),
        ("labeled_section_code", _STR),
        ("labeled_section_name", _STR),
        ("code_system", _STR),
        # WHERE inside the labeled section the sentence was read from. A real label nests its
        # warnings in subsections; without this a finding cannot be traced back to the one it
        # came from.
        ("labeled_subsection_code", _STR),
        ("labeled_subsection_name", _STR),
        ("searched_sources", _LIST_STR),
        # The manifest behind a `no_evidence_found` row. Emitted so the independent verifier
        # can insist the negative search actually exists in the release, rather than taking
        # "we looked and found nothing" on trust.
        ("search_id", _STR),
        ("source_record_id", _STR),
        ("source_url", _STR),
        ("access_date", _STR),
        ("release_version", _STR),
        ("raw_response_sha256", _STR),
        ("extraction_transform", _STR),
    ]
)


# --- the canonical INPUT bundle -------------------------------------------------------
# The audit could not reconstruct an NEBPI class or a margin from the release: the
# context, potency, link, observation, form and search rows were consumed but never
# emitted. Every input the engine reads is now an artifact the verifier can rebuild from.

CONTEXT_SCHEMA = pa.schema([
    ("context_id", _STR), ("candidate_id", _STR), ("active_moiety_id", _STR),
    ("route", _STR), ("formulation", _STR), ("dose", _STR), ("schedule", _STR),
    ("tumor_context", _STR), ("population", _STR), ("is_fixture", _BOOL),
])

DRUG_FORM_SCHEMA = pa.schema([
    ("candidate_id", _STR), ("active_moiety_id", _STR), ("active_moiety_name", _STR),
    ("unii", _STR), ("inchikey", _STR), ("administered_form", _STR),
    ("administered_form_name", _STR), ("maps_to_active_moiety_id", _STR),
    ("mapping_source_record_id", _STR), ("namespace", _STR),
    ("chembl_id", _STR), ("pubchem_cid", _STR), ("drugbank_id", _STR), ("rxcui", _STR),
    ("target", _STR), ("mechanism", _STR), ("direction_compatibility", _STR),
    # The candidate row is hashed WHOLE into candidate_rows_sha256 -> scorecard_set_id, so the
    # release must carry it WHOLE or the verifier cannot recompute that hash. It used to carry a
    # lossy projection: a resealed release could have rewritten a candidate's UNII, target or
    # mechanism and nothing would have noticed.
    ("program_direction", _STR), ("drug_effect_direction", _STR),
    ("stage3_evidence_source_record_ids", _LIST_STR),
    ("production_eligible", _BOOL), ("eligibility_reason_code", _STR),
])

# `property_record_id` identifies the ROW; `property_id` names which of the six CNS-MPO
# inputs it carries. Two agreeing rows are BOTH accepted and BOTH emitted — the audit found
# the selector taking rows[0], so one score carried two possible provenance chains.
PROPERTY_SCHEMA = pa.schema([
    ("property_record_id", _STR),
    ("candidate_id", _STR), ("active_moiety_id", _STR), ("property_id", _STR),
    ("value_source_string", _STR), ("value_canonical_decimal", _STR), ("units", _STR),
    ("value_in_base_units", _F64), ("base_units", _STR), ("unit_conversion", _STR),
    ("determination", _STR), ("calculator_id", _STR), ("method", _STR),
    ("software_version", _STR), ("database_version", _STR), ("method_conformance", _STR),
    ("component_score_t0", _F64), ("accepted", _BOOL),
    ("rejection_reason_code", _STR),
    ("source_record_id", _STR), ("source_url", _STR), ("access_date", _STR),
    ("release_version", _STR), ("raw_response_sha256", _STR),
    ("extraction_transform", _STR),
])

POTENCY_SCHEMA = pa.schema([
    ("potency_id", _STR), ("candidate_id", _STR), ("active_moiety_id", _STR),
    ("metric", _STR), ("value_source_string", _STR), ("value_canonical_decimal", _STR),
    ("units", _STR), ("binding_state", _STR), ("assay", _STR),
    ("biological_context", _STR), ("evidence_type", _STR),
    ("source_record_id", _STR), ("source_url", _STR), ("access_date", _STR),
    ("release_version", _STR), ("raw_response_sha256", _STR),
    ("extraction_transform", _STR),
])

# The FULL provenance binding, not just a source id: the independent verifier resolves
# `source_record_id` against source_catalog and re-checks `raw_response_sha256` against the
# acquired bytes. The audit created an NEBPI class from a link citing `src.DOES_NOT_EXIST`.
POTENCY_CONTEXT_LINK_SCHEMA = pa.schema([
    ("link_id", _STR), ("potency_id", _STR), ("tumor_context", _STR), ("rationale", _STR),
    ("source_record_id", _STR), ("source_url", _STR), ("access_date", _STR),
    ("release_version", _STR), ("raw_response_sha256", _STR),
    ("extraction_transform", _STR),
])

# The WHOLE observation row. `nebpi_reduce` takes the identity of an observation from
# every one of these fields, so the independent verifier must see every one of them: a
# provenance field dropped here would let two distinct rows look like one duplicate.
NEBPI_OBSERVATION_SCHEMA = pa.schema([
    ("observation_id", _STR), ("candidate_id", _STR), ("context_id", _STR),
    ("criterion_id", _STR), ("state", _STR), ("assessment_adequate", _BOOL),
    ("adequacy_rationale", _STR), ("measurement_id", _STR), ("potency_id", _STR),
    ("evidence_type", _STR), ("source_record_id", _STR), ("source_url", _STR),
    ("access_date", _STR), ("release_version", _STR),
    ("raw_response_sha256", _STR), ("extraction_transform", _STR),
])

NEBPI_DECISION_SCHEMA = pa.schema([
    ("candidate_id", _STR), ("context_id", _STR), ("nebpi_status", _STR),
    ("nebpi_class", _STR), ("nebpi_primary_gate", _BOOL), ("delivery_requirement", _STR),
    ("derived_pk_level", _STR), ("pk_measurement_id", _STR), ("pk_potency_id", _STR),
    ("pk_margin_canonical_decimal", _STR), ("pk_detection_status", _STR),
    # How a non-detect was bounded against the MEC, and whether it cleared it.
    ("pk_censored_bound_kind", _STR), ("pk_censored_bound_source_string", _STR),
    ("pk_censored_bound_canonical_decimal", _STR), ("pk_censored_bound_units", _STR),
    ("pk_censored_bound_over_mec_canonical_decimal", _STR),
    ("pk_censored_bound_below_mec", _BOOL),
    ("pk_transform", _STR), ("pk_blocked_code", _STR),
    ("pd_state", _STR), ("radiographic_state", _STR),
    ("satisfied_branches", _LIST_STR), ("reason_codes", _LIST_STR),
    ("method_id", _STR), ("method_version", _STR),
])

# A negative search is a claim about bytes that came back empty, so it names the registered
# source record those bytes belong to. `response_sha256` IS the binding's hash, not a number
# the caller may assert: the audit appended a second manifest under the same search_id with
# an invented endpoint and an invented hash, and both were kept.
# NEBPI is a CRITERION-LEVEL evidence model, and this is the table that says so. One row per
# (candidate, context, criterion): its status, the evidence lane it consumes, whether the source
# lets it satisfy a Part-II branch at all, and whether it did.
#
# The alternative — reporting NEBPI as one class and hiding the nine criteria behind it — is
# exactly the "decorative score" the method exists to prevent: it would make an agent with NO
# NEB evidence and an agent with MEASURED sub-therapeutic NEB exposure look the same from the
# outside. A criterion nobody evaluated reads `not_evaluated` here, forever, and that is never
# a favourable state.
NEBPI_CRITERIA_SCHEMA = pa.schema([
    ("candidate_id", _STR), ("context_id", _STR), ("criterion_id", _STR),
    ("status", _STR),
    ("importance", _STR),
    ("in_part_i_table", _BOOL),
    ("can_satisfy_part_ii_branch", _BOOL),
    ("carried_the_assigned_class", _BOOL),
    ("evidence_lane_consumed", _STR),
    ("requires_potency_context", _BOOL),
    ("n_observations", pa.int64()),
    ("observation_ids", _LIST_STR),
    ("source_verbatim", _STR),
    ("method_id", _STR),
])

SEARCH_MANIFEST_SCHEMA = pa.schema([
    ("search_id", _STR), ("source", _STR), ("endpoint", _STR), ("query_canonical", _STR),
    ("search_scope", _STR), ("executed_date", _STR), ("source_release", _STR),
    ("n_results", pa.int64()), ("response_sha256", _STR),
    ("source_record_id", _STR), ("source_url", _STR), ("access_date", _STR),
    ("release_version", _STR), ("extraction_transform", _STR),
])

SOURCE_CATALOG_SCHEMA = pa.schema([
    ("source_record_id", _STR), ("source_type", _STR), ("source_name", _STR),
    ("acquisition_status", _STR), ("is_fixture", _BOOL), ("url", _STR),
    ("record_id", _STR), ("access_date", _STR), ("release_version", _STR),
    ("license", _STR), ("raw_sha256", _STR), ("raw_bytes", pa.int64()),
    ("raw_media_type", _STR),
])

TABLE_SCHEMAS_V1: dict[str, pa.Schema] = {
    # derived lanes
    "delivery_evidence": DELIVERY_SCHEMA,
    "transporter_evidence": TRANSPORTER_SCHEMA,
    "exposure_evidence": EXPOSURE_SCHEMA,
    "safety_evidence": SAFETY_SCHEMA,
    "nebpi_decisions": NEBPI_DECISION_SCHEMA,
    "nebpi_criteria": NEBPI_CRITERIA_SCHEMA,
    # the canonical input bundle every derived lane is reconstructable from
    "contexts": CONTEXT_SCHEMA,
    "drug_forms": DRUG_FORM_SCHEMA,
    "property_evidence": PROPERTY_SCHEMA,
    "potency_evidence": POTENCY_SCHEMA,
    "potency_context_links": POTENCY_CONTEXT_LINK_SCHEMA,
    "delivery_assignments": DELIVERY_ASSIGNMENT_SCHEMA,
    "nebpi_observations": NEBPI_OBSERVATION_SCHEMA,
    "search_manifests": SEARCH_MANIFEST_SCHEMA,
    "source_catalog": SOURCE_CATALOG_SCHEMA,
}

# The key each table is sorted by. Row order is part of the contract, so every key here is
# TOTAL: it identifies at most one row. A partial key (property_evidence used to sort on
# candidate/property/calculator, which two agreeing rows share) leaves the byte order of the
# parquet up to the input order, and the content hash with it.
SORT_KEYS_V1: dict[str, tuple[str, ...]] = {
    "delivery_evidence": ("candidate_id", "context_id"),
    "transporter_evidence": ("observation_id",),
    "exposure_evidence": ("measurement_id", "potency_id"),
    "safety_evidence": ("evidence_id",),
    "nebpi_decisions": ("candidate_id", "context_id"),
    "nebpi_criteria": ("candidate_id", "context_id", "criterion_id"),
    "contexts": ("context_id",),
    "drug_forms": ("candidate_id",),
    "property_evidence": ("property_record_id",),
    "potency_evidence": ("potency_id",),
    "potency_context_links": ("link_id",),
    "delivery_assignments": ("assignment_id",),
    "nebpi_observations": ("observation_id",),
    "search_manifests": ("search_id",),
    "source_catalog": ("source_record_id",),
}


def normalize_rows(table_name: str, rows: list[dict[str, Any]],
                   version: ContractVersion = ContractVersion.V1) -> list[dict[str, Any]]:
    """Project every row onto the declared columns, in declared order, sorted.

    The sort key must actually be a key: two rows sharing it would make the emitted byte
    order depend on the order they were handed in, which is exactly how one
    `scorecard_set_id` came to have two sets of artifact hashes.
    """
    schema = table_schemas(version)[table_name]
    names = schema.names
    out: list[dict[str, Any]] = []
    for r in rows:
        unknown = set(r) - set(names)
        if unknown:
            raise ValueError(f"{table_name}: unknown columns {sorted(unknown)}")
        out.append({n: r.get(n) for n in names})
    keys = sort_keys(version)[table_name]

    def sort_key(d: dict[str, Any]) -> tuple[str, ...]:
        return tuple(("" if d.get(k) is None else str(d[k])) for k in keys)

    seen: dict[tuple[str, ...], int] = {}
    for i, d in enumerate(out):
        k = sort_key(d)
        if k in seen:
            raise ValueError(
                f"{table_name}: rows {seen[k]} and {i} share sort key {keys}={k}. The sort "
                "key must identify at most one row, or the emitted row order — and the "
                "content hash taken over it — would depend on the input order."
            )
        seen[k] = i

    out.sort(key=sort_key)
    return out


def write_table(table_name: str, rows: list[dict[str, Any]], out_path: str,
                version: ContractVersion = ContractVersion.V1) -> dict[str, Any]:
    """Write one parquet table and describe it for the manifest."""
    schema = table_schemas(version)[table_name]
    norm = normalize_rows(table_name, rows, version)
    arrays = [
        pa.array([r[name] for r in norm], type=field.type)
        for name, field in zip(schema.names, schema)
    ]
    table = pa.Table.from_arrays(arrays, schema=schema)
    pq.write_table(table, out_path, compression="snappy", version="2.6", write_statistics=False)
    return {
        "filename": os.path.basename(out_path),
        "table": table_name,
        "rows": len(norm),
        "columns": list(schema.names),
        "dtypes": [str(f.type) for f in schema],
        "sort_key": list(sort_keys(version)[table_name]),
        "content_sha256": content_sha256(norm),
        "file_sha256": sha256_file(out_path),
    }


# --------------------------------------------------------------------------- contract v2
# v1 above is FROZEN: a release emitted before v2 existed must still verify, and its parquet
# must still have exactly the columns it had. So v2 is built HERE, by APPENDING to the v1
# schemas -- never by editing them. The v1 column tuple is therefore a strict prefix of the v2
# one, which is what makes "a v1 row is exactly a v1 row" a structural fact rather than a
# promise.

_V2_EXTRA_FIELDS: dict[str, list[tuple[str, Any]]] = {
    "potency_evidence": [
        # What the source SAID about the magnitude. "MEC > 500 nM" is not "MEC = 500 nM".
        ("relation", _STR),
        ("assay_activity_id", _STR), ("assay_assay_id", _STR), ("assay_target_id", _STR),
        ("assay_document_id", _STR), ("assay_type", _STR), ("assay_description", _STR),
        ("assay_experimental_system", _STR), ("assay_target_organism", _STR),
        ("assay_target_uniprot_accession", _STR), ("assay_confidence_score", pa.int64()),
        ("assay_validity_comment", _STR),
    ],
    "exposure_evidence": [
        ("pk_metric", _STR), ("pk_statistic", _STR), ("pk_sample_size", pa.int64()),
        ("pk_variability_kind", _STR), ("pk_variability_source_string", _STR),
        ("pk_variability_units", _STR),
        ("sampling_method", _STR), ("sample_location", _STR), ("time_relative_to_dose", _STR),
        ("analytical_method", _STR), ("steady_state", _BOOL),
        ("residual_blood_correction", _STR), ("microdialysis_recovery_state", _STR),
        ("microdialysis_recovery_source_string", _STR), ("microdialysis_recovery_method", _STR),
        ("co_medications", _LIST_STR), ("assay_method", _STR),
        ("paired_plasma_measurement_id", _STR),
        ("binding_state_basis", _STR), ("unbound_from_measurement_id", _STR),
        ("unbound_fraction_unbound_id", _STR), ("unbound_transform", _STR),
        ("kp_basis", _STR), ("kp_value_source_string", _STR),
        ("kp_derivation_transform", _STR), ("kp_input_measurement_ids", _LIST_STR),
        ("kp_fraction_unbound_ids", _LIST_STR),
        ("kp_uu_basis", _STR), ("kp_uu_value_source_string", _STR),
        ("kp_uu_derivation_transform", _STR), ("kp_uu_input_measurement_ids", _LIST_STR),
        ("kp_uu_fraction_unbound_ids", _LIST_STR),
    ],
    "safety_evidence": [
        # ACQUISITION's organ-system evidence shape, field for field. Never inferred.
        ("organ_system", _STR), ("organ_system_value_kind", _STR),
        ("organ_system_evidence_state", _STR), ("organ_system_source_key", _STR),
        ("organ_system_source_record_id", _STR), ("organ_system_setid", _STR),
        ("organ_system_label_version", _STR), ("organ_system_raw_response_sha256", _STR),
        ("organ_system_section_code", _STR), ("organ_system_subsection_code", _STR),
        ("organ_system_code_system", _STR), ("organ_system_locator", _STR),
        ("organ_system_extraction_transform", _STR), ("organ_system_reason", _STR),
    ],
}

# An fu is an OBSERVATION -- species, method, concentration dependence, a source of its own --
# so it is a table, not a field buried inside a concentration. Kp,uu rests on two of them.
FRACTION_UNBOUND_SCHEMA = pa.schema([
    ("fraction_unbound_id", _STR), ("candidate_id", _STR), ("active_moiety_id", _STR),
    ("matrix", _STR), ("value_source_string", _STR), ("method", _STR), ("species", _STR),
    ("concentration_dependence", _STR),
    ("source_record_id", _STR), ("source_url", _STR), ("access_date", _STR),
    ("release_version", _STR), ("raw_response_sha256", _STR), ("extraction_transform", _STR),
])

# What a fetch must be able to show before its bytes count: the canonical query, the UTC access
# time, the HTTP status, the terms URL, the adapter build, and how a single record was SELECTED
# among the candidates the query matched.
SOURCE_ACQUISITION_SCHEMA = pa.schema([
    ("acquisition_id", _STR), ("source_record_id", _STR), ("request_url", _STR),
    ("canonical_query", _STR), ("accessed_at_utc", _STR), ("http_status", pa.int64()),
    ("raw_media_type", _STR), ("response_headers_json", _STR),
    ("release_or_last_updated", _STR), ("license_or_terms_url", _STR),
    ("license_exception_note", _STR), ("raw_bytes", pa.int64()), ("raw_sha256", _STR),
    ("content_sha256", _STR), ("content_hash_rule", _STR), ("extraction_transform", _STR),
    ("adapter_id", _STR), ("adapter_code_sha256", _STR), ("review_status", _STR),
    ("observation_state", _STR), ("search_id", _STR), ("conflict_note", _STR),
    ("not_applicable_reason", _STR),
    ("selection_disposition", _STR), ("selection_pin", _STR),
    ("match_total_reported", pa.int64()), ("records_returned", pa.int64()),
    ("result_set_complete", _BOOL),
])

_V2_ONLY_SCHEMAS = {
    "fraction_unbound": FRACTION_UNBOUND_SCHEMA,
    "source_acquisition": SOURCE_ACQUISITION_SCHEMA,
}


def _extend(schema: "pa.Schema", extras: list[tuple[str, Any]]) -> "pa.Schema":
    return pa.schema(list(schema) + [pa.field(n, t) for n, t in extras])


TABLE_SCHEMAS_V2 = {
    **{name: (_extend(sch, _V2_EXTRA_FIELDS[name]) if name in _V2_EXTRA_FIELDS else sch)
       for name, sch in TABLE_SCHEMAS_V1.items()},
    **_V2_ONLY_SCHEMAS,
}

SORT_KEYS_V2 = {
    **SORT_KEYS_V1,
    "fraction_unbound": ("fraction_unbound_id",),
    "source_acquisition": ("acquisition_id",),
}

TABLE_SCHEMAS: dict[ContractVersion, dict[str, Any]] = {
    ContractVersion.V1: TABLE_SCHEMAS_V1,
    ContractVersion.V2: TABLE_SCHEMAS_V2,
}

SORT_KEYS: dict[ContractVersion, dict[str, tuple[str, ...]]] = {
    ContractVersion.V1: SORT_KEYS_V1,
    ContractVersion.V2: SORT_KEYS_V2,
}


def table_schemas(version: ContractVersion) -> dict[str, Any]:
    return TABLE_SCHEMAS[version]


def sort_keys(version: ContractVersion) -> dict[str, tuple[str, ...]]:
    return SORT_KEYS[version]
