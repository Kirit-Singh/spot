"""Command-line entry point for the Stage-2 temporal cross-condition estimator.

It reuses the direct lane's argument surface verbatim — same inputs, same lanes, same
release gate — and adds only ``--conditions``. A temporal run that could be pointed at
different inputs from the screen it stands on would not be differencing that screen.

Reports every comparison it computed, and for each one the batch verdict. It never
reports a "top mover": there is no combined temporal objective and no headline arm, so
there is nothing to head a list with.
"""
from __future__ import annotations

import argparse
import json
import sys

from .. import config, gate
from . import run_temporal, verify_temporal


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Stage-2 temporal cross-condition estimator (difference-in-"
                    "differences on program projections; population-level, NOT fate)")
    ap.add_argument("--selection", required=True,
                    help="immutable stage01 selection contract (JSON)")
    ap.add_argument("--registry", required=True)
    ap.add_argument("--de-main", required=True)
    ap.add_argument("--by-guide", required=True)
    ap.add_argument("--by-donors", required=True)
    ap.add_argument("--sgrna", required=True)
    ap.add_argument("--guide-manifest", default=None)
    ap.add_argument("--source-registry", default=None)
    ap.add_argument("--stage1-release", default=None)
    ap.add_argument("--stage1-validation", default=None)
    ap.add_argument("--stage1-gate-spec", default=None)
    ap.add_argument("--target-identity-map", default=None)
    ap.add_argument("--donor-crosswalk", default=None)
    ap.add_argument("--env-lock", default=None)
    ap.add_argument("--allow-dirty-tree", action="store_true",
                    help="take a RELEASE-grade run from an uncommitted tree. The digest "
                         "then describes bytes that exist in no commit, so this is "
                         "RECORDED in the run binding and CHANGES the run id — a dirty "
                         "release is allowed to exist, not to look like a clean one.")
    ap.add_argument("--lane", default=config.LANE_PRODUCTION,
                    choices=list(config.LANES))
    ap.add_argument("--strict-replay", action="store_true",
                    help="THE RELEASE GATE, exactly as the within-condition lane "
                         "applies it. Expensive; run on tcefold.")
    ap.add_argument("--pseudobulk", default=None)
    ap.add_argument("--batch-policy", default=None,
                    help="the frozen batch-confound policy (defaults to the pinned "
                         "policy shipped alongside this module)")
    ap.add_argument("--stage1-v3-selection", default=None,
                    help="a Stage-1 v3 selection contract with "
                         "analysis_mode=temporal_cross_condition. Its ORDERED condition "
                         "pair is the comparison that gets computed, and it is bound "
                         "into the run identity.")
    ap.add_argument("--stage1-v3-schema", default=None,
                    help="the PINNED v3 JSON schema the contract is validated against")
    ap.add_argument("--conditions", nargs="*", default=None,
                    help="conditions to compare (default: the v3 contract's pair, or "
                         "every condition the release ships). EVERY ordered pair of them "
                         "is computed, in BOTH directions; none is ever refused.")
    ap.add_argument("--out-root", required=True)
    args = ap.parse_args(argv)

    try:
        result = run_temporal.build_temporal(args, conditions=args.conditions)
    except gate.GateError as exc:
        print(json.dumps(exc.report or {"verdict": "NO_GO", "error": str(exc)},
                         indent=2, sort_keys=True))
        return 1

    v = result["verification"]
    print(json.dumps({
        "temporal_run_id": result["temporal_run_id"],
        "temporal_method_sha256": result["temporal_method_sha256"],
        "out_dir": result["out_dir"],
        "conditions": result["conditions"],
        "n_comparisons": result["n_comparisons"],
        "n_records": result["n_records"],
        # every comparison, with its batch verdict. Nothing is omitted from this list:
        # a comparison the CLI did not print is a comparison nobody will go looking for.
        "comparisons": {c["comparison_id"]:
                        {"batch_status": c["batch_status"],
                         "batch_partially_confounded":
                             c["batch_partially_confounded"]}
                        for c in _comparisons(result["out_dir"])},
        "verification": {"verdict": v["verdict"], "n_failed": v["n_failed"]},
        # said where a reader looks, not only in the methods doc
        "inference_status": "not_calibrated",
        "estimand": "population_level_program_projection_shift_not_per_cell_fate",
    }, indent=2))
    # A REJECTED artifact is an exit code, not a log line.
    return 0 if v["verdict"] == verify_temporal.ADMIT else 1


def _comparisons(out_dir: str) -> list[dict]:
    import os
    with open(os.path.join(out_dir, "temporal_provenance.json")) as fh:
        return json.load(fh)["comparisons"]


if __name__ == "__main__":
    sys.exit(main())
