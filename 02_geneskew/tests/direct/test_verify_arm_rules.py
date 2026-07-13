"""The INDEPENDENT arm rules, re-derived from ROUND4_ADDENDUM c4773562.

These tests check the VERIFIER's own reimplementation against the addendum TEXT — never
against the producer. The producer is not imported here for the same reason the verifier
does not import it: two copies of a rule that were derived from each other are one copy.

The addendum's frozen mapping, quoted:

    away_from_A(high) -> decrease
    away_from_A(low)  -> increase
    toward_B(high)    -> increase
    toward_B(low)     -> decrease
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "analysis", "direct"))

import verify_arm_rules as AR  # noqa: E402


class TestTheFrozenDesiredChangeMapping:
    @pytest.mark.parametrize("role,pole,change", [
        ("away_from_A", "high", "decrease"),
        ("away_from_A", "low", "increase"),
        ("toward_B", "high", "increase"),
        ("toward_B", "low", "decrease"),
    ])
    def test_each_of_the_four_addendum_lines(self, role, pole, change):
        assert AR.desired_change(role, pole) == change

    def test_the_mapping_has_exactly_four_entries_and_no_default(self):
        assert len(AR.DESIRED_CHANGE_BY_ROLE_AND_POLE) == 4
        with pytest.raises(AR.ArmRuleError):
            AR.desired_change("away_from_A", "sideways")

    def test_the_same_pole_is_OPPOSITE_changes_in_the_two_roles(self):
        # the whole reason a pole may not key an arm
        for pole in ("high", "low"):
            assert AR.desired_change("away_from_A", pole) != \
                AR.desired_change("toward_B", pole)


class TestTheArmKey:
    def test_the_key_format_is_direct_program_change_condition(self):
        assert AR.direct_arm_key("Treg", "increase", "Rest") == \
            "direct|Treg|increase|Rest"

    def test_a_POLE_may_never_key_an_arm(self):
        for pole in ("high", "low"):
            with pytest.raises(AR.ArmRuleError):
                AR.direct_arm_key("Treg", pole, "Rest")

    def test_a_ROLE_may_never_key_an_arm(self):
        for role in ("away_from_A", "toward_B"):
            with pytest.raises(AR.ArmRuleError):
                AR.direct_arm_key("Treg", role, "Rest")

    def test_the_expected_inventory_is_two_arms_per_admitted_program(self):
        admitted = [f"p{i}" for i in range(10)]
        keys = AR.expected_arm_keys(admitted, "Rest")
        assert len(keys) == 20
        assert len(set(keys)) == 20
        assert keys == sorted(keys)
        for p in admitted:
            assert f"direct|{p}|increase|Rest" in keys
            assert f"direct|{p}|decrease|Rest" in keys


class TestTheSignTransform:
    def test_increase_is_the_base_delta_itself(self):
        assert AR.arm_value(0.25, "increase") == 0.25

    def test_decrease_is_the_EXACT_negation(self):
        assert AR.arm_value(0.25, "decrease") == -0.25

    def test_zero_negates_to_positive_zero_never_minus_zero(self):
        v = AR.arm_value(0.0, "decrease")
        assert v == 0.0
        # -0.0 prints as a different number and the data makes no such distinction
        assert str(v) == "0.0"

    def test_a_null_base_delta_has_no_arm_value(self):
        assert AR.arm_value(None, "increase") is None


class TestTheRankRule:
    def _row(self, tid, value, evaluable=True):
        return {"target_id": tid, "value": value, "evaluable": evaluable, "rank": None}

    def test_rank_1_is_the_LARGEST_arm_value(self):
        rows = [self._row("t2", 1.0), self._row("t1", 5.0)]
        assert AR.rank_arm(rows)["t1"] == 1
        assert AR.rank_arm(rows)["t2"] == 2

    def test_ties_break_on_target_id_ASCENDING(self):
        rows = [self._row("tb", 2.0), self._row("ta", 2.0)]
        ranks = AR.rank_arm(rows)
        assert (ranks["ta"], ranks["tb"]) == (1, 2)

    def test_a_non_evaluable_target_is_ABSENT_from_the_ranking_not_last(self):
        rows = [self._row("t1", 5.0), self._row("t2", 9.0, evaluable=False)]
        ranks = AR.rank_arm(rows)
        assert ranks["t1"] == 1
        assert ranks["t2"] is None

    def test_a_nonfinite_value_is_never_ranked(self):
        rows = [self._row("t1", 5.0), self._row("t2", float("nan")),
                self._row("t3", float("inf"))]
        ranks = AR.rank_arm(rows)
        assert ranks["t2"] is None and ranks["t3"] is None

    def test_the_ranks_are_dense_1_to_n(self):
        rows = [self._row(f"t{i}", float(i)) for i in range(5)]
        rows.append(self._row("tx", None, evaluable=False))
        ranks = AR.rank_arm(rows)
        assigned = sorted(r for r in ranks.values() if r is not None)
        assert assigned == [1, 2, 3, 4, 5]

    def test_ranking_is_invariant_to_input_row_order(self):
        rows = [self._row(f"t{i}", float(i % 3)) for i in range(6)]
        forward = AR.rank_arm(list(rows))
        backward = AR.rank_arm(list(reversed(rows)))
        assert forward == backward

    def test_the_top_of_one_arm_is_the_BOTTOM_of_the_other(self):
        base = {"ta": 3.0, "tb": 1.0, "tc": -2.0}
        up = AR.rank_arm([self._row(t, AR.arm_value(v, "increase"))
                          for t, v in base.items()])
        down = AR.rank_arm([self._row(t, AR.arm_value(v, "decrease"))
                            for t, v in base.items()])
        assert up["ta"] == 1 and down["ta"] == 3
        assert up["tc"] == 3 and down["tc"] == 1


class TestTheCanonicalRowProjection:
    def _row(self, **kw):
        row = {"arm_key": "direct|p|increase|Rest", "program_id": "p",
               "desired_change": "increase", "condition": "Rest", "target_id": "t1",
               "base_delta": 1.5, "value": 1.5, "rank": 1, "evaluable": True,
               "projection_status": "ok", "base_state": "qc_pass_two_guide",
               "base_passed": True, "n_panel_surviving": 4, "n_control_surviving": 12}
        row.update(kw)
        return row

    def test_a_float_rank_from_parquet_canonicalises_to_an_int(self):
        # parquet round-trips an integer rank to a float; the bound hash must not care
        assert AR.canonical_rows([self._row(rank=1.0)]) == \
            AR.canonical_rows([self._row(rank=1)])

    def test_a_NaN_rank_canonicalises_to_null(self):
        [row] = AR.canonical_rows([self._row(rank=float("nan"))])
        assert row["rank"] is None

    def test_a_nonfinite_value_canonicalises_to_null(self):
        [row] = AR.canonical_rows([self._row(value=float("inf"))])
        assert row["value"] is None

    def test_the_hash_is_invariant_to_row_ORDER(self):
        a, b = self._row(target_id="t1"), self._row(target_id="t2")
        assert AR.rows_sha256([a, b]) == AR.rows_sha256([b, a])

    def test_the_hash_CHANGES_when_a_value_changes(self):
        assert AR.rows_sha256([self._row()]) != \
            AR.rows_sha256([self._row(value=1.6)])

    def test_the_hash_CHANGES_when_a_rank_changes(self):
        assert AR.rows_sha256([self._row()]) != AR.rows_sha256([self._row(rank=2)])


class TestTheForbiddenDisplayOnlyFields:
    def test_a_pareto_tier_ANYWHERE_is_a_violation(self):
        hits = AR.forbidden_hits({"arms": [{"arm_key": "k", "pareto_tier": 1}]})
        assert hits and any("pareto_tier" in h for h in hits)

    def test_a_joint_status_NESTED_deep_is_a_violation(self):
        hits = AR.forbidden_hits({"a": {"b": [{"c": {"joint_status": "opposed"}}]}})
        assert hits

    def test_a_q_value_or_fdr_is_a_violation(self):
        for field in ("p_value", "q_value", "fdr", "padj", "pval"):
            assert AR.forbidden_hits({field: 0.01}), field

    def test_a_combined_or_balanced_or_weighted_or_overall_score_is_a_violation(self):
        for field in ("combined_score", "balanced_skew", "weighted_score",
                      "overall_rank"):
            assert AR.forbidden_hits({field: 1.0}), field

    def test_a_pair_ROLE_field_is_a_violation(self):
        for field in ("away_from_A", "toward_B", "rank_away_from_A"):
            assert AR.forbidden_hits({field: 1.0}), field

    def test_the_NEGATIVE_declarations_are_not_violations(self):
        # `pareto_emitted: false` is a DISCLOSURE, not an emission. A check that could
        # not tell them apart would force the bundle to stop saying what it refuses to do.
        method = {"pareto_emitted": False, "concordance_emitted": False,
                  "pair_fields_emitted": False, "combined_objective_permitted": False,
                  "arm_key_carries_pole_or_role": False, "names_a_program_pair": False}
        assert AR.forbidden_hits(method) == []

    def test_a_negative_declaration_flipped_TRUE_is_a_violation(self):
        assert AR.forbidden_hits({"pareto_emitted": True})

    def test_a_forbidden_token_hiding_in_a_STRING_VALUE_is_a_violation(self):
        assert AR.forbidden_hits({"note": "the pareto_tier is 3"})

    def test_a_clean_arm_bundle_body_has_no_hits(self):
        assert AR.forbidden_hits({
            "schema_version": "spot.stage02_direct_arm_bundle.v1",
            "condition": "Rest",
            "arms": [{"arm_key": "direct|Treg|increase|Rest", "n_ranked": 3,
                      "rank_rule_id": "spot.stage02.direct.arm_rank.v1"}],
        }) == []
