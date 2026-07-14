"""Two v2 blockers the independent audit found at 65e58c6. Both were LATENT — green suite, real hole.

**(1) The v2 CLI bound the v1 method.** `run_stage4.main` called `load_method_bundle()` with no
version, so every run — including one whose evidence bundle DECLARES v2 — loaded the seven v1
method files. The v2 method is where `safety_taxonomy_v2.prohibited_outputs_v2.
additional_forbidden_field_names` lives, and that list is the nested no-p/q firewall:

    p_value  q_value  fdr  adjusted_p  organ_system_score  organ_system_burden
    toxicity_score  safety_grade  organ_risk

Bind v1 and none of those names is forbidden. The firewall was not weak on the v2 path — it was
ABSENT, and a nested `p_value` would have sailed through a v2 run untouched. Stage 4 computes no
statistic and consumes none; a forbidden-field list that is not loaded is not a list.

**(2) The v2 verifier required a column the v2 emitter never emits.** `verifier/columns.py`
demanded `source_acquisition.selection_uniqueness`; the emitter writes W8's actual selection
vocabulary — `selection_disposition`, `selection_pin`, `match_total_reported`,
`records_returned`, `result_set_complete`. So EVERY real v2 release carrying acquisition rows was
refused as "unverifiable" (`release_reconstructable`). The suite stayed green because no test
emitted a v2 release WITH acquisition rows and then verified it: the one shape that mattered.

Neither may weaken v1: the historical v1 release is byte-frozen and must keep verifying.
"""

from __future__ import annotations

import json
import os

import pyarrow.parquet as pq
import pytest

from analysis.contract_version import BUNDLE_SCHEMA, ContractVersion
from analysis.emit import emit
from analysis.evidence_bundle import LANE_MODELS, load_evidence_bundle
from analysis.tables_v2 import table_schemas
from analysis.method_config import METHOD_FILES_V1, METHOD_FILES_V2, load_method_bundle
from analysis.pipeline import run_pipeline
from analysis.safety import ForbiddenFieldError, assert_no_forbidden_fields
from fixtures import stage4_inputs, stage4_inputs_v2
from test_stage3_handoff_and_integrity import COMMITTED_BUNDLES
from verifier.checks import verify_release
from verifier.columns import REQUIRED_COLUMNS_V1, REQUIRED_COLUMNS_V2

METHOD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "method")

NESTED_P_VALUE = {
    "candidates": [
        {"candidate_id": "FIXTURE-001",
         "evidence": {"potency": {"summary": {"p_value": "0.003"}}}}      # buried three deep
    ]
}


def _emit(tmp_path, inputs, method):
    out, manifest = emit(inputs, run_pipeline(inputs, method), method, str(tmp_path))
    return out, manifest


# ---------------------------------------------- BLOCKER 1: the CLI must bind the v2 method

def test_the_v2_method_bundle_arms_the_nested_no_pq_firewall():
    """The names only exist at v2. This is what binding v1 for a v2 run threw away."""
    v1 = load_method_bundle(version=ContractVersion.V1).forbidden_fields
    v2 = load_method_bundle(version=ContractVersion.V2).forbidden_fields

    for name in ("p_value", "q_value", "fdr", "adjusted_p"):
        assert name in v2, f"{name} is not forbidden at v2 — the no-p/q firewall is not armed"
        assert name not in v1, (
            f"{name} became forbidden at v1. v1's method files are byte-frozen into every release "
            "ever emitted; they may not change.")


def test_a_nested_p_value_is_rejected_under_the_v2_method_and_invisible_under_v1():
    """NESTED, not top-level: the scan must reach three levels down."""
    v2 = load_method_bundle(version=ContractVersion.V2)
    with pytest.raises(ForbiddenFieldError) as exc:
        assert_no_forbidden_fields(NESTED_P_VALUE, v2.forbidden_fields, "scorecards.json")
    assert "p_value" in str(exc.value)

    # ...and the exact reason the CLI bug mattered: under v1 the same document sails through.
    v1 = load_method_bundle(version=ContractVersion.V1)
    assert_no_forbidden_fields(NESTED_P_VALUE, v1.forbidden_fields, "scorecards.json")


def test_the_cli_selects_the_method_bundle_from_the_admitted_contract():
    """`run_stage4` must choose the method by the contract the evidence bundle DECLARES."""
    from analysis.run_stage4 import method_for_contract

    v1 = method_for_contract(ContractVersion.V1)
    v2 = method_for_contract(ContractVersion.V2)

    assert set(v1.method_file_sha256) == set(METHOD_FILES_V1)
    assert set(v2.method_file_sha256) == set(METHOD_FILES_V2)
    assert "safety_taxonomy_v2" in v2.method_file_sha256
    assert "nebpi_source_framing" in v2.method_file_sha256
    assert "p_value" in v2.forbidden_fields


def test_a_v2_run_binds_the_v2_method_into_the_release(tmp_path):
    """End to end: the release a v2 run writes must record the v2 method files in its identity.
    If it records the v1 seven, the run was never governed by the v2 firewall."""
    i = stage4_inputs_v2()
    method = load_method_bundle(version=ContractVersion.V2)
    _out, manifest = _emit(tmp_path, i, method)

    bound = manifest["method_file_sha256"]
    assert set(bound) == set(METHOD_FILES_V2)
    assert "safety_taxonomy_v2" in bound and "nebpi_source_framing" in bound


def test_a_v1_run_still_binds_exactly_the_seven_frozen_method_files(tmp_path):
    """v1 stays byte-frozen. A v2 addition may never reach into it."""
    i = stage4_inputs()
    method = load_method_bundle(version=ContractVersion.V1)
    _out, manifest = _emit(tmp_path, i, method)
    assert set(manifest["method_file_sha256"]) == set(METHOD_FILES_V1)
    assert len(METHOD_FILES_V1) == 7


# ------------------------------- BLOCKER 2: the verifier must require the EMITTED v2 shape

def test_the_verifier_never_requires_a_column_the_emitter_does_not_emit():
    """THE general guard, against the EMITTED PARQUET SCHEMA — the only authority on what a
    release actually carries.

    A required column that is never emitted refuses every real release, and does it under the
    name `release_reconstructable`, which reads as though the RELEASE were at fault when the
    verifier's own expectation is the stale thing. This is the check that would have caught
    `selection_uniqueness` on the day it landed.
    """
    for version, required in ((ContractVersion.V1, REQUIRED_COLUMNS_V1),
                              (ContractVersion.V2, REQUIRED_COLUMNS_V2)):
        schemas = table_schemas(version)
        for table, cols in required.items():
            assert table in schemas, f"{version} verifier requires table {table!r}, never emitted"
            stale = sorted(set(cols) - set(schemas[table].names))
            assert not stale, (
                f"{version} verifier requires {stale} on {table!r}, which the emitter never "
                "writes. Every real release carrying that table is refused as unverifiable.")


def test_the_v2_verifier_requires_W8s_actual_selection_disposition_fields():
    """W8's `selection.py` vocabulary, not a second one invented in the verifier."""
    required = set(REQUIRED_COLUMNS_V2["source_acquisition"])

    for name in ("selection_disposition", "selection_pin", "match_total_reported",
                 "records_returned", "result_set_complete"):
        assert name in required, f"the v2 verifier does not require {name!r}"

    assert "selection_uniqueness" not in required, (
        "`selection_uniqueness` is a field no emitter has ever written.")


def test_a_v2_release_carrying_acquisition_rows_VERIFIES(tmp_path):
    """The shape that mattered, and the one nothing exercised: a v2 release WITH
    source_acquisition rows, put through the INDEPENDENT verifier."""
    i = stage4_inputs_v2()
    method = load_method_bundle(version=ContractVersion.V2)
    out, _ = _emit(tmp_path, i, method)

    rows = pq.read_table(os.path.join(out, "source_acquisition.parquet")).num_rows
    assert rows, "this test is vacuous without acquisition rows"

    report = verify_release(out, METHOD_DIR)
    failed = [c for c in report["checks"] if c["status"] == "fail"]
    assert report["status"] == "pass", f"a real v2 release does not verify: {failed}"


def test_a_v2_release_missing_a_disposition_field_is_REFUSED(tmp_path):
    """Missing, not merely wrong: a release that cannot say HOW a record was selected cannot
    show that it was not selected by position."""
    i = stage4_inputs_v2()
    method = load_method_bundle(version=ContractVersion.V2)
    out, _ = _emit(tmp_path, i, method)

    path = os.path.join(out, "source_acquisition.parquet")
    t = pq.read_table(path)
    stripped = t.drop_columns(["selection_disposition"])
    pq.write_table(stripped, path)

    report = verify_release(out, METHOD_DIR)
    assert report["status"] == "fail", "a v2 release with no selection_disposition verified"
    assert any(c["check_id"] == "release_reconstructable" and c["status"] == "fail"
               for c in report["checks"])


# ------------------------------------------- BLOCKER 1, END TO END: the real CLI, on a real bundle

LANE_ATTR = {"source_acquisition": "acquisitions"}


def _write_bundle(tmp_path, inputs, version):
    """Serialise a fixture input set into the evidence bundle a real run is handed on disk."""
    bundle = {"schema_id": BUNDLE_SCHEMA[version],
              "sources": {k: json.loads(v.model_dump_json()) for k, v in inputs.sources.items()}}
    for lane in LANE_MODELS[version]:
        # the wire lane and the in-memory attribute differ for exactly one lane; `run_stage4`
        # reads bundle["source_acquisition"] into `inputs.acquisitions`.
        rows = getattr(inputs, LANE_ATTR.get(lane, lane), None) or []
        bundle[lane] = [json.loads(r.model_dump_json()) for r in rows]

    path = str(tmp_path / f"evidence_bundle_{version.value}.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, sort_keys=True)
    return path, bundle


def _method_the_cli_selects(monkeypatch, bundle_path, tmp_path):
    """Drive the REAL argv path and capture the method `main()` hands the Stage-3 door.

    The defect was in `main()`'s selection, so the probe has to go through `main()`. It cannot go
    all the way to a release: no Stage-3 fixture is PAIRED with the Stage-4 evidence fixture (the
    wire bundles describe `AM:INCHIKEY:SYNTH…` candidates, the evidence fixture `FIXTURE-00x`), so
    a full v2 run through this door correctly refuses with `dangling_candidate_ref` long before it
    emits. That pairing needs a real Stage-3 v2 bundle, which is exactly what Stage 4 is waiting
    on. `test_a_v2_run_binds_the_v2_method_into_the_release` covers the emit side.
    """
    import analysis.run_stage4 as R

    seen = {}

    def _capture(_bundle, _evidence, _root, _receipt, _pointer, method, **_kw):
        seen["method"] = method
        return 0

    monkeypatch.setattr(R, "run_stage3_door", _capture)
    rc = R.main(["--stage3-bundle", COMMITTED_BUNDLES["fixture"],
                 "--evidence-bundle", bundle_path, "--outputs-root", str(tmp_path / "out")])
    assert rc == 0
    return seen["method"]


def test_the_v2_CLI_end_to_end_binds_the_v2_method_and_arms_the_nested_firewall(
        monkeypatch, tmp_path):
    """THE probe the audit asked for: the real `main()`, real argv, a real v2 bundle on disk.

    Not `load_method_bundle(version=V2)` called by hand — that was already green while `main()`
    was binding v1 underneath it.
    """
    bundle_path, _ = _write_bundle(tmp_path, stage4_inputs_v2(), ContractVersion.V2)
    method = _method_the_cli_selects(monkeypatch, bundle_path, tmp_path)

    assert set(method.method_file_sha256) == set(METHOD_FILES_V2), (
        "the v2 CLI bound the wrong method. If these are the v1 seven, the nested no-p/q firewall "
        f"never loaded and the run was ungoverned: {sorted(method.method_file_sha256)}")

    # ...and the firewall the CLI armed is the one that catches a p_value buried three deep.
    with pytest.raises(ForbiddenFieldError):
        assert_no_forbidden_fields(NESTED_P_VALUE, method.forbidden_fields, "scorecards.json")


def test_a_v1_CLI_run_still_binds_exactly_the_seven_frozen_files(monkeypatch, tmp_path):
    """The other half: selecting the method by contract must not have moved the v1 path."""
    bundle_path, _ = _write_bundle(tmp_path, stage4_inputs(), ContractVersion.V1)
    method = _method_the_cli_selects(monkeypatch, bundle_path, tmp_path)

    assert set(method.method_file_sha256) == set(METHOD_FILES_V1)
    # and under it, the same nested p_value is invisible — which is precisely why binding v1 for
    # a v2 bundle was a hole rather than a nuisance.
    assert_no_forbidden_fields(NESTED_P_VALUE, method.forbidden_fields, "scorecards.json")


def test_a_bundle_that_declares_no_contract_still_runs_as_v1(tmp_path):
    """Absent is v1 — the frozen default. Only an UNKNOWN schema is unverifiable, and the door
    refuses that by name; the method chooser never gets to guess."""
    from analysis.run_stage4 import contract_of_evidence_bundle

    assert contract_of_evidence_bundle(None) is ContractVersion.V1
    assert contract_of_evidence_bundle(str(tmp_path / "does_not_exist.json")) is ContractVersion.V1

    path, _ = _write_bundle(tmp_path, stage4_inputs_v2(), ContractVersion.V2)
    assert contract_of_evidence_bundle(path) is ContractVersion.V2


def test_a_v2_bundle_carrying_a_nested_p_value_is_refused_at_the_DOOR(tmp_path):
    """Defence in depth, and the honest statement of where each layer sits.

    The typed lanes are `extra="forbid"`, so a statistic smuggled into an evidence row never
    reaches the engine at all — the bundle is refused on load. The method's forbidden-field list
    is the SECOND layer, guarding the document Stage 4 itself writes. Blocker 1 disabled that
    second layer on the v2 path; this pins the first one so a future `extra="allow"` cannot
    quietly become the only thing standing.
    """
    path, bundle = _write_bundle(tmp_path, stage4_inputs_v2(), ContractVersion.V2)
    bundle["potencies"][0]["p_value"] = "0.003"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(bundle, fh, sort_keys=True)

    from analysis.firewall import Rejection

    with pytest.raises(Rejection) as exc:
        load_evidence_bundle(path)
    assert exc.value.code == "evidence_bundle_row_invalid"
    assert "potencies" in str(exc.value)


# ---------- BLOCKER 3: the v2 acquisition profile was unsatisfiable for EVERY real Stage-3 run

def test_a_real_stage3_bundle_with_an_acquisition_complete_v2_bundle_ADMITS(tmp_path):
    """The v2 contract must be SATISFIABLE by the only door a real run comes through.

    `stage3_inputs` merges Stage-3's own source records into `inputs.sources` — upstream
    provenance, carried across untouched. `_acquisition_violations` then walked EVERY source in
    that merged catalog and demanded a Stage-4 acquisition record for each, so all 19 of
    Stage-3's records were refused as `source_not_acquired`.

    Stage 4 cannot hold an acquisition record for bytes STAGE 3 fetched, and never will. So the
    v2 path refused every real Stage-3 bundle, whatever the evidence — the contract could not be
    satisfied by any input that existed. A rule nothing can satisfy is not a firewall.

    The check's own docstring says "every source whose BYTES are CONSUMED". That is the set
    `provenance_bindings` yields, and it is now the set the check walks.
    """
    from analysis.contract_profile import contract_violations
    from analysis.run_stage4 import adapt, load_stage3_bundle, stage3_inputs

    bundle_path, _ = _write_bundle(tmp_path, stage4_inputs_v2(), ContractVersion.V2)

    admission = adapt(*load_stage3_bundle(COMMITTED_BUNDLES["fixture"]))
    built = stage3_inputs(admission, bundle_path)      # the merge that carries Stage-3's sources

    carried = set(admission.source_records)
    assert carried, "this test is vacuous unless Stage 3 brings source records of its own"
    assert not {a.source_record_id for a in built.acquisitions} & carried, (
        "Stage 4 must not be holding acquisition records for bytes Stage 3 fetched")

    violations = contract_violations(built)
    assert not violations, (
        "a real Stage-3 bundle + an acquisition-complete v2 evidence bundle was REFUSED "
        f"({len(violations)} violations, e.g. {violations[0].code}). Stage 4 cannot hold an "
        "acquisition record for bytes STAGE 3 fetched, so the v2 contract was unsatisfiable "
        "through the only door a real run has.")


def test_a_source_a_stage4_row_ACTUALLY_CITES_must_still_be_acquired():
    """The firewall, undiminished. Narrowing to consumed bytes may not let an unacquired source
    underneath a real Stage-4 claim."""
    from dataclasses import replace as dc_replace

    from analysis.contract_profile import contract_violations

    i = stage4_inputs_v2()
    assert not contract_violations(i), "the v2 fixture must start acquisition-complete"

    from analysis.pipeline import provenance_bindings

    _owner, prov = provenance_bindings(i)[0]         # a source a real row actually rests on
    cited = prov.source_record_id
    stripped = dc_replace(i, acquisitions=[a for a in i.acquisitions
                                           if a.source_record_id != cited])
    codes = [v.code for v in contract_violations(stripped)]
    assert "source_not_acquired" in codes, (
        f"a source a real evidence row CITES lost its acquisition record and nothing refused "
        f"it: {codes}")


def test_an_UNCITED_source_carrying_bytes_is_not_demanded():
    """The narrowing, stated directly: Stage-3's carried-across provenance is not Stage-4's to
    acquire. An uncited source underpins no Stage-4 claim, so it is not evidence Stage 4 rests on."""
    from dataclasses import replace as dc_replace

    from analysis.contract_profile import contract_violations
    from analysis.contracts import SourceRecord

    i = stage4_inputs_v2()
    orphan = SourceRecord(
        source_record_id="src.upstream.stage3.never_cited_by_stage4",
        source_type="fixture", source_name="a Stage-3 record, carried across for provenance",
        acquisition_status="synthetic_fixture", access_date="2026-07-13",
        raw_sha256="d" * 64, raw_bytes=1,
    )
    widened = dc_replace(i, sources={**i.sources, orphan.source_record_id: orphan})
    assert not contract_violations(widened), (
        "an uncited upstream source was demanded a Stage-4 acquisition record it can never have")
