"""A shared UniProt accession (one accession -> many genes) is AMBIGUOUS: it must not
admit direct gene drug evidence. Real case: calmodulin is encoded by three genes
(CALM1/2/3 = ENSG00000143933 / ENSG00000160014 / ENSG00000198668) whose products share
the accessions P0DP23/P0DP24/P0DP25 (and Q96HY3), so mechanism assertions 6210 and 6862
would otherwise be copied onto all three genes. Fail closed: ``ambiguous_identity``.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "analysis")))

from druglink import universe_store as us            # noqa: E402
from druglink.universe_identity import resolve_identity  # noqa: E402

GENES = ["ENSG00000143933", "ENSG00000160014", "ENSG00000198668"]
ACCS = ["P0DP23", "P0DP24", "P0DP25", "Q96HY3"]
UNIVERSE = [{"target_id": g, "target_id_namespace": "ensembl_gene"} for g in GENES]
EVIDENCE = {"CHEMBL_CALM": [
    {"molecule_chembl_id": "CHEMBL_M6210", "mec_id": 6210,
     "action_type_source": "INHIBITOR", "max_phase": "4"},
    {"molecule_chembl_id": "CHEMBL_M6862", "mec_id": 6862,
     "action_type_source": "INHIBITOR", "max_phase": "4"}]}


def _resolution(gene_order=GENES, acc_order=ACCS):
    gene_accessions = [(g, a) for g in gene_order for a in acc_order]
    accession_targets = [(a, "CHEMBL_CALM") for a in acc_order]
    return resolve_identity(universe_ensg=set(GENES),
                            gene_accessions=gene_accessions,
                            accession_targets=accession_targets)


def _rows(resolution):
    return {r["target_id"]: r for r in us.build_store_rows(
        universe_targets=UNIVERSE, resolution=resolution,
        evidence_by_target=EVIDENCE)}


def test_shared_accession_genes_are_ambiguous_identity_not_drug_evidence():
    rows = _rows(_resolution())
    for g in GENES:
        assert rows[g]["disposition"] == "ambiguous_identity", g
        assert rows[g]["drugs"] == []               # NOT admitted as rankable evidence
        assert rows[g]["no_evidence_reason"] == \
            "shared_uniprot_accession_maps_to_multiple_genes"


def test_ambiguous_source_assertions_are_preserved_separately():
    rows = _rows(_resolution())
    ids = {a["source_row_id"] for a in rows[GENES[0]]["ambiguous_source_assertions"]}
    assert ids == {6210, 6862}                       # source kept, just not rankable


def test_ambiguous_rows_excluded_from_drug_evidence_count():
    summ = us.coverage_summary(_rows(_resolution()).values())
    assert summ["n_drug_evidence"] == 0
    assert summ["n_ambiguous_identity"] == 3
    assert summ["n_ensg"] == 3
    # split still totals: ensg = drug + no_drug + ambiguous
    assert (summ["n_drug_evidence"] + summ["n_no_drug_evidence"]
            + summ["n_ambiguous_identity"]) == summ["n_ensg"]


def test_ambiguity_verdict_is_order_independent():
    a = {k: v["disposition"] for k, v in _rows(_resolution(GENES, ACCS)).items()}
    b = {k: v["disposition"] for k, v in
         _rows(_resolution(list(reversed(GENES)), list(reversed(ACCS)))).items()}
    assert a == b == {g: "ambiguous_identity" for g in GENES}
