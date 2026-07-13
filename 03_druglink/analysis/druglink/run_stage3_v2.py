"""The Stage-3 v2 CLI path: admit Stage-2 from disk, then EMIT.

Split out of ``run_stage3`` (which breached the 500-line project gate) at the seam the module
already had: v1 consumes a Direct RUN DIRECTORY; v2 consumes an ADMITTED Stage-2 AGGREGATE plus
the bridge carrying the typed identity and modality the native arms do not have.

Behaviour is unchanged — this is a move, not a rewrite.
"""
from __future__ import annotations

from typing import Any, Optional

from . import admitted_universe, arm_query as aq, artifacts_v2
from . import stage2_aggregate as sa
from . import universe_rows, v2_input_loader as v2

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


V2_REQUIRED = ("--stage2-manifest", "--stage2-report", "--bundles-root", "--stage1-release",
               "--universe-store", "--stage2-bridge", "--stage2-bridge-report",
               "--stage2-bridge-receipt")

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


