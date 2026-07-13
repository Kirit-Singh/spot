"""The UI/CLI face of the DEVELOPMENT projection. Split from :mod:`druglink.dev_projection`
at the 500-line gate, at the seam the module already had: that is the ENGINE (real bytes -> real
edges), this is the FACE (what a consumer reads, and the command that writes it).

Nothing here computes science. Every field below is DERIVED from the edges the engine produced, so
the compact UI rows can never become a second source of truth that drifts from the tables they
summarise.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from . import edge_build_v2 as eb
from . import modality_contract as mc
from . import universe_rows as ur
from . import workflow as wf
from .dev_projection import (
    LANE_DIRECT,
    STATUS_UNADMITTED,
    DevProjectionError,
    _load_json,
    attach_pathway_context,
    build_document,
    load_direct_arms,
    project,
)
from .hashing import file_sha256


def ui_artifact(document: dict[str, Any]) -> dict[str, Any]:
    """A COMPACT block shaped like the Stage3UiArtifact candidate rows W23 already renders.

    It is a projection of the richer tables above, never a second source of truth: every field is
    DERIVED from the edges in this document. The top-level namespace stays
    ``development_unadmitted`` so W23 must opt in to a dev route explicitly and cannot mistake it
    for production.

    Fields Stage-3 has no admitted producer for yet (potency, disease-context review, the Stage-4
    assessment) are NAMED as not-evaluated rather than defaulted to zero or empty — "we did not
    run it" and "we ran it and found nothing" are different facts, and a 0 makes them one.
    """
    rows = []
    for cand in document["candidates"]:
        edges = [t for arm in cand["arms"] for t in arm["targets"]]
        observed = sorted({arm["arm_key"] for arm in cand["arms"] for t in arm["targets"]
                           if t.get("observed_perturbation_support") is True})
        inverse = sorted({arm["arm_key"] for arm in cand["arms"] for t in arm["targets"]
                          if str(t.get("directional_evidence_status") or "")
                          == wf.INVERSE_DIRECTION_HYPOTHESIS})
        rows.append({
            "candidate_id": cand["candidate_id"],
            "active_moiety_id": cand["active_moiety_id"],
            "preferred_name": cand["preferred_name"],
            "identity_status": cand.get("identity_status") or "active_moiety",
            "form_ids": [cand["molecule_chembl_id"]] if cand.get("molecule_chembl_id") else [],
            "target_ensembls": sorted({str(t["target_id"]) for t in edges
                                       if str(t.get("target_id_namespace"))
                                       == mc.W3_NS_ENSEMBL_GENE_ID}),
            "n_edges": len(edges),
            "n_direct_gene_edges": len(edges),          # this runner projects the Direct lane only
            "development_state_aggregate": cand.get("max_phase_source"),
            # NAMED, not zeroed. Stage-3 has no admitted potency producer in this dev route.
            "n_potency_rows": None,
            "potency_state": "not_evaluated_in_development_projection",
            "observed_perturbation_arms": observed,
            "inverse_direction_support": bool(inverse),
            "pathway_hypothesis_arms": [],              # pathway NEVER promotes; see pathway_context
            "stage3_evidence_classes": sorted({str(t["stage3_evidence_class"]) for t in edges
                                               if t.get("stage3_evidence_class")}),
            "disease_context_review_status": "not_evaluated_in_development_projection",
            "disease_context_review_result": None,
            "stage4_assessment_status": "not_assessed_release_is_not_admitted",
            "source_record_ids": sorted({str(t["source_record_id"]) for t in edges
                                         if t.get("source_record_id")}),
        })
    return {
        "schema_version": "spot.stage03_dev_ui_artifact.v0",
        "status": STATUS_UNADMITTED,
        "is_production_result": False,
        "combined_objective_permitted": False,
        "candidates": rows,
        "n_candidates": len(rows),
    }


def main(argv: Optional[list[str]] = None) -> int:
    """Project ONE same-condition question over the REAL Direct bytes. Writes ONE JSON."""
    import argparse

    ap = argparse.ArgumentParser(
        description="DEVELOPMENT projection over real, UNADMITTED Stage-2 Direct bytes. "
                    "This is not a production result and writes no Stage-3 bundle.")
    ap.add_argument("--direct-bundle", required=True,
                    help="the real Direct bundle dir (arm_bundle.json + arms.parquet + "
                         "target_identity.json)")
    ap.add_argument("--universe-store", required=True, help="the ADMITTED universe store")
    ap.add_argument("--a-program", required=True, help="the A pole's program_id")
    ap.add_argument("--a-change", required=True, choices=("increase", "decrease"))
    ap.add_argument("--b-program", required=True, help="the B pole's program_id")
    ap.add_argument("--b-change", required=True, choices=("increase", "decrease"))
    ap.add_argument("--selection", default=None,
                    help="the real Stage-1 v3 selection contract, bound for identity")
    ap.add_argument("--pathway-context", default=None,
                    help="a COMPACT GO-BP endpoint context. Absent => a NAMED unavailable entry.")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    try:
        arms, provenance = load_direct_arms(args.direct_bundle)
        store = ur.load_store(args.universe_store)
        condition = str(provenance["condition"])
        a_key = f"{LANE_DIRECT}|{args.a_program}|{args.a_change}|{condition}"
        b_key = f"{LANE_DIRECT}|{args.b_program}|{args.b_change}|{condition}"
        projection = project(arms=arms, store=store, a_arm_key=a_key, b_arm_key=b_key)
    except (DevProjectionError, ur.UniverseRowsError, eb.CandidatesV2Error) as exc:
        print(f"REFUSED: {exc}")
        print("nothing was written. This runner has no fixture fallback.")
        return 3

    selection: dict[str, Any] = {
        "a": {"program_id": args.a_program, "desired_change": args.a_change,
              "arm_key": a_key, "condition": condition},
        "b": {"program_id": args.b_program, "desired_change": args.b_change,
              "arm_key": b_key, "condition": condition},
        "analysis_mode": "within_condition",
        "roles_are_assigned_at_join_time_never_stored_on_an_arm": True,
    }
    if args.selection and os.path.isfile(args.selection):
        doc = _load_json(args.selection, "Stage-1 v3 selection contract")
        selection["stage1_selection"] = {
            "path": os.path.basename(args.selection),
            "raw_sha256": file_sha256(args.selection),
            "selection_id": doc.get("selection_id"),
            "question_id": doc.get("question_id"),
        }

    document = build_document(condition=condition, selection=selection, projection=projection,
                              provenance=provenance, store=store,
                              store_dir=args.universe_store)
    attach_pathway_context(document, args.pathway_context)
    document["ui_artifact"] = ui_artifact(document)

    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(document, fh, sort_keys=True, indent=1)
        fh.write("\n")

    a, b = document["arms"][a_key], document["arms"][b_key]
    print(f"[{STATUS_UNADMITTED}] {condition}: {args.a_program}|{args.a_change} -> "
          f"{args.b_program}|{args.b_change}")
    for block in (a, b):
        print(f"  {block['arm_key']:<44} {block['n_ranked']:>6} ranked  "
              f"{block['n_edges']:>5} edges  {block['n_candidates']:>4} candidates")
    print(f"  candidates (both arms)                       {document['n_candidates']}")
    print(f"  pathway_context                              {document['pathway_context']['status']}")
    print(f"  store                                        {store.store_id[:16]}… (admitted)")
    print(f"  -> {args.out}  sha256={file_sha256(args.out)}")
    print("NOT a production result: the Stage-2 aggregate and bridge are not admitted.")
    return 0


if __name__ == "__main__":                                   # pragma: no cover
    raise SystemExit(main())
