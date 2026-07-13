"""INDEPENDENT verifier for a temporal pathway enrichment bundle. Fail-closed.

A SECOND IMPLEMENTATION, not a re-use of the producer. It imports NONE of the producer's
modules: the ranked enrichment statistic, the coverage governance, the arm-key grammar, the
native bundle/ranking reader and the not-evaluable convergence object are ALL re-derived here
from the written spec, so the verifier can DISAGREE with the generator instead of echoing it.
Content hashing is ``verify_rules`` (``R.content_sha256``); the only shared contract module is
``admission`` (``load_shipped`` + the recursive p/q firewall ``forbidden_keys``).

It reads the SHIPPED bytes off disk, RE-DERIVES the enrichment from the temporal DiD rankings the
bundle stands on, and refuses — each at a NAMED gate — an endpoint/within-condition bundle handed
in as a temporal input, a reverse-pair from/to swap, a missing or foreign arm, a forged ranking,
any convergence claim, a combined objective, a p/q/FDR alias at any depth, and an incomplete arm
set. It admits only when every gate passes.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from . import admission
from . import verify_rules as R

VERIFIER_ID = "spot.stage02.temporal_pathway.verifier.v1"
REPORT_SCHEMA = "spot.stage02_temporal_pathway_verification.v1"
ADMIT, REJECT = "ADMIT", "REJECT"

# ---- CONTRACT STRINGS, restated locally (a verifier that imported them from the producer would
# ---- bind to whatever the producer says today, not to the spec). ----
BUNDLE_FILE = "arm_bundle.json"
PROVENANCE_FILE = "temporal_pathway_provenance.json"
CONVERGENCE_FILE = "convergence.json"
SCHEMA_BUNDLE = "spot.stage02_temporal_pathway_arm_bundle.v1"
CONVERGENCE_SCHEMA = "spot.stage02_temporal_pathway_convergence.v1"
INPUT_BUNDLE_SCHEMA = "spot.stage02_temporal_arm_bundle.v1"
INPUT_RANKING_SCHEMA = "spot.stage02_temporal_arm_ranking.v1"
INPUT_LANE = "temporal"
INPUT_MODE = "temporal_cross_condition"
CONVERGENCE_STATUS_NOT_EVALUABLE = "not_evaluable_for_temporal_convergence"
DESIRED_CHANGES = ("increase", "decrease")

# ---- THE COVERAGE POLICY, re-derived exactly like verify_pathway does (its OWN copy). ----
SPEC_MIN_SOURCE_COVERAGE = 0.50
SPEC_MIN_ARM_RANKED_MEMBERS = 3
SPEC_COVERAGE_POLICY_ID = "spot.stage02.pathway.coverage_governance.prospective.v2"
_RANKABLE = "rankable"
_LOW = "descriptive_only_low_source_coverage"
_UNKNOWN = "descriptive_only_source_coverage_unknown"
_THIN = "descriptive_only_thin_arm"
_UNDEFINED = "undefined"

# ---- THE ENRICHMENT STATISTIC, re-implemented (weighted running-sum, half-even 6dp). ----
_SCORE_WEIGHT = 1.0


def _temporal_arm_key(program: str, change: str, from_c: str, to_c: str) -> str:
    """``temporal|program|desired_change|from|to`` — the native key, as a plain string builder."""
    return "|".join(("temporal", str(program), str(change), str(from_c), str(to_c)))


def _global_disposition(coverage: Optional[float]) -> tuple[str, bool]:
    """The GLOBAL coverage rule, re-derived. Necessary for a headline arm, never sufficient."""
    if coverage is None:
        return _UNKNOWN, False
    if coverage >= SPEC_MIN_SOURCE_COVERAGE:
        return _RANKABLE, True
    return _LOW, False


def _arm_disposition(global_passed: Optional[bool], n_hits: int,
                     enrichment_value: Optional[float]) -> tuple[str, bool]:
    """The PER-ARM rule, re-derived. Inclusive at the boundary; never combined with the global."""
    defined = enrichment_value is not None
    thick = n_hits >= SPEC_MIN_ARM_RANKED_MEMBERS
    passed = bool(global_passed) and thick and defined
    if not defined:
        return _UNDEFINED, passed
    if global_passed is None:
        return _UNKNOWN, passed
    if not global_passed:
        return _LOW, passed
    if not thick:
        return _THIN, passed
    return _RANKABLE, passed


def _enrich_one(ranked: list[tuple[str, float]], set_genes: set) -> dict[str, Any]:
    """Direction-aware ranked running-sum enrichment, re-implemented from the spec. Returns the
    peak (half-even 6dp), the leading-edge size, and the number of set members in the ranking."""
    n = len(ranked)
    hits = [(g, v) for g, v in ranked if g in set_genes]
    n_hits = len(hits)
    if n == 0 or n_hits == 0 or n_hits == n:
        return {"enrichment_value": None, "n_leading_edge": 0, "n_hits_in_ranking": n_hits}
    hit_mass = sum(abs(v) ** _SCORE_WEIGHT for _g, v in hits)
    if hit_mass == 0:
        return {"enrichment_value": None, "n_leading_edge": 0, "n_hits_in_ranking": n_hits}
    miss_step = 1.0 / (n - n_hits)
    running, peak, peak_rank = 0.0, 0.0, 0
    seen: list[str] = []
    edge_at_peak: list[str] = []
    for i, (gene, value) in enumerate(ranked, start=1):
        if gene in set_genes:
            running += (abs(value) ** _SCORE_WEIGHT) / hit_mass
            seen.append(gene)
        else:
            running -= miss_step
        if abs(running) > abs(peak):
            peak, peak_rank = running, i
            edge_at_peak = list(seen)
    if peak < 0:
        edge = [g for i, (g, _v) in enumerate(ranked, start=1)
                if g in set_genes and i > peak_rank]
    else:
        edge = edge_at_peak
    return {"enrichment_value": round(float(peak), 6), "n_leading_edge": len(edge),
            "n_hits_in_ranking": n_hits}


# --------------------------------------------------------------------------- #
# LOCAL native readers — the temporal bundle + rankings, and the gene sets.
# --------------------------------------------------------------------------- #
class _InputError(ValueError):
    pass


def _load_native_bundle(bundle_dir: str) -> dict[str, Any]:
    """Read the native temporal all-arm bundle + every DiD ranking, REFUSING an endpoint / within-
    condition bundle by schema, lane and mode — without importing the producer's reader."""
    b = admission.load_shipped(bundle_dir, "arm_bundle.json")["doc"]
    if str(b.get("schema_version")) != INPUT_BUNDLE_SCHEMA \
            or str(b.get("lane")) != INPUT_LANE or str(b.get("analysis_mode")) != INPUT_MODE:
        raise _InputError(f"not a native temporal all-arm bundle: schema="
                          f"{b.get('schema_version')!r} lane={b.get('lane')!r}")
    from_c, to_c = str(b["from_condition"]), str(b["to_condition"])
    admitted = sorted(str(p) for p in (b.get("program_admission") or {}).get("programs", []))
    if not admitted:
        raise _InputError("the temporal bundle admits no program")
    rankings: dict[str, dict[str, Any]] = {}
    for p in admitted:
        for c in DESIRED_CHANGES:
            rk = admission.load_shipped(
                os.path.join(bundle_dir, "rankings"), f"{p}__{c}.json")["doc"]
            if str(rk.get("schema_version")) != INPUT_RANKING_SCHEMA:
                raise _InputError(f"{p}__{c}: ranking schema is {rk.get('schema_version')!r}")
            rankings[_temporal_arm_key(p, c, from_c, to_c)] = rk
    return {"from": from_c, "to": to_c, "admitted": admitted, "rankings": rankings}


def _ranked(ranking: dict[str, Any]) -> list[tuple[str, float]]:
    """Evaluable rows only, ordered by rank -> [(target_id, arm_value)]."""
    rows = [r for r in (ranking.get("ranked") or [])
            if r.get("evaluable") and r.get("arm_value") is not None and r.get("rank") is not None]
    rows.sort(key=lambda r: r["rank"])
    return [(str(r["target_id"]), float(r["arm_value"])) for r in rows]


def _target_universe(rankings: dict[str, dict[str, Any]]) -> set:
    """The perturbation-target universe, re-derived from the shipped rankings."""
    return {str(r["target_id"]) for rk in rankings.values() for r in (rk.get("ranked") or [])}


def _gene_set_members(gene_doc: dict[str, Any], universe: set) -> dict[str, dict[str, Any]]:
    """Each set's members that fall in the perturbation-target universe, re-derived from the raw
    shipped gene-set doc — no genesets import."""
    out: dict[str, dict[str, Any]] = {}
    for s in (gene_doc.get("sets") or []):
        genes = [str(g) for g in (s.get("genes_target") or s.get("genes") or [])]
        members = {g for g in genes if g in universe}
        out[str(s["set_id"])] = {"members": members, "n_in_universe": len(members),
                                 "n_source_symbols": s.get("n_source_symbols")}
    return out


# --------------------------------------------------------------------------- #
class _Report:
    def __init__(self) -> None:
        self.gates: list[dict[str, Any]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.gates.append({"gate": name, "passed": bool(ok), "detail": "" if ok else str(detail)})
        return bool(ok)

    @property
    def failed(self) -> list[str]:
        return [g["gate"] for g in self.gates if not g["passed"]]

    def doc(self, **extra: Any) -> dict[str, Any]:
        verdict = ADMIT if (self.gates and not self.failed) else REJECT
        return {"schema_version": REPORT_SCHEMA, "verifier_id": VERIFIER_ID,
                "generator_is_not_verifier": True, "fail_closed": True, "verdict": verdict,
                "n_gates": len(self.gates), "n_passed": len(self.gates) - len(self.failed),
                "n_failed": len(self.failed), "failed_gates": self.failed, "gates": self.gates,
                **extra}


def verify(out_dir: str, *, temporal_bundle_dir: str, gene_sets_path: str) -> dict[str, Any]:
    """Verify the shipped temporal pathway bundle at ``out_dir`` against the temporal bundle + gene
    sets it was computed over. ``verdict == ADMIT`` iff every gate passed."""
    r = _Report()

    for fname in (BUNDLE_FILE, PROVENANCE_FILE, CONVERGENCE_FILE):
        if not r.check(f"the_shipped_file_{fname}_is_on_disk",
                       os.path.exists(os.path.join(out_dir, fname)), f"missing {fname}"):
            return r.doc()
    try:
        bundle = admission.load_shipped(out_dir, BUNDLE_FILE)["doc"]
        prov = admission.load_shipped(out_dir, PROVENANCE_FILE)["doc"]
        conv = admission.load_shipped(out_dir, CONVERGENCE_FILE)["doc"]
    except admission.ShippedDocError as exc:
        r.check("shipped_documents_load_from_disk", False, str(exc))
        return r.doc()
    r.check("shipped_documents_load_from_disk", True)

    # GATE: this IS a temporal pathway bundle — not an endpoint/within-condition one.
    r.check("the_bundle_is_a_temporal_pathway_bundle_not_an_endpoint",
            str(bundle.get("schema_version")) == SCHEMA_BUNDLE
            and str(bundle.get("lane")) == INPUT_LANE
            and str(bundle.get("analysis_mode")) == INPUT_MODE,
            f"schema={bundle.get('schema_version')!r} lane={bundle.get('lane')!r} "
            f"mode={bundle.get('analysis_mode')!r}")

    # GATE: the p/q/FDR/combined-objective firewall, recursive at any depth (shared contract).
    hits = admission.forbidden_keys(bundle) + admission.forbidden_keys(prov) \
        + admission.forbidden_keys(conv)
    r.check("no_forbidden_p_q_fdr_or_combined_key_at_any_depth", not hits, f"{hits[:6]}")
    r.check("inference_status_is_not_calibrated",
            str(bundle.get("inference_status")) == "not_calibrated"
            and str(prov.get("inference_status")) == "not_calibrated",
            f"{bundle.get('inference_status')!r}")

    # GATE: the temporal estimator identity is bound (a temporal result may not float free).
    method = bundle.get("method") or {}
    rb = prov.get("run_binding") or {}
    r.check("the_temporal_estimator_identity_is_bound",
            bool(method.get("temporal_method_sha256")) and bool(rb.get("temporal_bundle_id"))
            and method.get("recomputes_temporal_estimand") is False,
            f"temporal_method={method.get('temporal_method_sha256')!r} "
            f"bundle_id={rb.get('temporal_bundle_id')!r}")

    # GATE: convergence is not_evaluable — no claim, no supportive pair, no denominator.
    r.check("convergence_is_not_evaluable_for_temporal_with_no_support",
            str(conv.get("convergence_status")) == CONVERGENCE_STATUS_NOT_EVALUABLE
            and not conv.get("supportive_pairs")
            and conv.get("denominator") in (None, 0)
            and int(conv.get("n_supporting_perturbations") or 0) == 0
            and int(conv.get("n_intra_set_pairs") or 0) == 0
            and str((bundle.get("convergence_ref") or {}).get("convergence_status"))
            == CONVERGENCE_STATUS_NOT_EVALUABLE,
            f"status={conv.get('convergence_status')!r} pairs={conv.get('supportive_pairs')!r}")
    # GATE: re-derive the not-evaluable convergence hash from the shipped bytes (R.content_sha256).
    body = {k: v for k, v in conv.items()
            if k not in ("convergence_sha256", "temporal_pathway_run_id")}
    r.check("convergence_hash_rederives_from_the_shipped_bytes",
            conv.get("convergence_sha256") == R.content_sha256(body)
            and str(conv.get("schema_version")) == CONVERGENCE_SCHEMA,
            "the convergence artifact does not hash to its own not-evaluable bytes")

    # ---- RE-DERIVE from the temporal bundle it stands on (a native reader of our own) ----
    try:
        loaded = _load_native_bundle(temporal_bundle_dir)
    except (admission.ShippedDocError, _InputError, KeyError) as exc:
        r.check("the_bound_temporal_bundle_loads_natively", False, str(exc))
        return r.doc()
    r.check("the_bound_temporal_bundle_loads_natively", True)
    from_c, to_c, admitted = loaded["from"], loaded["to"], loaded["admitted"]

    # GATE: forged ranking bytes — re-hash each input ranking, compare to what the bundle bound.
    bound_rank = rb.get("temporal_ranking_sha256") or {}
    forged = [k for k, rk in loaded["rankings"].items()
              if bound_rank.get(k) != R.content_sha256(rk)]
    r.check("every_bound_ranking_hash_rederives_from_the_shipped_ranking_bytes",
            not forged and set(bound_rank) == set(loaded["rankings"]),
            f"ranking hash mismatch for {forged[:4]}")

    # GATE: complete arm set — exactly |admitted| x 2, and every program x change present.
    expected_keys = {_temporal_arm_key(p, c, from_c, to_c)
                     for p in admitted for c in DESIRED_CHANGES}
    record_keys = {str(rec.get("temporal_arm_key")) for rec in bundle.get("records") or []}
    r.check("the_arm_set_is_complete_admitted_programs_times_two",
            int(bundle.get("n_arm_slots") or 0) == len(admitted) * 2
            and record_keys == expected_keys,
            f"record - expected = {sorted(record_keys - expected_keys)[:4]}; "
            f"expected - record = {sorted(expected_keys - record_keys)[:4]}")

    # GATE: every record's key is the NATIVE temporal key for THIS ordered pair — refuses a
    # foreign/direct key AND a reverse-pair from/to swap.
    bad_key = [rec.get("temporal_arm_key") for rec in bundle.get("records") or []
               if str(rec.get("temporal_arm_key")) != _temporal_arm_key(
                   str(rec.get("program_id")), str(rec.get("desired_change")),
                   str(rec.get("from_condition")), str(rec.get("to_condition")))
               or str(rec.get("from_condition")) != from_c
               or str(rec.get("to_condition")) != to_c]
    r.check("every_record_key_is_the_native_temporal_key_no_reverse_swap_no_foreign_arm",
            not bad_key, f"{bad_key[:4]}")

    # GATE: RE-DERIVE the enrichment independently (generator != verifier). The target universe is
    # re-derived from the shipped rankings; each set's members from the raw gene-set doc.
    universe = _target_universe(loaded["rankings"])
    gene_doc = admission.load_shipped(
        os.path.dirname(gene_sets_path) or ".", os.path.basename(gene_sets_path))["doc"]
    sets = _gene_set_members(gene_doc, universe)
    by_key = {(str(rec.get("temporal_arm_key")), str(rec.get("set_id"))): rec
              for rec in bundle.get("records") or []}
    enrich_bad: list[str] = []
    cov_bad: list[str] = []
    for p in admitted:
        for c in DESIRED_CHANGES:
            key = _temporal_arm_key(p, c, from_c, to_c)
            ranked = _ranked(loaded["rankings"][key])
            for set_id, s in sets.items():
                e = _enrich_one(ranked, s["members"])
                rec = by_key.get((key, set_id))
                if rec is None or rec.get("enrichment_value") != e["enrichment_value"] \
                        or rec.get("n_leading_edge") != e["n_leading_edge"]:
                    enrich_bad.append(f"{key}/{set_id}")
                    continue
                n_src = s["n_source_symbols"]
                cov = (s["n_in_universe"] / n_src) if n_src else None
                gdisp, gpass = _global_disposition(cov)
                adisp, apass = _arm_disposition(
                    gpass, e["n_hits_in_ranking"], e["enrichment_value"])
                if (rec.get("global_coverage_disposition") != gdisp
                        or rec.get("global_coverage_policy_passed") != gpass
                        or rec.get("arm_coverage_disposition") != adisp
                        or rec.get("arm_headline_rankable") != apass):
                    cov_bad.append(f"{key}/{set_id}")
    r.check("enrichment_rederives_from_the_temporal_ranking_for_every_arm_and_set",
            not enrich_bad, f"{enrich_bad[:4]}")

    # GATE: coverage / per-arm eligibility re-derive, and are never combined into one score.
    cov_present = all(("arm_headline_rankable" in rec and "global_coverage_disposition" in rec)
                      for rec in bundle.get("records") or [])
    r.check("coverage_and_per_arm_eligibility_are_present_and_never_combined",
            cov_present and not cov_bad, f"{cov_bad[:4]}")

    # GATE: records_sha256 recomputes from the emitted records.
    r.check("records_sha256_recomputes_from_the_emitted_records",
            bundle.get("records_sha256") == R.content_sha256(bundle.get("records") or []),
            "records hash does not match the shipped records")

    return r.doc(from_condition=from_c, to_condition=to_c,
                 n_records=len(bundle.get("records") or []))
