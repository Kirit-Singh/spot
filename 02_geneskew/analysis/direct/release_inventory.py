"""THE PER-LANE RELEASE INVENTORY: exactly the bundles that lane must ship, by their bytes.

A lane release is not "the directories that happen to be there". It is an EXACT inventory —
Direct 3 condition bundles, temporal 6 ordered pairs, pathway 6 condition x source — bound
to every byte each bundle stands on, and content-addressed so that editing any of it changes
its name.

THE RECONCILIATION (deliberate, and the two shapes are NOT the same)
-------------------------------------------------------------------
Two independent verifiers already ship, and they admit a release in two different ways.
Neither is wrong, and neither is bent to match the other:

  ADMIT_IN_PLACE   (Direct, W10)   `direct_release.json`
      The producer writes the inventory UN-ADMITTED (`verdict: pending_independent_verification`,
      `admitted: false`, `self_admitted: false`, `verifier_id: null`) and the independent
      verifier fills those four fields in, in the same file. This is only honest because the
      artifact's own hash — `direct_release_sha256` — is taken over the body EXCLUDING those
      four fields: admitting a release therefore cannot change what the release IS. A reader
      who did not know that would think the verifier had rewritten the producer's artifact.

  SEPARATE_ENVELOPE (temporal, W11 99eaa81; pathway)
      The producer's inventory is IMMUTABLE and stays `pending` forever. The independent
      verifier emits a SEPARATE content-addressed envelope that BINDS that inventory by id
      and raw hash. Nothing the producer wrote is ever touched.

The envelope form is the stronger of the two — an artifact nobody may rewrite is easier to
reason about than one whose hash is carefully blind to the fields that get rewritten — so
pathway (which has no producer yet) takes it. Direct keeps its in-place form because it is
ALREADY SHIPPED AND ADMITTED, and bending W10's contract to match a preference would
invalidate an admission that is currently valid. The aggregate reads both, natively.
"""
from __future__ import annotations

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

ADMIT_IN_PLACE = "admit_in_place"
SEPARATE_ENVELOPE = "separate_envelope"
ADMISSION_MODE_OF = {
    LANE_DIRECT: ADMIT_IN_PLACE,
    LANE_TEMPORAL: SEPARATE_ENVELOPE,
    LANE_PATHWAY: SEPARATE_ENVELOPE,
}

# The four fields an ADMIT_IN_PLACE verifier fills in, and which the artifact's own hash is
# therefore blind to. This is what makes admitting a release identity-preserving.
ADMISSION_FIELDS = ("verdict", "admitted", "self_admitted", "verifier_id")

VERDICT_PENDING = "pending_independent_verification"
SELF_HASH_FIELD_OF = {
    LANE_DIRECT: "direct_release_sha256",
    LANE_TEMPORAL: "release_id",
    LANE_PATHWAY: "release_id",
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


def _files_of(bundle_dir: str) -> dict[str, dict[str, str]]:
    """Every byte in the bundle, by its bundle-relative path. Nothing is skipped."""
    out: dict[str, dict[str, str]] = {}
    for base, _dirs, names in os.walk(bundle_dir):
        for name in sorted(names):
            path = os.path.join(base, name)
            rel = os.path.relpath(path, bundle_dir).replace(os.sep, "/")
            entry = {"raw_sha256": file_sha256(path)}
            if rel.endswith(".json"):
                import json
                try:
                    with open(path) as fh:
                        entry["canonical_sha256"] = content_hash(json.load(fh))
                except (OSError, ValueError):
                    raise RunManifestError(
                        f"{rel} is not readable JSON; a release cannot bind bytes nobody "
                        "can open") from None
            out[rel] = entry
    return out


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
        bid = str(inv.get("bundle_id"))
        ids.append(bid)
        arm_keys += [str(a.get("arm_key")) for a in (inv.get("arms") or [])]
        entries.append({
            "bundle_id": bid,
            "context": dict(inv.get("context") or {}),
            "relative_dir": os.path.relpath(d, root).replace(os.sep, "/"),
            "n_arms": len(inv.get("arms") or []),
            "files": _files_of(d),
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
    doc = dict(body, **{f: v for f, v in (
        ("verdict", VERDICT_PENDING), ("admitted", False),
        ("self_admitted", False), ("verifier_id", None))})
    doc[SELF_HASH_FIELD_OF[lane]] = content_hash(body)
    return doc
