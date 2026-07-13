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
from . import artifacts_v2
from . import stage2_aggregate as sa
from . import universe_rows
from . import admitted_universe, arm_query as aq, v2_input_loader as v2
from .direction import V1_ORIGIN_TYPES, V2_ORIGIN_TYPES
from .hashing import short_id

CRISPRI_MODALITY = "CRISPRi_knockdown"

# The origins a V1 BUNDLE contains, counted SEPARATELY and never pooled. Unchanged: this drives
# the frozen bundle document, whose bytes Stage 4 binds by SHA.
ORIGINS = V1_ORIGIN_TYPES

# The v2 lane's typed origins. Two are MEASURED and are DISTINCT ESTIMANDS — a same-condition
# effect and a cross-time difference-in-differences answer different questions, and fusing them
# was the defect a1d8958 fixed. One is INFERRED and was never perturbed at all. They are
# counted separately, always: a total across them would be a combined objective wearing a
# total's clothes.
V2_ORIGINS = V2_ORIGIN_TYPES


def load_v2_inputs(*, universe_store: str,
                   universe_targets: list[dict[str, str]],
                   direct_arm_bundle: Optional[dict[str, Any]] = None,
                   direct_admission: Optional[aq.ExternalAdmission] = None,
                   temporal_arm_bundles: tuple = (),
                   pathway_arm_bundle: Optional[dict[str, Any]] = None,
                   pathway_nodes: tuple = (),
                   require_production: bool = False,
                   admitted_aggregate: Optional[Any] = None) -> dict[str, Any]:
    """THE v2 input stage: bind the admitted universe store, then load the three typed origins.

    Two bindings, in this order, and neither is optional:

      1. the UNIVERSE STORE an independent verifier admitted, by its exact ``store_id``. A
         missing store REFUSES — it does not quietly become a fixture, which is precisely how
         a synthetic number becomes a result;
      2. the ADMITTED Stage-2 evidence, origin-typed: ``direct_target`` and
         ``temporal_cross_time_measured`` (both measured, distinct estimands, never fused) and
         ``endpoint_pathway_context`` (inferred, never perturbed, never a measurement).

    Direction is NOT decided here. The frozen direction engine decides it at view time, from
    the arm's own desired_change and the drug's sourced action — never the cache and never the
    loader. That is rule 3 of the admission contract, and it is why this function returns
    inputs rather than verdicts.
    """
    store_binding = admitted_universe.bind(store_dir=universe_store,
                                           universe_targets=universe_targets)
    inputs = v2.load_admitted_stage2_inputs(
        direct_arm_bundle=direct_arm_bundle, direct_admission=direct_admission,
        temporal_arm_bundles=temporal_arm_bundles,
        pathway_arm_bundle=pathway_arm_bundle, pathway_nodes=pathway_nodes,
        measured_target_ids=None, require_production=require_production,
        admitted_aggregate=admitted_aggregate)
    return {"universe_store_binding": store_binding, "v2_inputs": inputs}


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


V2_REQUIRED = ("--stage2-manifest", "--stage2-report", "--bundles-root", "--stage1-release",
               "--universe-store", "--stage2-bridge", "--stage2-bridge-report")

# The bridge CONSUMER is not implemented yet. The flags exist (the contract is published to W3
# and they are generating against it), but nothing in this module reads them.
#
# An accepted-and-ignored flag is worse than a missing one: a caller who passes --stage2-bridge
# would get a run that silently never honoured it, and an artifact that looks like it was built
# on admitted identity and modality when it was not. So the v2 path REFUSES BY NAME until the
# consumer lands. It is not "wired" — it is declared, and it says so.
GATE_BRIDGE_CONSUMER_NOT_IMPLEMENTED = "the_stage3_bridge_consumer_is_not_implemented_yet"


def bridge_consumer_ready() -> bool:
    """Can Stage-3 actually ADMIT and CONSUME the bridge (not merely accept its path)?

    False. `stage2_contract` has no bridge admitter: nothing re-hashes `bridge_sha256`, nothing
    binds the separate bridge report to those exact bytes, nothing cross-binds the bridge to the
    aggregate, and nothing re-checks the bridge's arm_value against the native ranking file.

    This reports a fact about THIS module — whether the consumer exists — and it is checked by a
    test that greps for the admitter. It is NOT an artifact-admission gate. (An artifact gate
    must never be a Boolean in Stage-3's own source; that was `DETACHED_CLONE_MATRIX_GREEN`, and
    retiring it is why the aggregate is now admitted from disk.)
    """
    return hasattr(sa, "admit_bridge")


def _v2_main(args) -> int:
    """The v2 path: admit Stage-2 from disk, open the admitted universe store, EMIT a bundle.

    This used to pass ``universe_targets=[]`` and write nothing, justified by a module constant
    (``DETACHED_CLONE_MATRIX_GREEN``) that no artifact could ever flip. Both are gone. The empty
    list was the worse of the two: an EMPTY typed universe hashes to a real, stable digest
    (4f53cda1…) and verifies perfectly — against nothing. A run that answers "no drug evidence"
    because it was handed no targets is indistinguishable, in the artifact, from one that
    genuinely looked and found none.

    Now the universe is DERIVED from the admitted store's own rows, and the gate is the Stage-2
    admission itself: its manifest recomputes its own identity, and a SEPARATE verifier's report
    admits those exact bytes. No admitted aggregate, no run.
    """
    missing = [f for f in V2_REQUIRED if not getattr(args, f[2:].replace("-", "_"), None)]
    if missing:
        print(f"REFUSED [{args.artifact_class}]: --v2 requires {', '.join(missing)}. There is "
              "no fixture fallback and no default: Stage 3 stands on Stage-2's admitted "
              "aggregate and the admitted universe store, or it does not run.")
        return 2

    # Fail closed rather than silently ignore the bridge the caller supplied. The native ranking
    # rows carry {target_id, arm_value, evaluable, rank} — no namespace, no modality — so an
    # analysis built without the bridge would have to INVENT both. It will not.
    if not bridge_consumer_ready():
        print(f"REFUSED [{args.artifact_class}]: [{GATE_BRIDGE_CONSUMER_NOT_IMPLEMENTED}] the "
              "bridge consumer is not implemented. Stage-3 will not run a v2 analysis while "
              "ignoring the bridge: the native arms carry no target namespace and no "
              "perturbation modality, and those facts exist ONLY in the bridge. Building "
              "without it would mean inferring identity and defaulting a modality from a "
              "config constant — a setting wearing the costume of an assay. No bundle was "
              "written.")
        return 3

    try:
        aggregate = sa.admit_aggregate(
            manifest_path=args.stage2_manifest, report_path=args.stage2_report,
            bundles_root=args.bundles_root, stage1_release_path=args.stage1_release,
            artifact_class=args.artifact_class)
        store = universe_rows.load_store(args.universe_store)
        loaded = load_v2_inputs(
            universe_store=args.universe_store,
            # the REAL typed universe, derived from the store's own rows — never []
            universe_targets=store.typed_universe,
            require_production=True,
            admitted_aggregate=aggregate)
        emitted = artifacts_v2.emit(
            output_root=args.output_root, artifact_class=args.artifact_class,
            aggregate=aggregate, store=store, report_path=args.stage2_report)
    except (admitted_universe.AdmittedUniverseError, v2.V2InputLoaderError,
            sa.Stage2AggregateError, universe_rows.UniverseRowsError,
            aq.ArmQueryError) as exc:
        print(f"REFUSED [{args.artifact_class}]: {exc}")
        print("no bundle was written. Stage 3 does not fabricate candidates: a synthetic "
              "number in a bundle is a synthetic number on its way to Stage 4.")
        return 3

    # `emit` returns {bundle_dir, bundle_id, document, tables}. This block used to read
    # emitted["path"] and emitted["counts"] — neither key exists — so a SUCCESSFUL emit wrote the
    # bundle and then died with KeyError, reporting a good run as a failed CLI. The success path
    # had never been executed. Counts are derived from the tables actually written, not from a
    # summary that could drift from them.
    binding = loaded["universe_store_binding"]
    tables = emitted["tables"]
    print(f"stage2_aggregate {aggregate.manifest_self_hash[:16]}… "
          f"admitted_by={aggregate.verifier_id} verdict={aggregate.verdict}")
    print(f"                 {len(aggregate.bundles)} bundles / {len(aggregate.arms)} arm slots")
    print(f"universe_store   {binding['store_id'][:16]}… "
          f"({len(store.typed_universe)} typed targets)")
    print(f"bundle           {emitted['bundle_id']}")
    print(f"                 {emitted['bundle_dir']}")
    for name in sorted(tables):
        print(f"  {name:<28} {len(tables[name])}")
    print("origins counted SEPARATELY; no combined objective; pathway is CONTEXT and never "
          "sources a drug edge.")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="spot Stage-3 drug link (offline; verified Direct run only)")
    # ---- v2: the three typed origins + the admitted universe store -------------------
    ap.add_argument("--v2", action="store_true",
                    help="consume ADMITTED Stage-2 arm bundles through the v2 input loader: "
                         "direct_target + temporal_cross_time_measured (measured, distinct "
                         "estimands, never fused) + endpoint_pathway_context (inferred). "
                         "GATED: emits no candidate bundle until the independent "
                         "detached-clone matrix is green.")
    ap.add_argument("--universe-store", default=None,
                    help="the universe store an INDEPENDENT verifier admitted, bound by its "
                         "exact store_id. A missing store REFUSES; there is no fixture "
                         "fallback.")
    # ---- the ADMITTED Stage-2 aggregate: the four paths W3's native contract publishes ----
    # These are not optional and there is no default. Stage 3 stands on Stage-2's admission or
    # it does not run: the manifest proves its own identity, and the SEPARATE verifier's report
    # is what admits it (a manifest never admits itself).
    ap.add_argument("--stage2-manifest", default=None,
                    help="v2: Stage-2's native aggregate run manifest "
                         "(spot.stage02_run_manifest.v3_topology_only)")
    ap.add_argument("--stage2-report", default=None,
                    help="v2: the SEPARATE aggregate verifier's report "
                         "(spot.stage02_run_manifest_verification.v1). Stage 3 reads "
                         "verdict=='admit' from THIS file, never from the manifest.")
    ap.add_argument("--bundles-root", default=None,
                    help="v2: the root the manifest's bundles[] resolve against")
    ap.add_argument("--stage1-release", default=None,
                    help="v2: the authoritative Stage-1 v3 release the manifest pins")
    # ---- the Stage-3 BRIDGE: typed identity + modality, which the native arms do NOT carry ----
    # Native ranking records are {target_id, arm_value, evaluable, rank} — no namespace, no
    # modality. Those two facts live ONLY in W3's bridge (spot.stage02_stage3_bridge.v1), which
    # its own independent verifier admits and which REBUILDS every row from the admitted native
    # bytes. Stage 3 binds the bridge; it never infers identity and never defaults a modality
    # from a config constant.
    ap.add_argument("--stage2-bridge", default=None,
                    help="v2: W3's stage3_bridge.json (spot.stage02_stage3_bridge.v1) — the "
                         "typed identity + modality the native arms do not carry")
    ap.add_argument("--stage2-bridge-report", default=None,
                    help="v2: stage3_bridge_verification.json — the SEPARATE bridge verifier's "
                         "report. Stage 3 admits the bridge from THIS, never from the bridge.")
    ap.add_argument("--artifact-class", required=True,
                    choices=list(ac.ARTIFACT_CLASSES),
                    help="analysis (a real computation) or fixture (synthetic; never "
                         "reaches Stage 4). The production/research namespaces are "
                         "retired.")
    # Required for the v1 (Direct run-directory) path, and validated below rather than by
    # argparse — the v2 path consumes admitted ARM BUNDLES and has no run directory to name.
    ap.add_argument("--direct-run", default=None,
                    help="v1: a Stage-2 Direct RUN DIRECTORY. There is no --lever-set.")
    ap.add_argument("--direct-inputs-root", default=None,
                    help="v1: the raw inputs the Direct run's files were pinned against")
    ap.add_argument("--cache-root", default=None)
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

    if args.v2:
        if not args.universe_store:
            ap.error("--v2 requires --universe-store: the admitted universe store is bound "
                     "by its exact store_id, and a run without it has no admitted store")
        return _v2_main(args)

    missing = [f for f, v in (("--direct-run", args.direct_run),
                              ("--direct-inputs-root", args.direct_inputs_root),
                              ("--cache-root", args.cache_root)) if not v]
    if missing:
        ap.error(f"the v1 Direct-run path requires {missing}")

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
