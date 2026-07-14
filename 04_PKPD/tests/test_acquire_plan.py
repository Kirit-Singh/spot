"""The plan: can the real candidate queue be acquired the moment it is admitted?

Offline, no network, no admission change. The plan proves READINESS — it does not create it, and
it must never overstate it:

  * every URL is built by the SAME code that fetches, so plan and request cannot drift;
  * every identifier is validated against the format its source actually issues;
  * ChEMBL/UniProt are counted as REUSED, never planned as fetches;
  * a lane with no adapter (potency, exposure, transporters, PK literature) is planned as
    `not_evaluated` WITH A REASON — never as work that could be done.
"""

from __future__ import annotations

import pytest

from _stage3_forge import PINNED_BUNDLE
from analysis.acquire_http import Client
from analysis.acquire_plan import (
    UNREACHABLE_LANES,
    plan_document,
    plan_queue,
    validate_identifier,
    validate_url,
)
from analysis.firewall import Rejection
from analysis.stage3_admission import admit


@pytest.fixture(scope="module")
def plans():
    admission = admit(PINNED_BUNDLE)          # gate 1; admission is NOT loosened anywhere here
    return plan_queue(Client(), admission.tables)      # a client with NO network permission


def test_the_plan_covers_every_queued_candidate_and_no_others(plans):
    assert len(plans) == 7                    # the seven rows Stage 3 queued
    assert all(p.candidate_id.startswith("AM:CHEMBL:") for p in plans)


def test_every_queued_candidate_is_acquirable_the_moment_the_bundle_is_admitted(plans):
    """This is the readiness claim, and it is the whole point of the exercise."""
    assert all(p.acquirable for p in plans), [p.refusals for p in plans if not p.acquirable]
    assert all(p.moiety_name for p in plans)


def test_the_plan_makes_no_request_it_does_not_have_permission_for(plans):
    """The plan is built with a Client that has NO network permission. If planning could fetch,
    this suite would have hit the real internet."""
    for plan in plans:
        for request in plan.requests:
            assert request.url.startswith("https://")


def test_every_planned_url_is_on_a_ledgered_host(plans):
    hosts = set()
    for plan in plans:
        for request in plan.requests:
            validate_url(request.source_key, request.url)     # raises if off-host
            hosts.add(request.url.split("/")[2])
    assert hosts == {
        "pubchem.ncbi.nlm.nih.gov", "rxnav.nlm.nih.gov",
        "dailymed.nlm.nih.gov", "api.fda.gov",
    }


def test_chembl_and_uniprot_are_counted_as_reused_never_planned_as_fetches(plans):
    planned_sources = {r.source_key for p in plans for r in p.requests}
    assert "chembl" not in planned_sources and "uniprot" not in planned_sources

    # ...and they ARE present as reusable Stage-3 records, or the reuse claim would be empty talk
    reused = {k for p in plans for k in p.reusable_source_records}
    assert "chembl" in reused


def test_the_dependent_requests_declare_what_they_wait_for(plans):
    """The SPL cannot be fetched until DailyMed selection yields a set ID; Drugs@FDA cannot be
    queried until the label yields an application number. The plan says so."""
    deps = {r.depends_on for p in plans for r in p.requests if r.depends_on}
    assert deps == {"pubchem_cid", "dailymed_setid", "fda_application_number"}


def test_lanes_with_no_adapter_are_planned_as_not_evaluated_with_a_reason(plans):
    for plan in plans:
        assert set(plan.unreachable) == set(UNREACHABLE_LANES)
        for lane, reason in plan.unreachable.items():
            assert len(reason) > 30, f"{lane} has no real reason"

    doc = plan_document(plans)
    assert "potency_mec" in doc["candidates"][0]["lanes_not_evaluated"]
    # a plan never promises a lane no code can fill
    planned_lanes = {r["lane"] for c in doc["candidates"] for r in c["requests"]}
    assert planned_lanes.isdisjoint(set(UNREACHABLE_LANES))


def test_the_plan_document_is_a_readiness_statement_not_a_result(plans):
    doc = plan_document(plans)
    assert doc["n_candidates_queued"] == 7
    assert doc["n_acquirable"] == 7
    assert doc["n_requests_total"] == 7 * 7        # seven requests per candidate
    assert "ranks nothing" in " ".join(doc["hard_rules"])

    fields = set()

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                fields.add(k)
                walk(v)
        elif isinstance(node, list):
            for i in node:
                walk(i)

    walk(doc)
    for banned in ("rank", "score", "recommendation", "priority"):
        assert not any(banned in f for f in fields)


# ------------------------------------------------------------------ identifier validation


@pytest.mark.parametrize("kind,value", [
    ("chembl_id", "CHEMBL1789844"),
    ("uniprot_accession", "P10747"),
    ("pubchem_cid", "5394"),
    ("rxcui", "37776"),
    ("inchikey", "BPEGJWRSRHCHSN-UHFFFAOYSA-N"),
    ("dailymed_setid", "046a9011-3911-4d3f-a15f-fbb56d5aad56"),
    ("fda_application_number", "NDA021029"),
    ("unii", "YF1K15M17Y"),
])
def test_a_well_formed_identifier_passes(kind, value):
    assert validate_identifier(kind, value) == value


@pytest.mark.parametrize("kind,value", [
    ("chembl_id", "CHEMBL"),                       # no number
    ("chembl_id", "1789844"),                      # no prefix
    ("uniprot_accession", "NOTANACC"),
    ("pubchem_cid", "5394a"),
    ("inchikey", "BPEGJWRSRHCHSN-UHFFFAOYSA"),     # two blocks, not three
    ("dailymed_setid", "046a9011-3911-4d3f-a15f"),  # truncated UUID
    ("fda_application_number", "NDA21029"),        # five digits
    ("unii", "TOOSHORT"),
])
def test_a_malformed_identifier_is_refused_at_plan_time_not_sent_to_a_public_api(kind, value):
    with pytest.raises(Rejection) as exc:
        validate_identifier(kind, value)
    assert exc.value.code == "malformed_identifier"


def test_a_url_off_the_ledgered_host_is_refused():
    with pytest.raises(Rejection) as exc:
        validate_url("pubchem", "https://evil.example.com/rest/pug/compound/name/x/cids/JSON")
    assert exc.value.code == "host_not_in_ledger"


def test_an_http_url_is_refused_even_on_the_right_host():
    with pytest.raises(Rejection) as exc:
        validate_url("pubchem", "http://pubchem.ncbi.nlm.nih.gov/rest/pug/x")
    assert exc.value.code == "insecure_source_url"
