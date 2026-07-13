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

# The PENDING producer inventory this admits a lane against. The AUTHORITATIVE producer is
# analysis/direct/release_inventory.py (invoked by run_release.py `python -m
# direct.release_inventory --lane pathway`), NOT the stale pathway_release.py — the two emit the
# same schema_version with divergent shapes (see the W1 handoff note). This binds the real one.
RELEASE_SCHEMA = "spot.stage02_pathway_arm_release.v1"
RELEASE_FILE = "pathway_arm_release.json"
VERDICT_PENDING = "pending_independent_verification"
# The EXACT native top-level field set release_inventory.build emits for the pathway lane —
# allowlist, enforced (there is NO env_lock/topology; the lane binding is solver_lock_sha256 +
# stage1_binding, and the un-admitted producer ships verdict/admitted/self_admitted/verifier_id).
NATIVE_INVENTORY_FIELDS = frozenset({
    "schema_version", "lane", "release_id_rule", "n_bundles", "n_logical_arms", "arm_keys",
    "bundles", "stage1_binding", "solver_lock_sha256", "producer_commit",
    "independent_verifier_commit", "external_admission", "verdict", "admitted", "self_admitted",
    "verifier_id", "release_id"})
# The bundle files the inventory names that this binds byte-for-byte (present ones).
BOUND_BUNDLE_FILES = ("arm_bundle.json", "pathway_provenance.json", "gene_sets.source.json",
                      "signature_ref.json", "convergence.json")

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
    "V6b_convergence_size_domain_rederives_from_bound_gene_sets_and_signatures",
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

# The inferential firewall: a pathway arm is a rank position, never a test statistic. These
# substrings (normalized) are forbidden at ANY depth of ANY shipped document — a resealed
# forgery that self-consistently carries a q-value is still refused.
FORBIDDEN_INFERENTIAL = ("p_value", "q_value", "empirical_q", "empirical_p", "pvalue", "qvalue",
                         "p_adj", "q_adj", "padj", "adjusted_p", "fdr", "false_discovery")

# The CANONICAL values of every universe descriptor the gene-set binding must carry (genesets.py
# UNIVERSE_ROLE / ENSEMBL_GENE_ID / TARGET_ID_NAMESPACE). A wrong-but-truthy role — e.g.
# "analysis_universe" — is a different claim about what the universe IS; only the exact string is
# the readout-signature space, so these are matched by value, never by truthiness.
CANONICAL_UNIVERSE_DESCRIPTORS = {
    "effect_universe_role": "de_readout_signature_vector_space_and_effect_matrix_columns",
    "target_universe_role": "perturbation_target_ranked_population_gene_set_membership",
    "gene_id_namespace": "ensembl_gene_id",
    "gene_id_namespace_effect": "ensembl_gene_id",
    "target_id_namespace": "mixed_ensembl_gene_id_and_released_gene_symbol",
}

# THE NAMED GATE INVENTORY — the exact list the envelope carries.
G_RELEASE_ANCHOR = "the_condition_and_source_universe_comes_from_the_authoritative_stage1_release"
G_TOPOLOGY = "the_bundles_are_exactly_the_authoritative_condition_x_source_grid_once_each"
G_REOPEN = "every_bundle_reopens_and_its_nonnull_run_id_rederives_from_its_own_binding"
G_ONE_RELEASE = "one_scorer_view_and_stage1_that_match_the_release_pins_and_the_pinned_solver_lock"
G_DISTINCT = "every_cell_has_a_distinct_nonnull_run_id_and_distinct_nonnull_arm_record_bytes"
G_SOURCE = "each_bundle_agrees_with_itself_about_which_condition_x_source_cell_it_is"
G_GENE_SETS = "method_gene_sets_binds_two_pinned_sources_agrees_with_provenance_one_universe"
G_UNIVERSE = "the_gene_set_universes_match_the_authoritative_native_run_binding_universe_fields"
G_FIREWALL = "no_p_q_fdr_inferential_key_at_any_depth_of_any_shipped_document"
G_BUNDLE_ADMITTED = "every_cell_has_one_independent_admitting_report_with_the_exact_gate_inventory"
G_INVENTORY_PRESENT = "the_producer_inventory_is_present_pending_native_rederives_and_binds_this"
G_INVENTORY_BYTES = "the_producer_inventory_binds_the_exact_bytes_that_landed_on_disk"
GATE_INVENTORY = (G_RELEASE_ANCHOR, G_TOPOLOGY, G_REOPEN, G_ONE_RELEASE, G_DISTINCT, G_SOURCE,
                  G_GENE_SETS, G_UNIVERSE, G_FIREWALL, G_BUNDLE_ADMITTED, G_INVENTORY_PRESENT,
                  G_INVENTORY_BYTES)


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
    checks.append(_universe(bundles))
    checks.append(_firewall(bundles, bundle_report_paths))
    checks.append(_verify_bundle_reports(bundle_report_paths, bundles))
    inv_present, inv_bytes, inv_release_id, inv_raw = _verify_inventory(
        inventory_path, bundles, auth_cond_set, pins)
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
            # the NATIVE gene-set binding is at arm_bundle.method.gene_sets, with the copy the
            # run id is taken over at run_binding.method.gene_sets — NEVER a top-level gene_sets.
            "method_gene_sets": ((doc.get("method") or {}).get("gene_sets")),
            "prov_gene_sets": ((binding.get("method") or {}).get("gene_sets")),
            "top_level_gene_sets": "gene_sets" in doc,
            # the AUTHORITATIVE universe identities the science computed against, bound into the
            # run id at the top of run_binding — the gene-set block must match THESE.
            "rb_effect_universe_sha256": binding.get("gene_universe_sha256"),
            "rb_target_universe_sha256": binding.get("target_universe_sha256"),
            "rb_n_effect_universe_genes": binding.get("n_effect_universe_genes"),
            "rb_n_target_universe_genes": binding.get("n_target_universe_genes"),
            "arm_bundle_hashes": _hashes(bp), "provenance_hashes": _hashes(pp),
            "file_hashes": {name: _hashes(os.path.join(d, name)) for name in BOUND_BUNDLE_FILES
                            if os.path.exists(os.path.join(d, name))},
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
    """The NATIVE gene-set binding, at arm_bundle.method.gene_sets — identity, provenance
    agreement, pinned bytes, universes — and exactly two artifacts, one per source.

    ``run_pathway_arms`` writes the binding under ``arm_bundle.method.gene_sets`` and takes the
    pathway run id over a copy at ``run_binding.method.gene_sets``. This reads ONLY that native
    location (a top-level ``gene_sets`` is a non-native crutch and is refused), requires the two
    copies to AGREE exactly, checks the gene-set identity field by field, binds the pinned
    ``gene_set_release.sha256`` to the gene_sets.source.json bytes on disk (and to the per-bundle
    report's attestation), and holds the release to ONE effect + ONE target universe.
    """
    bad = []
    by_source: dict[Any, set] = {}
    effect_universes, target_universes = set(), set()
    attested = _attested_gene_sets(report_paths)
    for b in bundles:
        mgs, prov_mgs = b["method_gene_sets"], b["prov_gene_sets"]
        if b["top_level_gene_sets"] and not isinstance(mgs, dict):
            bad.append(f"{b['dir']}: a top-level gene_sets is not the native binding "
                       "(it lives at method.gene_sets)")
        if not isinstance(mgs, dict):
            bad.append(f"{b['dir']}: arm_bundle carries no method.gene_sets")
            continue
        if not isinstance(prov_mgs, dict) or mgs != prov_mgs:
            bad.append(f"{b['dir']}: method.gene_sets disagrees with the provenance copy "
                       "(run_binding.method.gene_sets)")
        rel = mgs.get("gene_set_release") or {}
        if _norm_source(rel.get("source")) != b["source"]:
            bad.append(f"{b['dir']}: gene_set_release.source {rel.get('source')!r} is not the "
                       f"cell's source {b['source']!r}")
        if mgs.get("status") != "bound":
            bad.append(f"{b['dir']}: gene-set binding status is {mgs.get('status')!r}, not bound")
        # the pinned bytes: gene_set_release.sha256 IS the gene_sets.source.json on disk.
        pinned_sha = rel.get("sha256")
        if pinned_sha != b["gene_sets_raw_sha256"]:
            bad.append(f"{b['dir']}: gene_set_release.sha256 is not the gene_sets.source.json "
                       "bytes on disk")
        got = attested.get(b["run_id"])
        if got is not None and pinned_sha is not None and got != pinned_sha:
            bad.append(f"{b['dir']}: the independent report attested a different gene-set file")
        # BOTH universe hashes must be present (their exact identity — value, role, namespace,
        # count — is bound against the authoritative run_binding fields in G_UNIVERSE).
        for u in ("effect_universe_sha256", "target_universe_sha256"):
            if not mgs.get(u):
                bad.append(f"{b['dir']}: the gene-set binding declares no {u}")
        effect_universes.add(mgs.get("effect_universe_sha256"))
        target_universes.add(mgs.get("target_universe_sha256"))
        by_source.setdefault(b["source"], set()).add(pinned_sha)
    for src, hashes in by_source.items():
        if len(hashes) > 1:
            bad.append(f"source {src!r} bundles do not share ONE gene-set artifact")
    artifacts = {str(src): sorted(h)[0] for src, h in by_source.items() if h and None not in h}
    if auth_src_set and len(artifacts) != len(auth_src_set):
        bad.append(f"expected {len(auth_src_set)} gene-set sources, found {len(artifacts)}")
    if len({h for hs in by_source.values() for h in hs}) != len(by_source):
        bad.append("two different sources share the same gene-set artifact")
    if bundles and len(effect_universes) > 1:
        bad.append("the release is not built against ONE effect (readout) universe")
    if bundles and len(target_universes) > 1:
        bad.append("the release is not built against ONE target (perturbation) universe")
    return _check(G_GENE_SETS, bool(bundles) and not bad, "; ".join(bad[:4])), artifacts


def _universe(bundles):
    """The gene-set block's universes MUST equal the authoritative native run_binding universe
    fields — hash, count — for BOTH the effect (readout) and target (perturbation) universe, and
    the roles/namespaces must be declared. A fake effect+target universe resealed self-consistently
    into method.gene_sets across all six still disagrees with run_binding.{gene,target}_universe.
    """
    bad = []
    eff_auth, tgt_auth = set(), set()
    for b in bundles:
        mgs = b["method_gene_sets"]
        if not isinstance(mgs, dict):
            bad.append(f"{b['dir']}: no method.gene_sets to bind universes from")
            continue
        pairs = (("effect_universe_sha256", "rb_effect_universe_sha256", "effect hash"),
                 ("target_universe_sha256", "rb_target_universe_sha256", "target hash"),
                 ("n_effect_universe_genes", "rb_n_effect_universe_genes", "effect count"),
                 ("n_target_universe_genes", "rb_n_target_universe_genes", "target count"))
        for mkey, bkey, label in pairs:
            if b[bkey] is None:
                bad.append(f"{b['dir']}: run_binding declares no authoritative {label}")
            elif mgs.get(mkey) != b[bkey]:
                bad.append(f"{b['dir']}: method.gene_sets {label} {mgs.get(mkey)!r} != the "
                           f"authoritative run_binding {b[bkey]!r}")
        # EXACT canonical values, not mere presence: a wrong-but-truthy role/namespace is a
        # different claim about what the universe IS, and must refuse.
        for desc, want in CANONICAL_UNIVERSE_DESCRIPTORS.items():
            if mgs.get(desc) != want:
                bad.append(f"{b['dir']}: gene-set {desc} is {str(mgs.get(desc))[:32]!r}, not the "
                           f"canonical {want!r}")
        eff_auth.add(b["rb_effect_universe_sha256"])
        tgt_auth.add(b["rb_target_universe_sha256"])
    if bundles and len(eff_auth) > 1:
        bad.append("the release binds more than one authoritative effect universe")
    if bundles and len(tgt_auth) > 1:
        bad.append("the release binds more than one authoritative target universe")
    return _check(G_UNIVERSE, bool(bundles) and not bad, "; ".join(bad[:4]))


def _forbidden_hits(obj, path):
    """Every key at any depth whose normalized name carries a p/q/FDR alias."""
    hits = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            norm = str(k).lower().replace("-", "_").replace(" ", "_")
            if any(tok in norm for tok in FORBIDDEN_INFERENTIAL):
                hits.append(f"{path}.{k}")
            hits += _forbidden_hits(v, f"{path}.{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            hits += _forbidden_hits(v, f"{path}[{i}]")
    return hits


def _firewall(bundles, report_paths):
    """No inferential key at any depth of the shipped arm bundle, run binding / provenance, or
    the independent reports — resealed or not. The pathway lane ships rank evidence, not tests."""
    hits = []
    for b in bundles:
        for name in (BUNDLE_FILE, PROVENANCE_FILE):
            p = os.path.join(b["dir"], name)
            if os.path.exists(p):
                try:
                    hits += _forbidden_hits(_json(p), f"{os.path.basename(b['dir'])}/{name}")
                except Exception:                       # noqa: BLE001, S112
                    continue
    for p in (report_paths or []):
        if os.path.exists(p):
            try:
                hits += _forbidden_hits(_json(p), os.path.basename(p))
            except Exception:                           # noqa: BLE001, S112
                continue
    return _check(G_FIREWALL, not hits, "; ".join(sorted(set(hits))[:5]))


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
    if not att.get(GENE_SETS_FILE):
        return None, "the report does not attest gene_sets.source.json (mandatory)"
    return rid, None


def _entry_cell(e):
    ctx = e.get("context") if isinstance(e.get("context"), dict) else {}
    cond = e.get("condition") or ctx.get("condition")
    src = e.get("source") or ctx.get("gene_set_source") or ctx.get("source")
    return (str(cond) if cond is not None else None, _norm_source(src))


def _verify_inventory(inventory_path, bundles, auth_cond_set, pins):
    """Require the PENDING producer inventory in its REAL native shape (release_inventory.py),
    re-derive its MANDATORY release_id, and bind the exact bytes it names.

    The native pathway inventory ships UN-ADMITTED: verdict pending, admitted/self_admitted
    false, verifier_id null. It binds the lane with solver_lock_sha256 + stage1_binding, NOT an
    env_lock/topology block. Its release_id is content_hash(doc excluding release_id).
    """
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
    if inv.get("lane") != "pathway":
        present.append(f"inventory lane is {inv.get('lane')!r}, not 'pathway'")
    # THE PRODUCER DOES NOT ADMIT ITS OWN RELEASE — it must ship un-admitted.
    if (inv.get("external_admission") or {}).get("status") != "pending":
        present.append("external_admission.status is not pending")
    if inv.get("verdict") != VERDICT_PENDING:
        present.append(f"verdict is {inv.get('verdict')!r}, not {VERDICT_PENDING!r}")
    if inv.get("admitted") is not False or inv.get("self_admitted") is not False \
            or inv.get("verifier_id") is not None:
        present.append("the producer inventory is already admitted — it must ship un-admitted")
    if inv.get("solver_lock_sha256") != STAGE2_SOLVER_LOCK_SHA256:
        present.append("solver_lock_sha256 is not the pinned 2983d140… constant")
    # stage1_binding is anchored OUTWARD to the release, not merely present.
    s1 = inv.get("stage1_binding") or {}
    if auth_cond_set and {str(c) for c in (s1.get("conditions") or [])} != auth_cond_set:
        present.append("stage1_binding.conditions are not the authoritative release's")
    pin_view = pins.get("scorer_view_canonical_sha256")
    if pin_view and s1.get("registry_scorer_view_canonical_sha256") != pin_view:
        present.append("stage1_binding scorer view is not the release's published pin")
    # release_id is MANDATORY, non-null, and must re-derive (pathway excludes only release_id).
    release_id = inv.get("release_id")
    if release_id is None:
        present.append("the inventory carries no release_id — a release must name its identity")
    elif release_id != R.content_sha256({k: v for k, v in inv.items() if k != "release_id"}):
        present.append("the inventory release_id does not re-derive from its own bytes")
    present_ok = not present

    byte_bad = _bind_inventory_bytes(inv.get("bundles") or [], bundles)
    return (_check(G_INVENTORY_PRESENT, present_ok, "; ".join(present[:3])),
            _check(G_INVENTORY_BYTES, present_ok and not byte_bad, "; ".join(byte_bad[:4])),
            release_id, inv_raw_sha)


def _bind_inventory_bytes(inv_entries, bundles):
    """Every cell the inventory names binds the exact bytes on disk — arm_bundle, provenance,
    gene-set source, and the signature/convergence refs — and the right bundle id."""
    byte_bad = []
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
        for name, want in b["file_hashes"].items():           # every bound file present on disk
            f = files.get(name) or {}
            if f.get("raw_sha256") != want["raw_sha256"] or \
                    f.get("canonical_sha256") != want.get("canonical_sha256"):
                byte_bad.append(f"{cell}: inventory {name} bytes are not the ones on disk")
        bid = e.get("bundle_id")
        if bid is not None and b["run_id"] is not None and str(bid) != str(b["run_id"]):
            byte_bad.append(f"{cell}: inventory names a different bundle id")
    return byte_bad


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
