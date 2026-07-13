"""The unified Stage-3 v2 input loader.

Stage-3 today ingests only a same-time Direct *run directory* + an optional pathway
*document*. Temporal is refused (``join_semantics.admit_gene_arm_source``), and the reusable
arm-bundle contracts (``arm_query``, ``pathway_bridge``) that hold the v2 design are unwired.

This loader is the one entry point that consumes **admitted** Stage-2 evidence for all three
lanes — Direct (same-time) + temporal (cross-time, ordered from→to) + pathway-supported —
and returns TYPED, ORIGIN-SEPARATED levers. It owns none of the science; it dispatches to
``arm_query`` (measured levers) and ``pathway_bridge`` (inferred nodes) and reconciles their
typed origins into one projection where **measured and inferred never merge**.

Hard invariants (each reused from the lane modules, asserted here across lanes):
  * **Typed origins separate** — Direct/temporal → ``direct_target``; pathway → ``pathway_node``.
    They live in separate collections and never share a row.
  * **Arbitrary ordered axes/conditions** — same-time ``{condition}``; cross-time ordered
    ``{from_condition, to_condition}`` (from != to), preserved verbatim on every lever.
  * **Direction compatibility** — carried per arm (``desired_change`` + modulation); a
    pathway node's direction is NEVER inherited from membership.
  * **Exact Stage-2 admission hashes** — every lane binds an ``ExternalAdmission`` /
    independent ``verification_ref``; no default, no ``admitted=True`` path (no self-admission).
  * **No combined score** — arms are independent; counts are per-lane, never pooled.
  * **No fixture fallback** — a lane with no admitted bundle stays EMPTY; nothing is invented.
  * **Production consumption GATED** — while the independent detached-clone matrix is not
    green (``arm_query.DETACHED_CLONE_MATRIX_GREEN``), the loader will not serve a production
    run: no real candidates until a real admitted Stage-2 bundle exists.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from . import arm_query as aq
from . import pathway_bridge as pb
from .direction import ORIGIN_DIRECT_TARGET, ORIGIN_PATHWAY_NODE

LOADER_SCHEMA = "spot.stage03_v2_input_loader.v1"
LOADER_METHOD_ID = "spot.stage03.v2_input_loader.v1"


class V2InputLoaderError(ValueError):
    """Admitted Stage-2 inputs and the v2 loader contract do not agree."""


class ProductionConsumptionGated(V2InputLoaderError):
    """The independent detached-clone matrix is not green; no real candidates yet."""


def _load_measured_bundle(bundle: dict[str, Any],
                          admission: Optional[aq.ExternalAdmission]):
    """One admitted Direct/temporal arm bundle -> measured (direct_target) levers."""
    adm = aq.require_external_admission(bundle, admission)   # no self-admission, no default
    levers: list[dict[str, Any]] = []
    for arm in bundle.get("arms", []):
        for row in aq.normalize_arm(arm, bundle=bundle, admission=adm):
            levers.append(dict(row, origin_type=ORIGIN_DIRECT_TARGET))
    return levers, adm


def _load_pathway_nodes(bundle: dict[str, Any], nodes: Sequence[dict[str, Any]],
                        measured_target_ids: Optional[set]) -> list[dict[str, Any]]:
    """Admitted pathway arm bundle + its nodes -> inferred (pathway_node) records."""
    pb.require_admitted_bundle(bundle)          # independent verifier, no self-admission
    mids = set(measured_target_ids or set())
    out: list[dict[str, Any]] = []
    for node in nodes:
        node_class = pb.classify(node, measured_target_ids=mids)
        if node_class == pb.MEASURED_LEVER:
            # This set member is ALSO a measured target: it is not a pathway hypothesis.
            # Its direction is carried by its measured lever (in measured_levers), never the
            # set. We do not resolve a pathway direction for it.
            resolved: dict[str, Any] = {
                "desired_target_modulation": None, "direction_provenance": None,
                "may_improve_drug_ordering": None,
                "note": "measured target; direction carried by its measured lever, "
                        "not by this set membership"}
        else:
            resolved = pb.resolve_direction(node, node_class=node_class)
        out.append({
            "target_id": node.get("target_id"),
            "target_id_namespace": node.get("target_id_namespace"),
            "set_id": node.get("set_id"),
            "origin_type": ORIGIN_PATHWAY_NODE,
            "node_class": node_class,
            "arm_rank": None, "arm_direction_measured": False,
            **resolved})
    return out


def _assert_origins_never_merge(measured: list[dict[str, Any]],
                                pathway: list[dict[str, Any]]) -> None:
    for l in measured:
        if l.get("origin_type") != ORIGIN_DIRECT_TARGET:
            raise V2InputLoaderError(
                f"measured lever {l.get('target_id')!r} is not a direct_target origin")
    for n in pathway:
        if n.get("origin_type") != ORIGIN_PATHWAY_NODE:
            raise V2InputLoaderError(
                f"pathway node {n.get('target_id')!r} is not a pathway_node origin")
        if n.get("arm_rank") is not None:      # an inferred node with a measured rank
            raise V2InputLoaderError(
                f"pathway node {n.get('target_id')!r} carries a measured arm rank")


def load_admitted_stage2_inputs(
    *,
    direct_arm_bundle: Optional[dict[str, Any]] = None,
    direct_admission: Optional[aq.ExternalAdmission] = None,
    temporal_arm_bundles: Sequence = (),        # ordered list of (bundle, ExternalAdmission)
    pathway_arm_bundle: Optional[dict[str, Any]] = None,
    pathway_nodes: Sequence[dict[str, Any]] = (),
    measured_target_ids: Optional[set] = None,
    require_production: bool = False,
) -> dict[str, Any]:
    """Unified admitted-Stage-2 input load. Typed origins separate; ordered axes preserved;
    admission hashes bound; no combined score / fixture fallback / self-admission."""
    gated = not aq.DETACHED_CLONE_MATRIX_GREEN
    if require_production and gated:
        raise ProductionConsumptionGated(
            "the independent detached-clone matrix is not green; Stage 3 will not serve a "
            "production run or generate real candidates until a real admitted Stage-2 "
            "bundle exists")

    measured: list[dict[str, Any]] = []
    admission_binding: dict[str, Any] = {"direct": None, "temporal": [], "pathway": None}
    per_lane: dict[str, Any] = {"direct": None, "temporal": [], "pathway": None}

    if direct_arm_bundle is not None:
        levers, adm = _load_measured_bundle(direct_arm_bundle, direct_admission)
        measured.extend(levers)
        admission_binding["direct"] = adm.as_binding()
        per_lane["direct"] = {"n_levers": len(levers),
                              "context": aq.arm_context(direct_arm_bundle)}

    for pair in temporal_arm_bundles:
        bundle, adm_in = pair
        ctx = aq.arm_context(bundle)
        if ctx.get("from_condition") == ctx.get("to_condition"):
            raise V2InputLoaderError(
                "a temporal axis must be an ORDERED pair (from_condition != to_condition)")
        levers, adm = _load_measured_bundle(bundle, adm_in)
        measured.extend(levers)
        admission_binding["temporal"].append(adm.as_binding())
        per_lane["temporal"].append({"n_levers": len(levers), "context": ctx})

    pathway: list[dict[str, Any]] = []
    if pathway_arm_bundle is not None:
        pathway = _load_pathway_nodes(pathway_arm_bundle, pathway_nodes, measured_target_ids)
        admission_binding["pathway"] = {
            "verifier_id": (pathway_arm_bundle.get("verification_ref") or {}).get(
                "verifier_id")}
        per_lane["pathway"] = {"n_nodes": len(pathway)}

    _assert_origins_never_merge(measured, pathway)

    return {
        "schema_version": LOADER_SCHEMA, "method_id": LOADER_METHOD_ID,
        "measured_levers": measured,        # origin_type == direct_target
        "pathway_nodes": pathway,           # origin_type == pathway_node — SEPARATE
        "typed_origins": {
            "measured": ORIGIN_DIRECT_TARGET, "inferred": ORIGIN_PATHWAY_NODE,
            "gene_and_pathway_evidence_are_never_merged": True},
        "admission_binding": admission_binding,
        "arms_are_independent": True,
        "combined_objective_permitted": False,
        "headline_arm_permitted": False,
        "production_consumption_gated": gated,
        "counts": {"n_measured_levers": len(measured), "n_pathway_nodes": len(pathway),
                   "per_lane": per_lane},
    }
