"""Emit ONE content-addressed temporal arm bundle per frozen ordered condition pair.

THE PHYSICAL CONTRACT, EMITTED NATIVELY
---------------------------------------
Each ordered-pair bundle directory carries, under names the aggregate run-manifest and
W11's verifier read directly — no rename, no post-hoc copy, no shim:

    arm_bundle.json            the reusable-arm inventory (base records + arms + rankings)
    temporal_provenance.json   what produced it, binding the bundle by content hash
    temporal_verification.json the INDEPENDENT verifier's typed report, binding the bundle
    rankings/<program>__<change>.json   the bytes each arm's rank/counts stand on

PORTABLE BY CONSTRUCTION
------------------------
The bytes are canonical JSON with NO timestamp, NO hostname and NO absolute path. Every
path a shipped artifact carries is BUNDLE-RELATIVE, so the bundle is byte-identical on any
host and can be content-addressed at all. Absolute paths, hostnames and private addresses
are refused at any depth — W11's resealed path-injection fails closed here, because the
portability firewall runs inside the verifier regardless of whether the content hash is
internally consistent.

VERIFIED ON WHAT LANDED, BY A SEPARATE VERIFIER
-----------------------------------------------
``emit_bundle`` writes, then READS THE FILES BACK OFF DISK and hands them to
``arm_admission`` — a module structurally separate from the one that built them, which
re-derives every claim from the shipped bytes. A bundle that fails is removed whole: no
provenance and no verification report are left on disk beside an artifact that did not earn
them. The verdict lives only in the separate report, never embedded in the bundle.
"""
from __future__ import annotations

import json
import os
import shutil
from typing import Any, Optional

from ...hashing import canonical_json, content_hash, sha256_hex
from . import arm_admission, arm_bundle, arm_provenance, arm_report

BUNDLE_FILENAME = arm_bundle.BUNDLE_FILENAME
PROVENANCE_FILENAME = arm_bundle.PROVENANCE_FILENAME
VERIFICATION_FILENAME = arm_bundle.VERIFICATION_FILENAME
SCHEMA_PROVENANCE = arm_provenance.SCHEMA_PROVENANCE
SCHEMA_VERIFICATION = arm_report.SCHEMA_VERIFICATION
SCHEMA_ADDRESS = "spot.stage02_temporal_arm_release_address.v1"


class EmitRefused(ValueError):
    """The bundle did not survive its own verifier. Nothing is left on disk claiming it did."""


def bundle_dirname(from_condition: str, to_condition: str) -> str:
    """``<from>__to__<to>`` — one directory per ORDERED pair. Reversing it is a new bundle."""
    return f"{from_condition}__to__{to_condition}"


def bundle_bytes(bundle: dict[str, Any]) -> bytes:
    """The canonical bytes of a bundle. The ONLY serialisation; there is no other form."""
    return canonical_json(bundle).encode("utf-8")


def _write(path: str, obj: Any) -> tuple[bytes, str]:
    """Write canonical bytes; return ``(bytes, raw_sha256)``."""
    raw = canonical_json(obj).encode("utf-8")
    with open(path, "wb") as fh:
        fh.write(raw)
    return raw, sha256_hex(raw)


def _refuse_machine_local(obj: Any, what: str) -> None:
    """Fail-closed if a to-be-shipped document carries any machine-local address."""
    hits = arm_admission.machine_local_strings(obj)
    if hits:
        raise EmitRefused(
            f"the {what} carries machine-local string(s) {hits[:6]}; a shipped artifact "
            "must be portable and content-addressable, and an absolute path or hostname is "
            "neither reproducible off this host nor anybody's business downstream")


def emit_bundle(bundle: dict[str, Any], out_root: str) -> dict[str, Any]:
    """Write one bundle's four artifact kinds, verify what LANDED, return relative addresses.

    Fail-closed: if the independent verifier refuses the shipped bytes, the whole bundle
    directory is removed and ``EmitRefused`` is raised — no provenance and no verification
    report survive beside a bundle that did not pass.
    """
    out_dir = os.path.join(out_root,
                           bundle_dirname(bundle["from_condition"],
                                          bundle["to_condition"]))
    try:
        _emit_into(bundle, out_dir)
    except Exception:
        shutil.rmtree(out_dir, ignore_errors=True)
        raise
    return _address(bundle, out_dir)


def _emit_into(bundle: dict[str, Any], out_dir: str) -> None:
    os.makedirs(os.path.join(out_dir, arm_bundle.RANKINGS_DIR), exist_ok=True)

    # 1. the per-arm ranking files — the BYTES each arm's rank and counts stand on
    for arm in bundle["arms"]:
        obj = arm_bundle.ranking_object(arm)
        _write(os.path.join(out_dir, arm["ranking"]["path"]), obj)

    # 2. the arm inventory
    _refuse_machine_local(bundle, "arm bundle")
    bundle_path = os.path.join(out_dir, BUNDLE_FILENAME)
    with open(bundle_path, "wb") as fh:
        fh.write(bundle_bytes(bundle))

    # 3. VERIFY WHAT LANDED — read back, re-derive from the shipped bytes off disk.
    result = arm_admission.verify_shipped(out_dir)
    if not result["admitted"]:
        raise EmitRefused(
            f"the emitted bundle {bundle['bundle_key']!r} did not survive its own "
            f"verifier: {result['failures'][:8]}")

    with open(bundle_path, "rb") as fh:
        arm_raw = sha256_hex(fh.read())

    # 4. provenance — binds the arm inventory by hash
    prov = arm_provenance.build_provenance(bundle, bundle_file=BUNDLE_FILENAME,
                                           bundle_raw_sha256=arm_raw)
    _refuse_machine_local(prov, "provenance")
    _, prov_raw = _write(os.path.join(out_dir, PROVENANCE_FILENAME), prov)

    # 5. the INDEPENDENT report — binds the bundle AND the provenance it judged
    report = arm_report.build_report(result, bundle_id=bundle["bundle_id"],
                                     arm_bundle_sha256=arm_raw, provenance_sha256=prov_raw)
    _refuse_machine_local(report, "verification report")
    _write(os.path.join(out_dir, VERIFICATION_FILENAME), report)


def _address(bundle: dict[str, Any], out_dir: str) -> dict[str, Any]:
    """The RELATIVE content address of an emitted bundle. No absolute path, at any depth.

    ``dir`` and every key of ``files`` are bundle-relative; a test or a local caller that
    needs a runtime absolute path reconstructs it with ``resolve_local_paths`` — which lives
    OUTSIDE this contract precisely so a machine-local path can never enter it.
    """
    files: dict[str, dict[str, str]] = {}
    for fname in (BUNDLE_FILENAME, PROVENANCE_FILENAME, VERIFICATION_FILENAME):
        with open(os.path.join(out_dir, fname), "rb") as fh:
            raw = fh.read()
        files[fname] = {"raw_sha256": sha256_hex(raw),
                        "canonical_sha256": content_hash(json.loads(raw))}
    address = {
        "schema_version": SCHEMA_ADDRESS,
        "lane": bundle["lane"],
        "analysis_mode": bundle["analysis_mode"],
        "bundle_key": bundle["bundle_key"],
        "bundle_id": bundle["bundle_id"],
        "from_condition": bundle["from_condition"],
        "to_condition": bundle["to_condition"],
        "dir": bundle_dirname(bundle["from_condition"], bundle["to_condition"]),
        "files": files,
        "n_arms": bundle["n_arms"],
        "n_programs": bundle["n_programs"],
        "n_targets": bundle["n_targets"],
        "n_base_records": bundle["n_base_records"],
        "arm_keys": list(bundle["arm_keys"]),
        "verdict": "admit",
    }
    _refuse_machine_local(address, "release address")
    return address


def resolve_local_paths(out_root: str, address: dict[str, Any]) -> dict[str, str]:
    """TEST/LOCAL-ONLY: reconstruct the absolute paths of a bundle's files ON DEMAND.

    Deliberately OUTSIDE the release contract. Absolute paths are machine-local and must
    never enter a shipped or returned artifact, so they are never stored — they are computed
    transiently, here, from ``out_root`` plus the relative ``dir`` the address carries. The
    return value is not serialisable into any contract; it is for a caller standing on this
    machine, right now.
    """
    d = os.path.join(out_root, address["dir"])
    return {fname: os.path.join(d, fname) for fname in address["files"]}


def emit_release(bundles: list[dict[str, Any]], out_root: str,
                 expect_n_bundles: Optional[int] = None) -> dict[str, Any]:
    """Emit every ordered-pair bundle, and account for the release as a whole.

    The inventory is DERIVED from the bundles that were actually emitted, and it is
    RELATIVE-ONLY: no absolute path, hostname or private address enters the returned release
    object, which a caller may serialise into a run manifest.
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

    release = {
        "schema_version": SCHEMA_ADDRESS,
        "n_bundles": len(addresses),
        "n_logical_arms": len(arm_keys),
        "bundles": addresses,
        "arm_keys": sorted(arm_keys),
    }
    _refuse_machine_local(release, "release inventory")
    return release


__all__ = ["BUNDLE_FILENAME", "PROVENANCE_FILENAME", "VERIFICATION_FILENAME",
           "SCHEMA_PROVENANCE", "SCHEMA_VERIFICATION", "SCHEMA_ADDRESS", "EmitRefused",
           "bundle_bytes", "bundle_dirname", "emit_bundle", "emit_release",
           "resolve_local_paths", "arm_bundle"]
