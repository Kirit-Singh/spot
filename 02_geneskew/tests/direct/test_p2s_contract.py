"""The definitive P2S-facing contract: a strict JSON Schema and a canonical fixture.

A downstream lane (Perturb2State, Stage-3) may assume THIS and nothing else. In
particular it may not assume a combined objective, a headline rank, an A-only
primary, or the retired ``eligibility_state`` / ``toward_b`` columns.
"""
import json
import os

import jsonschema
import pandas as pd
import pytest
from direct import config
from direct.run_screen import build_screen

SCHEMA_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(
        __import__("direct").__file__))),
    "direct", "schemas", "stage02_direct_run.schema.json")
CANONICAL_FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                 "fixtures", "canonical_two_arm_run.json")


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH) as fh:
        return json.load(fh)


def _descriptor(result) -> dict:
    """The run descriptor a consumer reads, assembled from the emitted artifacts."""
    out = result["out_dir"]
    with open(os.path.join(out, "provenance.json")) as fh:
        prov = json.load(fh)
    screen = pd.read_parquet(os.path.join(out, "screen.parquet"))
    binding = prov["run_binding"]
    return {
        "run_id": prov["run_id"],
        "question_id": prov["question_id"],
        "selection_id": prov["selection_id"],
        "analysis_condition": prov["analysis_condition"],
        "lane": binding["lane"],
        "namespace": prov["namespace"],
        "production_eligible": prov["production_eligible"],
        "stage3_eligible": prov["stage3_eligible"],
        "production_gate_passed": prov["production_gate_passed"],
        "mask_sha256": prov["mask_sha256"],
        "gene_universe_sha256": prov["gene_universe_sha256"],
        "hashes": {
            "run_binding_sha256": prov["run_binding_sha256"],
            "code_tree_sha256": binding["code_tree_sha256"],
            "contributor_manifest_sha256":
                binding["guide_manifest"].get("manifest_sha256"),
            "environment_lock_sha256": binding["environment_lock"]["sha256"],
            "stage1_release": {
                "kind": binding["stage1_release"]["kind"],
                "method_version": binding["stage1_release"]["method_version"],
                "n_production_selectable":
                    binding["stage1_release"]["n_production_selectable"],
            },
        },
        "screen": {
            "row_key": "target_id",
            "arms": list(config.ARMS),
            "columns": {c: str(screen[c].dtype) for c in screen.columns},
            "row_example": _row_example(screen),
        },
    }


def _row_example(screen: pd.DataFrame) -> dict:
    """One fully-typed emitted row: a consumer must handle nulls in EITHER arm."""
    row = screen.iloc[0]
    out = {}
    for c in screen.columns:
        v = row[c]
        out[c] = None if pd.isna(v) else (
            bool(v) if isinstance(v, (bool,)) else
            int(v) if hasattr(v, "item") and str(screen[c].dtype).startswith(("int", "Int"))
            else float(v) if str(screen[c].dtype).startswith("float")
            else bool(v) if str(screen[c].dtype) == "bool"
            else str(v))
    return out


def test_the_schema_itself_is_valid(schema):
    jsonschema.Draft202012Validator.check_schema(schema)


def test_a_real_run_conforms_to_the_definitive_schema(schema, synthetic_run):
    result = build_screen(synthetic_run())
    jsonschema.validate(_descriptor(result), schema)


def test_the_committed_canonical_fixture_conforms(schema):
    """The canonical fixture IS the contract a P2S adapter should be written against."""
    with open(CANONICAL_FIXTURE) as fh:
        canonical = json.load(fh)
    jsonschema.validate(canonical, schema)


def test_the_canonical_fixture_matches_what_the_lane_actually_emits(synthetic_run):
    """If the emitted column set drifts from the published contract, this fails."""
    result = build_screen(synthetic_run())
    emitted = set(_descriptor(result)["screen"]["columns"])
    with open(CANONICAL_FIXTURE) as fh:
        canonical = set(json.load(fh)["screen"]["columns"])
    assert emitted == canonical, (
        f"contract drift — only in run: {sorted(emitted - canonical)}; "
        f"only in fixture: {sorted(canonical - emitted)}")


@pytest.mark.parametrize("banned", [
    "rank", "primary_rank", "headline_rank", "combination", "balanced_skew",
    "combined_score", "total_skew", "is_eligible", "eligibility_state", "toward_b",
    "p_value", "q_value",
])
def test_the_schema_rejects_every_retired_or_combined_column(schema, banned):
    with open(CANONICAL_FIXTURE) as fh:
        doc = json.load(fh)
    doc["screen"]["columns"][banned] = None
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, schema)


def test_the_schema_rejects_a_float_rank(schema):
    with open(CANONICAL_FIXTURE) as fh:
        doc = json.load(fh)
    doc["screen"]["row_example"]["rank_away_from_A"] = 1.5
    with pytest.raises(jsonschema.ValidationError):
        jsonschema.validate(doc, schema)


def test_the_schema_requires_both_arm_ranks_and_both_evaluable_flags(schema):
    for missing in ("rank_away_from_A", "rank_toward_B", "A_evaluable",
                    "B_evaluable", "away_from_A", "toward_B"):
        with open(CANONICAL_FIXTURE) as fh:
            doc = json.load(fh)
        doc["screen"]["columns"].pop(missing)
        doc["screen"]["row_example"].pop(missing)
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(doc, schema)
