"""Stage-4 pipeline: hash-bound inputs -> six separate evidence lanes.

The lanes never merge. There is no step in this file that combines CNS-MPO, transporter,
exposure, NEBPI and safety evidence into one number, because the moment such a number
exists, everything below it stops being read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .cnsmpo import CnsMpoResult, score_cns_mpo
from .contracts import EvidenceContext, SourceRecord, Stage3DrugCandidateSet
from .delivery import DeliveryResult, resolve_delivery_requirement
from .acquisition import SourceAcquisitionRecord
from .contract_profile import assert_contract_satisfied
from .contract_version import ContractVersion
from .pk_records import FractionUnboundRecord
from .evidence_records import (
    DeliveryAssignment,
    ExposureMeasurement,
    NebpiObservation,
    PotencyContextLink,
    PotencyRecord,
    PropertyRecord,
    Provenance,
    SafetyEvidenceRecord,
    SearchManifest,
    TransporterObservation,
)
from .exposure import MarginResult, compute_exposure_margin, matrix_caveats
from .firewall import Rejection, production_eligibility
from .integrity import check_referential_integrity
from .method_config import MethodBundle
from .nebpi import NebpiResult, evaluate_nebpi
from .properties import PropertySelection, cross_candidate_calculator_mixing, select_properties
from .safety import render_evidence_state, scenario_matrix
from .transporters import transporter_summary

# Only a declared target concentration may serve as the denominator of a margin. An
# IC50 is not an MEC: turning one into the other needs an unbound fraction and a
# declared transform, and Stage 4 will not supply either silently.
MARGIN_METRICS = ("MEC", "target_concentration")


@dataclass
class Stage4Inputs:
    candidate_set: Stage3DrugCandidateSet
    contexts: list[EvidenceContext]
    sources: dict[str, SourceRecord]
    properties: list[PropertyRecord] = field(default_factory=list)
    potencies: list[PotencyRecord] = field(default_factory=list)
    transporters: list[TransporterObservation] = field(default_factory=list)
    exposures: list[ExposureMeasurement] = field(default_factory=list)
    delivery_assignments: list[DeliveryAssignment] = field(default_factory=list)
    nebpi_observations: list[NebpiObservation] = field(default_factory=list)
    safety_records: list[SafetyEvidenceRecord] = field(default_factory=list)
    # Typed and source-bound. Previously an untyped dict that was OMITTED from the id, so
    # adding one flipped a margin from not_computable to computed without moving the id.
    potency_context_links: list[PotencyContextLink] = field(default_factory=list)
    search_manifests: list[SearchManifest] = field(default_factory=list)
    # v2. An fu is an OBSERVATION -- it has a species, a method, a concentration dependence
    # and a source of its own -- so it is a lane, not a field buried inside a concentration.
    # Kp,uu rests on two of these, and a Kp,uu whose fu records cannot be inspected is an
    # unbound ratio asserted from total concentrations.
    fraction_unbound: list[FractionUnboundRecord] = field(default_factory=list)
    # v2. The acquisition manifest behind the sources: canonical query, accessed_at_utc, HTTP
    # status, terms URL, adapter code hash, observation state. Content-addressed and bound
    # into the scorecard_set_id.
    acquisitions: list[SourceAcquisitionRecord] = field(default_factory=list)
    config: dict[str, Any] = field(default_factory=dict)
    # Which evidence contract these rows speak. A v1 bundle stays v1 forever: it does not
    # become acquisition-complete because newer code can read it, and its rows do not acquire
    # v2 columns full of nulls.
    contract_version: ContractVersion = ContractVersion.V1

    def evidence_lanes(self) -> dict[str, list[Any]]:
        """Everything that feeds the scorecard_set_id, as the exact rows the release carries.

        Keyed by EMITTED TABLE, and carrying the FULL canonical row of each consumed record
        (`evidence_inputs.py`) — not a hand-picked subset of its fields, and not the pydantic
        object. Both properties matter:

          * full row — the re-audit rewrote a negative search's `search_scope`, `source`,
            `executed_date` and `extraction_transform` in a resealed release, and the id did
            not move because those columns were never hashed. Every bound column is here now.
          * emitted table — the independent verifier can read these same rows back out of the
            parquet and recompute this digest, which it could not do from a pydantic dump.
        """
        from .evidence_inputs import evidence_input_rows

        return evidence_input_rows(self, self.contract_version)


@dataclass
class CandidateResult:
    candidate_id: str
    active_moiety_id: str
    cns_mpo: CnsMpoResult
    delivery: list[DeliveryResult]
    nebpi: list[NebpiResult]
    exposure: list[tuple[ExposureMeasurement, MarginResult]]
    transporters: dict[str, Any]
    safety_rows: list[SafetyEvidenceRecord]
    scenario_matrix: list[dict[str, Any]]
    production_eligible: bool
    eligibility_reason_code: str
    eligibility_reason: str


@dataclass
class Stage4Result:
    candidates: list[CandidateResult]
    calculator_mixing: dict[str, Any]
    property_selections: dict[str, PropertySelection]


def provenance_bindings(inputs: Stage4Inputs) -> list[tuple[str, Provenance]]:
    """Every (owner, provenance) pair the firewall must check against the registry.

    EVERY result-affecting row belongs here. The audit found three that did not:

      * `potency_context_links` — an unregistered source and an invented hash turned a
        margin from not_computable into computed and an NEBPI class from None into
        insufficiently_permeable, and both verifiers passed it.
      * `delivery_assignments` — an assignment citing `src.DOES_NOT_EXIST` set the NEBPI
        primary gate.
      * `search_manifests` — a caller-authored negative search passed as sourced evidence.

    A row that can change a result and is not in this list is a hole in the firewall.
    """
    out: list[tuple[str, Provenance]] = []
    for prop in inputs.properties:
        out.append((f"property:{prop.property_record_id}", prop.provenance))
    for pot in inputs.potencies:
        out.append((f"potency:{pot.potency_id}", pot.provenance))
    for link in inputs.potency_context_links:
        out.append((f"potency_context_link:{link.link_id}", link.provenance))
    for trp in inputs.transporters:
        out.append((f"transporter:{trp.observation_id}", trp.provenance))
    for exp in inputs.exposures:
        out.append((f"exposure:{exp.measurement_id}", exp.provenance))
    for asg in inputs.delivery_assignments:
        # An assignment with no evidence binding is legal and is downgraded to uncertain.
        # An assignment that CITES a source must resolve to acquired, matching bytes.
        if asg.evidence is not None:
            out.append((f"delivery_assignment:{asg.assignment_id}", asg.evidence))
    for neb in inputs.nebpi_observations:
        out.append((f"nebpi:{neb.observation_id}", neb.provenance))
    for man in inputs.search_manifests:
        out.append((f"search_manifest:{man.search_id}", man.provenance))
    for saf in inputs.safety_records:
        if saf.provenance is not None:
            out.append((f"safety:{saf.evidence_id}", saf.provenance))
    return out


def select_margin_potency(
    candidate_id: str, potencies: list[PotencyRecord]
) -> tuple[Optional[PotencyRecord], Optional[str], Optional[str]]:
    """-> (potency, reason_code, reason). Never picks between ambiguous records."""
    mine = [p for p in potencies if p.candidate_id == candidate_id]
    if not mine:
        return None, "no_potency_record", "No potency/MEC record for this candidate."
    usable = [p for p in mine if p.metric in MARGIN_METRICS]
    if not usable:
        return (
            None,
            "potency_metric_not_a_target_concentration",
            "Available potency metrics are "
            + ", ".join(sorted({p.metric for p in mine}))
            + ". A margin needs an MEC or a declared target concentration; deriving one from an "
            "IC50/IC90 requires an unbound fraction and a declared transform.",
        )
    if len(usable) > 1:
        return (
            None,
            "ambiguous_potency_records",
            "More than one MEC/target-concentration record: "
            + ", ".join(sorted(p.potency_id for p in usable))
            + ". Stage 4 will not choose one.",
        )
    return usable[0], None, None


def run_pipeline(inputs: Stage4Inputs, method: MethodBundle) -> Stage4Result:
    """Every number here is either an input record or a declared transform of one."""
    # The bundle declares a contract; this is where it has to carry it. A v2 bundle that
    # is missing the fields that make it acquisition-complete stops HERE, before any
    # lane is computed -- a run that got as far as a release would have produced a
    # document that reads like a result.
    assert_contract_satisfied(inputs)
    check_referential_integrity(inputs)

    ctx_by_candidate: dict[str, list[EvidenceContext]] = {}
    for c in inputs.contexts:
        ctx_by_candidate.setdefault(c.candidate_id, []).append(c)

    known = {c.candidate_id for c in inputs.candidate_set.candidates}
    for c in inputs.contexts:
        if c.candidate_id not in known:
            raise Rejection("orphan_context", f"context {c.context_id!r} refers to unknown candidate {c.candidate_id!r}")

    selections: dict[str, PropertySelection] = {}
    results: list[CandidateResult] = []

    for cand in sorted(inputs.candidate_set.candidates, key=lambda c: c.candidate_id):
        cid = cand.candidate_id
        moiety = cand.active_moiety.active_moiety_id

        # --- CNS-MPO (per moiety; a physicochemical score has no dosing context) ----
        props = [p for p in inputs.properties if p.candidate_id == cid]
        for p in props:
            if p.active_moiety_id != moiety:
                raise Rejection(
                    "moiety_mismatch",
                    f"property {p.property_id!r} for {cid!r} is bound to moiety {p.active_moiety_id!r}, "
                    f"but the candidate's active moiety is {moiety!r}. Salt/prodrug/metabolite values "
                    "must not be joined onto the active moiety.",
                )
        sel = select_properties(props, method.calculator_policy)
        selections[cid] = sel
        mpo = score_cns_mpo(cid, moiety, sel, method.cns_mpo)

        # --- delivery + NEBPI (per evidence context) -------------------------------
        deliveries: list[DeliveryResult] = []
        nebpis: list[NebpiResult] = []
        for ctx in sorted(ctx_by_candidate.get(cid, []), key=lambda c: c.context_id):
            d = resolve_delivery_requirement(cid, ctx.context_id, inputs.delivery_assignments, method.delivery_rules)
            deliveries.append(d)
            nebpis.append(
                evaluate_nebpi(
                    cid, ctx, inputs.nebpi_observations, inputs.potencies, d, method.nebpi,
                    measurements=inputs.exposures,
                    potency_context_links=inputs.potency_context_links,
                )
            )

        # --- exposure (one row per measurement) ------------------------------------
        potency, p_code, p_reason = select_margin_potency(cid, inputs.potencies)
        ctx_by_id = {c.context_id: c for c in inputs.contexts}
        exposures: list[tuple[ExposureMeasurement, MarginResult]] = []
        for m in sorted([e for e in inputs.exposures if e.candidate_id == cid], key=lambda e: e.measurement_id):
            exposure_ctx = ctx_by_id.get(m.context_id)
            if exposure_ctx is None:
                raise Rejection("orphan_context", f"exposure {m.measurement_id!r} refers to unknown context {m.context_id!r}")
            if potency is None:
                margin = MarginResult(
                    measurement_id=m.measurement_id, potency_id=None, candidate_id=cid,
                    context_id=m.context_id, status="not_computable", margin=None,
                    margin_canonical_decimal=None, harmonized_units=None,
                    exposure_harmonized=None, potency_harmonized=None,
                    binding_state=m.binding_state, matrix=m.matrix,
                    enhancement_context=m.enhancement_context,
                    detection_status=m.detection_status,
                    reason_code=p_code, reason=p_reason, transform=None,
                    # What the matrix cannot say holds whether or not an MEC exists. A CSF
                    # measurement with no admissible potency is exactly where the reader has
                    # least to go on, and it used to be emitted with no caveat at all.
                    caveats=matrix_caveats(m),
                )
            else:
                margin = compute_exposure_margin(m, potency, exposure_ctx, inputs.potency_context_links)
            exposures.append((m, margin))

        elig = production_eligibility(inputs.candidate_set, cand, inputs.sources)
        safety_rows = sorted(
            [s for s in inputs.safety_records if s.candidate_id == cid], key=lambda s: s.evidence_id
        )

        results.append(
            CandidateResult(
                candidate_id=cid,
                active_moiety_id=moiety,
                cns_mpo=mpo,
                delivery=deliveries,
                nebpi=nebpis,
                exposure=exposures,
                transporters=transporter_summary(inputs.transporters, cid, method.prose),
                safety_rows=safety_rows,
                scenario_matrix=scenario_matrix(cid, safety_rows),
                production_eligible=elig.production_eligible,
                eligibility_reason_code=elig.reason_code,
                eligibility_reason=elig.reason,
            )
        )

    return Stage4Result(
        candidates=results,
        calculator_mixing=cross_candidate_calculator_mixing(selections, method.prose),
        property_selections=selections,
    )


# ------------------------------------------------------------------- provenance chain


def build_provenance_chain(cr: CandidateResult, prose: dict[str, Any]) -> list[dict[str, Any]]:
    """Every displayed scientific field -> the response hash and transform behind it."""
    chain: list[dict[str, Any]] = []

    for p in cr.cns_mpo.input_provenance:
        chain.append(
            {
                "field_path": f"candidates.{cr.candidate_id}.lanes.cns_mpo.components.{p['property_id']}",
                "property_record_id": p["property_record_id"],
                "value": p["component_score_t0"],
                "derived_from": {
                    "value_source_string": p["value_source_string"],
                    "value_canonical_decimal": p["value_canonical_decimal"],
                    "units": p["units"],
                    "unit_conversion": p["unit_conversion"],
                },
                "transform": (
                    f"{p['property_id']} desirability (Wager 2010 Table 1 "
                    f"{'hump' if p['property_id'] == 'tpsa' else 'monotonic decreasing'})"
                ),
                "method_id": cr.cns_mpo.method_id,
                "calculator_id": p["calculator_id"],
                "method_conformance": p["method_conformance"],
                "source_record_id": p["source_record_id"],
                "raw_response_sha256": p["raw_response_sha256"],
            }
        )
    if cr.cns_mpo.status == "complete":
        chain.append(
            {
                "field_path": f"candidates.{cr.candidate_id}.lanes.cns_mpo.total_published",
                "value": cr.cns_mpo.total_published,
                "transform": "sum of the six equally weighted T0 components, rounded half-up to 1 dp",
                "method_id": cr.cns_mpo.method_id,
                "source_record_id": None,
                "raw_response_sha256": None,
                "note": prose["provenance_chain"]["cns_mpo_total_note"],
            }
        )

    for d in cr.delivery:
        chain.append(
            {
                "field_path": f"candidates.{cr.candidate_id}.lanes.delivery.{d.context_id}.requirement",
                "value": d.requirement,
                "transform": f"delivery_rules::{d.rule_id or 'default'} ({d.reason_code})",
                "method_id": "delivery_rules_v1",
                "assigned_by": d.assigned_by,
                "assignment_id": d.assignment_id,
                "conflicting_assignment_ids": list(d.conflicting_assignment_ids),
                "source_record_id": d.evidence_source_record_id,
                "raw_response_sha256": d.evidence_sha256,
            }
        )

    for n in cr.nebpi:
        chain.append(
            {
                "field_path": f"candidates.{cr.candidate_id}.lanes.nebpi.{n.context_id}.nebpi_class",
                "value": n.nebpi_class,
                "transform": "NEBPI Part-II branch logic over the criterion observations listed in evidence_observation_ids",
                "method_id": n.method_id,
                "supporting_observation_ids": n.evidence_observation_ids,
                "source_record_id": None,
                "raw_response_sha256": None,
                "note": prose["provenance_chain"]["nebpi_class_note"],
            }
        )

    for m, margin in cr.exposure:
        chain.append(
            {
                "field_path": f"candidates.{cr.candidate_id}.lanes.exposure.{m.measurement_id}.concentration",
                "value": m.concentration_source_string,
                "value_canonical_decimal": m.quantity.canonical_decimal if m.quantity else None,
                "units": m.concentration_units,
                "detection_status": m.detection_status,
                "transform": m.provenance.extraction_transform,
                "source_record_id": m.provenance.source_record_id,
                "raw_response_sha256": m.provenance.raw_response_sha256,
            }
        )
        if margin.status == "computed":
            chain.append(
                {
                    "field_path": f"candidates.{cr.candidate_id}.lanes.exposure.{m.measurement_id}.margin",
                    "value": margin.margin_canonical_decimal,
                    "transform": margin.transform,
                    "source_record_id": m.provenance.source_record_id,
                    "raw_response_sha256": m.provenance.raw_response_sha256,
                    "potency_id": margin.potency_id,
                }
            )

    for t in cr.transporters["transporters"]:
        for o in t["observations"]:
            chain.append(
                {
                    "field_path": f"candidates.{cr.candidate_id}.lanes.transporters.{t['transporter']}.{o['observation_id']}",
                    "value": o["interaction"],
                    "transform": f"{o['assay']} in {o['biological_system']} ({o['species']})",
                    "source_record_id": o["source_record_id"],
                    "raw_response_sha256": o["raw_response_sha256"],
                }
            )

    for s in cr.safety_rows:
        chain.append(
            {
                "field_path": f"candidates.{cr.candidate_id}.lanes.safety.{s.evidence_id}",
                "value": s.evidence_state.value,
                **render_evidence_state(s.evidence_state.value),
                "transform": (s.provenance.extraction_transform if s.provenance
                              else prose["provenance_chain"]["safety_no_source_transform"]),
                "source_record_id": s.provenance.source_record_id if s.provenance else None,
                "raw_response_sha256": s.provenance.raw_response_sha256 if s.provenance else None,
                "search_id": s.search_id,
                "labeled_section": s.label_identity.labeled_section_code if s.label_identity else None,
                "label_version": s.label_identity.label_version if s.label_identity else None,
            }
        )

    # A field with two agreeing sources has two chain entries, so field_path alone is no
    # longer a key. Sorting on the source binding too keeps the chain byte-stable.
    chain.sort(key=lambda c: (c["field_path"],
                              str(c.get("source_record_id") or ""),
                              str(c.get("raw_response_sha256") or "")))
    return chain
