"""The Stage-2 aggregate: 15 bundles, 300 reusable arm slots, and the fixture firewall.

Admission-chain refusals (identity, report binding, path, inventory, bytes) live in
``test_stage2_admission.py``. Sealed non-production releases: ``stage2_release_fixture.py``.
"""
from __future__ import annotations

import dataclasses
import pytest

from druglink import stage2_aggregate as sa

from stage2_release_fixture import (
    TARGETS,
    INDEPENDENT,
    PROGRAMS,
    _gate,
    build_release,
)

# --------------------------------------------------------------------------- #
# The honest release. NON-VACUOUS: nothing here passes on an empty collection.
# --------------------------------------------------------------------------- #
def test_the_topology_is_exactly_15_bundles_and_300_arm_slots(admitted):
    assert len(admitted.bundles) == 15
    assert len(admitted.arms) == 300
    assert admitted.counts["bundles_per_lane"] == {"direct": 3, "temporal": 6,
                                                   "pathway": 6}
    assert admitted.counts["arms_per_lane"] == {"direct": 60, "temporal": 120,
                                                "pathway": 120}
    assert len({b.bundle_key for b in admitted.bundles}) == 15
    assert len({a.arm_key for a in admitted.arms}) == 300
    assert admitted.program_ids == tuple(sorted(PROGRAMS))


def test_the_counts_are_derived_from_the_conditions_not_copied(admitted):
    assert sa.N_BUNDLES == 3 + 6 + 6
    assert sa.N_ARM_SLOTS == 300
    assert len(sa.ordered_condition_pairs()) == 6
    assert ("Rest", "Stim48hr") in sa.ordered_condition_pairs()
    assert ("Stim48hr", "Rest") in sa.ordered_condition_pairs()   # a DISTINCT bundle
    assert admitted.counts["topology_is_derived_not_declared"] is True


def test_every_arm_retains_its_reusable_identity_and_context(admitted):
    assert admitted.arms, "non-vacuous guard: there must be arms to check"
    for arm in admitted.arms:
        assert arm.arm_key and arm.program_id in PROGRAMS
        assert arm.desired_change in sa.DESIRED_CHANGES
        assert arm.lane in sa.LANES
        ctx = arm.bundle                     # the arm's context, typed, not copied out
        if arm.lane == sa.LANE_TEMPORAL:
            assert ctx.from_condition and ctx.to_condition
            assert ctx.from_condition != ctx.to_condition
        elif arm.lane == sa.LANE_PATHWAY:
            assert ctx.condition and ctx.pathway_source in sa.PATHWAY_SOURCES
        else:
            assert ctx.condition in sa.CONDITIONS
        assert arm.ranking["raw_sha256"] and arm.ranking["canonical_sha256"]
        assert arm.provenance["manifest_self_hash"] == admitted.manifest_self_hash
        assert arm.provenance["independent_verifier_id"] == INDEPENDENT
        assert arm.provenance["bundle_raw_sha256"]
        assert arm.records, "an arm with no records retains no target identity"


def test_measured_records_carry_exact_identity_and_a_released_estimate(admitted):
    measured = [a for a in admitted.arms if a.lane in sa.MEASURED_LANES]
    assert len(measured) == 180
    for arm in measured:
        for rec in arm.records:
            assert rec["target_id"] in TARGETS
            assert rec["target_id_namespace"] == "fixture"
            assert rec["released_estimate_id"]
            if arm.lane == sa.LANE_TEMPORAL:
                # a DiD stands on BOTH endpoints; reporting one misattributes the change
                assert set(rec["released_estimate_id"]) == {"from", "to"}


def test_an_unranked_target_arrives_as_NULL_never_zero_and_never_last(admitted):
    unranked = [r for a in admitted.arms for r in a.records if r["rank"] is None]
    assert unranked, "non-vacuous guard: the fixture must contain unranked targets"
    for rec in unranked:
        assert rec["rank"] is None
        assert rec["rank"] != 0
    ranked = [r for a in admitted.arms for r in a.records if r["rank"] is not None]
    assert ranked and all(r["rank"] >= 1 for r in ranked)


def test_an_arm_carries_no_pair_role_no_pole_and_no_combined_score(admitted):
    names = {f.name for f in dataclasses.fields(sa.LoadedArm)}
    record_keys = set(admitted.arms[0].records[0])
    for banned in ("away_from_A", "toward_B", "role", "pole", "desired_arm",
                   "score", "combined_score", "total"):
        assert banned not in names and banned not in record_keys
    assert admitted.counts["pair_roles_assigned"] is False
    assert admitted.counts["combined_objective_permitted"] is False


# --------------------------------------------------------------------------- #
# The fixture firewall. These sealed releases can never become an analysis.
# --------------------------------------------------------------------------- #
def test_a_fixture_aggregate_is_refused_by_the_analysis_path(admitted):
    assert admitted.artifact_class == "fixture"
    with pytest.raises(sa.AggregateAdmissionRefused) as exc:
        sa.require_analysis(admitted)
    assert sa.GATE_FIXTURE_FIREWALL in _gate(exc)


def test_an_unknown_artifact_class_is_refused(tmp_path):
    from druglink import artifact_class as ac
    paths = build_release(tmp_path, artifact_class="production")
    with pytest.raises(ac.ArtifactClassError):
        sa.admit_aggregate(**paths)
