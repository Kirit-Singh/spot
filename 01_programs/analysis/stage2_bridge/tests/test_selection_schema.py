"""Validate emitted spot.stage01_selection.v3 contracts against the formal JSON Schema, and confirm
the schema itself forbids the retired production/research split fields."""
import json
import os

import jsonschema
import pytest

import emit_selection_contract as sc

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCHEMA_PATH = os.path.join(HERE, "schemas", "spot.stage01_selection.v3.schema.json")

CASES = [
    dict(a_program_id="treg_like", a_direction="high", b_program_id="th1_like", b_direction="high", conditions=["Stim48hr"]),   # ready
    dict(a_program_id="th9_like", a_direction="low", b_program_id="th1_like", b_direction="high", conditions=["Rest"]),         # refused
    dict(a_program_id="treg_like", a_direction="high", b_program_id="th1_like", b_direction="high", conditions=["Stim8hr", "Stim48hr"]),  # awaiting
    dict(a_program_id="cd4_ctl_like", a_direction="low", b_program_id="diff_memory", b_direction="high", conditions=["Rest"]),
]


@pytest.fixture(scope="module")
def schema():
    s = json.load(open(SCHEMA_PATH))
    jsonschema.Draft202012Validator.check_schema(s)   # the schema is itself valid
    return s


def test_emitted_contracts_conform(schema):
    val = jsonschema.Draft202012Validator(schema)
    for kw in CASES:
        c = sc.build_contract(**kw)
        errs = sorted(val.iter_errors(c), key=lambda e: e.path)
        assert not errs, f"{kw}: {[e.message for e in errs]}"


def test_schema_pins_v3_and_no_split(schema):
    # schema_version const + strict object (no extra top-level keys -> no re-introduced split fields)
    assert schema["properties"]["schema_version"]["const"] == "spot.stage01_selection.v3"
    assert schema["additionalProperties"] is False
    assert schema["properties"]["execution_status"]["enum"] == ["ready", "refused", "awaiting_estimator"]
    # a contract with a re-introduced production/research field must FAIL validation
    bad = sc.build_contract(**CASES[0]); bad["production_execution_status"] = "not_selectable"
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_historical_active_gate_false_enforced(schema):
    bad = sc.build_contract(**CASES[0])
    bad["historical_validation_provenance"]["active_gate"] = True   # frozen validation may never be a live gate
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(bad, schema)


def test_within_ready_temporal_awaiting_refused_statuses(schema):
    assert sc.build_contract(**CASES[0])["execution_status"] == "ready"
    assert sc.build_contract(**CASES[1])["execution_status"] == "refused"
    assert sc.build_contract(**CASES[2])["execution_status"] == "awaiting_estimator"
