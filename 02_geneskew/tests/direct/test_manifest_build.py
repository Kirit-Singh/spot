"""B5 — the contributor manifest is BUILT from the pinned source, and covers every scope.

The stale manifest labelled 6 of the 33,983 released pooled-main scopes ``ambiguous``
(ENSG00000137265 and ENSG00000196535, at each of the three conditions) when the source in
fact keeps targeting guides for all six. Both genes carry TWO symbol aliases in the guide
library — IRF4/MUM1 and MYO18A/TIAF1 — so a generator resolving contributors by SYMBOL saw
two guide families for one scope and called it ambiguous. Resolved by the thing the
release actually keys on, ``(perturbed_gene_id, culture_condition)``, there is no
ambiguity: the contributors are every kept TARGETING guide for that scope.

The synthetic tests here run against a fixture source with the SAME alias shape, so the
rule is exercised without the 44 GB object. The release-scale assertion (33,983 / 0) runs
only against the real pinned source, opt-in.
"""
from __future__ import annotations

import json
import os

import pytest
from direct import manifest_build, manifest_schema

# The two real alias-collision genes, and the shape that fooled the old generator.
ALIASED = ("ENSG00000137265", "ENSG00000196535")


class TestTheAliasCollisionResolves:
    """A gene whose guides arrive under TWO symbol families has ONE contributor set."""

    def test_two_guide_families_for_one_ensembl_target_is_not_an_ambiguity(
            self, tmp_path):
        from direct import replay
        from fixtures_evidence import write_source_file
        from fixtures_spec import CONDITION, TargetSpec

        # IRF4/MUM1 in miniature: four guides, two symbol families, ONE target id.
        spec = TargetSpec(ALIASED[0], ["IRF4-1", "IRF4-2", "MUM1-1", "MUM1-2"], 4.0,
                          a_effect=-1.0)
        path, _sha, _proof = write_source_file(str(tmp_path), [spec])
        provable = replay.source_provable_guides(replay.read_evidence(path))

        kept = provable.get((ALIASED[0], CONDITION))
        assert kept == {"IRF4-1", "IRF4-2", "MUM1-1", "MUM1-2"}
        # ...and that is a DETERMINED scope: the source keeps targeting guides for it
        assert len(kept) >= 1

    def test_a_scope_the_source_keeps_no_targeting_guide_for_is_genuinely_ambiguous(
            self, tmp_path):
        from direct import replay
        from fixtures_evidence import write_source_file
        from fixtures_spec import CONDITION, TargetSpec

        # no library guides -> the source holds no contributor rows for it at all
        spec = TargetSpec("ENSG00000000999", [], 2.0, a_effect=-1.0)
        path, _sha, _proof = write_source_file(str(tmp_path), [spec])
        provable = replay.source_provable_guides(replay.read_evidence(path))
        assert provable.get(("ENSG00000000999", CONDITION)) is None


class TestTheBuilderDeclaresItsRule:
    def test_it_resolves_by_the_released_target_id_not_by_guide_name(self):
        rule = manifest_build.RESOLUTION_RULE
        assert "targeting" in rule and "keep_for_DE" in rule
        assert "never by guide NAME" in rule or "never by guide name" in rule.lower()

    def test_the_rule_names_the_two_alias_genes_that_broke_the_old_generator(self):
        assert "IRF4/MUM1" in manifest_build.RESOLUTION_RULE
        assert "MYO18A/TIAF1" in manifest_build.RESOLUTION_RULE

    def test_a_scope_with_no_kept_targeting_guide_is_still_emitted_as_ambiguous(self):
        # The honest branch survives, for a future release that genuinely has one. It is
        # empty for the pinned release, and it is never a licence to guess.
        import inspect
        src = inspect.getsource(manifest_build._rows_and_records)
        assert manifest_schema.AMBIGUOUS in src or "AMBIGUOUS" in src
        assert "guide_id=None" in src


# --------------------------------------------------------------------------- #
# The release-scale assertion. Opt-in: it reads the pinned 44 GB pseudobulk obs.
# --------------------------------------------------------------------------- #
REAL = os.environ.get("SPOT_STAGE2_RELEASE_TESTS") == "1"
BUILT = "/home/tcelab/.spot-runs/20260712T021343Z/direct-pooled-main-p0/rebuilt-w18"
FRESH = os.path.join(BUILT, manifest_build.MANIFEST_NAME)
REPLAY = os.path.join(BUILT, manifest_build.REPLAY_REPORT_NAME)


@pytest.mark.skipif(not os.path.exists(FRESH),
                    reason="the freshly built release manifest is not present")
class TestTheFreshlyBuiltReleaseManifest:
    """Asserted against the artifact the builder actually wrote from the pinned source."""

    @pytest.fixture(scope="class")
    def built(self):
        with open(FRESH) as fh:
            return json.load(fh)

    @pytest.fixture(scope="class")
    def replay_report(self):
        with open(REPLAY) as fh:
            return json.load(fh)

    def test_every_released_scope_is_determined_and_none_is_ambiguous(self, built):
        c = built["counts"]
        assert c["n_released_pooled_main_scopes"] == 33983
        assert c["n_scopes_determined"] == 33983
        assert c["n_scopes_ambiguous"] == 0

    def test_the_six_scopes_the_stale_manifest_called_ambiguous_are_determined(
            self, built):
        rows = {(r["target_id"], r["condition"]): r for r in built["rows"]}
        for target in ALIASED:
            for condition in ("Rest", "Stim8hr", "Stim48hr"):
                row = rows[(target, condition)]
                assert row["evidence_state"] == manifest_schema.DETERMINED
                assert row["guide_id"]
                assert row["source_record_id"]

    def test_strict_replay_confirms_it_against_the_raw_source(self, replay_report):
        r = replay_report
        assert r["verdict"] == "replayed"
        assert r["completeness_verdict"] == "complete"
        assert r["n_failed"] == 0
        # the two failure classes the classifier separates: neither occurs
        assert r["n_scopes_downgraded"] == 0      # evidence the source holds, deleted
        assert r["n_scopes_overclaimed"] == 0     # evidence the source lacks, invented
        assert r["n_records_offset_proven"] == r["n_records"]

    def test_no_non_targeting_guide_was_ever_cited_as_a_contributor(self,
                                                                    replay_report):
        assert replay_report["n_nontargeting_guides_cited"] == 0

    def test_it_pins_the_exact_sources_it_was_built_from(self, built):
        names = {s["name"] for s in built["sources"]}
        assert manifest_build.PB_SOURCE_NAME in names
        assert manifest_build.DE_SOURCE_NAME in names
        for s in built["sources"]:
            assert len(s["sha256"]) == 64


@pytest.mark.skipif(not REAL, reason="opt-in: reads the pinned release source")
def test_the_builder_reproduces_the_manifest_from_the_pinned_source(tmp_path):
    """The whole point: run it again, get the same evidence."""
    result = manifest_build.build(
        de_main="/home/tcelab/datasets/marson2025_gwcd4_perturbseq/GWCD4i.DE_stats.h5ad",
        pseudobulk=("/home/tcelab/datasets/marson2025_gwcd4_perturbseq/"
                    "GWCD4i.pseudobulk_merged.h5ad"),
        out_dir=str(tmp_path))
    assert result["n_scopes_determined"] == 33983
    assert result["n_scopes_ambiguous"] == 0
    assert result["replay_verdict"] == "replayed"
    assert result["replay_completeness_verdict"] == "complete"
    assert result["replay_n_scopes_downgraded"] == 0
    assert result["replay_n_scopes_overclaimed"] == 0
