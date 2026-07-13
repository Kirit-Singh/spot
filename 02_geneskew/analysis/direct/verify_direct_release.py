"""STANDALONE independent verifier for the WHOLE Direct release: every condition, once.

Usage:
    python analysis/direct/verify_direct_release.py --release <dir> \\
        --de-main <h5ad> --sgrna <csv> --guide-manifest <json> \\
        --stage1-v3-release <json> --release-root <dir> \\
        [--recompute sample|all] [--report <json>]

Exit 0 = ADMIT; 1 = REFUSE. A crash IS a refusal.

INDEPENDENCE RULE (test-enforced): imports nothing from the generator. It does not import
``arm_release`` — the producer's own inventory rule — because a checker that asked the
generator what a complete release is would be asking the generator whether it was complete.

BLOCKER 6. ``run_arms`` emits ONE condition per invocation, and nothing said what a whole
Direct release is. So a one-bundle run was indistinguishable from a finished release, and
no verifier could tell them apart because the expectation lived nowhere.

WHERE THE EXPECTED CONDITIONS COME FROM
---------------------------------------
From the BOUND Stage-1 release's ``selector.conditions`` — re-derived here from the
release's own bytes, never from a constant in this repo and never from the Direct release
document being checked. A hard-coded three would keep passing after Stage-1 shipped a
fourth, and an incomplete release would sail under a complete-looking name: the same copied
count that put a 999-slot bundle past every hash it advertised, one level up.

WHAT MAKES THE THREE BUNDLES ONE RELEASE
----------------------------------------
Not that they exist. That they agree: every bundle must cite the SAME Stage-1 release, the
SAME scorer view, and the SAME code identity. Three bundles built from three different
program sets are three measurements, not one release — and nothing in the aggregate document
would say so.

Each condition bundle is verified INDEPENDENTLY, in full, by ``verify_arm_bundle``. A
release cannot be admitted on the strength of an inventory: an inventory says the bundles
are present, not that any of them is true.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import verify_arm_bundle as VB  # noqa: E402
import verify_arm_rules as AR  # noqa: E402
import verify_arm_view as AV  # noqa: E402
from verify_arm_report import Report, verifier_code_sha256  # noqa: E402

VERIFIER_ID = "spot.stage02.direct.release.verifier.v1"
REPORT_SCHEMA = "spot.stage02_direct_release_verification.v1"
RELEASE_SCHEMA = "spot.stage02_direct_release.v1"
RELEASE_FILE = "direct_release.json"
VERDICT_PENDING = "pending_independent_verification"


def _load_json(path: str) -> Any:
    with open(path) as fh:
        return json.load(fh)


def _bundle_args(args, bundle_dir: str, condition: str):
    """The single-bundle verifier's args, aimed at ONE condition of this release."""
    ns = argparse.Namespace(**vars(args))
    ns.bundle = bundle_dir
    ns.condition = condition
    return ns


def gate_inventory(release: dict, expected: list[str], rep: Report) -> list[dict]:
    """EXACTLY the conditions the bound Stage-1 release ships, each EXACTLY once."""
    bundles = release.get("bundles") or []
    got = [str(b.get("condition")) for b in bundles]

    rep.gate("the Direct release declares the allowlisted schema",
             release.get("schema_version") == RELEASE_SCHEMA,
             f"got {release.get('schema_version')!r}")

    duplicates = sorted({c for c in got if got.count(c) > 1})
    rep.gate("no condition was produced more than once — two bundles for one condition are "
             "two identities for one measurement",
             not duplicates, f"duplicated: {duplicates}")

    unknown = sorted(set(got) - set(expected))
    rep.gate("no bundle names a condition the bound Stage-1 release never shipped",
             not unknown, f"unknown: {unknown}; the release ships {expected}")

    missing = [c for c in expected if c not in got]
    rep.gate("every condition the bound Stage-1 release ships HAS a bundle — an incomplete "
             "release must not be indistinguishable from a complete one",
             not missing, f"missing: {missing}")

    rep.gate("the expected condition set is DERIVED from the bound release, not declared "
             "by the artifact under test",
             sorted(str(c) for c in (release.get("expected_conditions") or []))
             == sorted(expected),
             f"declared={release.get('expected_conditions')!r} derived={expected!r}")

    rep.gate("the physical bundle count equals the derived condition count",
             release.get("n_physical_bundles") == len(expected) == len(bundles),
             f"declared={release.get('n_physical_bundles')!r} derived={len(expected)}")
    return bundles


def gate_one_release(release: dict, bundles: list[dict], scorer_view_sha: str,
                     rep: Report) -> None:
    """The bundles are ONE release: same Stage-1 release, same view, same code."""
    rep.gate("every bundle cites the SAME scorer view as the release — three bundles built "
             "from three program sets would be three measurements, not one release",
             release.get("scorer_view_sha256") == scorer_view_sha,
             f"release={release.get('scorer_view_sha256')!r} derived={scorer_view_sha!r}")

    ids = [b.get("arm_bundle_run_id") for b in bundles]
    rep.gate("no two conditions share a bundle id", len(set(ids)) == len(ids), f"{ids}")

    rows = [b.get("arm_rows_sha256") for b in bundles]
    rep.gate("the conditions are distinct MEASUREMENTS — two conditions with identical arm "
             "bytes would mean one of them was never computed",
             len(set(rows)) == len(rows), f"{rows}")

    body = {k: v for k, v in release.items()
            if k not in ("direct_release_sha256", "direct_release_run_id", "verdict",
                         "admitted", "self_admitted", "verifier_id")}
    rep.gate("the Direct release document is SELF-HASHED and re-derives",
             release.get("direct_release_sha256") == AR.content_sha256(body),
             f"declared={release.get('direct_release_sha256')!r}")

    rep.gate("the PRODUCER did not admit its own release — it ships un-admitted for an "
             "independent verifier to fill",
             release.get("admitted") is False
             and release.get("self_admitted") is False
             and release.get("verifier_id") is None
             and release.get("verdict") == VERDICT_PENDING,
             f"verdict={release.get('verdict')!r} "
             f"admitted={release.get('admitted')!r}")


def verify(args) -> Report:
    rep = Report(verifier_code_sha256())

    release_path = os.path.join(args.release, RELEASE_FILE)
    if not os.path.exists(release_path):
        rep.gate(f"the Direct release document {RELEASE_FILE} is present", False,
                 f"not found under {args.release!r}")
        return rep
    rep.gate(f"the Direct release document {RELEASE_FILE} is present", True)
    release = _load_json(release_path)

    # THE EXPECTED INVENTORY, derived from the BOUND Stage-1 release — never from the
    # document under test, and never from a constant here.
    try:
        stage1 = AV.load_v3_release(args.stage1_v3_release, args.release_root)
    except AV.ScorerViewError as exc:
        rep.gate("the bound Stage-1 v3 release loads and proves its own components",
                 False, str(exc))
        return rep
    rep.gate("the bound Stage-1 v3 release loads and proves its own components", True)

    expected = [str(c) for c in (stage1["selector"].get("conditions") or [])]
    rep.gate("the bound Stage-1 release declares the conditions a complete Direct release "
             "consists of — an inventory that defaulted to three would be a guess",
             bool(expected), "the release's selector declares no conditions")
    if not expected:
        return rep

    bundles = gate_inventory(release, expected, rep)
    gate_one_release(release, bundles,
                     stage1["stage2_arm_view"]["scorer_view_sha256"], rep)

    # EVERY BUNDLE, VERIFIED IN FULL. An inventory says the bundles are present; it does
    # not say any of them is true.
    per_bundle: list[dict] = []
    code_ids: set = set()
    lock_shas: set = set()
    for entry in bundles:
        cond = str(entry.get("condition"))
        bundle_dir = os.path.join(args.release, str(entry.get("path") or ""))
        if not os.path.isdir(bundle_dir):
            rep.gate(f"the bundle for {cond} is on disk at the path the release cites",
                     False, f"{bundle_dir!r}")
            continue
        rep.gate(f"the bundle for {cond} is on disk at the path the release cites", True)

        sub = VB.verify(_bundle_args(args, bundle_dir, cond)).doc()
        per_bundle.append({"condition": cond, "verdict": sub["verdict"],
                           "n_failed": sub["n_failed"],
                           "failed_gates": sub["failed_gates"],
                           "report_sha256": sub["report_sha256"],
                           "arm_bundle_run_id":
                               sub["bound_artifact"].get("arm_bundle_run_id")})
        rep.gate(f"the {cond} bundle is INDEPENDENTLY ADMITTED in full",
                 sub["verdict"] == "ADMIT",
                 f"{sub['n_failed']} gate(s) failed: {sub['failed_gates'][:2]}")

        rep.gate(f"the {cond} bundle's id is the one the release cites",
                 sub["bound_artifact"].get("arm_bundle_run_id")
                 == entry.get("arm_bundle_run_id"),
                 f"cited={entry.get('arm_bundle_run_id')!r}")

        prov = _load_json(os.path.join(bundle_dir, "provenance.json"))
        run_binding = prov.get("run_binding") or {}
        code_ids.add((run_binding.get("code_identity") or {}).get("canonical_digest"))
        lock_shas.add((run_binding.get("environment_lock") or {}).get("sha256"))

    rep.gate("every bundle in the release was built by the SAME code — a release whose "
             "conditions came from different code is not one release",
             len(code_ids) <= 1, f"code digests: {sorted(str(c) for c in code_ids)}")

    # CROSS-BUNDLE LOCK AGREEMENT. Each bundle's lock is hard-pinned individually; this is the
    # separate claim that they are the same lock. Two conditions computed under two
    # environments are not one release, and a downstream lane differencing them would be
    # differencing the solvers as much as the biology.
    rep.gate("every bundle in the release binds the SAME solver lock, and it is the hard "
             "pin — two conditions computed under two environments are not one release",
             len(lock_shas) == 1
             and next(iter(lock_shas)) == VB.G.PINNED_SOLVER_LOCK_SHA256,
             f"locks across bundles: {sorted(str(s) for s in lock_shas)}; pinned="
             f"{VB.G.PINNED_SOLVER_LOCK_SHA256}")

    n_logical = sum(int(b.get("n_expected_arm_slots") or 0) for b in bundles)
    rep.gate("the release's logical arm count is the sum of its bundles' derived slots",
             release.get("n_logical_arms") == n_logical,
             f"declared={release.get('n_logical_arms')!r} derived={n_logical}")

    rep.bound = {
        "direct_release_run_id": release.get("direct_release_run_id"),
        "direct_release_sha256": release.get("direct_release_sha256"),
        "expected_conditions": expected,
        "n_physical_bundles": len(bundles),
        "n_logical_arms": n_logical,
        "stage1_scorer_view_canonical_sha256":
            stage1["stage1_scorer_view_canonical_sha256"],
        "registry_scorer_projection_sha256":
            stage1["registry_scorer_projection_sha256"],
        "scorer_view_sha256": stage1["stage2_arm_view"]["scorer_view_sha256"],
        "solver_lock_sha256": (next(iter(lock_shas)) if len(lock_shas) == 1 else None),
        "solver_lock_pinned_sha256": VB.G.PINNED_SOLVER_LOCK_SHA256,
        "bundles": per_bundle,
    }
    return rep


def build_parser() -> argparse.ArgumentParser:
    ap = VB.build_parser()
    ap.prog = "verify_direct_release"
    ap.description = ("Independently verify a WHOLE Direct release: every condition the "
                      "bound Stage-1 release ships, exactly once, each admitted in full.")
    for action in ap._actions:
        if action.dest == "bundle":
            action.required = False
    ap.add_argument("--release", required=True,
                    help="the Direct release directory (holding direct_release.json)")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        rep = verify(args)
    except Exception as exc:                    # a crash IS a verification failure
        rep = Report(verifier_code_sha256())
        rep.gate(f"the verifier completed ({type(exc).__name__}: {exc})", False)

    doc = dict(rep.doc(), verifier_id=VERIFIER_ID, schema_version=REPORT_SCHEMA)
    doc["report_sha256"] = AR.content_sha256(
        {k: v for k, v in doc.items() if k != "report_sha256"})
    print(rep.render())
    if doc["failed_gates"]:
        print("\nFAILED GATES:")
        for name in doc["failed_gates"]:
            print(f"  - {name}")
    if args.report:
        with open(args.report, "w") as fh:
            json.dump(doc, fh, indent=2, sort_keys=True)
            fh.write("\n")
    return 0 if doc["verdict"] == "ADMIT" else 1


if __name__ == "__main__":
    sys.exit(main())
