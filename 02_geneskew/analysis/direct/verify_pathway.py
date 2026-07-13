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

REQUIRED_FILES = ("pathway.json", "pathway_provenance.json")

VERIFIER_ID = "spot.stage02.pathway.verifier.v2"

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


PROVENANCE_FILE = "pathway_provenance.json"
RECORDS_FILE = "pathway.json"


def verify(*, out_dir: str, provenance: Optional[dict[str, Any]] = None,
           gene_sets_path: Optional[str] = None) -> dict[str, Any]:
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
    files = {n: (file_sha256(os.path.join(out_dir, n))
                 if os.path.exists(os.path.join(out_dir, n)) else None)
             for n in REQUIRED_FILES}
    identity = {"files": files, "artifact_sha256": content_hash(files),
                "required_files": list(REQUIRED_FILES)}
    checks: list[dict[str, Any]] = []

    absent = [n for n, sha in files.items() if sha is None]
    checks.append(_check("every_required_file_is_present", not absent,
                         f"absent: {absent}"))
    if absent:
        return _report(provenance or {}, identity, checks, n_records=0)

    # ---- 0. LOAD BOTH SHIPPED DOCUMENTS. This is what gets verified. ----
    try:
        shipped_prov = admission.load_shipped(out_dir, PROVENANCE_FILE)
        shipped_doc = admission.load_shipped(out_dir, RECORDS_FILE)
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
    records = doc["records"]

    # ---- 1. NO p / q / FDR / combined objective, ANYWHERE, at ANY depth ----
    # The same recursive firewall the temporal lane fails closed on, over the SHIPPED
    # bytes of both documents. A pathway p-value would be the single most believable
    # wrong number this whole layer could emit.
    hits = admission.forbidden_keys(doc) + admission.forbidden_keys(provenance)
    checks.append(_check("no_forbidden_key_at_any_depth", not hits,
                         f"forbidden keys: {sorted(set(hits))[:8]}"))
    checks.append(_check(
        "inference_status_is_not_calibrated",
        provenance["inference_status"] == "not_calibrated"))

    # ---- 2. CONTENT ADDRESSING: the id follows the content ----
    stripped = [{k: v for k, v in r.items()
                 if k not in ("pathway_run_id", "pathway_method_sha256")}
                for r in records]
    recomputed = content_hash(stripped)
    claimed = doc["records_sha256"]
    checks.append(_check("records_sha256_recomputes_from_the_emitted_records",
                         recomputed == claimed,
                         f"recomputed {recomputed[:16]} != claimed {claimed[:16]}"))
    checks.append(_check(
        "the_run_binding_names_the_records_it_shipped",
        provenance["run_binding"]["records_sha256"] == claimed))
    checks.append(_check(
        "every_record_carries_the_run_id",
        all(r.get("pathway_run_id") == provenance["pathway_run_id"]
            for r in records)))

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
    checks.append(_check(
        "arm_eligibility_is_independent_and_never_combined",
        method.get("arm_eligibility_is_independent_per_arm") is True
        and method.get("combined_arm_eligibility_permitted") is False))

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
                                      method=method, gene_sets_path=gene_sets_path)
    checks.extend(rc_checks)
    reconstruction: dict[str, Any] = {"reconstructed": facts is not None}
    if facts is not None:
        reconstruction.update(facts["identity"])
        reconstruction["rederived"] = _rederive(records, facts, checks)

    # ---- 6. the two evidence lines are side by side, NEVER fused ----
    checks.append(_check(
        "the_two_evidence_lines_are_never_combined",
        doc["method"]["evidence_lines_are_combined"] is False))
    both_arms = all(set(r["enrichment"]) == {"away_from_A", "toward_B"}
                    for r in records)
    checks.append(_check("enrichment_is_emitted_per_arm_never_across_arms", both_arms))

    # ---- 7. EVERY set is emitted — including the ones nothing could be asked of ----
    n_sets = provenance["run_binding"]["gene_sets"].get("gene_set_release", {}).get(
        "n_sets")
    checks.append(_check(
        "every_gene_set_in_the_bundle_is_emitted",
        n_sets is None or len(records) == n_sets,
        f"{len(records)} records for {n_sets} sets: a pathway missing from the table is "
        "indistinguishable from one that was tested and found nothing"))

    return _report(provenance, identity, checks, n_records=len(records),
                   reconstruction=reconstruction)


def _report(provenance: dict[str, Any], identity: dict[str, Any],
            checks: list[dict[str, Any]], *, n_records: int,
            reconstruction: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    failures = _fails(checks)
    return {
        "schema_version": "spot.stage02_pathway_verification.v1",
        "verifier_id": VERIFIER_ID,
        "generator_is_not_verifier": True,
        "fail_closed": True,
        "pathway_run_id": provenance["pathway_run_id"],
        "pathway_method_sha256": provenance["pathway_method_sha256"],
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
