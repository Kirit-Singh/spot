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
  * **THREE typed origins, separate** — ``direct_target`` (same-condition measured),
    ``temporal_cross_time_measured`` (cross-time DiD measured — a DISTINCT estimand) and
    ``endpoint_pathway_context`` (inferred). Measured and inferred live in separate
    collections and never share a row; Direct and temporal are never fused.

    (This paragraph previously read "Direct/temporal -> direct_target; pathway ->
    pathway_node" — the very fusion a1d8958 removed, left behind in the prose. A docstring
    that describes the defect the code just fixed will be believed by the next reader over
    the code, so it is corrected here rather than carried forward.)
  * **Arbitrary ordered axes/conditions** — same-time ``{condition}``; cross-time ordered
    ``{from_condition, to_condition}`` (from != to), preserved verbatim on every lever.
  * **Direction compatibility** — carried per arm (``desired_change`` + modulation); a
    pathway node's direction is NEVER inherited from membership.
  * **Exact Stage-2 admission hashes** — every lane binds an ``ExternalAdmission`` /
    independent ``verification_ref``; no default, no ``admitted=True`` path (no self-admission).
  * **No combined score** — arms are independent; counts are per-lane, never pooled.
  * **No fixture fallback** — a lane with no admitted bundle stays EMPTY; nothing is invented.
  * **Production consumption GATED BY AN ARTIFACT** — a production run must present a
    Stage-2 aggregate admitted FROM DISK (``stage2_aggregate.admit_aggregate``): manifest
    re-hashed, an INDEPENDENT report binding those exact manifest bytes, and the full
    15-bundle / 300-arm-slot topology reconstructed from the bundles root. No real
    candidates until such an aggregate exists.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from . import arm_query as aq
from . import pathway_bridge as pb
from . import stage2_aggregate as sa
from .direction import ORIGIN_DIRECT_TARGET

LOADER_SCHEMA = "spot.stage03_v2_input_loader.v1"
LOADER_METHOD_ID = "spot.stage03.v2_input_loader.v1"

# THREE typed origins, stamped explicitly on every row so no consumer ever infers from
# time_scope. Direct (same-condition) and temporal (cross-time DiD) are BOTH measured but
# are DISTINCT estimands and MUST NOT be fused; pathway is the inferred endpoint context.
ORIGIN_DIRECT_SAME_TIME = ORIGIN_DIRECT_TARGET             # "direct_target"
ORIGIN_TEMPORAL_CROSS_TIME = "temporal_cross_time_measured"
ORIGIN_ENDPOINT_PATHWAY = "endpoint_pathway_context"
MEASURED_ORIGINS = frozenset({ORIGIN_DIRECT_SAME_TIME, ORIGIN_TEMPORAL_CROSS_TIME})


class V2InputLoaderError(ValueError):
    """Admitted Stage-2 inputs and the v2 loader contract do not agree."""


class ProductionConsumptionGated(V2InputLoaderError):
    """The independent detached-clone matrix is not green; no real candidates yet."""


def _measured_origin(ctx: dict[str, Any]) -> str:
    """direct_target for same-condition, temporal_cross_time_measured for cross-time DiD.
    The origin is decided HERE from the bundle's own context and stamped on the row, so a
    consumer never has to read time_scope to tell Direct from temporal."""
    return (ORIGIN_TEMPORAL_CROSS_TIME if ctx["time_scope"] == aq.CROSS_TIME
            else ORIGIN_DIRECT_SAME_TIME)


def _load_measured_bundle(bundle: dict[str, Any],
                          admission: Optional[aq.ExternalAdmission]):
    """One admitted Direct/temporal arm bundle -> measured levers, origin-typed by time
    scope (Direct and temporal are DISTINCT origins, never fused)."""
    adm = aq.require_external_admission(bundle, admission)   # no self-admission, no default
    origin = _measured_origin(aq.arm_context(bundle))
    levers: list[dict[str, Any]] = []
    for arm in bundle.get("arms", []):
        for row in aq.normalize_arm(arm, bundle=bundle, admission=adm):
            levers.append(dict(row, origin_type=origin, measured_evidence=True))
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
            "origin_type": ORIGIN_ENDPOINT_PATHWAY,
            "measured_evidence": False,
            "node_class": node_class,
            "arm_rank": None, "arm_direction_measured": False,
            **resolved})
    return out


def _assert_origins_never_merge(measured: list[dict[str, Any]],
                                pathway: list[dict[str, Any]]) -> None:
    for lever in measured:
        ot = lever.get("origin_type")
        if ot not in MEASURED_ORIGINS:
            raise V2InputLoaderError(
                f"measured lever {lever.get('target_id')!r} has non-measured origin {ot!r}")
        if lever.get("measured_evidence") is not True:
            raise V2InputLoaderError(
                f"measured lever {lever.get('target_id')!r} not flagged measured_evidence")
        # the origin must AGREE with the row's own time scope — Direct and temporal fused
        # into one origin is exactly the defect this asserts against.
        ts = lever.get("time_scope")
        if ts == aq.CROSS_TIME and ot != ORIGIN_TEMPORAL_CROSS_TIME:
            raise V2InputLoaderError(
                f"cross-time row {lever.get('target_id')!r} stamped {ot!r}: Direct and "
                "temporal must never be fused")
        if ts == aq.SAME_TIME and ot != ORIGIN_DIRECT_SAME_TIME:
            raise V2InputLoaderError(
                f"same-time row {lever.get('target_id')!r} stamped {ot!r}")
    for n in pathway:
        if n.get("origin_type") != ORIGIN_ENDPOINT_PATHWAY:
            raise V2InputLoaderError(
                f"pathway node {n.get('target_id')!r} is not an endpoint_pathway_context "
                "origin")
        if n.get("measured_evidence") is not False:
            raise V2InputLoaderError(
                f"pathway node {n.get('target_id')!r} must not be flagged measured")
        if n.get("arm_rank") is not None:      # an inferred node with a measured rank
            raise V2InputLoaderError(
                f"pathway node {n.get('target_id')!r} carries a measured arm rank")


GATE_NO_ADMITTED_AGGREGATE: str = "a_production_run_has_no_admitted_stage2_aggregate"


def _aggregate_binding(admitted: Optional[sa.AdmittedAggregate]) -> Optional[dict[str, Any]]:
    """Name the exact aggregate that opened the production gate, by its own bytes.

    ``aggregate_verifier_id`` is Stage-2's PINNED aggregate verifier
    (``spot.stage02.run_manifest.verifier.v1``). Its name does not contain the word
    "independent" and never did — independence is asserted by the structured field
    ``generator_is_not_verifier``, which ``admit_aggregate`` binds. A substring in an id is
    not a binding.
    """
    if admitted is None:
        return None
    return {
        "manifest_raw_sha256": admitted.manifest_raw_sha256,
        "manifest_canonical_sha256": admitted.manifest_canonical_sha256,
        # the producer's SEMANTIC self-hash, re-derived by Stage 3 from the manifest bytes
        "manifest_self_hash": admitted.manifest_self_hash,
        "stage1_release_sha256": admitted.stage1_release_sha256,
        "aggregate_verifier_id": admitted.verifier_id,
        "verifier_id": admitted.verifier_id,      # retained: the same pinned identity
        "verdict": admitted.verdict,
        # STAGE-3's own class. Stage 2 declares no artifact_class, and never did.
        "artifact_class": admitted.artifact_class,
        "n_bundles": len(admitted.bundles),
        "n_arms": len(admitted.arms),
    }


def _require_admitted_aggregate(admitted: Optional[sa.AdmittedAggregate]) -> None:
    """A production run must present a Stage-2 aggregate ADMITTED FROM DISK.

    This replaces the module constant `arm_query.DETACHED_CLONE_MATRIX_GREEN`, which was a
    Boolean literal in Stage-3's own source. Nothing an upstream lane could produce, and no
    artifact on disk, could ever flip it — only a Stage-3 edit could, so the "gate" recorded
    a Stage-3 intention rather than an upstream fact, and it would have gone on reporting
    green with no admitted bundle behind it.

    The gate is now the ARTIFACT, and specifically STAGE-2's OWN ADMISSION:
    ``admit_aggregate`` re-derives the manifest's semantic self-hash, requires the pinned
    aggregate verifier's report to ADMIT exactly those bytes (verdict=admit, n_failed=0,
    topology_complete, release_admissible, admission.status=admitted, and
    generator_is_not_verifier=true), and reconstructs the full 15-bundle / 300-slot topology
    from the bundles root. A fixture cannot produce that report out of Stage-2's real
    verifier, which is what makes it a gate rather than a label.

    THE CLASS FIREWALL IS NOT THIS GATE. This function used to end with an unconditional
    ``require_analysis(admitted)``, so a run declaring ``--artifact-class fixture`` was ALSO
    required to be an analysis, and refused at ``a_fixture_aggregate_cannot_enter_the_analysis_path``.
    That is wrong twice over: it made a fixture run impossible to execute at all, and it invited
    the one thing the firewall exists to prevent — relabelling a synthetic aggregate "analysis"
    just to get it to run.

    A fixture aggregate must be able to emit a FIXTURE bundle (which is barred from Stage 4 by
    its class), while an ANALYSIS still requires a genuinely admitted production aggregate. So
    the class check belongs where the class is DECLARED — ``bundle_v2.build_document`` already
    does it, conditionally, and that is the only place it should live. This gate answers one
    question only: is there an admitted Stage-2 aggregate at all?
    """
    if admitted is None:
        raise ProductionConsumptionGated(
            f"[{GATE_NO_ADMITTED_AGGREGATE}] a production run requires a Stage-2 aggregate "
            "admitted from disk (druglink.stage2_aggregate.admit_aggregate); Stage 3 will "
            "not serve a production run or generate real candidates without one")


def load_admitted_stage2_inputs(
    *,
    direct_arm_bundle: Optional[dict[str, Any]] = None,
    direct_admission: Optional[aq.ExternalAdmission] = None,
    temporal_arm_bundles: Sequence = (),        # ordered list of (bundle, ExternalAdmission)
    pathway_arm_bundle: Optional[dict[str, Any]] = None,
    pathway_nodes: Sequence[dict[str, Any]] = (),
    measured_target_ids: Optional[set] = None,
    require_production: bool = False,
    admitted_aggregate: Optional[sa.AdmittedAggregate] = None,
) -> dict[str, Any]:
    """Unified admitted-Stage-2 input load. Typed origins separate; ordered axes preserved;
    admission hashes bound; no combined score / fixture fallback / self-admission."""
    if require_production:
        _require_admitted_aggregate(admitted_aggregate)

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
        # origin_type is direct_target OR temporal_cross_time_measured — two DISTINCT
        # measured estimands, stamped explicitly, never fused into one
        "measured_levers": measured,
        # origin_type == endpoint_pathway_context — INFERRED, and a separate collection:
        # measured and inferred never share a row
        "pathway_nodes": pathway,
        "typed_origins": {
            "same_condition_direct": ORIGIN_DIRECT_SAME_TIME,
            "temporal_cross_time_measured": ORIGIN_TEMPORAL_CROSS_TIME,
            "endpoint_pathway_context": ORIGIN_ENDPOINT_PATHWAY,
            "direct_and_temporal_never_fused": True,
            "gene_and_pathway_evidence_are_never_merged": True,
            "origin_stamped_explicitly_no_downstream_time_scope_inference": True},
        "admission_binding": admission_binding,
        "arms_are_independent": True,
        "combined_objective_permitted": False,
        "headline_arm_permitted": False,
        # Gated is now a FACT about the inputs, not a constant in Stage-3's source: it is
        # true exactly when no Stage-2 aggregate was admitted from disk. The binding names
        # WHICH aggregate opened the gate, so the claim is checkable against the bytes.
        "production_consumption_gated": admitted_aggregate is None,
        "stage2_aggregate_binding": _aggregate_binding(admitted_aggregate),
        "counts": {"n_measured_levers": len(measured), "n_pathway_nodes": len(pathway),
                   "per_lane": per_lane},
    }
