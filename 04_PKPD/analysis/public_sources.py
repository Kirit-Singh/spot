"""The public-source ledger: who may be fetched, on whose terms, and who may not.

Loaded from `method/acquisition_sources_v1.json`. A source that is not in the ledger cannot
be fetched, and a source the ledger marks `reuse_only` (ChEMBL, UniProt) is never fetched by
Stage 4 at all — its records come from the admitted Stage-3 bundle, verbatim, or they do not
exist. DrugBank is refused outright: no valid public licence has been established for it.

The ledger is NOT part of the method bundle hash: it declares source TERMS, not a scientific
parameter, so a licence correction must not silently move a scorecard id. Its own file hash
travels in the acquisition manifest (`source_ledger_sha256`) instead.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Any

from .canonical import sha256_bytes
from .firewall import Rejection
from .method_config import METHOD_DIR

LEDGER_FILE = "acquisition_sources_v1.json"
LEDGER_PATH = os.path.join(METHOD_DIR, LEDGER_FILE)

FETCH_PERMITTED = "permitted"
FETCH_REUSE_ONLY = "reuse_only"


@lru_cache(maxsize=1)
def _load() -> tuple[dict[str, Any], str]:
    with open(LEDGER_PATH, "rb") as fh:
        raw = fh.read()
    return json.loads(raw.decode("utf-8")), sha256_bytes(raw)


def ledger() -> dict[str, Any]:
    return _load()[0]


def ledger_sha256() -> str:
    """The exact ledger bytes this run's terms were read from."""
    return _load()[1]


def source(source_key: str) -> dict[str, Any]:
    """The ledger entry for a source. An unlisted source is a refusal, not a default."""
    entry = ledger()["sources"].get(source_key)
    if entry is None:
        forbidden = ledger()["forbidden"].get(source_key)
        if forbidden:
            raise Rejection(
                "forbidden_source",
                f"{source_key!r} is forbidden: {forbidden['reason']}")
        raise Rejection(
            "unknown_source",
            f"{source_key!r} is not in the public-source ledger ({LEDGER_FILE}). Stage 4 does "
            "not acquire from a source whose terms it has not recorded.")
    return entry


def assert_fetch_permitted(source_key: str) -> dict[str, Any]:
    """May Stage 4 put a request on the wire for this source? -> the ledger entry, or refuse."""
    entry = source(source_key)
    mode = entry.get("fetch")
    if mode == FETCH_REUSE_ONLY:
        raise Rejection(
            "stage3_source_reuse_required",
            f"{source_key!r} is reuse_only. {entry.get('fetch_note', '')} Stage 4 takes its "
            f"{source_key} records from the admitted Stage-3 bundle and does not re-query them.")
    if mode != FETCH_PERMITTED:
        raise Rejection(
            "source_fetch_not_permitted",
            f"the ledger does not permit fetching {source_key!r} (fetch={mode!r})")
    return entry


def terms(source_key: str) -> tuple[str, str, str]:
    """(licence text, terms URL, licence status) — recorded on every record from this source."""
    entry = source(source_key)
    return (str(entry["license"]), str(entry["license_or_terms_url"]),
            str(entry["license_status"]))


def host(source_key: str) -> str:
    return str(source(source_key)["host"])


def base_url(source_key: str) -> str:
    return str(source(source_key)["base_url"])


def allowed_hosts() -> frozenset[str]:
    """Every host any fetchable ledger entry names. The HTTP client will talk to no other."""
    return frozenset(
        str(e["host"]) for e in ledger()["sources"].values()
        if e.get("fetch") == FETCH_PERMITTED and e.get("host")
    )
