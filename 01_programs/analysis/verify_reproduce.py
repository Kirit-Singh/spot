#!/usr/bin/env python3
"""Per-barcode reproducibility + schema-contract gate (continuous-score remediation, v2).

Two guarantees:

  1. SCIENCE FROZEN — the canonical per-barcode table (barcode, cluster, condition, donor,
     the 12 continuous scores, rounded to 5 dp) hashes to the committed REFERENCE, as does
     the barcode set. If either moves, the gate STOPS and names which scientific value
     changed. A schema-only display cleanup must NOT move these hashes.

  2. SCHEMA CLEAN — the served overlay is validated against an explicit whitelist: exact
     allowed cell keys, forbidden retired fields, a required meta schema, the programs[]
     contract, and frozen display domains — over EVERY cell, not a sample. Served artifacts
     (overlay, records, and the app HTML/trace/notebook if present) are scanned for retired
     strings from the withdrawn categorical pipeline.

Exits nonzero on any failure. Run from the app dir (reproduce.sh writes app/data/).
"""
import json, sys, hashlib, re
from pathlib import Path

OVERLAY = "data/stage01_umap_seed.json"
RECORDS = "data/stage01_cell_records.json"
METHOD_VERSION = "stage1-continuous-v2"
SCHEMA_VERSION = "stage1-overlay-v3-schema"
ROUND = 5

REFERENCE = {
    "n_cells": 40000,
    "score_fields": ['cd4_ctl_like_score', 'cd4_ctl_like_score_actadj', 'diff_activated_score',
                     'diff_checkpoint_score', 'diff_memory_score', 'diff_naive_score', 'tfh_like_score',
                     'th17_like_score', 'th1_like_score', 'th2_like_score', 'th9_like_score', 'treg_like_score'],
    "barcode_set_sha256": "1224312e52231f4b2e07c192b39c6f9c69dd6e2d5b8bd64d936c17a9b2435a93",
    "canonical_table_sha256": "6e1665d13eab1781407b43d232d089fb5fb6a6b9df5acd83cbbfb8fe3aed2755",
}

# cell key whitelist = identifiers + the 12 frozen score fields. Nothing else may appear.
ALLOWED_CELL_KEYS = {"barcode", "x", "y", "cluster", "condition", "donor", *REFERENCE["score_fields"]}
# explicit retired cell fields (a subset of "unexpected", flagged with a clear message)
FORBIDDEN_CELL_KEYS = {"treg_score", "func_margin", "low_conf", "dominant_program_for_display_only",
                       "func", "ds", "funcc", "dsc", "top_program"}
FORBIDDEN_KEY_SUBSTR = ("p_value", "q_value", "qval", "fdr", "nomen", "perm", "null")
REQUIRED_META_KEYS = ["schema_version", "method_version", "source", "genome", "scoring_universe_n",
                      "display_n", "design", "embedding", "score_fields", "programs",
                      "score_display_domains", "verification", "methods_and_scope"]
FORBIDDEN_META_KEYS = {"clusters", "nomen_counts", "nomen_method", "match_pct",
                       "treg_module_genes", "cluster_method"}
PROGRAM_FIELDS = {"score_field", "display_label", "family", "panel_genes", "scoring_method",
                  "role", "display_domain", "source"}
VALID_FAMILIES = {"differentiation", "functional", "sensitivity"}
# retired-pipeline strings that must not survive in any served artifact
STALE_STRINGS = ["N_PERM", "paper-exact", "reproduces Suppl", "Reproduces Suppl", "Suppl Fig 2",
                 "full executable notebook", "Treg 2.6%", "CD4-CTL 1.4%", "dominant_program_for_display_only",
                 "treg_score", "func_margin", "low_conf", "nomen_counts", "empirical p", "q<0.05",
                 "permutation-FDR", "permutation FDR"]
SERVED_TEXT_ARTIFACTS = ["data/stage01_umap_seed.json", "data/stage01_cell_records.json",
                         "programs.html", "01_trace.html", "01_notebook.html"]


def canonical(cells, fields):
    rows = []
    for c in cells:
        row = [str(c["barcode"]), str(c.get("cluster")), str(c.get("condition", "")), str(c.get("donor", ""))]
        row += [f"{round(float(c[f]), ROUND):.{ROUND}f}" for f in fields]
        rows.append("\t".join(row))
    rows.sort()
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()


def barcode_set_hash(cells):
    return hashlib.sha256("\n".join(sorted(str(c["barcode"]) for c in cells)).encode()).hexdigest()


def check_schema(overlay, fail):
    meta = overlay.get("meta", {})
    for k in REQUIRED_META_KEYS:
        if k not in meta:
            fail.append(f"meta missing required key {k!r}")
    for k in FORBIDDEN_META_KEYS:
        if k in meta:
            fail.append(f"meta carries retired key {k!r}")
    if meta.get("schema_version") != SCHEMA_VERSION:
        fail.append(f"meta.schema_version {meta.get('schema_version')!r} != {SCHEMA_VERSION!r}")
    emb = json.dumps(meta.get("embedding", {}))
    for bad in ("paper-exact", "reproduces Suppl", "Suppl Fig 2"):
        if bad.lower() in emb.lower():
            fail.append(f"meta.embedding still claims {bad!r}")
    # programs[] contract
    progs = meta.get("programs", [])
    if len(progs) != len(REFERENCE["score_fields"]):
        fail.append(f"meta.programs has {len(progs)} entries, expected {len(REFERENCE['score_fields'])}")
    prog_fields = set()
    for p in progs:
        missing = PROGRAM_FIELDS - set(p)
        if missing:
            fail.append(f"program {p.get('score_field')!r} missing {sorted(missing)}")
        if p.get("family") not in VALID_FAMILIES:
            fail.append(f"program {p.get('score_field')!r} bad family {p.get('family')!r}")
        prog_fields.add(p.get("score_field"))
    if prog_fields != set(REFERENCE["score_fields"]):
        fail.append("meta.programs score_fields != the 12 frozen score fields")
    # frozen display domains, monotone p02<=p50<=p98, one per score field
    dom = meta.get("score_display_domains", {})
    for f in REFERENCE["score_fields"]:
        d = dom.get(f)
        if not d:
            fail.append(f"score_display_domains missing {f!r}")
        elif not (d.get("p02") <= d.get("p50") <= d.get("p98")):
            fail.append(f"score_display_domains[{f}] not monotone p02<=p50<=p98")


def check_cells(cells, fields, fail):
    seen_forbidden, seen_extra = set(), set()
    for c in cells:
        keys = set(c)
        for k in keys & FORBIDDEN_CELL_KEYS:
            seen_forbidden.add(k)
        for k in keys:
            if any(s in k for s in FORBIDDEN_KEY_SUBSTR):
                seen_forbidden.add(k)
        extra = keys - ALLOWED_CELL_KEYS
        for k in extra:
            seen_extra.add(k)
        missing = ALLOWED_CELL_KEYS - keys
        if missing:
            fail.append(f"cell {c.get('barcode')} missing keys {sorted(missing)}")
            break
        for f in fields:  # numeric over EVERY cell
            if not isinstance(c.get(f), (int, float)):
                fail.append(f"non-numeric score {f} on barcode {c.get('barcode')}")
                break
    if seen_forbidden:
        fail.append(f"retired/forbidden cell fields present: {sorted(seen_forbidden)}")
    if seen_extra - FORBIDDEN_CELL_KEYS:
        fail.append(f"unexpected cell fields (not in whitelist): {sorted(seen_extra - FORBIDDEN_CELL_KEYS)}")


def scan_stale(fail):
    for rel in SERVED_TEXT_ARTIFACTS:
        p = Path(rel)
        if not p.exists():
            continue
        txt = p.read_text(errors="ignore")
        hits = sorted({s for s in STALE_STRINGS if s in txt})
        if hits:
            fail.append(f"stale retired-pipeline strings in {rel}: {hits}")


def main():
    overlay = json.load(open(OVERLAY))
    cells = overlay["cells"]
    fail = []

    n = len(cells)
    bcs = [str(c["barcode"]) for c in cells]
    if n == 0:
        fail.append("zero cells in overlay")
    dup = n - len(set(bcs))
    if dup:
        fail.append(f"duplicate barcodes: {dup}")
    if overlay["meta"].get("method_version") != METHOD_VERSION:
        fail.append(f"method_version {overlay['meta'].get('method_version')!r} != {METHOD_VERSION!r}")

    fields = REFERENCE["score_fields"]
    if sorted(overlay["meta"].get("score_fields", [])) != sorted(fields):
        fail.append("meta.score_fields != the 12 frozen score fields")

    check_schema(overlay, fail)
    check_cells(cells, fields, fail)

    table_hash = canonical(cells, fields) if n else None
    bc_hash = barcode_set_hash(cells) if n else None

    # overlay <-> records agreement on EVERY score for EVERY overlay barcode
    if Path(RECORDS).exists():
        rec = json.load(open(RECORDS))
        missing = [b for b in bcs if b not in rec]
        if missing:
            fail.append(f"{len(missing)} overlay barcodes missing from records")
        mism = 0
        for c in cells:
            r = rec.get(str(c["barcode"]), {})
            for f in fields:
                if abs(round(float(c[f]), ROUND) - round(float(r.get(f, 1e18)), ROUND)) > 10 ** -ROUND:
                    mism += 1
                    break
        if mism:
            fail.append(f"{mism} cells disagree between overlay and records")
    else:
        fail.append(f"records file {RECORDS} missing")

    # FROZEN-SCIENCE gate — name exactly which value moved
    if REFERENCE["n_cells"] != n:
        fail.append(f"n_cells {n} != reference {REFERENCE['n_cells']}")
    if REFERENCE["barcode_set_sha256"] != bc_hash:
        fail.append("barcode-set hash CHANGED — the emitted barcode selection differs from the frozen reference. STOP.")
    if REFERENCE["canonical_table_sha256"] != table_hash:
        fail.append("canonical_table_sha256 CHANGED — a scientific value (barcode/cluster/condition/donor/score) "
                    "differs from the frozen reference. STOP and identify which score or identifier moved.")

    # meta-stored hashes must match the recomputed ones
    v = overlay["meta"].get("verification", {})
    if v.get("canonical_table_sha256") not in (None, table_hash):
        fail.append("meta.verification.canonical_table_sha256 does not match the recomputed table hash")
    if v.get("barcode_set_sha256") not in (None, bc_hash):
        fail.append("meta.verification.barcode_set_sha256 does not match the recomputed barcode-set hash")

    scan_stale(fail)

    if fail:
        print("VERIFY FAILED:", file=sys.stderr)
        print("\n".join("  - " + x for x in fail), file=sys.stderr)
        sys.exit(1)
    print(f"OK — {n} cells; schema whitelist clean; per-barcode table verified "
          f"(canonical {table_hash[:16]}…, barcodes {bc_hash[:12]}…); overlay↔records agree; no stale strings.")


if __name__ == "__main__":
    main()
