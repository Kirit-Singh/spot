"""Fast E2E harness checks (no Docker): fixtures well-formed + manifest plans.

The full DAG (STARsolo->kite->cellqc->de) runs via run_e2e.sh on tcefold.
"""

import gzip
from pathlib import Path

from spot_pipeline import load_manifest, plan_run

FIX = Path(__file__).parent / "e2e" / "fixtures"


def _fastq_ok(path: Path) -> bool:
    with gzip.open(path, "rt") as f:
        head, seq, plus, qual = (f.readline() for _ in range(4))
    return head.startswith("@") and plus.startswith("+") and len(seq.strip()) == len(qual.strip())


def test_fixtures_present_and_valid() -> None:
    for name in ("gex_R1", "gex_R2", "guide_R1", "guide_R2"):
        assert _fastq_ok(FIX / "raw" / f"{name}.fastq.gz")
    assert (FIX / "reference" / "mini.fa").read_text().startswith(">chr_mini")
    assert "NTC" in (FIX / "guides" / "t2g.txt").read_text()


def test_fixture_manifest_plans_two_branches() -> None:
    plan = plan_run(load_manifest(FIX / "manifest.yaml"))
    assert plan.gex_runs == ["FIXTURE_GEX"]
    assert plan.guide_runs == ["FIXTURE_GUIDE"]
