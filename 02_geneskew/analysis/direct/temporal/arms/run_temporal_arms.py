"""Production ALL-ARM temporal entrypoint — the CLI the scheduler actually invokes.

    python -m direct.temporal.arms.run_temporal_arms \
        --stage1-view    stage01_stage2_registry_view.json \
        --stage1-release release_identity.json \
        --direct-bundle  Rest:<direct_rest_bundle_dir> \
        --direct-bundle  Stim8hr:<direct_stim8_bundle_dir> \
        --w10-report     Rest:<rest_admission.json> \
        --w10-report     Stim8hr:<stim8_admission.json> \
        --env-lock       analysis/stage02_solver_lock.txt \
        --conditions     Rest,Stim8hr,Stim48hr \
        --out-root       <dir> \
        [ --from-condition Rest --to-condition Stim8hr | --all-pairs ]

``--env-lock`` is the AUTHORITATIVE frozen/staged Stage-2 solver lock
(``analysis/stage02_solver_lock.txt``), the SAME lock Direct, pathway and the real run bind;
its bytes must hash to 2983d140…. The old ``_requirements/base.lock`` (b9284e63…) is NOT it
and is refused by name.

It lives in the ``arms`` subpackage — NOT beside ``run_temporal.py`` — on purpose: the
legacy temporal method binds ``code_tree_sha256`` over a FLAT listing of the temporal
package directory, so an entrypoint added there would change every legacy temporal_run_id.
The arms subpackage is invisible to that hash, so this producer is strictly additive.

WHAT IT DOES
------------
Derives the base-portable program axis and the per-program projection map from the bound
Stage-1 scorer view; reads EVERY temporal endpoint as an ADMITTED Direct all-arm bundle
(whose ``base_delta`` per (condition, program, target) IS the masked program projection);
differences two Direct bundles by the frozen temporal estimand (``base_delta(to) −
base_delta(from)``); and emits, per ordered pair, a content-addressed arm bundle
(``arm_bundle.json`` + ``temporal_provenance.json`` + ``temporal_preflight.json`` +
``rankings/*.json``) plus the root inventory ``temporal_arm_release.json``.

WHAT IT REFUSES
---------------
A missing/wrong solver lock; a Stage-1 view with no base-portable program; and — at the
named gates in ``arm_direct_source`` — a missing/ambiguous/stale/wrong-condition Direct
bundle, an increase/decrease pair that disagrees, a Direct bundle with no admitting W10
report, and the temporal fixture effect source standing in for a real Direct bundle. It
binds the two Direct bundle ids + their admissions, the committed solver-lock, the shared
code identity and the Stage-1 release, so a run is attributable to exactly what it stood on.

WHAT IT IS NOT
--------------
Not a fate/lineage claim; not a heavy-data loader; NOT a consumer of a giant serialized
``effect_source.json`` (there is none in the real run — the endpoints are Direct bundles).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Optional

from ...hashing import content_hash, file_sha256
from .. import config as tconfig
from . import arm_bundle as ab
from . import arm_direct_source as src
from . import arm_emit, arm_env, arm_programs


class _Release:
    """The bound Stage-1 view, in the shape ``arm_programs`` reads: ``.programs`` by id."""

    def __init__(self, view: dict[str, Any]):
        progs = view.get("programs") or []
        recs = progs.values() if isinstance(progs, dict) else progs
        self.programs = {str(r["program_id"]): r for r in recs}


def _load_json(path: str, what: str) -> dict[str, Any]:
    if not path or not os.path.exists(path):
        raise SystemExit(f"[run_temporal_arms] {what} not found: {path!r}")
    with open(path) as fh:
        return json.load(fh)


def _pairs(items: Optional[list[str]], what: str) -> dict[str, str]:
    """``COND:PATH`` entries into a ``{condition: path}`` map. Refuses ambiguity."""
    out: dict[str, str] = {}
    for entry in (items or []):
        if ":" not in entry:
            raise SystemExit(f"[run_temporal_arms] --{what} must be COND:PATH, got {entry!r}")
        cond, path = entry.split(":", 1)
        if cond in out:
            raise SystemExit(f"[run_temporal_arms] two --{what} for condition {cond!r}")
        out[cond] = path
    return out


def _stage1(view: dict[str, Any], view_path: str, release: dict[str, Any],
            conditions: list[str]) -> dict[str, Any]:
    """The Stage-1 metadata the bundle binds. Scorer-view hashes derived from the view file;
    release self-hash and the SCALAR projection identity come from the release; the
    per-program MAP is DERIVED by the producer from the view records."""
    return {
        "release_self_sha256": release.get("release_self_sha256"),
        "scorer_view_raw_sha256": file_sha256(view_path),
        "scorer_view_canonical_sha256": content_hash(view),
        "registry_scorer_projection_sha256":
            release.get("registry_scorer_projection_sha256"),
        "selector_condition_sequence": list(conditions),
    }


def _method(view: dict[str, Any], release: dict[str, Any]) -> dict[str, Any]:
    return ab.method_block(
        temporal_method_sha256=release.get("temporal_method_sha256"),
        direct_method_version=tconfig.ESTIMATOR_VERSION,
        direct_config_sha256=release.get("direct_config_sha256"),
        # the raw perturbation source hash the Direct bundles were built from (a
        # release-level constant); the PER-PAIR Direct bundle ids live in endpoint_source
        effect_source_sha256=release.get("effect_source_sha256"),
        effect_universe_sha256=view.get("effect_universe_symbols_sha256"))


def run(args) -> dict[str, Any]:
    """Build and emit the release from two admitted Direct all-arm bundles per pair.

    Every temporal endpoint is a Direct all-arm bundle at that condition; the frozen DiD is
    the difference of two Direct bundles' base deltas. There is no fixture effect source in
    the real run — a missing/ambiguous/stale/swapped/mismatched Direct bundle or a missing
    W10 report is refused at a named gate (see ``arm_direct_source``).
    """
    view = _load_json(args.stage1_view, "stage1 view")
    release = (_load_json(args.stage1_release, "stage1 release")
               if args.stage1_release else {})
    direct = _pairs(args.direct_bundle, "direct-bundle")
    w10 = _pairs(args.w10_report, "w10-report")

    admitted = arm_programs.admitted_programs(_Release(view))
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    if len(conditions) != len(set(conditions)) or len(conditions) < 2:
        raise SystemExit(
            f"[run_temporal_arms] --conditions must be >=2 distinct conditions, got "
            f"{conditions}")

    env_lock = arm_env.env_lock_block(args.env_lock)
    stage1 = _stage1(view, args.stage1_view, release, conditions)
    method = _method(view, release)
    code = ab.code_identity()

    if args.from_condition and args.to_condition:
        pairs = [(args.from_condition, args.to_condition)]
    elif args.all_pairs:
        pairs = arm_programs.ordered_pairs(conditions)
    else:
        raise SystemExit(
            "[run_temporal_arms] name a pair (--from-condition/--to-condition) or "
            "--all-pairs")

    # load + verify each condition's admitted Direct bundle ONCE (fail-closed on the gates)
    loaded: dict[str, dict[str, Any]] = {}
    for cond in sorted({c for pair in pairs for c in pair}):
        if cond not in direct:
            raise SystemExit(f"[run_temporal_arms] no --direct-bundle for condition {cond!r}")
        loaded[cond] = src.load_direct_bundle(
            direct[cond], expect_condition=cond, w10_report=w10.get(cond))

    bundles = [
        ab.build_bundle(
            from_condition=frm, to_condition=to, admitted=admitted,
            from_endpoints=src.endpoints(loaded[frm], admitted),
            to_endpoints=src.endpoints(loaded[to], admitted),
            method=method, conditions=conditions,
            scorer_view_sha256=stage1["scorer_view_canonical_sha256"],
            stage1=stage1, env_lock=env_lock,
            endpoint_source=src.source_binding(loaded[frm], loaded[to]), code=code)
        for frm, to in pairs]

    if args.all_pairs:
        # the COMPLETE release: every ordered pair + the content-addressed root inventory
        rel = arm_emit.emit_release(
            bundles, args.out_root,
            expect_n_bundles=len(arm_programs.ordered_pairs(conditions)))
        return {"mode": "release", "release_id": rel["release_id"],
                "n_bundles": rel["n_bundles"], "n_logical_arms": rel["n_logical_arms"],
                "release_file": rel["release_file"]}
    # ONE ordered pair (the scheduler's per-pair invocation): one content-addressed bundle,
    # no root inventory — the release manifest is written once the whole run has landed.
    addr = arm_emit.emit_bundle(bundles[0], args.out_root)
    return {"mode": "bundle", "bundle_id": addr["bundle_id"],
            "bundle_key": addr["bundle_key"], "n_arms": addr["n_arms"], "dir": addr["dir"]}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m direct.temporal.arms.run_temporal_arms",
        description="Stage-2 production ALL-ARM temporal producer: emit content-addressed "
                    "reusable temporal arm bundles (population-level difference-in-"
                    "differences on program projections; NOT fate/lineage).")
    ap.add_argument("--stage1-view", required=True,
                    help="the bound Stage-1 scorer view (stage01_stage2_registry_view.json): "
                         "the ONE source of the base-portable programs and their records")
    ap.add_argument("--stage1-release", default=None,
                    help="Stage-1 release identity (JSON): release_self_sha256 and the SCALAR "
                         "registry_scorer_projection_sha256 the release publishes")
    ap.add_argument("--direct-bundle", action="append", metavar="COND:PATH",
                    help="an ADMITTED Direct all-arm bundle for a condition, as COND:PATH "
                         "(repeat once per condition). Its base_delta rows ARE the temporal "
                         "endpoints; there is no fixture effect source in the real run")
    ap.add_argument("--w10-report", action="append", metavar="COND:PATH", default=None,
                    help="the independent report admitting each Direct bundle, COND:PATH. A "
                         "Direct endpoint with no admitting report is refused")
    ap.add_argument("--env-lock", required=True,
                    help="the committed Stage-2 solver-lock; its BYTES are read and bound as "
                         "env_lock_sha256. A missing or swapped lock is refused")
    ap.add_argument("--conditions", required=True,
                    help="the DECLARED selector condition sequence, comma-separated and in "
                         "order (e.g. Rest,Stim8hr,Stim48hr) — carried verbatim, never sorted")
    ap.add_argument("--out-root", required=True,
                    help="output directory; one bundle dir per ordered pair plus the root "
                         "content-addressed temporal_arm_release.json")
    pair = ap.add_argument_group("which ordered pair(s) to emit")
    pair.add_argument("--from-condition", default=None)
    pair.add_argument("--to-condition", default=None)
    pair.add_argument("--all-pairs", action="store_true",
                      help="emit every ordered pair the condition universe supports plus the "
                           "complete-release root inventory")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    result = run(args)
    print(json.dumps({**result, "out_root": args.out_root}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
