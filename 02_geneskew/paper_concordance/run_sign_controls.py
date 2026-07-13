"""CLI: run the sign-control re-derivation on the pinned DE object, fail-closed on hash.

Records input hashes, emits the diagnostic report. NON-RANKING, NON-GATING: the report is
never a production output, and upstream FDR stays inside provenance_diagnostics.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import sign_derivation as sd            # noqa: E402
from de_accessor import DEAccessor      # noqa: E402


def file_sha256(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--de", required=True)
    ap.add_argument("--spec", required=True)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)

    with open(a.spec) as fh:
        spec = json.load(fh)
    de_sha = file_sha256(a.de)
    pin = spec["source"]["de_object"]["sha256"]
    if de_sha != pin:                          # fail-closed on a byte-drifted DE object
        print(f"FAIL: DE sha256 {de_sha} != spec pin {pin}", file=sys.stderr)
        return 2

    acc = DEAccessor(a.de)
    try:
        report = sd.derive_all(spec, observe=acc.observe)
    finally:
        acc.close()

    report["inputs"] = {
        "de_object_basename": os.path.basename(a.de), "de_object_sha256": de_sha,
        "spec_sha256": file_sha256(a.spec), "matches_spec_pin": de_sha == pin,
        "authors_code_commit": spec["source"]["authors_code_commit"],
        "preprint_doi": spec["source"]["preprint"]["doi"]}
    report["tissue_organ_axis"] = spec["tissue_organ_axis"]
    report["provenance_diagnostics_policy"] = spec["provenance_diagnostics_policy"]
    report["classification"] = "diagnostic_non_gating"
    with open(a.out, "w") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)

    dirs = [r for r in report["results"] if r["kind"] == "directional"]
    broad = [r for r in report["results"] if r["kind"] == "broad_effect"]
    n_conc = sum(1 for r in dirs if r["outcome"]["concordant_significant"])
    print(json.dumps({
        "de_sha_matches_pin": de_sha == pin,
        "directional_controls_concordant": f"{n_conc}/{len(dirs)}",
        "directional_discordant": [r["control_id"] for r in dirs
                                   if not r["outcome"]["concordant_significant"]],
        "broad_effect_confirmed": sum(1 for r in broad if r["outcome"]["broad"]),
        "out": a.out}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
