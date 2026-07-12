"""HTTP plumbing for the bounded public acquisition: fetch, paginate, record.

This is the ONLY module in Stage 3 that may open a socket, and it opens one only
when the caller hands it a network transport. The transport is a PARAMETER, so:

  * ``acquire_public`` passes :func:`default_transport` and talks to the real APIs;
  * every test passes a fake transport keyed on pinned response bytes and never
    touches a socket;
  * ``verify_acquisition`` imports nothing from here that could reach the network.

What it records is what the response actually returned. Release strings, totals,
next-links, ETags and content types are read off the wire, never copied from a
document. A page that cannot state its own place in a pagination chain is an
error, not a silently truncated result.
"""
from __future__ import annotations

import datetime as _dt
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

_LINK_NEXT_RE = re.compile(r'<([^>]+)>\s*;[^<]*rel="next"')

# The server did not answer. Retrying the SAME url is not adaptive acquisition.
TRANSIENT_STATUS = frozenset({429, 500, 502, 503, 504})

USER_AGENT = "spot-stage3-druglink/acquire_public (research; public REST APIs)"
DEFAULT_TIMEOUT = 60
MAX_PAGES = 500                      # a chain longer than this is a bug, not data

UNIPROT_ORIGIN = "https://rest.uniprot.org"
CHEMBL_ORIGIN = "https://www.ebi.ac.uk"

# Which JSON array carries the records, per endpoint. Read from the body; a body
# that does not carry its declared array is an unusable page.
RECORDS_KEY = {
    "uniprot_search": "results",
    "chembl_target": "targets",
    "chembl_mechanism": "mechanisms",
    "chembl_molecule": "molecules",
    "chembl_activity": "activities",
    "chembl_status": None,           # a single release record, not a page of records
}

# Headers whose values are retained verbatim in the access record.
RECORDED_HEADERS = ("content-type", "etag", "last-modified", "link",
                    "x-total-results", "x-uniprot-release", "x-uniprot-release-date")


class HttpError(RuntimeError):
    """A public endpoint refused, failed, or returned an unusable response."""


@dataclass(frozen=True)
class Response:
    url: str
    status: int
    headers: dict[str, str]          # keys lower-cased
    body: bytes

    def header(self, name: str) -> Optional[str]:
        return self.headers.get(name.lower())


Transport = Callable[[str], Response]


@dataclass(frozen=True)
class Page:
    """One HTTP response page and the pagination facts it stated about itself."""
    index: int
    url: str
    response: Response
    retrieved_at: str
    n_records: int
    total_count: Optional[int]       # what the SOURCE said the total was
    next_url: Optional[str]
    prev_url: Optional[str]
    body_json: dict[str, Any] = field(repr=False, default_factory=dict)


def default_transport(timeout: int = DEFAULT_TIMEOUT, retries: int = 3,
                      backoff: float = 2.0) -> Transport:
    """The real network transport. Only ``acquire_public`` ever passes this.

    A 429/5xx or a dropped connection is a TRANSPORT failure -- the server did not
    answer -- so the same URL is retried a bounded number of times. This is not
    adaptive acquisition: the URL, the query and the frozen queue are unchanged,
    and a 4xx (the server DID answer, with a refusal) is never retried.
    """

    def once(url: str) -> Response:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT,
                                                   "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return Response(url=url, status=resp.status,
                            headers={k.lower(): v for k, v in resp.headers.items()},
                            body=resp.read())

    def fetch(url: str) -> Response:
        last = ""
        for attempt in range(retries + 1):
            try:
                return once(url)
            except urllib.error.HTTPError as exc:
                last = f"{exc.code} from {url}: {exc.reason}"
                if exc.code not in TRANSIENT_STATUS:
                    raise HttpError(last) from exc      # a refusal, not a hiccup
            except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
                last = f"cannot reach {url}: {exc}"
            if attempt < retries:
                time.sleep(backoff * (2 ** attempt))
        raise HttpError(f"{last} (after {retries + 1} attempts)")

    return fetch


def canonical_url(base: str, params: dict[str, str]) -> str:
    """A deterministic URL: parameters sorted by name, every value percent-encoded.

    The same logical query always produces the same byte-identical URL string, so
    the URL can be part of the content-addressed source locator.
    """
    for k, v in params.items():
        if not isinstance(k, str) or not isinstance(v, str):
            raise HttpError(f"request parameters must be strings: {k!r}={v!r}")
    query = urllib.parse.urlencode(sorted(params.items()),
                                   quote_via=urllib.parse.quote, safe="")
    return f"{base}?{query}" if query else base


def now_utc() -> str:
    return _dt.datetime.now(_dt.UTC).isoformat().replace("+00:00", "Z")


def parse_link_next(link_header: Optional[str]) -> Optional[str]:
    """UniProt paginates with ``Link: <url>; rel="next"``. No link means no page.

    The URL itself contains commas (``fields=accession,reviewed,...``), so the
    header is NOT split on commas: each ``<...>`` bracket is matched whole and its
    parameters are read only up to the next bracket.
    """
    if not link_header:
        return None
    if "rel=\"next\"" not in link_header:
        return None
    match = _LINK_NEXT_RE.search(link_header)
    if not match:
        raise HttpError(f"malformed Link header: {link_header!r}")
    return match.group(1).strip()


def _int_or_none(value: Optional[str]) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise HttpError(f"non-integer count header: {value!r}") from exc


def _body_json(resp: Response) -> dict[str, Any]:
    try:
        obj = json.loads(resp.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HttpError(f"{resp.url}: response is not UTF-8 JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise HttpError(f"{resp.url}: response is not a JSON object")
    return obj


def _records(body: dict[str, Any], adapter: str, url: str) -> list[Any]:
    key = RECORDS_KEY[adapter]
    if key is None:
        return []
    rows = body.get(key)
    if not isinstance(rows, list):
        raise HttpError(f"{url}: response has no {key!r} array")
    return rows


def _absolute(origin: str, link: Optional[str]) -> Optional[str]:
    if not link:
        return None
    return link if link.startswith("http") else origin + link


def fetch_page(transport: Transport, url: str, *, adapter: str, index: int,
               origin: str) -> Page:
    """Fetch one page and read its own pagination claims out of the response."""
    resp = transport(url)
    if resp.status != 200:
        raise HttpError(f"{url}: HTTP {resp.status}")
    body = _body_json(resp)
    rows = _records(body, adapter, url)

    if RECORDS_KEY[adapter] is None:
        # A release/status record: one document, no records array, no pagination.
        total, nxt, prev = None, None, None
    elif origin == UNIPROT_ORIGIN:
        # UniProt states the total in a header and the successor in a Link header.
        total = _int_or_none(resp.header("x-total-results"))
        nxt = parse_link_next(resp.header("link"))
        prev = None
    else:
        meta = body.get("page_meta")
        if not isinstance(meta, dict):
            raise HttpError(f"{url}: ChEMBL response has no page_meta")
        total = meta.get("total_count")
        if total is not None and not isinstance(total, int):
            raise HttpError(f"{url}: page_meta.total_count is not an integer")
        nxt = _absolute(origin, meta.get("next"))
        prev = _absolute(origin, meta.get("previous"))

    return Page(index=index, url=url, response=resp, retrieved_at=now_utc(),
                n_records=len(rows), total_count=total, next_url=nxt, prev_url=prev,
                body_json=body)


def paginate(transport: Transport, first_url: str, *, adapter: str,
             origin: str) -> list[Page]:
    """Follow EVERY successor until the source says there is none.

    A repeated URL, a missing page, or a chain longer than :data:`MAX_PAGES` is an
    error: a truncated chain is a silently wrong result, which is worse than none.
    """
    pages: list[Page] = []
    seen: set[str] = set()
    url: Optional[str] = first_url
    while url is not None:
        if url in seen:
            raise HttpError(f"pagination loops back to {url}")
        seen.add(url)
        page = fetch_page(transport, url, adapter=adapter, index=len(pages),
                          origin=origin)
        pages.append(page)
        if len(pages) > MAX_PAGES:
            raise HttpError(f"pagination exceeded {MAX_PAGES} pages at {first_url}")
        url = page.next_url

    observed = sum(p.n_records for p in pages)
    total = pages[0].total_count if pages else None
    if total is not None and observed != total:
        raise HttpError(
            f"{first_url}: source declared total_count={total} but {len(pages)} "
            f"page(s) carried {observed} records; refusing an incomplete chain")
    return pages


def access_record(page: Page, *, acquired_by: str) -> dict[str, Any]:
    """What the acquisition step actually observed on the wire."""
    return {
        "retrieved_at": page.retrieved_at,
        "http_status": page.response.status,
        "content_type": page.response.header("content-type"),
        "etag": page.response.header("etag"),
        "last_modified": page.response.header("last-modified"),
        "acquired_by": acquired_by,
    }


def observed_headers(page: Page) -> dict[str, Optional[str]]:
    """The response headers retained verbatim (release, totals, next-link, caching)."""
    return {name: page.response.header(name) for name in RECORDED_HEADERS}


def pagination_record(pages: list[Page], i: int) -> dict[str, Any]:
    """Where this page sits in its chain: predecessor, successor, counts.

    The successor recorded here is the URL the NEXT page was actually fetched from,
    and the predecessor is the URL the previous page was actually fetched from, so a
    dropped middle page breaks the chain in both directions.
    """
    page = pages[i]
    return {
        "page_index": i,
        "n_pages_in_group": len(pages),
        "predecessor_url": pages[i - 1].url if i > 0 else None,
        "successor_url": pages[i + 1].url if i + 1 < len(pages) else None,
        "declared_next_url": page.next_url,
        "declared_previous_url": page.prev_url,
        "is_first_page": i == 0,
        "is_last_page": i + 1 == len(pages),
        "expected_total_count": page.total_count,
        "observed_count": page.n_records,
        "cumulative_observed_count": sum(p.n_records for p in pages[: i + 1]),
        "group_observed_count": sum(p.n_records for p in pages),
    }
