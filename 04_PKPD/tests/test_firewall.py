"""Input firewall: what Stage 4 refuses, and with which code."""

from __future__ import annotations

import copy
import json

import pytest

from analysis.firewall import (
    Rejection,
    compute_candidate_rows_sha256,
    production_eligibility,
    resolve_within,
    safe_path_component,
    validate_stage3_candidate_set,
    validate_source_bindings,
)
from analysis.contracts import Namespace
from fixtures import fixture_bytes, load_candidate_set, source_registry, stage4_inputs


def payload() -> dict:
    raw = json.loads(fixture_bytes("stage3_candidate_set.json").decode("utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def rehash(p: dict) -> dict:
    """Re-bind the row hash after editing rows.

    The hash gate fires before the semantic gates (correctly — it is cheaper and
    stricter), so to test a semantic rejection the payload has to be internally
    consistent first. Otherwise these tests would only ever re-prove hash_mismatch.
    """
    from analysis.contracts import Stage3Candidate

    cands = [Stage3Candidate.model_validate(c) for c in p["candidates"]]
    p["candidate_rows_sha256"] = compute_candidate_rows_sha256(cands)
    return p


def test_valid_fixture_candidate_set_passes():
    cset = validate_stage3_candidate_set(payload())
    assert len(cset.candidates) == 4
    assert cset.is_fixture is True


def test_stored_row_hash_is_the_real_hash_of_the_rows():
    cset = load_candidate_set()
    assert compute_candidate_rows_sha256(cset.candidates) == cset.candidate_rows_sha256


def test_unknown_schema_id_is_rejected():
    p = payload()
    p["schema_id"] = "spot.stage03_drug_candidate_set.v2"
    with pytest.raises(Rejection) as exc:
        validate_stage3_candidate_set(p)
    assert exc.value.code == "schema_unknown"


def test_missing_row_hash_is_rejected():
    p = payload()
    del p["candidate_rows_sha256"]
    with pytest.raises(Rejection) as exc:
        validate_stage3_candidate_set(p)
    assert exc.value.code == "hash_missing"


def test_mutating_any_candidate_row_breaks_the_hash():
    """A biology-only id is not a cache key: change a row, the content hash moves."""
    p = payload()
    p["candidates"][0]["mechanism"] = "fixture mechanism, quietly edited"
    with pytest.raises(Rejection) as exc:
        validate_stage3_candidate_set(p)
    assert exc.value.code == "hash_mismatch"


def test_unknown_field_is_rejected():
    p = payload()
    p["candidates"][0]["surprise_field"] = 1
    with pytest.raises(Rejection) as exc:
        validate_stage3_candidate_set(p)
    assert exc.value.code == "schema_invalid"


def test_duplicate_candidate_id_is_rejected():
    p = payload()
    p["candidates"].append(copy.deepcopy(p["candidates"][0]))
    with pytest.raises(Rejection) as exc:
        validate_stage3_candidate_set(rehash(p))
    assert exc.value.code == "duplicate_candidate_identity"


def test_same_moiety_target_mechanism_under_two_ids_is_rejected():
    """The same candidate wearing two ids would double-count its evidence downstream."""
    p = payload()
    twin = copy.deepcopy(p["candidates"][0])
    twin["candidate_id"] = "FIXTURE-001-BIS"
    p["candidates"].append(twin)
    with pytest.raises(Rejection) as exc:
        validate_stage3_candidate_set(rehash(p))
    assert exc.value.code == "duplicate_candidate_identity"


@pytest.mark.parametrize(
    "mutate,expected",
    [
        (lambda m: m.update({"maps_to_active_moiety_id": None}), "salt without a mapping"),
        (lambda m: m.update({"maps_to_active_moiety_id": "FXM-999"}), "mapping points elsewhere"),
        (lambda m: m.update({"mapping_source_record_id": None}), "mapping with no source"),
    ],
)
def test_ambiguous_salt_or_prodrug_mapping_is_rejected(mutate, expected):
    p = payload()
    moiety = p["candidates"][3]["active_moiety"]  # the salt fixture
    assert moiety["administered_form"] == "salt"
    mutate(moiety)
    with pytest.raises(Rejection) as exc:
        validate_stage3_candidate_set(rehash(p))
    assert exc.value.code == "ambiguous_moiety_mapping", expected


def production_payload() -> dict:
    """The internal fixture, promoted to the production namespace, row hash re-bound.

    The fixture itself is `namespace=fixture` — a fixture must never sit in the production
    namespace, and the audit was right that it did. But the production GATES still have to
    be tested, so the tests that exercise them build a production set explicitly here
    instead of leaning on a mislabelled fixture.
    """
    p = payload()
    p["namespace"] = "production"
    for c in p["candidates"]:
        if c["namespace"] == "fixture":
            c["namespace"] = "production"
    return rehash(p)


def test_research_only_set_cannot_contain_a_production_candidate():
    p = production_payload()
    p["namespace"] = "research_only"  # a set-level field: the row hash is unaffected
    with pytest.raises(Rejection) as exc:
        validate_stage3_candidate_set(p)
    assert exc.value.code == "namespace_escalation"


def test_a_fixture_set_is_never_in_the_production_namespace():
    """MINOR 8: the smoke manifest used to read `namespace=production, is_fixture=true`."""
    cset = load_candidate_set()
    assert cset.is_fixture is True
    assert cset.namespace == Namespace.FIXTURE
    assert all(c.namespace != Namespace.PRODUCTION for c in cset.candidates)


def test_research_only_candidate_is_never_production_eligible():
    """Stage 4 adds evidence; it does not launder provenance."""
    cset = load_candidate_set()
    research = next(c for c in cset.candidates if c.namespace == Namespace.RESEARCH_ONLY)
    note = production_eligibility(cset, research)
    assert note.production_eligible is False
    assert note.reason_code == "research_only_namespace"


@pytest.mark.parametrize("compat,code", [("incompatible", "direction_incompatible"),
                                         ("unknown", "direction_unknown")])
def test_direction_incompatibility_blocks_production_eligibility(compat, code):
    """A direction gate is only meaningful in the production namespace, so test it there."""
    from analysis.contracts import Stage3Candidate

    cset = validate_stage3_candidate_set(production_payload())
    row = cset.candidates[0].model_dump(mode="json") | {"direction_compatibility": compat}
    c = Stage3Candidate.model_validate(row)
    assert production_eligibility(cset, c).reason_code == code


@pytest.mark.parametrize("bad", ["../escape", "/etc/passwd", "a/b", "..", ".hidden", "x\x00y", ""])
def test_path_traversal_is_rejected(bad):
    with pytest.raises(Rejection) as exc:
        safe_path_component(bad)
    assert exc.value.code == "path_traversal"


def test_resolve_within_blocks_escape(tmp_path):
    root = str(tmp_path)
    assert resolve_within(root, "sub/file.json").startswith(root)
    with pytest.raises(Rejection) as exc:
        resolve_within(root, "../../etc/passwd")
    assert exc.value.code == "path_traversal"


def test_evidence_bound_to_an_unknown_source_is_rejected():
    inputs = stage4_inputs()
    prov = inputs.properties[0].provenance
    with pytest.raises(Rejection) as exc:
        validate_source_bindings([("p", prov)], {})
    assert exc.value.code == "unbound_source_record"


def test_mutating_a_source_hash_is_rejected():
    """Change what the registry says the bytes were, and every number bound to it fails."""
    inputs = stage4_inputs()
    reg = source_registry()
    sid = inputs.properties[0].provenance.source_record_id
    reg[sid] = reg[sid].model_copy(update={"raw_sha256": "a" * 64})
    with pytest.raises(Rejection) as exc:
        validate_source_bindings([("p", inputs.properties[0].provenance)], reg)
    assert exc.value.code == "source_hash_mismatch"


def test_there_is_no_model_output_source_type():
    """LLM output is never a scientific source — it has no door into the registry."""
    from analysis.contracts import SourceRecord

    with pytest.raises(Exception):
        SourceRecord(
            source_record_id="src.bad", source_type="model_output", source_name="claude",
            access_date="2026-07-11", raw_sha256="0" * 64,
        )
