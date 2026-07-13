"""THE STAGE-2 RUN MANIFEST: one artifact that binds every lane output of one run.

WHY THIS EXISTS (round-3 MAJOR)
-------------------------------
Each lane emits its own artifact and its own identity — ``screen.parquet`` under a
``run_id``, ``temporal.parquet`` under a ``temporal_run_id``, ``pathway.json`` under a
``pathway_run_id``. Every one of them is verified, content-addressed and honest.

What did NOT exist was anything that said WHICH of them belong to the same run. A reader
handed three directories had no way to know they were the same science, and nothing stopped
a screen from one commit being cited beside a pathway result from another. "The per-lane
outputs are the contract" is a defensible position right up until somebody has to assemble
them, and then it silently becomes the reader's problem.

So this is the aggregate: it names every lane invocation of a complete Stage-2 run, binds
each one's id and artifact hashes, binds the shared code identity, and hashes the whole
thing. It PRODUCES nothing scientific — it is an index, and it says so.

WHAT A COMPLETE STAGE-2 RUN IS
------------------------------
    Direct   (+ Pareto) : 3 invocations — one per condition
    Temporal            : 6 invocations — one per ORDERED condition pair
    Pathway             : 6 invocations — 3 conditions x 2 gene-set sources

Fifteen invocations. Perturb2State is NOT part of it (see ``P2S_DISPOSITION``): it is a
secondary method, explicitly DEFERRED, and "complete Stage-2" means
Direct + Pareto + temporal + pathway.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Any, Optional

from . import code_digest
from .hashing import content_hash, file_sha256

SCHEMA_VERSION = "spot.stage02_run_manifest.v1"
MANIFEST_ID = "spot.stage02.run_manifest.v1"

LANE_DIRECT = "direct"
LANE_TEMPORAL = "temporal"
LANE_PATHWAY = "pathway"
LANES = (LANE_DIRECT, LANE_TEMPORAL, LANE_PATHWAY)

# WHAT each lane ships. A manifest that named a file the lane does not emit would be
# describing a run that did not happen.
LANE_ARTIFACTS = {
    LANE_DIRECT: ("screen.parquet", "masks.parquet", "contributing_guides.parquet",
                  "guide_support.parquet", "donor_support.parquet", "axis.json",
                  "gene_universe.json", "input_manifest.json", "provenance.json",
                  "verification.json"),
    LANE_TEMPORAL: ("temporal.parquet", "endpoints.parquet",
                    "temporal_provenance.json", "temporal_verification.json"),
    LANE_PATHWAY: ("pathway.json", "pathway_provenance.json",
                   "pathway_verification.json"),
}

# THE EXPECTED MATRIX of a complete run. Stated, so a partial run is visibly partial.
EXPECTED_INVOCATIONS = {LANE_DIRECT: 3, LANE_TEMPORAL: 6, LANE_PATHWAY: 6}
N_EXPECTED = sum(EXPECTED_INVOCATIONS.values())          # 15

# --------------------------------------------------------------------------- #
# PERTURB2STATE — EXPLICITLY DEFERRED (round-3 MAJOR).
#
# P2S is a SECONDARY method. It is not part of this run, it is not part of "complete
# Stage-2", and it does not gate the run. Saying nothing about it would leave a reader to
# infer either that it ran (it did not) or that it was forgotten (it was not), so it is
# named here with its state.
# --------------------------------------------------------------------------- #
P2S_DISPOSITION = {
    "component": "perturb2state",
    "state": "deferred_not_part_of_this_run",
    "tier": "secondary_method",
    "gates_the_run": False,
    "complete_stage2_is": ("direct", "pareto", "temporal", "pathway"),
}


class RunManifestError(ValueError):
    """A lane output cannot be bound. Refuse; never invent."""


def bind_lane(lane: str, out_dir: str, run_id: str,
              expected: Optional[tuple] = None) -> dict[str, Any]:
    """Bind ONE lane invocation: its id, its directory, every artifact it shipped.

    An artifact the lane is supposed to emit and did not is a REFUSAL, not a gap: a
    manifest that quietly omitted a missing file would certify an incomplete run.
    """
    if lane not in LANES:
        raise RunManifestError(f"unknown lane {lane!r}; expected one of {list(LANES)}")
    names = expected if expected is not None else LANE_ARTIFACTS[lane]

    files: dict[str, Optional[str]] = {}
    missing = []
    for name in names:
        path = os.path.join(out_dir, name)
        if os.path.exists(path):
            files[name] = file_sha256(path)
        else:
            files[name] = None
            missing.append(name)
    if missing:
        raise RunManifestError(
            f"{lane} run {run_id!r} is missing {missing}; a manifest that omitted a "
            "missing artifact would certify an incomplete run as complete")

    return {
        "lane": lane,
        "run_id": run_id,
        "out_dir": os.path.basename(out_dir.rstrip(os.sep)),
        "files": files,
        "artifact_sha256": content_hash(files),
    }


def build(*, invocations: list[dict[str, Any]], out_path: str,
          allow_partial: bool = False,
          code_identity: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """The aggregate manifest over every lane invocation of ONE Stage-2 run."""
    by_lane: dict[str, list[dict[str, Any]]] = {lane: [] for lane in LANES}
    for inv in invocations:
        by_lane[inv["lane"]].append(inv)

    counts = {lane: len(by_lane[lane]) for lane in LANES}
    complete = counts == EXPECTED_INVOCATIONS
    if not complete and not allow_partial:
        raise RunManifestError(
            f"this is a PARTIAL run: {counts} against the expected "
            f"{EXPECTED_INVOCATIONS}. A partial run may be manifested — pass "
            "allow_partial — but it is never silently called complete")

    code = code_identity or code_digest.run_binding()
    doc = {
        "schema_version": SCHEMA_VERSION,
        "manifest_id": MANIFEST_ID,
        "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        # THIS IS AN INDEX. It produces no science and it says so.
        "produces_scientific_values": False,
        "binds_lane_outputs": True,
        "code_identity": code,
        "expected_invocations": dict(EXPECTED_INVOCATIONS),
        "n_expected_invocations": N_EXPECTED,
        "invocation_counts": counts,
        "n_invocations": sum(counts.values()),
        "complete": complete,
        "perturb2state": P2S_DISPOSITION,
        "invocations": sorted(invocations,
                              key=lambda i: (i["lane"], i["run_id"])),
    }
    doc["manifest_sha256"] = content_hash(
        {k: v for k, v in doc.items() if k != "created_at"})
    with open(out_path, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    doc["path"] = out_path
    return doc


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="Bind every lane output of one Stage-2 run into a run manifest")
    ap.add_argument("--direct", nargs="*", default=[],
                    help="direct lane output directories (one per condition)")
    ap.add_argument("--temporal", nargs="*", default=[],
                    help="temporal lane output directories (one per ordered pair)")
    ap.add_argument("--pathway", nargs="*", default=[],
                    help="pathway lane output directories (condition x gene-set source)")
    ap.add_argument("--allow-partial", action="store_true")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    invocations = []
    for lane, dirs in ((LANE_DIRECT, args.direct), (LANE_TEMPORAL, args.temporal),
                       (LANE_PATHWAY, args.pathway)):
        for d in dirs:
            invocations.append(
                bind_lane(lane, d, run_id=os.path.basename(d.rstrip(os.sep))))

    doc = build(invocations=invocations, out_path=args.out,
                allow_partial=args.allow_partial)
    print(json.dumps({k: v for k, v in doc.items() if k != "invocations"},
                     indent=2, sort_keys=True))
    return 0 if doc["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
