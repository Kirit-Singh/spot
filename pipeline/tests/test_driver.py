"""Tests for the pipeline gate driver (deterministic -> must test)."""

from pathlib import Path

import pytest
from pydantic import ValidationError
from spot_pipeline import load_manifest, plan_run

FIX = Path(__file__).parent / "fixtures"


def test_valid_manifest_plans_two_branches() -> None:
    plan = plan_run(load_manifest(FIX / "valid.yaml"))
    assert plan.dataset_id == "fixture_ds"
    assert plan.gex_runs == ["SRR000001"]
    assert plan.guide_runs == ["SRR000002"]
    assert plan.stages[0] == "fetch"
    assert "de" in plan.stages


def test_floating_image_tag_rejected() -> None:
    with pytest.raises(ValidationError):
        load_manifest(FIX / "invalid_floating_tag.yaml")


def test_missing_ntc_rejected() -> None:
    with pytest.raises(ValidationError):
        load_manifest(FIX / "invalid_no_ntc.yaml")
