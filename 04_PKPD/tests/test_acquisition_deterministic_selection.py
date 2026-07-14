"""No arbitrary first record. No arbitrary first product. Ever.

The independent cross-check flagged `results[0]`, `products[0]` and `limit=1` in
openfda_approval.py. It was right, and the LIVE data proves it was not theoretical:

    TEMODAR's openFDA label carries TWO application numbers — NDA021029 (capsule) and
    NDA022277 (injection) — and its Drugs@FDA record carries SIX products.

`_first(...)` picked one application number by position, and the approval cross-check then ran
against an arbitrarily chosen approval. Oral and IV are not the same exposure. `limit=1` made it
worse: it truncated the result set, so multiplicity could not even be DETECTED.

Every selection in this layer is now one of exactly three things:

  * downstream of a UNIQUE identity pin, PROVEN by the source's own `meta.results.total`;
  * a collect-all set, canonically ordered, with nothing dropped;
  * a typed refusal naming every candidate.

Ordering may never change an outcome, and a duplicate may never be silently deduplicated into a
selection.
"""

from __future__ import annotations

import json

import pytest

from analysis.acquire_http import Client, StaticTransport
from analysis.acquisition import RunRoot
from analysis.dailymed_select import parse_spl_listing, assert_listing_complete
from analysis.firewall import Rejection
from analysis.openfda_approval import (
    acquire_approval,
    cross_check_approval,
    parse_drugsfda,
    parse_openfda_label_identity,
)
from analysis.selection import exactly_one, sorted_unique

SETID = "ffffffff-0000-4000-8000-fixtureacq01"
OTHER = "ffffffff-0000-4000-8000-fixtureacq02"
OPENFDA = "https://api.fda.gov"
CLOCK = "2026-07-13T05:00:00Z"


def _label(results, total=None):
    return json.dumps({
        "meta": {"last_updated": "2026-06-30",
                 "results": {"skip": 0, "limit": 25,
                             "total": len(results) if total is None else total}},
        "results": results,
    }).encode()


def _label_row(setid=SETID, apps=("NDA999901",), uniis=("FIXTURE001",), version="40"):
    return {
        "set_id": setid, "version": version, "effective_time": "20260220",
        "openfda": {"application_number": list(apps), "unii": list(uniis),
                    "spl_set_id": [setid], "generic_name": ["FIXTUROMIDE"]},
    }


def _drugsfda(results, total=None):
    return json.dumps({
        "meta": {"last_updated": "2026-06-30",
                 "results": {"skip": 0, "limit": 25,
                             "total": len(results) if total is None else total}},
        "results": results,
    }).encode()


def _fda_row(app="NDA999901", products=(("001", "Prescription"),), unii="FIXTURE001"):
    return {
        "application_number": app,
        "sponsor_name": "SPOT FIXTURE LABORATORIES",
        "openfda": {"unii": [unii], "generic_name": ["FIXTUROMIDE"]},
        "products": [{"product_number": n, "marketing_status": s,
                      "dosage_form": "CAPSULE", "active_ingredients": []}
                     for n, s in products],
    }


# ------------------------------------------------------- the generic uniqueness primitive


def test_exactly_one_matches_by_identity_not_by_position():
    rows = [{"id": "b"}, {"id": "a"}, {"id": "c"}]
    assert exactly_one(rows, matches=lambda r: r["id"] == "a", what="row", pin="a",
                       zero_code="none", many_code="many") == {"id": "a"}


def test_exactly_one_refuses_zero_matches_with_a_typed_code():
    with pytest.raises(Rejection) as exc:
        exactly_one([{"id": "b"}], matches=lambda r: r["id"] == "a", what="row", pin="a",
                    zero_code="row_not_found", many_code="row_ambiguous")
    assert exc.value.code == "row_not_found"


def test_exactly_one_refuses_duplicates_it_never_deduplicates_into_a_choice():
    """Two records claiming the same identity are two records. Collapsing them to one is a
    decision, and this layer does not get to make it silently."""
    rows = [{"id": "a", "v": 1}, {"id": "a", "v": 2}]
    with pytest.raises(Rejection) as exc:
        exactly_one(rows, matches=lambda r: r["id"] == "a", what="row", pin="a",
                    zero_code="row_not_found", many_code="row_ambiguous")
    assert exc.value.code == "row_ambiguous"
    assert "2" in exc.value.detail


def test_sorted_unique_is_order_independent_and_drops_nothing():
    assert sorted_unique(["b", "a", "b"]) == ("a", "b")
    assert sorted_unique(["a", "b"]) == sorted_unique(["b", "a"])


# ------------------------------------------------------------------ the openFDA label record


def test_the_label_is_matched_on_its_set_id_not_on_being_first():
    """A response that also carries another product's label must still select by identity."""
    forward = parse_openfda_label_identity(
        _label([_label_row(OTHER, apps=("NDA000000",)), _label_row(SETID)], total=2), SETID)
    reversed_ = parse_openfda_label_identity(
        _label([_label_row(SETID), _label_row(OTHER, apps=("NDA000000",))], total=2), SETID)

    assert forward.set_id == SETID == reversed_.set_id
    assert forward.application_numbers == reversed_.application_numbers == ("NDA999901",)


def test_two_label_records_for_one_set_id_is_a_refusal_not_a_first_hit():
    with pytest.raises(Rejection) as exc:
        parse_openfda_label_identity(_label([_label_row(), _label_row(version="41")]), SETID)
    assert exc.value.code == "openfda_label_ambiguous"


def test_a_truncated_result_set_is_refused_because_multiplicity_cannot_be_seen():
    """`limit=1` hid this: the source said `total: 7` and we looked at one row. A result set we
    cannot see all of cannot prove uniqueness."""
    with pytest.raises(Rejection) as exc:
        parse_openfda_label_identity(_label([_label_row()], total=7), SETID)
    assert exc.value.code == "openfda_result_set_truncated"
    assert "7" in exc.value.detail


def test_a_label_that_is_not_the_set_id_we_asked_for_is_refused():
    with pytest.raises(Rejection) as exc:
        parse_openfda_label_identity(_label([_label_row(OTHER)]), SETID)
    assert exc.value.code == "openfda_label_not_found"


def test_every_application_number_on_the_label_survives_in_canonical_order():
    """THE TEMODAR CASE. Its label declares NDA021029 (capsule) AND NDA022277 (injection).
    Picking one by position bound the approval cross-check to an arbitrary route."""
    forward = parse_openfda_label_identity(
        _label([_label_row(apps=("NDA021029", "NDA022277"))]), SETID)
    reversed_ = parse_openfda_label_identity(
        _label([_label_row(apps=("NDA022277", "NDA021029"))]), SETID)

    assert forward.application_numbers == ("NDA021029", "NDA022277")
    assert forward.application_numbers == reversed_.application_numbers   # order-independent


def test_a_label_with_two_active_moiety_uniis_is_refused_not_reduced():
    with pytest.raises(Rejection) as exc:
        parse_openfda_label_identity(
            _label([_label_row(uniis=("FIXTURE001", "FIXTURE999"))]), SETID)
    assert exc.value.code == "openfda_unii_ambiguous"


# --------------------------------------------------------------------- the Drugs@FDA record


def test_drugsfda_is_matched_on_the_application_number_not_on_being_first():
    payload = _drugsfda([_fda_row("NDA000000"), _fda_row("NDA999901")], total=2)
    approval = parse_drugsfda(payload, "NDA999901")
    assert approval.application_number == "NDA999901"

    reversed_ = parse_drugsfda(
        _drugsfda([_fda_row("NDA999901"), _fda_row("NDA000000")], total=2), "NDA999901")
    assert reversed_ == approval


def test_duplicate_drugsfda_records_for_one_application_are_refused():
    with pytest.raises(Rejection) as exc:
        parse_drugsfda(_drugsfda([_fda_row(), _fda_row()]), "NDA999901")
    assert exc.value.code == "drugsfda_application_ambiguous"


def test_every_product_marketing_status_survives_and_none_is_chosen_by_position():
    """SIX products in the live TEMODAR record. `products[0].marketing_status` was a coin toss."""
    payload = _drugsfda([_fda_row(products=(("002", "Prescription"), ("001", "Discontinued"),
                                            ("003", "Prescription")))])
    approval = parse_drugsfda(payload, "NDA999901")

    assert approval.marketing_statuses == ("Discontinued", "Prescription")   # sorted, deduped
    assert approval.n_products == 3

    reordered = parse_drugsfda(
        _drugsfda([_fda_row(products=(("003", "Prescription"), ("001", "Discontinued"),
                                      ("002", "Prescription")))]), "NDA999901")
    assert reordered.marketing_statuses == approval.marketing_statuses


def test_a_drugsfda_record_that_answers_with_another_application_is_refused():
    with pytest.raises(Rejection) as exc:
        parse_drugsfda(_drugsfda([_fda_row("NDA111111")]), "NDA999901")
    assert exc.value.code == "drugsfda_application_not_found"


# ----------------------------------------------------------------- the cross-check, on SETS


def test_the_cross_check_requires_drugsfda_to_answer_for_every_application_the_label_declared():
    cross_check_approval(label_application_numbers=("NDA021029", "NDA022277"),
                         drugsfda_application_numbers=("NDA022277", "NDA021029"))  # order-free

    with pytest.raises(Rejection) as exc:
        cross_check_approval(label_application_numbers=("NDA021029", "NDA022277"),
                             drugsfda_application_numbers=("NDA021029",))
    assert exc.value.code == "approval_conflict"
    assert "NDA022277" in exc.value.detail


# ------------------------------------------------------- end to end: the TEMODAR-shaped label


def test_a_label_with_two_applications_acquires_both_approvals_and_picks_neither(tmp_path):
    run_root = RunRoot(str(tmp_path / "run"))
    routes = {
        f"{OPENFDA}/drug/label.json?limit=25&search=openfda.spl_set_id%3A%22{SETID}%22":
            (200, {"content-type": "application/json"},
             _label([_label_row(apps=("NDA021029", "NDA022277"))])),
        f"{OPENFDA}/drug/drugsfda.json?limit=25&search=openfda.application_number%3A%22NDA021029%22":
            (200, {"content-type": "application/json"},
             _drugsfda([_fda_row("NDA021029", products=(("001", "Discontinued"),))])),
        f"{OPENFDA}/drug/drugsfda.json?limit=25&search=openfda.application_number%3A%22NDA022277%22":
            (200, {"content-type": "application/json"},
             _drugsfda([_fda_row("NDA022277", products=(("001", "Prescription"),))])),
    }
    client = Client(transport=StaticTransport(routes, clock=CLOCK), allow_network=True)

    approval, records = acquire_approval(client, run_root, SETID)

    assert approval.application_numbers == ("NDA021029", "NDA022277")
    assert [a.application_number for a in approval.approvals] == ["NDA021029", "NDA022277"]
    assert approval.marketing_statuses == ("Discontinued", "Prescription")
    # one label response + one Drugs@FDA response PER application. Nothing was skipped.
    assert len(records) == 3


# ------------------------------------------------- DailyMed: mismatch, duplicate, no version


DAILYMED = "https://dailymed.nlm.nih.gov/dailymed/services/v2"


def _spl_routes(spl: bytes, listing: bytes | None = None):
    listing = listing or json.dumps({
        "metadata": {"total_elements": 1, "current_page": 1, "total_pages": 1},
        "data": [{"setid": SETID, "spl_version": 40, "title": "FIXTUROMIDE CAPSULE"}],
    }).encode()
    return {
        f"{DAILYMED}/spls.json?drug_name=fixturomide&pagesize=100":
            (200, {"content-type": "application/json"}, listing),
        f"{DAILYMED}/spls/{SETID}.xml": (200, {"content-type": "application/xml"}, spl),
    }


def _live_spl() -> bytes:
    import os
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "fixtures", "acquisition", "dailymed_spl.xml")
    with open(path, "rb") as fh:
        return fh.read()


def test_a_document_served_under_another_set_id_is_refused(tmp_path):
    """MISMATCH: the bytes must BE the record that was asked for."""
    from analysis.dailymed_select import acquire_label

    spl = _live_spl().replace(
        b'<setId root="ffffffff-0000-4000-8000-fixtureacq01"/>',
        b'<setId root="ffffffff-0000-4000-8000-fixtureacq02"/>')
    client = Client(transport=StaticTransport(_spl_routes(spl), clock=CLOCK), allow_network=True)

    with pytest.raises(Rejection) as exc:
        acquire_label(client, RunRoot(str(tmp_path / "r")), "fixturomide")
    assert exc.value.code == "dailymed_setid_conflict"


def test_a_label_with_no_version_is_unavailable_never_an_unversioned_identity(tmp_path):
    """MISSING VERSION: there is no `.vunversioned` label. A document that will not say which
    revision it is cannot be re-checked, and a placeholder version is a fabricated identity."""
    from analysis.dailymed_select import acquire_label

    spl = _live_spl().replace(b'<versionNumber value="40"/>', b"")
    client = Client(transport=StaticTransport(_spl_routes(spl), clock=CLOCK), allow_network=True)

    with pytest.raises(Rejection) as exc:
        acquire_label(client, RunRoot(str(tmp_path / "r")), "fixturomide")
    assert exc.value.code == "dailymed_version_unavailable"


def test_a_listing_entry_with_no_version_is_unavailable_too(tmp_path):
    from analysis.dailymed_select import acquire_label

    listing = json.dumps({
        "metadata": {"total_elements": 1, "current_page": 1, "total_pages": 1},
        "data": [{"setid": SETID, "title": "FIXTUROMIDE CAPSULE"}],      # no spl_version
    }).encode()
    client = Client(transport=StaticTransport(_spl_routes(_live_spl(), listing), clock=CLOCK),
                    allow_network=True)

    with pytest.raises(Rejection) as exc:
        acquire_label(client, RunRoot(str(tmp_path / "r")), "fixturomide")
    assert exc.value.code == "dailymed_version_unavailable"


def test_a_listing_that_carries_the_same_set_id_twice_is_refused_not_deduplicated():
    """DUPLICATE: two entries claiming one set ID are two records, even under an explicit pin."""
    from analysis.dailymed_select import select_spl

    raw = json.dumps({
        "metadata": {"total_elements": 2, "current_page": 1, "total_pages": 1},
        "data": [{"setid": SETID, "spl_version": 40, "title": "A"},
                 {"setid": SETID, "spl_version": 41, "title": "B"}],
    }).encode()
    with pytest.raises(Rejection) as exc:
        select_spl(parse_spl_listing(raw), setid=SETID)
    assert exc.value.code == "dailymed_product_selection_ambiguous"


def test_a_pinned_set_id_that_is_not_in_the_listing_is_refused():
    from analysis.dailymed_select import select_spl

    raw = json.dumps({
        "metadata": {"total_elements": 1, "current_page": 1, "total_pages": 1},
        "data": [{"setid": OTHER, "spl_version": 3, "title": "SOMETHING ELSE"}],
    }).encode()
    with pytest.raises(Rejection) as exc:
        select_spl(parse_spl_listing(raw), setid=SETID)
    assert exc.value.code == "dailymed_setid_not_in_listing"


# ------------------------------------------------------------------ DailyMed: same disease


def test_a_truncated_dailymed_listing_is_refused_rather_than_selected_from():
    """A page-1 listing that claims 40 total elements is not the candidate set. Selecting the
    'only' product on page 1 would be a first-hit with extra steps."""
    raw = json.dumps({
        "metadata": {"total_elements": 40, "current_page": 1, "total_pages": 2},
        "data": [{"setid": SETID, "spl_version": 40, "title": "ONE OF FORTY"}],
    }).encode()
    listings = parse_spl_listing(raw)
    with pytest.raises(Rejection) as exc:
        assert_listing_complete(raw, listings)
    assert exc.value.code == "dailymed_listing_incomplete"
    assert "40" in exc.value.detail
