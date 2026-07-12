"""Base QC once, then two independent arms: gates, support, direction."""

from direct import config, disposition
from direct.config import ARM_A, ARM_B
from direct.projection import INSUFFICIENT_AXIS_COVERAGE, MASK_UNRESOLVED, OK


# --------------------------------------------------------------------------- #
# Base QC is pre-outcome and reads NEITHER arm.
# --------------------------------------------------------------------------- #
def _base(**over):
    kw = dict(row_present=True, mask_resolved=True, n_cells=500.0,
              low_target_gex=False, ontarget_significant=True, n_guides=2.0)
    kw.update(over)
    return disposition.base_qc(**kw)


def test_base_qc_takes_no_arm_value_at_all():
    """If an arm value could reach base QC, one arm could gate the other."""
    import inspect
    params = set(inspect.signature(disposition.base_qc).parameters)
    for banned in ("away_from_A", "toward_B", "arm", "value", "projection_status",
                   "delta"):
        assert banned not in params, banned


def test_base_qc_precedence_and_complete_reasons():
    state, passed, reasons = _base(n_cells=5.0)
    assert (state, passed) == ("underpowered_cells", False)
    assert "qc_pass_two_guide" in reasons          # nothing is hidden

    assert _base()[:2] == ("qc_pass_two_guide", True)
    assert _base(n_guides=1.0)[:2] == ("qc_pass_single_guide", True)
    assert _base(n_guides=3.0)[:2] == ("qc_pass_multi_guide", True)
    assert _base(mask_resolved=False)[:2] == ("mask_unresolved", False)
    assert _base(low_target_gex=True)[:2] == ("low_target_expression", False)
    assert _base(ontarget_significant=False)[:2] == (
        "no_detectable_source_on_target_repression", False)
    assert _base(row_present=False)[:2] == ("unavailable_in_condition", False)
    assert _base(n_guides=None)[:2] == ("mask_unresolved", False)


# --------------------------------------------------------------------------- #
# Arm evaluability is INDEPENDENT per arm.
# --------------------------------------------------------------------------- #
def test_an_arm_is_evaluable_on_base_qc_plus_its_own_projection():
    state, ok, _ = disposition.arm_state(base_state="qc_pass_two_guide",
                                         base_passed=True, projection_status=OK)
    assert (state, ok) == (disposition.ARM_EVALUABLE, True)


def test_one_arm_failing_coverage_does_not_touch_the_other():
    """A's insufficient coverage is A's problem. B is still evaluable."""
    a_state, a_ok, a_reasons = disposition.arm_state(
        base_state="qc_pass_two_guide", base_passed=True,
        projection_status=INSUFFICIENT_AXIS_COVERAGE)
    b_state, b_ok, _ = disposition.arm_state(
        base_state="qc_pass_two_guide", base_passed=True, projection_status=OK)

    assert (a_state, a_ok) == (disposition.ARM_INSUFFICIENT_COVERAGE, False)
    assert "arm_insufficient_axis_coverage" in a_reasons
    assert (b_state, b_ok) == (disposition.ARM_EVALUABLE, True)


def test_failing_base_qc_excludes_both_arms_with_the_base_reason():
    for status in (OK, INSUFFICIENT_AXIS_COVERAGE):
        state, ok, reasons = disposition.arm_state(
            base_state="underpowered_cells", base_passed=False,
            projection_status=status)
        assert (state, ok) == (disposition.ARM_EXCLUDED_BASE_QC, False)
        assert reasons == ["base_qc:underpowered_cells"]


def test_an_unresolved_mask_makes_an_arm_unevaluable():
    state, ok, _ = disposition.arm_state(base_state="qc_pass_two_guide",
                                         base_passed=True,
                                         projection_status=MASK_UNRESOLVED)
    assert (state, ok) == (disposition.ARM_MASK_UNRESOLVED, False)


# --------------------------------------------------------------------------- #
# Direction per arm; conflicts are PRESERVED.
# --------------------------------------------------------------------------- #
def test_modulation_is_derived_only_with_direction_evidence_in_that_arm():
    assert disposition.desired_modulation(0.5, evaluable=True) == \
        disposition.MOD_DECREASE
    assert disposition.desired_modulation(-0.5, evaluable=True) == \
        disposition.MOD_INCREASE
    assert disposition.desired_modulation(0.0, evaluable=True) == \
        disposition.MOD_NO_DIRECTION
    # not evaluable -> no pharmacologic direction at all, whatever the number
    assert disposition.desired_modulation(9.0, evaluable=False) == \
        disposition.MOD_NOT_EVALUATED
    assert disposition.desired_modulation(None, evaluable=True) == \
        disposition.MOD_NOT_EVALUATED


def test_conflicting_arm_directions_stay_a_conflict_and_pick_no_winner():
    out = disposition.modulation_agreement(disposition.MOD_DECREASE,
                                           disposition.MOD_INCREASE)
    assert out == disposition.MOD_CONFLICT
    assert out not in (disposition.MOD_AGREE, "matched", "decrease", "increase")


def test_agreement_and_single_arm_cases():
    assert disposition.modulation_agreement(
        disposition.MOD_DECREASE, disposition.MOD_DECREASE) == disposition.MOD_AGREE
    assert disposition.modulation_agreement(
        disposition.MOD_DECREASE, disposition.MOD_NOT_EVALUATED) == \
        disposition.MOD_ONLY_A
    assert disposition.modulation_agreement(
        disposition.MOD_NOT_EVALUATED, disposition.MOD_INCREASE) == \
        disposition.MOD_ONLY_B
    assert disposition.modulation_agreement(
        disposition.MOD_NO_DIRECTION, disposition.MOD_NOT_EVALUATED) == \
        disposition.MOD_NONE


# --------------------------------------------------------------------------- #
# Guide replication is PER ARM. A's support is never B's support.
# --------------------------------------------------------------------------- #
def _slot(eid, gid, a_val, b_val, reason=None):
    return {"estimate_id": eid, "guide_id": gid,
            "values": {ARM_A: a_val, ARM_B: b_val},
            "unresolved_reason": reason}


def test_guide_replication_is_computed_independently_for_each_arm():
    # both guides agree in A, but disagree in B
    slots = [_slot("guide_1", "g-1", 0.9, 0.9), _slot("guide_2", "g-2", 0.8, -0.8)]
    rep_a = disposition.guide_replication(1.0, slots, ARM_A)
    rep_b = disposition.guide_replication(1.0, slots, ARM_B)

    assert rep_a["guide_replication_state"] == disposition.REPLICATION_CONCORDANT
    assert rep_a["guide_replication_supported"] is True
    # B must NOT inherit A's support
    assert rep_b["guide_replication_state"] == disposition.REPLICATION_DISCORDANT
    assert rep_b["guide_replication_supported"] is False


def test_a_guide_evaluated_in_one_arm_only_counts_only_there():
    slots = [_slot("guide_1", "g-1", 0.9, 0.9), _slot("guide_2", "g-2", 0.8, None)]
    rep_a = disposition.guide_replication(1.0, slots, ARM_A)
    rep_b = disposition.guide_replication(1.0, slots, ARM_B)
    assert rep_a["n_guides_evaluated"] == 2
    assert rep_b["n_guides_evaluated"] == 1
    assert rep_b["guide_replication_state"] == disposition.REPLICATION_SINGLE
    assert f"guide_2:not_evaluated_in_{ARM_B}" in rep_b["guide_missing_reasons"]


def test_one_guide_can_never_become_replicated_support_in_either_arm():
    slots = [_slot("guide_1", "g-1", 0.9, 0.9),
             _slot("guide_2", None, None, None, reason="ambiguous")]
    for arm in config.ARMS:
        rep = disposition.guide_replication(1.0, slots, arm)
        assert rep["guide_replication_state"] == disposition.REPLICATION_SINGLE
        assert rep["guide_replication_supported"] is False
        assert rep["n_guides_mapped"] == 1
        assert "guide_2:ambiguous" in rep["guide_missing_reasons"]


def test_two_slots_naming_the_same_guide_are_not_two_guides():
    slots = [_slot("guide_1", "g-1", 0.9, 0.9), _slot("guide_2", "g-1", 0.8, 0.8)]
    rep = disposition.guide_replication(1.0, slots, ARM_A)
    assert rep["n_guides_mapped"] == 1
    assert rep["guide_replication_state"] == disposition.REPLICATION_SINGLE


def test_a_single_guide_target_is_capped_in_every_arm():
    slots = [_slot("guide_1", "g-1", 0.9, 0.9), _slot("guide_2", "g-2", 0.8, 0.8)]
    for arm in config.ARMS:
        rep = disposition.guide_replication(1.0, slots, arm,
                                            base_state="qc_pass_single_guide")
        assert rep["guide_replication_state"] == disposition.REPLICATION_SINGLE
        assert rep["guide_replication_supported"] is False


# --------------------------------------------------------------------------- #
# Tier / support state, per arm.
# --------------------------------------------------------------------------- #
def test_evidence_tier_reads_only_its_own_arm():
    kw = dict(arm_evaluable=True, guide_replicated=True, donor_split_supported=True)
    assert disposition.evidence_tier(arm_value=1.0, **kw) == \
        "tier1_guide_and_donor_split"
    assert disposition.evidence_tier(
        arm_value=1.0, arm_evaluable=True, guide_replicated=True,
        donor_split_supported=False) == "tier2_guide_replicated"
    assert disposition.evidence_tier(
        arm_value=1.0, arm_evaluable=True, guide_replicated=False,
        donor_split_supported=False) == "tier3_screen_only"
    # a negative value in THIS arm is no signal in THIS arm
    assert disposition.evidence_tier(arm_value=-1.0, **kw) == \
        "evaluable_no_directional_signal"
    assert disposition.evidence_tier(
        arm_value=1.0, arm_evaluable=False, guide_replicated=True,
        donor_split_supported=True) == "not_evaluated"


def test_no_target_can_reach_cell_level_support_in_this_lane():
    state = disposition.support_state(arm_evaluable=True, guide_replicated=True,
                                      donor_split_supported=True)
    assert state == "within_dataset_replicated"
    assert state != "cell_level_supported"
