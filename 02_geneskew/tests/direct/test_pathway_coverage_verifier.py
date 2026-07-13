"""A3 — verify_pathway must RE-DERIVE the coverage arithmetic, not ratify it.

The coverage governance was GENERATOR-ONLY. The verifier admitted whatever the generator
declared, so every rule the generator was supposed to obey was enforced by the same code
that could break it. An audit resealed a ZERO-coverage pathway as headline-rankable and the
verifier ADMITTED it.

The verifier now holds its OWN copy of the frozen policy — deliberately NOT imported from
``genesets`` — so it can DISAGREE with the generator. A verifier that read the generator's
thresholds would ratify whatever the generator currently says, including a threshold quietly
loosened to make a result rankable, which is precisely the attack the governance exists to
stop.

Each mutation below edits the SHIPPED bytes and re-runs the standalone verifier.
"""
from __future__ import annotations

import json
import os

import pytest
from direct import genesets, run_pathway, verify_pathway
from direct.hashing import content_hash
from fixtures_pathway import write_gene_sets
from fixtures_spec import TARGET_GENES, UNIVERSE


@pytest.fixture
def artifact(synthetic_run, tmp_path):
    """A clean, ADMITTED pathway artifact — the thing to attack."""
    from direct import run_screen as rs
    from direct import universe as uni

    args = synthetic_run()
    ctx = rs.prepare(args)
    tu = uni.target_universe(ctx["identities_by_condition"])
    args.gene_sets = write_gene_sets(
        os.path.dirname(args.de_main), UNIVERSE, list(TARGET_GENES),
        ctx["gene_universe"]["sha256"], target_universe_sha256=tu["sha256"])

    res = run_pathway.build_pathway(args)
    assert res["verification"]["verdict"] == verify_pathway.ADMIT
    out = res["out_dir"]
    with open(os.path.join(out, "pathway_provenance.json")) as fh:
        prov = json.load(fh)
    return out, prov


def reseal_and_verify(out_dir, prov, mutate):
    """Mutate the shipped records, RESEAL records_sha256 honestly, and re-verify.

    Resealing matters: a sloppy forger who edits a record and leaves the content hash stale
    is caught by the content-addressing check, and the coverage rule is never reached. The
    HONEST-PRODUCER attack re-hashes its own forgery, so only an independent re-derivation
    of the coverage arithmetic can refuse it. That is the attack under test.
    """
    path = os.path.join(out_dir, "pathway.json")
    with open(path) as fh:
        doc = json.load(fh)
    mutate(doc)

    stripped = [{k: v for k, v in r.items()
                 if k not in ("pathway_run_id", "pathway_method_sha256")}
                for r in doc["records"]]
    doc["records_sha256"] = content_hash(stripped)
    prov = json.loads(json.dumps(prov))
    prov["run_binding"]["records_sha256"] = doc["records_sha256"]

    with open(path, "w") as fh:
        json.dump(doc, fh)
    with open(os.path.join(out_dir, "pathway_provenance.json"), "w") as fh:
        json.dump(prov, fh)
    return verify_pathway.verify(out_dir=out_dir, provenance=prov)


def failed(report):
    return {c["check"] for c in report["checks"]
            if c["status"] == verify_pathway.FAIL}


COVERAGE_CHECK = "coverage_and_per_arm_eligibility_rederive_from_the_record"
POLICY_CHECK = "the_artifact_ran_under_the_FROZEN_coverage_policy"


class TestMutation1_ZeroCoverageDeclaredRankable:
    """The audit's exact attack: a ZERO-coverage pathway, resealed as headline-rankable."""

    def _mutate(self, doc):
        r = doc["records"][0]
        r["n_source_symbols"] = 100
        r["n_genes_in_target_universe"] = 0
        r["target_source_coverage"] = 0.0
        r["global_coverage_disposition"] = "rankable"
        r["global_coverage_policy_passed"] = True
        for e in r["enrichment"].values():
            e["global_target_source_coverage"] = 0.0
            e["arm_headline_rankable"] = True
            e["arm_coverage_disposition"] = "rankable"

    def test_it_is_REJECTED(self, artifact):
        out, prov = artifact
        r = reseal_and_verify(out, prov, self._mutate)
        assert r["verdict"] == verify_pathway.REJECT

    def test_it_fails_the_named_coverage_re_derivation_gate(self, artifact):
        out, prov = artifact
        r = reseal_and_verify(out, prov, self._mutate)
        assert COVERAGE_CHECK in failed(r)

    def test_the_content_hash_was_RESEALED_so_only_the_coverage_check_can_catch_it(
            self, artifact):
        out, prov = artifact
        r = reseal_and_verify(out, prov, self._mutate)
        assert "records_sha256_recomputes_from_the_emitted_records" not in failed(r)


class TestMutation2_FourGlobalOneArmEvaluableDeclaredRankable:
    """4 global members, 1 in this arm's ranking — declared headline-rankable.

    Global coverage 4/6 = 0.67 genuinely PASSES the global bar. The arm ranked ONE member.
    An enrichment on one gene is well defined and is not a statement about a pathway.
    """

    def _mutate(self, doc):
        r = doc["records"][0]
        r["n_source_symbols"] = 6
        r["n_genes_in_target_universe"] = 4
        r["target_source_coverage"] = round(4 / 6, 6)
        r["global_coverage_disposition"] = "rankable"
        r["global_coverage_policy_passed"] = True
        e = r["enrichment"]["away_from_A"]
        e["n_hits_in_ranking"] = 1
        e["enrichment_value"] = 1.0
        e["arm_evaluable_source_coverage"] = round(1 / 6, 6)
        e["global_target_source_coverage"] = round(4 / 6, 6)
        e["arm_headline_rankable"] = True                 # the lie
        e["arm_coverage_disposition"] = "rankable"        # the lie

    def test_it_is_REJECTED(self, artifact):
        out, prov = artifact
        r = reseal_and_verify(out, prov, self._mutate)
        assert r["verdict"] == verify_pathway.REJECT
        assert COVERAGE_CHECK in failed(r)

    def test_the_refusal_names_the_thin_arm(self, artifact):
        out, prov = artifact
        r = reseal_and_verify(out, prov, self._mutate)
        detail = [c["detail"] for c in r["checks"] if c["check"] == COVERAGE_CHECK][0]
        assert "arm_headline_rankable" in detail or "arm disposition" in detail


class TestMutation3_NullOrUnknownCoverageDeclaredRankable:
    def _mutate(self, doc):
        r = doc["records"][0]
        r["n_source_symbols"] = None
        r["target_source_coverage"] = None
        r["global_coverage_disposition"] = "rankable"     # the lie
        r["global_coverage_policy_passed"] = True         # the lie
        for e in r["enrichment"].values():
            e["global_target_source_coverage"] = None
            e["arm_evaluable_source_coverage"] = None
            e["arm_headline_rankable"] = True
            e["arm_coverage_disposition"] = "rankable"

    def test_UNKNOWN_coverage_declared_rankable_is_REJECTED(self, artifact):
        out, prov = artifact
        r = reseal_and_verify(out, prov, self._mutate)
        assert r["verdict"] == verify_pathway.REJECT
        assert COVERAGE_CHECK in failed(r)


def rewrite_record_honestly(doc, *, n_src, n_tgt, hits):
    """Rewrite record 0 so EVERY derived field re-derives — the frozen rule, applied.

    A mutation that only rewrites the arm under attack leaves the OTHER arm's arithmetic
    dangling against the new n_source_symbols, and the verifier refuses it for that instead.
    Which is correct of the verifier — but it would let a bad inclusive-boundary test pass
    for the wrong reason. So the boundary case is honest everywhere except the boundary.
    """
    r = doc["records"][0]
    r["n_source_symbols"] = n_src
    r["n_genes_in_target_universe"] = n_tgt
    cov = round(n_tgt / n_src, 6)
    passed = cov >= 0.50
    r["target_source_coverage"] = cov
    r["global_coverage_disposition"] = "rankable" if passed else "descriptive_only"
    r["global_coverage_policy_passed"] = passed
    for arm, e in r["enrichment"].items():
        n_hits = hits[arm]
        e["n_hits_in_ranking"] = n_hits
        e["enrichment_value"] = 0.5
        e["arm_evaluable_source_coverage"] = round(n_hits / n_src, 6)
        e["global_target_source_coverage"] = cov
        rankable = passed and n_hits >= 3
        e["arm_headline_rankable"] = rankable
        e["arm_coverage_disposition"] = "rankable" if rankable else (
            "descriptive_only_thin_arm" if passed else "descriptive_only")
    return r


class TestMutation4_TheThresholdIsINCLUSIVE:
    """EXACTLY three arm-evaluable members IS rankable. The boundary is part of the rule."""

    def test_a_SELF_CONSISTENT_rewrite_of_the_counts_is_now_REJECTED(self, artifact):
        """A4: internal consistency is no longer enough, and this test used to say it was.

        It rewrote record 0's counts to n_src=4 / n_tgt=4 / 3 hits per arm, recomputed every
        ratio and disposition from them, and asserted ADMIT — because the A3 verifier
        re-derived the coverage arithmetic FROM THE RECORD, so a forgery that agreed with
        itself agreed with the verifier too. That is exactly the hole an audit walked through
        to make a zero-coverage pathway headline-rankable.

        The counts are now RECOUNTED from the pinned gene-set bundle, the bound target
        universe and each arm's ranking. The record's own arithmetic still checks out — and
        the artifact is refused anyway, because those are not the counts.
        """
        out, prov = artifact
        r = reseal_and_verify(out, prov, lambda d: rewrite_record_honestly(
            d, n_src=4, n_tgt=4, hits={"away_from_A": 3, "toward_B": 3}))
        assert COVERAGE_CHECK not in failed(r)          # self-consistent, as before
        assert r["verdict"] == verify_pathway.REJECT    # and false, which is what matters
        assert {"n_source_genes_rederives_from_the_pinned_gene_set_bundle",
                "target_intersection_count_mismatch"} & failed(r)

    def test_exactly_three_ranked_members_IS_rankable_on_a_REAL_record(self, artifact):
        # The inclusive boundary, demonstrated on a record that GENUINELY has 3 of its 5
        # source genes in the ranking — not on one that was rewritten to claim it does.
        out, prov = artifact
        r = verify_pathway.verify(out_dir=out, provenance=prov)
        assert r["verdict"] == verify_pathway.ADMIT
        truth = r["reconstruction"]["rederived"]["FX:CONVERGENT"]
        assert truth["n_source_symbols"] == 5
        assert truth["n_genes_in_target_universe"] == 3
        assert truth["enrichment"]["away_from_A"]["n_hits_in_ranking"] == 3
        assert truth["enrichment"]["away_from_A"]["arm_headline_rankable"] is True

    def test_two_declared_rankable_is_REJECTED(self, artifact):
        out, prov = artifact

        def mutate(doc):
            rec = rewrite_record_honestly(
                doc, n_src=4, n_tgt=4, hits={"away_from_A": 2, "toward_B": 3})
            e = rec["enrichment"]["away_from_A"]
            e["arm_headline_rankable"] = True             # one below the bar — the lie
            e["arm_coverage_disposition"] = "rankable"

        r = reseal_and_verify(out, prov, mutate)
        assert r["verdict"] == verify_pathway.REJECT
        assert COVERAGE_CHECK in failed(r)

    def test_the_arms_are_judged_INDEPENDENTLY_at_the_boundary(self, artifact):
        # A thin arm does not drag down a thick one, and a thick one does not carry a thin
        # one. Two arms, two verdicts, from one record.
        out, prov = artifact
        r = reseal_and_verify(out, prov, lambda d: rewrite_record_honestly(
            d, n_src=4, n_tgt=4, hits={"away_from_A": 3, "toward_B": 2}))
        assert COVERAGE_CHECK not in failed(r)
        with open(os.path.join(out, "pathway.json")) as fh:
            arms = json.load(fh)["records"][0]["enrichment"]
        assert arms["away_from_A"]["arm_headline_rankable"] is True
        assert arms["toward_B"]["arm_headline_rankable"] is False

    def test_the_verifiers_own_threshold_is_three_and_inclusive(self):
        assert verify_pathway.SPEC_MIN_ARM_RANKED_MEMBERS == 3
        _, rank = verify_pathway._arm_disposition(True, 3, 0.5)
        assert rank is True
        _, rank = verify_pathway._arm_disposition(True, 2, 0.5)
        assert rank is False


class TestALoosenedThresholdIsRefused:
    """The verifier holds its OWN policy so it can disagree with the generator."""

    def test_an_artifact_declaring_a_LOOSER_threshold_is_REJECTED(self, artifact):
        out, prov = artifact

        def mutate(doc):
            doc["method"]["min_arm_ranked_members"] = 1      # loosened after the fact
            doc["method"]["min_source_coverage"] = 0.01

        r = reseal_and_verify(out, prov, mutate)
        assert r["verdict"] == verify_pathway.REJECT
        assert POLICY_CHECK in failed(r)

    def test_the_verifier_does_NOT_import_the_generators_thresholds(self):
        # It reimplements them. A verifier that read the generator's constants would
        # ratify a loosened one by construction.
        import inspect
        src = inspect.getsource(verify_pathway)
        assert "SPEC_MIN_SOURCE_COVERAGE = 0.50" in src
        assert "from . import genesets" not in src
        assert "import genesets" not in src

    def test_it_agrees_with_the_generator_on_the_frozen_values(self):
        # Two implementations, same rule. If they ever diverge, THAT is the finding.
        assert verify_pathway.SPEC_MIN_SOURCE_COVERAGE == genesets.MIN_SOURCE_COVERAGE
        assert verify_pathway.SPEC_MIN_ARM_RANKED_MEMBERS == \
            genesets.MIN_ARM_RANKED_MEMBERS
        assert verify_pathway.SPEC_COVERAGE_POLICY_ID == genesets.COVERAGE_POLICY_ID


class TestTheCleanArtifactStillAdmits:
    def test_it_admits(self, artifact):
        out, prov = artifact
        r = verify_pathway.verify(out_dir=out, provenance=prov)
        assert r["verdict"] == verify_pathway.ADMIT
        assert r["n_failed"] == 0

    def test_the_coverage_checks_actually_ran(self, artifact):
        out, prov = artifact
        names = {c["check"] for c in
                 verify_pathway.verify(out_dir=out, provenance=prov)["checks"]}
        assert COVERAGE_CHECK in names
        assert POLICY_CHECK in names
