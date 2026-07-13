"""End-to-end offline extraction over a SYNTHETIC ChEMBL SQLite in the real schema, plus
the UniProt Ensembl-xref parser. This is the fixture gate that runs before any real 5.76 GB
extraction: eligibility predicates, version-stripped ENSG join, one-assertion-per-mec_id,
and the namespace-split store all exercised on tiny deterministic data.
"""
from __future__ import annotations

import gzip
import os
import sqlite3
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "analysis")))

from druglink import universe_extract as ux  # noqa: E402


def _build_chembl_fixture(path: str) -> None:
    c = sqlite3.connect(path)
    c.executescript("""
    CREATE TABLE target_dictionary(tid INT, chembl_id TEXT, target_type TEXT,
        tax_id INT, organism TEXT, pref_name TEXT, species_group_flag INT);
    CREATE TABLE target_components(tid INT, component_id INT, homologue INT);
    CREATE TABLE component_sequences(component_id INT, component_type TEXT, tax_id INT,
        accession TEXT);
    CREATE TABLE drug_mechanism(mec_id INT, molregno INT, tid INT, action_type TEXT,
        mechanism_of_action TEXT, molecular_mechanism INT, direct_interaction INT,
        disease_efficacy INT, mechanism_comment TEXT, selectivity_comment TEXT,
        variant_id INT);
    CREATE TABLE molecule_dictionary(molregno INT, chembl_id TEXT, pref_name TEXT,
        max_phase, molecule_type TEXT, withdrawn_flag INT);
    CREATE TABLE compound_structures(molregno INT, standard_inchi_key TEXT);
    CREATE TABLE mechanism_refs(mecref_id INT, mec_id INT, ref_id TEXT, ref_url TEXT);
    """)
    # T1: eligible human single protein, one component P1
    c.execute("INSERT INTO target_dictionary VALUES(1,'CHEMBL_T1','SINGLE PROTEIN',9606,'Homo sapiens','Kinase A',0)")
    c.execute("INSERT INTO target_components VALUES(1,11,0)")
    c.execute("INSERT INTO component_sequences VALUES(11,'PROTEIN',9606,'P1')")
    # T2: mouse single protein (must be rejected)
    c.execute("INSERT INTO target_dictionary VALUES(2,'CHEMBL_T2','SINGLE PROTEIN',10090,'Mus musculus','MouseK',0)")
    c.execute("INSERT INTO target_components VALUES(2,22,0)")
    c.execute("INSERT INTO component_sequences VALUES(22,'PROTEIN',10090,'P2')")
    # T3: human but TWO components (must be rejected by cardinality)
    c.execute("INSERT INTO target_dictionary VALUES(3,'CHEMBL_T3','SINGLE PROTEIN',9606,'Homo sapiens','TwoComp',0)")
    c.executemany("INSERT INTO target_components VALUES(?,?,?)", [(3,31,0),(3,32,0)])
    c.executemany("INSERT INTO component_sequences VALUES(?,?,?,?)",
                  [(31,'PROTEIN',9606,'P3a'),(32,'PROTEIN',9606,'P3b')])
    # molecules
    c.execute("INSERT INTO molecule_dictionary VALUES(1,'CHEMBL_M1','DrugA',4,'Small molecule',0)")
    c.execute("INSERT INTO compound_structures VALUES(1,'IK1')")
    # two mechanism assertions on T1 for the SAME molecule/action, different mec_id
    c.execute("INSERT INTO drug_mechanism VALUES(101,1,1,'INHIBITOR','moa',1,1,1,NULL,NULL,NULL)")
    c.execute("INSERT INTO drug_mechanism VALUES(102,1,1,'INHIBITOR','moa',1,1,1,NULL,'variant-selective',9)")
    # a mechanism on the mouse target (must never reach the store)
    c.execute("INSERT INTO drug_mechanism VALUES(201,1,2,'INHIBITOR','moaM',1,1,1,NULL,NULL,NULL)")
    c.execute("INSERT INTO mechanism_refs VALUES(1,101,'PMID:1','http://x/1')")
    c.commit(); c.close()


def _write_idmapping(path: str) -> None:
    # UniProt idmapping.dat.gz rows: accession \t id_type \t id. ENSG is VERSIONED here.
    lines = [
        "P1\tEnsembl\tENSG_A.7",           # eligible -> gene ENSG_A
        "P1\tEnsembl_PRO\tENSP_A.1",       # not gene-level; ignored
        "P2\tEnsembl\tENSG_MOUSE.2",       # mouse accession's gene (target rejected anyway)
        "P1\tGene_Name\tKINA",             # not an Ensembl xref; ignored
    ]
    with gzip.open(path, "wt") as fh:
        fh.write("\n".join(lines) + "\n")


def test_parse_idmapping_strips_version_and_filters_to_ensembl_gene(tmp_path):
    p = str(tmp_path / "idmap.dat.gz")
    _write_idmapping(p)
    pairs = ux.parse_idmapping_ensembl(p)
    assert ("ENSG_A", "P1") in pairs
    assert ("ENSG_MOUSE", "P2") in pairs
    # transcript/protein/name xrefs are excluded; versions are stripped
    assert all(not g.endswith(".1") and "ENSP" not in g for g, _ in pairs)


def test_eligible_targets_apply_predicates(tmp_path):
    db = str(tmp_path / "chembl.db")
    _build_chembl_fixture(db)
    conn = sqlite3.connect(db)
    pairs, dispositions = ux.eligible_accession_targets(conn)
    # only the human one-component protein is eligible
    assert ("P1", "CHEMBL_T1") in pairs
    assert not any(t == "CHEMBL_T2" for _, t in pairs)   # mouse rejected
    assert not any(t == "CHEMBL_T3" for _, t in pairs)   # two-component rejected
    reasons = {d["target_chembl_id"]: d["disposition"] for d in dispositions}
    assert reasons["CHEMBL_T2"] == "reject_nonhuman_target_taxon"
    assert reasons["CHEMBL_T3"] == "reject_component_cardinality"
    conn.close()


def test_end_to_end_build_from_sqlite(tmp_path):
    db = str(tmp_path / "chembl.db"); _build_chembl_fixture(db)
    idm = str(tmp_path / "idmap.dat.gz"); _write_idmapping(idm)
    universe = [{"target_id": "ENSG_A", "target_id_namespace": "ensembl_gene"},
                {"target_id": "ENSG_UNDRUGGED", "target_id_namespace": "ensembl_gene"},
                {"target_id": "MTRNR2L1", "target_id_namespace": "symbol"}]
    res = ux.build_from_sqlite(sqlite_path=db, idmapping_path=idm,
                               universe_targets=universe)
    rows = {r["target_id"]: r for r in res["rows"]}
    # ENSG_A got drug evidence via P1 -> CHEMBL_T1. mec 101 is general (NULL variant) ->
    # rankable; mec 102 is variant-specific (variant_id=9) -> preserved non-rankable. Both
    # retained in their proper lanes.
    assert rows["ENSG_A"]["disposition"] == "drug_evidence"
    assert {d["source_row_id"] for d in rows["ENSG_A"]["drugs"]} == {101}
    assert {a["source_row_id"]
            for a in rows["ENSG_A"]["variant_specific_assertions"]} == {102}
    assert rows["ENSG_A"]["drugs"][0]["max_phase_source"] == "4"
    # mouse mechanism 201 never leaks into either lane
    assert all(d["source_row_id"] != 201 for d in rows["ENSG_A"]["drugs"])
    assert all(a["source_row_id"] != 201
               for a in rows["ENSG_A"]["variant_specific_assertions"])
    assert rows["ENSG_UNDRUGGED"]["disposition"] == "no_drug_evidence"
    assert rows["MTRNR2L1"]["disposition"] == "unsupported_namespace"
    # coverage split + a frozen extraction-query hash are emitted
    assert res["coverage"]["n_symbol_only_unsupported_namespace"] == 1
    assert len(res["extraction_query_sha256"]) == 64
