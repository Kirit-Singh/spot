"""Universe identity resolver: ENSG <-> UniProt <-> ChEMBL, conflict-aware.

The existing ``targets.build`` does ``uniprot_to_gene[accession] = ensg`` — a plain dict
assignment, so when one accession maps to two genes the LAST write silently wins and the
first gene's relation vanishes. The universe resolver must never do that: a shared
accession is an EXPLICIT one-to-many relation (both genes kept), and resolution is
order-independent and duplicate-tolerant.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "analysis")))

from druglink import universe_identity as ui  # noqa: E402


def test_one_gene_many_accessions_kept_as_explicit_relation():
    res = ui.resolve_identity(
        universe_ensg={"ENSG1"},
        gene_accessions=[("ENSG1", "P1"), ("ENSG1", "P2")],
        accession_targets=[("P1", "CHEMBL_T1"), ("P2", "CHEMBL_T2")])
    g = res["ENSG1"]
    assert g["accessions"] == ["P1", "P2"]           # sorted, both kept
    assert g["targets"] == ["CHEMBL_T1", "CHEMBL_T2"]
    assert g["identity_status"] == "resolved"


def test_shared_accession_is_explicit_one_to_many_never_last_write_wins():
    # P1 is shared by ENSG1 and ENSG2. A last-write-wins dict would keep only one gene.
    res = ui.resolve_identity(
        universe_ensg={"ENSG1", "ENSG2"},
        gene_accessions=[("ENSG1", "P1"), ("ENSG2", "P1")],
        accession_targets=[("P1", "CHEMBL_T1")])
    assert res["ENSG1"]["identity_status"] == "shared_accession"
    assert res["ENSG2"]["identity_status"] == "shared_accession"
    # BOTH genes retained; the shared accession names ALL genes it touches.
    assert res["ENSG1"]["shared_accession_genes"]["P1"] == ["ENSG1", "ENSG2"]
    assert res["ENSG2"]["shared_accession_genes"]["P1"] == ["ENSG1", "ENSG2"]


def test_order_reversal_is_deterministic():
    a = ui.resolve_identity(
        universe_ensg={"ENSG1", "ENSG2"},
        gene_accessions=[("ENSG1", "P1"), ("ENSG2", "P2")],
        accession_targets=[("P1", "T1"), ("P2", "T2")])
    b = ui.resolve_identity(
        universe_ensg={"ENSG2", "ENSG1"},
        gene_accessions=[("ENSG2", "P2"), ("ENSG1", "P1")],
        accession_targets=[("P2", "T2"), ("P1", "T1")])
    assert a == b


def test_duplicate_relations_are_deduped_not_multiplied():
    res = ui.resolve_identity(
        universe_ensg={"ENSG1"},
        gene_accessions=[("ENSG1", "P1"), ("ENSG1", "P1")],
        accession_targets=[("P1", "T1"), ("P1", "T1")])
    assert res["ENSG1"]["accessions"] == ["P1"]
    assert res["ENSG1"]["targets"] == ["T1"]


def test_unmapped_universe_gene_is_explicit():
    res = ui.resolve_identity(
        universe_ensg={"ENSG1", "ENSG_ORPHAN"},
        gene_accessions=[("ENSG1", "P1")],
        accession_targets=[("P1", "T1")])
    assert res["ENSG_ORPHAN"]["identity_status"] == "unmapped"
    assert res["ENSG_ORPHAN"]["accessions"] == []
    assert res["ENSG_ORPHAN"]["targets"] == []


def test_accession_with_no_single_protein_target_is_resolved_but_targetless():
    res = ui.resolve_identity(
        universe_ensg={"ENSG1"},
        gene_accessions=[("ENSG1", "P1")],
        accession_targets=[])           # P1 has no SINGLE PROTEIN ChEMBL target
    assert res["ENSG1"]["identity_status"] == "resolved"
    assert res["ENSG1"]["accessions"] == ["P1"]
    assert res["ENSG1"]["targets"] == []


def test_relations_outside_the_universe_are_ignored():
    res = ui.resolve_identity(
        universe_ensg={"ENSG1"},
        gene_accessions=[("ENSG1", "P1"), ("ENSG_NOT_IN_UNIVERSE", "P9")],
        accession_targets=[("P1", "T1"), ("P9", "T9")])
    assert set(res.keys()) == {"ENSG1"}
    assert res["ENSG1"]["targets"] == ["T1"]
