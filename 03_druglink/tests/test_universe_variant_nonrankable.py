"""A variant-specific mechanism assertion is NOT general wild-type-gene evidence. Only
``variant_id IS NULL`` enters the general gene-drug lane. Variant assertions (including the
ChEMBL sentinel ``-1`` = 'UNDEFINED MUTATION', and specific V600E/V617F) are preserved but
``variant_specific_nonrankable`` and excluded from the general drug lane.

Real examples: mec 9593/9909 (JAK2 V617F), 995/992/5298 (BRAF V600E), and variant_id -1.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "analysis")))

from druglink import universe_store as us  # noqa: E402

GENE = "ENSG00000096968"       # JAK2
UNIVERSE = [{"target_id": GENE, "target_id_namespace": "ensembl_gene"}]
RESOLUTION = {GENE: {"accessions": ["O60674"], "targets": ["CHEMBL_JAK2"],
                     "identity_status": "resolved", "shared_accession_genes": {}}}
EVIDENCE = {"CHEMBL_JAK2": [
    {"mec_id": 1000, "variant_id": None, "molecule_chembl_id": "M_GEN",
     "action_type_source": "INHIBITOR", "max_phase": "4"},          # general wild-type
    {"mec_id": 9593, "variant_id": 42, "molecule_chembl_id": "M_V617F_a",
     "action_type_source": "INHIBITOR", "max_phase": "4"},          # V617F variant
    {"mec_id": 9909, "variant_id": 42, "molecule_chembl_id": "M_V617F_b",
     "action_type_source": "INHIBITOR", "max_phase": "4"},          # V617F variant
    {"mec_id": 7777, "variant_id": -1, "molecule_chembl_id": "M_UNDEF",
     "action_type_source": "INHIBITOR", "max_phase": "4"}]}         # -1 UNDEFINED MUTATION


def _row():
    return us.build_store_rows(universe_targets=UNIVERSE, resolution=RESOLUTION,
                               evidence_by_target=EVIDENCE)[0]


def test_only_null_variant_enters_the_general_drug_lane():
    r = _row()
    assert {d["source_row_id"] for d in r["drugs"]} == {1000}
    assert r["disposition"] == "drug_evidence"
    for d in r["drugs"]:
        assert d["general_gene_rankable"] is True


def test_variant_assertions_including_minus_one_are_preserved_nonrankable():
    r = _row()
    vids = {a["source_row_id"] for a in r["variant_specific_assertions"]}
    assert vids == {9593, 9909, 7777}               # incl the -1 undefined mutation
    for a in r["variant_specific_assertions"]:
        assert a["general_gene_rankable"] is False
        assert a["variant_disposition"] == "variant_specific_nonrankable"


def test_gene_with_only_variant_assertions_has_no_general_drug_evidence():
    ev = {"CHEMBL_JAK2": [{"mec_id": 995, "variant_id": 17, "molecule_chembl_id": "M",
                           "action_type_source": "INHIBITOR", "max_phase": "4"}]}
    r = us.build_store_rows(universe_targets=UNIVERSE, resolution=RESOLUTION,
                            evidence_by_target=ev)[0]
    assert r["disposition"] == "no_drug_evidence"
    assert r["no_evidence_reason"] == "only_variant_specific_assertions"
    assert r["drugs"] == []
    assert {a["source_row_id"] for a in r["variant_specific_assertions"]} == {995}


def test_coverage_counts_only_general_drug_evidence():
    r = _row()
    summ = us.coverage_summary([r])
    assert summ["n_drug_evidence"] == 1              # the gene has 1 general assertion
    assert summ["n_variant_specific_assertions"] == 3
