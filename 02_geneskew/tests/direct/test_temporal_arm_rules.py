"""The verifier's SEPARATELY STATED rule implementation, tested on its own.

These rules are re-stated from the frozen contract, NOT imported from the producer. The
first test in this module is the one that keeps that true: if the verifier ever reaches
into ``direct.temporal.arms`` for a sign, a key or a rank, the whole lane collapses back
into a producer checking itself.
"""
from __future__ import annotations

import ast
import os
import sys

import pytest

_ANALYSIS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..",
                                         "analysis"))
if _ANALYSIS not in sys.path:
    sys.path.insert(0, _ANALYSIS)

from verify_temporal_arms import canonical, rules  # noqa: E402

PKG_DIR = os.path.join(_ANALYSIS, "verify_temporal_arms")


class TestTheVerifierIsIndependentOfTheProducer:
    """The verifier may not import the thing it verifies. Enforced on the source."""

    def test_no_verifier_module_imports_the_producer_or_the_direct_lane(self):
        offenders = []
        for name in sorted(os.listdir(PKG_DIR)):
            if not name.endswith(".py"):
                continue
            tree = ast.parse(open(os.path.join(PKG_DIR, name)).read())
            for node in ast.walk(tree):
                mods = []
                if isinstance(node, ast.Import):
                    mods = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    mods = [node.module or ""]
                    if node.level:            # any relative import beyond the package
                        mods = [f".{m}" for m in mods]
                for mod in mods:
                    root = mod.split(".")[0]
                    if root in ("direct", "run_screen", "projection", "disposition"):
                        offenders.append(f"{name}: {mod}")
        assert offenders == [], (
            f"the verifier imports the lane it verifies: {offenders}. A checker that "
            "reuses the producer's sign map, key grammar or rank rule cannot catch an "
            "error in any of them")

    def test_the_verifier_never_imports_numpy_or_a_data_stack(self):
        """Pure stdlib: the rules must be readable and runnable without the stack."""
        offenders = []
        for name in sorted(os.listdir(PKG_DIR)):
            if not name.endswith(".py"):
                continue
            src = open(os.path.join(PKG_DIR, name)).read()
            for node in ast.walk(ast.parse(src)):
                if isinstance(node, ast.Import):
                    offenders += [a.name for a in node.names if a.name == "numpy"]
                if isinstance(node, ast.ImportFrom) and node.module == "numpy":
                    offenders.append(name)
        assert offenders == []


class TestTheSignTransform:
    def test_the_sign_map_is_exactly_the_two_desired_changes(self):
        assert rules.SIGN == {"increase": 1, "decrease": -1}
        assert rules.DESIRED_CHANGES == ("increase", "decrease")

    def test_arm_value_is_the_signed_base_delta(self):
        assert rules.arm_value(2.5, "increase") == 2.5
        assert rules.arm_value(2.5, "decrease") == -2.5

    def test_a_missing_base_stays_missing_and_never_becomes_zero(self):
        assert rules.arm_value(None, "increase") is None
        assert rules.arm_value(None, "decrease") is None

    def test_zero_never_acquires_a_sign(self):
        assert rules.arm_value(0.0, "decrease") == 0.0
        assert str(rules.arm_value(0.0, "decrease")) == "0.0"

    def test_a_pole_handed_in_where_a_desired_change_belongs_is_refused_by_name(self):
        with pytest.raises(rules.RuleViolation, match="POLE"):
            rules.arm_value(1.0, "high")

    def test_a_role_is_not_a_desired_change(self):
        with pytest.raises(rules.RuleViolation):
            rules.arm_value(1.0, "toward_B")


class TestTheBaseEffectIsADifferenceInDifferences:
    def test_base_delta_is_to_minus_from(self):
        assert rules.base_temporal_delta(1.0, 4.0) == 3.0

    def test_swapping_the_ordered_pair_negates_the_base_effect(self):
        assert rules.base_temporal_delta(4.0, 1.0) == -3.0

    def test_a_missing_endpoint_is_no_estimate_and_never_zero(self):
        assert rules.base_temporal_delta(None, 4.0) is None
        assert rules.base_temporal_delta(1.0, None) is None

    def test_a_nonfinite_endpoint_is_not_a_value(self):
        assert rules.base_temporal_delta(float("nan"), 1.0) is None
        assert rules.base_temporal_delta(float("inf"), 1.0) is None


class TestTheEstimandIsNotAFateClaim:
    def test_the_rule_module_holds_no_rate_slope_or_trajectory(self):
        src = open(os.path.join(PKG_DIR, "rules.py")).read().lower()
        for banned in ("def rate", "def slope", "def velocity", "def trajectory",
                       "per_cell", "lineage"):
            assert f"{banned}(" not in src

    def test_the_declared_estimand_is_population_level(self):
        assert rules.ESTIMAND_LEVEL == "population"
        assert rules.ESTIMAND_IS_PER_CELL_FATE is False
        assert rules.ESTIMAND_IS_LINEAGE_TRACED is False


class TestTheArmKeyGrammar:
    def test_the_key_is_kind_program_change_from_to(self):
        assert rules.arm_key("treg_like", "increase", "Rest", "Stim48hr") == \
            "temporal|treg_like|increase|Rest|Stim48hr"

    def test_swapping_from_and_to_is_a_different_key(self):
        a = rules.arm_key("p", "increase", "Rest", "Stim8hr")
        b = rules.arm_key("p", "increase", "Stim8hr", "Rest")
        assert a != b

    def test_the_key_carries_neither_a_pole_nor_a_role(self):
        key = rules.arm_key("treg_like", "decrease", "Rest", "Stim48hr")
        for token in ("high", "low", "away_from_A", "toward_B"):
            assert token not in key

    def test_a_separator_inside_a_part_is_refused(self):
        with pytest.raises(rules.RuleViolation, match=r"\|"):
            rules.arm_key("a|b", "increase", "Rest", "Stim8hr")

    def test_parse_round_trips_and_refuses_a_forged_key(self):
        key = rules.arm_key("p", "decrease", "Rest", "Stim8hr")
        assert rules.parse_arm_key(key) == ("p", "decrease", "Rest", "Stim8hr")
        with pytest.raises(rules.RuleViolation):
            rules.parse_arm_key("direct|p|decrease|Rest")


class TestTheOrderedPairUniverse:
    def test_three_conditions_give_exactly_six_ordered_distinct_pairs(self):
        pairs = rules.ordered_pairs(["Rest", "Stim8hr", "Stim48hr"])
        assert len(pairs) == 6
        assert len(set(pairs)) == 6
        assert all(a != b for a, b in pairs)
        assert ("Rest", "Stim48hr") in pairs and ("Stim48hr", "Rest") in pairs

    def test_both_directions_of_every_pair_are_present(self):
        pairs = set(rules.ordered_pairs(["Rest", "Stim8hr", "Stim48hr"]))
        assert all((b, a) in pairs for a, b in pairs)

    def test_the_pair_set_is_derived_and_not_a_hard_coded_treg_th1_pair(self):
        pairs = rules.ordered_pairs(["A", "B", "C", "D"])
        assert len(pairs) == 12                      # n*(n-1), derived

    def test_a_duplicated_condition_is_refused_rather_than_deduplicated(self):
        with pytest.raises(rules.RuleViolation, match="duplicate"):
            rules.ordered_pairs(["Rest", "Rest", "Stim8hr"])

    def test_fewer_than_two_conditions_cannot_make_an_ordered_pair(self):
        with pytest.raises(rules.RuleViolation):
            rules.ordered_pairs(["Rest"])


class TestTheProjectionIdentity:
    def test_delta_is_the_panel_mean_minus_the_control_mean(self):
        assert rules.projection_delta(2.0, 0.5) == 1.5

    def test_projection_status_is_derived_from_the_surviving_counts(self):
        assert rules.projection_status(5, 12) == "ok"
        assert rules.projection_status(0, 12) == "insufficient_axis_coverage"
        assert rules.projection_status(5, 9) == "insufficient_axis_coverage"

    def test_an_unresolved_mask_is_never_projected(self):
        assert rules.projection_status(None, None, mask_resolved=False) == \
            "mask_unresolved"


class TestEvaluabilityAndTemporalStatus:
    def test_a_failed_base_qc_is_not_evaluable(self):
        state, ok, _ = rules.arm_state(base_state="excluded_low_expression",
                                       base_passed=False, projection_status="ok")
        assert (state, ok) == ("excluded_base_qc", False)

    def test_an_ok_projection_on_passing_base_qc_is_evaluable(self):
        state, ok, _ = rules.arm_state(base_state="base_qc_passed", base_passed=True,
                                       projection_status="ok")
        assert (state, ok) == ("evaluable", True)

    def test_absence_outranks_non_evaluability(self):
        assert rules.temporal_status(from_present=False, to_present=True,
                                     from_evaluable=False, to_evaluable=True) == \
            "target_absent_at_from_condition"

    def test_both_endpoints_evaluable_and_present_is_estimated(self):
        assert rules.temporal_status(from_present=True, to_present=True,
                                     from_evaluable=True, to_evaluable=True) == \
            "estimated"


class TestTheRankRule:
    def _recs(self, values):
        return [{"target_id": t, "arm_value": v, "evaluable": v is not None}
                for t, v in values]

    def test_rank_is_descending_on_the_emitted_canonical_value(self):
        got = rules.rank_population(self._recs([("T1", 1.0), ("T2", 3.0),
                                                ("T3", 2.0)]))
        assert got == {"T2": 1, "T3": 2, "T1": 3}

    def test_an_exact_tie_breaks_on_target_id_ascending_in_BOTH_arms(self):
        inc = rules.rank_population(self._recs([("T2", 5.0), ("T1", 5.0)]))
        dec = rules.rank_population(self._recs([("T2", -5.0), ("T1", -5.0)]))
        assert inc == {"T1": 1, "T2": 2}
        # the decrease arm is NOT the mirror image: the tie-break runs ascending in both
        assert dec == {"T1": 1, "T2": 2}

    def test_a_non_evaluable_or_null_target_gets_a_null_rank(self):
        got = rules.rank_population(self._recs([("T1", 1.0), ("T2", None)]))
        assert got == {"T1": 1}

    def test_ranking_is_invariant_to_input_order(self):
        a = rules.rank_population(self._recs([("T1", 1.0), ("T2", 3.0)]))
        b = rules.rank_population(self._recs([("T2", 3.0), ("T1", 1.0)]))
        assert a == b


class TestTheCanonicalFormIsTheVerifiersOwn:
    def test_key_order_is_not_content(self):
        assert canonical.content_hash({"a": 1, "b": 2}) == \
            canonical.content_hash({"b": 2, "a": 1})

    def test_a_changed_value_changes_the_content_hash(self):
        assert canonical.content_hash({"a": 1}) != canonical.content_hash({"a": 2})

    def test_nan_may_not_be_serialised(self):
        with pytest.raises(ValueError):
            canonical.canonical_json({"a": float("nan")})

    def test_a_nonfinite_scientific_value_canonicalises_to_null(self):
        assert canonical.canonical_num(float("inf")) is None
        assert canonical.canonical_num(float("nan")) is None
        assert canonical.canonical_num(2.5) == 2.5
