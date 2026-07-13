"""THE PATHWAY RECORD: the full evidence table, and what Claude Science may do with it.

One record per gene set. It carries BOTH lines of evidence side by side, never fused:

  * per-ARM enrichment (``enrichment.py``): does this pathway sit at the top of ONE arm's
    ranking? Emitted once per arm, with the leading edge that produced it. Never summed
    across arms — a pathway enriched in ``away_from_A`` and depleted in ``toward_B`` is a
    finding, and any single "pathway score" would erase exactly that;

  * signature CONVERGENCE (``convergence.py``): do different knockdowns of this pathway's
    members produce the SAME transcriptional consequence? Requires >= 2 measured
    perturbations, or it is not a convergence claim at all.

They answer different questions and they can disagree. A pathway can be enriched with no
convergence (one strong target dragging its members up behind it) or convergent with no
enrichment (its members agree with each other and none of them is near the top). Both
disagreements are informative and both survive into the record intact.

EVERY SET IS EMITTED
--------------------
Including the ones that were never testable — too small, too large, no measured member.
A pathway missing from the table is indistinguishable from one that was tested and found
nothing, and the difference between "not asked" and "asked and no" is the whole of an
honest negative result.

WHAT CLAUDE SCIENCE MAY DO
--------------------------
Interpret, annotate, prioritise, write it up. It may attach typed evidence references —
each one an id, a hash and a record type, so a claim can be traced to the thing it came
from.

It may NOT change a primary rank. Not either arm's rank, not a Pareto tier, not an
enrichment value, not a convergence verdict. Those are measurements; an interpretation
that can quietly edit its own evidence is not an interpretation. The schema enforces this
by construction: there is no writable field here that any ranking reads.
"""
from __future__ import annotations

from typing import Any, Optional

from . import config, convergence, enrichment, genesets
from .hashing import content_hash

SCHEMA_VERSION = "spot.stage02_pathway_record.v1"
METHOD_ID = "spot.stage02.pathway.v1"

# The two evidence lines, named. They are never combined into one number.
EVIDENCE_ENRICHMENT = "ranked_arm_enrichment"
EVIDENCE_CONVERGENCE = "signature_convergence"
EVIDENCE_LINES = (EVIDENCE_ENRICHMENT, EVIDENCE_CONVERGENCE)

# What a Claude Science evidence reference must BE. Typed, hashed, resolvable: a
# free-text citation is not evidence, it is a promise that evidence exists.
SCIENCE_EVIDENCE_FIELDS = ("science_evidence_id", "sha256", "record_type")
SCIENCE_RECORD_TYPES = ("literature", "database", "analysis", "annotation")

# The one thing Claude Science may never touch.
SCIENCE_MAY_INTERPRET = True
SCIENCE_MAY_CHANGE_PRIMARY_RANKS = False
PRIMARY_RANK_FIELDS = (
    list(config.ARM_RANK_COLUMN.values()) + list(config.ARMS)
    + ["pareto_tier", "joint_status"])


def method_block(bundle: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Which methods, at which versions, over which pinned gene-set release."""
    return {
        "method_id": METHOD_ID,
        "pathway_method_version": SCHEMA_VERSION,
        "enrichment_method_id": enrichment.METHOD_ID,
        "enrichment_statistic_name": enrichment.STATISTIC_NAME,
        "enrichment_rounding_rule": enrichment.ROUNDING_RULE,
        "convergence_method_id": convergence.METHOD_ID,
        "similarity_metric": convergence.SIMILARITY_METRIC,
        "similarity_threshold": convergence.SIMILARITY_THRESHOLD,
        "min_shared_unmasked_genes": convergence.MIN_SHARED_GENES,
        "min_perturbations_for_convergence":
            convergence.MIN_PERTURBATIONS_FOR_CONVERGENCE,
        "convergence_size_policy_id": convergence.CONVERGENCE_SIZE_POLICY_ID,
        "convergence_size_basis": convergence.CONVERGENCE_SIZE_BASIS,
        "max_convergence_set_size": convergence.MAX_CONVERGENCE_SET_SIZE,
        # B1: WHAT convergence means, and the restriction that keeps it honest. Bound
        # into the hash so a run cannot go back to global components under this id.
        "convergence_definition": convergence.CONVERGENCE_DEFINITION,
        "convergence_membership_restriction": convergence.MEMBERSHIP_RESTRICTION,
        "convergence_support_may_route_through_non_members":
            convergence.SUPPORT_MAY_ROUTE_THROUGH_NON_MEMBERS,
        # M1: which end of the ranking a leading edge is taken from, and in which
        # direction. A negative enrichment's edge is its TRAILING edge.
        "enrichment_leading_edge_convention": enrichment.LEADING_EDGE_CONVENTION,
        "enrichment_edge_is_direction_aware": enrichment.EDGE_IS_DIRECTION_AWARE,
        "evidence_lines": list(EVIDENCE_LINES),
        "evidence_lines_are_combined": False,
        # B1: WHICH UNIVERSE each computation tests membership in. Bound into the method
        # hash: a run that swapped them would answer a different question under this id,
        # and that swap is exactly the bug this binding exists to make impossible.
        "enrichment_membership_universe": "perturbation_target",
        "convergence_membership_universe": "perturbation_target",
        "convergence_signature_vector_space": "de_readout",
        "two_universes_are_bound_separately": True,
        # B4: the PROSPECTIVE coverage governance, frozen before any result.
        "coverage_policy_id": genesets.COVERAGE_POLICY_ID,
        "min_source_coverage": genesets.MIN_SOURCE_COVERAGE,
        "min_arm_ranked_members": genesets.MIN_ARM_RANKED_MEMBERS,
        "coverage_namespace": genesets.COVERAGE_NAMESPACE,
        "arm_eligibility_is_independent_per_arm": True,
        "combined_arm_eligibility_permitted": False,
        "inference_status": enrichment.INFERENCE_STATUS,
        "no_pq_reason": enrichment.NO_PQ_REASON,
        "gene_sets": genesets.binding_block(bundle),
    }


def build_records(rows: list[dict[str, Any]], bundle: Optional[dict[str, Any]],
                  signatures: dict[str, dict[str, float]],
                  config_sha256: str,
                  pairs: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    """The FULL pathway evidence table. Absent bundle -> an explicit unavailable state.

    ``pairs`` may be supplied by the production runner. Absent, this function computes
    only the in-domain INTRA-SET pairs itself. The old fixture shortcut computed every
    global pair and could therefore bypass the frozen set-size domain.
    """
    if bundle is None:
        return {
            "schema_version": SCHEMA_VERSION,
            "method": method_block(None),
            "pathway_layer_available": False,
            "n_records": 0,
            "records": [],
        }

    per_arm = {arm: {e["set_id"]: e for e in enrichment.enrich_arm(rows, bundle, arm)}
               for arm in config.ARMS}
    if pairs is None:
        pairs = convergence.pairwise_within_sets(bundle, signatures)
    # NO global clustering. Each set's convergence is computed on the subgraph induced by
    # its OWN members, so a non-member can never bridge two of them (B1).
    conv = {c["set_id"]: c
            for c in convergence.converge_sets(bundle, signatures, pairs)}

    records = []
    for set_id in sorted(bundle["sets"]):
        s = bundle["sets"][set_id]
        c = conv[set_id]
        records.append({
            "schema_version": SCHEMA_VERSION,
            "set_id": set_id,
            "set_name": s["name"],
            "gene_set_release": bundle["gene_set_release"],
            "gene_id_namespace": bundle["gene_id_namespace"],
            "effect_universe_sha256": bundle["effect_universe_sha256"],
            "direct_config_sha256": config_sha256,
            "n_genes_in_set": s["n_genes_target"],
            "n_genes_in_universe": s["n_genes_in_target_universe"],
            "coverage": s["coverage"],
            # B1: BOTH universes, side by side. The statistic is computed in the TARGET
            # space; the readout space is what the signature vectors live in.
            "n_genes_in_target_universe": s["n_genes_in_target_universe"],
            "n_genes_in_readout_universe": s["n_genes_in_universe"],
            "target_source_coverage": s["target_source_coverage"],
            "readout_source_coverage": s["readout_source_coverage"],
            # A2: the record carries the GLOBAL disposition — a property of the pathway
            # and the assay. It is NECESSARY for a headline arm result and never
            # SUFFICIENT, and it deliberately does NOT imply that either arm, let alone
            # both, may be ranked. That question is per-arm and lives in the arm blocks.
            "global_coverage_disposition": s["global_coverage_disposition"],
            "global_coverage_policy_passed": s["global_coverage_policy_passed"],
            # THE RE-KEYING DENOMINATOR. For a bundle re-keyed symbol -> Ensembl, the
            # members that could not be mapped were already removed, so `coverage` above
            # is 1.0 by construction. `source_coverage` is the fraction of the genes the
            # pathway ORIGINALLY NAMED that this experiment could actually measure — the
            # number a reader needs before believing anything about this set. Null for a
            # bundle that was never re-keyed; an absent loss is not a zero loss.
            "n_source_symbols": s["n_source_symbols"],
            "n_dropped_unmappable": (
                None if s["n_source_symbols"] is None
                else s["n_source_symbols"] - s["n_genes_in_target_universe"]),
            "source_coverage": s["source_coverage"],
            # BOTH lines, side by side. Never fused.
            "enrichment": {arm: _enrichment_block(per_arm[arm][set_id])
                           for arm in config.ARMS},
            "convergence": _convergence_block(c),
            # Claude Science may attach these. It may attach nothing else.
            "science_evidence_refs": [],
            "science_may_change_primary_ranks": SCIENCE_MAY_CHANGE_PRIMARY_RANKS,
        })

    return {
        "schema_version": SCHEMA_VERSION,
        "method": method_block(bundle),
        "pathway_layer_available": True,
        "n_records": len(records),
        "n_convergent": sum(1 for r in records if r["convergence"]["convergent"]),
        "n_single_target_support": sum(
            1 for r in records if r["convergence"]["single_target_support"]),
        "records": records,
        "records_sha256": content_hash(records),
    }


def _enrichment_block(e: dict[str, Any]) -> dict[str, Any]:
    """One arm's enrichment, with everything needed to reproduce or refute it."""
    return {
        "enrichment_value": e["enrichment_value"],
        "statistic_name": e["statistic_name"],
        "method_id": e["method_id"],
        "rounding_rule": e["rounding_rule"],
        "leading_edge": e["leading_edge"],
        "n_leading_edge": e["n_leading_edge"],
        # M1: WHICH end of the ranking this edge came from. A negative enrichment's
        # members are at the bottom, and the record says so rather than shipping an
        # empty list beside a real score.
        "leading_edge_side": e["leading_edge_side"],
        "leading_edge_convention": e["leading_edge_convention"],
        "n_hits_in_ranking": e["n_hits_in_ranking"],
        "n_ranked": e["n_ranked"],
        "peak_rank": e["peak_rank"],
        "testable": e["testable"],
        # A2 — PER-ARM ELIGIBILITY. `testable` says the statistic is defined; these say
        # whether a RANKING is allowed to speak for the pathway IN THIS ARM. Global
        # coverage alone never authorises that: a set can clear the global bar and still
        # have exactly one of its members in this arm's ranking.
        "n_source_symbols": e["n_source_symbols"],
        "global_target_source_coverage": e["global_target_source_coverage"],
        "arm_evaluable_source_coverage": e["arm_evaluable_source_coverage"],
        "arm_coverage_disposition": e["arm_coverage_disposition"],
        "arm_headline_rankable": e["arm_headline_rankable"],
        "arm_undefined_reason": e["arm_undefined_reason"],
        "undefined_reason": e["undefined_reason"],
        "inference_status": e["inference_status"],
        "no_pq_reason": e["no_pq_reason"],
    }


def _convergence_block(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "convergent": c["convergent"],
        "convergence_claim_eligible": c["convergence_claim_eligible"],
        "convergence_evaluable": c["convergence_evaluable"],
        "convergence_size_policy_id": c["convergence_size_policy_id"],
        "convergence_size_basis": c["convergence_size_basis"],
        "max_convergence_set_size": c["max_convergence_set_size"],
        "convergence_size_disposition": c["convergence_size_disposition"],
        "n_measured_convergence_endpoints": c["n_measured_convergence_endpoints"],
        "n_measured_perturbations": c["n_measured_perturbations"],
        "measured_perturbations": c["measured_perturbations"],
        "n_supporting_perturbations": c["n_supporting_perturbations"],
        "supporting_perturbations": c["supporting_perturbations"],
        "single_target_support": c["single_target_support"],
        "min_perturbations_for_convergence": c["min_perturbations_for_convergence"],
        # the set's OWN component structure. There is no global cluster id, by design.
        "n_intra_set_components": c["n_intra_set_components"],
        "intra_set_components": c["intra_set_components"],
        "convergence_definition": c["convergence_definition"],
        "membership_restriction": c["membership_restriction"],
        "support_may_route_through_non_members":
            c["support_may_route_through_non_members"],
        "n_supportive_pairs": c["n_supportive_pairs"],
        "pairwise_support": c["pairwise_support"],
        "similarity_metric": c["similarity_metric"],
        "similarity_threshold": c["similarity_threshold"],
        "min_shared_unmasked_genes": c["min_shared_unmasked_genes"],
        "method_id": c["method_id"],
        "rounding_rule": c["rounding_rule"],
        "convergence_refused_reason": c["convergence_refused_reason"],
    }


def validate_science_evidence(refs: Any) -> list[dict[str, Any]]:
    """A Science evidence reference is an id, a hash and a type. Or it is refused.

    Free text is not a citation. A reference nobody can resolve to exact bytes cannot be
    checked, cannot be contested, and will be believed anyway because it looks like one.
    """
    if not isinstance(refs, list):
        raise ValueError("science_evidence_refs must be a list")
    out = []
    for i, ref in enumerate(refs):
        if not isinstance(ref, dict):
            raise ValueError(f"science_evidence_refs[{i}] must be an object")
        missing = [k for k in SCIENCE_EVIDENCE_FIELDS if not ref.get(k)]
        if missing:
            raise ValueError(
                f"science_evidence_refs[{i}] is missing {missing}; an evidence "
                "reference that cannot be resolved to exact bytes is a promise that "
                "evidence exists, not evidence")
        if ref["record_type"] not in SCIENCE_RECORD_TYPES:
            raise ValueError(
                f"science_evidence_refs[{i}]: record_type must be one of "
                f"{list(SCIENCE_RECORD_TYPES)}, got {ref['record_type']!r}")
        out.append({k: ref[k] for k in SCIENCE_EVIDENCE_FIELDS})
    return out
