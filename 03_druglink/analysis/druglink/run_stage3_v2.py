"""The Stage-3 v2 CLI path: admit Stage-2 AND its bridge from disk, then EMIT.

Split out of ``run_stage3`` (which breached the 500-line project gate) at the seam the module
already had: v1 consumes a Direct RUN DIRECTORY; v2 consumes an ADMITTED Stage-2 AGGREGATE plus
the BRIDGE carrying the typed identity and modality the native arms do not have.

THE CHAIN, AND WHY EACH LINK EXISTS
-----------------------------------
    1. admit the AGGREGATE from disk    manifest re-hashed, a SEPARATE report admitting those
                                        exact bytes, the full topology rebuilt from the bundles
    2. admit the BRIDGE from disk       the native ranking says {target_id, arm_value, evaluable,
                                        rank} and NOTHING about who the target is or what was done
                                        to it. Only the bridge does. It is re-hashed, its SEPARATE
                                        report and the RECEIPT must admit these exact bytes over
                                        THIS aggregate, and every row is checked against the
                                        native ranking: it may ADD identity and modality, and may
                                        never CHANGE a measurement.
    3. JOIN                             native measurement + bridge identity -> typed records
    4. open the admitted UNIVERSE STORE and derive the typed universe from its OWN rows
    5. EMIT                             a content-addressed v2 bundle, written atomically
    6. (with --selection) PROJECT       the selection view, and the MEMBERSHIP RECEIPT that proves
                                        the membership gate RAN over those exact bytes

Nothing here is a Boolean. The old ``DETACHED_CLONE_MATRIX_GREEN`` was a constant in Stage-3's own
source that no upstream artifact could ever flip, and the old bridge gate was a
``hasattr``-shaped confession that the consumer did not exist. Both are gone: the gate is the
ARTIFACT, and every refusal below names the bytes that failed it.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from . import admitted_universe, arm_query as aq, artifacts_v2
from . import artifacts as v1
from . import membership_receipt as mr
from . import selection_v3 as s3
from . import selection_view as sv
from . import stage2_aggregate as sa
from . import stage2_contract as C
from . import universe_rows, v2_input_loader as v2
from . import view_contract as vc


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

VIEW_FILE = "selection_view.json"
RECEIPT_FILE = "membership_receipt.json"


def bridge_consumer_ready() -> bool:
    """Can Stage-3 actually ADMIT and CONSUME the bridge (not merely accept its path)?

    Yes. ``stage2_aggregate.admit_bridge`` re-hashes the bridge's raw and canonical bytes,
    re-derives its self-hash, requires the SEPARATE bridge verifier's report to have judged THOSE
    bytes, requires the receipt to bind them to the aggregate this run admitted, and checks every
    typed row against the native ranking it claims to have been rebuilt from.

    This is NOT an artifact-admission gate and never becomes one — an artifact gate must never be
    a Boolean in Stage-3's own source; that was ``DETACHED_CLONE_MATRIX_GREEN``. It reports one
    fact about THIS module, for the test that greps for the admitter.
    """
    return hasattr(sa, "admit_bridge")


def _emit_view(*, args, aggregate, bridge, emitted) -> Optional[dict[str, Any]]:
    """The selection view + the MEMBERSHIP RECEIPT, bound to the bundle just written.

    The receipt is emitted by the membership verifier, whose id differs from the producer's — a
    producer that verifies its own output has not been verified — and it is then RE-VERIFIED here
    from its own bytes on disk. Both land INSIDE the bundle, so ``view.path`` in the receipt is
    bundle-relative: an absolute path names a place on one machine, not an artifact.
    """
    selection = s3.load(args.selection)
    admission = sv.admit_receipt(args.stage2_bridge_receipt, aggregate=aggregate,
                                 report_path=args.stage2_report)
    # The Stage-2 run manifest itself — it carries the producer's own role x pole map, which the
    # arm resolver checks its derivation against, and the Stage-1 release the question must match.
    manifest, _ = C.load_json(args.stage2_manifest, "Stage-2 aggregate run manifest")
    view = sv.materialize(
        selection=selection, aggregate=aggregate, document=emitted["document"],
        tables=emitted["tables"], manifest=manifest,
        admission=admission, bundle_dir=emitted["bundle_dir"])
    vc.validate(dict(view))

    bundle_dir = emitted["bundle_dir"]
    view_path = os.path.join(bundle_dir, VIEW_FILE)
    v1.write_json(view_path, view)
    receipt = mr.emit(view_path=view_path, bundle_dir=bundle_dir)
    mr.write(receipt, os.path.join(bundle_dir, RECEIPT_FILE))
    # RE-VERIFIED FROM THE BYTES, never from the dict we just built.
    mr.verify(receipt, bundle_dir=bundle_dir)
    return {"selection": selection, "view": view, "receipt": receipt,
            "view_path": view_path, "bridge": bridge}


def _v2_main(args) -> int:
    """The v2 path: admit Stage-2 AND its bridge from disk, open the store, EMIT a bundle."""
    missing = [f for f in V2_REQUIRED if not getattr(args, f[2:].replace("-", "_"), None)]
    if missing:
        print(f"REFUSED [{args.artifact_class}]: --v2 requires {', '.join(missing)}. There is "
              "no fixture fallback and no default: Stage 3 stands on Stage-2's admitted "
              "aggregate, its admitted bridge and the admitted universe store, or it does not "
              "run.")
        return 2

    try:
        aggregate = sa.admit_aggregate(
            manifest_path=args.stage2_manifest, report_path=args.stage2_report,
            bundles_root=args.bundles_root, stage1_release_path=args.stage1_release,
            artifact_class=args.artifact_class)
        # THE BRIDGE. Without it the native arms carry no target namespace and no perturbation
        # modality, and an analysis built without it would have to INVENT identity and DEFAULT a
        # modality from a config constant — a setting wearing the costume of an assay.
        bridge = sa.admit_bridge(
            bridge_path=args.stage2_bridge, report_path=args.stage2_bridge_report,
            receipt_path=args.stage2_bridge_receipt, aggregate=aggregate,
            aggregate_report_path=args.stage2_report)
        typed = sa.bind_bridge(aggregate, bridge)

        store = universe_rows.load_store(args.universe_store)
        loaded = load_v2_inputs(
            universe_store=args.universe_store,
            # the REAL typed universe, derived from the store's own rows — never []
            universe_targets=store.typed_universe,
            require_production=True, admitted_aggregate=typed)
        emitted = artifacts_v2.emit(
            output_root=args.output_root, artifact_class=args.artifact_class,
            aggregate=typed, store=store, report_path=args.stage2_report, bridge=bridge)
        projected = (_emit_view(args=args, aggregate=typed, bridge=bridge, emitted=emitted)
                     if getattr(args, "selection", None) else None)
    except (admitted_universe.AdmittedUniverseError, v2.V2InputLoaderError,
            sa.Stage2AggregateError, sa.Stage2BridgeError, universe_rows.UniverseRowsError,
            aq.ArmQueryError, s3.SelectionError, sv.ViewRefusal,
            vc.ViewContractError) as exc:
        print(f"REFUSED [{args.artifact_class}]: {exc}")
        print("no bundle was written. Stage 3 does not fabricate candidates: a synthetic "
              "number in a bundle is a synthetic number on its way to Stage 4.")
        return 3

    binding = loaded["universe_store_binding"]
    tables = emitted["tables"]
    print(f"stage2_aggregate {aggregate.manifest_self_hash[:16]}… "
          f"admitted_by={aggregate.verifier_id} verdict={aggregate.verdict}")
    print(f"                 {len(aggregate.bundles)} bundles / {len(aggregate.arms)} arm slots")
    print(f"stage3_bridge    {bridge.bridge_self_hash[:16]}… "
          f"admitted_by={bridge.verifier_id} verdict={bridge.verdict}")
    print(f"                 {bridge.counts['n_target_rows']} typed target rows / "
          f"{bridge.counts['n_pathway_contexts']} pathway contexts (CONTEXT ONLY)")
    print(f"universe_store   {binding['store_id'][:16]}… "
          f"({len(store.typed_universe)} typed targets)")
    print(f"bundle           {emitted['bundle_id']}")
    print(f"                 {emitted['bundle_dir']}")
    for name in sorted(tables):
        print(f"  {name:<28} {len(tables[name])}")
    if projected:
        view = projected["view"]
        rows = view.get("rows") or {}
        print(f"selection        {projected['selection'].selection_id} "
              f"question={projected['selection'].question_id}")
        print(f"view             {view.get('view_id')}")
        for name in sorted(rows):
            print(f"  {name:<28} {len(rows[name])}")
        print(f"membership       verdict={projected['receipt']['verdict']} "
              f"generator={projected['receipt']['generator_id']}")
        print(f"                 verifier={projected['receipt']['verifier_id']}")
        print(f"                 receipt_sha256={projected['receipt']['receipt_sha256']}")
    print("origins counted SEPARATELY; no combined objective; pathway is CONTEXT and never "
          "sources a drug edge.")
    return 0
