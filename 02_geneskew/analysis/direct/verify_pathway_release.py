"""The INDEPENDENT pathway RELEASE verifier — the aggregate envelope over the six bundles.

The per-bundle verifier (``verify_signature_matrix``) admits ONE (condition, source) pathway
bundle against the external primaries. A release is more than six admitted bundles: it is the
claim that they are the COMPLETE grid — the AUTHORITATIVE conditions x gene-set sources the
Stage-1 v3 release declares — computed against ONE Stage-1 release, ONE scorer view, ONE code
identity and ONE solver lock, each cell distinct, each cell INDEPENDENTLY admitted, over exactly
TWO pinned gene-set source artifacts. Nothing in a single bundle can see that.

Everything the release stands on is anchored OUTWARD, never derived from the bundles being
judged (that is the whole reseal-proofing story):

  * the condition + source UNIVERSE  -> the Stage-1 v3 release ``selector`` (``--release``);
  * the scorer view + method version -> the release's PUBLISHED pins, not merely a value the six
    bundles happen to SHARE (six bundles that agree on a WRONG scorer view must still refuse);
  * the solver lock                  -> the pinned ``2983d140…`` constant;
  * each cell's LOCAL validity        -> the SEPARATE independent per-bundle report, one to one,
    whose self-hash + verdict + EXACT gate inventory + re-derived run id + attested bytes this
    re-checks — NEVER the producer's own ``pathway_verification.json``;
  * the gene-set source              -> exactly two distinct ``gene_sets.source.json`` artifacts,
    one per source, each attested by its bundle's independent report;
  * the producer INVENTORY            -> required, PENDING, its native field allowlist enforced,
    its ``release_id`` MANDATORY and re-derived, byte-bound to what landed on disk.

LANE-SPECIFIC, NOT TEMPORAL. The envelope carries a pathway schema and a pathway verifier id; its
self-hash field (``report_id``) and ``binds`` block follow the integration adapter's rule so the
aggregate can consume it — but the schema string stays pathway-specific (the W1 coordination
item). The output is content-addressed and immutable.

GENERATOR != VERIFIER. It imports no producer module — only ``json``/``hashlib`` and the
verifier-side ``verify_rules``. It never edits producer bytes; it writes ONE new file.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from . import verify_rules as R  # noqa: E402

# LANE-SPECIFIC identities. Never the temporal ones.
ADMISSION_SCHEMA = "spot.stage02_pathway_arm_external_admission.v1"
VERIFIER_ID = "spot.stage02.pathway.arm.independent_verifier.v1"
ADMISSION_FILE = "pathway_arm_external_admission.json"
REPORT_ID_FIELD = "report_id"                     # the integration adapter's self-hash field

# The PENDING producer inventory this admits a lane against (pathway_release.py).
RELEASE_SCHEMA = "spot.stage02_pathway_arm_release.v1"
RELEASE_FILE = "pathway_arm_release.json"
# The EXACT native top-level field set of pathway_arm_release.json — allowlist, enforced.
NATIVE_INVENTORY_FIELDS = frozenset({
    "schema_version", "release_id_rule", "lane", "stage1_binding", "env_lock", "env_lock_sha256",
    "topology", "n_bundles", "n_logical_arms", "arm_keys", "bundles", "external_admission",
    "release_id"})

# The AUTHORITATIVE Stage-1 v3 release: the ONLY source of the condition + source universe, and
# the PUBLISHED scorer-view / method pins the six bundles are checked against.
STAGE1_RELEASE_SCHEMA = "spot.stage01_v3_release.v1"

# The INDEPENDENT per-bundle verifier whose reports prove each cell is locally valid, and the
# EXACT gate inventory each of its reports must carry (no missing / extra / duplicate / unknown).
BUNDLE_REPORT_SCHEMA = "spot.stage02_signature_matrix_verification.v1"
BUNDLE_VERIFIER_ID = "spot.stage02.signature_matrix.verifier.v1"
REQUIRED_BUNDLE_GATES = frozenset({
    "V1_raw_bytes_match_the_manifest_and_every_reference",
    "V1_signature_ref_binds_and_rederives_the_shared_manifest_identity",
    "V2_values_sha256_recomputes_from_the_reread_matrix_bytes",
    "V2_bits_sha256_recomputes_from_the_reread_mask_bytes",
    "V2_canonical_descriptors_recompute_from_the_reread_bytes",
    "V2_matrix_values_rederive_from_the_pinned_de_main",
    "V2_all_values_are_finite_or_declared",
    "V3_gene_axis_order_and_hash_rederive_from_de_main",
    "V4_amended_bitmap_counts_and_source_mask_identity_rederive_and_are_bound",
    "V5_all_zero_is_unresolved_and_the_resolved_all_ones_set_rederives_from_the_bitmap",
    "V6_convergence_rederives_with_the_sorted_gene_left_fold",
    "V7_member_target_ids_rederive_from_the_bound_gene_sets",
    "V8_no_pathway_bundle_ships_signature_bytes",
    "V9_no_forbidden_key_at_any_depth",
    "V10_every_reference_resolves_and_every_shared_artifact_is_referenced",
    "the_signature_ref_is_bound_into_a_rederivable_pathway_run_id",
    "the_source_mask_matches_the_external_independent_direct_mask_verification",
    "the_stage2_solver_lock_is_bound_into_the_run_identity",
    "the_per_target_signature_qc_rederives_from_the_shipped_qc_table",
    "the_signature_artifact_was_built_from_the_bound_de_source",
    "the_pathway_stage1_release_is_the_one_the_direct_arms_were_built_on"})

# The pinned Stage-2 solver lock — an EXTERNAL constant, never a value the bundle supplies.
STAGE2_SOLVER_LOCK_SHA256 = \
    "2983d140941f13d223dad93bae71434663882f23f25f6717c3debe59d2711abe"

RUN_ID_LEN = 16
BUNDLE_FILE = "arm_bundle.json"
PROVENANCE_FILE = "pathway_provenance.json"
GENE_SETS_FILE = "gene_sets.source.json"

ADMIT, REFUSE = "ADMIT", "REFUSE"                 # byte-exact tokens the aggregate maps
PASS, FAIL = "pass", "fail"

# THE NAMED GATE INVENTORY — the exact list the envelope carries.
G_RELEASE_ANCHOR = "the_condition_and_source_universe_comes_from_the_authoritative_stage1_release"
G_TOPOLOGY = "the_bundles_are_exactly_the_authoritative_condition_x_source_grid_once_each"
G_REOPEN = "every_bundle_reopens_and_its_nonnull_run_id_rederives_from_its_own_binding"
G_ONE_RELEASE = "one_scorer_view_and_stage1_that_match_the_release_pins_and_the_pinned_solver_lock"
G_DISTINCT = "every_cell_has_a_distinct_nonnull_run_id_and_distinct_nonnull_arm_record_bytes"
G_SOURCE = "each_bundle_agrees_with_itself_about_which_condition_x_source_cell_it_is"
G_GENE_SETS = "exactly_two_pinned_gene_set_source_artifacts_one_per_source_each_attested"
G_BUNDLE_ADMITTED = "every_cell_has_one_independent_admitting_report_with_the_exact_gate_inventory"
G_INVENTORY_PRESENT = "the_producer_inventory_is_present_pending_native_rederives_and_binds_this"
G_INVENTORY_BYTES = "the_producer_inventory_binds_the_exact_bytes_that_landed_on_disk"
GATE_INVENTORY = (G_RELEASE_ANCHOR, G_TOPOLOGY, G_REOPEN, G_ONE_RELEASE, G_DISTINCT, G_SOURCE,
                  G_GENE_SETS, G_BUNDLE_ADMITTED, G_INVENTORY_PRESENT, G_INVENTORY_BYTES)


def _check(name, ok, detail=""):
    return {"check": name, "status": PASS if ok else FAIL, "detail": detail}


def _json(path):
    with open(path) as fh:
        return json.load(fh)


def _raw(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _hashes(path):
    return {"raw_sha256": _raw(path), "canonical_sha256": R.content_sha256(_json(path))}


def _norm_source(s):
    """Case-fold a gene-set source id. The release names sources display-cased (``GO-BP``,
    ``Reactome``); the bundles and ids use lowercase (``go_bp``, ``reactome``)."""
    return None if s is None else str(s).strip().lower().replace("-", "_")


def _authoritative_universe(release_path):
    """(conditions, sources, pins, detail) from ``release.selector`` — or (None, None, {}, why).

    ``pins`` carries the release's PUBLISHED scorer-view canonical hash and method version, so a
    release computed against a different scorer view is caught even if all six bundles agree.
    """
    if not release_path or not os.path.exists(release_path):
        return None, None, {}, ("no authoritative Stage-1 v3 release (--release); the "
                                "condition/source universe and scorer pins may not be taken from "
                                "the bundles being judged")
    try:
        rel = _json(release_path)
    except Exception as exc:                            # noqa: BLE001
        return None, None, {}, f"the Stage-1 release is not readable JSON: {exc}"
    if rel.get("schema") != STAGE1_RELEASE_SCHEMA:
        return None, None, {}, (f"the release schema is {rel.get('schema')!r}, not "
                                f"{STAGE1_RELEASE_SCHEMA!r} — this is not the Stage-1 v3 release")
    selector = rel.get("selector") or {}
    conds = [str(c) for c in (selector.get("conditions") or [])]
    srcs = [_norm_source(s) for s in (selector.get("pathway_sources") or [])]
    if not conds or not srcs:
        return None, None, {}, ("the release selector declares no conditions and/or no "
                                "pathway_sources; the universe is not derivable")
    pins = {"scorer_view_canonical_sha256": rel.get("registry_scorer_view_canonical_sha256")
            or selector.get("registry_scorer_view_canonical_sha256"),
            "method_version": rel.get("method_version"),
            "release_raw_sha256": _raw(release_path),
            "self_release_sha256": rel.get("self_release_sha256")}
    return conds, srcs, pins, f"conditions={conds}; sources={srcs}"


def verify(*, bundle_dirs: list[str], inventory_path: Optional[str],
           release_path: Optional[str], bundle_report_paths: Optional[list[str]]) -> dict[str, Any]:
    """Re-open the bundles and re-derive the aggregate release contract, anchored outward."""
    checks: list[dict[str, Any]] = []

    auth_conds, auth_srcs, pins, anchor_detail = _authoritative_universe(release_path)
    checks.append(_check(G_RELEASE_ANCHOR, auth_conds is not None and auth_srcs is not None,
                         anchor_detail))
    auth_cond_set, auth_src_set = set(auth_conds or []), set(auth_srcs or [])

    bundles, reopen_bad = _reopen_bundles(bundle_dirs)
    checks.append(_check(G_REOPEN, bool(bundles) and not reopen_bad, "; ".join(reopen_bad[:4])))

    checks.append(_topology(bundles, auth_cond_set, auth_src_set))
    checks.append(_one_release(bundles, pins))
    checks.append(_distinct(bundles))
    checks.append(_source(bundles, auth_src_set))
    gene_check, gene_artifacts = _gene_sets(bundles, auth_src_set, bundle_report_paths)
    checks.append(gene_check)
    checks.append(_verify_bundle_reports(bundle_report_paths, bundles))
    inv_present, inv_bytes, inv_release_id, inv_raw = _verify_inventory(
        inventory_path, bundles, auth_cond_set, auth_src_set)
    checks.append(inv_present)
    checks.append(inv_bytes)

    failures = [c for c in checks if c["status"] != PASS]
    verdict = ADMIT if not failures else REFUSE
    run_ids = [b["run_id"] for b in bundles]
    body = {
        "schema_version": ADMISSION_SCHEMA,
        "verifier_id": VERIFIER_ID,
        "lane": "pathway",
        "generator_is_not_verifier": True,
        "fail_closed": True,
        "authoritative_universe": {"conditions": auth_conds, "sources": auth_srcs,
                                   "scorer_view_canonical_sha256":
                                       pins.get("scorer_view_canonical_sha256"),
                                   "method_version": pins.get("method_version")},
        "n_bundles": len(bundles),
        "cells": sorted([[b["condition"], b["source"]] for b in bundles]),
        "bundle_run_ids": sorted(x for x in run_ids if x),
        "gene_set_source_artifacts": gene_artifacts,
        "binds": {"producer_release_id": inv_release_id,
                  "producer_release_raw_sha256": inv_raw,
                  "inventory_raw_sha256": inv_raw,
                  "stage1_release_raw_sha256": pins.get("release_raw_sha256")},
        "gate_inventory": list(GATE_INVENTORY),
        "gates": [{"check": c["check"], "status": c["status"]} for c in checks],
        "n_failed": len(failures),
        "verdict": verdict,
    }
    body[REPORT_ID_FIELD] = R.content_sha256(body)
    return {"body": body, "checks": checks, "verdict": verdict}


def _reopen_bundles(bundle_dirs):
    bundles, bad = [], []
    for d in bundle_dirs:
        pp, bp = os.path.join(d, PROVENANCE_FILE), os.path.join(d, BUNDLE_FILE)
        if not (os.path.exists(pp) and os.path.exists(bp)):
            bad.append(f"{d}: missing {PROVENANCE_FILE} or {BUNDLE_FILE}")
            continue
        prov, doc = _json(pp), _json(bp)
        binding = prov.get("run_binding") or {}
        rederived = R.content_sha256(binding) if binding else None
        run_id = prov.get("pathway_run_id")
        if not run_id or rederived is None or rederived != prov.get("pathway_run_sha256") \
                or rederived[:RUN_ID_LEN] != run_id:
            bad.append(f"{d}: pathway_run_id is null or does not re-derive from run_binding")
        gs = os.path.join(d, GENE_SETS_FILE)
        bundles.append({
            "dir": d,
            "condition": binding.get("condition") or doc.get("condition"),
            "source": _norm_source(binding.get("source") or doc.get("source")),
            "binding_condition": binding.get("condition"),
            "binding_source": _norm_source(binding.get("source")),
            "doc_condition": doc.get("condition"), "doc_source": _norm_source(doc.get("source")),
            "run_id": run_id,
            "scorer_view_sha256": binding.get("scorer_view_sha256"),
            "release_scorer_view_canonical_sha256":
                binding.get("release_scorer_view_canonical_sha256"),
            "code_identity": binding.get("code_identity"),
            "stage1_release_hashes": binding.get("stage1_release_hashes"),
            "stage1_method_version": (binding.get("stage1_release_hashes") or {})
            .get("method_version"),
            "env_lock_sha256": (binding.get("environment_lock") or {}).get("sha256"),
            "records_sha256": binding.get("records_sha256"),
            "gene_sets_raw_sha256": _raw(gs) if os.path.exists(gs) else None,
            "arm_bundle_hashes": _hashes(bp), "provenance_hashes": _hashes(pp),
        })
    return bundles, bad


def _topology(bundles, auth_cond_set, auth_src_set):
    got: dict[Any, int] = {}
    for c in [(b["condition"], b["source"]) for b in bundles]:
        got[c] = got.get(c, 0) + 1
    expected = {(c, s) for c in auth_cond_set for s in auth_src_set}
    dups = [c for c, n in got.items() if n > 1]
    unknown = sorted(k for k in got if k not in expected)
    missing = sorted(expected - set(got))
    ok = bool(expected) and len(bundles) == len(expected) and not dups \
        and not unknown and not missing
    return _check(G_TOPOLOGY, ok,
                  f"{len(bundles)} bundles vs authoritative grid of {len(expected)}; "
                  f"duplicated {dups[:2]}; not-in-release {unknown[:2]}; missing {missing[:2]}")


def _one_release(bundles, pins):
    bad = []
    for key, label in (("scorer_view_sha256", "scorer view"),
                       ("release_scorer_view_canonical_sha256", "release scorer view"),
                       ("code_identity", "code identity"),
                       ("stage1_release_hashes", "Stage-1 release"),
                       ("env_lock_sha256", "solver lock")):
        vals = [b.get(key) for b in bundles]
        if any(v is None for v in vals):
            bad.append(f"a bundle binds a NULL {label}")
        elif len({json.dumps(v, sort_keys=True) for v in vals}) > 1:
            bad.append(f"the release does not share ONE {label}")
    # NOT only agreement with each other: agreement with the AUTHORITATIVE release pins.
    pin_view = pins.get("scorer_view_canonical_sha256")
    views = {b.get("release_scorer_view_canonical_sha256") for b in bundles}
    if bundles and pin_view and views != {pin_view}:
        bad.append("the release scorer view is not the one the Stage-1 release publishes")
    pin_method = pins.get("method_version")
    methods = {b.get("stage1_method_version") for b in bundles}
    if bundles and pin_method and methods != {pin_method}:
        bad.append("the Stage-1 method version is not the one the release publishes")
    locks = {b.get("env_lock_sha256") for b in bundles}
    if bundles and locks != {STAGE2_SOLVER_LOCK_SHA256}:
        bad.append("the bound solver lock is not the pinned 2983d140… constant")
    return _check(G_ONE_RELEASE, bool(bundles) and not bad, "; ".join(bad[:3]))


def _distinct(bundles):
    run_ids = [b["run_id"] for b in bundles]
    recs = [b["records_sha256"] for b in bundles]
    ok = (bool(bundles)
          and all(x is not None for x in run_ids) and len(set(run_ids)) == len(run_ids)
          and all(x is not None for x in recs) and len(set(recs)) == len(recs))
    return _check(G_DISTINCT, ok,
                  "a cell has a null or shared run id / arm record bytes — six identical bundles "
                  "are one bundle counted six times")


def _source(bundles, auth_src_set):
    bad = []
    for b in bundles:
        if b["source"] is None or (auth_src_set and b["source"] not in auth_src_set):
            bad.append(f"{b['dir']}: source {b['source']!r} is null or not in the release")
        for field, dv, bv in (("source", b["doc_source"], b["binding_source"]),
                              ("condition", b["doc_condition"], b["binding_condition"])):
            if dv is not None and bv is not None and dv != bv:
                bad.append(f"{b['dir']}: arm_bundle {field} {dv!r} != run_binding {bv!r}")
    return _check(G_SOURCE, bool(bundles) and not bad, "; ".join(bad[:3]))


def _gene_sets(bundles, auth_src_set, report_paths):
    """Exactly two pinned gene-set source artifacts, one per source, each attested by its report.

    The only per-source content hash exists PER BUNDLE (``gene_sets.source.json``): there is no
    upstream pin. So the release binds the two distinct artifacts itself — one shared across each
    source's bundles — and requires the independent per-bundle report to have ATTESTED the same
    bytes (so a swapped gene-set file that never went through the per-bundle verifier is caught).
    """
    bad = []
    by_source: dict[Any, set] = {}
    for b in bundles:
        if b["gene_sets_raw_sha256"] is None:
            bad.append(f"{b['dir']}: no {GENE_SETS_FILE}")
            continue
        by_source.setdefault(b["source"], set()).add(b["gene_sets_raw_sha256"])
    for src, hashes in by_source.items():
        if len(hashes) > 1:
            bad.append(f"source {src!r} bundles do not share ONE gene-set artifact")
    artifacts = {str(src): sorted(h)[0] for src, h in by_source.items() if h}
    distinct = {h for hs in by_source.values() for h in hs}
    if auth_src_set and len(artifacts) != len(auth_src_set):
        bad.append(f"expected {len(auth_src_set)} gene-set sources, found {len(artifacts)}")
    if len(distinct) != len(artifacts):
        bad.append("two different sources share the same gene-set artifact")
    # cross-check attestation: the per-bundle report must have READ these exact gene-set bytes.
    attested = _attested_gene_sets(report_paths)
    for b in bundles:
        want = b["gene_sets_raw_sha256"]
        got = attested.get(b["run_id"])
        if want is not None and got is not None and got != want:
            bad.append(f"{b['dir']}: the independent report attested a different gene-set file")
    ok = bool(bundles) and not bad
    return _check(G_GENE_SETS, ok, "; ".join(bad[:3])), artifacts


def _attested_gene_sets(report_paths):
    """run_id -> the gene_sets.source.json raw hash the per-bundle report says it read."""
    out = {}
    for p in (report_paths or []):
        if not os.path.exists(p):
            continue
        try:
            rep = _json(p)
        except Exception:                               # noqa: BLE001
            continue
        for rid, att in (rep.get("bound_artifacts") or {}).items():
            if isinstance(att, dict) and att.get(GENE_SETS_FILE):
                out[rid] = att[GENE_SETS_FILE]
    return out


def _verify_bundle_reports(report_paths, bundles):
    """Exactly one INDEPENDENT admitting report per cell, one to one, with the EXACT gate set.

    NEVER the producer's ``pathway_verification.json``. Each report: self-hash recomputes, verdict
    admit, its gate inventory is EXACTLY ``REQUIRED_BUNDLE_GATES`` (no missing / extra / duplicate
    / unknown, not merely a nonempty all-pass list), it names exactly ONE run id that is one of
    the bundles', and its attested provenance bytes are the ones on disk. Six bundles => six
    reports, each binding a distinct bundle.
    """
    want_ids = {b["run_id"] for b in bundles if b["run_id"]}
    prov_by_id = {b["run_id"]: b["provenance_hashes"]["raw_sha256"] for b in bundles if b["run_id"]}
    if not report_paths:
        return _check(G_BUNDLE_ADMITTED, False,
                      "no independent per-bundle verification reports were supplied "
                      "(--bundle-report)")
    bad = []
    covered: dict[str, int] = {}
    for p in report_paths:
        rid, problem = _one_report(p, want_ids, prov_by_id)
        if problem:
            bad.append(f"{p}: {problem}")
        elif rid:
            covered[rid] = covered.get(rid, 0) + 1
    dup = [r for r, n in covered.items() if n > 1]
    missing = sorted(want_ids - set(covered))
    if dup:
        bad.append(f"more than one report for cells {dup[:2]}")
    if missing:
        bad.append(f"cells with no admitting report: {missing[:3]}")
    ok = bool(want_ids) and not bad and len(covered) == len(want_ids)
    return _check(G_BUNDLE_ADMITTED, ok, "; ".join(bad[:4]))


def _one_report(p, want_ids, prov_by_id):
    """Validate ONE independent per-bundle report -> (run_id, problem). Exactly one of them set."""
    if not os.path.exists(p):
        return None, "missing report"
    try:
        rep = _json(p)
    except Exception as exc:                            # noqa: BLE001
        return None, f"unreadable ({exc})"
    if rep.get("schema_version") != BUNDLE_REPORT_SCHEMA \
            or rep.get("verifier_id") != BUNDLE_VERIFIER_ID:
        return None, "not an independent signature-matrix report"
    body = {k: v for k, v in rep.items() if k != "report_sha256"}
    recomputed = hashlib.sha256(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if recomputed != rep.get("report_sha256"):
        return None, "report self-hash does not recompute"
    names = [g.get("check") for g in (rep.get("gates") or [])]
    if len(names) != len(set(names)):
        return None, "the report has duplicate gates"
    if set(names) != REQUIRED_BUNDLE_GATES:
        miss = sorted(REQUIRED_BUNDLE_GATES - set(names))
        extra = sorted(set(names) - REQUIRED_BUNDLE_GATES)
        return None, f"gate inventory mismatch (missing {miss[:2]}, unknown {extra[:2]})"
    if rep.get("verdict") != "admit" or rep.get("n_failed") not in (0, "0") \
            or any(g.get("status") != PASS for g in rep.get("gates") or []):
        return None, "not a clean ADMIT"
    rids = rep.get("run_ids") or []
    if len(rids) != 1:
        return None, f"a release report must bind exactly one cell, names {len(rids)}"
    rid = rids[0]
    if rid not in want_ids:
        return None, "names a run id not in this release"
    att = (rep.get("bound_artifacts") or {}).get(rid) or {}
    if att.get(PROVENANCE_FILE) != prov_by_id.get(rid):
        return None, "attested provenance bytes are not the ones on disk"
    return rid, None


def _entry_cell(e):
    ctx = e.get("context") if isinstance(e.get("context"), dict) else {}
    cond = e.get("condition") or ctx.get("condition")
    src = e.get("source") or ctx.get("gene_set_source") or ctx.get("source")
    return (str(cond) if cond is not None else None, _norm_source(src))


def _verify_inventory(inventory_path, bundles, auth_cond_set, auth_src_set):
    """Require the PENDING producer inventory in its native shape, re-derive its MANDATORY
    release_id, and bind the exact bytes it names."""
    none = (None, None)
    if not inventory_path or not os.path.exists(inventory_path):
        return (_check(G_INVENTORY_PRESENT, False, "no pathway_arm_release.json was supplied"),
                _check(G_INVENTORY_BYTES, False, "no inventory to bind"), *none)
    try:
        with open(inventory_path, "rb") as fh:
            raw = fh.read()
        inv = json.loads(raw)
        inv_raw_sha = hashlib.sha256(raw).hexdigest()
    except Exception as exc:                            # noqa: BLE001
        return (_check(G_INVENTORY_PRESENT, False, f"unreadable inventory: {exc}"),
                _check(G_INVENTORY_BYTES, False, "the inventory did not load"), *none)

    present = []
    keys = set(inv.keys())
    missing_fields = sorted(NATIVE_INVENTORY_FIELDS - keys)
    extra_fields = sorted(keys - NATIVE_INVENTORY_FIELDS)
    if missing_fields:
        present.append(f"the inventory omits native fields {missing_fields[:3]}")
    if extra_fields:
        present.append(f"the inventory carries non-native fields {extra_fields[:3]}")
    if inv.get("schema_version") != RELEASE_SCHEMA:
        present.append(f"inventory schema is {inv.get('schema_version')!r}, not {RELEASE_SCHEMA!r}")
    ea = inv.get("external_admission") or {}
    if ea.get("status") != "pending":
        present.append("the producer inventory is not PENDING")
    req = ea.get("required_verifier_id") or inv.get("required_verifier_id")
    if req not in (None, VERIFIER_ID):
        present.append("the inventory requires a different verifier")
    if not ea.get("required_report_schema_version"):
        present.append("the inventory names no required_report_schema_version")
    if inv.get("env_lock_sha256") not in (None, STAGE2_SOLVER_LOCK_SHA256):
        present.append("the inventory env_lock_sha256 is not the pinned solver lock")
    # topology must agree with the authoritative universe, not merely exist.
    topo = inv.get("topology") or {}
    if auth_cond_set and set(str(c) for c in (topo.get("conditions") or [])) != auth_cond_set:
        present.append("the inventory topology conditions are not the release's")
    if auth_src_set and {_norm_source(s) for s in (topo.get("sources") or [])} != auth_src_set:
        present.append("the inventory topology sources are not the release's")
    # release_id is MANDATORY, non-null, and must re-derive from the inventory bytes.
    release_id = inv.get("release_id")
    if release_id is None:
        present.append("the inventory carries no release_id — a release must name its identity")
    elif release_id != R.content_sha256({k: v for k, v in inv.items() if k != "release_id"}):
        present.append("the inventory release_id does not re-derive from its own bytes")
    present_ok = not present

    byte_bad = []
    inv_entries = inv.get("bundles") or []
    inv_by_cell = {_entry_cell(e): e for e in inv_entries}
    disk_by_cell = {(b["condition"], b["source"]): b for b in bundles}
    if set(inv_by_cell) != set(disk_by_cell):
        byte_bad.append("the inventory names a different set of cells than landed on disk")
    for cell, b in disk_by_cell.items():
        e = inv_by_cell.get(cell)
        if e is None:
            continue
        for field in ("bundle_id", "relative_dir", "files"):
            if field not in e:
                byte_bad.append(f"{cell}: the inventory entry omits {field}")
        files = e.get("files") or {}
        for name, want in ((BUNDLE_FILE, b["arm_bundle_hashes"]),
                           (PROVENANCE_FILE, b["provenance_hashes"])):
            f = files.get(name) or {}
            if f.get("raw_sha256") != want["raw_sha256"] or \
                    f.get("canonical_sha256") != want["canonical_sha256"]:
                byte_bad.append(f"{cell}: inventory {name} bytes are not the ones on disk")
        bid = e.get("bundle_id")
        if bid is not None and b["run_id"] is not None and str(bid) != str(b["run_id"]):
            byte_bad.append(f"{cell}: inventory names a different bundle id")
    return (_check(G_INVENTORY_PRESENT, present_ok, "; ".join(present[:3])),
            _check(G_INVENTORY_BYTES, present_ok and not byte_bad, "; ".join(byte_bad[:4])),
            release_id, inv_raw_sha)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="python -m direct.verify_pathway_release",
        description="Independent Stage-2 pathway RELEASE verifier: re-opens the pathway bundles, "
                    "anchors the condition x source universe AND the scorer/method pins to the "
                    "authoritative Stage-1 v3 release, requires one independent admitting "
                    "per-bundle report per cell (exact gate inventory, attested bytes), binds "
                    "exactly two gene-set source artifacts, re-derives the aggregate contract and "
                    "the PENDING producer inventory (native fields, mandatory release_id), and "
                    "emits a lane-specific content-addressed pathway_arm_external_admission. "
                    "Imports no producer module. Exit 0 = ADMIT, nonzero = REFUSE.")
    ap.add_argument("--bundle", required=True, action="append", dest="bundles", metavar="DIR",
                    help="a pathway bundle dir (repeatable; the condition x source cells)")
    ap.add_argument("--release", default=None,
                    help="the AUTHORITATIVE Stage-1 v3 release json (universe + scorer pins)")
    ap.add_argument("--bundle-report", action="append", dest="bundle_reports", default=None,
                    metavar="PATH", help="an INDEPENDENT per-bundle verification report "
                    "(repeatable; exactly one admitting report per cell)")
    ap.add_argument("--inventory", default=None,
                    help="the PENDING producer root inventory pathway_arm_release.json")
    ap.add_argument("--out", required=True,
                    help=f"path to write {ADMISSION_FILE} (content-addressed, ADMIT/REFUSE)")
    args = ap.parse_args(argv)

    try:
        result = verify(bundle_dirs=list(args.bundles), inventory_path=args.inventory,
                        release_path=args.release,
                        bundle_report_paths=list(args.bundle_reports or []))
        body = result["body"]
    except Exception as exc:                            # a crash IS a refusal
        body = {"schema_version": ADMISSION_SCHEMA, "verifier_id": VERIFIER_ID,
                "lane": "pathway", "verdict": REFUSE, "n_failed": 1,
                "gates": [{"check": "verifier_completed_without_error", "status": FAIL}],
                "detail": f"{type(exc).__name__}: {exc}"}
        body[REPORT_ID_FIELD] = R.content_sha256(body)
        result = {"checks": [], "verdict": REFUSE}

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w") as fh:
        json.dump(body, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(json.dumps({"verdict": body["verdict"], "n_failed": body.get("n_failed"),
                      "out": args.out, REPORT_ID_FIELD: body[REPORT_ID_FIELD]}, indent=2))
    if body["verdict"] != ADMIT:
        for c in result.get("checks", []):
            if c["status"] != PASS:
                print(f"  REFUSE [{c['check']}] {c.get('detail', '')}", file=sys.stderr)
    return 0 if body["verdict"] == ADMIT else 1


if __name__ == "__main__":
    sys.exit(main())
