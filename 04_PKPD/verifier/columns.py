"""The columns the reconstruction reads, and the delivery fields it reproduces.

Split out of `checks.py` to keep it under the repo's 500-line rule. Declared here so a release
from a different Stage-4 version is reported as UNVERIFIABLE rather than crashing the verifier
on a missing column — "I could not check this" and "I checked this and it passed" are not the
same answer, and only one of them is safe to act on.
"""

from __future__ import annotations

# The columns reconstruction actually reads. Declared here so a release from a different
# Stage-4 version is reported as unverifiable rather than crashing the verifier.
REQUIRED_COLUMNS_V1: dict[str, tuple[str, ...]] = {
    "contexts": ("context_id", "candidate_id", "active_moiety_id", "route", "formulation",
                 "dose", "schedule", "tumor_context"),
    "drug_forms": ("candidate_id", "namespace", "direction_compatibility"),
    "property_evidence": ("property_record_id", "candidate_id", "property_id",
                          "value_source_string", "units", "calculator_id", "accepted",
                          "source_record_id", "raw_response_sha256"),
    "potency_evidence": ("potency_id", "candidate_id", "active_moiety_id", "metric",
                         "value_source_string", "units", "binding_state",
                         "biological_context", "source_record_id", "raw_response_sha256"),
    # Every field the source binding is checked on. A link is the only way a potency from
    # one tumour context may be used in another, so it rests on acquired bytes like any
    # other evidence row.
    "potency_context_links": ("link_id", "potency_id", "tumor_context",
                              "source_record_id", "raw_response_sha256"),
    # Every field the delivery reducer takes identity from. Without these the verifier could
    # only re-read the generator's reduced answer, which is not a check.
    "delivery_assignments": ("assignment_id", "candidate_id", "context_id", "requirement",
                             "basis", "assigned_by", "rule_id", "rule_version", "rationale",
                             "evidence_source_record_id", "evidence_source_url",
                             "evidence_access_date", "evidence_release_version",
                             "evidence_sha256", "evidence_extraction_transform"),
    "search_manifests": ("search_id", "source", "endpoint", "query_canonical",
                         "search_scope", "executed_date", "n_results", "response_sha256",
                         "source_record_id"),
    "exposure_evidence": ("measurement_id", "candidate_id", "active_moiety_id", "context_id",
                          "matrix", "enhancement_context", "binding_state",
                          "detection_status", "concentration_source_string",
                          "concentration_units", "quantitation_limit_kind",
                          "quantitation_limit_source_string", "quantitation_limit_units",
                          "margin_status", "margin_canonical_decimal",
                          "margin_reason_code"),
    # Every field the reducer takes identity from. A release that omits one of them cannot
    # be reduced the way the generator reduced it, and is unverifiable rather than passing.
    "nebpi_observations": ("observation_id", "candidate_id", "context_id", "criterion_id",
                           "state", "assessment_adequate", "adequacy_rationale",
                           "measurement_id", "potency_id", "evidence_type",
                           "source_record_id", "source_url", "access_date",
                           "release_version", "raw_response_sha256", "extraction_transform"),
    "nebpi_criteria": ("candidate_id", "context_id", "criterion_id", "status", "importance",
                       "in_part_i_table", "can_satisfy_part_ii_branch",
                       "carried_the_assigned_class", "evidence_lane_consumed",
                       "requires_potency_context", "n_observations", "observation_ids",
                       "source_verbatim"),
    "nebpi_decisions": ("candidate_id", "context_id", "nebpi_status", "nebpi_class",
                        "derived_pk_level", "pd_state", "radiographic_state",
                        "pk_censored_bound_kind", "pk_censored_bound_below_mec",
                        "satisfied_branches"),
    "safety_evidence": ("evidence_id", "candidate_id", "evidence_state", "finding_text",
                        "search_id"),
    "source_catalog": ("source_record_id", "acquisition_status", "raw_sha256"),
    "delivery_evidence": ("candidate_id", "context_id", "delivery_requirement",
                          "nebpi_primary_gate", "reason_code", "assignment_id",
                          "conflicting_assignment_ids", "evidence_source_record_id",
                          "evidence_sha256"),
}

# Every delivery_evidence field the independent reducer reproduces. The generator's reduced
# answer is the thing being checked, so every one of them must agree.
DELIVERY_REBUILT_FIELDS = (
    "delivery_requirement", "nebpi_primary_gate", "reason_code", "downgraded_from",
    "assignment_id", "evidence_source_record_id", "evidence_sha256",
)


# v2 reconstruction reads more, because v2 rows SAY more. A v1 release is not asked for any of
# it: demanding a `relation` column of a release written before that column existed is how a
# historical artifact becomes "unverifiable" -- which is not the same answer as "wrong", and
# only one of the two is safe to act on.
REQUIRED_COLUMNS_V2: dict[str, tuple[str, ...]] = {
    **REQUIRED_COLUMNS_V1,
    "potency_evidence": REQUIRED_COLUMNS_V1["potency_evidence"] + ("relation",),
    "fraction_unbound": ("fraction_unbound_id", "candidate_id", "active_moiety_id", "matrix",
                         "value_source_string", "source_record_id", "raw_response_sha256"),
    "source_acquisition": ("acquisition_id", "source_record_id", "canonical_query",
                           "accessed_at_utc", "observation_state", "adapter_code_sha256",
                           "review_status", "selection_uniqueness"),
}

REQUIRED_COLUMNS = {"v1": REQUIRED_COLUMNS_V1, "v2": REQUIRED_COLUMNS_V2}


def required_columns(version: str = "v1") -> dict[str, tuple[str, ...]]:
    return REQUIRED_COLUMNS[version]
