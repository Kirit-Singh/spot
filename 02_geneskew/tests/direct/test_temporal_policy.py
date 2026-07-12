"""The LOCKED batch-confound policy, and the rule that derives it.

The policy is not a list of blessed condition names. It is a measured composition table
— which donor sat in which replicate at each condition — and the confound flag is
DERIVED from it: a pair is confounded exactly when some donor changes replicate between
the two endpoints. That derivation reproduces the locked verdict (Rest<->Stim8hr clean,
every Stim48hr pair confounded) without the code ever naming a condition, so a release
with a different design gets the right answer instead of a stale one.
"""
from __future__ import annotations

import pytest
from direct.temporal import policy as P

REST, S8, S48 = "Rest", "Stim8hr", "Stim48hr"


@pytest.fixture(scope="module")
def pol():
    return P.load()


class TestTheFrozenDiagnosticIsPinned:
    def test_the_policy_names_the_diagnostic_it_was_locked_from(self, pol):
        prov = pol.provenance
        assert prov["diagnostic_run_id"]
        assert len(prov["report_sha256"]) == 64
        assert len(prov["results_sha256"]) == 64

    def test_the_verdict_it_encodes_is_the_one_the_diagnostic_reached(self, pol):
        assert pol.verdict == "MODERATE"

    def test_the_additive_batch_effect_is_recorded_as_negligible_and_cancelling(
            self, pol):
        # <0.5% of variance, and it cancels in a difference-of-differences either way,
        # which is why no correction is applied anywhere in this estimator.
        assert pol.additive_batch["correction_applied"] is False
        assert pol.additive_batch["max_variance_fraction"] < 0.005


class TestPairClassification:
    def test_a_pair_whose_donors_all_keep_their_replicate_is_clean(self, pol):
        v = pol.classify_pair(REST, S8)
        assert v["batch_partially_confounded"] is False
        assert v["batch_status"] == P.BATCH_CLEAN
        assert v["donors_changing_replicate"] == []

    def test_the_clean_verdict_holds_in_both_directions(self, pol):
        assert pol.classify_pair(S8, REST)["batch_status"] == P.BATCH_CLEAN

    def test_a_pair_where_donors_switch_replicate_is_partially_confounded(self, pol):
        v = pol.classify_pair(REST, S48)
        assert v["batch_partially_confounded"] is True
        assert v["batch_status"] == P.BATCH_PARTIALLY_CONFOUNDED

    def test_it_names_exactly_which_donors_moved_and_which_did_not(self, pol):
        v = pol.classify_pair(REST, S48)
        # D1,D2 flip R1->R2; D3,D4 stay R2. The flag is useless without the names.
        assert v["donors_changing_replicate"] == ["D1", "D2"]
        assert v["donors_keeping_replicate"] == ["D3", "D4"]

    def test_every_stim48_pair_is_confounded_in_both_directions(self, pol):
        for a, b in [(REST, S48), (S48, REST), (S8, S48), (S48, S8)]:
            assert pol.classify_pair(a, b)["batch_partially_confounded"] is True

    def test_no_pair_is_ever_refused_only_flagged(self, pol):
        for a, b in pol.ordered_pairs():
            v = pol.classify_pair(a, b)
            assert v["refused"] is False

    def test_all_six_directed_pairs_over_three_conditions_are_enumerated(self, pol):
        pairs = pol.ordered_pairs()
        assert len(pairs) == 6
        assert (REST, S8) in pairs and (S8, REST) in pairs
        assert (REST, S48) in pairs and (S48, REST) in pairs
        assert (S8, S48) in pairs and (S48, S8) in pairs
        assert all(a != b for a, b in pairs)

    def test_a_condition_the_policy_never_measured_is_typed_unknown_not_clean(
            self, pol):
        v = pol.classify_pair(REST, "Stim96hr_not_in_the_diagnostic")
        assert v["batch_status"] == P.BATCH_COMPOSITION_UNKNOWN
        # UNKNOWN is not CLEAN. An unmeasured composition has not been cleared.
        assert v["batch_partially_confounded"] is None
        assert v["refused"] is False


class TestTheInteractionFloor:
    def test_each_program_carries_the_interaction_std_the_diagnostic_measured(self,
                                                                              pol):
        assert pol.interaction_std("diff_naive") == pytest.approx(0.157, abs=5e-4)
        assert pol.interaction_std("diff_memory") == pytest.approx(0.082, abs=5e-4)
        assert pol.interaction_std("diff_checkpoint") == pytest.approx(0.471, abs=5e-4)
        assert pol.interaction_std("cd4_ctl_like") == pytest.approx(0.756, abs=5e-4)

    def test_an_unmeasured_program_has_no_floor_rather_than_a_convenient_one(self,
                                                                            pol):
        assert pol.interaction_std("fx_program_a") is None

    def test_the_floor_is_the_batch_aligned_split_because_that_is_the_confounded_one(
            self, pol):
        assert pol.interaction_floor_source["split"] == "split1_batchAligned"


class TestSparsePanelCaution:
    def test_the_three_low_reproducibility_programs_carry_extra_caution(self, pol):
        for program in ("th17_like", "th2_like", "tfh_like"):
            assert pol.sparse_panel_caution(program) is True

    def test_a_well_reproduced_program_does_not(self, pol):
        assert pol.sparse_panel_caution("treg_like") is False

    def test_the_non_selectable_program_is_still_listed_so_nothing_can_slip_back_in(
            self, pol):
        assert "th9_like" in pol.sparse_panel_caution_programs


class TestWhatCouldNotBeEstimated:
    def test_the_pure_batch_effect_is_declared_not_identifiable(self, pol):
        note = pol.not_identifiable
        assert note["quantity"] == "pure_batch_effect"
        assert note["identifiable"] is False
        assert "aliased" in note["reason"].lower()

    def test_the_reason_is_the_aliasing_with_donor_not_a_shortage_of_data(self, pol):
        # More cells would not fix this: batch IS donor-half in every condition.
        assert "donor" in pol.not_identifiable["reason"].lower()
