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


def stage1_binding(prov: dict[str, Any], conditions: list[str]) -> dict[str, Any]:
    """The v3 release / scorer / program / condition identity the release stood on.

    Built from the provenance the producer actually read — no fabricated value. Fields the
    producer does not yet bind (per-program projection hashes, the release self-hash) are
    explicit ``null``, flagged for the larger Stage-1 binding follow-up, never invented.
    """
    sr = (prov.get("run_binding") or {}).get("selection_release") or {}
    return {
        "registry_scorer_view_sha256": sr.get("registry_scorer_view_sha256"),
        "programs_derived_from": sr.get("programs_derived_from"),
        "admitted_programs": list(sr.get("admitted_programs") or []),
        "n_programs": sr.get("n_programs"),
        "conditions": sorted({str(c) for c in conditions}),
        "n_conditions": len({str(c) for c in conditions}),
        "effect_universe_sha256": sr.get("effect_universe_sha256"),
        "effect_source_sha256": sr.get("effect_source_sha256"),
        # NOT yet bound — carried as null, never fabricated (Stage-1 binding follow-up)
        "stage1_release_self_sha256": None,
        "per_program_projection_sha256": None,
        "selector_condition_sequence": None,
    }


def build_release(addresses: list[dict[str, Any]], out_root: str,
                  provenance: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """The root inventory over every emitted bundle. Deterministic and self-addressed.

    ``provenance`` is any one bundle's provenance (all six share the release identity); the
    Stage-1 binding is read from it. On-disk hashes are re-read here so the inventory binds
    what actually LANDED, not what a caller claimed.
    """
    addrs = sorted(addresses, key=lambda a: a["bundle_key"])
    bundles = [_bundle_entry(a, os.path.join(out_root, a["dir"])) for a in addrs]
    conditions = sorted({a["from_condition"] for a in addrs}
                        | {a["to_condition"] for a in addrs})

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_RELEASE,
        "release_id_rule": RELEASE_ID_RULE,
        "lane": arm_bundle.BUNDLE_LANE,
        "analysis_mode": arm_bundle.ANALYSIS_MODE,
        "stage1_binding": stage1_binding(provenance or {}, conditions),
        "n_bundles": len(bundles),
        "n_logical_arms": sum(len(b["arm_keys"]) for b in bundles),
        "arm_keys": sorted(k for b in bundles for k in b["arm_keys"]),
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
