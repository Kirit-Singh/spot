"""Adversarial provenance attacks for the GBM disease-context layer (packaging-audit repair).

Every displayed disease number must trace to the exact pinned bytes (endpoint, HTTP status,
API/data version, raw sha256, licence). DepMap coverage may not be claimed while the official
26Q1 catalog is empty. The dependency threshold must match the FROZEN engine exactly (strict
> 0.5). No public artifact may leak a machine-local path. Nothing is fabricated; ranks are
never touched.
"""
from __future__ import annotations

from druglink.gbm_context import states as st
from druglink.gbm_context import depmap_bridge as db
from druglink.gbm_context import build_gbm_context as bg
from druglink.gbm_context import GbmContextError
from verifier import cache_sweep as cs
import pytest


def _fetch_like(**over):
    base = {"evaluated": True, "data_version": "26.06", "api_version": "26.6.3",
            "endpoint": "https://api.platform.opentargets.org/api/v4/graphql",
            "http_status": 200, "license": "CC0 1.0",
            "raw_sha256": "0ac55a97bb9a14a95b9fe9f2469063021d3b14cd815766c2aa334ddc0e0dd6df",
            "response_artifact": "ot_ENSG00000146648_0ac55a97.json",
            "diseases": {"MONDO_0018177": {"name": "glioblastoma",
                         "reported_overall_association_score": 0.6544,
                         "datatype_evidence": {"literature": 0.997}}}}
    base.update(over)
    return base


# --- attack 1: a disease number with no trace-to-bytes is a defect ------------------- #
def test_disease_axis_carries_full_source_provenance():
    r = st.disease_association_state(_fetch_like())
    sp = r["source_provenance"]
    assert sp["endpoint"].startswith("https://api.platform.opentargets.org")
    assert sp["http_status"] == 200
    assert sp["api_version"] == "26.6.3"
    assert sp["data_version"] == "26.06"
    assert sp["raw_sha256"].startswith("0ac55a97")
    assert sp["license"] == "CC0 1.0"
    assert sp["response_artifact"] == "ot_ENSG00000146648_0ac55a97.json"


def test_not_evaluated_disease_still_records_endpoint_and_status():
    r = st.disease_association_state(
        {"evaluated": False, "reason": "http_503", "http_status": 503,
         "endpoint": "https://api.platform.opentargets.org/api/v4/graphql", "diseases": {}})
    assert r["state"] == st.NOT_EVALUATED
    assert r["source_provenance"]["http_status"] == 503
    assert r["source_provenance"]["endpoint"].startswith("https://api.platform")


def test_score_traces_to_same_bytes_as_artifact():
    r = st.disease_association_state(_fetch_like())
    # the score displayed and the sha of the pinned response are bound in one record
    assert r["diseases"]["MONDO_0018177"]["reported_overall_association_score"] == 0.6544
    assert r["source_provenance"]["raw_sha256"] == _fetch_like()["raw_sha256"]


# --- attack 2: strict frozen-engine threshold --------------------------------------- #
def test_dependency_threshold_is_strict_greater_than_matching_frozen_engine():
    assert db.DEPENDENCY_PROB_THRESHOLD == 0.5
    assert db.DEPENDENCY_PROB_STRICT is True
    assert db.DEPENDENCY_PROB_COMPARATOR == ">"
    assert db.is_dependent_line(0.5) is False          # boundary is NOT dependent (strict)
    assert db.is_dependent_line(0.5000004) is True
    assert db.is_dependent_line(0.49) is False
    assert db.is_dependent_line(None) is None


def test_states_records_strict_comparator():
    r = st.tumor_dependency_state({"evaluated": True, "n_gbm_glioma_lines_evaluated": 6,
                                   "n_lines_dependent": 4, "median_gene_effect": -0.7})
    assert r["coverage"]["dependency_prob_comparator"] == ">"
    assert r["coverage"]["dependency_prob_strict"] is True
    assert r["coverage"]["dependency_prob_threshold"] == 0.5


# --- attack 3: no coverage claim while official catalog is empty --------------------- #
def test_official_depmap_handoff_refused_while_catalog_empty():
    assert db.DEPMAP_OFFICIAL_CATALOG_POPULATED is False
    official = {"release_id": "depmap_public_26q1", "source_class": "official",
                "catalog_verified": True, "genes": {}}
    with pytest.raises(GbmContextError):
        db.load_dependency_handoff(official)


def test_release_provenance_states_coverage_not_claimed():
    prov = db.release_provenance(None)
    assert prov["evaluated"] is False
    assert prov["official_catalog_populated"] is False
    assert prov["coverage_claimed"] is False


# --- attack 4: no machine-local path in any public artifact -------------------------- #
def test_handoff_has_no_machine_local_path():
    arms = [{"target_ensembl": "ENSG00000146648", "target_symbol": "EGFR",
             "desired_change": "decrease", "program_id": "p", "arm_key": "k"}]
    h = bg.build_handoff(arms, ot_by_gene={"ENSG00000146648": _fetch_like()},
                         dep_handoff=None,
                         raw_response_artifacts={"ENSG00000146648": {
                             "basename": "ot_ENSG00000146648_0ac55a97.json",
                             "sha256": "0ac55a97", "http_status": 200}})
    assert cs.leaks_in(h) == []
    # sanity: the detector actually fires on a leak
    assert cs.leaks_in({"x": "/home/tcelab/secret/out.json"})


def test_raw_artifact_manifest_uses_basenames_not_paths():
    arms = [{"target_ensembl": "ENSG00000146648", "target_symbol": "EGFR",
             "desired_change": "decrease", "program_id": "p", "arm_key": "k"}]
    man = {"ENSG00000146648": {"basename": "ot_ENSG00000146648_0ac55a97.json",
                               "sha256": "0ac55a97", "http_status": 200,
                               "endpoint": "https://api.platform.opentargets.org/api/v4/graphql"}}
    h = bg.build_handoff(arms, ot_by_gene={"ENSG00000146648": _fetch_like()},
                         dep_handoff=None, raw_response_artifacts=man)
    entry = h["raw_response_artifacts"]["ENSG00000146648"]
    assert "/" not in entry["basename"]      # basename, never a path
    assert entry["sha256"] == "0ac55a97"


# --- attack 5: no fabrication -------------------------------------------------------- #
def test_absent_ot_result_invents_no_disease_number():
    arms = [{"target_ensembl": "ENSG00000049768", "target_symbol": "FOXP3",
             "desired_change": "increase", "program_id": "p", "arm_key": "k"}]
    h = bg.build_handoff(arms, ot_by_gene={}, dep_handoff=None)
    da = h["genes"]["ENSG00000049768"]["disease_axis"]
    assert da["state"] == st.NOT_EVALUATED
    assert da["diseases"] == {}
