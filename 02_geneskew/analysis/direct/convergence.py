"""(B) PERTURBATION-SIGNATURE CONVERGENCE: do different knockdowns do the SAME thing?

Enrichment (A) asks whether a pathway's genes sit at the top of an arm's ranking. That is
a question about the RANKING. It can be answered by one strong target dragging its whole
pathway up behind it, and the pathway then looks like a mechanism when it is really one
gene with company.

This asks a different and harder question: take the FULL target-masked expression
signature of each perturbation — the whole effect vector, not the marker panel — and ask
whether perturbing DIFFERENT members of a pathway produces the SAME transcriptional
consequence. Convergence is evidence that the pathway is doing something. One target's
signature is evidence about that target.

WHY THE FULL SIGNATURE AND NOT THE PANEL
----------------------------------------
The marker panels are the axis the arms are scored on, so two targets that both move the
program will agree on the panel BY CONSTRUCTION — that is what "moves the program" means.
Agreement there is close to circular. The full signature includes everything the panels
do not, and it is where two knockdowns can be shown to do the same thing for reasons the
score never looked at, or to reach the same score by completely different routes.

THE MASK MATTERS, AND IT IS WHY THIS IS NOT A CORRELATION OF RAW VECTORS
-----------------------------------------------------------------------
Each signature has its OWN mask: the perturbed gene, its neighbourhood, and its guides'
off-target alignments are removed. Two targets therefore have different holes in their
vectors. Comparing them on the union of their measured genes would compare a gene one of
them never measured against a value the other one has, so the similarity is computed on
the INTERSECTION of the two unmasked supports, and the size of that intersection is
emitted with every pair. A similarity over eleven shared genes is not the same claim as
one over eleven thousand, and a reader must be able to tell them apart.

THE FROZEN METRIC
-----------------
Cosine similarity on the shared unmasked support, on the canonical float64 effect values.
Frozen, and chosen for a reason: it responds to the DIRECTION of the transcriptional
response and not to its magnitude, so a weak-but-identical knockdown and a strong one
converge — which is the biology we are asking about — while two strong responses in
different directions do not.

A CONVERGENCE CLAIM NEEDS AT LEAST TWO PERTURBATIONS
----------------------------------------------------
This is the load-bearing rule. A pathway "supported" by a single measured target is not
convergent; it is one experiment, and calling it a pathway result launders a single
observation into a mechanism. Such pathways are still EMITTED — with
``n_supporting_perturbations = 1`` and ``single_target_support = true`` — because deleting
them would hide how thin the evidence is. They are simply never called convergent.

SUPPORT IS INTRA-PATHWAY. IT MAY NEVER ROUTE THROUGH A NON-MEMBER
-----------------------------------------------------------------
The retired version clustered ALL perturbations globally and then asked which of a
pathway's members shared a global connected component. That is a different question, and
a false one: two members can land in the same global component while being connected ONLY
through a gene that is not in the pathway at all. The pathway is then reported convergent
on the strength of a similarity that neither member has to the other — a mechanism
fabricated out of a bridge.

So convergence is computed on the subgraph INDUCED BY THE SET'S OWN MEASURED MEMBERS.
Only supportive pairs whose BOTH endpoints are members of the set are edges. A non-member
is not evidence about the set, however similar it is to one of them, and there is no
global component anywhere in this module for one to hide in.
"""
from __future__ import annotations

import math
import multiprocessing as mp
from typing import Any, Optional

from . import genesets

# v3, not v2: convergence now enforces the already-frozen pathway-size domain. The v2
# pair builder silently computed giant GO root terms despite ``MAX_SET_SIZE=500`` and could
# call them convergent. A 10,371-gene "biological process" root is not a specific pathway.
METHOD_ID = "spot.stage02.pathway.signature_convergence.v3"
SIMILARITY_METRIC = "cosine_on_shared_unmasked_support"

# THE DEFINITION, and the restriction that makes it honest. Both enter the method hash:
# a run that quietly went back to global components would be answering a different
# question under the same id.
CONVERGENCE_DEFINITION = (
    "intra_pathway_largest_connected_component_over_supportive_pairs_in_the_subgraph_"
    "induced_by_the_gene_set_s_own_measured_members")
MEMBERSHIP_RESTRICTION = (
    "an_edge_counts_only_when_both_endpoints_are_members_of_the_set; a supportive pair "
    "to a non_member carries no support into the set and can never link two members")
SUPPORT_MAY_ROUTE_THROUGH_NON_MEMBERS = False

# A pair is SUPPORTIVE at or above this similarity. Frozen before any real signature was
# looked at; it is a threshold on a descriptive metric, not a significance cut.
SIMILARITY_THRESHOLD = 0.5

# ...and a pair computed over fewer shared genes than this says nothing at all. Two
# vectors always look similar on a handful of genes.
MIN_SHARED_GENES = 10

# The rule this module exists to enforce.
MIN_PERTURBATIONS_FOR_CONVERGENCE = 2
SINGLE_TARGET_SUPPORT = "single_target_support"

FLOAT_DECIMALS = 6
ROUNDING_RULE = "half_even_6dp"

# A scientific upper-bound rule, not an execution setting. It is repeated in the method
# block and every emitted set record, so removing or changing it moves the method/run
# identity. The convergence method's existing >=2 supporting-perturbation requirement is
# preserved separately; the enrichment lane's MIN_SET_SIZE=3 is not imported here.
CONVERGENCE_SIZE_POLICY_ID = (
    "spot.stage02.pathway.convergence_size_governance.prospective.v1")
CONVERGENCE_SIZE_BASIS = (
    "pathway_members_intersect_perturbation_target_universe_intersect_available_"
    "perturbation_signature_targets")
MAX_CONVERGENCE_SET_SIZE = genesets.MAX_SET_SIZE
SIZE_EVALUABLE = "evaluable"
SIZE_TOO_LARGE = "non_evaluable_set_too_large"
SIZE_DISPOSITIONS = (SIZE_EVALUABLE, SIZE_TOO_LARGE)

# Execution only: changing these does not change the statistic, its order, or its bytes.
# ``fork`` is required because the real signature dictionary is several GiB and pickling it
# into workers would both duplicate the scientific input and erase the speedup.  Production
# runs on Linux; callers elsewhere retain the serial default and fail closed if they request
# multiprocessing on a platform without fork.
DEFAULT_PAIRWISE_WORKERS = 1
DEFAULT_PAIR_CHUNK_SIZE = 500
PAIRWISE_EXECUTION_ID = "spot.stage02.convergence.ordered_fork_pair_chunks.v1"

_PAIRWISE_SIGNATURES: Optional[dict[str, dict[str, float]]] = None


class ConvergenceExecutionError(ValueError):
    """The requested execution topology cannot preserve the frozen computation."""


def _target_members(gene_set: dict[str, Any]) -> list[str]:
    """Members in the bound perturbation-target universe, with fixture compatibility."""
    values = gene_set.get("genes_in_target_universe")
    if values is None:
        values = gene_set.get("genes_target", [])
    return sorted(set(str(g) for g in values))


def convergence_size_disposition(
        gene_set: dict[str, Any], signatures: dict[str, dict[str, float]]) -> dict[str, Any]:
    """Re-derive whether a set is in the frozen convergence-size domain.

    The induced graph's endpoints are perturbation targets with an available signature.
    The DE-readout universe supplies the coordinates *inside* each signature; it is not the
    endpoint membership universe. Both the conservative target-universe count and the
    actual condition-specific endpoint count are emitted for independent reconstruction.
    """
    target_members = _target_members(gene_set)
    n_target_members = len(target_members)
    n_endpoints = sum(1 for gene in target_members if gene in signatures)
    if n_endpoints > MAX_CONVERGENCE_SET_SIZE:
        disposition = SIZE_TOO_LARGE
    else:
        disposition = SIZE_EVALUABLE
    return {
        "convergence_size_policy_id": CONVERGENCE_SIZE_POLICY_ID,
        "convergence_size_basis": CONVERGENCE_SIZE_BASIS,
        "max_convergence_set_size": MAX_CONVERGENCE_SET_SIZE,
        "n_genes_in_target_universe": n_target_members,
        "n_measured_convergence_endpoints": n_endpoints,
        "convergence_size_disposition": disposition,
        "convergence_evaluable": disposition == SIZE_EVALUABLE,
    }


def cosine_on_shared(vec_a: dict[str, float],
                     vec_b: dict[str, float]) -> tuple[Optional[float], int]:
    """Cosine similarity on the INTERSECTION of two masked supports.

    Returns ``(similarity, n_shared)``. ``None`` when the two signatures share too few
    measured genes to say anything, or when either is flat on the shared support — a
    zero vector has no direction, and calling its similarity 0.0 would report "unrelated"
    where the honest answer is "undefined".
    """
    shared = sorted(set(vec_a) & set(vec_b))
    n = len(shared)
    if n < MIN_SHARED_GENES:
        return None, n

    a = [vec_a[g] for g in shared]
    b = [vec_b[g] for g in shared]
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return None, n
    dot = sum(x * y for x, y in zip(a, b))
    return round(dot / (na * nb), FLOAT_DECIMALS), n


def pairwise(signatures: dict[str, dict[str, float]]) -> list[dict[str, Any]]:
    """Every unordered pair of measured signatures, with its shared support size."""
    targets = sorted(signatures)
    out = []
    for i, a in enumerate(targets):
        for b in targets[i + 1:]:
            sim, n_shared = cosine_on_shared(signatures[a], signatures[b])
            out.append({
                "target_a": a, "target_b": b,
                "similarity": sim,
                "n_shared_unmasked_genes": n_shared,
                "supportive": sim is not None and sim >= SIMILARITY_THRESHOLD,
                "similarity_metric": SIMILARITY_METRIC,
                "method_id": METHOD_ID,
            })
    return out


def _pair_record(pair: tuple[str, str],
                 signatures: dict[str, dict[str, float]]) -> dict[str, Any]:
    """One frozen pair record, shared by serial and process execution."""
    a, b = pair
    sim, n_shared = cosine_on_shared(signatures[a], signatures[b])
    return {
        "target_a": a, "target_b": b,
        "similarity": sim,
        "n_shared_unmasked_genes": n_shared,
        "supportive": sim is not None and sim >= SIMILARITY_THRESHOLD,
        "similarity_metric": SIMILARITY_METRIC,
        "method_id": METHOD_ID,
    }


def _pair_chunk(pairs: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """Fork worker. The signatures are inherited read-only; they are never pickled."""
    if _PAIRWISE_SIGNATURES is None:
        raise ConvergenceExecutionError(
            "ordered pair worker has no inherited signature dictionary")
    return [_pair_record(pair, _PAIRWISE_SIGNATURES) for pair in pairs]


def pairwise_within_sets(bundle: dict[str, Any],
                         signatures: dict[str, dict[str, float]], *,
                         workers: int = DEFAULT_PAIRWISE_WORKERS,
                         chunk_size: int = DEFAULT_PAIR_CHUNK_SIZE,
                         ) -> list[dict[str, Any]]:
    """Only the pairs a gene set can actually stand on: BOTH endpoints in the same set.

    After B1 these are the only pairs convergence ever reads — a cross-set pair cannot
    be an edge of any set's induced subgraph, so computing it would be work done to
    produce a number nothing is allowed to use.

    It is also what makes the production lane tractable: the all-pairs form is O(n^2)
    over every measured target (~11k targets is ~63M pairs), while the union of
    within-set pairs is bounded by the sets themselves.
    """
    wanted: set[tuple[str, str]] = set()
    for s in bundle["sets"].values():
        # Every set remains emitted by ``converge_sets``, but an out-of-domain set
        # contributes ZERO pair computations. A giant root cannot consume compute or
        # manufacture a convergence claim merely because it contains most genes.
        if not convergence_size_disposition(s, signatures)["convergence_evaluable"]:
            continue
        measured = sorted(g for g in _target_members(s) if g in signatures)
        for i, a in enumerate(measured):
            for b in measured[i + 1:]:
                wanted.add((a, b))

    if workers < 1:
        raise ConvergenceExecutionError("pairwise workers must be >= 1")
    if chunk_size < 1:
        raise ConvergenceExecutionError("pair chunk size must be >= 1")

    ordered = sorted(wanted)
    if workers == 1 or len(ordered) <= 1:
        return [_pair_record(pair, signatures) for pair in ordered]

    if "fork" not in mp.get_all_start_methods():
        raise ConvergenceExecutionError(
            "parallel convergence requires multiprocessing start method 'fork'; "
            "use workers=1 on this platform")

    chunks = [ordered[i:i + chunk_size]
              for i in range(0, len(ordered), chunk_size)]
    n_processes = min(workers, len(chunks))
    global _PAIRWISE_SIGNATURES
    if _PAIRWISE_SIGNATURES is not None:
        raise ConvergenceExecutionError(
            "parallel convergence is already active in this process")
    _PAIRWISE_SIGNATURES = signatures
    try:
        # map() returns in INPUT order. Each chunk is a contiguous slice of sorted pairs,
        # and flattening therefore reproduces the serial record order byte-for-byte even
        # when workers finish out of order.
        ctx = mp.get_context("fork")
        with ctx.Pool(processes=n_processes) as pool:
            results = pool.map(_pair_chunk, chunks, chunksize=1)
        return [record for chunk in results for record in chunk]
    finally:
        _PAIRWISE_SIGNATURES = None


def induced_components(members: list[str],
                       supportive_pairs: list[dict[str, Any]]
                       ) -> list[list[str]]:
    """Connected components over the subgraph INDUCED BY ``members``, largest first.

    Every edge here already has both endpoints in ``members`` — the caller selects them —
    so no component can be joined by a gene outside the set. That is the whole of the B1
    fix, and it is why this takes a member list rather than a global target list.

    Deterministic and seedless on purpose. k-means, Leiden and friends all need a seed, a
    k, or a resolution — three more knobs that change which pathways look convergent, and
    every one of them is a place to tune the answer after seeing it. Connected components
    over a frozen threshold has no such freedom: the graph is the graph.

    Singletons are not components. A member with no supportive partner INSIDE the set is
    not a cluster of one; it is a target.
    """
    parent = {m: m for m in members}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for p in supportive_pairs:
        a, b = p["target_a"], p["target_b"]
        if a not in parent or b not in parent:      # belt and braces: never a non-member
            continue
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra if ra > rb else rb] = rb if ra > rb else ra

    groups: dict[str, list[str]] = {}
    for m in members:
        groups.setdefault(find(m), []).append(m)

    components = [sorted(g) for g in groups.values()
                  if len(g) >= MIN_PERTURBATIONS_FOR_CONVERGENCE]
    # largest first; ties broken on the smallest member id, so the choice is total
    return sorted(components, key=lambda c: (-len(c), c[0]))


def converge_sets(bundle: dict[str, Any], signatures: dict[str, dict[str, float]],
                  pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per gene set: which of its members were MEASURED, and did they converge?

    ``n_supporting_perturbations`` counts the members of the set's LARGEST INTRA-PATHWAY
    component — members shown to do the same thing as each other. A set with exactly one
    measured member can never reach two, and is flagged ``single_target_support`` rather
    than dropped.

    There is no global cluster here to consult. A supportive pair between a member and a
    non-member is not an edge of this graph, so it cannot make two members look connected
    when their only link is a gene the pathway does not contain.
    """
    by_pair = {(p["target_a"], p["target_b"]): p for p in pairs}
    out = []

    for set_id in sorted(bundle["sets"]):
        s = bundle["sets"][set_id]
        size = convergence_size_disposition(s, signatures)
        # B1: a SIGNATURE exists only for a gene that was PERTURBED, so a set's candidate
        # members live in the PERTURBATION-TARGET universe — not the readout universe. The
        # readout universe is the space the signature VECTORS live in (the cosine is taken
        # over readout genes); it is not the space membership is decided in.
        measured = sorted(g for g in _target_members(s) if g in signatures)
        member_set = set(measured)

        # THE INDUCED SUBGRAPH: only pairs whose BOTH endpoints are members of this set.
        internal = []
        if size["convergence_evaluable"]:
            for i, a in enumerate(measured):
                for b in measured[i + 1:]:
                    p = by_pair.get((a, b)) or by_pair.get((b, a))
                    if p is not None:
                        internal.append(p)
        supportive = ([p for p in internal if p["supportive"]]
                      if size["convergence_evaluable"] else [])
        assert all(p["target_a"] in member_set and p["target_b"] in member_set
                   for p in supportive), "an edge escaped the membership restriction"

        components = (induced_components(measured, supportive)
                      if size["convergence_evaluable"] else [])
        best: list[str] = components[0] if components else []
        n_supporting = len(best)

        convergent = (size["convergence_evaluable"] and
                      n_supporting >= MIN_PERTURBATIONS_FOR_CONVERGENCE)
        single = len(measured) == 1

        n_source = s.get("n_source_symbols")
        n_target = size["n_genes_in_target_universe"]
        target_source_coverage = s.get("target_source_coverage")
        if target_source_coverage is None and n_source not in (None, 0):
            target_source_coverage = round(n_target / int(n_source), 6)
        coverage = genesets.coverage_disposition(target_source_coverage)

        out.append({
            "set_id": set_id,
            "method_id": METHOD_ID,
            "similarity_metric": SIMILARITY_METRIC,
            "similarity_threshold": SIMILARITY_THRESHOLD,
            "min_shared_unmasked_genes": MIN_SHARED_GENES,
            "rounding_rule": ROUNDING_RULE,
            # WHAT convergence means here, on the record that claims it
            "convergence_definition": CONVERGENCE_DEFINITION,
            "membership_restriction": MEMBERSHIP_RESTRICTION,
            "support_may_route_through_non_members":
                SUPPORT_MAY_ROUTE_THROUGH_NON_MEMBERS,
            "n_genes_in_set": s.get("n_genes_target", n_target),
            "n_source_symbols": n_source,
            "n_genes_in_target_universe": n_target,
            "target_source_coverage": target_source_coverage,
            "n_genes_in_readout_universe": s.get("n_genes_in_universe"),
            "readout_source_coverage": s.get("readout_source_coverage"),
            "global_coverage_disposition": coverage["global_coverage_disposition"],
            "global_coverage_policy_passed": coverage["global_coverage_policy_passed"],
            **size,
            "n_measured_perturbations": len(measured),
            "measured_perturbations": measured,
            "n_supporting_perturbations": n_supporting,
            "supporting_perturbations": list(best),
            # the set's OWN component structure. Not a global cluster id: there is none.
            "n_intra_set_components": len(components),
            "intra_set_components": components,
            "n_supportive_pairs": len(supportive),
            "pairwise_support": [
                {"target_a": p["target_a"], "target_b": p["target_b"],
                 "similarity": p["similarity"],
                 "n_shared_unmasked_genes": p["n_shared_unmasked_genes"]}
                for p in sorted(supportive,
                                key=lambda p: (p["target_a"], p["target_b"]))],
            # THE RULE. One measured perturbation is one experiment, and calling it a
            # pathway result launders an observation into a mechanism.
            "min_perturbations_for_convergence": MIN_PERTURBATIONS_FOR_CONVERGENCE,
            "convergence_claim_eligible": size["convergence_evaluable"],
            "convergent": convergent,
            "single_target_support": single,
            "convergence_refused_reason": (
                None if convergent else
                size["convergence_size_disposition"]
                if not size["convergence_evaluable"] else
                SINGLE_TARGET_SUPPORT if single else
                "no_measured_perturbation" if not measured else
                "fewer_than_two_perturbations_converge"),
        })
    return out
