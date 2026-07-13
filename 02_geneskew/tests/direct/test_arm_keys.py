"""The canonical ARM key: desired_change, never the pole and never the role.

THE DEFECT this exists to prevent (ROUND4_ADDENDUM fd59ecb6, Rule 2): the same pole means
OPPOSITE perturbations depending on the role it is playing.

    away_from_A(high) -> decrease        toward_B(high) -> increase
    away_from_A(low)  -> increase        toward_B(low)  -> decrease

So an arm cached under `high` would fuse two opposite perturbations under one key, and a UI
joining two arms would silently serve one of them as the other. The reusable arm therefore
keys on the DESIRED CHANGE — what the perturbation is trying to do to the program — and the
pole and role stay behind in the selection contract as metadata that may never alter a
cached arm's values.

The two arms of a program in a context are SIGN TRANSFORMS of ONE base effect, not two
experimental estimates: compute the base once, derive `increase` and `decrease` exactly.
"""
from __future__ import annotations

import pytest
from direct import arm_keys as arms


class TestTheFourRolePoleMappings:
    """All four, exhaustively. This table is the correction."""

    def test_away_from_A_high_is_a_DECREASE(self):
        assert arms.desired_change(arms.ROLE_AWAY, "high") == arms.DECREASE

    def test_away_from_A_low_is_an_INCREASE(self):
        assert arms.desired_change(arms.ROLE_AWAY, "low") == arms.INCREASE

    def test_toward_B_high_is_an_INCREASE(self):
        assert arms.desired_change(arms.ROLE_TOWARD, "high") == arms.INCREASE

    def test_toward_B_low_is_a_DECREASE(self):
        assert arms.desired_change(arms.ROLE_TOWARD, "low") == arms.DECREASE

    def test_the_table_is_exactly_these_four(self):
        assert arms.DESIRED_CHANGE_BY_ROLE_AND_POLE == {
            (arms.ROLE_AWAY, "high"): arms.DECREASE,
            (arms.ROLE_AWAY, "low"): arms.INCREASE,
            (arms.ROLE_TOWARD, "high"): arms.INCREASE,
            (arms.ROLE_TOWARD, "low"): arms.DECREASE,
        }

    def test_THE_SAME_POLE_IN_THE_TWO_ROLES_IS_THE_OPPOSITE_PERTURBATION(self):
        # The whole reason the key is not the pole.
        assert arms.desired_change(arms.ROLE_AWAY, "high") != \
            arms.desired_change(arms.ROLE_TOWARD, "high")
        assert arms.desired_change(arms.ROLE_AWAY, "low") != \
            arms.desired_change(arms.ROLE_TOWARD, "low")

    def test_an_unknown_role_or_pole_is_REFUSED_never_guessed(self):
        with pytest.raises(arms.ArmError):
            arms.desired_change("sideways_from_A", "high")
        with pytest.raises(arms.ArmError):
            arms.desired_change(arms.ROLE_AWAY, "up")


class TestTheCanonicalKeys:
    def test_direct(self):
        assert arms.direct_arm_key("treg_like", arms.DECREASE, "Rest") == \
            "direct|treg_like|decrease|Rest"

    def test_pathway_appends_the_source(self):
        assert arms.pathway_arm_key("treg_like", arms.INCREASE, "Rest", "reactome") == \
            "pathway|treg_like|increase|Rest|reactome"

    def test_temporal_is_an_ORDERED_pair(self):
        assert arms.temporal_arm_key("treg_like", arms.INCREASE, "Rest", "Stim48hr") == \
            "temporal|treg_like|increase|Rest|Stim48hr"

    def test_the_temporal_pair_is_DIRECTED_not_a_set(self):
        assert arms.temporal_arm_key("p", arms.INCREASE, "Rest", "Stim48hr") != \
            arms.temporal_arm_key("p", arms.INCREASE, "Stim48hr", "Rest")


class TestAnArmKeyNEVERCarriesAPoleOrARole:
    """The guard. A key with `high` or `away_from_A` in it is the bug, restated."""

    @pytest.mark.parametrize("key", [
        arms.direct_arm_key("p", arms.INCREASE, "Rest"),
        arms.direct_arm_key("p", arms.DECREASE, "Rest"),
        arms.pathway_arm_key("p", arms.INCREASE, "Rest", "go_bp"),
        arms.temporal_arm_key("p", arms.DECREASE, "Rest", "Stim8hr"),
    ])
    def test_no_pole_or_role_token_appears(self, key):
        for forbidden in ("high", "low", arms.ROLE_AWAY, arms.ROLE_TOWARD):
            assert forbidden not in key

    def test_the_key_builders_REFUSE_a_pole_passed_where_a_desired_change_belongs(self):
        # the exact slip this design is guarding: `high` handed to the arm key
        with pytest.raises(arms.ArmError):
            arms.direct_arm_key("p", "high", "Rest")


class TestTheSameProgramAndPoleAcrossTIME:
    """Same program, same pole, same role — different context is a DIFFERENT arm."""

    def test_the_same_program_high_at_two_conditions_is_two_direct_arms(self):
        dc = arms.desired_change(arms.ROLE_AWAY, "high")
        rest = arms.direct_arm_key("treg_like", dc, "Rest")
        stim = arms.direct_arm_key("treg_like", dc, "Stim48hr")
        assert rest != stim

    def test_they_agree_on_everything_EXCEPT_the_condition(self):
        dc = arms.desired_change(arms.ROLE_AWAY, "high")
        rest = arms.direct_arm_key("treg_like", dc, "Rest").rsplit("|", 1)[0]
        stim = arms.direct_arm_key("treg_like", dc, "Stim48hr").rsplit("|", 1)[0]
        assert rest == stim

    def test_the_cross_time_arm_is_a_TEMPORAL_key_not_two_direct_ones(self):
        dc = arms.desired_change(arms.ROLE_AWAY, "high")
        assert arms.temporal_arm_key("treg_like", dc, "Rest", "Stim48hr").startswith(
            "temporal|treg_like|decrease|")

    def test_the_same_program_high_in_the_OTHER_role_is_the_OPPOSITE_arm_at_the_same_time(
            self):
        # away_from_A(high) and toward_B(high) at Rest: same program, same pole, same
        # condition — and they must NOT collide, because they are opposite perturbations.
        away = arms.direct_arm_key(
            "treg_like", arms.desired_change(arms.ROLE_AWAY, "high"), "Rest")
        toward = arms.direct_arm_key(
            "treg_like", arms.desired_change(arms.ROLE_TOWARD, "high"), "Rest")
        assert away != toward
        assert away.endswith("decrease|Rest") and toward.endswith("increase|Rest")


class TestConvergenceIsSHAREDNotCopiedPerArm:
    """Convergence depends on (condition, source) alone — 6 artifacts, not 120."""

    def test_the_key_carries_no_program_and_no_desired_change(self):
        key = arms.convergence_key("Rest", "reactome")
        assert key == "convergence|Rest|reactome"
        for forbidden in ("increase", "decrease", "treg_like"):
            assert forbidden not in key

    def test_every_arm_in_one_bundle_references_the_SAME_convergence_artifact(self):
        # the 20 enrichment arms of one (condition, source) bundle
        keys = {arms.convergence_key("Rest", "reactome")
                for _program in ("p1", "p2", "p3")
                for _change in arms.DESIRED_CHANGES}
        assert len(keys) == 1, "the same claim would have been restated per arm"

    def test_a_different_condition_or_source_is_a_DIFFERENT_convergence_artifact(self):
        assert arms.convergence_key("Rest", "reactome") != \
            arms.convergence_key("Stim48hr", "reactome")
        assert arms.convergence_key("Rest", "reactome") != \
            arms.convergence_key("Rest", "go_bp")


class TestAnEnrichmentArmIsNEVERInferredFromTheOther:
    """A ranking is not antisymmetric. All 120 enrichment arms are COMPUTED."""

    def test_a_sign_transform_of_an_enrichment_arm_is_REFUSED_by_name(self):
        with pytest.raises(arms.EnrichmentAntisymmetryError):
            arms.derive_arm_values([1.0, -2.0], arms.DECREASE,
                                   quantity="pathway_enrichment")

    def test_the_module_declares_enrichment_is_computed(self):
        assert arms.ENRICHMENT_ARMS_ARE_COMPUTED_NOT_DERIVED is True
        assert arms.mapping_block()["enrichment_rank_antisymmetry_assumed"] is False

    def test_the_sign_transform_is_scoped_to_the_SIGNED_base_deltas(self):
        assert set(arms.SIGN_TRANSFORM_APPLIES_TO) == {
            "direct_base_delta", "temporal_base_delta"}


class TestTheTwoArmsAreSignTransformsOfONEBaseEffect:
    """Not two experimental estimates — one estimate, two exact sign transforms."""

    def test_increase_is_plus_one_and_decrease_is_minus_one(self):
        assert arms.SIGN[arms.INCREASE] == 1
        assert arms.SIGN[arms.DECREASE] == -1

    def test_the_derived_values_are_exact_negations(self):
        base = [0.4, -1.25, 0.0]
        up = arms.derive_arm_values(base, arms.INCREASE)
        down = arms.derive_arm_values(base, arms.DECREASE)
        assert up == [0.4, -1.25, 0.0]
        assert down == [-0.4, 1.25, 0.0]

    def test_a_round_trip_returns_the_base_exactly(self):
        base = [0.4, -1.25, 3.5]
        assert arms.derive_arm_values(
            arms.derive_arm_values(base, arms.DECREASE), arms.DECREASE) == base

    def test_zero_has_no_signed_twin_and_stays_zero(self):
        # -0.0 == 0.0 in float, but it must not print as a different number
        assert arms.derive_arm_values([0.0], arms.DECREASE) == [0.0]
