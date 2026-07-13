"""Open Targets target<->disease association acquisition for the GBM disease-context layer.

Verified against the live public API on 2026-07-13 (Open Targets Platform Data 26.06,
GraphQL api.platform.opentargets.org/api/v4/graphql, licence CC0 1.0):

  * ``Target.associatedDiseases`` takes a ``Bs`` list of disease ids (NOT ``efoIds``);
  * glioblastoma is ``MONDO_0018177`` and glioma is ``MONDO_0021042`` (``EFO_0000519`` is
    null/deprecated — it was NOT used);
  * each row carries an aggregated ``score`` and a ``datatypeScores`` breakdown.

The one socket-opening function takes ``transport`` as a PARAMETER so tests serve pinned
bytes and never touch the network. The parser refuses target mis-attribution and fails
closed on a drifted data version. OT's aggregated scores are carried as descriptive,
upstream-reported evidence only — the caller never gates or ranks on them.
"""
from __future__ import annotations

import hashlib
import json
import urllib.request
from typing import Any, Callable

from . import GbmContextError

OT_ENDPOINT = "https://api.platform.opentargets.org/api/v4/graphql"
OT_LICENSE = "CC0 1.0"
OT_LICENSE_URL = "https://platform-docs.opentargets.org/licence"
OT_DATA_VERSION_EXPECTED = "26.06"
OT_VERIFIED_ON = "2026-07-13"

GLIOBLASTOMA_ID = "MONDO_0018177"
GLIOMA_ID = "MONDO_0021042"
# Verified live; a fixture/caller may not rename these.
GBM_GLIOMA_DISEASES = {GLIOBLASTOMA_ID: "glioblastoma", GLIOMA_ID: "glioma"}

QUERY = """query GbmDiseaseAssoc($ensemblId: String!, $diseaseIds: [String!]) {
  meta { dataVersion { year month } apiVersion { x y z } }
  target(ensemblId: $ensemblId) {
    id
    approvedSymbol
    associatedDiseases(Bs: $diseaseIds) {
      count
      rows { score disease { id name } datatypeScores { id score } }
    }
  }
}"""

# transport(url, data_bytes, headers) -> (http_status:int, raw_bytes:bytes)
Transport = Callable[[str, bytes, dict[str, str]], tuple[int, bytes]]


def build_request_payload(ensembl_id: str) -> dict[str, Any]:
    return {"query": QUERY,
            "variables": {"ensemblId": ensembl_id,
                          "diseaseIds": list(GBM_GLIOMA_DISEASES)}}


def data_version_of(obj: dict[str, Any]) -> str:
    dv = obj["data"]["meta"]["dataVersion"]
    return f'{dv["year"]}.{dv["month"]}'


def api_version_of(obj: dict[str, Any]) -> Optional[str]:
    av = (obj.get("data") or {}).get("meta", {}).get("apiVersion") or {}
    if not av:
        return None
    return f'{av.get("x")}.{av.get("y")}.{av.get("z")}'


def verify_data_version(obj: dict[str, Any]) -> str:
    got = data_version_of(obj)
    if got != OT_DATA_VERSION_EXPECTED:
        raise GbmContextError(
            f"Open Targets data version drifted: got {got!r}, pinned "
            f"{OT_DATA_VERSION_EXPECTED!r}. Re-pin and re-verify before trusting bytes.")
    return got


def parse_association(obj: dict[str, Any], ensembl_id: str) -> dict[str, Any]:
    """Pure parse of one target's GBM/glioma association rows. Refuses a target whose id
    does not match the request (never a silent mis-attribution). Absent target -> evaluated
    with no association (honest), never invented."""
    data = obj.get("data") or {}
    version = data_version_of(obj)
    target = data.get("target")
    if target is None:
        return {"evaluated": True, "data_version": version,
                "api_version": api_version_of(obj), "diseases": {}}
    if target.get("id") not in (None, ensembl_id):
        raise GbmContextError(
            f"OT response is for target {target.get('id')!r}, not requested "
            f"{ensembl_id!r} — refusing to mis-attribute.")
    rows = ((target.get("associatedDiseases") or {}).get("rows")) or []
    diseases: dict[str, Any] = {}
    for row in rows:
        d = row.get("disease") or {}
        mondo = d.get("id")
        if mondo not in GBM_GLIOMA_DISEASES:
            continue
        diseases[mondo] = {
            "name": d.get("name"),
            "reported_overall_association_score": row.get("score"),
            "datatype_evidence": {s["id"]: s["score"]
                                  for s in (row.get("datatypeScores") or [])}}
    return {"evaluated": True, "data_version": version,
            "api_version": api_version_of(obj),
            "approved_symbol": target.get("approvedSymbol"), "diseases": diseases}


def default_transport(url: str, data: bytes, headers: dict[str, str]) -> tuple[int, bytes]:
    req = urllib.request.Request(url, data=data, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as e:  # type: ignore[attr-defined]
        return e.code, e.read()


def fetch_gene(ensembl_id: str, *, transport: Transport) -> dict[str, Any]:
    """Acquire one gene's GBM/glioma association through ``transport`` and record
    provenance (endpoint, http status, raw byte hash, data version). A non-200 is
    ``not_evaluated`` with the status recorded — never invented. A GraphQL ``errors``
    payload is refused."""
    body = json.dumps(build_request_payload(ensembl_id)).encode()
    status, raw = transport(OT_ENDPOINT, body,
                            {"Content-Type": "application/json",
                             "User-Agent": "spot-stage3-gbm-context (research; CC0 public API)"})
    if status != 200:
        return {"evaluated": False, "reason": f"http_{status}", "http_status": status,
                "endpoint": OT_ENDPOINT, "diseases": {}}
    obj = json.loads(raw)
    if obj.get("errors"):
        raise GbmContextError(f"Open Targets returned GraphQL errors: {obj['errors']!r}")
    verify_data_version(obj)
    result = parse_association(obj, ensembl_id)
    result["endpoint"] = OT_ENDPOINT
    result["http_status"] = status
    result["raw_sha256"] = hashlib.sha256(raw).hexdigest()
    result["license"] = OT_LICENSE
    result["raw_response_text"] = raw.decode("utf-8")
    return result
