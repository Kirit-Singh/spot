"""The universe manifest is RUN-INDEPENDENT (no direct_run_id, no per-arm queue): it binds
source releases + the ENSG universe, proves its own identity, and a per-run VIEW is a pure
selection over the store that re-acquires nothing.
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(_HERE, "..", "analysis")))

from druglink import universe_manifest as um     # noqa: E402
from druglink import universe_store as us         # noqa: E402


def _manifest():
    return um.build_universe_manifest(
        chembl_release="CHEMBL_37", chembl_source_sha256="a" * 64,
        uniprot_release="2026_02", uniprot_source_sha256="b" * 64,
        extraction_query_sha256="c" * 64,
        universe_targets=[{"target_id": "ENSG1", "target_id_namespace": "ensembl_gene"},
                          {"target_id": "MTRNR2L1", "target_id_namespace": "symbol"}],
        coverage={"n_targets_total": 2, "n_ensg": 1,
                  "n_symbol_only_unsupported_namespace": 1,
                  "n_drug_evidence": 1, "n_no_drug_evidence": 0},
        store_rows_sha256="d" * 64)


def test_manifest_is_run_independent():
    m = _manifest()
    assert "direct_run_id" not in json.dumps(m)          # NOT bound to any run
    assert m["run_independent"] is True
    assert m["schema_version"] == "spot.stage03_universe_manifest.v1"


def test_manifest_binds_both_source_releases_with_verified_licenses():
    r = _manifest()["releases"]
    assert r["chembl"]["source_release"] == "CHEMBL_37"
    assert r["chembl"]["source_sha256"] == "a" * 64
    assert r["chembl"]["license"] == "CC BY-SA 3.0"
    assert r["uniprot"]["source_release"] == "2026_02"
    assert r["uniprot"]["source_sha256"] == "b" * 64
    assert r["uniprot"]["license"] == "CC BY 4.0"


def test_manifest_binds_universe_and_coverage_split():
    m = _manifest()
    assert m["universe_binding"]["n_ensg"] == 1
    assert m["universe_binding"]["n_symbol_only"] == 1
    assert len(m["universe_binding"]["universe_targets_sha256"]) == 64
    assert m["coverage"]["n_ensg"] == 1


def test_manifest_proves_its_own_identity():
    m = _manifest()
    claimed = m["content_sha256"]
    assert um.content_sha256(m) == claimed          # recomputes to the same hash
    m2 = dict(m)
    m2["universe_binding"] = dict(m2["universe_binding"], n_ensg=999)
    assert um.content_sha256(m2) != claimed         # tamper is detected


def test_manifest_identity_is_timestamp_independent():
    a = _manifest()
    b = _manifest()
    # created_at differs run-to-run, but the content identity must not.
    assert um.content_sha256(a) == um.content_sha256(b)


# ---- per-run view over the run-independent store -------------------------- #

STORE = [
    {"target_id": "ENSG1", "target_id_namespace": "ensembl_gene",
     "disposition": "drug_evidence", "drugs": [{"molecule_chembl_id": "M1"}]},
    {"target_id": "ENSG2", "target_id_namespace": "ensembl_gene",
     "disposition": "no_drug_evidence", "drugs": []},
]


def test_view_is_a_pure_selection_order_independent():
    a = us.view_for_queue(store_rows=STORE, target_queue=["ENSG1", "ENSG2"])
    b = us.view_for_queue(store_rows=STORE, target_queue=["ENSG2", "ENSG1"])
    assert a["view_id"] == b["view_id"]                 # rank/order independent
    assert {r["target_id"] for r in a["rows"]} == {"ENSG1", "ENSG2"}


def test_view_reports_missing_never_fabricates():
    v = us.view_for_queue(store_rows=STORE, target_queue=["ENSG1", "ENSG_NOT_IN_STORE"])
    assert v["missing_from_store"] == ["ENSG_NOT_IN_STORE"]
    assert {r["target_id"] for r in v["rows"]} == {"ENSG1"}
    assert v["n_requested"] == 2 and v["n_covered"] == 1


def test_view_deduplicates_queue():
    v = us.view_for_queue(store_rows=STORE, target_queue=["ENSG1", "ENSG1"])
    assert len(v["rows"]) == 1
