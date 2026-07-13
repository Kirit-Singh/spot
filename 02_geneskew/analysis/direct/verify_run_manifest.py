"""THE INDEPENDENT VERIFIER for the Stage-2 aggregate run manifest. Fail-closed.

generator != verifier. This module imports NOTHING from the producer: the canonical hash,
the desired-change table, the slot algebra and the key firewalls are reimplemented from the
written spec, so this can DISAGREE with ``run_manifest``. Frozen against ROUND4_ADDENDUM.md
sha256 c477356278c5b7d2842659f5354792c9db7203ee774f8dd70653921124477a9f.

WHAT IT REFUSES TO TAKE FROM THE MANIFEST UNDER TEST
----------------------------------------------------
Everything that decides what COMPLETE means, WHO may admit an arm, and WHAT the run was
built from — each loaded from a SEPARATE pinned artifact:

    programs / conditions / sources <- the release                 (--release)
    the release itself   <- an independently pinned canonical hash (--expect-release-sha256)
    gene-set identities  <- the pinned source identities           (--expect-gene-sets)
    lane verifiers       <- the pinned verifier + gate inventory   (--expect-verifiers)
    code identity        <- the pinned checkout                    (--expected-code-identity)
    the environment      <- the lock, and the verifier's OWN pin   (--env-lock)

The batch policy is NOT an authority here. The manifest's own conditions, sources, counts,
``topology_complete`` and ``manifest_sha256`` are CHECKED against the pins above; none is
believed. Seams closed by earlier reviews (see the git log): a gene-set source NAME is not
an identity; a verdict string is not an admission; ``clean_tree`` is attested by an external
pin, never by the artifact itself. Counts are RECONSTRUCTED, never read.

Every input is explicit; no path is ever inferred. See ``verify_invocation`` for the
machine-readable contract W7 consumes. Exit 0 = ADMIT; 1 = REJECT.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import verify_bundle_scan as S  # noqa: E402  (the per-bundle scan)
import verify_invocation as I  # noqa: E402  (the W7 contract + dry run)
import verify_manifest_rules as R  # noqa: E402
import verify_release_envelope as E  # noqa: E402  (the inventory + the external envelope)
import verify_release_rules as W  # noqa: E402  (the W5-audit rules)  (independent reimplementation)

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
G_INVENTORY = "the_PRODUCER_ROOT_INVENTORY_is_present_self_hashing_and_byte_true"
G_EXTERNAL_ADMISSION = "an_INDEPENDENT_ROOT_ADMISSION_ENVELOPE_admits_this_release"
G_EXTERNAL_BINDS = "the_external_admission_BINDS_THIS_EXACT_producer_inventory"
G_KEYED_PROVENANCE = "stage2_inputs_is_a_FIXED_KEYED_OBJECT_never_a_role_value_list"
G_RANKS = "every_declared_RANK_rederives_from_that_arms_own_values"
G_CROSS_BUNDLE = "the_REVERSE_of_every_ordered_pair_is_the_exact_negation_ACROSS_bundles"
G_NO_STALE = "no_STALE_unbound_ranking_file_sits_in_a_bundle_looking_like_evidence"
G_STAGE1_NONNULL = "no_Stage1_release_projection_or_selector_field_is_NULL"
G_PREFLIGHT = "the_PREFLIGHT_proves_the_FINAL_bytes_and_admits_NOTHING"
G_INVENTORY_ARMS = "the_INVENTORY_binds_EXACTLY_the_rankings_the_ARMS_bind"
G_ENV_LOCK = "every_bundle_binds_the_COMMITTED_env_lock_and_it_is_the_lock_supplied"


def _one(rep, pairs, gate, what):
    """Every bundle must agree about a binding that is supposed to be SHARED."""
    values = {v for _bid, v in pairs}
    rep.gate(gate, len(values) <= 1,
             f"{len(values)} distinct {what}; they do not agree, so these outputs are not "
             "the same run")


def verify(*, manifest_path: str, bundles_root: str, release_path: str,
           release_root: str, expect_release_sha256: str, expect_gene_sets_path: str,
           expect_verifiers_path: str, expected_code_identity_path: str,
           env_lock_path: str = None, expect_env_lock_sha256: str = None,
           release_root_dir: str = None) -> dict[str, Any]:
    rep = R.Report()
    root = release_root_dir or bundles_root
    # THE ENVIRONMENT LOCK, by its BYTES (see ``verify_release_rules.check_supplied_lock``).
    env_lock = (R.file_sha256(env_lock_path)
                if env_lock_path and os.path.exists(env_lock_path) else None)
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
    found = S.scan(bundles=bundles, bundles_root=bundles_root, programs=programs,
                   projection=projection, pinned=pinned,
                   expect_verifiers=expect_verifiers, expected_code=expected_code,
                   release=release, env_lock_sha256=env_lock)
    filled, ids = found["filled"], found["ids"]
    codes, selections = found["codes"], found["selections"]
    inputs, methods = found["inputs"], found["methods"]
    geneset_by_source, convergences = found["geneset_by_source"], found["convergences"]
    missing, bad_bytes, not_all_arm = (found["missing"], found["bad_bytes"],
                                       found["not_all_arm"])
    bad_map, bad_projection = found["bad_map"], found["bad_projection"]
    pair_stored, forbidden, unloadable = (found["pair_stored"], found["forbidden"],
                                          found["unloadable"])
    bad_hits, bad_reports, bad_code = (found["bad_hits"], found["bad_reports"],
                                       found["bad_code"])
    bad_gene_sets, batch_stored = found["bad_gene_sets"], found["batch_stored"]
    bad_keyed, bad_ranks = found["bad_keyed"], found["bad_ranks"]
    stale, null_stage1 = found["stale"], found["null_stage1"]
    bad_preflight = found["bad_preflight"]
    bad_env = (W.check_supplied_lock(env_lock, expect_env_lock_sha256)
               + list(found["bad_env"]))
    bad_cross = W.check_cross_bundle(found["arm_values"])

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
    rep.gate(G_PROJECTION, not bad_projection, "; ".join(bad_projection[:4]))
    rep.gate(G_RECONSTRUCT, not bad_hits, "; ".join(bad_hits[:3]))
    rep.gate(G_RANKS, not bad_ranks, "; ".join(bad_ranks[:3]))
    rep.gate(G_KEYED_PROVENANCE, not bad_keyed, "; ".join(bad_keyed[:3]))
    rep.gate(G_CROSS_BUNDLE, not bad_cross, "; ".join(bad_cross[:3]))
    rep.gate(G_NO_STALE, not stale, "; ".join(stale[:3]))
    rep.gate(G_STAGE1_NONNULL, not null_stage1, "; ".join(null_stage1[:3]))
    rep.gate(G_PREFLIGHT, not bad_preflight, "; ".join(bad_preflight[:3]))
    rep.gate(G_ENV_LOCK, not bad_env, "; ".join(bad_env[:3]))
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

    # ---- 5b. THE PRODUCER INVENTORY + THE INDEPENDENT ADMISSION ENVELOPE ---- #
    # A file cannot testify that some other process made it (``verify_release_envelope``).
    # EVERY LANE'S RELEASE IS ADMITTED BY ITS OWN INDEPENDENT VERIFIER: one generic report
    # cannot say which lane it admitted, and a release missing any lane's admission is not
    # a release. 3 Direct + 6 temporal + 6 pathway = 15 bundles / 300 arms.
    bad_inv, bad_env_adm, bad_binds = [], [], []
    inventories = {}
    n_bundles_of = {lane: len(want[lane]) // (2 * len(programs)) if programs else 0
                    for lane in R.LANES}
    for lane in R.LANES:
        inv, problems = E.check_inventory(
            root, expect_bundles=n_bundles_of[lane],
            expect_arms=len(want[lane]), lane=lane)
        inventories[lane] = inv
        bad_inv += [f"[{lane}] {p}" for p in problems]

        pinned_id = (expect_verifiers.get(lane) or {}).get("verifier_id")
        env, eprob = E.check_external_admission(root, inv, pinned_id, lane=lane)
        binds_msgs = [p for p in eprob
                      if "admission of something else" in p or "binds inventory bytes" in p]
        bad_env_adm += [f"[{lane}] {p}" for p in eprob if p not in binds_msgs]
        bad_binds += [f"[{lane}] {p}" for p in binds_msgs]
        if env is None and not binds_msgs:
            bad_binds.append(f"[{lane}] no external admission envelope to bind")

    rep.gate(G_INVENTORY, not bad_inv, "; ".join(bad_inv[:4]))
    rep.gate(G_EXTERNAL_ADMISSION, not bad_env_adm, "; ".join(bad_env_adm[:3]))
    rep.gate(G_EXTERNAL_BINDS, not bad_binds, "; ".join(bad_binds[:3]))

    bad_inv_arms = []
    for lane in R.LANES:
        bad_inv_arms += W.inventory_matches_arms(inventories[lane],
                                                 found["bound_rankings"])
    rep.gate(G_INVENTORY_ARMS, not bad_inv_arms, "; ".join(bad_inv_arms[:3]))

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

    # THE PRODUCER MAY NOT ADMIT ITS OWN RUN: a correctly-shaped run is not a verified one,
    # and the shape is all the producer can see.
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
    ap.add_argument("--release-inventory-root", required=True,
                    help="the CONTENT-ADDRESSED release root holding the producer inventory "
                         "and the INDEPENDENT external admission envelope. REQUIRED and "
                         "explicit: a guessed path is a path nobody agreed to.")
    ap.add_argument("--env-lock", required=True,
                    help="the COMMITTED Stage-2 environment lock. Its BYTES are hashed and "
                         "compared to what every bundle binds — a named lock proves nothing")
    ap.add_argument("--expect-env-lock-sha256", required=True,
                    help="the INDEPENDENTLY pinned sha256 of the authoritative Stage-2 "
                         "solver lock. The supplied --env-lock must BE that lock: which "
                         "environment the run used is not the operator's to choose")
    ap.add_argument("--dry-run", action="store_true",
                    help="resolve and report the invocation contract WITHOUT reading a "
                         "single bundle. Zero compute; exits 0 iff every required input is "
                         "present and readable.")
    ap.add_argument("--report", default=None, help="write the verdict here (JSON)")
    args = ap.parse_args(argv)

    if args.dry_run:
        doc = I.dry_run(args)
        print(json.dumps(doc, indent=2, sort_keys=True))
        return 0 if doc["ready"] else 1

    try:
        doc = verify(manifest_path=args.manifest, bundles_root=args.bundles_root,
                     release_path=args.release, release_root=args.release_root,
                     expect_release_sha256=args.expect_release_sha256,
                     expect_gene_sets_path=args.expect_gene_sets,
                     expect_verifiers_path=args.expect_verifiers,
                     expected_code_identity_path=args.expected_code_identity,
                     env_lock_path=args.env_lock,
                     expect_env_lock_sha256=args.expect_env_lock_sha256,
                     release_root_dir=args.release_inventory_root)
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
