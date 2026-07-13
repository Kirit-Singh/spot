"""The 15 all-arm bundle DIRECTORIES, RE-READ FROM DISK and proved byte for byte.

Split from :mod:`verifier.v2_reconstruct` at the 500-line gate, on the seam that module already
had: it answers "did Stage 2 ADMIT this release"; this one answers "are these its BYTES". The
public entry point stays on ``v2_reconstruct``, which re-exports these names.

Nothing here reads a hash the manifest declares without recomputing it from the bytes on disk: a
bundle nobody re-read is a bundle a forger owns.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from . import canon
from . import v2_contract as C
from .report import Report
from .v2_reconstruct_util import _gate, _load_json, stage2_content_sha256


# --------------------------------------------------------------------------- #
# 2. The 15 bundle DIRECTORIES, and every byte the manifest bound.
# --------------------------------------------------------------------------- #
def _resolve_dir(rep: Report, name: Any, root: str, what: str) -> Optional[str]:
    """Resolve an out_dir NAME to exactly ONE directory inside the root, or refuse.

    A bare name is required (so an absolute path and ``..`` never resolve), and AMBIGUITY is
    refused: two directories of one name under a root are two bundles claiming one identity, and
    taking the first match would let the loser's bytes go unread.
    """
    bad = (not isinstance(name, str) or not name or os.path.isabs(str(name))
           or "/" in str(name) or "\\" in str(name) or name in (".", ".."))
    if bad:
        _gate(rep, C.GATE_PATH_TRAVERSAL,
              f"{what} names a bare bundle directory inside the explicit bundles root (an "
              "absolute or traversing path reads bytes from outside it)",
              False, f"out_dir={name!r}")
        return None
    real_root = os.path.realpath(root)
    hits = [os.path.join(base, d)
            for base, dirs, _f in os.walk(real_root) for d in dirs if d == name]
    if len(hits) != 1:
        _gate(rep, C.GATE_DUPLICATE_BUNDLE if hits else C.GATE_ARTIFACT_NOT_ON_DISK,
              f"{what} resolves to EXACTLY ONE bundle directory under the bundles root (two "
              "directories of one name are two bundles claiming one identity, and one of them "
              "would never be read)",
              False, f"{len(hits)} match(es) for {name!r}")
        return None
    full = os.path.realpath(hits[0])
    if os.path.commonpath([real_root, full]) != real_root:
        _gate(rep, C.GATE_PATH_TRAVERSAL,
              f"{what} resolves INSIDE the bundles root (a symlink counts — realpath is what "
              "actually gets opened)",
              False, f"resolved={full!r}")
        return None
    return full


def _bundle_key(lane: Any, ctx: dict[str, Any]) -> str:
    """Stage-3's slot label, derived from the bundle's OWN native context."""
    if lane == C.LANE_DIRECT:
        return f"{C.LANE_DIRECT}|{ctx.get('condition')}"
    if lane == C.LANE_TEMPORAL:
        return f"{C.LANE_TEMPORAL}|{ctx.get('from_condition')}|{ctx.get('to_condition')}"
    return (f"{C.LANE_PATHWAY}|{ctx.get('condition')}|"
            f"{ctx.get(C.NATIVE_PATHWAY_SOURCE_KEY)}")


def _bundles(rep: Report, manifest: dict[str, Any],
             bundles_root: str) -> Optional[list[tuple[dict[str, Any], str]]]:
    entries = manifest.get("bundles")
    if not isinstance(entries, list) or not entries:
        _gate(rep, C.GATE_INCOMPLETE_TOPOLOGY,
              f"the manifest ships a `bundles` array (the release is exactly {C.N_BUNDLES} "
              "all-arm bundle DIRECTORIES; a partial release is never admissible — and an "
              "`inventory` array is not this contract: Stage 2 has never emitted one)",
              False, f"bundles={type(entries).__name__}")
        return None

    expected = C.expected_bundle_keys()
    seen: dict[str, dict[str, Any]] = {}
    out: list[tuple[dict[str, Any], str]] = []
    unknown, duplicate, moved = [], [], []
    for entry in entries:
        lane, ctx = entry.get("lane"), entry.get("context") or {}
        key = _bundle_key(lane, ctx)
        if lane not in C.LANES or key not in expected or expected.get(key) != lane:
            unknown.append(f"{key!r} (lane={lane!r})")
            continue
        if key in seen:
            duplicate.append(key)
            continue
        full = _resolve_dir(rep, entry.get("out_dir"), bundles_root, f"bundle {key!r}")
        if full is None:
            return None

        files = entry.get("files")
        if not isinstance(files, dict) or C.ARM_BUNDLE_FILE not in files:
            moved.append(f"{key}: binds no {C.ARM_BUNDLE_FILE}")
            continue
        # EVERY bound byte, re-hashed from disk. Not a sample: the file a forger edits is the one
        # nobody re-read.
        for rel, sha in sorted(files.items()):
            path = os.path.realpath(os.path.join(full, str(rel)))
            if os.path.commonpath([full, path]) != full:
                moved.append(f"{key}: {rel!r} escapes its bundle")
            elif not os.path.isfile(path):
                moved.append(f"{key}: {rel!r} is not on disk")
            elif canon.file_sha256(path) != sha:
                moved.append(f"{key}: {rel!r} hashes to "
                             f"{canon.file_sha256(path)[:12]}… vs bound {str(sha)[:12]}…")
        if stage2_content_sha256(files) != entry.get("artifact_sha256"):
            moved.append(f"{key}: the verified file map does not hash to its artifact_sha256")

        entry = dict(entry, bundle_key=key,
                     raw_sha256=str(files.get(C.ARM_BUNDLE_FILE)),
                     canonical_sha256=stage2_content_sha256(files),
                     condition=ctx.get("condition"),
                     from_condition=ctx.get("from_condition"),
                     to_condition=ctx.get("to_condition"),
                     pathway_source=ctx.get(C.NATIVE_PATHWAY_SOURCE_KEY))
        seen[key] = entry
        out.append((entry, full))

    ok = _gate(rep, C.GATE_UNKNOWN_LANE,
               f"every bundle is one of the {C.N_BUNDLES} DERIVED from {list(C.CONDITIONS)} x "
               f"{list(C.PATHWAY_SOURCES)} and agrees with its own context (a mislabelled bundle "
               "fills the wrong slot)",
               not unknown, "; ".join(unknown[:3]))
    ok = _gate(rep, C.GATE_DUPLICATE_BUNDLE,
               "no bundle key appears twice (a duplicate silently fills a missing slot, and the "
               "count still looks right)",
               not duplicate, str(duplicate[:3])) and ok
    ok = _gate(rep, C.GATE_BUNDLE_BYTES_MOVED,
               "EVERY byte the manifest bound is still on disk and still hashes to what it "
               "bound, and each bundle's file map hashes to its own artifact_sha256 (the file a "
               "forger edits is the one nobody re-reads)",
               not moved, "; ".join(moved[:3])) and ok

    missing = sorted(set(expected) - set(seen))
    ok = _gate(rep, C.GATE_MISSING_BUNDLE,
               f"the manifest resolves all {C.N_BUNDLES} bundles — 3 Direct, 6 ORDERED temporal "
               "pairs, 6 pathway condition x source (a missing bundle is indistinguishable from "
               "one computed and found empty)",
               not missing and len(out) == C.N_BUNDLES,
               f"missing={missing[:4]} resolved={len(out)}") and ok
    return out if ok else None


def _arms_of(rep: Report, entry: dict[str, Any], full: str,
             provenance: dict[str, Any]) -> Optional[list[dict[str, Any]]]:
    """The arms a bundle DIRECTORY actually ships, with each arm's ranking rows VERBATIM."""
    loaded = _load_json(rep, os.path.join(full, C.ARM_BUNDLE_FILE),
                        f"arm inventory of bundle {entry['bundle_key']!r}",
                        C.GATE_ARTIFACT_NOT_ON_DISK)
    if loaded is None:
        return None
    doc, _raw = loaded

    arms: list[dict[str, Any]] = []
    broken: list[str] = []
    for arm in (doc.get("arms") or ()):
        # EACH LANE'S OWN ARM-KEY FIELD, restated independently (never imported from the
        # producer). The pathway lane names its key `pathway_arm_key`; Direct and temporal name
        # theirs `arm_key`, and the older release spelled it `arm_key` on all three. Reading only
        # `arm_key` resolved a current pathway arm to None and failed the release's own topology.
        arm_key = str(arm.get("pathway_arm_key" if entry["lane"] == C.LANE_PATHWAY
                              else "arm_key") or arm.get("arm_key") or "")
        program_id, change = arm.get("program_id"), arm.get("desired_change")
        if not arm_key or not program_id or change not in C.DESIRED_CHANGES:
            broken.append(f"{arm.get('arm_key')!r}/{change!r}")
            continue
        binding = arm.get("ranking") or {}
        path = os.path.realpath(os.path.join(full, str(binding.get("path") or "")))
        if os.path.commonpath([full, path]) != full or not os.path.isfile(path):
            broken.append(f"{arm_key}: ranking is not inside the bundle")
            continue
        if canon.file_sha256(path) != binding.get("raw_sha256"):
            broken.append(f"{arm_key}: its ranking hashes to {canon.file_sha256(path)[:12]}… "
                          f"but the bundle bound {str(binding.get('raw_sha256'))[:12]}…")
            continue
        ranking = _load_json(rep, path, f"ranking of arm {arm_key!r}",
                             C.GATE_ARTIFACT_NOT_ON_DISK)
        if ranking is None:
            return None
        rows = (ranking[0] or {}).get("records")
        if not isinstance(rows, list):
            broken.append(f"{arm_key}: its ranking ships no `records` rows")
            continue
        arms.append({
            "arm_key": arm_key, "lane": entry["lane"], "bundle_key": entry["bundle_key"],
            "program_id": str(program_id), "desired_change": str(change),
            "condition": entry.get("condition"),
            "from_condition": entry.get("from_condition"),
            "to_condition": entry.get("to_condition"),
            "pathway_source": entry.get("pathway_source"),
            "ranking": dict(binding),
            "bundle_raw_sha256": entry["raw_sha256"],
            "bundle_canonical_sha256": entry["canonical_sha256"],
            "provenance": dict(provenance),
            # VERBATIM. Nothing is renamed and nothing is defaulted in: a field Stage 2 does not
            # emit is a field Stage 3 does not have.
            "records": [dict(r) for r in rows]})

    ok = _gate(rep, C.GATE_INCOMPLETE_TOPOLOGY,
               f"every arm in bundle {entry['bundle_key']!r} names a key, a program and a known "
               "desired_change, and binds a ranking that is ON DISK and still hashes to what the "
               "bundle bound (an arm whose ranking nobody can read is an arm nobody can replay)",
               not broken, "; ".join(broken[:3]))

    declared = sorted(str(k) for k in (entry.get("arm_keys") or []))
    ok = _gate(rep, C.GATE_ARM_INDEX_DISAGREES,
               f"the manifest's arm index for bundle {entry['bundle_key']!r} IS the set of arms "
               "the bundle ships (an index that disagrees with the bytes describes a bundle that "
               "is not there)",
               declared == sorted(a["arm_key"] for a in arms),
               f"manifest indexes {len(declared)}, the bundle ships {len(arms)}") and ok
    return arms if ok else None


def _arm_topology(rep: Report, arms: list[dict[str, Any]], bundles: list[dict[str, Any]],
                  programs: list[str]) -> bool:
    got = sorted({a["program_id"] for a in arms})
    slots = {(a["bundle_key"], a["program_id"], a["desired_change"]) for a in arms}
    expected = {(b["bundle_key"], p, d)
                for b in bundles for p in programs for d in C.DESIRED_CHANGES}
    return _gate(rep, C.GATE_INCOMPLETE_TOPOLOGY,
                 f"the release resolves the FULL {C.N_ARM_SLOTS}-slot arm topology — "
                 f"{C.N_PROGRAMS} programs x {len(C.DESIRED_CHANGES)} desired changes x "
                 f"{C.N_BUNDLES} contexts, each filled exactly once, with no duplicate standing "
                 "in for a missing slot (DERIVED from the loaded arms, never read from a "
                 "declared count)",
                 got == programs and len(slots) == len(arms)
                 and len(slots) == C.N_ARM_SLOTS and not (expected - slots),
                 f"programs={len(got)} slots={len(slots)} arms={len(arms)} "
                 f"missing={len(expected - slots)}")


