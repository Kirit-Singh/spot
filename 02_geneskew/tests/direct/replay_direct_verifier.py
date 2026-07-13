"""REPLAY: the whole independent Direct verification, against whatever producer is checked out.

Not a test — the acceptance harness. It re-runs, from the shipped bytes:

  1. the shipped-order MASK COUNTEREXAMPLE (the defect W14 repaired), which must now show the
     bound hash re-deriving from masks.parquet;
  2. the single-condition bundle gate;
  3. the full three-condition RELEASE gate;
  4. every audit mutation, each of which must still refuse at a NAMED gate.

Run:
    cd 02_geneskew
    PYTHONPATH=analysis:tests/direct python tests/direct/replay_direct_verifier.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "analysis", "direct"))

import conftest  # noqa: E402
import fixtures_direct as F  # noqa: E402
import fixtures_v3_release as V3  # noqa: E402
import verify_arm_bundle as VB  # noqa: E402
import verify_arm_rules as AR  # noqa: E402
import verify_arm_science as S  # noqa: E402
import verify_direct_release as VR  # noqa: E402
from direct import arm_release, run_arms  # noqa: E402  (harness drives the PRODUCER)
from verify_arm_report import verifier_code_sha256  # noqa: E402

CONDITIONS = ("Rest", "Stim8hr", "Stim48hr")

# THE PINNED STAGE-2 SOLVER LOCK. Every run binds it; the verifier re-hashes it and hard-pins
# it, so the harness must supply the real one — a fixture that skipped it would be testing a
# configuration the lane refuses.
LOCK = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "analysis", "stage02_solver_lock.txt")



def _key(row):
    return tuple("" if row.get(k) is None else str(row.get(k)) for k in S.MASK_ROW_SORT)


def _hash(rows):
    """The verifier's OWN canonical mask hash — reimplemented, never imported."""
    return AR.content_sha256(S._canonical_mask_rows(rows))


def _read_masks(bundle_dir):
    df = pd.read_parquet(os.path.join(bundle_dir, "masks.parquet"))
    return [{c: (None if pd.isna(r[c]) else r[c]) for c in df.columns}
            for _, r in df.iterrows()]


def mask_counterexample(tmp) -> dict:
    """THE counterexample, re-run: is `mask_sha256` a function of the bytes the bundle SHIPS?

    Also the SHUFFLED BYTE-IDENTITY property the fix turns on: the mask is a SET of facts, so
    the same rows in any input order must give the same canonical table and the same hash. If
    a reshuffle moved the number, the bundle's identity would move without one value changing.
    """
    args = conftest.synthetic_run.__wrapped__(tmp)()
    args.condition, args.out_root = F.CONDITION, os.path.join(tmp, "ce")
    args.env_lock = LOCK
    res = run_arms.build_bundle(args)

    bound = res["provenance"]["run_binding"]["mask_sha256"]
    shipped = _read_masks(res["out_dir"])

    # a deterministic, seedless reshuffle: reverse, then interleave from both ends
    reversed_rows = list(reversed(shipped))
    interleaved = [r for pair in zip(shipped, reversed_rows) for r in pair][:len(shipped)]

    return {
        "n_rows": len(shipped),
        "bound_mask_sha256": bound,
        "hash_shipped_order": _hash(shipped),
        "hash_reversed": _hash(reversed_rows),
        "hash_interleaved": _hash(interleaved),
        "REDERIVES_FROM_SHIPPED_BYTES": _hash(shipped) == bound,
        "SHUFFLE_INVARIANT": _hash(shipped) == _hash(reversed_rows) == _hash(interleaved),
        "shipped_parquet_is_already_canonical":
            [S._mask_order_key(r) for r in S._canonical_mask_rows(shipped)]
            == [S._mask_order_key(r) for r in
                [{c: S._native(x.get(c)) for c in S.MASK_ROW_COLUMNS} for x in shipped]],
    }


def bundle_gate(tmp) -> dict:
    args = conftest.synthetic_run.__wrapped__(tmp)()
    args.condition, args.out_root = F.CONDITION, os.path.join(tmp, "bundle")
    args.env_lock = LOCK
    res = run_arms.build_bundle(args)
    argv = ["--bundle", res["out_dir"], "--de-main", args.de_main, "--sgrna", args.sgrna,
            "--by-guide", args.by_guide, "--by-donors", args.by_donors,
            "--guide-manifest", args.guide_manifest, "--registry", args.registry,
            "--condition", args.condition, "--recompute", "all", "--env-lock", LOCK]
    for flag, attr in (("--source-registry", "source_registry"),
                       ("--pseudobulk", "pseudobulk")):
        value = getattr(args, attr, None)
        if value:
            argv += [flag, value]
    return VB.verify(VB.build_parser().parse_args(argv)).doc()


def release_gate(tmp) -> dict:
    prod = conftest.synthetic_run.__wrapped__(tmp)(conditions=CONDITIONS)
    root = os.path.join(tmp, "s1root")
    stage1 = V3.stage_release(root, conditions=CONDITIONS)
    prod.stage1_release, prod.stage1_release_root = stage1, root
    prod.env_lock = LOCK
    prod.out_root = os.path.join(tmp, "release")
    res = arm_release.build_release(prod)

    argv = ["--release", res["out_dir"], "--de-main", prod.de_main, "--sgrna", prod.sgrna,
            "--by-guide", prod.by_guide, "--by-donors", prod.by_donors,
            "--guide-manifest", prod.guide_manifest, "--registry", prod.registry,
            "--stage1-v3-release", stage1, "--release-root", root, "--recompute", "all",
            "--env-lock", LOCK]
    for flag, attr in (("--source-registry", "source_registry"),
                       ("--pseudobulk", "pseudobulk")):
        value = getattr(prod, attr, None)
        if value:
            argv += [flag, value]
    return VR.verify(VR.build_parser().parse_args(argv)).doc()


def audit_mutations() -> dict:
    """The seven audit attacks, re-run as the committed acceptance tests."""
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q",
         "tests/direct/test_verify_arm_bundle.py::TestTheIndependentAuditsExactAttacks",
         "tests/direct/test_verify_direct_release.py"],
        capture_output=True, text=True,
        env=dict(os.environ, PYTHONPATH="analysis:tests/direct"))
    tail = [ln for ln in proc.stdout.strip().splitlines() if ln.strip()][-1:]
    return {"exit": proc.returncode, "summary": tail[0] if tail else ""}


def main() -> int:
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    out: dict = {"producer_tree_commit": commit,
                 "verifier_code_sha256": verifier_code_sha256()}

    with tempfile.TemporaryDirectory() as tmp:
        out["mask_counterexample"] = mask_counterexample(tmp)
    with tempfile.TemporaryDirectory() as tmp:
        bundle = bundle_gate(tmp)
    with tempfile.TemporaryDirectory() as tmp:
        release = release_gate(tmp)

    out["bundle"] = {"verdict": bundle["verdict"], "n_passed": bundle["n_passed"],
                     "n_gates": bundle["n_gates"],
                     "failed_gates": bundle["failed_gates"],
                     "gate_inventory_sha256": bundle["gate_inventory_sha256"],
                     "report_sha256": bundle["report_sha256"]}
    out["release"] = {"verdict": release["verdict"], "n_passed": release["n_passed"],
                      "n_gates": release["n_gates"],
                      "failed_gates": release["failed_gates"],
                      "report_sha256": release["report_sha256"]}
    out["audit_mutations"] = audit_mutations()

    print(json.dumps(out, indent=2))
    ce = out["mask_counterexample"]
    ok = (ce["REDERIVES_FROM_SHIPPED_BYTES"] and ce["SHUFFLE_INVARIANT"]
          and bundle["verdict"] == "ADMIT" and release["verdict"] == "ADMIT"
          and out["audit_mutations"]["exit"] == 0)
    print("\nREPLAY:", "ALL GREEN — ADMIT" if ok else "NOT CLEAN")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
