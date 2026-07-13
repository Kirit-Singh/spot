"""THE INDEPENDENT VERIFIER for the Stage-2 aggregate run manifest. Fail-closed.

generator != verifier. This module imports NOTHING from the producer: the canonical hash,
the desired-change table, the slot algebra and the key firewalls are reimplemented from
the written spec in ``verify_manifest_rules``, so this can DISAGREE with ``run_manifest``.

FROZEN AGAINST ``ROUND4_ADDENDUM.md`` sha256
``c477356278c5b7d2842659f5354792c9db7203ee774f8dd70653921124477a9f``.

WHAT IT REFUSES TO TAKE FROM THE MANIFEST UNDER TEST
----------------------------------------------------
Everything that decides what COMPLETE means. If the expected topology came from the
document being audited, a forger would declare a smaller run and pass. So each dimension
of the expectation is loaded from a SEPARATE pinned artifact:

    admitted programs   <- the v3 generic release / scorer view   (--scorer-view)
    condition universe  <- the frozen temporal batch policy        (--batch-policy)
    gene-set sources    <- the pinned source identities            (--expect-gene-sets)

The manifest's own ``conditions``, ``gene_set_sources``, ``scorer_view``, counts,
``complete`` flag and ``manifest_sha256`` are CHECKED against those. None is believed.

Counts are RECONSTRUCTED, never read: ``n_hits_in_ranking`` is recomputed from the bytes
the bundle bound (its gene-set membership INTERSECT its arm's ranked target ids).

Usage:
    python -m direct.verify_run_manifest --manifest M --bundles-root R \\
        --scorer-view V --batch-policy P --expect-gene-sets G
Exit 0 = ADMIT; 1 = REJECT.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verify_manifest_rules as R  # noqa: E402  (independent reimplementation)

VERIFIER_ID = "spot.stage02.run_manifest.verifier.v1"
SCHEMA_VERSION = "spot.stage02_run_manifest_verification.v1"

# ---- THE NAMED GATES. Each mutation dies at the one that names its violation. ---- #
G_SCORER = "scorer_view_program_set_rederives_from_its_own_portability_field"
G_MANIFEST_SCORER = "the_manifest_binds_the_scorer_view_it_was_verified_against"
G_CONDITIONS = "the_condition_universe_comes_from_the_frozen_batch_policy"
G_SOURCES = "the_gene_set_sources_are_the_pinned_ones"
G_FILES = "every_bundle_ships_its_required_files_and_they_load"
G_BYTES = "every_artifact_byte_matches_the_hash_its_bundle_bound"
G_ALL_ARM = "every_bundle_is_an_ALL_ARM_bundle_for_its_context"
G_DIRECT_SLOTS = "the_direct_bundles_fill_exactly_the_condition_slots"
G_TEMPORAL_SLOTS = "the_temporal_bundles_fill_exactly_the_ordered_pair_slots"
G_PATHWAY_SLOTS = "the_pathway_bundles_fill_exactly_the_condition_x_source_slots"
G_UNIQUE = "every_bundle_is_a_DISTINCT_invocation_no_bundle_id_appears_twice"
G_SLOTS = "every_logical_arm_slot_is_filled_exactly_once"
G_CODE = "every_bundle_binds_the_IDENTICAL_code_identity"
G_CLEAN = "the_bound_code_identity_is_a_clean_checkout"
G_SELECTION = "every_bundle_binds_the_IDENTICAL_selection_release"
G_INPUTS = "every_bundle_binds_the_IDENTICAL_shared_inputs"
G_PROJECTION = "every_arm_binds_its_programs_Stage1_scorer_projection"
G_VERDICT = "every_bundle_ships_an_independent_verification_verdict_of_ADMIT"
G_GENESET_ID = "the_gene_set_identity_is_source_specific_and_identical_within_a_source"
G_CONVERGENCE = "each_pathway_bundle_ships_ONE_shared_convergence_artifact"
G_RECONSTRUCT = "n_hits_in_ranking_RECONSTRUCTS_from_the_bytes_the_bundle_bound"
G_MAPPING = "the_desired_change_mapping_follows_the_frozen_role_x_pole_table"
G_PAIR_VIEW = "no_pair_derived_ordering_is_stored_in_a_reusable_arm_bundle"
G_COMBINED = "no_combined_balanced_weighted_or_hidden_cross_arm_score_or_order"
G_NO_PQ = "no_p_q_or_FDR_field_is_produced_by_spot_at_any_depth"
G_SELF_HASH = "the_aggregate_manifest_sha256_recomputes_from_its_own_content"
G_COMPLETE = "complete_is_true_only_when_every_slot_is_filled_exactly_once"
G_ADMISSIBLE = "a_partial_run_is_never_release_admissible"


def _one(rep, pairs, gate, what):
    """Every bundle must agree about a binding that is supposed to be SHARED."""
    values = {v for _bid, v in pairs}
    rep.gate(gate, len(values) <= 1,
             f"{len(values)} distinct {what} across the bundles; they do not agree, so "
             "these outputs are not the same run")


def verify(*, manifest_path: str, bundles_root: str, scorer_view_path: str,
           batch_policy_path: str, expect_gene_sets_path: str) -> dict[str, Any]:
    rep = R.Report()
    manifest = R.load_json(manifest_path)
    if not isinstance(manifest, dict):
        rep.gate(G_SELF_HASH, False, "the manifest is not a readable JSON document")
        return rep.doc(VERIFIER_ID, SCHEMA_VERSION, n_bundles=0, n_arm_slots=0)

    # ---- 0. THE INDEPENDENT EXPECTATION, from three separately pinned artifacts ---- #
    scorer = R.load_json(scorer_view_path)
    programs, projection = R.scorer_programs(scorer)
    declared = sorted(str(p) for p in
                      ((scorer or {}).get("base_portable_programs") or []))
    rep.gate(G_SCORER, bool(programs) and programs == declared,
             f"re-derived {programs} from the view's portability field; the view declares "
             f"{declared}. The declared list is never believed")

    policy = R.load_json(batch_policy_path) or {}
    conditions = sorted((policy.get("condition_composition") or {}).keys())
    rep.gate(G_CONDITIONS, bool(conditions),
             "the frozen batch policy names no conditions; the condition universe may "
             "not be taken from the manifest under test")

    pinned = R.load_json(expect_gene_sets_path) or {}
    sources = sorted(pinned.keys())
    rep.gate(G_SOURCES, bool(sources),
             "no pinned gene-set source identities supplied; the source universe may not "
             "be taken from the manifest under test")
    if not programs or not conditions or not sources:
        return rep.doc(VERIFIER_ID, SCHEMA_VERSION, n_bundles=0, n_arm_slots=0)

    bound = manifest.get("scorer_view") or {}
    rep.gate(G_MANIFEST_SCORER,
             bound.get("raw_sha256") == R.file_sha256(scorer_view_path)
             and bound.get("canonical_sha256") == R.content_sha256(scorer)
             and sorted(bound.get("programs") or []) == programs,
             f"the manifest binds scorer view {str(bound.get('raw_sha256'))[:16]}; the "
             f"one verified here is {R.file_sha256(scorer_view_path)[:16]}")

    want = R.expected_slots(programs, conditions, sources)

    # ---- 1. THE SELF-HASH. A caller-supplied value is trusted nowhere ---- #
    claimed = manifest.get("manifest_sha256")
    recomputed = R.content_sha256({k: v for k, v in manifest.items()
                                   if k not in ("created_at", "manifest_sha256", "path")})
    rep.gate(G_SELF_HASH, claimed == recomputed,
             f"the manifest claims {str(claimed)[:16]}; its own content hashes to "
             f"{recomputed[:16]}")

    # ---- 2. EVERY BUNDLE, from the bytes on disk ---- #
    bundles = manifest.get("bundles") or []
    filled: dict[str, list[str]] = {lane: [] for lane in R.LANES}
    ids, codes, selections, inputs, verdicts = [], [], [], [], []
    geneset_by_source: dict[str, list] = {}
    convergences: list[tuple] = []
    missing, bad_bytes, not_all_arm, bad_map = [], [], [], []
    bad_projection, pair_stored, forbidden, unloadable, bad_hits = [], [], [], [], []

    for b in bundles:
        lane, bid = b.get("lane"), str(b.get("bundle_id"))
        ids.append(bid)
        path = (R.find_bundle_dir(bundles_root, str(b.get("out_dir")))
                if b.get("out_dir") else None)
        if lane not in R.LANES or path is None:
            missing.append(f"{bid}: bundle directory {b.get('out_dir')!r} not found")
            continue

        # (a) the required files exist and LOAD. An expected filename holding arbitrary
        #     bytes is not an artifact, however neatly it hashes.
        for fn in R.BUNDLE_FILES[lane]:
            fp = os.path.join(path, fn)
            if not os.path.exists(fp):
                missing.append(f"{bid}: missing {fn}")
            elif R.load_json(fp) is None:
                unloadable.append(f"{bid}/{fn}: not readable JSON — arbitrary bytes "
                                  "under an expected filename are not an artifact")

        # (b) EVERY file the bundle bound still hashes to what it bound.
        for fn, bound_sha in sorted((b.get("files") or {}).items()):
            fp = os.path.join(path, fn)
            if not os.path.exists(fp):
                missing.append(f"{bid}: bound {fn} is absent")
            elif R.file_sha256(fp) != bound_sha:
                bad_bytes.append(f"{bid}/{fn}: bound {str(bound_sha)[:16]}, on disk "
                                 f"{R.file_sha256(fp)[:16]}")

        inv = R.load_json(os.path.join(path, "arm_bundle.json"))
        prov = R.load_json(os.path.join(path, R.PROVENANCE_OF[lane]))
        report = R.load_json(os.path.join(path, R.REPORT_OF[lane]))
        if not isinstance(inv, dict) or not isinstance(prov, dict) \
                or not isinstance(report, dict):
            continue

        forbidden += R.forbidden_keys(inv) + R.forbidden_keys(prov)
        pair_stored += R.pair_derived_keys(inv)

        # (c) the bundle is an ALL-ARM bundle for its context
        ctx = inv.get("context") or {}
        arms = inv.get("arms") or []
        want_keys = {R.arm_key(lane, p, dc, ctx)
                     for p in programs for dc in R.DESIRED_CHANGES}
        got_keys = [str(a.get("arm_key")) for a in arms]
        if sorted(got_keys) != sorted(want_keys):
            not_all_arm.append(
                f"{bid}: carries {len(got_keys)} arms; an all-arm bundle for this context "
                f"is {len(want_keys)} ({len(programs)} programs x 2 desired changes). A "
                "pair-specific bundle leaves the rest of its slots empty")
        filled[lane] += got_keys

        membership = (R.load_json(os.path.join(
            path, ((inv.get("bindings") or {}).get("gene_set_membership") or {})
            .get("path", ""))) if lane == R.LANE_PATHWAY else None)

        for a in arms:
            key = str(a.get("arm_key"))
            # (d) the desired change follows the FROZEN role x pole table
            for origin in (a.get("derived_from_poles") or []):
                spec = R.SPEC_DESIRED_CHANGE.get(
                    (str(origin.get("role")), str(origin.get("pole_direction"))))
                if spec is not None and spec != a.get("desired_change"):
                    bad_map.append(
                        f"{key}: {origin.get('role')}({origin.get('pole_direction')}) is "
                        f"a {spec}, but the arm declares {a.get('desired_change')}")
            # (e) the arm binds its program's Stage-1 scorer projection
            pid = str(a.get("program_id"))
            if projection.get(pid) and a.get("program_method_hash") != projection[pid]:
                bad_projection.append(
                    f"{key}: binds scorer projection "
                    f"{str(a.get('program_method_hash'))[:16]}; the scorer view says "
                    f"{str(projection[pid])[:16]}")
            # (f) RECONSTRUCT the hit counts from the bound bytes. Never read them.
            if lane == R.LANE_PATHWAY:
                ranking = R.load_json(os.path.join(
                    path, (a.get("ranking") or {}).get("path", "")))
                recomputed_hits = R.reconstruct_hits(membership, ranking)
                claimed_hits = {str(k): int(v) for k, v in
                                (a.get("n_hits_by_set") or {}).items()}
                if claimed_hits != recomputed_hits:
                    bad_hits.append(
                        f"{key}: declares hits {dict(list(claimed_hits.items())[:3])}; "
                        f"recomputing from the bound membership and ranking bytes gives "
                        f"{dict(list(recomputed_hits.items())[:3])}")

        binding = prov.get("run_binding") or {}
        codes.append((bid, R.content_sha256(binding.get("code_identity"))))
        selections.append((bid, R.content_sha256(binding.get("selection_release"))))
        inputs.append((bid, R.content_sha256(binding.get("stage2_inputs"))))
        verdicts.append((bid, report.get("verdict")))

        if lane == R.LANE_PATHWAY:
            src = str(ctx.get("gene_set_source"))
            geneset_by_source.setdefault(src, []).append(
                (bid, R.content_sha256(inv.get("gene_sets"))))
            conv = inv.get("convergence") or {}
            cpath = os.path.join(path, "convergence.json")
            convergences.append((
                bid, str(conv.get("convergence_id")),
                {str(a.get("convergence_id")) for a in arms if a.get("convergence_id")},
                conv.get("sha256"),
                R.file_sha256(cpath) if os.path.exists(cpath) else None))

    rep.gate(G_FILES, not missing and not unloadable,
             "; ".join((missing + unloadable)[:4]))
    rep.gate(G_BYTES, not bad_bytes, "; ".join(bad_bytes[:4]))
    rep.gate(G_ALL_ARM, not not_all_arm, "; ".join(not_all_arm[:3]))
    rep.gate(G_MAPPING, not bad_map, "; ".join(bad_map[:4]))
    rep.gate(G_PROJECTION, not bad_projection, "; ".join(bad_projection[:4]))
    rep.gate(G_RECONSTRUCT, not bad_hits, "; ".join(bad_hits[:3]))
    rep.gate(G_PAIR_VIEW, not pair_stored,
             f"a reusable arm bundle stores pair-derived ordering(s) {pair_stored[:5]}; "
             "Pareto tiers and concordance labels are join-time display only")
    rep.gate(G_NO_PQ, not forbidden, f"forbidden keys: {sorted(set(forbidden))[:6]}")

    # ---- 3. THE TOPOLOGY: the slots, per lane ---- #
    gate_of = {R.LANE_DIRECT: G_DIRECT_SLOTS, R.LANE_TEMPORAL: G_TEMPORAL_SLOTS,
               R.LANE_PATHWAY: G_PATHWAY_SLOTS}
    all_ok = True
    for lane in R.LANES:
        got = filled[lane]
        miss = sorted(want[lane] - set(got))
        dupes = sorted({k for k in got if got.count(k) > 1})
        extra = sorted(set(got) - want[lane])
        ok = not miss and not dupes and not extra
        all_ok = all_ok and ok
        rep.gate(gate_of[lane], ok,
                 f"{len(set(got) & want[lane])}/{len(want[lane])} slots filled; "
                 f"{len(miss)} missing (e.g. {miss[:2]}), {len(dupes)} duplicated (e.g. "
                 f"{dupes[:2]}), {len(extra)} unexpected (e.g. {extra[:2]})")

    dupe_ids = sorted({i for i in ids if ids.count(i) > 1})
    rep.gate(G_UNIQUE, not dupe_ids,
             f"bundle id(s) {dupe_ids} appear more than once: a duplicate result cannot "
             "stand in for a missing one, and one invocation repeated is not two")

    n_filled = sum(len(set(filled[lane]) & want[lane]) for lane in R.LANES)
    n_want = sum(len(want[lane]) for lane in R.LANES)
    rep.gate(G_SLOTS, all_ok and not dupe_ids,
             f"{n_filled}/{n_want} logical arm slots filled exactly once")

    # ---- 4. THE SHARED BINDINGS: identical where the science requires it ---- #
    _one(rep, codes, G_CODE, "code identities")
    _one(rep, selections, G_SELECTION, "selection releases")
    _one(rep, inputs, G_INPUTS, "shared input bindings")

    dirty = [b.get("bundle_id") for b in bundles
             if (b.get("code_identity") or {}).get("clean_tree") is not True]
    rep.gate(G_CLEAN, not dirty,
             f"{len(dirty)} bundle(s) were taken from a dirty tree; a digest over "
             "uncommitted bytes does not identify the commit printed beside it")

    rejected = [bid for bid, v in verdicts if v != R.ADMIT]
    rep.gate(G_VERDICT, bool(verdicts) and not rejected,
             f"bundle(s) {rejected[:4]} carry no independent verdict of ADMIT")

    # ---- 5. GENE SETS + THE SHARED CONVERGENCE ---- #
    bad_gs = []
    for src, entries in sorted(geneset_by_source.items()):
        if len({h for _b, h in entries}) > 1:
            bad_gs.append(f"{src}: its bundles bind DIFFERENT gene-set identities")
        if src not in pinned:
            bad_gs.append(f"{src}: not one of the pinned gene-set sources {sources}")
    identities = {h for e in geneset_by_source.values() for _b, h in e}
    if len(geneset_by_source) > 1 and len(identities) < len(geneset_by_source):
        bad_gs.append("two sources share one gene-set identity")
    rep.gate(G_GENESET_ID, not bad_gs, "; ".join(bad_gs[:4]))

    bad_conv = []
    for bid, cid, refs, declared_sha, actual_sha in convergences:
        if not cid or cid == "None":
            bad_conv.append(f"{bid}: ships no convergence artifact")
        if refs and refs != {cid}:
            bad_conv.append(f"{bid}: its arms reference convergence {sorted(refs)[:2]}, "
                            f"but the bundle ships {cid}")
        if declared_sha != actual_sha:
            bad_conv.append(f"{bid}: convergence.json bytes do not match the id it bound")
    if convergences and len({c[1] for c in convergences}) != len(convergences):
        bad_conv.append("two pathway bundles share one convergence artifact; convergence "
                        "is per (condition, source)")
    rep.gate(G_CONVERGENCE, not bad_conv, "; ".join(bad_conv[:4]))

    # ---- 6. NO COMBINED OBJECTIVE, and COMPLETENESS ---- #
    rep.gate(G_COMBINED,
             manifest.get("combined_objective") is None
             and manifest.get("cross_arm_score_or_order") is None
             and manifest.get("combined_objective_permitted") is False,
             "the manifest carries or permits a combined cross-arm objective")

    truly = all_ok and not dupe_ids and n_filled == n_want
    rep.gate(G_COMPLETE, bool(manifest.get("complete")) == truly,
             f"the manifest declares complete={manifest.get('complete')}; "
             f"{n_filled}/{n_want} slots are filled exactly once, so complete={truly}")
    rep.gate(G_ADMISSIBLE, bool(manifest.get("release_admissible")) is truly,
             "a partial run declared itself release-admissible")

    return rep.doc(
        VERIFIER_ID, SCHEMA_VERSION,
        manifest_sha256=claimed, manifest_sha256_recomputed=recomputed,
        n_bundles=len(bundles), n_arm_slots=n_filled, n_expected_arm_slots=n_want,
        programs=programs, conditions=conditions, gene_set_sources=sources,
        selection_capacity=R.selection_capacity(len(programs), len(conditions)))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Independent verifier for the Stage-2 aggregate run manifest")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--bundles-root", required=True)
    ap.add_argument("--scorer-view", required=True,
                    help="the v3 generic release / scorer view: the admitted programs")
    ap.add_argument("--batch-policy", required=True,
                    help="the frozen batch policy: the condition universe")
    ap.add_argument("--expect-gene-sets", required=True,
                    help="the pinned gene-set source identities: the source universe")
    ap.add_argument("--report", default=None, help="write the verdict here (JSON)")
    args = ap.parse_args(argv)

    try:
        doc = verify(manifest_path=args.manifest, bundles_root=args.bundles_root,
                     scorer_view_path=args.scorer_view,
                     batch_policy_path=args.batch_policy,
                     expect_gene_sets_path=args.expect_gene_sets)
    except Exception as exc:                    # a crash IS a verification failure
        rep = R.Report()
        rep.gate(f"verifier_completed({type(exc).__name__})", False, str(exc))
        doc = rep.doc(VERIFIER_ID, SCHEMA_VERSION, n_bundles=0, n_arm_slots=0)

    if args.report:
        with open(args.report, "w") as fh:
            json.dump(doc, fh, indent=2, sort_keys=True)
            fh.write("\n")
    print(json.dumps({k: v for k, v in doc.items() if k != "checks"},
                     indent=2, sort_keys=True, default=str))
    if doc["failed_gates"]:
        print("\nFAILED GATES:")
        for c in doc["checks"]:
            if c["status"] == R.FAIL:
                print(f"  - {c['gate']}: {c['detail']}")
    return 0 if doc["verdict"] == R.ADMIT else 1


if __name__ == "__main__":
    raise SystemExit(main())
