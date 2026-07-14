"""Every emitted cell is bound into identity or reconstructed. Nothing is taken on trust.

The re-audit's finding: `verify.py` claimed the emitted tables "are exactly the inputs" while
comparing a hand-written subset of columns, and the standalone verifier never recomputed
`evidence_inputs_sha256` from the release at all. So a resealed release could rewrite a
negative search's `search_scope` / `source` / `executed_date` / `extraction_transform`, or a
potency-context link's `access_date` / `extraction_transform`, keep the `scorecard_set_id`,
and pass BOTH verifiers (202/0 and 193/0).

`no_evidence_found` means something different when the searched scope changes. That release
told a different scientific story under one identity.

The class of bug was the hand-written list, not the columns it forgot. These tests pin the
general property:

    for EVERY column of EVERY evidence table, a resealed mutation must be caught —
    either because it moves the bound identity, or because it contradicts a reconstruction.

Each tamper below reseals the parquet through the canonical writer AND rewrites the file
hash, the content hash and the manifest self-hash, so arithmetic alone can never catch it.
"""

from __future__ import annotations

import copy
import json
import os

import pyarrow.parquet as pq
import pytest

from analysis.canonical import content_sha256, sha256_file
from analysis.contract_version import ContractVersion
from analysis.evidence_inputs import (
    EXPLANATORY_COLUMNS,
    derived_columns,
    evidence_input_rows,
    input_columns,
)
from analysis.ids import evidence_inputs_digest
from analysis.tables import table_schemas, write_table

from provenance_helpers import both_verifiers, emit_run, failed
from verifier import inputs as vinputs

import fixtures as fx

# The sweep runs over BOTH contracts. v1 cells are swept against the frozen v1 fixture and v2
# cells against the v2 one, because a cell that no fixture carries is a cell nothing proves.
INPUT_COLUMNS = input_columns(ContractVersion.V2)
DERIVED_COLUMNS = derived_columns(ContractVersion.V2)
TABLE_SCHEMAS = table_schemas(ContractVersion.V2)


def _reseal(out_dir, table, rows):
    """Rewrite one parquet and reseal EVERY hash the release declares over it."""
    path = os.path.join(out_dir, f"{table}.parquet")
    desc = write_table(table, rows, path)
    mpath = os.path.join(out_dir, "manifest.json")
    with open(mpath, encoding="utf-8") as fh:
        manifest = json.load(fh)
    for art in manifest["artifacts"]:
        if art["filename"] == f"{table}.parquet":
            art["content_sha256"] = desc["content_sha256"]
            art["file_sha256"] = desc["file_sha256"]
            art["rows"] = desc["rows"]
    manifest.pop("manifest_content_sha256")
    manifest["manifest_content_sha256"] = content_sha256(manifest)
    with open(mpath, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True, ensure_ascii=False)
        fh.write("\n")
    assert sha256_file(path) == desc["file_sha256"], "the reseal must be complete"


def _mutate(value, col):
    if isinstance(value, bool):
        return not value
    if isinstance(value, int):
        return value + 1
    if isinstance(value, float):
        return value + 1.0
    if isinstance(value, list):
        return list(value) + ["TAMPERED"]
    if value is None:
        return "TAMPERED"
    if col.endswith("sha256") and isinstance(value, str) and len(value) == 64:
        return "a" * 64
    if col.endswith("date") and isinstance(value, str) and len(value) == 10:
        return "1999-01-01"
    return f"TAMPERED {value}"[:200]


ALL_CELLS = [
    (version, table, col)
    for version in (ContractVersion.V1, ContractVersion.V2)
    for table in sorted(input_columns(version))
    for col in list(input_columns(version)[table]) + list(derived_columns(version)[table])
]


def _inputs_for(table, version=ContractVersion.V2):
    """The fixture set, plus whatever that table needs in order to have a row at all.

    `potency_context_links` is EMPTY in the base fixtures — every potency already sits in its
    own tumour context. Sweeping it against the base set silently skipped all ten of its
    columns, and it is the exact table the re-audit rewrote. A table with no rows is not a
    table that passed.
    """
    inputs = (fx.stage4_inputs() if version == ContractVersion.V1
              else fx.stage4_inputs_v2())
    if table == "potency_context_links":
        from analysis.evidence_records import PotencyContextLink, PotencyRecord
        inputs.potencies = [
            PotencyRecord(**{**p.model_dump(), "biological_context": "OTHER_TUMOR"})
            if p.potency_id == "POT-001" else p for p in inputs.potencies]
        inputs.potency_context_links = [
            PotencyContextLink(
                link_id="LNK-SWEEP", potency_id="POT-001", tumor_context="GBM_fixture",
                rationale="FIXTURE: the same target is expressed in both models.",
                provenance=fx._prov("src.fixture.potency", "read the relevance argument"))]
    return inputs


# ------------------------------------------------------ the declaration is exhaustive

def test_every_emitted_column_is_classified_input_or_derived():
    """A column that is neither is a column nobody bound and nobody rebuilt."""
    for table in INPUT_COLUMNS:
        declared = set(INPUT_COLUMNS[table]) | set(DERIVED_COLUMNS[table])
        schema = set(TABLE_SCHEMAS[table].names)
        assert schema == declared, (
            f"{table}: unclassified={sorted(schema - declared)} "
            f"declared-but-absent={sorted(declared - schema)}")


def test_the_verifier_restates_the_bound_columns_without_importing_them():
    """Two independent declarations. A drift between them is the correct failure.

    Checked for BOTH contracts. The verifier restates v1 (frozen) and v2 (its additions)
    separately, and a verifier that imported the generator's declaration would be checking the
    generator against itself.
    """
    for version in (ContractVersion.V1, ContractVersion.V2):
        assert dict(vinputs.input_columns(version.value)) == dict(input_columns(version)), (
            f"the generator and the verifier disagree about the {version.value} bound columns")


def test_there_are_no_explanatory_exemptions_left():
    """Zero. Every emitted cell is bound into identity or reconstructed.

    `property_evidence.rejection_reason` and `exposure_evidence.margin_reason` used to be
    exempt: free prose, hashed into nothing and reconstructed by nothing, excused because a
    machine-readable code sat beside them. That excuse does not survive contact with the
    threat — a resealed release could rewrite the sentence a human actually reads while the
    code beside it stayed honest. A neighbouring machine code does not license unbound prose.

    Both columns are gone from the parquet. The typed code is reconstructed; the human
    sentence lives in scorecards.json, where prose belongs.
    """
    assert EXPLANATORY_COLUMNS == {}
    assert "rejection_reason" not in TABLE_SCHEMAS["property_evidence"].names
    assert "margin_reason" not in TABLE_SCHEMAS["exposure_evidence"].names
    # ...and the typed codes that replaced them ARE reconstructed
    assert "rejection_reason_code" in DERIVED_COLUMNS["property_evidence"]
    assert "margin_reason_code" in DERIVED_COLUMNS["exposure_evidence"]
    # the text a reader sees beside a safety finding was never exempt, and still is not
    assert "evidence_state_display" in DERIVED_COLUMNS["safety_evidence"]


@pytest.mark.parametrize("table,code_col", [
    ("property_evidence", "rejection_reason_code"),
    ("exposure_evidence", "margin_reason_code"),
])
def test_the_typed_reason_code_that_replaced_the_prose_is_caught(table, code_col, tmp_path):
    inputs = fx.stage4_inputs()
    out_dir, _m, _r = emit_run(inputs, tmp_path)
    rows = pq.read_table(os.path.join(out_dir, f"{table}.parquet")).to_pylist()
    target = next(r for r in rows if r[code_col] is not None)
    target[code_col] = "TAMPERED_code"
    _reseal(out_dir, table, rows)

    emit_time, standalone = both_verifiers(out_dir, inputs)
    assert emit_time["status"] == "fail" or standalone["status"] == "fail"


# --------------------------------------------------- the digest IS the emitted rows

def test_the_standalone_verifier_recomputes_the_digest_from_the_release(tmp_path):
    """It could not do this before: it only checked that a digest had been DECLARED."""
    inputs = fx.stage4_inputs()
    out_dir, manifest, _r = emit_run(inputs, tmp_path)

    from_release = vinputs.evidence_inputs_digest(vinputs.load_input_tables(out_dir))
    assert from_release == manifest["evidence_inputs_sha256"]
    assert from_release == manifest["scorecard_set_id_inputs"]["evidence_inputs_sha256"]
    # and the engine's own digest over the consumed records is the same number
    assert evidence_inputs_digest(evidence_input_rows(inputs)) == from_release


def test_the_release_identity_is_rederivable_from_the_release_alone(tmp_path):
    _out, manifest, _r = emit_run(fx.stage4_inputs(), tmp_path)
    rederived = vinputs.rederive_scorecard_set_id(manifest["scorecard_set_id_inputs"])
    assert rederived == manifest["scorecard_set_id"]


def test_row_permutation_does_not_change_the_digest(tmp_path):
    inputs = fx.stage4_inputs()
    rows = evidence_input_rows(inputs)
    reversed_rows = {t: list(reversed(r)) for t, r in rows.items()}
    assert evidence_inputs_digest(rows) == evidence_inputs_digest(reversed_rows)


# ------------------------------------------- the exact re-audit tampers, resealed

def test_the_reaudit_negative_search_tamper_is_refused(tmp_path):
    """search_scope / source / executed_date / extraction_transform, resealed.

    Passed both verifiers before this fix. `no_evidence_found` over a narrowed scope is a
    different claim about safety, and it was reachable under one scorecard_set_id.
    """
    inputs = fx.stage4_inputs()
    out_dir, _m, _r = emit_run(inputs, tmp_path)
    emit_time, standalone = both_verifiers(out_dir, inputs)
    assert emit_time["status"] == "pass" and standalone["status"] == "pass"

    rows = pq.read_table(os.path.join(out_dir, "search_manifests.parquet")).to_pylist()
    rows[0]["search_scope"] = "TAMPERED narrow scope excluding relevant safety evidence"
    rows[0]["executed_date"] = "1999-01-01"
    rows[0]["source"] = "invented source label"
    rows[0]["extraction_transform"] = "tampered transform"
    _reseal(out_dir, "search_manifests", rows)

    emit_time, standalone = both_verifiers(out_dir, inputs)
    assert standalone["status"] == "fail"
    assert emit_time["status"] == "fail"
    assert "evidence_inputs_sha256_recomputed_from_the_release" in failed(standalone)
    assert "bound_input_tables_emitted_exactly" in failed(emit_time)


def test_the_reaudit_potency_link_metadata_tamper_is_refused(tmp_path):
    """access_date / extraction_transform on a link, resealed. Also passed both before."""
    inputs = fx.stage4_inputs()
    out_dir, _m, _r = emit_run(inputs, tmp_path)

    from analysis.evidence_records import PotencyContextLink, PotencyRecord
    inputs.potencies = [
        PotencyRecord(**{**p.model_dump(), "biological_context": "OTHER_TUMOR"})
        if p.potency_id == "POT-001" else p for p in inputs.potencies]
    inputs.potency_context_links = [
        PotencyContextLink(
            link_id="LNK-OK", potency_id="POT-001", tumor_context="GBM_fixture",
            rationale="FIXTURE: legitimate.",
            provenance=fx._prov("src.fixture.potency", "read the relevance argument"))]
    out_dir, _m, _r = emit_run(inputs, tmp_path, name="linked")

    rows = pq.read_table(os.path.join(out_dir, "potency_context_links.parquet")).to_pylist()
    rows[0]["access_date"] = "1999-01-01"
    rows[0]["extraction_transform"] = "tampered transform"
    _reseal(out_dir, "potency_context_links", rows)

    emit_time, standalone = both_verifiers(out_dir, inputs)
    assert standalone["status"] == "fail"
    assert emit_time["status"] == "fail"
    assert "evidence_inputs_sha256_recomputed_from_the_release" in failed(standalone)


# --------------------------------------- the systematic sweep: EVERY cell, resealed

@pytest.mark.parametrize("version,table,col", ALL_CELLS,
                         ids=[f"{v.value}.{t}.{c}" for v, t, c in ALL_CELLS])
def test_every_resealed_cell_mutation_is_caught(version, table, col, tmp_path):
    """The general property the re-audit's four columns were only an instance of.

    Swept over BOTH contracts: every bound v1 cell against the frozen v1 fixture, and every
    bound v2 cell against the v2 one. A cell that no fixture carries is a cell nothing proves,
    which is why this refuses to skip an empty table rather than passing vacuously.
    """
    inputs = _inputs_for(table, version)
    out_dir, _m, _r = emit_run(inputs, tmp_path)

    path = os.path.join(out_dir, f"{table}.parquet")
    rows = pq.read_table(path).to_pylist()
    assert rows, (
        f"{table} has no rows in this fixture set, so sweeping its columns proves nothing. "
        "Give it a row (see _inputs_for) rather than skipping it.")

    before = copy.deepcopy(rows)
    rows[0][col] = _mutate(rows[0][col], col)
    if rows[0][col] == before[0][col]:
        pytest.skip("value is not mutable in a meaningful way")

    try:
        _reseal(out_dir, table, rows)
    except Exception:
        return  # the canonical writer refused the tampered row outright — also a refusal

    emit_time, standalone = both_verifiers(out_dir, inputs)
    caught = emit_time["status"] == "fail" or standalone["status"] == "fail"

    if col in EXPLANATORY_COLUMNS.get(table, ()):
        # Enumerated prose twin: it may legitimately go unnoticed, because the code beside it
        # is reconstructed (see the twin-code test above). Nothing else may.
        return

    assert caught, (
        f"{table}.{col} was rewritten in a fully resealed release and NEITHER verifier "
        "noticed. Every emitted cell must move the bound identity or contradict a "
        "reconstruction."
    )
