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
import json
import os
import sys
from typing import Any, Optional

from . import (
    arm_bundle,
    config,
    disposition,
    emit,
    envlock,
    gate,
    guides,
    io_data,
    masks,
    preflight,
    scorer_view,
)
from . import projection as proj
from . import run_screen as rs
from . import universe as uni
from .hashing import canonical_json, content_hash, sha256_hex

SCHEMA_REQUEST = "spot.stage02_arm_bundle_request.v1"
SCHEMA_PROVENANCE = "spot.stage02_arm_bundle_provenance.v1"
RUNNER_ID = "spot.stage02.direct.all_arm_runner.v1"
BUNDLE_RUN_ID_LEN = 16

# THE PHYSICAL CONTRACT (owner, pre-integration). These names are what the independent
# verifier (W10) and the aggregate manifest (W3) read. They are emitted NATIVELY — there is
# no copy and no rename step, because a shim means the bytes that ship are not the bytes the
# producer wrote, and the two can drift.
ROWS_FILE = "arms.parquet"
MASKS_FILE = "masks.parquet"
BUNDLE_FILE = "arm_bundle.json"
PROVENANCE_FILE = "provenance.json"
VERIFICATION_FILE = "verification.json"


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


def base_deltas(*, ctx: dict[str, Any], args, cond: str, admitted: list[str],
                signature_targets: Optional[set] = None) -> dict[str, Any]:
    """ONE base delta per (program, target). The single dense read in the lane.

    The mask is the SAME mask the within-condition screen takes its score under — built per
    target, once, and reused for every program. A program projected under a different mask
    from its neighbour would not be comparable to it, and the arms are meant to be joined.
    """
    release = ctx["release"]
    identities = ctx["identities_by_condition"][cond]
    library, manifest_index = ctx["library"], ctx["manifest_index"]

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
    signatures: dict[str, dict[str, float]] = {}
    mask_rows: list[dict[str, Any]] = []
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
        mask_rows += masks.mask_rows_for_emit(est, mask, universe_ids, run_id=None)

        # THE TARGET-MASKED SIGNATURE, under the SAME mask the deltas are taken under. A
        # signature masked differently from the numbers it explains would explain different
        # numbers.
        if (signature_targets is not None and target in signature_targets
                and mask_set is not None):
            row_values = main["log_fc"][i]
            signatures[target] = {
                g: float(row_values[gene_index[g]]) for g in universe_ids
                if g in gene_index and g not in mask_set}

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
    return {"base": out, "signatures": signatures, "mask_rows": mask_rows}


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

    scan = base_deltas(ctx=ctx, args=args, cond=cond, admitted=admitted)
    base = scan["base"]
    rows = arm_bundle.build_rows(condition=cond, admitted=admitted,
                                 base_by_program=base)
    doc = arm_bundle.build(condition=cond, view=view, base_by_program=base, rows=rows)

    # THE REUSABLE-BUNDLE INPUTS. The A/B selection is NOT one of them (W10): binding it
    # gave byte-identical bundles different ids whenever a pair the bundle neither contains
    # nor uses had changed, and an arm keyed on the question that happened to be asked first
    # is not reusable.
    manifest = rs.bundle_input_manifest(args)
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
        # EVERY delta depends on these bytes: the contributor manifest decides which guides
        # contributed, which decides the mask, which decides the projection. Binding a COUNT
        # of them binds nothing — two different manifests with the same number of rows would
        # produce different science under the same id (W10).
        "contributor_manifest": rs.contributor_manifest_identity(args, ctx),
        "mask_sha256": emit.mask_content_sha256(scan["mask_rows"]),
        "n_mask_rows": len(scan["mask_rows"]),
        "evidence_domain": rs._domain_block(ctx),
        "release_gate": verdict["release_gate"],
        "code_identity": rs.code_identity_for(
            ctx["lane"], getattr(args, "allow_dirty_tree", False)),
        # THE SOLVER LOCK, VERIFIED against the pin and bound by its FULL sha256. Recording it
        # beside the run says which environment the producer HAD; binding it INTO the run id
        # says which environment the numbers CAME FROM. Only the second survives a swap.
        "environment_lock": envlock.block(getattr(args, "env_lock", None)),
        "arm_rows_sha256": doc["arm_rows_sha256"],
    }
    full = sha256_hex(canonical_json(binding))
    bundle_run_id = full[:BUNDLE_RUN_ID_LEN]

    out_dir = os.path.join(args.out_root, bundle_run_id)
    os.makedirs(out_dir, exist_ok=True)
    for r in rows:
        r["arm_bundle_run_id"] = bundle_run_id

    emit.write_json(os.path.join(out_dir, BUNDLE_FILE),
                    dict(doc, arm_bundle_run_id=bundle_run_id))
    emit.write_parquet(rows, os.path.join(out_dir, ROWS_FILE),
                       sort_by=["arm_key", "target_id"])
    # The MASK ARTIFACT ships too. Binding the hash of bytes nobody can hold is the same
    # defect as naming a gene-set file that lives on the producer's disk: a verifier could
    # check the mask hashed to X and had no way to obtain X.
    emit.write_parquet(scan["mask_rows"], os.path.join(out_dir, MASKS_FILE),
                       ["estimate_type", "estimate_id", "target_id",
                        "masked_gene_ensembl", "mask_reason", "guide_id"])

    prov = {
        "schema_version": SCHEMA_PROVENANCE,
        "arm_bundle_run_id": bundle_run_id,
        "arm_bundle_run_sha256": full,
        "created_at": created_at,
        "run_binding": binding,
        "n_arm_slots": doc["n_arm_slots"],
        "n_expected_arm_slots": doc["n_expected_arm_slots"],
        "n_arm_rows": doc["n_arm_rows"],
        "inference_status": config.INFERENCE_STATUS,
    }
    emit.write_json(os.path.join(out_dir, PROVENANCE_FILE), prov)

    # THE VERIFICATION SLOT — fail-closed, and NOT self-admission.
    #
    # A producer may not admit its own output: the independent Direct verifier (W10) reads
    # the SHIPPED bytes at these exact paths and decides. So the artifact ships with an
    # explicit NOT-YET-ADMITTED verdict rather than a clean bill of health it wrote itself.
    # An artifact with no verification file at all would be indistinguishable from one whose
    # verifier had not run, and a downstream reader would have to guess which.
    emit.write_json(os.path.join(out_dir, VERIFICATION_FILE), {
        "schema_version": "spot.stage02_direct_arm_verification.v1",
        "arm_bundle_run_id": bundle_run_id,
        "arm_bundle_run_sha256": full,
        "generator_is_not_verifier": True,
        "fail_closed": True,
        "verifier_id": None,
        "verdict": "pending_independent_verification",
        "admitted": False,
        "verified_paths": [BUNDLE_FILE, PROVENANCE_FILE, ROWS_FILE, MASKS_FILE],
        "arm_rows_sha256": doc["arm_rows_sha256"],
        "n_expected_arm_slots": doc["n_expected_arm_slots"],
        "n_arm_slots": doc["n_arm_slots"],
    })

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
    ap.add_argument("--condition", required=True,
                    help="THE CONTEXT this bundle is for (e.g. Rest). A bundle names a "
                         "context, never an A/B pair.")
    ap.add_argument("--registry", default=None)
    ap.add_argument("--stage1-release", default=None)
    ap.add_argument("--stage1-validation", default=None)
    ap.add_argument("--stage1-gate-spec", default=None)
    ap.add_argument("--de-main", required=True)
    ap.add_argument("--by-guide", default=None)
    ap.add_argument("--by-donors", default=None)
    ap.add_argument("--sgrna", default=None)
    ap.add_argument("--guide-manifest", default=None)
    ap.add_argument("--source-registry", default=None)
    ap.add_argument("--target-identity-map", default=None)
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
