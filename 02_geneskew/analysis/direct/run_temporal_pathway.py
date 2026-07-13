"""THE TEMPORAL PATHWAY PRODUCER CLI + run hook.

One content-addressed bundle per (ordered condition pair, pinned source) over the temporal DiD
rankings the temporal all-arm bundle already ships. It reuses existing temporal rankings; it does
NOT recompute the temporal difference-in-differences and it launches no production compute.

The run hook enumerates the release's invocations — 6 ordered condition pairs x GO-BP (the sole
release source; Reactome is parked) — as a plan of invocations, never a launch. The producer and
verifier stay source-generic; only the release list is GO-BP.
"""
from __future__ import annotations

import argparse
import json
import os
from typing import Any, Optional

from . import temporal_pathway as tp

# THE RELEASE SOURCE. The producer and verifier are source-GENERIC (they read the source from
# the bundle and take --gene-sets), but the production/release list for this lane is GO-BP ONLY.
# A different pinned source may be run through the same generic producer, but it is not part of
# this release and nothing here waits on it.
RELEASE_SOURCES = ("go_bp",)

# THE TEMPORAL PATHWAY LANE descriptor for run-manifest / invocation support. Self-contained so
# this commit is narrowly portable; integrating it into the frozen aggregate topology (which
# expects EXACTLY 3 direct / 6 temporal / 6 pathway physical bundles) is a separate cross-lane
# change owned by the aggregate lane.
LANE_TEMPORAL_PATHWAY = "temporal_pathway"
LANE_ARTIFACTS = (tp.BUNDLE_FILE, tp.PROVENANCE_FILE, tp.CONVERGENCE_FILE)
# 6 ordered condition pairs x GO-BP (one release source) = 6 invocations. NOT 12.
EXPECTED_INVOCATIONS = 6


def _write_json(path: str, obj: Any) -> None:
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True)


def run(args) -> dict[str, Any]:
    result = tp.build_temporal_pathway(
        bundle_dir=args.temporal_bundle_dir, gene_sets_path=args.gene_sets,
        env_lock_path=getattr(args, "env_lock", None),
        allow_dirty_tree=getattr(args, "allow_dirty_tree", False))
    out_dir = os.path.join(args.out_root, result["run_id"])
    os.makedirs(out_dir, exist_ok=True)
    _write_json(os.path.join(out_dir, tp.BUNDLE_FILE), result["doc"])
    _write_json(os.path.join(out_dir, tp.PROVENANCE_FILE), result["provenance"])
    _write_json(os.path.join(out_dir, tp.CONVERGENCE_FILE), result["convergence"])
    # FAIL-CLOSED, not self-admission: the independent verifier reads the shipped bytes and
    # decides. A producer that admitted its own output would be marking its own homework.
    _write_json(os.path.join(out_dir, tp.VERIFICATION_FILE), {
        "schema_version": tp.SCHEMA_VERIFICATION_STUB,
        "temporal_pathway_run_id": result["run_id"],
        "temporal_pathway_run_sha256": result["run_sha256"],
        "generator_is_not_verifier": True, "fail_closed": True,
        "verifier_id": None, "verdict": "pending_independent_verification", "admitted": False,
        "verified_paths": [tp.BUNDLE_FILE, tp.PROVENANCE_FILE, tp.CONVERGENCE_FILE],
    })
    return dict(result, out_dir=out_dir)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m direct.run_temporal_pathway",
        description="Emit ONE (ordered condition pair, source) temporal pathway enrichment "
                    "bundle over the temporal DiD ranking. Descriptive pathway context over the "
                    "temporal ranking; NOT a new estimand, NO convergence, NO p/q, NO combined "
                    "objective.")
    ap.add_argument("--temporal-bundle-dir", required=True,
                    help="an ADMITTED native temporal all-arm bundle dir "
                         "(output/temporal/<From>__to__<To>/) with its rankings/")
    ap.add_argument("--gene-sets", required=True,
                    help="a pinned, licensed gene-set bundle (GO-BP or Reactome)")
    ap.add_argument("--env-lock", default=None)
    ap.add_argument("--allow-dirty-tree", action="store_true")
    ap.add_argument("--out-root", required=True,
                    help="output directory; the bundle lands under <out-root>/<run_id>")
    return ap


def main(argv: Optional[list[str]] = None) -> dict[str, Any]:
    args = build_parser().parse_args(argv)
    r = run(args)
    print(json.dumps({k: r[k] for k in (
        "run_id", "from_condition", "to_condition", "source", "n_records", "n_arm_slots",
        "out_dir")}, indent=2))
    return r


# --------------------------------------------------------------------------- #
# The run HOOK: enumerate the full release's invocations. A PLAN, never a launch.
# --------------------------------------------------------------------------- #
def enumerate_invocations(*, temporal_output_root: str, gene_sets_by_source: dict[str, str],
                          out_root: str,
                          sources: tuple[str, ...] = RELEASE_SOURCES) -> list[dict[str, Any]]:
    """The RELEASE invocations of a complete temporal pathway lane: 6 ordered pairs x GO-BP = 6.

    Reuses the EXISTING temporal rankings under ``temporal_output_root``/<From>__to__<To>/ — it
    discovers the ordered-pair bundle dirs (never hardcodes conditions), pairs each with each
    RELEASE source (GO-BP only by default), and returns the argv plan. It runs NOTHING and waits
    on no other source. ``sources`` stays a parameter so the same generic producer can be driven
    by another source out-of-release, but the release default is GO-BP alone.
    """
    pair_dirs = sorted(
        d for d in os.listdir(temporal_output_root)
        if "__to__" in d and os.path.isdir(os.path.join(temporal_output_root, d)))
    plan: list[dict[str, Any]] = []
    for d in pair_dirs:
        for source in sources:
            gs = gene_sets_by_source.get(source)
            plan.append({
                "ordered_pair": d, "source": source,
                "argv": ["python", "-m", "direct.run_temporal_pathway",
                         "--temporal-bundle-dir", os.path.join(temporal_output_root, d),
                         "--gene-sets", gs or f"<gene-sets:{source}>",
                         "--out-root", out_root],
            })
    return plan


if __name__ == "__main__":
    main()
