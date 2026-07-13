"""Cache warming from W16's Direct-prefix prefetch manifest. Bytes only — never evidence.

This exists to spend the waiting time usefully: fetch the public responses a candidate queue will
need, into the content-addressed cache, so that when the real Stage-3 analysis bundle is admitted
the acquisition is a cache replay instead of an hour of network.

It is deliberately a DEAD END with respect to Stage 4:

  * it does **not** take a Stage-3 bundle, does not admit anything, and implies **no** production
    admission. It reads W16's prefetch manifest and nothing else;
  * it writes **no acquisition manifest** — only a prefetch receipt and the raw cache. Stage-4
    materialization reads `acquisition_manifest.json`; there is none here, so a warmed cache
    cannot walk into materialization on its own;
  * every record it would have built is stamped `prefetch_only`, and `assert_not_prefetch_only`
    refuses such a record at the materialization/admission door. Two independent walls, because
    one of them is a convention and conventions get refactored away.

**Re-binding is the point, not a workaround.** The cache is keyed on the CANONICAL QUERY, so when
the admitted bundle finally lands, `run_acquire` asks the same questions, gets the same bytes back
from the cache, and builds records bound to THAT bundle — with the access time of the fetch that
really happened, never re-stamped. The prefetch never decides what the evidence means; it only
means the bytes are already local.

**It does not run before W16 supplies the manifest.** No manifest, or a manifest that does not
declare itself prefetch-only and bound to a Direct run, is a refusal.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .acquire_cache import RequestCache
from .acquire_http import Client
from .acquire_pool import bounded_map
from .acquisition import RunRoot
from .canonical import strict_content_sha256
from .firewall import Rejection
from .prefetch_verify import VerifiedPrefetchManifest, verify_prefetch_manifest

MAX_CONCURRENCY = 4
RECEIPT = "prefetch_receipt.json"
PREFETCH_ONLY = "prefetch_only"

# What W16's manifest must declare before a single byte is fetched. A prefetch that cannot say
# which Direct run it belongs to is not bound to anything, and its cache could not be re-bound.
# The binding that lets a warmed cache be re-tied to what it was warmed for.
BINDING_KEYS = ("universe_store", "method_id", "schema_version")


@dataclass
class PrefetchOutcome:
    candidate_id: str
    moiety_name: str
    status: str                      # acquired | not_found | error
    detail: str = ""
    requests: list[dict[str, Any]] = field(default_factory=list)


def load_prefetch_manifest(path: str, *, expect_raw_sha256: Optional[str] = None,
                           expect_content_sha256: Optional[str] = None
                           ) -> VerifiedPrefetchManifest:
    """W16's manifest, INDEPENDENTLY verified, or a refusal. Nothing is fetched before this."""
    return verify_prefetch_manifest(path, expect_raw_sha256=expect_raw_sha256,
                                    expect_content_sha256=expect_content_sha256)


def work_list(verified: VerifiedPrefetchManifest) -> list[dict[str, Any]]:
    """The DISTINCT molecules to warm, in identity order. 455 rows carry 439 molecules; asking the
    same question twice is not more evidence, it is more load on someone else's server."""
    seen: dict[str, dict[str, Any]] = {}
    for record in verified.document["records"]:
        key = str(record["machine_lookup_key"])
        if key in seen:
            continue
        seen[key] = {
            "candidate_id": key,
            "moiety_name": str(record["molecule_pref_name"]),
            "source_locator": record.get("source_locator"),
            "source_release": record.get("source_release"),
        }
    return [seen[k] for k in sorted(seen)]


def prefetch_one(client: Client, run_root: RunRoot, candidate: dict[str, Any]) -> PrefetchOutcome:
    """Warm the cache for ONE candidate. A miss is counted, never fatal to the queue."""
    from .dailymed_select import acquire_label, acquire_rxcui
    from .openfda_approval import acquire_approval
    from .pubchem import acquire_pubchem_identity

    candidate_id = str(candidate.get("candidate_id") or "")
    name = str(candidate.get("moiety_name") or candidate.get("preferred_name") or "").strip()
    if not name:
        return PrefetchOutcome(candidate_id, "", "error",
                               "the manifest row carries no moiety name, so no public source can "
                               "be asked about it. Stage 4 does not guess a drug name.")

    verified: list[dict[str, Any]] = []

    def check(records: Any) -> None:
        """Every request/response/source/hash, verified as it arrives."""
        from .acquisition import verify_cached_bytes

        for rec in records if isinstance(records, list) else [records]:
            verify_cached_bytes(rec, run_root)       # the cache holds what was hashed
            verified.append({
                "source_key": rec.source_key,
                "url": rec.url,
                "canonical_query": rec.canonical_query,
                "http_status": rec.http_status,
                "raw_media_type": rec.raw_media_type,
                "raw_bytes": rec.raw_bytes,
                "raw_sha256": rec.raw_sha256,
                "release_or_last_updated": rec.release_or_last_updated,
                "license_or_terms_url": rec.license_or_terms_url,
                "accessed_at_utc": rec.accessed_at_utc,
                "cache_relpath": rec.cache_relpath,
            })

    try:
        _, records = acquire_pubchem_identity(client, run_root, name)
        check(records)
        _, rx = acquire_rxcui(client, run_root, name)
        check(rx)
        _, label_records = acquire_label(client, run_root, name,
                                         setid=candidate.get("dailymed_setid"))
        check(label_records)
        # The approval chain too. Warming only part of the chain leaves the replay half-cold, and
        # the acquisition that follows would still go to the network for the rest.
        _, approval_records = acquire_approval(client, run_root, _setid_of(label_records))
        check(approval_records)
    except Rejection as exc:
        status = "not_found" if exc.code.endswith(("_not_found", "_ambiguous")) else "error"
        return PrefetchOutcome(candidate_id, name, status, f"[{exc.code}] {exc.detail}", verified)

    return PrefetchOutcome(candidate_id, name, "acquired",
                           f"{len(verified)} response(s) cached", verified)


def _setid_of(label_records: list[Any]) -> str:
    """The set ID of the SPL that was actually served — not one we assumed."""
    spl = next(r for r in label_records if (r.raw_media_type or "").endswith("xml"))
    return str(spl.stable_record_id)


def run_prefetch(manifest_path: str, run_root_dir: str, *, client: Optional[Client] = None,
                 max_workers: int = MAX_CONCURRENCY,
                 expect_raw_sha256: Optional[str] = None,
                 expect_content_sha256: Optional[str] = None) -> dict[str, Any]:
    """Warm the cache. Emits a receipt and a cache — never an acquisition manifest."""
    verified = load_prefetch_manifest(manifest_path, expect_raw_sha256=expect_raw_sha256,
                                      expect_content_sha256=expect_content_sha256)
    manifest = verified.document
    run_root = RunRoot(run_root_dir)
    cache = RequestCache(run_root)
    http = client or Client(allow_network=True, cache=cache)
    # An injected client MUST get the cache too. Without this the warm-up fetches bytes but never
    # files them under their canonical query — so the replay that is the entire point of warming
    # would silently not happen, and the run would look successful.
    if getattr(http, "cache", None) is None:
        http.cache = cache

    todo = work_list(verified)
    started = time.monotonic()
    outcomes = bounded_map(
        todo, lambda c: prefetch_one(http, run_root, c), max_workers=max_workers)
    elapsed = time.monotonic() - started

    counts = {"acquired": 0, "not_found": 0, "error": 0}
    for outcome in outcomes:
        counts[outcome.status] += 1

    receipt: dict[str, Any] = {
        "schema_id": "spot.stage04_prefetch_receipt.v1",
        # THE WALL. This document is not evidence and cannot become evidence.
        "prefetch_only": True,
        "stage4_admissible": False,
        "stage3_admission_required": False,
        "stage3_admission_implied": False,
        "bound_to": {
            "manifest_id": verified.manifest_id,
            "manifest_raw_sha256": verified.raw_sha256,
            "manifest_content_sha256": verified.content_sha256,
            "artifact_class": verified.artifact_class,
            "method_id": verified.method_id,
            **{k: manifest[k] for k in BINDING_KEYS if isinstance(manifest.get(k), str)},
        },
        "n_manifest_records": verified.n_records,
        "n_distinct_molecules": len(todo),
        "counts": counts,
        "n_candidates": len(outcomes),
        "n_responses_cached": sum(len(o.requests) for o in outcomes),
        "transport": {"fetched": http.n_fetched, "reused_from_cache": http.n_reused,
                      "max_workers": max_workers, "cache_entries": cache.n_entries()},
        "elapsed_seconds": round(elapsed, 2),
        "candidates": [
            {"candidate_id": o.candidate_id, "moiety_name": o.moiety_name, "status": o.status,
             "detail": o.detail, "requests": o.requests}
            for o in outcomes
        ],
        "hard_rules": [
            "Cache warming only. This receipt is not evidence and never becomes an evidence "
            "bundle.",
            "It neither requires nor implies Stage-3 production admission.",
            "No acquisition manifest is written, so Stage-4 materialization cannot read it.",
            "Substitution re-binds these cached BYTES to the final admitted Stage-3 analysis "
            "bundle; the cache is keyed on the canonical query, and a reused response keeps the "
            "access time of the fetch that really happened.",
            "No drug is ranked and no PK value is invented.",
        ],
    }
    # The receipt's own content hash: what was warmed, addressable.
    hashable = {k: v for k, v in receipt.items() if k not in ("elapsed_seconds", "transport")}
    receipt["content_sha256"] = strict_content_sha256(hashable)

    path = os.path.join(run_root.root, RECEIPT)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh, indent=2, sort_keys=True)
        fh.write("\n")

    # Belt and braces: warming must never leave something materialization could pick up.
    assert not os.path.exists(os.path.join(run_root.root, "acquisition_manifest.json")), (
        "a prefetch run wrote an acquisition manifest. That is the one thing it must never do.")
    return receipt


def assert_not_prefetch_only(document: dict[str, Any]) -> None:
    """The door. A prefetch artifact may not enter Stage-4 materialization or admission."""
    if document.get(PREFETCH_ONLY) is True or document.get("stage4_admissible") is False:
        raise Rejection(
            "prefetch_only_artifact_refused",
            "this document is a PREFETCH artifact: it warmed a cache and was never bound to an "
            "admitted Stage-3 analysis bundle. It cannot enter Stage-4 materialization or "
            "admission. Re-run the acquisition against the admitted bundle — the cached bytes "
            "will be reused, so it costs nothing but is bound to something real.")


def main(argv: Optional[list[str]] = None, *, client: Optional[Client] = None) -> int:
    ap = argparse.ArgumentParser(prog="run_prefetch", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prefetch-manifest", required=True,
                    help="W16's Direct-prefix, prefetch-only candidate manifest")
    ap.add_argument("--run-root", required=True, help="content-addressed cache, OUTSIDE the tree")
    ap.add_argument("--max-concurrency", type=int, default=MAX_CONCURRENCY)
    ap.add_argument("--expect-raw-sha256", help="refuse unless the file hashes to exactly this")
    ap.add_argument("--expect-content-sha256", help="refuse unless the content hashes to this")
    args = ap.parse_args(argv)

    try:
        receipt = run_prefetch(args.prefetch_manifest, args.run_root, client=client,
                               max_workers=args.max_concurrency,
                               expect_raw_sha256=args.expect_raw_sha256,
                               expect_content_sha256=args.expect_content_sha256)
    except Rejection as exc:
        print(f"REFUSED [{exc.code}] {exc.detail}", file=sys.stderr)
        return 2

    c = receipt["counts"]
    print("prefetch (CACHE WARMING ONLY — not evidence, not admissible to Stage 4)")
    print(f"  bound to        : {receipt['bound_to']}")
    print(f"  candidates      : {receipt['n_candidates']}")
    print(f"  acquired        : {c['acquired']}")
    print(f"  not_found       : {c['not_found']}")
    print(f"  error           : {c['error']}")
    print(f"  responses cached: {receipt['n_responses_cached']} "
          f"(fetched={receipt['transport']['fetched']} "
          f"reused={receipt['transport']['reused_from_cache']})")
    print(f"  cache path      : {os.path.abspath(args.run_root)}")
    print(f"  receipt hash    : {receipt['content_sha256']}")
    print(f"  elapsed         : {receipt['elapsed_seconds']}s")
    print("\nNo Stage-4 artifact was produced and no Stage-3 admission was performed or implied.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
