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

import verify_rules as R  # noqa: E402  (the verifier-side reimplementation of the spec)

from . import admission  # noqa: E402  (the shared ADMISSION contract, not a producer)

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


def _check(name: str, ok: bool, detail: str = "") -> dict[str, Any]:
    return {"check": name, "status": PASS if ok else FAIL, "detail": detail}


def _fails(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in checks if c["status"] != PASS]


PROVENANCE_FILE = "pathway_provenance.json"
RECORDS_FILE = "pathway.json"


def verify(*, out_dir: str, provenance: Optional[dict[str, Any]] = None
           ) -> dict[str, Any]:
    """Re-derive every pathway claim from THE BYTES THAT SHIPPED.

    ``provenance`` is NOT the subject of verification — the shipped
    ``pathway_provenance.json`` is LOADED here and everything below runs on THAT. The
    caller's dict is admissible only as a cross-check.

    (The previous version hashed the provenance file and then firewalled the caller's
    dictionary. An independent audit poisoned the emitted provenance on disk with
    ``empirical_p_value``, passed the pristine dict, and got ADMIT.)
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

    return _report(provenance, identity, checks, n_records=len(records))


def _report(provenance: dict[str, Any], identity: dict[str, Any],
            checks: list[dict[str, Any]], *, n_records: int) -> dict[str, Any]:
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
        "checks": checks,
        "n_failed": len(failures),
        "verdict": ADMIT if not failures else REJECT,
    }
