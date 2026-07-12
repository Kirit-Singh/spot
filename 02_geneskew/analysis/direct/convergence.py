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
"""
from __future__ import annotations

import math
from typing import Any, Optional

METHOD_ID = "spot.stage02.pathway.signature_convergence.v1"
SIMILARITY_METRIC = "cosine_on_shared_unmasked_support"

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


def clusters(pairs: list[dict[str, Any]],
             targets: list[str]) -> dict[str, Optional[int]]:
    """Connected components over the SUPPORTIVE pairs. target -> cluster id (or None).

    Deterministic and seedless on purpose. k-means, Leiden and friends all need a seed, a
    k, or a resolution — three more knobs that change which pathways look convergent, and
    every one of them is a place to tune the answer after seeing it. Connected components
    over a frozen threshold has no such freedom: the graph is the graph.

    A target with no supportive partner is in no cluster (``None``), not in a cluster of
    one. A cluster of one is not a cluster; it is a target.
    """
    parent = {t: t for t in targets}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for p in pairs:
        if not p["supportive"]:
            continue
        ra, rb = find(p["target_a"]), find(p["target_b"])
        if ra != rb:
            parent[ra if ra > rb else rb] = rb if ra > rb else ra

    groups: dict[str, list[str]] = {}
    for t in targets:
        groups.setdefault(find(t), []).append(t)

    out: dict[str, Optional[int]] = {t: None for t in targets}
    cid = 1
    for root in sorted(groups, key=lambda r: sorted(groups[r])[0]):
        members = groups[root]
        if len(members) < MIN_PERTURBATIONS_FOR_CONVERGENCE:
            continue                       # a cluster of one is a target, not a cluster
        for t in members:
            out[t] = cid
        cid += 1
    return out


def converge_sets(bundle: dict[str, Any], signatures: dict[str, dict[str, float]],
                  pairs: list[dict[str, Any]],
                  cluster_of: dict[str, Optional[int]]) -> list[dict[str, Any]]:
    """Per gene set: which of its members were MEASURED, and did they converge?

    ``n_supporting_perturbations`` counts the set's members that share a cluster — i.e.
    that were shown to do the same thing. A set with exactly one measured member can
    never reach two, and is flagged ``single_target_support`` rather than dropped.
    """
    by_pair = {(p["target_a"], p["target_b"]): p for p in pairs}
    out = []

    for set_id in sorted(bundle["sets"]):
        s = bundle["sets"][set_id]
        measured = sorted(g for g in s["genes"] if g in signatures)

        # the set's own supportive pairs, and the clusters its members fall into
        internal = []
        for i, a in enumerate(measured):
            for b in measured[i + 1:]:
                p = by_pair.get((a, b)) or by_pair.get((b, a))
                if p is not None:
                    internal.append(p)
        supportive = [p for p in internal if p["supportive"]]

        member_clusters: dict[int, list[str]] = {}
        for t in measured:
            c = cluster_of.get(t)
            if c is not None:
                member_clusters.setdefault(c, []).append(t)
        best = max(member_clusters.items(), key=lambda kv: (len(kv[1]), -kv[0]),
                   default=(None, []))
        n_supporting = len(best[1])

        convergent = n_supporting >= MIN_PERTURBATIONS_FOR_CONVERGENCE
        single = len(measured) == 1

        out.append({
            "set_id": set_id,
            "method_id": METHOD_ID,
            "similarity_metric": SIMILARITY_METRIC,
            "similarity_threshold": SIMILARITY_THRESHOLD,
            "min_shared_unmasked_genes": MIN_SHARED_GENES,
            "rounding_rule": ROUNDING_RULE,
            "n_genes_in_set": s["n_genes"],
            "n_measured_perturbations": len(measured),
            "measured_perturbations": measured,
            "n_supporting_perturbations": n_supporting,
            "supporting_perturbations": sorted(best[1]),
            "cluster_id": best[0],
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
            "convergent": convergent,
            "single_target_support": single,
            "convergence_refused_reason": (
                None if convergent else
                SINGLE_TARGET_SUPPORT if single else
                "no_measured_perturbation" if not measured else
                "fewer_than_two_perturbations_converge"),
        })
    return out
