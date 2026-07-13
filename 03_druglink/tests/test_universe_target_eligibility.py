"""BLOCKER 1: 'human SINGLE PROTEIN' alone is NOT an adequate identity rule.

A direct-gene-eligible ChEMBL target must satisfy every predicate and have EXACTLY ONE
total component (which is the eligible human protein):

  td.target_type='SINGLE PROTEIN' AND td.tax_id=9606 AND td.species_group_flag=0
  AND cs.component_type='PROTEIN' AND cs.tax_id=9606 AND tc.homologue=0
  AND exactly one total component.

Anything else emits a NAMED non-rankable disposition, never a silent gene edge.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "analysis")))

from druglink import universe_target_eligibility as te  # noqa: E402


def _target(**over):
    t = {"target_chembl_id": "CHEMBL_T", "target_type": "SINGLE PROTEIN",
         "tax_id": 9606, "species_group_flag": 0,
         "components": [{"component_type": "PROTEIN", "tax_id": 9606,
                         "homologue": 0, "accession": "P1"}]}
    t.update(over)
    return t


def test_human_single_protein_one_component_is_eligible():
    r = te.evaluate(_target())
    assert r["eligible"] is True
    assert r["accession"] == "P1"
    assert r["disposition"] == "eligible_human_single_protein"


def test_wrong_target_type_rejected():
    r = te.evaluate(_target(target_type="PROTEIN COMPLEX"))
    assert r["eligible"] is False and r["disposition"] == "reject_wrong_target_type"


def test_mouse_target_taxon_rejected():
    r = te.evaluate(_target(tax_id=10090))
    assert r["eligible"] is False
    assert r["disposition"] == "reject_nonhuman_target_taxon"


def test_species_group_flag_rejected():
    r = te.evaluate(_target(species_group_flag=1))
    assert r["eligible"] is False and r["disposition"] == "reject_species_group"


def test_two_distinct_components_reject_cardinality():
    r = te.evaluate(_target(components=[
        {"component_type": "PROTEIN", "tax_id": 9606, "homologue": 0, "accession": "P1"},
        {"component_type": "PROTEIN", "tax_id": 9606, "homologue": 0, "accession": "P2"}]))
    assert r["eligible"] is False
    assert r["disposition"] == "reject_component_cardinality"
    assert r["accession"] is None


def test_homologue_component_rejected():
    r = te.evaluate(_target(components=[
        {"component_type": "PROTEIN", "tax_id": 9606, "homologue": 1, "accession": "P1"}]))
    assert r["eligible"] is False and r["disposition"] == "reject_homologue"


def test_nonprotein_component_rejected():
    r = te.evaluate(_target(components=[
        {"component_type": "DNA", "tax_id": 9606, "homologue": 0, "accession": "P1"}]))
    assert r["eligible"] is False and r["disposition"] == "reject_nonprotein_component"


def test_nonhuman_component_taxon_rejected():
    r = te.evaluate(_target(components=[
        {"component_type": "PROTEIN", "tax_id": 10090, "homologue": 0,
         "accession": "P1"}]))
    assert r["eligible"] is False
    assert r["disposition"] == "reject_nonhuman_component_taxon"


def test_zero_components_rejected():
    r = te.evaluate(_target(components=[]))
    assert r["eligible"] is False and r["disposition"] == "reject_component_cardinality"


def test_duplicated_identical_component_rows_are_deduped_then_eligible():
    # A join artifact may repeat the SAME component row; that is still one component.
    comp = {"component_type": "PROTEIN", "tax_id": 9606, "homologue": 0,
            "accession": "P1"}
    r = te.evaluate(_target(components=[dict(comp), dict(comp)]))
    assert r["eligible"] is True and r["accession"] == "P1"


def test_component_order_does_not_change_a_two_component_rejection():
    a = te.evaluate(_target(components=[
        {"component_type": "PROTEIN", "tax_id": 9606, "homologue": 0, "accession": "P1"},
        {"component_type": "PROTEIN", "tax_id": 9606, "homologue": 0, "accession": "P2"}]))
    b = te.evaluate(_target(components=[
        {"component_type": "PROTEIN", "tax_id": 9606, "homologue": 0, "accession": "P2"},
        {"component_type": "PROTEIN", "tax_id": 9606, "homologue": 0, "accession": "P1"}]))
    assert a["disposition"] == b["disposition"] == "reject_component_cardinality"
