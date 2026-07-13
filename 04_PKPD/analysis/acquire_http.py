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

import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Protocol

from .firewall import Rejection
from .public_sources import assert_fetch_permitted, base_url, host

USER_AGENT = "spot-stage4-acquisition/1.0 (+public-source evidence; contact: repository owner)"
DEFAULT_TIMEOUT_S = 30
DEFAULT_MAX_BYTES = 16 * 1024 * 1024

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
    accessed_at_utc: str

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
                 timeout: int = DEFAULT_TIMEOUT_S, max_bytes: int = DEFAULT_MAX_BYTES) -> None:
        self.allow_network = allow_network
        self.transport = transport or _urllib_transport
        self.timeout = timeout
        self.max_bytes = max_bytes

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
        if not self.allow_network:
            raise Rejection(
                "network_not_permitted",
                f"a fetch of {url!r} was attempted without network permission. Acquisition is "
                "opt-in: the caller passes allow_network=True (the CLI's --allow-network), so "
                "no code path reaches a public API by accident.")

        try:
            status, headers, body = self.transport(url, self.timeout)
        except Rejection:
            raise
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            raise Rejection(
                "source_unreachable",
                f"{source_key}: {url!r} could not be fetched ({type(exc).__name__}: {exc}). A "
                "source that did not answer has not been evaluated; it has not said 'no'.")

        if status != 200:
            raise Rejection(
                "source_http_error",
                f"{source_key}: {url!r} returned HTTP {status}. Only a 200 carries bytes Stage 4 "
                "will read; a 404 is not evidence of absence and a 500 is not evidence of "
                "anything.")
        if len(body) > self.max_bytes:
            raise Rejection(
                "source_response_too_large",
                f"{source_key}: {url!r} returned {len(body)} bytes, over the {self.max_bytes}-byte "
                "cap. Acquisition is bounded.")

        return HttpResponse(
            source_key=source_key,
            url=url,
            canonical_query=canonical_query,
            status=status,
            headers={k: v for k, v in sorted(headers.items()) if k in HEADER_ALLOWLIST},
            body=body,
            accessed_at_utc=self._now(),
        )

    def _now(self) -> str:
        clock = getattr(self.transport, "clock", None)
        if isinstance(clock, str):
            return clock
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
