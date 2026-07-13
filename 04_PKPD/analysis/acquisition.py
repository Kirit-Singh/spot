"""The acquisition manifest — the record that makes a source re-fetchable and checkable.

The audit's finding (§4.7): Stage 4's source contract carried an access DATE and nothing that
would let a reviewer reconstruct the request — no UTC timestamp, no canonical query, no HTTP
status, no response headers, no terms URL, and no hash of the adapter that did the extracting.
This module is that record.

Three origins, and no path between them:

  fetched_public       Stage 4 put the request on the wire. It must show the locator (URL +
                       canonical query + UTC time + HTTP 200) and the bytes (count + SHA-256 +
                       a cache entry under the run root). Missing any of it -> refused.
  reused_from_stage3   the bytes were acquired, hashed and released by Stage 3. Carried
                       VERBATIM (see stage3_reuse.py). Stage 4 does not re-query them and does
                       not re-interpret them.
  synthetic_fixture    a labelled synthetic response. It has a hash — of exactly the bytes the
                       parser was handed — and it can never become a public record.

Raw bytes live OUTSIDE Git, under a caller-supplied run root, addressed by their own SHA-256.
Git holds small synthetic fixtures and manifests only. `RunRoot` refuses to write a cache
inside the working tree, because a cached live label committed by accident is a licence
problem that no later `git rm` undoes.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Any, Literal, Optional

from pydantic import Field, model_validator

from .canonical import LOCAL_PATH_RE, sha256_bytes, short_id, strict_content_sha256
from .contracts import ID_PATTERN, SHA256_PATTERN, AcquisitionStatus, SourceRecord, Strict
from .firewall import Rejection
from .method_config import STAGE4_DIR

ACQUISITION_SCHEMA_ID = "spot.stage04_acquisition_manifest.v1"
MANIFEST_FILE = "acquisition_manifest.json"
RAW_DIR = "raw"

REPO_ROOT = os.path.dirname(STAGE4_DIR)
UTC_PATTERN = r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"
DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"

Origin = Literal["fetched_public", "reused_from_stage3", "synthetic_fixture"]
EvidenceState = Literal[
    "observed",
    "not_evaluated",
    "not_found_after_reproducible_search",
    "conflicting",
    "not_applicable",
]

# What a fetched record must show before it is allowed to be evidence about anything.
PUBLIC_REQUIRED = (
    "url", "canonical_query", "accessed_at_utc", "http_status", "raw_media_type",
    "raw_bytes", "raw_sha256", "cache_relpath", "license_or_terms_url",
)

HARD_RULES = [
    "Raw bytes are cached outside Git under the run root; Git holds synthetic fixtures only.",
    "A source does not declare itself free: every acquired record carries its terms URL.",
    "ChEMBL and UniProt are reuse_only — their records come from the admitted Stage-3 bundle, "
    "verbatim, and are never re-queried here.",
    "An absent lane is a stated absence (`not_evaluated`), never an empty field.",
    "No descriptor source here supplies logD7.4 or most-basic pKa; CNS-MPO stays incomplete "
    "rather than fabricated.",
    "This manifest acquires evidence. It ranks no drug and asserts nothing about safety, "
    "brain penetrance or benefit.",
]


class AcquisitionRecord(Strict):
    """One response, one record. Every scientific number will bind to one of these."""

    acquisition_record_id: str = Field(pattern=ID_PATTERN)
    source_key: str
    source_name: str
    source_type: Literal[
        "primary_literature", "regulatory_label", "public_database", "public_api",
        "structure_probe", "fixture",
    ]
    origin: Origin

    # --- the locator ---------------------------------------------------------------
    stable_record_id: Optional[str] = None
    url: Optional[str] = None
    canonical_query: Optional[str] = None
    # Stage 3 records the canonical query as a HASH, not as text. When that is all that
    # exists, this is where it goes — the text is NOT reconstructed from it.
    canonical_query_sha256: Optional[str] = Field(default=None, pattern=SHA256_PATTERN)
    accessed_at_utc: Optional[str] = Field(default=None, pattern=UTC_PATTERN)
    # Stage-3-reused records carry Stage 3's acquisition DATE; a UTC timestamp Stage 3 never
    # recorded is not invented here.
    access_date: Optional[str] = Field(default=None, pattern=DATE_PATTERN)

    # --- the response --------------------------------------------------------------
    http_status: Optional[int] = None
    raw_media_type: Optional[str] = None
    response_headers: dict[str, str] = Field(default_factory=dict)
    release_or_last_updated: Optional[str] = None

    # --- the terms -----------------------------------------------------------------
    license: Optional[str] = None
    license_or_terms_url: Optional[str] = None
    license_status: Optional[str] = None
    redistribution: Optional[str] = None

    # --- the bytes -----------------------------------------------------------------
    raw_bytes: Optional[int] = Field(default=None, ge=0)
    raw_sha256: Optional[str] = Field(default=None, pattern=SHA256_PATTERN)
    # Only when the transport envelope is volatile (a retrieval date stamped into every
    # response). The RULE is recorded with it: a hash whose derivation is undeclared is not
    # reproducible by a reviewer.
    content_sha256: Optional[str] = Field(default=None, pattern=SHA256_PATTERN)
    content_hash_rule: Optional[str] = None
    cache_relpath: Optional[str] = None

    # --- what was done with it ------------------------------------------------------
    extraction_transform: str
    adapter_code_sha256: str = Field(pattern=SHA256_PATTERN)
    review_status: Literal["unreviewed", "machine_verified", "human_reviewed", "not_applicable"]
    evidence_state: EvidenceState = "observed"

    stage3_source_record_id: Optional[str] = None
    note: Optional[str] = None

    @model_validator(mode="after")
    def _origin_evidence(self) -> "AcquisitionRecord":
        if self.origin == "fetched_public":
            missing = [f for f in PUBLIC_REQUIRED if not getattr(self, f)]
            if missing:
                raise ValueError(
                    f"a fetched_public record ({self.acquisition_record_id!r}) is missing "
                    f"{sorted(missing)}. A fetch that cannot show its locator, its terms and "
                    "its bytes is not a public source record; it is a claim.")
            if self.http_status != 200:
                raise ValueError(
                    f"http_status={self.http_status} is not evidence. Only a 200 response "
                    "carries bytes Stage 4 will read.")
            if self.source_type == "fixture":
                raise ValueError("source_type='fixture' cannot be origin='fetched_public'")
        elif self.origin == "synthetic_fixture":
            if not self.raw_sha256:
                raise ValueError("a synthetic fixture still hashes the exact bytes it parsed")
            if self.evidence_state == "observed":
                raise ValueError(
                    "a synthetic fixture is not an observation of anything; its evidence_state "
                    "may not be 'observed'")
        elif self.origin == "reused_from_stage3":
            if not self.stage3_source_record_id:
                raise ValueError(
                    "a reused record must name the Stage-3 source_record_id it was carried from")
            if self.raw_sha256 and not self.raw_bytes:
                raise ValueError("a hash without a byte count is not a checkable record")
            if not self.raw_sha256 and self.evidence_state == "observed":
                raise ValueError(
                    "there are no bytes behind this Stage-3 record, so there is no observation "
                    "behind it; evidence_state must say so")

        if self.cache_relpath:
            if os.path.isabs(self.cache_relpath) or LOCAL_PATH_RE.search(self.cache_relpath):
                raise ValueError(
                    f"cache_relpath {self.cache_relpath!r} is machine-local. The manifest records "
                    "the path relative to the run root; an absolute path is not content and "
                    "cannot be re-verified on the reviewer's machine.")
        if self.content_sha256 and not self.content_hash_rule:
            raise ValueError(
                "a content hash without its declared rule cannot be reproduced by a reviewer")
        return self

    @property
    def has_bytes(self) -> bool:
        return bool(self.raw_sha256)


class MissingEvidence(Strict):
    """A stated absence. `missingness_explicit` -> refuse_artifact."""

    lane: str
    evidence_state: Literal[
        "not_evaluated", "not_found_after_reproducible_search", "conflicting", "not_applicable"
    ]
    reason: str
    source_key: Optional[str] = None
    search_manifest_sha256: Optional[str] = Field(default=None, pattern=SHA256_PATTERN)


class AcquisitionManifest(Strict):
    """Every response this run stands on, plus everything it did NOT acquire."""

    schema_id: Literal["spot.stage04_acquisition_manifest.v1"]
    run_id: str = Field(pattern=ID_PATTERN)
    # The admitted Stage-3 bundle these records were acquired for. Hashes, never a path.
    stage3_binding: dict[str, str] = Field(default_factory=dict)
    source_ledger_sha256: str = Field(pattern=SHA256_PATTERN)
    records: list[AcquisitionRecord] = Field(default_factory=list)
    missing: list[MissingEvidence] = Field(default_factory=list)

    def content(self) -> dict[str, Any]:
        """The identity content: sorted records, the binding, the terms ledger. No wall clock
        beyond the access timestamps that are themselves part of a record."""
        return {
            "schema_id": self.schema_id,
            "stage3_binding": dict(sorted(self.stage3_binding.items())),
            "source_ledger_sha256": self.source_ledger_sha256,
            "records": [
                r.model_dump(exclude_none=True)
                for r in sorted(self.records, key=lambda r: r.acquisition_record_id)
            ],
            "missing": [
                m.model_dump(exclude_none=True)
                for m in sorted(self.missing, key=lambda m: (m.lane, m.reason))
            ],
        }

    def as_document(self) -> dict[str, Any]:
        doc = self.content()
        doc["run_id"] = self.run_id
        doc["hard_rules"] = list(HARD_RULES)
        doc["content_sha256"] = manifest_content_sha256(self)
        return doc


def manifest_content_sha256(manifest: AcquisitionManifest) -> str:
    return strict_content_sha256(manifest.content())


# ------------------------------------------------------------------------- the run root


class RunRoot:
    """A caller-supplied directory OUTSIDE Git that holds the raw bytes and the manifest."""

    def __init__(self, root: str) -> None:
        self.root = os.path.abspath(root)
        _refuse_inside_git(self.root)
        os.makedirs(self.root, exist_ok=True)

    def store(self, data: bytes, *, source_key: str, suffix: str = "") -> tuple[str, str]:
        """Cache raw bytes, addressed by their own SHA-256. -> (relpath, sha256)."""
        sha = sha256_bytes(data)
        relpath = f"{RAW_DIR}/{_safe(source_key)}/{sha}{_safe_suffix(suffix)}"
        path = os.path.join(self.root, relpath)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if not os.path.exists(path):  # content-addressed: the same bytes are one entry
            tmp = path + ".part"
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, path)
        return relpath, sha

    def read(self, relpath: str) -> bytes:
        with open(os.path.join(self.root, relpath), "rb") as fh:
            return fh.read()

    def write_manifest(self, manifest: AcquisitionManifest, filename: str = MANIFEST_FILE) -> str:
        path = os.path.join(self.root, filename)
        tmp = path + ".part"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(manifest.as_document(), fh, indent=2, sort_keys=True)
            fh.write("\n")
        os.replace(tmp, path)
        return path


def _refuse_inside_git(root: str) -> None:
    """The run root may not be inside a Git working tree.

    A live DailyMed label committed by accident is a licensing problem that no later `git rm`
    undoes — the bytes stay in history. So the cache simply cannot be opened in the tree.
    """
    probe = root
    while True:
        if os.path.exists(os.path.join(probe, ".git")):
            raise Rejection(
                "run_root_inside_git",
                f"the run root {root!r} is inside the Git working tree at {probe!r}. Raw source "
                "bytes (live labels above all) are cached OUTSIDE Git — Git holds synthetic "
                "fixtures only. Point --run-root at a scratch or run directory.")
        parent = os.path.dirname(probe)
        if parent == probe:
            return
        probe = parent


_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def _safe(name: str) -> str:
    return _SAFE.sub("_", name)


def _safe_suffix(suffix: str) -> str:
    return "." + _safe(suffix.lstrip(".")) if suffix else ""


def verify_cached_bytes(record: AcquisitionRecord, run_root: RunRoot) -> bytes:
    """Re-hash the cached response. FAIL-CLOSED: `source_bytes_bound` -> refuse_row."""
    if not record.cache_relpath or not record.raw_sha256:
        raise Rejection(
            "acquisition_no_cached_bytes",
            f"record {record.acquisition_record_id!r} has no cached bytes to verify")
    try:
        data = run_root.read(record.cache_relpath)
    except OSError as exc:
        raise Rejection(
            "acquisition_cache_missing",
            f"the cached response for {record.acquisition_record_id!r} is not in the run root "
            f"({exc}). A record whose bytes are gone is not evidence.") from exc

    got = sha256_bytes(data)
    if got != record.raw_sha256:
        raise Rejection(
            "acquisition_raw_hash_mismatch",
            f"{record.acquisition_record_id!r}: the cached bytes hash to {got}, but the manifest "
            f"records {record.raw_sha256}. The bytes are the evidence; a record that no longer "
            "matches them is refused, not repaired.")
    if record.raw_bytes is not None and len(data) != record.raw_bytes:
        raise Rejection(
            "acquisition_raw_byte_count_mismatch",
            f"{record.acquisition_record_id!r}: {len(data)} bytes cached, {record.raw_bytes} "
            "recorded")
    return data


# ------------------------------------------------------------------------- constructors


def fixture_record(*, acquisition_record_id: str, source_key: str, raw: bytes,
                   extraction_transform: str, adapter_code_sha256: str,
                   note: Optional[str] = None) -> AcquisitionRecord:
    """A labelled synthetic response. It hashes the exact bytes the parser was handed, and it
    can never become a public record."""
    return AcquisitionRecord(
        acquisition_record_id=acquisition_record_id,
        source_key=source_key,
        source_name=f"synthetic {source_key} fixture",
        source_type="fixture",
        origin="synthetic_fixture",
        raw_bytes=len(raw),
        raw_sha256=sha256_bytes(raw),
        license="synthetic fixture (no licence: not real data)",
        extraction_transform=extraction_transform,
        adapter_code_sha256=adapter_code_sha256,
        review_status="not_applicable",
        evidence_state="not_applicable",
        note=note or "synthetic, response-shaped bytes. Not evidence about any drug.",
    )


def record_from_response(response: Any, *, run_root: RunRoot, stable_record_id: str,
                         extraction_transform: str, adapter_file: str,
                         release: str, suffix: str = "",
                         review_status: str = "unreviewed",
                         content_sha256: Optional[str] = None,
                         content_hash_rule: Optional[str] = None,
                         note: Optional[str] = None) -> AcquisitionRecord:
    """A fetched response -> a cached, hashed, terms-bound acquisition record.

    `release` is passed in by the adapter because only the adapter knows where its source puts
    one: openFDA has `meta.last_updated`, DailyMed has a per-SPL version, and PubChem PUG REST
    has none at all — which is recorded as `not_reported_by_source`, not left blank and not
    filled with a plausible-looking date.
    """
    from .public_sources import source as ledger_source

    entry = ledger_source(response.source_key)
    relpath, sha = run_root.store(response.body, source_key=response.source_key, suffix=suffix)
    return AcquisitionRecord(
        acquisition_record_id=new_record_id("acq", response.source_key, response.canonical_query),
        source_key=response.source_key,
        source_name=str(entry["source_name"]),
        source_type=str(entry["source_type"]),  # type: ignore[arg-type]
        origin="fetched_public",
        stable_record_id=stable_record_id,
        url=response.url,
        canonical_query=response.canonical_query,
        accessed_at_utc=response.accessed_at_utc,
        access_date=response.accessed_at_utc[:10],
        http_status=response.status,
        raw_media_type=response.media_type,
        response_headers=dict(response.headers),
        release_or_last_updated=release,
        license=str(entry["license"]),
        license_or_terms_url=str(entry["license_or_terms_url"]),
        license_status=str(entry["license_status"]),
        redistribution=str(entry.get("redistribution") or "bytes_cached_outside_git"),
        raw_bytes=len(response.body),
        raw_sha256=sha,
        content_sha256=content_sha256,
        content_hash_rule=content_hash_rule,
        cache_relpath=relpath,
        extraction_transform=extraction_transform,
        adapter_code_sha256=code_sha256(adapter_file),
        review_status=review_status,  # type: ignore[arg-type]
        evidence_state="observed",
        note=note,
    )


def to_source_record(record: AcquisitionRecord) -> SourceRecord:
    """The bridge into the Stage-4 evidence contract (W9's `SourceRecord`).

    Acquisition does not widen that contract — it fills it. A record with no bytes becomes
    `not_acquired`, never a hash.
    """
    if record.origin == "synthetic_fixture":
        status = AcquisitionStatus.SYNTHETIC_FIXTURE
    elif record.has_bytes:
        status = AcquisitionStatus.ACQUIRED_PUBLIC
    else:
        status = AcquisitionStatus.NOT_ACQUIRED

    access_date = (record.accessed_at_utc or "")[:10] or record.access_date or "1970-01-01"
    return SourceRecord(
        source_record_id=record.acquisition_record_id,
        source_type=record.source_type,
        source_name=record.source_name,
        acquisition_status=status,
        url=record.url,
        record_id=record.stable_record_id,
        access_date=access_date,
        release_version=record.release_or_last_updated,
        license=record.license,
        raw_sha256=record.raw_sha256,
        raw_bytes=record.raw_bytes,
        raw_media_type=record.raw_media_type,
    )


def new_record_id(prefix: str, *parts: str) -> str:
    """A content-addressed record id: the same request, re-run, is the same id."""
    return f"{prefix}_{short_id(sha256_bytes('|'.join(parts).encode('utf-8')))}"


@lru_cache(maxsize=32)
def code_sha256(module_file: str) -> str:
    """The hash of the adapter source that did the extracting.

    An extraction transform named in prose ("parsed the warnings section") is not reproducible;
    the bytes of the code that did it are. Change the adapter and every record it writes gets a
    new identity, which is the point.
    """
    with open(module_file, "rb") as fh:
        return sha256_bytes(fh.read())
