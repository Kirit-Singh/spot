"""The P2S v2 SECONDARY runner: support for ONE reusable Direct arm (and its sibling).

    python -m p2s_arms.run_p2s_arms \
        --direct-bundle  <the W10-ADMITTED Direct bundle dir for that condition> \
        --w10-report     <DIRECT_BUNDLE_ADMISSION_<condition>.json> \
        --env-lock       analysis/stage02_solver_lock.txt \
        --stage1-release <the bound v3 release> \
        --arm-key 'direct|treg_like|increase|Stim48hr' \
        --cells <prepared npz> --effects <parquet> --masks <parquet> --eligible <parquet> \
        --out-root <outside every tracked tree>

IT RUNS ONLY FROM A REAL, W10-ADMITTED DIRECT ARM
-------------------------------------------------
The four bindings above are REQUIRED. "Sequencing alone is not a binding": a wrapper can run
this lane after Direct and W10 and still have bound nothing, because a producer that does not
ACCEPT the bundle and the report cannot be said to have run from them.

Exit 0 = support emitted. Exit 2 = a NAMED refusal, with a TYPED DEFERRED DISPOSITION written
to ``p2s_deferred_disposition.json``. Never exit 1, which is a crash: a scheduler has to be
able to tell "P2S declined this arm, for this reason" from "P2S broke".

It writes ONLY into its own content-addressed run directory. It never writes into Direct's
output, never imports into Direct, and changes no byte under ``analysis/direct/`` — which is
what makes the byte-identity invariant structural rather than a promise.

THE GRID
--------
Both arms of the program come from ONE fit per (donor scope, effect layer, model config):

    all_donor  x  {zscore, log_fc}  x  {pca_off, pca_on_50}     = 4 fits
    lodo_D*    x  {zscore}          x  {pca_off}                = 1 fit per donor

The LODO fits OVERLAP — they share most of their cells — and are never called independent
replicates. They measure whether a coefficient survives dropping a donor, which is a
different and much weaker statement than replication.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from typing import Any, Optional

import numpy as np
from direct import runid
from direct.hashing import content_hash

from . import (
    armfit,
    binding,
    config,
    emit,
    io_data,
    model,
    pmatrix,
    signature,
    stability,
    universe,
    upstream,
)
from . import (
    disposition as D,
)

ALL_DONOR = "all_donor"
LODO_PREFIX = "lodo_"

# The ONLY lane in which a stand-in model may run. See ``execute``.
LANE_SYNTHETIC = "synthetic"


def scopes_for(donors: np.ndarray) -> list[tuple[str, Optional[str]]]:
    """``all_donor`` plus one leave-one-donor-out scope per donor."""
    uniq = sorted({str(d) for d in donors})
    return [(ALL_DONOR, None)] + [(f"{LODO_PREFIX}{d}", d) for d in uniq]


def grid(scope: str) -> list[tuple[str, config.ModelConfig]]:
    """Which (layer, model config) pairs run in a scope. LODO runs the author layer only."""
    if scope == ALL_DONOR:
        return [(layer, cfg) for layer in config.EFFECT_LAYERS for cfg in config.CONFIGS]
    return [(config.AUTHOR_LAYER, config.CONFIGS[0])]


def run_grid(*, program_id: str, condition: str, cells: dict[str, Any],
             universe_gene_ids: list[str], effects: dict[str, Any],
             eligible_targets: list[str], mask_by_target: dict[str, set],
             fit=None, seed: int = config.RANDOM_STATE) -> dict[str, Any]:
    """Every fit for one program. Both arms come out of each, as an exact sign transform."""
    scores = cells["scores"]
    if program_id not in scores:
        raise io_data.InputError(
            "program_score_absent",
            f"the prepared cell matrix carries no Stage-1 score for {program_id!r}; scores "
            "are read by barcode and never recomputed")
    if config.ACTIVATION_PROGRAM_ID not in scores:
        raise io_data.InputError(
            "activation_score_absent",
            f"the activation covariate {config.ACTIVATION_PROGRAM_ID!r} has no score in the "
            "prepared cell matrix, so the confound it exists to absorb cannot be adjusted "
            "for")

    donors = cells["donors"]
    expr_all = cells["expr"]
    col_of = {g: i for i, g in enumerate(cells["gene_ids"])}
    missing = [g for g in universe_gene_ids if g not in col_of]
    if missing:
        raise io_data.InputError(
            "universe_gene_absent_from_cells",
            f"{len(missing)} readout gene(s) are not in the cell matrix (e.g. {missing[:3]})")
    take = np.asarray([col_of[g] for g in universe_gene_ids], dtype=int)

    coef_rows: list[dict[str, Any]] = []
    recon_rows: list[dict[str, Any]] = []
    signatures: dict[str, dict[str, Any]] = {}

    for scope, held_out in scopes_for(donors):
        keep = np.ones(len(donors), dtype=bool) if held_out is None \
            else (donors != held_out)

        z_program = signature.within_donor_z(scores[program_id][keep], donors[keep])
        z_act = signature.within_donor_z(
            scores[config.ACTIVATION_PROGRAM_ID][keep], donors[keep])

        sig = signature.base_signature(
            z_program=z_program, activation=z_act, donors=donors[keep],
            expr=expr_all[np.ix_(keep, take)])
        signatures[scope] = {
            "n_units": sig["n_units"], "rank": sig["rank"],
            "design_columns": sig["design_columns"],
            "signature_sha256": content_hash(
                [round(float(v), 6) for v in sig["signature"]]),
        }

        for layer, cfg in grid(scope):
            x, _coverage = pmatrix.build_masked_x(
                effect_by_target=effects["by_layer"][layer],
                effect_gene_ids=effects["gene_ids"],
                universe_gene_ids=universe_gene_ids,
                target_order=eligible_targets,
                mask_by_target=mask_by_target)

            got = armfit.fit_program(
                program_id=program_id, condition=condition,
                base_signature=sig["signature"], x=x, cfg=cfg, layer=layer, scope=scope,
                fit=fit, seed=seed)
            coef_rows += got["coefficients"]
            recon_rows += got["reconstruction"]

    return {"coefficients": coef_rows, "reconstruction": recon_rows,
            "signatures": signatures}


def execute(*, bound: dict[str, Any], release, view: dict[str, Any],
            paths: dict[str, str], up: dict[str, Any], out_root: str,
            lane: str = "production", seed: int = config.RANDOM_STATE,
            env_lock: Optional[str] = None, argv: Optional[list[str]] = None,
            derived_from: Optional[dict[str, Any]] = None,
            fit=None) -> dict[str, Any]:
    """The pipeline AFTER binding: fit, stabilise, emit. Pure of argparse.

    ``fit`` is injectable so the whole producer can be driven end to end without the
    upstream package — the tests exercise THIS function, not a re-implementation of it.
    It is REFUSED outside the synthetic lane (see below).
    """
    if fit is not None and lane != LANE_SYNTHETIC:
        raise model.ModelError(
            "stand_in_model_outside_the_synthetic_lane",
            f"a stand-in fit was supplied in the {lane!r} lane. A stand-in is a DIFFERENT "
            "MODEL producing numbers under this lane's name and under the pinned model's "
            f"provenance, so it may run only in the {LANE_SYNTHETIC!r} lane. Everywhere "
            "else the pinned upstream model is not optional")

    created_at = _dt.datetime.now(_dt.timezone.utc).isoformat()
    ref = bound["arm"]

    cells = io_data.load_cells(paths["cells"])
    effects = io_data.load_effects(paths["effects"])
    masks = io_data.load_masks(paths["masks"])
    elig = io_data.load_eligible(paths["eligible"])

    excluded = universe.panel_and_control(
        release.programs,
        list(view["admitted_program_ids"]) + [config.ACTIVATION_PROGRAM_ID])
    uni = universe.build(effect_gene_ids=effects["gene_ids"],
                         excluded_program_genes=excluded,
                         target_gene_ids=elig["target_gene_ids"])
    universe.assert_clean(uni, excluded)

    got = run_grid(
        program_id=ref.program_id, condition=ref.condition, cells=cells,
        universe_gene_ids=uni["gene_ids"], effects=effects,
        eligible_targets=elig["targets"],
        mask_by_target=pmatrix.mask_sets(masks["rows"]), fit=fit, seed=seed)

    support_rows = stability.compute(got["coefficients"])

    doc = emit.support_document(
        bound=bound, support_rows=support_rows, coef_rows=got["coefficients"],
        recon_rows=got["reconstruction"], upstream=up, universe=uni)

    run_binding = {
        "runner_id": config.RUNNER_ID,
        "lane": lane,
        "lane_role": config.LANE_ROLE,
        "arm_key": ref.arm_key,
        "method": doc["method"],
        "upstream_software": up,
        "gene_universe_sha256": uni["gene_universe_sha256"],
        "stage2_inputs": sorted(
            [{"name": name, "sha256": obj["sha256"]}
             for name, obj in (("cells", cells), ("effects", effects),
                               ("masks", masks), ("eligible", elig))],
            key=lambda i: i["name"]),
        "environment_lock": runid.env_lock_block(env_lock),
        "support_rows_sha256": doc["support_rows_sha256"],
        "coefficient_rows_sha256": doc["coefficient_rows_sha256"],
        "seed": seed,
    }
    run_id, run_sha = emit.run_id_for(run_binding)

    prov = {
        "schema_version": config.SCHEMA_PROVENANCE,
        "p2s_run_id": run_id,
        "p2s_run_sha256": run_sha,
        "created_at": created_at,
        "run_binding": run_binding,
        "signatures": got["signatures"],
        "argv": list(argv if argv is not None else sys.argv[1:]),
        # role and pole are SELECTION metadata, recorded as provenance. They are never part
        # of the arm key, and neither may alter a cached arm's values.
        "derived_from": derived_from or {"role": None, "pole": None},
        "n_support_rows": len(support_rows),
    }

    written = emit.write(out_root, doc=doc, provenance=prov,
                         support_rows=support_rows, coef_rows=got["coefficients"],
                         recon_rows=got["reconstruction"], run_id=run_id)
    return dict(written, arm_key=ref.arm_key, n_support_rows=len(support_rows))


def build(args, *, fit=None) -> dict[str, Any]:
    """One run from the command line. Admit the inputs, bind, verify the pin, execute.

    ORDER MATTERS. The solver lock and W10's admission are checked BEFORE the Stage-1 release
    is loaded, so that a missing report or an unadmitted bundle comes back as a NAMED typed
    refusal rather than as whatever the release loader raises on the way past it.
    """
    admitted = binding.admit_inputs(
        bundle_dir=args.direct_bundle, w10_report=args.w10_report,
        env_lock=args.env_lock, lane=args.lane)

    try:
        release, view = binding.load_release(
            release_path=args.stage1_release, kind=args.release_kind,
            validation_path=args.stage1_validation, gate_spec_path=args.stage1_gate_spec)
    except Exception as e:                      # the loader's own error type is not ours
        raise D.RefusalError(
            D.REFUSE_RELEASE_UNREADABLE,
            f"the bound Stage-1 v3 release could not be loaded ({e})") from e

    bound = binding.bind(
        arm_key=args.arm_key, bundle_dir=args.direct_bundle, w10_report=args.w10_report,
        env_lock=args.env_lock, view=view, release=release, lane=args.lane,
        admitted=admitted)
    up = upstream.identity(expect_tree_sha256=args.upstream_tree_sha256)

    return execute(
        bound=bound, release=release, view=view, up=up,
        paths={"cells": args.cells, "effects": args.effects, "masks": args.masks,
               "eligible": args.eligible},
        out_root=args.out_root, lane=args.lane, seed=args.seed, env_lock=args.env_lock,
        derived_from={"role": args.derived_from_role, "pole": args.derived_from_pole},
        fit=fit)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Perturb2State SECONDARY reconstruction support for ONE reusable arm")

    # THE FOUR BINDINGS the W7 wrapper's preflight checks for BY NAME
    # (stage2_run.py -> SECONDARY_LANE_BINDING_GAP). Its note is the whole point:
    #
    #     "Sequencing alone is not a binding."
    #
    # A wrapper can run this lane AFTER Direct and W10 and still have bound nothing. A
    # producer that does not ACCEPT the bundle and the report cannot be said to have run
    # from them. All four are REQUIRED: a default here would be a binding nobody supplied.
    ap.add_argument("--direct-bundle", required=True, dest="direct_bundle",
                    help="the ADMITTED Direct all-arm bundle directory "
                         "(<out-root>/<arm_bundle_run_id>); discover it with "
                         "`python -m direct.bundle_index`, never by guessing a path")
    ap.add_argument("--w10-report", required=True, dest="w10_report",
                    help="W10's INDEPENDENT admission report for that bundle "
                         "(DIRECT_BUNDLE_ADMISSION_<condition>.json). NOT the bundle's own "
                         "verification.json, which is the producer's empty slot")
    ap.add_argument("--env-lock", required=True, dest="env_lock",
                    help="analysis/stage02_solver_lock.txt — hashed here and checked against "
                         "this lane's own pin")
    ap.add_argument("--stage1-release", required=True)

    ap.add_argument("--arm-key", required=True,
                    help="direct|program_id|desired_change|condition")
    ap.add_argument("--release-kind", default="production",
                    choices=("production", "research_only", "fixture"))
    ap.add_argument("--stage1-validation", default=None)
    ap.add_argument("--stage1-gate-spec", default=None)
    ap.add_argument("--cells", required=True, help="prepared npz (scores read by barcode)")
    ap.add_argument("--effects", required=True)
    ap.add_argument("--masks", required=True)
    ap.add_argument("--eligible", required=True)
    ap.add_argument("--out-root", required=True,
                    help="OUTSIDE every tracked tree; the run dir is named for its content")
    ap.add_argument("--lane", default="production", choices=list(config.LANES))
    ap.add_argument("--seed", type=int, default=config.RANDOM_STATE)
    ap.add_argument("--upstream-tree-sha256", default=None,
                    help="pin the upstream source-tree content hash (catches an edited file "
                         "under a pinned commit)")
    ap.add_argument("--derived-from-role", default=None,
                    choices=(None, "away_from_A", "toward_B"))
    ap.add_argument("--derived-from-pole", default=None, choices=(None, "high", "low"))
    return ap


DEFERRED_FILE = "p2s_deferred_disposition.json"

# Exit codes. 0 = support emitted. 2 = a NAMED refusal (never 1, which is a crash): a
# scheduler must be able to tell "P2S declined this arm, for this reason" from "P2S broke".
EXIT_OK = 0
EXIT_REFUSED = 2


def emit_deferred(out_root: str, refusal: "D.RefusalError", *, arm_key: str,
                  argv: list[str]) -> str:
    """A TYPED DEFERRED DISPOSITION — a refusal RECORDED, never a silence.

    A refused arm is not an arm P2S has no opinion about; it is an arm P2S refused to speak
    for, and this says which. It NEVER fills a primary slot and it carries no support.
    """
    rec = refusal.record(arm_key=arm_key)
    rec["argv"] = list(argv)
    rec["lane_role"] = config.LANE_ROLE
    rec["counts_toward_completeness"] = False
    rec["filled_a_primary_slot"] = False
    os.makedirs(out_root, exist_ok=True)
    path = os.path.join(out_root, DEFERRED_FILE)
    emit.write_json(path, rec)
    return path


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    args = build_parser().parse_args(argv)

    if args.seed != config.RANDOM_STATE:
        print(f"note: seed {args.seed} is not the pinned {config.RANDOM_STATE}; it is "
              "recorded in the run binding and CHANGES the run id", file=sys.stderr)

    try:
        out = build(args)
    except D.RefusalError as e:
        path = emit_deferred(args.out_root, e, arm_key=args.arm_key, argv=argv)
        print(json.dumps({"state": "refused", "reason": e.reason,
                          "arm_key": args.arm_key, "support_emitted": False,
                          "disposition": os.path.basename(path)}, indent=2),
              file=sys.stderr)
        return EXIT_REFUSED

    print(f"{out['p2s_run_id']}  {out['arm_key']}  "
          f"{out['n_support_rows']} support row(s)  -> {os.path.basename(out['out_dir'])}")
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
