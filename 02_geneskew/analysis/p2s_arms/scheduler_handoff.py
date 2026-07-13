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

from . import armref, binding, config, run_p2s_arms, w10
from . import disposition as D

HANDOFF_SCHEMA = "spot.stage02_p2s_scheduler_handoff.v1"
UNIT_KIND = "p2s_secondary_arm"


def units(*, program_ids: list[str], condition: str, inputs_dir: str, direct_bundle: str,
          w10_report: str, env_lock: str, stage1_release: str, out_root: str,
          lane: str = "production") -> list[dict[str, Any]]:
    """One unit per (program, condition). Both arm keys; ONE fit."""
    out: list[dict[str, Any]] = []
    for program_id in sorted(program_ids):
        inc, dec = armref.both_arms(program_id, condition)
        argv = [
            "--direct-bundle", direct_bundle,
            "--w10-report", w10_report,
            "--env-lock", env_lock,
            "--stage1-release", stage1_release,
            "--arm-key", inc.arm_key,
            "--cells", os.path.join(inputs_dir, "cells.npz"),
            "--effects", os.path.join(inputs_dir, "effects.parquet"),
            "--masks", os.path.join(inputs_dir, "masks.parquet"),
            "--eligible", os.path.join(inputs_dir, "eligible.parquet"),
            "--lane", lane,
            "--out-root", out_root,
        ]
        out.append({
            "unit_id": f"{UNIT_KIND}|{program_id}|{condition}",
            "kind": UNIT_KIND,
            "program_id": program_id,
            "condition": condition,
            # BOTH arms come out of the ONE fit below. Do not schedule the sibling.
            "arm_keys": [inc.arm_key, dec.arm_key],
            "arms_emitted_per_unit": 2,
            "n_fits": 1,
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
            f"unit {unit['unit_id']!r} must be fitted on its INCREASE arm; the decrease arm "
            "is that fit's exact negation and is never fitted separately")


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
        env_lock=args.env_lock, stage1_release=args.stage1_release,
        out_root=args.out_root, lane=args.lane)

    for u in unit_list:
        validate(u)

    doc = {
        "schema_version": HANDOFF_SCHEMA,
        "lane_role": config.LANE_ROLE,
        "condition": args.condition,
        "n_units": len(unit_list),
        "n_fits": sum(u["n_fits"] for u in unit_list),
        "n_arms": sum(u["arms_emitted_per_unit"] for u in unit_list),
        "one_fit_per_program_condition": True,
        "both_sign_arms_emitted_per_fit": True,
        "every_argv_is_parser_valid": True,
        "counts_toward_completeness": False,
        "n_admitted_programs": view["n_admitted_programs"],
        "scorer_view_sha256": view["scorer_view_sha256"],
        "p2s_inputs_run_id": inputs_manifest.get("p2s_inputs_run_id"),
        "arm_bundle_run_id": admission.get("arm_bundle_run_id"),
        "w10_report_sha256": admission.get("w10_report_sha256"),
        "solver_lock_sha256": admitted["solver_lock"]["sha256"],
        "units": unit_list,
    }
    return dict(doc, handoff_sha256=w10.content_sha256(doc))


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="Emit the P2S scheduler handoff for one condition")
    ap.add_argument("--direct-bundle", required=True, dest="direct_bundle")
    ap.add_argument("--w10-report", required=True, dest="w10_report")
    ap.add_argument("--env-lock", required=True, dest="env_lock")
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
                      ("condition", "n_units", "n_fits", "n_arms", "handoff_sha256")},
                     indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
