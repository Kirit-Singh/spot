"""The v2 parquet schemas — built by APPENDING to the frozen v1 ones.

Split out of `tables.py` for the 500-line rule. v1 is never edited here: the v2 schemas are the
v1 schemas plus declared extra fields, which is what makes the v1 column tuple a strict PREFIX of
the v2 one. "A v1 row is exactly a v1 row" is therefore a structural fact rather than a promise.
"""

from __future__ import annotations

from typing import Any

import pyarrow as pa

from .contract_version import ContractVersion
from .tables import SORT_KEYS_V1, TABLE_SCHEMAS_V1

# Declared here rather than imported back out of `tables`: this module is imported FROM
# `tables` (to re-export), so reaching back into it for a type alias is a cycle that only
# happens to work.
_STR = pa.string()
_BOOL = pa.bool_()
_LIST_STR = pa.list_(pa.field("element", pa.string()))


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
    ("acquisition_record_id", _STR), ("source_key", _STR), ("source_name", _STR),
    ("source_type", _STR), ("origin", _STR), ("stable_record_id", _STR), ("url", _STR),
    ("canonical_query", _STR), ("canonical_query_sha256", _STR), ("accessed_at_utc", _STR),
    ("access_date", _STR), ("http_status", pa.int64()), ("raw_media_type", _STR),
    ("response_headers_json", _STR), ("release_or_last_updated", _STR), ("license", _STR),
    ("license_or_terms_url", _STR), ("license_status", _STR), ("redistribution", _STR),
    ("raw_bytes", pa.int64()), ("raw_sha256", _STR), ("content_sha256", _STR),
    ("content_hash_rule", _STR), ("cache_relpath", _STR), ("extraction_transform", _STR),
    ("adapter_code_sha256", _STR), ("review_status", _STR), ("evidence_state", _STR),
    ("stage3_source_record_id", _STR), ("note", _STR),
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
    "source_acquisition": ("acquisition_record_id",),
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
