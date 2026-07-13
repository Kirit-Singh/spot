"""THE PER-LANE RELEASE INVENTORY: exactly the bundles that lane must ship, by their bytes.

A lane release is not "the directories that happen to be there". It is an EXACT inventory —
Direct 3 condition bundles, temporal 6 ordered pairs, pathway 6 condition x source — bound
to every byte each bundle stands on, and content-addressed so that editing any of it changes
its name.

THE ORDER OF OPERATIONS (and the circularity this closes)
--------------------------------------------------------
The external admission BINDS the inventory by hash. So the inventory must EXIST BEFORE the
independent verifier runs — it cannot be manufactured afterwards by the aggregate, because
then the admission would be binding something that did not exist when it was written.
`run_release` used to create a missing inventory itself, which made the pathway lane
impossible to run at all: the admission needed the inventory, and the inventory was only
written by the step that needed the admission.

    1. the lane PRODUCER emits its bundles          (Direct 3 / temporal 6 / pathway 6)
    2. THIS MODULE'S CLI writes the PENDING inventory over those exact bundle dirs
    3. the INDEPENDENT verifier reads the bundles back, and admits — binding (2) by hash
    4. `run_release` CONSUMES (2) and (3). It manufactures nothing.

THE PRODUCER NEVER ADMITS ITSELF — IN ANY LANE
---------------------------------------------
Every lane's inventory is IMMUTABLE and ships PENDING:

    verdict: pending_independent_verification | admitted: false
    self_admitted: false                      | verifier_id: null

and the independent verifier emits a SEPARATE, content-addressed report that BINDS that
inventory by its hash. Nothing the producer wrote is ever touched by an admission.

I previously modelled Direct as ADMIT_IN_PLACE — the verifier filling those four fields into
`direct_release.json` itself. That was WRONG, and it was wrong in the dangerous direction:
W10 does not fill them in, it GATES them ("the PRODUCER did not admit its own release — it
ships un-admitted", `verify_direct_release.py`). So an aggregate that tolerated an admitted
producer file would have been tolerating a file somebody had EDITED. It is now refused.

The lane admissions, all SEPARATE:

    direct    direct_release.json  (pending, immutable)
              + direct_release_admission.json   spot.stage02_direct_release_verification.v1
    temporal  temporal_arm_release.json
              + temporal_arm_external_admission.json      (W11 99eaa81)
    pathway   pathway_arm_release.json
              + pathway_arm_external_admission.json
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from .arm_topology import LANE_DIRECT, LANE_PATHWAY, LANE_TEMPORAL, RunManifestError
from .hashing import content_hash, file_sha256

SCHEMA_OF = {
    LANE_DIRECT: "spot.stage02_direct_release.v1",
    LANE_TEMPORAL: "spot.stage02_temporal_arm_release.v1",
    LANE_PATHWAY: "spot.stage02_pathway_arm_release.v1",
}

# The file each lane's inventory lives in. Direct's is W10's, verbatim.
INVENTORY_FILE_OF = {
    LANE_DIRECT: "direct_release.json",
    LANE_TEMPORAL: "temporal_arm_release.json",
    LANE_PATHWAY: "pathway_arm_release.json",
}

SEPARATE_ENVELOPE = "separate_envelope"
ADMISSION_MODE_OF = {lane: SEPARATE_ENVELOPE
                     for lane in (LANE_DIRECT, LANE_TEMPORAL, LANE_PATHWAY)}

# The lane's independent admission report — a SEPARATE artifact, never the inventory.
ADMISSION_FILE_OF = {
    LANE_DIRECT: "direct_release_admission.json",
    LANE_TEMPORAL: "temporal_arm_external_admission.json",
    LANE_PATHWAY: "pathway_arm_external_admission.json",
}

# The fields the producer ships un-filled, and which its own hash is blind to.
ADMISSION_FIELDS = ("verdict", "admitted", "self_admitted", "verifier_id")

VERDICT_PENDING = "pending_independent_verification"
SELF_HASH_FIELD_OF = {
    LANE_DIRECT: "direct_release_sha256",
    LANE_TEMPORAL: "release_id",
    LANE_PATHWAY: "release_id",
}
# Direct also carries a short run id, as W10's `arm_release.py` emits it.
RUN_ID_FIELD_OF = {LANE_DIRECT: "direct_release_run_id"}
RUN_ID_LEN = 16

# EXACTLY what each lane's independent verifier excludes when it re-derives the self-hash.
SELF_HASH_EXCLUDES_OF = {
    LANE_DIRECT: ("direct_release_sha256", "direct_release_run_id", "verdict", "admitted",
                  "self_admitted", "verifier_id"),
    LANE_TEMPORAL: ("release_id",),
    LANE_PATHWAY: ("release_id",),
}

# EXACTLY this many bundles. Not "at least", not "whatever was found".
def expected_bundle_count(lane: str, n_conditions: int, n_sources: int) -> int:
    if lane == LANE_DIRECT:
        return n_conditions
    if lane == LANE_TEMPORAL:
        return n_conditions * (n_conditions - 1)
    if lane == LANE_PATHWAY:
        return n_conditions * n_sources
    raise RunManifestError(f"unknown lane {lane!r}")


RANKINGS_DIR = "rankings/"


def _files_of(bundle_dir: str) -> tuple:
    """Every byte in the bundle. RANKINGS are listed SEPARATELY, as the verifier reads them:
    it compares the inventory's ranking list against the paths the ARMS bind, and a ranking
    hidden among the ordinary files is one nothing can cross-check."""
    files: dict[str, dict[str, str]] = {}
    rankings: dict[str, dict[str, str]] = {}
    for base, _dirs, names in os.walk(bundle_dir):
        for name in sorted(names):
            path = os.path.join(base, name)
            rel = os.path.relpath(path, bundle_dir).replace(os.sep, "/")
            entry = {"raw_sha256": file_sha256(path)}
            if rel.endswith(".json"):
                try:
                    with open(path) as fh:
                        entry["canonical_sha256"] = content_hash(json.load(fh))
                except (OSError, ValueError):
                    raise RunManifestError(
                        f"{rel} is not readable JSON; a release cannot bind bytes nobody "
                        "can open") from None
            (rankings if rel.startswith(RANKINGS_DIR) else files)[rel] = entry
    return files, rankings


def build(*, lane: str, bundle_dirs: list[str], root: str, expect_bundles: int,
          stage1: dict[str, Any], env_lock_sha256: str,
          producer_commit: Optional[str] = None,
          verifier_commit: Optional[str] = None) -> dict[str, Any]:
    """The lane's inventory: EXACT count, every byte, content-addressed, UN-ADMITTED."""
    if len(bundle_dirs) != expect_bundles:
        raise RunManifestError(
            f"the {lane} release ships {len(bundle_dirs)} bundle(s); this lane is exactly "
            f"{expect_bundles}. A release that is 'nearly' complete is not one")

    entries, ids, arm_keys = [], [], []
    for d in sorted(bundle_dirs):
        import json
        inv_path = os.path.join(d, "arm_bundle.json")
        if not os.path.exists(inv_path):
            raise RunManifestError(f"{d}: no arm_bundle.json — this is not a bundle")
        with open(inv_path) as fh:
            inv = json.load(fh)
        # NATIVE identity: read the REAL producer fields (Direct arm_bundle_run_id,
        # pathway pathway_run_id, pathway_arm_key), never a top-level lane/bundle_id the
        # real producers do not write.
        from . import bundle_normalize as BN
        try:
            norm = BN.normalize(inv)
        except BN.BundleShapeError as exc:
            raise RunManifestError(f"{d}: {exc}") from None
        bid = norm["bundle_id"]
        ids.append(bid)
        arm_keys += list(norm["arm_keys"])
        files, rankings = _files_of(d)
        entries.append({
            "bundle_id": bid,
            "context": dict(norm["context"]),
            "relative_dir": os.path.relpath(d, root).replace(os.sep, "/"),
            "n_arms": len(inv.get("arms") or []),
            "files": files,
            "rankings": rankings,
        })

    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise RunManifestError(
            f"the {lane} release cites bundle id(s) {dupes} more than once; a duplicate "
            "cannot stand in for a missing bundle")
    dupe_keys = sorted({k for k in arm_keys if arm_keys.count(k) > 1})
    if dupe_keys:
        raise RunManifestError(
            f"the {lane} release fills arm slot(s) {dupe_keys[:3]} twice")

    body: dict[str, Any] = {
        "schema_version": SCHEMA_OF[lane],
        "lane": lane,
        "release_id_rule": "sha256(canonical JSON excluding the id and admission fields)",
        "n_bundles": len(entries),
        "n_logical_arms": len(arm_keys),
        "arm_keys": sorted(arm_keys),
        "bundles": sorted(entries, key=lambda b: b["bundle_id"]),
        # WHAT THE LANE STOOD ON. Bound, so a release cannot be re-attributed later.
        "stage1_binding": dict(stage1),
        "solver_lock_sha256": env_lock_sha256,
        "producer_commit": producer_commit,
        "independent_verifier_commit": verifier_commit,
        # THE PRODUCER DOES NOT ADMIT ITS OWN RELEASE.
        "external_admission": {"status": "pending"},
    }
    doc = dict(body, verdict=VERDICT_PENDING, admitted=False,
               self_admitted=False, verifier_id=None)

    # THE SELF-HASH, over exactly what the INDEPENDENT VERIFIER re-derives it over. Direct's
    # is blind to the four fields W10's verifier reads (it never writes them, but its own
    # rule excludes them); temporal/pathway hash everything but the id. A producer whose hash
    # rule differed from the verifier's would ship an inventory nobody could confirm.
    field = SELF_HASH_FIELD_OF[lane]
    excludes = SELF_HASH_EXCLUDES_OF[lane]
    if lane in RUN_ID_FIELD_OF:
        doc[RUN_ID_FIELD_OF[lane]] = content_hash(
            {k: v for k, v in doc.items() if k not in excludes})[:RUN_ID_LEN]
    doc[field] = content_hash({k: v for k, v in doc.items() if k not in excludes})
    return doc


def main(argv=None) -> int:
    """Write ONE lane's PENDING inventory over the bundles that lane actually emitted.

    This runs BEFORE the independent verifier, because the verifier's admission binds this
    file by hash. It writes no verdict: admitting is not the producer's to do.
    """
    import argparse

    from .arm_topology import load_release
    from .hashing import file_sha256 as _sha

    ap = argparse.ArgumentParser(
        prog="build_release_inventory",
        description="Write a lane's PENDING release inventory from its emitted bundles. "
                    "Run this BEFORE the independent verifier: the admission binds it.")
    ap.add_argument("--lane", required=True,
                    choices=[LANE_DIRECT, LANE_TEMPORAL, LANE_PATHWAY])
    ap.add_argument("--bundles-root", required=True)
    ap.add_argument("--release", required=True)
    ap.add_argument("--release-root", required=True)
    ap.add_argument("--env-lock", required=True)
    ap.add_argument("--producer-commit", default=None)
    ap.add_argument("--verifier-commit", default=None)
    ap.add_argument("--out", default=None,
                    help="default: <bundles-root>/<the lane's canonical inventory name>")
    args = ap.parse_args(argv)

    from . import run_release as RR

    rel = load_release(args.release, args.release_root)
    dirs = RR.discover(args.bundles_root, args.lane)
    want = expected_bundle_count(args.lane, len(rel["conditions"]),
                                 len(rel["gene_set_sources"]))
    stage1 = {
        "release_canonical_sha256": rel["release_canonical_sha256"],
        "registry_scorer_view_canonical_sha256":
            rel["registry_scorer_view_canonical_sha256"],
        "registry_scorer_projection_sha256":
            rel["registry_scorer_projection_sha256"],
        "admitted_programs": rel["programs"],
        "conditions": rel["conditions"],
    }
    try:
        doc = build(lane=args.lane, bundle_dirs=dirs, root=args.bundles_root,
                    expect_bundles=want, stage1=stage1,
                    env_lock_sha256=_sha(args.env_lock),
                    producer_commit=args.producer_commit,
                    verifier_commit=args.verifier_commit)
    except RunManifestError as exc:
        print(json.dumps({"written": False, "error": str(exc)}, indent=2))
        return 1

    out = args.out or os.path.join(args.bundles_root, INVENTORY_FILE_OF[args.lane])
    with open(out, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print(json.dumps({
        "written": out,
        "lane": args.lane,
        "n_bundles": doc["n_bundles"],
        "n_logical_arms": doc["n_logical_arms"],
        "self_hash_field": SELF_HASH_FIELD_OF[args.lane],
        "self_hash": doc[SELF_HASH_FIELD_OF[args.lane]],
        "verdict": doc["verdict"],
        "admitted": doc["admitted"],
        "next": f"the INDEPENDENT verifier now admits this, binding "
                f"{SELF_HASH_FIELD_OF[args.lane]}",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
