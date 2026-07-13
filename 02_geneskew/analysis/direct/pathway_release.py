"""``pathway_arm_release.json`` — the content-addressed ROOT inventory of the pathway release.

The aggregate verifier expects a per-lane PRODUCER INVENTORY for every lane it admits
(``verify_release_envelope``): an immutable, content-addressed artifact naming every bundle
and every byte it stands on, whose ``external_admission.status`` is ``pending`` — the ONLY
honest producer state. Temporal already ships one (``temporal_arm_release.json``); the audit
(BLOCKER 7) found NO production implementation emitting the pathway one, so the aggregate
demanded a file nothing wrote.

This is that producer. It is the exact sibling of ``temporal/arms/arm_release.py``, over the
pathway topology instead of the temporal one:

    physical bundles = 3 conditions x 2 pinned gene-set sources = 6
    logical arms     = |admitted programs| x {increase, decrease} x (condition, source)

A COMPLETE pathway release is exactly that Cartesian grid, once each. A missing cell, a
duplicated (condition, source), or a source the release never shipped is REFUSED at a named
gate — never truncated, never inventoried. The producer does NOT admit its own release: an
independent verifier reads the six bundles back off disk and emits a SEPARATE envelope.

Relative-only, no timestamp, no machine-local address: byte-stable and portable across hosts.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from .hashing import content_hash, file_sha256

SCHEMA_RELEASE = "spot.stage02_pathway_arm_release.v1"
RELEASE_FILENAME = "pathway_arm_release.json"
RELEASE_ID_RULE = "sha256(canonical JSON excluding release_id)"
LANE = "pathway"
TOPOLOGY_RULE_ID = (
    "spot.stage02.pathway.arm.topology.programs_x_changes_x_conditions_x_sources.v1")

# The independent pathway verifier that ALONE may admit this release, and the external
# admission report schema the aggregate reads (the shared external-admission report schema,
# as temporal and the lane-admission adapter already use).
REQUIRED_VERIFIER_ID = "spot.stage02.pathway.arm.independent_verifier.v1"
REQUIRED_REPORT_SCHEMA = "spot.stage02_temporal_arm_external_admission.v1"

# The pathway bundle's on-disk top files (the ones that are JSON and CAN be canonically
# hashed). Only those PRESENT are inventoried — a real W4 bundle and a fixture may differ,
# and the inventory binds what actually landed.
_TOP_FILES = ("arm_bundle.json", "pathway_provenance.json",
              "pathway_verification.json", "convergence.json")

# THE NAMED REFUSAL GATES.
REFUSE_NO_BUNDLES = "no_pathway_bundle_was_supplied"
REFUSE_DUPLICATE_CELL = "a_condition_x_source_cell_was_produced_more_than_once"
REFUSE_UNKNOWN_CELL = "a_bundle_names_a_condition_or_source_the_release_never_shipped"
REFUSE_MISSING_CELL = "the_release_grid_has_a_condition_x_source_cell_with_no_bundle"
REFUSE_BAD_BUNDLE = "a_pathway_bundle_is_missing_or_unreadable"


class PathwayReleaseError(ValueError):
    """The pathway release inventory is not the complete 3x2 grid the release implies."""

    def __init__(self, reason: str, message: str):
        super().__init__(f"[{reason}] {message}")
        self.reason = reason


def _load(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        raise PathwayReleaseError(REFUSE_BAD_BUNDLE, f"no bundle document at {path!r}")
    try:
        with open(path) as fh:
            return json.load(fh)
    except json.JSONDecodeError as exc:
        raise PathwayReleaseError(
            REFUSE_BAD_BUNDLE, f"{path!r} is not readable JSON: {exc}") from exc


def _hashes(path: str) -> dict[str, str]:
    raw = file_sha256(path)
    with open(path) as fh:
        canon = content_hash(json.load(fh))
    return {"raw_sha256": raw, "canonical_sha256": canon}


def _cell(bundle: dict[str, Any]) -> tuple[str, str]:
    """(condition, source) of a pathway bundle, from its own bytes. Never guessed."""
    ctx = bundle.get("context") or {}
    condition = (ctx.get("condition") if isinstance(ctx, dict) else None) \
        or bundle.get("condition")
    source = (ctx.get("gene_set_source") or ctx.get("source")
              if isinstance(ctx, dict) else None) or bundle.get("source")
    return str(condition), str(source)


def _arm_keys(bundle: dict[str, Any]) -> list[str]:
    return [str(a.get("arm_key") or a.get("pathway_arm_key"))
            for a in (bundle.get("arms") or [])]


def _bundle_entry(out_root: str, out_dir: str) -> dict[str, Any]:
    """One bundle's row: its context, its top files and EVERY ranking file the arms bind."""
    rel_dir = os.path.relpath(out_dir, out_root).replace(os.sep, "/")
    bundle = _load(os.path.join(out_dir, "arm_bundle.json"))
    cond, source = _cell(bundle)
    bundle_id = str(bundle.get("bundle_id") or bundle.get("pathway_run_id"))

    files = {name: _hashes(os.path.join(out_dir, name))
             for name in _TOP_FILES if os.path.exists(os.path.join(out_dir, name))}

    # RANKINGS, exactly as the arms bind them (so the inventory names neither more nor fewer
    # than the arms do — the check the aggregate's ``inventory_matches_arms`` enforces). A
    # producer whose arms carry no per-arm ranking file simply inventories none.
    rankings: dict[str, dict[str, str]] = {}
    for arm in (bundle.get("arms") or []):
        binding = arm.get("ranking")
        if isinstance(binding, dict) and binding.get("path"):
            rel = str(binding["path"])
            p = os.path.join(out_dir, rel)
            if os.path.exists(p):
                rankings[rel] = _hashes(p)
    rdir = os.path.join(out_dir, "rankings")
    if os.path.isdir(rdir):
        for fn in sorted(os.listdir(rdir)):
            rel = f"rankings/{fn}"
            rankings.setdefault(rel, _hashes(os.path.join(out_dir, rel)))

    return {
        "bundle_key": f"{cond}|{source}",
        "bundle_id": bundle_id,
        "condition": cond,
        "source": source,
        "relative_dir": rel_dir,
        "n_arms": len(bundle.get("arms") or []),
        "arm_keys": sorted(_arm_keys(bundle)),
        "files": files,
        "rankings": rankings,
    }


def _stage1_binding(out_dir: str) -> dict[str, Any]:
    """The v3 release identity the bundle stood on, from its provenance (best effort)."""
    prov_path = os.path.join(out_dir, "pathway_provenance.json")
    if not os.path.exists(prov_path):
        return {}
    prov = _load(prov_path)
    rb = prov.get("run_binding") or {}
    return dict(rb.get("selection_release")
                or {"stage1_release_hashes": rb.get("stage1_release_hashes")}
                or {})


def _env_lock(out_dir: str) -> dict[str, Any]:
    prov_path = os.path.join(out_dir, "pathway_provenance.json")
    if not os.path.exists(prov_path):
        return {}
    prov = _load(prov_path)
    block = ((prov.get("run_binding") or {}).get("environment_lock") or {})
    return dict(block) if isinstance(block, dict) else {}


def expected_grid(conditions: list[str], sources: list[str]) -> list[tuple[str, str]]:
    conds = sorted({str(c) for c in conditions})
    srcs = sorted({str(s) for s in sources})
    return [(c, s) for c in conds for s in srcs]


def assert_grid(expected: list[tuple[str, str]],
                produced: list[tuple[str, str]]) -> None:
    """Exactly the release's (condition, source) grid, each cell once. Nothing more/less."""
    dupes = sorted({c for c in produced if produced.count(c) > 1})
    if dupes:
        raise PathwayReleaseError(
            REFUSE_DUPLICATE_CELL,
            f"(condition, source) cells produced more than once: {dupes}. Two bundles for "
            "one cell are two identities for one measurement")
    unknown = sorted(set(produced) - set(expected))
    if unknown:
        raise PathwayReleaseError(
            REFUSE_UNKNOWN_CELL,
            f"bundles name cells the release never shipped: {unknown}. The release grid is "
            f"{sorted(expected)}")
    missing = sorted(set(expected) - set(produced))
    if missing:
        raise PathwayReleaseError(
            REFUSE_MISSING_CELL,
            f"the release grid is {sorted(expected)} but no bundle was produced for "
            f"{missing}. An incomplete pathway release must not pass as a complete one")


def build_release(bundle_dirs: list[str], out_root: str, *,
                  conditions: Optional[list[str]] = None,
                  sources: Optional[list[str]] = None,
                  write: bool = True) -> dict[str, Any]:
    """The root inventory over every emitted pathway bundle. Deterministic, self-addressed.

    ``conditions`` and ``sources`` are the AUTHORITATIVE grid from the bound Stage-1 v3
    release. When omitted they are derived from the bundles themselves — which cannot see a
    wholly-absent source, so passing the release's own conditions/sources is the safe path.
    """
    if not bundle_dirs:
        raise PathwayReleaseError(REFUSE_NO_BUNDLES,
                                  "a pathway release is 3 conditions x 2 sources; zero "
                                  "bundles is not a release")
    entries = sorted((_bundle_entry(out_root, d) for d in bundle_dirs),
                     key=lambda b: b["bundle_key"])
    produced = [(b["condition"], b["source"]) for b in entries]

    conds = list(conditions) if conditions is not None \
        else sorted({c for c, _s in produced})
    srcs = list(sources) if sources is not None \
        else sorted({s for _c, s in produced})
    grid = expected_grid(conds, srcs)
    assert_grid(grid, produced)

    arm_keys = sorted(k for b in entries for k in b["arm_keys"])
    s1 = _stage1_binding(bundle_dirs[0])
    env_lock = _env_lock(bundle_dirs[0])

    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_RELEASE,
        "release_id_rule": RELEASE_ID_RULE,
        "lane": LANE,
        "stage1_binding": s1,
        "env_lock": env_lock,
        "env_lock_sha256": env_lock.get("sha256") or env_lock.get("env_lock_sha256"),
        "topology": {
            "topology_rule_id": TOPOLOGY_RULE_ID,
            "n_conditions": len(sorted({str(c) for c in conds})),
            "n_sources": len(sorted({str(s) for s in srcs})),
            "conditions": sorted({str(c) for c in conds}),
            "sources": sorted({str(s) for s in srcs}),
            "expected_n_bundles": len(grid),
            "grid": [f"{c}|{s}" for c, s in grid],
        },
        "n_bundles": len(entries),
        "n_logical_arms": len(arm_keys),
        "arm_keys": arm_keys,
        "bundles": entries,
        # `pending` is the ONLY honest producer state; the independent verifier emits a
        # SEPARATE content-addressed envelope and never rewrites this.
        "external_admission": {
            "status": "pending",
            "required_verifier_id": REQUIRED_VERIFIER_ID,
            "required_report_schema_version": REQUIRED_REPORT_SCHEMA,
        },
    }
    manifest["release_id"] = content_hash(manifest)

    if write:
        os.makedirs(out_root, exist_ok=True)
        with open(os.path.join(out_root, RELEASE_FILENAME), "w") as fh:
            json.dump(manifest, fh, indent=2, sort_keys=True)
            fh.write("\n")
    return manifest


def main(argv=None) -> int:
    import argparse

    from .arm_topology import load_release

    ap = argparse.ArgumentParser(
        description="Build the pathway release root inventory (pathway_arm_release.json): "
                    "the content-addressed 3-condition x 2-source, PENDING producer "
                    "inventory the aggregate admits a lane against.")
    ap.add_argument("--pathway", nargs="+", required=True, metavar="DIR",
                    help="the six pathway all-arm bundle directories (condition x source)")
    ap.add_argument("--release", default=None,
                    help="the authoritative Stage-1 v3 release: the ONLY source of the "
                         "conditions and pathway sources the grid is checked against")
    ap.add_argument("--release-root", default=None,
                    help="the directory the release is STAGED in")
    ap.add_argument("--out-root", required=True,
                    help="pathway_arm_release.json is written here (the release root)")
    args = ap.parse_args(argv)

    conditions = sources = None
    if args.release:
        if not args.release_root:
            ap.error("--release requires --release-root")
        release = load_release(args.release, args.release_root)
        conditions, sources = release["conditions"], release["gene_set_sources"]

    doc = build_release(args.pathway, args.out_root,
                        conditions=conditions, sources=sources)
    print(json.dumps({k: v for k, v in doc.items() if k != "bundles"},
                     indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
