"""The only place Stage 4 is allowed to put a request on the wire.

Four rules, enforced here rather than remembered:

  * NO NETWORK BY DEFAULT. `Client()` refuses to fetch. A caller that wants the network says so
    (`allow_network=True`), which means a test can never reach a real host by forgetting a mock.
  * ONLY LEDGERED HOSTS. The host must be the one `method/acquisition_sources_v1.json` records
    for that source. ChEMBL/UniProt raise (reuse_only); DrugBank raises (forbidden).
  * BOUNDED. One request, one timeout, one byte cap, no retries-forever, no redirect off-host.
  * RECORDED. The response carries the canonical URL and query, the UTC access time, the HTTP
    status, the media type and a small ALLOWLIST of headers — never the whole header block, some
    of which is per-request noise that would make an identical response hash differently.

`StaticTransport` is how the offline tests drive the adapters: a URL that is not in its routing
table cannot be fetched at all.
"""

from __future__ import annotations

import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Protocol

from .firewall import Rejection
from .public_sources import assert_fetch_permitted, base_url, host

USER_AGENT = "spot-stage4-acquisition/1.0 (+public-source evidence; contact: repository owner)"
DEFAULT_TIMEOUT_S = 30
DEFAULT_MAX_BYTES = 16 * 1024 * 1024

# Bounded. A public API is shared infrastructure, and a retry storm is how an acquisition gets
# throttled into failure halfway through a queue.
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BACKOFF_S = 0.5
# Minimum spacing between requests to ONE host. PubChem asks for no more than a few per second.
DEFAULT_MIN_INTERVAL_S = 0.25

# Transient: worth asking again. A 4xx is an ANSWER — retrying a 404 does not make it evidence of
# absence on the third attempt, it just adds noise to someone else's server. 429 is the exception:
# it explicitly means "later".
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

# The headers that are part of the record. Everything else (Date, Set-Cookie, request ids,
# CDN noise) is per-request and would make the same document hash differently on every fetch.
HEADER_ALLOWLIST = ("content-type", "last-modified", "etag", "content-length")


@dataclass(frozen=True)
class HttpResponse:
    source_key: str
    url: str
    canonical_query: str
    status: int
    headers: dict[str, str]
    body: bytes
    # The clock of the fetch that ACTUALLY happened. A cache hit carries the ORIGINAL time — it is
    # never re-stamped, because no access occurred now and claiming one would be fabricated
    # provenance.
    accessed_at_utc: str
    from_cache: bool = False

    @property
    def media_type(self) -> str:
        return (self.headers.get("content-type") or "application/octet-stream").split(";")[0].strip()


class Transport(Protocol):
    def __call__(self, url: str, timeout: int) -> tuple[int, dict[str, str], bytes]: ...


@dataclass
class StaticTransport:
    """The offline wire. A URL that is not in `routes` is not reachable, by construction."""

    routes: dict[str, tuple[int, dict[str, str], bytes]]
    clock: str = "1970-01-01T00:00:00Z"
    seen: list[str] = field(default_factory=list)

    def __call__(self, url: str, timeout: int) -> tuple[int, dict[str, str], bytes]:
        self.seen.append(url)
        if url not in self.routes:
            raise Rejection(
                "offline_route_missing",
                f"no synthetic response is registered for {url!r}. The offline transport does "
                "not fall through to the network — a missing fixture is a failing test, not a "
                "live request.")
        return self.routes[url]


def _urllib_transport(url: str, timeout: int) -> tuple[int, dict[str, str], bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                               "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (scheme checked below)
        return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()


class Client:
    """A bounded, ledger-checked HTTP GET. It does nothing else."""

    def __init__(self, *, allow_network: bool = False, transport: Optional[Transport] = None,
                 timeout: int = DEFAULT_TIMEOUT_S, max_bytes: int = DEFAULT_MAX_BYTES,
                 cache: Optional[Any] = None, max_attempts: int = DEFAULT_MAX_ATTEMPTS,
                 backoff_s: float = DEFAULT_BACKOFF_S,
                 min_interval_s: float = DEFAULT_MIN_INTERVAL_S,
                 sleep: Optional[Callable[[float], None]] = None,
                 clock: Optional[Callable[[], float]] = None) -> None:
        self.allow_network = allow_network
        self.transport = transport or _urllib_transport
        self.timeout = timeout
        self.max_bytes = max_bytes
        # Fetch each canonical query once. A reuse keeps the ORIGINAL access time.
        self.cache = cache
        self.max_attempts = max(1, max_attempts)
        self.backoff_s = backoff_s
        self.min_interval_s = min_interval_s
        self._sleep = sleep or time.sleep
        self._clock = clock or time.monotonic
        self._last_request: dict[str, float] = {}
        self._lock = threading.Lock()
        self.n_fetched = 0
        self.n_reused = 0

    # -- query construction is part of the record, so it lives here ---------------------
    @staticmethod
    def canonical_query(path: str, params: Optional[dict[str, str]] = None) -> str:
        """The exact question asked, in a stable form: sorted params, percent-encoded.

        Two runs that asked different questions must not be able to look like one run, so the
        query is content — not a display string.
        """
        path = path.lstrip("/")
        if not params:
            return path
        encoded = urllib.parse.urlencode(sorted(params.items()), quote_via=urllib.parse.quote)
        return f"{path}?{encoded}"

    def get(self, source_key: str, path: str,
            params: Optional[dict[str, str]] = None) -> HttpResponse:
        entry = assert_fetch_permitted(source_key)   # reuse_only / forbidden / unlisted -> raise
        query = self.canonical_query(path, params)
        url = f"{str(entry['base_url']).rstrip('/')}/{query}"
        return self._fetch(source_key, url, query)

    def get_url(self, source_key: str, url: str) -> HttpResponse:
        """Fetch an absolute URL, still bound to its source's ledger entry and host."""
        assert_fetch_permitted(source_key)
        parsed = urllib.parse.urlparse(url)
        prefix = base_url(source_key).rstrip("/") + "/"
        query = url[len(prefix):] if url.startswith(prefix) else parsed.path.lstrip("/")
        return self._fetch(source_key, url, query)

    def _fetch(self, source_key: str, url: str, canonical_query: str) -> HttpResponse:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https":
            raise Rejection(
                "insecure_source_url",
                f"{url!r} is not https. A source read over a channel that can be rewritten in "
                "flight is not a source record.")
        expected = host(source_key)
        if parsed.hostname != expected:
            raise Rejection(
                "host_not_in_ledger",
                f"{source_key!r} is registered at {expected!r} in the public-source ledger, but "
                f"the request targets {parsed.hostname!r}. Stage 4 talks to the host the ledger "
                "names, and to no other.")
        # A response already fetched for this exact question is REUSED, with the envelope of the
        # fetch that really happened. This is the only path that returns bytes without a request.
        if self.cache is not None:
            hit = self.cache.recall(url)
            if hit is not None:
                entry, body = hit
                self.n_reused += 1
                return HttpResponse(
                    source_key=source_key, url=url, canonical_query=canonical_query,
                    status=int(entry["status"]),
                    headers={k: v for k, v in sorted(dict(entry["headers"]).items())
                             if k in HEADER_ALLOWLIST},
                    body=body,
                    accessed_at_utc=str(entry["accessed_at_utc"]),   # the ORIGINAL access
                    from_cache=True,
                )

        if not self.allow_network:
            raise Rejection(
                "network_not_permitted",
                f"a fetch of {url!r} was attempted without network permission. Acquisition is "
                "opt-in: the caller passes allow_network=True (the CLI's --allow-network), so "
                "no code path reaches a public API by accident.")

        status, headers, body = self._fetch_with_retry(source_key, url)

        if len(body) > self.max_bytes:
            raise Rejection(
                "source_response_too_large",
                f"{source_key}: {url!r} returned {len(body)} bytes, over the {self.max_bytes}-byte "
                "cap. Acquisition is bounded.")

        accessed_at_utc = self._now()
        self.n_fetched += 1
        if self.cache is not None:
            self.cache.remember(
                url=url, source_key=source_key, canonical_query=canonical_query, status=status,
                headers=headers, accessed_at_utc=accessed_at_utc, body=body,
                suffix=_suffix_for(headers))

        return HttpResponse(
            source_key=source_key,
            url=url,
            canonical_query=canonical_query,
            status=status,
            headers={k: v for k, v in sorted(headers.items()) if k in HEADER_ALLOWLIST},
            body=body,
            accessed_at_utc=accessed_at_utc,
            from_cache=False,
        )

    def _fetch_with_retry(self, source_key: str, url: str) -> tuple[int, dict[str, str], bytes]:
        """Bounded retry, transient failures only. A 4xx is an answer, not a flake."""
        last: Optional[Rejection] = None
        for attempt in range(1, self.max_attempts + 1):
            self._respect_rate_limit(source_key)
            try:
                status, headers, body = self.transport(url, self.timeout)
            except Rejection:
                raise
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                last = Rejection(
                    "source_unreachable",
                    f"{source_key}: {url!r} could not be fetched ({type(exc).__name__}: {exc}). A "
                    "source that did not answer has not been evaluated; it has not said 'no'.")
            else:
                if status == 200:
                    return status, headers, body
                last = Rejection(
                    "source_http_error",
                    f"{source_key}: {url!r} returned HTTP {status} after {attempt} attempt(s). "
                    "Only a 200 carries bytes Stage 4 will read; a 404 is not evidence of absence "
                    "and a 500 is not evidence of anything.")
                if status not in RETRYABLE_STATUS:
                    raise last          # an answer. Asking again does not change it.

            if attempt < self.max_attempts:
                self._sleep(self.backoff_s * (2 ** (attempt - 1)))

        assert last is not None
        raise last

    def _respect_rate_limit(self, source_key: str) -> None:
        """Space requests to one host. Politeness here is what keeps a long queue from throttling."""
        if self.min_interval_s <= 0:
            return
        with self._lock:
            host_key = host(source_key)
            previous = self._last_request.get(host_key)
            now = self._clock()
            if previous is not None:
                wait = self.min_interval_s - (now - previous)
                if wait > 0:
                    self._sleep(wait)
                    now = self._clock()
            self._last_request[host_key] = now

    def _now(self) -> str:
        clock = getattr(self.transport, "clock", None)
        if isinstance(clock, str):
            return clock
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# Media type -> cache-file suffix. The bytes are addressed by hash; the suffix is only so a
# reviewer opening the run root can see what a file is.
_SUFFIX = {"application/json": "json", "application/xml": "xml", "text/xml": "xml",
           "text/html": "html", "text/plain": "txt"}


def _suffix_for(headers: dict[str, str]) -> str:
    media = (headers.get("content-type") or "").split(";")[0].strip().lower()
    return _SUFFIX.get(media, "bin")
