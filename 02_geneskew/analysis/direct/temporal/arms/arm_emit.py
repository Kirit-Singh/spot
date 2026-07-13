"""Emit ONE content-addressed temporal arm bundle per frozen ordered condition pair.

THE PHYSICAL CONTRACT, EMITTED NATIVELY
---------------------------------------
The PRODUCER writes exactly these, under names the aggregate run-manifest and W11's
verifier read directly — no rename, no post-hoc copy, no shim:

    per bundle dir <from>__to__<to>/:
        arm_bundle.json          the reusable-arm inventory (base records + arms + rankings)
        temporal_provenance.json what produced it, binding the bundle by content hash
        temporal_preflight.json  the producer's own self-check — a STATUS, never an admission
        rankings/<program>__<change>.json  the bytes each arm's rank/counts stand on
    at the release root:
        temporal_arm_release.json  the content-addressed six-bundle inventory (every file +
                                   ranking hash), external_verification.status=pending

The authoritative ``temporal_verification.json`` is NOT written here. It is the INDEPENDENT
verifier's (W11's) artifact, written after W11 reopens the shipped bytes — a producer may
not sign an admission under an independent verifier's identity for code it invoked itself.
The producer's own re-derivation is a fail-closed emission gate recorded as a preflight.

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
from . import (
    arm_admission,
    arm_bundle,
    arm_preflight,
    arm_provenance,
    arm_release,
    arm_report,
)

BUNDLE_FILENAME = arm_bundle.BUNDLE_FILENAME
PROVENANCE_FILENAME = arm_bundle.PROVENANCE_FILENAME
PREFLIGHT_FILENAME = "temporal_preflight.json"
VERIFICATION_FILENAME = arm_bundle.VERIFICATION_FILENAME
RELEASE_FILENAME = arm_release.RELEASE_FILENAME
SCHEMA_PROVENANCE = arm_provenance.SCHEMA_PROVENANCE
SCHEMA_PREFLIGHT = arm_preflight.SCHEMA_PREFLIGHT
SCHEMA_VERIFICATION = arm_report.SCHEMA_VERIFICATION
SCHEMA_RELEASE = arm_release.SCHEMA_RELEASE
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
    """Write the PRODUCER's artifacts, self-check what LANDED, return relative addresses.

    The producer emits exactly ``arm_bundle.json``, ``temporal_provenance.json`` and
    ``rankings/*.json`` — and NOT ``temporal_verification.json``. The authoritative
    verification is written by the INDEPENDENT verifier (W11) after it reopens these bytes;
    a producer cannot be the independent witness for code it invokes itself.

    Fail-closed: the producer runs its OWN re-derivation as an INTERNAL emission gate. It is
    a producer SELF-CHECK, not an admission — if it fails, the whole bundle directory is
    removed and ``EmitRefused`` is raised, so no artifact survives that the producer could
    not itself reconstruct. It writes no verdict, under no verifier id.
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

    # 3. PRODUCER SELF-CHECK (fail-closed) — read the bytes back off disk and re-derive.
    # This is NOT an independent admission: the producer invoked it, so it may not claim
    # independence. It refuses to leave behind bytes it cannot itself reconstruct.
    result = arm_admission.verify_shipped(out_dir)
    if not result["admitted"]:
        raise EmitRefused(
            f"the emitted bundle {bundle['bundle_key']!r} did not survive the producer "
            f"self-check: {result['failures'][:8]}")

    with open(bundle_path, "rb") as fh:
        arm_raw = sha256_hex(fh.read())

    # 4. provenance — binds the arm inventory by hash.
    prov = arm_provenance.build_provenance(bundle, bundle_file=BUNDLE_FILENAME,
                                           bundle_raw_sha256=arm_raw)
    _refuse_machine_local(prov, "provenance")
    _, prov_raw = _write(os.path.join(out_dir, PROVENANCE_FILENAME), prov)

    # 5. the PRODUCER PREFLIGHT — the self-check recorded as pass|fail, never an admission.
    # The authoritative external admission is the INDEPENDENT verifier's (W11's) root
    # envelope, written after it reopens these bytes.
    preflight = arm_preflight.build_preflight(
        result, bundle=bundle, arm_bundle_sha256=arm_raw, provenance_sha256=prov_raw)
    _refuse_machine_local(preflight, "producer preflight")
    _write(os.path.join(out_dir, PREFLIGHT_FILENAME), preflight)


def _address(bundle: dict[str, Any], out_dir: str) -> dict[str, Any]:
    """The RELATIVE content address of the PRODUCER's emitted bytes. No absolute path.

    ``dir`` and every key of ``files`` are bundle-relative; a test or a local caller that
    needs a runtime absolute path reconstructs it with ``resolve_local_paths`` — which lives
    OUTSIDE this contract precisely so a machine-local path can never enter it. The address
    carries NO verdict: the producer does not admit its own bytes, and it names WHERE the
    independent verification will live (``verification.status = pending_external_verification``).
    """
    files: dict[str, dict[str, str]] = {}
    for fname in (BUNDLE_FILENAME, PROVENANCE_FILENAME, PREFLIGHT_FILENAME):
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
        # the producer does NOT admit its own bytes; it declares the REQUIRED external
        # admission (the independent verifier's root envelope), pending until W11 emits it
        "external_admission": {
            "status": "pending",
            "required_verifier_id": arm_report.VERIFIER_ID,
            "required_report_schema_version": arm_report.EXTERNAL_ADMISSION_SCHEMA,
        },
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
    """Emit every ordered-pair bundle AND the content-addressed root release inventory.

    Writes ``temporal_arm_release.json`` at ``out_root``: the six-bundle inventory with
    every native file and ranking hash, ``external_verification.status = pending`` (the
    authoritative admission is W11's), and a self-addressed ``release_id``. Relative-only —
    no absolute path, hostname or timestamp enters it, so it is byte-stable across hosts.
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

    # the Stage-1 binding is read from one bundle's provenance (all six share the release);
    # read it off disk so the root inventory binds what actually shipped.
    first = sorted(addresses, key=lambda a: a["bundle_key"])[0]
    with open(os.path.join(out_root, first["dir"], PROVENANCE_FILENAME), "rb") as fh:
        first_prov = json.loads(fh.read())
    manifest = arm_release.build_release(addresses, out_root, provenance=first_prov)
    _refuse_machine_local(manifest, "release inventory")
    _write(os.path.join(out_root, RELEASE_FILENAME), manifest)

    return {
        "schema_version": SCHEMA_ADDRESS,
        "release_id": manifest["release_id"],
        "release_file": RELEASE_FILENAME,
        "n_bundles": len(addresses),
        "n_logical_arms": len(arm_keys),
        "bundles": addresses,
        "arm_keys": sorted(arm_keys),
        "release": manifest,
    }


__all__ = ["BUNDLE_FILENAME", "PROVENANCE_FILENAME", "PREFLIGHT_FILENAME",
           "VERIFICATION_FILENAME", "RELEASE_FILENAME", "SCHEMA_PROVENANCE",
           "SCHEMA_PREFLIGHT", "SCHEMA_VERIFICATION", "SCHEMA_RELEASE", "SCHEMA_ADDRESS",
           "EmitRefused", "bundle_bytes", "bundle_dirname", "emit_bundle", "emit_release",
           "resolve_local_paths", "arm_bundle"]
