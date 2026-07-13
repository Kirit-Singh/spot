"""THE PRODUCTION COMMAND: assemble a Stage-2 release from ADMITTED bytes, and verify it.

It does three things, in this order, and refuses at the first that fails:

  1. DISCOVER — but only what has been INDEPENDENTLY ADMITTED. A lane whose independent
     verifier has not admitted it does not enter the release; it is not "included with a
     warning", and it is not "included pending review". The producer's own preflight is not
     an admission, and a directory that merely exists is not evidence.
  2. BUILD the aggregate manifest over exactly those bundles.
  3. INVOKE THE SEPARATE AGGREGATE VERIFIER on the result — a different process, reading the
     bytes back off disk. This command does not get to certify its own output, and the exit
     code is the verifier's, not its own.

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
    """Bundle directories for ONE lane. A directory is a bundle iff it says it is."""
    found = []
    for base, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        if "arm_bundle.json" not in files:
            continue
        try:
            with open(os.path.join(base, "arm_bundle.json")) as fh:
                if json.load(fh).get("lane") == lane:
                    found.append(base)
        except (OSError, ValueError):
            raise RunManifestError(
                f"{base}: arm_bundle.json is not readable JSON — a directory that cannot "
                "be opened is not a bundle") from None
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
    stage1 = {
        "release_canonical_sha256": release["release_canonical_sha256"],
        "registry_scorer_view_canonical_sha256":
            release["registry_scorer_view_canonical_sha256"],
        "registry_scorer_projection_sha256":
            release["registry_scorer_projection_sha256"],
        "admitted_programs": release["programs"],
        "conditions": release["conditions"],
    }

    # ---- 2. THE EXACT PER-LANE INVENTORIES ---- #
    inventories, bundles = {}, []
    for lane in LANES:
        dirs = discover(args.bundles_root, lane)
        want = RI.expected_bundle_count(lane, n_cond, n_src)
        inv = RI.build(lane=lane, bundle_dirs=dirs, root=args.bundles_root,
                       expect_bundles=want, stage1=stage1,
                       env_lock_sha256=env_lock_sha256,
                       producer_commit=args.producer_commit,
                       verifier_commit=args.verifier_commit)
        path = os.path.join(args.bundles_root, RI.INVENTORY_FILE_OF[lane])
        if not os.path.exists(path):          # a lane that ships its own is not overwritten
            with open(path, "w") as fh:
                json.dump(inv, fh, indent=2, sort_keys=True)
                fh.write("\n")
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
    ap.add_argument("--out", required=True)
    ap.add_argument("--verify", action="store_true",
                    help="invoke the SEPARATE aggregate verifier on the result. The exit "
                         "code becomes the VERIFIER's: this command does not certify its "
                         "own output.")
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

    # THE SEPARATE VERIFIER. A different process, reading the bytes back off disk.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from . import verify_run_manifest as V

    report = V.verify(
        manifest_path=doc["path"], bundles_root=args.bundles_root,
        release_path=args.release, release_root=args.release_root,
        expect_release_sha256=args.expect_release_sha256,
        expect_gene_sets_path=args.expect_gene_sets,
        expect_verifiers_path=args.expect_verifiers,
        expected_code_identity_path=args.expected_code_identity,
        env_lock_path=args.env_lock,
        expect_env_lock_sha256=args.expect_env_lock_sha256)
    print(json.dumps({"aggregate_verdict": report["verdict"],
                      "n_failed": report["n_failed"],
                      "failed_gates": report["failed_gates"]}, indent=2))
    return 0 if report["verdict"] == "admit" else 1


if __name__ == "__main__":
    raise SystemExit(main())
