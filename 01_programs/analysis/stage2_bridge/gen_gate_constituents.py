#!/usr/bin/env python3
"""CP3a — emit the per-constituent evidence table for the Stage-1 T7b MEASUREMENT gates.

Runs in the solver-locked compute environment against the pinned v3.0.1 inputs. It reuses the EXACT recovered
T7b statistics (spearman: average ranks, finite-only, None if <2 finite or rank std 0;
iqr: Q75-Q25 numpy-linear, None if empty) so every derived aggregate reproduces the frozen
`stage01_validation.json` byte-for-byte — but instead of collapsing to a lossy extremum it
emits ONE ROW PER CONSTITUENT STRATUM so definedness is authoritative and never inferred
from a numeric zero or a metric name.

Constituent grids (gate_class = measurement_validity):
  coverage.n_panel_genes_used            : 1 per program                    (11)
  condition_measurability.panel_score_iqr: donor                            (11*3*4=132)
  condition_measurability.n_panel_..._1pct: donor                           (132)
  lomo.spearman_rho_full_minus_gene      : removed_marker x donor           (53*3*4=636)
  lomo.median_abs_delta_over_iqr         : removed_marker x donor           (636)
  control_draw.spearman_rho_primary_alt  : alt_seed x donor                 (11*3*20*4=2640)
  control_draw.abs_median_delta_over_iqr : alt_seed x donor                 (2640)
Plus (gate_class = base_portability): 2 program-level rows x 11 = 22 (Stage-2, separate).

value is null ONLY when the denominator IQR is 0/undefined (never a numeric-zero heuristic);
a real zero numerator over a positive denominator stays a defined numeric zero.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import time

import h5py
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import scipy.sparse as sp
from scipy.stats import rankdata

FN = "ntc_clustered.h5ad"
PARAMS = "t7b_params.json"
SCORES = "stage01_scores_full.parquet"
BINS = "stage01_bins_v3.csv"
METHOD_VERSION = "stage1-continuous-v3.0.1"
H5AD_EXPECT = "2edc6d318415c8b0ee779d707ab86e26ddb6f0274db51ab4a12f21ebfda50e43"
BINS_CONTENT_EXPECT = "32f926cace9322752aba10557b1bafe3e0c8f9d8f285551fcd2d3648bd335f78"

CONDS = ["Rest", "Stim8hr", "Stim48hr"]
DONORS = ["D1", "D2", "D3", "D4"]

P = json.load(open(PARAMS))
PRIMARY = P["primary_programs"]
PANELS = P["panels"]
CTRL = P["committed_controls"]
ACT = P["activation_predictors"]
EU = set(P["effect_universe_symbols"])
ALT_SEEDS = P["alt_seeds"]
MASTER = P["master_seed"]


def spearman(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 2:
        return None
    ra = rankdata(a[m], method="average"); rb = rankdata(b[m], method="average")
    if ra.std() == 0 or rb.std() == 0:
        return None
    return float(np.corrcoef(ra, rb)[0, 1])


def iqr(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    if x.size == 0:
        return None
    q75, q25 = np.percentile(x, [75, 25])   # numpy linear (default)
    return float(q75 - q25)


def median(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return float(np.median(x)) if x.size else None


def file_sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for blk in iter(lambda: fh.read(16 * 1024 * 1024), b""):
            h.update(blk)
    return h.hexdigest()


t0 = time.time()
with h5py.File(FN, "r") as f:
    shape = tuple(int(x) for x in f["X"].attrs["shape"]); N, G = shape
    var_names = f["var/_index"][:].astype(str)
    data = f["X/data"][:]; indices = f["X/indices"][:]; indptr = f["X/indptr"][:]

    def read_obs(k):
        node = f[f"obs/{k}"]
        if isinstance(node, h5py.Group):
            cats = node["categories"][:]; codes = node["codes"][:]
            cats = np.array([c.decode() if isinstance(c, bytes) else str(c) for c in cats])
            return cats[codes]
        a = node[:]
        return np.array([x.decode() if isinstance(x, bytes) else str(x) for x in a]) if a.dtype.kind in "SO" else a
    barcode = read_obs("barcode"); condition = read_obs("condition"); donor = read_obs("donor")
X = sp.csr_matrix((data, indices, indptr), shape=(N, G)).astype(np.float64)
name2i = {s: i for i, s in enumerate(var_names)}
print(f"loaded X {X.shape} nnz {X.nnz} {time.time()-t0:.1f}s", flush=True)

h5ad_raw = file_sha(FN)
assert h5ad_raw == H5AD_EXPECT, f"h5ad raw sha {h5ad_raw} != frozen"

# frozen per-gene bins (LOADED, not recomputed)
bins = np.full(G, -1, dtype=int)
with open(BINS) as fh:
    for r in csv.DictReader(fh):
        vi = int(r["var_index"]); assert var_names[vi] == r["gene"]; bins[vi] = int(r["bin"])
assert (bins >= 0).all()
bins_content = hashlib.sha256(("\n".join(f"{i},{var_names[i]},{int(bins[i])}" for i in range(G))).encode()).hexdigest()
assert bins_content == BINS_CONTENT_EXPECT, "bins content != frozen"

nnz_per = np.asarray((X != 0).sum(axis=0)).ravel()
detected = set(np.where(nnz_per > 0)[0].tolist())
all_markers = set()
for pk in PANELS:
    all_markers |= set(PANELS[pk]["measured"])
all_markers |= set(ACT)
marker_idx = set(name2i[g] for g in all_markers if g in name2i)
pool_idx = sorted(detected - marker_idx)
pool_sha = hashlib.sha256("\n".join(sorted(var_names[i] for i in pool_idx)).encode()).hexdigest()
assert pool_sha == P["frozen_pool_sha256"], "pool sha != frozen"

var_index = {var_names[i]: i for i in range(G)}
bin_to_pool = {}
for i in pool_idx:
    bin_to_pool.setdefault(int(bins[i]), []).append(var_names[i])
for b in bin_to_pool:
    bin_to_pool[b].sort(key=lambda g: var_index[g])


def draw_controls(program_id, occupied_bins, seed):
    out = {}
    for b in occupied_bins:
        keyed = [(hashlib.sha256(f"{seed}|{program_id}|{b}|{g}".encode()).hexdigest(), var_index[g], g)
                 for g in bin_to_pool[b]]
        keyed.sort(key=lambda t: (t[0], t[1]))
        out[b] = [g for _, _, g in keyed[:50]]
    return out


def occupied_bins_for(measured):
    return sorted(set(int(bins[name2i[g]]) for g in measured if g in name2i))


def panel_mean_matrix(measured):
    idx = [name2i[g] for g in measured if g in name2i]
    return np.asarray(X[:, idx].mean(axis=1)).ravel() if idx else None


def control_mean_matrix(ctrl_by_bin):
    genes = [g for b in ctrl_by_bin for g in ctrl_by_bin[b]]
    idx = [name2i[g] for g in genes if g in name2i]
    return np.asarray(X[:, idx].mean(axis=1)).ravel() if idx else None


def score_program(measured, ctrl_by_bin):
    return panel_mean_matrix(measured) - control_mean_matrix(ctrl_by_bin)


CTRL_INT = {pk: {int(b): v for b, v in CTRL[pk].items()} for pk in CTRL}
cond_mask = {c: (condition == c) for c in CONDS}
donor_mask = {d: (donor == d) for d in DONORS}
dc_mask = {(d, c): (donor_mask[d] & cond_mask[c]) for d in DONORS for c in CONDS}

tb = pq.read_table(SCORES).to_pydict()
pq_bc = np.array(tb["barcode"])
scores_full = {k: np.array(tb[k], float) for k in P["score_fields"]}
assert np.array_equal(pq_bc, barcode), "parquet barcode order != X"

# HARD integrity: redraw at master seed reproduces committed controls + frozen primary scores
redraw_ok = True; score_exact = True; maxerr = 0.0
for pk in PRIMARY:
    meas = PANELS[pk]["measured"]; occ = occupied_bins_for(meas)
    dr = draw_controls(pk, occ, MASTER)
    for b in occ:
        if dr[b] != CTRL_INT[pk].get(b, []):
            redraw_ok = False
    sc = score_program(meas, dr); scr = np.round(sc, 5); emit = scores_full[f"{pk}_score"]
    fin = np.isfinite(scr) & np.isfinite(emit)
    if not np.array_equal(scr[fin], emit[fin]):
        score_exact = False
    maxerr = max(maxerr, float(np.nanmax(np.abs(sc - emit))))
assert redraw_ok, "control redraw != committed"
assert score_exact or maxerr <= 5e-6, f"score reproduction failed maxerr={maxerr}"
print(f"integrity OK redraw={redraw_ok} exact={score_exact} maxerr={maxerr} {time.time()-t0:.1f}s", flush=True)

ROWS = []


def add(gate_class, gate_family, subcheck_id, program_id, condition_, operator, threshold,
        value, metric_defined, undefined_reason, *, donor=None, removed_marker=None, alt_seed=None,
        numerator=None, denominator=None, n_cells=None):
    predicate_met = None
    if metric_defined and value is not None:
        predicate_met = bool({">=": value >= threshold, ">": value > threshold,
                              "<=": value <= threshold, "<": value < threshold,
                              "==": value == threshold}[operator])
    ROWS.append({
        "gate_class": gate_class, "gate_family": gate_family, "subcheck_id": subcheck_id,
        "program_id": program_id, "condition": condition_, "donor": donor,
        "removed_marker": removed_marker, "alt_seed": alt_seed,
        "numerator": numerator, "denominator": denominator,
        "value": value, "metric_defined": bool(metric_defined),
        "undefined_reason": undefined_reason,
        "operator": operator, "threshold": threshold, "predicate_met": predicate_met,
        "n_cells": n_cells,
    })


# ---- coverage (program-level single) ----
for pk in PRIMARY:
    n = len(PANELS[pk]["measured"])
    add("measurement_validity", "global_coverage", "coverage.n_panel_genes_used", pk, None,
        ">=", 3, n, True, None)

# ---- base_portability (program-level, SEPARATE Stage-2) ----
for pk in PRIMARY:
    meas = PANELS[pk]["measured"]; ctrl = [g for b in CTRL_INT[pk] for g in CTRL_INT[pk][b]]
    n_panel_eu = sum(1 for g in meas if g in EU); n_ctrl_eu = sum(1 for g in ctrl if g in EU)
    add("base_portability", "stage2_base_portability", "base_portability.n_panel_in_effect_universe",
        pk, None, ">=", 3, n_panel_eu, True, None)
    add("base_portability", "stage2_base_portability", "base_portability.n_control_in_effect_universe",
        pk, None, ">=", 10, n_ctrl_eu, True, None)

# ---- condition_measurability (per donor) ----
for pk in PRIMARY:
    meas = PANELS[pk]["measured"]; sc = score_program(meas, CTRL_INT[pk])
    pidx = [name2i[g] for g in meas if g in name2i]
    for c in CONDS:
        for d in DONORS:
            m = dc_mask[(d, c)]; nc = int(m.sum())
            v = iqr(sc[m])
            add("measurement_validity", "condition_measurability",
                "condition_measurability.panel_score_iqr", pk, c, ">", 0,
                v, v is not None, None if v is not None else "empty_stratum",
                donor=d, denominator=None, n_cells=nc)
            sub = X[m][:, pidx]
            frac = np.asarray((sub != 0).sum(axis=0)).ravel() / m.sum()
            ndet = int((frac >= 0.01).sum())
            add("measurement_validity", "condition_measurability",
                "condition_measurability.n_panel_genes_detected_ge_1pct_cells", pk, c, ">=", 2,
                ndet, True, None, donor=d, n_cells=nc)
print(f"condition done {time.time()-t0:.1f}s", flush=True)

# ---- LOMO (per removed_marker x donor) ----
for pk in PRIMARY:
    meas = PANELS[pk]["measured"]
    pm_full = panel_mean_matrix(meas)
    for c in CONDS:
        for g in meas:
            pm_minus = panel_mean_matrix([x for x in meas if x != g])
            for d in DONORS:
                m = dc_mask[(d, c)]; nc = int(m.sum())
                rho = spearman(pm_full[m], pm_minus[m])
                add("measurement_validity", "lomo_panel_robustness",
                    "lomo.spearman_rho_full_minus_gene", pk, c, ">=", 0.80,
                    rho, rho is not None, None if rho is not None else "undefined_correlation",
                    donor=d, removed_marker=g, n_cells=nc)
                iq = iqr(pm_full[m])
                num = median(np.abs(pm_full[m] - pm_minus[m]))
                if iq is None:
                    val, defd, reason = None, False, "empty_stratum"
                elif iq > 0:
                    val, defd, reason = (num / iq if num is not None else None), (num is not None), (None if num is not None else "numerator_none")
                else:
                    val, defd, reason = None, False, "zero_iqr_undefined"
                add("measurement_validity", "lomo_panel_robustness",
                    "lomo.median_abs_delta_over_iqr", pk, c, "<=", 0.25,
                    val, defd, reason, donor=d, removed_marker=g,
                    numerator=num, denominator=iq, n_cells=nc)
print(f"lomo done {time.time()-t0:.1f}s", flush=True)

# ---- control_draw (per alt_seed x donor) ----
for pk in PRIMARY:
    meas = PANELS[pk]["measured"]; occ = occupied_bins_for(meas)
    prim = scores_full[f"{pk}_score"]
    prim_med = {}; prim_iqr = {}
    for c in CONDS:
        for d in DONORS:
            m = dc_mask[(d, c)]; prim_med[(d, c)] = median(prim[m]); prim_iqr[(d, c)] = iqr(prim[m])
    for c in CONDS:
        for seed in ALT_SEEDS:
            sc_alt = score_program(meas, draw_controls(pk, occ, seed))
            for d in DONORS:
                m = dc_mask[(d, c)]; nc = int(m.sum())
                rho = spearman(prim[m], sc_alt[m])
                add("measurement_validity", "control_draw_sensitivity",
                    "control_draw.spearman_rho_primary_alt", pk, c, ">=", 0.90,
                    rho, rho is not None, None if rho is not None else "undefined_correlation",
                    donor=d, alt_seed=int(seed), n_cells=nc)
                ip = prim_iqr[(d, c)]; am = median(sc_alt[m]); pm_ = prim_med[(d, c)]
                num = abs(am - pm_) if (am is not None and pm_ is not None) else None
                if ip is None:
                    val, defd, reason = None, False, "empty_stratum"
                elif ip > 0:
                    val, defd, reason = (num / ip if num is not None else None), (num is not None), (None if num is not None else "numerator_none")
                else:
                    val, defd, reason = None, False, "zero_iqr_undefined"
                add("measurement_validity", "control_draw_sensitivity",
                    "control_draw.abs_median_delta_over_iqr", pk, c, "<=", 0.25,
                    val, defd, reason, donor=d, alt_seed=int(seed),
                    numerator=num, denominator=ip, n_cells=nc)
print(f"control_draw done {time.time()-t0:.1f}s", flush=True)

# ---- deterministic sort ----
SORT_KEYS = ["gate_class", "gate_family", "subcheck_id", "program_id", "condition",
             "donor", "removed_marker", "alt_seed"]


def sort_key(r):
    return tuple(("" if r[k] is None else (f"{r[k]:012d}" if isinstance(r[k], int) else str(r[k]))) for k in SORT_KEYS)


ROWS.sort(key=sort_key)

# ---- canonical content hash (deterministic; over sorted rows) ----
content_canonical = hashlib.sha256(
    json.dumps(ROWS, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()).hexdigest()

# ---- write parquet ----
COLS = ["gate_class", "gate_family", "subcheck_id", "program_id", "condition", "donor",
        "removed_marker", "alt_seed", "numerator", "denominator", "value", "metric_defined",
        "undefined_reason", "operator", "threshold", "predicate_met", "n_cells"]
arrays = {}
for col in COLS:
    vals = [r[col] for r in ROWS]
    if col in ("alt_seed", "n_cells"):
        arrays[col] = pa.array(vals, type=pa.int64())
    elif col in ("numerator", "denominator", "value", "threshold"):
        arrays[col] = pa.array([None if v is None else float(v) for v in vals], type=pa.float64())
    elif col in ("metric_defined", "predicate_met"):
        arrays[col] = pa.array(vals, type=pa.bool_())
    else:
        arrays[col] = pa.array([None if v is None else str(v) for v in vals], type=pa.string())
table = pa.table(arrays)
pq.write_table(table, "stage01_gate_constituents_v1.parquet", compression="zstd")
parquet_raw = file_sha("stage01_gate_constituents_v1.parquet")

# ---- json mirror (gzip) for pyarrow-free local consumption ----
with gzip.open("stage01_gate_constituents_v1.json.gz", "wt", encoding="utf-8") as fh:
    json.dump(ROWS, fh, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)

# ---- expected grids ----
grids = {}
for pk in PRIMARY:
    grids[pk] = {"n_markers": len(PANELS[pk]["measured"])}
expected = {
    "coverage.n_panel_genes_used": len(PRIMARY),
    "condition_measurability.panel_score_iqr": len(PRIMARY) * 3 * 4,
    "condition_measurability.n_panel_genes_detected_ge_1pct_cells": len(PRIMARY) * 3 * 4,
    "lomo.spearman_rho_full_minus_gene": sum(len(PANELS[pk]["measured"]) for pk in PRIMARY) * 3 * 4,
    "lomo.median_abs_delta_over_iqr": sum(len(PANELS[pk]["measured"]) for pk in PRIMARY) * 3 * 4,
    "control_draw.spearman_rho_primary_alt": len(PRIMARY) * 3 * len(ALT_SEEDS) * 4,
    "control_draw.abs_median_delta_over_iqr": len(PRIMARY) * 3 * len(ALT_SEEDS) * 4,
    "base_portability.n_panel_in_effect_universe": len(PRIMARY),
    "base_portability.n_control_in_effect_universe": len(PRIMARY),
}

manifest = {
    "schema": "spot.stage01_gate_constituents.manifest.v1",
    "method_version": METHOD_VERSION,
    "artifact": "stage01_gate_constituents_v1.parquet",
    "json_mirror": "stage01_gate_constituents_v1.json.gz",
    "row_count": len(ROWS),
    "columns": COLS,
    "dtypes": {c: str(arrays[c].type) for c in COLS},
    "sort_key": SORT_KEYS,
    "expected_grids": expected,
    "content_canonical_sha256": content_canonical,
    "parquet_raw_sha256": parquet_raw,
    "inputs": {
        "h5ad_raw_sha256": h5ad_raw,
        "bins_content_sha256": bins_content,
        "bins_raw_sha256": file_sha(BINS),
        "pool_sha256": pool_sha,
        "scores_parquet_raw_sha256": file_sha(SCORES),
        "scores_canonical_content_sha256": P["scores_canonical_content_sha256"],
        "params_raw_sha256": file_sha(PARAMS),
    },
    "generator_code_sha256": file_sha(__file__),
    "integrity": {"control_redraw_matches_committed": redraw_ok,
                  "primary_score_exact_after_5dp_round": score_exact,
                  "primary_score_maxerr_preround": maxerr},
    "hard_gate_undefined_policy": {"iqr_zero": "fail", "undefined_correlation": "fail",
                                   "undefined_is_fail": True, "no_numeric_sentinel": True},
}
json.dump(manifest, open("stage01_gate_constituents_v1.manifest.json", "w"), indent=2, sort_keys=True)
print("ROWS", len(ROWS), "content_canonical", content_canonical, "parquet_raw", parquet_raw, flush=True)
print("expected_grids_total", sum(expected.values()))
print("DONE_CONSTITUENTS", time.time() - t0, flush=True)
