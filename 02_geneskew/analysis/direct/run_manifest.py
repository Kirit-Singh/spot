"""THE STAGE-2 AGGREGATE RUN MANIFEST: one artifact binding every reusable ARM of a run.

FROZEN AGAINST ``ROUND4_ADDENDUM.md`` sha256
``c477356278c5b7d2842659f5354792c9db7203ee774f8dd70653921124477a9f``.

Each bundle already carries its own identity, its own provenance and its own independent
admission. What did NOT exist was anything saying WHICH of them belong to the same run, or
whether the run is COMPLETE — and a run that cannot say what completeness means cannot be
released. Counting invocations was not it: three copies of one Direct result counted as
three and passed.

So this binds the ARMS. The topology (``arm_topology``) says which arm slots a complete
run must fill; the admitted program set is RE-DERIVED from the bound v3 generic release /
scorer view; and every bundle's provenance and verification report is LOADED, not assumed.

    logical arm slots  = programs x {increase, decrease} x context
    physical bundles   = one ALL-ARM bundle per context

A bundle that ships one pair's two arms leaves the rest of its slots empty. That is the
whole point of the count.

THIS MODULE PRODUCES NO SCIENCE. It is an index, and it says so. It does not verify
itself: ``verify_run_manifest`` does that, independently and from the same bytes.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Any, Optional

from . import code_digest, config
from .arm_topology import (
    ARM_BINDING,
    BATCH_KEYS,
    BINDING_FIELDS,
    BUNDLE_BINDINGS,
    BUNDLE_FILES,
    DESIRED_CHANGES,
    EXCLUDED_FROM_RELEASE,
    EXCLUSION_RULE_ID,
    LANES,
    PAIR_DERIVED_VIEW_POLICY,
    RETIRED_ENTRY_POINTS,
    RunManifestError,
    expected_bundles,
    expected_slots,
    key_hits,
    load_release,
    pair_derived_hits,
    role_pole_map,
    selection_capacity,
)
from .cli_contracts import CLI_CONTRACTS
from .hashing import content_hash, file_sha256

SCHEMA_VERSION = "spot.stage02_run_manifest.v3_topology_only"

# The producer states the TOPOLOGY. It never states the ADMISSION.
ADMISSION_PENDING = "pending_independent_aggregate_admission"
ADMISSION_RULE_ID = "spot.stage02.run_manifest.admission.independent_only.v1"

# ---- NAMED REFUSAL GATES. A partial or duplicated topology dies at the ONE that
# names its violation. Discovery must resolve EXACTLY 3 Direct + 6 temporal + 6
# pathway PHYSICAL bundles; a 2/6/6 or a repeated bundle is refused by DEFAULT, and
# --allow-partial is the ONLY (explicit, never-admissible) escape.
GATE_BUNDLE_COUNT = (
    "each_lane_ships_EXACTLY_its_expected_physical_bundle_count"
    "_3_direct_6_temporal_6_pathway")
GATE_NO_DUPLICATE_BUNDLE = (
    "no_bundle_id_appears_more_than_once_a_repeated_invocation_is_not_two")
GATE_TOPOLOGY_COMPLETE = (
    "every_expected_arm_slot_is_filled_exactly_once_by_a_distinct_bundle")
MANIFEST_ID = "spot.stage02.run_manifest.v2"
FROZEN_ADDENDUM_SHA256 = (
    "c477356278c5b7d2842659f5354792c9db7203ee774f8dd70653921124477a9f")

__all__ = ["build", "bind_bundle", "load_release", "RunManifestError", "main"]


def _load(path: str, what: str) -> dict[str, Any]:
    if not os.path.exists(path):
        raise RunManifestError(
            f"bundle is missing its {what} ({os.path.basename(path)}); an arm nobody can "
            "trace and nobody independently admitted is not evidence")
    try:
        with open(path) as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise RunManifestError(
            f"bundle {what} ({os.path.basename(path)}) is not readable JSON: {exc}. "
            "Arbitrary bytes under an expected filename are not an artifact") from exc


def _bind_artifact(out_dir: str, binding: Any, what: str) -> dict[str, Any]:
    """Resolve ONE bound on-disk artifact and prove its bytes.

    The pathway audit: nothing bound the ranking or the membership list, so
    ``n_hits_in_ranking`` — the number that decides whether an arm is headline-rankable —
    could not be reconstructed by anybody and was, in the end, taken on trust. Every count
    now has its bytes bound: a path INSIDE the bundle, a raw hash and a canonical hash.
    """
    if not isinstance(binding, dict) or any(f not in binding for f in BINDING_FIELDS):
        raise RunManifestError(
            f"bundle binding {what!r} must declare {list(BINDING_FIELDS)}; a count whose "
            "source cannot be opened is a count nobody can check")
    rel = str(binding["path"])
    if os.path.isabs(rel) or ".." in rel.split("/"):
        raise RunManifestError(
            f"bundle binding {what!r} path {rel!r} must be bundle-relative; an artifact "
            "outside the bundle can be swapped without changing the bundle")
    path = os.path.join(out_dir, rel)
    if not os.path.exists(path):
        raise RunManifestError(
            f"bundle binding {what!r} names {rel!r}, which is not in the bundle")
    raw = file_sha256(path)
    if raw != binding["raw_sha256"]:
        raise RunManifestError(
            f"bundle binding {what!r}: {rel!r} hashes to {raw[:16]}, but the bundle "
            f"bound {str(binding['raw_sha256'])[:16]}")
    doc = _load(path, f"bound artifact {rel}")
    canon = content_hash(doc)
    if canon != binding["canonical_sha256"]:
        raise RunManifestError(
            f"bundle binding {what!r}: {rel!r} canonical content hashes to {canon[:16]}, "
            f"but the bundle bound {str(binding['canonical_sha256'])[:16]}")
    return {"path": rel, "raw_sha256": raw, "canonical_sha256": canon}


def bind_bundle(out_dir: str) -> dict[str, Any]:
    """Bind ONE all-arm bundle: its context, its arms, its bindings, its admission."""
    bundle = _load(os.path.join(out_dir, "arm_bundle.json"), "arm inventory")

    lane = bundle.get("lane")
    if lane not in LANES:
        raise RunManifestError(
            f"bundle declares lane {lane!r}; expected one of {list(LANES)}")
    names = BUNDLE_FILES[lane]

    # A reusable arm may not carry a pair's ordering. REFUSED, not filtered: a bundle that
    # stored one was built against a pair, and dropping the field quietly would hide that.
    stored = pair_derived_hits(bundle)
    if stored:
        raise RunManifestError(
            f"{lane} bundle stores pair-derived ordering(s) {stored[:5]} in its arm "
            "inventory. Pareto tiers and concordance labels are JOIN-TIME display only: "
            "an arm is pair-agnostic, and a tier baked into it would travel into every "
            "future join that reuses the arm")

    # Nor may it carry BATCH COMMENTARY. The reusable temporal chain omits it by owner
    # rule: the DiD estimand is population-level, the arm key already carries the ordered
    # pair, and a batch field baked into an arm is commentary travelling into every join
    # that reuses it.
    batch = key_hits(bundle, BATCH_KEYS)
    if batch:
        raise RunManifestError(
            f"{lane} bundle carries batch commentary {batch[:5]} in its arm inventory; "
            "batch stays out of the reusable temporal chain")

    prov = _load(os.path.join(out_dir, names["provenance"]), "provenance")
    # Temporal ships a PREFLIGHT (the producer's own self-check); the other lanes still
    # ship a per-bundle report. Neither is an admission: that is the root envelope.
    report_name = names.get("verification") or names.get("preflight")
    report = _load(os.path.join(out_dir, report_name),
                   "verification report" if names.get("verification") else "preflight")

    files: dict[str, str] = {}
    for base, _dirs, filenames in os.walk(out_dir):
        for fn in filenames:
            path = os.path.join(base, fn)
            files[os.path.relpath(path, out_dir).replace(os.sep, "/")] = \
                file_sha256(path)
    for required in names.values():
        if required not in files:
            raise RunManifestError(
                f"{lane} bundle is missing {required!r}; a manifest that omitted a "
                "missing artifact would certify an incomplete run as complete")

    # ---- the BYTES every count is derived from ---- #
    bindings = {what: _bind_artifact(out_dir, (bundle.get("bindings") or {}).get(what),
                                     what)
                for what in BUNDLE_BINDINGS[lane]}
    arms = bundle.get("arms") or []
    for arm in arms:
        key = str(arm.get("arm_key"))
        bindings[f"{key}::{ARM_BINDING}"] = _bind_artifact(
            out_dir, arm.get(ARM_BINDING), f"{key} {ARM_BINDING}")

    return {
        "lane": lane,
        "bundle_id": str(bundle.get("bundle_id")),
        "out_dir": os.path.basename(out_dir.rstrip(os.sep)),
        "context": bundle.get("context") or {},
        "arm_keys": sorted(str(a.get("arm_key")) for a in arms),
        "n_arms": len(arms),
        "stage1_v3_release": bundle.get("stage1_v3_release") or {},
        "gene_sets": bundle.get("gene_sets"),
        "convergence": bundle.get("convergence"),
        "bound_artifacts": bindings,
        # WHAT the bundle stood on, as the bundle itself recorded it. The verifier
        # re-derives every one of these from the shipped bytes rather than reading them.
        "code_identity": (prov.get("run_binding") or {}).get("code_identity") or {},
        "selection_release": (
            (prov.get("run_binding") or {}).get("selection_release") or {}),
        # W5's native Stage-1 binding: HOW the program axis was derived. The verifier
        # re-derives it against the release rather than reading the bundle's own count.
        "admitted_programs": (prov.get("program_admission") or {}).get("programs"),
        "program_admission": prov.get("program_admission") or {},
        "stage2_inputs": (prov.get("run_binding") or {}).get("stage2_inputs") or [],
        "verification_verdict": report.get("verdict"),
        "preflight_is_not_an_admission": bool(names.get("preflight")),
        "files": files,
        "artifact_sha256": content_hash(files),
    }


def build(*, bundles: list[dict[str, Any]], out_path: str, release: dict[str, Any],
          allow_partial: bool = False, lane_admissions: Optional[dict] = None,
          code_identity: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """The aggregate manifest over every ARM of one Stage-2 run.

    The programs, the conditions and the gene-set sources ALL come from the bound
    authoritative Stage-1 v3 release. There is no separate --conditions, and the temporal
    batch policy is not an authority here: the condition universe is
    ``release.selector.conditions``.
    """
    conditions, sources = release["conditions"], release["gene_set_sources"]
    slots = expected_slots(release["programs"], conditions, sources)
    want_bundles = expected_bundles(conditions, sources)

    filled: dict[str, list[str]] = {lane: [] for lane in LANES}
    for b in bundles:
        filled[b["lane"]] += b["arm_keys"]

    per_lane, topology_complete = {}, True
    for lane in LANES:
        want, got = set(slots[lane]), filled[lane]
        missing = sorted(want - set(got))
        unexpected = sorted(set(got) - want)
        duplicated = sorted({k for k in got if got.count(k) > 1})
        ok = not missing and not unexpected and not duplicated
        topology_complete = topology_complete and ok
        per_lane[lane] = {
            "n_expected_slots": len(want),
            "n_filled_slots": len(set(got) & want),
            "n_bundles_expected": len(want_bundles[lane]),
            "n_bundles_present": sum(1 for b in bundles if b["lane"] == lane),
            "missing_slots": missing,
            "unexpected_slots": unexpected,
            "duplicated_slots": duplicated,
            "lane_complete": ok,
        }

    ids = [b["bundle_id"] for b in bundles]
    dupe_ids = sorted({i for i in ids if ids.count(i) > 1})
    if dupe_ids:
        topology_complete = False

    # PHYSICAL BUNDLE COUNT, per lane. Discovery must resolve EXACTLY 3 Direct + 6
    # temporal + 6 pathway physical bundles; a 2/6/6 is a short run wearing a complete
    # run's name.
    bundle_count_mismatch = {
        lane: (per_lane[lane]["n_bundles_present"],
               per_lane[lane]["n_bundles_expected"])
        for lane in LANES
        if per_lane[lane]["n_bundles_present"]
        != per_lane[lane]["n_bundles_expected"]}

    # REFUSED BY DEFAULT at the gate that names the violation. --allow-partial is the
    # only escape, and it emits an incomplete manifest that is NEVER release-admissible.
    if not allow_partial and (dupe_ids or bundle_count_mismatch
                              or not topology_complete):
        failed = []
        if bundle_count_mismatch:
            failed.append(
                f"[{GATE_BUNDLE_COUNT}] physical bundle counts (present, expected) "
                f"{bundle_count_mismatch}")
        if dupe_ids:
            failed.append(
                f"[{GATE_NO_DUPLICATE_BUNDLE}] bundle id(s) {dupe_ids} appear more than "
                "once; a repeated result cannot stand in for a missing one")
        if not topology_complete:
            failed.append(
                f"[{GATE_TOPOLOGY_COMPLETE}] lane slot completeness "
                f"{ {lane: per_lane[lane]['lane_complete'] for lane in LANES} }")
        raise RunManifestError(
            "this run's TOPOLOGY is incomplete: " + "; ".join(failed) + ". It MAY be "
            "manifested — pass --allow-partial — but it is never silently called "
            "complete. (A COMPLETE topology is still not an admission: see 'admission'.)")

    doc: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "manifest_id": MANIFEST_ID,
        "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        # THIS IS AN INDEX. It produces no science and it says so.
        "produces_scientific_values": False,
        "binds_arm_outputs": True,
        "frozen_topology_addendum_sha256": FROZEN_ADDENDUM_SHA256,
        "code_identity": code_identity or code_digest.run_binding(),
        "stage1_v3_release": release,
        # ORDER PRESERVED, as the release states it: a reordered condition list is a
        # different release, and the pinned release hash is what says so.
        "conditions": list(conditions),
        "gene_set_sources": list(sources),
        "condition_universe_source": release["condition_universe_source"],
        "temporal_estimand": {
            "estimand_level": "population",
            "is_per_cell_fate": False,
            "is_lineage_traced": False,
            "batch_commentary_in_reusable_bundles": False,
        },
        "desired_change_vocabulary": list(DESIRED_CHANGES),
        "desired_change_by_role_and_pole": role_pole_map(),
        "arm_key_rule": (
            "lane|program_id|desired_change|context — the pole direction and the role are "
            "PROVENANCE on the arm, never its identity"),
        "n_expected_arm_slots": sum(len(slots[lane]) for lane in LANES),
        "n_bound_arm_slots": sum(len(b["arm_keys"]) for b in bundles),
        "n_expected_bundles": sum(len(v) for v in want_bundles.values()),
        "n_bundles": len(bundles),
        "expected_bundles": want_bundles,
        "per_lane": per_lane,
        "duplicate_bundle_ids": dupe_ids,
        "selection_capacity": selection_capacity(
            release["n_programs"], len(conditions)),
        "cli_invocation_contracts": CLI_CONTRACTS,
        # WHAT THE RELEASE IS NOT. Named, so a scheduler cannot discover a retired lane and
        # a code digest cannot sweep in scratch that no result depends on.
        "release_scope": {
            "retired_entry_points": list(RETIRED_ENTRY_POINTS),
            "excluded_from_release": list(EXCLUDED_FROM_RELEASE),
            "rule_id": EXCLUSION_RULE_ID,
        },
        # THE PINNED LANE VERIFIERS (W7 consumes these).
        "pinned_lane_verifiers": {
            "temporal": {"verifier_id":
                         "spot.stage02.temporal.arm.independent_verifier.v1",
                         "commit": "99eaa81"},
            "direct": {"verifier_id": "spot.stage02.direct.release.verifier.v1"},
        },
        "combined_objective": None,
        "combined_objective_permitted": config.COMBINED_OBJECTIVE_PERMITTED,
        "cross_arm_score_or_order": None,
        "pair_derived_views": PAIR_DERIVED_VIEW_POLICY,
        "emits_p_q_or_fdr": False,
        "upstream_significance_gate": config.UPSTREAM_SIGNIFICANCE_GATE,
        # ---- TOPOLOGY ONLY. THE PRODUCER DOES NOT ADMIT ITS OWN RUN. ---- #
        # This says every expected arm slot is filled exactly once by a distinct bundle.
        # It says NOTHING about whether those bundles were independently verified, whether
        # their lane reports are typed admissions from the pinned verifiers, or whether
        # they bind one selection. A run can be perfectly shaped and still be nonsense.
        "topology_complete": topology_complete,
        "topology_complete_is_an_admission": False,
        # WHAT EACH LANE'S OWN VERIFIER SAID, verbatim, beside the aggregate's disposition.
        # Bound into the manifest's content hash: a native verdict that was quietly
        # rewritten, or a disposition that does not follow from it, changes the manifest.
        "lane_admissions": lane_admissions or {},
        "lane_admission_mapping_rule_id":
            "spot.stage02.run_manifest.lane_admission_map.v1",
        "lane_verdicts_are_transliterated": False,
        # ---- RELEASE ADMISSION IS NOT THE PRODUCER'S TO GRANT ---- #
        # It used to be set from the topology alone, so a run whose lane reports were bare
        # verdict strings, or which bound inconsistent selections, was stamped
        # release_admissible=true HERE and only refused later by the external verifier. A
        # generator that admits its own output is the exact failure this lane exists to
        # close, so it no longer has an opinion: admission is granted, if at all, by the
        # SEPARATE independent aggregate admission report (verify_run_manifest).
        "release_admissible": None,
        "admission": {
            "status": ADMISSION_PENDING,
            "granted_by": None,
            "rule_id": ADMISSION_RULE_ID,
            "producer_may_declare_admission": False,
            "granted_only_by": "spot.stage02.run_manifest.verifier.v1",
        },
        "bundles": sorted(bundles, key=lambda b: (b["lane"], b["bundle_id"])),
    }
    # The self-hash is over the manifest's CONTENT, excluding the timestamp and itself.
    # A caller-supplied value is accepted nowhere in this lane.
    doc["manifest_sha256"] = content_hash(
        {k: v for k, v in doc.items() if k != "created_at"})
    with open(out_path, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    doc["path"] = out_path
    return doc


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="Bind every reusable ARM of one Stage-2 run into a run manifest")
    ap.add_argument("--direct", nargs="*", default=[],
                    help="direct all-arm bundle directories (one per condition)")
    ap.add_argument("--temporal", nargs="*", default=[],
                    help="temporal all-arm bundles (one per ordered condition pair)")
    ap.add_argument("--pathway", nargs="*", default=[],
                    help="pathway all-arm bundles (condition x gene-set source)")
    ap.add_argument("--release", required=True,
                    help="the authoritative Stage-1 v3 release: the ONLY source of the "
                         "admitted programs, the conditions and the pathway sources. NOT "
                         "the legacy program registry, and NOT a batch policy.")
    ap.add_argument("--release-root", required=True,
                    help="the directory the release is STAGED in; component paths resolve "
                         "against it, never against a machine default")
    ap.add_argument("--allow-partial", action="store_true",
                    help="manifest a partial run: it is flagged complete=false and is "
                         "never release-admissible")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    release = load_release(args.release, args.release_root)
    bundles = [bind_bundle(d) for d in (args.direct + args.temporal + args.pathway)]
    doc = build(bundles=bundles, out_path=args.out, release=release,
                allow_partial=args.allow_partial)
    print(json.dumps({k: v for k, v in doc.items() if k != "bundles"},
                     indent=2, sort_keys=True, default=str))
    return 0 if doc["topology_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
