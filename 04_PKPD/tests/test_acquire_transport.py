"""Transport: retry, rate limit, cache reuse, bounded concurrency.

These are the knobs that make a real candidate queue acquirable in minutes instead of an hour.
They are PURE TRANSPORT — they change how bytes arrive, never what the bytes mean:

  * a REUSED response keeps the access time, status, headers and hash of the fetch that
    actually happened. It does not get a fresh `accessed_at_utc`, because no access happened.
    (A cache hit that re-stamps the clock is a fabricated provenance claim.)
  * a RETRY is bounded and only for transient failures. A 404 is not retried: it is an answer.
  * CONCURRENCY may not change a result. Same queue, any interleaving, same records.
"""

from __future__ import annotations

import os

import pytest

from analysis.acquire_cache import RequestCache
from analysis.acquire_http import Client, StaticTransport
from analysis.acquire_pool import bounded_map
from analysis.acquisition import RunRoot
from analysis.firewall import Rejection

PUBCHEM = "https://pubchem.ncbi.nlm.nih.gov/rest/pug"
URL = f"{PUBCHEM}/compound/name/x/cids/JSON"
JSON = {"content-type": "application/json"}
BODY = b'{"IdentifierList": {"CID": [1]}}'
CLOCK = "2026-07-13T05:00:00Z"


@pytest.fixture()
def run_root(tmp_path):
    return RunRoot(str(tmp_path / "run"))


# ------------------------------------------------------------------- content-addressed store


def test_the_raw_store_is_safe_when_two_workers_write_the_same_bytes(run_root):
    """The tmp file was `path + '.part'` — a FIXED name. Two workers caching identical bytes
    would interleave into one tmp file and could publish a truncated object under a hash that
    no longer describes it. Content-addressing makes that silent."""
    data = b"x" * 200_000
    results = bounded_map(range(8), lambda _: run_root.store(data, source_key="pubchem",
                                                             suffix="json"),
                          max_workers=8)
    relpaths = {r[0] for r in results}
    shas = {r[1] for r in results}
    assert len(relpaths) == 1 and len(shas) == 1
    assert run_root.read(next(iter(relpaths))) == data     # not truncated, not interleaved


# ----------------------------------------------------------------------------- the retry


class _FlakyTransport:
    """Fails `fail_times` with a transient error, then succeeds."""

    clock = CLOCK

    def __init__(self, fail_times: int, status: int = 503):
        self.fail_times = fail_times
        self.status = status
        self.calls = 0

    def __call__(self, url: str, timeout: int):
        self.calls += 1
        if self.calls <= self.fail_times:
            return self.status, JSON, b"transient"
        return 200, JSON, BODY


def test_a_transient_failure_is_retried_up_to_the_bound(run_root):
    transport = _FlakyTransport(fail_times=2)
    client = Client(transport=transport, allow_network=True, max_attempts=3,
                    sleep=lambda _s: None)

    resp = client.get_url("pubchem", URL)
    assert resp.status == 200 and resp.body == BODY
    assert transport.calls == 3


def test_retries_are_bounded_and_the_last_failure_is_reported(run_root):
    transport = _FlakyTransport(fail_times=99)
    client = Client(transport=transport, allow_network=True, max_attempts=3,
                    sleep=lambda _s: None)

    with pytest.raises(Rejection) as exc:
        client.get_url("pubchem", URL)
    assert exc.value.code == "source_http_error"
    assert transport.calls == 3          # bounded: it does not hammer the source


@pytest.mark.parametrize("status", [400, 404, 422])
def test_a_client_error_is_never_retried_it_is_an_answer(run_root, status):
    """A 404 is not a transient failure. Retrying it is noise against a public API, and it does
    not become evidence of absence on the third attempt either."""
    transport = _FlakyTransport(fail_times=99, status=status)
    client = Client(transport=transport, allow_network=True, max_attempts=3,
                    sleep=lambda _s: None)

    with pytest.raises(Rejection):
        client.get_url("pubchem", URL)
    assert transport.calls == 1


# ------------------------------------------------------------------------- the rate limit


def test_requests_to_one_host_are_spaced_by_the_declared_minimum(run_root):
    slept: list[float] = []
    transport = StaticTransport({URL: (200, JSON, BODY)}, clock=CLOCK)
    # ticks: call-1 now=0.0 | call-2 now=0.05 (0.05s later) | post-sleep now=0.2
    client = Client(transport=transport, allow_network=True, sleep=slept.append,
                    min_interval_s=0.2, clock=_FakeClock([0.0, 0.05, 0.2]).next)

    client.get_url("pubchem", URL)
    client.get_url("pubchem", URL)

    # the second call arrived 0.05s after the first, so it waits the REMAINING 0.15s — not a
    # fixed 0.2s, and not zero.
    assert slept and 0.14 < slept[0] < 0.16


class _FakeClock:
    def __init__(self, ticks): self.ticks = list(ticks)

    def next(self) -> float:
        return self.ticks.pop(0) if self.ticks else 999.0


# ------------------------------------------------------------------------- the cache reuse


def test_a_cached_request_is_reused_without_touching_the_network(run_root):
    cache = RequestCache(run_root)
    transport = StaticTransport({URL: (200, JSON, BODY)}, clock=CLOCK)
    client = Client(transport=transport, allow_network=True, cache=cache)

    first = client.get_url("pubchem", URL)
    second = client.get_url("pubchem", URL)

    assert len(transport.seen) == 1                    # the wire was touched exactly once
    assert second.body == first.body == BODY
    assert second.from_cache is True and first.from_cache is False


def test_a_reused_response_keeps_the_access_time_of_the_fetch_that_actually_happened(run_root):
    """A cache hit that re-stamps the clock claims an access that did not occur. The record must
    say when the bytes were REALLY fetched."""
    cache = RequestCache(run_root)
    first_transport = StaticTransport({URL: (200, JSON, BODY)}, clock="2026-07-13T05:00:00Z")
    Client(transport=first_transport, allow_network=True, cache=cache).get_url("pubchem", URL)

    later = StaticTransport({URL: (200, JSON, BODY)}, clock="2026-07-14T23:59:59Z")
    reused = Client(transport=later, allow_network=True, cache=cache).get_url("pubchem", URL)

    assert reused.accessed_at_utc == "2026-07-13T05:00:00Z"   # NOT the later clock
    assert later.seen == []                                   # and no request was made


def test_a_cache_entry_whose_bytes_no_longer_hash_is_refused_not_served(run_root):
    cache = RequestCache(run_root)
    transport = StaticTransport({URL: (200, JSON, BODY)}, clock=CLOCK)
    Client(transport=transport, allow_network=True, cache=cache).get_url("pubchem", URL)

    entry = cache.recall_entry(URL)
    path = os.path.join(run_root.root, entry["cache_relpath"])
    with open(path, "wb") as fh:
        fh.write(b"tampered")

    with pytest.raises(Rejection) as exc:
        Client(transport=transport, allow_network=True, cache=cache).get_url("pubchem", URL)
    assert exc.value.code == "acquisition_raw_hash_mismatch"


def test_the_cache_is_keyed_on_the_canonical_query_not_on_the_drug(run_root):
    """Two different questions are two cache entries, even about the same molecule."""
    cache = RequestCache(run_root)
    other = f"{PUBCHEM}/compound/cid/1/property/InChIKey/JSON"
    transport = StaticTransport({URL: (200, JSON, BODY),
                                 other: (200, JSON, b'{"PropertyTable": {}}')}, clock=CLOCK)
    client = Client(transport=transport, allow_network=True, cache=cache)

    client.get_url("pubchem", URL)
    client.get_url("pubchem", other)
    assert len(transport.seen) == 2
    assert cache.recall_entry(URL)["raw_sha256"] != cache.recall_entry(other)["raw_sha256"]


# ------------------------------------------------------------------------- the concurrency


def test_bounded_map_preserves_input_order_regardless_of_completion_order():
    """Concurrency may not change a result. The queue's order is the manifest's order."""
    import time

    def work(i: int) -> int:
        time.sleep(0.02 if i % 2 == 0 else 0.001)   # evens finish last
        return i * 10

    assert bounded_map(range(6), work, max_workers=6) == [0, 10, 20, 30, 40, 50]


def test_bounded_map_never_exceeds_its_worker_bound():
    import threading

    live = 0
    peak = 0
    lock = threading.Lock()

    def work(_i: int) -> int:
        nonlocal live, peak
        with lock:
            live += 1
            peak = max(peak, live)
        import time
        time.sleep(0.01)
        with lock:
            live -= 1
        return 0

    bounded_map(range(20), work, max_workers=4)
    assert peak <= 4


def test_a_failure_in_one_item_does_not_silently_drop_the_others():
    def work(i: int) -> int:
        if i == 2:
            raise Rejection("boom", "item 2 refused")
        return i

    with pytest.raises(Rejection) as exc:
        bounded_map(range(5), work, max_workers=4)
    assert exc.value.code == "boom"
