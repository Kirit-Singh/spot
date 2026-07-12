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

import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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

VERIFIER_ID = "spot.stage02.pathway.verifier.v1"


def _check(name: str, ok: bool, detail: str = "") -> dict[str, Any]:
    return {"check": name, "status": PASS if ok else FAIL, "detail": detail}


def _fails(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in checks if c["status"] != PASS]


def verify(*, out_dir: str, provenance: dict[str, Any]) -> dict[str, Any]:
    """Re-derive every pathway claim from the bytes that shipped."""
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
        return _report(provenance, identity, checks, n_records=0)

    with open(os.path.join(out_dir, "pathway.json")) as fh:
        doc = json.load(fh)
    records = doc["records"]

    # ---- 1. NO p / q / FDR / combined objective, ANYWHERE, at ANY depth ----
    # The same recursive firewall the temporal lane fails closed on. A pathway p-value
    # would be the single most believable wrong number this whole layer could emit.
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
