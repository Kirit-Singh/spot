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

# --------------------------------------------------------------------- input columns
# The FULL row of the consumed record: every scientifically meaningful field, including the
# complete provenance binding (source id, url, access date, release, response hash, transform).
# `verifier/inputs.py` restates this tuple-for-tuple; a drift between them fails a test.

INPUT_COLUMNS: dict[str, tuple[str, ...]] = {
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
        "labeled_section_code", "labeled_section_name", "code_system", "searched_sources",
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

# ------------------------------------------------------------------- derived columns
# A pure function of the bound inputs + the method + the code — all three of which are in the
# scorecard_set_id. They are therefore RECONSTRUCTED by the independent verifier rather than
# hashed into identity: a tampered derived column contradicts the rebuild and fails.

DERIVED_COLUMNS: dict[str, tuple[str, ...]] = {
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


def all_columns(table: str) -> tuple[str, ...]:
    return INPUT_COLUMNS[table] + DERIVED_COLUMNS[table]


def project(table: str, row: dict[str, Any]) -> dict[str, Any]:
    """The bound (identity-bearing) part of one emitted row."""
    return {c: row.get(c) for c in INPUT_COLUMNS[table]}


# ------------------------------------------------------------------- the input rows


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


def evidence_input_rows(inputs: Any) -> dict[str, list[dict[str, Any]]]:
    """Every consumed evidence-input row, as the exact dict the parquet must carry."""
    from .delivery_reduce import assignment_content

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
             "evidence_type": p.evidence_type.value, **_prov(p.provenance)}
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
             "evidence_type": m.evidence_type.value, **_prov(m.provenance)}
            for m in inputs.exposures
        ],
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
             "searched_sources": list(s.searched_sources), "search_id": s.search_id,
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

    for table, table_rows in rows.items():
        expected = set(INPUT_COLUMNS[table])
        for r in table_rows:
            if set(r) != expected:
                raise ValueError(
                    f"{table}: the built input row does not carry exactly the declared input "
                    f"columns (missing={sorted(expected - set(r))} "
                    f"extra={sorted(set(r) - expected)}). An unclassified field is an unbound "
                    "field."
                )
    return rows
