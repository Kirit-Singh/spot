"""M1 — a negative enrichment must report its TRAILING edge, not an empty list.

The defect: the leading edge was always taken as "the hits seen at or before the peak
rank". For a POSITIVE enrichment that is right — the members responsible for the score
are the ones at the top. For a NEGATIVE enrichment it is exactly wrong: the running sum
descends to its trough on a run of MISSES, so at the trough no hit has been seen yet and
the edge comes back EMPTY. The reviewer's counterexample is the extreme case: every set
member sits at the bottom of the ranking, ES = -1.0, and the layer reported "enriched at
-1.0, responsible genes: none" — a score with nothing behind it.

A negative enrichment's members are at the BOTTOM. Its edge is the trailing edge: the
hits that fall AFTER the trough.
"""
from __future__ import annotations

import pytest
from direct import enrichment

# A ranking of 10 targets, scores descending.
RANKED = [(f"T{i}", 10.0 - i) for i in range(10)]      # T0=10.0 ... T9=1.0


class TestTheReviewersCounterexample:
    """Every member of the set sits at the very bottom -> ES = -1.0."""

    def test_the_score_really_is_minus_one(self):
        r = enrichment.enrich_one(RANKED, {"T8", "T9"})
        assert r["enrichment_value"] == pytest.approx(-1.0)

    def test_its_leading_edge_is_NOT_empty(self):
        r = enrichment.enrich_one(RANKED, {"T8", "T9"})
        assert r["leading_edge"] != []
        assert r["n_leading_edge"] > 0

    def test_the_edge_is_exactly_the_members_at_the_bottom(self):
        r = enrichment.enrich_one(RANKED, {"T8", "T9"})
        assert sorted(r["leading_edge"]) == ["T8", "T9"]

    def test_the_edge_is_declared_to_come_from_the_bottom(self):
        r = enrichment.enrich_one(RANKED, {"T8", "T9"})
        assert r["leading_edge_side"] == enrichment.EDGE_BOTTOM

    def test_the_score_still_has_someone_standing_behind_it(self):
        # The invariant the defect broke: a defined enrichment ALWAYS names the members
        # responsible for it. A score nobody is behind is a score nobody can check.
        r = enrichment.enrich_one(RANKED, {"T8", "T9"})
        assert r["enrichment_value"] is not None
        assert r["n_leading_edge"] >= 1


class TestPositiveEnrichmentIsUnchanged:
    def test_members_at_the_top_give_a_positive_score(self):
        r = enrichment.enrich_one(RANKED, {"T0", "T1"})
        assert r["enrichment_value"] > 0

    def test_its_edge_is_the_hits_at_or_before_the_peak(self):
        r = enrichment.enrich_one(RANKED, {"T0", "T1"})
        assert r["leading_edge"] == ["T0", "T1"]
        assert r["leading_edge_side"] == enrichment.EDGE_TOP

    def test_a_positive_edge_never_reaches_past_the_peak(self):
        # T0 is at the top; T9 at the bottom. The peak is at rank 1, so only T0 is in it.
        r = enrichment.enrich_one(RANKED, {"T0", "T9"})
        assert r["enrichment_value"] > 0
        assert r["leading_edge"] == ["T0"]
        assert "T9" not in r["leading_edge"]


class TestTheEdgeIsAlwaysWhatProducedTheScore:
    @pytest.mark.parametrize("members", [
        {"T8", "T9"}, {"T7", "T8", "T9"}, {"T0", "T1"}, {"T0"}, {"T9"},
        {"T4", "T5"}, {"T0", "T5", "T9"},
    ])
    def test_every_defined_enrichment_names_a_non_empty_edge(self, members):
        r = enrichment.enrich_one(RANKED, members)
        if r["enrichment_value"] is None:
            pytest.skip("undefined statistic reports no edge, by design")
        assert r["n_leading_edge"] >= 1
        assert len(r["leading_edge"]) == r["n_leading_edge"]

    @pytest.mark.parametrize("members", [
        {"T8", "T9"}, {"T7", "T8", "T9"}, {"T0", "T1"}, {"T4", "T5"},
    ])
    def test_the_edge_only_ever_contains_members_of_the_set(self, members):
        r = enrichment.enrich_one(RANKED, members)
        assert set(r["leading_edge"]) <= members

    def test_the_side_follows_the_sign_of_the_score(self):
        for members in ({"T8", "T9"}, {"T0", "T1"}, {"T4", "T5"}):
            r = enrichment.enrich_one(RANKED, members)
            if r["enrichment_value"] is None:
                continue
            expect = (enrichment.EDGE_TOP if r["enrichment_value"] > 0
                      else enrichment.EDGE_BOTTOM)
            assert r["leading_edge_side"] == expect

    def test_an_undefined_statistic_still_reports_no_edge_and_says_why(self):
        r = enrichment.enrich_one(RANKED, {"NOT_IN_THE_RANKING"})
        assert r["enrichment_value"] is None
        assert r["leading_edge"] == []
        assert r["leading_edge_side"] is None
        assert r["undefined_reason"] == "no_set_gene_in_ranking"


class TestTheConventionIsDeclaredAndBound:
    def test_the_module_names_its_edge_convention(self):
        assert enrichment.LEADING_EDGE_CONVENTION
        assert "trailing" in enrichment.LEADING_EDGE_CONVENTION.lower()
        assert enrichment.EDGE_IS_DIRECTION_AWARE is True

    def test_the_convention_enters_the_method_hash(self):
        from direct import pathway
        block = pathway.method_block(None)
        assert block["enrichment_leading_edge_convention"] == \
            enrichment.LEADING_EDGE_CONVENTION
        assert block["enrichment_edge_is_direction_aware"] is True

    def test_the_enrichment_method_id_records_that_the_edge_rule_changed(self):
        # A different edge rule is a different method: the same set can now come back
        # with members behind it where it previously came back with none.
        assert enrichment.METHOD_ID.endswith(".v2")
