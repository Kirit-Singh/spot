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
    """Mutate the SHIPPED artifact on disk, then re-verify it.

    ``mutate_prov`` writes the mutated provenance BACK TO DISK — because that is what a
    real bad artifact looks like, and because the verifier now reads the shipped bytes
    rather than whatever dict a caller hands it. The mutated dict is passed as the caller
    copy too, so the honest-producer case (generator emits a bad artifact and hands over
    its own view of it) is what gets exercised. See ``TestTheVerifierReadsTheShippedBytes``
    for the adversarial case: poison the file, pass the CLEAN dict.
    """
    if mutate_df is not None:
        path = os.path.join(out_dir, "temporal.parquet")
        mutate_df(pd.read_parquet(path)).to_parquet(path, index=False)
    if mutate_prov is not None:
        prov = mutate_prov(json.loads(json.dumps(prov)))
        with open(os.path.join(out_dir, "temporal_provenance.json"), "w") as fh:
            json.dump(prov, fh, indent=2)
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


class TestTheQShapedHoleTheReAuditWalkedThrough:
    """B4 residual — the SIX fields an independent re-audit injected and got ADMITTED.

    The pattern caught ``pvalue`` (via ``pval``) but had nothing for the q-spellings,
    nothing for ``significance``, and nothing for a key that is just ``p``. Each of these
    was injected into ``provenance.estimator`` and came back verdict=admit.

    They are parametrised at the exact injection site the auditor used, so this test is
    the demonstration, not a paraphrase of it.
    """

    DEMONSTRATED = [
        ("qval", 0.4),
        ("adj_qval", 0.4),
        ("q_val_adjusted", 0.4),
        ("qvalue", 0.4),
        ("bh_significance", 0.01),
        ("p", 0.01),
    ]

    @pytest.mark.parametrize("key,value", DEMONSTRATED)
    def test_the_firewall_now_catches_it(self, key, value):
        assert admission.forbidden_keys({key: value}) == [key]

    @pytest.mark.parametrize("key,value", DEMONSTRATED)
    def test_injected_into_provenance_estimator_the_artifact_is_REJECTED(
            self, artifact, key, value):
        out, prov = artifact

        def mutate(p):
            p["estimator"][key] = value
            return p

        r = reverify(out, prov, mutate_prov=mutate)
        assert r["verdict"] == verify_temporal.REJECT
        assert "no_forbidden_key_at_any_depth" in failed(r)

    @pytest.mark.parametrize("key,value", DEMONSTRATED)
    def test_it_is_caught_at_ANY_nesting_depth_too(self, key, value):
        obj = {"estimator": {"calibration": [{"per_program": {key: value}}]}}
        hits = admission.forbidden_keys(obj)
        assert hits == [f"estimator.calibration[0].per_program.{key}"]

    def test_the_docstring_no_longer_claims_more_than_the_code_delivers(self):
        # The original docstring asserted q_val_adjusted was caught. It was not. A
        # firewall documented as stricter than it is, is the one nobody re-checks.
        import inspect
        doc = inspect.getdoc(admission)
        for spelling in ("qval", "q_val", "significance", "adj_"):
            assert spelling in doc
        for claimed in ("q_val_adjusted", "bh_significance"):
            assert admission.forbidden_keys({claimed: 1}) == [claimed]


class TestTheVerifierReadsTheShippedBytes:
    """B4 re-audit — the verifier used to firewall the CALLER'S DICT, not the artifact.

    The demonstrated attack: poison the emitted ``temporal_provenance.json`` on disk, then
    hand the verifier the pristine in-memory dict. It ADMITTED — and printed the sha256 of
    the file it never opened. A verifier that trusts its caller's copy of the thing it is
    verifying is not a verifier; it is a formality with a hash beside it.
    """

    def _poison_file_only(self, out_dir, key, value, at=None):
        """Poison the SHIPPED file. Return the CLEAN dict, as the attacker would pass."""
        path = os.path.join(out_dir, "temporal_provenance.json")
        with open(path) as fh:
            clean = json.load(fh)
        poisoned = json.loads(json.dumps(clean))
        target = poisoned if at is None else poisoned[at]
        target[key] = value
        with open(path, "w") as fh:
            json.dump(poisoned, fh, indent=2)
        return clean

    @pytest.mark.parametrize("key", [
        "empirical_q_value", "empirical_p_value", "nominal_p", "q_val", "qvalue",
        "fdr", "combined_objective",
    ])
    def test_an_ON_DISK_poison_is_REJECTED_even_with_a_clean_caller_dict(
            self, artifact, key):
        out, _ = artifact
        clean = self._poison_file_only(out, key, 0.01, at="estimator")
        # the caller's copy really is clean: the poisoned KEY is not in it
        assert key not in clean["estimator"]
        assert admission.forbidden_keys(clean) == []

        r = verify_temporal.verify(out_dir=out, provenance=clean)
        assert r["verdict"] == verify_temporal.REJECT
        assert "no_forbidden_key_at_any_depth" in failed(r)

    def test_the_caller_dict_is_not_even_required(self, artifact):
        # The shipped bytes are the subject. A verifier that needs to be TOLD what it is
        # verifying can be told the wrong thing.
        out, _ = artifact
        assert verify_temporal.verify(out_dir=out)["verdict"] == verify_temporal.ADMIT

        self._poison_file_only(out, "empirical_q_value", 0.01, at="estimator")
        r = verify_temporal.verify(out_dir=out)      # no caller dict at all
        assert r["verdict"] == verify_temporal.REJECT
        assert "no_forbidden_key_at_any_depth" in failed(r)

    def test_a_caller_dict_that_disagrees_with_the_shipped_file_is_REJECTED(self,
                                                                            artifact):
        out, _ = artifact
        clean = self._poison_file_only(out, "empirical_q_value", 0.01, at="estimator")
        r = verify_temporal.verify(out_dir=out, provenance=clean)
        assert "caller_provenance_matches_the_shipped_file" in failed(r)

    def test_it_proves_the_bytes_it_firewalled_are_the_bytes_it_hashed(self, artifact):
        out, prov = artifact
        r = verify_temporal.verify(out_dir=out, provenance=prov)
        assert r["verdict"] == verify_temporal.ADMIT
        # the check exists, it passed, and the report pins the canonical bytes it read
        assert "the_provenance_we_verified_is_the_provenance_we_hashed" in {
            c["check"] for c in r["checks"]}
        assert len(r["artifact_identity"]["provenance_canonical_sha256"]) == 64

    def test_an_unparseable_shipped_provenance_is_REJECTED(self, artifact):
        out, prov = artifact
        with open(os.path.join(out, "temporal_provenance.json"), "w") as fh:
            fh.write("{ this is not json")
        r = verify_temporal.verify(out_dir=out, provenance=prov)
        assert r["verdict"] == verify_temporal.REJECT
        assert "shipped_provenance_loads_from_disk" in failed(r)


class TestTheNominalPHole:
    """The THIRD audit's key: not a p-word, not a bare p. Both earlier passes missed it."""

    def test_nominal_p_is_caught(self):
        assert admission.forbidden_keys({"nominal_p": 0.01}) == ["nominal_p"]

    @pytest.mark.parametrize("key", [
        "nominal_p", "nominal_q", "raw_p", "raw_q", "p_adjusted", "q_adjusted",
        "emp_p", "emp_q", "p_bh", "p", "q",
    ])
    def test_every_standalone_p_or_q_token_is_caught(self, key):
        assert admission.forbidden_keys({key: 1}) == [key]

    @pytest.mark.parametrize("key", [
        "program_id", "pathway_run_id", "n_panel_surviving", "comparison_id",
        "target_symbol", "peak_rank", "coverage", "policy_id", "sparse_panel_caution",
    ])
    def test_an_honest_key_containing_p_or_q_is_not_caught(self, key):
        assert admission.forbidden_keys({key: 1}) == []


class TestTheBareScalarKeys:
    def test_a_bare_p_and_a_bare_q_are_refused(self):
        assert admission.forbidden_keys({"p": 0.01}) == ["p"]
        assert admission.forbidden_keys({"q": 0.05}) == ["q"]
        assert admission.forbidden_keys({"P": 0.01}) == ["P"]

    def test_they_are_matched_EXACTLY_and_never_as_a_substring(self):
        # A substring rule for "p" would refuse every key with a p in it, and a firewall
        # that refuses everything is a firewall somebody turns off.
        for innocent in ("program_id", "pathway_run_id", "n_panel_surviving",
                         "comparison_id", "target_symbol", "peak_rank", "coverage"):
            assert admission.forbidden_keys({innocent: 1}) == []


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
    def test_the_exact_exceptions_are_EXACTLY_these(self):
        """The list is EXACT, and widening it is a deliberate act that lands here first.

        MIGRATION (all-arm pathway contract): the five `scorer_view` names were added. They
        match /score/ because "scorer" contains "score", but they are IDENTITY HASHES — they
        name WHICH Stage-1 scorer view a run bound — and never a number computed from one.
        Without the exemption the firewall fired on every honest all-arm bundle and refused
        the truth; a firewall that refuses the truth is one somebody turns off.

        The PATTERN is untouched. `pathway_score`, `combined_score` and every other
        statistic-shaped key still fire — see the two tests below, which is what makes this
        an exemption and not a hole.
        """
        assert admission.KEY_FIREWALL_EXCEPTIONS == frozenset({
            "away_from_A_zscore", "toward_B_zscore",
            "scorer_view", "scorer_view_id", "scorer_view_sha256",
            "release_scorer_view_canonical_sha256", "release_scorer_projection_sha256",
        })

    def test_the_scorer_view_exemption_is_not_a_hole_in_the_pattern(self):
        """Every statistic-shaped key the exemption might have let through still fires."""
        for key in ("pathway_score", "combined_score", "balanced_score", "score",
                    "weighted_score", "scorer_view_score", "p_value", "q_value", "fdr",
                    "nominal_p", "padj"):
            assert admission.forbidden_keys({key: 1.0}) == [key], key

    def test_the_exempt_names_pass_ONLY_at_their_exact_spelling(self):
        assert admission.forbidden_keys({"scorer_view_sha256": "abc"}) == []
        assert admission.forbidden_keys({"scorer_view_sha256_score": 1.0}) == [
            "scorer_view_sha256_score"]

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

    def test_the_pathway_lanes_prohibition_is_exempt_only_while_it_forbids(self):
        # the ban on fusing enrichment with convergence into one "pathway score"
        assert admission.forbidden_keys({"evidence_lines_are_combined": False}) == []
        assert admission.forbidden_keys({"evidence_lines_are_combined": True}) == \
            ["evidence_lines_are_combined"]

    def test_the_reliability_declaration_is_exempt_only_while_it_denies(self):
        # "the reliability badge is NOT a significance test" — the broadened pattern now
        # matches it (via /significance/), and it is exempt only while it says so.
        assert admission.forbidden_keys(
            {"reliability_is_a_significance_test": False}) == []
        assert admission.forbidden_keys(
            {"reliability_is_a_significance_test": True}) == \
            ["reliability_is_a_significance_test"]

    def test_every_negative_declaration_is_a_prohibition_and_defaults_to_false(self):
        # An exemption list is only auditable if everything on it is the same KIND of
        # thing. Each of these is a rule saying "this is forbidden".
        assert set(admission.NEGATIVE_DECLARATIONS) == {
            "combined_objective_permitted", "evidence_lines_are_combined",
            "reliability_is_a_significance_test",
            "combined_arm_eligibility_permitted"}
        assert all(v is False for v in admission.NEGATIVE_DECLARATIONS.values())


class TestTheBroadenedPatternDoesNotRefuseHonestArtifacts:
    """A firewall that refuses everything is a firewall somebody turns off."""

    def test_a_clean_temporal_artifact_still_admits(self, artifact):
        out, prov = artifact
        assert verify_temporal.verify(
            out_dir=out, provenance=prov)["verdict"] == verify_temporal.ADMIT

    def test_the_honest_emitted_keys_do_not_fire(self, artifact):
        # every key the real artifacts ship, against the broadened pattern
        out, prov = artifact
        df = pd.read_parquet(os.path.join(out, "temporal.parquet"))
        ends = pd.read_parquet(os.path.join(out, "endpoints.parquet"))
        hits = (admission.forbidden_keys({c: None for c in df.columns})
                + admission.forbidden_keys({c: None for c in ends.columns})
                + admission.forbidden_keys(prov))
        assert hits == []

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
