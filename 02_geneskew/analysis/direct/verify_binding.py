"""What the run CLAIMS about itself, verified — part of the STANDALONE verifier.

INDEPENDENCE RULE (test-enforced): imports nothing from the generator.

Split out of ``verify_run`` so each module stays readable. These are the checks over the
run BINDING and the PROVENANCE — the claims a run makes about what it stood on, as
opposed to the tables it emitted:

  * the support contract — support was unavailable, run_id hashed that fact, AND the
    counts it declares are the counts the release actually ships;
  * the evidence domain — its id, its RULE id and the size of the global pooled-main
    universe — checked in EVERY copy independently, and every copy compared to the
    INDEPENDENTLY derived raw coverage. A forged copy may never be excused by an honest
    one: both are written by the same producer, so "at least one of them is right" says
    nothing about either;
  * the release gate: a release-grade lane must have re-derived completeness from the
    raw source in ITS OWN invocation, and bound that;
  * the replay/completeness RULE IDS the run bound — not merely the word "complete";
  * the Stage-1 hard gates, re-derived from the validation rows rather than trusted;
  * run_id / question_id, re-derived from the binding content.

WHY A COUNT IS NOT SELF-CERTIFYING
----------------------------------
Every count in the binding is written by the producer and then hashed by the producer.
Re-deriving ``sha256(binding)`` proves the run hashed what it hashed — nothing more. So
a claim like "33,983 released pooled-main scopes" or "59,414 guide support estimates
observed" is checked against the RAW METADATA, re-enumerated here. Consistency between
two copies of a number is not evidence for the number; the release is.
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verify_rules as R  # noqa: E402
from verify_evidence import EVIDENCE_DOMAIN_RULE_ID  # noqa: E402
from verify_source import COMPLETENESS_RULE_ID, REPLAY_RULE_ID  # noqa: E402

# The release-gate vocabulary, RESTATED here rather than imported from the generator.
RELEASE_LANES = ("production", "research_only")
GATE_FRESH = "fresh_strict_replay"
GATE_NOT_REQUIRED = "not_required_fixture_lane"
GATE_STATES = (GATE_FRESH, GATE_NOT_REQUIRED)

# The RETIRED gate: a "pinned strict-preflight GO artifact", accepted on presentation
# and hashed into run_id. It authenticated nothing (any hand-authored five-field JSON
# passed) and was bound to no context (a genuine GO from one run authorised any other),
# so binding it proved only WHICH unverified claim the run had committed to. It is gone
# from the generator, and a run that presents one is refused here rather than read.
RETIRED_GATE_STATES = ("pinned_strict_preflight_go",)
RETIRED_GATE_KEYS = ("strict_preflight_sha256",)


def verify_support_contract(prov, binding, observed, rep):
    """Support must be EXPLICITLY unavailable — and its COUNTS must be the real ones.

    ``observed`` is re-enumerated by the verifier from the released by-guide / by-donor
    OBS metadata (never a layer, never the run's own provenance). Without it, the only
    thing checked was that the contract's counts agreed with each other, and three
    mutually consistent copies of ``999999`` sail through: the run declares it accounted
    for every released support estimate, and nothing has counted them.
    """
    contract = prov.get("support_contract") or {}
    rep.check("the run declares support explicitly UNAVAILABLE",
              contract.get("state") == R.SUPPORT_STATE_UNAVAILABLE
              and contract.get("guide_support_available") is False
              and contract.get("donor_support_available") is False
              and contract.get("support_may_elevate_evidence_tier") is False,
              f"support_contract={contract}")
    rep.check("no support estimate was projected or masked",
              contract.get("support_estimates_projected") == 0
              and contract.get("support_masks_built") == 0)
    rep.check("the support contract is bound into run_id",
              binding.get("stage2_support_contract") == contract,
              "the emitted contract is not the one run_id hashed")

    if observed is None:
        return
    # ...and every observed count, in EVERY copy, is the count the release ships.
    bound = binding.get("stage2_support_contract") or {}
    for where, doc in (("the support contract", contract),
                       ("the run binding", bound)):
        rep.check(f"{where} counts the guide support estimates the release "
                  "actually ships",
                  doc.get("n_guide_estimates_observed") == observed["n_guide"],
                  f"declares {doc.get('n_guide_estimates_observed')!r}, the release "
                  f"ships {observed['n_guide']}")
        rep.check(f"{where} counts the donor-pair support estimates the release "
                  "actually ships",
                  doc.get("n_donor_pair_estimates_observed") == observed["n_donor"],
                  f"declares {doc.get('n_donor_pair_estimates_observed')!r}, the "
                  f"release ships {observed['n_donor']}")
        rep.check(f"{where} counts the support estimates the release actually ships",
                  doc.get("n_support_estimates_observed") == observed["n_support"],
                  f"declares {doc.get('n_support_estimates_observed')!r}, the release "
                  f"ships {observed['n_support']}")
        rep.check(f"{where} names the support modalities the release actually ships",
                  list(doc.get("guide_modalities_observed") or [])
                  == observed["guide_modalities"]
                  and list(doc.get("donor_pairs_observed") or [])
                  == observed["donor_pairs"],
                  f"declares guides={doc.get('guide_modalities_observed')!r} "
                  f"donors={doc.get('donor_pairs_observed')!r}; the release ships "
                  f"guides={observed['guide_modalities']} "
                  f"donors={observed['donor_pairs']}")


def verify_evidence_domain(prov, binding, coverage, observed, rep):
    """EVERY copy of the domain claim, checked INDEPENDENTLY against the frozen id AND
    against the raw release.

    This check used to accept the correct domain in the run binding OR in provenance.
    That is not a check: a forged copy is masked by whichever honest copy happens to be
    read first, and the two are written by the same producer, so "one of them is right"
    is the weakest possible statement about either. It also accepted a bound manifest
    that declared NO domain at all — ``None`` was in the allowed set — which is the
    cheapest forgery available: delete the field and the check that was supposed to pin
    the domain passes silently.

    The scope COUNTS are held to the same standard. A wholly dropped scope has no
    manifest row, so no per-row check will ever look at it, and the only thing that can
    see it is a count — re-derived from the RAW DE obs, never read from the run.
    """
    bound = binding.get("stage2_evidence_domain") or {}
    emitted = prov.get("evidence_domain") or {}
    gm = binding.get("guide_manifest") or {}
    gm_domain = gm.get("evidence_domain")

    rep.check("the evidence domain in the RUN BINDING is the frozen domain",
              bound.get("domain_id") == R.EVIDENCE_DOMAIN_ID,
              f"run_id bound {bound.get('domain_id')!r}")
    rep.check("the evidence domain in PROVENANCE is the frozen domain",
              emitted.get("domain_id") == R.EVIDENCE_DOMAIN_ID,
              f"provenance says {emitted.get('domain_id')!r}")
    rep.check("the bound MANIFEST declares the frozen evidence domain, explicitly",
              gm_domain == R.EVIDENCE_DOMAIN_ID,
              f"the bound manifest declares {gm_domain!r}; a manifest that declares no "
              "domain has not been matched against one")

    rep.check("the domain RULE id in the RUN BINDING is the frozen rule",
              bound.get("rule_id") == EVIDENCE_DOMAIN_RULE_ID,
              f"run_id bound {bound.get('rule_id')!r}")
    rep.check("the domain RULE id in PROVENANCE is the frozen rule",
              emitted.get("rule_id") == EVIDENCE_DOMAIN_RULE_ID,
              f"provenance says {emitted.get('rule_id')!r}")

    n_bound = bound.get("n_global_pooled_main_scopes")
    n_emitted = emitted.get("n_global_pooled_main_scopes")
    rep.check("the global pooled-main scope count is bound into run_id",
              isinstance(n_bound, int) and n_bound == n_emitted,
              f"binding={n_bound!r} provenance={n_emitted!r}")

    if coverage is None:
        return
    released = coverage["n_released"]
    # EVERY copy of the count, against the RAW release. Agreement between copies is not
    # evidence: one producer wrote all of them.
    for where, value in (
            ("the run binding", n_bound),
            ("provenance", n_emitted),
            ("the run binding's manifest scope count", bound.get("manifest_n_scopes")),
            ("provenance's manifest scope count", emitted.get("manifest_n_scopes")),
            ("the bound manifest", gm.get("n_scopes"))):
        rep.check(f"the scope count in {where} IS the count the raw DE release ships",
                  value == released,
                  f"{where} says {value!r}, the raw DE release ships {released}")

    rep.check("the bound manifest's ROW count is the manifest's own row count",
              gm.get("n_rows") == coverage.get("n_manifest_rows")
              == bound.get("manifest_n_rows") == emitted.get("manifest_n_rows"),
              f"binding manifest n_rows={gm.get('n_rows')!r}, domain block says "
              f"{bound.get('manifest_n_rows')!r}, the manifest holds "
              f"{coverage.get('n_manifest_rows')!r}")

    if observed is None:
        return
    for where, doc in (("the run binding", bound), ("provenance", emitted)):
        rep.check(f"the observed support-estimate count in {where} IS the count the "
                  "release ships",
                  doc.get("n_support_estimates_observed") == observed["n_support"],
                  f"{where} says {doc.get('n_support_estimates_observed')!r}, the "
                  f"release ships {observed['n_support']}")


def verify_release_gate(binding, rep):
    """A release-grade run must have re-derived its gate, HERE, and bound that.

    There is exactly one passing state. The retired ``pinned_strict_preflight_go`` is
    refused explicitly rather than merely being absent from the allowed set, so a run
    carrying one gets a named refusal instead of a generic "unknown state".
    """
    g = binding.get("stage2_release_gate") or {}
    lane = binding.get("lane")
    rep.check("the release gate is bound into run_id", bool(g),
              "run_id hashed no release-gate block")
    rep.check("the run does not stand on the RETIRED pinned-preflight gate",
              g.get("state") not in RETIRED_GATE_STATES
              and not (set(RETIRED_GATE_KEYS) & set(g)),
              f"gate={g}; a pinned strict-preflight artifact authenticated nothing and "
              "was bound to no manifest, source or domain — it is not a gate")
    rep.check("the bound gate state is one this verifier knows",
              g.get("state") in GATE_STATES, f"gate state {g.get('state')!r}")
    if lane not in RELEASE_LANES:
        return
    rep.check("a release-grade run re-derived completeness from the RAW SOURCE in its "
              "own invocation, and bound that",
              g.get("state") == GATE_FRESH
              and g.get("strict_replay_required") is True
              and g.get("strict_replay_ran") is True,
              f"lane={lane!r} gate={g}")


def verify_replay_rules_bound(gm, rep):
    """run_id must bind WHICH replay/completeness rule produced its release gate.

    The binding used to read the obsolete ``replay_rule`` / ``completeness_rule`` keys.
    A v2 report has neither, so both came back null, and run_id hashed a null: the run
    was bound to the WORD "complete" without being bound to the rule that computed it,
    and could be re-gated later under a weaker rule while keeping its identity.
    """
    sr = gm.get("source_replay") or {}
    rep.check("run_id binds the exact v2 replay rule id",
              sr.get("replay_rule_id") == REPLAY_RULE_ID,
              f"bound {sr.get('replay_rule_id')!r}, expected {REPLAY_RULE_ID!r}")
    rep.check("run_id binds the exact v2 completeness rule id",
              sr.get("completeness_rule_id") == COMPLETENESS_RULE_ID,
              f"bound {sr.get('completeness_rule_id')!r}, expected "
              f"{COMPLETENESS_RULE_ID!r}")
    rep.check("no OBSOLETE rule key survives in the run binding",
              not ({"replay_rule", "completeness_rule"} & set(sr)),
              "the binding still carries a superseded rule key; it reads null from a "
              "v2 report, and a null nobody checks is a rule that stopped being bound")


def verify_stage1_gates(binding, by_sha, axis_doc, prov, cond, rep):
    """Re-derive the hard gates from the validation rows. Never trust the text."""
    rel = binding.get("stage1_release", {})
    hashes = rel.get("hashes", {})
    vpath = by_sha.get(hashes.get("validation_raw_sha256", ""))
    gpath = by_sha.get(hashes.get("gate_spec_raw_sha256", ""))
    if not (vpath and gpath):
        rep.check("Stage-1 validation + gate spec located by their pinned hashes",
                  False, "not found under --inputs-root")
        return
    validation = json.load(open(vpath))
    spec = json.load(open(gpath))
    cmp_ = {"ge": lambda v, t: v >= t, "gt": lambda v, t: v > t,
            "le": lambda v, t: v <= t, "lt": lambda v, t: v < t,
            "eq": lambda v, t: v == t}
    hard = spec["hard_gates"]
    measured = {}
    for row in validation["rows"]:
        if row["gate_id"] not in hard:
            continue
        th = spec["thresholds"][row["gate_id"]]
        ok = cmp_[th["comparator"]](float(row["value"]), float(th["threshold"]))
        measured.setdefault((row["program_id"], row["condition"]), {})[
            row["gate_id"]] = bool(ok)

    n_sel = sum(1 for g in measured.values()
                if all(g.get(h) for h in hard) and len(g) == len(hard))
    rep.check("Stage-1 production-selectable count re-derives from the metric rows",
              n_sel == rel.get("n_production_selectable"),
              f"re-derived {n_sel}, emitted {rel.get('n_production_selectable')}")
    rep.check("emitted production_gate_passed matches the re-derived gate",
              bool(prov.get("production_gate_passed")) == (n_sel > 0))

    lane = binding["lane"]
    for p in ("A", "B"):
        pair = (axis_doc[p]["program_id"], cond)
        derived = pair in {k for k, g in measured.items()
                           if all(g.get(h) for h in hard) and len(g) == len(hard)}
        if lane == "production":
            rep.check(f"production: pole {p} is genuinely gate-selectable", derived)
    if lane != "production":
        rep.check("a non-production run is never production_eligible",
                  prov.get("production_eligible") is False)
        rep.check("a non-production run is never stage3_eligible",
                  prov.get("stage3_eligible") is False)


def _v3_question_id(axis_doc, v3):
    """The v3 recipe, re-derived from the axis THAT ACTUALLY RAN.

    A v3 contract's question_id hashes the ordered ENDPOINTS — pole A at conditions[0], pole
    B at conditions[-1] — plus the analysis_mode. It is 16 hex and carries no lane prefix.
    That is a different hash of different content from the legacy id below, so a verifier
    that applied the legacy recipe to a v3 run would call an honest run forged.

    The BIOLOGY comes from ``axis_doc`` — the axis the run actually screened, panels and all
    — and never from the contract's own say-so. The ORDER and the MODE come from the v3
    binding block, which is hashed into ``run_binding_sha256`` and therefore into the run id:
    editing it to match a forged question_id renames the run's own directory.
    """
    conds = list(v3["conditions"])
    return R.content_sha256({
        "A": {"program_id": axis_doc["A"]["program_id"],
              "direction": axis_doc["A"]["direction"], "condition": conds[0]},
        "B": {"program_id": axis_doc["B"]["program_id"],
              "direction": axis_doc["B"]["direction"], "condition": conds[-1]},
        "analysis_mode": v3["analysis_mode"]})[:16]


def verify_identity(prov, binding, axis_doc, run_dir, rep):
    # WHICH contract drove this run decides WHICH recipe re-derives its question_id. The two
    # are not interchangeable: the legacy id is 32 hex over (poles, analysis_condition) with
    # a lane prefix; the v3 id is 16 hex over the ordered endpoints and the mode. A v3 run
    # was previously unverifiable here — it stamped a 64-hex biology hash that no recipe on
    # this path could reproduce — so this check could only ever have failed on it.
    #
    # Branched on the RUN BINDING, not on a free-standing provenance field: the binding is
    # hashed into the run id, so a run cannot lie about which contract drove it in order to
    # be checked by the laxer recipe.
    v3 = binding.get("stage1_v3")
    if v3:
        rep.check("question_id re-derives from the v3 biology alone (ordered endpoints)",
                  prov["question_id"] == _v3_question_id(axis_doc, v3))
        # ...and the endpoints the contract bound must be the biology that actually ran. The
        # question_id above is derived from the AXIS, so a v3 block naming other poles would
        # otherwise sit in the run identity unchallenged.
        rep.check("the v3 endpoints name the axis that actually ran",
                  all(v3["endpoints"][p]["program_id"] == axis_doc[p]["program_id"]
                      and v3["endpoints"][p]["direction"] == axis_doc[p]["direction"]
                      for p in ("A", "B")))
    else:
        q = R.content_sha256({
            "A": {"program_id": axis_doc["A"]["program_id"],
                  "direction": axis_doc["A"]["direction"]},
            "B": {"program_id": axis_doc["B"]["program_id"],
                  "direction": axis_doc["B"]["direction"]},
            "analysis_condition": prov["analysis_condition"]})[:32]
        prefix = {"synthetic": "fx_", "research_only": "rq_"}.get(binding["lane"], "")
        rep.check("question_id re-derives from the biology alone",
                  prov["question_id"] == prefix + q)
    full = R.content_sha256(binding)
    rep.check("run_binding_sha256 is the hash of the binding content",
              full == prov["run_binding_sha256"])
    rep.check("run_id is the binding hash and names the output directory",
              full[:16] == prov["run_id"]
              == os.path.basename(run_dir.rstrip("/")))
