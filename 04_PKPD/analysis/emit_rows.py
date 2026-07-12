"""Every parquet row the release carries, built from the pipeline result.

Split out of `emit.py`, which was doing three jobs at once (environment lock, row building,
document assembly) and had grown past the repo's 500-line rule. Nothing here decides anything:
each builder is a projection of what the engine already computed.

The pure-input tables ARE the canonical consumed rows, cell for cell (`evidence_inputs.py`).
The mixed tables are that row plus the table's declared DERIVED columns, and nothing else —
`assert_full_row_binding` refuses a column that is neither.
"""

from __future__ import annotations

from typing import Any

from .evidence_inputs import DERIVED_COLUMNS, evidence_input_rows
from .method_config import MethodBundle
from .pipeline import Stage4Inputs, Stage4Result
from .safety import render_evidence_state

# ------------------------------------------------------------------------ table rows


def _delivery_rows(result: Stage4Result, inputs: Stage4Inputs) -> list[dict[str, Any]]:
    moiety = {c.candidate_id: c.active_moiety.active_moiety_id for c in inputs.candidate_set.candidates}
    rows = []
    for cr in result.candidates:
        for d in cr.delivery:
            rows.append(
                {
                    "candidate_id": d.candidate_id,
                    "context_id": d.context_id,
                    "active_moiety_id": moiety[d.candidate_id],
                    "delivery_requirement": d.requirement,
                    "nebpi_primary_gate": d.nebpi_primary_gate,
                    "basis": d.basis,
                    "assigned_by": d.assigned_by,
                    "rule_id": d.rule_id,
                    "rule_version": d.rule_version,
                    "rationale": d.rationale,
                    "reason_code": d.reason_code,
                    "downgraded_from": d.downgraded_from,
                    "assignment_id": d.assignment_id,
                    "conflicting_assignment_ids": list(d.conflicting_assignment_ids),
                    "evidence_source_record_id": d.evidence_source_record_id,
                    "evidence_sha256": d.evidence_sha256,
                }
            )
    return rows


def _pure_input_rows(rows: dict[str, list[dict[str, Any]]], table: str) -> list[dict[str, Any]]:
    """A table whose every column is an input column IS the canonical input row."""
    assert not DERIVED_COLUMNS[table], f"{table} has derived columns"
    return rows[table]


def _exposure_rows(inputs: Stage4Inputs, result: Stage4Result) -> list[dict[str, Any]]:
    """The canonical input row + the margin the engine derived from it."""
    base = {r["measurement_id"]: r for r in evidence_input_rows(inputs)["exposure_evidence"]}
    rows = []
    for cr in result.candidates:
        for m, margin in cr.exposure:
            q = m.quantity
            qlimit = m.quantitation_limit
            rows.append({
                **base[m.measurement_id],
                "concentration_canonical_decimal": q.canonical_decimal if q else None,
                "quantitation_limit_canonical_decimal": (
                    qlimit.canonical_decimal if qlimit else None),
                "margin_status": margin.status,
                "margin": margin.margin,
                "margin_canonical_decimal": margin.margin_canonical_decimal,
                "margin_reason_code": margin.reason_code,
                "harmonized_units": margin.harmonized_units,
                "exposure_harmonized": margin.exposure_harmonized,
                "potency_harmonized": margin.potency_harmonized,
                "potency_id": margin.potency_id,
                "potency_context_link_id": margin.potency_context_link_id,
                "margin_transform": margin.transform,
                "caveats": margin.caveats,
            })
    return rows


# --- the canonical input bundle: everything a verifier needs to rebuild the lanes ------


def _drug_form_rows(inputs: Stage4Inputs, result: Stage4Result) -> list[dict[str, Any]]:
    elig = {cr.candidate_id: cr for cr in result.candidates}
    rows = []
    for c in inputs.candidate_set.candidates:
        m, ids = c.active_moiety, c.compound_ids
        cr = elig.get(c.candidate_id)
        rows.append({
            "candidate_id": c.candidate_id, "active_moiety_id": m.active_moiety_id,
            "active_moiety_name": m.active_moiety_name, "unii": m.unii,
            "inchikey": m.inchikey, "administered_form": m.administered_form,
            "administered_form_name": m.administered_form_name,
            "maps_to_active_moiety_id": m.maps_to_active_moiety_id,
            "mapping_source_record_id": m.mapping_source_record_id,
            "namespace": c.namespace.value,
            "chembl_id": ids.chembl_id, "pubchem_cid": ids.pubchem_cid,
            "drugbank_id": ids.drugbank_id, "rxcui": ids.rxcui,
            "target": c.target, "mechanism": c.mechanism,
            "direction_compatibility": c.direction_compatibility.value,
            "program_direction": c.program_direction,
            "drug_effect_direction": c.drug_effect_direction,
            "stage3_evidence_source_record_ids": list(c.stage3_evidence_source_record_ids),
            "production_eligible": cr.production_eligible if cr else False,
            "eligibility_reason_code": cr.eligibility_reason_code if cr else "not_evaluated",
        })
    return rows


def _property_rows(inputs: Stage4Inputs, result: Stage4Result) -> list[dict[str, Any]]:
    """Every property record — accepted AND rejected — as its canonical input row + what
    the engine derived from it.

    A property the engine refused (disallowed calculator, wrong unit, conflicting sources)
    is part of the evidence. It is emitted with its rejection reason rather than dropped,
    so a reviewer can see what was offered and why it was not used. The reason CODE is
    reconstructed by the independent verifier; the prose beside it is its enumerated twin.
    """
    scored: dict[str, dict[str, Any]] = {}
    for cr in result.candidates:
        for used in cr.cns_mpo.input_provenance:
            scored[used["property_record_id"]] = used

    rejected: dict[tuple[str, str], str] = {}
    for cid, sel in result.property_selections.items():
        for miss in sel.missing:
            rejected[(cid, miss.property_id)] = miss.reason_code

    base = {r["property_record_id"]: r
            for r in evidence_input_rows(inputs)["property_evidence"]}
    rows = []
    for r in inputs.properties:
        q = r.quantity
        entry = scored.get(r.property_record_id)
        code = rejected.get((r.candidate_id, r.property_id))
        rows.append({
            **base[r.property_record_id],
            "value_canonical_decimal": q.canonical_decimal,
            "value_in_base_units": float(q.in_base()),
            "base_units": q.base_unit(),
            "unit_conversion": q.conversion_transform(),
            "method_conformance": entry["method_conformance"] if entry else None,
            "component_score_t0": entry["component_score_t0"] if entry else None,
            "accepted": entry is not None,
            "rejection_reason_code": None if entry else code,
        })
    return rows



def _potency_rows(inputs: Stage4Inputs) -> list[dict[str, Any]]:
    """Canonical input row + the exact decimal the engine parsed the magnitude to."""
    rows = evidence_input_rows(inputs)["potency_evidence"]
    canonical = {p.potency_id: p.quantity.canonical_decimal for p in inputs.potencies}
    return [{**r, "value_canonical_decimal": canonical[r["potency_id"]]} for r in rows]



def _nebpi_decision_rows(result: Stage4Result) -> list[dict[str, Any]]:
    rows = []
    for cr in result.candidates:
        for n in cr.nebpi:
            d: dict[str, Any] = n.pk_derivation or {}
            rows.append({
                "candidate_id": n.candidate_id, "context_id": n.context_id,
                "nebpi_status": n.nebpi_status, "nebpi_class": n.nebpi_class,
                "nebpi_primary_gate": n.nebpi_primary_gate,
                "delivery_requirement": n.delivery_requirement,
                "derived_pk_level": d.get("derived_level"),
                "pk_measurement_id": d.get("measurement_id"),
                "pk_potency_id": d.get("potency_id"),
                "pk_margin_canonical_decimal": d.get("margin_canonical_decimal"),
                "pk_detection_status": d.get("detection_status"),
                "pk_censored_bound_kind": d.get("censored_bound_kind"),
                "pk_censored_bound_source_string": d.get("censored_bound_source_string"),
                "pk_censored_bound_canonical_decimal": d.get("censored_bound_canonical_decimal"),
                "pk_censored_bound_units": d.get("censored_bound_units"),
                "pk_censored_bound_over_mec_canonical_decimal": d.get(
                    "censored_bound_over_mec_canonical_decimal"),
                "pk_censored_bound_below_mec": d.get("censored_bound_below_mec"),
                "pk_transform": d.get("transform"),
                "pk_blocked_code": d.get("blocked_code"),
                "pd_state": n.criterion_states.get("pd_in_neb"),
                "radiographic_state": n.criterion_states.get("radiographic_response_in_neb"),
                "satisfied_branches": sorted(b.branch_id for b in n.branch_proof if b.satisfied),
                "reason_codes": list(n.reason_codes),
                "method_id": n.method_id, "method_version": n.method_version,
            })
    return rows


def _nebpi_criteria_rows(result: Stage4Result, method: MethodBundle) -> list[dict[str, Any]]:
    """One row per (candidate, context, CRITERION). NEBPI is not a scalar.

    A criterion with no qualifying observation reads `not_evaluated` — never a favourable
    state, and never silently absent from the table. The reader can see WHICH of the nine
    criteria were actually evaluated, which the class alone would hide.
    """
    spec = {c["criterion_id"]: c for c in method.nebpi["part_i_criteria"]}
    branch_criterion = {k: v for k, v in method.nebpi["part_ii_branch_criterion"].items()
                        if not k.startswith("_")}

    rows = []
    for cr in result.candidates:
        for n in cr.nebpi:
            # Which criteria actually carried the class that was ASSIGNED. A branch of some
            # OTHER class may well be satisfied (an `impermeable::no_relevant_pd` conjunct is
            # satisfied whenever the `insufficiently_permeable` one is) — that is not this
            # candidate's class and must not be reported as if it were.
            carried: set[str] = set()
            for b in n.branch_proof:
                if not b.satisfied or not n.nebpi_class:
                    continue
                token = b.branch_id.split("::", 1)[-1]
                owner = b.branch_id.split("::", 1)[0] if "::" in b.branch_id else None
                if owner is not None and owner != n.nebpi_class:
                    continue
                if owner is None and n.nebpi_class != "sufficiently_permeable":
                    continue
                crit = branch_criterion.get(token)
                if crit:
                    carried.add(crit)

            for cid, state in sorted(n.criterion_states.items()):
                sp = spec.get(cid, {})
                consumes = sp.get("consumes", {}) or {}
                obs_ids = sorted(n.criterion_observation_ids.get(cid, []))
                rows.append({
                    "candidate_id": n.candidate_id,
                    "context_id": n.context_id,
                    "criterion_id": cid,
                    "status": state,
                    "importance": sp.get("importance"),
                    "in_part_i_table": bool(sp.get("in_part_i_table")),
                    "can_satisfy_part_ii_branch": bool(sp.get("can_satisfy_part_ii_branch")),
                    "carried_the_assigned_class": cid in carried,
                    "evidence_lane_consumed": consumes.get("stage4_lane"),
                    "requires_potency_context": bool(consumes.get("requires_potency_context")),
                    "n_observations": len(obs_ids),
                    "observation_ids": obs_ids,
                    "source_verbatim": sp.get("source_verbatim"),
                    "method_id": n.method_id,
                })
    return rows


def _source_catalog_rows(inputs: Stage4Inputs) -> list[dict[str, Any]]:
    return [
        {
            "source_record_id": r.source_record_id, "source_type": r.source_type,
            "source_name": r.source_name,
            "acquisition_status": r.source_class,
            "is_fixture": r.is_fixture, "url": r.url, "record_id": r.record_id,
            "access_date": r.access_date, "release_version": r.release_version,
            "license": r.license, "raw_sha256": r.raw_sha256, "raw_bytes": r.raw_bytes,
            "raw_media_type": r.raw_media_type,
        }
        for r in inputs.sources.values()
    ]


def _safety_rows(inputs: Stage4Inputs, result: Stage4Result) -> list[dict[str, Any]]:
    """Canonical input row + how the state renders. NOT ONE of the five states renders safe."""
    base = {r["evidence_id"]: r for r in evidence_input_rows(inputs)["safety_evidence"]}
    rows = []
    for cr in result.candidates:
        for s_row in cr.safety_rows:
            rendered = render_evidence_state(s_row.evidence_state.value)
            rows.append({
                **base[s_row.evidence_id],
                "renders_as_safe": rendered["renders_as_safe"],
                "evidence_state_display": rendered["display_text"],
            })
    return rows
