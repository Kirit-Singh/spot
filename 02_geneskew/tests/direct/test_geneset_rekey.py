"""The symbol -> Ensembl re-keying: the last thing between Direct+temporal and pathways.

The pinned Reactome + GO-BP cache is SYMBOL-keyed; the Stage-2 effect universe is
ENSEMBL-keyed; ``genesets.load`` refuses the mismatch rather than joining at a loss. These
tests cover the crosswalk (built from the release's OWN ``var/gene_name`` -> ``gene_ids``),
the re-keying, the loss accounting, and the pathway lane running end to end on the result.

The fixture uses the SAME builder the real cache is built with — so what is exercised here
is the code that produced the shipped artifact, not a lookalike.
"""
from __future__ import annotations

import json
import os

import pytest
from direct import crosswalk, geneset_build, genesets, run_pathway, verify_pathway
from fixtures_spec import OFF_READOUT_TARGET, TARGET_GENES, UNIVERSE, gene_symbol

# The fixture DE object writes var/gene_ids = UNIVERSE (Ensembl) and var/gene_name = the
# same strings, so a fixture crosswalk is the identity. To exercise the REAL shape — sets
# named by SYMBOL, mapped through the crosswalk — the fixture GMT names genes by the
# symbols the crosswalk publishes.


def _symbols_for(ens: list[str]) -> list[str]:
    """The SYMBOLS a GMT would name these genes by — a real GMT never names Ensembl ids."""
    return [gene_symbol(e) for e in ens]


def write_gmt(path: str, sets, id_col: int) -> str:
    with open(path, "w") as fh:
        for set_id, name, genes in sets:
            cols = ([name, set_id] if id_col == 1 else [set_id, name]) + list(genes)
            fh.write("\t".join(cols) + "\n")
    return path


class TestTheCrosswalkComesFromTheReleaseItself:
    def test_it_is_built_from_var_gene_name_to_var_gene_ids(self, synthetic_run):
        args = synthetic_run()
        xw = crosswalk.build(args.de_main)
        assert xw["primary_source"].startswith("GWCD4i.DE_stats.h5ad:var")
        assert len(xw["primary_source_sha256"]) == 64
        assert xw["n_rows"] == len(UNIVERSE)
        assert xw["n_universe_genes"] == len(UNIVERSE)

    def test_every_mapped_id_is_in_the_effect_universe(self, synthetic_run):
        args = synthetic_run()
        xw = crosswalk.build(args.de_main)
        assert set(xw["mapping"].values()) <= set(UNIVERSE)

    def test_it_records_the_source_sha_so_the_crosswalk_can_be_re_derived(
            self, synthetic_run):
        from direct.hashing import file_sha256
        args = synthetic_run()
        xw = crosswalk.build(args.de_main)
        assert xw["primary_source_sha256"] == file_sha256(args.de_main)
        assert len(xw["canonical_sha256"]) == 64

    def test_an_object_with_no_gene_name_column_is_REFUSED_not_guessed(self, tmp_path):
        import h5py
        import numpy as np
        p = os.path.join(str(tmp_path), "no_names.h5ad")
        with h5py.File(p, "w") as fh:
            var = fh.create_group("var")
            var.create_dataset("gene_ids", data=np.array(UNIVERSE, dtype="S64"))
        with pytest.raises(crosswalk.CrosswalkError, match="gene_name"):
            crosswalk.build(p)


class TestAmbiguityIsFailClosed:
    """A symbol naming two genes is UNRESOLVED. There is no 'pick the first'."""

    def test_an_ambiguous_symbol_is_dropped_with_a_named_reason(self):
        xw = {"mapping": {"GOOD": "ENSG1"},
              "ambiguous_symbols": {"DOUBLE": ["ENSG2", "ENSG3"]}}
        m = crosswalk.map_symbols(xw, ["GOOD", "DOUBLE"])
        assert m["ensembl"] == ["ENSG1"]
        assert m["n_dropped"] == 1
        assert m["dropped"][0] == {"symbol": "DOUBLE",
                                   "reason": crosswalk.DROP_AMBIGUOUS}

    def test_it_is_never_silently_resolved_to_one_of_them(self):
        xw = {"mapping": {}, "ambiguous_symbols": {"DOUBLE": ["ENSG2", "ENSG3"]}}
        m = crosswalk.map_symbols(xw, ["DOUBLE"])
        assert m["ensembl"] == []          # NOT ["ENSG2"]

    def test_an_unmappable_symbol_says_it_was_not_in_the_universe(self):
        xw = {"mapping": {"GOOD": "ENSG1"}, "ambiguous_symbols": {}}
        m = crosswalk.map_symbols(xw, ["GOOD", "NEVER_MEASURED"])
        assert m["dropped"] == [{"symbol": "NEVER_MEASURED",
                                 "reason": crosswalk.DROP_NOT_IN_UNIVERSE}]

    def test_two_symbols_resolving_to_ONE_gene_are_de_duplicated(self):
        # a set naming a gene by both its primary symbol and an alias
        xw = {"mapping": {"PRIMARY": "ENSG1", "ALIAS": "ENSG1"},
              "ambiguous_symbols": {}}
        m = crosswalk.map_symbols(xw, ["PRIMARY", "ALIAS"])
        assert m["ensembl"] == ["ENSG1"]   # a gene counted twice would be double-counted
        assert m["n_mapped"] == 1


class TestTheAliasResolverIsSubordinate:
    def test_it_never_overrides_the_primary(self, synthetic_run, tmp_path):
        args = synthetic_run()
        primary = crosswalk.build(args.de_main)
        with_alias = crosswalk.build(args.de_main, args.sgrna)
        for sym, ens in primary["mapping"].items():
            assert with_alias["mapping"][sym] == ens

    def test_it_can_only_re_attach_a_MEASURED_gene_never_add_one(self, synthetic_run):
        args = synthetic_run()
        xw = crosswalk.build(args.de_main, args.sgrna)
        assert set(xw["mapping"].values()) <= set(UNIVERSE)
        assert set(xw["alias_symbols_recovered"].values()) <= set(UNIVERSE)

    def test_every_recovery_is_recorded_by_name(self, synthetic_run):
        args = synthetic_run()
        xw = crosswalk.build(args.de_main, args.sgrna)
        assert xw["n_alias_rows"] == len(xw["alias_symbols_recovered"])
        assert xw["n_rows"] == xw["n_primary_rows"] + xw["n_alias_rows"]


def specs_with_off_readout_target():
    """The default specs PLUS a target that was perturbed and never measured (B1).

    It is an obs row with no var column — precisely the shape of the 2,029 real targets
    that the retired single-universe rule made ineligible for pathway membership.
    """
    from fixtures_direct import default_specs
    from fixtures_spec import TargetSpec
    return default_specs() + [
        TargetSpec(OFF_READOUT_TARGET, ["g-OR-1", "g-OR-2"], 2.0,
                   a_effect=-11.0,          # ranks near the TOP of away_from_A
                   b_effect=1.0,
                   guide_slot_effects={"guide_1": -11.0, "guide_2": -11.0},
                   manifest_slots={"guide_1": "g-OR-1", "guide_2": "g-OR-2"})]


@pytest.fixture
def rekeyed(synthetic_run, tmp_path):
    """A fixture cache, re-keyed by the REAL builder, bound to BOTH fixture universes."""
    from direct import io_data
    from direct import universe as uni

    args = synthetic_run(specs_with_off_readout_target())
    gu = uni.primary_universe(io_data.load_main_gene_ids(args.de_main))

    d = str(tmp_path)
    t = list(TARGET_GENES)
    filler = [g for g in UNIVERSE if g not in t]
    # a set whose members are ALL measurable, and one with members that are NOT
    sets = [
        ("R-HSA-CONV", "convergent pathway", _symbols_for(t[0:3] + filler[0:2])),
        ("R-HSA-DIVE", "divergent pathway", _symbols_for(t[4:7] + filler[6:8])),
        ("R-HSA-LOSSY", "half of it was never measured",
         _symbols_for(t[9:12]) + ["NOT_MEASURED_1", "NOT_MEASURED_2", "NOT_MEASURED_3"]),
        ("R-HSA-GONE", "none of it was measured",
         ["NEVER_1", "NEVER_2", "NEVER_3", "NEVER_4"]),
        # B1 — THE BUG, IN A SET. Its members were PERTURBED but never MEASURED: they are
        # obs rows and not var columns, exactly like the 2,029 real ones. Under the retired
        # single-universe rule NONE of them could be a member of any pathway.
        ("R-HSA-OFFREADOUT", "perturbed but never measured",
         _symbols_for([OFF_READOUT_TARGET] + t[0:2])),
    ]
    gmt = write_gmt(os.path.join(d, "reactome_human.canonical.gmt"), sets, id_col=1)
    from direct import run_screen as rs
    ctx = rs.prepare(args)
    tu = uni.target_universe(ctx["identities_by_condition"])

    out = geneset_build.build(
        source="reactome", gmt=gmt,
        release={"release_id": "V97", "license": "CC0-1.0",
                 "license_reference": "https://reactome.org/license"},
        de_main=args.de_main, out_dir=d, sgrna=args.sgrna,
        effect_universe_sha256=gu["sha256"], target_universe_sha256=tu["sha256"])
    args.gene_sets = out["path"]
    return args, out, gu, tu


class TestTheRekeyedBundleIsAdmitted:
    def test_genesets_load_ADMITS_it_against_BOTH_universes(self, rekeyed):
        _, out, gu, tu = rekeyed
        b = genesets.load(out["path"], gu["gene_ids"], gu["sha256"],
                          tu["target_ids"], tu["sha256"])
        assert b["gene_id_namespace"] == genesets.ENSEMBL_GENE_ID
        assert b["single_universe_binding"] is False
        assert len(b["sets"]) == 5

    def test_a_SYMBOL_keyed_bundle_is_still_REFUSED(self, rekeyed, tmp_path):
        _, _, gu, tu = rekeyed
        doc = {"schema_version": genesets.SCHEMA_VERSION,
               "release": {"source": "reactome", "release_id": "V97",
                           "license": "CC0-1.0",
                           "license_reference": "https://reactome.org/license"},
               "gene_id_namespace": "gene_symbol",
               "sets": [{"set_id": "S", "name": "s", "genes": ["IL6"]}]}
        p = os.path.join(str(tmp_path), "sym.json")
        with open(p, "w") as fh:
            json.dump(doc, fh)
        with pytest.raises(genesets.GeneSetError, match="gene_id_namespace"):
            genesets.load(p, gu["gene_ids"], gu["sha256"])

    def test_the_licence_is_carried_through_unchanged(self, rekeyed):
        # m3 must not regress: a re-keying does not change who licensed the sets.
        _, out, gu, tu = rekeyed
        b = genesets.load(out["path"], gu["gene_ids"], gu["sha256"],
                          tu["target_ids"], tu["sha256"])
        assert b["gene_set_license"] == "CC0-1.0"
        assert b["gene_set_license_reference"] == "https://reactome.org/license"

    def test_it_is_content_addressed_on_BOTH_memberships(self, rekeyed):
        _, out, _, _ = rekeyed
        assert len(out["canonical_sha256"]) == 64
        assert len(out["sha256"]) == 64


class TestB1_TheTargetUniverseIsWhatEnrichmentRanks:
    """THE SCIENTIFIC BUG. Gene-set membership was tested in the READOUT universe, but the
    arms rank PERTURBED TARGETS. 2,029 real targets are perturbed and never measured — they
    could top an arm's ranking and never count as a member of any pathway."""

    def test_the_two_universes_are_DIFFERENT_populations(self, rekeyed):
        _, _, gu, tu = rekeyed
        assert OFF_READOUT_TARGET in tu["target_ids"]         # it WAS perturbed
        assert OFF_READOUT_TARGET not in gu["gene_ids"]       # it was NEVER measured

    def test_a_perturbed_but_unmeasured_target_IS_a_pathway_member(self, rekeyed):
        _, out, gu, tu = rekeyed
        b = genesets.load(out["path"], gu["gene_ids"], gu["sha256"],
                          tu["target_ids"], tu["sha256"])
        s = b["sets"]["R-HSA-OFFREADOUT"]
        # THE FIX: it is a member in the space the arms actually rank
        assert OFF_READOUT_TARGET in s["genes_in_target_universe"]
        # ...and it is correctly absent from the space signature vectors live in
        assert OFF_READOUT_TARGET not in s["genes_in_universe"]

    def test_the_retired_readout_only_rule_would_have_EXCLUDED_it(self, rekeyed):
        # the counterfactual, asserted: bind ONLY the readout universe and it vanishes
        _, out, gu, _ = rekeyed
        readout_only = genesets.load(out["path"], gu["gene_ids"], gu["sha256"])
        assert readout_only["single_universe_binding"] is True
        s = readout_only["sets"]["R-HSA-OFFREADOUT"]
        assert OFF_READOUT_TARGET not in s["genes_in_target_universe"]

    def test_it_is_ELIGIBLE_FOR_RANKED_ARM_ENRICHMENT(self, rekeyed):
        """The regression the review asked for, end to end."""
        from direct import config, enrichment
        from direct import run_screen as rs
        args, out, gu, tu = rekeyed
        b = genesets.load(out["path"], gu["gene_ids"], gu["sha256"],
                          tu["target_ids"], tu["sha256"])
        ctx = rs.prepare(args)
        built = rs.condition_rows(ctx=ctx, args=args, cond=ctx["cond"],
                                  identity_hashes=rs.identity_hashes_of(
                                      rs.stage2_input_manifest(args)))
        rows = built["screen"]

        arm = config.ARM_A
        ranked = enrichment.rank_targets(rows, arm)
        assert OFF_READOUT_TARGET in [t for t, _v in ranked]      # it IS ranked
        # ...and it registers as a HIT for its pathway, in that arm's leading edge
        res = {e["set_id"]: e for e in enrichment.enrich_arm(rows, b, arm)}
        e = res["R-HSA-OFFREADOUT"]
        assert e["n_hits_in_ranking"] >= 1
        assert OFF_READOUT_TARGET in e["leading_edge"]

    def test_convergence_membership_is_also_the_target_space(self, rekeyed):
        # a signature exists only for a gene that was PERTURBED
        _, out, gu, tu = rekeyed
        b = genesets.load(out["path"], gu["gene_ids"], gu["sha256"],
                          tu["target_ids"], tu["sha256"])
        assert OFF_READOUT_TARGET in b["sets"]["R-HSA-OFFREADOUT"]["genes_target"]

    def test_the_signature_VECTOR_space_is_still_the_readout_universe(self, rekeyed):
        # convergence still compares signatures over READOUT genes: the cosine is taken in
        # the measured space, and a perturbed-but-unmeasured gene has no column there.
        from direct import run_screen as rs
        args, _, gu, _ = rekeyed
        ctx = rs.prepare(args)
        built = rs.condition_rows(
            ctx=ctx, args=args, cond=ctx["cond"],
            identity_hashes=rs.identity_hashes_of(rs.stage2_input_manifest(args)),
            signature_targets={OFF_READOUT_TARGET})
        sig = built["signatures"][OFF_READOUT_TARGET]
        assert set(sig) <= set(gu["gene_ids"])       # vectors live in the READOUT space

    def test_BOTH_universes_are_bound_into_the_pathway_method_hash(self):
        from direct import pathway
        m = pathway.method_block(None)
        assert m["enrichment_membership_universe"] == "perturbation_target"
        assert m["convergence_membership_universe"] == "perturbation_target"
        assert m["convergence_signature_vector_space"] == "de_readout"
        assert m["two_universes_are_bound_separately"] is True


class TestB4_CoverageIsGOVERNED_notMerelyDisclosed:
    """Size is not coverage. A pathway retaining 0.25% of its genes must not rank."""

    def test_the_policy_is_prospective_and_named(self):
        assert genesets.COVERAGE_POLICY_ID.endswith("prospective.v1")
        assert genesets.MIN_SOURCE_COVERAGE == 0.50
        assert genesets.COVERAGE_NAMESPACE == "perturbation_target"

    def test_a_well_covered_pathway_is_RANKABLE(self):
        d = genesets.coverage_disposition(0.9)
        assert d["coverage_disposition"] == genesets.DISPOSITION_RANKABLE
        assert d["headline_rankable"] is True

    def test_a_low_coverage_pathway_is_DESCRIPTIVE_ONLY(self):
        d = genesets.coverage_disposition(0.0025)      # the reviewer's 0.25% case
        assert d["coverage_disposition"] == genesets.DISPOSITION_DESCRIPTIVE_ONLY
        assert d["headline_rankable"] is False

    def test_exactly_at_the_threshold_is_rankable(self):
        assert genesets.coverage_disposition(0.50)["headline_rankable"] is True

    def test_UNKNOWN_coverage_is_descriptive_only_never_rankable(self):
        # a bundle that will not say how much of a pathway it kept has not earned a rank
        d = genesets.coverage_disposition(None)
        assert d["coverage_disposition"] == genesets.DISPOSITION_UNKNOWN_COVERAGE
        assert d["headline_rankable"] is False

    def test_a_descriptive_only_set_is_STILL_COMPUTED_and_EMITTED(self, rekeyed):
        # it is not deleted: a pathway missing from the table is indistinguishable from
        # one that was tested and found nothing.
        args, _, _, _ = rekeyed
        res = run_pathway.build_pathway(args)
        with open(os.path.join(res["out_dir"], "pathway.json")) as fh:
            doc = json.load(fh)
        low = [r for r in doc["records"] if not r["headline_rankable"]]
        assert low, "the fixture must exercise the descriptive-only branch"
        for r in low:
            assert r["coverage_disposition"].startswith("descriptive_only")
            assert "enrichment" in r and "convergence" in r     # still computed

    def test_the_disposition_reaches_the_enrichment_block(self, rekeyed):
        args, _, _, _ = rekeyed
        res = run_pathway.build_pathway(args)
        with open(os.path.join(res["out_dir"], "pathway.json")) as fh:
            doc = json.load(fh)
        for r in doc["records"]:
            for arm_block in r["enrichment"].values():
                assert arm_block["headline_rankable"] == r["headline_rankable"]

    def test_the_policy_is_bound_into_the_method_hash(self):
        from direct import pathway
        m = pathway.method_block(None)
        assert m["coverage_policy_id"] == genesets.COVERAGE_POLICY_ID
        assert m["min_source_coverage"] == genesets.MIN_SOURCE_COVERAGE


class TestTheLossIsRecordedNeverHidden:
    def test_a_partly_unmeasured_set_reports_its_real_coverage(self, rekeyed):
        _, out, gu, tu = rekeyed
        b = genesets.load(out["path"], gu["gene_ids"], gu["sha256"],
                          tu["target_ids"], tu["sha256"])
        s = b["sets"]["R-HSA-LOSSY"]
        assert s["n_source_symbols"] == 6
        # 3 of the 6 named genes were perturbed; the other 3 name nothing in this release
        assert s["target_source_coverage"] == pytest.approx(0.5)

    def test_a_set_with_ZERO_members_is_EMITTED_not_deleted(self, rekeyed):
        _, out, gu, tu = rekeyed
        b = genesets.load(out["path"], gu["gene_ids"], gu["sha256"],
                          tu["target_ids"], tu["sha256"])
        s = b["sets"]["R-HSA-GONE"]
        assert s["n_genes_target"] == 0
        assert s["n_source_symbols"] == 4
        assert s["target_source_coverage"] == 0.0
        assert s["headline_rankable"] is False

    def test_an_empty_set_that_EXPLAINS_NOTHING_is_still_refused(self, tmp_path):
        doc = {"schema_version": genesets.SCHEMA_VERSION,
               "release": {"source": "reactome", "release_id": "V97",
                           "license": "CC0-1.0",
                           "license_reference": "https://reactome.org/license"},
               "gene_id_namespace": "ensembl_gene_id",
               "sets": [{"set_id": "S", "name": "s", "genes": []}]}
        p = os.path.join(str(tmp_path), "b.json")
        with open(p, "w") as fh:
            json.dump(doc, fh)
        with pytest.raises(genesets.GeneSetError, match="names no genes"):
            genesets.load(p, UNIVERSE)

    def test_the_builder_reports_the_loss_PER_NAMESPACE(self, rekeyed):
        _, out, _, _ = rekeyed
        loss = out["mapping_loss"]
        assert set(loss) == {"perturbation_target", "de_readout"}
        for ns in loss.values():
            assert ns["n_sets"] == 5
            assert 0 <= ns["total_loss_fraction"] <= 1


class TestThePathwayLaneRunsOnTheRekeyedSets:
    """The whole point: enrichment + convergence, end to end, on masked signatures."""

    def test_it_produces_a_content_addressed_artifact_its_verifier_ADMITS(self,
                                                                          rekeyed):
        args, _, _, _ = rekeyed
        res = run_pathway.build_pathway(args)
        assert res["verification"]["verdict"] == verify_pathway.ADMIT
        assert res["verification"]["n_failed"] == 0
        assert len(res["records_sha256"]) == 64
        assert res["n_records"] == 5

    def test_BOTH_universes_are_bound_into_the_run_identity(self, rekeyed):
        args, _, gu, tu = rekeyed
        res = run_pathway.build_pathway(args)
        with open(os.path.join(res["out_dir"], "pathway_provenance.json")) as fh:
            b = json.load(fh)["run_binding"]
        assert b["gene_universe_sha256"] == gu["sha256"]
        assert b["target_universe_sha256"] == tu["sha256"]
        assert b["gene_universe_sha256"] != b["target_universe_sha256"]

    def test_NO_p_q_or_FDR_anywhere_in_the_artifact(self, rekeyed):
        from direct.temporal import admission
        args, _, _, _ = rekeyed
        res = run_pathway.build_pathway(args)
        for name in ("pathway.json", "pathway_provenance.json"):
            with open(os.path.join(res["out_dir"], name)) as fh:
                assert admission.forbidden_keys(json.load(fh)) == []


class TestB1_BOTH_UNIVERSES_ARE_IN_THE_METHOD_HASH:
    """The round-3 commit CLAIMED both universe ids were bound into the pathway METHOD
    hash. Only the READOUT id was: `binding_block` never carried
    `target_universe_sha256`, so two bundles differing ONLY in which population was
    PERTURBED produced an IDENTICAL method hash.

    The target universe is the space enrichment tests membership in. Two runs that differ
    in it are running a different method, not merely a different input — so the claim had
    to become true, not be withdrawn.
    """

    def _bundle(self, target_sha):
        return {
            "schema_version": genesets.SCHEMA_VERSION,
            "gene_set_release": {"source": "reactome", "release_id": "V97"},
            "gene_set_license": "CC0-1.0", "gene_set_license_reference": "x",
            "gene_id_namespace": "ensembl_gene_id",
            "effect_universe_sha256": "r" * 64,
            "target_universe_sha256": target_sha,
            "single_universe_binding": False,
            "min_set_size": 3, "max_set_size": 500,
            "canonical_sha256": "c" * 64, "sets": {},
        }

    def test_the_binding_block_carries_BOTH_universe_ids(self):
        blk = genesets.binding_block(self._bundle("t" * 64))
        assert blk["effect_universe_sha256"] == "r" * 64
        assert blk["target_universe_sha256"] == "t" * 64

    def test_two_bundles_differing_ONLY_in_the_TARGET_universe_hash_DIFFERENTLY(self):
        from direct import run_pathway
        from direct.hashing import content_hash
        a = content_hash(run_pathway.method_block(self._bundle("t" * 64)))
        b = content_hash(run_pathway.method_block(self._bundle("Z" * 64)))
        assert a != b, ("the method hash is blind to the target universe — the space "
                        "enrichment tests membership in")

    def test_the_readout_universe_still_moves_the_method_hash_too(self):
        from direct import run_pathway
        from direct.hashing import content_hash
        base = self._bundle("t" * 64)
        other = dict(base, effect_universe_sha256="Q" * 64)
        assert content_hash(run_pathway.method_block(base)) != \
            content_hash(run_pathway.method_block(other))

    def test_a_real_run_binds_both_into_its_method_hash(self, rekeyed):
        args, _, gu, tu = rekeyed
        res = run_pathway.build_pathway(args)
        with open(os.path.join(res["out_dir"], "pathway_provenance.json")) as fh:
            prov = json.load(fh)
        gs = prov["run_binding"]["pathway_method"]["pathway_method"]["gene_sets"]
        assert gs["effect_universe_sha256"] == gu["sha256"]
        assert gs["target_universe_sha256"] == tu["sha256"]
        assert gs["effect_universe_sha256"] != gs["target_universe_sha256"]
