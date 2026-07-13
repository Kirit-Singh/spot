"""v2 cache identity — the EXACT predicates of the independent source audit.

    STAGE3_DRUG_CACHE_INDEPENDENT_SOURCE_AUDIT.fa64054e.md
    sha256 fa64054e0698448b143c7e4e564dd2e7003a6e21161ee18b54f826a744a65e67  (verified)

Read from the document, not from a summary of it. That distinction was not academic: the
relayed version used invented field names (`target_taxon`, `relationship`) instead of
ChEMBL's own (`tax_id`, `homologue`), missed that `homologue=2` is a species-group
representative, and dropped the cardinality rule entirely — "exactly one ELIGIBLE **and**
exactly one TOTAL component". A gate written to the summary would have admitted a
three-component target whose one eligible component happened to look right.

The audit reproduced the defect against this very checkout, and the last line is the point:

    synthetic target: target_type=SINGLE PROTEIN, organism=Mus musculus,
    two components mapping to ENSG_A and ENSG_B
    direct_gene_lane_eligible True
    dispositions []
"""
from __future__ import annotations

import pytest

from verifier import cache_evidence as ce
from verifier import cache_identity as ci
from verifier.report import Report


def _comp(**over):
    c = {"accession": "P16410", "component_type": "PROTEIN",
         "tax_id": 9606, "homologue": 0}
    c.update(over)
    return c


def _target(**over):
    t = {"target_chembl_id": "CHEMBL1778", "target_type": "SINGLE PROTEIN",
         "tax_id": 9606, "species_group_flag": 0, "target_components": [_comp()]}
    t.update(over)
    return t


def _failed(rep):
    return [n for n, ok, _ in rep.checks if not ok]


def test_the_audit_sha_is_pinned():
    assert ci.AUDIT_SHA256 == (
        "fa64054e0698448b143c7e4e564dd2e7003a6e21161ee18b54f826a744a65e67")


# --------------------------------------------------------------------------- #
# The audit's OWN reproduced failure.
# --------------------------------------------------------------------------- #
def test_the_audits_reproduced_defect_is_now_refused():
    """Mus musculus + two components. The engine admitted it with NO disposition."""
    mouse_two_component = _target(
        target_chembl_id="CHEMBL_SYNTH", tax_id=10090,
        target_components=[_comp(accession="A"), _comp(accession="B")])
    ok, reason = ci.gene_lane_admissible(mouse_two_component)
    assert not ok
    assert ci.DISP_NON_HUMAN_TARGET in reason

    disp = ci.disposition_for(mouse_two_component)
    assert disp["rankable"] is False
    assert disp["state"] == ci.DISP_NON_HUMAN_TARGET


def test_a_refused_target_is_never_silently_dropped():
    """`dispositions []` was the other half of the defect."""
    rep = Report()
    bad = _target(target_chembl_id="CHEMBL_MOUSE", tax_id=10090)
    ci.check_gene_lane_identity(rep, targets=[bad], admitted_entity_ids=set(),
                                dispositions=[])
    assert any("NAMED non-rankable disposition" in n for n in _failed(rep))


def test_a_refused_target_WITH_its_disposition_passes():
    rep = Report()
    bad = _target(target_chembl_id="CHEMBL_MOUSE", tax_id=10090)
    ci.check_gene_lane_identity(rep, targets=[bad], admitted_entity_ids=set(),
                                dispositions=[ci.disposition_for(bad)])
    assert not _failed(rep)


# --------------------------------------------------------------------------- #
# The six frozen predicates, in ChEMBL's own column names.
# --------------------------------------------------------------------------- #
def test_a_real_human_single_protein_is_admissible():
    ok, reason = ci.gene_lane_admissible(_target())
    assert ok and "exactly_one_eligible_and_one_total" in reason


def test_target_type_must_be_SINGLE_PROTEIN():
    ok, r = ci.gene_lane_admissible(_target(target_type="PROTEIN COMPLEX"))
    assert not ok and ci.DISP_NOT_SINGLE_PROTEIN in r


def test_td_tax_id_must_be_9606():
    ok, r = ci.gene_lane_admissible(_target(tax_id=10090))
    assert not ok and ci.DISP_NON_HUMAN_TARGET in r


def test_species_group_flag_must_be_0():
    ok, r = ci.gene_lane_admissible(_target(species_group_flag=1))
    assert not ok and ci.DISP_SPECIES_GROUP in r


def test_cs_component_type_must_be_PROTEIN():
    ok, r = ci.gene_lane_admissible(
        _target(target_components=[_comp(component_type="NUCLEIC ACID")]))
    assert not ok and ci.DISP_NON_PROTEIN_COMPONENT in r


def test_cs_tax_id_must_be_9606_even_when_the_target_says_human():
    ok, r = ci.gene_lane_admissible(
        _target(target_components=[_comp(tax_id=10090)]))
    assert not ok and ci.DISP_NON_HUMAN_COMPONENT in r


@pytest.mark.parametrize("homologue,label", [(1, "homologue"),
                                             (2, "species-group representative")])
def test_tc_homologue_must_be_0_exact(homologue, label):
    """0 = exact, 1 = homologue, 2 = species-group rep. BOTH 1 and 2 are refused.

    The summary said "homologue" and I would have checked a relationship string. A
    species-group representative (2) would have sailed straight through.
    """
    ok, r = ci.gene_lane_admissible(
        _target(target_components=[_comp(homologue=homologue)]))
    assert not ok and ci.DISP_HOMOLOGUE in r, f"{label} must be refused"


# --------------------------------------------------------------------------- #
# Cardinality: exactly one ELIGIBLE **and** exactly one TOTAL.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("n", [0, 2, 3])
def test_anything_other_than_exactly_one_TOTAL_component_is_refused(n):
    ok, r = ci.gene_lane_admissible(
        _target(target_components=[_comp() for _ in range(n)]))
    assert not ok and ci.DISP_COMPONENT_CARDINALITY in r


def test_one_ELIGIBLE_among_several_components_is_STILL_refused():
    """The rule a summary loses. Filtering down to the component you like and calling the
    result a single protein is exactly the silent failure."""
    ok, r = ci.gene_lane_admissible(_target(target_components=[
        _comp(accession="P16410"),                       # eligible
        _comp(accession="X", tax_id=10090),              # not
        _comp(accession="Y", homologue=1),               # not
    ]))
    assert not ok
    assert ci.DISP_COMPONENT_CARDINALITY in r
    assert "3 total component(s), 1 eligible" in r


# --------------------------------------------------------------------------- #
# A coarser cache is REFUSED. The REST adapter must not discard source fields.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("field", ci.REQUIRED_TARGET_FIELDS)
def test_a_target_missing_a_source_field_is_refused(field):
    t = _target()
    del t[field]
    ok, r = ci.gene_lane_admissible(t)
    assert not ok and ci.DISP_CACHE_TOO_COARSE in r


@pytest.mark.parametrize("field", ci.REQUIRED_COMPONENT_FIELDS)
def test_a_component_missing_a_source_field_is_refused(field):
    c = _comp()
    del c[field]
    ok, r = ci.gene_lane_admissible(_target(target_components=[c]))
    assert not ok


def test_a_rest_shaped_adapter_that_discarded_the_fields_FAILS():
    rep = Report()
    stripped = {"target_chembl_id": "C1", "target_type": "SINGLE PROTEIN",
                "target_components": [{"accession": "P16410"}]}
    ci.check_cache_is_not_coarser_than_the_contract(rep, [stripped])
    assert _failed(rep)


# --------------------------------------------------------------------------- #
# BLOCKER 2 — mec_id, and the fields that make it lossless.
# --------------------------------------------------------------------------- #
def _assertion(**over):
    a = {"source_row_id": 7, "mechanism_of_action": "x", "molecular_mechanism": True,
         "direct_interaction": True, "disease_efficacy": True, "variant_id": None,
         "selectivity_comment": None, "action_type_source": "INHIBITOR"}
    a.update(over)
    return a


def test_two_rows_for_one_mec_id_is_double_counting():
    rep = Report()
    ce.check_one_assertion_per_mec_id(rep, [_assertion(), _assertion()])
    assert any("ONE cache assertion per ChEMBL mec_id" in n for n in _failed(rep))


@pytest.mark.parametrize("field", ce.REQUIRED_ASSERTION_FIELDS)
def test_an_assertion_missing_any_identity_or_context_field_is_lossy(field):
    a = _assertion()
    del a[field]
    rep = Report()
    ce.check_one_assertion_per_mec_id(rep, [a])
    assert any("identity/context fields" in n for n in _failed(rep))


def test_a_lossless_assertion_passes():
    rep = Report()
    ce.check_one_assertion_per_mec_id(rep, [_assertion(source_row_id=7),
                                            _assertion(source_row_id=8)])
    assert not _failed(rep)




# --------------------------------------------------------------------------- #
# BLOCKER 3 — the typed universe; the four are HASHED ROWS.
# --------------------------------------------------------------------------- #
def _universe(**over):
    u = {"universe_is_homogeneous_ensembl": False, "namespaces_are_split": True,
         "store_id_hashes_typed_universe": True,
         "hashed_rows": [{"target_id": s, "target_id_namespace": "gene_symbol",
                          "disposition": ci.UNSUPPORTED_NAMESPACE}
                         for s in ci.SYMBOL_ONLY_TARGETS]}
    u.update(over)
    return u


def test_the_typed_universe_passes():
    rep = Report()
    ci.check_typed_universe(rep, _universe())
    assert not _failed(rep)


def test_the_four_symbols_must_be_HASHED_ROWS_not_an_out_of_band_note():
    rep = Report()
    ci.check_typed_universe(rep, _universe(hashed_rows=[]))
    assert any("HASHED ROWS" in n for n in _failed(rep))


def test_a_store_id_hashing_only_the_ensg_set_is_refused():
    """It omits four real perturbation targets from the artifact's own identity."""
    rep = Report()
    ci.check_typed_universe(rep, _universe(store_id_hashes_typed_universe=False))
    assert any("store_id hashes the TYPED universe" in n for n in _failed(rep))


def test_a_universe_declared_homogeneous_ensg_is_refused():
    rep = Report()
    ci.check_typed_universe(rep, _universe(universe_is_homogeneous_ensembl=True))
    assert _failed(rep)


def test_the_audited_counts_and_de_stats_hash_are_pinned():
    assert (ci.N_TARGETS, ci.N_ENSEMBL, ci.N_UNSUPPORTED_SYMBOL) == (11_526, 11_522, 4)
    assert ci.SYMBOL_ONLY_TARGETS == ("MTRNR2L1", "MTRNR2L4", "MTRNR2L8", "OCLM")
    assert ci.DE_STATS_SHA256.startswith("c355f535")


# --------------------------------------------------------------------------- #
# The top-N union contains SYMBOLS. `*_ensg_*` is simply false.
# --------------------------------------------------------------------------- #
def test_a_union_field_named_ensg_is_refused():
    """The audit re-derived that the direction-only unions contain MTRNR2L4 and MTRNR2L8."""
    rep = Report()
    ci.check_top_n_union_is_not_called_ensg(
        rep, {"union_unique_ensg_top_n_per_arm": 1429})
    assert any("*_ensg_*" in n for n in _failed(rep))


def test_a_target_id_named_union_passes():
    rep = Report()
    ci.check_top_n_union_is_not_called_ensg(
        rep, {"union_unique_target_id_top_n_per_arm": 1429,
              "n_ensembl": 1427, "n_symbol_only": 2,
              "significant_filter_is_proxy": True})
    assert not _failed(rep)


def test_symbols_really_are_in_the_top_n_union():
    assert ci.SYMBOLS_IN_TOP_N_UNION == ("MTRNR2L4", "MTRNR2L8")


# --------------------------------------------------------------------------- #
# MAJOR 2 / 3 / 4.
# --------------------------------------------------------------------------- #
def test_the_max_phase_transformation_code_must_be_BOUND_by_hash():
    rep = Report()
    ci.check_max_phase_is_context_only(rep, [], ordering_keys=["arm_rank"],
                                       manifest={"max_phase_rule_id": "x"})
    assert any("BOUND by hash" in n for n in _failed(rep))


def test_a_bound_max_phase_manifest_passes():
    rep = Report()
    ci.check_max_phase_is_context_only(
        rep, [], ordering_keys=["arm_rank"],
        manifest={"max_phase_rule_id": "spot.stage03.chembl_max_phase.preserve_exact.v1",
                  "max_phase_code_sha256": "a" * 64})
    assert not _failed(rep)


def test_an_ordering_naming_max_phase_FAILS():
    rep = Report()
    ci.check_max_phase_is_context_only(rep, [], ordering_keys=["max_phase"])
    assert any("context only" in n for n in _failed(rep))


def test_an_invented_pubchem_cid_is_refused():
    """ChEMBL SQLite supplies InChI/InChIKey; it does not supply PubChem CID or UNII."""
    rep = Report()
    ci.check_cross_identifiers_are_sourced(
        rep, [{"molecule_chembl_id": "CHEMBL1", "pubchem_cid": 2244}])
    assert any("not_in_source" in n for n in _failed(rep))


def test_a_null_pubchem_cid_with_not_in_source_provenance_passes():
    rep = Report()
    ci.check_cross_identifiers_are_sourced(rep, [{
        "molecule_chembl_id": "CHEMBL1", "pubchem_cid": None,
        "pubchem_cid_provenance": ci.NOT_IN_SOURCE,
        "unii": None, "unii_provenance": ci.NOT_IN_SOURCE}])
    assert not _failed(rep)


def test_cache_DATA_may_not_be_represented_as_MIT():
    rep = Report()
    ci.check_license_separation(rep, [
        {"source": "chembl", "license": "MIT", "source_record_id": "c1"}])
    assert any("MIT" in n for n in _failed(rep))


def test_a_chembl_row_wearing_the_uniprot_license_is_refused():
    rep = Report()
    ci.check_license_separation(rep, [
        {"source": "chembl", "license": "CC BY 4.0", "source_record_id": "c1"}])
    assert any("ITS OWN source's licence" in n for n in _failed(rep))


def test_the_chembl_layer_must_bundle_LICENSE_and_REQUIRED_ATTRIBUTION():
    rep = Report()
    ci.check_license_separation(
        rep, [{"source": "chembl", "license": "CC BY-SA 3.0"}],
        packaging={"chembl_bundled_files": ["LICENSE"], "chembl_release": "CHEMBL_37",
                   "chembl_doi": "10.6019/CHEMBL.database.37",
                   "chembl_layer_is_separable": True})
    assert any("REQUIRED.ATTRIBUTION" in n for n in _failed(rep))


def test_a_properly_packaged_separable_chembl_layer_passes():
    rep = Report()
    ci.check_license_separation(
        rep, [{"source": "chembl", "license": "CC BY-SA 3.0"},
              {"source": "uniprot", "license": "CC BY 4.0"}],
        packaging={"chembl_bundled_files": list(ci.CHEMBL_REQUIRED_FILES),
                   "chembl_release": "CHEMBL_37",
                   "chembl_doi": "10.6019/CHEMBL.database.37",
                   "chembl_layer_is_separable": True})
    assert not _failed(rep)


# --------------------------------------------------------------------------- #
# REAL-STORE ATTACK — mec_id 6210/6862 across three ENSG targets.
#
# The store FLAGGED the ambiguity (`shared_accession`) and then emitted `drug_evidence`
# anyway. A flag that does not gate is decoration: the drug lands on all three genes, and
# each one reads to a consumer as independent evidence.
# --------------------------------------------------------------------------- #
THREE_GENES = ["ENSG00000000001", "ENSG00000000002", "ENSG00000000003"]
SHARED_ACC = "P0DUMMY"


def _edge(mec, gene, **over):
    e = {"edge_id": f"e{mec}_{gene[-1]}", "source_row_id": mec, "target_ensembl": gene,
         "uniprot_id": SHARED_ACC, "identity_status": ce.IDENTITY_SHARED_ACCESSION,
         "lane": "direct_gene_mechanism", "rankable": True}
    e.update(over)
    return e


REAL_ACC_MAP = {SHARED_ACC: THREE_GENES}


def test_the_real_counterexample_is_refused_mec_6210_and_6862_across_three_genes():
    """The exact rows found in the extracted store."""
    edges = [_edge(mec, g) for mec in ce.REAL_ATTACK_MEC_IDS for g in THREE_GENES]
    assert len(edges) == 6                       # 2 mec_ids x 3 genes

    rep = Report()
    ce.check_no_drug_evidence_on_ambiguous_identity(
        rep, edges=edges, accession_to_genes=REAL_ACC_MAP, dispositions=[])
    failed = _failed(rep)
    assert any("SHARED identity" in n for n in failed)
    assert any("ambiguous_identity" in n for n in failed)


def test_one_mec_id_may_not_be_evidence_for_three_genes():
    rep = Report()
    ce.check_one_mec_id_is_not_spread_across_genes(
        rep, [_edge(6210, g) for g in THREE_GENES])
    assert any("MORE THAN ONE gene" in n for n in _failed(rep))
    assert ce.REAL_ATTACK_N_GENES == 3


def test_shared_accession_flagged_but_still_rankable_is_the_defect():
    """The row SAYS shared_accession and carries drug_evidence. Noticing is not acting."""
    rep = Report()
    ce.check_no_drug_evidence_on_ambiguous_identity(
        rep, edges=[_edge(6210, THREE_GENES[0])],
        accession_to_genes=REAL_ACC_MAP, dispositions=[])
    assert any("SHARED identity" in n for n in _failed(rep))


def test_an_unresolved_identity_may_never_be_rankable():
    rep = Report()
    ce.check_no_drug_evidence_on_ambiguous_identity(
        rep, edges=[_edge(1, "ENSG1", identity_status="unresolved",
                          uniprot_id="P_CLEAN")],
        accession_to_genes={"P_CLEAN": ["ENSG1"]}, dispositions=[])
    assert any("unresolved" in d for _, ok, d in rep.checks if not ok)


def test_a_shared_accession_needs_a_NAMED_ambiguous_identity_disposition():
    """No edge is necessary but not sufficient: an absent edge with no record is
    indistinguishable from a drug nobody found."""
    rep = Report()
    ce.check_no_drug_evidence_on_ambiguous_identity(
        rep, edges=[], accession_to_genes=REAL_ACC_MAP, dispositions=[])
    assert any("ambiguous_identity" in n for n in _failed(rep))


def test_a_shared_accession_WITH_its_disposition_and_no_edge_passes():
    rep = Report()
    ce.check_no_drug_evidence_on_ambiguous_identity(
        rep, edges=[], accession_to_genes=REAL_ACC_MAP,
        dispositions=[{"subject_id": SHARED_ACC,
                       "state": ce.DISP_AMBIGUOUS_IDENTITY}])
    assert not _failed(rep)


def test_a_resolved_one_to_one_accession_still_ranks():
    """The gate must not refuse everything — a clean identity is still drug evidence."""
    rep = Report()
    ce.check_no_drug_evidence_on_ambiguous_identity(
        rep,
        edges=[_edge(9, "ENSG_CLEAN", uniprot_id="P16410",
                     identity_status=ce.IDENTITY_RESOLVED)],
        accession_to_genes={"P16410": ["ENSG_CLEAN"]},
        dispositions=[])
    assert not _failed(rep)
