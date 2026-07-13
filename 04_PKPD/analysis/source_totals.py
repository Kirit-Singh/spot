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

# W6's typed proof, carried from the fetch. It is AUTHORITATIVE — the adapter knows what it asked
# for — but it is cross-checked against the endpoint, because an adapter that labels a SEARCH as an
# `identity_get` would skip the total requirement entirely. That is the one path that launders a
# dropped total into a legitimate-looking null.
IDENTITY_GET = "identity_get"      # one named record. No result set, so no total, no completeness.
EXACTLY_ONE = "exactly_one"        # a search pinned to one record. The source reports a total.
SORTED_UNIQUE = "sorted_unique"    # collect-all in canonical order. Nothing chosen, nothing dropped.

# Which dispositions an endpoint class may honestly claim.
ALLOWED_BY_CLASS = {
    SEARCH_LIST: {EXACTLY_ONE, SORTED_UNIQUE},
    DIRECT: {IDENTITY_GET, SORTED_UNIQUE},
}

# W9's end-to-end adapter GO. The wire stays shut until it is set — an explicit switch, not an
# accident of a missing field. (Before W6 landed, the hold happened to come from the model being
# unable to carry the proof at all; that is not a gate, it is a coincidence.)
ADAPTER_GO_ENV = "SPOT_STAGE4_ADAPTER_GO"


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
    """PREFLIGHT 1. The contract must be able to hold the proof at all."""
    from .acquisition import AcquisitionRecord

    fields = set(getattr(AcquisitionRecord, "model_fields", {}))
    absent = [f for f in REQUIRED_TOTAL_FIELDS if f not in fields]
    if absent:
        raise Rejection(
            "source_totals_not_bound",
            f"AcquisitionRecord cannot carry {absent}, so no adapter can pass the source-reported "
            "totals through record_from_response and no receipt could state them. NO REQUEST IS "
            "MADE.")


def assert_adapter_go() -> None:
    """PREFLIGHT 2. W9's end-to-end adapter GO. The wire stays shut without it.

    This is an EXPLICIT switch, deliberately. Until W6 landed, the network happened to be held
    because the model could not carry the selection proof — but a hold that depends on a field
    being missing evaporates the moment the field arrives, which is exactly what happened. A gate
    has to be a gate.
    """
    import os

    if os.environ.get(ADAPTER_GO_ENV) != "1":
        raise Rejection(
            "adapter_go_not_given",
            f"W9's end-to-end adapter GO has not been given ({ADAPTER_GO_ENV} is not set). The "
            "selection proof now reaches the record, but no request goes on the wire until the "
            "adapters have been attacked end to end and passed. NO REQUEST IS MADE.")


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
        canonical_query = str(getattr(record, "canonical_query", ""))
        cls = query_class(source_key, canonical_query)

        # An endpoint nobody has classified is refused BEFORE it can be accepted. Without this a
        # new adapter — or a new path on an existing source — falls through both rules and is
        # admitted with no total requirement AND no invented-total check: the one shape that
        # escapes the gate entirely. Whether a source reports a match total is a fact about that
        # endpoint, so a new one is a decision someone makes on the record, not a default.
        if cls == UNKNOWN:
            raise Rejection(
                "source_endpoint_unclassified",
                f"{rid!r}: {source_key!r} endpoint {canonical_query!r} is in neither "
                f"SEARCH_LIST_ENDPOINTS nor DIRECT_ENDPOINTS. Stage 4 does not guess whether an "
                "endpoint reports a match total — guessing 'no' would excuse a dropped total, and "
                "guessing 'yes' would demand an invented one. Classify it in source_totals.py "
                "against the source's actual response shape, then re-run.")

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
        disposition = str(getattr(record, "selection_disposition", ""))

        # The adapter's typed claim must match what the endpoint actually IS. An adapter that calls
        # an openFDA SEARCH an `identity_get` would be excused from reporting a total — a dropped
        # total wearing an honest null's clothes.
        if disposition not in ALLOWED_BY_CLASS.get(cls, set()):
            raise Rejection(
                "selection_disposition_mismatch",
                f"{rid!r}: the adapter claims selection_disposition={disposition!r} for "
                f"{source_key!r} {canonical_query!r}, which is a {cls} endpoint (allowed: "
                f"{sorted(ALLOWED_BY_CLASS.get(cls, set()))}). A search labelled an identity GET "
                "escapes the source-total requirement entirely; the label must match the request "
                "that was actually made.")

        # An identity GET has no result set, so completeness is not a question it can answer.
        if disposition == IDENTITY_GET and (total is not None or complete is not None):
            raise Rejection(
                "source_total_invented",
                f"{rid!r}: an identity_get returns ONE named record — there is no result set, so "
                f"match_total_reported={total!r} / result_set_complete={complete!r} are answers to "
                "a question the request never asked. Both stay null.")

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
