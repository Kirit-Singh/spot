"""Flattening a v2 sub-record into the bound columns of an emitted row.

Split out of `evidence_inputs.py` for the 500-line rule. Every helper here answers the same
question the same way: a v1 row has no v2 sub-record, so every v2 cell is None -- the honest
representation of "this row never carried a PK metric", not a default that invents one.
"""

from __future__ import annotations

from typing import Any

from .canonical import canonical_json

# W8's AcquisitionRecord, minus `response_headers` (carried as canonical JSON, below).
_ACQ_FIELDS = (
    "acquisition_record_id", "source_key", "source_name", "source_type", "origin",
    "stable_record_id", "url", "canonical_query", "canonical_query_sha256", "accessed_at_utc",
    "access_date", "http_status", "raw_media_type", "release_or_last_updated", "license",
    "license_or_terms_url", "license_status", "redistribution", "raw_bytes", "raw_sha256",
    "content_sha256", "content_hash_rule", "cache_relpath", "extraction_transform",
    "adapter_code_sha256", "review_status", "evidence_state", "stage3_source_record_id", "note",
)


def _unbound(m: Any) -> dict[str, Any]:
    """Was the free concentration measured, or calculated from a total and an fu?"""
    d = m.unbound_derivation
    return {
        "binding_state_basis": m.binding_state_basis,
        "unbound_from_measurement_id": d.from_measurement_id if d else None,
        "unbound_fraction_unbound_id": d.fraction_unbound_id if d else None,
        "unbound_transform": d.transform if d else None,
    }


def _ratio(prefix: str, r: Any) -> dict[str, Any]:
    """A Kp/Kp,uu, flattened -- and `basis` says whether the SOURCE reported it or someone
    worked it out. A derived ratio carries the transform and the rows it was derived from."""
    return {
        f"{prefix}_basis": r.basis if r else None,
        f"{prefix}_value_source_string": r.value_source_string if r else None,
        f"{prefix}_derivation_transform": r.derivation_transform if r else None,
        f"{prefix}_input_measurement_ids": list(r.input_measurement_ids) if r else [],
        f"{prefix}_fraction_unbound_ids": list(r.fraction_unbound_ids) if r else [],
    }


def _acquisition_row(a: Any) -> dict[str, Any]:
    """W8's AcquisitionRecord, flattened.

    `response_headers` is a verbatim capture of a selected header set, so it is carried as ONE
    canonical JSON string rather than exploded into columns: it is opaque provenance, not a
    scientific field anything reads. Canonical (sorted keys, no whitespace) so the digest is
    stable across re-serialisation.
    """
    row = {f: getattr(a, f) for f in _ACQ_FIELDS}
    row["response_headers_json"] = canonical_json(dict(sorted(a.response_headers.items())))
    return row


def _prov(p: Any) -> dict[str, Any]:
    """The complete provenance binding, flat. Never a subset — that was the bug."""
    return {
        "source_record_id": p.source_record_id,
        "source_url": p.source_url,
        "access_date": p.access_date,
        "release_version": p.release_version,
        "raw_response_sha256": p.raw_response_sha256,
        "extraction_transform": p.extraction_transform,
    }


def _empty_prov() -> dict[str, Any]:
    return {k: None for k in ("source_record_id", "source_url", "access_date",
                              "release_version", "raw_response_sha256",
                              "extraction_transform")}


# The v2 assay binding, flattened. A v1 row has no binding and every cell is None — which is
# the honest representation of "this row never carried an activity id", not a default.
_ASSAY_FIELDS = (
    ("assay_activity_id", "activity_id"),
    ("assay_assay_id", "assay_id"),
    ("assay_target_id", "target_id"),
    ("assay_document_id", "document_id"),
    ("assay_type", "assay_type"),
    ("assay_description", "assay_description"),
    ("assay_experimental_system", "experimental_system"),
    ("assay_target_organism", "target_organism"),
    ("assay_target_uniprot_accession", "target_uniprot_accession"),
    ("assay_confidence_score", "confidence_score"),
    ("assay_validity_comment", "validity_comment"),
)


def _assay(b: Any) -> dict[str, Any]:
    return {col: (getattr(b, attr) if b is not None else None) for col, attr in _ASSAY_FIELDS}


_PK_FIELDS = (
    ("pk_metric", "pk_metric"),
    ("pk_statistic", "statistic"),
    ("pk_sample_size", "sample_size"),
    ("pk_variability_kind", "variability_kind"),
    ("pk_variability_source_string", "variability_source_string"),
    ("pk_variability_units", "variability_units"),
)

_SAMPLING_FIELDS = (
    ("sampling_method", "sampling_method"),
    ("sample_location", "sample_location"),
    ("time_relative_to_dose", "time_relative_to_dose"),
    ("analytical_method", "analytical_method"),
    ("steady_state", "steady_state"),
    ("residual_blood_correction", "residual_blood_correction"),
    ("microdialysis_recovery_state", "microdialysis_recovery_state"),
    ("microdialysis_recovery_source_string", "microdialysis_recovery_source_string"),
    ("microdialysis_recovery_method", "microdialysis_recovery_method"),
)


def _enum_value(v: Any) -> Any:
    """Enums enter canonical content as their declared string, never as `PkMetric.CMAX`."""
    return getattr(v, "value", v)


def _flatten(obj: Any, fields: tuple[tuple[str, str], ...]) -> dict[str, Any]:
    """A v1 row has no v2 sub-record, so every cell is None — the honest representation of
    'this row never carried a PK metric', not a default that invents one."""
    return {col: (_enum_value(getattr(obj, attr)) if obj is not None else None)
            for col, attr in fields}


_ORGAN_FIELDS = (
    ("organ_system", "organ_system"),
    ("organ_system_value_kind", "value_kind"),
    ("organ_system_evidence_state", "evidence_state"),
    ("organ_system_source_key", "source_key"),
    ("organ_system_source_record_id", "source_record_id"),
    ("organ_system_setid", "setid"),
    ("organ_system_label_version", "label_version"),
    ("organ_system_raw_response_sha256", "raw_response_sha256"),
    ("organ_system_section_code", "section_code"),
    ("organ_system_subsection_code", "subsection_code"),
    ("organ_system_code_system", "code_system"),
    ("organ_system_locator", "locator"),
    ("organ_system_extraction_transform", "extraction_transform"),
    ("organ_system_reason", "reason"),
)


def _organ(e: Any) -> dict[str, Any]:
    """Acquisition's organ-system evidence, flattened -- INCLUDING the absence case, which
    still says where we looked and at which bytes. That is what stops "unspecified" from being
    read as "never checked", and it is why the reason travels with the value."""
    return {col: (getattr(e, attr) if e is not None else None) for col, attr in _ORGAN_FIELDS}


def _pk_detail(d: Any) -> dict[str, Any]:
    return _flatten(d, _PK_FIELDS)


def _sampling(s: Any) -> dict[str, Any]:
    return _flatten(s, _SAMPLING_FIELDS)
