"""STANDALONE independent verifier for ONE Direct all-arm condition bundle.

Usage:
    python analysis/direct/verify_arm_bundle.py --bundle <dir> \\
        --de-main <h5ad> --sgrna <csv> --guide-manifest <json> \\
        --stage1-v3-release <json> --release-root <dir> \\
        [--recompute sample|all] [--report <json>]

Exit 0 = ADMIT (every gate passed); 1 = REFUSE (at least one failed, or the verifier could
not complete). A crash IS a refusal: a checker that fell over has not checked.

INDEPENDENCE RULE (test-enforced). This module and its rule modules import NOTHING from the
generator — not ``arm_bundle``, ``run_arms``, ``scorer_view``, ``arm_keys``, nor the
producer's ``hashing``. Every rule is re-derived from ROUND4_ADDENDUM (sha c4773562):

    verify_arm_rules      the arm keys, the frozen role x pole -> desired_change mapping,
                          the sign transform, the per-arm rank rule, the canonical row
                          projection, and the forbidden display-only fields
    verify_arm_view       the admitted program set, DERIVED from the bound generic v3
                          release's scorer view — never a legacy registry, never a count
    verify_arm_recompute  the masks, the base deltas, the QC and the denominators,
                          re-derived from the bound DE data
    verify_arm_gates      the artifact gates: what the bundle IS and what it BINDS
    verify_arm_science    the science gates: what RE-DERIVES
    verify_arm_report     the typed report, bound to the artifact and to this code

WHAT IT RE-OPENS AND RE-DERIVES
-------------------------------
Every emitted file is re-opened FROM DISK and hashed. The rows are re-read from the shipped
parquet — not from the document that describes them — and the arm values, the per-arm
ranks, the per-arm bytes, the whole-bundle rows hash and the run identity are all re-derived
from those bytes. A RESEALED mutation therefore still fails: changing a value changes the
rows hash, and the rows hash is an input to the run id, so a forger must either leave a hash
disagreeing with the bytes or produce a bundle that is honestly a different run — and the
base deltas are then re-derived from the DE data anyway.

M4B, AND WHAT THIS VERIFIER WILL NOT DO
---------------------------------------
It will not gate admission on a display field. ``joint_status``, Pareto tiers and
concordance are functions of TWO arms, and a quantity that exists only when two arms are put
side by side cannot decide whether ONE of them is admissible. They are not tolerated here
and defaulted off — they are FORBIDDEN, and a bundle carrying one is refused. A coherently
sign-flipped arm configuration — the one the pair-bound verifier rejected at 152/153 over
exactly such a label — must ADMIT.
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

import verify_arm_gates as G  # noqa: E402
import verify_arm_recompute as RC  # noqa: E402
import verify_arm_rules as AR  # noqa: E402
import verify_arm_science as S  # noqa: E402
import verify_arm_view as AV  # noqa: E402
from verify_arm_report import (  # noqa: E402,F401
    BUNDLE_FILE,
    BUNDLE_RUN_ID_LEN,
    EXPECTED_FILES,
    MASKS_FILE,
    PROVENANCE_FILE,
    ROWS_FILE,
    SPEC_SHA256,
    VERIFICATION_FILE,
    VERIFIER_ID,
    Report,
    verifier_code_sha256,
)

# This module is the ENTRY POINT — the CLI, and what a consumer imports. The contract
# constants are re-exported here so the seam a caller binds to does not move when the
# implementation behind it is split.
__all__ = [
    "BUNDLE_FILE", "BUNDLE_RUN_ID_LEN", "EXPECTED_FILES", "PROVENANCE_FILE",
    "ROWS_FILE", "SPEC_SHA256", "VERIFIER_ID", "Report", "verifier_code_sha256",
    "build_parser", "main", "verify",
]


def _read_parquet_rows(path: str) -> tuple[list[dict], list[str]]:
    """The SHIPPED rows, re-read from the parquet — never from the doc describing them."""
    import pandas as pd

    df = pd.read_parquet(path)
    cols = list(df.columns)
    rows = [{c: (None if pd.isna(r[c]) else r[c]) for c in cols}
            for _, r in df.iterrows()]
    return rows, cols


def _load_json(path: str) -> Any:
    with open(path) as fh:
        return json.load(fh)


# --------------------------------------------------------------------------- #
# --------------------------------------------------------------------------- #
def verify(args) -> Report:
    rep = Report(verifier_code_sha256())
    G.gate_independence(rep)

    paths = G.gate_files(args.bundle, rep)
    if paths is None:
        return rep

    doc = _load_json(paths[BUNDLE_FILE])
    prov = _load_json(paths[PROVENANCE_FILE])
    verification = _load_json(paths[VERIFICATION_FILE])
    binding = prov.get("run_binding") or {}
    rows, columns = _read_parquet_rows(paths[ROWS_FILE])
    mask_rows, _ = _read_parquet_rows(paths[MASKS_FILE])

    file_shas = G.gate_on_disk(paths, doc, prov, rep)
    G.gate_not_self_admitted(verification, rep)
    G.gate_schemas(doc, prov, rep)
    G.gate_no_display_fields(doc, prov, columns, rep)

    condition = args.condition or doc.get("condition")
    G.gate_condition(doc, prov, rows, condition, rep)
    G.gate_identity(prov, doc, rows, rep)
    G.gate_code_identity(binding, rep)

    # ---- the admitted set, derived from the bound release ----
    release = None
    if args.stage1_v3_release:
        try:
            release = AV.load_v3_release(args.stage1_v3_release, args.release_root)
        except AV.ScorerViewError as exc:
            rep.gate("the bound Stage-1 v3 release loads and proves its own components",
                     False, str(exc))
            return rep
        rep.gate("the bound Stage-1 v3 release loads and proves its own components", True)
        programs = release["programs"]
    else:
        programs = AV.programs_from_doc(_load_json(args.registry)) if args.registry else {}

    admitted = S.gate_admitted_set(doc, binding, release, programs,
                                 str(binding.get("lane")), rep)
    if admitted is None:
        return rep

    S.gate_arm_inventory(doc, rows, admitted, condition, rep)
    S.gate_arm_values_and_ranks(doc, rows, rep)
    S.gate_arm_bytes(doc, rows, rep)

    # The pinned Stage-2 inputs by their STABLE RELEASE NAMES, restated here rather than
    # imported: a name the checker borrowed from the producer is a name nobody checked. The
    # pair selection is deliberately NOT among them — an all-arm bundle has no such input,
    # and gate_inputs refuses one if it ever appears.
    named = {
        "GWCD4i.DE_stats.h5ad": args.de_main,
        "GWCD4i.DE_stats.by_guide.h5mu": args.by_guide,
        "GWCD4i.DE_stats.by_donors.h5mu": args.by_donors,
        "sgrna_library_metadata.suppl_table.csv": args.sgrna,
        "guide_contributor_manifest.json": args.guide_manifest,
        "source_registry.json": args.source_registry,
        "target_identity_map.json": args.target_identity_map,
        "donor_crosswalk.json": args.donor_crosswalk,
        "strict_replay_raw_source": args.strict_replay_source,
        "pseudobulk_source": args.pseudobulk,
        "stage01_program_registry.json": args.registry,
    }
    G.gate_inputs(binding, named, rep)
    G.gate_consumed_inputs_bound(binding, rep)
    G.gate_support_unavailable(binding, columns, rep)

    if args.expect_h5ad_sha256:
        rep.gate("the DE H5AD is the PINNED object, byte for byte",
                 AR.sha256_file(args.de_main) == args.expect_h5ad_sha256,
                 f"actual={AR.sha256_file(args.de_main)}")

    # ---- the science, recomputed ----
    manifest_doc = _load_json(args.guide_manifest) if args.guide_manifest else None
    contributors = RC.contributors_from_manifest(manifest_doc) if manifest_doc else {}

    all_targets = sorted({str(r["target_id"]) for r in rows})
    targets = (None if args.recompute == "all"
               else RC.deterministic_sample(all_targets, args.sample_size))
    genes = RC.read_pooled_meta(args.de_main, condition)[0]
    recomputed = RC.recompute(
        de_main=args.de_main, sgrna=args.sgrna, condition=condition,
        programs=programs, admitted=admitted, contributors=contributors,
        universe=genes, targets=targets)

    S.gate_recompute(rows, recomputed, args.recompute, rep)
    S.gate_evidence_bindings(binding, recomputed, manifest_doc, args.guide_manifest,
                             recomputed["gene_universe_sha256"], mask_rows, rep)

    rep.bound = {
        "arm_bundle_run_id": prov.get("arm_bundle_run_id"),
        "arm_bundle_run_sha256": prov.get("arm_bundle_run_sha256"),
        "condition": condition,
        "lane": binding.get("lane"),
        "arm_rows_sha256": doc.get("arm_rows_sha256"),
        "scorer_view_sha256": doc.get("scorer_view", {}).get("scorer_view_sha256"),
        "stage1_scorer_view_canonical_sha256": (
            release["stage1_scorer_view_canonical_sha256"] if release else None),
        "registry_scorer_projection_sha256": (
            release["registry_scorer_projection_sha256"] if release else None),
        "artifact_sha256": file_shas,
        "n_admitted_programs": len(admitted),
        "n_arm_slots": doc.get("n_arm_slots"),
        "n_arm_rows": doc.get("n_arm_rows"),
        "recompute_mode": args.recompute,
        "n_targets_recomputed": recomputed["n_projected"],
        "n_masks_rederived": recomputed["n_targets"],
        "n_targets_in_bundle": len(all_targets),
        "arm_inventory": sorted(
            ({"arm_key": a["arm_key"], "arm_rows_sha256": a.get("arm_rows_sha256")}
             for a in (doc.get("arms") or []) if a.get("arm_key")),
            key=lambda a: a["arm_key"]),
    }
    return rep


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="verify_arm_bundle",
        description="Independently verify ONE Direct all-arm condition bundle. "
                    "Fail-closed: exit 0 admits, 1 refuses.")
    ap.add_argument("--bundle", required=True, help="the bundle directory")
    ap.add_argument("--condition", default=None)
    ap.add_argument("--de-main", required=True)
    ap.add_argument("--sgrna", required=True)
    ap.add_argument("--by-guide", default=None)
    ap.add_argument("--by-donors", default=None)
    ap.add_argument("--guide-manifest", default=None)
    ap.add_argument("--source-registry", default=None)
    ap.add_argument("--target-identity-map", default=None)
    ap.add_argument("--donor-crosswalk", default=None)
    ap.add_argument("--strict-replay-source", default=None)
    ap.add_argument("--pseudobulk", default=None)
    ap.add_argument("--registry", default=None,
                    help="the v3 program registry (the synthetic fixture lane's program "
                         "source; a release-grade lane must bind --stage1-v3-release)")
    ap.add_argument("--selection", default=None,
                    help="a pair selection, ONLY so the verifier can prove the bundle did "
                         "not bind it")
    ap.add_argument("--stage1-v3-release", default=None,
                    help="the generic spot.stage01_v3_release.v1 release")
    ap.add_argument("--release-root", default=None,
                    help="the EXPLICITLY STAGED root the release's component paths resolve "
                         "against; never a machine default")
    ap.add_argument("--recompute", choices=("sample", "all"), default="sample",
                    help="'all' is the production mode: every base delta re-derived")
    ap.add_argument("--sample-size", type=int, default=8)
    ap.add_argument("--expect-h5ad-sha256", default=None)
    ap.add_argument("--report", default=None, help="write the typed report here")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        rep = verify(args)
    except Exception as exc:                    # a crash IS a verification failure
        rep = Report(verifier_code_sha256())
        rep.gate(f"the verifier completed ({type(exc).__name__}: {exc})", False)

    doc = rep.doc()
    print(rep.render())
    if doc["failed_gates"]:
        print("\nFAILED GATES:")
        for name in doc["failed_gates"]:
            detail = next(g["detail"] for g in doc["gates"] if g["gate"] == name)
            print(f"  - {name}" + (f"\n      {detail}" if detail else ""))
    if args.report:
        with open(args.report, "w") as fh:
            json.dump(doc, fh, indent=2, sort_keys=True)
            fh.write("\n")
    return 0 if doc["verdict"] == "ADMIT" else 1


if __name__ == "__main__":
    sys.exit(main())
