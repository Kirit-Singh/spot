"""The run schema is the DEFINITIVE contract, or it is decoration.

``stage02_direct_run.schema.json`` is the one artifact a Perturb2State / Stage-3 adapter
is written against. It was not a contract. It was a floor:

  * it REQUIRED 12 of the 91 emitted columns. A run could drop an arm's support status,
    its replication state, its evidence tier, its state, its evaluability flag, its
    mask identity or its QC measurements — and validate. A consumer written against the
    schema would then read ``None`` for a column that had simply ceased to exist, and
    could not tell "not supported" from "not emitted";

  * its ``base_qc_state`` enum listed 8 of the 11 states the code can actually produce.
    ``unresolved_target_identity``, ``missing_qc_measurement`` and
    ``invalid_qc_measurement`` were missing — and the synthetic run EMITS the first of
    them. The schema only escaped because ``row_example`` samples row 0 of the table and
    row 0 happened to be a passing row. Sample an unresolved row and the run's own
    published contract rejects the run;

  * ten more columns with closed runtime vocabularies — both arms' ``projection_status``
    and ``support_state``, ``contributor_status``, ``contributor_source``,
    ``crispri_modality``, ``inference_status``, ``cell_level_support_state``,
    ``schema_version`` — were constrained by ``{}``. Anything at all validated.

An enum that is a subset of what the code emits is worse than no enum: it says the
vocabulary is closed, and it is closed around the wrong set. So the schema now pins the
EXACT emitted column set in both ``columns`` and ``row_example``, and EVERY closed
vocabulary is enumerated. The drift test below compares each enum to the code, so the
next divergence fails here instead of in a consumer.
"""
from __future__ import annotations

import copy
import json
import os

import jsonschema
import pandas as pd
import pytest

from direct import config, disposition as D, emit, guides
from direct import projection as P
from direct.run_screen import build_screen

from test_p2s_contract import SCHEMA_PATH, _descriptor, _row_example


@pytest.fixture(scope="module")
def schema():
    with open(SCHEMA_PATH) as fh:
        return json.load(fh)


_CACHE: dict = {}


@pytest.fixture
def descriptor(synthetic_run):
    """ONE real synthetic run's descriptor, built once and reused.

    It is pure data (no handles, no paths into the run dir), so caching it is safe —
    and it keeps ~90 schema attacks from rebuilding the same screen ~90 times. Every
    test deep-copies before mutating.
    """
    if "doc" not in _CACHE:
        _CACHE["doc"] = _descriptor(build_screen(synthetic_run()))
    return copy.deepcopy(_CACHE["doc"])


def validate(doc, schema):
    jsonschema.validate(doc, schema)


# --------------------------------------------------------------------------- #
# 1. EVERY emitted column is required, in BOTH places.
# --------------------------------------------------------------------------- #
def test_the_schema_pins_the_exact_emitted_column_set(schema, descriptor):
    emitted = set(descriptor["screen"]["columns"])
    screen = schema["properties"]["screen"]["properties"]
    assert set(screen["columns"]["required"]) == emitted
    assert set(screen["columns"]["properties"]) == emitted
    assert set(screen["row_example"]["required"]) == emitted
    assert set(screen["row_example"]["properties"]) == emitted
    assert screen["columns"]["additionalProperties"] is False
    assert screen["row_example"]["additionalProperties"] is False


def test_a_real_run_still_conforms(schema, descriptor):
    """The strictest schema in the world is worthless if the lane cannot satisfy it."""
    validate(copy.deepcopy(descriptor), schema)


# The columns a consumer CANNOT be left to guess about. Dropping any of them silently
# turns a missing measurement into an absent key, and a consumer cannot distinguish
# "this arm has no support" from "this run stopped emitting support".
CONSUMER_CRITICAL = [
    "A_support_status", "B_support_status",
    "A_guide_replication_state", "B_guide_replication_state",
    "A_evidence_tier", "B_evidence_tier",
    "A_state", "B_state",
    "A_evaluable", "B_evaluable",
    "A_projection_status", "B_projection_status",
    "A_support_state", "B_support_state",
    "A_desired_target_modulation", "B_desired_target_modulation",
    "away_from_A", "toward_B",
    "rank_away_from_A", "rank_toward_B",
    "mask_resolved", "mask_gene_count", "mask_unresolved_reason",
    "base_qc_state", "base_qc_passed", "base_qc_reasons",
    "contributor_status", "contributor_source", "contributing_guide_ids",
    "qc_ontarget_significant", "qc_low_target_expression", "n_cells_target",
    "target_id", "target_id_namespace", "target_ensembl", "released_estimate_id",
    "concordance_class", "desired_modulation_agreement",
]


@pytest.mark.parametrize("column", CONSUMER_CRITICAL)
def test_dropping_a_consumer_critical_column_fails_the_schema(schema, descriptor,
                                                              column):
    """Every one of these validated against the old schema. All of them."""
    doc = copy.deepcopy(descriptor)
    doc["screen"]["columns"].pop(column)
    doc["screen"]["row_example"].pop(column)
    with pytest.raises(jsonschema.ValidationError):
        validate(doc, schema)


def test_dropping_ANY_emitted_column_fails_the_schema(schema, descriptor):
    """Not merely the named ones: the whole emitted set is the contract."""
    survived = []
    for column in sorted(descriptor["screen"]["columns"]):
        doc = copy.deepcopy(descriptor)
        doc["screen"]["columns"].pop(column)
        doc["screen"]["row_example"].pop(column)
        try:
            validate(doc, schema)
            survived.append(column)
        except jsonschema.ValidationError:
            pass
    assert not survived, f"{len(survived)} column(s) may be dropped: {survived}"


def test_an_INVENTED_column_fails_the_schema(schema, descriptor):
    """additionalProperties=false, in both places. An allowlist, not a denylist."""
    for where in ("columns", "row_example"):
        doc = copy.deepcopy(descriptor)
        doc["screen"][where]["synergy_score"] = 1.0
        with pytest.raises(jsonschema.ValidationError):
            validate(doc, schema)


# --------------------------------------------------------------------------- #
# 2. EVERY runtime enum. Synchronized, and PROVEN synchronized.
# --------------------------------------------------------------------------- #
RUNTIME_VOCABULARY = {
    "baseQcState": list(D.BASE_QC_PRECEDENCE),
    "armState": [D.ARM_EVALUABLE, D.ARM_EXCLUDED_BASE_QC,
                 D.ARM_INSUFFICIENT_COVERAGE, D.ARM_MASK_UNRESOLVED],
    "supportStatus": list(D.SUPPORT_STATUSES),
    "replicationState": [D.REPLICATION_NOT_EVALUATED, D.REPLICATION_UNAVAILABLE,
                         D.REPLICATION_SUPPORT_UNAVAILABLE, D.REPLICATION_SINGLE,
                         D.REPLICATION_CONCORDANT, D.REPLICATION_DISCORDANT],
    "modulation": [D.MOD_DECREASE, D.MOD_INCREASE, D.MOD_NO_DIRECTION,
                   D.MOD_NOT_EVALUATED],
    "modulationAgreement": [D.MOD_AGREE, D.MOD_CONFLICT, D.MOD_ONLY_A, D.MOD_ONLY_B,
                            D.MOD_NONE],
    "concordanceClass": [P.CONCORDANT, P.A_ONLY, P.B_ONLY, P.DISCORDANT, P.PARTIAL,
                         P.NOT_EVALUATED],
    "projectionStatus": [P.OK, P.INSUFFICIENT_AXIS_COVERAGE, P.MASK_UNRESOLVED],
    "contributorStatus": [guides.RESOLVED, guides.UNRESOLVED],
    "tier": ["not_evaluated", "evaluable_no_directional_signal", "tier3_screen_only",
             "tier2_guide_replicated", "tier1_guide_and_donor_split"],
    "armSupportState": ["not_evaluated", "screen_only", "within_dataset_replicated"],
    "targetIdNamespace": ["ensembl_gene_id", "gene_symbol"],
}


@pytest.mark.parametrize("name", sorted(RUNTIME_VOCABULARY))
def test_every_schema_enum_is_EXACTLY_the_runtime_vocabulary(schema, name):
    """THE anti-drift check. A schema enum that is a SUBSET of what the code emits
    declares a closed vocabulary and closes it around the wrong set."""
    declared = set(schema["$defs"][name]["enum"])
    runtime = set(RUNTIME_VOCABULARY[name])
    assert declared == runtime, (
        f"{name}: schema is missing {sorted(runtime - declared)}; "
        f"schema invents {sorted(declared - runtime)}")


@pytest.mark.parametrize("state", list(D.BASE_QC_PRECEDENCE))
def test_every_runtime_base_qc_state_validates(schema, descriptor, state):
    """All 11. Three of them — unresolved_target_identity, missing_qc_measurement,
    invalid_qc_measurement — were rejected by the run's own published contract."""
    doc = copy.deepcopy(descriptor)
    doc["screen"]["row_example"]["base_qc_state"] = state
    validate(doc, schema)


def test_a_base_qc_state_the_runtime_cannot_produce_is_REJECTED(schema, descriptor):
    """Widening the enum to 'anything' is not the fix for a too-narrow enum."""
    doc = copy.deepcopy(descriptor)
    doc["screen"]["row_example"]["base_qc_state"] = "qc_pass_probably"
    with pytest.raises(jsonschema.ValidationError):
        validate(doc, schema)


@pytest.mark.parametrize("column,bad", [
    ("A_state", "sort_of_evaluable"),
    ("B_support_status", "evaluated_ish"),
    ("A_guide_replication_state", "replicated_maybe"),
    ("B_evidence_tier", "tier0_confirmed"),
    ("A_desired_target_modulation", "increase_a_bit"),
    ("A_projection_status", "fine"),
    ("B_support_state", "cell_level_supported"),
    ("contributor_status", "assumed"),
    ("contributor_source", "guide_slot_rank"),
    ("concordance_class", "mostly_concordant"),
    ("desired_modulation_agreement", "resolved_in_favour_of_A"),
    ("target_id_namespace", "hgnc"),
    ("crispri_modality", "CRISPRa"),
    ("inference_status", "calibrated"),
    ("cell_level_support_state", "cell_level_supported"),
    ("schema_version", "spot.stage02_screen.v2"),
])
def test_an_off_vocabulary_value_is_rejected_in_EITHER_arm(schema, descriptor,
                                                           column, bad):
    """Ten of these columns had NO constraint at all: `{}` accepted anything."""
    doc = copy.deepcopy(descriptor)
    doc["screen"]["row_example"][column] = bad
    with pytest.raises(jsonschema.ValidationError):
        validate(doc, schema)


# --------------------------------------------------------------------------- #
# 3. THE REGRESSION THAT WAS ALREADY LIVE.
# --------------------------------------------------------------------------- #
def test_a_row_example_taken_from_an_UNRESOLVED_row_validates(schema, synthetic_run):
    """The bug was not hypothetical — the synthetic run already emits this state.

    ``row_example`` samples ``screen.iloc[0]``. Row 0 happened to be a passing row, so
    the missing enum member was never exercised. Sample a row that carries
    ``unresolved_target_identity`` — a state this lane produces on every run with a
    symbol-namespace target — and the run's own published contract used to reject the
    run that produced it.
    """
    result = build_screen(synthetic_run())
    screen = pd.read_parquet(os.path.join(result["out_dir"], "screen.parquet"))
    unresolved = screen[screen["base_qc_state"] == "unresolved_target_identity"]
    assert not unresolved.empty, "the fixture no longer exercises this state"

    doc = _descriptor(result)
    doc["screen"]["row_example"] = _row_example(unresolved.reset_index(drop=True))
    validate(doc, schema)


def test_the_rank_columns_must_be_declared_nullable_Int64(schema, descriptor):
    """A float rank invents a rank for a target that has none; int() on a NaN crashes."""
    for col in ("rank_away_from_A", "rank_toward_B"):
        doc = copy.deepcopy(descriptor)
        doc["screen"]["columns"][col] = "float64"
        with pytest.raises(jsonschema.ValidationError):
            validate(doc, schema)


def test_the_schema_still_forbids_every_combined_objective_alias(schema, descriptor):
    """Tightening the allowlist may not lose the denylist that names the aliases."""
    for banned in ("balanced_skew", "combined_score", "rank", "p_value",
                   "eligibility_state", "toward_b"):
        doc = copy.deepcopy(descriptor)
        doc["screen"]["columns"][banned] = "float64"
        with pytest.raises(jsonschema.ValidationError):
            validate(doc, schema)


def test_the_emitted_screen_schema_version_is_the_one_the_schema_pins(schema):
    node = schema["properties"]["screen"]["properties"]["row_example"]
    assert node["properties"]["schema_version"]["const"] == emit.SCHEMA_SCREEN
    assert (node["properties"]["crispri_modality"]["const"]
            == config.CRISPRI_MODALITY)
    assert (node["properties"]["inference_status"]["const"]
            == config.INFERENCE_STATUS)
