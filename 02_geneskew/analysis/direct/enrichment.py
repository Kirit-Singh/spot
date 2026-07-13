"""(A) RANKED-ARM ENRICHMENT: which pathways sit at the top of ONE arm's ranking.

The question, stated exactly: for arm X, rank every eligible target by its measured arm
score; do the genes of pathway P concentrate at the top of that ranking?

ONE STATISTIC PER ARM, NEVER ACROSS ARMS
----------------------------------------
The two arms are ranked separately and enriched separately, and the results are emitted
side by side, never summed. A pathway enriched in ``away_from_A`` and depleted in
``toward_B`` is a FINDING — targets in it move away from A while opposing B — and any
single "pathway score" would erase precisely that. Same rule as the screen: no combined
objective, at any layer.

THE STATISTIC
-------------
A weighted running-sum enrichment score (Kolmogorov–Smirnov style), computed on the
ranked target list:

    walk the ranking from rank 1 down;
    a HIT (target in P)  adds  |score_i|^w / sum(|score_j|^w for j in hits)
    a MISS               subtracts  1 / (N - N_hits)
    ES = the running sum's greatest deviation from zero, keeping its sign.

The LEADING EDGE is the set of members actually responsible for the score. It is emitted
in full, because "pathway P is enriched" is not a claim anyone can check, whereas "these
six of its genes are the ones at the top" is.

THE EDGE IS DIRECTION-AWARE, AND IT HAS TO BE
---------------------------------------------
A POSITIVE score is produced by members at the TOP: its edge is the hits at or before the
positive peak.

A NEGATIVE score is produced by members at the BOTTOM, and taking "the hits at or before
the peak" there is exactly wrong. The running sum descends to its trough on a run of
MISSES, so at the trough no hit has been seen yet and that rule returns an EMPTY edge —
the layer reports a score of -1.0 with no gene behind it. A negative enrichment's edge is
its TRAILING edge: the hits that fall AFTER the trough, which are the members sitting at
the bottom of the ranking and the reason the sum went there.

The invariant, either way: a DEFINED enrichment always names the members responsible for
it. A score nobody is standing behind is a score nobody can check or refute.

NO P-VALUE. NO q. NO FDR.
-------------------------
The usual ES comes with a permutation null. We do not have a calibrated one: the arm
scores are masked program projections with no null model in this lane
(``inference_status = not_calibrated``), and permuting targets would test a hypothesis
about the ranking's shape, not about the biology, while producing a number that LOOKS
like a p-value and would be read as one within a week.

So the statistic is emitted as a magnitude with its coverage and its leading edge, and
nothing here is significance. It ranks pathways for a human to look at; it does not
decide which are real. Emitting a p we cannot stand behind would be worse than emitting
none, and this lane already refuses that trade everywhere else.
"""
from __future__ import annotations

from typing import Any, Optional

from . import config, genesets

# v2, not v1: the leading edge is now direction-aware. A negative enrichment that used to
# come back with an empty edge now names the members at the bottom that produced it, so
# the emitted record genuinely changes and the method changes with it.
METHOD_ID = "spot.stage02.pathway.ranked_arm_enrichment.v2"
STATISTIC_NAME = "weighted_running_sum_enrichment_score"

# WHICH END of the ranking an edge is taken from. Emitted per record and bound into the
# method hash: two runs that disagree about this disagree about which genes a pathway
# result is made of.
EDGE_TOP = "top_leading_edge_at_or_before_the_positive_peak"
EDGE_BOTTOM = "bottom_trailing_edge_after_the_negative_trough"
EDGE_SIDES = (EDGE_TOP, EDGE_BOTTOM)
LEADING_EDGE_CONVENTION = (
    "positive_enrichment -> hits at or before the positive peak (top leading edge); "
    "negative_enrichment -> hits after the negative trough (bottom trailing edge). A "
    "defined enrichment always names a non-empty edge.")
EDGE_IS_DIRECTION_AWARE = True

# The exponent on the score magnitude in the running sum. w = 1 weights a hit by how far
# the target actually moved; w = 0 would make it a plain hit-count and throw the effect
# sizes away. Frozen.
SCORE_WEIGHT = 1.0

ROUNDING_RULE = "half_even_6dp"
FLOAT_DECIMALS = 6

# Why there is no p/q here, as an id a consumer resolves rather than a paragraph it reads.
INFERENCE_STATUS = config.INFERENCE_STATUS          # "not_calibrated"
NO_PQ_REASON = "no_calibrated_null_for_this_enrichment_statistic"


def _round(x: Optional[float]) -> Optional[float]:
    return None if x is None else round(float(x), FLOAT_DECIMALS)


def rank_targets(rows: list[dict[str, Any]], arm: str) -> list[tuple[str, float]]:
    """One arm's eligible targets, best first. The SAME population the arm ranks.

    Eligibility is the arm's own: evaluable, with a non-null finite score. A target the
    arm could not score is not a zero — it is absent, and it contributes to neither the
    hits nor the misses. Ties break on target_id so the walk is deterministic.
    """
    pole = config.ARM_POLE[arm]
    eligible = []
    for r in rows:
        if not bool(r.get(f"{pole}_evaluable")):
            continue
        v = r.get(arm)
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f != f or f in (float("inf"), float("-inf")):
            continue
        eligible.append((str(r["target_id"]), f))
    return sorted(eligible, key=lambda t: (-t[1], t[0]))


def enrich_one(ranked: list[tuple[str, float]], set_genes: set[str]) -> dict[str, Any]:
    """The running-sum ES and its leading edge, for ONE set against ONE arm's ranking."""
    n = len(ranked)
    hits = [(g, v) for g, v in ranked if g in set_genes]
    n_hits = len(hits)
    if n == 0 or n_hits == 0 or n_hits == n:
        # No ranking, no members in it, or nothing BUT members: in each case the statistic
        # is undefined rather than zero, and saying zero would claim "no enrichment".
        return {"enrichment_value": None, "leading_edge": [],
                "n_leading_edge": 0, "leading_edge_side": None,
                "n_hits_in_ranking": n_hits, "n_ranked": n, "peak_rank": None,
                "undefined_reason": ("empty_ranking" if n == 0 else
                                     "no_set_gene_in_ranking" if n_hits == 0 else
                                     "every_ranked_target_is_a_set_gene")}

    hit_mass = sum(abs(v) ** SCORE_WEIGHT for _g, v in hits)
    if hit_mass == 0:
        return {"enrichment_value": None, "leading_edge": [], "n_leading_edge": 0,
                "leading_edge_side": None, "n_hits_in_ranking": n_hits, "n_ranked": n,
                "peak_rank": None,
                "undefined_reason": "every_set_gene_scored_exactly_zero"}

    miss_step = 1.0 / (n - n_hits)
    running = 0.0
    peak, peak_rank = 0.0, 0
    seen_hits: list[str] = []
    edge_at_peak: list[str] = []

    for i, (gene, value) in enumerate(ranked, start=1):
        if gene in set_genes:
            running += (abs(value) ** SCORE_WEIGHT) / hit_mass
            seen_hits.append(gene)
        else:
            running -= miss_step
        if abs(running) > abs(peak):
            peak, peak_rank = running, i
            # the TOP edge: the hits seen at or before this rank
            edge_at_peak = list(seen_hits)

    # THE DIRECTION-AWARE EDGE (M1). A positive score is made by the members at the top,
    # so its edge is the hits at or before the peak. A negative score is made by the
    # members at the BOTTOM: the sum reached its trough on a run of misses, so no hit has
    # been seen there and the top-edge rule returns an empty list. Its edge is the
    # TRAILING edge — the hits after the trough, which are the reason it went down.
    if peak < 0:
        edge = [g for i, (g, _v) in enumerate(ranked, start=1)
                if g in set_genes and i > peak_rank]
        side = EDGE_BOTTOM
    else:
        edge = edge_at_peak
        side = EDGE_TOP

    return {
        "enrichment_value": _round(peak),
        # The members actually responsible for the score. "Pathway P is enriched" is not
        # checkable; "these are its genes at the bottom, in rank order" is.
        "leading_edge": edge,
        "n_leading_edge": len(edge),
        "leading_edge_side": side,
        "n_hits_in_ranking": n_hits,
        "n_ranked": n,
        "peak_rank": peak_rank,
        "undefined_reason": None,
    }


def enrich_arm(rows: list[dict[str, Any]], bundle: dict[str, Any],
               arm: str) -> list[dict[str, Any]]:
    """Every gene set, against ONE arm's ranking. Untestable sets are emitted too."""
    ranked = rank_targets(rows, arm)
    out = []
    for set_id in sorted(bundle["sets"]):
        s = bundle["sets"][set_id]
        # B1: THE ARMS RANK PERTURBED TARGETS, so membership is tested in the
        # PERTURBATION-TARGET universe. Testing it in the readout universe — which is what
        # this did — made 2,029 perturbed targets permanently ineligible to be a member of
        # any pathway: they could top the ranking and never count as a hit.
        genes = set(s["genes_target"])
        n_in = len(s["genes_in_target_universe"])
        testable = bundle["min_set_size"] <= n_in <= bundle["max_set_size"]

        result: dict[str, Any]
        if not testable:
            # EMITTED, not dropped. Silently omitting a set hides which pathways were
            # never tested, and a reader cannot tell "not enriched" from "never asked".
            result = {"enrichment_value": None, "leading_edge": [], "n_leading_edge": 0,
                      "leading_edge_side": None,
                      "n_hits_in_ranking": 0, "n_ranked": len(ranked),
                      "peak_rank": None,
                      "undefined_reason": ("set_too_small_to_test"
                                           if n_in < bundle["min_set_size"]
                                           else "set_too_large_to_be_specific")}
        else:
            result = enrich_one(ranked, genes)

        out.append({
            "set_id": set_id,
            "arm": arm,
            "statistic_name": STATISTIC_NAME,
            "method_id": METHOD_ID,
            "rounding_rule": ROUNDING_RULE,
            "score_weight": SCORE_WEIGHT,
            "leading_edge_convention": LEADING_EDGE_CONVENTION,
            "edge_is_direction_aware": EDGE_IS_DIRECTION_AWARE,
            "n_genes_in_set": s["n_genes_target"],
            "n_genes_in_universe": s["n_genes_in_target_universe"],
            "coverage": s["coverage"],
            "n_source_symbols": s["n_source_symbols"],
            "global_target_source_coverage": s["target_source_coverage"],
            "testable": testable,
            # A2: the GLOBAL disposition — necessary, never sufficient.
            "global_coverage_disposition": s["global_coverage_disposition"],
            "global_coverage_policy_passed": s["global_coverage_policy_passed"],
            # ...and THIS ARM's own eligibility, computed on the members THIS ARM ranked.
            # The arms are independent: no combined eligibility, no combined score.
            "n_ranked": len(ranked),
            **genesets.arm_disposition(
                global_policy_passed=s["global_coverage_policy_passed"],
                n_hits_in_ranking=result["n_hits_in_ranking"],
                enrichment_value=result["enrichment_value"],
                n_source_symbols=s["n_source_symbols"]),
            "arm_undefined_reason": result["undefined_reason"],
            "inference_status": INFERENCE_STATUS,
            "no_pq_reason": NO_PQ_REASON,
            **result,
        })
    return out
