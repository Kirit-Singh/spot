"""The request cache: fetch each canonical query once, and never re-stamp the clock.

A candidate queue asks the same questions many times over — the same DailyMed listing, the same
Drugs@FDA application behind two labels. Re-fetching them is slow, rude to a shared public API, and
buys nothing: the bytes are content-addressed already.

The rule that makes this safe:

    A REUSED response carries the access time, status, headers and hash of the fetch that ACTUALLY
    HAPPENED. It is never re-stamped with the current clock.

A cache hit that says "accessed just now" is a fabricated provenance claim about an access that did
not occur — the same species of defect as the invented `1970-01-01` access date this codebase
already had to remove. So the cache stores the original response envelope beside the bytes, and
`from_cache` says plainly which fetch a record came from.

The entry is keyed on the **canonical query** (the exact question), not on the drug: two different
questions about one molecule are two entries. Bytes are re-hashed on the way out — a cache whose
bytes no longer match the hash they were filed under is refused, not served.
"""

from __future__ import annotations

import json
import os
from typing import Any, Optional

from .canonical import sha256_bytes
from .firewall import Rejection

INDEX_DIR = "requests"


class RequestCache:
    """Canonical query -> the response that was actually fetched for it, under the run root."""

    def __init__(self, run_root: Any) -> None:
        self.run_root = run_root
        self.dir = os.path.join(run_root.root, INDEX_DIR)
        os.makedirs(self.dir, exist_ok=True)

    @staticmethod
    def key(url: str) -> str:
        return sha256_bytes(url.encode("utf-8"))

    def _path(self, url: str) -> str:
        return os.path.join(self.dir, f"{self.key(url)}.json")

    def recall_entry(self, url: str) -> Optional[dict[str, Any]]:
        try:
            with open(self._path(url), encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return None

    def recall(self, url: str) -> Optional[tuple[dict[str, Any], bytes]]:
        """-> (the original response envelope, its bytes) or None. Refuses tampered bytes."""
        entry = self.recall_entry(url)
        if not entry:
            return None
        try:
            data = self.run_root.read(entry["cache_relpath"])
        except OSError:
            return None                      # the bytes are gone: re-fetch, do not pretend

        got = sha256_bytes(data)
        if got != entry["raw_sha256"]:
            raise Rejection(
                "acquisition_raw_hash_mismatch",
                f"the cached response for {url!r} hashes to {got}, but the request index records "
                f"{entry['raw_sha256']}. The bytes are the evidence; a cache that no longer "
                "matches them is refused, never served.")
        return entry, data

    def remember(self, *, url: str, source_key: str, canonical_query: str, status: int,
                 headers: dict[str, str], accessed_at_utc: str, body: bytes,
                 suffix: str = "") -> dict[str, Any]:
        """File a response under its canonical query, with the envelope of the REAL fetch."""
        relpath, sha = self.run_root.store(body, source_key=source_key, suffix=suffix)
        entry = {
            "url": url,
            "source_key": source_key,
            "canonical_query": canonical_query,
            "status": status,
            "headers": dict(sorted(headers.items())),
            # The clock of the fetch that actually happened. A reuse never overwrites it.
            "accessed_at_utc": accessed_at_utc,
            "raw_sha256": sha,
            "raw_bytes": len(body),
            "cache_relpath": relpath,
        }
        path = self._path(url)
        tmp = f"{path}.{os.getpid()}.part"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(entry, fh, indent=2, sort_keys=True)
        os.replace(tmp, path)
        return entry

    def n_entries(self) -> int:
        return len([n for n in os.listdir(self.dir) if n.endswith(".json")])
