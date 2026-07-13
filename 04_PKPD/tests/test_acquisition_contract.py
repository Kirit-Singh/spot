"""The source acquisition record: what a fetch must be able to show before its bytes count.

Every rule here is a rule the audit named. A record that cannot show WHEN it was fetched (to
the second, in UTC), WHAT exact query produced it, WHICH terms it came under, and WHICH adapter
build read it is not a reproducible acquisition — it is a claim about one.

The mutation tests are the point: each takes a VALID record and breaks exactly one binding.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from analysis.acquisition import (
    EvidenceObservationState,
    ReviewStatus,
    SourceAcquisitionManifest,
    SourceAcquisitionRecord,
)

SHA_A = "a" * 64
SHA_B = "b" * 64
SHA_C = "c" * 64


def _record(**over) -> SourceAcquisitionRecord:
    base = dict(
        acquisition_id="acq.chembl.CHEMBL1201585",
        source_record_id="src.chembl.CHEMBL1201585",
        request_url="https://www.ebi.ac.uk/chembl/api/data/molecule/CHEMBL1201585.json",
        canonical_query="GET /chembl/api/data/molecule/CHEMBL1201585.json?format=json",
        accessed_at_utc="2026-07-13T04:55:45Z",
        http_status=200,
        raw_media_type="application/json",
        response_headers={"content-type": "application/json", "etag": "W/\"1a2b\""},
        release_or_last_updated="ChEMBL_37",
        license_or_terms_url="https://creativecommons.org/licenses/by-sa/3.0/",
        raw_bytes=4821,
        raw_sha256=SHA_A,
        content_sha256=SHA_A,
        extraction_transform="$.molecule_properties.full_mwt",
        adapter_id="chembl_molecule_adapter",
        adapter_code_sha256=SHA_B,
        review_status=ReviewStatus.HUMAN_REVIEWED,
        observation_state=EvidenceObservationState.OBSERVED,
    )
    base.update(over)
    return SourceAcquisitionRecord(**base)


# ------------------------------------------------------------------ the happy path

def test_a_complete_acquisition_record_validates():
    rec = _record()
    assert rec.observation_state is EvidenceObservationState.OBSERVED
    assert rec.has_bytes is True


def test_the_five_evidence_states_are_exactly_the_audited_vocabulary():
    assert {s.value for s in EvidenceObservationState} == {
        "observed",
        "not_evaluated",
        "not_found_after_reproducible_search",
        "conflicting",
        "not_applicable",
    }


# --------------------------------------------------- time is a timestamp, not a date

def test_a_bare_access_date_is_refused_it_is_not_an_accessed_at_utc():
    """The audit: the source contract recorded an access DATE. A release that changes
    hourly cannot be pinned to a day."""
    with pytest.raises(ValidationError):
        _record(accessed_at_utc="2026-07-13")


def test_a_local_timestamp_without_utc_is_refused():
    with pytest.raises(ValidationError):
        _record(accessed_at_utc="2026-07-13T04:55:45")


def test_a_non_utc_offset_is_refused():
    with pytest.raises(ValidationError):
        _record(accessed_at_utc="2026-07-13T04:55:45+02:00")


# --------------------------------------------------------- the query must be canonical

def test_an_acquisition_without_a_canonical_query_is_refused():
    with pytest.raises(ValidationError):
        _record(canonical_query="")


# ------------------------------------------------------------------- terms and licence

def test_a_licence_NAME_is_not_a_terms_URL():
    """`license: "Public domain"` is the overclaim the audit found in the ledger. The
    contract wants the exact terms document, not an adjective."""
    with pytest.raises(ValidationError):
        _record(license_or_terms_url="Public domain (NLM DailyMed)")


def test_the_terms_url_must_be_a_url():
    with pytest.raises(ValidationError):
        _record(license_or_terms_url="CC BY 4.0")


# ------------------------------------------------------------- headers carry no secrets

@pytest.mark.parametrize("header", ["authorization", "Authorization", "cookie",
                                    "set-cookie", "x-api-key", "proxy-authorization"])
def test_a_credential_header_is_refused_never_hashed_into_a_public_artifact(header):
    with pytest.raises(ValidationError):
        _record(response_headers={"content-type": "application/json", header: "secret"})


# ------------------------------------------------------- bytes must match the state

def test_observed_requires_bytes():
    """`observed` is a claim that something came back. Without bytes it is a memory."""
    with pytest.raises(ValidationError):
        _record(raw_sha256=None, raw_bytes=None, content_sha256=None)


def test_observed_requires_a_2xx_status():
    """A 404 body is not an observation of the thing you asked for."""
    with pytest.raises(ValidationError):
        _record(http_status=404)


def test_observed_requires_nonzero_bytes():
    with pytest.raises(ValidationError):
        _record(raw_bytes=0)


def test_not_evaluated_must_not_carry_bytes():
    """`not_evaluated` means nobody looked. A hash here would be a fiction."""
    with pytest.raises(ValidationError):
        _record(observation_state=EvidenceObservationState.NOT_EVALUATED)


def test_not_evaluated_with_no_bytes_is_legal():
    rec = _record(
        observation_state=EvidenceObservationState.NOT_EVALUATED,
        raw_sha256=None, raw_bytes=None, content_sha256=None,
        http_status=None, raw_media_type=None, response_headers={},
        review_status=ReviewStatus.NOT_REVIEWED,
    )
    assert rec.has_bytes is False


# ------------------------------------- a negative search is a claim about a real search

def test_not_found_after_reproducible_search_requires_the_search_manifest():
    """This is the whole difference between 'we looked and found nothing' and 'nobody
    looked'. Without the manifest the two are the same sentence."""
    with pytest.raises(ValidationError):
        _record(observation_state=EvidenceObservationState.NOT_FOUND_AFTER_SEARCH)


def test_not_found_after_reproducible_search_requires_the_empty_response_bytes():
    """The content-addressed part: the manifest must point at the bytes that came back
    empty, or the negative result is unfalsifiable."""
    with pytest.raises(ValidationError):
        _record(
            observation_state=EvidenceObservationState.NOT_FOUND_AFTER_SEARCH,
            search_id="search.pubmed.no_neb_pk",
            raw_sha256=None, raw_bytes=None, content_sha256=None,
        )


def test_a_manifested_empty_search_is_legal():
    rec = _record(
        observation_state=EvidenceObservationState.NOT_FOUND_AFTER_SEARCH,
        search_id="search.pubmed.no_neb_pk",
    )
    assert rec.search_id == "search.pubmed.no_neb_pk"


def test_a_search_id_on_an_observed_record_is_refused():
    """An observed row did not come from a negative search."""
    with pytest.raises(ValidationError):
        _record(search_id="search.pubmed.no_neb_pk")


# ------------------------------------------------------------------------ conflicting

def test_conflicting_requires_the_conflict_to_be_stated():
    with pytest.raises(ValidationError):
        _record(observation_state=EvidenceObservationState.CONFLICTING)


def test_conflicting_with_a_stated_conflict_is_legal():
    rec = _record(
        observation_state=EvidenceObservationState.CONFLICTING,
        conflict_note="PubChem CID 5288826 and ChEMBL CHEMBL1201585 give different InChIKeys.",
    )
    assert rec.conflict_note


def test_not_applicable_requires_a_reason():
    with pytest.raises(ValidationError):
        _record(observation_state=EvidenceObservationState.NOT_APPLICABLE,
                raw_sha256=None, raw_bytes=None, content_sha256=None,
                http_status=None, raw_media_type=None, response_headers={})


# ------------------------------------------------- the volatile-envelope content hash

def test_a_content_hash_that_differs_from_the_raw_hash_must_declare_its_rule():
    """The Grossman BioC envelope stamps the retrieval date into every response, so the raw
    bytes of an unchanged paper differ daily. A separate content hash is correct — but only
    if the normalisation that produced it is declared and reviewable."""
    with pytest.raises(ValidationError):
        _record(content_sha256=SHA_C)


def test_a_declared_normalisation_rule_makes_a_distinct_content_hash_legal():
    rec = _record(
        content_sha256=SHA_C,
        content_hash_rule="sha256 over the response with the BioC <date> element blanked.",
    )
    assert rec.content_sha256 == SHA_C
    assert rec.raw_sha256 == SHA_A


# ------------------------------------------------------------- the adapter is bound

def test_the_adapter_code_hash_is_required_the_transform_is_only_half_the_story():
    """The transform says WHAT was taken out; the adapter hash says WHICH build took it.
    A parser bugfix (like the nested-SPL repair) changes the extracted value without
    changing the transform string or the bytes."""
    with pytest.raises(ValidationError):
        _record(adapter_code_sha256=None)


def test_an_extraction_transform_is_required():
    with pytest.raises(ValidationError):
        _record(extraction_transform="")


# ---------------------------------------------------------------------- the manifest

def test_the_manifest_is_content_addressed_and_order_independent():
    a = _record()
    b = _record(acquisition_id="acq.uniprot.P42345", source_record_id="src.uniprot.P42345")
    one = SourceAcquisitionManifest(manifest_id="man.1", records=[a, b])
    two = SourceAcquisitionManifest(manifest_id="man.1", records=[b, a])
    assert one.manifest_content_sha256 == two.manifest_content_sha256


def test_changing_one_bound_field_moves_the_manifest_hash():
    before = SourceAcquisitionManifest(manifest_id="man.1", records=[_record()])
    after = SourceAcquisitionManifest(
        manifest_id="man.1",
        records=[_record(canonical_query="GET /chembl/api/data/molecule/CHEMBL999.json")],
    )
    assert before.manifest_content_sha256 != after.manifest_content_sha256


def test_a_duplicate_acquisition_id_is_refused_nothing_downstream_could_pick():
    with pytest.raises(ValidationError):
        SourceAcquisitionManifest(manifest_id="man.1", records=[_record(), _record()])


def test_two_acquisitions_of_one_source_record_are_refused():
    """One source record is one response. Two acquisitions for it would let a reader pick."""
    with pytest.raises(ValidationError):
        SourceAcquisitionManifest(
            manifest_id="man.1",
            records=[_record(), _record(acquisition_id="acq.other")],
        )


# ------------------------------------------------- selection: no arbitrary first record
#
# The vocabulary is `analysis/selection.py`'s, not a second one invented beside it: a selection
# is `exactly_one` (matched on an identity PIN, zero and many both refusals) or `sorted_unique`
# (collect-all). What the RECORD adds is the proof: the source's own match total against what
# actually arrived. The live data settled this — TEMODAR's openFDA label declares TWO
# application numbers and its Drugs@FDA record carries SIX products, so `results[0]` was
# returning a wrong answer while `limit=1` made the multiplicity impossible to see.


def test_an_exactly_one_selection_must_name_the_identity_pin_it_matched_on():
    """Matching on position is not matching on identity."""
    with pytest.raises(ValidationError) as exc:
        _record(selection_disposition="exactly_one",
                match_total_reported=1, records_returned=1, result_set_complete=True)
    assert "PIN" in str(exc.value) or "pin" in str(exc.value)


def test_a_proven_unique_selection_is_legal():
    rec = _record(selection_disposition="exactly_one", selection_pin="setid=046a9011",
                  match_total_reported=1, records_returned=1, result_set_complete=True)
    assert rec.result_set_complete is True


def test_a_truncated_result_set_cannot_be_observed_this_is_the_limit_1_bug():
    """The source says seven records match; one arrived. Nothing about that one row can be
    called unique — and `limit=1` did not merely risk the wrong record, it removed the evidence
    that would have shown the risk."""
    with pytest.raises(ValidationError) as exc:
        _record(selection_disposition="exactly_one", selection_pin="setid=046a9011",
                match_total_reported=7, records_returned=1, result_set_complete=False)
    assert "truncated" in str(exc.value).lower() or "complete" in str(exc.value).lower()


def test_completeness_cannot_simply_be_asserted_it_must_agree_with_the_source_total():
    """`result_set_complete` is the source's own total agreeing with what we can see. It is not
    a flag an adapter gets to set because it feels confident."""
    with pytest.raises(ValidationError):
        _record(selection_disposition="exactly_one", selection_pin="setid=X",
                match_total_reported=7, records_returned=1, result_set_complete=True)


def test_a_total_the_source_never_reported_cannot_prove_uniqueness():
    """Uniqueness that cannot be proven is not assumed. Without a total, the rows that arrived
    cannot be shown to be all of them."""
    with pytest.raises(ValidationError):
        _record(selection_disposition="exactly_one", selection_pin="setid=X",
                match_total_reported=None, records_returned=1, result_set_complete=False)


def test_a_collect_all_selection_needs_no_pin_because_it_chooses_nothing():
    """`sorted_unique` drops nothing and picks nothing — every application, every marketing
    status — so there is no choice to justify."""
    rec = _record(selection_disposition="sorted_unique",
                  match_total_reported=6, records_returned=6, result_set_complete=True)
    assert rec.selection_pin is None


def test_an_unseparable_match_is_conflicting_not_a_silent_arg_max():
    rec = _record(
        observation_state=EvidenceObservationState.CONFLICTING,
        selection_disposition="sorted_unique",
        match_total_reported=2, records_returned=2, result_set_complete=True,
        conflict_note=("TEMODAR declares NDA021029 (capsule, Discontinued) and NDA022277 "
                       "(injection, Prescription). The two applications disagree."),
    )
    assert rec.observation_state is EvidenceObservationState.CONFLICTING
