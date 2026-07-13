"""The canonical full row of every consumed evidence input. One declaration, three users.

The re-audit's finding: `verify.py` claimed the emitted tables "are exactly the inputs", but
compared only a hand-written subset of columns. A resealed release could therefore rewrite a
negative search's `search_scope`, `source`, `executed_date` and `extraction_transform` — or a
potency-context link's `access_date` and `extraction_transform` — keep `scorecard_set_id`, and
pass BOTH verifiers. `no_evidence_found` means something different when the searched scope
changes, so that release told a different scientific story under one identity.

The class of bug is the hand-maintained projection, not the four columns it forgot. So the
column set is declared ONCE, here, and everything reads it:

  1. `ids.evidence_inputs_digest` hashes these rows -> `evidence_inputs_sha256` -> the
     `scorecard_set_id`. Change any bound column and the identity moves.
  2. `emit` writes these rows (plus each table's declared DERIVED columns) to parquet, and
     asserts the emitted columns are exactly INPUT | DERIVED — so a new column cannot appear
     without being classified as one or the other.
  3. `verifier/inputs.py` RESTATES this column set independently, reads the rows back out of
     the parquet, recomputes the digest, and re-derives the `scorecard_set_id` from it. The
     generator's declared digest is the thing being checked, never an input to the check.

EXPLANATORY columns (below) are the ONLY fields excluded from identity. Each is a prose
restatement of a machine-checked field sitting next to it, so tampering with one cannot change
any machine-consumable claim while the claim itself stays verified. Nothing else is exempt.
"""

from __future__ import annotations

from typing import Any

from .contract_v1_frozen import DERIVED_COLUMNS_V1, INPUT_COLUMNS_V1
from .contract_version import ContractVersion
from .row_flatten import (
    _acquisition_row,
    _assay,
    _empty_prov,
    _organ,
    _pk_detail,
    _prov,
    _ratio,
    _sampling,
    _unbound,
)

# --------------------------------------------------------------------- input columns
# The FULL row of the consumed record: every scientifically meaningful field, including the
# complete provenance binding (source id, url, access date, release, response hash, transform).
# `verifier/inputs.py` restates this tuple-for-tuple; a drift between them fails a test.

# v1 is FROZEN and lives in `contract_v1_frozen.py`. v2 is expressed here as an ADDITION to it,
# never as an edit of it: the v2 columns are appended AFTER the v1 columns, so the v1 column
# tuple is a strict prefix of the v2 one and a v1 row is exactly a v1 row.

# What v2 ADDS to a table that already existed in v1.
V2_ADDED_COLUMNS: dict[str, tuple[str, ...]] = {
    "potency_evidence": (
        # What the source SAID about the magnitude, and the assay record it said it in.
        "relation", "assay_activity_id", "assay_assay_id", "assay_target_id",
        "assay_document_id", "assay_type", "assay_description",
        "assay_experimental_system", "assay_target_organism",
        "assay_target_uniprot_accession", "assay_confidence_score",
        "assay_validity_comment",
    ),
    "exposure_evidence": (
        # WHICH exposure, over how many subjects, with what spread.
        "pk_metric", "pk_statistic", "pk_sample_size", "pk_variability_kind",
        "pk_variability_source_string", "pk_variability_units",
        # How/where/when it was sampled, and what was done to it afterwards.
        "sampling_method", "sample_location", "time_relative_to_dose", "analytical_method",
        "steady_state", "residual_blood_correction", "microdialysis_recovery_state",
        "microdialysis_recovery_source_string", "microdialysis_recovery_method",
        "co_medications", "assay_method", "paired_plasma_measurement_id",
        # Measured free, or C_total * fu? The second inherits every assumption in the fu.
        "binding_state_basis", "unbound_from_measurement_id", "unbound_fraction_unbound_id",
        "unbound_transform",
        # Reported by the source, or worked out by someone?
        "kp_basis", "kp_value_source_string", "kp_derivation_transform",
        "kp_input_measurement_ids", "kp_fraction_unbound_ids",
        "kp_uu_basis", "kp_uu_value_source_string", "kp_uu_derivation_transform",
        "kp_uu_input_measurement_ids", "kp_uu_fraction_unbound_ids",
    ),
    "safety_evidence": (
        # ACQUISITION's own organ-system evidence shape (`organ_system.py`), field for field:
        # the value verbatim, whether it is a controlled term or the source's own, whether it
        # was observed at all, and the exact record + locator it was read from. `unspecified` +
        # `not_evaluated` is what an absent source field produces -- and it still says WHERE we
        # looked and at WHICH bytes, so "unspecified" can never be read as "never checked".
        "organ_system", "organ_system_value_kind", "organ_system_evidence_state",
        "organ_system_source_key", "organ_system_source_record_id", "organ_system_setid",
        "organ_system_label_version", "organ_system_raw_response_sha256",
        "organ_system_section_code", "organ_system_subsection_code",
        "organ_system_code_system", "organ_system_locator",
        "organ_system_extraction_transform", "organ_system_reason",
    ),
}

# Tables that exist ONLY in v2. A v1 release does not carry an empty one — it has no such table.
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

INPUT_COLUMNS: dict[ContractVersion, dict[str, tuple[str, ...]]] = {
    ContractVersion.V1: INPUT_COLUMNS_V1,
    ContractVersion.V2: INPUT_COLUMNS_V2,
}


def input_columns(version: ContractVersion) -> dict[str, tuple[str, ...]]:
    return INPUT_COLUMNS[version]


# ------------------------------------------------------------------- derived columns
# A pure function of the bound inputs + the method + the code — all three of which are in the
# scorecard_set_id. They are therefore RECONSTRUCTED by the independent verifier rather than
# hashed into identity: a tampered derived column contradicts the rebuild and fails.

DERIVED_COLUMNS_V2: dict[str, tuple[str, ...]] = {
    "contexts": (),
    "property_evidence": (
        "value_canonical_decimal", "value_in_base_units", "base_units", "unit_conversion",
        "method_conformance", "component_score_t0", "accepted", "rejection_reason_code",
    ),
    "potency_evidence": ("value_canonical_decimal",),
    "potency_context_links": (),
    "transporter_evidence": (),
    "exposure_evidence": (
        "concentration_canonical_decimal", "quantitation_limit_canonical_decimal",
        "margin_status", "margin", "margin_canonical_decimal", "margin_reason_code",
        "harmonized_units", "exposure_harmonized", "potency_harmonized",
        "potency_id", "potency_context_link_id", "margin_transform", "caveats",
    ),
    "delivery_assignments": (),
    "nebpi_observations": (),
    "safety_evidence": ("renders_as_safe", "evidence_state_display"),
    "search_manifests": (),
    "fraction_unbound": (),
    "source_acquisition": (),
}

# --------------------------------------------------------------- explanatory columns
# EMPTY, and it stays empty.
#
# `property_evidence.rejection_reason` and `exposure_evidence.margin_reason` used to live here:
# free prose, hashed into nothing and reconstructed by nothing. The justification was that each
# sat beside a machine-readable code that WAS reconstructed. That justification does not hold.
# A neighbouring machine code does not license unbound prose — a resealed release could rewrite
# "refused: the calculator does not implement this quantity" into anything at all while the code
# beside it still read `disallowed_calculator`, and a human reading the table would believe the
# prose.
#
# Both columns are GONE from the parquet. The reason is carried by its typed code
# (`rejection_reason_code`, `margin_reason_code`), which the independent verifier reconstructs
# cell for cell. The human-readable sentence still exists in `scorecards.json`, where prose
# belongs; it is no longer duplicated into the machine-readable evidence table where nothing
# was checking it.
#
# Every cell of every emitted evidence table is now either bound into identity or reconstructed.
# There are no exemptions. If a future column cannot be one or the other, it does not belong in
# the table.
EXPLANATORY_COLUMNS: dict[str, tuple[str, ...]] = {}


DERIVED_COLUMNS: dict[ContractVersion, dict[str, tuple[str, ...]]] = {
    ContractVersion.V1: DERIVED_COLUMNS_V1,
    ContractVersion.V2: DERIVED_COLUMNS_V2,
}


def derived_columns(version: ContractVersion) -> dict[str, tuple[str, ...]]:
    return DERIVED_COLUMNS[version]


def all_columns(table: str, version: ContractVersion = ContractVersion.V2) -> tuple[str, ...]:
    return input_columns(version)[table] + derived_columns(version)[table]


def project(table: str, row: dict[str, Any],
            version: ContractVersion = ContractVersion.V2) -> dict[str, Any]:
    """The bound (identity-bearing) part of one emitted row."""
    return {c: row.get(c) for c in input_columns(version)[table]}





def evidence_input_rows(inputs: Any,
                        version: ContractVersion | None = None
                        ) -> dict[str, list[dict[str, Any]]]:
    """Every consumed evidence-input row, as the exact dict the parquet must carry.

    The rows are built in their v2 shape and then PROJECTED onto the declared contract's column
    set. So a v1 bundle emits exactly the v1 columns — not the v1 columns plus a row of nulls,
    which would still be a v2 row and would still move the v1 digest — and the v2-only tables
    do not exist for it at all.
    """
    from .delivery_reduce import assignment_content

    version = version or getattr(inputs, "contract_version", None) or ContractVersion.V1

    rows: dict[str, list[dict[str, Any]]] = {
        "contexts": [
            {"context_id": c.context_id, "candidate_id": c.candidate_id,
             "active_moiety_id": c.active_moiety_id, "route": c.route,
             "formulation": c.formulation, "dose": c.dose, "schedule": c.schedule,
             "tumor_context": c.tumor_context, "population": c.population,
             "is_fixture": c.is_fixture}
            for c in inputs.contexts
        ],
        "property_evidence": [
            {"property_record_id": r.property_record_id, "candidate_id": r.candidate_id,
             "active_moiety_id": r.active_moiety_id, "property_id": r.property_id,
             "value_source_string": r.value_source_string, "units": r.units,
             "determination": r.determination, "calculator_id": r.calculator_id,
             "method": r.method, "software_version": r.software_version,
             "database_version": r.database_version, **_prov(r.provenance)}
            for r in inputs.properties
        ],
        "potency_evidence": [
            {"potency_id": p.potency_id, "candidate_id": p.candidate_id,
             "active_moiety_id": p.active_moiety_id, "metric": p.metric,
             "value_source_string": p.value_source_string, "units": p.units,
             "binding_state": p.binding_state, "assay": p.assay,
             "biological_context": p.biological_context,
             "evidence_type": p.evidence_type.value,
             "relation": p.relation.value, **_assay(p.assay_binding),
             **_prov(p.provenance)}
            for p in inputs.potencies
        ],
        "potency_context_links": [
            {"link_id": k.link_id, "potency_id": k.potency_id,
             "tumor_context": k.tumor_context, "rationale": k.rationale,
             **_prov(k.provenance)}
            for k in inputs.potency_context_links
        ],
        "transporter_evidence": [
            {"observation_id": o.observation_id, "candidate_id": o.candidate_id,
             "active_moiety_id": o.active_moiety_id, "transporter": o.transporter,
             "transporter_gene": o.transporter_gene, "interaction": o.interaction,
             "assay": o.assay, "species": o.species,
             "biological_system": o.biological_system, "concentration": o.concentration,
             "concentration_units": o.concentration_units,
             "result_metric": o.result_metric, "result_value": o.result_value,
             "result_units": o.result_units, "direction": o.direction,
             "evidence_type": o.evidence_type.value, **_prov(o.provenance)}
            for o in inputs.transporters
        ],
        "exposure_evidence": [
            {"measurement_id": m.measurement_id, "candidate_id": m.candidate_id,
             "active_moiety_id": m.active_moiety_id, "context_id": m.context_id,
             "formulation": m.formulation, "route": m.route, "dose": m.dose,
             "schedule": m.schedule, "species_population": m.species_population,
             "matrix": m.matrix, "enhancement_context": m.enhancement_context,
             "binding_state": m.binding_state,
             "concentration_source_string": m.concentration_source_string,
             "concentration_units": m.concentration_units,
             "detection_status": m.detection_status,
             "quantitation_limit_kind": m.quantitation_limit_kind,
             "quantitation_limit_source_string": m.quantitation_limit_source_string,
             "quantitation_limit_units": m.quantitation_limit_units,
             "timepoint": m.timepoint,
             "kp_reported_source_string": m.kp_reported_source_string,
             "kp_uu_brain_reported_source_string": m.kp_uu_brain_reported_source_string,
             "evidence_type": m.evidence_type.value,
             **_pk_detail(m.pk_detail), **_sampling(m.sampling),
             "co_medications": list(m.co_medications),
             "assay_method": m.assay_method,
             "paired_plasma_measurement_id": m.paired_plasma_measurement_id,
             **_unbound(m), **_ratio("kp", m.kp), **_ratio("kp_uu", m.kp_uu_brain),
             **_prov(m.provenance)}
            for m in inputs.exposures
        ],
        "fraction_unbound": [
            {"fraction_unbound_id": f.fraction_unbound_id, "candidate_id": f.candidate_id,
             "active_moiety_id": f.active_moiety_id, "matrix": f.matrix,
             "value_source_string": f.value_source_string, "method": f.method,
             "species": f.species,
             "concentration_dependence": f.concentration_dependence,
             **_prov(f.provenance)}
            for f in getattr(inputs, "fraction_unbound", [])
        ],
        "source_acquisition": [_acquisition_row(a)
                               for a in getattr(inputs, "acquisitions", [])],
        "delivery_assignments": [assignment_content(a) for a in inputs.delivery_assignments],
        "nebpi_observations": [
            {"observation_id": o.observation_id, "candidate_id": o.candidate_id,
             "context_id": o.context_id, "criterion_id": o.criterion_id.value,
             "state": o.state.value, "assessment_adequate": o.assessment_adequate,
             "adequacy_rationale": o.adequacy_rationale,
             "measurement_id": o.measurement_id, "potency_id": o.potency_id,
             "evidence_type": o.evidence_type.value, **_prov(o.provenance)}
            for o in inputs.nebpi_observations
        ],
        "safety_evidence": [
            {"evidence_id": s.evidence_id, "candidate_id": s.candidate_id,
             "active_moiety_id": s.active_moiety_id,
             "evidence_state": s.evidence_state.value,
             "finding_type": s.finding_type.value if s.finding_type else None,
             "finding_text": s.finding_text,
             "gbm_scenario": s.gbm_scenario.value if s.gbm_scenario else None,
             "interaction_type": s.interaction_type.value if s.interaction_type else None,
             "label_source": s.label_identity.label_source if s.label_identity else None,
             "setid": s.label_identity.setid if s.label_identity else None,
             "application_number": (s.label_identity.application_number
                                    if s.label_identity else None),
             "product_identity": (s.label_identity.product_identity
                                  if s.label_identity else None),
             "label_version": s.label_identity.label_version if s.label_identity else None,
             "effective_date": (s.label_identity.effective_date
                                if s.label_identity else None),
             "labeled_section_code": (s.label_identity.labeled_section_code
                                      if s.label_identity else None),
             "labeled_section_name": (s.label_identity.labeled_section_name
                                      if s.label_identity else None),
             "code_system": s.label_identity.code_system if s.label_identity else None,
             "labeled_subsection_code": (s.label_identity.labeled_subsection_code
                                         if s.label_identity else None),
             "labeled_subsection_name": (s.label_identity.labeled_subsection_name
                                         if s.label_identity else None),
             "searched_sources": list(s.searched_sources), "search_id": s.search_id,
             **_organ(s.organ_system_evidence),
             **(_prov(s.provenance) if s.provenance else _empty_prov())}
            for s in inputs.safety_records
        ],
        "search_manifests": [
            {"search_id": s.search_id, "source": s.source, "endpoint": s.endpoint,
             "query_canonical": s.query_canonical, "search_scope": s.search_scope,
             "executed_date": s.executed_date, "source_release": s.source_release,
             "n_results": s.n_results,
             "source_record_id": s.provenance.source_record_id,
             "source_url": s.provenance.source_url,
             "access_date": s.provenance.access_date,
             "release_version": s.provenance.release_version,
             "response_sha256": s.provenance.raw_response_sha256,
             "extraction_transform": s.provenance.extraction_transform}
            for s in inputs.search_manifests
        ],
    }

    cols = input_columns(version)

    # Project onto the declared contract. A v1 release has no `relation` cell to be null.
    projected = {
        table: [{c: r.get(c) for c in cols[table]} for r in table_rows]
        for table, table_rows in rows.items() if table in cols
    }

    for table, table_rows in projected.items():
        expected = set(cols[table])
        for r in table_rows:
            if set(r) != expected:
                raise ValueError(
                    f"{table}: the built input row does not carry exactly the declared input "
                    f"columns (missing={sorted(expected - set(r))} "
                    f"extra={sorted(set(r) - expected)}). An unclassified field is an unbound "
                    "field."
                )
    missing_tables = sorted(set(cols) - set(projected))
    if missing_tables:
        raise ValueError(
            f"the {version.value} contract declares table(s) {missing_tables} that were never "
            "built. A declared table with no builder is a silently empty lane."
        )
    return projected
