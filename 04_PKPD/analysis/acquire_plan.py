"""The acquisition PLAN: what would be fetched for a real candidate queue, and can it be?

The purpose is to be ready, not to be optimistic. When the admitted Stage-3 bundle lands, the
queue must be acquirable immediately — so this walks the queue NOW, offline, and answers:

  * which lane can be filled for each queued candidate, and from which named source;
  * the exact canonical URL that would be requested, built by the SAME code that fetches, so it is
    correct by construction rather than by a duplicated string a reviewer must eyeball;
  * every identifier validated against its source's own format;
  * every lane that CANNOT be filled, stated as `not_evaluated` with a reason — never left blank.

It performs NO network access and it does NOT admit anything. Admission stays exactly where it is
(`stage3_admission.admit`, both gates); a plan over an unadmitted bundle is a refusal, because
planning against bytes nobody verified is how an unverified bundle sneaks into a run.

**No lane is invented.** There is no potency, exposure, transporter or primary-literature adapter,
so those lanes plan as `not_evaluated` with the reason spelled out. A plan that promised them would
be a schedule for evidence that no code can produce.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

from .acquire_http import Client
from .dailymed_select import DAILYMED, PAGE_SIZE, RXNORM
from .firewall import Rejection
from .openfda_approval import QUERY_LIMIT
from .openfda_approval import SOURCE_KEY as OPENFDA
from .public_sources import FETCH_REUSE_ONLY, ledger
from .pubchem import PROPERTIES
from .pubchem import SOURCE_KEY as PUBCHEM

# Each identifier is checked against the format ITS SOURCE actually issues. A malformed id is a
# refusal at plan time — cheap — rather than a 404 in the middle of a live queue.
ID_FORMATS: dict[str, re.Pattern[str]] = {
    "chembl_id": re.compile(r"^CHEMBL\d+$"),
    "uniprot_accession": re.compile(
        r"^([OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2})$"),
    "pubchem_cid": re.compile(r"^\d+$"),
    "rxcui": re.compile(r"^\d+$"),
    "inchikey": re.compile(r"^[A-Z]{14}-[A-Z]{10}-[A-Z]$"),
    "dailymed_setid": re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I),
    "fda_application_number": re.compile(r"^(NDA|ANDA|BLA)\d{6}$"),
    "unii": re.compile(r"^[A-Z0-9]{10}$"),
}

# Lanes with no adapter. Named so the absence is a statement, not a silence.
UNREACHABLE_LANES = {
    "potency_mec": "no ChEMBL activity/assay adapter exists. Stage 3's ChEMBL records are curated "
                   "mechanism/target evidence, not a potency acquisition. A potency lane needs the "
                   "structured activity/assay/document fields the source audit lists (§4.2/§4.4).",
    "systemic_exposure": "no clinical-PK adapter exists, and the exposure schema is not yet "
                         "acquisition-complete (no structured PK metric/statistic/fu inputs).",
    "brain_csf_exposure": "no adapter. Human non-enhancing-brain exposure lives in heterogeneous "
                          "primary literature, not in any structured public API in the ledger.",
    "transporters": "no adapter. ABCB1/ABCG2 observations are not carried by any ledgered source.",
    "primary_pk_literature": "no acquisition/review workflow. A deterministic search manifest, a "
                             "content-addressed document cache and a dual extraction/review step "
                             "are all still required.",
}


@dataclass(frozen=True)
class PlannedRequest:
    """One request that WOULD be made. The URL is built by the fetching code, not re-typed."""

    lane: str
    source_key: str
    canonical_query: str
    url: str
    depends_on: Optional[str] = None   # an id that only exists after an earlier step


@dataclass
class CandidatePlan:
    candidate_id: str
    active_moiety_id: str
    moiety_name: Optional[str]
    reusable_source_records: dict[str, int] = field(default_factory=dict)
    requests: list[PlannedRequest] = field(default_factory=list)
    unreachable: dict[str, str] = field(default_factory=dict)
    refusals: list[str] = field(default_factory=list)

    @property
    def acquirable(self) -> bool:
        return not self.refusals and bool(self.requests)


def validate_identifier(kind: str, value: str) -> str:
    """A malformed identifier is refused at plan time, not discovered as a 404 mid-queue."""
    pattern = ID_FORMATS.get(kind)
    if pattern is None:
        raise Rejection("unknown_identifier_kind",
                        f"{kind!r} is not an identifier Stage 4 knows how to validate")
    text = str(value).strip()
    if not pattern.match(text):
        raise Rejection(
            "malformed_identifier",
            f"{kind}={value!r} does not match the format its source issues ({pattern.pattern}). "
            "Stage 4 refuses it here rather than sending it to a public API and reading whatever "
            "comes back.")
    return text


def validate_url(source_key: str, url: str) -> str:
    """The URL must be https and on the host the ledger names for that source."""
    entry = ledger()["sources"].get(source_key)
    if entry is None:
        raise Rejection("unknown_source", f"{source_key!r} is not in the public-source ledger")
    expected = str(entry.get("host") or "")
    if not url.startswith("https://"):
        raise Rejection("insecure_source_url", f"{url!r} is not https")
    if not url.startswith(f"https://{expected}/"):
        raise Rejection(
            "host_not_in_ledger",
            f"the planned URL {url!r} is not on {expected!r}, the host the ledger records for "
            f"{source_key!r}.")
    return url


def _planned(client: Client, lane: str, source_key: str, path: str,
             params: Optional[dict[str, str]] = None,
             depends_on: Optional[str] = None) -> PlannedRequest:
    """Build the request THE FETCHER would build. Same code, so the plan cannot drift from it."""
    entry = ledger()["sources"][source_key]
    query = client.canonical_query(path, params)
    url = f"{str(entry['base_url']).rstrip('/')}/{query}"
    return PlannedRequest(lane=lane, source_key=source_key, canonical_query=query,
                          url=validate_url(source_key, url), depends_on=depends_on)


def plan_candidate(client: Client, candidate: dict[str, Any], moiety: dict[str, Any],
                   source_records: list[dict[str, Any]]) -> CandidatePlan:
    """Everything that would be acquired for ONE queued candidate. No network, no admission."""
    name = (moiety.get("preferred_name") or "").strip()
    plan = CandidatePlan(
        candidate_id=str(candidate["candidate_id"]),
        active_moiety_id=str(candidate["active_moiety_id"]),
        moiety_name=name or None,
    )

    # --- what Stage 3 already acquired: REUSED, never re-queried ----------------------
    ids = set(candidate.get("source_record_ids") or [])
    for row in source_records:
        if row.get("source_record_id") not in ids:
            continue
        source_key = str(row.get("source") or "unknown")
        if str(row.get("acquisition_status")) != "acquired_public":
            continue
        entry = ledger()["sources"].get(source_key) or {}
        if entry.get("fetch") == FETCH_REUSE_ONLY:
            plan.reusable_source_records[source_key] = (
                plan.reusable_source_records.get(source_key, 0) + 1)

    # --- identity: the only lane a public API can actually fill ------------------------
    if not name:
        plan.refusals.append(
            f"candidate {plan.candidate_id!r} has no preferred_name on its active moiety, so no "
            "public source can be queried for it by name. Stage 4 does not guess a drug name.")
    else:
        plan.requests.append(_planned(client, "identity", PUBCHEM,
                                      f"compound/name/{name}/cids/JSON"))
        plan.requests.append(_planned(
            client, "identity", PUBCHEM,
            f"compound/cid/{{cid}}/property/{','.join(PROPERTIES)}/JSON", depends_on="pubchem_cid"))
        plan.requests.append(_planned(client, "identity_crosswalk", RXNORM, "rxcui.json",
                                      {"name": name, "search": "0"}))
        plan.requests.append(_planned(client, "label", DAILYMED, "spls.json",
                                      {"drug_name": name, "pagesize": PAGE_SIZE}))
        plan.requests.append(_planned(client, "label", DAILYMED, "spls/{setid}.xml",
                                      depends_on="dailymed_setid"))
        plan.requests.append(_planned(
            client, "approval", OPENFDA, "drug/label.json",
            {"search": 'openfda.spl_set_id:"{setid}"', "limit": QUERY_LIMIT},
            depends_on="dailymed_setid"))
        plan.requests.append(_planned(
            client, "approval", OPENFDA, "drug/drugsfda.json",
            {"search": 'openfda.application_number:"{application_number}"', "limit": QUERY_LIMIT},
            depends_on="fda_application_number"))

    # --- validate whatever identifiers Stage 3 already gave us -------------------------
    for kind, value in (("chembl_id", moiety.get("moiety_chembl_id")),
                        ("inchikey", moiety.get("moiety_inchikey")),
                        ("unii", moiety.get("moiety_unii"))):
        if value:
            try:
                validate_identifier(kind, str(value))
            except Rejection as exc:
                plan.refusals.append(f"{plan.candidate_id}: {exc.detail}")

    # --- and every lane no adapter can reach -------------------------------------------
    plan.unreachable = dict(UNREACHABLE_LANES)
    return plan


def plan_queue(client: Client, tables: dict[str, list[dict[str, Any]]]) -> list[CandidatePlan]:
    """The whole queued candidate set, in candidate order. Offline."""
    moieties = {m["active_moiety_id"]: m for m in tables["active_moieties"]}
    sources = tables["source_records"]
    queued = [c for c in tables["candidates"] if c.get("stage4_assessment_status") == "queued"]

    plans = []
    for candidate in sorted(queued, key=lambda c: str(c["candidate_id"])):
        moiety = moieties.get(candidate["active_moiety_id"], {})
        plans.append(plan_candidate(client, candidate, moiety, sources))
    return plans


def plan_document(plans: list[CandidatePlan]) -> dict[str, Any]:
    """The plan, as a receipt. It is a readiness statement, not a result."""
    return {
        "schema_id": "spot.stage04_acquisition_plan.v1",
        "n_candidates_queued": len(plans),
        "n_acquirable": sum(1 for p in plans if p.acquirable),
        "n_requests_total": sum(len(p.requests) for p in plans),
        "candidates": [
            {
                "candidate_id": p.candidate_id,
                "active_moiety_id": p.active_moiety_id,
                "moiety_name": p.moiety_name,
                "acquirable": p.acquirable,
                "reused_from_stage3": dict(sorted(p.reusable_source_records.items())),
                "requests": [
                    {"lane": r.lane, "source_key": r.source_key, "url": r.url,
                     "canonical_query": r.canonical_query, "depends_on": r.depends_on}
                    for r in p.requests
                ],
                "lanes_not_evaluated": p.unreachable,
                "refusals": p.refusals,
            }
            for p in plans
        ],
        "hard_rules": [
            "A plan is a readiness statement. It acquires nothing, admits nothing, and ranks "
            "nothing.",
            "Every URL here is built by the same code that fetches, so the plan cannot drift from "
            "the request.",
            "ChEMBL/UniProt are reuse_only: they are counted, never planned as fetches.",
            "A lane with no adapter is stated not_evaluated with a reason; it is never planned as "
            "if it could be filled.",
        ],
    }
