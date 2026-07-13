"""CLI + core runner for the Stage-3 v2 GBM disease-context handoff.

Reads the selected Stage-2 arm rows, acquires the Open Targets GBM/glioma association per
gene, PINS each raw public response as an artifact (basename + sha, never a machine path),
consumes an optional DepMap dependency handoff, and writes the descriptive, NON-GATING
handoff keyed by Ensembl id. Every disease number traces to its exact pinned bytes via the
per-gene ``source_provenance`` and the top-level ``raw_response_artifacts`` manifest. Records
run timestamp, source pins + licences, code hash, env, and the rerun command. It never
ranks, gates, or alters any Stage-2 output.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from typing import Any, Callable, Optional

from . import ot_disease as ot
from . import provenance as pv
from . import build_gbm_context as bg

_PKG_DIR = os.path.dirname(os.path.abspath(__file__))


def _package_code_paths() -> list[str]:
    return [os.path.join(_PKG_DIR, f) for f in os.listdir(_PKG_DIR) if f.endswith(".py")]


def _distinct_ensembls(arms: list[dict[str, Any]]) -> list[str]:
    seen, out = set(), []
    for r in arms:
        ens = r.get("target_ensembl")
        if ens and ens not in seen:
            seen.add(ens)
            out.append(ens)
    return out


def _acquire_open_targets(arms, tp, artifacts_dir):
    """Fetch OT per gene; pin each raw 200 response as an artifact (basename + sha).
    Returns (ot_by_gene, raw_response_artifacts, artifacts_dir_basename)."""
    ot_by_gene: dict[str, Any] = {}
    raw_artifacts: dict[str, Any] = {}
    wrote = False
    for ens in _distinct_ensembls(arms):
        res = ot.fetch_gene(ens, transport=tp)
        raw_text = res.pop("raw_response_text", None)      # never inline raw bytes in a record
        if raw_text is not None and res.get("http_status") == 200:
            sha = res.get("raw_sha256") or ""
            basename = f"ot_{ens}_{sha[:8]}.json"
            os.makedirs(artifacts_dir, exist_ok=True)
            with open(os.path.join(artifacts_dir, basename), "w", encoding="utf-8") as fh:
                fh.write(raw_text)
            wrote = True
            res["response_artifact"] = basename
            raw_artifacts[ens] = {
                "basename": basename, "sha256": res.get("raw_sha256"),
                "endpoint": res.get("endpoint"), "http_status": res.get("http_status"),
                "api_version": res.get("api_version"),
                "data_version": res.get("data_version"), "license": res.get("license")}
        ot_by_gene[ens] = res
    return ot_by_gene, raw_artifacts, (os.path.basename(artifacts_dir) if wrote else None)


def run(*, arms: list[dict[str, Any]], out_path: str,
        transport: Optional[Callable] = None, live: bool = False,
        depmap_handoff: Optional[dict[str, Any]] = None,
        now_utc: str, code_paths: Optional[list[str]] = None,
        artifacts_dir: Optional[str] = None) -> dict[str, Any]:
    """Build + write the handoff. ``transport`` (or ``live``) enables the OT axis; without
    either it stays ``not_evaluated`` (never invented). Raw responses are pinned next to the
    output as basename-only artifacts."""
    tp = transport if transport is not None else (ot.default_transport if live else None)
    adir = artifacts_dir or (out_path + ".artifacts")
    ot_by_gene: dict[str, Any] = {}
    raw_artifacts: dict[str, Any] = {}
    artifacts_rel: Optional[str] = None
    if tp is not None:
        ot_by_gene, raw_artifacts, artifacts_rel = _acquire_open_targets(arms, tp, adir)
    ot_evaluated = any(v.get("evaluated") for v in ot_by_gene.values())

    code_sha = pv.code_hash(code_paths or _package_code_paths())
    n_genes = len(_distinct_ensembls(arms))
    run_prov = pv.run_provenance(
        run_timestamp_utc=now_utc, code_sha256=code_sha, n_genes=n_genes,
        ot_evaluated=ot_evaluated, depmap_evaluated=bool(depmap_handoff))
    run_prov["raw_response_artifacts_dir"] = artifacts_rel      # relative basename or None

    handoff = bg.build_handoff(
        arms, ot_by_gene=ot_by_gene, dep_handoff=depmap_handoff,
        sources=pv.SOURCES, tissue_organ_axis=pv.TISSUE_ORGAN_AXIS,
        raw_response_artifacts=raw_artifacts, run_provenance=run_prov)

    with open(out_path, "w") as fh:
        json.dump(handoff, fh, indent=2, sort_keys=True)
    return handoff


def _now_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z")


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Stage-3 v2 GBM disease-context handoff")
    ap.add_argument("--arms", required=True, help="JSON list of selected Stage-2 arm rows")
    ap.add_argument("--out", required=True)
    ap.add_argument("--live-open-targets", action="store_true",
                    help="query the live Open Targets API (CC0)")
    ap.add_argument("--depmap-handoff", default=None,
                    help="optional DepMap per-gene dependency handoff JSON")
    ap.add_argument("--run-class", default="production",
                    help="label recorded in the handoff (e.g. real_open_targets_smoke)")
    a = ap.parse_args(argv)

    with open(a.arms) as fh:
        arms = json.load(fh)
    dep = None
    if a.depmap_handoff:
        with open(a.depmap_handoff) as fh:
            dep = json.load(fh)

    handoff = run(arms=arms, out_path=a.out, live=a.live_open_targets,
                  depmap_handoff=dep, now_utc=_now_utc())
    handoff.setdefault("run_provenance", {})["run_class"] = a.run_class
    with open(a.out, "w") as fh:
        json.dump(handoff, fh, indent=2, sort_keys=True)

    pvm = handoff["run_provenance"]["populated_vs_missing"]
    print(json.dumps({"out": a.out, "n_genes": handoff["n_genes"],
                      "populated_vs_missing": pvm,
                      "raw_response_artifacts": len(handoff["raw_response_artifacts"]),
                      "classification": handoff["classification"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
