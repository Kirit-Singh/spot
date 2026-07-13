"""BLOCKER 2: mechanism assertions must not be silently collapsed, and MAJOR 3: PubChem
CID / UNII are not in the pinned SQLite join. One cache row per ``mec_id`` with full
assertion/context identity; cross-refs omitted with explicit provenance.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "analysis")))

from druglink import universe_store as us  # noqa: E402

RESOLUTION = {"ENSG1": {"accessions": ["P1"], "targets": ["CHEMBL_T1"],
                        "identity_status": "resolved", "shared_accession_genes": {}}}
UNIVERSE = [{"target_id": "ENSG1", "target_id_namespace": "ensembl_gene"}]
# Two rows: same molecule, target and action_type, but DIFFERENT mec_id (one variant-
# specific). A collapse-by-(molecule,target,action) would erase one.
EVIDENCE = {"CHEMBL_T1": [
    {"molecule_chembl_id": "M1", "mec_id": 101, "pref_name": "DrugA",
     "action_type_source": "INHIBITOR", "mechanism_of_action": "moa",
     "molecular_mechanism": True, "disease_efficacy": True,
     "variant_id": None, "selectivity_comment": None,
     "direct_interaction": True, "mechanism_refs": ["PMID:1"],
     "molecule_type": "Small molecule", "inchikey": "IK1",
     "pubchem_cid": "999", "unii": "U9", "max_phase": "4"},
    {"molecule_chembl_id": "M1", "mec_id": 102, "pref_name": "DrugA",
     "action_type_source": "INHIBITOR", "mechanism_of_action": "moa",
     "molecular_mechanism": True, "disease_efficacy": True,
     "variant_id": "VAR9", "selectivity_comment": "selective for the T790M variant",
     "direct_interaction": True, "mechanism_refs": [],
     "molecule_type": "Small molecule", "inchikey": "IK1",
     "pubchem_cid": "999", "unii": "U9", "max_phase": "4"},
]}


def _row():
    return us.build_store_rows(universe_targets=UNIVERSE, resolution=RESOLUTION,
                               evidence_by_target=EVIDENCE)[0]


def test_two_mec_ids_are_both_retained_not_collapsed():
    r = _row()
    # 101 is general (NULL variant) -> rankable; 102 is variant-specific -> preserved
    # non-rankable. Both retained, in their proper lanes; neither is lost or merged.
    assert {d["source_row_id"] for d in r["drugs"]} == {101}
    assert {a["source_row_id"] for a in r["variant_specific_assertions"]} == {102}


def test_assertion_context_fields_are_present():
    a = next(x for x in _row()["variant_specific_assertions"]
             if x["source_row_id"] == 102)
    assert a["mechanism_of_action"] == "moa"
    assert a["molecular_mechanism"] is True
    assert a["disease_efficacy"] is True
    assert a["variant_id"] == "VAR9"
    assert a["variant_specific"] is True
    assert a["variant_disposition"] == "variant_specific_nonrankable"
    assert a["selectivity_comment"] == "selective for the T790M variant"


def test_non_variant_assertion_is_not_flagged_variant_specific():
    d = next(x for x in _row()["drugs"] if x["source_row_id"] == 101)
    assert d["variant_id"] is None and d["variant_specific"] is False
    assert d["general_gene_rankable"] is True


def test_pubchem_and_unii_are_omitted_with_explicit_provenance():
    d = _row()["drugs"][0]
    assert "pubchem_cid" not in d           # not sourced by the pinned SQLite join
    assert "unii" not in d
    assert d["cross_ref_provenance"]["pubchem_cid"] == "not_in_pinned_sqlite_source"
    assert d["cross_ref_provenance"]["unii"] == "not_in_pinned_sqlite_source"
    assert d["inchikey"] == "IK1"            # InChIKey IS in compound_structures
