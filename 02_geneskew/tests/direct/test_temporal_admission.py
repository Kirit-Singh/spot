"""B4 — the temporal verifier must FAIL CLOSED.

The defect: admission was a DENYLIST of exact column names. ``p_value`` was refused;
``did_pval``, ``q_val``, ``significance_padj`` and ``fdr_adjusted`` were all admitted,
because none of them is spelled exactly like a name on the list. The combined-objective
check was a substring scan that missed ``weighted`` entirely. And nothing recursed: a
disguised p/q nested inside the provenance JSON was never looked at. The verifier passed
artifacts it exists to refuse, which falsified the "verifier-enforced no-p/q" claim.

Admission is now:

  * an EXACT COLUMN ALLOWLIST per emitted file — an unknown column is a REJECT, not a
    shrug. A denylist can only refuse what someone thought of; an allowlist refuses
    everything nobody authorised;
  * a RECURSIVE KEY-NAME FIREWALL over every emitted object, at ANY nesting depth;
  * an IDENTITY BINDING: method, run, per-file and whole-directory hashes.
"""
from __future__ import annotations

import json
import os

import pandas as pd
import pytest
from direct.temporal import admission, run_temporal, verify_temporal


@pytest.fixture
def artifact(temporal_run):
    res = run_temporal.build_temporal(temporal_run())
    out = res["out_dir"]
    with open(os.path.join(out, "temporal_provenance.json")) as fh:
        prov = json.load(fh)
    assert res["verification"]["verdict"] == verify_temporal.ADMIT
    return out, prov


def reverify(out_dir, prov, mutate_df=None, mutate_prov=None):
    if mutate_df is not None:
        path = os.path.join(out_dir, "temporal.parquet")
        mutate_df(pd.read_parquet(path)).to_parquet(path, index=False)
    if mutate_prov is not None:
        prov = mutate_prov(json.loads(json.dumps(prov)))
    return verify_temporal.verify(out_dir=out_dir, provenance=prov)


def failed(report) -> set[str]:
    return {c["check"] for c in report["checks"] if c["status"] == verify_temporal.FAIL}


class TestACleanArtifactIsAdmitted:
    def test_it_admits(self, artifact):
        out, prov = artifact
        r = verify_temporal.verify(out_dir=out, provenance=prov)
        assert r["verdict"] == verify_temporal.ADMIT
        assert r["n_failed"] == 0


class TestTheDisguisedPQFirewall:
    """Every one of these was ADMITTED by the old exact-name denylist."""

    @pytest.mark.parametrize("column", [
        "p_value", "pvalue", "q_value", "fdr", "padj",       # the obvious ones
        "did_pval", "q_val_adjusted", "significance_padj",   # the disguises
        "fdr_adjusted", "A_temporal_pvalue", "empirical_pval",
    ])
    def test_a_disguised_p_or_q_column_is_rejected(self, artifact, column):
        out, prov = artifact

        def mutate(df):
            df[column] = 0.01
            return df

        r = reverify(out, prov, mutate_df=mutate)
        assert r["verdict"] == verify_temporal.REJECT
        assert failed(r) & {"no_forbidden_key_at_any_depth",
                            "temporal_columns_match_the_exact_allowlist"}

    def test_a_p_value_NESTED_in_the_provenance_is_rejected(self, artifact):
        out, prov = artifact

        def mutate(p):
            p["batch_policy"]["interaction_std"]["diff_naive_p_value"] = 0.03
            return p

        r = reverify(out, prov, mutate_prov=mutate)
        assert r["verdict"] == verify_temporal.REJECT
        assert "no_forbidden_key_at_any_depth" in failed(r)

    def test_a_p_value_buried_DEEP_in_a_nested_list_is_rejected(self, artifact):
        out, prov = artifact

        def mutate(p):
            p["comparisons"][0]["diagnostics"] = [
                {"per_target": [{"target": "X", "fdr": 0.001}]}]
            return p

        r = reverify(out, prov, mutate_prov=mutate)
        assert r["verdict"] == verify_temporal.REJECT
        assert "no_forbidden_key_at_any_depth" in failed(r)

    def test_the_firewall_reports_the_exact_path_it_refused(self, artifact):
        out, prov = artifact

        def mutate(p):
            p["estimator"]["calibration"] = {"empirical_fdr": 0.05}
            return p

        r = reverify(out, prov, mutate_prov=mutate)
        detail = [c["detail"] for c in r["checks"]
                  if c["check"] == "no_forbidden_key_at_any_depth"][0]
        assert "empirical_fdr" in detail


class TestTheCombinedObjectiveFirewall:
    @pytest.mark.parametrize("column", [
        "combined_did", "balanced_skew", "weighted_did", "combined_temporal_score",
        "overall_weighted_objective", "temporal_score",
    ])
    def test_a_combined_or_weighted_objective_column_is_rejected(self, artifact,
                                                                 column):
        out, prov = artifact

        def mutate(df):
            df[column] = 1.0
            return df

        r = reverify(out, prov, mutate_df=mutate)
        assert r["verdict"] == verify_temporal.REJECT

    def test_a_combined_objective_NESTED_in_the_provenance_is_rejected(self, artifact):
        out, prov = artifact

        def mutate(p):
            p["temporal_policy"]["combined_objective"] = {"weights": [0.5, 0.5]}
            return p

        r = reverify(out, prov, mutate_prov=mutate)
        assert r["verdict"] == verify_temporal.REJECT
        assert "no_forbidden_key_at_any_depth" in failed(r)


class TestTheExactColumnAllowlist:
    def test_an_unknown_column_is_rejected_even_when_it_looks_harmless(self, artifact):
        out, prov = artifact

        def mutate(df):
            df["notes"] = "just a helpful annotation"
            return df

        r = reverify(out, prov, mutate_df=mutate)
        assert r["verdict"] == verify_temporal.REJECT
        assert "temporal_columns_match_the_exact_allowlist" in failed(r)

    def test_a_missing_required_column_is_rejected(self, artifact):
        out, prov = artifact

        def mutate(df):
            return df.drop(columns=["away_from_A_temporal_did"])

        r = reverify(out, prov, mutate_df=mutate)
        assert r["verdict"] == verify_temporal.REJECT
        assert "temporal_columns_match_the_exact_allowlist" in failed(r)

    def test_the_allowlist_is_exactly_what_the_generator_emits(self, artifact):
        # The allowlist IS the contract. If the generator grows a column, this fails and
        # someone has to authorise it — which is the entire point.
        out, _ = artifact
        cols = set(pd.read_parquet(os.path.join(out, "temporal.parquet")).columns)
        assert cols == set(admission.TEMPORAL_COLUMNS)

    def test_the_endpoint_allowlist_is_exactly_what_the_generator_emits(self, artifact):
        out, _ = artifact
        cols = set(pd.read_parquet(os.path.join(out, "endpoints.parquet")).columns)
        assert cols == set(admission.ENDPOINT_COLUMNS)


class TestTheNamedFirewallExceptions:
    def test_the_within_condition_zscore_columns_are_the_ONLY_exact_exceptions(self):
        # They match /score/ but they are the within-condition sensitivity effect layer,
        # not an objective. The exception is an explicit, enumerated, auditable list —
        # not a silent hole in the pattern.
        assert admission.KEY_FIREWALL_EXCEPTIONS == frozenset(
            {"away_from_A_zscore", "toward_B_zscore"})

    def test_the_exception_does_not_license_a_lookalike(self, artifact):
        out, prov = artifact

        def mutate(df):
            df["combined_zscore"] = 1.0        # not an exception; matches the pattern
            return df

        r = reverify(out, prov, mutate_df=mutate)
        assert r["verdict"] == verify_temporal.REJECT


class TestTheNegativeDeclarationIsExemptOnlyWhileItForbids:
    """The artifact must be able to write down its own prohibition — and only that."""

    def test_the_prohibition_itself_is_admitted(self):
        assert admission.forbidden_keys({"combined_objective_permitted": False}) == []

    def test_flipping_the_prohibition_ON_fires_the_firewall(self):
        # This is the exact event the firewall exists to catch: a run that has started
        # permitting a combined objective. The exemption does not survive the flip.
        assert admission.forbidden_keys(
            {"combined_objective_permitted": True}) == ["combined_objective_permitted"]

    def test_a_truthy_lookalike_cannot_pose_as_the_prohibition(self):
        for sneaky in (1, "false", "no", [], 0):
            assert admission.forbidden_keys(
                {"combined_objective_permitted": sneaky}) == \
                ["combined_objective_permitted"]

    def test_a_flipped_prohibition_in_a_real_artifact_is_rejected(self, artifact):
        out, prov = artifact

        def mutate(p):
            p["run_binding"]["temporal_method"]["within_condition_method"][
                "combined_objective_permitted"] = True
            return p

        r = reverify(out, prov, mutate_prov=mutate)
        assert r["verdict"] == verify_temporal.REJECT
        assert "no_forbidden_key_at_any_depth" in failed(r)


class TestTheIdentityBinding:
    def test_the_records_must_carry_the_provenance_run_id(self, artifact):
        out, prov = artifact

        def mutate(df):
            df["temporal_run_id"] = "0" * 16
            return df

        r = reverify(out, prov, mutate_df=mutate)
        assert r["verdict"] == verify_temporal.REJECT
        assert "records_are_bound_to_the_run_and_the_method" in failed(r)

    def test_the_records_must_carry_the_provenance_method_hash(self, artifact):
        out, prov = artifact

        def mutate(df):
            df["temporal_method_sha256"] = "0" * 64
            return df

        r = reverify(out, prov, mutate_df=mutate)
        assert r["verdict"] == verify_temporal.REJECT
        assert "records_are_bound_to_the_run_and_the_method" in failed(r)

    def test_the_report_pins_every_file_and_the_directory(self, artifact):
        out, prov = artifact
        r = verify_temporal.verify(out_dir=out, provenance=prov)
        files = r["artifact_identity"]["files"]
        assert set(files) == {"temporal.parquet", "endpoints.parquet",
                              "temporal_provenance.json"}
        for sha in files.values():
            assert len(sha) == 64
        assert len(r["artifact_identity"]["artifact_sha256"]) == 64

    def test_the_directory_hash_moves_when_any_file_moves(self, artifact):
        out, prov = artifact
        before = verify_temporal.verify(
            out_dir=out, provenance=prov)["artifact_identity"]["artifact_sha256"]

        def mutate(df):
            df.loc[df.index[0], "away_from_A_from_value"] = 123.456
            return df

        after = reverify(out, prov,
                         mutate_df=mutate)["artifact_identity"]["artifact_sha256"]
        assert after != before

    def test_a_required_file_that_is_absent_is_rejected(self, artifact):
        out, prov = artifact
        os.remove(os.path.join(out, "endpoints.parquet"))
        r = verify_temporal.verify(out_dir=out, provenance=prov)
        assert r["verdict"] == verify_temporal.REJECT


class TestTheFirewallItself:
    def test_it_walks_dicts_lists_and_nested_mixtures(self):
        obj = {"a": [{"b": {"c": [{"q_value": 1}]}}]}
        hits = admission.forbidden_keys(obj)
        assert hits and "q_value" in hits[0]

    def test_it_reports_the_full_path_to_the_offending_key(self):
        obj = {"level1": {"level2": [{"level3": {"combined_score": 1}}]}}
        hits = admission.forbidden_keys(obj)
        assert hits == ["level1.level2[0].level3.combined_score"]

    def test_a_clean_object_produces_no_hits(self):
        assert admission.forbidden_keys(
            {"target_id": "X", "away_from_A_temporal_did": 1.0}) == []

    @pytest.mark.parametrize("key", [
        "p_value", "q_value", "fdr", "pval", "padj", "combined", "balanced",
        "weighted", "score", "PVAL", "Combined_Objective", "my_weighted_thing",
    ])
    def test_every_pattern_the_reviewer_named_is_caught_case_insensitively(self, key):
        assert admission.forbidden_keys({key: 1}) == [key]
