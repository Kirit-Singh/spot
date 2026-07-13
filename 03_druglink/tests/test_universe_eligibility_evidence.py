"""The compact store must ship independently revalidatable eligibility evidence for
ACCEPTED and REJECTED ChEMBL target mappings: the exact predicate fields (taxon, type,
species-group, component type/taxon/homologue, cardinality) plus the verdict, sanitized
(no machine paths) and content-addressed.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "analysis")))

from druglink import universe_target_eligibility as te   # noqa: E402
from druglink.hashing import contains_local_path          # noqa: E402


def _target(**over):
    t = {"target_chembl_id": "CHEMBL_T", "target_type": "SINGLE PROTEIN",
         "tax_id": 9606, "species_group_flag": 0,
         "components": [{"component_type": "PROTEIN", "tax_id": 9606,
                         "homologue": 0, "accession": "P1"}]}
    t.update(over)
    return t


def test_accepted_record_carries_the_exact_predicate_fields():
    rec = te.evidence_record(_target())
    assert rec["target_type"] == "SINGLE PROTEIN"
    assert rec["tax_id"] == 9606 and rec["species_group_flag"] == 0
    assert rec["n_components"] == 1
    assert rec["components"] == [{"component_type": "PROTEIN", "tax_id": 9606,
                                  "homologue": 0, "accession": "P1"}]
    assert rec["eligible"] is True
    assert rec["disposition"] == "eligible_human_single_protein"
    assert rec["accession"] == "P1"


def test_mutations_change_the_verdict_and_carry_the_failing_field():
    assert te.evidence_record(_target(tax_id=10090))["disposition"] == \
        "reject_nonhuman_target_taxon"
    assert te.evidence_record(_target(target_type="PROTEIN COMPLEX"))["disposition"] == \
        "reject_wrong_target_type"
    assert te.evidence_record(_target(components=[
        {"component_type": "PROTEIN", "tax_id": 9606, "homologue": 1,
         "accession": "P1"}]))["disposition"] == "reject_homologue"
    two = te.evidence_record(_target(components=[
        {"component_type": "PROTEIN", "tax_id": 9606, "homologue": 0, "accession": "P1"},
        {"component_type": "PROTEIN", "tax_id": 9606, "homologue": 0, "accession": "P2"}]))
    assert two["disposition"] == "reject_component_cardinality" and two["n_components"] == 2


def test_evidence_record_has_no_machine_path():
    assert contains_local_path(te.evidence_record(_target())) == []


def test_artifact_is_content_addressable_and_counts_dispositions():
    recs = [te.evidence_record(_target()),
            te.evidence_record(_target(target_chembl_id="CHEMBL_M", tax_id=10090))]
    art = te.eligibility_evidence_artifact(recs)
    assert art["schema"] == "spot.stage03_target_eligibility_evidence.v1"
    assert art["eligible_single_protein_sql"] == te.ELIGIBLE_SINGLE_PROTEIN_SQL
    assert art["counts"]["n_total"] == 2 and art["counts"]["n_eligible"] == 1
    assert art["counts"]["by_disposition"]["reject_nonhuman_target_taxon"] == 1
    assert contains_local_path(art) == []


def test_artifact_is_order_independent():
    a = te.eligibility_evidence_artifact(
        [te.evidence_record(_target(target_chembl_id="A")),
         te.evidence_record(_target(target_chembl_id="B"))])
    b = te.eligibility_evidence_artifact(
        [te.evidence_record(_target(target_chembl_id="B")),
         te.evidence_record(_target(target_chembl_id="A"))])
    assert a == b
