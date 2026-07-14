"""The acquisition manifest: what makes a source record re-fetchable and checkable.

The audit's finding (STAGE4_PK_SOURCE_AUDIT.md §4.7): the source contract carried an access
DATE but no UTC timestamp, no canonical query, no terms URL, no HTTP status and no response
headers, and there was no adapter-code hash anywhere. These tests pin the repair.

Nothing here touches the network. The bytes are synthetic fixtures; the run root is a tmp dir.
"""

from __future__ import annotations

import json
import os

import pytest
from pydantic import ValidationError

from analysis.acquisition import (
    ACQUISITION_SCHEMA_ID,
    AcquisitionManifest,
    AcquisitionRecord,
    RunRoot,
    fixture_record,
    manifest_content_sha256,
    to_source_record,
    verify_cached_bytes,
)
from analysis.firewall import Rejection

RAW = b'{"cid": 5394, "inchikey": "BPEGJWRSRHCHSN-UHFFFAOYSA-N"}'
RAW_SHA = "0" * 64  # replaced in fixtures below by the real digest


def _public_record(**over) -> AcquisitionRecord:
    from analysis.canonical import sha256_bytes

    kw = dict(
        acquisition_record_id="acq_pubchem_cid_5394",
        source_key="pubchem",
        source_name="PubChem PUG REST",
        source_type="public_api",
        origin="fetched_public",
        stable_record_id="5394",
        url="https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid/5394/property/InChIKey/JSON",
        canonical_query="compound/cid/5394/property/InChIKey/JSON",
        accessed_at_utc="2026-07-13T05:00:00Z",
        http_status=200,
        raw_media_type="application/json",
        response_headers={"content-type": "application/json"},
        release_or_last_updated="not_reported_by_source",
        license="NCBI: no NCBI restriction on molecular data; third-party rights may exist",
        license_or_terms_url="https://www.ncbi.nlm.nih.gov/home/about/policies/",
        raw_bytes=len(RAW),
        raw_sha256=sha256_bytes(RAW),
        cache_relpath="raw/pubchem/" + sha256_bytes(RAW) + ".json",
        extraction_transform="pubchem.parse_property_table:v1",
        adapter_code_sha256="a" * 64,
        review_status="unreviewed",
        evidence_state="observed",
    )
    kw.update(over)
    return AcquisitionRecord(**kw)


# --------------------------------------------------------------- the required fields


def test_a_fetched_public_record_carries_every_field_the_audit_requires():
    r = _public_record()
    required = [
        "source_record_id", "source_type", "source_name", "stable_record_id", "url",
        "canonical_query", "accessed_at_utc", "release_or_last_updated",
        "license_or_terms_url", "raw_media_type", "http_status", "raw_bytes", "raw_sha256",
        "extraction_transform", "adapter_code_sha256", "review_status",
    ]
    doc = r.model_dump()
    doc["source_record_id"] = doc["acquisition_record_id"]
    for field in required:
        assert doc.get(field) not in (None, ""), f"{field} is required by the admission checklist"


@pytest.mark.parametrize(
    "missing",
    ["url", "canonical_query", "accessed_at_utc", "http_status", "raw_sha256", "raw_bytes",
     "license_or_terms_url", "raw_media_type", "cache_relpath"],
)
def test_a_fetched_public_record_without_its_locator_or_its_bytes_is_refused(missing):
    with pytest.raises(ValidationError, match="fetched_public"):
        _public_record(**{missing: None})


def test_source_terms_are_not_optional_a_source_may_not_declare_itself_free():
    """`source_terms_recorded` — consequence_on_fail: refuse_release."""
    with pytest.raises(ValidationError, match="license_or_terms_url"):
        _public_record(license_or_terms_url=None)


def test_a_non_200_response_is_never_evidence():
    with pytest.raises(ValidationError, match="http_status"):
        _public_record(http_status=404)


def test_a_cache_path_may_never_be_machine_local():
    """The raw bytes live outside Git under a caller-supplied run root; the manifest records
    the path RELATIVE to it. An absolute path is not content and is not re-verifiable."""
    with pytest.raises(ValidationError, match="machine-local|relative"):
        _public_record(cache_relpath="/home/somebody/.spot-runs/x/raw/abc.json")


def test_a_synthetic_fixture_is_never_an_acquired_public_record():
    rec = fixture_record(
        acquisition_record_id="acq_fx_1",
        source_key="dailymed",
        raw=b"<document/>",
        extraction_transform="label_adapters.parse_dailymed_spl:v1",
        adapter_code_sha256="b" * 64,
    )
    assert rec.origin == "synthetic_fixture"
    assert rec.evidence_state == "not_applicable"
    assert rec.raw_sha256 and rec.url is None
    # Relabelling a fixture as an acquired public record cannot be done by editing one field:
    # the public record's locator and terms are simply not there.
    with pytest.raises(ValidationError, match="fetched_public"):
        AcquisitionRecord.model_validate({**rec.model_dump(), "origin": "fetched_public"})


# ------------------------------------------------------------- content-addressed cache


def test_the_run_root_caches_raw_bytes_outside_git_and_addresses_them_by_hash(tmp_path):
    root = RunRoot(str(tmp_path))
    relpath, sha = root.store(RAW, source_key="pubchem", suffix=".json")

    from analysis.canonical import sha256_bytes

    assert sha == sha256_bytes(RAW)
    assert sha in relpath and not os.path.isabs(relpath)
    assert root.read(relpath) == RAW
    # written under the run root, not into the repo
    assert os.path.isfile(os.path.join(str(tmp_path), relpath))


def test_storing_the_same_bytes_twice_is_one_cache_entry(tmp_path):
    root = RunRoot(str(tmp_path))
    a, sha_a = root.store(RAW, source_key="pubchem", suffix=".json")
    b, sha_b = root.store(RAW, source_key="pubchem", suffix=".json")
    assert (a, sha_a) == (b, sha_b)


def test_mutated_cached_bytes_are_refused_the_hash_is_the_evidence(tmp_path):
    """FAIL-CLOSED (hash): `source_bytes_bound` -> refuse_row."""
    root = RunRoot(str(tmp_path))
    relpath, _ = root.store(RAW, source_key="pubchem", suffix=".json")
    rec = _public_record(cache_relpath=relpath)
    verify_cached_bytes(rec, root)  # clean

    with open(os.path.join(str(tmp_path), relpath), "wb") as fh:
        fh.write(RAW.replace(b"5394", b"9999"))

    with pytest.raises(Rejection) as exc:
        verify_cached_bytes(rec, root)
    assert exc.value.code == "acquisition_raw_hash_mismatch"


# ------------------------------------------------------------------------ the manifest


def test_the_manifest_hash_moves_when_the_canonical_query_moves():
    """FAIL-CLOSED (query): two runs that asked the source different questions are not the
    same acquisition, even when the bytes happen to be identical."""
    a = AcquisitionManifest(
        schema_id=ACQUISITION_SCHEMA_ID,
        run_id="run_1",
        stage3_binding={"bundle_id": "s3_x", "document_sha256": "c" * 64},
        source_ledger_sha256="d" * 64,
        records=[_public_record()],
    )
    b = a.model_copy(update={
        "records": [_public_record(canonical_query="compound/cid/2244/property/InChIKey/JSON")]
    })
    assert manifest_content_sha256(a) != manifest_content_sha256(b)


def test_the_manifest_hash_moves_when_the_source_release_moves():
    """FAIL-CLOSED (release): a record read from ChEMBL_37 is not the same record read from
    ChEMBL_35."""
    a = AcquisitionManifest(
        schema_id=ACQUISITION_SCHEMA_ID, run_id="run_1",
        stage3_binding={"bundle_id": "s3_x", "document_sha256": "c" * 64},
        source_ledger_sha256="d" * 64, records=[_public_record()])
    b = a.model_copy(update={"records": [_public_record(release_or_last_updated="2026-06-01")]})
    assert manifest_content_sha256(a) != manifest_content_sha256(b)


def test_the_manifest_hash_moves_when_the_adapter_code_moves():
    a = AcquisitionManifest(
        schema_id=ACQUISITION_SCHEMA_ID, run_id="run_1",
        stage3_binding={"bundle_id": "s3_x", "document_sha256": "c" * 64},
        source_ledger_sha256="d" * 64, records=[_public_record()])
    b = a.model_copy(update={"records": [_public_record(adapter_code_sha256="e" * 64)]})
    assert manifest_content_sha256(a) != manifest_content_sha256(b)


def test_the_manifest_is_written_under_the_run_root_and_reloads_identically(tmp_path):
    root = RunRoot(str(tmp_path))
    m = AcquisitionManifest(
        schema_id=ACQUISITION_SCHEMA_ID, run_id="run_1",
        stage3_binding={"bundle_id": "s3_x", "document_sha256": "c" * 64},
        source_ledger_sha256="d" * 64, records=[_public_record()],
        missing=[{"lane": "potency_mec", "evidence_state": "not_evaluated",
                  "reason": "no ChEMBL activity record was acquired in this pass"}])
    path = root.write_manifest(m)
    assert os.path.dirname(path) == str(tmp_path)

    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    assert doc["content_sha256"] == manifest_content_sha256(m)
    assert doc["missing"][0]["evidence_state"] == "not_evaluated"


def test_missing_evidence_stays_explicit_it_is_never_an_empty_list_by_default():
    """`missingness_explicit` -> refuse_artifact. An absent lane is a stated absence."""
    m = AcquisitionManifest(
        schema_id=ACQUISITION_SCHEMA_ID, run_id="run_1",
        stage3_binding={"bundle_id": "s3_x", "document_sha256": "c" * 64},
        source_ledger_sha256="d" * 64, records=[_public_record()])
    doc = m.as_document()
    assert doc["missing"] == []
    assert "not_evaluated" in json.dumps(doc["hard_rules"])


# ------------------------------------------------- the bridge into the evidence contract


def test_an_acquisition_record_translates_into_the_stage4_source_contract():
    """W9 owns SourceRecord. Acquisition does not widen it — it fills it."""
    rec = _public_record()
    src = to_source_record(rec)
    assert src.acquisition_status.value == "acquired_public"
    assert src.access_date == "2026-07-13"
    assert src.raw_sha256 == rec.raw_sha256
    assert src.record_id == "5394"


def test_a_record_with_no_bytes_translates_to_not_acquired_never_to_a_hash():
    rec = AcquisitionRecord(
        acquisition_record_id="acq_missing_1",
        source_key="chembl",
        source_name="ChEMBL",
        source_type="public_database",
        origin="reused_from_stage3",
        stage3_source_record_id="abc",
        evidence_state="not_evaluated",
        extraction_transform="stage3_reuse.carry_verbatim:v1",
        adapter_code_sha256="f" * 64,
        review_status="not_applicable",
        license_or_terms_url="https://www.ebi.ac.uk/about/terms-of-use",
    )
    src = to_source_record(rec)
    assert src.acquisition_status.value == "not_acquired"
    assert src.raw_sha256 is None and src.raw_bytes is None
