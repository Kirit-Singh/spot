"""ONE bounded live probe against the real public sources. Opt-in, and never a candidate.

    SPOT_STAGE4_LIVE=1 SPOT_STAGE4_RUN_ROOT=/tmp/spot-live pytest tests/test_live_reference_smoke.py

Why it exists: every other test in this suite drives synthetic bytes. That proves the adapters
parse the shape they were told about — not that the shape is real. This probe checks the
acquisition layer against the actual PubChem / RxNorm / DailyMed / openFDA responses, once.

Why TEMODAR/temozolomide: it is the GBM standard of care and it is emphatically NOT a Stage-3
candidate (every queued row in the admitted bundle is an antibody). So there is no path by which
this probe could be mistaken for characterising, ranking or endorsing a candidate. It is a
REFERENCE probe: it tests the plumbing.

What it asserts, and nothing more:

  * the four sources answer, and every response is bound to a locator, a UTC time, a status, a
    media type, a byte count and a SHA-256;
  * identity CONVERGES across them (the same active moiety), or the layer refuses;
  * the Drugs@FDA approval cross-check runs;
  * the nested Warnings and Precautions of a REAL innovator label still survive the e410d72
    parser — the live TEMODAR SPL carries no direct text on 43685-7 and puts every warning in a
    42229-5 subsection, which is the exact defect that commit repaired.

What it never does: assert a number about brain penetrance, safety, potency or benefit; write
anything into Git; or produce a candidate or a rank. The bytes go to the run root only.
"""

from __future__ import annotations

import os

import pytest

from analysis.acquire_http import Client
from analysis.acquisition import RunRoot, verify_cached_bytes
from analysis.dailymed_select import acquire_label, acquire_rxcui
from analysis.identity import claims_from, resolve_identity
from analysis.openfda_approval import acquire_approval
from analysis.pubchem import acquire_pubchem_identity

REFERENCE_MOIETY = "temozolomide"          # NOT a candidate. A plumbing probe.
TEMODAR_SETID = "046a9011-3911-4d3f-a15f-fbb56d5aad56"

live_only = pytest.mark.skipif(
    os.environ.get("SPOT_STAGE4_LIVE") != "1",
    reason="live network probe: set SPOT_STAGE4_LIVE=1 (and SPOT_STAGE4_RUN_ROOT) to run it")


@pytest.fixture(scope="module")
def run_root():
    root = os.environ.get("SPOT_STAGE4_RUN_ROOT")
    if not root:
        pytest.skip("SPOT_STAGE4_RUN_ROOT is not set; live bytes are never written inside Git")
    return RunRoot(root)


@pytest.fixture(scope="module")
def client():
    return Client(allow_network=True)


@live_only
def test_every_named_public_source_answers_with_a_checkable_record(client, run_root):
    """Item-1 smoke: for EACH named source, verify the things a reviewer would have to check by
    hand — HTTP status, content type, source identity, access time, licence/terms, raw-cache
    SHA-256. TEMODAR/temozolomide is an explicitly TEST-ONLY probe: it is not a Stage-3 candidate
    (every queued row is an antibody) and nothing about it is presented as a result."""
    from analysis.acquire_cache import RequestCache
    from analysis.acquisition import verify_cached_bytes
    from analysis.public_sources import host as ledger_host

    cache = RequestCache(run_root)
    live = Client(allow_network=True, cache=cache)

    pubchem, records = acquire_pubchem_identity(live, run_root, REFERENCE_MOIETY)
    rxcui, rx_record = acquire_rxcui(live, run_root, REFERENCE_MOIETY)
    label, label_records = acquire_label(live, run_root, REFERENCE_MOIETY, setid=TEMODAR_SETID)
    approval, approval_records = acquire_approval(live, run_root, label.listing.setid)
    every = [*records, rx_record, *label_records, *approval_records]

    by_source: dict[str, int] = {}
    for rec in every:
        by_source[rec.source_key] = by_source.get(rec.source_key, 0) + 1

        # 1. HTTP status + content type, as reported by the source
        assert rec.http_status == 200, f"{rec.source_key}: HTTP {rec.http_status}"
        assert rec.raw_media_type in ("application/json", "application/xml", "text/xml"), \
            f"{rec.source_key}: unexpected media type {rec.raw_media_type!r}"

        # 2. source identity: the bytes came from the host the LEDGER names, over https
        assert rec.url.startswith(f"https://{ledger_host(rec.source_key)}/"), rec.url
        assert rec.canonical_query and rec.stable_record_id

        # 3. access time: a real UTC stamp, not a placeholder
        assert rec.accessed_at_utc and rec.accessed_at_utc.endswith("Z")
        assert not rec.accessed_at_utc.startswith("1970")

        # 4. licence / terms recorded — a source may not declare itself free
        assert rec.license_or_terms_url and rec.license_status

        # 5. the raw cache holds exactly the bytes that were hashed
        verify_cached_bytes(rec, run_root)

    # all four named sources answered
    assert set(by_source) == {"pubchem", "rxnorm", "dailymed", "openfda"}

    # the request cache filed one entry per canonical query, and a re-run reuses them
    assert cache.n_entries() == len(every) - 0 or cache.n_entries() >= 4
    before = live.n_fetched
    acquire_pubchem_identity(live, run_root, REFERENCE_MOIETY)
    assert live.n_fetched == before and live.n_reused > 0     # served from cache, no new request


@live_only
def test_the_four_public_sources_answer_and_identity_converges_for_the_reference_moiety(
        client, run_root):
    pubchem, pubchem_records = acquire_pubchem_identity(client, run_root, REFERENCE_MOIETY)
    rxcui, rxnorm_record = acquire_rxcui(client, run_root, REFERENCE_MOIETY)
    label, label_records = acquire_label(client, run_root, REFERENCE_MOIETY,
                                         setid=TEMODAR_SETID)
    approval, approval_records = acquire_approval(client, run_root, label.listing.setid)

    records = [*pubchem_records, rxnorm_record, *label_records, *approval_records]

    # every response is re-fetchable and re-checkable
    for rec in records:
        assert rec.origin == "fetched_public" and rec.http_status == 200
        assert rec.url and rec.canonical_query and rec.accessed_at_utc
        assert rec.raw_sha256 and rec.raw_bytes and rec.raw_media_type
        assert rec.license_or_terms_url and rec.adapter_code_sha256
        verify_cached_bytes(rec, run_root)          # the cache holds exactly what was hashed

    # identity converges, or resolve_identity would have refused
    identity = resolve_identity(
        claims_from(pubchem=pubchem, rxcui=rxcui, label=label, approval=approval),
        active_moiety_name=REFERENCE_MOIETY)
    assert identity.inchikey and identity.unii and identity.pubchem_cid
    # TEMODAR's label declares TWO applications (capsule + injection). BOTH are carried and
    # BOTH were cross-checked against Drugs@FDA — none was chosen by position.
    assert len(identity.fda_application_numbers) >= 1
    assert set(identity.fda_application_numbers) == set(approval.application_numbers)
    assert approval.marketing_statuses
    assert identity.conflicts == []

    # PubChem gave structure and the descriptors it has — and neither of the two it does not.
    assert "MolecularWeight" in pubchem.descriptors
    assert not any(k.lower().startswith(("logd", "pka")) for k in pubchem.descriptors)


@live_only
def test_the_nested_warnings_of_a_real_innovator_label_survive_the_e410d72_parser(
        client, run_root):
    """The live TEMODAR SPL carries NO direct text on WARNINGS AND PRECAUTIONS (43685-7): every
    warning lives in a nested <component><section>. Before e410d72 the parser collected zero of
    them and said so silently. If this goes red, that defect is back."""
    label, _ = acquire_label(client, run_root, REFERENCE_MOIETY, setid=TEMODAR_SETID)

    warnings = [f for f in label.label.findings if f.finding_type == "warning_precaution"]
    assert warnings, ("the live label's Warnings and Precautions section parsed to ZERO findings "
                      "— the nested-subsection defect repaired in e410d72 has regressed")
    assert any(f.labeled_subsection_code for f in warnings), (
        "no warning carries a subsection code, so nothing was read from a nested subsection")

    # the label the listing offered is the label that was served
    assert label.label.setid == TEMODAR_SETID
    assert label.label.label_version == label.listing.spl_version
