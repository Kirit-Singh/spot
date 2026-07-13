"""THE PRODUCTION COMMAND: assemble a Stage-2 release from ADMITTED bytes, and verify it.

It does three things, in this order, and refuses at the first that fails:

  1. DISCOVER — but only what has been INDEPENDENTLY ADMITTED. A lane whose independent
     verifier has not admitted it does not enter the release; it is not "included with a
     warning", and it is not "included pending review". The producer's own preflight is not
     an admission, and a directory that merely exists is not evidence.
  2. BUILD the aggregate manifest over exactly those bundles.
  3. INVOKE THE SEPARATE AGGREGATE VERIFIER — as a SEPARATE PROCESS, reading the bytes back
     off disk and WRITING ITS OWN REPORT. Not an in-process call whose return value this
     command then summarises: a summary written by the thing being audited is not a
     verification. The exit code is the verifier's, not its own.

THE CANONICAL LAYOUT (one root; no staging step)
------------------------------------------------
    OUT/                                  <- --bundles-root AND --release-inventory-root
      direct/<bundle-dir>/ ...            (3)   the lane producers write these
      temporal/<bundle-dir>/ ...          (6)
      pathway/<bundle-dir>/ ...           (6)
      direct_release.json                       producer inventory   (PENDING)
      direct_release_admission.json             W10 external admission
      temporal_arm_release.json                 producer inventory   (PENDING)
      temporal_arm_external_admission.json      W11 external admission
      pathway_arm_release.json                  producer inventory   (PENDING)
      pathway_arm_external_admission.json       W4 external admission
      stage2_run_manifest.json                  <- --out (a FILE, not a directory)
      stage2_aggregate_verification.json        <- --verify-report (the SEPARATE report)

Bundles live in lane subdirectories; the release-level artifacts live at the ROOT. Discovery
walks the tree, so the subdirectory names are free: a bundle is a bundle because its
``arm_bundle.json`` says which lane it is, never because of the folder it sits in.

WHAT IT NEVER DOES
------------------
It launches no compute. It reads what the lane producers already wrote, and it refuses
anything it cannot attribute.

P2S IS A SEPARATE, SECONDARY INDEX. Perturb2State is indexed here so a reader can see it
exists and see what it is — a deferred secondary method. It is NOT part of the release, it
does NOT gate it, and it can never move a Direct arm value or rank: it is recorded beside
the release, never inside it. A secondary method that could change a primary ranking would
not be secondary.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import subprocess
import sys
from typing import Any, Optional

from . import bundle_shapes as BS
from . import release_inventory as RI
from . import run_manifest
from .arm_topology import LANES, RunManifestError, load_release

P2S_INDEX = {
    "component": "perturb2state",
    "tier": "secondary_method",
    "state": "deferred_not_part_of_this_release",
    "gates_the_release": False,
    "may_change_a_direct_arm_value_or_rank": False,
    "indexed_beside_the_release_never_inside_it": True,
}


def _git(repo: str, *args: str) -> Optional[str]:
    try:
        r = subprocess.run(("git", "-C", repo) + args, capture_output=True, text=True,
                           timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return r.stdout.strip() if r.returncode == 0 else None


def discover(root: str, lane: str) -> list[str]:
    """Bundle directories for ONE lane, by the bundle's OWN SCHEMA.

    Not by a top-level `lane` key: only the temporal producer emits one. Direct names itself
    `spot.stage02_direct_arm_bundle.v1` and pathway `spot.stage02_pathway_arm_bundle.v1`, and
    an aggregate that looked for `lane` found neither — so a 15-bundle release was 6 bundles
    and a fixture. The schema is the one field every producer does write.
    """
    found = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if BS.BUNDLE_FILE not in files:
            continue
        norm = BS.read(base)
        if norm and norm["lane"] == lane:
            found.append(base)
    return sorted(found)


def admitted_lanes(root: str) -> tuple:
    """Which lanes an INDEPENDENT verifier has admitted. Nothing else may be released."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import verify_lane_admission as LA

    admitted, refused = {}, []
    for lane in LANES:
        block, problems = LA.adapt(root, lane)
        if problems or not block or block.get("aggregate_disposition") != LA.ADMITTED:
            refused += problems or [f"[{lane}] not independently admitted"]
            continue
        admitted[lane] = block
    return admitted, refused


def assemble(args) -> dict[str, Any]:
    """Build the release: admitted lanes only, exact inventories, aggregate manifest."""
    release = load_release(args.release, args.release_root)
    env_lock_sha256 = RI.file_sha256(args.env_lock)

    # ---- 1. ONLY WHAT WAS INDEPENDENTLY ADMITTED ---- #
    admitted, refused = admitted_lanes(args.bundles_root)
    if refused:
        raise RunManifestError(
            "these lanes are NOT independently admitted and may not enter a release: "
            + "; ".join(refused[:6]))

    n_cond = len(release["conditions"])
    n_src = len(release["gene_set_sources"])

    # ---- 2. THE EXACT PER-LANE INVENTORIES ---- #
    inventories, bundles = {}, []
    for lane in LANES:
        dirs = discover(args.bundles_root, lane)
        want = RI.expected_bundle_count(lane, n_cond, n_src)
        # CONSUME, NEVER MANUFACTURE. The admission binds the inventory by hash, so an
        # inventory written HERE — after the lane was admitted — would be binding something
        # that did not exist when the verifier wrote its report. The producer writes it
        # first (`python -m direct.release_inventory --lane ...`); this step reads it.
        path = os.path.join(args.bundles_root, RI.INVENTORY_FILE_OF[lane])
        if not os.path.exists(path):
            raise RunManifestError(
                f"the {lane} lane has no {RI.INVENTORY_FILE_OF[lane]}. The PRODUCER writes "
                "the pending inventory BEFORE the independent verifier admits it — the "
                "admission binds it by hash, so it cannot be manufactured here afterwards. "
                f"Run: python -m direct.release_inventory --lane {lane} --bundles-root "
                "<root> --release <rel> --release-root <root> --env-lock <lock>")
        with open(path) as fh:
            inv = json.load(fh)
        if len(dirs) != want or int(inv.get("n_bundles") or 0) != want:
            raise RunManifestError(
                f"the {lane} release ships {len(dirs)} bundle(s) and its inventory names "
                f"{inv.get('n_bundles')}; this lane is exactly {want}")
        inventories[lane] = {
            "file": RI.INVENTORY_FILE_OF[lane],
            "admission_mode": RI.ADMISSION_MODE_OF[lane],
            "n_bundles": inv["n_bundles"],
            "n_logical_arms": inv["n_logical_arms"],
        }
        bundles += [run_manifest.bind_bundle(d) for d in dirs]

    # ---- 3. THE AGGREGATE MANIFEST ---- #
    doc = run_manifest.build(
        bundles=bundles, out_path=args.out, release=release,
        lane_admissions=admitted)
    doc["release_assembly"] = {
        "assembled_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "lane_inventories": inventories,
        "producer_commit": args.producer_commit,
        "verifier_commit": args.verifier_commit,
        "solver_lock_sha256": env_lock_sha256,
        "launched_compute": False,
        "perturb2state": P2S_INDEX,
    }
    return doc


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Assemble a Stage-2 release from INDEPENDENTLY ADMITTED bytes, then "
                    "hand it to the SEPARATE aggregate verifier. Launches no compute.")
    ap.add_argument("--bundles-root", required=True)
    ap.add_argument("--release", required=True)
    ap.add_argument("--release-root", required=True)
    ap.add_argument("--env-lock", required=True)
    ap.add_argument("--expect-env-lock-sha256", required=True)
    ap.add_argument("--expect-release-sha256", required=True)
    ap.add_argument("--expect-gene-sets", required=True)
    ap.add_argument("--expect-verifiers", required=True)
    ap.add_argument("--expected-code-identity", required=True)
    ap.add_argument("--producer-commit", default=None)
    ap.add_argument("--verifier-commit", default=None)
    ap.add_argument("--out", required=True,
                    help="the aggregate manifest. A FILE, not a directory.")
    ap.add_argument("--verify-report", default=None,
                    help="where the SEPARATE aggregate verifier writes its report. "
                         "Default: stage2_aggregate_verification.json beside --out.")
    ap.add_argument("--verify", action="store_true",
                    help="run the SEPARATE aggregate verifier as its OWN PROCESS. It writes "
                         "its own report and its exit code becomes ours: this command does "
                         "not certify its own output.")
    args = ap.parse_args(argv)

    try:
        doc = assemble(args)
    except RunManifestError as exc:
        print(json.dumps({"assembled": False, "error": str(exc)}, indent=2))
        return 1

    print(json.dumps({k: v for k, v in doc.items() if k != "bundles"},
                     indent=2, sort_keys=True, default=str))
    if not args.verify:
        return 0 if doc["topology_complete"] else 1

    # THE SEPARATE VERIFIER — ITS OWN PROCESS, ITS OWN REPORT. Not an in-process call whose
    # return value this command then prints: a summary written by the thing being audited is
    # not a verification.
    report_path = args.verify_report or os.path.join(
        os.path.dirname(os.path.abspath(args.out)),
        "stage2_aggregate_verification.json")
    cmd = [
        sys.executable, "-m", "direct.verify_run_manifest",
        "--manifest", doc["path"],
        "--bundles-root", args.bundles_root,
        "--release-inventory-root", args.bundles_root,
        "--release", args.release,
        "--release-root", args.release_root,
        "--expect-release-sha256", args.expect_release_sha256,
        "--expect-gene-sets", args.expect_gene_sets,
        "--expect-verifiers", args.expect_verifiers,
        "--expected-code-identity", args.expected_code_identity,
        "--env-lock", args.env_lock,
        "--expect-env-lock-sha256", args.expect_env_lock_sha256,
        "--report", report_path,
    ]
    env = dict(os.environ)
    analysis = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env["PYTHONPATH"] = analysis + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)

    if not os.path.exists(report_path):
        print(json.dumps({
            "aggregate_verdict": None,
            "error": "the separate aggregate verifier wrote NO report; an admission nobody "
                     "recorded is not an admission",
            "verifier_exit_code": proc.returncode}, indent=2))
        return 1
    with open(report_path) as fh:
        report = json.load(fh)
    print(json.dumps({
        "aggregate_verdict": report["verdict"],
        "n_failed": report["n_failed"],
        "failed_gates": report["failed_gates"],
        "verifier_report": report_path,
        "verifier_exit_code": proc.returncode,
        "verifier_ran_in_a_separate_process": True,
    }, indent=2))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
