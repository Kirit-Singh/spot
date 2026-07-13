"""Command-line entry point for the Stage-2 direct screen.

Reports the TWO arm populations. There is no single ``n_ranked`` and no single
eligibility summary, because there is no headline arm.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import config, gate, preflight
from .run_screen import build_screen


def main(argv=None):
    ap = argparse.ArgumentParser(description="Stage-2 direct perturbation screen")
    ap.add_argument("--selection", required=True,
                    help="immutable stage01 selection contract (JSON)")
    ap.add_argument("--registry", required=True)
    ap.add_argument("--de-main", required=True)
    ap.add_argument("--by-guide", required=True)
    ap.add_argument("--by-donors", required=True)
    ap.add_argument("--sgrna", required=True)
    ap.add_argument("--guide-manifest", default=None,
                    help="canonical contributing-guide manifest; authoritative when given")
    ap.add_argument("--source-registry", default=None,
                    help="independently trusted pins for the manifest's sources")
    ap.add_argument("--stage1-release", default=None,
                    help="Stage-1 release manifest (production) or verified v3 "
                         "measurement bundle (research_only)")
    ap.add_argument("--stage1-validation", default=None,
                    help="Stage-1 validation rows (fixture lane)")
    ap.add_argument("--stage1-gate-spec", default=None,
                    help="Stage-1 gate spec (fixture lane)")
    ap.add_argument("--target-identity-map", default=None,
                    help="explicit target_id -> Ensembl gene id map; the ONLY way a "
                         "symbol-namespace target may acquire an Ensembl id")
    ap.add_argument("--donor-crosswalk", default=None,
                    help="explicit Stage-1-donor-label -> release-donor-token map")
    ap.add_argument("--env-lock", default=None)
    ap.add_argument("--allow-dirty-tree", action="store_true",
                    help="take a RELEASE-grade run from an uncommitted tree. The digest "
                         "then describes bytes that exist in no commit, so this is "
                         "RECORDED in the run binding and CHANGES the run id — a dirty "
                         "release is allowed to exist, not to look like a clean one.")
    ap.add_argument("--lane", default=config.LANE_PRODUCTION,
                    choices=list(config.LANES),
                    help="must match the selection contract's declared lane")
    ap.add_argument("--preflight-only", action="store_true",
                    help="validate Stage-1 selection/release, the public source pins, "
                         "the global pooled-main scope identity, the contributor "
                         "manifest + source-record table + completeness report, the "
                         "selected-condition main count and the explicit unavailable "
                         "support contract — all BEFORE any dense layer read. Writes "
                         "no scientific result artifact; reports a machine-readable "
                         "verdict and exits 0 on GO, 1 on NO_GO.")
    ap.add_argument("--preflight-out", default=None,
                    help="write the preflight verdict here (JSON)")
    ap.add_argument("--strict-replay", action="store_true",
                    help="re-derive the contributor COMPLETENESS from the raw ~44 GB "
                         "pseudobulk source and require the fresh verdict to agree "
                         "with the pinned report, instead of trusting it. THIS IS THE "
                         "RELEASE GATE, and it is the only way to pass it: a "
                         "production / research_only run without it refuses before the "
                         "dense read. Expensive; run on tcefold.")
    ap.add_argument("--pseudobulk", default=None,
                    help="the raw pseudobulk source for --strict-replay")
    ap.add_argument("--out-root", default=None,
                    help="required for a real build; a preflight writes no results")
    args = ap.parse_args(argv)

    if args.preflight_only:
        report = preflight.run(args)
        if args.preflight_out:
            preflight.write(report, args.preflight_out)
        print(json.dumps(report, indent=2, sort_keys=True))
        return report

    if not args.out_root:
        ap.error("--out-root is required for a real build")

    # EVERY build runs the gate. ``build_screen`` applies it internally, over the very
    # inputs it is about to score, and refuses before the dense read — so there is no
    # path that reaches a scientific artifact without passing what --preflight-only
    # would have asked. A refusal is an exit code, not a log line.
    try:
        result = build_screen(args)
    except gate.GateError as exc:
        report = exc.report or {"schema_version": preflight.SCHEMA_VERSION,
                                "verdict": preflight.NO_GO,
                                "failures": [{"check": gate.CHECK_MANIFEST,
                                              "error": str(exc)}]}
        print(json.dumps(report, indent=2, sort_keys=True))
        return report

    v = result["verification"]
    per_arm = v["ranking"]["per_arm"]
    print(json.dumps({
        "run_id": result["run_id"],
        "lane": result["lane"],
        "namespace": result["namespace"],
        "production_eligible": result["production_eligible"],
        "stage3_eligible": result["stage3_eligible"],
        "out_dir": result["out_dir"],
        "n_rows": result["n_rows"],
        "complete_disposition": v["complete_disposition"],
        # two arms, two populations. There is no single "n_ranked".
        "arms": {arm: {"n_evaluable": per_arm[arm]["n_evaluable"],
                       "n_ranked": per_arm[arm]["n_ranked"],
                       "ranks_valid": (per_arm[arm]["ranks_contiguous"]
                                       and per_arm[arm]["rank_is_nullable_integer"]),
                       "arm_state_counts": per_arm[arm]["arm_state_counts"]}
                 for arm in config.ARMS},
        "base_qc_state_counts": v["base_qc_state_counts"],
        "contributor_status_counts": v["contributor_status_counts"],
        "no_pq_columns": v["no_pq_columns"],
        "no_combined_objective": v["ranking"]["no_combined_objective"],
        "no_causal_language": v["no_causal_language"],
        # this pass grants NO guide/donor support, and says so where a reader looks
        "support_contract": result["support_contract"]["state"],
        "evidence_domain": result["evidence_domain"]["domain_id"],
    }, indent=2))
    return result


def _exit_code(result) -> int:
    """NO_GO is an exit code, not a log line. A preflight nobody can gate on is a
    preflight nobody will gate on."""
    if isinstance(result, dict) and result.get("schema_version") \
            == preflight.SCHEMA_VERSION:
        return 0 if result.get("verdict") == preflight.GO else 1
    return 0


if __name__ == "__main__":
    sys.exit(_exit_code(main()))

