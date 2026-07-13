"""FIND a content-addressed bundle. Never guess its path.

A bundle's directory is its RUN ID, and a run id is a hash of everything that produced it — so
nobody can know it before the run. A runbook that wrote `direct-Rest/` would be inventing a
name the producer never used, and the first thing it would do is fail to find the bundle; the
second, worse thing it could do is find a STALE one from an earlier run that happened to sit
where the guess pointed.

So the bundle is DISCOVERED: scan the output root, read each `provenance.json`, and select the
one whose binding actually says it is this condition. Fail-closed at both ends —

  * NO match      -> refuse. The dependency this run needs was never produced.
  * MANY matches  -> refuse, and NAME them. Two bundles for one condition means two different
                    runs are on disk and nothing here can know which one the caller meant. A
                    "pick the newest" rule would silently choose, and a silent choice between
                    two scientific artifacts is the thing this whole lane exists to prevent.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Optional

REFUSE_NOT_FOUND = "dependency_bundle_not_found"
REFUSE_AMBIGUOUS = "dependency_bundle_is_ambiguous"

PROVENANCE_BY_KIND = {
    "direct": "provenance.json",
    "pathway": "pathway_provenance.json",
}
RUN_ID_BY_KIND = {
    "direct": "arm_bundle_run_id",
    "pathway": "pathway_run_id",
}


class BundleIndexError(ValueError):
    def __init__(self, gate: str, message: str):
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


def _candidates(root: str, kind: str) -> list[dict[str, Any]]:
    prov_name = PROVENANCE_BY_KIND[kind]
    out = []
    if not os.path.isdir(root):
        return out
    for name in sorted(os.listdir(root)):
        path = os.path.join(root, name, prov_name)
        if not os.path.exists(path):
            continue
        try:
            with open(path) as fh:
                doc = json.load(fh)
        except (OSError, json.JSONDecodeError):
            continue
        out.append({"dir": os.path.join(root, name), "provenance": doc})
    return out


def find(root: str, *, condition: str, kind: str = "direct",
         source: Optional[str] = None) -> dict[str, Any]:
    """THE bundle for this condition. Refuses on none, and refuses on more than one."""
    hits = []
    for c in _candidates(root, kind):
        binding = c["provenance"].get("run_binding", {})
        if str(binding.get("condition")) != str(condition):
            continue
        if source is not None and str(binding.get("source")) != str(source):
            continue
        hits.append(c)

    what = f"{kind} bundle for condition {condition!r}" + (
        f" / source {source!r}" if source else "")
    if not hits:
        raise BundleIndexError(
            REFUSE_NOT_FOUND,
            f"no {what} under {root!r}. It is a DEPENDENCY of the step that asked for it, and "
            "a step whose input was never produced cannot be run — least of all with a guessed "
            "path, which would either find nothing or find something from another run")
    if len(hits) > 1:
        ids = [os.path.basename(h["dir"]) for h in hits]
        raise BundleIndexError(
            REFUSE_AMBIGUOUS,
            f"{len(hits)} {what} under {root!r}: {ids}. Two bundles for one context means two "
            "different runs are on disk, and nothing here can know which one was meant. "
            "Choosing the newest would be choosing between two scientific artifacts silently")

    hit = hits[0]
    prov = hit["provenance"]
    return {
        "dir": hit["dir"],
        "run_id": prov.get(RUN_ID_BY_KIND[kind]),
        "condition": condition,
        "source": source,
        "provenance_path": os.path.join(hit["dir"], PROVENANCE_BY_KIND[kind]),
    }


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m direct.bundle_index",
        description="Print the directory of the content-addressed bundle for a context. "
                    "Refuses if it is absent or ambiguous — a runbook may not guess a run id.")
    ap.add_argument("--root", required=True)
    ap.add_argument("--condition", required=True)
    ap.add_argument("--kind", default="direct", choices=sorted(PROVENANCE_BY_KIND))
    ap.add_argument("--source", default=None)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        hit = find(args.root, condition=args.condition, kind=args.kind, source=args.source)
    except BundleIndexError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(hit["dir"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
