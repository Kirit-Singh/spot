"""v2 arm → drug query, driven by W5's REAL transcribed bytes (cc82599).

Selection-independent by construction: these tests never mention `away_from_A` or
`toward_B`, because an arm does not know its role. If any of them needed one, the contract
would be wrong.

The bundle is PROVISIONAL (W11 admission pending), so every path here goes through an
explicit ExternalAdmission — which is exactly the thing under test.
"""
from __future__ import annotations

import json
import os

import pytest

from druglink import arm_query as aq
from druglink import join_semantics as js

HERE = os.path.dirname(os.path.abspath(__file__))
BUNDLE_PATH = os.path.join(HERE, "fixtures_w5_temporal",
                           "FixRest__to__FixStim48", "arm_bundle.json")


@pytest.fixture(scope="module")
def bundle():
    with open(BUNDLE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def admission():
    """A PROVISIONAL admission standing in for W11's. Replaced by the real one on landing."""
    return aq.ExternalAdmission(
        verifier_id="spot.stage02.temporal.arm.independent_verifier.v1",
        producer_commit="cc82599",
        bundle_sha256="d2d7aaaf68cdbf9143b453e568b157a2ccc80ea1d5804876f75cf9383d351ed2",
        verdict="admit")


@pytest.fixture(scope="module")
def rows(bundle, admission):
    out = []
    for arm in bundle["arms"]:
        out += aq.normalize_arm(arm, bundle=bundle, admission=admission)
    return out


# --------------------------------------------------------------------------- #
# The admission gate. No default, no fallback, no fourth self-verifier.
# --------------------------------------------------------------------------- #
def test_a_provisional_bundle_cannot_be_used_without_an_external_admission(bundle):
    with pytest.raises(aq.ExternalAdmissionRequired, match="PROVISIONAL"):
        aq.require_external_admission(bundle, None)


def test_a_self_verified_admission_is_refused():
    with pytest.raises(aq.ExternalAdmissionRequired, match="INDEPENDENT"):
        aq.ExternalAdmission(verifier_id="spot.stage02.temporal_arm.verifier.v1",
                             producer_commit="cc82599", bundle_sha256="a" * 64,
                             verdict="admit")


def test_a_non_admit_verdict_is_refused():
    with pytest.raises(aq.ExternalAdmissionRequired, match="did not admit"):
        aq.ExternalAdmission(
            verifier_id="spot.stage02.temporal.arm.independent_verifier.v1",
            producer_commit="cc82599", bundle_sha256="a" * 64, verdict="reject")


def test_an_admission_must_name_the_commit_AND_the_bytes():
    with pytest.raises(aq.ExternalAdmissionRequired, match="producer commit AND the bytes"):
        aq.ExternalAdmission(
            verifier_id="spot.stage02.temporal.arm.independent_verifier.v1",
            producer_commit="", bundle_sha256="", verdict="admit")


def test_the_admission_travels_into_every_emitted_row(rows):
    for r in rows[:5]:
        assert r["external_verifier_id"].endswith("independent_verifier.v1")
        assert r["external_producer_commit"] == "cc82599"
        assert r["external_verdict"] == "admit"


# --------------------------------------------------------------------------- #
# Selection-independence: an arm has no role.
# --------------------------------------------------------------------------- #
def test_an_arm_carries_a_desired_change_and_NO_role_or_pole(rows):
    for r in rows:
        assert r["desired_change"] in aq.DESIRED_CHANGES
        for role_or_pole in ("desired_arm", "role", "pole", "away_from_A", "toward_B"):
            assert role_or_pole not in r, (
                f"a reusable arm must not carry {role_or_pole!r} — a role is assigned by "
                "the SELECTION at join time, and baking one in fuses two questions")


def test_the_same_arm_serves_any_selection(bundle, admission):
    """The query never asks which selection is running. That is the whole contract."""
    arm = bundle["arms"][0]
    a = aq.normalize_arm(arm, bundle=bundle, admission=admission)
    b = aq.normalize_arm(arm, bundle=bundle, admission=admission)
    assert a == b


# --------------------------------------------------------------------------- #
# Cross-time context is typed, and is NOT temporal enrichment.
# --------------------------------------------------------------------------- #
def test_a_temporal_bundle_yields_a_cross_time_context(bundle, rows):
    ctx = aq.arm_context(bundle)
    assert ctx["time_scope"] == aq.CROSS_TIME
    assert ctx["analysis_mode"] == js.TEMPORAL_CROSS_CONDITION
    assert ctx["from_condition"] and ctx["to_condition"]
    for r in rows[:3]:
        assert r["from_condition"] == ctx["from_condition"]
        assert r["to_condition"] == ctx["to_condition"]


def test_a_cross_time_lever_binds_BOTH_endpoint_estimates(rows):
    """A DiD stands on two endpoints. Reporting one would misattribute the difference."""
    r = rows[0]
    assert set(r["released_estimate_id"]) == {"from", "to"}
    assert r["released_estimate_id"]["from"] and r["released_estimate_id"]["to"]


def test_a_bundle_carrying_a_cross_time_pathway_statistic_is_refused(bundle, admission):
    bad = dict(bundle)
    bad["sets"] = [{"temporal_enrichment": 3.3}]
    with pytest.raises(js.JoinSemanticsError, match="ACROSS TIME"):
        aq.require_external_admission(bad, admission)


# --------------------------------------------------------------------------- #
# Exact identity, verified join, no symbol join.
# --------------------------------------------------------------------------- #
def test_every_lever_carries_exact_identity_resolved_through_base_records(rows):
    for r in rows:
        assert r["target_id"]
        assert r["target_id_namespace"]
        assert "target_ensembl" in r and "target_symbol" in r


def test_a_dangling_base_key_is_refused(bundle, admission):
    broken = json.loads(json.dumps(bundle))
    broken["arms"][0]["records"][0]["base_key"] = "NOPE|NOPE"
    with pytest.raises(aq.ArmQueryError, match="resolves to nothing"):
        aq.normalize_arm(broken["arms"][0], bundle=broken, admission=admission)


def test_a_base_key_resolving_to_a_DIFFERENT_target_is_refused(bundle, admission):
    """The join is checked, not trusted — this is the silent mis-attribution it prevents."""
    broken = json.loads(json.dumps(bundle))
    rec = broken["arms"][0]["records"][0]
    other = next(b for b in broken["base_records"]
                 if b["target_id"] != rec["target_id"]
                 and b["program_id"] == broken["arms"][0]["program_id"])
    rec["base_key"] = other["base_key"]                 # key now points at another target
    with pytest.raises(aq.ArmQueryError, match="but the arm record says"):
        aq.normalize_arm(broken["arms"][0], bundle=broken, admission=admission)


# --------------------------------------------------------------------------- #
# Rank-null targets are RETAINED.
# --------------------------------------------------------------------------- #
def test_every_target_is_retained_including_the_unranked(bundle, rows):
    n_records = sum(len(a["records"]) for a in bundle["arms"])
    assert len(rows) == n_records, "no target may be dropped on the way to Stage 3"


def test_an_unranked_lever_keeps_a_NULL_rank_never_a_zero(rows):
    for r in rows:
        assert r["arm_rank"] is None or r["arm_rank"] >= 1, (
            "an unranked target arrives as null, never as 0 and never as last")


# --------------------------------------------------------------------------- #
# Modulation compatibility, and the ordering firewall.
# --------------------------------------------------------------------------- #
def test_only_supports_inhibition_is_inhibitor_compatible(rows):
    for r in rows:
        mod = r["arm_desired_target_modulation"]
        assert r["inhibitor_direction_compatible"] == (mod == aq.SUPPORTS_INHIBITION)


def test_an_opposed_lever_is_retained_but_INERT(rows):
    opposed = [r for r in rows
               if r["arm_desired_target_modulation"] == aq.OPPOSED_NEEDS_ACTIVATION]
    if not opposed:
        pytest.skip("this fixture pair produced no opposed arm value")
    for r in opposed:
        assert r["inhibitor_direction_compatible"] is False
        assert r["may_improve_drug_ordering"] is False, (
            "'opposed' says ACTIVATION would be needed — it is not an activator lead, "
            "and it must never lift a drug up the ordering")
        assert r["pharmacologic_reversibility_assumed"] is False
    assert all(r not in aq.orderable_levers(rows) for r in opposed)


def test_a_not_evaluable_lever_never_improves_ordering(rows):
    for r in rows:
        if r["arm_desired_target_modulation"] == aq.NOT_EVALUABLE:
            assert r["may_improve_drug_ordering"] is False


def test_orderable_levers_are_exactly_the_inhibitor_compatible_ones(rows):
    orderable = aq.orderable_levers(rows)
    assert all(r["arm_desired_target_modulation"] == aq.SUPPORTS_INHIBITION
               for r in orderable)
    assert len(orderable) < len(rows), "not every lever may order drugs"


# --------------------------------------------------------------------------- #
# Measured evidence never merges with pathway hypothesis.
# --------------------------------------------------------------------------- #
def test_every_arm_lever_is_MEASURED_evidence(rows):
    for r in rows:
        assert r["evidence_class"] == aq.MEASURED_PERTURBATION
        assert r["crispri_modality"] == aq.PERTURBATION_MODALITY


def test_a_pathway_hypothesis_carrying_a_measured_rank_is_refused():
    bad = [{"evidence_class": aq.PATHWAY_HYPOTHESIS, "target_id": "X", "arm_rank": 1}]
    with pytest.raises(aq.ArmQueryError, match="no rank to carry"):
        aq.assert_evidence_classes_never_merge(bad)


def test_the_two_evidence_classes_are_disjoint():
    assert aq.MEASURED_PERTURBATION != aq.PATHWAY_HYPOTHESIS
    assert set(aq.EVIDENCE_CLASSES) == {aq.MEASURED_PERTURBATION, aq.PATHWAY_HYPOTHESIS}


# --------------------------------------------------------------------------- #
# The temporal loader stays SHUT until the independent matrix is green.
# --------------------------------------------------------------------------- #
def test_the_temporal_loader_is_still_gated_on_the_detached_clone_matrix():
    """W5/W11/W3 have clean heads. That is not the same as a green report.

    Each lane's own suite passing is precisely the self-consistency the cross-lane matrix
    exists to rule out — the same failure this lane has now met four times (B6, M4b, the
    temporal verification_ref, and the producer's own `pending` release).
    """
    assert aq.DETACHED_CLONE_MATRIX_GREEN is False
    assert aq.TEMPORAL_HEADS == {"W5": "62fbf8b", "W11": "61ee45b", "W3": "71f50f1"}
    assert "still RUNNING" in aq.PROVISIONAL_SOURCES[aq.TEMPORAL_ARM_BUNDLE]
