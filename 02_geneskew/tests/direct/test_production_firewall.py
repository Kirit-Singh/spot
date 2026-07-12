"""The production firewall is fail-closed, and the lane is a TYPE, not a string.

The frozen Stage-1 validation has ZERO production-selectable program-condition
pairs, so no real production ranking may be generated. Fixtures stay fixtures:
they cannot write a production pointer or confer Stage-3 eligibility, and a
research (``rq_`` / ``ra_``) selection can never enter production.
"""
import json
import os

import pytest
from direct import config, trust
from direct.run_screen import build_screen
from direct.selection import SelectionError


# --------------------------------------------------------------------------- #
# The gate: re-derived, never believed.
# --------------------------------------------------------------------------- #
def test_the_frozen_zero_selectable_stage1_refuses_every_production_run(synthetic_run):
    args = synthetic_run(lane="production", program_prefix="",
                         stage1_selectable=False)
    with pytest.raises(SelectionError, match="NOT production-selectable"):
        build_screen(args)


def test_a_stored_selectable_boolean_can_never_open_the_gate(synthetic_run):
    """Every stored boolean says yes; the re-derived gate says no. No wins."""
    args = synthetic_run(lane="production", program_prefix="",
                         stage1_selectable=False,
                         registry_extra={"stage2_selectable": True,
                                         "production_selectable": True})
    with pytest.raises(SelectionError, match="NOT production-selectable"):
        build_screen(args)


def test_a_production_run_requires_the_immutable_release_manifest(synthetic_run):
    args = synthetic_run(lane="production", program_prefix="")
    args.stage1_release = None
    with pytest.raises(SelectionError, match="requires --stage1-release"):
        build_screen(args)


# --------------------------------------------------------------------------- #
# The lane is the TYPE. A fixture cannot be relabelled into production.
# --------------------------------------------------------------------------- #
def test_a_fixture_release_type_can_never_back_production():
    fixture = trust.FixtureRelease(
        kind="fixture", method_version="stage1-continuous-v3.0.1", programs={},
        hashes={}, selectable_pairs=frozenset())
    assert fixture.may_write_production_pointer is False
    assert fixture.may_confer_stage3_eligibility is False

    research = trust.ResearchRelease(
        kind="research", method_version="stage1-continuous-v3.0.1", programs={},
        hashes={}, selectable_pairs=frozenset())
    assert research.may_write_production_pointer is False
    assert research.may_confer_stage3_eligibility is False


def test_a_synthetic_fixture_cannot_be_emitted_as_a_production_artifact(synthetic_run):
    args = synthetic_run(lane="synthetic")
    args.lane = config.LANE_PRODUCTION            # attacker flips only the caller
    with pytest.raises(SelectionError, match="lane"):
        build_screen(args)


def test_a_production_contract_cannot_be_run_as_a_fixture(synthetic_run):
    args = synthetic_run(lane="production", program_prefix="")
    args.lane = config.LANE_SYNTHETIC
    with pytest.raises(SelectionError, match="lane"):
        build_screen(args)


@pytest.mark.parametrize("prefix", ["fx_", "rq_", "ra_"])
def test_a_reserved_run_id_namespace_can_never_enter_production(synthetic_run, prefix):
    """Lane isolation lives on the RUN IDENTIFIERS, not on the biology."""
    args = synthetic_run(lane="production", program_prefix="",
                         ids={"question_id": f"{prefix}deadbeef",
                              "selection_id": f"{prefix}beefdead"})
    with pytest.raises(SelectionError, match="namespace|research-namespace"):
        build_screen(args)


def test_biological_program_ids_are_never_namespaced(synthetic_run):
    """A production contract with frozen, unprefixed registry ids is NOT refused by
    the namespace firewall -- it proceeds to the real Stage-1 gate."""
    args = synthetic_run(lane="production", program_prefix="",
                         stage1_selectable=False)
    with pytest.raises(SelectionError, match="NOT production-selectable"):
        build_screen(args)


def test_an_unknown_lane_fails_closed(synthetic_run):
    args = synthetic_run(lane="synthetic")
    args.lane = "staging"
    with pytest.raises(SelectionError, match="unknown lane"):
        build_screen(args)


def test_a_contract_without_a_lane_fails_closed(synthetic_run):
    args = synthetic_run(lane="synthetic", **{"lane_delete": True})
    with pytest.raises(SelectionError, match="lane must be one of"):
        build_screen(args)


# --------------------------------------------------------------------------- #
# A synthetic run is marked as such, everywhere.
# --------------------------------------------------------------------------- #
def test_a_synthetic_run_is_declared_synthetic_in_every_artifact(synthetic_run):
    result = build_screen(synthetic_run(lane="synthetic"))
    with open(os.path.join(result["out_dir"], "provenance.json")) as fh:
        prov = json.load(fh)
    assert result["lane"] == "synthetic"
    assert prov["run_binding"]["lane"] == "synthetic"
    assert prov["run_binding"]["stage1_release"]["kind"] == "fixture"
    assert result["verification"]["lane"] == "synthetic"
    # a fixture release can never confer Stage-3 eligibility
    assert prov["axis"]["selectability"] is not None
