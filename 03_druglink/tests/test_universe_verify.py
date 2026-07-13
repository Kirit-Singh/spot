"""Audit gate 10: a generator-INDEPENDENT verifier over a built store + manifest, with
tamper mutations. The verifier reuses only the shared content-addressing leaf
(``hashing``); it never imports the build logic (store/identity/eligibility/extract).
"""
from __future__ import annotations

import copy
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "analysis")))

from druglink import universe_verify as uv        # noqa: E402
from druglink import universe_manifest as um       # test builds valid input with generator
from druglink import universe_store as us          # noqa: E402
from druglink import universe_target_eligibility as te  # noqa: E402
from druglink.hashing import content_hash          # noqa: E402


def _elig_target(**over):
    t = {"target_chembl_id": "CHEMBL_T", "target_type": "SINGLE PROTEIN",
         "tax_id": 9606, "species_group_flag": 0,
         "components": [{"component_type": "PROTEIN", "tax_id": 9606,
                         "homologue": 0, "accession": "P1"}]}
    t.update(over)
    return t


def _store_manifest_with_eligibility(art):
    store, _, universe = _valid()
    manifest = um.build_universe_manifest(
        chembl_release="CHEMBL_37", chembl_source_sha256="a" * 64,
        uniprot_release="2026_02", uniprot_source_sha256="b" * 64,
        extraction_query_sha256="c" * 64, universe_targets=universe,
        coverage=us.coverage_summary(store), store_rows_sha256=content_hash(store),
        eligibility_evidence_sha256=content_hash(art))
    return store, manifest, universe


def test_actual_eligibility_artifact_is_hashed_and_replayed():
    art = te.eligibility_evidence_artifact([te.evidence_record(_elig_target())])
    store, manifest, universe = _store_manifest_with_eligibility(art)
    assert uv.verify(store_rows=store, manifest=manifest, universe_targets=universe,
                     eligibility_evidence=art)["ok"] is True


def test_altered_eligibility_evidence_is_refused():
    art = te.eligibility_evidence_artifact([te.evidence_record(_elig_target())])
    store, manifest, universe = _store_manifest_with_eligibility(art)
    # mutate a predicate field without touching manifest/store: hash drifts AND the
    # independent verdict replay disagrees with the recorded disposition.
    art["records"][0]["tax_id"] = 10090
    assert uv.verify(store_rows=store, manifest=manifest, universe_targets=universe,
                     eligibility_evidence=art)["ok"] is False


def test_public_provenance_mutated_on_disk_is_refused_by_verify_from_disk(tmp_path):
    # post-generation: alter source_provenance.public.json on disk while leaving the
    # manifest/store untouched. verify_from_disk must reopen+hash it and fail closed.
    store, _, universe = _valid()
    prov = [{"name": "chembl_sqlite", "url": "https://x", "acquired_sha256": "a" * 64}]
    art = te.eligibility_evidence_artifact([te.evidence_record(_elig_target())])
    manifest = um.build_universe_manifest(
        chembl_release="CHEMBL_37", chembl_source_sha256="a" * 64,
        uniprot_release="2026_02", uniprot_source_sha256="b" * 64,
        extraction_query_sha256="c" * 64, universe_targets=universe,
        coverage=us.coverage_summary(store), store_rows_sha256=content_hash(store),
        eligibility_evidence_sha256=content_hash(art),
        public_source_provenance_sha256=content_hash(prov))
    d = str(tmp_path)
    for name, obj in [("universe_store.rows.json", store),
                      ("target_eligibility_evidence.json", art),
                      ("source_provenance.public.json", prov)]:
        with open(os.path.join(d, name), "w") as fh:
            json.dump(obj, fh)
    assert uv.verify_from_disk(store_dir=d, manifest=manifest,
                               universe_targets=universe)["ok"] is True
    with open(os.path.join(d, "source_provenance.public.json"), "w") as fh:
        json.dump([dict(prov[0], acquired_sha256="b" * 64)], fh)   # tamper on disk
    r = uv.verify_from_disk(store_dir=d, manifest=manifest, universe_targets=universe)
    assert r["ok"] is False
    assert "public_source_provenance_hash_drift" in r["violations"]


def test_provenance_deleted_on_disk_is_refused_by_verify_from_disk(tmp_path):
    # deletion (not just mutation): a REQUIRED artifact removed on disk -> named refusal,
    # never an exception. verify_from_disk is called directly on the real directory.
    store, _, universe = _valid()
    prov = [{"name": "chembl_sqlite", "url": "https://x", "acquired_sha256": "a" * 64}]
    art = te.eligibility_evidence_artifact([te.evidence_record(_elig_target())])
    manifest = um.build_universe_manifest(
        chembl_release="CHEMBL_37", chembl_source_sha256="a" * 64,
        uniprot_release="2026_02", uniprot_source_sha256="b" * 64,
        extraction_query_sha256="c" * 64, universe_targets=universe,
        coverage=us.coverage_summary(store), store_rows_sha256=content_hash(store),
        eligibility_evidence_sha256=content_hash(art),
        public_source_provenance_sha256=content_hash(prov))
    d = str(tmp_path)
    for name, obj in [("universe_store.rows.json", store),
                      ("target_eligibility_evidence.json", art),
                      ("source_provenance.public.json", prov)]:
        with open(os.path.join(d, name), "w") as fh:
            json.dump(obj, fh)
    assert uv.verify_from_disk(store_dir=d, manifest=manifest,
                               universe_targets=universe)["ok"] is True
    os.remove(os.path.join(d, "source_provenance.public.json"))   # DELETE on disk
    r = uv.verify_from_disk(store_dir=d, manifest=manifest, universe_targets=universe)
    assert r["ok"] is False
    assert "missing_artifact:source_provenance.public.json" in r["violations"]


def test_ambiguous_assertion_missing_named_disposition_is_refused():
    store, _, universe = _ambiguous_store_and_manifest(False)
    store[0]["ambiguous_source_assertions"][0].pop("ambiguity_disposition")
    manifest = um.build_universe_manifest(
        chembl_release="CHEMBL_37", chembl_source_sha256="a" * 64,
        uniprot_release="2026_02", uniprot_source_sha256="b" * 64,
        extraction_query_sha256="c" * 64, universe_targets=universe,
        coverage=us.coverage_summary(store), store_rows_sha256=content_hash(store))
    assert uv.verify(store_rows=store, manifest=manifest,
                     universe_targets=universe)["ok"] is False


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


def _ambiguous_store_and_manifest(rankable_flag):
    store = [{"target_id": "ENSG_A", "target_id_namespace": "ensembl_gene",
              "disposition": "ambiguous_identity", "identity": None, "drugs": [],
              "no_evidence_reason": "shared_uniprot_accession_maps_to_multiple_genes",
              "ambiguous_source_assertions": [
                  {"source_row_id": 6210, "action_type_source": "INHIBITOR",
                   "general_gene_rankable": rankable_flag,
                   "ambiguity_disposition": "ambiguous_identity_nonrankable"}]}]
    universe = [{"target_id": "ENSG_A", "target_id_namespace": "ensembl_gene"}]
    manifest = um.build_universe_manifest(
        chembl_release="CHEMBL_37", chembl_source_sha256="a" * 64,
        uniprot_release="2026_02", uniprot_source_sha256="b" * 64,
        extraction_query_sha256="c" * 64, universe_targets=universe,
        coverage=us.coverage_summary(store), store_rows_sha256=content_hash(store))
    return store, manifest, universe


def test_nested_ambiguous_assertion_marked_rankable_is_refused():
    # even with internally-consistent hashes, a nested ambiguous assertion claiming
    # general_gene_rankable=True is a flattening hazard and must be refused.
    store, manifest, universe = _ambiguous_store_and_manifest(True)
    assert uv.verify(store_rows=store, manifest=manifest,
                     universe_targets=universe)["ok"] is False


def test_nested_ambiguous_assertion_marked_nonrankable_passes():
    store, manifest, universe = _ambiguous_store_and_manifest(False)
    assert uv.verify(store_rows=store, manifest=manifest,
                     universe_targets=universe)["ok"] is True


def test_coverage_that_conflates_ensg_with_total_is_rejected():
    store, manifest, universe = _valid()
    # claim all-ENSG coverage of the total (i.e. deny the 4 symbol split)
    manifest["coverage"] = dict(manifest["coverage"], n_ensg=2,
                                n_symbol_only_unsupported_namespace=0)
    manifest["content_sha256"] = um.content_sha256(manifest)   # re-seal the lie
    r = uv.verify(store_rows=store, manifest=manifest, universe_targets=universe)
    assert r["ok"] is False    # coverage must match the typed universe rows
