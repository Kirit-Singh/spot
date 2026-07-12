"""Schema drift, the Stage-3 provisional declaration, the CLI fail-closed gates, and
the environment lock.
"""

from __future__ import annotations

import json
import os

import pytest

from analysis import schemas_export
from analysis.contracts import STAGE3_CONTRACT_STATUS, Namespace
from analysis.emit import ENV_LOCK_PATH, ENV_LOCK_SRC_PATH, environment_lock
from analysis.method_config import load_method_bundle
from analysis.pipeline import run_pipeline
from analysis.run_stage4 import (
    PRODUCTION_POINTER,
    ProductionGateRefusal,
    fixture_inputs,
    main,
    production_pointer_decision,
    write_production_pointer,
)
from fixtures import stage4_inputs

METHOD = load_method_bundle()


# ------------------------------------------------------------------- schema drift

@pytest.mark.parametrize("filename", sorted(schemas_export.GENERATED))
def test_exported_schema_matches_the_code(filename):
    """The published contract cannot silently disagree with the enforced one.

    If this fails: python -m analysis.schemas_export
    """
    path = os.path.join(schemas_export.SCHEMA_DIR, filename)
    with open(path, encoding="utf-8") as fh:
        on_disk = fh.read()
    regenerated = schemas_export.render(schemas_export.GENERATED[filename]())
    assert on_disk == regenerated, f"{filename} is stale — regenerate it"


def test_table_schema_export_matches_the_parquet_writer():
    from analysis.tables import SORT_KEYS, TABLE_SCHEMAS

    exported = schemas_export.tables_schema()["tables"]
    assert set(exported) == set(TABLE_SCHEMAS)
    for name, schema in TABLE_SCHEMAS.items():
        assert exported[name]["columns"] == list(schema.names)
        assert exported[name]["dtypes"] == [str(f.type) for f in schema]
        assert exported[name]["sort_key"] == list(SORT_KEYS[name])


# ------------------------------------------------- Stage-3 contract is provisional

def test_stage3_contract_is_reconciled_against_the_real_stage3():
    """Stage 3 has landed. Stage 4 consumes its real documents through the adapter, and
    says so — including that a production Stage-3 lock is not producible yet."""
    assert STAGE3_CONTRACT_STATUS["status"] == "reconciled_via_adapter"
    assert STAGE3_CONTRACT_STATUS["stage3_implementation_landed"] is True
    assert STAGE3_CONTRACT_STATUS["validated_against_real_stage3_output"] is True
    assert STAGE3_CONTRACT_STATUS["production_stage3_producible_today"] is False
    assert "stage3_adapter" in STAGE3_CONTRACT_STATUS["adapter"]
    assert len(STAGE3_CONTRACT_STATUS["stage3_documents"]) == 3


def test_stage3_schema_file_carries_the_contract_status():
    path = os.path.join(schemas_export.SCHEMA_DIR, "spot.stage03_drug_candidate_set.v1.schema.json")
    with open(path, encoding="utf-8") as fh:
        schema = json.load(fh)
    assert schema["x-spot-stage3-contract-status"] == STAGE3_CONTRACT_STATUS


def test_emitted_artifacts_carry_the_stage3_contract_status(tmp_path):
    from analysis.emit import emit

    inputs = stage4_inputs()
    out, manifest = emit(inputs, run_pipeline(inputs, METHOD), METHOD, str(tmp_path))
    assert manifest["upstream"]["stage3_contract_status"] == STAGE3_CONTRACT_STATUS
    with open(os.path.join(out, "scorecards.json"), encoding="utf-8") as fh:
        status = json.load(fh)["upstream"]["stage3_contract_status"]
    assert status["stage3_implementation_landed"] is True
    assert status["production_stage3_producible_today"] is False


# --------------------------------------------------------------- CLI, fail-closed

def test_fixture_run_can_never_write_a_production_pointer():
    inputs = stage4_inputs()
    result = run_pipeline(inputs, METHOD)
    decision = production_pointer_decision(inputs, result)

    assert decision["eligible"] is False
    assert decision["production_pointer_written"] is False
    codes = " ".join(decision["refusals"])
    assert "fixture_input" in codes
    assert "fixture_sources" in codes

    with pytest.raises(ProductionGateRefusal, match="refusing to write a production pointer"):
        write_production_pointer("/tmp", inputs, result, "deadbeef")


def test_research_only_namespace_is_refused_a_production_pointer():
    inputs = stage4_inputs()
    inputs.candidate_set = inputs.candidate_set.model_copy(
        update={"namespace": Namespace.RESEARCH_ONLY}
    )
    decision = production_pointer_decision(inputs, run_pipeline(inputs, METHOD))
    assert any("research_only_namespace" in r for r in decision["refusals"])


def test_even_a_clean_run_is_refused_a_production_pointer_in_this_pass():
    """No --force. Real evidence and a real Stage-3 artifact come first.

    `is_fixture` is no longer a settable label: it is derived from acquisition_status, so
    a source can only stop being a fixture by claiming to be an acquired public record —
    which then has to carry a URL, a record id, a release, a license and a byte count.
    """
    from analysis.contracts import Stage3Candidate, SourceRecord

    inputs = stage4_inputs()
    # The fixture set is namespace=fixture (a fixture never sits in the production
    # namespace). To test the PRODUCTION pointer gate, build a production set explicitly.
    promoted = [
        Stage3Candidate.model_validate(c.model_dump(mode="json") | {"namespace": "production"})
        if c.namespace == Namespace.FIXTURE else c
        for c in inputs.candidate_set.candidates
    ]
    inputs.candidate_set = inputs.candidate_set.model_copy(
        update={"is_fixture": False, "namespace": Namespace.PRODUCTION, "candidates": promoted})
    for sid, rec in inputs.sources.items():
        # Re-validated, not model_copy'd: a relabel has to satisfy the acquired_public
        # rules (locator + release + license + bytes), which is the whole point.
        inputs.sources[sid] = SourceRecord.model_validate(
            rec.model_dump(mode="json") | {
                "acquisition_status": "acquired_public", "source_type": "public_api",
                "url": f"https://example.org/{sid}", "record_id": sid,
                "release_version": "v1", "license": "CC0",
            }
        )
    result = run_pipeline(inputs, METHOD)

    assert production_pointer_decision(inputs, result)["eligible"] is True
    with pytest.raises(ProductionGateRefusal, match="no independently reviewed real-source"):
        write_production_pointer("/tmp", inputs, result, "deadbeef")


def test_fixture_inputs_are_labelled_as_fixtures():
    assert fixture_inputs().candidate_set.is_fixture is True


def test_cli_needs_exactly_one_input(capsys):
    assert main([]) == 2
    assert "supply exactly one" in capsys.readouterr().err


def test_cli_refuses_both_doors_at_once(tmp_path, capsys):
    assert main(["--fixtures", "--stage3-bundle", str(tmp_path)]) == 2
    assert "supply exactly one" in capsys.readouterr().err


def test_cli_fixture_smoke_run(tmp_path, capsys):
    rc = main(["--fixtures", "--outputs-root", str(tmp_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "verification     : pass" in out
    assert "selection        : no_selection_emitted" in out
    assert "production ptr   : not written" in out
    assert "FIXTURE run" in out

    written = os.listdir(tmp_path)
    assert len(written) == 1  # exactly one scorecard set directory
    assert PRODUCTION_POINTER not in written
    from analysis.emit import ARTIFACTS

    assert sorted(os.listdir(tmp_path / written[0])) == sorted(ARTIFACTS)


def test_cli_refuses_the_production_pointer_flag_with_a_nonzero_exit(tmp_path, capsys):
    rc = main(["--fixtures", "--outputs-root", str(tmp_path), "--write-production-pointer"])
    assert rc == 3
    assert "REFUSED" in capsys.readouterr().err
    assert PRODUCTION_POINTER not in os.listdir(tmp_path)


# ----------------------------------------------------------------- environment lock

def test_the_lock_is_a_real_hash_pinned_solver_lock():
    """Not a loose requirements list: every distribution is sha256-pinned."""
    assert ENV_LOCK_PATH.endswith("requirements-stage4.lock")
    with open(ENV_LOCK_PATH, encoding="utf-8") as fh:
        text = fh.read()
    assert "pip-compile" in text and "--generate-hashes" in text
    assert text.count("--hash=sha256:") > 100
    pins = [ln for ln in text.splitlines() if "==" in ln and not ln.strip().startswith("#")]
    assert len(pins) >= 10  # direct + transitive, all pinned
    assert os.path.exists(ENV_LOCK_SRC_PATH)


def test_environment_lock_is_reported_honestly_and_matches_the_runtime():
    env = environment_lock()
    assert env["production_lockable"] is True
    assert "--require-hashes" in env["lock_kind"]
    assert env["observed_matches_lock"] is True, env["divergent_packages"]
    assert env["locked_direct_versions"]["pyarrow"] == env["observed_runtime"]["pyarrow"]
    assert env["lock_sha256"] and len(env["lock_sha256"]) == 64


def test_changing_the_lock_changes_the_scorecard_set_id():
    from analysis.ids import derive_scorecard_set_id

    inputs = stage4_inputs()
    a = derive_scorecard_set_id(inputs.candidate_set, METHOD, inputs.evidence_lanes(),
                                inputs.sources, "a" * 64, inputs.config)[0]
    b = derive_scorecard_set_id(inputs.candidate_set, METHOD, inputs.evidence_lanes(),
                                inputs.sources, "b" * 64, inputs.config)[0]
    assert a != b
