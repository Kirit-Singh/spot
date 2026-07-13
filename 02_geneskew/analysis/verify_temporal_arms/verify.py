"""THE RELEASE-LEVEL VERIFIER. Reopens every artifact from disk and re-derives the topology.

WHAT IT IS FOR
--------------
The producer emits six ordered-pair bundles carrying 120 logical arms and, beside each
one, its own admission report. That report is a SELF-REPORT: it is recorded here and it is
never sufficient. This module re-derives the whole release from two things it did not
write — the bound Stage-1 v3 release, and the bytes on disk.

THE TOPOLOGY IS DERIVED, NEVER ASSERTED
---------------------------------------
The bundle set is not read from the producer's inventory: it is DERIVED from the release's
own conditions, and then looked for on disk.

    ordered pairs   = every ordered pair of DISTINCT released conditions      (3 -> 6)
    programs        = every base-portable, projectable program in the view    (-> 10)
    arms per bundle = programs x desired changes                              (-> 20)
    logical arms    = arms per bundle x ordered pairs                         (-> 120)

Every one of those numbers is a CONSEQUENCE. Nothing here holds a 6, a 10, a 20 or a 120,
and nothing here names a condition or a program: a verifier with a hard-coded pair would
confirm the topology it was told to expect rather than the one that shipped.

DIRECTION IS IDENTITY
---------------------
The reverse-direction bundle is a DIFFERENT artifact, not a view of this one, and its base
deltas must be the exact negation of the forward bundle's. Checking that ACROSS the two
bundles is the only way to catch a release whose two directions are each internally
consistent and jointly a lie.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from . import admission, code_identity, direct_source, rules, schema
from . import bundle as bundle_check
from . import release as release_mod
from .canonical import content_hash, file_sha256, sha256_hex
from .failures import Failures

ADMIT = "ADMIT"
REJECT = "REJECT"

VERIFIER_ID = "spot.stage02.temporal.arm.independent_verifier.v1"
RUN_ID_RULE_ID = "spot.stage02.temporal.arm.run_id.v1"
RUN_ID_LEN = 16


def verify_release(*, release_root: str, bundle_root: str,
                   expect_conditions: Optional[Any] = None,
                   expect_scorer_view_prefix: Optional[str] = None,
                   expect_scorer_projection_prefix: Optional[str] = None,
                   sign: bool = False,
                   producer_checkout: Optional[str] = None,
                   require_clean_checkout: bool = True,
                   env_lock: Optional[str] = None,
                   direct_bundles: Optional[dict] = None,
                   w10_reports: Optional[dict] = None,
                   expect_env_lock_sha256: Optional[str] =
                   code_identity.FROZEN_STAGE2_ENV_LOCK_SHA256,
                   host_denylist=()) -> dict[str, Any]:
    """Verify the whole temporal arm release. Returns a TYPED, CONTENT-ADDRESSED report.

    ``sign=True`` also WRITES the authoritative ``temporal_verification.json`` beside each
    bundle — the verdict downstream reads. It is written HERE, by the lane that reopened the
    bytes, and never by the lane that produced them.
    """
    f = Failures()

    try:
        bound = release_mod.load_release(release_root)
    except release_mod.ReleaseRefused as exc:
        f.check("release_shape_is_the_current_stage1_v3_release", False, "release",
                str(exc))
        return _report(f, bound=None, bundles=[], counts={}, run_id=None)

    for gate, pin, fn in (
            ("release_conditions_match_the_pinned_universe", expect_conditions,
             lambda: release_mod.require_conditions(bound, expect_conditions)),
            ("scorer_view_binding_matches_the_pinned_prefix", expect_scorer_view_prefix,
             lambda: release_mod.require_scorer_binding(
                 bound, view_prefix=expect_scorer_view_prefix)),
            ("scorer_projection_binding_matches_the_pinned_prefix",
             expect_scorer_projection_prefix,
             lambda: release_mod.require_scorer_binding(
                 bound, projection_prefix=expect_scorer_projection_prefix))):
        if pin:
            try:
                fn()
            except release_mod.ReleaseRefused as exc:
                f.check(gate, False, "release", str(exc))

    docs, counts = _bundles(f, bound, bundle_root, host_denylist)
    _directions(f, docs)
    run_id = _run_identity(f, bound, docs)
    _release_level(f, bound, docs)
    inventory = admission.inventory(f, bound, bundle_root, docs, host_denylist)

    # ONE BUILD produced the whole release, and it is re-derived against a checkout the
    # CALLER pins. Checking only the first bundle would let a release carry six different
    # builds and be judged on one of them: a fake-but-self-consistent commit on bundle 2..6
    # would never be looked at, and the envelope — which binds one code_identity — would
    # print the honest one over the top of it.
    recorded = _one_code_identity(f, docs)
    _one_stage1_binding(f, docs)
    code_identity.check_env_lock(f, _one_env_lock(f, docs), env_lock,
                                expect_sha256=expect_env_lock_sha256)
    direct_source.verify_endpoints(f, bound, docs, direct_bundles or {},
                                  w10_reports or {})

    if producer_checkout:
        code_identity.check(f, recorded,
                            digest_root=os.path.join(producer_checkout, "02_geneskew"),
                            repo=producer_checkout,
                            require_clean=require_clean_checkout)
    else:
        f.check("the_producer_checkout_was_pinned_for_code_identity", False, "release",
                "--producer-checkout was not supplied, so the code identity the bundles "
                "record could not be RE-DERIVED and the final clean-tree status could not "
                "be decided. A recorded build nobody re-derived is a build nobody checked")

    report = _report(f, bound=bound, bundles=docs, counts=counts, run_id=run_id)
    if sign:
        report = dict(report)
        report["external_verification_envelope"] = admission.write_envelope(
            report=report, inventory=inventory, docs=docs, bundle_root=bundle_root,
            verifier_id=VERIFIER_ID, rules_id=rules.RULES_ID, id_len=RUN_ID_LEN)
    return report


def _bundles(f: Failures, bound, bundle_root: str,
             host_denylist) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Find the bundles the RELEASE implies, reopen each from disk, and re-derive it."""
    root = os.path.abspath(str(bundle_root))
    expected = {rules.bundle_dirname(a, b): (a, b) for a, b in bound.ordered_pairs}
    present = {d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d))}

    missing = sorted(set(expected) - present)
    f.check("every_ordered_pair_of_the_release_has_exactly_one_bundle", not missing,
            "release",
            f"the release ships {len(bound.conditions)} conditions, so it has "
            f"{len(bound.ordered_pairs)} ordered pairs; these have no bundle: {missing}")
    extra = sorted(present - set(expected))
    f.check("no_bundle_directory_the_release_did_not_ask_for", not extra, "release",
            f"{extra} name comparisons the bound release did not release")

    docs: list[dict[str, Any]] = []
    counts = {"base_deltas": 0, "arm_values": 0}
    for dirname in sorted(set(expected) & present):
        frm, to = expected[dirname]
        d = os.path.join(root, dirname)
        bpath = os.path.join(d, schema.BUNDLE_FILENAME)
        if not f.check("the_bundle_file_is_on_disk", os.path.exists(bpath), dirname,
                       schema.BUNDLE_FILENAME):
            continue

        # REOPENED FROM DISK. The subject of the verification is what landed, never what
        # somebody held in memory and said they wrote.
        with open(bpath, "rb") as fh:
            raw = fh.read()
        doc = json.loads(raw)

        sub, sub_counts = bundle_check.verify_bundle(
            doc, bound=bound, from_condition=frm, to_condition=to, artifact_dir=d,
            host_denylist=host_denylist)
        f.extend(sub)
        for k in counts:
            counts[k] += sub_counts.get(k, 0)

        _provenance_file(f, d, dirname, doc, raw, bound, host_denylist)
        producer = _no_producer_verdict(f, d, dirname)
        docs.append({"dirname": dirname, "from_condition": frm, "to_condition": to,
                     "doc": doc, "raw_sha256": file_sha256(bpath),
                     "canonical_sha256": content_hash(doc),
                     "producer_self_report": producer})
    return docs, counts


def _provenance_file(f: Failures, d: str, dirname: str, doc: dict[str, Any],
                     raw: bytes, bound, host_denylist) -> None:
    """``temporal_provenance.json`` — WHAT the bundle stood on, bound to its exact bytes."""
    ppath = os.path.join(d, schema.PROVENANCE_FILENAME)
    if not f.check("the_provenance_file_is_on_disk", os.path.exists(ppath), dirname,
                   schema.PROVENANCE_FILENAME):
        return
    with open(ppath) as fh:
        prov = json.load(fh)

    problems = schema.exact_keys(prov, schema.PROVENANCE_KEYS, "provenance")
    f.check("provenance_keys_are_the_exact_allowlist", not problems, dirname,
            "; ".join(problems))

    # THE FIREWALLS RUN ON THE PROVENANCE TOO. It is a shipped artifact of the reusable-arm
    # release, and a banned field inside it is a banned field in the release.
    banned = schema.banned_keys(prov)
    f.check("provenance_carries_no_role_pole_pair_pareto_or_batch_field", not banned,
            dirname,
            f"{banned}. A reusable arm's provenance may not use the ROLE/POLE vocabulary "
            "at any depth: the whole point of the topology is that a role is JOIN-TIME "
            "metadata, and a firewall that reads intent instead of names is not a firewall")
    machine = schema.machine_path_hits(prov, host_denylist=host_denylist)
    f.check("provenance_carries_no_machine_path_hostname_or_private_address", not machine,
            dirname, str(machine))
    if problems:
        return

    f.check("provenance_binds_the_exact_bundle_bytes_it_describes",
            prov["bundle_file"] == schema.BUNDLE_FILENAME
            and prov["bundle_raw_sha256"] == sha256_hex(raw)
            and prov["bundle_canonical_sha256"] == content_hash(doc)
            and prov["bundle_id"] == doc.get("bundle_id"), dirname,
            "a provenance that named its bundle only by key could be paired with a "
            "different inventory of the same ordered pair")

    rb = prov.get("run_binding") or {}
    rbp = schema.exact_keys(rb, schema.RUN_BINDING_KEYS, "run_binding")
    f.check("provenance_run_binding_keys_are_the_exact_allowlist", not rbp, dirname,
            "; ".join(rbp))

    # THE CANONICAL STAGE-2 INPUTS: ONE fixed-key object, every field present and non-null,
    # and every field equal to the method it claims to bind. Five fields loose in
    # run_binding are five things a reader can forget one of; one object is a thing it can
    # hash, compare and refuse as a unit.
    si = rb.get("stage2_inputs")
    sip = schema.exact_keys(si if isinstance(si, dict) else {}, schema.STAGE2_INPUTS_KEYS,
                            "stage2_inputs")
    if f.check("provenance_carries_a_canonical_fixed_key_stage2_inputs_object",
               isinstance(si, dict) and not sip, dirname,
               "; ".join(sip) or "run_binding ships no stage2_inputs object"):
        nulls = sorted(k for k in schema.STAGE2_INPUTS_KEYS
                       if si.get(k) in (None, "", [], {}))
        f.check("no_stage2_input_is_null", not nulls, dirname,
                f"{nulls} are null; an input a run cannot name is an input nobody can check")
        method = doc.get("method") or {}
        drift = sorted(k for k in schema.STAGE2_INPUTS_KEYS
                       if k in method and si.get(k) != method.get(k))
        f.check("the_stage2_inputs_are_the_method_the_bundle_declares", not drift, dirname,
                f"{drift} disagree with the bundle's own method block")

    # THE STAGE-1 BINDING, re-derived against the release WE loaded — not against the one
    # the producer says it read.
    sel = rb.get("selection_release") or {}
    f.check("provenance_binds_the_stage1_scorer_view_of_the_bound_release",
            sel.get("registry_scorer_view_sha256") == bound.scorer_view_sha256, dirname,
            f"provenance binds {sel.get('registry_scorer_view_sha256')}, the bound "
            f"release's scorer view canonically hashes to {bound.scorer_view_sha256}")
    f.check("provenance_binds_the_effect_universe_it_projected",
            bool(sel.get("effect_universe_sha256")), dirname, "")


def _no_producer_verdict(f: Failures, d: str, dirname: str) -> dict[str, Any]:
    """The producer's bundle directory may not contain a VERDICT. It may contain evidence.

    ``temporal_verification.json`` is the EXTERNAL admission, and it lives ONCE, at the
    release root, written by this lane. A copy inside a producer bundle directory is a
    self-verdict: a reader resolving it by path would find an admission the producer wrote
    about itself, and it would look exactly like the real thing.
    """
    stray = [n for n in (schema.ENVELOPE_FILENAME, schema.LEGACY_VERDICT_FILENAME)
             if os.path.exists(os.path.join(d, n))]
    f.check("no_verdict_file_inside_a_producer_bundle_directory", not stray, dirname,
            f"{stray} in the producer's bundle directory. The external admission is ONE "
            "file at the release root, written by the lane that reopened the bytes. A "
            "verdict sitting in the directory it judges is, to a reader resolving it by "
            "path, indistinguishable from a self-verdict")

    # The producer's PREFLIGHT: recorded, never evidence. The one thing it may not do is
    # claim to be an admission, or sign itself with this lane's identity.
    ppath = os.path.join(d, schema.PREFLIGHT_FILENAME)
    if not os.path.exists(ppath):
        return {"preflight": None}
    with open(ppath) as fh:
        pre = json.load(fh)
    f.check("the_producer_preflight_does_not_claim_to_be_an_admission",
            pre.get("is_admission") is False
            and pre.get("verifier_id") != VERIFIER_ID, dirname,
            "a producer self-check may say it passed; it may not say it was ADMITTED, and "
            "it may not sign itself with the independent verifier's contract")
    machine = schema.machine_path_hits(pre)
    f.check("the_producer_preflight_carries_no_machine_path", not machine, dirname,
            str(machine))
    return {"preflight": {"self_check_passed": pre.get("self_check_passed"),
                          "is_admission": pre.get("is_admission")}}


def _directions(f: Failures, docs: list[dict[str, Any]]) -> None:
    """The reverse bundle must negate every base delta. Checked ACROSS the two artifacts.

    Each direction can be internally perfect and the PAIR of them still be a lie: only a
    cross-bundle check can see it.
    """
    by_pair = {(d["from_condition"], d["to_condition"]): d["doc"] for d in docs}
    for (frm, to), doc in sorted(by_pair.items()):
        other = by_pair.get((to, frm))
        if other is None:
            continue
        rev = {b["base_key"]: b["base_delta"] for b in other["base_records"]}
        bad = []
        for base in doc["base_records"]:
            want = rev.get(base["base_key"])
            got = base["base_delta"]
            if got is None:
                if want is not None:
                    bad.append(base["base_key"])
            elif want is None or want != -got:
                bad.append(base["base_key"])
        f.check("reverse_direction_bundle_negates_every_base_delta", not bad,
                f"{frm} -> {to}",
                f"{len(bad)} base delta(s) are not the exact negation of the reverse "
                f"bundle's: {bad[:3]}. Swapping the ordered pair negates the difference — "
                "an artifact where it does not is not a difference of these two conditions")


def run_id_for(*, release_binding: dict[str, Any], method: dict[str, Any],
               bundle_ids: list[str]) -> str:
    """THE RUN IDENTITY RULE, stated once, here.

    A temporal arm run is identified by WHAT it bound (the Stage-1 v3 release), HOW it
    computed (the method), and WHAT came out (the content address of every bundle). Change
    any of the three and it is a different run — so a run id cannot be carried across a
    method change, and a forged one does not re-derive.
    """
    return content_hash({
        "run_id_rule_id": RUN_ID_RULE_ID,
        "release_binding": release_binding,
        "method": method,
        "bundles": sorted(bundle_ids),
    })[:RUN_ID_LEN]


def _one_stage1_binding(f: Failures, docs: list[dict[str, Any]]) -> None:
    """EVERY bundle stood on the SAME Stage-1 release. Divergence is fatal, not averaged."""
    if not docs:
        return
    by_hash: dict[str, list[str]] = {}
    for d in docs:
        by_hash.setdefault(content_hash(d["doc"].get("stage1_binding")),
                           []).append(d["dirname"])
    f.check("one_stage1_binding_underlies_every_bundle_in_the_release", len(by_hash) == 1,
            "release",
            "the bundles of one release stood on DIFFERENT Stage-1 identities: "
            + "; ".join(f"{h[:12]}={sorted(v)}" for h, v in sorted(by_hash.items()))
            + ". Admitting that on the strength of the first bundle admits the others unseen")


def _one_env_lock(f: Failures, docs: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """EVERY bundle was built in the SAME environment. Divergence is fatal, not averaged."""
    if not docs:
        return None
    by_hash: dict[str, list[str]] = {}
    for d in docs:
        by_hash.setdefault(content_hash(d["doc"].get("env_lock")), []).append(d["dirname"])
    f.check("one_environment_lock_underlies_every_bundle_in_the_release", len(by_hash) == 1,
            "release",
            "the bundles of one release were built in DIFFERENT environments: "
            + "; ".join(f"{h[:12]}={sorted(v)}" for h, v in sorted(by_hash.items())))
    return docs[0]["doc"].get("env_lock")


def _one_code_identity(f: Failures, docs: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """EVERY bundle must record the SAME build. Divergence is fatal, not averaged."""
    if not docs:
        return None
    by_hash: dict[str, list[str]] = {}
    for d in docs:
        ci = d["doc"].get("code_identity")
        by_hash.setdefault(content_hash(ci), []).append(d["dirname"])
    if not f.check("one_code_identity_produced_every_bundle_in_the_release",
                   len(by_hash) == 1, "release",
                   "the bundles of one release record DIFFERENT builds: "
                   + "; ".join(f"{h[:12]}={sorted(v)}" for h, v in sorted(by_hash.items()))
                   + ". A release whose bundles were built from different trees is not one "
                     "release, and admitting it on the strength of the first one is "
                     "admitting the others unseen"):
        return None
    return docs[0]["doc"].get("code_identity")


def _run_identity(f: Failures, bound,
                  docs: list[dict[str, Any]]) -> Optional[str]:
    """ONE method produced this release, and the run id is derived from what it produced."""
    if not docs:
        return None
    methods = {content_hash(d["doc"].get("method", {})) for d in docs}
    f.check("one_method_produced_every_bundle_in_the_release", len(methods) == 1,
            "release",
            "the bundles of one release were produced by different methods; a release "
            "whose halves were computed differently is not one release")
    if len(methods) != 1:
        return None
    return run_id_for(
        release_binding=bound.binding_block(), method=docs[0]["doc"]["method"],
        bundle_ids=[f"{d['doc']['bundle_key']}:{d['doc']['bundle_id']}" for d in docs])


def _release_level(f: Failures, bound, docs: list[dict[str, Any]]) -> None:
    """The whole-release facts, derived from the BUNDLES — never from an index.

    There is no release-index file: the producer RETURNS its index for a run manifest to
    serialise, and inventing one on disk would mean verifying an artifact nobody ships. Both
    of these are properties of the six bundles, and they are checked on the six bundles.
    """
    arm_keys = [k for d in docs for k in d["doc"].get("arm_keys", [])]
    f.check("each_arm_key_has_exactly_one_home_in_the_release",
            len(set(arm_keys)) == len(arm_keys), "release",
            "an arm key appears in more than one bundle; a reusable arm has exactly one "
            "home, and two would be two chances to disagree")
    f.check("the_release_carries_the_topology_its_stage1_release_implies",
            len(docs) == len(bound.ordered_pairs)
            and len(arm_keys) == bound.n_logical_arms, "release",
            f"{len(docs)} bundles / {len(arm_keys)} logical arms on disk; the bound release "
            f"implies {len(bound.ordered_pairs)} bundles and {bound.n_logical_arms} arms")


def _report(f: Failures, *, bound, bundles: list[dict[str, Any]],
            counts: dict[str, int], run_id: Optional[str]) -> dict[str, Any]:
    """The TYPED, CONTENT-ADDRESSED verifier report. It carries no machine and no timestamp.

    A report whose identity moved every time it was written could not be cited, and one
    that carried the path it was written at could not be republished.
    """
    n_programs = bound.n_admitted_programs if bound else 0
    n_pairs = len(bound.ordered_pairs) if bound else 0
    payload: dict[str, Any] = {
        "schema_version": schema.SCHEMA_REPORT,
        "verifier_id": VERIFIER_ID,
        "rules_id": rules.RULES_ID,
        "verdict": ADMIT if not f.items else REJECT,
        "n_failed": len(f.items),
        "failures": f.items,
        "producer_self_report_trusted": False,
        "gates_run": sorted(f.evaluated),
        "n_gates_run": len(f.evaluated),
        "estimand_level": rules.ESTIMAND_LEVEL,
        "inference_status": rules.INFERENCE_STATUS,
        "conditions": list(bound.conditions) if bound else [],
        "ordered_pairs": [list(p) for p in bound.ordered_pairs] if bound else [],
        "programs": sorted(bound.admitted_programs) if bound else [],
        "counts": {
            "n_conditions": len(bound.conditions) if bound else 0,
            "n_ordered_pairs": n_pairs,
            "n_programs": n_programs,
            "n_desired_changes": len(rules.DESIRED_CHANGES),
            "n_arms_per_bundle": n_programs * len(rules.DESIRED_CHANGES),
            "n_bundles": len(bundles),
            "n_logical_arms": sum(len(b["doc"].get("arm_keys", [])) for b in bundles),
        },
        "n_base_deltas_rederived": counts.get("base_deltas", 0),
        "n_arm_values_rederived": counts.get("arm_values", 0),
        "release_binding": bound.binding_block() if bound else {},
        "temporal_arm_run_id": run_id,
        "bundles": [{
            "bundle_key": b["doc"].get("bundle_key"),
            "bundle_id": b["doc"].get("bundle_id"),
            "from_condition": b["from_condition"],
            "to_condition": b["to_condition"],
            "raw_sha256": b["raw_sha256"],
            "canonical_sha256": b["canonical_sha256"],
            "n_arms": b["doc"].get("n_arms"),
            "producer_self_report": b["producer_self_report"],
        } for b in bundles],
    }
    payload["report_id"] = content_hash(
        {k: v for k, v in payload.items()})[:RUN_ID_LEN]
    return payload
