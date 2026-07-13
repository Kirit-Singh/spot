"""The Stage-3 drug-annotation consumer (spot.stage34_annotation_adapter.v1).

Admission only. The CONTRACT — what the schema is, what is retired, and every hash that must
reproduce before a row is believed — lives in `stage3_contract_v2.py`, which this imports and
which the tests exercise directly. Splitting them keeps each under the repo's 500-line rule and
makes the verification readable on its own: it is the half a reviewer actually needs to audit.

`stage4_assessment_status = queued` is the ONLY admission signal, and it is not a promotion
signal. Stage 3 says so in the document itself:

    "a stage-4 assessment computes PK/safety properties; it is not biological promotion and
     not a recommendation"

WHAT IS CARRIED THROUGH UNCHANGED, and must never be collapsed:

  * `arm_evidence_states` — one entry per (desired_arm, origin_type). Stage 4 computes NO
    combined rank, NO headline arm, NO cross-arm objective. There is no field to hold one.
  * `inverse_direction_hypothesis_arms` + `inverse_direction_support` — a LABELLED HYPOTHESIS.
    Never reported as observed gain of function.
  * the disease-context review — a COMPLETABLE result (supportive/contradictory/mixed/
    insufficient), not a one-way flag. `pending` is not reviewed; `insufficient` is not a
    soft yes. Carried verbatim, interpreted never.
  * `origin_type` — a `pathway_node` result may NEVER be reported as a measured one.
  * science-evidence refs `{science_evidence_id, science_evidence_sha256, record_type}` —
    carried verbatim as typed REFERENCES, never dereferenced, embedded or summarised.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Optional

from .contracts import (
    ActiveMoiety,
    CompoundIds,
    DirectionCompatibility,
    Namespace,
    SourceRecord,
    Stage3Binding,
    Stage3Candidate,
    Stage3DrugCandidateSet,
)
from .firewall import Rejection, compute_candidate_rows_sha256
from .stage3_admission import NOT_RUN, admit
from .stage3_v2_seam import assert_v2_admissible
from .stage3_contract_v2 import (
    ACQUISITION_STATUSES,
    ADAPTER_ID,
    ADAPTER_VERSION,
    ANNOTATION_SCHEMA,
    QUEUED,
    RETIRED_KEYS,
    SCIENCE_REF_KEYS,
    STAGE3_CONTRACT_VERSION,
    _ID_TYPE_TO_FIELD,
    _read_json,
    verify_annotation_bundle,
)

__all__ = [
    "ADAPTER_ID", "ADAPTER_VERSION", "ANNOTATION_SCHEMA", "RETIRED_KEYS",
    "STAGE3_CONTRACT_VERSION", "AnnotationAdmission", "ArmEvidence", "DiseaseContextReview",
    "QueuedCandidate", "adapt_annotation_bundle", "verify_annotation_bundle",
]

@dataclass
class ArmEvidence:
    """One (desired_arm, origin_type) cell. The arms are never merged."""

    desired_arm: str
    origin_type: str
    arm_evidence_state: str
    raw: dict[str, Any]


@dataclass
class DiseaseContextReview:
    """A COMPLETABLE disease-context review, carried verbatim from Stage 3.

    Not a one-way flag. `status` is pending / completed / not_required; `result` is
    supportive / contradictory / mixed / insufficient (only when completed, else None). A
    substantive result is one Stage 3 already paid for with resolvable evidence bindings —
    Stage 4 reports it and interprets none of it. `pending` is not reviewed; `insufficient` is
    not a soft yes.
    """

    status: str
    result: Optional[str]
    reason: str
    evidence_refs: list[dict[str, Any]]
    reviewed_by: Optional[str]


@dataclass
class QueuedCandidate:
    """What Stage 3 queued, carried through without collapse."""

    candidate_id: str
    active_moiety_id: str
    stage4_assessment_reason: str
    arm_evidence_states: list[ArmEvidence]
    observed_perturbation_arms: list[str]
    inverse_direction_hypothesis_arms: list[str]
    inverse_direction_support: list[dict[str, Any]]
    pathway_hypothesis_arms: list[str]
    opposed_arms: list[str]
    stage3_evidence_classes: list[str]
    disease_context_review: DiseaseContextReview
    potency_state: str
    science_evidence_refs: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class AnnotationAdmission:
    bundle_id: str
    bundle_dir: str
    schema_version: str
    artifact_class: str
    document_sha256: str
    canonical_content_sha256: str
    manifest_sha256: str
    data_status: str
    n_candidates_in_bundle: int
    admitted_as_candidates: int
    not_queued: int
    candidate_set: Optional[Stage3DrugCandidateSet]
    queued: list[QueuedCandidate] = field(default_factory=list)
    not_queued_reasons: dict[str, str] = field(default_factory=dict)
    source_records: dict[str, SourceRecord] = field(default_factory=dict)
    refusal_reason: Optional[str] = None
    # Which gates actually ran. `external_verifier` is PASSED only when Stage-3's own
    # verifier really executed and exited 0 — `not_run` is not a pass, and no integration-GO
    # may be claimed on a bundle it never saw. See `stage3_admission`.
    external_verifier: str = NOT_RUN
    gates: tuple[str, ...] = ("stage4_restatement",)


# --------------------------------------------------------------------------- admission


def _science_refs(tables: dict[str, list[dict]]) -> list[dict[str, Any]]:
    """Typed science-evidence REFERENCES, carried verbatim. Never dereferenced or embedded.

    Stage 3 refuses a free-form object or string in their place: an interpretation is not a
    computation, and an un-hashed blob cannot be verified or attributed. Stage 4 keeps them a
    reference too — it does not read the record, summarise it, or let it stand in for
    programmatic evidence.
    """
    refs: list[dict[str, Any]] = []
    for table in ("pathway_nodes", "pathways"):
        for row in tables.get(table, []):
            for ref in (row.get("science_evidence_ids") or []):
                if not isinstance(ref, dict) or set(SCIENCE_REF_KEYS) - set(ref):
                    raise Rejection(
                        "stage3_science_ref_untyped",
                        f"{table}: a science-evidence reference must be a typed "
                        f"{list(SCIENCE_REF_KEYS)} record, not {type(ref).__name__}. An "
                        "un-hashed blob cannot be verified or attributed.")
                refs.append({k: ref[k] for k in SCIENCE_REF_KEYS})
    refs.sort(key=lambda r: (r["science_evidence_id"], r["record_type"]))
    return refs


def _source_records(rows: list[dict[str, Any]], access_date: str) -> dict[str, SourceRecord]:
    """Stage-3's classes, carried across VERBATIM. `not_acquired` stays `not_acquired`."""
    out: dict[str, SourceRecord] = {}
    for r in rows:
        status = r.get("acquisition_status")
        if status not in ACQUISITION_STATUSES:
            raise Rejection(
                "stage3_unknown_acquisition_status",
                f"source record declares acquisition_status={status!r}, which Stage 4 does not "
                f"recognise. Known: {list(ACQUISITION_STATUSES)}. Stage 4 refuses rather than "
                "guessing whether bytes exist behind a row.")
        out[r["source_record_id"]] = SourceRecord(
            source_record_id=r["source_record_id"],
            source_type="public_api",
            source_name=f"Stage-3 {r.get('source')} ({r.get('adapter')})",
            acquisition_status=status,
            access_date=access_date,
            url=r.get("retrieval_url"),
            record_id=r.get("source_record_id"),
            release_version=r.get("source_release"),
            license=r.get("license"),
            raw_sha256=r.get("raw_sha256"),
            raw_bytes=r.get("raw_bytes"),
            raw_media_type=r.get("raw_media_type"),
        )
    return out


def _access_date(doc: dict[str, Any]) -> str:
    acq = doc.get("acquisition") or {}
    for key in ("acquired_at", "access_date", "acquisition_date"):
        v = acq.get(key)
        if isinstance(v, str) and len(v) >= 10:
            return v[:10]
    return "1970-01-01"


def adapt_annotation_bundle(bundle_dir: str, *,
                            require_external_verifier: bool = False) -> AnnotationAdmission:
    """Verify, then admit ONLY the rows Stage 3 queued for a Stage-4 assessment.

    Admission runs through `stage3_admission.admit`, which is BOTH gates: Stage-4's own
    restatement of the bytes AND Stage-3's independent `verifier.verify_stage3`. Set
    `require_external_verifier=True` for a data-bound run — it refuses a bundle that Stage-3's
    verifier has not actually passed.
    """
    # THE V2 SEAM, before the v1 reader sees a single byte.
    #
    # A v2 bundle read by the v1 reader would have its new fields silently ignored and its evidence
    # admitted against a contract nobody checked it against — and every downstream hash would be a
    # self-consistent hash of a misreading. So a bundle DECLARING v2 is refused by name until W16
    # publishes the final schema-set hash and Stage 4 re-pins deliberately.
    assert_v2_admissible(bundle_dir)

    admission_gates = admit(bundle_dir, require_external_verifier=require_external_verifier)
    doc, tables = admission_gates.document, admission_gates.tables

    candidates = tables["candidates"]
    moieties = {m["active_moiety_id"]: m for m in tables["active_moieties"]}
    forms_by_moiety: dict[str, list[dict]] = {}
    for f in tables["drug_forms"]:
        forms_by_moiety.setdefault(f["active_moiety_id"], []).append(f)
    ids_by_form: dict[str, list[dict]] = {}
    for i in tables["drug_identifiers"]:
        ids_by_form.setdefault(i["form_id"], []).append(i)

    science = _science_refs(tables)

    queued = [c for c in candidates if c.get("stage4_assessment_status") == QUEUED]
    not_queued = {c["candidate_id"]: c.get("stage4_assessment_reason") or "not_queued"
                  for c in candidates if c.get("stage4_assessment_status") != QUEUED}

    carried: list[QueuedCandidate] = []
    for c in sorted(queued, key=lambda r: r["candidate_id"]):
        arms = [
            ArmEvidence(desired_arm=a["desired_arm"], origin_type=a["origin_type"],
                        arm_evidence_state=a["arm_evidence_state"], raw=dict(a))
            for a in sorted(c.get("arm_evidence_states") or [],
                            key=lambda a: (a["desired_arm"], a["origin_type"]))
        ]
        carried.append(QueuedCandidate(
            candidate_id=c["candidate_id"],
            active_moiety_id=c["active_moiety_id"],
            stage4_assessment_reason=c.get("stage4_assessment_reason") or "",
            arm_evidence_states=arms,
            observed_perturbation_arms=list(c.get("observed_perturbation_arms") or []),
            inverse_direction_hypothesis_arms=list(
                c.get("inverse_direction_hypothesis_arms") or []),
            inverse_direction_support=[dict(s) for s in
                                       (c.get("inverse_direction_support") or [])],
            pathway_hypothesis_arms=list(c.get("pathway_hypothesis_arms") or []),
            opposed_arms=list(c.get("opposed_arms") or []),
            stage3_evidence_classes=list(c.get("stage3_evidence_classes") or []),
            disease_context_review=DiseaseContextReview(
                status=c.get("disease_context_review_status") or "not_required",
                result=c.get("disease_context_review_result"),
                reason=c.get("disease_context_review_reason") or "",
                evidence_refs=[dict(r) for r in
                               (c.get("disease_context_review_evidence_refs") or [])],
                reviewed_by=c.get("disease_context_reviewed_by"),
            ),
            potency_state=c.get("potency_state") or "not_evaluated",
            science_evidence_refs=science,
        ))

    admission = AnnotationAdmission(
        bundle_id=doc["bundle_id"],
        bundle_dir=os.path.abspath(bundle_dir),
        schema_version=doc["schema_version"],
        artifact_class=doc["artifact_class"],
        document_sha256=doc["document_sha256"],
        canonical_content_sha256=doc["canonical_content_sha256"],
        manifest_sha256=_read_json(os.path.join(bundle_dir, "manifest.json"))["manifest_sha256"],
        data_status=doc.get("data_status", "unknown"),
        n_candidates_in_bundle=len(candidates),
        admitted_as_candidates=len(queued),
        not_queued=len(not_queued),
        candidate_set=None,
        queued=carried,
        not_queued_reasons=not_queued,
        source_records=_source_records(tables["source_records"], _access_date(doc)),
        external_verifier=admission_gates.external_verifier,
        gates=admission_gates.gates,
    )

    if not queued:
        admission.refusal_reason = (
            "no candidate in this bundle has stage4_assessment_status=queued. Stage 4 assesses "
            "only what Stage 3 queued; it does not queue rows itself.")
        return admission

    built: list[Stage3Candidate] = []
    for q in carried:
        m = moieties.get(q.active_moiety_id)
        if m is None:
            raise Rejection("stage3_dangling_moiety",
                            f"candidate {q.candidate_id!r} names active moiety "
                            f"{q.active_moiety_id!r}, which has no row")
        if m.get("identity_status") != "resolved":
            raise Rejection(
                "stage3_unresolved_moiety",
                f"candidate {q.candidate_id!r} has identity_status="
                f"{m.get('identity_status')!r}. An unresolved molecule cannot be PK-assessed, "
                "and Stage 4 will not guess which one it is.")

        forms = sorted(forms_by_moiety.get(q.active_moiety_id, []),
                       key=lambda f: f["form_id"])
        parent = next((f for f in forms if f.get("form_class") == "parent"), None) or (
            forms[0] if forms else {})

        compound: dict[str, Any] = {}
        for f in forms:
            for i in ids_by_form.get(f["form_id"], []):
                key = _ID_TYPE_TO_FIELD.get(str(i.get("id_type") or ""))
                if key and not compound.get(key):
                    compound[key] = i.get("id_value")
        if not compound.get("chembl_id") and m.get("moiety_chembl_id"):
            compound["chembl_id"] = m["moiety_chembl_id"]

        src = next((c for c in candidates if c["candidate_id"] == q.candidate_id), {})
        built.append(Stage3Candidate(
            candidate_id=q.candidate_id,
            namespace=Namespace.RESEARCH_ONLY,
            active_moiety=ActiveMoiety(
                active_moiety_id=q.active_moiety_id,
                active_moiety_name=m.get("preferred_name") or q.active_moiety_id,
                unii=m.get("moiety_unii"),
                inchikey=m.get("moiety_inchikey"),
                administered_form="active_moiety",
                administered_form_name=parent.get("preferred_name"),
                maps_to_active_moiety_id=q.active_moiety_id,
                mapping_source_record_id=(src.get("source_record_ids") or [None])[0],
            ),
            compound_ids=CompoundIds(**compound),
            target=", ".join(src.get("target_ensembls") or []) or "unspecified",
            mechanism=q.stage4_assessment_reason or "unspecified",
            # NO single direction, in ANY field. `away_from_A` and `toward_B` are independent
            # hypotheses with their own evidence states per origin_type; collapsing them into
            # one program direction, one drug-effect direction or one compatibility would BE
            # the cross-arm objective Stage 3 forbids, and would silently privilege whichever
            # arm happened to be listed first. The per-arm states travel intact on `queued`.
            program_direction="unspecified",
            drug_effect_direction="unspecified",
            direction_compatibility=DirectionCompatibility.UNKNOWN,
            stage3_evidence_source_record_ids=list(src.get("source_record_ids") or []),
        ))

    admission.candidate_set = Stage3DrugCandidateSet(
        # Stage-4's INTERNAL normalized form. The Stage-3 wire schema is on the binding below.
        schema_id="spot.stage03_drug_candidate_set.v1",
        stage3_run_id=doc["upstream"].get("direct_run_id") or doc["bundle_id"],
        candidate_set_id=doc["bundle_id"],
        candidate_rows_sha256=compute_candidate_rows_sha256(built),
        # Stage 3 retired `namespace`. Stage 4 keeps its OWN internal namespace enum and pins
        # every Stage-3 assessment to the non-promotable lane: a Stage-4 assessment is not
        # biological promotion, and there is no Stage-3 field that could say otherwise.
        namespace=Namespace.RESEARCH_ONLY,
        is_fixture=False,
        stage3_method_version=str((doc.get("method") or {}).get("stage3_method_version")
                                  or STAGE3_CONTRACT_VERSION),
        candidates=built,
        stage3_binding=Stage3Binding(
            stage3_schema_version=doc["schema_version"],
            stage3_document_id=doc["bundle_id"],
            stage3_namespace=Namespace.RESEARCH_ONLY,
            canonical_content_sha256=doc["canonical_content_sha256"],
            document_sha256=doc["document_sha256"],
            table_hashes=dict(sorted(doc["table_hashes"].items())),
            stage3_method={k: str(v) for k, v in (doc.get("method") or {}).items()
                           if isinstance(v, (str, int, float, bool))},
            stage3_upstream={k: str(v) for k, v in (doc.get("upstream") or {}).items()
                             if isinstance(v, (str, int, float, bool))},
            stage3_source_status={
                "n_source_records": len(tables["source_records"]),
                "n_acquired_public": sum(1 for r in tables["source_records"]
                                         if r.get("acquisition_status") == "acquired_public"),
                "n_not_acquired": sum(1 for r in tables["source_records"]
                                      if r.get("acquisition_status") != "acquired_public"),
            },
            stage3_eligible=False,
            stage4_eligible=True,
            production_candidate=False,
            adapter_id=ADAPTER_ID,
            adapter_version=ADAPTER_VERSION,
        ),
    )
    return admission
