"""Offline bulk extractor: pinned ChEMBL 37 SQLite + UniProt idmapping -> universe store.

No network, no per-gene crawl. Reads the pinned SQLite and the pinned idmapping file,
applies the frozen human-single-protein eligibility gate
(:mod:`druglink.universe_target_eligibility`), resolves identity conflict-aware
(:mod:`druglink.universe_identity`), keeps one assertion per ``mec_id`` and exact
``max_phase``, and builds the namespace-split store (:mod:`druglink.universe_store`).

``max_phase`` is read as ``CAST(max_phase AS TEXT)`` so the exact source string is
preserved and no float can drift. Direction is NEVER computed here — ``action_type`` is
carried verbatim and translated only at view time by the frozen ``direction.py``.
"""
from __future__ import annotations

import gzip
import sqlite3
from typing import Any

from .hashing import content_hash
from .universe_identity import resolve_identity
from .universe_store import build_store_rows, coverage_summary
from .universe_target_eligibility import (ELIGIBLE_SINGLE_PROTEIN_SQL,
                                          ELIGIBILITY_POLICY_VERSION,
                                          eligibility_evidence_artifact,
                                          evidence_record, evaluate)

EXTRACT_POLICY_VERSION = "stage3-universe-extract-v1"

# Frozen SQL, hashed into extraction provenance. Candidate pool = SINGLE PROTEIN targets;
# the full six predicates + one-component cardinality are enforced in evaluate().
Q_TARGETS = (
    "SELECT td.tid, td.chembl_id, td.target_type, td.tax_id, td.species_group_flag, "
    "tc.homologue, cs.component_type, cs.tax_id AS comp_tax_id, cs.accession "
    "FROM target_dictionary td "
    "LEFT JOIN target_components tc ON td.tid = tc.tid "
    "LEFT JOIN component_sequences cs ON tc.component_id = cs.component_id "
    "WHERE td.target_type = 'SINGLE PROTEIN'")

Q_MECHANISMS = (
    "SELECT dm.mec_id, dm.molregno, td.chembl_id AS target_chembl_id, dm.action_type, "
    "dm.mechanism_of_action, dm.molecular_mechanism, dm.direct_interaction, "
    "dm.disease_efficacy, dm.selectivity_comment, dm.variant_id, "
    "md.chembl_id AS molecule_chembl_id, md.pref_name, "
    "CAST(md.max_phase AS TEXT) AS max_phase, md.molecule_type, "
    "cs.standard_inchi_key AS inchikey "
    "FROM drug_mechanism dm "
    "JOIN target_dictionary td ON dm.tid = td.tid "
    "JOIN molecule_dictionary md ON dm.molregno = md.molregno "
    "LEFT JOIN compound_structures cs ON dm.molregno = cs.molregno")

Q_MECH_REFS = "SELECT mec_id, ref_id, ref_url FROM mechanism_refs"

ENSEMBL_XREF_ID_TYPE = "Ensembl"     # gene-level ENSG (versioned); Ensembl_TRS/PRO excluded


def parse_idmapping_ensembl(path: str) -> list[tuple[str, str]]:
    """(ensg_unversioned, accession) from the UniProt Ensembl gene xref.

    Only the ``Ensembl`` id_type is a gene (ENSG); ``Ensembl_TRS``/``Ensembl_PRO`` are
    transcript/protein and excluded. The ``.NN`` version suffix is stripped so the key
    matches the DE object's unversioned ENSG.
    """
    pairs: set[tuple[str, str]] = set()
    opener = gzip.open if path.endswith(".gz") else open
    with opener(path, "rt") as fh:
        for line in fh:
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 3:
                continue
            acc, id_type, value = parts
            if id_type != ENSEMBL_XREF_ID_TYPE or not value.startswith("ENSG"):
                continue
            pairs.add((value.split(".", 1)[0], acc))
    return sorted(pairs)


def _dedup(seq):
    out, seen = [], set()
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def eligible_accession_targets(
        conn: sqlite3.Connection) -> tuple[list[tuple[str, str]], list[dict[str, Any]]]:
    """Apply the frozen eligibility gate; return eligible (accession, target_chembl_id)
    pairs and NAMED rejection dispositions for the candidate pool."""
    rows = conn.execute(Q_TARGETS).fetchall()
    by_tid: dict[Any, dict[str, Any]] = {}
    for (tid, chembl_id, ttype, tax_id, sgf, homologue, ctype, comp_tax, acc) in rows:
        t = by_tid.setdefault(tid, {
            "target_chembl_id": chembl_id, "target_type": ttype, "tax_id": tax_id,
            "species_group_flag": sgf, "components": []})
        if ctype is not None or acc is not None or comp_tax is not None \
                or homologue is not None:
            t["components"].append({"component_type": ctype, "tax_id": comp_tax,
                                    "homologue": homologue, "accession": acc})

    pairs: list[tuple[str, str]] = []
    evidence: list[dict[str, Any]] = []
    for t in by_tid.values():
        verdict = evaluate(t)
        evidence.append(evidence_record(t, verdict))   # accepted AND rejected
        if verdict["eligible"]:
            pairs.append((verdict["accession"], t["target_chembl_id"]))
    return sorted(set(pairs)), sorted(evidence,
                                      key=lambda r: r["target_chembl_id"] or "")


def mechanisms_by_target(conn: sqlite3.Connection,
                         target_chembl_ids: set[str]) -> dict[str, list[dict[str, Any]]]:
    """One evidence dict per drug_mechanism row (mec_id), for eligible targets only."""
    refs: dict[Any, list[str]] = {}
    for mec_id, ref_id, ref_url in conn.execute(Q_MECH_REFS).fetchall():
        refs.setdefault(mec_id, []).append(ref_id or ref_url)

    out: dict[str, list[dict[str, Any]]] = {}
    for r in conn.execute(Q_MECHANISMS).fetchall():
        (mec_id, molregno, target_chembl_id, action_type, moa, molecular_mechanism,
         direct_interaction, disease_efficacy, selectivity_comment, variant_id,
         molecule_chembl_id, pref_name, max_phase, molecule_type, inchikey) = r
        if target_chembl_id not in target_chembl_ids:
            continue
        out.setdefault(target_chembl_id, []).append({
            "mec_id": mec_id, "molecule_chembl_id": molecule_chembl_id,
            "pref_name": pref_name, "action_type_source": action_type,
            "mechanism_of_action": moa,
            "molecular_mechanism": None if molecular_mechanism is None
            else bool(molecular_mechanism),
            "direct_interaction": None if direct_interaction is None
            else bool(direct_interaction),
            "disease_efficacy": None if disease_efficacy is None
            else bool(disease_efficacy),
            "variant_id": variant_id, "selectivity_comment": selectivity_comment,
            "mechanism_refs": _dedup(refs.get(mec_id, [])),
            "molecule_type": molecule_type, "inchikey": inchikey,
            "max_phase": max_phase,
        })
    return out


def extraction_query_sha256() -> str:
    """Content hash of the frozen extraction method: SQL text + eligibility policy."""
    return content_hash({
        "extract_policy_version": EXTRACT_POLICY_VERSION,
        "eligibility_policy_version": ELIGIBILITY_POLICY_VERSION,
        "eligible_single_protein_sql": ELIGIBLE_SINGLE_PROTEIN_SQL,
        "q_targets": Q_TARGETS, "q_mechanisms": Q_MECHANISMS,
        "q_mech_refs": Q_MECH_REFS, "ensembl_xref_id_type": ENSEMBL_XREF_ID_TYPE,
    })


def build_from_sqlite(*, sqlite_path: str, idmapping_path: str,
                      universe_targets: list[dict[str, str]]) -> dict[str, Any]:
    """Full offline build: pinned SQLite + idmapping -> namespace-split universe store."""
    gene_accessions = parse_idmapping_ensembl(idmapping_path)
    conn = sqlite3.connect(sqlite_path)
    try:
        pairs, eligibility_records = eligible_accession_targets(conn)
        universe_ensg = {t["target_id"] for t in universe_targets
                         if t["target_id_namespace"] == "ensembl_gene"}
        resolution = resolve_identity(universe_ensg=universe_ensg,
                                      gene_accessions=gene_accessions,
                                      accession_targets=pairs)
        wanted_targets = {tid for g in resolution.values() for tid in g["targets"]}
        evidence = mechanisms_by_target(conn, wanted_targets)
    finally:
        conn.close()

    rows = build_store_rows(universe_targets=universe_targets, resolution=resolution,
                            evidence_by_target=evidence)
    elig_art = eligibility_evidence_artifact(eligibility_records)
    return {
        "rows": rows,
        "coverage": coverage_summary(rows),
        "eligibility_evidence": elig_art,
        "eligibility_evidence_sha256": content_hash(elig_art),
        "extraction_query_sha256": extraction_query_sha256(),
    }
