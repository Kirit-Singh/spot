#!/usr/bin/env python3
"""CP3c companion — constituent definedness for the two NON-production ratio/denominator
metrics whose aggregates the deleted zero-value heuristic mislabels:

  overlay_distributions.abs_median_over_iqr : per program x donor x condition
      value = |median(overlay) - median(full)| / iqr(full);  null when iqr(full)==0
  donor_sensitivity.lodo_ratio              : per program x condition x left_out_donor
      value = |median(3-donor) - median(4-donor)| / iqr(4-donor);  null when iqr==0

Uses ONLY the frozen scores parquet (score + barcode/donor/condition) and the frozen 40k
overlay barcode set. No 91GB .X load. Real numeric zero (positive denominator) stays a
defined zero; a zero denominator yields value:null. Mirrors the recovered T7b gate-10/12
math exactly so aggregate definedness is authoritative, not name/zero-inferred.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import time

import numpy as np
import pyarrow.parquet as pq

PARAMS = "t7b_params.json"; SCORES = "stage01_scores_full.parquet"; FROZEN40K = "t7b_frozen40k.json"
METHOD_VERSION = "stage1-continuous-v3.0.1"
CONDS = ["Rest", "Stim8hr", "Stim48hr"]; DONORS = ["D1", "D2", "D3", "D4"]

P = json.load(open(PARAMS))
PRIMARY = P["primary_programs"]
FROZEN_BCS = set(json.load(open(FROZEN40K))["barcodes"])


def median(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return float(np.median(x)) if x.size else None


def iqr(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    if x.size == 0:
        return None
    q75, q25 = np.percentile(x, [75, 25])
    return float(q75 - q25)


def file_sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 24), b""):
            h.update(blk)
    return h.hexdigest()


t0 = time.time()
tb = pq.read_table(SCORES).to_pydict()
barcode = np.array(tb["barcode"]); donor = np.array(tb["donor"]); condition = np.array(tb["condition"])
scores = {pk: np.array(tb[f"{pk}_score"], float) for pk in PRIMARY}
ov_mask = np.array([b in FROZEN_BCS for b in barcode])
assert int(ov_mask.sum()) == 40000, f"overlay set size {int(ov_mask.sum())} != 40000"
cond_mask = {c: (condition == c) for c in CONDS}
dc = {(d, c): (donor == d) & (condition == c) for d in DONORS for c in CONDS}

ROWS = []


def add(subcheck_id, gate_family, program_id, condition_, operator, threshold,
        value, metric_defined, undefined_reason, *, donor=None, left_out_donor=None,
        numerator=None, denominator=None):
    predicate_met = None
    if metric_defined and value is not None:
        predicate_met = bool({">=": value >= threshold, ">": value > threshold,
                              "<=": value <= threshold, "<": value < threshold}[operator])
    ROWS.append({
        "gate_class": "semantics_definedness", "gate_family": gate_family,
        "subcheck_id": subcheck_id, "program_id": program_id, "condition": condition_,
        "donor": donor, "left_out_donor": left_out_donor,
        "numerator": numerator, "denominator": denominator, "value": value,
        "metric_defined": bool(metric_defined), "undefined_reason": undefined_reason,
        "operator": operator, "threshold": threshold, "predicate_met": predicate_met,
    })


# overlay_distributions median-error ratio (per program x donor x condition)
for pk in PRIMARY:
    sc = scores[pk]
    for c in CONDS:
        for d in DONORS:
            mfull = dc[(d, c)]; movl = mfull & ov_mask
            iqf = iqr(sc[mfull]); num = None
            mo, mf = median(sc[movl]), median(sc[mfull])
            if mo is not None and mf is not None:
                num = abs(mo - mf)
            if iqf is None:
                val, defd, reason = None, False, "empty_stratum"
            elif iqf > 0:
                val, defd, reason = (num / iqf if num is not None else None), (num is not None), (None if num is not None else "numerator_none")
            else:
                val, defd, reason = None, False, "zero_iqr_undefined"
            add("overlay_distributions.abs_median_over_iqr", "overlay_distributions", pk, c,
                "<=", 0.10, val, defd, reason, donor=d, numerator=num, denominator=iqf)

# donor_sensitivity LODO ratio (per program x condition x left_out_donor)
for pk in PRIMARY:
    sc = scores[pk]
    for c in CONDS:
        m4 = cond_mask[c]; med4 = median(sc[m4]); iq4 = iqr(sc[m4])
        for dleft in DONORS:
            m3 = cond_mask[c] & (donor != dleft); med3 = median(sc[m3])
            num = abs(med3 - med4) if (med3 is not None and med4 is not None) else None
            if iq4 is None:
                val, defd, reason = None, False, "empty_stratum"
            elif iq4 > 0:
                val, defd, reason = (num / iq4 if num is not None else None), (num is not None), (None if num is not None else "numerator_none")
            else:
                val, defd, reason = None, False, "zero_iqr_undefined"
            add("donor_sensitivity.lodo_ratio", "donor_sensitivity", pk, c, ">", 0.25,
                val, defd, reason, left_out_donor=dleft, numerator=num, denominator=iq4)

SORT_KEYS = ["subcheck_id", "program_id", "condition", "donor", "left_out_donor"]
ROWS.sort(key=lambda r: tuple("" if r[k] is None else str(r[k]) for k in SORT_KEYS))
content = hashlib.sha256(json.dumps(ROWS, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=True, allow_nan=False).encode()).hexdigest()
with gzip.open("stage01_gate_constituents_overlay_donor_v1.json.gz", "wt", encoding="utf-8") as fh:
    json.dump(ROWS, fh, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
expected = {
    "overlay_distributions.abs_median_over_iqr": len(PRIMARY) * 3 * 4,
    "donor_sensitivity.lodo_ratio": len(PRIMARY) * 3 * 4,
}
manifest = {
    "schema": "spot.stage01_gate_constituents_overlay_donor.manifest.v1",
    "method_version": METHOD_VERSION,
    "json_mirror": "stage01_gate_constituents_overlay_donor_v1.json.gz",
    "row_count": len(ROWS), "sort_key": SORT_KEYS, "expected_grids": expected,
    "content_canonical_sha256": content,
    "inputs": {"scores_parquet_raw_sha256": file_sha(SCORES), "params_raw_sha256": file_sha(PARAMS),
               "frozen40k_raw_sha256": file_sha(FROZEN40K), "overlay_set_size": int(ov_mask.sum())},
    "generator_code_sha256": file_sha(__file__),
    "note": "Companion definedness evidence for the two non-production ratio metrics whose "
            "aggregates the deleted zero-value heuristic mislabels. value:null iff denom IQR==0.",
}
json.dump(manifest, open("stage01_gate_constituents_overlay_donor_v1.manifest.json", "w"), indent=2, sort_keys=True)
print("overlay_donor ROWS", len(ROWS), "content", content, f"{time.time()-t0:.1f}s")
print("DONE_OVERLAY_DONOR")
