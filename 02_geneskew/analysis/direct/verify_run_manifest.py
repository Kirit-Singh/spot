"""THE INDEPENDENT VERIFIER for the Stage-2 aggregate run manifest. Fail-closed.

generator != verifier. This module imports NOTHING from the producer: the canonical hash,
the desired-change table, the slot algebra and the key firewalls are reimplemented from
the written spec in ``verify_manifest_rules``, so this can DISAGREE with ``run_manifest``.

FROZEN AGAINST ``ROUND4_ADDENDUM.md`` sha256
``c477356278c5b7d2842659f5354792c9db7203ee774f8dd70653921124477a9f``.

WHAT IT REFUSES TO TAKE FROM THE MANIFEST UNDER TEST
----------------------------------------------------
Everything that decides what COMPLETE means, WHO may admit an arm, and WHAT the run was
built from. If any of that came from the document being audited, a forger would simply
declare it and pass. So each is loaded from a SEPARATE pinned artifact:

    admitted programs   <- release.selector + program.base_portable   (--release)
    condition universe  <- release.selector.conditions               (--release)
    gene-set sources    <- release.selector.pathway_sources          (--release)
    the release itself  <- an independently pinned canonical hash    (--expect-release-sha256)
    gene-set identities <- the pinned source identities              (--expect-gene-sets)
    lane verifiers      <- the pinned verifier + gate inventory      (--expect-verifiers)
    code identity       <- the pinned checkout                       (--expected-code-identity)

The temporal BATCH POLICY is NOT an authority here and is no longer read: batch is out of
the reusable temporal chain, and a confound diagnostic was never the right place to learn
which conditions exist. The DiD estimand stays population-level.

The manifest's own ``conditions``, ``gene_set_sources``, ``scorer_view``, counts,
``complete`` flag and ``manifest_sha256`` are CHECKED against those. None is believed.

THREE SEAMS AN INDEPENDENT REVIEW FOUND, AND WHAT CLOSED THEM
-------------------------------------------------------------
* A gene-set source NAME is not an identity. Checking only that the two sources differed
  and agreed within themselves let a FORGED "reactome" pass, because nothing compared it
  to the Reactome that was actually pinned. Now every field — release, raw and canonical
  hash, both namespaces, licence, both universe bindings — is compared to the pin.
* ``report["verdict"] == "admit"`` is a string, not an admission. A two-byte file saying
  ``{"verdict": "admit"}`` passed. A report is now a TYPED artifact from the PINNED lane
  verifier, carrying its gate inventory, and it must BIND THE BUNDLE IT JUDGED — an ADMIT
  that names no bundle can be copied onto any bundle.
* ``clean_tree: true`` was believed because the artifact said so. A bundle now RECORDS its
  tree state and its ``code_identity``; the VERIFIER decides the final clean-tree status
  against an independently pinned build. A run does not get to be the witness for its own
  checkout.

PAIR AGNOSTICISM. A reusable arm carries NO role, NO pole and NO pair-derived program id,
and none is required of it — requiring one would drag a pair back into an artifact whose
whole purpose is to be reusable. What a bundle MUST bind is the Stage-1 identity its arms
stand on (the release's scorer view + admitted program ids) and the BUILD that produced it
(``code_identity``), kept explicitly separate from WHAT THE CODE DID (the method digests).

Counts are RECONSTRUCTED, never read: ``n_hits_in_ranking`` is recomputed from the bytes
the bundle bound (its gene-set membership INTERSECT its arm's ranked target ids).

Usage:
    python -m direct.verify_run_manifest --manifest M --bundles-root R \\
        --release REL --release-root ROOT --expect-release-sha256 SHA \\
        --expect-gene-sets G --expect-verifiers V --expected-code-identity C
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
G_SCORER = "the_admitted_set_rederives_from_base_portable_AND_agrees_with_the_selector"
G_RELEASE_PIN = "the_release_canonically_hashes_to_the_INDEPENDENTLY_pinned_release"
G_VIEW_PIN = "the_release_binds_the_scorer_view_and_projection_hashes_it_publishes"
G_MANIFEST_SCORER = "the_manifest_binds_the_release_it_was_verified_against"
G_CONDITIONS = "the_condition_universe_comes_from_release_selector_conditions"
G_SOURCES = "the_gene_set_sources_are_the_releases_pathway_sources"
G_NO_BATCH = "no_batch_commentary_in_a_reusable_bundle_or_the_aggregate_manifest"
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
G_METHOD = "every_bundle_binds_the_IDENTICAL_method_digest"
G_PROJECTION = "every_bundle_binds_the_releases_scorer_view_and_admitted_programs"
G_VERDICT = "every_bundle_ships_an_independent_verification_verdict_of_ADMIT"
G_GENESET_ID = "the_gene_set_identity_is_source_specific_and_identical_within_a_source"
G_CONVERGENCE = "each_pathway_bundle_ships_ONE_shared_convergence_artifact"
G_RECONSTRUCT = "n_hits_in_ranking_RECONSTRUCTS_from_the_bytes_the_bundle_bound"
G_MAPPING = "every_arm_is_PAIR_AGNOSTIC_its_key_and_desired_change_agree"
G_PAIR_VIEW = "no_pair_derived_ordering_is_stored_in_a_reusable_arm_bundle"
G_COMBINED = "no_combined_balanced_weighted_or_hidden_cross_arm_score_or_order"
G_NO_PQ = "no_p_q_or_FDR_field_is_produced_by_spot_at_any_depth"
G_SELF_HASH = "the_aggregate_manifest_sha256_recomputes_from_its_own_content"
G_COMPLETE = "topology_complete_is_true_only_when_every_slot_is_filled_exactly_once"
G_NO_SELF_ADMISSION = "the_PRODUCER_never_self_declares_release_admission"


def _one(rep, pairs, gate, what):
    """Every bundle must agree about a binding that is supposed to be SHARED."""
    values = {v for _bid, v in pairs}
    rep.gate(gate, len(values) <= 1,
             f"{len(values)} distinct {what} across the bundles; they do not agree, so "
             "these outputs are not the same run")


def verify(*, manifest_path: str, bundles_root: str, release_path: str,
           release_root: str, expect_release_sha256: str, expect_gene_sets_path: str,
           expect_verifiers_path: str, expected_code_identity_path: str
           ) -> dict[str, Any]:
    rep = R.Report()
    expect_verifiers = R.load_json(expect_verifiers_path) or {}
    expected_code = R.load_json(expected_code_identity_path) or {}
    manifest = R.load_json(manifest_path)
    if not isinstance(manifest, dict):
        rep.gate(G_SELF_HASH, False, "the manifest is not a readable JSON document")
        return rep.doc(VERIFIER_ID, SCHEMA_VERSION, n_bundles=0, n_arm_slots=0)

    # ---- 0. THE INDEPENDENT EXPECTATION, from the AUTHORITATIVE Stage-1 v3 release ---- #
    # The programs, the conditions and the pathway sources ALL come from the release. The
    # batch policy is NOT an authority here: batch is out of the reusable temporal chain,
    # and a confound diagnostic was never the right place to learn which conditions exist.
    release = R.load_json(release_path)
    release_canon = R.content_sha256(release) if release is not None else None

    # THE PIN. A forged, truncated or REORDERED selector.conditions changes this hash —
    # which is the whole reason the release is content-addressed and pinned outside the run.
    rep.gate(G_RELEASE_PIN,
             bool(expect_release_sha256) and release_canon == expect_release_sha256,
             f"the staged release canonically hashes to {str(release_canon)[:16]}; the "
             f"pinned release is {str(expect_release_sha256)[:16]}. A forged, missing or "
             "reordered condition list is a different release")

    view = R.resolve_component(release, R.VIEW_COMPONENT, release_root)
    programs, projection = R.scorer_programs(view)
    declared = R.release_admitted(release)
    rep.gate(G_SCORER,
             bool(programs) and bool(declared) and programs == declared,
             f"base_portable derives {programs}; the release selector declares {declared}. "
             "Two independent statements of the same fact — a disagreement means one of "
             "them is wrong about what this release admits")

    rep.gate(G_VIEW_PIN,
             view is not None
             and R.content_sha256(view) == (release or {}).get(
                 "registry_scorer_view_canonical_sha256")
             and bool((release or {}).get("registry_scorer_projection_sha256")),
             "the staged scorer view is not the one the release binds, or the release "
             "publishes no scorer-projection hash")

    conditions = R.release_conditions(release)
    rep.gate(G_CONDITIONS, bool(conditions),
             "release.selector.conditions names no conditions; the condition universe may "
             "not be taken from the manifest under test, and not from a batch policy")

    sources = R.release_sources(release)
    pinned = R.load_json(expect_gene_sets_path) or {}
    rep.gate(G_SOURCES,
             bool(sources) and sorted(sources) == sorted(pinned.keys()),
             f"the release names sources {sources}; the pinned gene-set identities cover "
             f"{sorted(pinned.keys())}")
    if not programs or not conditions or not sources:
        return rep.doc(VERIFIER_ID, SCHEMA_VERSION, n_bundles=0, n_arm_slots=0)

    bound = manifest.get("stage1_v3_release") or {}
    rep.gate(G_MANIFEST_SCORER,
             bound.get("release_canonical_sha256") == release_canon
             and sorted(bound.get("programs") or []) == programs
             and list(bound.get("conditions") or []) == conditions,
             f"the manifest binds release {str(bound.get('release_canonical_sha256'))[:16]}"
             f" / conditions {bound.get('conditions')}; the release verified here is "
             f"{str(release_canon)[:16]} / {conditions}")

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
    ids, codes, selections, inputs, methods = [], [], [], [], []
    geneset_by_source: dict[str, list] = {}
    convergences: list[tuple] = []
    missing, bad_bytes, not_all_arm, bad_map = [], [], [], []
    bad_projection, pair_stored, forbidden, unloadable, bad_hits = [], [], [], [], []
    bad_reports, bad_code, bad_gene_sets, batch_stored = [], [], [], []

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
        batch_stored += R.batch_keys(inv)

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
            # (d) THE ARM IS PAIR-AGNOSTIC. It carries no role, no pole and no pair-derived
            #     program id, and none is required of it. What must hold is that its key and
            #     its declared desired_change agree, and that the change is one of the two.
            dc = a.get("desired_change")
            if dc not in R.DESIRED_CHANGES:
                bad_map.append(f"{key}: desired_change {dc!r} is not one of "
                               f"{list(R.DESIRED_CHANGES)}")
            elif key.split("|")[2:3] != [str(dc)]:
                bad_map.append(f"{key}: the key says "
                               f"{key.split('|')[2:3]} but the arm declares {dc!r}")
            if str(a.get("program_id")) not in programs:
                bad_map.append(f"{key}: program {a.get('program_id')!r} is not admitted by "
                               "the release")
            # (f) RECONSTRUCT the counts from the bound bytes. Never read them.
            ranking = R.load_json(os.path.join(
                path, (a.get("ranking") or {}).get("path", "")))
            # RETAINED-ROW semantics (W5): every target stays in the rows with rank null
            # when it is not rankable, so n_ranked is a count of RANKS, not of rows.
            if a.get("n_ranked") is not None and \
                    int(a["n_ranked"]) != R.n_ranked(ranking):
                bad_hits.append(
                    f"{key}: declares n_ranked={a.get('n_ranked')}, but the bound ranking "
                    f"carries {R.n_ranked(ranking)} non-null ranks over "
                    f"{len(R.arm_records(ranking))} retained rows")
            if lane == R.LANE_PATHWAY:
                recomputed_hits = R.reconstruct_hits(membership, ranking)
                claimed_hits = {str(k): int(v) for k, v in
                                (a.get("n_hits_by_set") or {}).items()}
                if claimed_hits != recomputed_hits:
                    bad_hits.append(
                        f"{key}: declares hits {dict(list(claimed_hits.items())[:3])}; "
                        f"recomputing from the bound membership and ranking bytes gives "
                        f"{dict(list(recomputed_hits.items())[:3])}")

        binding = prov.get("run_binding") or {}
        codes.append((bid, R.content_sha256(R.code_binding(prov))))
        selections.append((bid, R.content_sha256(binding.get("selection_release"))))
        inputs.append((bid, R.content_sha256(binding.get("stage2_inputs"))))
        methods.append((bid, R.content_sha256(R.method_binding(prov))))

        # The report must be a TYPED admission from the PINNED verifier, ABOUT THIS
        # BUNDLE. A file that merely says {"verdict": "admit"} is not one.
        bad_reports += R.check_report(
            report, lane, bid, expect_verifiers,
            R.file_sha256(os.path.join(path, "arm_bundle.json")),
            R.file_sha256(os.path.join(path, R.PROVENANCE_OF[lane])))
        # Every bundle's code identity, against an INDEPENDENTLY pinned checkout.
        bad_code += R.check_code_identity(R.code_binding(prov), expected_code, bid)

        if lane == R.LANE_PATHWAY:
            src = str(ctx.get("gene_set_source"))
            geneset_by_source.setdefault(src, []).append(
                (bid, R.content_sha256(inv.get("gene_sets"))))
            # ...and the gene-set identity FIELD BY FIELD against the pinned source.
            bad_gene_sets += R.check_gene_sets(
                inv.get("gene_sets"), pinned.get(src), src, bid)
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
    # THE STAGE-1 BINDING, verified against the release — NOT against a pair.
    #
    # A reusable arm is PAIR-AGNOSTIC: it carries no role, no pole and no pair-derived
    # program id, and W3 must not require one. What it MUST bind is the Stage-1 identity
    # its arms were projected on — the scorer view this release publishes, and the admitted
    # program ids. Those are re-derived here from the release's own bytes.
    want_view = (release or {}).get("registry_scorer_view_canonical_sha256")
    for b in bundles:
        sel = b.get("selection_release") or {}
        bound_view = (sel.get("registry_scorer_view_sha256")
                      or sel.get("registry_scorer_view_canonical_sha256"))
        if bound_view != want_view:
            bad_projection.append(
                f"{b.get('bundle_id')}: binds scorer view {str(bound_view)[:16]}; this "
                f"release publishes {str(want_view)[:16]}")
        admitted = b.get("admitted_programs")
        if admitted is not None and sorted(admitted) != programs:
            bad_projection.append(
                f"{b.get('bundle_id')}: its arms stand on {sorted(admitted)[:3]}…; the "
                f"release admits {programs[:3]}…")
    rep.gate(G_PROJECTION, not bad_projection, "; ".join(bad_projection[:4]))
    rep.gate(G_RECONSTRUCT, not bad_hits, "; ".join(bad_hits[:3]))
    rep.gate(G_PAIR_VIEW, not pair_stored,
             f"a reusable arm bundle stores pair-derived ordering(s) {pair_stored[:5]}; "
             "Pareto tiers and concordance labels are join-time display only")
    rep.gate(G_NO_PQ, not forbidden, f"forbidden keys: {sorted(set(forbidden))[:6]}")
    rep.gate(G_NO_BATCH,
             not batch_stored and not R.batch_keys(manifest.get("bundles") or []),
             f"batch commentary {sorted(set(batch_stored))[:5]} is stored in a reusable "
             "bundle; the DiD estimand is population-level and batch stays out of the "
             "reusable temporal chain")

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
    _one(rep, selections, G_SELECTION, "selection releases")
    _one(rep, inputs, G_INPUTS, "shared input bindings")
    _one(rep, methods, G_METHOD, "method digests")

    # A code identity that differs BETWEEN bundles is caught here; one that differs from
    # the PINNED checkout is caught by ``bad_code`` below. Both are G_CODE: the bundles
    # must agree with each other AND with a witness outside the run.
    if len({v for _bid, v in codes}) > 1:
        bad_code.append(
            f"{len({v for _bid, v in codes})} distinct code identities across the "
            "bundles; these outputs were not built from one checkout")

    # The code identity is compared to an INDEPENDENTLY PINNED checkout, not believed.
    # A resealed clean_tree=true over another commit is exactly the claim that needs an
    # outside witness, and the manifest is not one.
    rep.gate(G_CODE, not bad_code, "; ".join(bad_code[:4]))
    # THE CHECKOUT IS ATTESTED BY THE PIN, NOT BY THE RUN.
    # A bundle that swore it was clean would be the artifact vouching for itself — the C3
    # seam. W5's native producer correctly binds no commit and no clean_tree at all: it
    # never fabricates a commit it did not read. So the witness is the external pin.
    # The producer RECORDS its tree state; the VERIFIER decides the final clean-tree
    # status, against the external pin. A bundle that swore it was clean would be the
    # artifact vouching for itself — the C3 seam.
    recorded_dirty = [b.get("bundle_id") for b in bundles
                      if (b.get("code_identity") or {}).get("clean_tree") is False]
    rep.gate(G_CLEAN,
             expected_code.get("clean_tree") is True and not recorded_dirty,
             f"the pinned build declares clean_tree={expected_code.get('clean_tree')!r} and "
             f"{len(recorded_dirty)} bundle(s) RECORDED a dirty tree. A digest over "
             "uncommitted bytes does not identify the build printed beside it, and a run "
             "may not vouch for its own checkout")

    rep.gate(G_VERDICT, bool(bundles) and not bad_reports,
             "; ".join(bad_reports[:4]))

    # ---- 5. GENE SETS + THE SHARED CONVERGENCE ---- #
    bad_gs = list(bad_gene_sets)
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
    rep.gate(G_COMPLETE, bool(manifest.get("topology_complete")) == truly,
             f"the manifest declares topology_complete="
             f"{manifest.get('topology_complete')}; {n_filled}/{n_want} slots are filled "
             f"exactly once, so topology_complete={truly}")

    # THE PRODUCER MAY NOT ADMIT ITS OWN RUN.
    #
    # It used to set release_admissible from the topology alone, so a run whose lane
    # reports were bare verdict strings, or which bound inconsistent selections, was
    # stamped admissible by the thing that produced it and only refused later, here. A
    # correctly-shaped run is not a verified one, and the shape is all the producer can
    # see. So a manifest arriving with an admission already granted is refused outright —
    # whatever else is true of it.
    admission = manifest.get("admission") or {}
    rep.gate(G_NO_SELF_ADMISSION,
             manifest.get("release_admissible") is not True
             and manifest.get("complete") is not True
             and admission.get("granted_by") in (None, VERIFIER_ID)
             and manifest.get("topology_complete_is_an_admission") is not True,
             f"the manifest declares release_admissible="
             f"{manifest.get('release_admissible')!r} / complete="
             f"{manifest.get('complete')!r} / admission.granted_by="
             f"{admission.get('granted_by')!r}. A correctly-shaped run is not a verified "
             "one, and the shape is all the producer can see")

    doc = rep.doc(
        VERIFIER_ID, SCHEMA_VERSION,
        manifest_sha256=claimed, manifest_sha256_recomputed=recomputed,
        n_bundles=len(bundles), n_arm_slots=n_filled, n_expected_arm_slots=n_want,
        programs=programs, conditions=conditions, gene_set_sources=sources,
        selection_capacity=R.selection_capacity(len(programs), len(conditions)))
    # ---- THE ADMISSION. Granted HERE, by this independent report, or not at all. ---- #
    # The manifest says what SHAPE the run has. This says whether it may be released: every
    # native lane report typed and admitted by its pinned verifier, one selection, one
    # checkout, every slot filled exactly once.
    doc["topology_complete"] = truly
    doc["release_admissible"] = doc["verdict"] == R.ADMIT
    doc["admission"] = {
        "status": ("admitted" if doc["verdict"] == R.ADMIT
                   else "refused_by_independent_aggregate_admission"),
        "granted_by": VERIFIER_ID,
        "topology_complete_is_an_admission": False,
    }
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Independent verifier for the Stage-2 aggregate run manifest")
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--bundles-root", required=True)
    ap.add_argument("--release", required=True,
                    help="the authoritative Stage-1 v3 release: the admitted programs, the "
                         "conditions and the pathway sources")
    ap.add_argument("--release-root", required=True,
                    help="the directory the release is STAGED in; components resolve "
                         "against it, never against a machine default")
    ap.add_argument("--expect-release-sha256", required=True,
                    help="the INDEPENDENTLY pinned canonical hash of that release; a "
                         "forged, missing or reordered condition list changes it")
    ap.add_argument("--expect-gene-sets", required=True,
                    help="the pinned gene-set source identities: the source universe, and "
                         "the exact release/hash/namespace/licence/universe bindings every "
                         "bundle of that source must declare")
    ap.add_argument("--expect-verifiers", required=True,
                    help="the pinned per-lane verifier identity and required gate "
                         "inventory: WHO may admit an arm, and WHAT they must have checked")
    ap.add_argument("--expected-code-identity", required=True,
                    help="the independently pinned checkout (commit + digest) every bundle "
                         "must have been built from; a run's code identity may not be "
                         "taken from the run")
    ap.add_argument("--report", default=None, help="write the verdict here (JSON)")
    args = ap.parse_args(argv)

    try:
        doc = verify(manifest_path=args.manifest, bundles_root=args.bundles_root,
                     release_path=args.release, release_root=args.release_root,
                     expect_release_sha256=args.expect_release_sha256,
                     expect_gene_sets_path=args.expect_gene_sets,
                     expect_verifiers_path=args.expect_verifiers,
                     expected_code_identity_path=args.expected_code_identity)
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
