"""Source-reported totals: required where the source reports one, NULL where it does not.

The integration gate, in the form W6/W9 corrected it to:

    It is not enough for `AcquisitionRecord` to HAVE the fields. The real adapter constructors —
    pubchem, dailymed_select, openfda_approval — must pass `selection_disposition`,
    `selection_pin`, `match_total_reported`, `records_returned` and `result_set_complete` THROUGH
    `record_from_response`, from the response the source actually sent.

But the requirement is not uniform, and treating it as uniform is its own fabrication:

  * **SEARCH / LIST endpoints** — openFDA `drug/label.json`, openFDA `drug/drugsfda.json`, DailyMed
    `spls.json` — DO report how many records matched (`meta.results.total`,
    `metadata.total_elements`). For these the total is MANDATORY, and `result_set_complete` must be
    DERIVED from it (total == returned). A truncated page called complete is the exact defect the
    `limit=1` audit found.

  * **DIRECT identity / full-list endpoints** — PubChem name→CIDs, PubChem CID→properties, RxNorm
    `rxcui.json`, DailyMed `spls/{setid}.xml` — report NO match total. They return the document, or
    the whole list, and that is all. For these `match_total_reported` stays **null**, and the proof
    of completeness is the typed `selection_disposition`, not a number.

**Inventing `total = 1` because one row came back is forbidden.** It is indistinguishable in the
artifact from a total the source actually reported, and it silently converts "the source did not
say" into "the source said one". An honest null is preserved — in the record and in the receipt —
and is never refused.
"""

from __future__ import annotations

from typing import Any, Iterable, Optional

from .firewall import Rejection

# What the ADAPTER must pass through `record_from_response`. Presence is mandatory; a null VALUE is
# legitimate only where this module says it is.
REQUIRED_TOTAL_FIELDS = (
    "selection_disposition",     # the typed proof of HOW this record was selected
    "selection_pin",             # the identity the query pinned (setid, application number, CID…)
    "match_total_reported",      # the source's OWN match count — null where the source reports none
    "records_returned",          # how many rows actually arrived
    "result_set_complete",       # DERIVED from total vs returned. Null where there is no total.
)

# Endpoints that report a match total. Keyed on (source_key, canonical-query prefix).
SEARCH_LIST_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("openfda", "drug/label.json"),
    ("openfda", "drug/drugsfda.json"),
    ("dailymed", "spls.json"),
)

# Endpoints that report no total at all. A number here would have been invented.
DIRECT_ENDPOINTS: tuple[tuple[str, str], ...] = (
    ("pubchem", "compound/"),
    ("rxnorm", "rxcui.json"),
    ("dailymed", "spls/"),
)

SEARCH_LIST = "search_list"
DIRECT = "direct"
UNKNOWN = "unknown"


def query_class(source_key: str, canonical_query: str) -> str:
    """Does THIS endpoint report a match total? The rule is the endpoint's, not the record's."""
    query = (canonical_query or "").lstrip("/")
    for key, prefix in SEARCH_LIST_ENDPOINTS:
        if source_key == key and query.startswith(prefix):
            return SEARCH_LIST
    for key, prefix in DIRECT_ENDPOINTS:
        if source_key == key and query.startswith(prefix):
            return DIRECT
    return UNKNOWN


def assert_model_carries_totals() -> None:
    """PREFLIGHT. Refuse before a single request if the contract cannot even hold the fields.

    Without this the gate would fire only after the bytes were fetched — refused, but with the
    network already touched. The hold is checked BEFORE the wire, not after it.
    """
    from .acquisition import AcquisitionRecord

    fields = set(getattr(AcquisitionRecord, "model_fields", {}))
    absent = [f for f in REQUIRED_TOTAL_FIELDS if f not in fields]
    if absent:
        raise Rejection(
            "source_totals_not_bound",
            f"AcquisitionRecord cannot carry {absent}, so no adapter can pass the source-reported "
            "totals through record_from_response and no receipt could state them. NO REQUEST IS "
            "MADE. Held pending the exact W6 commit (the fields AND the adapter constructors that "
            "fill them) and W9's end-to-end adapter GO.")


def totals_of(record: Any) -> dict[str, Any]:
    """Read the five off a record. A null stays null — it is never defaulted and never stamped."""
    return {field: getattr(record, field, None) for field in REQUIRED_TOTAL_FIELDS}


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def assert_totals_bound(records: Iterable[Any]) -> None:
    """Gate each fetched record BY ITS ENDPOINT CLASS. Honest absence is preserved, not refused."""
    for record in records:
        if getattr(record, "origin", None) != "fetched_public":
            continue                      # a reused/fixture record made no request of its own

        rid = getattr(record, "acquisition_record_id", "?")
        source_key = str(getattr(record, "source_key", ""))
        cls = query_class(source_key, str(getattr(record, "canonical_query", "")))

        # The typed proof of selection, and the count of what arrived, are ALWAYS required: we
        # always know how we chose and how many rows we parsed.
        for always in ("selection_disposition", "records_returned"):
            if getattr(record, always, None) is None:
                raise Rejection(
                    "source_totals_not_bound",
                    f"{rid!r} ({source_key}) carries no {always}. The adapter did not pass it "
                    "through record_from_response. Held pending the W6 commit and W9's "
                    "end-to-end adapter GO.")

        total = _as_int(getattr(record, "match_total_reported", None))
        returned = _as_int(getattr(record, "records_returned", None))
        complete = getattr(record, "result_set_complete", None)

        if cls == SEARCH_LIST:
            # The source DOES report a total here. Its absence is a dropped field, not an honest
            # null, and completeness must be derived from it.
            if total is None:
                raise Rejection(
                    "source_total_missing_on_search",
                    f"{rid!r}: {source_key} search/list endpoints report a match total "
                    "(meta.results.total / metadata.total_elements) and the adapter did not pass "
                    "it through. Without it a truncated page cannot be told from a complete one — "
                    "which is exactly the defect the limit=1 audit found.")
            if complete is None:
                raise Rejection(
                    "source_total_missing_on_search",
                    f"{rid!r}: result_set_complete is null on a search/list endpoint that reports "
                    "a total. Completeness is derivable here, so it must be derived.")
            if bool(complete) != (total == returned):
                raise Rejection(
                    "source_totals_inconsistent",
                    f"{rid!r}: result_set_complete={complete!r} does not follow from "
                    f"match_total_reported={total!r} and records_returned={returned!r}. "
                    "Completeness is DERIVED from what the source reported; a flag that disagrees "
                    "with its own inputs was asserted, not measured.")

        elif cls == DIRECT:
            # The source reports NO total. Null is the honest answer and is preserved. A number
            # here was invented — above all a `1` that merely echoes the single row that arrived.
            if total is not None:
                raise Rejection(
                    "source_total_invented",
                    f"{rid!r}: {source_key} direct/identity endpoints report no match total, but "
                    f"this record carries match_total_reported={total!r}. A total the source never "
                    "reported is a fabricated one — a `1` that echoes the single row that arrived "
                    "is indistinguishable in the artifact from a total the source actually stated. "
                    "Preserve null and let selection_disposition carry the proof.")
            if complete is not None:
                raise Rejection(
                    "source_total_invented",
                    f"{rid!r}: result_set_complete={complete!r} on an endpoint with no reported "
                    "total. Completeness cannot be derived from a total that does not exist; the "
                    "typed selection_disposition is the proof here, not a boolean.")
