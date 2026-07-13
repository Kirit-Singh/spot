"""THE PER-LANE RELEASE INVENTORY: exactly the bundles that lane must ship, by their bytes.

A lane release is not "the directories that happen to be there". It is an EXACT inventory —
Direct 3 condition bundles, temporal 6 ordered pairs, pathway 6 condition x source — bound
to every byte each bundle stands on, and content-addressed so that editing any of it changes
its name.

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
