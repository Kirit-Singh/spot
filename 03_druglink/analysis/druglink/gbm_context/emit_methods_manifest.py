"""Emit the Stage-3 (Drugs) Methods & Provenance drawer payload from the run handoff.

Derives the Open Targets retrieval time + the content address of the pinned response set
STRAIGHT from the handoff's own recorded provenance — never re-typed by hand — then writes the
canonical manifest and reports its sha256 for W12 to pin in STAGE_METHODS_HASHES.drugs.
"""
from __future__ import annotations

import argparse
import json
import sys

from .methods_manifest import build_manifest, canonical_json, content_sha256


def from_handoff(handoff: dict) -> dict:
    """Build the manifest using only values traced in the handoff."""
    rp = handoff["run_provenance"]
    artifacts = handoff["raw_response_artifacts"]
    if not artifacts:
        raise SystemExit("handoff pins no raw Open Targets responses — refusing to emit a "
                         "manifest that would claim untraceable disease numbers")
    return build_manifest(
        ot_retrieval_utc=rp["run_timestamp_utc"],
        ot_response_set_canonical_sha256=content_sha256(artifacts))


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--handoff", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    with open(a.handoff) as fh:
        handoff = json.load(fh)
    manifest = from_handoff(handoff)
    raw = canonical_json(manifest)
    with open(a.out, "w", encoding="utf-8") as fh:
        fh.write(raw)
    print(json.dumps({
        "out": a.out,
        "content_sha256": content_sha256(manifest),
        "bytes": len(raw.encode("utf-8")),
        "stage_label": manifest["stage_label"],
        "source_chain": [s["record_id"] for s in manifest["provenance"]["source_chain"]],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
