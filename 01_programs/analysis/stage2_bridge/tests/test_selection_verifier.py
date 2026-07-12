"""Mutation tests for the producer-independent semantic selection verifier + the schema if/then tuple gate
(external review S1-B3). A fully resealed contradictory contract must be REJECTED by both."""
import hashlib
import json
import os

import jsonschema
import pytest

import canonical
import emit_selection_contract as sc
import verify_selection_contract as vc

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA = json.load(open(os.path.join(HERE, "schemas", "spot.stage01_selection.v3.schema.json")))

READY = dict(a_program_id="treg_like", a_direction="high", b_program_id="th1_like", b_direction="high",
             conditions=["Stim48hr"])
TEMPORAL = dict(a_program_id="treg_like", a_direction="high", b_program_id="th1_like", b_direction="high",
                conditions=["Stim8hr", "Stim48hr"])


def _reseal(c):
    body = {k: v for k, v in c.items() if k != "full_contract_content_sha256"}
    c["full_contract_content_sha256"] = hashlib.sha256(canonical.canonical_json(body).encode()).hexdigest()
    return c


def _reseal_selection(c):
    sel = hashlib.sha256(canonical.canonical_json(c["canonical_content"]).encode()).hexdigest()
    c["selection_id"] = sel[:16]
    c["selection_full_sha256"] = sel
    return _reseal(c)


def test_verifier_accepts_legitimate_contracts():
    for kw in (READY, TEMPORAL):
        ok, reasons = vc.verify_contract(sc.build_contract(**kw))
        assert ok, reasons


def test_impossible_temporal_ready_not_implemented_rejected():
    """The exact review forgery: temporal_cross_condition + ready + not_implemented, fully resealed.
    Rejected by BOTH the schema if/then AND the independent semantic verifier."""
    c = sc.build_contract(**TEMPORAL)                 # legitimately ready/available
    c["execution_status"] = "ready"
    c["estimator_status"] = "not_implemented"
    c["estimator"]["status"] = "not_implemented"
    c["estimator"].pop("method_sha256", None)
    _reseal(c)
    with pytest.raises(jsonschema.ValidationError):   # schema: ready => estimator_status available
        jsonschema.validate(c, SCHEMA)
    ok, reasons = vc.verify_contract(c)               # independent semantic verifier
    assert not ok
    assert any("ready" in r for r in reasons)


def test_verifier_catches_tampered_selection_id():
    c = sc.build_contract(**READY)
    c["selection_id"] = "0" * 16
    _reseal(c)
    ok, reasons = vc.verify_contract(c)
    assert not ok and any("selection_id" in r for r in reasons)


def test_verifier_catches_tampered_scorer_view():
    c = sc.build_contract(**READY)
    c["canonical_content"]["registry_scorer_view_sha256"] = "f" * 64
    _reseal_selection(c)                              # rederive selection hashes so ONLY the view binding is wrong
    ok, reasons = vc.verify_contract(c)
    assert not ok and any("view" in r for r in reasons)


def test_verifier_catches_borrowed_within_condition_estimator():
    """A temporal mode that names the within-condition estimator is rejected — never borrow."""
    c = sc.build_contract(**TEMPORAL)
    c["estimator_id"] = "within_condition_v1"
    c["estimator"]["estimator_id"] = "within_condition_v1"
    _reseal(c)
    ok, reasons = vc.verify_contract(c)
    assert not ok and any("estimator_id" in r for r in reasons)


def test_schema_allows_legitimate_ready_and_awaiting(schema=SCHEMA):
    jsonschema.Draft202012Validator.check_schema(SCHEMA)   # if/then additions keep the schema itself valid
    jsonschema.validate(sc.build_contract(**READY), SCHEMA)          # within ready
    jsonschema.validate(sc.build_contract(**TEMPORAL), SCHEMA)       # temporal ready (estimator present)
