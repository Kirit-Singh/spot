"""RxNorm identity crosswalk, and DETERMINISTIC DailyMed product/version selection.

The audit's §4.5 finding: the SPL parser could read a label but could not FIND one — it did not
discover products, choose among them, or check that the document it got back is the version it
asked for. "Take the first hit" is not a selection rule; it is a coin toss that a reviewer
cannot reproduce.

So:

  * discovery is a canonical query (`spls.json?drug_name=…`), recorded like any other request;
  * selection is deterministic: EXACTLY ONE product, or the caller pins the set ID explicitly.
    Two products for one name is `dailymed_product_selection_ambiguous` — a refusal that names
    every candidate, so the pin is a decision someone makes on the record;
  * the fetched document must BE the version the listing offered. If the listing says version 40
    and the SPL says 41, they are not the same label and Stage 4 does not quietly prefer one.

DailyMed has NO verified blanket licence, and its own warning is that in-use labelling may
differ from current FDA-approved labelling. Both facts travel on the record; the approval
cross-check lives in `openfda_approval.py`, and full label bytes never enter Git.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from .acquire_http import Client
from .acquisition import AcquisitionRecord, RunRoot, record_from_response
from .firewall import Rejection
from .label_adapters import LabelParseError, ParsedLabel, parse_dailymed_spl

DAILYMED = "dailymed"
RXNORM = "rxnorm"

# DailyMed paginates. Ask for the whole candidate set in one page, and refuse to select from a
# partial one (`assert_listing_complete`) rather than reading whichever products arrived.
PAGE_SIZE = "100"


@dataclass(frozen=True)
class SplListing:
    """One product in the DailyMed discovery response."""

    setid: str
    spl_version: str
    title: str
    published_date: Optional[str]


@dataclass(frozen=True)
class SelectedLabel:
    listing: SplListing
    label: ParsedLabel


# ------------------------------------------------------------------------------- RxNorm


def parse_rxcuis(raw: bytes) -> list[str]:
    payload = _json(raw, "rxcui.json")
    ids = (payload.get("idGroup") or {}).get("rxnormId") or []
    return [str(i) for i in ids]


def acquire_rxcui(client: Client, run_root: RunRoot,
                  name: str) -> tuple[str, AcquisitionRecord]:
    """name -> exactly one RxCUI, or a refusal. RxNorm establishes identity, nothing else."""
    resp = client.get(RXNORM, "rxcui.json", {"name": name, "search": "0"})
    rxcuis = parse_rxcuis(resp.body)
    if not rxcuis:
        raise Rejection(
            "rxnorm_identity_not_found",
            f"RxNorm resolved no RxCUI for {name!r}. The crosswalk is unresolved and is reported "
            "as unresolved.")
    if len(rxcuis) > 1:
        raise Rejection(
            "rxnorm_identity_ambiguous",
            f"RxNorm resolved {name!r} to {len(rxcuis)} RxCUIs ({', '.join(rxcuis[:8])}). Stage 4 "
            "does not choose one for you.")

    record = record_from_response(
        resp, run_root=run_root, stable_record_id=rxcuis[0], suffix="json",
        # Fetched BY IDENTITY: one named record was asked for and that record came back.
        # `exactly_one` on a pin — nothing was chosen by position.
        # `rxcui.json?name=...` is a NAME-TO-LIST query: RxNorm returns every RxCUI matching the
        # name. A collect-all in canonical order — not a GET of one named record.
        selection_disposition="sorted_unique", selection_pin=rxcuis[0],
        records_returned=len(rxcuis),

        release=_rxnorm_release(resp.body),
        extraction_transform="dailymed_select.parse_rxcuis:v1", adapter_file=__file__,
        note="RxNorm identity crosswalk only. It is not evidence of potency, exposure, safety "
             "or approval.")
    return rxcuis[0], record


def _rxnorm_release(raw: bytes) -> str:
    payload = _json(raw, "rxcui.json")
    version = (payload.get("idGroup") or {}).get("rxnormVersion")
    return str(version) if version else "not_reported_by_source"


# ----------------------------------------------------------------------------- DailyMed


def parse_spl_listing(raw: bytes) -> list[SplListing]:
    payload = _json(raw, "spls.json")
    rows = payload.get("data")
    if not isinstance(rows, list):
        raise Rejection("dailymed_response_unparseable",
                        "the DailyMed listing response carries no `data` array")
    listings = []
    for row in rows:
        setid = str(row.get("setid") or "").strip()
        if not setid:
            continue
        listings.append(SplListing(
            setid=setid,
            spl_version=str(row.get("spl_version") or "").strip(),
            title=str(row.get("title") or "").strip(),
            published_date=_opt(row.get("published_date")),
        ))
    return listings


def listing_total_reported(raw: bytes) -> Optional[int]:
    """DailyMed's OWN match count (`metadata.total_elements`), carried instead of discarded.

    `assert_listing_complete` reads this to refuse a partial page — and it was then thrown away, so
    the emitted record could not state the number the source actually reported and `materialize`
    fabricated `match_total_reported=1`. The source's own count now travels with the bytes. `None`
    means DailyMed reported no total, and `None` is what is carried.
    """
    total = (_json(raw, "spls.json").get("metadata") or {}).get("total_elements")
    return total if isinstance(total, int) else None


def assert_listing_complete(raw: bytes, listings: list[SplListing]) -> None:
    """The listing we selected from must be the WHOLE listing.

    DailyMed paginates. A page-1 response that reports 40 total elements while handing back one
    product is not the candidate set, and selecting the "only" product on it is a first-hit with
    extra steps — the same defect the openFDA `limit=1` had.
    """
    metadata = _json(raw, "spls.json").get("metadata") or {}
    total = metadata.get("total_elements")
    if isinstance(total, int) and total > len(listings):
        raise Rejection(
            "dailymed_listing_incomplete",
            f"DailyMed reports {total} products for this query but this page carries "
            f"{len(listings)}. Stage 4 will not select from a partial listing: uniqueness cannot "
            "be established from a page. Pin the product with --dailymed-setid, or widen the "
            "page size.")


def select_spl(listings: list[SplListing], *, setid: Optional[str] = None) -> SplListing:
    """Deterministic selection. One product, or an explicit pin, or a refusal naming them all."""
    if not listings:
        raise Rejection(
            "dailymed_product_not_found",
            "DailyMed returned no product for this query. No label is selected, and 'no label' "
            "is not evidence that the drug is unlabelled — it is an unsuccessful search.")

    if setid:
        chosen = [ls for ls in listings if ls.setid == setid]
        if not chosen:
            raise Rejection(
                "dailymed_setid_not_in_listing",
                f"the pinned set ID {setid!r} is not among the products DailyMed returned "
                f"({', '.join(ls.setid for ls in listings)}). A pin that does not match the "
                "discovery response is a stale pin, not a selection.")
        if len(chosen) > 1:
            raise Rejection(
                "dailymed_product_selection_ambiguous",
                f"DailyMed returned {len(chosen)} entries for set ID {setid!r}")
        return chosen[0]

    if len(listings) > 1:
        candidates = "; ".join(f"{ls.setid} (v{ls.spl_version}) {ls.title[:60]}"
                               for ls in sorted(listings, key=lambda x: x.setid))
        raise Rejection(
            "dailymed_product_selection_ambiguous",
            f"DailyMed returned {len(listings)} products for this drug name. Stage 4 does not "
            "take the first hit — a labelled warning read off the wrong product is worse than "
            f"no warning at all. Pin one with --dailymed-setid. Candidates: {candidates}")
    return listings[0]


def acquire_label(client: Client, run_root: RunRoot, name: str, *,
                  setid: Optional[str] = None) -> tuple[SelectedLabel, list[AcquisitionRecord]]:
    """Discover -> select deterministically -> fetch -> verify the version -> parse."""
    listing_resp = client.get(DAILYMED, "spls.json",
                              {"drug_name": name, "pagesize": PAGE_SIZE})
    listings = parse_spl_listing(listing_resp.body)
    assert_listing_complete(listing_resp.body, listings)
    chosen = select_spl(listings, setid=setid)

    spl_resp = client.get(DAILYMED, f"spls/{chosen.setid}.xml")
    try:
        label = parse_dailymed_spl(spl_resp.body)
    except LabelParseError as exc:
        raise Rejection(
            "dailymed_label_unparseable",
            f"the SPL for set ID {chosen.setid!r} is not the document shape the parser accepts: "
            f"{exc}") from exc

    # A label with no version has no identity. There is no `.vunversioned` label: an SPL that
    # does not say which version it is cannot be re-fetched, re-checked, or distinguished from
    # the next revision of itself, so it is UNAVAILABLE rather than usable-with-a-placeholder.
    if not chosen.spl_version:
        raise Rejection(
            "dailymed_version_unavailable",
            f"the DailyMed listing for set ID {chosen.setid!r} carries no spl_version. A label "
            "version is part of the label's identity; Stage 4 does not substitute a placeholder "
            "for one the source did not give.")
    if not label.label_version:
        raise Rejection(
            "dailymed_version_unavailable",
            f"the SPL served for set ID {chosen.setid!r} declares no versionNumber. An unversioned "
            "document cannot be distinguished from the next revision of itself, and Stage 4 will "
            "not invent a version to bind evidence to.")
    if label.label_version != chosen.spl_version:
        raise Rejection(
            "dailymed_version_conflict",
            f"DailyMed listed set ID {chosen.setid!r} at version {chosen.spl_version}, but the "
            f"document it served is version {label.label_version}. Those are two different "
            "labels; Stage 4 refuses rather than deciding which one the evidence came from.")
    if label.setid != chosen.setid:
        raise Rejection(
            "dailymed_setid_conflict",
            f"the document served under set ID {chosen.setid!r} declares set ID {label.setid!r}. "
            "The document is not the record that was requested, and Stage 4 does not read a label "
            "it did not ask for.")

    records = [
        record_from_response(
            listing_resp, run_root=run_root, stable_record_id=chosen.setid, suffix="json",
            release=f"listing:{len(listings)}_product(s)",
            # THE DailyMed LISTING is a SEARCH: `total_elements` is the source's own match count,
            # and it is carried rather than discarded. When it exceeds what the page handed back,
            # the result set is NOT complete and this record says so.
            # The LISTING is a genuine SEARCH: `total_elements` is DailyMed's own match count, and
            # uniqueness must be DEMONSTRATED against what actually arrived. `exactly_one` on a pin,
            # with the source's numbers — never assumed complete.
            selection_disposition="exactly_one", selection_pin=chosen.setid,
            match_total_reported=listing_total_reported(listing_resp.body),
            records_returned=len(listings),
            result_set_complete=(listing_total_reported(listing_resp.body) == len(listings)),
            extraction_transform="dailymed_select.parse_spl_listing:v1", adapter_file=__file__,
            note=f"product discovery for {name!r}; selection is deterministic (one product, or "
                 "an explicit pin)"),
        record_from_response(
            spl_resp, run_root=run_root, stable_record_id=chosen.setid, suffix="xml",
            release=f"spl_version={label.label_version}; effective_time={label.effective_date}",
            # GET /spls/{setid}.xml — a TRUE identity GET. The document IS the record: no result
            # set, no total, and no completeness boolean. Both stay null rather than being invented.
            selection_disposition="identity_get", selection_pin=chosen.setid,
            records_returned=1,
            extraction_transform="label_adapters.parse_dailymed_spl:v1 (nested subsections "
                                 "included; Highlights <excerpt> excluded)",
            adapter_file=__file__, review_status="unreviewed",
            note="DailyMed has NO verified blanket licence and warns that in-use labelling may "
                 "differ from current FDA-approved labelling. These bytes are cached under the "
                 "run root and are never committed to Git."),
    ]
    return SelectedLabel(listing=chosen, label=label), records


def _json(raw: bytes, what: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise Rejection("dailymed_response_unparseable",
                        f"the {what} response is not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise Rejection("dailymed_response_unparseable", f"the {what} response is not an object")
    return payload


def _opt(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
