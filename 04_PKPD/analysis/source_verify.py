"""Re-hash the method's cited source documents, from any machine.

    python -m analysis.source_verify [--cache-root DIR] [--json]

The previous registry recorded one developer's absolute paths
(`/home/tcelab/.spot-runs/.../PMC13338342.bioc.xml`). That verifies exactly one machine.
On any other checkout the documents simply were not there, and nothing said so.

So: entries now carry a public `retrieval_url` and a bare `cache_filename`, the cache root
is supplied at call time (`--cache-root`, or `$SPOT_SOURCE_CACHE`), and acquisition status
is reported EXPLICITLY per source:

    verified       the cached bytes hash to the recorded raw_sha256
    MISMATCH       the bytes are there and are NOT what the method was built from
    not_cached     no bytes here; re-fetch from retrieval_url and re-run
    not_acquired   the registry itself records that these bytes were never obtained
                   (wager2016_cnsmpo_desirability). Nothing is validated against them.

Exit code is non-zero only on MISMATCH. A missing cache is not a failure — the documents
are deliberately not bundled (copyright; "public data only, nothing bundled") — but it is
never silently reported as success either.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from typing import Any, Optional

from .method_config import METHOD_DIR

CACHE_ROOT_ENV = "SPOT_SOURCE_CACHE"


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _entries(sources: dict[str, Any]) -> list[dict[str, Any]]:
    """One row per hashable document, including each structure probe."""
    out: list[dict[str, Any]] = []
    for s in sources["sources"]:
        sid = s["source_id"]
        if s.get("document_acquired") is False:
            out.append({
                "source_id": sid, "status": "not_acquired",
                "cache_filename": None, "retrieval_url": s.get("doi"),
                "declared_sha256": None, "recomputed_sha256": None,
                "note": s.get("acquisition_blocked_by", "the registry records no bytes"),
            })
            continue
        if s.get("raw_sha256"):
            out.append({
                "source_id": sid, "status": None,
                "cache_filename": s.get("cache_filename"),
                "retrieval_url": s.get("retrieval_url") or s.get("url"),
                "declared_sha256": s["raw_sha256"], "recomputed_sha256": None,
                # Where present, THIS is the scientific identity; raw_sha256 is one fetch.
                "declared_content_sha256": s.get("content_sha256"),
                "recomputed_content_sha256": None,
            })
        for probe in s.get("probes", []) or []:
            out.append({
                "source_id": f"{sid}::{probe['setid'][:8]}", "status": None,
                "cache_filename": probe.get("cache_filename"),
                "retrieval_url": probe.get("retrieval_url"),
                "declared_sha256": probe["raw_sha256"], "recomputed_sha256": None,
            })
    return out


def _content_sha256(raw: bytes) -> str:
    """The document with the PMC BioC envelope's retrieval-date element blanked.

    Restated here rather than imported from `nebpi_source`, so a source-registry check does not
    depend on the NEBPI extractor.
    """
    import hashlib
    import re

    return hashlib.sha256(
        re.sub(rb"<date>\s*\d{8}\s*</date>", b"<date></date>", raw, count=1)).hexdigest()


def verify_sources(cache_root: Optional[str] = None,
                   method_dir: str = METHOD_DIR) -> dict[str, Any]:
    """-> a report. Never claims a document is verified without hashing its bytes."""
    with open(os.path.join(method_dir, "sources.json"), encoding="utf-8") as fh:
        sources = json.load(fh)

    root = cache_root or os.environ.get(CACHE_ROOT_ENV)
    rows = _entries(sources)

    for row in rows:
        if row["status"] == "not_acquired":
            continue
        if not root or not row["cache_filename"]:
            row["status"] = "not_cached"
            row["note"] = ("no cache root supplied"
                           if not root else "no cache_filename in the registry")
            continue
        path = os.path.join(root, row["cache_filename"])
        if not os.path.exists(path):
            row["status"] = "not_cached"
            row["note"] = f"not in {root}; re-fetch from retrieval_url"
            continue
        actual = _sha256_file(path)
        row["recomputed_sha256"] = actual

        # A source may declare a CONTENT hash as well as a raw byte hash. Where it does, the
        # content hash is the scientific identity and the raw hash is a snapshot of one fetch.
        #
        # The PMC BioC endpoint stamps the RETRIEVAL DATE into the envelope of every response,
        # so the raw bytes of an unchanged paper differ by one byte every day. A registry that
        # pinned only the raw hash would report MISMATCH on an untouched document daily — which
        # trains a reviewer to ignore the one signal that is supposed to stop a tamper.
        if row.get("declared_content_sha256"):
            with open(path, "rb") as fh:
                content = _content_sha256(fh.read())
            row["recomputed_content_sha256"] = content
            if content == row["declared_content_sha256"]:
                row["status"] = "verified"
                if actual != row["declared_sha256"]:
                    row["note"] = (
                        "raw bytes differ from the pinned snapshot but the CONTENT hash matches: "
                        "this is the API's retrieval-date envelope, not a change to the article.")
            else:
                row["status"] = "MISMATCH"
                row["note"] = "the document CONTENT does not hash to what the registry declares"
            continue

        row["status"] = "verified" if actual == row["declared_sha256"] else "MISMATCH"

    counts = {s: sum(1 for r in rows if r["status"] == s)
              for s in ("verified", "MISMATCH", "not_cached", "not_acquired")}
    return {
        "schema_id": "spot.stage04_source_verification.v1",
        "cache_root": root,
        "cache_root_env": CACHE_ROOT_ENV,
        "counts": counts,
        "status": "fail" if counts["MISMATCH"] else "pass",
        "sources": rows,
        "note": (
            "Raw documents are not bundled in this repository. `not_cached` means the bytes "
            "are not on THIS machine, not that they are wrong; re-fetch from retrieval_url. "
            "`not_acquired` means the bytes were never obtained at all, and nothing in the "
            "method is validated against them."
        ),
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="source_verify", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cache-root", help=f"directory of cached source bytes (or ${CACHE_ROOT_ENV})")
    ap.add_argument("--json", action="store_true", help="emit the machine-readable report")
    args = ap.parse_args(argv)

    report = verify_sources(args.cache_root)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"cache_root : {report['cache_root'] or '(none supplied)'}")
        for row in report["sources"]:
            print(f"  {row['status']:<12} {row['source_id']}")
            if row["status"] == "MISMATCH":
                print(f"      declared   {row['declared_sha256']}")
                print(f"      recomputed {row['recomputed_sha256']}")
        c = report["counts"]
        print(f"\nverified={c['verified']} mismatch={c['MISMATCH']} "
              f"not_cached={c['not_cached']} not_acquired={c['not_acquired']}")
    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    raise SystemExit(main())
