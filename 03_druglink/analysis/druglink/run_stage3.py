"""Stage-3 orchestrator. Offline; fixture-firewalled; refuses rather than guesses.

    python -m druglink.run_stage3 \
        --artifact-class analysis \
        --direct-run <verified Direct run dir> \
        --direct-inputs-root <the raw inputs those files were pinned against> \
        --cache-root <acquisition cache> \
        --output-root <outputs> \
        [--pathway-hypotheses <spot.stage02_pathway_hypotheses.v1>]

There is deliberately NO ``--lever-set``. The only input is a Direct run directory, and
it is admitted only after Direct's own standalone verifier RECONSTRUCTS it from the raw
sources and exits 0. A caller-authored lever document is not a fallback: the argument
does not exist, so no code path can reach one.

Stage 3 reports scientific workflow STATES (``druglink.workflow``). It has no
promotion, eligibility or recommendation vocabulary — that is retired. There are two
artifact classes and one firewall: ``analysis`` (a real computation) and ``fixture``
(synthetic, which can never be relabelled and never reaches Stage 4).

This module GENERATES. ``03_druglink/verifier/`` independently RECONSTRUCTS and checks;
it shares no expansion, direction, workflow or content-hashing code with this package.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import sys
from typing import Any, Optional

from . import (acquisition, adapters, armlever, artifact_class as ac, artifacts,
               bundle, candidates, direct_run, drug_mapping, identity,
               joint_context, mechanisms, pathways, potency,
               science_registry as sr, science_review, targets, workflow as wf)
from .direction import ORIGIN_DIRECT_TARGET, ORIGIN_PATHWAY_NODE
from .hashing import short_id

CRISPRI_MODALITY = "CRISPRi_knockdown"
ORIGINS = (ORIGIN_DIRECT_TARGET, ORIGIN_PATHWAY_NODE)


def _disposition_rows(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for d in raw:
        row = {"subject_kind": d["subject_kind"], "subject_id": d["subject_id"],
               "state": d["state"], "reason": d["reason"],
               "detail": d.get("detail"),
               "source_record_id": d.get("source_record_id")}
        row["disposition_id"] = short_id(row)
        out.append(row)
    return sorted(out, key=lambda r: r["disposition_id"])


def build(*, artifact_class: str, direct: direct_run.DirectRun,
          acquired: dict[str, Any],
          pathway_hypotheses: Optional[dict[str, Any]] = None,
          reviews: Optional[dict[str, Any]] = None,
          science_registry_root: Optional[str] = None) -> dict[str, Any]:
    ac.require(artifact_class)

    # ---- two arms, always both, never collapsed --------------------------------
    expanded = armlever.expand(direct.screen, direct_run_id=direct.run_id)
    arm_levers = expanded["arm_levers"]

    # ---- pathway nodes: a SECOND lane, never merged with the measured one -------
    paths = pathway_hypotheses or {"levers": [], "pathways": [], "dispositions": [],
                                   "ref": dict(pathways.NOT_EVALUATED)}
    node_levers = paths["levers"]
    reviews = reviews or {"by_candidate": {}, "ref": dict(science_review.NOT_PROVIDED)}

    # Keyed by (gene, arm, ORIGIN): a gene that is both a measured target and an
    # inferred node holds two distinct levers, and neither borrows the other's rank,
    # tier or support.
    arm_index = armlever.index_by_key(arm_levers + node_levers)

    source_records = {s["source_record_id"]: dict(s)
                      for s in acquired["source_records"]}
    dispositions = (list(acquired["dispositions"]) + list(expanded["dispositions"])
                    + list(paths["dispositions"]))

    # ---- parse acquired bytes, or dispose --------------------------------------
    records: list[dict[str, Any]] = []
    for src_id, blob in acquired["raw"].items():
        adapter = blob["adapter"]
        rec = source_records[src_id]
        if adapter.status not in ac.REQUIRED_ADAPTER_STATUS[artifact_class]:
            rec["parse_status"] = "adapter_not_ready"
            rec["parse_detail"] = (
                f"adapter {adapter.name} is {adapter.status}; {artifact_class} "
                f"requires one of {ac.REQUIRED_ADAPTER_STATUS[artifact_class]}")
            dispositions.append({
                "subject_kind": "adapter", "subject_id": adapter.name,
                "state": adapter.status,
                "reason": "adapter_not_permitted_for_this_artifact_class",
                "detail": rec["parse_detail"], "source_record_id": src_id})
            continue
        try:
            records.extend(adapters.parse_raw(adapter, blob["bytes"],
                                              blob["entry"], src_id))
            rec["parse_status"] = "parsed"
        except adapters.UnsupportedSchema as exc:
            rec["parse_status"] = "unsupported_schema"
            rec["parse_detail"] = str(exc)
            dispositions.append({
                "subject_kind": "source_record", "subject_id": src_id,
                "state": "unsupported_schema",
                "reason": "response_shape_not_supported_by_this_adapter_version",
                "detail": str(exc), "source_record_id": src_id})

    # ---- identity, targets, mechanisms, potency --------------------------------
    graph = identity.build_graph(records)
    dispositions.extend(graph["dispositions"])

    tgt = targets.build(records)
    dispositions.extend(tgt["dispositions"])

    asserted = mechanisms.build_assertions(records=records, graph=graph, targets=tgt)
    dispositions.extend(asserted["dispositions"])

    built = mechanisms.build_edges(assertions=asserted["assertions"],
                                   arm_lever_index=arm_index, graph=graph,
                                   targets=tgt, modality=CRISPRI_MODALITY)
    dispositions.extend(built["dispositions"])

    pot = potency.build(records=records, edges=built["edges"], graph=graph,
                        targets=tgt)
    dispositions.extend(pot["dispositions"])

    # ---- drug_mapping_status: mapped | unmapped | refused -----------------------
    mapping = drug_mapping.build(levers=arm_levers + node_levers, targets=tgt)
    dispositions.extend(drug_mapping.dispositions(mapping))

    # ---- candidates, summarised per (arm, origin) -------------------------------
    arm_summaries = candidates.build_arm_summaries(edges=built["edges"])
    cands = candidates.order(candidates.build(
        artifact_class=artifact_class, edges=built["edges"],
        moieties=graph["moieties"], arm_summaries=arm_summaries,
        potency_rows=pot["potency_rows"], reviews=reviews))
    dispositions.extend(candidates.not_queued(cands))

    tables = {
        "arm_levers": arm_levers,
        "pathway_nodes": node_levers,
        "pathways": paths["pathways"],
        "cross_arm": expanded["cross_arm"],
        "source_records": list(source_records.values()),
        "target_entities": list(tgt["entities"].values()),
        "target_entity_components": tgt["components"],
        "drug_forms": graph["forms"],
        "drug_identifiers": graph["identifiers"],
        "drug_form_relations": graph["relations"],
        "active_moieties": list(graph["moieties"].values()),
        "mechanism_assertions": asserted["assertions"],
        "target_drug_edges": built["edges"],
        "candidate_arm_summaries": arm_summaries,
        "drug_mapping": mapping,
        "potency_evidence": pot["potency_rows"],
        "dispositions": _disposition_rows(dispositions),
        "candidates": cands,
    }

    counts = _counts(expanded=expanded, graph=graph, tgt=tgt, asserted=asserted,
                     edges=built["edges"], potency_rows=pot["potency_rows"],
                     arm_summaries=arm_summaries, candidates=cands,
                     dispositions=tables["dispositions"], node_levers=node_levers,
                     mapping=mapping)

    doc = bundle.build_document(
        artifact_class=artifact_class, upstream=direct.binding,
        acquisition=acquired["acquisition_ref"],
        pathway=paths["ref"],
        joint=joint_context.from_provenance(direct.provenance),
        science_registry=sr.registry_ref(science_registry_root),
        review=reviews["ref"],
        table_hashes=artifacts.table_content_hashes(tables),
        candidates=cands, counts=counts)

    return {"document": doc, "document_id": doc["bundle_id"], "tables": tables,
            "counts": counts, "direct": direct}


def _counts(*, expanded, graph, tgt, asserted, edges, potency_rows, arm_summaries,
            candidates, dispositions, node_levers, mapping) -> dict[str, Any]:
    def by_status(rows, status):
        return sum(1 for e in rows
                   if e["directional_evidence_status"] == status)

    per_arm = {}
    for arm in armlever.ARMS:
        arm_edges = [e for e in edges if e["desired_arm"] == arm]
        entry = {**expanded["counts"]["per_arm"][arm], "n_edges": len(arm_edges)}
        # Counted SEPARATELY by origin: a measured target and an inferred pathway node
        # are never added together. Every status is reported, INCLUDING the zeros.
        for origin in ORIGINS:
            rows = [e for e in arm_edges if e["origin_type"] == origin]
            entry[origin] = {
                "n_edges": len(rows),
                "n_observed_perturbation": by_status(rows, wf.OBSERVED_PERTURBATION),
                "n_inverse_direction_hypothesis": by_status(
                    rows, wf.INVERSE_DIRECTION_HYPOTHESIS),
                "n_pathway_hypothesis": by_status(rows, wf.PATHWAY_HYPOTHESIS),
                "n_opposed": by_status(rows, wf.OPPOSED),
                "n_unresolved": by_status(rows, wf.UNRESOLVED),
            }
        per_arm[arm] = entry

    return {
        "n_screen_rows": expanded["counts"]["n_screen_rows"],
        "n_arm_levers": expanded["counts"]["n_arm_levers"],
        "n_unique_immutable_keys": expanded["counts"]["n_unique_immutable_keys"],
        "n_pathway_nodes": len(node_levers),
        "per_arm": per_arm,
        "drug_mapping": drug_mapping.counts(mapping),
        "n_forms": len(graph["forms"]),
        "n_active_moieties": len(graph["moieties"]),
        "n_target_entities": len(tgt["entities"]),
        "n_mechanism_assertions": len(asserted["assertions"]),
        "n_edges": len(edges),
        "n_potency_rows": len(potency_rows),
        "n_candidate_arm_summaries": len(arm_summaries),
        "n_candidates": len(candidates),
        "n_stage4_queued": sum(1 for c in candidates
                               if c["stage4_assessment_status"] == wf.QUEUED),
        "n_stage4_not_queued": sum(1 for c in candidates
                                   if c["stage4_assessment_status"] == wf.NOT_QUEUED),
        "disease_context_review": {
            status: sum(1 for c in candidates
                        if c["disease_context_review_status"] == status)
            for status in science_review.REVIEW_STATUSES},
        "disease_context_review_results": {
            result: sum(1 for c in candidates
                        if c["disease_context_review_result"] == result)
            for result in science_review.REVIEW_RESULTS},
        "n_dispositions": len(dispositions),
    }


def run(*, artifact_class: str, direct_run_dir: str, direct_inputs_root: str,
        cache_root: str, output_root: str, direct_analysis: Optional[str] = None,
        pathway_hypotheses: Optional[str] = None,
        science_registry_root: Optional[str] = None,
        disease_context_review: Optional[str] = None,
        created_at: Optional[str] = None) -> dict[str, Any]:
    direct = direct_run.load(direct_run_dir, direct_inputs_root,
                             artifact_class=artifact_class,
                             direct_analysis=direct_analysis)
    acquired = acquisition.load_manifest(cache_root, artifact_class, direct=direct)
    paths = pathways.load(pathway_hypotheses, artifact_class=artifact_class,
                          direct=direct,
                          science_registry_root=science_registry_root)
    reviews = science_review.load(disease_context_review,
                                  artifact_class=artifact_class, direct=direct,
                                  science_registry_root=science_registry_root)
    result = build(artifact_class=artifact_class, direct=direct, acquired=acquired,
                   pathway_hypotheses=paths, reviews=reviews,
                   science_registry_root=science_registry_root)
    created_at = created_at or _dt.datetime.now(_dt.UTC).isoformat()
    bundle_path = artifacts.write_bundle(
        output_root=output_root, artifact_class=artifact_class,
        document=result["document"], doc_id=result["document_id"],
        tables=result["tables"], created_at=created_at)
    return {**result, "bundle_dir": bundle_path}


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="spot Stage-3 drug link (offline; verified Direct run only)")
    ap.add_argument("--artifact-class", required=True,
                    choices=list(ac.ARTIFACT_CLASSES),
                    help="analysis (a real computation) or fixture (synthetic; never "
                         "reaches Stage 4). The production/research namespaces are "
                         "retired.")
    ap.add_argument("--direct-run", required=True,
                    help="a Stage-2 Direct RUN DIRECTORY. There is no --lever-set.")
    ap.add_argument("--direct-inputs-root", required=True,
                    help="the raw inputs the Direct run's files were pinned against")
    ap.add_argument("--cache-root", required=True)
    ap.add_argument("--output-root", required=True)
    ap.add_argument("--direct-analysis", default=None,
                    help="Direct analysis root providing direct.verify_run "
                         "(default: $SPOT_DIRECT_ANALYSIS, then the sibling worktree)")
    ap.add_argument("--pathway-hypotheses", default=None,
                    help="OPTIONAL spot.stage02_pathway_hypotheses.v1 document, EMITTED "
                         "BY STAGE 2. Its nodes are inferred, never perturbed: they are "
                         "a SEPARATE lane (origin_type=pathway_node) and can never be "
                         "an observed_perturbation. Omit it and the lane is "
                         "not_evaluated.")
    ap.add_argument("--science-registry", default=None,
                    help="content-addressed Claude Science evidence registry. Every "
                         "referenced record is RESOLVED and RE-HASHED; a missing or "
                         "altered record fails closed.")
    ap.add_argument("--disease-context-review", default=None,
                    help="OPTIONAL spot.stage03_disease_context_review.v1 document. A "
                         "COMPLETED result must carry evidence bindings that resolve in "
                         "the registry; one that cites nothing is downgraded to "
                         "insufficient, never favourable by default.")
    args = ap.parse_args(argv)

    try:
        out = run(artifact_class=args.artifact_class, direct_run_dir=args.direct_run,
                  direct_inputs_root=args.direct_inputs_root,
                  cache_root=args.cache_root, output_root=args.output_root,
                  direct_analysis=args.direct_analysis,
                  pathway_hypotheses=args.pathway_hypotheses,
                  science_registry_root=args.science_registry,
                  disease_context_review=args.disease_context_review)
    except (direct_run.DirectRunError, armlever.ArmLeverError,
            acquisition.AcquisitionError, pathways.PathwayError,
            sr.ScienceRegistryError, science_review.ReviewError,
            ac.ArtifactClassError, artifacts.ArtifactError) as exc:
        print(f"REFUSED [{args.artifact_class}]: {exc}")
        return 2

    doc, counts = out["document"], out["counts"]
    print(f"artifact_class   {doc['artifact_class']}")
    print(f"bundle_id        {doc['bundle_id']}")
    print(f"direct_run_id    {doc['upstream']['direct_run_id']}")
    print(f"data_status      {doc['data_status']}")
    print(f"pathway_lane     {doc['pathway_hypotheses']['pathway_lane']}")
    print(f"arm_levers       {counts['n_arm_levers']} "
          f"({counts['n_screen_rows']} screen rows x 2 arms)")
    for arm, per in counts["per_arm"].items():
        for origin in ORIGINS:
            o = per[origin]
            print(f"  {arm:<12} {origin:<14} edges={o['n_edges']} "
                  f"observed={o['n_observed_perturbation']} "
                  f"inverse={o['n_inverse_direction_hypothesis']} "
                  f"pathway={o['n_pathway_hypothesis']} "
                  f"opposed={o['n_opposed']} unresolved={o['n_unresolved']}")
    print(f"drug_mapping     {counts['drug_mapping']}")
    print(f"candidates       {counts['n_candidates']} "
          f"(stage4 queued={counts['n_stage4_queued']} "
          f"not_queued={counts['n_stage4_not_queued']})")
    print(f"                 {wf.STAGE4_ASSESSMENT_NOTE}")
    print(f"disease review   {counts['disease_context_review']} "
          f"results={counts['disease_context_review_results']}")
    print(f"bundle_dir       {out['bundle_dir']}")
    print("run the INDEPENDENT verifier before trusting any of this")
    return 0


if __name__ == "__main__":
    sys.exit(main())
