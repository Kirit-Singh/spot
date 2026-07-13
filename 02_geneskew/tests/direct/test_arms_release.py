"""A complete Direct release is THREE physical bundles — and nothing else says so.

BLOCKER 6. `run_arms` emits one condition per invocation and had no aggregate producer, no
manifest and no rule that the Direct contribution is Rest + Stim8hr + Stim48hr, once each. A
one-bundle run was therefore indistinguishable from a complete Direct release.

WHERE THE CONDITIONS COME FROM
------------------------------
`release.selector.conditions`. Not a batch policy, not a runbook's argv, not a constant in
this repo. The set of physical bundles a complete Direct release consists of is a property of
the STAGE-1 RELEASE the arms are bound to — so a release that shipped a fourth condition would
demand a fourth bundle, automatically, and a producer that hard-coded three would quietly ship
an incomplete release under a complete-looking name.

Missing, duplicated and unknown conditions each refuse at a named gate.
"""
from __future__ import annotations

import json
import os

import fixtures_v3_release as V3
import pytest
from direct import arm_release, run_arms
from fixtures_direct import _PINNED_LOCK

CONDITIONS = ("Rest", "Stim8hr", "Stim48hr")


@pytest.fixture
def three_condition_run(synthetic_run, tmp_path):
    """A fixture release that ships all three Direct conditions, and DE data for each."""
    args = synthetic_run(conditions=CONDITIONS)
    root = str(tmp_path / "root")
    release_path = V3.stage_release(root, conditions=CONDITIONS)
    args.stage1_release = release_path
    args.stage1_release_root = root
    args.out_root = str(tmp_path / "out")
    return args


class TestTheExpectedConditionsAreDerivedFromTheBoundRelease:
    def test_the_conditions_come_from_the_release_SELECTOR(self, tmp_path):
        from direct import stage1_release_v3 as rel
        root = str(tmp_path / "root")
        path = V3.stage_release(root, conditions=CONDITIONS)
        release = rel.load(path, root=root, lane="production")
        assert arm_release.expected_conditions(release) == list(CONDITIONS)

    def test_a_release_that_ships_a_FOURTH_condition_demands_a_fourth_bundle(self,
                                                                            tmp_path):
        from direct import stage1_release_v3 as rel
        root = str(tmp_path / "root")
        path = V3.stage_release(root, conditions=CONDITIONS + ("Stim96hr",))
        release = rel.load(path, root=root, lane="production")
        # nothing hard-codes three: the expectation is a FUNCTION of the bound release
        assert arm_release.expected_conditions(release) == list(CONDITIONS) + ["Stim96hr"]

    def test_a_release_with_NO_conditions_is_REFUSED(self):
        class R:
            conditions = ()
        with pytest.raises(arm_release.DirectReleaseError) as exc:
            arm_release.expected_conditions(R())
        assert exc.value.reason == arm_release.REFUSE_NO_CONDITIONS


class TestTheInventoryRefusesAnIncompleteRelease:
    def _produced(self, conditions):
        return [{"condition": c, "arm_bundle_run_id": f"id_{c}",
                 "arm_bundle_run_sha256": "0" * 64, "n_arm_slots": 4,
                 "n_expected_arm_slots": 4, "arm_rows_sha256": "a" * 64,
                 "out_dir": f"/x/id_{c}"} for c in conditions]

    def test_a_COMPLETE_inventory_passes(self):
        arm_release.assert_inventory(list(CONDITIONS), self._produced(CONDITIONS))

    def test_a_MISSING_condition_is_REFUSED(self):
        with pytest.raises(arm_release.DirectReleaseError) as exc:
            arm_release.assert_inventory(list(CONDITIONS),
                                         self._produced(("Rest", "Stim8hr")))
        assert exc.value.reason == arm_release.REFUSE_MISSING_CONDITION
        assert "Stim48hr" in str(exc.value)

    def test_a_DUPLICATE_condition_is_REFUSED(self):
        with pytest.raises(arm_release.DirectReleaseError) as exc:
            arm_release.assert_inventory(
                list(CONDITIONS), self._produced(CONDITIONS + ("Rest",)))
        assert exc.value.reason == arm_release.REFUSE_DUPLICATE_CONDITION

    def test_an_UNKNOWN_condition_the_release_never_shipped_is_REFUSED(self):
        with pytest.raises(arm_release.DirectReleaseError) as exc:
            arm_release.assert_inventory(
                list(CONDITIONS), self._produced(CONDITIONS + ("StimMystery",)))
        assert exc.value.reason == arm_release.REFUSE_UNKNOWN_CONDITION

    def test_a_ONE_BUNDLE_run_cannot_pass_as_a_complete_release(self):
        # the exact defect: one bundle was indistinguishable from a finished Direct release
        with pytest.raises(arm_release.DirectReleaseError):
            arm_release.assert_inventory(list(CONDITIONS), self._produced(("Rest",)))


class TestTheAggregateReleaseIsProducedEndToEnd:
    def test_three_bundles_are_built_and_BOUND_into_one_release(self, three_condition_run):
        result = arm_release.build_release(three_condition_run)

        assert [b["condition"] for b in result["bundles"]] == list(CONDITIONS)
        assert result["n_physical_bundles"] == 3
        # every bundle is a DISTINCT physical measurement
        ids = {b["arm_bundle_run_id"] for b in result["bundles"]}
        assert len(ids) == 3

        doc = json.load(open(os.path.join(result["out_dir"],
                                          arm_release.RELEASE_FILE)))
        assert doc["expected_conditions"] == list(CONDITIONS)
        assert {b["arm_bundle_run_id"] for b in doc["bundles"]} == ids

    def test_the_logical_arm_count_is_DERIVED_from_conditions_times_slots(
            self, three_condition_run):
        result = arm_release.build_release(three_condition_run)
        per_bundle = result["bundles"][0]["n_expected_arm_slots"]
        assert result["n_logical_arms"] == 3 * per_bundle

    def test_the_release_binds_the_STAGE1_release_it_stands_on(self, three_condition_run):
        result = arm_release.build_release(three_condition_run)
        doc = json.load(open(os.path.join(result["out_dir"], arm_release.RELEASE_FILE)))
        assert doc["stage1_release"]["release_self_sha256"]
        assert doc["stage1_release"]["registry_scorer_view_canonical_sha256"]

    def test_the_aggregate_release_does_NOT_admit_itself(self, three_condition_run):
        result = arm_release.build_release(three_condition_run)
        doc = json.load(open(os.path.join(result["out_dir"], arm_release.RELEASE_FILE)))
        assert doc["admitted"] is False
        assert doc["verdict"] == run_arms.VERDICT_PENDING

    def test_the_release_manifest_cites_bundles_by_RELATIVE_path(self, three_condition_run):
        result = arm_release.build_release(three_condition_run)
        doc = json.load(open(os.path.join(result["out_dir"], arm_release.RELEASE_FILE)))
        for b in doc["bundles"]:
            assert not os.path.isabs(b["path"])
        assert "/tmp/" not in json.dumps(doc)


class TestTheShippedCLIBuildsTheWholeRelease:
    def test_all_conditions_runs_end_to_end_from_the_COMMAND(self, three_condition_run,
                                                             tmp_path):
        args = three_condition_run
        result = run_arms.main([
            "--env-lock", _PINNED_LOCK,
            "--all-conditions", "--out-root", str(tmp_path / "cli"),
            "--de-main", args.de_main, "--by-guide", args.by_guide,
            "--by-donors", args.by_donors, "--sgrna", args.sgrna,
            "--guide-manifest", args.guide_manifest,
            "--source-registry", args.source_registry,
            "--pseudobulk", args.pseudobulk,
            "--lane", "synthetic", "--allow-dirty-tree",
            # THE PINNED SOLVER LOCK. Every invocation binds it and a run without it REFUSES,
            # so a test that omitted it would be exercising a path production cannot take.
            "--env-lock", args.env_lock,
            "--stage1-release", args.stage1_release,
            "--stage1-release-root", args.stage1_release_root])
        assert result["n_physical_bundles"] == 3
        assert result["expected_conditions"] == list(CONDITIONS)

    def test_NEITHER_condition_NOR_all_conditions_is_an_ERROR_not_a_default(self):
        with pytest.raises(SystemExit):
            run_arms.main(["--de-main", "x", "--out-root", "y"])
