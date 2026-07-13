"""The INDEPENDENT verifier for the pathway artifact. generator != verifier. Fail-closed.

It reads the shipped bytes back off disk and re-derives, from them alone:

  * that the records are CONTENT-ADDRESSED: ``records_sha256`` recomputed from the
    emitted records must equal the one the artifact claims, and the run binding must name
    it. An artifact whose id does not follow its content can be edited and keep its name;
  * B1 — that NO convergence claim rests on a non-member. Every supporting perturbation
    and every supportive pair of every set must lie inside that set's own members, and
    the record must declare ``support_may_route_through_non_members: false``;
  * B1 — that ``convergent`` is exactly ``n_supporting_perturbations >= 2``, and that a
    single-measured-member set is never convergent;
  * M1 — that a DEFINED enrichment always names a non-empty leading edge, that the edge
    contains only members of its set, and that its side follows the sign of the score;
  * that the two evidence lines were never FUSED: no combined pathway score exists;
  * NO p, NO q, NO FDR — enforced by the same recursive key-name firewall the temporal
    lane uses (``temporal.admission``), over the WHOLE document at any nesting depth.

Fail-closed: any failed check REJECTS the artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verify_reconstruct as RC  # noqa: E402  (re-derives the claims from the artifacts)
import verify_rules as R  # noqa: E402  (the verifier-side reimplementation of the spec)

from .temporal import admission  # noqa: E402  (the ADMISSION contract, not a producer)

# The canonical hashes are RE-DERIVED from the written spec (``verify_rules``), never
# imported from the generator's ``hashing``. A verifier that hashed with the producer's
# own function would agree with it by construction, whatever it happens to compute today.
content_hash = R.content_sha256
file_sha256 = R.sha256_file

ADMIT = "admit"
REJECT = "reject"
PASS = "pass"
FAIL = "fail"

# THE ALL-ARM CONTRACT. The producer emits `arm_bundle.json` + a separate `convergence.json`
# (ONE convergence claim per (condition, source), referenced by every arm — restating it
# twenty times is twenty chances to disagree with it), and it ships NO signature bytes.
#
# This verifier previously required `pathway.json`, the LEGACY pair-scoped records file. No
# all-arm bundle has ever contained one. It therefore refused every honest bundle at
# `every_required_file_is_present` and then died in its own reporter on a KeyError — a
# verifier that cannot read the contract cannot admit it, and cannot refuse it for a reason
# either.
ALL_ARM_RECORDS_FILE = "arm_bundle.json"
LEGACY_RECORDS_FILE = "pathway.json"
PROVENANCE_FILE = "pathway_provenance.json"
CONVERGENCE_FILE = "convergence.json"
EVIDENCE_FILE = "pathway_evidence.json"
GENE_SETS_FILE = "gene_sets.source.json"
SIGNATURE_REF_FILE = "signature_ref.json"

CONTRACT_ALL_ARM = "all_arm"
CONTRACT_LEGACY = "legacy_pair_scoped"

# BOTH GENERATIONS, EACH FAIL-CLOSED. Replacing the legacy file set with the all-arm one made
# every honest legacy artifact die at `every_required_file_is_present` — a silent regression
# dressed as a repair. A verifier that can only read the newest thing it was shown is not a
# verifier, it is a version check.
REQUIRED_BY_CONTRACT = {
    CONTRACT_ALL_ARM: (ALL_ARM_RECORDS_FILE, PROVENANCE_FILE, CONVERGENCE_FILE,
                       EVIDENCE_FILE, GENE_SETS_FILE, SIGNATURE_REF_FILE),
    CONTRACT_LEGACY: (LEGACY_RECORDS_FILE, PROVENANCE_FILE),
}
# kept for callers that ask what the CURRENT contract is
REQUIRED_FILES = REQUIRED_BY_CONTRACT[CONTRACT_ALL_ARM]

GATE_CONTRACT = "the_bundle_presents_exactly_one_known_pathway_contract"


def detect_contract(out_dir: str):
    """WHICH contract is on disk. Neither, or BOTH, is a refusal — never a guess.

    A directory holding both records files is not a bundle that supports two readers; it is
    two bundles in a trench coat, and whichever one the verifier picked, the other would go
    unchecked.
    """
    all_arm = os.path.exists(os.path.join(out_dir, ALL_ARM_RECORDS_FILE))
    legacy = os.path.exists(os.path.join(out_dir, LEGACY_RECORDS_FILE))
    if all_arm and not legacy:
        return CONTRACT_ALL_ARM
    if legacy and not all_arm:
        return CONTRACT_LEGACY
    return None

VERIFIER_ID = "spot.stage02.pathway.verifier.v3_all_arm"

# --------------------------------------------------------------------------- #
# A3 — THE COVERAGE POLICY, REIMPLEMENTED FROM THE WRITTEN SPEC.
#
# These constants are NOT imported from ``genesets``. They are the verifier's OWN copy of
# the frozen rule, held here so this module can DISAGREE with the generator. A verifier
# that read the generator's thresholds would ratify whatever the generator currently says —
# including a threshold quietly loosened to make a result rankable, which is precisely the
# attack the coverage governance exists to stop.
#
# The artifact DECLARES the policy it ran under. That declaration is CHECKED against these
# constants: an artifact that ran under a different rule is refused, whatever it computed.
#
#     MIN_SOURCE_COVERAGE    = 0.50   a pathway must retain half the genes it is named for
#     MIN_ARM_RANKED_MEMBERS = 3      ...and an ARM must actually rank three of them
#                                     (INCLUSIVE: exactly three is enough)
# --------------------------------------------------------------------------- #
SPEC_MIN_SOURCE_COVERAGE = 0.50
SPEC_MIN_ARM_RANKED_MEMBERS = 3
SPEC_COVERAGE_POLICY_ID = "spot.stage02.pathway.coverage_governance.prospective.v2"

RANKABLE = "rankable"
LOW_COVERAGE = "descriptive_only_low_source_coverage"
UNKNOWN_COVERAGE = "descriptive_only_source_coverage_unknown"
THIN_ARM = "descriptive_only_thin_arm"
UNDEFINED = "undefined"

FLOAT_TOL = 1e-6


def _global_disposition(target_source_coverage):
    """The GLOBAL rule, re-derived. Necessary for a headline arm result, never sufficient."""
    if target_source_coverage is None:
        return UNKNOWN_COVERAGE, False
    if target_source_coverage >= SPEC_MIN_SOURCE_COVERAGE:
        return RANKABLE, True
    return LOW_COVERAGE, False


def _arm_disposition(global_passed, n_hits, enrichment_value):
    """The PER-ARM rule, re-derived. Inclusive at the boundary."""
    defined = enrichment_value is not None
    thick = n_hits >= SPEC_MIN_ARM_RANKED_MEMBERS
    passed = bool(global_passed) and thick and defined
    if not defined:
        return UNDEFINED, passed
    if global_passed is None:
        return UNKNOWN_COVERAGE, passed
    if not global_passed:
        return LOW_COVERAGE, passed
    if not thick:
        return THIN_ARM, passed
    return RANKABLE, passed


# A4 — the named gates of the RE-DERIVATION. The counts are recomputed from the bound
# artifacts and the DECLARED value must equal the reconstruction; the rankability decision
# is then taken on the RE-DERIVED counts. ``MEMBER_COUNT_MISMATCH`` is the reason code a
# count-drift refusal carries, so an audit can assert on the drift itself and not on prose.
MEMBER_COUNT_MISMATCH = "gene_set_pathway_member_count_mismatch"

GATE_N_SOURCE = "n_source_genes_rederives_from_the_pinned_gene_set_bundle"
GATE_N_TARGET = RC.GATE_TARGET_INTERSECTION      # "target_intersection_count_mismatch"
GATE_COVERAGE = "global_coverage_and_disposition_rederive_from_the_bound_artifacts"
GATE_N_HITS = RC.GATE_RANKING_HITS               # "ranking_hit_count_mismatch"
GATE_ARM_ELIGIBILITY = "arm_eligibility_rederives_from_the_bound_artifacts"
GATE_LEADING_EDGE = "the_leading_edge_rederives_from_the_bound_arm_ranking"
GATE_ENRICHMENT = "the_enrichment_score_rederives_from_the_bound_arm_ranking"
GATE_CONVERGENCE = "convergence_support_rederives_from_the_bound_masked_signatures"
GATE_RUN_ID = "pathway_run_id_rederives_from_run_binding"

# ---- the gates the ALL-ARM contract needs, and the legacy one had nowhere to put ----
# The convergence claim now lives in its OWN file, referenced by all twenty arms. So it must
# be bound like anything else: hashed, named by the bundle, and named by the run id.
GATE_CONVERGENCE_BOUND = "the_convergence_artifact_hashes_to_the_run_binding"
# Twenty flat arm records carry the SET-level declarations twenty times over. The legacy
# per-set record could not disagree with itself; these can. If two arms of one set declare
# different coverage, one of them is false and the verifier may not pick a favourite.
GATE_SET_AGREEMENT = "the_arms_of_a_set_agree_on_that_set_s_declarations"
# The three lists of set ids — the pinned release, the arm records, the convergence
# artifact — must be THE SAME LIST. An orphan convergence claim is a claim about a
# pathway nothing else in the bundle mentions, and no other gate would ever see it.
GATE_SET_IDS_AGREE = (
    "the_set_ids_agree_across_the_release_the_records_and_the_convergence_artifact")
# THE STREAMED DENOMINATOR. The producer no longer emits non-supportive pair records; it
# emits the supportive ones and declares `n_intra_set_pairs` for all EVALUATED pairs. Nothing
# re-derived that number, so a bundle could multiply its own denominator and stay coherent.
GATE_INTRA_SET_PAIRS = "n_intra_set_pairs_rederives_from_the_bound_masked_signatures"
# Fail-closed instead of KeyError.
GATE_PROVENANCE_USABLE = "the_shipped_provenance_carries_the_run_identity_it_is_verified_by"
# The domain the pairs were drawn from. An oversized root contributes ZERO pairs; a run that
# raised its own maximum could pair one, call it convergent, and stay perfectly coherent.
GATE_CONVERGENCE_SIZE = "the_convergence_size_domain_rederives_from_the_frozen_policy"

# The run id is the sha256 of the canonical run binding, truncated. The verifier RECOMPUTES
# it rather than reading it: an artifact whose id does not follow its own binding has had
# something changed underneath its name, and the name is what everything downstream cites.
PATHWAY_RUN_ID_LEN = 16


def _check(name: str, ok: bool, detail: str = "") -> dict[str, Any]:
    return {"check": name, "status": PASS if ok else FAIL, "detail": detail}


def _same(a, b) -> bool:
    """Float-tolerant equality that keeps None distinct from 0.0."""
    if a is None or b is None:
        return a is None and b is None
    return abs(float(a) - float(b)) <= FLOAT_TOL


def _rederive(records: list[dict[str, Any]], facts: dict[str, Any],
              checks: list[dict[str, Any]]) -> dict[str, Any]:
    """The AUTHORITATIVE counts and dispositions, recomputed from the bound artifacts.

    Nothing here reads a count from the record. The record's declarations are COMPARED to
    the reconstruction, and the coverage, the per-arm eligibility and the headline
    rankability are decided on the RECONSTRUCTED numbers.
    """
    sets = facts["sets"]
    src, tgt, cov, hits, arm, edge, val, conv = ([] for _ in range(8))
    authoritative: dict[str, Any] = {}

    for r in records:
        sid = r["set_id"]
        f = sets.get(sid)
        if f is None:
            src.append(f"{MEMBER_COUNT_MISMATCH} {sid}: the pinned gene-set bundle "
                       "contains no such set")
            continue

        n_src, n_tgt = f["n_source_symbols"], f["n_in_target_universe"]

        # (i) THE MEMBER COUNTS. From the bundle and the universes — never from the record.
        if r.get("n_source_symbols") != n_src:
            src.append(f"{MEMBER_COUNT_MISMATCH} {sid}: declares n_source_symbols="
                       f"{r.get('n_source_symbols')}; the PINNED BUNDLE says {n_src}")
        if r.get("n_genes_in_set") != f["n_genes_in_set"]:
            src.append(f"{MEMBER_COUNT_MISMATCH} {sid}: declares n_genes_in_set="
                       f"{r.get('n_genes_in_set')}; the PINNED BUNDLE names "
                       f"{f['n_genes_in_set']}")
        if r["n_genes_in_target_universe"] != n_tgt:
            tgt.append(f"{MEMBER_COUNT_MISMATCH} {sid}: declares "
                       f"n_genes_in_target_universe="
                       f"{r['n_genes_in_target_universe']}, but only {n_tgt} of its "
                       "members lie in the BOUND perturbation-target universe")
        if r.get("n_genes_in_readout_universe") != f["n_in_readout_universe"]:
            tgt.append(f"{MEMBER_COUNT_MISMATCH} {sid}: declares "
                       f"n_genes_in_readout_universe="
                       f"{r.get('n_genes_in_readout_universe')}; the BOUND readout "
                       f"universe holds {f['n_in_readout_universe']}")

        # (ii) COVERAGE AND DISPOSITION, decided on the RE-DERIVED counts.
        true_cov = (round(n_tgt / n_src, 6) if n_src else None)
        disposition, passed = _global_disposition(true_cov)
        if not _same(r.get("target_source_coverage"), true_cov):
            cov.append(f"{sid}: declares target_source_coverage="
                       f"{r.get('target_source_coverage')}; RE-DERIVED {n_tgt}/{n_src} = "
                       f"{true_cov}")
        if r["global_coverage_disposition"] != disposition:
            cov.append(f"{sid}: declares {r['global_coverage_disposition']}; the "
                       f"RE-DERIVED coverage {true_cov} is {disposition}")
        if bool(r["global_coverage_policy_passed"]) != passed:
            cov.append(f"{sid}: declares global_coverage_policy_passed="
                       f"{r['global_coverage_policy_passed']}; RE-DERIVED {passed}")

        arms_out: dict[str, Any] = {}
        for a_name, e in r["enrichment"].items():
            a = f["arms"].get(a_name)
            if a is None:
                hits.append(f"{MEMBER_COUNT_MISMATCH} {sid}/{a_name}: the run bound no "
                            "ranking for this arm")
                continue

            # (iii) THE ARM-EVALUABLE COUNT: the members THIS ARM actually ranked.
            if e["n_hits_in_ranking"] != a["n_hits"]:
                hits.append(f"{MEMBER_COUNT_MISMATCH} {sid}/{a_name}: declares "
                            f"n_hits_in_ranking={e['n_hits_in_ranking']}; the BOUND "
                            f"ranking contains {a['n_hits']} of its members")

            # (iv) ELIGIBILITY, decided on the RE-DERIVED counts. The arms are independent.
            true_ac = (round(a["n_hits"] / n_src, 6) if n_src else None)
            a_disp, a_rank = _arm_disposition(passed, a["n_hits"], a["value"])
            if not _same(e.get("arm_evaluable_source_coverage"), true_ac):
                arm.append(f"{sid}/{a_name}: declares arm_evaluable_source_coverage="
                           f"{e.get('arm_evaluable_source_coverage')}; RE-DERIVED "
                           f"{a['n_hits']}/{n_src} = {true_ac}")
            if e["arm_coverage_disposition"] != a_disp:
                arm.append(f"{sid}/{a_name}: declares {e['arm_coverage_disposition']}; "
                           f"RE-DERIVED {a_disp}")
            if bool(e["arm_headline_rankable"]) != a_rank:
                arm.append(f"{sid}/{a_name}: declares arm_headline_rankable="
                           f"{e['arm_headline_rankable']}; RE-DERIVED {a_rank} from "
                           f"global_passed={passed}, n_hits={a['n_hits']}, "
                           f"defined={a['value'] is not None}")

            # (v) THE SCORE AND THE MEMBERS BEHIND IT, walked again on the bound ranking.
            if not _same(e["enrichment_value"], a["value"]):
                val.append(f"{sid}/{a_name}: declares enrichment_value="
                           f"{e['enrichment_value']}; the BOUND ranking produces "
                           f"{a['value']}")
            if list(e["leading_edge"]) != list(a["edge"]):
                edge.append(f"{sid}/{a_name}: declares a {len(e['leading_edge'])}-gene "
                            f"edge; the BOUND ranking puts {len(a['edge'])} of its "
                            "members behind that score")
            if e["n_leading_edge"] != len(a["edge"]) or (
                    e["leading_edge_side"] != a["side"]):
                edge.append(f"{sid}/{a_name}: the edge count or side disagrees with the "
                            "BOUND ranking")

            arms_out[a_name] = {
                "n_hits_in_ranking": a["n_hits"],
                "arm_evaluable_source_coverage": true_ac,
                "arm_coverage_disposition": a_disp,
                "arm_headline_rankable": a_rank,
                "enrichment_value": a["value"],
                "n_leading_edge": len(a["edge"]),
            }

        # (vi) CONVERGENCE SUPPORT, recomputed on the bound masked signatures.
        c, dc = f["convergence"], r["convergence"]
        if (dc["n_measured_perturbations"] != c["n_measured"]
                or list(dc["measured_perturbations"]) != c["measured"]):
            conv.append(f"{sid}: declares {dc['n_measured_perturbations']} measured "
                        f"perturbations; the BOUND signatures hold {c['n_measured']}")
        if (dc["n_supporting_perturbations"] != c["n_supporting"]
                or list(dc["supporting_perturbations"]) != c["supporting"]):
            conv.append(f"{sid}: declares n_supporting_perturbations="
                        f"{dc['n_supporting_perturbations']}; the BOUND signatures "
                        f"support {c['n_supporting']}")
        if bool(dc["convergent"]) != c["convergent"]:
            conv.append(f"{sid}: declares convergent={dc['convergent']}; RE-DERIVED "
                        f"{c['convergent']}")
        if dc["n_supportive_pairs"] != c["n_supportive_pairs"]:
            conv.append(f"{sid}: declares {dc['n_supportive_pairs']} supportive pairs; "
                        f"the BOUND signatures produce {c['n_supportive_pairs']}")

        authoritative[sid] = {
            "n_source_symbols": n_src,
            "n_genes_in_target_universe": n_tgt,
            "target_source_coverage": true_cov,
            "global_coverage_disposition": disposition,
            "global_coverage_policy_passed": passed,
            "enrichment": arms_out,
            "n_supporting_perturbations": c["n_supporting"],
            "convergent": c["convergent"],
        }

    checks.append(_check(GATE_N_SOURCE, not src, "; ".join(src[:5])))
    checks.append(_check(GATE_N_TARGET, not tgt, "; ".join(tgt[:5])))
    checks.append(_check(GATE_COVERAGE, not cov, "; ".join(cov[:5])))
    checks.append(_check(GATE_N_HITS, not hits, "; ".join(hits[:5])))
    checks.append(_check(GATE_ARM_ELIGIBILITY, not arm, "; ".join(arm[:5])))
    checks.append(_check(GATE_ENRICHMENT, not val, "; ".join(val[:5])))
    checks.append(_check(GATE_LEADING_EDGE, not edge, "; ".join(edge[:5])))
    checks.append(_check(GATE_CONVERGENCE, not conv, "; ".join(conv[:5])))
    return authoritative


def _fails(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in checks if c["status"] != PASS]


# The SET-level fields every arm record of a set restates, and must restate identically.
SET_LEVEL_FIELDS = ("set_name", "n_source_symbols", "n_genes_in_target_universe",
                    "target_source_coverage", "global_coverage_disposition",
                    "global_coverage_policy_passed")


def _set_view(records: list[dict[str, Any]], conv_doc: dict[str, Any],
              checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The all-arm bundle, read as the per-set view every gate below already knows how to
    check. AN ADAPTER, NOT A RELAXATION.

    The legacy artifact had ONE record per set, carrying `enrichment` (per arm) and
    `convergence`. The all-arm bundle has one FLAT record per (set, arm) — twenty of them —
    and keeps the single convergence claim in its own bound file. The science is identical;
    only the shape moved. So this regroups the shape and changes not one threshold.

    The one thing that genuinely CAN go wrong in the new shape is disagreement: twenty
    records now restate each set's coverage, and nothing forced them to agree. So they are
    checked against each other, and a set whose arms contradict one another is REFUSED rather
    than resolved by taking the first record's word for it. Every declared value below is
    still the PRODUCER's — the reconstruction compares them against the bound artifacts, and
    nothing here pre-agrees with anything.
    """
    conv_by_set = {c["set_id"]: c for c in conv_doc.get("sets", [])}
    by_set: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        by_set.setdefault(r["set_id"], []).append(r)

    disagreements, missing = [], []
    view: list[dict[str, Any]] = []
    for sid, arm_records in sorted(by_set.items()):
        for field in SET_LEVEL_FIELDS:
            values = {json.dumps(r.get(field), sort_keys=True) for r in arm_records}
            if len(values) > 1:
                disagreements.append(
                    f"{sid}: its {len(arm_records)} arms declare {len(values)} different "
                    f"values for {field}: {sorted(values)[:3]}")
        head = arm_records[0]

        conv = conv_by_set.get(sid)
        if conv is None:
            missing.append(sid)
            continue

        view.append({
            "set_id": sid,
            "set_name": head.get("set_name"),
            "n_source_symbols": head.get("n_source_symbols"),
            "n_genes_in_target_universe": head["n_genes_in_target_universe"],
            # The all-arm ARM record does not restate these two; the bound convergence
            # artifact does, and it is hashed into the run id like everything else.
            "n_genes_in_set": conv.get("n_genes_in_set"),
            "n_genes_in_readout_universe": conv.get("n_genes_in_readout_universe"),
            "target_source_coverage": head.get("target_source_coverage"),
            "global_coverage_disposition": head["global_coverage_disposition"],
            "global_coverage_policy_passed": head["global_coverage_policy_passed"],
            "enrichment": {
                r["direct_arm_key"]: {
                    "n_hits_in_ranking": r["n_hits_in_ranking"],
                    "arm_evaluable_source_coverage": r.get(
                        "arm_evaluable_source_coverage"),
                    "arm_coverage_disposition": r["arm_coverage_disposition"],
                    "arm_headline_rankable": r["arm_headline_rankable"],
                    "enrichment_value": r["enrichment_value"],
                    "leading_edge": r["leading_edge"],
                    "n_leading_edge": r["n_leading_edge"],
                    "leading_edge_side": r["leading_edge_side"],
                    # each ARM's own restatement of the global verdict — compared against the
                    # set's, so an arm cannot be ranked on a coverage its set never had
                    "global_target_source_coverage": r.get("target_source_coverage"),
                } for r in arm_records},
            "convergence": conv,
        })

    checks.append(_check(GATE_SET_AGREEMENT, not disagreements,
                         "; ".join(disagreements[:5])))

    # EXACT set-id equality, BOTH WAYS. Checking only "every record has a convergence block"
    # let a convergence artifact carry an ORPHAN set that no record mentions — a convergence
    # claim about a pathway the bundle never ranked, invisible to every other gate. And a
    # duplicated arm row inside a set would silently overwrite its twin in the view.
    rec_ids, conv_ids = set(by_set), set(conv_by_set)
    orphans = sorted(conv_ids - rec_ids)
    dupes = sorted(sid for sid, rs in by_set.items()
                   if len({r["direct_arm_key"] for r in rs}) != len(rs))
    checks.append(_check(
        GATE_SET_IDS_AGREE, not (missing or orphans or dupes),
        f"sets with arm records but no convergence claim: {missing[:3]}; convergence claims "
        f"about sets no record emits: {orphans[:3]}; sets with duplicate arm rows: "
        f"{dupes[:3]}"))
    return view


def _all_arm_view(out_dir, doc, provenance, raw_records, identity, checks):
    """The ALL-ARM extras: bind the separate convergence artifact, then regroup to the
    per-set view every gate below already knows how to check.

    Returns (None, {}) when the convergence artifact cannot be bound — fail-closed, named.
    """
    try:
        shipped_conv = admission.load_shipped(out_dir, CONVERGENCE_FILE)
    except admission.ShippedDocError as exc:
        checks.append(_check(GATE_CONVERGENCE_BOUND, False, str(exc)))
        return None, {}
    conv_doc = shipped_conv["doc"]
    # RE-DERIVED exactly as the producer computes it: the content hash of the artifact minus
    # its own identity fields. The bundle names it and the run binding names it; a
    # convergence claim swapped for another run's is why all three are checked.
    conv_recomputed = content_hash({k: v for k, v in conv_doc.items()
                                    if k not in ("convergence_sha256", "pathway_run_id")})
    conv_claimed = conv_doc.get("convergence_sha256")
    checks.append(_check(
        GATE_CONVERGENCE_BOUND,
        conv_recomputed == conv_claimed
        and doc.get("convergence_sha256") == conv_claimed
        and provenance["run_binding"].get("convergence_sha256") == conv_claimed,
        f"the convergence artifact hashes to {conv_recomputed[:16]}…; it calls itself "
        f"{str(conv_claimed)[:16]}…, the bundle names "
        f"{str(doc.get('convergence_sha256'))[:16]}… and the run binding names "
        f"{str(provenance['run_binding'].get('convergence_sha256'))[:16]}…"))
    identity["convergence_canonical_sha256"] = conv_recomputed
    return _set_view(raw_records, conv_doc, checks), conv_doc


def verify(*, out_dir: str, provenance: Optional[dict[str, Any]] = None,
           gene_sets_path: Optional[str] = None,
           signature_matrix_root: Optional[str] = None) -> dict[str, Any]:
    """Re-derive every pathway claim from THE BYTES THAT SHIPPED and the ARTIFACTS BOUND.

    ``provenance`` is NOT the subject of verification — the shipped
    ``pathway_provenance.json`` is LOADED here and everything below runs on THAT. The
    caller's dict is admissible only as a cross-check.

    (The previous version hashed the provenance file and then firewalled the caller's
    dictionary. An independent audit poisoned the emitted provenance on disk with
    ``empirical_p_value``, passed the pristine dict, and got ADMIT.)

    A4: the COUNTS are not read from the record either. They are RECONSTRUCTED from the
    pinned gene-set bundle, the bound target universe, the exact arm rankings and the bound
    masked signatures (``verify_reconstruct``), and the rankability decision is taken on the
    RE-DERIVED counts — never on the declared ones. ``gene_sets_path`` overrides where the
    pinned bundle is read from; the bytes found there must still hash to the release pin.
    """
    checks: list[dict[str, Any]] = []
    contract = detect_contract(out_dir)
    checks.append(_check(
        GATE_CONTRACT, contract is not None,
        f"a pathway bundle presents EITHER {ALL_ARM_RECORDS_FILE} (all-arm) OR "
        f"{LEGACY_RECORDS_FILE} (legacy pair-scoped). This directory presents "
        f"{'both' if os.path.exists(os.path.join(out_dir, ALL_ARM_RECORDS_FILE)) else 'neither'}"))
    if contract is None:
        return _report({}, {"files": {}, "artifact_sha256": content_hash({}),
                            "required_files": [], "contract": None}, checks, n_records=0)

    required = REQUIRED_BY_CONTRACT[contract]
    files = {n: (file_sha256(os.path.join(out_dir, n))
                 if os.path.exists(os.path.join(out_dir, n)) else None)
             for n in required}
    identity = {"files": files, "artifact_sha256": content_hash(files),
                "required_files": list(required), "contract": contract}

    absent = [n for n, sha in files.items() if sha is None]
    checks.append(_check("every_required_file_is_present", not absent,
                         f"absent from the {contract} contract: {absent}"))
    if absent:
        return _report(provenance or {}, identity, checks, n_records=0)
    records_file = (ALL_ARM_RECORDS_FILE if contract == CONTRACT_ALL_ARM
                    else LEGACY_RECORDS_FILE)

    # ---- 0. LOAD BOTH SHIPPED DOCUMENTS. This is what gets verified. ----
    try:
        shipped_prov = admission.load_shipped(out_dir, PROVENANCE_FILE)
        shipped_doc = admission.load_shipped(out_dir, records_file)
    except admission.ShippedDocError as exc:
        checks.append(_check("shipped_documents_load_from_disk", False, str(exc)))
        return _report(provenance or {}, identity, checks, n_records=0)
    checks.append(_check("shipped_documents_load_from_disk", True))

    checks.append(_check(
        "the_provenance_we_verified_is_the_provenance_we_hashed",
        shipped_prov["sha256"] == files[PROVENANCE_FILE],
        f"loaded {shipped_prov['sha256'][:16]} != pinned "
        f"{str(files[PROVENANCE_FILE])[:16]}"))
    checks.append(_check(
        "caller_provenance_matches_the_shipped_file",
        admission.caller_matches(shipped_prov["doc"], provenance),
        "the caller's provenance dict differs from the shipped bytes; the shipped "
        "bytes are what is verified"))

    # FROM HERE ON these mean THE SHIPPED DOCUMENTS.
    provenance = shipped_prov["doc"]
    doc = shipped_doc["doc"]
    identity["provenance_canonical_sha256"] = shipped_prov["canonical_sha256"]
    raw_records = doc["records"]

    # A provenance with no run identity cannot be verified BY that identity. Say so at a
    # named gate and stop — the previous version walked on and died on a KeyError in its own
    # reporter, which is a crash, not a verdict, and a harness reading the report got nothing.
    if not (provenance.get("pathway_run_id") and provenance.get("run_binding")):
        checks.append(_check(
            GATE_PROVENANCE_USABLE, False,
            "the shipped provenance carries no pathway_run_id / run_binding. Everything "
            "below is verified BY that identity, so there is nothing here to verify against"))
        return _report(provenance, identity, checks, n_records=len(raw_records))
    checks.append(_check(GATE_PROVENANCE_USABLE, True))

    # ---- THE CONVERGENCE ARTIFACT ----
    # ALL-ARM only: the claim lives in its own file and must be bound like its own file. The
    # LEGACY record carries its convergence inline, where it is already covered by
    # records_sha256, so there is nothing separate to bind and nothing here to skip.
    if contract == CONTRACT_LEGACY:
        records = raw_records
        conv_doc = {}
    else:
        records, conv_doc = _all_arm_view(out_dir, doc, provenance, raw_records,
                                          identity, checks)
        if records is None:
            return _report(provenance, identity, checks, n_records=len(raw_records))



    # ---- 1. NO p / q / FDR / combined objective, ANYWHERE, at ANY depth ----
    # The same recursive firewall the temporal lane fails closed on, over the SHIPPED
    # bytes of both documents. A pathway p-value would be the single most believable
    # wrong number this whole layer could emit.
    hits = admission.forbidden_keys(doc) + admission.forbidden_keys(provenance)
    checks.append(_check("no_forbidden_key_at_any_depth", not hits,
                         f"forbidden keys: {sorted(set(hits))[:8]}"))
    checks.append(_check(
        "inference_status_is_not_calibrated",
        provenance.get("inference_status") == "not_calibrated",
        f"inference_status is {provenance.get('inference_status')!r}; spot calibrates nothing here and must say so"))

    # ---- 2. CONTENT ADDRESSING: the id follows the content ----
    # Re-derived by the PRODUCER'S OWN RULE, on the RAW shipped records: the content hash of
    # the records sorted by (pathway_arm_key, set_id). Recomputing it under some other rule
    # would be checking a number this artifact never claimed.
    stripped = [{k: v for k, v in r.items()
                 if k not in ("pathway_run_id", "pathway_method_sha256")}
                for r in raw_records]
    # Each contract's OWN rule, re-derived. The all-arm producer hashes its records SORTED by
    # (pathway_arm_key, set_id); the legacy one hashes them in emitted order. Recomputing
    # under the other contract's rule would check a number this artifact never claimed.
    recomputed = content_hash(
        sorted(stripped, key=lambda r: (r["pathway_arm_key"], r["set_id"]))
        if contract == CONTRACT_ALL_ARM else stripped)
    claimed = doc["records_sha256"]
    checks.append(_check("records_sha256_recomputes_from_the_emitted_records",
                         recomputed == claimed,
                         f"recomputed {recomputed[:16]} != claimed {claimed[:16]}"))
    checks.append(_check(
        "the_run_binding_names_the_records_it_shipped",
        provenance["run_binding"]["records_sha256"] == claimed))
    if contract == CONTRACT_LEGACY:
        # the LEGACY record stamps the run id on every row, and that is checked as it was
        checks.append(_check(
            "every_record_carries_the_run_id",
            all(r.get("pathway_run_id") == provenance["pathway_run_id"]
                for r in raw_records)))
    else:
        # The all-arm record does NOT carry the run id — the DOCUMENT does, and the records
        # are tied to it through records_sha256, which is inside the binding the id hashes.
        # So the two claims that actually hold here: the document names this run, and no
        # record smuggles in a FOREIGN run's id.
        checks.append(_check(
            "the_bundle_document_names_this_run",
            doc.get("pathway_run_id") == provenance["pathway_run_id"],
            f"the bundle calls itself {doc.get('pathway_run_id')!r}; the provenance says "
            f"{provenance['pathway_run_id']!r}"))
    foreign = sorted({str(r["pathway_run_id"]) for r in raw_records
                      if r.get("pathway_run_id") not in (None,
                                                         provenance["pathway_run_id"])})
    checks.append(_check("no_record_carries_a_foreign_run_id", not foreign,
                         f"records carrying another run's id: {foreign[:3]}"))

    # ---- 2b. THE RUN ID FOLLOWS THE RUN BINDING. Recomputed, never read. ----
    # Everything the run stands on lives in the binding: the method, both universes, the
    # gene-set release, the evidence hashes, the records hash. The id is that binding's
    # sha256. A forger who edits ANY of it — swapping an evidence hash to match a forged
    # evidence file, say — and then reseals the documents inside the bundle still has to
    # produce an id the binding hashes to. A stale or invented id means something moved
    # underneath the name that every downstream stage cites.
    full = content_hash(provenance["run_binding"])
    claimed_id = provenance.get("pathway_run_id")
    claimed_full = provenance.get("pathway_run_sha256")
    checks.append(_check(
        GATE_RUN_ID,
        claimed_id == full[:PATHWAY_RUN_ID_LEN] and claimed_full == full,
        f"the run binding hashes to {full[:16]}…, so this run is "
        f"{full[:PATHWAY_RUN_ID_LEN]!r}; the artifact calls itself {claimed_id!r} "
        f"(pathway_run_sha256 {str(claimed_full)[:16]}…). An id that does not follow its own "
        "binding is a name that outlived the thing it named"))

    # ---- 3. B1: convergence rests on INTRA-PATHWAY support, and nothing else ----
    bad = []
    for r in records:
        c = r["convergence"]
        members = set(c["measured_perturbations"])
        if c["support_may_route_through_non_members"] is not False:
            bad.append(f"{r['set_id']}: declares support may route through non-members")
        for t in c["supporting_perturbations"]:
            if t not in members:
                bad.append(f"{r['set_id']}: supporting perturbation {t} is not a "
                           "measured member of the set")
        for p in c["pairwise_support"]:
            if p["target_a"] not in members or p["target_b"] not in members:
                bad.append(f"{r['set_id']}: supportive pair "
                           f"({p['target_a']}, {p['target_b']}) touches a non-member")
        for comp in c["intra_set_components"]:
            for t in comp:
                if t not in members:
                    bad.append(f"{r['set_id']}: component contains non-member {t}")
    checks.append(_check("no_convergence_claim_rests_on_a_non_member", not bad,
                         "; ".join(bad[:5])))

    # ---- 4. B1: the convergence verdict follows its own rule ----
    bad = []
    for r in records:
        c = r["convergence"]
        expect = c["n_supporting_perturbations"] >= c["min_perturbations_for_convergence"]
        if bool(c["convergent"]) != expect:
            bad.append(f"{r['set_id']}: convergent={c['convergent']} but "
                       f"n_supporting={c['n_supporting_perturbations']}")
        if c["n_measured_perturbations"] == 1 and c["convergent"]:
            bad.append(f"{r['set_id']}: one measured perturbation is one experiment, "
                       "and it is never a convergence")
        if len(c["supporting_perturbations"]) != c["n_supporting_perturbations"]:
            bad.append(f"{r['set_id']}: supporting count does not match the list")
    checks.append(_check("convergence_verdict_follows_the_frozen_rule", not bad,
                         "; ".join(bad[:5])))

    # ---- 5. M1: a DEFINED enrichment always names the members behind it ----
    bad = []
    for r in records:
        for arm, e in r["enrichment"].items():
            if e["enrichment_value"] is None:
                if e["leading_edge"]:
                    bad.append(f"{r['set_id']}/{arm}: undefined score with an edge")
                continue
            if not e["leading_edge"]:
                bad.append(f"{r['set_id']}/{arm}: enrichment_value "
                           f"{e['enrichment_value']} with an EMPTY leading edge")
            if e["n_leading_edge"] != len(e["leading_edge"]):
                bad.append(f"{r['set_id']}/{arm}: leading-edge count disagrees")
            expect_side = ("top_leading_edge_at_or_before_the_positive_peak"
                           if e["enrichment_value"] > 0
                           else "bottom_trailing_edge_after_the_negative_trough")
            if e["leading_edge_side"] != expect_side:
                bad.append(f"{r['set_id']}/{arm}: edge side {e['leading_edge_side']} "
                           f"does not follow the sign of {e['enrichment_value']}")
    checks.append(_check("a_defined_enrichment_always_names_a_non_empty_edge", not bad,
                         "; ".join(bad[:5])))

    # ---- 5b. A3: THE COVERAGE ARITHMETIC AND PER-ARM ELIGIBILITY, RE-DERIVED ----
    # From the shipped bytes, against the verifier's OWN copy of the frozen policy. The
    # generator's thresholds are not consulted — they are CHECKED.
    method = doc["method"]
    declared = (method.get("coverage_policy_id"), method.get("min_source_coverage"),
                method.get("min_arm_ranked_members"))
    frozen = (SPEC_COVERAGE_POLICY_ID, SPEC_MIN_SOURCE_COVERAGE,
              SPEC_MIN_ARM_RANKED_MEMBERS)
    checks.append(_check(
        "the_artifact_ran_under_the_FROZEN_coverage_policy", declared == frozen,
        f"artifact declares {declared}; the frozen policy is {frozen} — a threshold "
        "loosened after the fact is the attack this governance exists to stop"))
    # The ESTIMAND, declared as negatives. The all-arm contract says this with a different
    # vocabulary than the legacy pair-scoped one — there is no "arm_eligibility_is_independent
    # _per_arm" key here because there is no pair to be independent OF. What it does declare is
    # every combination it refuses to have performed, and each of those is asserted. The
    # eligibility itself is not taken on trust from any of these: `_rederive` recomputes each
    # arm's disposition from the BOUND counts, per arm, with no arm consulting another.
    if contract == CONTRACT_LEGACY:
        negatives = {
            "arm_eligibility_is_independent_per_arm": True,
            "combined_arm_eligibility_permitted": False,
        }
    else:
        negatives = {
            "combined_objective_permitted": False,   # no combined/balanced/weighted objective
            "pareto_emitted": False,                 # join-time display, never a stored claim
            "joint_status_emitted": False,
            "pair_fields_emitted": False,            # a reusable arm knows no pair
            "pole_or_role_emitted": False,           # keyed by desired_change, never by pole
            "enrichment_rank_antisymmetry_assumed": False,   # all 120 arms are COMPUTED
            "enrichment_arms_are_computed_not_derived": True,
            "convergence_is_shared_across_arms": True,
        }
    wrong = {k: method.get(k) for k, want in negatives.items() if method.get(k) is not want}
    checks.append(_check(
        "arm_eligibility_is_independent_and_never_combined", not wrong,
        f"the artifact declares {wrong}; a reusable arm that admits a combined objective, a "
        "pole, a pair or an assumed antisymmetry is not a reusable arm"))

    bad = []
    for r in records:
        sid = r["set_id"]
        n_src = r.get("n_source_symbols")
        n_tgt = r["n_genes_in_target_universe"]

        # (i) the GLOBAL coverage arithmetic
        want_cov = (round(n_tgt / n_src, 6) if n_src else None)
        got_cov = r.get("target_source_coverage")
        if (want_cov is None) != (got_cov is None) or (
                want_cov is not None and abs(got_cov - want_cov) > FLOAT_TOL):
            bad.append(f"{sid}: target_source_coverage {got_cov} != {n_tgt}/{n_src}")

        # (ii) the GLOBAL disposition
        want_disp, want_passed = _global_disposition(got_cov)
        if r["global_coverage_disposition"] != want_disp:
            bad.append(f"{sid}: global disposition {r['global_coverage_disposition']} != "
                       f"{want_disp} for coverage {got_cov}")
        if bool(r["global_coverage_policy_passed"]) != want_passed:
            bad.append(f"{sid}: global_coverage_policy_passed "
                       f"{r['global_coverage_policy_passed']} != {want_passed}")

        # (iii) the PER-ARM arithmetic and eligibility. The arms are INDEPENDENT.
        for arm, e in r["enrichment"].items():
            n_hits = e["n_hits_in_ranking"]
            want_ac = (round(n_hits / n_src, 6) if n_src else None)
            got_ac = e["arm_evaluable_source_coverage"]
            if (want_ac is None) != (got_ac is None) or (
                    want_ac is not None and abs(got_ac - want_ac) > FLOAT_TOL):
                bad.append(f"{sid}/{arm}: arm_evaluable_source_coverage {got_ac} != "
                           f"{n_hits}/{n_src}")

            want_ad, want_rank = _arm_disposition(want_passed, n_hits,
                                                  e["enrichment_value"])
            if e["arm_coverage_disposition"] != want_ad:
                bad.append(f"{sid}/{arm}: arm disposition "
                           f"{e['arm_coverage_disposition']} != {want_ad}")
            if bool(e["arm_headline_rankable"]) != want_rank:
                bad.append(f"{sid}/{arm}: arm_headline_rankable "
                           f"{e['arm_headline_rankable']} != {want_rank} "
                           f"(global_passed={want_passed}, n_hits={n_hits}, "
                           f"defined={e['enrichment_value'] is not None})")

            # (iv) RECORD <-> ARM agreement. An arm may not be ranked on a global verdict
            # the record itself does not carry.
            if e["global_target_source_coverage"] != got_cov:
                bad.append(f"{sid}/{arm}: the arm block's global coverage "
                           f"{e['global_target_source_coverage']} disagrees with the "
                           f"record's {got_cov}")
            if e["arm_headline_rankable"] and not r["global_coverage_policy_passed"]:
                bad.append(f"{sid}/{arm}: headline-rankable while the RECORD says the "
                           "global coverage policy did not pass")
    checks.append(_check("coverage_and_per_arm_eligibility_rederive_from_the_record",
                         not bad, "; ".join(bad[:5])))

    # ---- 5c. A4: THE COUNTS THEMSELVES, RECONSTRUCTED FROM THE BOUND ARTIFACTS ----
    # Everything above re-derives the RATIOS from the record's own NUMERATORS and
    # DENOMINATORS. A forger who edits the counts and then honestly recomputes every ratio,
    # disposition and edge from them produces an artifact that passes every check above and
    # is entirely false — an audit promoted a ZERO-coverage pathway to headline-rankable
    # exactly that way, and it was ADMITTED with n_failed=0.
    #
    # So the counts are thrown away and computed again from the artifacts the run is BOUND
    # to. The declared value must EQUAL the reconstruction, and the RANKABILITY DECISION IS
    # TAKEN ON THE RECONSTRUCTED COUNTS — never on the declared ones.
    facts, rc_checks = RC.reconstruct(out_dir=out_dir, provenance=provenance,
                                      method=method, gene_sets_path=gene_sets_path,
                                      signature_matrix_root=signature_matrix_root)
    checks.extend(rc_checks)
    reconstruction: dict[str, Any] = {"reconstructed": facts is not None}
    if facts is not None:
        reconstruction.update(facts["identity"])
        reconstruction["rederived"] = _rederive(records, facts, checks)

        # THE THIRD LIST. `_set_view` proved the records and the convergence artifact name the
        # same sets; this proves they are the sets the PINNED RELEASE actually contains. Two
        # documents inside one bundle agreeing with each other is internal consistency; the
        # release is the only thing outside the bundle that can arbitrate.
        if contract == CONTRACT_ALL_ARM:
            release_ids = set(facts["sets"])
            emitted_ids = {r["set_id"] for r in records}
            checks.append(_check(
                GATE_SET_IDS_AGREE + "_and_the_pinned_release",
                release_ids == emitted_ids,
                f"the pinned release holds {len(release_ids)} sets; the bundle emits "
                f"{len(emitted_ids)}. Only in the release: "
                f"{sorted(release_ids - emitted_ids)[:3]}; only in the bundle: "
                f"{sorted(emitted_ids - release_ids)[:3]}"))

        # ---- 5d. THE STREAMED EVALUATED-PAIR DENOMINATOR, RE-DERIVED ----
        # The producer stopped emitting non-supportive pair records. `n_intra_set_pairs` is
        # the count of ALL pairs it evaluated, and it is the denominator the supportive
        # count is read against. Nothing checked it. So it is recomputed here from the bound
        # masked signatures — the union of the intra-set pairs over each set's MEASURED
        # members — and the declared number must equal it.
        true_pairs = facts["n_intra_set_pairs"]
        declared_pairs = conv_doc.get("n_intra_set_pairs",
                                      doc.get("n_intra_set_pairs"))
        reconstruction["n_intra_set_pairs"] = true_pairs
        if contract == CONTRACT_ALL_ARM:
            # MISSING IS A REFUSAL. `if declared is not None` was itself the bypass: DELETE
            # `n_intra_set_pairs`, reseal, and the gate simply did not run. A check a forger
            # can switch off by removing its subject is not a check. The all-arm producer
            # emits this number; a bundle that does not is not an all-arm bundle.
            ok = (isinstance(declared_pairs, int)
                  and not isinstance(declared_pairs, bool)
                  and declared_pairs >= 0
                  and declared_pairs == true_pairs)
            checks.append(_check(
                GATE_INTRA_SET_PAIRS, ok,
                f"the artifact declares n_intra_set_pairs={declared_pairs!r}; the BOUND "
                f"signatures evaluate {true_pairs}. The all-arm contract MUST declare a "
                "concrete non-negative evaluated-pair count: a denominator nobody recomputes "
                "is a denominator anybody can choose, and an ABSENT one is not an exemption"))
        elif declared_pairs is not None:
            # The legacy contract emitted every pair record and declares no such denominator.
            # Where it does declare one, it is re-derived.
            checks.append(_check(
                GATE_INTRA_SET_PAIRS, declared_pairs == true_pairs,
                f"the artifact declares n_intra_set_pairs={declared_pairs}; the BOUND "
                f"signatures evaluate {true_pairs}"))
        else:
            reconstruction["declares_no_evaluated_pair_denominator"] = True

        # ---- 5e. THE FROZEN CONVERGENCE-SIZE DOMAIN ----
        # The denominator above is only meaningful over the domain the pairs were drawn
        # from, so the domain is re-derived too — against the VERIFIER's OWN frozen policy
        # id, basis and maximum, never the artifact's. A run that raised its own maximum
        # could pair an oversized root, call it convergent, and stay perfectly coherent.
        bad = []
        for r in records:
            c, f = r["convergence"], facts["sets"].get(r["set_id"])
            if f is None:
                continue
            size = f["convergence"]["size"]
            for field, true_v in size.items():
                if c.get(field) != true_v:
                    bad.append(f"{r['set_id']}: declares {field}={c.get(field)!r}; the "
                               f"FROZEN policy re-derives {true_v!r}")
        # The policy the run DECLARES, in every place it declares it. `if field in block` was
        # a bypass of exactly the same shape: DELETE the policy id, reseal, and the
        # declaration check evaporates — leaving a bundle that names no size policy at all
        # and is congratulated for it. The all-arm producer emits all three fields in BOTH
        # the method block and the convergence artifact, so in that contract their ABSENCE is
        # a refusal, not a pass.
        frozen = {"convergence_size_policy_id": RC.SPEC_CONVERGENCE_SIZE_POLICY_ID,
                  "convergence_size_basis": RC.SPEC_CONVERGENCE_SIZE_BASIS,
                  "max_convergence_set_size": RC.SPEC_MAX_CONVERGENCE_SET_SIZE}
        required_blocks = ((("method", method), ("convergence", conv_doc))
                           if contract == CONTRACT_ALL_ARM else (("method", method),))
        for where, block in required_blocks:
            for field, true_v in frozen.items():
                if contract == CONTRACT_ALL_ARM and field not in block:
                    bad.append(f"the {where} block DECLARES NO {field}: a run that names no "
                               "convergence-size policy has not been held to one")
                elif field in block and block.get(field) != true_v:
                    bad.append(f"{where} ran under {field}={block.get(field)!r}; the FROZEN "
                               f"policy is {true_v!r}")
        checks.append(_check(GATE_CONVERGENCE_SIZE, not bad, "; ".join(bad[:5])))

    # ---- 6. the two evidence lines are side by side, NEVER fused ----
    fused = (method.get("evidence_lines_are_combined")
             if "evidence_lines_are_combined" in method
             else method.get("combined_objective_permitted"))
    checks.append(_check(
        "the_two_evidence_lines_are_never_combined", fused is False,
        f"the artifact declares fusion={fused!r}: enrichment and convergence are two "
        "evidence lines and there is no pathway score that is both"))
    # A reusable arm is keyed by DESIRED CHANGE — increase|decrease — never by the pole or
    # the role it happened to play in the pair that asked first. So the legacy check for the
    # two names {away_from_A, toward_B} is not tightened or loosened here, it is INAPPLICABLE:
    # those names do not exist in this contract. The invariant that survives is the one that
    # matters — every set carries the SAME arms, each arm is one direction of one program, and
    # both directions are present. An enrichment computed ACROSS arms would have nowhere to sit.
    arm_keys = [set(r["enrichment"]) for r in records]
    same_arms = all(a == arm_keys[0] for a in arm_keys) if arm_keys else False
    slots = arm_keys[0] if arm_keys else set()
    if contract == CONTRACT_LEGACY:
        # the legacy artifact names its two arms by ROLE, and that is checked as it was
        checks.append(_check(
            "enrichment_is_emitted_per_arm_never_across_arms",
            all(a == {"away_from_A", "toward_B"} for a in arm_keys)))
    else:
        # A reusable arm is keyed by DESIRED CHANGE — increase|decrease — never by the pole or
        # the role it played in the pair that asked first, so {away_from_A, toward_B} is not
        # loosened here, it is INAPPLICABLE: those names do not exist in this contract. An ARM
        # SLOT is (program, desired_change) — |admitted| x 2 — and the bundle emits one record
        # per (slot, set), so the record count is slots x sets. Confusing the two is how a
        # bundle missing four fifths of its arms would still look complete.
        changes = {k.split("|")[2] for k in slots}
        n_expected = doc.get("n_expected_arm_slots")
        n_sets_emitted = len(records)
        # CONCRETE, or refused. `n_expected is None or ...` let a forger delete the expected
        # slot count and disable the arm-completeness check entirely.
        ok = (same_arms and changes == {"increase", "decrease"}
              and isinstance(n_expected, int)
              and len(slots) == n_expected
              and len(raw_records) == n_expected * n_sets_emitted)
        checks.append(_check(
            "enrichment_is_emitted_per_arm_never_across_arms", ok,
            f"arms per set identical: {same_arms}; desired changes: {sorted(changes)}; "
            f"{len(slots)} arm slots (expected {n_expected}); {len(raw_records)} records "
            f"for {n_expected} slots x {n_sets_emitted} sets"))

    # ---- 7. EVERY set is emitted — including the ones nothing could be asked of ----
    # ...and the count comes from the PINNED RELEASE, at whichever place the contract binds
    # it. Reading it from a key the all-arm binding does not have returned None, and a None
    # here made this gate PASS ON NOTHING — a bundle could emit one set out of five and be
    # congratulated for completeness.
    binding_ = provenance["run_binding"]
    gs_block = (binding_.get("gene_sets")
                or (binding_.get("evidence_artifacts") or {}).get("gene_set_source")
                or {})
    n_sets = (gs_block.get("gene_set_release") or {}).get("n_sets")
    emitted = {r["set_id"] for r in records}
    if contract == CONTRACT_ALL_ARM:
        # A CONCRETE bound count, or nothing. `n_sets is None or ...` meant a forger could
        # DELETE n_sets from the binding, reseal, and the completeness gate would pass on
        # nothing at all — the most comfortable kind of green there is.
        ok = isinstance(n_sets, int) and len(emitted) == n_sets == len(records)
        detail = (f"the run binds n_sets={n_sets!r} and emits {len(emitted)} unique sets in "
                  f"{len(records)} records. The all-arm contract MUST bind a concrete set "
                  "count: a pathway missing from the table is indistinguishable from one "
                  "that was tested and found nothing, and an absent denominator is not a "
                  "reason to stop looking")
    else:
        ok = n_sets is None or len(records) == n_sets
        detail = (f"{len(records)} records for {n_sets} sets: a pathway missing from the "
                  "table is indistinguishable from one that was tested and found nothing")
    checks.append(_check("every_gene_set_in_the_bundle_is_emitted", ok, detail))

    return _report(provenance, identity, checks, n_records=len(records),
                   reconstruction=reconstruction)


def _report(provenance: dict[str, Any], identity: dict[str, Any],
            checks: list[dict[str, Any]], *, n_records: int,
            reconstruction: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    # EVERY read here is a `.get`. The reporter runs on the WORST artifact the verifier ever
    # sees — the absent one, the truncated one, the one whose provenance is `{}` — and a
    # reporter that raises on a missing key turns a REJECT into a stack trace. A crash is not
    # a verdict: it writes no report, names no gate, and tells a harness nothing about WHY.
    failures = _fails(checks)
    return {
        "schema_version": "spot.stage02_pathway_verification.v1",
        "verifier_id": VERIFIER_ID,
        "generator_is_not_verifier": True,
        "fail_closed": True,
        "pathway_run_id": provenance.get("pathway_run_id"),
        "pathway_method_sha256": provenance.get("pathway_method_sha256"),
        "artifact_identity": identity,
        "admission_policy": {
            "forbidden_key_pattern": admission.FORBIDDEN_KEY_PATTERN,
            "key_firewall_is_recursive": True,
        },
        "n_records": int(n_records),
        # WHAT the counts were recounted from, and what they came to. An admission that
        # names no evidence is an opinion.
        "reconstruction": reconstruction or {"reconstructed": False},
        "checks": checks,
        "n_failed": len(failures),
        "verdict": ADMIT if not failures else REJECT,
    }


# --------------------------------------------------------------------------- #
# A MINIMAL DETERMINISTIC CLI. Explicit inputs, an explicit persisted report, nonzero exit on
# any refusal. The persisted report is CONTENT-ADDRESSED: verdict + per-gate pass/fail only, no
# absolute paths or timestamps, so the runbook can bind report_sha256.
# --------------------------------------------------------------------------- #
def _cli_report(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": result.get("schema_version"),
        "verifier_id": result.get("verifier_id"),
        "generator_is_not_verifier": True,
        "fail_closed": True,
        "pathway_run_id": result.get("pathway_run_id"),
        "n_records": result.get("n_records"),
        "verdict": result.get("verdict"),
        "n_failed": result.get("n_failed"),
        "gates": [{"check": c["check"], "status": c["status"]}
                  for c in result.get("checks", [])],
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m direct.verify_pathway",
        description="Independent Stage-2 pathway (pathway.json) verifier: RE-DERIVES every "
                    "count from the pinned gene-set bundle, the bound universes, the arm "
                    "rankings and the masked signatures shipped in the bundle. Imports no "
                    "producer module. Exit 0 = ADMIT, nonzero = REJECT.")
    ap.add_argument("--out-dir", required=True,
                    help="the pathway bundle dir (pathway.json + pathway_provenance.json)")
    ap.add_argument("--gene-sets", default=None,
                    help="the pinned gene-set bundle to anchor the recount against (the "
                         "auditor's own copy of the release; a second opinion)")
    ap.add_argument(
        "--signature-matrix-root", default=None,
        help="the SHARED per-condition signature artifacts (Step 0). An all-arm bundle "
             "ships no signature bytes — it REFERENCES this matrix — so without it the "
             "convergence claim cannot be independently recomputed and the bundle is "
             "REFUSED rather than admitted on its own word")
    ap.add_argument("--out", required=True,
                    help="path to write the deterministic, content-addressed report JSON")
    args = ap.parse_args(argv)

    try:
        result = verify(out_dir=args.out_dir, gene_sets_path=args.gene_sets,
                        signature_matrix_root=args.signature_matrix_root)
    except Exception as exc:                       # a crash IS a verification failure
        result = {"schema_version": "spot.stage02_pathway_verification.v1",
                  "verifier_id": VERIFIER_ID, "verdict": REJECT, "n_failed": 1,
                  "checks": [{"check": "verifier_completed_without_error", "status": FAIL,
                              "detail": f"{type(exc).__name__}: {exc}"}]}

    report = _cli_report(result)
    report_bytes = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    report_sha256 = hashlib.sha256(report_bytes).hexdigest()
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(dict(report, report_sha256=report_sha256), fh, indent=2, sort_keys=True)
        fh.write("\n")

    print(json.dumps({"verdict": report["verdict"], "n_failed": report["n_failed"],
                      "report": args.out, "report_sha256": report_sha256}, indent=2))
    if report["verdict"] != ADMIT:
        for c in result.get("checks", []):
            if c["status"] != PASS:
                print(f"  REFUSE [{c['check']}] {c.get('detail', '')}", file=sys.stderr)
    return 0 if report["verdict"] == ADMIT else 1


if __name__ == "__main__":
    sys.exit(main())
