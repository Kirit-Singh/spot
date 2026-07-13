"""Emit ONE content-addressed temporal arm bundle per frozen ordered condition pair.

DETERMINISTIC BY CONSTRUCTION
----------------------------
The bytes are canonical JSON — sorted keys, compact separators, no NaN — and the bundle
carries NO timestamp, NO hostname and NO path. Rebuilding from the same inputs therefore
re-emits the SAME BYTES, which is what lets the bundle be content-addressed at all: an
artifact whose identity moved every time it was rebuilt could not be referenced by it.

TWO HASHES, AND THEY ARE DIFFERENT QUESTIONS
--------------------------------------------
``raw_sha256``       the sha256 of the bytes ON DISK. What a downstream stage pins, and
                     what an integrity gate re-reads and compares. It answers: are these
                     the bytes that were admitted?
``canonical_sha256`` the sha256 of the canonical form of the PARSED content. Key order is
                     not content, so a re-serialised bundle is the same bundle. It answers:
                     is this the same CLAIM?

Both ship. A single hash would conflate "these bytes changed" with "this claim changed",
and a reader chasing a mismatch could not tell which had happened.

THE VERIFICATION IS RUN ON WHAT LANDED
--------------------------------------
``emit_bundle`` writes, then READS THE FILE BACK OFF DISK and verifies the parsed bytes.
It does not verify the in-memory object it just serialised — that object is not the
artifact, and a truncated or partially-written file would have passed a check made against
it while shipping something nobody could re-derive.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from ...hashing import canonical_json, content_hash, file_sha256, sha256_hex
from . import arm_admission, arm_bundle

BUNDLE_FILENAME = "temporal_arm_bundle.json"
VERIFICATION_FILENAME = "temporal_arm_verification.json"
SCHEMA_VERIFICATION = "spot.stage02_temporal_arm_verification.v1"


class EmitRefused(ValueError):
    """The bundle did not survive its own verifier. Nothing is left on disk claiming it did."""


def bundle_dirname(from_condition: str, to_condition: str) -> str:
    """``<from>__to__<to>`` — one directory per ORDERED pair. Reversing it is a new bundle."""
    return f"{from_condition}__to__{to_condition}"


def bundle_bytes(bundle: dict[str, Any]) -> bytes:
    """The canonical bytes of a bundle. The ONLY serialisation; there is no other form."""
    return canonical_json(bundle).encode("utf-8")


def emit_bundle(bundle: dict[str, Any], out_root: str) -> dict[str, Any]:
    """Write one bundle, verify what LANDED, and return its content addresses.

    The verifier runs on the re-read bytes. If it refuses, ``EmitRefused`` is raised and no
    verification record is written: an artifact that failed its own admission must not be
    left on disk next to a report saying it passed.
    """
    import json

    out_dir = os.path.join(out_root,
                           bundle_dirname(bundle["from_condition"],
                                          bundle["to_condition"]))
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, BUNDLE_FILENAME)

    with open(path, "wb") as fh:
        fh.write(bundle_bytes(bundle))

    # READ BACK. The subject of the verification is what is on disk, never what we held.
    with open(path, "rb") as fh:
        raw = fh.read()
    shipped = json.loads(raw)

    report = arm_admission.verify_bundle(shipped)
    if not report["admitted"]:
        os.remove(path)
        raise EmitRefused(
            f"the emitted bundle {bundle['bundle_key']!r} did not survive its own "
            f"verifier and was removed: {report['failures']}")

    address = {
        "schema_version": SCHEMA_VERIFICATION,
        "bundle_key": shipped["bundle_key"],
        "bundle_id": shipped["bundle_id"],
        "from_condition": shipped["from_condition"],
        "to_condition": shipped["to_condition"],
        "path": BUNDLE_FILENAME,
        "raw_sha256": sha256_hex(raw),
        "canonical_sha256": content_hash(shipped),
        "n_arms": shipped["n_arms"],
        "n_programs": shipped["n_programs"],
        "n_targets": shipped["n_targets"],
        "n_base_records": shipped["n_base_records"],
        "arm_keys": list(shipped["arm_keys"]),
        "verification": report,
    }
    vpath = os.path.join(out_dir, VERIFICATION_FILENAME)
    with open(vpath, "wb") as fh:
        fh.write(canonical_json(address).encode("utf-8"))

    address["path_abs"] = path
    address["verification_path_abs"] = vpath
    address["raw_sha256_on_disk"] = file_sha256(path)
    return address


def emit_release(bundles: list[dict[str, Any]], out_root: str,
                 expect_n_bundles: Optional[int] = None) -> dict[str, Any]:
    """Emit every ordered-pair bundle, and account for the release as a whole.

    The inventory is DERIVED from the bundles that were actually emitted — the arm count is
    a consequence of the program axis and the ordered pairs, never a constant typed in
    here. ``expect_n_bundles`` is an optional completeness assertion for a caller that
    knows the topology it asked for; it is not a default, and nothing is inferred when it
    is absent.
    """
    addresses = [emit_bundle(b, out_root) for b in
                 sorted(bundles, key=lambda b: b["bundle_key"])]

    keys = [a["bundle_key"] for a in addresses]
    if len(set(keys)) != len(keys):
        raise EmitRefused(
            f"two bundles claim the same ordered pair: {sorted(keys)}. One would have "
            "overwritten the other, and the release would be short an entire comparison "
            "while still counting it")

    arm_keys = [k for a in addresses for k in a["arm_keys"]]
    if len(set(arm_keys)) != len(arm_keys):
        raise EmitRefused("an arm key appears in more than one bundle; a reusable arm has "
                          "exactly one home, and two would be two chances to disagree")

    if expect_n_bundles is not None and len(addresses) != expect_n_bundles:
        raise EmitRefused(
            f"expected {expect_n_bundles} ordered-pair bundles, emitted {len(addresses)}. "
            "A partial release cannot satisfy completeness, and a short bundle set that "
            "reported success would be indistinguishable from a whole one")

    return {
        "n_bundles": len(addresses),
        "n_logical_arms": len(arm_keys),
        "bundles": addresses,
        "arm_keys": sorted(arm_keys),
    }


__all__ = ["BUNDLE_FILENAME", "VERIFICATION_FILENAME", "EmitRefused", "bundle_bytes",
           "bundle_dirname", "emit_bundle", "emit_release", "arm_bundle"]
