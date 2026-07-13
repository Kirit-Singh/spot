"""What the v2 contract does with W8's acquisition records.

The RECORD is W8's (`analysis/acquisition.py`), adopted verbatim, and its own rules are W8's
tests. This lane built a rival `SourceAcquisitionRecord` before noticing that — the exact
duplication it had been told not to create — and deleted it. Two declarations of the same
evidence would have drifted, and the drift would have been invisible.

So what is tested here is CONSUMPTION: that the v2 profile actually requires an acquisition
behind every consumed byte, that it refuses one whose bytes disagree with the source registry,
and that a synthetic fixture can never launder itself into a public record.
"""

from __future__ import annotations

import pytest

from analysis.acquisition import AcquisitionRecord, fixture_record
from analysis.canonical import sha256_bytes
from analysis.contract_profile import contract_violations, is_acquisition_complete

import fixtures as fx


def _v2():
    return fx.stage4_inputs_v2()


# ------------------------------------------------- the record is W8's, not a look-alike

def test_the_acquisition_record_is_w8s_and_this_lane_declares_no_rival():
    """A second declaration of the same evidence is the duplication that was forbidden. If a
    `SourceAcquisitionRecord` ever reappears here, this fails."""
    import analysis.acquisition as acq

    assert acq.AcquisitionRecord is AcquisitionRecord
    assert not hasattr(acq, "SourceAcquisitionRecord")


def test_the_five_evidence_states_are_the_audited_vocabulary():
    states = set(AcquisitionRecord.model_fields["evidence_state"].annotation.__args__)
    assert states == {
        "observed", "not_evaluated", "not_found_after_reproducible_search",
        "conflicting", "not_applicable",
    }


# --------------------------------------------- every consumed byte has an acquisition

def test_the_v2_fixture_is_acquisition_complete():
    assert is_acquisition_complete(_v2()) is True


def test_a_source_that_supplies_bytes_but_was_never_acquired_is_refused():
    """The audit's BLOCKER, as a contract rule: a byte with no canonical query, access time,
    terms URL and adapter build is a byte nobody can get again."""
    inputs = _v2()
    inputs.acquisitions = [a for a in inputs.acquisitions
                           if a.source_key != "src.fixture.potency"]
    codes = {v.code for v in contract_violations(inputs)}
    assert "source_not_acquired" in codes


def test_two_acquisitions_of_one_source_are_refused():
    """One source record is one response. Two would let a reader choose which bytes the
    evidence rests on."""
    inputs = _v2()
    inputs.acquisitions = list(inputs.acquisitions) + [
        inputs.acquisitions[0].model_copy(update={"acquisition_record_id": "ACQ-DUP"})]
    codes = {v.code for v in contract_violations(inputs)}
    assert "duplicate_acquisition_for_source" in codes


def test_an_acquisition_naming_an_unregistered_source_is_refused():
    inputs = _v2()
    inputs.acquisitions[0] = inputs.acquisitions[0].model_copy(
        update={"source_key": "src.DOES_NOT_EXIST"})
    codes = {v.code for v in contract_violations(inputs)}
    assert "acquisition_of_unknown_source" in codes


def test_an_acquisition_whose_bytes_disagree_with_the_registry_is_refused():
    """The binding that makes the manifest worth having. If the acquisition says it fetched one
    set of bytes and the registry pins another, the evidence rests on exactly one of them — and
    nothing in the artifact would otherwise say which."""
    inputs = _v2()
    inputs.acquisitions[0] = inputs.acquisitions[0].model_copy(
        update={"raw_sha256": "f" * 64})
    codes = {v.code for v in contract_violations(inputs)}
    assert "acquisition_hash_mismatch" in codes


# ------------------------------------------------- a fixture cannot launder itself public

def test_a_synthetic_fixture_is_never_an_observation():
    """W8's rule, and this fixture set obeys it: labelled synthetic bytes are not evidence
    about any drug, so their evidence_state may not be `observed`."""
    for a in _v2().acquisitions:
        assert a.origin == "synthetic_fixture"
        assert a.evidence_state != "observed"


def test_a_fixture_record_cannot_claim_a_public_origin():
    with pytest.raises(Exception):
        AcquisitionRecord(
            acquisition_record_id="ACQ-X", source_key="src.x", source_name="x",
            source_type="fixture", origin="fetched_public",
            extraction_transform="t", adapter_code_sha256="a" * 64,
            review_status="unreviewed", evidence_state="observed")


def test_the_fixture_record_helper_hashes_the_exact_bytes_the_parser_was_handed():
    raw = b"<xml>fixture</xml>"
    r = fixture_record(acquisition_record_id="ACQ-1", source_key="src.x", raw=raw,
                       extraction_transform="t", adapter_code_sha256="a" * 64)
    assert r.raw_sha256 == sha256_bytes(raw)
    assert r.raw_bytes == len(raw)
    assert r.origin == "synthetic_fixture"


# ----------------------------------------------------- a negative search names its search

def test_a_negative_search_acquisition_needs_the_search_it_rests_on():
    inputs = _v2()
    inputs.acquisitions[0] = inputs.acquisitions[0].model_copy(
        update={"evidence_state": "not_found_after_reproducible_search"})
    inputs.search_manifests = []
    codes = {v.code for v in contract_violations(inputs)}
    assert "negative_search_manifest_missing" in codes
