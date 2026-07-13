"""Production ALL-ARM temporal entrypoint — the CLI the scheduler actually invokes.

    python -m direct.temporal.arms.run_temporal_arms \
        --stage1-view    stage01_stage2_registry_view.json \
        --stage1-release release_identity.json \
        --effect-source  effect_source.json \
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
Stage-1 scorer view, projects EVERY admitted program for every target at each named
condition (the masked program projection the direct lane uses), differences the two
condition populations by the frozen temporal estimand, and emits, per ordered pair, a
content-addressed arm bundle (``arm_bundle.json`` + ``temporal_provenance.json`` +
``temporal_preflight.json`` + ``rankings/*.json``) plus, over the whole run, the root
content-addressed inventory ``temporal_arm_release.json``.

WHAT IT REFUSES
---------------
A missing or swapped solver lock; a Stage-1 view with no base-portable program; a condition
the effect source does not ship; and — via the producer self-check — any bundle it cannot
itself reconstruct. It binds the committed Stage-2 solver-lock, the shared code identity and
the Stage-1 release identity, so a run is attributable to its build, its environment and its
Stage-1 release.

WHAT IT IS NOT
--------------
Not a fate/lineage claim; not a heavy-data loader. The ``effect source`` is the
projection-ready effect matrix (per condition, per target: an effect vector aligned to a
gene index, the contributor mask, and the upstream QC / denominators). Deriving that matrix
from the raw perturbation data is the upstream step; this entrypoint consumes it.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any

from ...hashing import content_hash, file_sha256
from .. import config as tconfig
from . import arm_bundle as ab
from . import arm_emit, arm_env, arm_programs
from . import arm_estimand as est

EFFECT_SOURCE_SCHEMA = "spot.stage02_temporal_arm_effect_source.v1"

# The per-endpoint fields the effect source supplies straight onto the endpoint.
_ENDPOINT_PASSTHROUGH = (
    "released_estimate_id", "target_symbol", "target_ensembl", "target_id_namespace",
    "base_qc_passed", "base_qc_state", "base_qc_reasons",
    "qc_ontarget_significant", "qc_ontarget_effect_size", "qc_target_baseMean",
    "qc_low_target_expression", "mask_resolved", "estimate_mask_sha256",
    "mask_gene_count", "mask_unresolved_reason", "n_guide_slots_released",
    "n_guides_mapped", "n_guides_evaluated", "n_splits_total", "n_splits_evaluable",
    "donor_split_denominator", "effective_donor_n", "n_cells_target")


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


def build_endpoints(admitted: dict[str, dict[str, Any]], effect_source: dict[str, Any],
                    condition: str) -> list[ab.TargetEndpoint]:
    """Project EVERY admitted program for every target at ``condition``.

    ``project_programs`` runs the masked program projection (panel mean − control mean,
    after the target's own contributor mask) for all admitted programs at once, so the arm
    bundle later differences a COMPLETE program axis rather than two poles.
    """
    import numpy as np

    gene_index = effect_source["gene_index"]
    conds = effect_source.get("conditions") or {}
    if condition not in conds:
        raise SystemExit(
            f"[run_temporal_arms] effect source ships no condition {condition!r}; "
            f"it has {sorted(conds)}")
    out: list[ab.TargetEndpoint] = []
    for tid, t in sorted((conds[condition].get("targets") or {}).items()):
        effect_row = np.asarray(t["effect"], dtype=float)
        mask = set(t.get("mask") or [])
        deltas = est.project_programs(effect_row, admitted, gene_index, mask)
        fields = {k: t.get(k) for k in _ENDPOINT_PASSTHROUGH if k in t}
        out.append(ab.TargetEndpoint(target_id=str(tid), program_delta=deltas, **fields))
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


def _method(view: dict[str, Any], effect_source_path: str,
            release: dict[str, Any]) -> dict[str, Any]:
    return ab.method_block(
        temporal_method_sha256=release.get("temporal_method_sha256"),
        direct_method_version=tconfig.ESTIMATOR_VERSION,
        direct_config_sha256=release.get("direct_config_sha256"),
        effect_source_sha256=file_sha256(effect_source_path),
        effect_universe_sha256=view.get("effect_universe_symbols_sha256"))


def run(args) -> dict[str, Any]:
    """Build and emit the release. Returns the emitted release inventory (relative-only)."""
    view = _load_json(args.stage1_view, "stage1 view")
    effect_source = _load_json(args.effect_source, "effect source")
    if effect_source.get("schema_version") != EFFECT_SOURCE_SCHEMA:
        raise SystemExit(
            f"[run_temporal_arms] effect source schema "
            f"{effect_source.get('schema_version')!r} is not {EFFECT_SOURCE_SCHEMA!r}")
    release = (_load_json(args.stage1_release, "stage1 release")
               if args.stage1_release else {})

    admitted = arm_programs.admitted_programs(_Release(view))
    conditions = [c.strip() for c in args.conditions.split(",") if c.strip()]
    if len(conditions) != len(set(conditions)) or len(conditions) < 2:
        raise SystemExit(
            f"[run_temporal_arms] --conditions must be >=2 distinct conditions, got "
            f"{conditions}")

    env_lock = arm_env.env_lock_block(args.env_lock)
    stage1 = _stage1(view, args.stage1_view, release, conditions)
    method = _method(view, args.effect_source, release)
    code = ab.code_identity()

    if args.from_condition and args.to_condition:
        pairs = [(args.from_condition, args.to_condition)]
    elif args.all_pairs:
        pairs = arm_programs.ordered_pairs(conditions)
    else:
        raise SystemExit(
            "[run_temporal_arms] name a pair (--from-condition/--to-condition) or "
            "--all-pairs")

    endpoints = {c: build_endpoints(admitted, effect_source, c)
                 for c in sorted({c for pair in pairs for c in pair})}
    bundles = [
        ab.build_bundle(
            from_condition=frm, to_condition=to, admitted=admitted,
            from_endpoints=endpoints[frm], to_endpoints=endpoints[to],
            method=method, conditions=conditions,
            scorer_view_sha256=stage1["scorer_view_canonical_sha256"],
            stage1=stage1, env_lock=env_lock, code=code)
        for frm, to in pairs]

    expect = len(arm_programs.ordered_pairs(conditions)) if args.all_pairs else None
    return arm_emit.emit_release(bundles, args.out_root, expect_n_bundles=expect)


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
    ap.add_argument("--effect-source", required=True,
                    help="projection-ready effect matrix (per condition/target: effect "
                         "vector, contributor mask, upstream QC and denominators)")
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
    rel = run(args)
    print(json.dumps({"release_id": rel["release_id"], "n_bundles": rel["n_bundles"],
                      "n_logical_arms": rel["n_logical_arms"],
                      "release_file": rel["release_file"], "out_root": args.out_root}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
