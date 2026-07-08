"""Validate a dataset manifest (the gate), then resolve the run plan.

Perturb-seq is a two-library problem: cells are called once on the GEX branch,
guides assigned to those cells. The driver validates via contracts and splits
the runs into the GEX and GUIDE branches the DAG consumes.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

import yaml
from spot_contracts import DatasetManifest, LibraryType

STAGES = ("fetch", "fastp", "starsolo", "guide", "cellqc", "de")


@dataclass(frozen=True)
class RunPlan:
    dataset_id: str
    gex_runs: list[str] = field(default_factory=list)
    guide_runs: list[str] = field(default_factory=list)
    stages: list[str] = field(default_factory=lambda: list(STAGES))


def load_manifest(path: str | Path) -> DatasetManifest:
    """Load + gate a manifest.yaml. Raises pydantic ValidationError on failure."""
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    return DatasetManifest.model_validate(data)


def plan_run(manifest: DatasetManifest) -> RunPlan:
    """Split runs into GEX/GUIDE branches; cells are called once on GEX."""
    gex = [r.accession for r in manifest.runs if r.library_type is LibraryType.GEX]
    guide = [r.accession for r in manifest.runs if r.library_type is LibraryType.GUIDE]
    return RunPlan(
        dataset_id=manifest.dataset_id, gex_runs=gex, guide_runs=guide, stages=list(STAGES)
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="spot-pipeline", description="Validate a dataset manifest and print the run plan."
    )
    parser.add_argument("manifest", help="path to a dataset manifest.yaml")
    ns = parser.parse_args(argv)
    try:
        manifest = load_manifest(ns.manifest)
    except Exception as exc:  # noqa: BLE001 - report any gate failure to the user
        print(f"manifest gate FAILED: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(asdict(plan_run(manifest)), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
