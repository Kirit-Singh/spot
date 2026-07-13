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
from typing import Any

from . import (
    arm_bundle,
    arm_inputs,
    config,
    disposition,
    emit,
    gate,
    guides,
    io_data,
    masks,
    preflight,
    runid,
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

ROWS_FILE = "arms.parquet"
BUNDLE_FILE = "arm_bundle.json"
PROVENANCE_FILE = "arm_bundle_provenance.json"


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


def base_deltas(*, ctx: dict[str, Any], args, cond: str,
                admitted: list[str]) -> dict[str, list[dict[str, Any]]]:
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
    return out


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

    base = base_deltas(ctx=ctx, args=args, cond=cond, admitted=admitted)
    rows = arm_bundle.build_rows(condition=cond, admitted=admitted,
                                 base_by_program=base)
    doc = arm_bundle.build(condition=cond, view=view, base_by_program=base, rows=rows)

    # THE BUNDLE'S OWN input manifest — never the pair path's. `stage2_input_manifest` hashes
    # `args.selection`, which both crashed this CLI (no such flag) and made a supposedly
    # pair-independent identity move with a pair the bundle never loaded.
    manifest = arm_inputs.bundle_input_manifest(args)
    arm_inputs.assert_no_pair_input(manifest)
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
        "evidence_domain": rs._domain_block(ctx),
        "release_gate": verdict["release_gate"],
        "code_identity": rs.code_identity_for(
            ctx["lane"], getattr(args, "allow_dirty_tree", False)),
        "environment_lock": runid.env_lock_block(getattr(args, "env_lock", None)),
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
