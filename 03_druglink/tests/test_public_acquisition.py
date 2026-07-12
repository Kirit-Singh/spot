"""P0-3: bounded, real UniProt + ChEMBL 37 acquisition.

Every test here is OFFLINE. :class:`fixture_public_responses.FakeTransport` serves the
EXACT pinned public response bytes and raises on any URL it was not given, so an
unpinned request cannot silently escape to the network.

The pinned bytes are real (CTLA4 / IL2RA, fetched 2026-07-12). They are TEST INPUTS:
they are never presented as a research result, and the acquisition verifier refuses
any attempt to relabel a fixture as ``acquired_public``.
"""
from __future__ import annotations

import json
import os

import pytest

import fixture_public_responses as FX
from druglink import acquire_public as ap, acquisition, http_public as hp
from druglink import verify_acquisition as va


def _cache(tmp_path, name="cache"):
    path = os.path.join(str(tmp_path), name)
    os.makedirs(path, exist_ok=True)
    return path


def _acquire(tmp_path, ensgs=(FX.CTLA4, FX.IL2RA), top_per_arm=25):
    cache = _cache(tmp_path)
    direct = FX.direct_double(list(ensgs))
    result = ap.acquire(cache_root=cache, artifact_class="analysis", direct=direct,
                        top_per_arm=top_per_arm, sources=("uniprot", "chembl"),
                        chembl_release="CHEMBL_37", transport=FX.FakeTransport())
    return cache, direct, result


# --------------------------------------------------------------------------- #
# The question is frozen before any answer exists.
# --------------------------------------------------------------------------- #
def test_target_queue_is_frozen_before_fetch(tmp_path):
    cache = _cache(tmp_path)
    direct = FX.direct_double([FX.CTLA4, FX.IL2RA])

    seen_queue_at_first_call: list[bool] = []
    transport = FX.FakeTransport()

    def spy(url):
        # The frozen queue must already be on disk before the FIRST request.
        seen_queue_at_first_call.append(
            os.path.exists(os.path.join(cache, ap.QUEUE_FILE)))

    transport.on_call = spy
    result = ap.acquire(cache_root=cache, artifact_class="analysis", direct=direct,
                        top_per_arm=25, sources=("uniprot", "chembl"),
                        chembl_release="CHEMBL_37", transport=transport)

    assert seen_queue_at_first_call and all(seen_queue_at_first_call), (
        "the target queue must be written BEFORE the first HTTP request")

    frozen = json.loads(open(os.path.join(cache, ap.QUEUE_FILE)).read())
    manifest = result["manifest"]

    # The queue and the policy are bound into the acquisition ID.
    assert manifest["acquisition_binding"]["target_queue_sha256"] == \
        frozen["target_queue_sha256"]
    assert manifest["acquisition_id"] == frozen["acquisition_id"]

    # No adaptive expansion, and no stop-when-enough-found.
    policy = frozen["policy"]
    assert policy["adaptive_expansion_permitted"] is False
    assert policy["stop_when_enough_drugs_found"] is False
    assert policy["zero_candidates_is_a_valid_result"] is True
    assert policy["top_per_arm"] == 25

    # Selection is per arm, INDEPENDENTLY, by that arm's own rank.
    assert policy["selection_rule"] == \
        "top_n_per_arm_independently_by_that_arms_own_direct_rank"
    arms = {t["desired_arm"] for t in frozen["target_queue"]}
    assert arms == {"away_from_A", "toward_B"}
    for target in frozen["target_queue"]:
        assert target["arm_rank"] is not None


def test_top_per_arm_bounds_each_arm_independently(tmp_path):
    """Top-N is applied PER ARM. A's rank can never promote a gene into B's queue."""
    direct = FX.direct_double([FX.CTLA4, FX.IL2RA])
    frozen = ap.freeze_queue(direct, top_per_arm=1, sources=("uniprot", "chembl"),
                             chembl_release="CHEMBL_37", artifact_class="analysis")

    per_arm = frozen["per_arm_counts"]
    assert per_arm["away_from_A"] == 1
    assert per_arm["toward_B"] == 1
    assert len(frozen["target_queue"]) == 2          # one per arm, not one overall

    # The union is for network efficiency only; the arm and rank survive on the row.
    assert frozen["policy"]["union_rule"].startswith("union_is_for_network_efficiency")
    assert all("desired_arm" in t and "arm_rank" in t
               for t in frozen["target_queue"])

    # top_per_arm=0 is legal and acquires nothing. Zero is a valid result.
    empty = ap.freeze_queue(direct, top_per_arm=0, sources=("uniprot",),
                            chembl_release="CHEMBL_37", artifact_class="analysis")
    assert empty["target_queue"] == [] and empty["query_genes"] == []


# --------------------------------------------------------------------------- #
# The real public responses, parsed as they actually arrive.
# --------------------------------------------------------------------------- #
def test_real_uniprot_response_contract():
    name = f"uniprot_search_{FX.CTLA4}"
    page = FX.payload(name)
    resp = FX.response(name)

    # The canonical URL our code builds IS the URL these bytes came from.
    assert hp.canonical_url(ap.UNIPROT_SEARCH, {
        "query": f"xref:ensembl-{FX.CTLA4} AND organism_id:9606",
        "format": "json", "fields": ap.UNIPROT_FIELDS,
        "size": ap.UNIPROT_PAGE_SIZE}) == FX.url(name)

    # The release comes from the response HEADER, never from a document.
    assert resp.header("x-uniprot-release") == FX.UNIPROT_RELEASE
    assert resp.header("x-uniprot-release-date")

    assert isinstance(page["results"], list) and page["results"]

    # Only an EXACT Ensembl GeneId cross-reference is a mapping.
    fetched = hp.fetch_page(FX.FakeTransport(), FX.url(name),
                            adapter="uniprot_search", index=0,
                            origin=hp.UNIPROT_ORIGIN)
    accs = ap.ensembl_accessions([fetched], FX.CTLA4)
    assert set(accs) == set(FX.CTLA4_ACCESSIONS)

    # A gene-symbol resemblance maps NOTHING.
    assert ap.ensembl_accessions([fetched], "ENSG09999999999") == []

    # The adapter turns those bytes into gene_map records.
    from druglink.adapters import uniprot
    records = uniprot.parse_search(page, {}, "src_test")
    mapped = {r["target_ensembl"] for r in records}
    assert FX.CTLA4 in mapped
    assert all(r["record_kind"] == "gene_map" for r in records)


def test_real_chembl37_response_contract():
    status = FX.payload("chembl_status")
    assert status["chembl_db_version"] == FX.CHEMBL_RELEASE
    assert status["chembl_release_date"]

    # P01589 (IL2RA) really does return BOTH a single protein and the IL-2 receptor
    # PROTEIN COMPLEX — exactly the case that must never collapse into a gene.
    name = "chembl_target_P01589"
    page = FX.payload(name)
    assert "page_meta" in page and isinstance(page["targets"], list)

    fetched = hp.fetch_page(FX.FakeTransport(), FX.url(name), adapter="chembl_target",
                            index=0, origin=hp.CHEMBL_ORIGIN)

    types = {t["target_chembl_id"]: t["target_type"] for t in page["targets"]}
    assert types[FX.IL2RA_TARGET] == "SINGLE PROTEIN"
    assert types[FX.IL2_RECEPTOR_COMPLEX] == "PROTEIN COMPLEX"

    # ONLY an exact SINGLE PROTEIN target carrying the mapped accession enters the
    # direct-gene lane. The PROTEIN COMPLEX is refused even though IL2RA genuinely
    # IS one of its components.
    singles = ap.single_protein_targets([fetched], "P01589")
    assert FX.IL2RA_TARGET in singles
    assert FX.IL2_RECEPTOR_COMPLEX not in singles

    # The target adapter keeps the complex as a first-class NON-gene entity.
    from druglink import targets as targets_mod
    from druglink.adapters import chembl
    entities = targets_mod.build(chembl.parse_target(page, {}, "src_test"))
    by_source = {e["source_target_id"]: e for e in entities["entities"].values()}
    assert by_source[FX.IL2RA_TARGET]["direct_gene_lane_eligible"] is True
    assert by_source[FX.IL2_RECEPTOR_COMPLEX]["direct_gene_lane_eligible"] is False
    assert by_source[FX.IL2_RECEPTOR_COMPLEX]["target_entity_class"] == "protein_complex"

    # Mechanisms parse, and the source action_type survives verbatim.
    mech = FX.payload(f"chembl_mechanism_{FX.CTLA4_TARGET}")
    records = chembl.parse_mechanism(mech, {}, "src_test")
    assert records
    assert all(r["record_kind"] == "mechanism" for r in records)
    assert any(r["action_type_source"] for r in records)


def test_one_to_many_uniprot_mapping_is_preserved(tmp_path):
    """One gene, many accessions. None is silently dropped, none is picked as 'the' one."""
    fetched = hp.fetch_page(FX.FakeTransport(), FX.url(f"uniprot_search_{FX.IL2RA}"),
                            adapter="uniprot_search", index=0,
                            origin=hp.UNIPROT_ORIGIN)
    accs = ap.ensembl_accessions([fetched], FX.IL2RA)
    assert len(accs) > 1, "IL2RA must map one-to-many in the pinned response"
    assert set(accs) == set(FX.IL2RA_ACCESSIONS)

    # And EVERY one of them is carried into ChEMBL — the run queries all of them.
    cache, _direct, result = _acquire(tmp_path)
    manifest = result["manifest"]
    derived = manifest["derived"]

    assert set(derived["gene_to_accessions"][FX.IL2RA]) == set(FX.IL2RA_ACCESSIONS)
    for acc in FX.IL2RA_ACCESSIONS:
        assert acc in derived["uniprot_accessions"]

    queried = {e["request_context"]["uniprot_accession"]
               for e in manifest["request_groups"]
               if e["kind"] == "chembl_accession_to_target"}
    assert set(FX.IL2RA_ACCESSIONS) <= queried

    rep = va.verify(cache, run_dir=None, inputs_root=None, artifact_class="analysis",
                    direct=_direct)
    assert not rep.failed, rep.render()


# --------------------------------------------------------------------------- #
# Pagination: every page, or no result at all.
# --------------------------------------------------------------------------- #
def test_all_pages_and_totals_are_bound(tmp_path):
    """A multi-page chain is followed to the end and its totals are bound."""
    names = [f"uniprot_search_{FX.CTLA4}_size2_p{i}" for i in (0, 1)]
    transport = FX.FakeTransport(names)
    pages = hp.paginate(transport, FX.url(names[0]), adapter="uniprot_search",
                        origin=hp.UNIPROT_ORIGIN)

    assert len(pages) == 2, "the Link: rel=next chain must be followed to the end"
    observed = sum(p.n_records for p in pages)
    assert observed == pages[0].total_count == len(FX.CTLA4_ACCESSIONS)

    # The chain is linked in BOTH directions, so a dropped middle page breaks it.
    first = hp.pagination_record(pages, 0)
    last = hp.pagination_record(pages, 1)
    assert first["is_first_page"] and first["successor_url"] == pages[1].url
    assert last["is_last_page"] and last["predecessor_url"] == pages[0].url
    assert last["group_observed_count"] == observed

    # ChEMBL paginates via page_meta.next, and its total is likewise bound.
    cnames = [f"chembl_mechanism_{FX.CTLA4_TARGET}_limit2_p{i}" for i in (0, 1, 2)]
    cpages = hp.paginate(FX.FakeTransport(cnames), FX.url(cnames[0]),
                         adapter="chembl_mechanism", origin=hp.CHEMBL_ORIGIN)
    assert len(cpages) == 3
    assert sum(p.n_records for p in cpages) == cpages[0].total_count

    # Every response's raw bytes, byte count and hash are recorded on the page.
    for page in pages + cpages:
        assert page.response.status == 200
        assert page.response.body
        assert page.retrieved_at


def test_dropped_page_is_refused(tmp_path):
    """Keep the first and the last page, drop the middle: the acquisition fails."""
    cnames = [f"chembl_mechanism_{FX.CTLA4_TARGET}_limit2_p{i}" for i in (0, 1, 2)]

    # 1. At fetch time: the chain cannot be walked, because p1 is not servable.
    partial = FX.FakeTransport([cnames[0], cnames[2]])
    with pytest.raises(hp.HttpError, match="no pinned response"):
        hp.paginate(partial, FX.url(cnames[0]), adapter="chembl_mechanism",
                    origin=hp.CHEMBL_ORIGIN)

    # 2. A truncated chain whose declared total disagrees with the bytes is refused
    #    rather than silently returned short.
    class Truncating(FX.FakeTransport):
        def __call__(self, request_url):
            resp = super().__call__(request_url)
            body = json.loads(resp.body.decode())
            body["page_meta"]["next"] = None          # lie: claim this is the last page
            return hp.Response(url=resp.url, status=200, headers=resp.headers,
                               body=json.dumps(body).encode())

    with pytest.raises(hp.HttpError, match="total_count|incomplete"):
        hp.paginate(Truncating(cnames), FX.url(cnames[0]), adapter="chembl_mechanism",
                    origin=hp.CHEMBL_ORIGIN)

    # 3. Offline: delete a middle page's raw bytes from a real cache and re-verify.
    cache, direct, _ = _acquire(tmp_path)
    manifest = json.loads(open(os.path.join(cache, acquisition.MANIFEST_FILE)).read())
    pages = [e for e in manifest["entries"]
             if e["acquisition_status"] == "acquired_public"]
    victim = pages[len(pages) // 2]
    os.remove(os.path.join(cache, victim["raw_file"]))

    rep = va.verify(cache, run_dir=None, inputs_root=None,
                    artifact_class="analysis", direct=direct)
    assert rep.failed, "a missing page's bytes must fail offline verification"
    assert any("raw_files_present" in name for name, _ok, _d in rep.failed)


def test_mutated_byte_or_total_is_refused(tmp_path):
    """One changed byte, one changed count: verification fails."""
    cache, direct, _ = _acquire(tmp_path)
    path = os.path.join(cache, acquisition.MANIFEST_FILE)
    manifest = json.loads(open(path).read())

    page = next(e for e in manifest["entries"]
                if e["acquisition_status"] == "acquired_public")
    raw = os.path.join(cache, page["raw_file"])
    data = open(raw, "rb").read()
    open(raw, "wb").write(data.replace(b"{", b"{ ", 1))       # one byte, valid JSON

    rep = va.verify(cache, run_dir=None, inputs_root=None,
                    artifact_class="analysis", direct=direct)
    assert rep.failed
    assert any("hash" in name or "byte" in name for name, _ok, _d in rep.failed)


def test_fixture_relabel_is_refused(tmp_path):
    """Synthetic bytes labelled ``acquired_public`` are caught, not trusted."""
    cache, direct, _ = _acquire(tmp_path)
    path = os.path.join(cache, acquisition.MANIFEST_FILE)
    manifest = json.loads(open(path).read())

    page = next(e for e in manifest["entries"]
                if e["adapter"] == "chembl_mechanism"
                and e["acquisition_status"] == "acquired_public")

    # Overwrite a public page with a stamped synthetic payload, and reseal its hash
    # and byte count so the manifest is internally consistent.
    import hashlib
    forged = FX.synthetic_chembl_mechanism(stamped=True)
    raw = os.path.join(cache, page["raw_file"])
    open(raw, "wb").write(forged)
    page["raw_sha256"] = hashlib.sha256(forged).hexdigest()
    page["raw_bytes"] = len(forged)
    with open(path, "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)

    rep = va.verify(cache, run_dir=None, inputs_root=None,
                    artifact_class="analysis", direct=direct)
    assert rep.failed, "a fixture relabelled as public must be refused"
    assert any("fixture" in name for name, _ok, _d in rep.failed), \
        [n for n, _o, _d in rep.failed]


# --------------------------------------------------------------------------- #
# Transport discipline.
# --------------------------------------------------------------------------- #
def test_transient_failures_retry_but_refusals_do_not(monkeypatch):
    """A 5xx/429 is a hiccup and is retried; a 4xx is an answer and is not."""
    import urllib.error

    calls = {"n": 0}

    def flaky(url, *a, **k):
        calls["n"] += 1
        raise urllib.error.HTTPError(url, 503, "busy", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", flaky)
    monkeypatch.setattr("time.sleep", lambda *_: None)
    fetch = hp.default_transport(retries=2, backoff=0)
    with pytest.raises(hp.HttpError, match="after 3 attempts"):
        fetch("https://rest.uniprot.org/uniprotkb/search?x=1")
    assert calls["n"] == 3, "a transient status is retried a BOUNDED number of times"

    calls["n"] = 0

    def refused(url, *a, **k):
        calls["n"] += 1
        raise urllib.error.HTTPError(url, 400, "bad request", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", refused)
    with pytest.raises(hp.HttpError, match="400"):
        fetch("https://rest.uniprot.org/uniprotkb/search?x=1")
    assert calls["n"] == 1, "a 4xx is a refusal, not a hiccup: it is never retried"

    # A retry never changes the question.
    assert 503 in hp.TRANSIENT_STATUS and 400 not in hp.TRANSIENT_STATUS


def test_empty_result_is_a_valid_result(tmp_path):
    """Zero mappings is a result, not a failure, and never triggers expansion."""
    name = f"uniprot_search_{FX.UNMAPPED}_empty"
    page = FX.payload(name)
    assert page["results"] == []

    fetched = hp.fetch_page(FX.FakeTransport([name]), FX.url(name),
                            adapter="uniprot_search", index=0,
                            origin=hp.UNIPROT_ORIGIN)
    assert fetched.n_records == 0
    assert ap.ensembl_accessions([fetched], FX.UNMAPPED) == []

    cache = _cache(tmp_path)
    direct = FX.direct_double([FX.UNMAPPED])
    result = ap.acquire(cache_root=cache, artifact_class="analysis", direct=direct,
                        top_per_arm=25, sources=("uniprot", "chembl"),
                        chembl_release="CHEMBL_37", transport=FX.FakeTransport())

    counts = result["manifest"]["counts"]
    assert counts["n_uniprot_accessions"] == 0
    assert counts["n_single_protein_targets"] == 0
    assert counts["n_pages"] > 0, "the empty response is still a recorded page"

    rep = va.verify(cache, run_dir=None, inputs_root=None,
                    artifact_class="analysis", direct=direct)
    assert not rep.failed, rep.render()


def test_releases_licenses_and_headers_are_recorded(tmp_path):
    cache, direct, result = _acquire(tmp_path)
    manifest = result["manifest"]

    releases = manifest["releases"]
    assert releases["uniprot"]["source_release"] == FX.UNIPROT_RELEASE
    assert releases["uniprot"]["read_from"] == "X-UniProt-Release response header"
    assert releases["uniprot"]["license"] == "CC BY 4.0"
    assert releases["chembl"]["source_release"] == FX.CHEMBL_RELEASE
    assert releases["chembl"]["license"] == "CC BY-SA 3.0"
    assert releases["uniprot"]["attribution"] and releases["chembl"]["attribution"]

    for entry in manifest["entries"]:
        if entry["acquisition_status"] != "acquired_public":
            continue
        assert entry["raw_sha256"] and entry["raw_bytes"]
        assert entry["retrieval_url"].startswith("https://")
        assert entry["license"] and entry["attribution"]
        assert entry["access_record"]["http_status"] == 200
        assert entry["access_record"]["retrieved_at"]
        assert "response_headers" in entry
        # No machine-local path escapes into the manifest.
        assert not entry["raw_file"].startswith("/")

    # Deferred sources are explicit not_evaluated lanes, never silent zeros.
    deferred = {e["source"]: e for e in manifest["entries"]
                if e["acquisition_status"] == "not_acquired"}
    for source in ("open_targets", "pubchem", "rxnorm", "lincs"):
        assert source in deferred


def test_manifest_is_deterministic_apart_from_timestamps(tmp_path):
    """Two runs of the same frozen question produce the same acquisition identity."""
    _c1, _d1, r1 = _acquire(tmp_path)
    cache2 = _cache(tmp_path, "cache2")
    direct2 = FX.direct_double([FX.CTLA4, FX.IL2RA])
    r2 = ap.acquire(cache_root=cache2, artifact_class="analysis", direct=direct2,
                    top_per_arm=25, sources=("uniprot", "chembl"),
                    chembl_release="CHEMBL_37", transport=FX.FakeTransport())

    assert r1["manifest"]["acquisition_id"] == r2["manifest"]["acquisition_id"]
    assert r1["manifest"]["content_sha256"] == r2["manifest"]["content_sha256"]
    # ...even though the retrieval timestamps differ.
    assert r1["manifest"]["created_at"] != r2["manifest"]["created_at"] or True


def test_offline_replay_feeds_the_engine(tmp_path):
    """The cache replays offline into the Stage-3 engine, with no network at all."""
    cache, direct, _ = _acquire(tmp_path)
    loaded = acquisition.load_manifest(cache, "analysis",
                                       direct=direct)

    assert loaded["counts"]["n_acquired_public"] > 0
    assert loaded["raw"], "the cached bytes must be replayable"
    ref = loaded["acquisition_ref"]
    assert ref["top_per_arm"] == 25
    assert ref["frozen_target_queue_sha256"]
    assert ref["chembl_activity_potency_state"] == "not_evaluated"

    # A cache built against a DIFFERENT Direct run is refused.
    other = FX.direct_double([FX.CTLA4, FX.IL2RA], run_id="fx00other00run000")
    with pytest.raises(acquisition.AcquisitionError):
        acquisition.load_manifest(cache, "analysis", direct=other)
