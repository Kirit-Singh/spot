"""Universe store builder: namespace-split dispositions, verbatim action_type, no
cache-native direction, exact max_phase. Direction/compatibility is NEVER precomputed in
the cache; it is derived only at view time by the frozen direction.py.
"""
from __future__ import annotations

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "analysis")))

from druglink import universe_store as us       # noqa: E402
from druglink import direction as dz            # noqa: E402


UNIVERSE = [
    {"target_id": "ENSG_DRUGGED", "target_id_namespace": "ensembl_gene"},
    {"target_id": "ENSG_UNDRUGGED", "target_id_namespace": "ensembl_gene"},
    {"target_id": "ENSG_UNMAPPED", "target_id_namespace": "ensembl_gene"},
    {"target_id": "MTRNR2L1", "target_id_namespace": "symbol"},
]
RESOLUTION = {
    "ENSG_DRUGGED": {"accessions": ["P1"], "targets": ["CHEMBL_T1"],
                     "identity_status": "resolved", "shared_accession_genes": {}},
    "ENSG_UNDRUGGED": {"accessions": ["P2"], "targets": ["CHEMBL_T2"],
                       "identity_status": "resolved", "shared_accession_genes": {}},
    "ENSG_UNMAPPED": {"accessions": [], "targets": [],
                      "identity_status": "unmapped", "shared_accession_genes": {}},
}
EVIDENCE = {
    "CHEMBL_T1": [
        {"molecule_chembl_id": "CHEMBL_M1", "pref_name": "DrugA",
         "action_type_source": "INHIBITOR", "mechanism_of_action": "X inhibitor",
         "direct_interaction": True, "mechanism_refs": ["PMID:1"],
         "molecule_type": "Small molecule", "inchikey": "IK1",
         "pubchem_cid": "111", "unii": "U1", "max_phase": "4"},
        {"molecule_chembl_id": "CHEMBL_M2", "pref_name": "DrugB",
         "action_type_source": "PARTIAL AGONIST", "mechanism_of_action": "X partial agonist",
         "direct_interaction": True, "mechanism_refs": [],
         "molecule_type": "Small molecule", "inchikey": "IK2",
         "pubchem_cid": None, "unii": None, "max_phase": "0.5"},
    ],
    "CHEMBL_T2": [],   # target exists but no drug_mechanism rows
}


def _rows():
    return {r["target_id"]: r for r in us.build_store_rows(
        universe_targets=UNIVERSE, resolution=RESOLUTION, evidence_by_target=EVIDENCE)}


def test_symbol_only_is_unsupported_namespace_with_no_drugs():
    r = _rows()["MTRNR2L1"]
    assert r["disposition"] == "unsupported_namespace"
    assert r["target_id_namespace"] == "symbol"
    assert r["drugs"] == []


def test_ensg_with_drug_is_drug_evidence():
    r = _rows()["ENSG_DRUGGED"]
    assert r["disposition"] == "drug_evidence"
    assert r["target_id_namespace"] == "ensembl_gene"
    assert {d["molecule_chembl_id"] for d in r["drugs"]} == {"CHEMBL_M1", "CHEMBL_M2"}


def test_ensg_without_drug_is_explicit_no_drug_evidence():
    assert _rows()["ENSG_UNDRUGGED"]["disposition"] == "no_drug_evidence"
    assert _rows()["ENSG_UNMAPPED"]["disposition"] == "no_drug_evidence"
    assert _rows()["ENSG_UNMAPPED"]["no_evidence_reason"] is not None


def test_action_type_is_verbatim_and_store_carries_no_direction():
    r = _rows()["ENSG_DRUGGED"]
    for d in r["drugs"]:
        assert "action_type_source" in d
        # The cache embeds NO precomputed direction / effect / compatibility.
        assert "direction" not in d
        assert "intervention_effect" not in d
        assert "directional_evidence_status" not in d
    got = {d["molecule_chembl_id"]: d["action_type_source"] for d in r["drugs"]}
    assert got == {"CHEMBL_M1": "INHIBITOR", "CHEMBL_M2": "PARTIAL AGONIST"}


def test_unknown_action_types_stay_unknown_under_frozen_direction():
    # The store keeps PARTIAL AGONIST verbatim; the FROZEN direction.py (the only
    # authority) must classify it unknown => non-rankable. The cache cannot promote it.
    r = _rows()["ENSG_DRUGGED"]
    by_mol = {d["molecule_chembl_id"]: d for d in r["drugs"]}
    eff, _ = dz.intervention_effect(by_mol["CHEMBL_M2"]["action_type_source"])
    assert eff == dz.EFFECT_UNKNOWN
    # DISRUPTING AGENT likewise (guarding the second named action type).
    assert dz.intervention_effect("DISRUPTING AGENT")[0] == dz.EFFECT_UNKNOWN
    # A real inhibitor is NOT unknown (sanity: the pipe works).
    assert dz.intervention_effect(by_mol["CHEMBL_M1"]["action_type_source"])[0] == \
        dz.FUNCTIONAL_INHIBITION


def test_max_phase_is_exact_not_coarsened():
    r = _rows()["ENSG_DRUGGED"]
    by_mol = {d["molecule_chembl_id"]: d for d in r["drugs"]}
    # 0.5 survives as an exact value, distinct from any integer bucket.
    assert by_mol["CHEMBL_M2"]["max_phase_source"] == "0.5"
    assert by_mol["CHEMBL_M2"]["max_phase_canonical"] != \
        by_mol["CHEMBL_M1"]["max_phase_canonical"]
    assert "development_state" not in by_mol["CHEMBL_M2"]  # not coarsened


def test_coverage_summary_splits_namespace_and_never_claims_11526_ensg():
    summ = us.coverage_summary(us.build_store_rows(
        universe_targets=UNIVERSE, resolution=RESOLUTION, evidence_by_target=EVIDENCE))
    assert summ["n_targets_total"] == 4
    assert summ["n_ensg"] == 3
    assert summ["n_symbol_only_unsupported_namespace"] == 1
    assert summ["n_drug_evidence"] == 1
    assert summ["n_no_drug_evidence"] == 2
    # the ENSG denominator is reported separately from the total; they are not conflated
    assert summ["n_ensg"] + summ["n_symbol_only_unsupported_namespace"] == \
        summ["n_targets_total"]


def test_build_is_order_independent():
    a = us.build_store_rows(universe_targets=UNIVERSE, resolution=RESOLUTION,
                            evidence_by_target=EVIDENCE)
    b = us.build_store_rows(universe_targets=list(reversed(UNIVERSE)),
                            resolution=RESOLUTION, evidence_by_target=EVIDENCE)
    assert sorted(a, key=lambda r: r["target_id"]) == \
        sorted(b, key=lambda r: r["target_id"])
