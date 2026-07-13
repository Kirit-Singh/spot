"""A flag Stage-3 ACCEPTS but does not CONSUME is worse than a flag it does not have.

`--stage2-bridge` and `--stage2-bridge-report` were added to the CLI ahead of the consumer, so
argparse accepted them and `_v2_main` never read them. A caller passing the bridge would have
got a run that silently never honoured it — and an artifact that LOOKS like it was built on
admitted identity and modality when it was not.

That is the defect this lane keeps meeting in new clothes: a name that isn't a binding. The
flag named the bridge; nothing bound it.

THE CONSUMER HAS LANDED. `stage2_bridge.admit_bridge` reads the bytes at the paths these flags
name, and `bridge_join` types the native records from them. So this file no longer asserts a
refusal-in-waiting: it asserts that the flags are CONSUMED, and that a bridge that cannot be
admitted still stops the run dead. The native ranking rows carry {target_id, arm_value, evaluable,
rank} — no namespace and no modality — so a run without an admitted bridge would have to INVENT
both, and it will not.
"""
from __future__ import annotations

import os

from druglink import run_stage3, stage2_aggregate as sa


def test_the_bridge_is_REQUIRED_on_the_v2_path():
    assert "--stage2-bridge" in run_stage3.V2_REQUIRED
    assert "--stage2-bridge-report" in run_stage3.V2_REQUIRED


def test_the_RECEIPT_is_required_too():
    """W3 emits THREE files, and the receipt is the JOIN. The bridge report binds no bridge
    bytes — only the receipt binds the aggregate AND the bridge by raw + canonical hash. A
    bridge presented with a report but no receipt is an ADMIT about nothing in particular, and
    it would let a verdict travel with an artifact it was never about."""
    assert "--stage2-bridge-receipt" in run_stage3.V2_REQUIRED


def test_the_readiness_check_reports_whether_the_ADMITTER_EXISTS():
    """It must be a fact about the code, not a hand-set Boolean. A hand-set flag is exactly the
    `DETACHED_CLONE_MATRIX_GREEN` defect: a constant in Stage-3's own source that no artifact
    could flip, asserting a state nothing had verified."""
    assert run_stage3.bridge_consumer_ready() is hasattr(sa, "admit_bridge")


def test_the_v2_path_REFUSES_when_the_bridge_cannot_be_admitted(tmp_path, capsys):
    """The flags are consumed, so a bridge that is not on disk stops the run — at a NAMED bridge
    gate, and with nothing written. A run that shrugged and proceeded would emit an artifact whose
    identity and modality it had invented."""
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
        "--stage2-bridge-receipt", str(tmp_path / "receipt.json"),
    ])
    assert code == 3, "a run that cannot honour the bridge must refuse, not proceed"
    printed = capsys.readouterr().out
    assert "REFUSED" in printed and "[" in printed, (
        "the refusal must NAME its gate, so nobody reads it as a data-driven 'no candidates'")
    # ...and it wrote NOTHING. A refusal that leaves a bundle behind is not a refusal.
    assert not (out.exists() and os.listdir(out)), "a refused run must write no bundle"


def test_the_refusal_says_WHY_rather_than_only_that(capsys, tmp_path):
    """A gate name tells you WHICH check failed. The sentence must say why the check EXISTS —
    otherwise the next reader deletes it.

    The aggregate is REAL here, so the run gets past the aggregate gate and the BRIDGE gate is the
    one that speaks. (With a missing manifest the aggregate refuses first, which is correct
    ordering and a different sentence entirely.)
    """
    import native_aggregate_fixture as NAF
    paths = NAF.build(str(tmp_path / "agg"))
    os.remove(paths["bridge"])

    run_stage3.main([
        "--v2", "--artifact-class", "fixture", "--output-root", str(tmp_path / "o"),
        "--universe-store", str(tmp_path),
        "--stage2-manifest", paths["manifest"], "--stage2-report", paths["report"],
        "--bundles-root", paths["bundles_root"],
        "--stage1-release", paths["stage1_release"],
        "--stage2-bridge", paths["bridge"],
        "--stage2-bridge-report", paths["bridge_report"],
        "--stage2-bridge-receipt", paths["receipt"]])
    printed = capsys.readouterr().out.lower()
    assert "the_stage3_bridge_is_not_on_disk" in printed
    # the facts that ONLY the bridge carries — the reason a bridge-less run is impossible
    assert "identity" in printed and "modality" in printed
    assert "no fixture fallback" in printed


def test_a_v2_run_missing_any_required_input_refuses_and_writes_nothing(tmp_path, capsys):
    out = tmp_path / "out2"
    code = run_stage3.main(["--v2", "--artifact-class", "analysis",
                            "--output-root", str(out),
                            "--universe-store", str(tmp_path)])
    assert code != 0
    assert not (out.exists() and os.listdir(out))
