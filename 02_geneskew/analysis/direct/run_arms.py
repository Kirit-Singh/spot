"""THE ALL-ARM DIRECT PRODUCER: one content-addressed bundle per condition.

Three physical bundles (Rest, Stim8hr, Stim48hr), each carrying every admitted program's two
reusable arms — |admitted| x 2 logical slots apiece. A pair is not an input here and is not
an output: it is a JOIN of two arms, done later, by whoever asks a question.

BUNDLE-SCOPED, NOT PAIR-SCOPED
------------------------------
The request names the LANE and the CONTEXT (the condition) and binds the frozen Stage-1 v3
release; it names NO A and NO B. That is the whole difference. The old runner's identity was
a function of the pair it was asked about, so the same measurement, requested twice for two
pairs, produced two bundles that could not be told apart from two different measurements —
and the arms inside them could never be reused. A bundle whose identity does not mention a
pair can be cited by every pair that needs it.

The admitted program set is DERIVED from the bound release's scorer view (``scorer_view``),
never from a legacy registry and never from a copied count, and the view's hash is bound into
the bundle identity — so a bundle cannot be re-attributed to a different program set later.

WHAT IT WILL NOT EMIT
---------------------
No pair fields. No Pareto. No concordance. No combined/balanced/weighted score. No p, q or
FDR (``inference_status = not_calibrated``). These are not omissions to be filled in later:
a reusable arm that carried a pair-derived ordering would only be reusable by that pair.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
from typing import Any, Optional

from . import (
    arm_bundle,
    arm_inputs,
    arm_support,
    config,
    disposition,
    emit,
    envlock,
    gate,
    guides,
    identity,
    io_data,
    masks,
    preflight,
    scorer_view,
    support_lanes,
)
from . import manifest as mf
from . import projection as proj
from . import run_screen as rs
from . import target_identity as tgt_id
from . import universe as uni

# THE NATIVE FILE SET lives in `arm_artifacts` — "what the bundle ships" is a thing with a
# definition, not a list of string literals inside a build function. Re-exported here because
# `run_arms.MASKS_FILE` is the name W3 and the verifier already reach for.
from .arm_artifacts import (
    BUNDLE_FILE,
    CONTRIB_FILE,
    DONOR_SUPPORT_FILE,
    GUIDE_SUPPORT_FILE,
    INPUTS_FILE,
    MASKS_FILE,
    PROVENANCE_FILE,
    ROWS_FILE,
    TARGET_IDENTITY_FILE,
    UNIVERSE_FILE,
    VERDICT_PENDING,
    VERIFICATION_FILE,
    artifact_manifest,
    verification_placeholder,
)
from .hashing import canonical_json, content_hash, file_sha256, sha256_hex

SCHEMA_REQUEST = "spot.stage02_arm_bundle_request.v1"
SCHEMA_PROVENANCE = "spot.stage02_arm_bundle_provenance.v1"
RUNNER_ID = "spot.stage02.direct.all_arm_runner.v1"
BUNDLE_RUN_ID_LEN = 16


def _raw_of(path: Optional[str]) -> Optional[str]:
    """The raw byte hash of a pinned input, or None when it was not supplied."""
    return file_sha256(path) if path and os.path.exists(path) else None


def request_block(args, ctx: dict[str, Any], view: dict[str, Any]) -> dict[str, Any]:
    """The typed, self-hashed ARM-BUNDLE REQUEST. It names a context; it names no pair."""
    release = ctx["release"]
    body = {
        "schema_version": SCHEMA_REQUEST,
        "lane": ctx["lane"],
        "condition": ctx["cond"],
        # WHAT the admitted set was derived from — the bound release, by hash
        "stage1_release_kind": release.kind,
        "stage1_release_hashes": dict(release.hashes),
        "scorer_view_id": view["view_id"],
        "scorer_view_sha256": view["scorer_view_sha256"],
        "admitted_program_ids": view["admitted_program_ids"],
        "n_expected_arm_slots": arm_bundle.expected_slots(view["admitted_program_ids"]),
        # ...and what it deliberately does NOT name
        "names_a_program_pair": False,
        "pair_selection_is_compatibility_only": True,
    }
    return dict(body, request_sha256=content_hash(body))


def scan(*, ctx: dict[str, Any], args, cond: str, admitted: list[str],
         signature_targets: Optional[set] = None) -> dict[str, Any]:
    """ONE base delta per (program, target) — AND the evidence that produced it.

    The single dense read in the lane. The mask is the SAME mask the within-condition screen
    takes its score under — built per target, once, and reused for every program. A program
    projected under a different mask from its neighbour would not be comparable to it, and
    the arms are meant to be joined.

    The masks, the contributing guides and the released support slots are COLLECTED here
    rather than discarded: every delta in the bundle is a function of those bytes, and a
    bundle that binds only a COUNT of them binds nothing — two different contributor
    manifests with the same number of rows would produce different science under one id.
    """
    release = ctx["release"]
    identities = ctx["identities_by_condition"][cond]
    library, manifest_index = ctx["library"], ctx["manifest_index"]
    universe_ids = ctx["gene_universe"]["gene_ids"]
    splits = ctx["splits"]
    guide_ids, donor_ids = ctx["guide_ids"], ctx["donor_ids"]

    mask_rows: list[dict[str, Any]] = []
    signatures: dict[str, dict[str, float]] = {}
    contrib_rows: list[dict[str, Any]] = []
    guide_rows: list[dict[str, Any]] = []
    donor_rows: list[dict[str, Any]] = []

    main = io_data.load_main(args.de_main, cond)
    meta, gene_index = main["meta"], main["gene_index"]
    targets = [str(t) for t in meta["target_id"]]

    # RESTRICTED to this run's gene universe, exactly as the pair path restricts its axis.
    # A program projected on genes the universe does not hold would be projected on a
    # different measurement from the program beside it — and these arms are meant to be
    # joined with each other.
    universe_ids = ctx["gene_universe"]["gene_ids"]
    panels = {p: uni.restrict([str(g) for g in release.programs[p]["panel_ensembl"]],
                              universe_ids) for p in admitted}
    controls = {p: uni.restrict([str(g) for g in release.programs[p]["control_ensembl"]],
                                universe_ids) for p in admitted}

    out: dict[str, list[dict[str, Any]]] = {p: [] for p in admitted}
    for i, target in enumerate(targets):
        ident = identities[target]
        n_guides = rs._f(meta["n_guides"][i])
        n_cells = rs._f(meta["n_cells_target"][i])

        est = guides.Estimate(
            estimate_type=guides.MAIN, estimate_id="main",
            released_estimate_id=ident.released_estimate_id,
            target_id=target, target_ensembl=ident.target_ensembl,
            condition=cond, n_guides=n_guides, n_cells=n_cells,
            target_id_namespace=ident.target_id_namespace,
            target_symbol=ident.target_symbol,
            released_target_ensembl=ident.released_target_ensembl)
        contrib = guides.resolve(est, library, manifest_index)
        mask = masks.build_estimate_mask(est, contrib,
                                         library.get(ident.target_ensembl))
        mask_set = mask["gene_set"]

        # THE EVIDENCE, KEPT. These are the bytes the deltas below are a function of.
        contrib_rows += guides.contributor_rows(est, contrib)
        mask_rows += masks.mask_rows_for_emit(est, mask, universe_ids, run_id=None)

        # THE TARGET-MASKED SIGNATURE (W18), under the SAME mask the deltas are taken under.
        # Step 0's shared signature matrix and the pathway lane read these; a signature masked
        # differently from the numbers it explains would explain different numbers.
        if (signature_targets is not None and target in signature_targets
                and mask_set is not None):
            row_values = main["log_fc"][i]
            signatures[target] = {
                g: float(row_values[gene_index[g]]) for g in universe_ids
                if g in gene_index and g not in mask_set}

        # SUPPORT: enumerated for accounting, never projected, and carrying no pole — the
        # legacy support rows are keyed on the PAIR's arms, and a bundle that shipped them
        # would have smuggled the pair back in through its evidence files.
        g_contrib, slots = support_lanes.guide_lane(ident, cond, guide_ids)
        contrib_rows += g_contrib
        guide_rows += arm_support.guide_support_rows(target, cond, slots)

        d_contrib, pair_values = support_lanes.donor_lane(ident, cond, donor_ids)
        contrib_rows += d_contrib
        donor_rows += arm_support.donor_support_rows(target, cond, pair_values,
                                                     splits["splits"])

        # BASE QC once per target: a function of no program's outcome, and of no arm's.
        base_state, base_passed, _reasons = disposition.base_qc(
            row_present=True, mask_resolved=mask["resolved"], n_cells=n_cells,
            low_target_gex=rs._b(meta["low_target_gex"][i]),
            ontarget_significant=rs._b(meta["ontarget_significant"][i]),
            n_guides=n_guides,
            target_identity_resolved=ident.ensembl_resolved)

        row = main["log_fc"][i]
        for program_id in admitted:
            d = proj.program_delta(row, panels[program_id], controls[program_id],
                                   gene_index, mask_set,
                                   config.MIN_SURVIVING_PANEL,
                                   config.MIN_SURVIVING_CONTROL)
            out[program_id].append({
                "target_id": target,
                "delta": d["delta"],
                "status": d["status"],
                "n_panel_surviving": d["n_panel_surviving"],
                "n_control_surviving": d["n_control_surviving"],
                "base_state": base_state,
                "base_passed": base_passed,
            })
    return {"base": out, "mask_rows": mask_rows, "contrib_rows": contrib_rows,
            "guide_rows": guide_rows, "donor_rows": donor_rows,
            "signatures": signatures,
            "n_source_targets": len(targets)}


def base_deltas(*, ctx: dict[str, Any], args, cond: str, admitted: list[str],
                signature_targets: Optional[set] = None) -> dict[str, Any]:
    """Compatibility name for `scan` (W18): the pathway lane and Step 0 call this."""
    return scan(ctx=ctx, args=args, cond=cond, admitted=admitted,
                signature_targets=signature_targets)


def build_bundle(args) -> dict[str, Any]:
    """Compute ONE condition's all-arm bundle. Content-addressed; verified before it ships."""
    created_at = _dt.datetime.now(_dt.timezone.utc).isoformat()

    # BUNDLE-SCOPED: a lane and a CONTEXT, and no pair. The pair-selection path is
    # compatibility/join-validation only and may not define a physical bundle's identity.
    ctx = rs.prepare_bundle(args, cond=args.condition)

    # THE SAME release gate the screen and the preflight apply, over the SAME ctx, before a
    # single dense layer is read. An all-arm bundle is not a back door around it.
    verdict = preflight.assess(args, ctx)
    if verdict["verdict"] != preflight.GO:
        detail = "; ".join(f"[{f['check']}] {f['error']}" for f in verdict["failures"])
        raise gate.GateError(
            f"release gate refused this arm bundle; nothing was written. {detail}",
            report=verdict)

    view = scorer_view.view(ctx["release"])
    admitted = view["admitted_program_ids"]
    cond = ctx["cond"]
    request = request_block(args, ctx, view)

    scanned = scan(ctx=ctx, args=args, cond=cond, admitted=admitted)
    base = scanned["base"]
    rows = arm_bundle.build_rows(condition=cond, admitted=admitted,
                                 base_by_program=base)
    arm_bundle.assert_exact_columns(rows)
    doc = arm_bundle.build(condition=cond, view=view, base_by_program=base, rows=rows)
    # The inventory is COMPLETE, UNIQUE and cites ONE scorer view — re-derived from the bound
    # release, before a byte is written. A bundle that shipped 19 arms while declaring 20 was
    # internally hash-consistent and scientifically wrong.
    arm_bundle.assert_complete_inventory(doc)

    # THE BUNDLE'S OWN input manifest — never the pair path's. `stage2_input_manifest` hashes
    # `args.selection`, which both crashed this CLI (no such flag) and made a supposedly
    # pair-independent identity move with a pair the bundle never loaded.
    # ---- THE PER-TARGET IDENTITY / ASSAY ARTIFACT (Stage-3 handoff) ----
    # Hashed BEFORE the run id, from the EXACT bytes. The raw hash of a file cannot normally
    # exist before the id names the directory it goes in — but these bytes are deterministic, so
    # they are serialized once, hashed, bound, and then written unchanged. Nothing is hashed
    # that is not shipped, and nothing is shipped that was not hashed.
    identity_doc = tgt_id.build(
        ctx["identities_by_condition"][cond], condition=cond,
        scored_targets={r["target_id"] for r in rows})
    identity_bytes = (json.dumps(identity_doc, indent=2, sort_keys=True, default=str)
                      + "\n").encode("utf-8")
    identity_binding = tgt_id.binding_block(
        identity_doc, hashlib.sha256(identity_bytes).hexdigest())

    manifest = arm_inputs.bundle_input_manifest(args)
    arm_inputs.assert_no_pair_input(manifest)

    # ONE canonical mask table: the parquet is serialized FROM it and mask_sha256 is taken OF
    # it. The old binding hashed the rows in the order the producer happened to build them
    # while the file shipped them under a different sort — so a verifier reading masks.parquet
    # could not reproduce the hash, and reordering identical rows moved the bundle id.
    canonical_masks = masks.canonical_mask_rows(scanned["mask_rows"])
    mask_sha = masks.mask_content_sha256(scanned["mask_rows"])
    binding = {
        "runner_id": RUNNER_ID,
        "lane": ctx["lane"],
        "condition": cond,
        # the REQUEST — bundle-scoped, and it names no pair
        "arm_bundle_request": request,
        "method": doc["method"],
        "scorer_view_sha256": view["scorer_view_sha256"],
        "stage2_inputs": sorted(
            [{"name": i["name"], "sha256": i["sha256"], "size_bytes": i["size_bytes"]}
             for i in manifest], key=lambda i: i["name"]),
        "gene_universe_sha256": ctx["gene_universe"]["sha256"],
        # ---- THE EVIDENCE EVERY DELTA IS A FUNCTION OF (audit BLOCKER 4) ----
        # The contributor manifest decides which guides contributed; the guides decide the
        # mask; the mask decides the projection. Binding a COUNT of them binds nothing: two
        # different manifests with the same number of rows would produce different science
        # under one identity. So the SEMANTICS are bound (a reordered manifest is the same
        # manifest and must not move the id) and so are the RAW bytes of the pinned upstream
        # artifacts, which genuinely are the evidence.
        # ONE key, both identities. The SEMANTIC block (a reordered manifest is the same
        # manifest and must not move the id) and the RAW bytes that actually arrived. Two
        # sibling keys for one fact can drift apart; one key cannot.
        "contributor_manifest": dict(
            mf.binding_block(ctx["manifest_doc"]),
            raw_sha256=_raw_of(getattr(args, "guide_manifest", None))),
        "source_registry_raw_sha256": _raw_of(getattr(args, "source_registry", None)),
        "target_identity_map": identity.binding_block(
            getattr(args, "target_identity_map", None)),
        "mask_sha256": mask_sha,
        # WHICH recipe produced that hash. A hash whose ordering rule is not named is a number
        # nobody else can recompute, however carefully they read the file.
        "mask_order_rule_id": masks.MASK_ORDER_RULE_ID,
        "n_mask_rows": len(canonical_masks),
        "support_contract": ctx["support_contract"],
        "evidence_domain": rs._domain_block(ctx),
        "release_gate": verdict["release_gate"],
        "code_identity": rs.code_identity_for(
            ctx["lane"], getattr(args, "allow_dirty_tree", False)),
        # THE SOLVER LOCK, VERIFIED against the pin and bound by its FULL sha256 (W18).
        # `runid.env_lock_block` hashed whatever path it was handed and reported
        # "not_supplied" when handed none — it never checked the file WAS the lock, and never
        # refused. Recording a lock beside a run says which environment the producer HAD;
        # binding a VERIFIED one into the run id says which environment the numbers CAME FROM.
        "environment_lock": envlock.block(getattr(args, "env_lock", None)),
        # WHAT each target IS, and what the assay DID to it. Stage 3 joins this to arms.parquet;
        # a bundle that shipped arm VALUES with no bound statement of the namespace would force
        # a consumer to infer it from the shape of the key — the one inference this lane forbids.
        "target_identity": identity_binding,
        "arm_rows_sha256": doc["arm_rows_sha256"],
    }
    full = sha256_hex(canonical_json(binding))
    bundle_run_id = full[:BUNDLE_RUN_ID_LEN]

    out_dir = os.path.join(args.out_root, bundle_run_id)
    os.makedirs(out_dir, exist_ok=True)
    for r in rows:
        r["arm_bundle_run_id"] = bundle_run_id
    for evidence in ("contrib_rows", "guide_rows", "donor_rows"):
        arm_support.stamp(scanned[evidence], bundle_run_id)
    arm_support.stamp(canonical_masks, bundle_run_id)

    emit.write_json(os.path.join(out_dir, BUNDLE_FILE),
                    dict(doc, arm_bundle_run_id=bundle_run_id))
    emit.write_parquet(rows, os.path.join(out_dir, ROWS_FILE),
                       sort_by=["arm_key", "target_id"])

    # THE EVIDENCE SHIPS. Binding the hash of bytes nobody can hold is the same defect as
    # citing a gene-set file that only exists on the producer's disk: a verifier could check
    # the mask hashed to X and have no way to obtain X.
    # sort_by=[] ON PURPOSE: these rows are ALREADY the canonical table, in the one order the
    # bound hash was taken over. Re-sorting here on a partial key — six of the fourteen
    # identity columns — is exactly what let the shipped order drift from the hashed one.
    emit.write_parquet(canonical_masks, os.path.join(out_dir, MASKS_FILE), [])
    # the VERY SAME BYTES that were hashed above — not a re-serialization, which would be a
    # different file that happens to mean the same thing
    with open(os.path.join(out_dir, TARGET_IDENTITY_FILE), "wb") as fh:
        fh.write(identity_bytes)
    emit.write_parquet(scanned["contrib_rows"], os.path.join(out_dir, CONTRIB_FILE),
                       ["estimate_type", "estimate_id", "target_id", "guide_id"])
    emit.write_parquet(scanned["guide_rows"], os.path.join(out_dir, GUIDE_SUPPORT_FILE),
                       ["target_id", "estimate_id", "guide_id"])
    emit.write_parquet(scanned["donor_rows"], os.path.join(out_dir, DONOR_SUPPORT_FILE),
                       ["target_id", "split_id"])
    emit.write_json(os.path.join(out_dir, INPUTS_FILE),
                    {"schema_version": emit.SCHEMA_MANIFEST,
                     "arm_bundle_run_id": bundle_run_id, "files": manifest})
    emit.write_json(os.path.join(out_dir, UNIVERSE_FILE),
                    {"schema_version": "spot.stage02_gene_universe.v1",
                     "arm_bundle_run_id": bundle_run_id, **ctx["gene_universe"]})

    prov = {
        "schema_version": SCHEMA_PROVENANCE,
        "arm_bundle_run_id": bundle_run_id,
        "arm_bundle_run_sha256": full,
        "created_at": created_at,
        "run_binding": binding,
        "n_arm_slots": doc["n_arm_slots"],
        "n_expected_arm_slots": doc["n_expected_arm_slots"],
        "n_arm_rows": doc["n_arm_rows"],
        "n_source_targets": scanned["n_source_targets"],
        "guide_manifest": mf.provenance_block(ctx["manifest_doc"]),
        "mask_sha256": mask_sha,
        "inference_status": config.INFERENCE_STATUS,
        # WHERE the bytes are, RELATIVE to this bundle — never a machine-local path. The
        # same science produced on tcefold and on a laptop must cite the same artifacts.
        "artifacts": artifact_manifest(out_dir),
    }
    emit.write_json(os.path.join(out_dir, PROVENANCE_FILE), prov)

    # THE PRODUCER DOES NOT ADMIT ITSELF. A generator that signs its own homework is not a
    # gate. This is a PLACEHOLDER: an independent verifier reads the files back off disk and
    # replaces it with a real verdict. Until it does, the bundle is not admitted.
    emit.write_json(os.path.join(out_dir, VERIFICATION_FILE),
                    verification_placeholder(bundle_run_id, doc, RUNNER_ID))

    return {
        "arm_bundle_run_id": bundle_run_id,
        "out_dir": out_dir,
        "condition": cond,
        "lane": ctx["lane"],
        "n_admitted_programs": view["n_admitted_programs"],
        "n_arm_slots": doc["n_arm_slots"],
        "n_expected_arm_slots": doc["n_expected_arm_slots"],
        "n_arm_rows": doc["n_arm_rows"],
        "provenance": prov,
        "bundle": doc,
    }


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m direct.run_arms",
        description="Emit ONE condition's all-arm Direct bundle: every admitted program's "
                    "increase and decrease arms, keyed on desired_change. Bundle-scoped: "
                    "it names a context, never an A/B pair.")
    ap.add_argument("--condition", default=None,
                    help="THE CONTEXT this bundle is for (e.g. Rest). A bundle names a "
                         "context, never an A/B pair.")
    # A COMPLETE Direct release is every condition the BOUND release ships — derived from
    # release.selector.conditions, never from a number written down here.
    ap.add_argument("--all-conditions", action="store_true",
                    help="build every condition the bound Stage-1 release ships and bind "
                         "them into one Direct release; refuses a missing, duplicated or "
                         "unknown condition")
    ap.add_argument("--registry", default=None)
    ap.add_argument("--stage1-release", default=None)
    # The v3 release declares its components by REPO-RELATIVE path. They resolve under this
    # explicitly staged root — never guessed from where the release JSON happens to sit.
    ap.add_argument("--stage1-release-root", default=None,
                    help="the staged root that a spot.stage01_v3_release.v1 release's "
                         "component paths resolve under")
    ap.add_argument("--stage1-validation", default=None)
    ap.add_argument("--stage1-gate-spec", default=None)
    ap.add_argument("--de-main", required=True)
    ap.add_argument("--by-guide", default=None)
    ap.add_argument("--by-donors", default=None)
    ap.add_argument("--sgrna", default=None)
    ap.add_argument("--guide-manifest", default=None)
    ap.add_argument("--source-registry", default=None)
    ap.add_argument("--target-identity-map", default=None)
    # CONSUMED, therefore DECLARED. The context builder reads this; the parser used not to
    # define it, so the only entry point a human can invoke died with AttributeError while
    # the in-process tests — which pass a dataclass that declares it — stayed green.
    ap.add_argument("--donor-crosswalk", default=None)
    ap.add_argument("--lane", default=config.LANE_PRODUCTION, choices=list(config.LANES))
    ap.add_argument("--strict-replay", action="store_true")
    ap.add_argument("--strict-replay-source", default=None)
    ap.add_argument("--pseudobulk", default=None)
    ap.add_argument("--env-lock", default=None)
    ap.add_argument("--allow-dirty-tree", action="store_true")
    ap.add_argument("--out-root", required=True,
                    help="bundles are written to <out-root>/<arm_bundle_run_id>/")
    return ap


def main(argv=None) -> dict[str, Any]:
    args = build_parser().parse_args(argv)

    if args.all_conditions:
        # imported here: arm_release drives THIS module's producer, so the dependency runs
        # one way at module level and the other only when the aggregate is asked for
        from . import arm_release
        result = arm_release.build_release(args)
        print(json.dumps({
            "direct_release_run_id": result["direct_release_run_id"],
            "out_dir": result["out_dir"],
            "expected_conditions": result["expected_conditions"],
            "n_physical_bundles": result["n_physical_bundles"],
            "n_logical_arms": result["n_logical_arms"],
            "bundles": [{"condition": b["condition"],
                         "arm_bundle_run_id": b["arm_bundle_run_id"]}
                        for b in result["bundles"]],
            "admitted": False,
            "verdict": VERDICT_PENDING,
        }, indent=2))
        return result

    if not args.condition:
        build_parser().error(
            "one of --condition (one bundle) or --all-conditions (the complete Direct "
            "release, derived from the bound Stage-1 release) is required")

    result = build_bundle(args)
    print(json.dumps({
        "arm_bundle_run_id": result["arm_bundle_run_id"],
        "condition": result["condition"],
        "lane": result["lane"],
        "out_dir": result["out_dir"],
        "n_admitted_programs": result["n_admitted_programs"],
        "n_arm_slots": result["n_arm_slots"],
        "n_expected_arm_slots": result["n_expected_arm_slots"],
        "n_arm_rows": result["n_arm_rows"],
        "pair_fields_emitted": False,
        "pareto_emitted": False,
        "inference_status": config.INFERENCE_STATUS,
    }, indent=2))
    return result


if __name__ == "__main__":
    main()
    sys.exit(0)
