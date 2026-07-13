"""The verifier's SCHEMA: exact key allowlists and four recursive firewalls.

An unknown key is a REJECT, never a warning: a generator that grows a field has to come
here and authorise it. And the firewalls run over the WHOLE artifact, at any depth, on
keys AND on values — a banned field buried three levels down inside a method block is
still a banned field.
"""
from __future__ import annotations

import os
import sys

import pytest

_ANALYSIS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
                                         "analysis"))
if _ANALYSIS not in sys.path:
    sys.path.insert(0, _ANALYSIS)

from verify_temporal_arms import schema  # noqa: E402


class TestTheInferenceFirewall:
    """This estimator has no calibrated null, so a number that LOOKS like significance
    would be READ as significance."""

    @pytest.mark.parametrize("key", [
        "p_value", "pval", "q_value", "qval", "padj", "fdr", "significance",
        "adj_p_value", "nominal_p", "emp_q", "p", "q", "p_bh",
    ])
    def test_a_p_q_or_fdr_field_is_refused_at_any_depth(self, key):
        doc = {"arms": [{"records": [{key: 0.01}]}]}
        assert schema.banned_keys(doc)

    def test_a_clean_document_trips_nothing(self):
        assert schema.banned_keys({"arms": [{"records": [{"arm_value": 1.0}]}]}) == []

    def test_the_letter_p_inside_a_word_is_not_a_p_value(self):
        """A firewall that refused every key containing 'p' is one somebody turns off."""
        assert schema.banned_keys({"panel_mean": 1.0, "n_panel_surviving": 3,
                                   "program_id": "x", "temporal_status": "estimated"}) == []


class TestTheObjectiveFirewall:
    @pytest.mark.parametrize("key", ["combined_score", "balanced_skew", "weighted_score",
                                     "objective_value", "composite_score"])
    def test_a_combined_balanced_or_weighted_objective_is_refused(self, key):
        assert schema.banned_keys({"method": {key: 1.0}})


class TestTheJoinTimeFirewall:
    """A reusable arm may not carry a JOIN-TIME or COMPARISON-SCOPED property."""

    @pytest.mark.parametrize("key", [
        "pair_id", "pair_key", "pareto_tier", "concordance_class", "joint_rank",
        "selection_id", "question_id",
    ])
    def test_a_pair_pareto_concordance_or_joint_field_is_refused(self, key):
        assert schema.banned_keys({"arms": [{key: "x"}]})

    @pytest.mark.parametrize("key", ["role", "pole", "roles", "poles", "arm_role",
                                     "program_pole"])
    def test_a_role_or_pole_field_is_refused(self, key):
        assert schema.banned_keys({key: "high"})

    @pytest.mark.parametrize("key", ["batch_status", "batch_partially_confounded",
                                     "donors_changing_replicate_batch"])
    def test_a_batch_field_is_refused_from_the_reusable_chain(self, key):
        assert schema.banned_keys({"method": {key: True}})

    def test_the_artifact_may_still_write_down_its_own_prohibition(self):
        assert schema.banned_keys({"bundle_carries_role_or_pole": False}) == []

    def test_but_it_may_not_keep_the_exemption_after_flipping_it_on(self):
        assert schema.banned_keys({"bundle_carries_role_or_pole": True})

    def test_a_truthy_impostor_cannot_pose_as_the_prohibition(self):
        assert schema.banned_keys({"bundle_carries_role_or_pole": 0})
        assert schema.banned_keys({"bundle_carries_role_or_pole": "false"})


class TestTheMachinePathAndHostFirewall:
    """No absolute path, no hostname, no private address — at any depth, key OR value."""

    @pytest.mark.parametrize("key", ["path_abs", "verification_path_abs",
                                     "raw_sha256_on_disk", "out_dir", "abs_path"])
    def test_a_machine_path_field_is_refused_by_name(self, key):
        assert schema.machine_path_hits({"bundles": [{key: "x"}]})

    @pytest.mark.parametrize("value", [
        "/Fixture/Machine/spot/outputs/temporal_arm_bundle.json",
        "/fixture-home/analyst/worktrees/out",
        "C:\\Fixture\\Machine\\spot",
        "file:///fixture-home/analyst/out.json",
    ])
    def test_an_absolute_path_VALUE_is_refused_wherever_it_hides(self, value):
        assert schema.machine_path_hits({"method": {"note": value}})

    @pytest.mark.parametrize("value", ["fixturehost.local", "localhost",
                                       "ssh://fixture-node/out",
                                       "analyst@fixture-node:/out"])
    def test_a_host_reference_is_refused_by_SHAPE_not_by_a_named_denylist(self, value):
        assert schema.machine_path_hits({"a": {"b": value}})

    def test_a_deployment_may_still_deny_its_own_hosts_BY_NAME(self):
        doc = {"a": "produced on fixture-compute-01"}
        assert schema.machine_path_hits(doc) == []
        assert schema.machine_path_hits(doc, host_denylist=["fixture-compute-01"])

    def test_this_module_names_no_real_machine(self):
        """A verifier that had to list the lab's hosts in order to reject them would be
        publishing the very thing it exists to keep out of an artifact."""
        src = open(os.path.join(os.path.dirname(schema.__file__), "schema.py")).read()
        assert "DENYLIST" not in src.upper() or "host_denylist" in src
        assert "/Users/" not in src and "/home/" not in src

    @pytest.mark.parametrize("value", ["192.168.1.7", "10.0.0.4", "172.16.5.2",
                                       "127.0.0.1"])
    def test_a_private_address_is_refused(self, value):
        assert schema.machine_path_hits({"a": value})

    def test_the_relative_artifact_path_a_bundle_legitimately_carries_is_allowed(self):
        assert schema.machine_path_hits({"path": "temporal_arm_bundle.json"}) == []
        assert schema.machine_path_hits(
            {"path": "Rest__to__Stim48hr/temporal_arm_bundle.json"}) == []

    def test_a_content_hash_is_not_a_path(self):
        assert schema.machine_path_hits({"raw_sha256": "a" * 64,
                                         "canonical_sha256": "b" * 64}) == []

    def test_a_relative_path_that_escapes_upward_is_refused(self):
        assert schema.machine_path_hits({"path": "../../etc/passwd"})


class TestTheExactKeyAllowlists:
    def test_an_unknown_top_level_bundle_key_is_rejected(self):
        assert schema.unknown_keys({"schema_version": "x", "surprise": 1},
                                   schema.BUNDLE_KEYS) == ["surprise"]

    def test_a_missing_required_bundle_key_is_rejected(self):
        assert "arms" in schema.missing_keys({"schema_version": "x"}, schema.BUNDLE_KEYS)

    def test_the_allowlists_carry_no_pole_role_pair_or_batch_key(self):
        every = (schema.BUNDLE_KEYS | schema.ARM_KEYS | schema.ARM_RECORD_KEYS
                 | schema.BASE_RECORD_KEYS | schema.VERIFICATION_KEYS
                 | schema.INVENTORY_KEYS)
        for key in every:
            assert not schema.banned_keys({key: "sentinel_value_never_matched"}) or \
                key in schema.NEGATIVE_DECLARATIONS, f"{key} is allowlisted AND banned"

    def test_the_allowlists_carry_no_machine_path_key(self):
        every = (schema.BUNDLE_KEYS | schema.ARM_KEYS | schema.ARM_RECORD_KEYS
                 | schema.BASE_RECORD_KEYS | schema.VERIFICATION_KEYS
                 | schema.INVENTORY_KEYS)
        assert not (every & {"path_abs", "verification_path_abs", "raw_sha256_on_disk"})
