"""The selection proof is READ from the source. It is never inferred, and never defaulted.

W9's closeout audit, and it is a release blocker. `materialize._selection` decided a fetch was "by
identity" if `stable_record_id` happened to appear as a SUBSTRING of `canonical_query`, and then
FABRICATED the proof:

    match_total_reported = 1     records_returned = 1     result_set_complete = True

For an **openFDA search** that is simply false. openFDA reports `meta.results.total` — it may say
forty matches and hand back one — and the emitted record would have sworn the result set was
complete. A fabricated completeness claim is worse than an absent one: it is the exact truncation
these fields exist to expose, **wearing the proof's clothes**.

Three more, all the same disease:

  * `AcquisitionRecord` DISCARDED the source's real total. The adapters read it (openFDA's
    `meta.results.total`, DailyMed's `total_elements`), fed it to `assert_result_set_complete`, and
    then threw it away — so the one number that could refute the fabrication was gone by the time
    anything could check.
  * `selection_disposition = None` bypassed every selection rule. The row asserted nothing, so
    nothing could refuse it, and a record chosen by POSITION was indistinguishable from one pinned
    by NAME. Silence is not a disposition.
  * Stage-3 reuse wrote a SOURCE KEY into `canonical_query` and dropped the query hash and the
    Stage-3 source record id. Nobody can re-issue the string "chembl"; a provenance field that
    cannot be re-issued is decoration.
"""

from __future__ import annotations

import pytest

from analysis.acquisition import AcquisitionRecord
from analysis.materialize import MaterializationError, _selection
from analysis.stage3_reuse import reuse_stage3_source


def _rec(**over):
    base = dict(
        acquisition_record_id="acq.openfda.search", source_key="openfda",
        source_name="openFDA drug/label", source_type="public_api", origin="fetched_public",
        stable_record_id="setid-1",
        # THE trap: the pin appears as a substring of the query. The old code read that as proof.
        canonical_query="GET /drug/label.json?search=openfda.spl_set_id:setid-1&limit=1",
        url="https://api.fda.gov/drug/label.json",
        accessed_at_utc="2026-07-13T00:00:00Z", access_date="2026-07-13",
        http_status=200, raw_sha256="a" * 64, raw_bytes=10, cache_relpath="raw/x.json",
        extraction_transform="parse", adapter_code_sha256="b" * 64,
        review_status="unreviewed", evidence_state="observed",
        # A fetched_public record must show its terms and its media type: a fetch that cannot show
        # its locator, its terms and its bytes is not a public source record, it is a claim.
        license_or_terms_url="https://open.fda.gov/terms/", raw_media_type="application/json",
    )
    base.update(over)
    return AcquisitionRecord(**base)


# ------------------------------------------------------- the fabrication, killed at the source

def test_a_SEARCH_never_fabricates_a_complete_RESULT_SET():
    """THE blocker. openFDA reported 40 matches and handed back 1. The old code saw the setid inside
    the query, called it an identity fetch, and swore the result set was complete."""
    rec = _rec(selection_disposition="exactly_one", selection_pin="setid-1",
               match_total_reported=40, records_returned=1, result_set_complete=False)

    proof = _selection(rec)
    assert proof["match_total_reported"] == 40, "the source's OWN total must survive"
    assert proof["records_returned"] == 1
    assert proof["result_set_complete"] is False, (
        "40 matched and 1 arrived — the other 39 were never shown, and the record must not claim "
        "otherwise")


def test_an_UNREPORTED_total_stays_None_and_is_NEVER_defaulted_to_1():
    """`None` means the source reported no total. `1` is a claim, and it is not ours to make."""
    rec = _rec(selection_disposition="sorted_unique", match_total_reported=None,
               records_returned=3, result_set_complete=False)

    proof = _selection(rec)
    assert proof["match_total_reported"] is None
    assert proof["result_set_complete"] is False


def test_the_proof_is_NOT_inferred_from_the_pin_appearing_in_the_query():
    """A substring test is not a proof. A query that CONTAINS an id is not a query FOR that id, and
    the old code could not tell the difference."""
    rec = _rec()                                  # pin IS in the query, and NO proof is stated
    assert rec.stable_record_id in rec.canonical_query

    proof = _selection(rec)
    assert proof["selection_disposition"] is None, "the disposition was inferred from a substring"
    assert proof["match_total_reported"] is None, "a match total was invented"
    assert proof["result_set_complete"] is None, (
        "completeness was invented. NOTE this assertion previously read `is False` — written while "
        "`_selection` still did `bool(rec.result_set_complete)`. That is the SAME defect one layer "
        "down: `None` means the source stated nothing, `False` means it stated the result set was "
        "TRUNCATED. Coercing the first into the second manufactures a claim the source never made.")


# ------------------------------------------- an OBSERVED row must be able to say how it selected

def test_an_OBSERVED_row_with_NO_disposition_is_REFUSED():
    """`selection_disposition = None` bypassed every selection rule: the row asserted nothing, so
    nothing could refuse it. Silence is not a disposition."""
    from analysis.materialize import _assert_selection_proven

    with pytest.raises(MaterializationError) as exc:
        _assert_selection_proven(_rec(selection_disposition=None))

    assert exc.value.code == "acquisition_row_without_selection_proof"
    assert "chosen by position" in str(exc.value)


@pytest.mark.parametrize("disposition", ["exactly_one", "sorted_unique"])
def test_a_row_that_STATES_how_it_selected_is_admitted(disposition):
    from analysis.materialize import _assert_selection_proven

    _assert_selection_proven(_rec(selection_disposition=disposition))


def test_a_NOT_EVALUATED_row_is_not_asked_for_a_selection_proof():
    """Nobody looked, so nothing was selected. Demanding a selection proof from a lane nobody
    examined would be demanding evidence of an absence."""
    from analysis.materialize import _assert_selection_proven

    _assert_selection_proven(_rec(evidence_state="not_evaluated", selection_disposition=None,
                                  origin="reused_from_stage3", stage3_source_record_id="s3src-1",
                                  raw_sha256=None, raw_bytes=None, cache_relpath=None,
                                  http_status=None, accessed_at_utc=None))


# ---------------------------------- the exact canonical query, its hash, and the Stage-3 source id

def test_stage3_REUSE_preserves_the_query_HASH_and_the_source_record_id():
    """Stage 3 stores its canonical query as a HASH, not as text. Carried as a hash — and NOT
    dropped, which is what happened."""
    row = {
        "source_record_id": "s3src-1", "source": "chembl", "acquisition_status": "acquired_public",
        "adapter": "chembl_target", "adapter_version": "v3", "source_release": "ChEMBL_37",
        "retrieval_url": "https://www.ebi.ac.uk/chembl/api/data/target.json?limit=1000",
        "query_canonical": "c" * 64, "raw_sha256": "d" * 64, "raw_bytes": 10,
        "license": "CC BY-SA 3.0", "raw_media_type": "application/json",
    }
    rec = reuse_stage3_source(row)

    assert rec.canonical_query_sha256 == "c" * 64, "the query hash was dropped"
    assert rec.stage3_source_record_id == "s3src-1", "the Stage-3 source id was dropped"


def test_a_SOURCE_KEY_is_never_written_where_a_CANONICAL_QUERY_belongs(tmp_path):
    """`canonical_query = rec.canonical_query or rec.source_key` wrote the string "chembl" into a
    field whose whole purpose is to be re-issued. Nobody can re-issue "chembl"."""
    from analysis.materialize import _acquisition_row

    rec = _rec(canonical_query=None, canonical_query_sha256="e" * 64,
               stage3_source_record_id="s3src-9", origin="reused_from_stage3",
               http_status=None, accessed_at_utc=None,
               selection_disposition="sorted_unique")

    row = _acquisition_row(rec)
    assert row.canonical_query != "openfda", "a source key was written as the canonical query"
    assert "e" * 64 in row.canonical_query or row.canonical_query_sha256 == "e" * 64
    assert row.canonical_query_sha256 == "e" * 64
    assert row.stage3_source_record_id == "s3src-9"


# ------------------ a REUSED response: the proof is DELEGATED, and the delegation is NAMED

def test_a_REUSED_row_delegates_its_selection_proof_to_STAGE_3():
    """Stage 4 did not issue the query — Stage 3 did. The same shape as the access time.

    Fabricating a disposition here would be the original defect in a new costume. DEMANDING one
    would be demanding that Stage 4 attest to a selection it never made. So the proof is delegated,
    and delegation is only honest if the record can NAME what it delegates to.
    """
    from analysis.materialize import _assert_selection_proven

    _assert_selection_proven(_rec(
        origin="reused_from_stage3", selection_disposition=None,
        stage3_source_record_id="s3src-1",
        http_status=None, accessed_at_utc=None))


def test_an_UNNAMED_delegation_CANNOT_EVEN_BE_BUILT():
    """A reused row that names no upstream row is standing on a selection nobody can find — and the
    RECORD CONTRACT refuses it before the materializer ever sees it. Defence in depth: the
    materializer keeps its own check (`reused_row_cannot_name_its_upstream_selection`), but the
    stronger statement is that such a record cannot be constructed at all."""
    with pytest.raises(Exception) as exc:
        _rec(origin="reused_from_stage3", selection_disposition=None,
             stage3_source_record_id=None, http_status=None, accessed_at_utc=None)

    assert "must name the Stage-3 source_record_id" in str(exc.value)


def test_a_STAGE4_FETCHED_row_may_NOT_delegate_and_must_prove_it_itself():
    """The asymmetry is the point: Stage 4 issued this query, so Stage 4 must say how it selected.
    A fetched row cannot hide behind an upstream id."""
    from analysis.materialize import _assert_selection_proven

    with pytest.raises(MaterializationError) as exc:
        _assert_selection_proven(_rec(origin="fetched_public", selection_disposition=None,
                                      stage3_source_record_id="s3src-1"))

    assert exc.value.code == "acquisition_row_without_selection_proof"
    assert "FETCHED by Stage 4" in str(exc.value)


# ============ END TO END: the REAL adapters, offline, with the SOURCE's own totals ============
#
# The repair had to reach the FETCH-TO-RECORD SEAM, not just the record contract. An independent
# read caught that `record_from_response` accepted no proof at all — so every `fetched_public`
# record was still born with `selection_disposition=None`, and my own gate would have rejected every
# real observed row. The tests passed because they built `AcquisitionRecord` by hand. That is a
# test-only repair, and it is exactly the shape of the defect it was meant to fix.

# The EXACT per-endpoint semantics. Getting these wrong in either direction is a fabrication:
#
#   sorted_unique   a NAME-TO-LIST query. RxNorm `rxcui.json?name=` and PubChem
#                   `compound/name/{name}/cids` both return a LIST. Calling either an identity GET
#                   would claim an identity the request never asserted.
#   identity_get    DailyMed `/spls/{setid}.xml` and PubChem property-BY-CID. No result set — so no
#                   total, and NO completeness boolean. `result_set_complete=True` here would be a
#                   completeness claim invented for an endpoint that reports no total.
#   exactly_one     a real SEARCH matched on a pin (DailyMed listing, openFDA label, Drugs@FDA).
#                   Uniqueness must be DEMONSTRATED against the source's own count.
EXPECTED_DISPOSITIONS = {
    "sorted_unique": "a name-to-list query returns a LIST, not one named record",
    "identity_get": "no result set: no total, and no completeness boolean",
    "exactly_one": "a search: uniqueness demonstrated against the source's own total",
}


def _real_records(tmp_path):
    from analysis.acquire_http import Client, StaticTransport
    from analysis.acquisition import RunRoot
    from analysis.dailymed_select import acquire_label, acquire_rxcui
    from analysis.openfda_approval import acquire_approval
    from analysis.pubchem import acquire_pubchem_identity
    from test_acquisition_identity import CLOCK, NAME, _routes

    run_root = RunRoot(str(tmp_path / "rr"))
    client = Client(transport=StaticTransport(_routes(), clock=CLOCK), allow_network=True)

    records = []
    _pc, recs = acquire_pubchem_identity(client, run_root, NAME)
    records += recs
    _rx, rx_rec = acquire_rxcui(client, run_root, NAME)   # ONE record, not a list
    records.append(rx_rec)
    label, recs = acquire_label(client, run_root, NAME)
    records += recs
    _ap, recs = acquire_approval(client, run_root, label.listing.setid)
    records += recs
    return records


def test_the_REAL_adapters_emit_records_that_CARRY_the_proof(tmp_path):
    """Drive the ACTUAL adapters over the offline transport and read what they wrote.

    The tests used to build `AcquisitionRecord` by hand, so they never saw that
    `record_from_response` accepted no proof at all — every fetched record was born with
    `selection_disposition=None`, and the gate would have rejected every real observed row. A
    test-only repair is exactly the shape of the defect it is meant to fix.
    """
    observed = [r for r in _real_records(tmp_path) if r.evidence_state == "observed"]
    assert observed, "the adapters produced no observed record"

    for rec in observed:
        assert rec.selection_disposition in EXPECTED_DISPOSITIONS, (
            f"{rec.source_key}: disposition {rec.selection_disposition!r} — a fetched, observed "
            "record that states none would be refused by the gate, and before the gate existed the "
            "materializer FABRICATED one")
        assert rec.selection_pin, f"{rec.source_key}: no pin"


def test_an_IDENTITY_GET_reports_NO_total_and_NO_completeness_boolean(tmp_path):
    """No result set means completeness has nothing to be true OR false about. `True` here would be
    a completeness claim invented for an endpoint that reports no total."""
    gets = [r for r in _real_records(tmp_path) if r.selection_disposition == "identity_get"]
    assert gets, "no identity GET was exercised — DailyMed /spls/{setid}.xml is one"

    for rec in gets:
        assert rec.match_total_reported is None, f"{rec.source_key}: a total for no result set"
        assert rec.result_set_complete is None, (
            f"{rec.source_key}: result_set_complete={rec.result_set_complete!r}. An identity GET "
            "has no result set; `True` invents a completeness claim and `False` reads as "
            "'incomplete', which is a different claim again.")
        assert rec.records_returned == 1


def test_a_NAME_TO_LIST_query_is_SORTED_UNIQUE_and_counts_what_arrived(tmp_path):
    """RxNorm `rxcui.json?name=` and PubChem `compound/name/{name}/cids` return LISTS."""
    lists = [r for r in _real_records(tmp_path) if r.selection_disposition == "sorted_unique"]
    assert lists, "no name-to-list query was exercised"

    for rec in lists:
        assert rec.records_returned is not None and rec.records_returned >= 1, (
            f"{rec.source_key}: a collect-all must count what it collected")


def test_a_SEARCH_demonstrates_uniqueness_against_the_SOURCE_own_total(tmp_path):
    """`exactly_one` is a claim about a RESULT SET, and it must be demonstrated — not assumed from
    the endpoint. openFDA may report forty matches and hand back one."""
    searches = [r for r in _real_records(tmp_path) if r.selection_disposition == "exactly_one"]
    assert searches, "no search was exercised"

    for rec in searches:
        assert rec.match_total_reported is not None, (
            f"{rec.source_key}: claims `exactly_one` and reports NO source total — uniqueness "
            "asserted, not demonstrated")
        assert rec.result_set_complete is not None


def test_those_REAL_records_MATERIALIZE_with_the_NULL_PRESERVED(tmp_path):
    """The seam, end to end: adapter -> AcquisitionRecord -> SourceAcquisitionRecord.

    `materialize._selection` used to do `bool(rec.result_set_complete)`, which rewrites an honest
    null into `False` — and `False` reads as "we looked and the result set was INCOMPLETE", which is
    a claim the endpoint never made. Absent must stay absent, end to end.
    """
    from analysis.materialize import _acquisition_row

    observed = [r for r in _real_records(tmp_path) if r.evidence_state == "observed"]
    for rec in observed:
        row = _acquisition_row(rec)

        assert row.selection_disposition == rec.selection_disposition
        assert row.match_total_reported == rec.match_total_reported, (
            "the source's own total was altered between the record and the bundle")
        assert row.records_returned == rec.records_returned
        assert row.result_set_complete == rec.result_set_complete, (
            "an honest null was coerced on the way into the bundle")

        if rec.selection_disposition == "identity_get":
            assert row.result_set_complete is None, "the null did not survive materialization"
