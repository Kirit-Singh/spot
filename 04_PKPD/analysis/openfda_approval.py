"""openFDA / Drugs@FDA — the approval cross-check, on SETS, with no first record and no first
product.

DailyMed publishes what is IN USE. Drugs@FDA publishes what is APPROVED. A selected label must
tie to an approval:

    setid --(openFDA drug/label)--> application number(s) --(drug/drugsfda)--> approval(s)

The independent cross-check flagged `results[0]`, `products[0]` and `limit=1` here, and the live
data proved the flag was not theoretical:

    TEMODAR's label declares TWO application numbers — NDA021029 (capsule) and NDA022277
    (injection) — and its Drugs@FDA record carries SIX products.

Taking the first application number bound the approval cross-check to an arbitrary ROUTE, and
oral and IV are not the same exposure. `limit=1` then truncated the result set so the multiplicity
could not even be seen. Both are gone:

  * the label record is selected by its set ID (`exactly_one`), and the query's own
    `meta.results.total` must agree with what came back, or the result set is refused as
    truncated;
  * EVERY application number the label declares survives, in canonical order, and EVERY ONE is
    cross-checked against Drugs@FDA. The cross-check compares SETS: Drugs@FDA must answer for
    each one, or `approval_conflict`;
  * every product's marketing status survives, sorted and de-duplicated. No product is chosen;
  * a label declaring two active-moiety UNIIs is refused, not reduced.

openFDA is generally CC0 **with marked source exceptions**, its data are unvalidated, and the
original response and its disclaimer are retained. None of that makes a field FDA-validated, and
an approval is not a safety finding.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from .acquire_http import Client
from .acquisition import AcquisitionRecord, RunRoot, record_from_response
from .firewall import Rejection
from .selection import assert_result_set_complete, exactly_one, sorted_unique

SOURCE_KEY = "openfda"

# Bounded, but wide enough that the source's own `total` can be checked against what arrived.
# `limit=1` could not have detected a duplicate even in principle.
QUERY_LIMIT = "25"


@dataclass(frozen=True)
class OpenFdaLabelIdentity:
    """What the openFDA label record says about the label we selected on DailyMed."""

    set_id: str
    application_numbers: tuple[str, ...]   # ALL of them. TEMODAR declares two.
    unii: Optional[str]                    # exactly one, or the parse refused
    generic_name: Optional[str]
    label_version: Optional[str]
    last_updated: str
    # THE SOURCE'S OWN MATCH TOTAL, carried rather than discarded.
    #
    # `meta.results.total` is read and fed to `assert_result_set_complete` — and was then thrown
    # away, so `materialize` had nothing to state and FABRICATED `match_total_reported=1,
    # result_set_complete=True`. For a SEARCH that is false: openFDA may report forty matches and
    # hand back one. The number the source actually reported now travels with the record. None
    # means openFDA reported no total — and None is carried, never 1.
    match_total_reported: Optional[int] = None
    records_returned: Optional[int] = None


@dataclass(frozen=True)
class ProductApproval:
    """One Drugs@FDA application. Its products are summarised, never sampled."""

    application_number: str
    sponsor: Optional[str]
    unii: Optional[str]
    marketing_statuses: tuple[str, ...]    # sorted, de-duplicated across every product
    n_products: int
    # openFDA's OWN match total, read by `assert_result_set_complete` and then discarded. Carried.
    match_total_reported: Optional[int] = None
    records_returned: Optional[int] = None


@dataclass(frozen=True)
class ApprovalSet:
    """Every approval the selected label ties to. Nothing here was chosen by position."""

    setid: str
    application_numbers: tuple[str, ...]
    approvals: tuple[ProductApproval, ...]
    label_unii: Optional[str]
    last_updated: str

    @property
    def marketing_statuses(self) -> tuple[str, ...]:
        return sorted_unique(s for a in self.approvals for s in a.marketing_statuses)

    @property
    def unii(self) -> Optional[str]:
        """The active-moiety UNII Drugs@FDA reports — one, or none. Two would have refused."""
        uniis = sorted_unique(a.unii for a in self.approvals if a.unii)
        if len(uniis) > 1:
            raise Rejection(
                "drugsfda_unii_ambiguous",
                f"the approvals for {self.setid!r} report {len(uniis)} different active-moiety "
                f"UNIIs ({', '.join(uniis)}). They are not all the same molecule.")
        return uniis[0] if uniis else None


def parse_openfda_label_identity(raw: bytes, setid: str) -> OpenFdaLabelIdentity:
    """The label record whose set ID IS the pin. Not the first one in the response."""
    payload = _json(raw, "drug/label.json")
    results = list(payload.get("results") or [])
    meta = ((payload.get("meta") or {}).get("results") or {})

    total = _int(meta.get("total"))
    assert_result_set_complete(total=total, returned=len(results),
                               what="openFDA label", pin=setid,
                               code="openfda_result_set_truncated", require_total=True)

    row = exactly_one(
        results,
        matches=lambda r: str(r.get("set_id") or "") == setid,
        what="openFDA label", pin=setid,
        zero_code="openfda_label_not_found",
        many_code="openfda_label_ambiguous",
        describe=lambda r: f"set_id={r.get('set_id')} version={r.get('version')}",
    )

    of = row.get("openfda") or {}
    uniis = sorted_unique(of.get("unii") or [])
    if len(uniis) > 1:
        raise Rejection(
            "openfda_unii_ambiguous",
            f"the openFDA label for set ID {setid!r} declares {len(uniis)} active-moiety UNIIs "
            f"({', '.join(uniis)}). A multi-ingredient product has no single active moiety, and "
            "Stage 4 does not pick one to hang a PK claim on.")

    return OpenFdaLabelIdentity(
        set_id=setid,
        # The source's own numbers, verbatim. None means openFDA reported no total -- and None is
        # what is carried, never 1.
        match_total_reported=total,
        records_returned=len(results),
        # Every application the label declares. TEMODAR: NDA021029 (capsule) + NDA022277 (IV).
        application_numbers=sorted_unique(of.get("application_number") or []),
        unii=uniis[0] if uniis else None,
        generic_name=(sorted_unique(of.get("generic_name") or []) or (None,))[0],
        label_version=_opt(row.get("version")),
        last_updated=str((payload.get("meta") or {}).get("last_updated")
                         or "not_reported_by_source"),
    )


def parse_drugsfda(raw: bytes, application_number: str) -> ProductApproval:
    """The application whose number IS the pin, with EVERY product's status preserved."""
    payload = _json(raw, "drug/drugsfda.json")
    results = list(payload.get("results") or [])
    meta = ((payload.get("meta") or {}).get("results") or {})

    fda_total = _int(meta.get("total"))
    assert_result_set_complete(total=fda_total, returned=len(results),
                               what="Drugs@FDA application", pin=application_number,
                               code="drugsfda_result_set_truncated", require_total=True)

    row = exactly_one(
        results,
        matches=lambda r: str(r.get("application_number") or "") == application_number,
        what="Drugs@FDA application", pin=application_number,
        zero_code="drugsfda_application_not_found",
        many_code="drugsfda_application_ambiguous",
        describe=lambda r: f"application_number={r.get('application_number')} "
                           f"sponsor={r.get('sponsor_name')}",
    )

    products = list(row.get("products") or [])
    return ProductApproval(
        match_total_reported=fda_total,
        records_returned=len(results),
        application_number=application_number,
        sponsor=_opt(row.get("sponsor_name")),
        unii=(sorted_unique((row.get("openfda") or {}).get("unii") or []) or (None,))[0],
        # Every product's status, sorted and de-duplicated. The live record has six products;
        # `products[0].marketing_status` was a coin toss among them.
        marketing_statuses=sorted_unique(p.get("marketing_status") for p in products),
        n_products=len(products),
    )


def cross_check_approval(*, label_application_numbers: tuple[str, ...],
                         drugsfda_application_numbers: tuple[str, ...]) -> None:
    """The gate, on SETS. Drugs@FDA must answer for every application the label declared.

    Note what carries the weight. Because `acquire_approval` PINS each declared application in its
    own query and `parse_drugsfda` refuses a record that is not that application
    (`drugsfda_application_not_found`), an application the label declares but Drugs@FDA does not
    know is already refused before this runs. This is therefore an INVARIANT check on that path —
    kept because it is the only thing standing between a future bulk/unpinned query and the exact
    subset-of-my-own-approvals bug the cross-check flagged.
    """
    declared = set(label_application_numbers)
    answered = set(drugsfda_application_numbers)
    if declared != answered:
        missing = sorted(declared - answered)
        extra = sorted(answered - declared)
        raise Rejection(
            "approval_conflict",
            f"the label declares applications {sorted(declared)}, but Drugs@FDA was resolved for "
            f"{sorted(answered)}"
            + (f"; unanswered: {missing}" if missing else "")
            + (f"; unexpected: {extra}" if extra else "")
            + ". Stage 4 does not cross-check a label against a subset of its own approvals — a "
              "label covering an oral and an IV product is not evidence about whichever one was "
              "listed first. The safety lane stays not_evaluated.")


def acquire_approval(client: Client, run_root: RunRoot,
                     setid: str) -> tuple[ApprovalSet, list[AcquisitionRecord]]:
    """setid -> every application it declares -> every approval, each one fetched and recorded."""
    label_resp = client.get(SOURCE_KEY, "drug/label.json",
                            {"search": f'openfda.spl_set_id:"{setid}"', "limit": QUERY_LIMIT})
    label = parse_openfda_label_identity(label_resp.body, setid)
    if not label.application_numbers:
        raise Rejection(
            "openfda_application_number_missing",
            f"the openFDA label for set ID {setid!r} carries no application number, so it cannot "
            "be tied to a Drugs@FDA approval. The safety lane stays not_evaluated.")

    records = [
        record_from_response(
            label_resp, run_root=run_root, stable_record_id=setid, suffix="json",
            # Fetched BY IDENTITY: one named record was asked for and that record came back.
            # `exactly_one` on a pin — nothing was chosen by position.
            selection_disposition="exactly_one",
            # THE SOURCE'S OWN NUMBERS, read in `parse_openfda_label_identity` and no longer
            # discarded here. openFDA may report forty matches and hand back one; if it does, this
            # record says so instead of swearing the result set was complete.
            match_total_reported=label.match_total_reported,
            records_returned=label.records_returned,
            result_set_complete=(label.match_total_reported == label.records_returned
                                 if label.match_total_reported is not None else False),
            release=label.last_updated,
            extraction_transform="openfda_approval.parse_openfda_label_identity:v2",
            adapter_file=__file__,
            note="openFDA is generally CC0 with marked source exceptions; its data are "
                 "unvalidated. Identity and EVERY declared application number, none chosen by "
                 "position."),
    ]

    approvals: list[ProductApproval] = []
    for application_number in label.application_numbers:      # canonical order, all of them
        fda_resp = client.get(
            SOURCE_KEY, "drug/drugsfda.json",
            {"search": f'openfda.application_number:"{application_number}"',
             "limit": QUERY_LIMIT})
        approval = parse_drugsfda(fda_resp.body, application_number)
        approvals.append(approval)
        records.append(record_from_response(
            fda_resp, run_root=run_root, stable_record_id=application_number, suffix="json",
            # A SEARCH over Drugs@FDA, matched on the application-number pin. Uniqueness is
            # DEMONSTRATED against openFDA's own total — never assumed from the endpoint.
            selection_disposition="exactly_one", selection_pin=application_number,
            match_total_reported=approval.match_total_reported,
            records_returned=approval.records_returned,
            result_set_complete=(approval.match_total_reported == approval.records_returned
                                 if approval.match_total_reported is not None else False),

            release=_last_updated(fda_resp.body),
            extraction_transform="openfda_approval.parse_drugsfda:v2", adapter_file=__file__,
            note=f"Drugs@FDA cross-check for {application_number}. Every product's marketing "
                 "status is preserved; none is selected. An approval is not a safety finding and "
                 "says nothing about brain penetrance."))

    cross_check_approval(
        label_application_numbers=label.application_numbers,
        drugsfda_application_numbers=tuple(a.application_number for a in approvals))

    approval_set = ApprovalSet(
        setid=setid,
        application_numbers=label.application_numbers,
        approvals=tuple(approvals),
        label_unii=label.unii,
        last_updated=label.last_updated,
    )
    approval_set.unii  # raises drugsfda_unii_ambiguous if the approvals disagree
    return approval_set, records


def _last_updated(raw: bytes) -> str:
    payload = _json(raw, "drug/drugsfda.json")
    return str((payload.get("meta") or {}).get("last_updated") or "not_reported_by_source")


def _json(raw: bytes, what: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise Rejection("openfda_response_unparseable",
                        f"the openFDA {what} response is not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise Rejection("openfda_response_unparseable",
                        f"the openFDA {what} response is not an object")
    return payload


def _int(value: Any) -> Optional[int]:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _opt(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
