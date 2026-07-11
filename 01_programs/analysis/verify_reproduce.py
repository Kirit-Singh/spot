#!/usr/bin/env python3
"""Per-barcode reproducibility gate (continuous-score remediation, v2).

Replaces the retired aggregate-count gate (which a zero-cell overlay could pass). It
hashes a CANONICAL SORTED per-barcode table of the emitted overlay — barcode, cluster,
condition, donor, every continuous program score, method_version — with exact hashing
for identifiers and canonical float ROUNDING (a tolerance policy; raw float-byte hashes
fail across environments). It then verifies: nonzero cardinality; unique barcodes ==
row count; an exact barcode-set hash; overlay <-> records agreement within tolerance;
required score-field schema; and (once frozen) equality to the committed REFERENCE.
Exits nonzero on any failure.

Run from the app dir (reproduce.sh writes app/data/). The display-only field
`dominant_program_for_display_only` is derivable from the scores and is NOT part of the
hashed scientific table.
"""
import json, sys, hashlib
from pathlib import Path

OVERLAY = "data/stage01_umap_seed.json"
RECORDS = "data/stage01_cell_records.json"
METHOD_VERSION = "stage1-continuous-v2"
ROUND = 5  # canonical float rounding (numerical tolerance for cross-environment stability)

# Frozen AFTER the first corrected run (the freeze step). While None, the gate prints the
# computed values (to stamp) and runs the structural checks only.
REFERENCE = {
    "n_cells": 40000,
    "score_fields": ['cd4_ctl_like_score', 'cd4_ctl_like_score_actadj', 'diff_activated_score',
                     'diff_checkpoint_score', 'diff_memory_score', 'diff_naive_score', 'tfh_like_score',
                     'th17_like_score', 'th1_like_score', 'th2_like_score', 'th9_like_score', 'treg_like_score'],
    "barcode_set_sha256": "1224312e52231f4b2e07c192b39c6f9c69dd6e2d5b8bd64d936c17a9b2435a93",
    "canonical_table_sha256": "6e1665d13eab1781407b43d232d089fb5fb6a6b9df5acd83cbbfb8fe3aed2755",
}


def score_fields(overlay):
    m = overlay["meta"].get("score_fields")
    if m:
        return list(m)
    c0 = overlay["cells"][0]
    return sorted(k for k in c0 if k.endswith("_score"))


def canonical(overlay, fields):
    rows = []
    for c in overlay["cells"]:
        row = [str(c["barcode"]), str(c.get("cluster")), str(c.get("condition", "")), str(c.get("donor", ""))]
        row += [f"{round(float(c[f]), ROUND):.{ROUND}f}" for f in fields]
        rows.append("\t".join(row))
    rows.sort()
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()


def barcode_set_hash(cells):
    return hashlib.sha256("\n".join(sorted(str(c["barcode"]) for c in cells)).encode()).hexdigest()


def main():
    overlay = json.load(open(OVERLAY))
    cells = overlay["cells"]
    fail = []

    n = len(cells)
    bcs = [str(c["barcode"]) for c in cells]
    if n == 0:
        fail.append("zero cells in overlay")
    if len(set(bcs)) != n:
        fail.append(f"duplicate barcodes: {n - len(set(bcs))}")
    if overlay["meta"].get("method_version") != METHOD_VERSION:
        fail.append(f"method_version {overlay['meta'].get('method_version')!r} != {METHOD_VERSION!r}")

    fields = score_fields(overlay)
    if not fields:
        fail.append("no *_score fields found")
    for c in cells[:200]:  # schema sample
        for f in fields:
            if not isinstance(c.get(f), (int, float)):
                fail.append(f"non-numeric score {f} on barcode {c['barcode']}")
                break

    table_hash = canonical(overlay, fields) if fields and n else None
    bc_hash = barcode_set_hash(cells) if n else None

    if Path(RECORDS).exists():
        rec = json.load(open(RECORDS))
        missing = [b for b in bcs if b not in rec]
        extra = [b for b in rec if b not in set(bcs)]
        if missing:
            fail.append(f"{len(missing)} overlay barcodes missing from records")
        # (records may legitimately hold the full 396k; only require overlay ⊆ records)
        mism = 0
        for c in cells:
            r = rec.get(str(c["barcode"]), {})
            for f in fields:
                if abs(round(float(c[f]), ROUND) - round(float(r.get(f, 1e18)), ROUND)) > 10 ** -ROUND:
                    mism += 1
                    break
        if mism:
            fail.append(f"{mism} cells disagree between overlay and records")
        _ = extra  # records superset is allowed; noted, not failed
    else:
        fail.append(f"records file {RECORDS} missing")

    if REFERENCE["canonical_table_sha256"]:
        if REFERENCE["n_cells"] != n:
            fail.append(f"n_cells {n} != reference {REFERENCE['n_cells']}")
        if REFERENCE["score_fields"] != fields:
            fail.append("score_fields != reference")
        if REFERENCE["barcode_set_sha256"] != bc_hash:
            fail.append("barcode-set hash != reference")
        if REFERENCE["canonical_table_sha256"] != table_hash:
            fail.append("canonical per-barcode table hash != reference")
    else:
        print("REFERENCE not frozen yet — computed values (stamp these to freeze the gate):")
        print(f"  n_cells: {n}")
        print(f"  score_fields: {fields}")
        print(f"  barcode_set_sha256: {bc_hash}")
        print(f"  canonical_table_sha256: {table_hash}")

    if fail:
        print("VERIFY FAILED:", file=sys.stderr)
        print("\n".join("  " + x for x in fail), file=sys.stderr)
        sys.exit(1)
    print(f"OK — {n} cells; per-barcode table verified "
          f"(hash {table_hash[:16]}…); overlay↔records agree; schema + barcode-set intact.")


if __name__ == "__main__":
    main()
