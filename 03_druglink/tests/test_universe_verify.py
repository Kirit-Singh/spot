"""Audit gate 10: a generator-INDEPENDENT verifier over a built store + manifest, with
tamper mutations. The verifier reuses only the shared content-addressing leaf
(``hashing``); it never imports the build logic (store/identity/eligibility/extract).
"""
from __future__ import annotations

import copy
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "analysis")))

from druglink import universe_verify as uv        # noqa: E402
from druglink import universe_manifest as um       # test builds valid input with generator
from druglink import universe_store as us          # noqa: E402
from druglink.hashing import content_hash          # noqa: E402


def _valid():
    universe = [{"target_id": "ENSG1", "target_id_namespace": "ensembl_gene"},
                {"target_id": "MTRNR2L1", "target_id_namespace": "symbol"}]
    store = [
        {"target_id": "ENSG1", "target_id_namespace": "ensembl_gene",
         "disposition": "drug_evidence", "identity": {"identity_status": "resolved"},
         "no_evidence_reason": None,
         "drugs": [{"source_row_id": 101, "molecule_chembl_id": "M1",
                    "action_type_source": "INHIBITOR", "max_phase_source": "4",
                    "max_phase_canonical": "4", "inchikey": "IK1",
                    "cross_ref_provenance": {"pubchem_cid": "not_in_pinned_sqlite_source",
                                             "unii": "not_in_pinned_sqlite_source"}}]},
        {"target_id": "MTRNR2L1", "target_id_namespace": "symbol",
         "disposition": "unsupported_namespace", "identity": None,
         "no_evidence_reason": "symbol_only_target_no_ensembl_xref_join", "drugs": []},
    ]
    manifest = um.build_universe_manifest(
        chembl_release="CHEMBL_37", chembl_source_sha256="a" * 64,
        uniprot_release="2026_02", uniprot_source_sha256="b" * 64,
        extraction_query_sha256="c" * 64, universe_targets=universe,
        coverage=us.coverage_summary(store),
        store_rows_sha256=content_hash(store))
    return store, manifest, universe


def test_valid_store_passes():
    store, manifest, universe = _valid()
    r = uv.verify(store_rows=store, manifest=manifest, universe_targets=universe)
    assert r["ok"] is True, r["violations"]


def test_direction_field_on_a_drug_is_rejected():
    store, manifest, universe = _valid()
    store[0]["drugs"][0]["direction"] = "functional_inhibition"   # forbidden
    r = uv.verify(store_rows=store, manifest=manifest, universe_targets=universe)
    assert r["ok"] is False


def test_development_state_coarsening_is_rejected():
    store, manifest, universe = _valid()
    store[0]["drugs"][0]["development_state"] = "approved"
    r = uv.verify(store_rows=store, manifest=manifest, universe_targets=universe)
    assert r["ok"] is False


def test_pubchem_field_is_rejected():
    store, manifest, universe = _valid()
    store[0]["drugs"][0]["pubchem_cid"] = "999"
    r = uv.verify(store_rows=store, manifest=manifest, universe_targets=universe)
    assert r["ok"] is False


def test_phase_based_rank_field_is_rejected():
    store, manifest, universe = _valid()
    store[0]["drugs"][0]["rank"] = 1        # a phase-derived rank must never appear
    r = uv.verify(store_rows=store, manifest=manifest, universe_targets=universe)
    assert r["ok"] is False


def test_duplicate_mec_id_within_target_is_rejected():
    store, manifest, universe = _valid()
    dup = copy.deepcopy(store[0]["drugs"][0])
    store[0]["drugs"].append(dup)           # same mec_id twice: collapse/dup
    manifest2 = um.build_universe_manifest(
        chembl_release="CHEMBL_37", chembl_source_sha256="a" * 64,
        uniprot_release="2026_02", uniprot_source_sha256="b" * 64,
        extraction_query_sha256="c" * 64, universe_targets=universe,
        coverage=manifest["coverage"], store_rows_sha256=content_hash(store))
    r = uv.verify(store_rows=store, manifest=manifest2, universe_targets=universe)
    assert r["ok"] is False


def test_symbol_row_claiming_drug_evidence_is_rejected():
    store, manifest, universe = _valid()
    store[1]["disposition"] = "drug_evidence"      # a symbol claiming ENSG-style coverage
    r = uv.verify(store_rows=store, manifest=manifest, universe_targets=universe)
    assert r["ok"] is False


def test_store_rows_hash_drift_is_rejected():
    store, manifest, universe = _valid()
    store[0]["drugs"][0]["action_type_source"] = "AGONIST"   # content changed silently
    r = uv.verify(store_rows=store, manifest=manifest, universe_targets=universe)
    assert r["ok"] is False   # recorded store_rows_sha256 no longer matches


def test_manifest_self_identity_tamper_is_rejected():
    store, manifest, universe = _valid()
    manifest["universe_binding"]["n_ensg"] = 999
    r = uv.verify(store_rows=store, manifest=manifest, universe_targets=universe)
    assert r["ok"] is False


def test_coverage_that_conflates_ensg_with_total_is_rejected():
    store, manifest, universe = _valid()
    # claim all-ENSG coverage of the total (i.e. deny the 4 symbol split)
    manifest["coverage"] = dict(manifest["coverage"], n_ensg=2,
                                n_symbol_only_unsupported_namespace=0)
    manifest["content_sha256"] = um.content_sha256(manifest)   # re-seal the lie
    r = uv.verify(store_rows=store, manifest=manifest, universe_targets=universe)
    assert r["ok"] is False    # coverage must match the typed universe rows
