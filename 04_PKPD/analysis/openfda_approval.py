"""openFDA / Drugs@FDA — the approval cross-check.

DailyMed publishes what is IN USE. Drugs@FDA publishes what is APPROVED. The audit's §4.5
finding is that Stage 4 was reading the first without ever consulting the second, and DailyMed
itself warns that in-use labelling may differ from current FDA-approved labelling and is not
reviewed by NLM.

So a selected label must tie to an approval:

    setid --(openFDA drug/label)--> application number --(openFDA drug/drugsfda)--> approval

If the application number the label carries is not the one Drugs@FDA returns for it, the two
records are about different things and the safety lane is `not_evaluated` — never
"cross-checked anyway". That is the `label_current_and_approval_crosschecked` gate:
consequence_on_fail is safety_not_evaluated, and this is where it fails.

openFDA is generally CC0 **with marked source exceptions**, its data are unvalidated, and the
original response (with its disclaimer) is retained. None of that makes a field FDA-validated.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Optional

from .acquire_http import Client
from .acquisition import AcquisitionRecord, RunRoot, record_from_response
from .firewall import Rejection

SOURCE_KEY = "openfda"


@dataclass(frozen=True)
class OpenFdaLabelIdentity:
    set_id: str
    application_number: Optional[str]
    unii: Optional[str]
    generic_name: Optional[str]
    label_version: Optional[str]
    last_updated: str


@dataclass(frozen=True)
class Approval:
    """What Drugs@FDA says, cross-checked against the label that pointed at it.

    The two UNIIs are kept SEPARATE — Drugs@FDA's and the openFDA label's. Collapsing them by
    preferring one source would hide precisely the disagreement the identity gate exists to
    catch: both claims travel, and `identity.resolve_identity` refuses if they differ.
    """

    application_number: str
    marketing_status: Optional[str]
    sponsor: Optional[str]
    unii: Optional[str]           # as reported by Drugs@FDA
    label_unii: Optional[str]     # as reported by the openFDA label record
    setid: str
    last_updated: str


def parse_openfda_label_identity(raw: bytes, setid: str) -> OpenFdaLabelIdentity:
    payload = _json(raw, "drug/label.json")
    results = payload.get("results") or []
    if not results:
        raise Rejection(
            "openfda_label_not_found",
            f"openFDA returned no label for set ID {setid!r}. Without it there is no application "
            "number, so the approval cross-check cannot run and the safety lane stays "
            "not_evaluated.")
    row = results[0]
    of = row.get("openfda") or {}
    return OpenFdaLabelIdentity(
        set_id=str(row.get("set_id") or setid),
        application_number=_first(of.get("application_number")),
        unii=_first(of.get("unii")),
        generic_name=_first(of.get("generic_name")),
        label_version=_opt(row.get("version")),
        last_updated=str((payload.get("meta") or {}).get("last_updated")
                         or "not_reported_by_source"),
    )


def parse_drugsfda(raw: bytes, application_number: str) -> tuple[str, Optional[str], Optional[str], Optional[str], str]:
    """-> (application number, marketing status, sponsor, UNII, last_updated) as REPORTED."""
    payload = _json(raw, "drug/drugsfda.json")
    results = payload.get("results") or []
    if not results:
        raise Rejection(
            "drugsfda_application_not_found",
            f"Drugs@FDA knows no application {application_number!r}. The label could not be tied "
            "to an approval, so it is not cross-checked.")
    row = results[0]
    products = row.get("products") or []
    return (
        str(row.get("application_number") or ""),
        _opt((products[0] or {}).get("marketing_status")) if products else None,
        _opt(row.get("sponsor_name")),
        _first((row.get("openfda") or {}).get("unii")),
        str((payload.get("meta") or {}).get("last_updated") or "not_reported_by_source"),
    )


def cross_check_approval(*, label_application_number: str,
                         drugsfda_application_number: str) -> None:
    """The gate. Two application numbers, or the safety lane is not evaluated."""
    if label_application_number != drugsfda_application_number:
        raise Rejection(
            "approval_conflict",
            f"the label carries application {label_application_number!r}, but Drugs@FDA answers "
            f"with {drugsfda_application_number!r}. Those are not the same approval. Stage 4 does "
            "not cross-check a label against an application that is not its own — the safety "
            "lane stays not_evaluated rather than borrowing someone else's approval.")


def acquire_approval(client: Client, run_root: RunRoot,
                     setid: str) -> tuple[Approval, list[AcquisitionRecord]]:
    """setid -> application number -> approval, with both responses recorded."""
    label_resp = client.get(SOURCE_KEY, "drug/label.json",
                            {"search": f'openfda.spl_set_id:"{setid}"', "limit": "1"})
    label = parse_openfda_label_identity(label_resp.body, setid)
    if not label.application_number:
        raise Rejection(
            "openfda_application_number_missing",
            f"the openFDA label for set ID {setid!r} carries no application number, so it cannot "
            "be tied to a Drugs@FDA approval. The safety lane stays not_evaluated.")

    fda_resp = client.get(
        SOURCE_KEY, "drug/drugsfda.json",
        {"search": f'openfda.application_number:"{label.application_number}"', "limit": "1"})
    app_no, marketing_status, sponsor, unii, last_updated = parse_drugsfda(
        fda_resp.body, label.application_number)

    cross_check_approval(label_application_number=label.application_number,
                         drugsfda_application_number=app_no)

    records = [
        record_from_response(
            label_resp, run_root=run_root, stable_record_id=setid, suffix="json",
            release=label.last_updated,
            extraction_transform="openfda_approval.parse_openfda_label_identity:v1",
            adapter_file=__file__,
            note="openFDA is generally CC0 with marked source exceptions; its data are "
                 "unvalidated. This record supplies identity and the application number only."),
        record_from_response(
            fda_resp, run_root=run_root, stable_record_id=app_no, suffix="json",
            release=last_updated,
            extraction_transform="openfda_approval.parse_drugsfda:v1", adapter_file=__file__,
            note="Drugs@FDA approval cross-check. An approval is not a safety finding and says "
                 "nothing about brain penetrance."),
    ]
    approval = Approval(
        application_number=app_no,
        marketing_status=marketing_status,
        sponsor=sponsor,
        unii=unii,
        label_unii=label.unii,
        setid=setid,
        last_updated=last_updated,
    )
    return approval, records


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


def _first(values: Any) -> Optional[str]:
    if isinstance(values, list) and values:
        return _opt(values[0])
    return None


def _opt(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
