"""The research_only lane: same evidence, same computation, no production claim."""
import contextlib
import io
import json
import os

import pandas as pd
import pytest
from direct import config, trust
from direct import selection as sel_mod
from direct.run_screen import build_screen
from direct.selection import SelectionError
from direct.trust import TrustError
from direct.verify_run import main as verify_main


def _prov(result):
    with open(os.path.join(result["out_dir"], "provenance.json")) as fh:
        return json.load(fh)


def test_research_only_is_an_executable_lane():
    assert config.LANE_RESEARCH == "research_only"
    assert config.LANE_RESEARCH in config.LANES
    assert hasattr(sel_mod, "load_research_selection")
    assert hasattr(trust, "load_research_release")


def test_research_runs_with_the_failed_production_gate(synthetic_run):
    """The whole point: 0/N production-selectable must not block research."""
    result = build_screen(synthetic_run(lane="research_only",
                                        stage1_selectable=False))
    prov = _prov(result)
    assert result["lane"] == "research_only"
    assert result["namespace"] == "research_only"
    assert prov["production_gate_passed"] is False
    assert prov["run_binding"]["stage1_release"]["n_production_selectable"] == 0

    screen = pd.read_parquet(os.path.join(result["out_dir"], "screen.parquet"))
    assert screen["A_evaluable"].astype(bool).any()      # it really analysed
    assert screen["rank_toward_B"].notna().any()


def test_a_research_run_is_never_production_or_stage3_eligible(synthetic_run):
    result = build_screen(synthetic_run(lane="research_only",
                                        stage1_selectable=False))
    prov = _prov(result)
    assert result["production_eligible"] is False
    assert result["stage3_eligible"] is False
    assert prov["production_eligible"] is False
    assert prov["stage3_eligible"] is False
    assert prov["axis"]["may_write_production_pointer"] is False


def test_production_still_refuses_the_same_failed_gate(synthetic_run):
    with pytest.raises(SelectionError, match="NOT production-selectable"):
        build_screen(synthetic_run(lane="production", stage1_selectable=False))


def test_research_requires_the_verified_measurement_bundle(synthetic_run):
    args = synthetic_run(lane="research_only")
    args.stage1_release = None
    with pytest.raises(SelectionError, match="requires --stage1-release"):
        build_screen(args)


def test_research_demands_complete_measured_evidence(synthetic_run, tmp_path):
    """Only the production GATE is relaxed. Every measurement binding stays."""
    args = synthetic_run(lane="research_only")
    with open(args.stage1_release) as fh:
        bundle = json.load(fh)
    bundle["artifacts"].pop("scores")
    with open(args.stage1_release, "w") as fh:
        json.dump(bundle, fh)
    with pytest.raises(TrustError, match="required bindings omitted"):
        build_screen(args)


def test_research_requires_primary_base_portable_axes(synthetic_run):
    args = synthetic_run(lane="research_only",
                         registry_extra={"base_portable": False})
    with pytest.raises(SelectionError, match="base-portable"):
        build_screen(args)

    args = synthetic_run(lane="research_only", registry_extra={"primary": False})
    with pytest.raises(SelectionError, match="primary axis"):
        build_screen(args)


def test_the_research_bridge_must_self_declare_its_namespace(synthetic_run):
    args = synthetic_run(lane="research_only")
    with open(args.selection) as fh:
        doc = json.load(fh)
    doc["bridge"]["production_gate_passed"] = True       # a lie
    with open(args.selection, "w") as fh:
        json.dump(doc, fh)
    with pytest.raises(SelectionError, match="production_gate_passed"):
        build_screen(args)


def test_the_research_bridge_must_use_the_bridge_schema(synthetic_run):
    args = synthetic_run(lane="research_only")
    with open(args.selection) as fh:
        doc = json.load(fh)
    doc["bridge"]["source"] = "somewhere_else"
    with open(args.selection, "w") as fh:
        json.dump(doc, fh)
    with pytest.raises(SelectionError, match="source"):
        build_screen(args)


def test_the_synthetic_lane_can_never_stand_in_for_research(synthetic_run):
    """A fixture is a fixture. It cannot be relabelled research."""
    args = synthetic_run(lane="synthetic")
    args.lane = config.LANE_RESEARCH
    with pytest.raises(SelectionError):
        build_screen(args)

    args = synthetic_run(lane="research_only")
    args.lane = config.LANE_SYNTHETIC
    with pytest.raises(SelectionError):
        build_screen(args)


def test_a_research_run_passes_standalone_verification(synthetic_run):
    args = synthetic_run(lane="research_only", stage1_selectable=False)
    result = build_screen(args)
    with contextlib.redirect_stdout(io.StringIO()):
        rc = verify_main(["--run-dir", result["out_dir"],
                          "--inputs-root", os.path.dirname(args.selection)])
    assert rc == 0


def test_research_uses_the_same_two_arm_computation(synthetic_run):
    """Same projection, masking and disposition as production — no shortcuts."""
    result = build_screen(synthetic_run(lane="research_only"))
    screen = pd.read_parquet(os.path.join(result["out_dir"], "screen.parquet"))
    for arm in config.ARMS:
        assert config.ARM_RANK_COLUMN[arm] in screen.columns
        assert str(screen[config.ARM_RANK_COLUMN[arm]].dtype) == "Int64"
    assert "combination" not in screen.columns
    assert "rank" not in screen.columns
    assert result["verification"]["ranking"]["arms_rank_independently"] is True
