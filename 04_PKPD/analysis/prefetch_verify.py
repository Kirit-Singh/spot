"""Independently verify W16's prefetch manifest before a single byte is fetched.

The first manifest (`353b7920`) declared bindings it did not have: independent inspection found
`source_locator` and `source_release` null in 455/455 rows and no molecule name at all. Its handoff
said otherwise. That is exactly why this module exists and why it RE-DERIVES rather than reads:

  * the **raw** SHA-256 of the file on disk;
  * the **self/content** hash, recomputed from the bytes under the manifest's own declared rule
    (canonical JSON, sorted keys, compact separators, ASCII, with the self-referential fields —
    `manifest_sha256`, `manifest_id`, `created_at` — excluded, since a document cannot contain its
    own hash);
  * `artifact_class == prefetch_only`, and that the manifest does **not** claim it may be admitted
    as a Stage-3 analysis, carry a score/rank, or permit a combined objective;
  * that EVERY record carries what the handoff promises: a source locator, a source release, a
    source-verbatim molecule name, and a machine lookup key with a stated status. A row that does
    not is refused — the count in `counts` is not taken on trust either, it is recounted.

A stale manifest is refused BY HASH. `353b7920` cannot be consumed by accident even if someone
points this at the old file.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any

from .firewall import Rejection

# Superseded, and refused by hash. Not "please don't use it" — cannot be used.
STALE_MANIFEST_IDS = frozenset({"353b7920"})

PREFETCH_CLASS = "prefetch_only"

# The self-referential fields a document cannot contain when hashing itself.
SELF_FIELDS = ("manifest_sha256", "manifest_id", "created_at")

# What every record must carry. The first manifest carried none of them.
REQUIRED_RECORD_FIELDS = (
    "source_locator", "source_release", "molecule_pref_name",
    "machine_lookup_key", "machine_lookup_key_kind", "lookup_key_status",
)

# Claims a prefetch manifest must NOT make.
FORBIDDEN_CLAIMS = {
    "may_be_admitted_as_a_stage3_analysis": False,
    "combined_objective_permitted": False,
    "cross_arm_ordering_permitted": False,
    "carries_no_score_or_rank": True,
}


@dataclass(frozen=True)
class VerifiedPrefetchManifest:
    path: str
    manifest_id: str
    raw_sha256: str
    content_sha256: str
    artifact_class: str
    method_id: str
    n_records: int
    document: dict[str, Any]


def content_sha256(document: dict[str, Any]) -> str:
    """Re-derive the manifest's self hash from its own content. No trust involved."""
    body = {k: v for k, v in document.items() if k not in SELF_FIELDS}
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def verify_prefetch_manifest(path: str, *, expect_raw_sha256: str | None = None,
                             expect_content_sha256: str | None = None
                             ) -> VerifiedPrefetchManifest:
    """Admit the manifest, or refuse it. Nothing is fetched until this returns."""
    if not os.path.isfile(path):
        raise Rejection("prefetch_manifest_missing", f"no prefetch manifest at {path!r}")

    with open(path, "rb") as fh:
        raw = fh.read()
    raw_sha = hashlib.sha256(raw).hexdigest()
    if expect_raw_sha256 and raw_sha != expect_raw_sha256:
        raise Rejection(
            "prefetch_manifest_raw_hash_mismatch",
            f"the file hashes to {raw_sha}, but {expect_raw_sha256} was expected. These are not "
            "the bytes that were handed over.")

    document = json.loads(raw.decode("utf-8"))

    manifest_id = str(document.get("manifest_id") or "")
    if manifest_id in STALE_MANIFEST_IDS or any(
            manifest_id.startswith(s) for s in STALE_MANIFEST_IDS):
        raise Rejection(
            "prefetch_manifest_superseded",
            f"manifest {manifest_id!r} is SUPERSEDED and refused by hash. It declared bindings it "
            "did not have (null source_locator/source_release in every row, no molecule name). "
            "Use the replacement.")

    # --- the self hash, RE-DERIVED --------------------------------------------------
    declared = str(document.get("manifest_sha256") or "")
    derived = content_sha256(document)
    if not declared:
        raise Rejection("prefetch_manifest_unhashed",
                        "the manifest declares no manifest_sha256, so nothing binds its content.")
    if derived != declared:
        raise Rejection(
            "prefetch_manifest_content_hash_mismatch",
            f"the manifest's content hashes to {derived}, but it declares {declared}. Its content "
            "is not what it says it is.")
    if expect_content_sha256 and derived != expect_content_sha256:
        raise Rejection(
            "prefetch_manifest_content_hash_mismatch",
            f"content hash {derived} != the expected {expect_content_sha256}")
    if manifest_id and not declared.startswith(manifest_id):
        raise Rejection(
            "prefetch_manifest_id_mismatch",
            f"manifest_id {manifest_id!r} is not the prefix of its own content hash {declared}")

    # --- the class, and the claims it must NOT make ---------------------------------
    artifact_class = str(document.get("artifact_class") or "")
    if artifact_class != PREFETCH_CLASS:
        raise Rejection(
            "prefetch_manifest_wrong_class",
            f"artifact_class={artifact_class!r}; this runner consumes {PREFETCH_CLASS!r} only. A "
            "document that is not a prefetch work-list is not warmed here.")
    for claim, required in FORBIDDEN_CLAIMS.items():
        if claim in document and document[claim] is not required:
            raise Rejection(
                "prefetch_manifest_overclaims",
                f"the manifest declares {claim}={document[claim]!r}; a prefetch work-list must "
                f"declare {required!r}. It is a work list, not a result.")

    # --- every record carries what the handoff promised. Recounted, not trusted. ------
    records = document.get("records")
    if not isinstance(records, list) or not records:
        raise Rejection("prefetch_manifest_empty", "the manifest carries no records")

    incomplete: list[str] = []
    for i, record in enumerate(records):
        missing = [f for f in REQUIRED_RECORD_FIELDS if not record.get(f)]
        if missing:
            incomplete.append(f"row {i} ({record.get('machine_lookup_key') or '?'}): {missing}")
        if len(incomplete) >= 5:
            break
    if incomplete:
        raise Rejection(
            "prefetch_manifest_records_incomplete",
            f"{len(incomplete)}+ record(s) are missing required bindings — the exact defect the "
            f"superseded manifest had: {'; '.join(incomplete)}")

    counts = document.get("counts") or {}
    declared_n = counts.get("n_prefetch_records")
    if declared_n is not None and int(declared_n) != len(records):
        raise Rejection(
            "prefetch_manifest_count_mismatch",
            f"counts.n_prefetch_records={declared_n} but the document carries {len(records)} "
            "records. A count that does not match the rows is not a count.")
    declared_null = counts.get("n_records_with_no_source_locator")
    actual_null = sum(1 for r in records if not r.get("source_locator"))
    if declared_null is not None and int(declared_null) != actual_null:
        raise Rejection(
            "prefetch_manifest_count_mismatch",
            f"counts.n_records_with_no_source_locator={declared_null} but {actual_null} rows have "
            "no locator.")

    return VerifiedPrefetchManifest(
        path=os.path.abspath(path),
        manifest_id=manifest_id,
        raw_sha256=raw_sha,
        content_sha256=derived,
        artifact_class=artifact_class,
        method_id=str(document.get("method_id") or ""),
        n_records=len(records),
        document=document,
    )
