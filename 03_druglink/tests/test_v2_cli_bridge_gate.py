"""A flag Stage-3 ACCEPTS but does not CONSUME is worse than a flag it does not have.

`--stage2-bridge` and `--stage2-bridge-report` were added to the CLI ahead of the consumer, so
argparse accepted them and `_v2_main` never read them. A caller passing the bridge would have
got a run that silently never honoured it — and an artifact that LOOKS like it was built on
admitted identity and modality when it was not.

That is the defect this lane keeps meeting in new clothes: a name that isn't a binding. The
flag named the bridge; nothing bound it.

Until the consumer exists, the v2 path REFUSES BY NAME. It does not run a bridge-less analysis,
because the native ranking rows carry {target_id, arm_value, evaluable, rank} — no namespace and
no modality — so a run without the bridge would have to INVENT both.
"""
from __future__ import annotations

import os

import pytest

from druglink import run_stage3, stage2_aggregate as sa


def test_the_bridge_is_REQUIRED_on_the_v2_path():
    assert "--stage2-bridge" in run_stage3.V2_REQUIRED
    assert "--stage2-bridge-report" in run_stage3.V2_REQUIRED


def test_the_readiness_check_reports_whether_the_ADMITTER_EXISTS():
    """It must be a fact about the code, not a hand-set Boolean. A hand-set flag is exactly the
    `DETACHED_CLONE_MATRIX_GREEN` defect: a constant in Stage-3's own source that no artifact
    could flip, asserting a state nothing had verified."""
    assert run_stage3.bridge_consumer_ready() is hasattr(sa, "admit_bridge")


def test_the_v2_path_refuses_by_name_while_the_consumer_is_absent(tmp_path, capsys):
    if run_stage3.bridge_consumer_ready():
        pytest.skip("the bridge consumer has landed; this gate is retired")

    out = tmp_path / "out"
    code = run_stage3.main([
        "--v2", "--artifact-class", "analysis", "--output-root", str(out),
        "--universe-store", str(tmp_path / "store"),
        "--stage2-manifest", str(tmp_path / "m.json"),
        "--stage2-report", str(tmp_path / "r.json"),
        "--bundles-root", str(tmp_path),
        "--stage1-release", str(tmp_path / "rel.json"),
        "--stage2-bridge", str(tmp_path / "bridge.json"),
        "--stage2-bridge-report", str(tmp_path / "bridge_report.json"),
    ])
    assert code == 3, "a run that cannot honour the bridge must refuse, not proceed"

    printed = capsys.readouterr().out
    assert run_stage3.GATE_BRIDGE_CONSUMER_NOT_IMPLEMENTED in printed, (
        "the refusal must NAME its gate, so nobody reads it as a data-driven 'no candidates'")

    # ...and it wrote NOTHING. A refusal that leaves a bundle behind is not a refusal.
    assert not (out.exists() and os.listdir(out)), "a refused run must write no bundle"


def test_the_refusal_says_WHY_rather_than_only_that(capsys, tmp_path):
    if run_stage3.bridge_consumer_ready():
        pytest.skip("the bridge consumer has landed; this gate is retired")
    run_stage3.main([
        "--v2", "--artifact-class", "analysis", "--output-root", str(tmp_path / "o"),
        "--universe-store", str(tmp_path), "--stage2-manifest", str(tmp_path / "m.json"),
        "--stage2-report", str(tmp_path / "r.json"), "--bundles-root", str(tmp_path),
        "--stage1-release", str(tmp_path / "rel.json"),
        "--stage2-bridge", str(tmp_path / "b.json"),
        "--stage2-bridge-report", str(tmp_path / "br.json")])
    printed = capsys.readouterr().out.lower()
    # the two facts that only the bridge carries — the reason a bridge-less run is impossible
    assert "namespace" in printed and "modality" in printed


def test_a_v2_run_missing_any_required_input_refuses_and_writes_nothing(tmp_path, capsys):
    out = tmp_path / "out2"
    code = run_stage3.main(["--v2", "--artifact-class", "analysis",
                            "--output-root", str(out),
                            "--universe-store", str(tmp_path)])
    assert code != 0
    assert not (out.exists() and os.listdir(out))
