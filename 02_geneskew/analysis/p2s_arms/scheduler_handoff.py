"""THE SCHEDULER HANDOFF: one fit per (program, condition) — and BOTH sign arms come free.

    python -m p2s_arms.scheduler_handoff --direct-bundle <dir> --w10-report <json> \
        --stage1-release <release> --condition Stim48hr --inputs <prepared dir> \
        --env-lock analysis/stage02_solver_lock.txt --out <handoff.json>

ONE FIT, TWO ARMS — SO THE SCHEDULER MUST NOT QUEUE TWO
-------------------------------------------------------
``increase`` is the fit; ``decrease`` is its EXACT negation. Scheduling both would run the
same fit twice, cost twice the compute, and — worse — invite two runs that could disagree by
a hair of floating point about a magnitude they are supposed to SHARE.

So the unit of work is the **(program, condition)**, not the arm. Each unit emits BOTH arm
keys, and the handoff says so in its own bytes: ``arms_emitted_per_unit: 2``.

EVERY EMITTED ARGV IS PARSER-VALID
----------------------------------
Checked here, by running the producer's OWN parser over it. A handoff whose commands do not
parse is a handoff that fails at 3am, one unit at a time, after the queue is already full.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

import numpy as np

from . import armref, binding, config, run_p2s_arms, w10
from . import disposition as D

HANDOFF_SCHEMA = "spot.stage02_p2s_scheduler_handoff.v1"
UNIT_KIND = "p2s_secondary_arm"

# The four Marson donors. The fit grid is a function of the donor SCOPES (all_donor + one
# leave-one-donor-out per donor), so the count is DERIVED from the producer's own grid
# functions rather than written down — a hard-coded "8" was already wrong once (it assumed
# the now-deferred pca_on_50).
DONORS = ("D1", "D2", "D3", "D4")


def fit_grid_summary() -> dict:
    """One INVOCATION runs the whole grid. Report base signatures, fits, and sign arms.

    n_fits is NOT 1. One invocation of the producer computes one base signature per donor
    scope, then a model fit per (layer, model-config) member of that scope's grid, and each
    fit yields BOTH sign arms of the program (increase, and its exact negation).
    """
    scopes = run_p2s_arms.scopes_for(np.asarray(DONORS))
    per_scope = []
    n_fits = 0
    for scope, _ in scopes:
        g = run_p2s_arms.grid(scope)
        per_scope.append({"scope": scope,
                          "members": [{"layer": lyr, "model_config": cfg.name} for lyr, cfg in g]})
        n_fits += len(g)
    return {
        "invocations_per_unit": 1,
        "base_signatures_per_unit": len(scopes),      # one per donor scope
        "fit_grid_members_per_unit": n_fits,          # model fits across the grid
        "sign_arms_per_fit": 2,                       # increase + its exact negation
        "model_configs": [c.name for c in config.CONFIGS],
        "primary_model_config": config.PRIMARY_MODEL_CONFIG,
        "determinism_mechanism": config.PCA_DETERMINISM_MECHANISM,
        "determinism_scope": config.DETERMINISM_SCOPE,
        "grid_by_scope": per_scope,
    }


def units(*, program_ids: list[str], condition: str, inputs_dir: str, direct_bundle: str,
          w10_report: str, env_lock: str, p2s_env_lock: str, stage1_release: str,
          out_root: str, lane: str = "production") -> list[dict[str, Any]]:
    """One unit per (program, condition). Both arm keys; ONE fit."""
    grid = fit_grid_summary()
    out: list[dict[str, Any]] = []
    for program_id in sorted(program_ids):
        inc, dec = armref.both_arms(program_id, condition)
        argv = [
            "--direct-bundle", direct_bundle,
            "--w10-report", w10_report,
            "--env-lock", env_lock,
            "--stage1-release", stage1_release,
            "--arm-key", inc.arm_key,
            "--inputs", inputs_dir,          # the prepared dir; its manifest is verified
            "--p2s-env-lock", p2s_env_lock,
            "--lane", lane,
            "--out-root", out_root,
        ]
        out.append({
            "unit_id": f"{UNIT_KIND}|{program_id}|{condition}",
            "kind": UNIT_KIND,
            "program_id": program_id,
            "condition": condition,
            # BOTH sign arms come out of ONE invocation. Do not schedule the sibling arm,
            # and do not read "one unit" as "one fit": one invocation runs the whole fit
            # grid (see fit_grid) and emits both arms.
            "arm_keys": [inc.arm_key, dec.arm_key],
            "arms_emitted_per_unit": 2,
            "invocations_per_unit": 1,
            "base_signatures_per_unit": grid["base_signatures_per_unit"],
            "fit_grid_members_per_unit": grid["fit_grid_members_per_unit"],
            "module": "p2s_arms.run_p2s_arms",
            "argv": argv,
            "produces": ["p2s_support.json", "p2s_arm_support.parquet"],
            "produces_on_refusal": ["p2s_deferred_disposition.json"],
            "exit_codes": {"0": "support emitted", "2": "a NAMED refusal, never a crash"},
            "counts_toward_completeness": False,
            "may_gate_or_alter_direct_ranks": False,
        })
    return out


def validate(unit: dict[str, Any]) -> None:
    """Run the PRODUCER'S OWN parser over the argv. A handoff that does not parse is a fault."""
    parser = run_p2s_arms.build_parser()
    try:
        args = parser.parse_args(unit["argv"])
    except SystemExit as e:
        raise D.RefusalError(
            D.REFUSE_INCOMPATIBLE_ARM,
            f"unit {unit['unit_id']!r} does not parse against the producer's own CLI "
            f"(argparse exit {e.code}). A handoff whose commands do not parse fails at 3am, "
            "one unit at a time, after the queue is already full") from e

    # ...and the arm key it carries must be the arm key it names
    ref = armref.parse(args.arm_key)
    if ref.program_id != unit["program_id"] or ref.condition != unit["condition"]:
        raise D.RefusalError(
            D.REFUSE_INCOMPATIBLE_ARM,
            f"unit {unit['unit_id']!r} names {unit['program_id']}/{unit['condition']} but its "
            f"argv asks for {ref.program_id}/{ref.condition}")
    if args.arm_key != unit["arm_keys"][0]:
        raise D.RefusalError(
            D.REFUSE_INCOMPATIBLE_ARM,
            f"unit {unit['unit_id']!r} must be invoked on its INCREASE arm; the decrease arm "
            "is that base effect's exact negation and is never fitted separately")


def build(args, *, view=None) -> dict[str, Any]:
    """The handoff document. Every unit validated against the producer's own parser."""
    admitted = binding.admit_inputs(
        bundle_dir=args.direct_bundle, w10_report=args.w10_report,
        env_lock=args.env_lock, lane=args.lane)
    admission = admitted["admission"]

    if str(admission.get("condition")) != args.condition:
        raise D.RefusalError(
            D.REFUSE_CONDITION_MISMATCH,
            f"--condition {args.condition!r} is not the admitted bundle's condition "
            f"({admission.get('condition')!r})")

    if view is None:
        _release, view = binding.load_release(
            release_path=args.stage1_release, kind=args.release_kind)

    # DERIVED from the release, never a copied count. Th9 is absent because the release says
    # it is not base_portable — not because a constant here says "10".
    programs = list(view["admitted_program_ids"])

    manifest_path = os.path.join(args.inputs, "p2s_inputs.json")
    if not os.path.exists(manifest_path):
        raise D.RefusalError(
            D.REFUSE_BUNDLE_INCOMPLETE,
            f"--inputs {args.inputs!r} carries no p2s_inputs.json; it was not produced by "
            "`python -m p2s_arms.prepare_inputs` and this lane will not guess at its bytes")
    with open(manifest_path) as fh:
        inputs_manifest = json.load(fh)

    if inputs_manifest.get("condition") != args.condition:
        raise D.RefusalError(
            D.REFUSE_CONDITION_MISMATCH,
            f"the prepared inputs are for {inputs_manifest.get('condition')!r}, not "
            f"{args.condition!r}")

    unit_list = units(
        program_ids=programs, condition=args.condition, inputs_dir=args.inputs,
        direct_bundle=args.direct_bundle, w10_report=args.w10_report,
        env_lock=args.env_lock, p2s_env_lock=args.p2s_env_lock,
        stage1_release=args.stage1_release, out_root=args.out_root, lane=args.lane)

    for u in unit_list:
        validate(u)

    doc = {
        "schema_version": HANDOFF_SCHEMA,
        "lane_role": config.LANE_ROLE,
        "condition": args.condition,
        "n_units": len(unit_list),
        "n_arms": sum(u["arms_emitted_per_unit"] for u in unit_list),
        "one_invocation_per_program_condition": True,
        "both_sign_arms_emitted_per_invocation": True,
        "fit_grid": fit_grid_summary(),
        "n_fit_grid_members_total":
            len(unit_list) * fit_grid_summary()["fit_grid_members_per_unit"],
        "every_argv_is_parser_valid": True,
        # PROFILE. Prefer ONE condition worker that reuses this condition's cells + effects
        # across its programs serially; a second worker re-reads the same 396k matrix. Never
        # more than two.
        "worker_profile": {
            "max_condition_workers": 2,
            "preferred_condition_workers": 1,
            "why": ("one condition worker reuses this condition's cells.npz and effects.npz "
                    "serially across its programs; a second worker re-reads the same 396k "
                    "cell matrix for no scientific gain"),
            "cells_and_effects_are_shared_within_a_condition": True,
        },
        "counts_toward_completeness": False,
        "n_admitted_programs": view["n_admitted_programs"],
        "scorer_view_sha256": view["scorer_view_sha256"],
        "p2s_inputs_run_id": inputs_manifest.get("p2s_inputs_run_id"),
        "arm_bundle_run_id": admission.get("arm_bundle_run_id"),
        "w10_report_sha256": admission.get("w10_report_sha256"),
        "direct_solver_lock_sha256": admitted["solver_lock"]["sha256"],
        "p2s_runtime_lock_sha256": inputs_manifest.get("environment_locks", {})
            .get("p2s_runtime_lock_sha256"),
        "two_environments": True,
        "stage1_scores_raw_sha256": inputs_manifest.get("stage1_scores", {})
            .get("raw_sha256"),
        "stage1_scores_canonical_sha256": inputs_manifest.get("stage1_scores", {})
            .get("canonical_scores_sha256"),
        "units": unit_list,
    }
    return dict(doc, handoff_sha256=w10.content_sha256(doc))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Emit the P2S scheduler handoff for one condition")
    ap.add_argument("--direct-bundle", required=True, dest="direct_bundle")
    ap.add_argument("--w10-report", required=True, dest="w10_report")
    ap.add_argument("--env-lock", required=True, dest="env_lock")
    ap.add_argument("--p2s-env-lock", required=True, dest="p2s_env_lock")
    ap.add_argument("--stage1-release", required=True)
    ap.add_argument("--condition", required=True, choices=list(config.CONDITIONS))
    ap.add_argument("--inputs", required=True,
                    help="the directory `prepare_inputs` produced")
    ap.add_argument("--out-root", required=True, help="where each unit will write")
    ap.add_argument("--out", required=True, help="write the handoff JSON here")
    ap.add_argument("--release-kind", default="production",
                    choices=("production", "research_only", "fixture"))
    ap.add_argument("--lane", default="production", choices=list(config.LANES))
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(list(sys.argv[1:] if argv is None else argv))
    try:
        doc = build(args)
    except D.RefusalError as e:
        print(json.dumps({"state": "refused", "reason": e.reason, "detail": e.message},
                         indent=2), file=sys.stderr)
        return 2

    with open(args.out, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(json.dumps({k: doc[k] for k in
                      ("condition", "n_units", "n_arms", "n_fit_grid_members_total",
                       "handoff_sha256")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
