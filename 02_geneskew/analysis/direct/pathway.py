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
        "evidence_lines": list(EVIDENCE_LINES),
        "evidence_lines_are_combined": False,
        "inference_status": enrichment.INFERENCE_STATUS,
        "no_pq_reason": enrichment.NO_PQ_REASON,
        "gene_sets": genesets.binding_block(bundle),
    }


def build_records(rows: list[dict[str, Any]], bundle: Optional[dict[str, Any]],
                  signatures: dict[str, dict[str, float]],
                  config_sha256: str) -> dict[str, Any]:
    """The FULL pathway evidence table. Absent bundle -> an explicit unavailable state."""
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
    pairs = convergence.pairwise(signatures)
    cluster_of = convergence.clusters(pairs, sorted(signatures))
    conv = {c["set_id"]: c
            for c in convergence.converge_sets(bundle, signatures, pairs, cluster_of)}

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
            "n_genes_in_set": s["n_genes"],
            "n_genes_in_universe": s["n_genes_in_universe"],
            "coverage": s["coverage"],
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
        "n_hits_in_ranking": e["n_hits_in_ranking"],
        "n_ranked": e["n_ranked"],
        "peak_rank": e["peak_rank"],
        "testable": e["testable"],
        "undefined_reason": e["undefined_reason"],
        "inference_status": e["inference_status"],
        "no_pq_reason": e["no_pq_reason"],
    }


def _convergence_block(c: dict[str, Any]) -> dict[str, Any]:
    return {
        "convergent": c["convergent"],
        "n_measured_perturbations": c["n_measured_perturbations"],
        "measured_perturbations": c["measured_perturbations"],
        "n_supporting_perturbations": c["n_supporting_perturbations"],
        "supporting_perturbations": c["supporting_perturbations"],
        "single_target_support": c["single_target_support"],
        "min_perturbations_for_convergence": c["min_perturbations_for_convergence"],
        "cluster_id": c["cluster_id"],
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
