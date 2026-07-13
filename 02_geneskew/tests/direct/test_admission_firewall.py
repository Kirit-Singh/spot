"""The SHARED artifact-admission contract (``direct.admission``): the recursive p/q/
combined-objective key firewall, and the shipped-bytes reader.

Both halves used to live in ``temporal.admission`` beside the retired fixed-pair verifier;
neither was temporal-specific (the pathway lane reads and firewalls its provenance with
them too), so they moved to the shared ``direct`` root. These tests are the firewall's own —
migrated off the retired verifier so the security coverage survives the lane it came in with.

The firewall is a DENYLIST's opposite: it fires on a PATTERN at any nesting depth, so a
disguised ``q_val`` nested in a diagnostics list is caught where an exact-name denylist would
have admitted it.
"""
from __future__ import annotations

import json

import pytest
from direct import admission as A


class TestTheDisguisedPQFamily:
    @pytest.mark.parametrize("key", [
        "p_value", "q_value", "q_val", "qval", "pval", "padj", "fdr",
        "adj_p", "adj_q", "q_val_adjusted", "bh_significance", "significance"])
    def test_a_disguised_inference_field_is_caught(self, key):
        assert A.forbidden_keys({key: 0.01}) == [key]

    def test_the_bare_scalar_p_and_q_keys_are_caught_case_insensitively(self):
        assert A.forbidden_keys({"p": 0.01}) == ["p"]
        assert A.forbidden_keys({"q": 0.05}) == ["q"]
        assert A.forbidden_keys({"P": 0.01}) == ["P"]

    def test_nominal_p_the_hole_two_earlier_passes_missed_is_caught(self):
        assert A.forbidden_keys({"nominal_p": 0.01}) == ["nominal_p"]
        assert A.forbidden_keys({"raw_q": 1}) == ["raw_q"]

    @pytest.mark.parametrize("innocent", [
        "program_id", "panel_mean", "sparse_panel_caution", "n_splits_total",
        "desired_change", "temporal_provenance"])
    def test_an_honest_key_is_not_refused(self, innocent):
        assert A.forbidden_keys({innocent: 1}) == []


class TestTheCombinedObjectiveFamily:
    @pytest.mark.parametrize("key", [
        "combined_value", "weighted_value", "balanced_objective", "combined_score",
        "scorer_value"])
    def test_a_combined_or_weighted_objective_field_is_caught(self, key):
        assert A.forbidden_keys({key: 1.0}) == [key]


class TestRecursionIntoNestedStructures:
    def test_a_pq_buried_in_a_list_of_diagnostics_is_found_by_path(self):
        obj = {"diagnostics": [{"ok": 1}, {"empirical_q_value": 0.02}]}
        assert A.forbidden_keys(obj) == ["diagnostics[1].empirical_q_value"]

    def test_a_clean_nested_document_passes(self):
        obj = {"a": {"b": [{"program_id": "x", "delta": 0.1}]}}
        assert A.forbidden_keys(obj) == []


class TestTheExactNameExemptions:
    def test_the_sensitivity_zscore_layers_are_exempt_by_exact_spelling(self):
        assert A.forbidden_keys({"away_from_A_zscore": 1.0}) == []
        assert A.forbidden_keys({"toward_B_zscore": 1.0}) == []

    def test_the_exemption_is_the_spelling_not_the_shape(self):
        # a combined_zscore is NOT one of the two exempt names and must still fire
        assert A.forbidden_keys({"combined_zscore": 1.0}) == ["combined_zscore"]

    def test_the_exemption_set_is_exactly_the_two_sensitivity_layers(self):
        assert A.KEY_FIREWALL_EXCEPTIONS == frozenset(
            {"away_from_A_zscore", "toward_B_zscore"})


class TestTheNegativeDeclarationsAreExemptOnlyWhileTheyForbid:
    @pytest.mark.parametrize("key", sorted(A.NEGATIVE_DECLARATIONS))
    def test_a_prohibition_stated_as_false_is_exempt(self, key):
        assert A.forbidden_keys({key: False}) == []

    @pytest.mark.parametrize("key", sorted(A.NEGATIVE_DECLARATIONS))
    def test_the_same_key_flipped_true_fires_the_firewall(self, key):
        assert A.forbidden_keys({key: True}) == [key]

    def test_a_truthy_impostor_cannot_pose_as_the_prohibition(self):
        # `is False`, not `== False`: a truthy 1 or the string "false" is NOT the literal
        assert A.forbidden_keys({"combined_objective_permitted": 1}) == \
            ["combined_objective_permitted"]
        assert A.forbidden_keys({"combined_objective_permitted": "false"}) == \
            ["combined_objective_permitted"]

    def test_every_declared_prohibition_ships_as_false(self):
        assert all(v is False for v in A.NEGATIVE_DECLARATIONS.values())


class TestTheShippedBytesReader:
    def test_it_reads_and_hashes_the_bytes_on_disk_not_the_callers_copy(self, tmp_path):
        doc = {"schema_version": "x", "value": 1}
        p = tmp_path / "prov.json"
        p.write_text(json.dumps(doc))
        loaded = A.load_shipped(str(tmp_path), "prov.json")
        assert loaded["doc"] == doc
        assert len(loaded["sha256"]) == 64 and len(loaded["canonical_sha256"]) == 64

    def test_an_absent_document_is_refused_never_treated_as_clean(self, tmp_path):
        with pytest.raises(A.ShippedDocError, match="absent"):
            A.load_shipped(str(tmp_path), "missing.json")

    def test_unparseable_bytes_are_refused(self, tmp_path):
        (tmp_path / "bad.json").write_text("{not json")
        with pytest.raises(A.ShippedDocError, match="not parseable"):
            A.load_shipped(str(tmp_path), "bad.json")

    def test_caller_matches_on_canonical_content_not_key_order(self):
        shipped = {"a": 1, "b": 2}
        assert A.caller_matches(shipped, {"b": 2, "a": 1}) is True   # re-ordered is the same
        assert A.caller_matches(shipped, {"a": 1, "b": 3}) is False  # different is not
        assert A.caller_matches(shipped, None) is True               # no caller copy to check
