"""A Stage-4 evidence bundle for the candidates a Stage-3 drug-annotation bundle QUEUES.

FIXTURE OBSERVATIONS. Every source record here is `synthetic_fixture` and every number is
invented. The molecules are real because Stage 3 resolved them from real pinned ChEMBL bytes;
the PK/safety numbers attached to them are not. **Nothing in this module is a scientific
finding about ipilimumab or any other molecule.**

It exists to drive the assessment lane end to end and to show what Stage 4 does with PARTIAL
evidence, which is the normal case:

  * a candidate with a full evidence set gets a full set of lanes;
  * a candidate with NO evidence gets empty/unknown lanes — never `safe`, never `permeable`,
    and never an NEBPI class. Missing evidence is missing evidence.

Stage 4 is generic over whatever Stage 3 queues: it keys on `candidate_id` /
`active_moiety_id` and asks nothing about which arm, origin_type or program produced them.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

ACCESS_DATE = "2026-07-12"
SCHEMA = "spot.stage04_evidence_bundle.v1"

RESPONSES: dict[str, dict[str, Any]] = {
    "src.assess.props": {"fixture": "physchem response"},
    "src.assess.potency": {"fixture": "potency response"},
    "src.assess.exposure": {"fixture": "PK response"},
    "src.assess.nebpi": {"fixture": "NEBPI response"},
    "src.assess.delivery": {"fixture": "delivery review record"},
    "src.assess.label": {"fixture": "label response"},
}


def _bytes(sid: str) -> bytes:
    return json.dumps(RESPONSES[sid], sort_keys=True, separators=(",", ":")).encode()


def _sha(sid: str) -> str:
    return hashlib.sha256(_bytes(sid)).hexdigest()


def _prov(sid: str, transform: str) -> dict[str, Any]:
    return {"source_record_id": sid, "access_date": ACCESS_DATE,
            "raw_response_sha256": _sha(sid), "extraction_transform": transform}


def _sources() -> dict[str, Any]:
    return {
        sid: {"source_record_id": sid, "source_type": "fixture",
              "source_name": f"FIXTURE assessment response ({sid})",
              "acquisition_status": "synthetic_fixture", "access_date": ACCESS_DATE,
              "raw_sha256": _sha(sid), "raw_bytes": len(_bytes(sid))}
        for sid in RESPONSES
    }


def build(candidate_ids: list[str], moiety_of: dict[str, str],
          n_with_evidence: int = 2) -> dict[str, Any]:
    contexts, properties, potencies, exposures = [], [], [], []
    delivery, nebpi, safety, searches = [], [], [], []

    for n, cid in enumerate(candidate_ids[:n_with_evidence], start=1):
        moiety = moiety_of[cid]
        ctx = f"ACTX-{n}"
        contexts.append({
            "context_id": ctx, "candidate_id": cid, "active_moiety_id": moiety,
            "route": "intravenous", "formulation": "solution", "dose": "3 mg/kg",
            "schedule": "q21d", "tumor_context": "GBM_assessment_fixture",
            "is_fixture": True,
        })

        # A monoclonal antibody: MW is the only CNS-MPO input that exists. The score stays
        # INCOMPLETE rather than being imputed — and an incomplete CNS-MPO is not, and can
        # never become, an NEBPI class.
        properties.append({
            "property_record_id": f"APRP-{n}-mw", "candidate_id": cid,
            "active_moiety_id": moiety, "property_id": "mw",
            "value_source_string": "148000", "units": "g_per_mol",
            "determination": "predicted", "calculator_id": "pubchem_molecular_weight",
            "method": "PubChem MolecularWeight", "software_version": "fixture-1.0",
            "provenance": _prov("src.assess.props", "read MW from the cached response"),
        })
        potencies.append({
            "potency_id": f"APOT-{n}", "candidate_id": cid, "active_moiety_id": moiety,
            "metric": "MEC", "value_source_string": "200", "units": "nM",
            "binding_state": "free", "assay": "FIXTURE target-engagement assay",
            "biological_context": "GBM_assessment_fixture", "evidence_type": "in_vitro",
            "provenance": _prov("src.assess.potency", "read MEC from the cached study"),
        })
        # Measured in non-enhancing brain, below the MEC -> low PK in NEB, DERIVED from the
        # concentration-vs-MEC comparison rather than asserted.
        exposures.append({
            "measurement_id": f"AEXP-{n}", "candidate_id": cid, "active_moiety_id": moiety,
            "context_id": ctx, "formulation": "solution", "route": "intravenous",
            "dose": "3 mg/kg", "schedule": "q21d",
            "species_population": "adult human (fixture)",
            "matrix": "brain_tissue_non_enhancing", "enhancement_context": "non_enhancing",
            "binding_state": "free", "concentration_source_string": "5",
            "concentration_units": "nM", "detection_status": "quantified",
            "timepoint": "168 h post-infusion", "evidence_type": "human_clinical",
            "provenance": _prov("src.assess.exposure", "read NEB concentration"),
        })
        delivery.append({
            "assignment_id": f"ADLV-{n}", "candidate_id": cid, "context_id": ctx,
            "requirement": "local_CNS_target_engagement_required",
            "basis": "mechanism_with_pharmacology_evidence",
            "assigned_by": "fixture-reviewer-assessment",
            "rule_id": "explicit_assignment_required", "rule_version": "1.0.0",
            "rationale": "FIXTURE: the effect requires target engagement in brain parenchyma.",
            "evidence": _prov("src.assess.delivery", "read the delivery assignment"),
        })
        nebpi.extend([
            {"observation_id": f"ANEB-{n}-1", "candidate_id": cid, "context_id": ctx,
             "criterion_id": "known_mec_potency", "state": "observed_present",
             "evidence_type": "in_vitro",
             "provenance": _prov("src.assess.nebpi", "read the MEC observation")},
            {"observation_id": f"ANEB-{n}-2", "candidate_id": cid, "context_id": ctx,
             "criterion_id": "pk_in_neb", "state": "observed_present",
             "measurement_id": f"AEXP-{n}", "potency_id": f"APOT-{n}",
             "evidence_type": "human_clinical",
             "provenance": _prov("src.assess.nebpi", "read the NEB PK observation")},
            # An absence claim ONLY where an adequate assessment actually looked.
            {"observation_id": f"ANEB-{n}-3", "candidate_id": cid, "context_id": ctx,
             "criterion_id": "pd_in_neb", "state": "observed_absent",
             "assessment_adequate": True,
             "adequacy_rationale": "FIXTURE: powered PD study in NEB tissue.",
             "evidence_type": "human_clinical",
             "provenance": _prov("src.assess.nebpi", "read the PD observation")},
            {"observation_id": f"ANEB-{n}-4", "candidate_id": cid, "context_id": ctx,
             "criterion_id": "radiographic_response_in_neb", "state": "observed_absent",
             "assessment_adequate": True,
             "adequacy_rationale": "FIXTURE: protocol-defined NEB response assessment.",
             "evidence_type": "human_clinical",
             "provenance": _prov("src.assess.nebpi", "read the radiographic observation")},
        ])
        safety.extend([
            {"evidence_id": f"ASCN-{n}-immune", "candidate_id": cid,
             "active_moiety_id": moiety, "evidence_state": "label_supported",
             "finding_type": "warning_precaution",
             "finding_text": "FIXTURE: immune-mediated adverse reactions have been reported.",
             "gbm_scenario": "corticosteroid_exposure",
             "interaction_type": "immune_activation_autoimmunity",
             "label_identity": {
                 "label_source": "dailymed_spl",
                 "setid": f"ffffffff-0000-4000-8000-assessment{n:03d}",
                 "product_identity": f"FIXTURE product for {moiety}",
                 "labeled_section_code": "34071-1",
                 "labeled_section_name": "WARNINGS AND PRECAUTIONS",
                 "code_system": "2.16.840.1.113883.6.1"},
             "provenance": _prov("src.assess.label", "parse the labelled warnings section")},
            # Searched and found nothing — a statement about the SEARCH, not a finding of safety.
            {"evidence_id": f"ASCN-{n}-bleed", "candidate_id": cid,
             "active_moiety_id": moiety, "evidence_state": "no_evidence_found",
             "gbm_scenario": "perioperative_setting", "interaction_type": "bleeding",
             "searched_sources": ["src.assess.label"], "search_id": f"ASRCH-{n}-bleed"},
        ])
        searches.append({
            "search_id": f"ASRCH-{n}-bleed", "source": "dailymed_spl",
            "endpoint": "/dailymed/services/v2/spls/{setid}.xml",
            "query_canonical": f"setid=ffffffff-0000-4000-8000-assessment{n:03d}; "
                               "terms=bleed|haemorrhage|hemorrhage",
            "search_scope": "all labelled sections of the cited SPL version",
            "executed_date": ACCESS_DATE, "source_release": "FIXTURE SPL v1", "n_results": 0,
            "provenance": _prov("src.assess.label",
                                "search every labelled section for bleeding terms; 0 hits"),
        })

    return {
        "schema_id": SCHEMA, "sources": _sources(), "contexts": contexts,
        "properties": properties, "potencies": potencies, "transporters": [],
        "exposures": exposures, "delivery_assignments": delivery,
        "nebpi_observations": nebpi, "safety_records": safety,
        "search_manifests": searches, "potency_context_links": [],
        "config": {"assessment_fixture_evidence": True},
    }


def write(path: str, candidate_ids: list[str], moiety_of: dict[str, str],
          n_with_evidence: int = 2) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(build(candidate_ids, moiety_of, n_with_evidence), fh, indent=2,
                  sort_keys=True)
        fh.write("\n")
    return path
