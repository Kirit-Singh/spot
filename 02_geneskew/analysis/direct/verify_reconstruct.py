"""A4 — RECONSTRUCTION. The verifier RECOUNTS. It never reads a count from the record.

A3 made ``verify_pathway`` re-derive the coverage arithmetic. It re-derived it FROM THE
RECORD: ``target_source_coverage`` was checked against the record's own
``n_genes_in_target_universe / n_source_symbols``. Every number in that division came out of
the document under attack. So an audit edited the counts AND the ratios AND the dispositions
AND the leading edge in one consistent sweep, resealed every self-hash honestly, and
promoted ``FX:UNMEASURED`` — a pathway with ZERO members in the perturbation-target
universe, whose genes were never perturbed and appear in no ranking — to headline-rankable
in BOTH arms with an enrichment of 0.95. The verifier ADMITTED it, n_failed = 0.

Internal consistency is not provenance. A count nobody can recount is a claim.

W18 (``pathway_evidence``) now SHIPS the bytes a count can be recounted from. This module is
the other half, and the two do not share a line of code: it loads those bytes and computes,
independently,

    n_source_genes        the source-symbol denominator
    n_in_target_universe  |set members INTERSECT the bound perturbation-target universe|
    n_hits_in_ranking     |set members INTERSECT that arm's ranked targets|
    the leading edge      the same ranking, walked again
    convergence support   the cosine, recomputed on the bound masked signatures

and ``verify_pathway`` then decides RANKABILITY ON THESE NUMBERS — never on the declared
ones. A declared value that disagrees is refused at a named gate carrying the reason code
``gene_set_pathway_member_count_mismatch``.

THE ANCHOR IS THE PINNED BUNDLE, AND IT IS MANDATORY
---------------------------------------------------
The evidence is written BY THE RUN and bound into the run identity by canonical hash. That
alone kills the audit's attack — the forger edits ``pathway.json`` and reseals
``records_sha256``, but ``pathway_evidence.json`` still says FX:UNMEASURED has no members.

It does NOT kill a forger who reseals the EVIDENCE too, recomputing its canonical hash and
the run id along with it. Nothing inside the bundle can: content-addressing proves an
artifact is internally coherent, never that it is true. A self-consistent reseal of the
evidence is still a lie, and it must still be caught.

So the reconstruction REQUIRES the PINNED GENE-SET BUNDLE, and the artifact SHIPS IT: the
exact source bytes are copied into every pathway output bundle under a fixed BUNDLE-RELATIVE
path (``gene_sets.source.json``), so the artifact is self-contained and verifiable by anyone
who holds it — not only on the machine that wrote it. No absolute path enters provenance or
any hash. The shipped copy's raw sha256 must equal the PINNED SOURCE IDENTITY the run was
given; its release id, licence and namespace are checked against the run provenance; its FULL
MAPPED MEMBERSHIP is what the counts are taken from; and the intersections with the bound
target universe and with each arm's ranking are the VERIFIER's own. The chain runs OUTWARD:

    to promote a pathway with no perturbed members, its genes must enter the
    perturbation-target universe -> that universe's content hash changes -> it no longer
    equals the hash the PINNED BUNDLE declares -> refused. Fixing that means editing the
    pinned bundle -> its raw sha256 changes -> and that is the number published with the
    release.

No shipped bundle, no admission: ``the_pinned_gene_set_bundle_is_shipped_inside_the_artifact``.
Membership that is only what the artifact SAYS it is has not been verified, it has been read.

``gene_sets_path`` remains available as an OPTIONAL second opinion — an auditor comparing the
shipped copy against their own copy of the release, at
``the_shipped_gene_set_copy_matches_the_original_source_cache``. It is never how the shipped
evidence is located.

THE THRESHOLDS AND THE STATISTICS HERE ARE THE VERIFIER'S OWN
------------------------------------------------------------
Nothing is imported from ``genesets`` / ``enrichment`` / ``convergence`` / ``pathway_evidence``.
A verifier that called the generator's functions would agree with it by construction,
whatever it happens to compute today — including a rule quietly loosened to make a result
rankable, which is the attack this exists to stop. These are a SECOND implementation of the
frozen written spec. If the two ever disagree, THAT is the finding.
"""
from __future__ import annotations

import json
import math
import os
import re
from typing import Any, Optional

import verify_rules as R

EVIDENCE_FILE = "pathway_evidence.json"
SIGNATURES_FILE = "pathway_signatures.parquet"
# The PINNED gene-set bundle, copied VERBATIM into every pathway output bundle. The verifier
# loads THIS — a bundle-relative logical path — and never a machine-local one: an artifact
# that can only be verified on the machine that wrote it is not a portable artifact, and an
# absolute path in public provenance is a leak and a hash that changes when nothing did.
SOURCE_BUNDLE_FILE = "gene_sets.source.json"
EVIDENCE_SCHEMA = "spot.stage02_pathway_evidence.v1"
EVIDENCE_KEY = "pathway_evidence"
SIGNATURES_KEY = "masked_signatures"
SOURCE_KEY = "gene_set_source"

# --------------------------------------------------------------------------- #
# THE FROZEN SPEC, REIMPLEMENTED — see the module docstring.
# --------------------------------------------------------------------------- #
MIN_SET_SIZE = 3
MAX_SET_SIZE = 500
SCORE_WEIGHT = 1.0
FLOAT_DECIMALS = 6
SIMILARITY_THRESHOLD = 0.5
MIN_SHARED_GENES = 10
MIN_PERTURBATIONS_FOR_CONVERGENCE = 2

EDGE_TOP = "top_leading_edge_at_or_before_the_positive_peak"
EDGE_BOTTOM = "bottom_trailing_edge_after_the_negative_trough"

TARGET_MEMBERSHIP_UNIVERSE = "perturbation_target"
READOUT_VECTOR_SPACE = "de_readout"

PASS, FAIL = "pass", "fail"

# --------------------------------------------------------------------------- #
# THE NAMED GATES. Every refusal says which one it failed.
# --------------------------------------------------------------------------- #
GATE_EVIDENCE_PRESENT = "the_reconstruction_evidence_artifact_is_present"
GATE_EVIDENCE_BOUND = "the_reconstruction_evidence_hashes_to_the_run_binding"
GATE_SIGNATURES_BOUND = "the_masked_signature_artifact_hashes_to_the_run_binding"
GATE_TARGET_UNIVERSE = "the_bound_target_universe_is_the_one_the_pinned_bundle_declares"
GATE_READOUT_UNIVERSE = "the_bound_readout_universe_is_the_one_the_pinned_bundle_declares"
GATE_TWO_UNIVERSES = "enrichment_tests_membership_in_the_perturbation_target_universe"
GATE_RANKING_IN_UNIVERSE = "every_ranked_target_lies_in_the_bound_target_universe"
GATE_SIGNATURES_IN_UNIVERSE = "every_signature_target_lies_in_the_bound_target_universe"
GATE_BUNDLE_BOUND = "the_pinned_gene_set_bundle_is_shipped_inside_the_artifact"
GATE_BUNDLE_LOADS = "the_shipped_gene_set_bundle_loads_from_its_bundle_relative_path"
# Only when the caller ALSO points at the original cache: a second opinion, never the way
# the shipped evidence is located.
GATE_SOURCE_CACHE = "the_shipped_gene_set_copy_matches_the_original_source_cache"

# The four DRIFT gates the audit asks for by name. A ``*_mismatch`` check that PASSES means
# no such drift was found; a FAIL names the exact disagreement between what the record
# declares and what the pinned release, the bound universe and the bound ranking actually say.
GATE_RAW_HASH = "gene_set_raw_hash_mismatch"
GATE_RELEASE_IDENTITY = "gene_set_release_identity_mismatch"
GATE_FULL_MEMBERSHIP = "full_membership_mismatch"
GATE_TARGET_INTERSECTION = "target_intersection_count_mismatch"
GATE_RANKING_HITS = "ranking_hit_count_mismatch"

# How the producer emitted its membership. e393285 ships genes ALREADY INTERSECTED with the
# target universe, which cannot independently prove membership — the intersection is the very
# thing under test. The verifier therefore counts from the PINNED BUNDLE and treats the
# emitted block as a cross-check, recording which form it received.
MEMBERSHIP_FULL = "full_mapped_membership"
MEMBERSHIP_INTERSECTED = "intersected_only_cannot_independently_prove_membership"


def _check(name: str, ok: bool, detail: str = "") -> dict[str, Any]:
    return {"check": name, "status": PASS if ok else FAIL, "detail": detail}


def _norm_license(value: Any) -> str:
    """``CC BY 4.0`` / ``cc-by-4.0`` / ``CC_BY_4.0`` all name the same licence."""
    return re.sub(r"[\s_]+", "-", str(value or "").strip()).upper().replace("--", "-")


# --------------------------------------------------------------------------- #
# THE STATISTICS, REIMPLEMENTED FROM THE WRITTEN SPEC.
# --------------------------------------------------------------------------- #
def enrich(ranked: list[tuple[str, float]], members: set[str]) -> dict[str, Any]:
    """The weighted running-sum ES and its DIRECTION-AWARE edge, recomputed.

    A positive score is made by the members at the TOP: its edge is the hits at or before
    the peak. A negative score is made by the members at the BOTTOM — the sum reaches its
    trough on a run of misses, so no hit has been seen there, and the top-edge rule would
    return an empty edge beside a real score. Its edge is the TRAILING hits after the
    trough. A defined enrichment always names a non-empty edge.
    """
    n = len(ranked)
    hits = [(g, v) for g, v in ranked if g in members]
    n_hits = len(hits)
    if n == 0 or n_hits == 0 or n_hits == n:
        return {"value": None, "edge": [], "side": None, "n_hits": n_hits, "n_ranked": n}

    hit_mass = sum(abs(v) ** SCORE_WEIGHT for _g, v in hits)
    if hit_mass == 0:
        return {"value": None, "edge": [], "side": None, "n_hits": n_hits, "n_ranked": n}

    miss_step = 1.0 / (n - n_hits)
    running, peak, peak_rank = 0.0, 0.0, 0
    seen: list[str] = []
    edge_at_peak: list[str] = []
    for i, (gene, value) in enumerate(ranked, start=1):
        if gene in members:
            running += (abs(value) ** SCORE_WEIGHT) / hit_mass
            seen.append(gene)
        else:
            running -= miss_step
        if abs(running) > abs(peak):
            peak, peak_rank = running, i
            edge_at_peak = list(seen)

    if peak < 0:
        edge = [g for i, (g, _v) in enumerate(ranked, start=1)
                if g in members and i > peak_rank]
        side = EDGE_BOTTOM
    else:
        edge, side = edge_at_peak, EDGE_TOP

    return {"value": round(peak, FLOAT_DECIMALS), "edge": edge, "side": side,
            "n_hits": n_hits, "n_ranked": n}


def cosine_on_shared(a: dict[str, float], b: dict[str, float]
                     ) -> tuple[Optional[float], int]:
    """Cosine on the INTERSECTION of two masked supports. Too few shared genes -> None."""
    shared = sorted(set(a) & set(b))
    n = len(shared)
    if n < MIN_SHARED_GENES:
        return None, n
    va, vb = [a[g] for g in shared], [b[g] for g in shared]
    na = math.sqrt(sum(x * x for x in va))
    nb = math.sqrt(sum(x * x for x in vb))
    if na == 0.0 or nb == 0.0:
        return None, n
    return round(sum(x * y for x, y in zip(va, vb)) / (na * nb), FLOAT_DECIMALS), n


def induced_components(members: list[str],
                       supportive: list[tuple[str, str]]) -> list[list[str]]:
    """Connected components over the subgraph INDUCED BY the set's own members (B1).

    A non-member is not an edge here, so it cannot bridge two members and manufacture a
    convergence out of a gene the pathway does not contain. Singletons are not components:
    a member with no supportive partner inside the set is a target, not a cluster of one.
    """
    parent = {m: m for m in members}

    def find(x: str) -> str:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in supportive:
        if a not in parent or b not in parent:
            continue
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    groups: dict[str, list[str]] = {}
    for m in members:
        groups.setdefault(find(m), []).append(m)
    comps = [sorted(g) for g in groups.values()
             if len(g) >= MIN_PERTURBATIONS_FOR_CONVERGENCE]
    return sorted(comps, key=lambda c: (-len(c), c[0]))


# --------------------------------------------------------------------------- #
# THE FROZEN CONVERGENCE-SIZE DOMAIN, REIMPLEMENTED FROM THE WRITTEN SPEC.
#
# A set whose MEASURED ENDPOINTS exceed the maximum is OUT OF DOMAIN: it is still emitted,
# but it contributes ZERO pair computations and can therefore never be convergent. A giant
# root may not consume O(n^2) compute or manufacture a convergence claim merely because it
# contains most of the genome.
#
# THIS MATTERS TO THE VERIFIER, NOT ONLY THE PRODUCER. A verifier that recomputed pairs for
# EVERY set would find real supportive pairs inside an oversized root that the producer
# correctly never evaluated, and would then REFUSE AN HONEST PRODUCTION BUNDLE at
# `convergence_support_rederives...`. The tiny fixture has no such set; Reactome and GO do.
# So the domain is re-derived here, from the frozen constants, and never imported from the
# producer — a verifier that took the generator's rule would ratify whatever the generator
# currently believes, including a max quietly raised to make a root convergent.
# --------------------------------------------------------------------------- #
SPEC_MAX_CONVERGENCE_SET_SIZE = 500
SPEC_CONVERGENCE_SIZE_POLICY_ID = (
    "spot.stage02.pathway.convergence_size_governance.prospective.v1")
SPEC_CONVERGENCE_SIZE_BASIS = (
    "pathway_members_intersect_perturbation_target_universe_intersect_available_"
    "perturbation_signature_targets")
SIZE_EVALUABLE = "evaluable"
SIZE_TOO_LARGE = "non_evaluable_set_too_large"


def size_disposition(members: list[str],
                     signatures: dict[str, dict[str, float]]) -> dict[str, Any]:
    """Is this set inside the frozen convergence-size domain? The verifier's own answer.

    The endpoints are the set's perturbation-target members that HAVE a signature — not its
    gene count, and not its readout footprint. The basis id says exactly that, and is checked.
    """
    n_endpoints = sum(1 for g in members if g in signatures)
    evaluable = n_endpoints <= SPEC_MAX_CONVERGENCE_SET_SIZE
    return {
        "convergence_size_policy_id": SPEC_CONVERGENCE_SIZE_POLICY_ID,
        "convergence_size_basis": SPEC_CONVERGENCE_SIZE_BASIS,
        "max_convergence_set_size": SPEC_MAX_CONVERGENCE_SET_SIZE,
        "n_measured_convergence_endpoints": n_endpoints,
        "convergence_size_disposition": SIZE_EVALUABLE if evaluable else SIZE_TOO_LARGE,
        "convergence_evaluable": evaluable,
    }


def evaluated_pair_union(members_by_set: dict[str, list[str]],
                        signatures: dict[str, dict[str, float]]
                        ) -> set[tuple[str, str]]:
    """Every intra-set pair the producer EVALUATES — the denominator behind n_intra_set_pairs.

    OUT-OF-DOMAIN SETS CONTRIBUTE NOTHING. This is the whole subtlety: a union taken over
    every set would count the pairs inside an oversized root that were never evaluated, and
    the re-derived denominator would exceed the honest declared one — REFUSING A TRUE BUNDLE.
    The pairs are a SET, not a list: a target pair shared by two sets is evaluated once.
    """
    pairs: set[tuple[str, str]] = set()
    for members in members_by_set.values():
        if not size_disposition(members, signatures)["convergence_evaluable"]:
            continue
        measured = sorted(g for g in members if g in signatures)
        for i, a in enumerate(measured):
            for b in measured[i + 1:]:
                pairs.add((a, b))
    return pairs


def converge(members: list[str], signatures: dict[str, dict[str, float]]
             ) -> dict[str, Any]:
    """Which of the set's members were MEASURED, and did they converge? Intra-set only.

    OUT OF DOMAIN => ZERO PAIRS. The set is still measured and still reported; it simply
    stands on nothing, because nothing was evaluated for it.
    """
    measured = sorted(g for g in members if g in signatures)
    size = size_disposition(members, signatures)

    supportive: list[tuple[str, str]] = []
    if size["convergence_evaluable"]:
        for i, a in enumerate(measured):
            for b in measured[i + 1:]:
                sim, _n = cosine_on_shared(signatures[a], signatures[b])
                if sim is not None and sim >= SIMILARITY_THRESHOLD:
                    supportive.append((a, b))
    comps = induced_components(measured, supportive)
    best = comps[0] if comps else []
    return {
        "measured": measured, "n_measured": len(measured),
        "supporting": list(best), "n_supporting": len(best),
        "n_supportive_pairs": len(supportive),
        "convergent": len(best) >= MIN_PERTURBATIONS_FOR_CONVERGENCE,
        "size": size,
    }


# --------------------------------------------------------------------------- #
# LOADING THE BOUND BYTES
# --------------------------------------------------------------------------- #
def load_signature_rows(path: str) -> list[dict[str, Any]]:
    """The masked signatures, LONG, in the canonical (target_id, gene_id) order.

    The canonical hash is taken over the ROWS, never the file: parquet bytes are not
    byte-stable across writers, and a hash that changes when nothing changed is a hash
    people learn to ignore.
    """
    import pandas as pd

    df = pd.read_parquet(path)
    missing = [c for c in ("target_id", "gene_id", "value") if c not in df.columns]
    if missing:
        raise ValueError(f"the signature table is missing {missing}")
    rows = [{"target_id": str(t), "gene_id": str(g), "value": float(v)}
            for t, g, v in zip(df["target_id"], df["gene_id"], df["value"])]
    rows.sort(key=lambda r: (r["target_id"], r["gene_id"]))
    return rows


def parse_bundle(doc: Any) -> dict[str, Any]:
    """The PINNED bundle's memberships, read by the verifier — not through ``genesets``."""
    if not isinstance(doc, dict):
        raise ValueError("gene-set bundle: top level is not an object")
    raw = doc.get("sets")
    if not isinstance(raw, list) or not raw:
        raise ValueError("gene-set bundle: 'sets' is not a non-empty list")

    sets: dict[str, dict[str, Any]] = {}
    for i, s in enumerate(raw):
        if not isinstance(s, dict):
            raise ValueError(f"gene-set bundle: set {i} is malformed")
        set_id = str(s.get("set_id", ""))
        if not set_id:
            raise ValueError(f"gene-set bundle: set {i} has no set_id")
        if set_id in sets:
            raise ValueError(f"gene-set bundle: duplicate set_id {set_id!r}")
        # A two-namespace bundle names its memberships separately; a legacy single-list
        # bundle names the same members in both.
        if ("genes_target" in s) or ("genes_readout" in s):
            g_target = [str(g) for g in (s.get("genes_target") or [])]
            g_readout = [str(g) for g in (s.get("genes_readout") or [])]
        else:
            legacy = [str(g) for g in (s.get("genes") or [])]
            g_target = g_readout = legacy
        n_source = s.get("n_source_symbols")
        sets[set_id] = {"genes_target": sorted(g_target),
                        "genes_readout": sorted(g_readout),
                        "n_source_symbols": int(n_source) if n_source else None}

    return {
        "sets": sets,
        "declared_target_universe_sha256": doc.get("target_universe_sha256"),
        "declared_effect_universe_sha256": doc.get("effect_universe_sha256"),
        "gene_id_namespace": str(doc.get("gene_id_namespace", "")),
        "source": str((doc.get("release") or {}).get("source", "")),
        "release_id": str((doc.get("release") or {}).get("release_id", "")),
        "license": (doc.get("release") or {}).get("license"),
        "canonical_sha256": R.content_sha256(
            [[k, v["genes_target"], v["genes_readout"]]
             for k, v in sorted(sets.items())]),
    }


def _anchor_to_bundle(*, shipped_path: str, rel_path: str, cache_path: Optional[str],
                      binding: dict[str, Any], ev: dict[str, Any],
                      source_block: dict[str, Any], target_set: set[str],
                      checks: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Anchor the whole reconstruction to the PINNED RELEASE, as SHIPPED inside the artifact.

    Everything else in the bundle — the record, the evidence, the run id — can be recomputed
    by whoever owns the output directory. The pinned gene-set bundle cannot: its raw sha256
    is the identity the release publishes, and it DECLARES the content hash of both universes
    it was built against.

    The bytes are read from a BUNDLE-RELATIVE path inside the artifact, so the artifact is
    self-contained and verifiable anywhere. ``cache_path`` is an optional second opinion —
    an auditor comparing the shipped copy against their own copy of the release — and it is
    never how the evidence is located.
    """
    # The PINNED RELEASE IDENTITY, wherever the contract puts it. The legacy binding carried
    # a top-level `gene_sets` block; the all-arm binding carries the same release identity
    # inside the evidence artifact it shipped it with. SAME FIELD, SAME MEANING, SAME CHECK —
    # this reads the pinned sha256 the run was given, and refuses if it cannot find one.
    gs = (binding.get("gene_sets")
          or (binding.get("evidence_artifacts") or {}).get(SOURCE_KEY)
          or {})
    release = gs.get("gene_set_release") or {}
    # The PINNED SOURCE IDENTITY the run was given, and the raw hash the run bound for the
    # copy it shipped. Both must equal the bytes actually on disk: the copy IS the source.
    pinned = release.get("sha256")
    bound_copy = source_block.get("raw_sha256")

    on_disk = R.sha256_file(shipped_path)
    try:
        with open(shipped_path) as fh:
            bundle = parse_bundle(json.load(fh))
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        checks.append(_check(
            GATE_BUNDLE_LOADS, False,
            f"the bytes shipped at {rel_path!r} are not a gene-set bundle: {exc}. The right "
            "filename is not the right file"))
        checks.append(_check(
            GATE_RAW_HASH, on_disk == pinned,
            f"shipped {on_disk[:16]}… vs the pinned release {str(pinned)[:16]}…"))
        return None
    checks.append(_check(GATE_BUNDLE_LOADS, True))

    # (1) THE SHIPPED BYTES ARE THE PINNED BYTES. This is the identity the run was given and
    # the one the release publishes; a copy that drifted from it is not that release.
    ok_pin = (on_disk == pinned) and (bound_copy is None or on_disk == bound_copy)
    checks.append(_check(
        GATE_RAW_HASH, ok_pin,
        f"the gene-set bundle shipped at {rel_path!r} hashes to {on_disk[:16]}…; the run "
        f"binding pins the source release at {str(pinned)[:16]}… and the copy it bound at "
        f"{str(bound_copy)[:16]}…. A pathway result computed against different bytes than "
        "the ones it cites is not evidence about that release"))
    # (1b) OPTIONAL: the auditor's own copy of the release, compared byte for byte. Reported
    # before any refusal returns, so a tampered copy says BOTH what it is and what it isn't.
    if cache_path:
        same = (os.path.exists(cache_path)
                and R.sha256_file(cache_path) == on_disk)
        checks.append(_check(
            GATE_SOURCE_CACHE, same,
            f"the copy shipped at {rel_path!r} does not match the source cache the auditor "
            "supplied; one of the two is not the release this run cites"))

    if not ok_pin:
        return None                      # STALE. Never reconstruct from unpinned bytes.

    # (2) THE RELEASE IS THE RELEASE: id, source, licence, namespace, size.
    bad = []
    # THE MEMBERSHIP CONTENT ID. Not the same quantity as the source block's
    # `canonical_sha256`, which hashes the whole shipped DOCUMENT: this is the digest of the
    # PARSED MEMBERSHIPS — [set_id, genes_target, genes_readout] — and it is the thing every
    # count is taken from. The legacy binding carried it under `gene_sets`; the all-arm
    # binding carries it under `method.gene_sets`. Comparing the membership digest against
    # the document hash would compare two different numbers and refuse every honest bundle;
    # accepting a MISSING one would compare nothing at all. So it is resolved from either
    # contract, and its ABSENCE is a refusal.
    bound_canonical = ((binding.get("gene_sets") or {}).get("canonical_sha256")
                       or ((binding.get("method") or {}).get("gene_sets") or {}).get(
                           "canonical_sha256"))
    if bound_canonical is None:
        bad.append("the run binds no gene-set membership content id, so the memberships "
                   "every count is taken from are anchored to nothing")
    elif bundle["canonical_sha256"] != bound_canonical:
        bad.append(f"the parsed memberships hash to {bundle['canonical_sha256'][:16]}…; the "
                   f"run binds {str(bound_canonical)[:16]}…")
    if bundle["source"] != release.get("source"):
        bad.append(f"source {bundle['source']!r} != {release.get('source')!r}")
    if bundle["release_id"] != release.get("release_id"):
        bad.append(f"release_id {bundle['release_id']!r} != {release.get('release_id')!r}")
    if len(bundle["sets"]) != release.get("n_sets"):
        bad.append(f"{len(bundle['sets'])} sets != the bound {release.get('n_sets')}")
    if bundle["gene_id_namespace"] != gs.get("gene_id_namespace"):
        bad.append(f"gene_id_namespace {bundle['gene_id_namespace']!r} != the bound "
                   f"{gs.get('gene_id_namespace')!r}")
    # The LICENCE decides what may be redistributed and how it must be attributed. A bundle
    # asserting a licence the run did not bind is a compliance claim nobody can stand behind.
    bound_license = gs.get("gene_set_license") or release.get("license")
    if bundle["license"] and bound_license and (
            _norm_license(bundle["license"]) != _norm_license(bound_license)):
        bad.append(f"the bundle declares licence {bundle['license']!r}; the run bound "
                   f"{bound_license!r}")
    checks.append(_check(GATE_RELEASE_IDENTITY, not bad, "; ".join(bad)))

    # (3) THE FULL MAPPED MEMBERSHIP. The counts below are taken from THIS — the published
    # set — and intersected by the verifier. The producer's emitted membership is only a
    # cross-check, and e393285 ships it ALREADY INTERSECTED, which cannot prove membership:
    # the intersection is the very thing under test. Both forms are accepted and the form is
    # RECORDED; a producer follow-up must ship the full mapped genes_target/genes_readout.
    emitted = ev.get("membership") or {}
    drift, forms = [], set()
    for set_id, s in bundle["sets"].items():
        got = sorted(str(g) for g in ((emitted.get(set_id) or {}).get("genes_target") or []))
        full = s["genes_target"]
        intersected = sorted(g for g in full if g in target_set)
        if got == full:
            forms.add(MEMBERSHIP_FULL)
        elif got == intersected:
            forms.add(MEMBERSHIP_INTERSECTED)
        else:
            drift.append(f"{set_id}: the emitted membership is neither the pinned set's "
                         f"{len(full)} mapped members nor its {len(intersected)} inside the "
                         "bound target universe")
        want_src = s["n_source_symbols"]
        got_src = (emitted.get(set_id) or {}).get("n_source_symbols")
        if got_src != want_src:
            drift.append(f"{set_id}: emitted n_source_symbols={got_src}; the PINNED BUNDLE "
                         f"says {want_src}")
    checks.append(_check(GATE_FULL_MEMBERSHIP, not drift, "; ".join(drift[:5])))
    bundle["membership_form"] = (MEMBERSHIP_INTERSECTED if MEMBERSHIP_INTERSECTED in forms
                                 else MEMBERSHIP_FULL)
    return bundle


# --------------------------------------------------------------------------- #
# THE RECONSTRUCTION
# --------------------------------------------------------------------------- #
SIGNATURE_REF_FILE = "signature_ref.json"

GATE_SIGNATURE_REF_BOUND = "the_signature_reference_is_the_one_the_run_id_covers"
GATE_SHARED_MATRIX_SUPPLIED = "the_shared_signature_matrix_was_supplied_to_the_verifier"
GATE_SHARED_MATRIX_IDENTITY = (
    "the_shared_signature_matrix_is_byte_for_byte_the_one_the_reference_names")


def _signatures_from_shipped_parquet(sig_path, bound, written, checks):
    """The LEGACY contract: the signatures shipped inside the bundle."""
    sig_bound = bound.get(SIGNATURES_KEY) or {}
    try:
        sig_rows = load_signature_rows(sig_path)
    except (ValueError, OSError) as exc:
        checks.append(_check(GATE_SIGNATURES_BOUND, False,
                             f"{SIGNATURES_FILE} does not load: {exc}"))
        return None, None
    sig_canon = R.content_sha256(sig_rows)
    sig_raw_want = (written.get(SIGNATURES_KEY) or {}).get("raw_sha256")
    ok = (sig_canon == sig_bound.get("canonical_sha256")
          and (sig_raw_want is None or R.sha256_file(sig_path) == sig_raw_want))
    checks.append(_check(
        GATE_SIGNATURES_BOUND, ok,
        f"the signature rows hash to {sig_canon[:16]}…; the run binding names "
        f"{str(sig_bound.get('canonical_sha256'))[:16]}…"))
    if not ok:
        return None, None
    signatures: dict[str, dict[str, float]] = {}
    for row in sig_rows:
        signatures.setdefault(row["target_id"], {})[row["gene_id"]] = row["value"]
    return signatures, sig_canon


def _vsm():
    """The verifier's OWN arrow readers, loaded lazily.

    `verify_signature_matrix` imports THIS module (package-relative), so importing it at
    module scope is a cycle. It is only needed on the all-arm path, so it is loaded there.
    """
    try:
        from direct import verify_signature_matrix as m
    except ImportError:                       # loaded as a top-level module, not a package
        import verify_signature_matrix as m
    return m


def _signatures_from_shared_matrix(out_dir, binding, root, checks):
    """The ALL-ARM contract: the bundle ships a REFERENCE; the bytes live in one shared,
    content-addressed per-condition matrix.

    Every hash below is RECOMPUTED HERE, from the arrow bytes, with the verifier's own
    readers — never read out of the manifest and never taken from the producer. The chain
    is: the run id covers the reference; the reference names the matrix by content; the
    matrix on disk hashes to exactly that. Break any link and this REFUSES.

    Fail-closed on absence: a matrix the verifier was not given is a convergence claim that
    cannot be recomputed, and what cannot be recomputed is not admitted.
    """
    VSM = _vsm()
    ref_path = os.path.join(out_dir, SIGNATURE_REF_FILE)
    if not os.path.exists(ref_path):
        checks.append(_check(
            GATE_SIGNATURES_BOUND, False,
            f"neither {SIGNATURES_FILE} nor {SIGNATURE_REF_FILE} is present: this bundle "
            "carries no signatures and names none, so no convergence claim in it can be "
            "recomputed by anyone"))
        return None, None
    try:
        with open(ref_path) as fh:
            ref = json.load(fh)
    except (ValueError, OSError) as exc:
        checks.append(_check(GATE_SIGNATURES_BOUND, False,
                             f"{SIGNATURE_REF_FILE} does not load: {exc}"))
        return None, None
    checks.append(_check(GATE_SIGNATURES_BOUND, True))

    # (1) THE REFERENCE IS THE ONE THE RUN ID COVERS. A bundle whose shipped reference is
    #     not the reference its binding hashed points at a matrix the id never covered.
    bound_ref = binding.get("signature_ref") or {}
    ok = bool(bound_ref) and R.content_sha256(ref) == R.content_sha256(bound_ref)
    checks.append(_check(
        GATE_SIGNATURE_REF_BOUND, ok,
        f"the shipped {SIGNATURE_REF_FILE} hashes to {R.content_sha256(ref)[:16]}…; the run "
        f"binding names {R.content_sha256(bound_ref)[:16] if bound_ref else 'nothing'}"))
    if not ok:
        return None, None

    if not root:
        checks.append(_check(
            GATE_SHARED_MATRIX_SUPPLIED, False,
            "this bundle ships no signature bytes — it references the SHARED per-condition "
            "matrix — and no --signature-matrix-root was given. The convergence claim "
            "therefore cannot be independently recomputed, and a claim that cannot be "
            "recomputed is not admitted"))
        return None, None
    checks.append(_check(GATE_SHARED_MATRIX_SUPPLIED, True))

    cond_dir = os.path.join(str(root), str(ref.get("condition")))
    axis_path = os.path.join(str(root), VSM.GENE_AXIS_FILE)
    matrix_path = os.path.join(cond_dir, VSM.MATRIX_FILE)
    mask_path = os.path.join(cond_dir, VSM.MASK_FILE)
    manifest_path = os.path.join(cond_dir, VSM.MANIFEST_FILE)
    try:
        gene_ids = VSM._read_gene_axis(axis_path)
        n_genes = len(gene_ids)
        targets, values = VSM._read_matrix(matrix_path, n_genes)
        m_targets, bitmap = VSM._read_mask(mask_path, (n_genes + 7) // 8)
        manifest = VSM._json(manifest_path)
    except (OSError, ValueError, KeyError) as exc:
        checks.append(_check(GATE_SHARED_MATRIX_IDENTITY, False,
                             f"the shared matrix under {cond_dir!r} does not load: {exc}"))
        return None, None

    got = {
        "matrix_values_sha256": VSM.values_sha256(values),
        "mask_bits_sha256": VSM.bits_sha256(bitmap),
        "gene_axis_raw_sha256": R.sha256_file(axis_path),
        "matrix_raw_sha256": R.sha256_file(matrix_path),
        "mask_raw_sha256": R.sha256_file(mask_path),
        "signature_manifest_canonical_sha256": VSM.manifest_canonical(manifest),
    }
    got["matrix_canonical_sha256"] = VSM.matrix_canonical(
        str(ref.get("condition")), targets, got["matrix_values_sha256"],
        got["gene_axis_raw_sha256"], n_genes)
    got["mask_canonical_sha256"] = VSM.mask_canonical(
        str(ref.get("condition")), m_targets, got["matrix_values_sha256"],
        got["mask_bits_sha256"], got["gene_axis_raw_sha256"], n_genes)
    drift = sorted(k for k, v in got.items() if ref.get(k) != v)
    if targets != m_targets:
        drift.append("matrix_and_mask_target_order")
    checks.append(_check(
        GATE_SHARED_MATRIX_IDENTITY, not drift,
        f"the matrix on disk disagrees with the reference the run id covers, at {drift}. "
        "A signature artifact swapped underneath a bundle is the quietest way to change "
        "what an experiment said while every hash inside the bundle still agrees"))
    if drift:
        return None, None

    want = [str(t) for t in (ref.get("member_target_ids") or [])]
    signatures = VSM.reconstruct_signatures(targets, values, bitmap, gene_ids, n_genes, want)
    return signatures, got["matrix_canonical_sha256"]


def reconstruct(*, out_dir: str, provenance: dict[str, Any], method: dict[str, Any],
                gene_sets_path: Optional[str] = None,
                signature_matrix_root: Optional[str] = None
                ) -> tuple[Optional[dict[str, Any]], list[dict[str, Any]]]:
    """Recount every claim from the bound bytes. ``None`` facts -> not reconstructible.

    Fail-closed at every step: an artifact that is missing, unreadable, unpinned or stale
    REFUSES at a named gate. What cannot be independently recounted is not admitted.
    """
    checks: list[dict[str, Any]] = []
    binding = provenance.get("run_binding", {})
    bound = binding.get("evidence_artifacts") or {}
    written = provenance.get("evidence_artifacts") or {}

    # ---- the EVIDENCE document ----
    ev_path = os.path.join(out_dir, EVIDENCE_FILE)
    if not os.path.exists(ev_path):
        checks.append(_check(
            GATE_EVIDENCE_PRESENT, False,
            f"{EVIDENCE_FILE} is absent from {out_dir}. Without the membership, the two "
            "universes and each arm's ranking, the record's counts can be recomputed by "
            "nothing but the generator — and a count that cannot be independently "
            "recounted is a claim, not evidence"))
        return None, checks
    try:
        with open(ev_path) as fh:
            ev = json.load(fh)
        if not isinstance(ev, dict) or ev.get("schema_version") != EVIDENCE_SCHEMA:
            raise ValueError(f"schema_version must be {EVIDENCE_SCHEMA!r}, got "
                             f"{(ev or {}).get('schema_version')!r}")
    except (ValueError, OSError) as exc:
        checks.append(_check(GATE_EVIDENCE_PRESENT, False,
                             f"{EVIDENCE_FILE} does not load: {exc}"))
        return None, checks
    checks.append(_check(GATE_EVIDENCE_PRESENT, True))

    # BOUND BY CONTENT (into the run id) AND BY BYTES (beside the file).
    ev_canon = R.content_sha256(ev)
    ev_raw = R.sha256_file(ev_path)
    want_canon = (bound.get(EVIDENCE_KEY) or {}).get("canonical_sha256")
    want_raw = (written.get(EVIDENCE_KEY) or {}).get("raw_sha256")
    checks.append(_check(
        GATE_EVIDENCE_BOUND,
        ev_canon == want_canon and (want_raw is None or ev_raw == want_raw),
        f"the evidence on disk has content {ev_canon[:16]}… / bytes {ev_raw[:16]}…; the run "
        f"binding names {str(want_canon)[:16]}… and the provenance pins "
        f"{str(want_raw)[:16]}…. What the counts were counted from is part of what the run IS"))

    # ---- the MASKED SIGNATURES ----
    # TWO contracts, and the bundle says which. The legacy pair-scoped artifact SHIPPED its
    # signatures as a parquet beside the records. The all-arm bundle ships NONE — one shared
    # per-condition matrix serves all six bundles, and the bundle carries a REFERENCE to it.
    # A verifier that only knew the first contract refused the second at
    # `every_required_file_is_present` and could admit nothing at all.
    sig_path = os.path.join(out_dir, SIGNATURES_FILE)
    if os.path.exists(sig_path):
        signatures, sig_canon = _signatures_from_shipped_parquet(
            sig_path, bound, written, checks)
    else:
        signatures, sig_canon = _signatures_from_shared_matrix(
            out_dir, binding, signature_matrix_root, checks)
    if signatures is None:
        return None, checks

    # ---- THE TWO UNIVERSES ----
    target_ids = [str(t) for t in (ev.get("target_universe") or [])]
    readout_ids = [str(g) for g in (ev.get("readout_universe") or [])]
    # The target universe is built sorted-and-unique; the readout universe keeps the pooled
    # object's own gene order. Two constructions, two hashes — reproduce each exactly.
    tu_hash = R.content_sha256(sorted(set(target_ids)))
    ru_hash = R.content_sha256(readout_ids)

    tu_ok = (tu_hash == ev.get("target_universe_sha256")
             and tu_hash == binding.get("target_universe_sha256"))
    ru_ok = (ru_hash == ev.get("readout_universe_sha256")
             and ru_hash == binding.get("gene_universe_sha256"))
    target_set, readout_set = set(target_ids), set(readout_ids)

    # ---- THE PINNED BUNDLE, SHIPPED INSIDE THE ARTIFACT. MANDATORY. ----
    # Without it nothing here is anchored, and a self-consistent reseal of the evidence
    # reaches this gate and dies on it. The path is BUNDLE-RELATIVE: the artifact must be
    # verifiable by anyone who has it, not only on the machine that wrote it.
    source_block = bound.get(SOURCE_KEY) or {}
    rel_path = source_block.get("path_in_bundle") or SOURCE_BUNDLE_FILE
    if os.path.isabs(str(rel_path)) or ".." in str(rel_path).split(os.sep):
        checks.append(_check(
            GATE_BUNDLE_BOUND, False,
            f"the gene-set source is bound at {rel_path!r}. The path must be BUNDLE-RELATIVE: "
            "an artifact that can only be verified on the machine that wrote it is not "
            "independently checkable, and a path that escapes the bundle is not a path into it"))
        return None, checks
    shipped_path = os.path.join(out_dir, str(rel_path))
    if not os.path.exists(shipped_path):
        checks.append(_check(
            GATE_BUNDLE_BOUND, False,
            f"the pinned gene-set bundle is not shipped inside the artifact (expected "
            f"{rel_path!r} beside the records). The record, the evidence and the run id can "
            "all be recomputed by whoever owns this directory; the published release cannot. "
            "Without those bytes, membership is only what the artifact SAYS it is — which is "
            "the claim under test"))
        return None, checks
    checks.append(_check(GATE_BUNDLE_BOUND, True))

    bundle = _anchor_to_bundle(shipped_path=shipped_path, rel_path=str(rel_path),
                               cache_path=gene_sets_path, binding=binding, ev=ev,
                               source_block=source_block, target_set=target_set,
                               checks=checks)
    if bundle is None:
        return None, checks
    # The pinned bundle DECLARES both universes it was built against. This is the link a
    # resealed forgery cannot forge without editing the published release.
    tu_ok = tu_ok and tu_hash == bundle["declared_target_universe_sha256"]
    ru_ok = ru_ok and ru_hash == bundle["declared_effect_universe_sha256"]

    declared_by = (f"; the PINNED BUNDLE was built against "
                   f"{str(bundle['declared_target_universe_sha256'])[:16]}…")
    checks.append(_check(
        GATE_TARGET_UNIVERSE, tu_ok,
        f"the {len(target_ids)} bound targets hash to {tu_hash[:16]}…; the run binds "
        f"{str(binding.get('target_universe_sha256'))[:16]}…{declared_by}. Gene-set "
        "membership is tested in the PERTURBATION-TARGET universe; membership tested in "
        "another perturbed population is not evidence about this one"))
    checks.append(_check(
        GATE_READOUT_UNIVERSE, ru_ok,
        f"the {len(readout_ids)} bound readout genes hash to {ru_hash[:16]}…; the run binds "
        f"{str(binding.get('gene_universe_sha256'))[:16]}…"))

    # B1: the two universes are DIFFERENT gene populations, and each computation names the
    # one it belongs to. Enrichment ranks PERTURBED targets; the signature vectors live in
    # the DE-READOUT space. A run that swapped them answered a different question.
    two_bad = []
    declares = any(k in method for k in ("enrichment_membership_universe",
                                         "convergence_signature_vector_space",
                                         "two_universes_are_bound_separately"))
    if declares:
        # The LEGACY contract SAYS which universe is which. Take it at its word, and check it.
        if method.get("enrichment_membership_universe") != TARGET_MEMBERSHIP_UNIVERSE:
            two_bad.append("enrichment does not declare the perturbation-target universe")
        if method.get("convergence_signature_vector_space") != READOUT_VECTOR_SPACE:
            two_bad.append("the signature vector space is not the DE readout")
        if method.get("two_universes_are_bound_separately") is not True:
            two_bad.append("the two universes are not bound separately")
    else:
        # The ALL-ARM contract makes no such declaration — so the property is RE-DERIVED from
        # the bound artifacts rather than read off a sentence the producer wrote about itself.
        # That is STRONGER, not weaker: a declaration can be true while the run did the other
        # thing, and this cannot.
        #   (i)  the run binds BOTH universes, separately, BY CONTENT
        if (binding.get("target_universe_sha256") != tu_hash
                or binding.get("gene_universe_sha256") != ru_hash):
            two_bad.append(
                "the run does not bind the two universes separately by content: it binds "
                f"target={str(binding.get('target_universe_sha256'))[:12]}… / "
                f"readout={str(binding.get('gene_universe_sha256'))[:12]}…, and the bound "
                f"evidence holds {tu_hash[:12]}… / {ru_hash[:12]}…")
        #   (ii) the SIGNATURE COORDINATES actually live in the DE-readout space. This is the
        #        substance of `convergence_signature_vector_space`, and it is a fact about the
        #        bytes rather than a claim about them.
        sig_genes = {g for vec in signatures.values() for g in vec}
        outside = sorted(sig_genes - readout_set)
        if outside:
            two_bad.append(
                f"{len(outside)} signature coordinates (e.g. {outside[:3]}) lie OUTSIDE the "
                "bound DE-readout universe: the vector space is not the readout")
    if tu_hash == ru_hash:
        two_bad.append("the target and readout universes are the same population")
    checks.append(_check(GATE_TWO_UNIVERSES, not two_bad, "; ".join(two_bad)))

    if not (tu_ok and ru_ok):
        return None, checks          # WRONG UNIVERSE: every count below would be meaningless.

    # ---- the RANKINGS and the SIGNATURES live INSIDE those universes, or they are lies ----
    rankings: dict[str, list[tuple[str, float]]] = {}
    stray: list[str] = []
    for arm, rows in (ev.get("arm_rankings") or {}).items():
        pairs = []
        for row in rows:
            t, v = str(row["target_id"]), float(row["score"])
            if t not in target_set:
                stray.append(f"{arm}: {t}")
            pairs.append((t, v))
        # RE-SORTED by the verifier: best first, ties on target_id. A permuted ranking is
        # not a different ranking, and the walk must not depend on the order it shipped in.
        rankings[arm] = sorted(pairs, key=lambda p: (-p[1], p[0]))
    checks.append(_check(
        GATE_RANKING_IN_UNIVERSE, not stray,
        f"ranked targets outside the bound perturbation-target universe: {stray[:5]}. A "
        "gene that was never perturbed cannot be a hit in a ranking of perturbations"))

    sig_stray = sorted(t for t in signatures if t not in target_set)
    gene_stray = sorted({g for vec in signatures.values() for g in vec
                         if g not in readout_set})
    checks.append(_check(
        GATE_SIGNATURES_IN_UNIVERSE, not sig_stray and not gene_stray,
        f"signatures for never-perturbed targets {sig_stray[:5]}; signature genes outside "
        f"the DE-readout universe {gene_stray[:5]}"))

    if stray or sig_stray or gene_stray:
        return None, checks

    # ---- THE FACTS, RECOUNTED PER SET ----
    # Membership is the PINNED BUNDLE's full mapped membership. The intersection with the
    # bound target universe, and with each arm's ranking, is the VERIFIER's own — which is
    # the whole point: the producer's intersected block cannot prove the intersection.
    members_by_set = {sid: s["genes_target"] for sid, s in bundle["sets"].items()}
    source_by_set = {sid: s["n_source_symbols"] for sid, s in bundle["sets"].items()}

    readout_by_set = {sid: s["genes_readout"] for sid, s in bundle["sets"].items()}

    facts: dict[str, Any] = {}
    # THE EVALUATED-PAIR DENOMINATOR, re-derived. The producer no longer EMITS its
    # non-supportive pair records — it streams only the supportive ones and keeps the count
    # of all evaluated pairs alive through a list subclass whose __len__ lies. That count
    # reaches disk as `n_intra_set_pairs`, and until now NOTHING re-derived it: a bundle
    # could multiply its own denominator and every other number in it would still agree.
    # It is the UNION of the intra-set pairs over measured members — the same set the
    # producer evaluates — so it is recomputable here, from the signatures, exactly.
    evaluated_pairs = evaluated_pair_union(members_by_set, signatures)
    for set_id, members in members_by_set.items():
        in_target = [g for g in members if g in target_set]
        n_in_target = len(in_target)
        # A set too small to say anything, or so large it says nothing, is UNTESTABLE: the
        # arm emits no statistic and no hits for it, however many members it ranked.
        testable = MIN_SET_SIZE <= n_in_target <= MAX_SET_SIZE
        member_set = set(members)

        arms = {}
        for arm, ranked in rankings.items():
            arms[arm] = (enrich(ranked, member_set) if testable else
                         {"value": None, "edge": [], "side": None, "n_hits": 0,
                          "n_ranked": len(ranked)})

        conv = converge(members, signatures)

        facts[set_id] = {
            "n_source_symbols": source_by_set.get(set_id),
            "n_in_target_universe": n_in_target,
            # B1: the OTHER universe. The signature vectors live here; membership does not.
            "n_in_readout_universe": len([g for g in readout_by_set.get(set_id, [])
                                          if g in readout_set]),
            "n_genes_in_set": len(members),
            "testable": testable,
            "arms": arms,
            "convergence": conv,
        }

    identity = {
        "bundle_anchor": "verified_against_the_pinned_release",
        "membership_source": "pinned_gene_set_bundle",
        "emitted_membership_form": bundle["membership_form"],
        "pathway_evidence_canonical_sha256": ev_canon,
        "pathway_evidence_raw_sha256": ev_raw,
        "masked_signatures_canonical_sha256": sig_canon,
        "target_universe_sha256": tu_hash,
        "n_target_universe_genes": len(target_set),
        "readout_universe_sha256": ru_hash,
        "n_readout_universe_genes": len(readout_set),
        "n_ranked": {arm: len(r) for arm, r in rankings.items()},
        "n_signature_targets": len(signatures),
        "count_rule_id": ev.get("count_rule_id"),
    }
    identity["gene_set_bundle_path_in_bundle"] = str(rel_path)
    identity["gene_set_bundle_sha256"] = R.sha256_file(shipped_path)
    identity["gene_set_release"] = {"source": bundle["source"],
                                    "release_id": bundle["release_id"],
                                    "license": bundle["license"],
                                    "n_sets": len(bundle["sets"])}
    return {"sets": facts, "identity": identity,
            "n_intra_set_pairs": len(evaluated_pairs)}, checks
