"""The v2 BUILD: arms x the admitted store -> edges, source records, dispositions, context.

Split from :mod:`druglink.edges_v2` (which owns ONE edge) at the 500-line gate — the same seam
the lane already draws between what a row IS and how the set of them is assembled. Re-exported
from ``edges_v2``, so a consumer still binds ONE module.

The orchestration is where the two lane rules live:
  * a MEASURED arm (Direct/temporal) yields edges, one per (typed target x rankable assertion);
  * a PATHWAY arm yields NONE, and says so by name — its records are gene-set enrichments, and
    the lane is not admitted (its verifier fails open).
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from . import direction as dr
from . import modality_v2 as mv2
from . import pathway_context_v2 as pc2
from . import stage2_aggregate as sa
from . import universe_rows as ur
from .assertions_v2 import moiety_id, rankable, source_record
from .dispositions_v2 import (
    STATE_NO_DRUG_EVIDENCE,
    STATE_NON_RANKABLE,
    STATE_NOT_IN_UNIVERSE,
    STATE_PATHWAY_IS_TYPED_CONTEXT,
    STATE_PATHWAY_LANE_NOT_ADMITTED,
    STATE_UNSUPPORTED_NAMESPACE,
    disposition,
)
from .edges_v2 import (
    ORIGIN_FOR_LANE,
    CandidatesV2Error,
    GATE_UNTYPED_TARGET,
    build_edge,
    check_edges,
)
from .hashing import short_id


def n_ranked(records: Iterable[Mapping[str, Any]]) -> int:
    """A count of RANKS, never a count of ROWS. Stage-2's retained-row semantics demand it.

    Stage 2 RETAINS every target with ``rank: null`` when it is not rankable, so "in the ranking"
    is NOT "in the rows". A consumer that counted rows would inflate every hit count by exactly
    the targets the arm could not evaluate — the ones LEAST entitled to support a claim.
    """
    return sum(1 for r in records if r.get("rank") is not None)


# --- 4. The build: arms x assertions -> edges, source records, dispositions. - #
def store_namespaces(store: ur.AdmittedStore) -> tuple[str, ...]:
    """The namespace tokens the ADMITTED STORE actually types its rows with. From the bytes."""
    return tuple(sorted({str(r["target_id_namespace"]) for r in store.rows}))


def typed_identity(arm: sa.LoadedArm, record: Mapping[str, Any],
                   store: ur.AdmittedStore) -> tuple[str, str]:
    """The record's typed identity: (target_id, STORE namespace), per row and GATED.

    The namespace is DECLARED on the row and mapped through the explicit token map. It is never
    defaulted from a release-level token and never guessed from the id's shape: the admitted
    universe is HETEROGENEOUS (Ensembl gene ids AND gene symbols), so one namespace stamped
    across every row would silently mistype every symbol in it.
    """
    tid = record.get("target_id")
    if not tid:
        raise CandidatesV2Error(
            GATE_UNTYPED_TARGET,
            f"arm {arm.arm_key!r} holds a record with target_id={tid!r}; a record with no "
            "target names nothing and can be joined to nothing")
    # The row's OWN token, asserted exactly and used VERBATIM in the join. No alias layer: if the
    # store spells its namespaces differently, that divergence is SURFACED, not translated away.
    namespace = mv2.namespace_of(record, arm_key=arm.arm_key)
    # The store's OWN tokens, read from its OWN rows — never a Stage-3 constant that could drift
    # from the bytes it describes. If the two vocabularies differ, that is SURFACED, not mapped.
    held = store_namespaces(store)
    mv2.check_store_namespace_vocabulary(held)
    mv2.check_namespace_against_store(
        str(tid), namespace, arm_key=arm.arm_key,
        # Every namespace the ADMITTED STORE actually holds THIS id under — asked of the store
        # itself, never assumed from the id's shape.
        store_namespaces=[n for n in held if store.row_for(str(tid), n) is not None])
    return str(tid), namespace


def _typed_targets(arms: Sequence[sa.LoadedArm],
                   store: ur.AdmittedStore) -> list[tuple[str, str]]:
    """The typed identities of the MEASURED arms. A pathway arm has no target rows to type."""
    return sorted({typed_identity(arm, rec, store)
                   for arm in arms
                   if ORIGIN_FOR_LANE[arm.lane] in dr.MEASURED_ORIGINS
                   for rec in arm.records})


def _target_dispositions(in_universe: list[tuple[str, str]],
                         by_target: dict[tuple[str, str], list[dict[str, Any]]],
                         store: ur.AdmittedStore) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tid, ns in in_universe:
        row = store.row_for(tid, ns) or {}
        if any(rankable(a) for a in by_target.get((tid, ns), ())):
            continue
        unsupported = row.get("disposition") == ur.DISP_UNSUPPORTED_NAMESPACE
        out.append(disposition(
            subject_kind="target", subject_id=f"{ns}:{tid}", target_id=tid,
            target_id_namespace=ns,
            state=(STATE_UNSUPPORTED_NAMESPACE if unsupported else STATE_NO_DRUG_EVIDENCE),
            reason=str(row.get("disposition")),
            detail=("this acquisition route cannot reach the target's namespace; that is "
                    "never an absence of drug evidence" if unsupported else
                    "the admitted store holds no general-gene rankable assertion for this "
                    "target")))
    return out


def build_edges(aggregate: sa.AdmittedAggregate,
                store: ur.AdmittedStore) -> dict[str, list[dict[str, Any]]]:
    """Every (reusable arm, typed origin, typed target, source assertion) edge — plus the
    source records they stand on, and a NAMED disposition for every absence."""
    digest = dr.vocabulary_digest()
    targets = _typed_targets(aggregate.arms, store)
    in_universe = [t for t in targets if store.row_for(t[0], t[1]) is not None]
    known = set(in_universe)

    dispositions = [
        disposition(subject_kind="target", subject_id=f"{ns}:{tid}", target_id=tid,
                    target_id_namespace=ns, state=STATE_NOT_IN_UNIVERSE,
                    reason=ur.GATE_TARGET_NOT_IN_ADMITTED_UNIVERSE,
                    detail="the admitted store covers a fixed typed universe; a target "
                           "outside it was never looked up, which is not an absence of drug "
                           "evidence")
        for tid, ns in targets if (tid, ns) not in known]

    assertions = ur.drug_edges_for_targets(
        store, [{"target_id": t, "target_id_namespace": ns} for t, ns in in_universe])
    by_target: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for assertion in assertions:
        by_target.setdefault((str(assertion["target_id"]),
                              str(assertion["target_id_namespace"])), []).append(assertion)

    dispositions += [
        disposition(subject_kind="source_assertion", subject_id=str(a.get("edge_id")),
                    source_record_id=a.get("edge_id"), candidate_id=moiety_id(a),
                    target_id=a.get("target_id"),
                    target_id_namespace=a.get("target_id_namespace"),
                    state=STATE_NON_RANKABLE, reason=str(a.get("lane")),
                    detail="preserved, and never rankable: a variant mechanism is evidence "
                           "about the variant, and a shared accession would make one "
                           "mechanism look like independent evidence for every gene it maps "
                           "to")
        for a in assertions if not rankable(a)]
    dispositions += _target_dispositions(in_universe, by_target, store)

    # The pathway arms, indexed by the EXACT typed identities in their leading edges. This is
    # the only thing a pathway record is allowed to do: contextualize a target somebody measured.
    pathways = pc2.index_by_target(aggregate.arms)

    edges: list[dict[str, Any]] = []
    for arm in aggregate.arms:
        # A PATHWAY ARM YIELDS NO DRUG EDGES, EVER — and says so, by name.
        #
        # Its records are gene-set enrichments, not per-target knockdown effects. Without this,
        # "pathway produced no drug evidence" and "pathway was never consulted" are the same
        # silence, and the next writer fills it by giving an enrichment value a sign.
        if ORIGIN_FOR_LANE[arm.lane] in dr.INFERRED_ORIGINS:
            dispositions.append(disposition(
                subject_kind="arm", subject_id=arm.arm_key, arm_key=arm.arm_key,
                origin_type=ORIGIN_FOR_LANE[arm.lane],
                state=(STATE_PATHWAY_IS_TYPED_CONTEXT if pc2.PATHWAY_LANE_ADMITTED
                       else STATE_PATHWAY_LANE_NOT_ADMITTED),
                reason=(mv2.GATE_INFERRED_ORIGIN_PRODUCED_A_DRUG_EDGE
                        if pc2.PATHWAY_LANE_ADMITTED
                        else pc2.GATE_PATHWAY_LANE_NOT_ADMITTED),
                detail=("a pathway record is a gene-set enrichment, not a measured per-target "
                        "knockdown effect: no CRISPRi sign, never rankable as measured support, "
                        "never a drug direction — a direction is not inherited from set "
                        "membership. " + ("" if pc2.PATHWAY_LANE_ADMITTED
                                          else pc2.PATHWAY_LANE_NOT_ADMITTED_REASON))))
            continue
        for rec in arm.records:
            key = typed_identity(arm, rec, store)
            for assertion in by_target.get(key, ()):
                if rankable(assertion):
                    edges.append(build_edge(
                        arm, rec, assertion, store=store, digest=digest, namespace=key[1],
                        # The pathway CONTEXTUALIZES this measured edge. It did not source it.
                        pathway_refs=pc2.refs_for(pathways, key[0], key[1])))

    check_edges(edges)
    # EVERY drug edge traces to a MEASURED target. Re-asserted on the emitted rows.
    pc2.check_edges_are_all_measured(edges, dr.INFERRED_ORIGINS)
    return {"target_drug_edges": edges,
            "pathway_context": pc2.build_context(
                pathways, measured_targets=in_universe, edges=edges, short_id=short_id),
            "source_records": dedup([source_record(a, store) for a in assertions],
                                    "source_record_id"),
            "dispositions": dedup(dispositions, "disposition_id")}


def dedup(rows: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    out: dict[Any, dict[str, Any]] = {}
    for row in rows:
        out[row[key]] = row
    return [out[k] for k in sorted(out, key=str)]
