"""scorecard_set_id derivation, artifact emission, mutation detection, determinism.

The mutation tests are the point of the stage: change a source hash, a candidate row, a
method file, a rule, an evidence row or the manifest, and verification must fail.
"""

from __future__ import annotations

import json
import os
import shutil

import pyarrow.parquet as pq
import pytest

from analysis.contract_version import ContractVersion
from analysis.emit import artifact_allowlist, emit, environment_lock

from analysis.ids import derive_scorecard_set_id
from analysis.method_config import load_method_bundle
from analysis.pipeline import run_pipeline
from analysis.safety import assert_no_forbidden_fields
from analysis.verify import verify_output_dir
from fixtures import stage4_inputs

ARTIFACTS = artifact_allowlist(ContractVersion.V1)

METHOD = load_method_bundle()


@pytest.fixture
def emitted(tmp_path):
    inputs = stage4_inputs()
    result = run_pipeline(inputs, METHOD)
    out, manifest = emit(inputs, result, METHOD, str(tmp_path))
    return inputs, result, out, manifest


def _id_for(inputs) -> str:
    return derive_scorecard_set_id(
        inputs.candidate_set, METHOD, inputs.evidence_lanes(), inputs.sources,
        environment_lock()["lock_sha256"], inputs.config,
    )[0]


# --------------------------------------------------------------- scorecard_set_id

def test_id_binds_stage3_content_method_sources_evidence_and_environment():
    inputs = stage4_inputs()
    _, key = derive_scorecard_set_id(
        inputs.candidate_set, METHOD, inputs.evidence_lanes(), inputs.sources,
        environment_lock()["lock_sha256"], inputs.config,
    )
    assert key["stage3"]["candidate_rows_sha256"] == inputs.candidate_set.candidate_rows_sha256
    assert set(key) == {
        "stage3", "stage4_method_version", "method_file_sha256", "analysis_code_sha256",
        "config_sha256", "evidence_inputs_sha256", "source_registry_sha256",
        "environment_lock_sha256",
    }
    # namespace and fixture status are part of content identity, not a label on the side.
    assert key["stage3"]["namespace"] == inputs.candidate_set.namespace.value
    assert key["stage3"]["is_fixture"] == inputs.candidate_set.is_fixture
    # A biology-only identifier is not enough on its own.
    assert key["stage3"]["candidate_set_id"] != _id_for(inputs)


def test_changing_the_property_calculator_changes_the_id():
    """Swap the ClogD package and the score changes while the biology does not. The cache
    key must move, or a stale scorecard would be served for a different number."""
    a = stage4_inputs()
    b = stage4_inputs()
    idx = next(i for i, p in enumerate(b.properties) if p.property_id == "clogd_74")
    b.properties[idx] = b.properties[idx].model_copy(update={"calculator_id": "chemaxon_logd"})
    assert _id_for(a) != _id_for(b)


def test_changing_a_property_source_record_changes_the_id():
    a = stage4_inputs()
    b = stage4_inputs()
    prov = b.properties[0].provenance.model_copy(update={"source_record_id": "src.fixture.props.acd"})
    b.properties[0] = b.properties[0].model_copy(update={"provenance": prov})
    assert _id_for(a) != _id_for(b)


def test_changing_a_source_raw_hash_changes_the_id():
    a = stage4_inputs()
    b = stage4_inputs()
    sid = "src.fixture.exposure"
    b.sources[sid] = b.sources[sid].model_copy(update={"raw_sha256": "b" * 64})
    assert _id_for(a) != _id_for(b)


def test_changing_a_method_file_changes_the_id(tmp_path):
    """An inflection point is content: edit it and every cached scorecard is invalid."""
    inputs = stage4_inputs()
    method_dir = str(tmp_path / "method")
    shutil.copytree(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "04_PKPD", "method")
                    if False else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "method"),
                    method_dir)
    with open(os.path.join(method_dir, "cns_mpo_wager2010_v1.json"), encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["properties"][0]["inflection_points"]["x2"] = 5.5  # ClogP 5 -> 5.5
    with open(os.path.join(method_dir, "cns_mpo_wager2010_v1.json"), "w") as fh:
        json.dump(doc, fh)

    tampered = load_method_bundle(method_dir)
    env = environment_lock()["lock_sha256"]
    original = derive_scorecard_set_id(inputs.candidate_set, METHOD, inputs.evidence_lanes(), inputs.sources, env, inputs.config)[0]
    mutated = derive_scorecard_set_id(inputs.candidate_set, tampered, inputs.evidence_lanes(), inputs.sources, env, inputs.config)[0]
    assert original != mutated


def test_changing_an_evidence_row_changes_the_id():
    a = stage4_inputs()
    b = stage4_inputs()
    b.exposures[0] = b.exposures[0].model_copy(update={"concentration_source_string": "41"})
    assert _id_for(a) != _id_for(b)


def test_adding_a_potency_context_link_changes_the_id():
    """The audit turned a margin from not_computable into computed without moving the id."""
    from analysis.evidence_records import PotencyContextLink, Provenance

    a = stage4_inputs()
    b = stage4_inputs()
    b.potency_context_links = [PotencyContextLink(
        link_id="LNK-X", potency_id="POT-001", tumor_context="OTHER_TUMOR",
        rationale="sourced relevance review",
        provenance=Provenance(source_record_id="src.fixture.potency", access_date="2026-07-11",
                              raw_response_sha256=a.sources["src.fixture.potency"].raw_sha256,
                              extraction_transform="test"),
    )]
    assert _id_for(a) != _id_for(b)


def test_relabelling_a_fixture_source_as_public_changes_the_id():
    """Relabelling fixture sources as public data left the id identical and made the
    production preflight report eligible=true."""
    from analysis.contracts import SourceRecord

    a = stage4_inputs()
    b = stage4_inputs()
    sid = "src.fixture.exposure"
    b.sources[sid] = SourceRecord.model_validate(
        b.sources[sid].model_dump(mode="json") | {
            "acquisition_status": "acquired_public", "source_type": "public_api",
            "url": "https://example.org/x", "record_id": "R1", "release_version": "v1",
            "license": "CC0",
        }
    )

    assert _id_for(a) != _id_for(b)


def test_altering_the_scoring_code_changes_the_id():
    """A changed scoring implementation must not serve a cached scorecard."""
    from analysis.ids import code_tree_sha256

    inputs = stage4_inputs()
    env = environment_lock()["lock_sha256"]
    real = code_tree_sha256()[0]
    a = derive_scorecard_set_id(inputs.candidate_set, METHOD, inputs.evidence_lanes(),
                                inputs.sources, env, inputs.config, code_sha256=real)[0]
    b = derive_scorecard_set_id(inputs.candidate_set, METHOD, inputs.evidence_lanes(),
                                inputs.sources, env, inputs.config, code_sha256="f" * 64)[0]
    assert a != b


def test_id_is_stable_for_identical_inputs():
    assert _id_for(stage4_inputs()) == _id_for(stage4_inputs())


# ------------------------------------------------------------------------- emission

def test_all_eight_artifacts_are_emitted(emitted):
    _, _, out, _ = emitted
    assert sorted(os.listdir(out)) == sorted(ARTIFACTS)


def test_emitted_set_verifies(emitted):
    inputs, _, out, _ = emitted
    v = verify_output_dir(out, inputs, METHOD)
    assert v["status"] == "pass", [c for c in v["checks"] if c["status"] == "fail"]
    assert v["n_checks"] > 100


def test_output_dir_is_the_scorecard_set_id(emitted):
    inputs, _, out, manifest = emitted
    assert os.path.basename(out) == manifest["scorecard_set_id"] == _id_for(inputs)


def test_manifest_records_row_order_dtypes_float_rules_and_environment(emitted):
    _, _, _, manifest = emitted
    # Identity content carries exact decimals; there is no universal float grid any more.
    assert "exact decimal" in manifest["float_rules"]["identity"]
    assert "floats are rejected" in manifest["float_rules"]["identity"]
    assert manifest["float_rules"]["publication_rounding"].startswith("ROUND_HALF_UP")
    assert manifest["environment"]["lock_sha256"]
    assert manifest["environment"]["observed_runtime"]["python"].startswith("3.12")
    assert manifest["analysis_code_sha256"]
    assert manifest["environment"]["observed_matches_lock"] is True
    tables = {a["table"]: a for a in manifest["artifacts"] if a["table"]}
    assert set(tables) == {
        "delivery_evidence", "transporter_evidence", "exposure_evidence", "safety_evidence",
        "nebpi_decisions", "nebpi_criteria",
        "contexts", "drug_forms", "property_evidence", "potency_evidence",
        # `delivery_assignments` is the INPUT the delivery decision is reduced from. Without
        # it in the release the verifier could only re-read the generator's reduced answer.
        "potency_context_links", "delivery_assignments", "nebpi_observations",
        "search_manifests", "source_catalog",
        # NOT fraction_unbound / source_acquisition: this is a v1 release, and a v1 release does
        # not carry two empty v2 tables. An empty `source_acquisition.parquet` would be a claim
        # that the release HAS an acquisition manifest and that it is empty, which is false.
    }
    for a in tables.values():
        assert a["columns"] and a["dtypes"] and a["sort_key"]
        assert a["content_sha256"] and a["file_sha256"]


def test_no_artifact_contains_a_traffic_light_or_composite_score(emitted):
    _, _, out, _ = emitted
    for name in ("scorecards.json", "manifest.json", "selection.json", "verification.json"):
        with open(os.path.join(out, name), encoding="utf-8") as fh:
            assert_no_forbidden_fields(json.load(fh), METHOD.forbidden_fields, name)
    for name in ARTIFACTS:
        if name.endswith(".parquet"):
            cols = [c.lower() for c in pq.read_schema(os.path.join(out, name)).names]
            assert not set(cols) & {f.lower() for f in METHOD.forbidden_fields}


def test_selection_emits_no_ranking_in_a_fixture_pass(emitted):
    _, _, out, _ = emitted
    with open(os.path.join(out, "selection.json"), encoding="utf-8") as fh:
        sel = json.load(fh)
    assert sel["selection_status"] == "no_selection_emitted"
    assert sel["selected"] == []
    assert sel["is_fixture"] is True
    assert "not a ranker" in sel["reason"]


def test_scorecards_order_is_declared_non_evaluative(emitted):
    _, _, out, _ = emitted
    with open(os.path.join(out, "scorecards.json"), encoding="utf-8") as fh:
        sc = json.load(fh)
    assert sc["ordering"]["is_ranking"] is False
    ids = [c["candidate_id"] for c in sc["candidates"]]
    assert ids == sorted(ids)


def test_every_displayed_number_traces_to_a_source_hash_or_a_declared_transform(emitted):
    _, _, out, _ = emitted
    with open(os.path.join(out, "scorecards.json"), encoding="utf-8") as fh:
        sc = json.load(fh)
    for cand in sc["candidates"]:
        chain = cand["provenance_chain"]
        assert chain, cand["candidate_id"]
        for link in chain:
            assert link["field_path"] and "transform" in link
            # Either it points at a response, or it is a declared transform of rows that do.
            assert link.get("raw_response_sha256") or link.get("note") or link.get("transform")


# -------------------------------------------------------------- mutation detection

def test_mutating_a_parquet_evidence_row_fails_verification(emitted):
    inputs, _, out, _ = emitted
    path = os.path.join(out, "exposure_evidence.parquet")
    table = pq.read_table(path).to_pylist()
    table[0]["concentration_source_string"] = "999"
    import pyarrow as pa

    from analysis.tables import table_schemas
    pq.write_table(pa.Table.from_pylist(table, schema=table_schemas(ContractVersion.V1)["exposure_evidence"]), path)

    v = verify_output_dir(out, inputs, METHOD)
    assert v["status"] == "fail"
    failed = {c["check_id"] for c in v["checks"] if c["status"] == "fail"}
    assert "artifact_content_sha256::exposure_evidence.parquet" in failed
    assert "artifact_file_sha256::exposure_evidence.parquet" in failed


def test_mutating_the_manifest_hash_fails_verification(emitted):
    inputs, _, out, _ = emitted
    path = os.path.join(out, "manifest.json")
    with open(path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    manifest["manifest_content_sha256"] = "0" * 64
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh)

    v = verify_output_dir(out, inputs, METHOD)
    assert v["status"] == "fail"
    assert any(c["check_id"] == "manifest_self_hash" and c["status"] == "fail" for c in v["checks"])


def test_mutating_a_source_hash_fails_verification(emitted):
    inputs, _, out, _ = emitted
    sid = "src.fixture.exposure"
    inputs.sources[sid] = inputs.sources[sid].model_copy(update={"raw_sha256": "c" * 64})

    v = verify_output_dir(out, inputs, METHOD)
    assert v["status"] == "fail"
    failed = {c["check_id"] for c in v["checks"] if c["status"] == "fail"}
    assert "source_registry_sha256_unchanged" in failed
    assert "scorecard_set_id_rederived" in failed


def test_mutating_an_evidence_input_row_fails_verification(emitted):
    inputs, _, out, _ = emitted
    inputs.exposures[0] = inputs.exposures[0].model_copy(
        update={"concentration_source_string": "41"})

    v = verify_output_dir(out, inputs, METHOD)
    assert v["status"] == "fail"
    failed = {c["check_id"] for c in v["checks"] if c["status"] == "fail"}
    assert "evidence_inputs_sha256_unchanged" in failed
    assert "scorecard_set_id_rederived" in failed


def test_mutating_a_method_rule_fails_verification(emitted, tmp_path):
    inputs, _, out, _ = emitted
    method_dir = tmp_path / "m"
    shutil.copytree(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "method"), method_dir)
    with open(method_dir / "delivery_rules_v1.json", encoding="utf-8") as fh:
        rules = json.load(fh)
    rules["values"][1]["nebpi_primary_gate"] = True  # systemic priming, silently gated
    with open(method_dir / "delivery_rules_v1.json", "w", encoding="utf-8") as fh:
        json.dump(rules, fh)

    v = verify_output_dir(out, inputs, load_method_bundle(str(method_dir)))
    assert v["status"] == "fail"
    failed = {c["check_id"] for c in v["checks"] if c["status"] == "fail"}
    assert "method_file_sha256_unchanged" in failed
    assert "scorecard_set_id_rederived" in failed


def test_mutating_a_stage3_candidate_row_fails_verification(emitted):
    """A row edited in place with its declared hash left untouched. The id binds the
    DECLARED hash, so the id alone would not move — verification has to recompute the
    row hash from the rows rather than trust what the artifact says it is."""
    inputs, _, out, _ = emitted
    rows = [c.model_dump(mode="json") for c in inputs.candidate_set.candidates]
    rows[0]["mechanism"] = "quietly edited"
    inputs.candidate_set = inputs.candidate_set.model_copy(update={
        "candidates": [type(inputs.candidate_set.candidates[0]).model_validate(r) for r in rows]
    })

    v = verify_output_dir(out, inputs, METHOD)
    assert v["status"] == "fail"
    assert any(c["check_id"] == "stage3_candidate_rows_recomputed" and c["status"] == "fail"
               for c in v["checks"])


def test_a_forged_scorecard_class_without_a_satisfied_branch_fails_verification(emitted):
    """Generator != evaluator: verification re-derives the claim from the document."""
    inputs, _, out, _ = emitted
    path = os.path.join(out, "scorecards.json")
    with open(path, encoding="utf-8") as fh:
        sc = json.load(fh)
    for cand in sc["candidates"]:
        for n in cand["lanes"]["nebpi"]:
            if n["nebpi_status"] == "not_classifiable":
                n["nebpi_class"] = "sufficiently_permeable"  # a class with no evidence
                n["nebpi_status"] = "classified"
                break
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(sc, fh)

    v = verify_output_dir(out, inputs, METHOD)
    assert v["status"] == "fail"
    # The independent verifier rebuilt the class from the evidence tables and disagrees.
    assert any(c["check_id"].startswith("json_parquet_nebpi") and c["status"] == "fail"
               for c in v["checks"])


# ------------------------------------------------------------------- determinism

def test_rerun_produces_identical_canonical_hashes(tmp_path):
    """Same inputs, same method, same environment -> byte-identical artifacts."""
    out_a, man_a = emit(stage4_inputs(), run_pipeline(stage4_inputs(), METHOD), METHOD, str(tmp_path / "a"))
    out_b, man_b = emit(stage4_inputs(), run_pipeline(stage4_inputs(), METHOD), METHOD, str(tmp_path / "b"))

    assert man_a["scorecard_set_id"] == man_b["scorecard_set_id"]
    assert man_a["evidence_inputs_sha256"] == man_b["evidence_inputs_sha256"]

    a = {x["filename"]: x for x in man_a["artifacts"]}
    b = {x["filename"]: x for x in man_b["artifacts"]}
    for name in a:
        assert a[name]["content_sha256"] == b[name]["content_sha256"], name
        assert a[name]["file_sha256"] == b[name]["file_sha256"], name

    for name in ARTIFACTS:
        if name in ("manifest.json", "verification.json"):
            continue  # manifest carries created_at, excluded from canonical content
        with open(os.path.join(out_a, name), "rb") as fa, open(os.path.join(out_b, name), "rb") as fb:
            assert fa.read() == fb.read(), name


def test_manifest_content_hash_ignores_the_timestamp(tmp_path):
    from analysis.canonical import content_sha256

    out_a, man_a = emit(stage4_inputs(), run_pipeline(stage4_inputs(), METHOD), METHOD, str(tmp_path / "a"))
    out_b, man_b = emit(stage4_inputs(), run_pipeline(stage4_inputs(), METHOD), METHOD, str(tmp_path / "b"))
    assert man_a["created_at"] != man_b["created_at"] or True  # may collide; not the point
    assert content_sha256(man_a) == content_sha256(man_b)


def test_emission_is_atomic_on_failure(tmp_path, monkeypatch):
    """A half-written scorecard set that still hashes would be worse than none."""
    import analysis.emit as emit_mod

    inputs = stage4_inputs()
    result = run_pipeline(inputs, METHOD)
    monkeypatch.setattr(emit_mod, "build_selection", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError, match="boom"):
        emit_mod.emit(inputs, result, METHOD, str(tmp_path))
    assert os.listdir(tmp_path) == []  # no partial directory left behind
