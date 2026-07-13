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
from fixtures_spec import TARGET_GENES, UNIVERSE

# The fixture DE object writes var/gene_ids = UNIVERSE (Ensembl) and var/gene_name = the
# same strings, so a fixture crosswalk is the identity. To exercise the REAL shape — sets
# named by SYMBOL, mapped through the crosswalk — the fixture GMT names genes by the
# symbols the crosswalk publishes.


def _symbols_for(ens: list[str]) -> list[str]:
    """The fixture's var/gene_name for these Ensembl ids (its own naming)."""
    return list(ens)


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
        assert xw["n_effect_universe_genes"] == len(UNIVERSE)

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


@pytest.fixture
def rekeyed(synthetic_run, tmp_path):
    """A fixture cache, re-keyed by the REAL builder, bound to the fixture universe."""
    from direct import io_data
    from direct import universe as uni

    args = synthetic_run()
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
    ]
    gmt = write_gmt(os.path.join(d, "reactome_human.canonical.gmt"), sets, id_col=1)
    out = geneset_build.build(
        source="reactome", gmt=gmt,
        release={"release_id": "V97", "license": "CC0-1.0",
                 "license_reference": "https://reactome.org/license"},
        de_main=args.de_main, out_dir=d, sgrna=args.sgrna,
        effect_universe_sha256=gu["sha256"])
    args.gene_sets = out["path"]
    return args, out, gu


class TestTheRekeyedBundleIsAdmitted:
    def test_genesets_load_ADMITS_it_against_the_ensembl_universe(self, rekeyed):
        _, out, gu = rekeyed
        b = genesets.load(out["path"], gu["gene_ids"], gu["sha256"])
        assert b["gene_id_namespace"] == genesets.ENSEMBL_GENE_ID
        assert len(b["sets"]) == 4

    def test_a_SYMBOL_keyed_bundle_is_still_REFUSED(self, rekeyed, tmp_path):
        _, _, gu = rekeyed
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
        _, out, gu = rekeyed
        b = genesets.load(out["path"], gu["gene_ids"], gu["sha256"])
        assert b["gene_set_license"] == "CC0-1.0"
        assert b["gene_set_license_reference"] == "https://reactome.org/license"

    def test_it_is_content_addressed_on_the_science(self, rekeyed):
        _, out, _ = rekeyed
        assert len(out["canonical_sha256"]) == 64
        assert len(out["sha256"]) == 64


class TestTheLossIsRecordedNeverHidden:
    def test_a_partly_unmeasured_set_reports_its_real_coverage(self, rekeyed):
        _, out, gu = rekeyed
        b = genesets.load(out["path"], gu["gene_ids"], gu["sha256"])
        s = b["sets"]["R-HSA-LOSSY"]
        assert s["n_source_symbols"] == 6
        assert s["n_dropped_unmappable"] == 3
        assert s["n_genes_in_universe"] == 3
        # THE NUMBER A READER NEEDS: half the pathway was never measurable here
        assert s["source_coverage"] == pytest.approx(0.5)

    def test_a_fully_measured_set_reports_full_coverage(self, rekeyed):
        _, out, gu = rekeyed
        b = genesets.load(out["path"], gu["gene_ids"], gu["sha256"])
        assert b["sets"]["R-HSA-CONV"]["source_coverage"] == pytest.approx(1.0)

    def test_a_set_with_ZERO_measured_genes_is_EMITTED_not_deleted(self, rekeyed):
        # A pathway missing from the table is indistinguishable from one that was tested
        # and found nothing. This one could never have been tested at all, and says so.
        _, out, gu = rekeyed
        b = genesets.load(out["path"], gu["gene_ids"], gu["sha256"])
        s = b["sets"]["R-HSA-GONE"]
        assert s["n_genes"] == 0
        assert s["n_source_symbols"] == 4
        assert s["n_dropped_unmappable"] == 4
        assert s["source_coverage"] == 0.0
        assert s["coverage"] is None          # no ratio exists; it is not 0.0

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

    def test_the_builder_reports_the_total_and_worst_case_loss(self, rekeyed):
        _, out, _ = rekeyed
        loss = out["mapping_loss"]
        assert loss["n_sets"] == 4
        assert loss["n_sets_with_zero_mapped_genes"] == 1
        assert 0 < loss["total_loss_fraction"] < 1
        assert loss["worst_set_loss_fraction"] == 1.0
        assert loss["worst_set_id"] == "R-HSA-GONE"


class TestThePathwayLaneRunsOnTheRekeyedSets:
    """The whole point: enrichment + convergence, end to end, on masked signatures."""

    def test_it_produces_a_content_addressed_artifact_its_verifier_ADMITS(self,
                                                                          rekeyed):
        args, _, _ = rekeyed
        res = run_pathway.build_pathway(args)
        assert res["verification"]["verdict"] == verify_pathway.ADMIT
        assert res["verification"]["n_failed"] == 0
        assert len(res["records_sha256"]) == 64
        assert res["n_records"] == 4

    def test_enrichment_and_convergence_both_ran(self, rekeyed):
        args, _, _ = rekeyed
        res = run_pathway.build_pathway(args)
        with open(os.path.join(res["out_dir"], "pathway.json")) as fh:
            doc = json.load(fh)
        assert res["n_signature_targets"] > 0
        for r in doc["records"]:
            assert set(r["enrichment"]) == {"away_from_A", "toward_B"}
            assert "convergent" in r["convergence"]

    def test_NO_p_q_or_FDR_anywhere_in_the_artifact(self, rekeyed):
        from direct.temporal import admission
        args, _, _ = rekeyed
        res = run_pathway.build_pathway(args)
        for name in ("pathway.json", "pathway_provenance.json"):
            with open(os.path.join(res["out_dir"], name)) as fh:
                assert admission.forbidden_keys(json.load(fh)) == []

    def test_the_pathway_record_carries_the_re_keying_coverage(self, rekeyed):
        # A pathway record must never look better-covered than it is.
        args, _, _ = rekeyed
        res = run_pathway.build_pathway(args)
        with open(os.path.join(res["out_dir"], "pathway.json")) as fh:
            doc = json.load(fh)
        by_id = {r["set_id"]: r for r in doc["records"]}
        assert by_id["R-HSA-LOSSY"]["source_coverage"] == pytest.approx(0.5)
        assert by_id["R-HSA-LOSSY"]["n_dropped_unmappable"] == 3
        assert by_id["R-HSA-CONV"]["source_coverage"] == pytest.approx(1.0)
