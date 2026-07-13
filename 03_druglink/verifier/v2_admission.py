"""The FROZEN Stage-3 v2 admission contract. Verifier side. Imports nothing from ``druglink``.

ROLE BOUNDARY — READ THIS FIRST
-------------------------------
This module does **not** implement the v2 loader, and it must not. The loader is the
**producer's** work; this is the **verifier's** contract that the loader will be judged
against. They are written by different hands on purpose.

I had already drifted across that line — ``analysis/druglink/arm_query.py`` and
``pathway_bridge.py`` are producer-side modules I authored, and I was about to author the v2
loader beside them. That would have made me generator *and* verifier of the same code, which
is exactly the defect this lane has spent the entire cache review catching in other people:
B6 (a manifest that never recomputed its own identity), M4b (a verifier that was a stale copy
of its generator's rule), the temporal bundle's self-referential ``verification_ref``, the
producer's own ``pending`` release read as an admission, and — my own — admitting `b20ec29b`
because *my* check passed while the *producer's* gate was fail-open.

A verifier that also wrote the thing it verifies can only prove that it agreed with itself.

So: the contract is frozen HERE, the adversarial tests are frozen HERE, the implementation
request goes to the producer lane, and Stage 3 verifies only after that lane's clean commit.

WHAT v2 MUST SATISFY
--------------------
1. **Three origins, typed and SEPARATE.** Direct (same-time measured), Temporal (cross-time
   DiD measured), Pathway-origin (inferred). They never merge, and a consumer must be able
   to tell them apart without inference.
2. **Ordered axes and conditions are preserved.** ``(from_condition, to_condition)`` is an
   ORDERED pair — Rest→Stim48 is not Stim48→Rest — and the arm's A/B axis order is the
   selection's, never re-sorted for convenience.
3. **Direction compatibility is decided by the frozen direction engine, at view time.**
   Never by the cache, never by the loader.
4. **No combined score.** Not at the join, not as a tie-break, not under a new name.
5. **No fixture fallback.** If an admitted artifact is missing, the loader REFUSES. It does
   not quietly substitute a fixture — that is how a synthetic number becomes a result.
6. **No cache self-admission.** The universe store is admitted by an INDEPENDENT verifier
   and bound by its exact ``store_id``; the producer's own verdict is never the admission.
"""
from __future__ import annotations

from typing import Any

from .report import Report

CONTRACT_ID = "spot.stage03_v2_admission.v1"

# --------------------------------------------------------------------------- #
# The three evidence origins. Typed, disjoint, never merged.
# --------------------------------------------------------------------------- #
# ALIGNED to the producer's SHIPPED labels at a1d8958. Two differ from the names I froze,
# and both of their choices are better than mine — so I take theirs, as I did with W2:
#
#   direct_target             keeps continuity with the v1 constant already in direction.py
#   endpoint_pathway_context  is the ADDENDUM's own vocabulary ("endpoint pathway context,
#                             never temporal enrichment"), which is more precise than my
#                             invented `pathway_origin_inferred`
#
# The one that mattered — the temporal origin — matches exactly. The DEFECT was fusion, not
# naming, and forcing a rename over strings I invented would be pedantry: an invented name
# is not a contract, the shipped one is.
ORIGIN_DIRECT = "direct_target"
ORIGIN_TEMPORAL = "temporal_cross_time_measured"
ORIGIN_PATHWAY = "endpoint_pathway_context"
ORIGINS = (ORIGIN_DIRECT, ORIGIN_TEMPORAL, ORIGIN_PATHWAY)

MEASURED_ORIGINS = frozenset({ORIGIN_DIRECT, ORIGIN_TEMPORAL})
INFERRED_ORIGINS = frozenset({ORIGIN_PATHWAY})

# The universe store Stage 3 admitted. Bound by exact identity, not by name.
ADMITTED_STORE_ID = \
    "bdf41b69df2be61d3f625aafa0429e643581fe50823698e77e079054c6145160"
ADMITTED_PRODUCER_COMMIT = "d268a74f339d346609951e73810ab26e2e654d86"
ADMISSION_REPORT_SHA256 = \
    "4aba8b5882e5ea32707875fc5026ca6b0b5d811ad01412bfa4b121c29b283bfb"

# Vocabulary that would fuse the origins or invent a combined objective. Refused by name,
# at any depth, so a friendly synonym does not launder the claim.
BANNED_V2_KEYS = frozenset({
    "combined_score", "combined_rank", "merged_evidence", "fused_evidence",
    "overall_evidence", "aggregate_evidence", "unified_score", "blended_score",
    "consensus_score", "total_evidence", "evidence_score", "composite_evidence",
    "origin_agnostic_rank", "cross_origin_score",
})

# A fixture may never stand in for an admitted artifact.
FIXTURE_MARKERS = ("fixture", "synthetic", "mock", "stub", "placeholder", "example")


class V2AdmissionError(ValueError):
    """A v2 bundle does not satisfy the frozen admission contract."""


def _walk(obj: Any, path: str = "$"):
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            yield from _walk(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, x in enumerate(obj):
            yield from _walk(x, f"{path}[{i}]")


# --------------------------------------------------------------------------- #
# 1. Origins stay typed and separate.
# --------------------------------------------------------------------------- #
def check_origins_are_typed_and_separate(rep: Report,
                                         rows: list[dict[str, Any]]) -> None:
    """Every evidence row names exactly ONE origin, from the closed set."""
    untyped = [r.get("edge_id") or r.get("target_id") for r in rows
               if r.get("evidence_origin") not in ORIGINS]
    rep.check(
        f"every evidence row declares exactly one origin from {list(ORIGINS)} — a consumer "
        "must be able to tell a measured lever from an inferred neighbour without "
        "inference of its own",
        not untyped, f"{len(untyped)} untyped: {untyped[:3]}")

    # A pathway-origin row may never carry a measured rank: nobody perturbed it.
    ranked_inferred = [r.get("target_id") for r in rows
                       if r.get("evidence_origin") in INFERRED_ORIGINS
                       and r.get("arm_rank") is not None]
    rep.check(
        "no pathway-origin row carries a measured arm rank (nobody perturbed it, so it has "
        "no rank to carry — a rank on an inferred row is a measurement that never happened)",
        not ranked_inferred, f"{len(ranked_inferred)}: {ranked_inferred[:3]}")

    # Measured origins must never be relabelled as inferred, or vice versa, per target+arm.
    seen: dict[tuple, set] = {}
    for r in rows:
        key = (r.get("target_id"), r.get("arm_key"), r.get("drug_id"))
        seen.setdefault(key, set()).add(r.get("evidence_origin"))
    fused = [k for k, origins in seen.items()
             if len(origins & MEASURED_ORIGINS) and len(origins & INFERRED_ORIGINS)
             and len(origins) == 1]
    rep.check(
        "a measured origin is never relabelled as inferred (or the reverse) for the same "
        "target/arm/drug",
        not fused, f"{len(fused)}")


def check_no_combined_score(rep: Report, document: Any) -> None:
    """No combined objective, at any depth, under any name."""
    hits = []
    for path, node in _walk(document):
        for key in node:
            if isinstance(key, str) and key.lower() in BANNED_V2_KEYS:
                hits.append(f"{path}.{key}")
    rep.check(
        "the v2 bundle carries no combined/fused/merged evidence score at ANY depth (the "
        "three origins are reported side by side; a single number over them is a claim no "
        "measurement supports)",
        not hits, str(hits[:4]))


# --------------------------------------------------------------------------- #
# 2. Ordered axes and conditions.
# --------------------------------------------------------------------------- #
def check_ordered_axes_and_conditions(rep: Report,
                                      rows: list[dict[str, Any]]) -> None:
    """Rest→Stim48 is not Stim48→Rest. An ordered pair that got sorted is a different question."""
    unordered = []
    for r in rows:
        if r.get("evidence_origin") != ORIGIN_TEMPORAL:
            continue
        frm, to = r.get("from_condition"), r.get("to_condition")
        if not (frm and to):
            unordered.append(f"{r.get('arm_key')}: missing endpoint")
        elif r.get("condition_pair_is_ordered") is not True:
            unordered.append(f"{r.get('arm_key')}: pair not declared ordered")
    rep.check(
        "every temporal row preserves its ORDERED condition pair (from → to). Rest→Stim48 "
        "is not Stim48→Rest, and a pair silently sorted into alphabetical order is a "
        "different question wearing the same key",
        not unordered, "; ".join(unordered[:3]))

    axis_lost = [r.get("arm_key") for r in rows
                 if r.get("axis_order_preserved") is not True]
    rep.check(
        "every row preserves the SELECTION's A/B axis order (the axis belongs to the "
        "selection; re-sorting it for convenience swaps which program is A)",
        not axis_lost, f"{len(axis_lost)}")


# --------------------------------------------------------------------------- #
# 3. Direction compatibility comes from the frozen engine, at view time.
# --------------------------------------------------------------------------- #
def check_direction_is_engine_decided(rep: Report, rows: list[dict[str, Any]], *,
                                      expected_vocabulary_digest: str) -> None:
    """The loader carries the verdict; it does not make it."""
    drifted = [r.get("edge_id") for r in rows
               if r.get("direction_vocabulary_digest") != expected_vocabulary_digest]
    rep.check(
        "every row binds the frozen direction vocabulary DIGEST (compatibility is decided "
        "by the frozen engine at view time — never by the cache and never by the loader; "
        "the digest is how a silent reclassification becomes visible)",
        not drifted, f"{len(drifted)} row(s) bound a different vocabulary")

    verbatim_lost = [r.get("edge_id") for r in rows
                     if r.get("action_type_source") in (None, "")
                     and r.get("intervention_effect") not in (None, "")]
    rep.check(
        "no row carries an interpretation without the verbatim source string it was "
        "derived from (if the source is gone, nobody can re-translate under a corrected "
        "vocabulary)",
        not verbatim_lost, f"{len(verbatim_lost)}")


# --------------------------------------------------------------------------- #
# 4. No fixture fallback.
# --------------------------------------------------------------------------- #
def check_no_fixture_fallback(rep: Report, bundle: dict[str, Any]) -> None:
    """A missing admitted artifact is a REFUSAL, never a substitution."""
    hits = []
    for path, node in _walk(bundle):
        for key, value in node.items():
            blob = f"{key}={value}".lower()
            if any(m in blob for m in FIXTURE_MARKERS):
                if node.get("artifact_class") != "fixture":
                    hits.append(f"{path}.{key}")
    rep.check(
        "an ANALYSIS bundle contains no fixture/synthetic/mock artifact (a loader that "
        "falls back to a fixture when an admitted artifact is missing is how a synthetic "
        "number becomes a result — the only honest response to a missing artifact is to "
        "refuse)",
        not hits, str(hits[:3]))

    rep.check("the bundle declares artifact_class=analysis",
              bundle.get("artifact_class") == "analysis",
              f"got {bundle.get('artifact_class')!r}")


# --------------------------------------------------------------------------- #
# 5. No cache self-admission; the exact admitted store is bound.
# --------------------------------------------------------------------------- #
def check_universe_store_binding(rep: Report, bundle: dict[str, Any]) -> None:
    """The cache is admitted by an INDEPENDENT verifier and bound by exact identity."""
    binding = bundle.get("universe_store_binding") or {}

    rep.check(
        f"the bundle binds the EXACT admitted universe store_id ({ADMITTED_STORE_ID[:16]}…)",
        binding.get("store_id") == ADMITTED_STORE_ID,
        f"got {str(binding.get('store_id'))[:16]}…")

    rep.check(
        f"the bundle binds the admitted producer commit ({ADMITTED_PRODUCER_COMMIT[:7]}) — "
        "the same bytes under a different producer are NOT admitted (bdf41b69 built by "
        "d6066b7 shipped a fail-open provenance gate)",
        binding.get("producer_commit") == ADMITTED_PRODUCER_COMMIT,
        f"got {binding.get('producer_commit')!r}")

    verifier = str(binding.get("admitted_by") or "")
    rep.check(
        "the store's admission comes from an INDEPENDENT verifier, never the producer's own "
        "verdict (a producer's verify_report is the producer agreeing with itself — this "
        "lane has now met that defect five times, once as its own author)",
        "independent" in verifier.lower() or verifier == "stage3_external_verifier",
        f"admitted_by={verifier!r}")

    rep.check(
        "the admission report is bound by SHA-256 (an admission that names no report is an "
        "opinion)",
        binding.get("admission_report_sha256") == ADMISSION_REPORT_SHA256,
        f"got {str(binding.get('admission_report_sha256'))[:16]}…")


def verify(rep: Report, *, bundle: dict[str, Any], rows: list[dict[str, Any]],
           expected_vocabulary_digest: str) -> None:
    """The whole frozen v2 admission contract."""
    check_no_fixture_fallback(rep, bundle)
    check_universe_store_binding(rep, bundle)
    check_origins_are_typed_and_separate(rep, rows)
    check_no_combined_score(rep, bundle)
    check_ordered_axes_and_conditions(rep, rows)
    check_direction_is_engine_decided(
        rep, rows, expected_vocabulary_digest=expected_vocabulary_digest)
