"""``temporal_arm_release.json`` — the content-addressed ROOT inventory of one release.

Per the sealed cross-check (a12f7eee, §C): the clean unit of external admission is the
SIX-BUNDLE release, because the independent verifier checks all ordered-pair topology and
reverse-direction identities across bundles. A producer cannot truthfully emit that verdict,
so it emits an IMMUTABLE inventory and declares — but does not assert — the required external
admission.

WHAT IT CARRIES
---------------
  * ``release_id`` — the FULL 64-hex sha256 over the canonical inventory EXCLUDING
    ``release_id`` itself, with ``release_id_rule`` stated explicitly so a reader recomputes
    it rather than trusting the length;
  * a hash-bound ``stage1_binding`` — the v3 release / scorer-view / program / condition
    identity the whole release stood on, carried once at the root;
  * per bundle: ``files`` (arm_bundle / provenance / preflight, each raw+canonical sha256)
    and ``rankings`` (every ranking path, each raw+canonical sha256);
  * ``external_admission.status = pending`` — the ONLY honest producer state — naming the
    required independent verifier and report schema. The wrapper is immutable; the
    independent verifier does not rewrite it to ``admit``, it emits a separate envelope.

Relative-only, no timestamp, no machine-local address: byte-stable and portable across hosts.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from ...hashing import content_hash, sha256_hex
from . import arm_bundle, arm_report

SCHEMA_RELEASE = "spot.stage02_temporal_arm_release.v1"
RELEASE_FILENAME = "temporal_arm_release.json"
RELEASE_ID_RULE = "sha256(canonical JSON excluding release_id)"

# The producer's top-level JSON files, in a stable order.
_TOP_FILES = (arm_bundle.BUNDLE_FILENAME, arm_bundle.PROVENANCE_FILENAME,
              arm_bundle.PREFLIGHT_FILENAME)


def _hashes(path: str) -> dict[str, str]:
    with open(path, "rb") as fh:
        raw = fh.read()
    return {"raw_sha256": sha256_hex(raw),
            "canonical_sha256": content_hash(json.loads(raw))}


def _bundle_entry(a: dict[str, Any], out_dir: str) -> dict[str, Any]:
    """One bundle's row: its top files and EVERY ranking file, each raw+canonical."""
    files = {fn: _hashes(os.path.join(out_dir, fn)) for fn in _TOP_FILES}
    rankings: dict[str, dict[str, str]] = {}
    rdir = os.path.join(out_dir, arm_bundle.RANKINGS_DIR)
    if os.path.isdir(rdir):
        for fn in sorted(os.listdir(rdir)):
            rel = f"{arm_bundle.RANKINGS_DIR}/{fn}"
            rankings[rel] = _hashes(os.path.join(out_dir, rel))
    return {
        "bundle_key": a["bundle_key"],
        "bundle_id": a["bundle_id"],
        "from_condition": a["from_condition"],
        "to_condition": a["to_condition"],
        "relative_dir": a["dir"],
        "n_arms": a["n_arms"],
        "arm_keys": list(a["arm_keys"]),
        "files": files,
        "rankings": rankings,
    }


def stage1_binding(prov: dict[str, Any]) -> dict[str, Any]:
    """The hash-bound v3 release / scorer / program / condition identity the release stood on.

    Carried through from the provenance the producer actually read — the SAME block the
    bundle bound. No fabricated value; the completeness gate refuses any null field.
    """
    return dict((prov.get("run_binding") or {}).get("selection_release") or {})


TOPOLOGY_RULE_ID = "spot.stage02.temporal.arm.topology.programs_x_changes_x_ordered_pairs.v1"


def ordered_pairs(conditions: list[str]) -> list[tuple[str, str]]:
    c = sorted({str(x) for x in conditions})
    return [(a, b) for a in c for b in c if a != b]


def expected_topology(programs: list[str], conditions: list[str]) -> dict[str, Any]:
    """The six-bundle / 120-arm topology, DERIVED from the Stage-1 programs + conditions.

    A COMPLETE run is not a fixture assertion of "120": it is exactly ``n_programs x 2
    desired changes x n_ordered_pairs`` arms over ``n_ordered_pairs`` bundles, and both
    counts fall out of the bound release. The independent verifier re-derives the same set;
    the producer records the derivation so it can be disagreed with.
    """
    progs = sorted({str(p) for p in programs})
    pairs = ordered_pairs(conditions)
    arm_keys = sorted(f"temporal|{p}|{dc}|{frm}|{to}"
                      for p in progs for dc in ("increase", "decrease")
                      for frm, to in pairs)
    return {
        "topology_rule_id": TOPOLOGY_RULE_ID,
        "n_programs": len(progs),
        "n_desired_changes": 2,
        "n_conditions": len({str(c) for c in conditions}),
        # the DECLARED selector order, carried verbatim — NOT the sorted inventory order.
        "selector_condition_sequence": [str(c) for c in conditions],
        "n_ordered_pairs": len(pairs),
        "expected_n_bundles": len(pairs),
        "expected_n_logical_arms": len(arm_keys),
        "ordered_pairs": [f"{a}->{b}" for a, b in pairs],
        "expected_arm_keys": arm_keys,
    }


class ReleaseError(ValueError):
    """The release inventory cannot be built as a COMPLETE release. Refuse; never truncate."""


# The identity every one of the six bundles must share, because they are ONE release built
# by ONE code from ONE Stage-1 binding. A non-first bundle with a self-consistent fake
# commit or a divergent method would otherwise hide in the middle of a release an
# aggregate that only pins the first bundle would admit.
_CROSS_BUNDLE_IDENTICAL = ("code_identity", "stage1_binding", "method",
                           "program_admission", "env_lock")


def _check_cross_bundle_identity(bundle_docs: list[dict[str, Any]]) -> list[str]:
    """Every bundle must agree on WHICH BUILD, WHICH Stage-1 release, WHICH method/scorer."""
    problems: list[str] = []
    first = bundle_docs[0]
    for field in _CROSS_BUNDLE_IDENTICAL:
        ref = first.get(field)
        for doc in bundle_docs[1:]:
            if doc.get(field) != ref:
                problems.append(
                    f"bundle {doc.get('bundle_key')!r} carries a different {field} than "
                    f"{first.get('bundle_key')!r} — a six-bundle release is ONE build of "
                    "ONE Stage-1 release; a divergent bundle is a forgery hiding in the set")
                break
    return problems


def build_release(addresses: list[dict[str, Any]], out_root: str,
                  provenance: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """The root inventory over every emitted bundle. Deterministic, self-addressed, complete.

    Reads every bundle's OWN bytes and refuses a release whose bundles disagree on the build
    (code_identity), the Stage-1 release, the method or the scorer view — an aggregate that
    pinned only the first bundle would admit a forgery hiding in the middle. On-disk hashes
    are re-read so the inventory binds what actually LANDED, the six-bundle / 120-arm
    topology is RE-DERIVED from the Stage-1 release, and the emitted bundles must fill it
    EXACTLY: a short, extra or duplicated bundle/arm/ranking is refused, not inventoried.
    """
    import json

    addrs = sorted(addresses, key=lambda a: a["bundle_key"])
    bundle_docs = [json.loads(
        open(os.path.join(out_root, a["dir"], arm_bundle.BUNDLE_FILENAME), "rb").read())
        for a in addrs]
    identity_problems = _check_cross_bundle_identity(bundle_docs)
    if identity_problems:
        raise ReleaseError(f"the six-bundle release is not one build: {identity_problems}")

    bundles = [_bundle_entry(a, os.path.join(out_root, a["dir"])) for a in addrs]
    # EXACT ranking set: every bundle binds ONE ranking per arm and NO more. A 121st
    # fully-valid resealed ranking is still an arm nobody bound — refused here.
    for entry, doc in zip(bundles, bundle_docs):
        if len(entry["rankings"]) != doc["n_arms"]:
            raise ReleaseError(
                f"bundle {doc['bundle_key']!r} inventories {len(entry['rankings'])} ranking "
                f"files but binds {doc['n_arms']} arms; an unbound ranking is unverified "
                "and indistinguishable from evidence")

    s1 = dict(bundle_docs[0]["stage1_binding"])
    env_lock = dict(bundle_docs[0].get("env_lock") or {})
    topology = expected_topology(s1.get("admitted_programs") or [],
                                 s1.get("selector_condition_sequence") or [])

    # COMPLETENESS + cross-bundle identity, all re-derived from the Stage-1 release.
    got_bundle_dirs = [f"{b['from_condition']}->{b['to_condition']}" for b in bundles]
    got_keys = [k for b in bundles for k in b["arm_keys"]]
    want_keys = set(topology["expected_arm_keys"])
    problems = []
    if sorted(got_bundle_dirs) != sorted(topology["ordered_pairs"]):
        problems.append(f"ordered-pair bundles {sorted(got_bundle_dirs)} != expected "
                        f"{sorted(topology['ordered_pairs'])}")
    if len(got_bundle_dirs) != len(set(got_bundle_dirs)):
        problems.append("a duplicate ordered-pair bundle")
    if set(got_keys) != want_keys:
        problems.append(f"missing={sorted(want_keys - set(got_keys))[:4]} "
                        f"extra={sorted(set(got_keys) - want_keys)[:4]}")
    if len(got_keys) != len(set(got_keys)):
        problems.append("a duplicate arm key across bundles")
    # cross-bundle: every ordered pair's REVERSE is also present (both directions shipped)
    dirs = set(got_bundle_dirs)
    missing_reverse = sorted(d for d in dirs
                             if f"{d.split('->')[1]}->{d.split('->')[0]}" not in dirs)
    if missing_reverse:
        problems.append(f"ordered pairs missing their reverse: {missing_reverse}")
    if problems:
        raise ReleaseError(
            "the emitted bundles do not fill the derived six-bundle topology exactly: "
            f"{problems}. A complete temporal release is programs x 2 x ordered-pairs; a "
            "run that is short, extra or duplicated is not a release")

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_RELEASE,
        "release_id_rule": RELEASE_ID_RULE,
        "lane": arm_bundle.BUNDLE_LANE,
        "analysis_mode": arm_bundle.ANALYSIS_MODE,
        "stage1_binding": s1,
        # the committed Stage-2 solver-lock identity, shared by all six bundles
        "env_lock": env_lock,
        "env_lock_sha256": env_lock.get("env_lock_sha256"),
        "topology": topology,
        "n_bundles": len(bundles),
        "n_logical_arms": len(got_keys),
        "arm_keys": sorted(got_keys),
        "bundles": bundles,
        # NO admission here. `pending` is the only honest producer state; the independent
        # verifier emits a SEPARATE content-addressed envelope and never rewrites this.
        "external_admission": {
            "status": "pending",
            "required_verifier_id": arm_report.VERIFIER_ID,
            "required_report_schema_version": arm_report.EXTERNAL_ADMISSION_SCHEMA,
        },
    }
    # FULL 64-hex self-hash over everything but release_id — the length is stated by the
    # rule, not implied by a truncation a reader has to know about.
    manifest["release_id"] = content_hash(manifest)
    return manifest
