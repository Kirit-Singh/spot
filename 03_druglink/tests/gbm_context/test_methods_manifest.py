"""Validate the Stage-3 (Drugs) Methods & Provenance drawer payload.

Must satisfy the UI contract (_frontend/src/domain/methodsManifest.ts) and the drawer's rules:
nothing invented (absent -> null), no editorial prose, no combined/overall rank, no p/q, no
machine-local path, and every hash traced to real pinned bytes.
"""
from __future__ import annotations

import json
import re

from druglink.gbm_context import methods_manifest as mm
from druglink.gbm_context import emit_methods_manifest as em
from verifier import cache_sweep as cs

HEX64 = re.compile(r"^[0-9a-f]{64}$")

METHOD_KEYS = {"data_input", "source_tissue", "estimand", "masks_qc", "upstream_model",
               "limitations", "method_id", "method_code_sha256", "environment",
               "last_run_utc", "reproduce_command"}
PROV_KEYS = {"release_revision", "raw_sha256", "canonical_sha256", "generator_status",
             "verifier_status", "cs_notebook_url", "artifact_paths", "source_chain"}
LINK_KEYS = {"label", "record_id", "url", "license", "retrieval_utc", "raw_sha256",
             "canonical_sha256"}

OT_SET = "b02ecf6c8c7c4ef0cde34c454aef09ff3dc03b83fbe8130ffcc1d1f99a9cc2bb"


def _m():
    return mm.build_manifest(ot_retrieval_utc="2026-07-13T17:42:55Z",
                             ot_response_set_canonical_sha256=OT_SET)


def test_shape_matches_the_ui_stage_methods_manifest_type():
    m = _m()
    assert set(m) == {"stage_label", "methods", "provenance"}
    assert set(m["methods"]) == METHOD_KEYS
    assert set(m["provenance"]) == PROV_KEYS
    for link in m["provenance"]["source_chain"]:
        assert set(link) == LINK_KEYS
    assert isinstance(m["methods"]["limitations"], list)
    assert isinstance(m["provenance"]["artifact_paths"], list)


def test_stage_label_and_pinned_source_tissue_are_exact():
    m = _m()
    assert m["stage_label"] == "Drugs"
    # byte-for-byte the SOURCE_TISSUE.drugs string pinned in stageMethods.ts
    assert m["methods"]["source_tissue"] == (
        "Biological input is the Stage-2 program/perturbation result from the Marson "
        "primary-human-CD4 dataset; drug evidence comes from separately listed public sources.")


def test_no_admitted_run_so_run_status_stays_unavailable_not_invented():
    md = _m()["methods"]
    for k in ("method_code_sha256", "environment", "last_run_utc", "reproduce_command"):
        assert md[k] is None
    pv = _m()["provenance"]
    for k in ("release_revision", "raw_sha256", "canonical_sha256", "generator_status",
              "verifier_status", "cs_notebook_url"):
        assert pv[k] is None
    assert pv["artifact_paths"] == []


def test_open_targets_link_is_traced_to_pinned_bytes():
    links = {s["record_id"]: s for s in _m()["provenance"]["source_chain"]}
    ot = links["open_targets_26_06"]
    assert ot["license"] == "CC0 1.0"
    assert ot["url"].startswith("https://api.platform.opentargets.org")
    assert ot["retrieval_utc"] == "2026-07-13T17:42:55Z"
    assert HEX64.match(ot["canonical_sha256"]) and ot["canonical_sha256"] == OT_SET


def test_depmap_link_claims_no_coverage_and_invents_no_hash():
    links = {s["record_id"]: s for s in _m()["provenance"]["source_chain"]}
    dm = links["depmap_public_26q1"]
    assert dm["license"] == "CC BY 4.0"
    assert dm["raw_sha256"] is None and dm["canonical_sha256"] is None
    assert dm["retrieval_utc"] is None          # not retrieved: catalog empty
    lims = " ".join(_m()["methods"]["limitations"])
    assert "not_evaluated" in lims and "no GBM/glioma cell-line coverage is claimed" in lims
    assert "strictly greater than 0.5" in lims


def test_stale_open_targets_not_wired_limitation_is_corrected():
    lims = _m()["methods"]["limitations"]
    # the old row claimed Open Targets was NOT wired; it now is, so that claim must be gone
    assert not any("Open Targets, DGIdb" in x for x in lims)
    assert any("DGIdb, DrugBank and DepMap-PRISM drug sensitivity are not" in x for x in lims)


def test_no_combined_rank_and_no_pq_claimed():
    m = _m()
    blob = json.dumps(m)
    assert "no combined or overall score" in blob
    assert "no p/q is emitted" in blob
    assert "never ranks, gates, or alters Stage-2" in blob
    for banned in ("combined_score", "overall_rank", "p_value", "q_value", "fdr"):
        assert banned not in blob


def test_no_machine_local_path_anywhere():
    assert cs.leaks_in(_m()) == []


def test_canonical_hash_is_deterministic_and_content_bound():
    m1, m2 = _m(), _m()
    h = mm.content_sha256(m1)
    assert HEX64.match(h) and h == mm.content_sha256(m2)
    # a one-byte mutation of ANY bound value invalidates the manifest (fail-closed gate)
    m2["provenance"]["source_chain"][2]["license"] = "CC0 1.1"
    assert mm.content_sha256(m2) != h


def test_canonical_json_matches_the_ui_rule():
    # sorted keys, no spaces, ASCII-escaped (the UI recomputes with the identical rule)
    raw = mm.canonical_json({"b": 1, "a": "⟷"})
    assert raw == '{"a":"\\u27f7","b":1}'


def test_emitter_refuses_a_handoff_with_no_pinned_responses():
    import pytest
    with pytest.raises(SystemExit):
        em.from_handoff({"run_provenance": {"run_timestamp_utc": "x"},
                         "raw_response_artifacts": {}})
