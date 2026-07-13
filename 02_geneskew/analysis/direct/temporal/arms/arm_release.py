"""``temporal_arm_release.json`` — the content-addressed ROOT inventory of one release.

WHAT IT IS
----------
One document at the release root that names EVERY physical bundle and EVERY native file
(and every ranking file) it ships, each by its bundle-relative path and content hash. It is
the immutable inventory a downstream stage — and the independent verifier — binds: an
inventory whose bytes can be swapped is not an inventory.

WHAT IT IS NOT
--------------
It carries NO admission. ``external_verification.status = pending`` says so out loud: the
producer has emitted the bytes, but the authoritative ``temporal_verification.json`` is
written SEPARATELY by the independent verifier (W11), which binds this immutable inventory.
The producer does not admit its own release.

SELF-ADDRESSED
--------------
``release_id`` is the content hash of the inventory over everything EXCEPT ``release_id``
itself — so the inventory proves its own identity, and a reader can recompute it. Paths are
all bundle-relative; no absolute path, hostname or timestamp enters it, so it is byte-stable
and portable across hosts.
"""
from __future__ import annotations

import os
from typing import Any

from ...hashing import content_hash, sha256_hex
from . import arm_bundle, arm_report

SCHEMA_RELEASE = "spot.stage02_temporal_arm_release.v1"
RELEASE_FILENAME = "temporal_arm_release.json"
RELEASE_ID_LEN = 16


def _bundle_file_hashes(out_dir: str) -> dict[str, dict[str, str]]:
    """Every native file in a bundle dir, by bundle-relative POSIX path, with its hashes.

    Includes the ranking files. A downstream binder opens each and recomputes; the release
    is only as trustworthy as the bytes it can point somebody at.
    """
    files: dict[str, dict[str, str]] = {}
    for base, _dirs, filenames in os.walk(out_dir):
        for fn in sorted(filenames):
            path = os.path.join(base, fn)
            rel = os.path.relpath(path, out_dir).replace(os.sep, "/")
            with open(path, "rb") as fh:
                raw = fh.read()
            entry = {"raw_sha256": sha256_hex(raw)}
            if rel.endswith(".json"):
                import json
                entry["canonical_sha256"] = content_hash(json.loads(raw))
            files[rel] = entry
    return dict(sorted(files.items()))


def build_release(addresses: list[dict[str, Any]], out_root: str) -> dict[str, Any]:
    """The root inventory over every emitted bundle. Deterministic and self-addressed.

    ``addresses`` are the per-bundle addresses ``emit_bundle`` returned (relative only);
    the on-disk file hashes are re-read here so the inventory binds what actually LANDED,
    not what a caller claimed.
    """
    bundles = []
    for a in sorted(addresses, key=lambda a: a["bundle_key"]):
        out_dir = os.path.join(out_root, a["dir"])
        bundles.append({
            "bundle_key": a["bundle_key"],
            "bundle_id": a["bundle_id"],
            "from_condition": a["from_condition"],
            "to_condition": a["to_condition"],
            "dir": a["dir"],
            "n_arms": a["n_arms"],
            "arm_keys": list(a["arm_keys"]),
            # EVERY native file and ranking file in the bundle, by relative path + hash
            "files": _bundle_file_hashes(out_dir),
        })

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_RELEASE,
        "lane": arm_bundle.BUNDLE_LANE,
        "analysis_mode": arm_bundle.ANALYSIS_MODE,
        "n_bundles": len(bundles),
        "n_logical_arms": sum(len(b["arm_keys"]) for b in bundles),
        "bundles": bundles,
        "arm_keys": sorted(k for b in bundles for k in b["arm_keys"]),
        # NO admission here. The independent verifier writes temporal_verification.json per
        # bundle and binds this immutable inventory; the producer only says it is pending.
        "external_verification": {
            "status": "pending",
            "verifier_id": arm_report.VERIFIER_ID,
            "verification_file": "temporal_verification.json",
            "written_by": "independent_verifier",
        },
    }
    manifest["release_id"] = content_hash(manifest)[:RELEASE_ID_LEN]
    return manifest
