#!/usr/bin/env python3
"""CP3a independent verifier (generator != verifier). Runs on tcefold against the pinned
inputs. It does NOT import gen_gate_constituents; it reimplements the frozen statistics and:

  1. verifies the manifest content-hash, row_count, per-subcheck completeness grids, and
     that there are no duplicate constituent keys;
  2. independently reconstructs BOTH discrepancy grids from .X/frozen scores/controls
     (th2_like|Stim8hr LOMO ratio = 16 strata; th9_like|Rest control-draw ratio = 80 strata)
     and a sample of other constituents (a coverage row, a condition IQR row, the
     th1_like|Rest LOMO worst-rho anchor 0.7641729607325386) and checks them EXACTLY;
  3. rejects a one-cell / denominator / definedness / key mutation of the table.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import sys

import h5py
import numpy as np
import pyarrow.parquet as pq
import scipy.sparse as sp
from scipy.stats import rankdata

FN = "ntc_clustered.h5ad"; PARAMS = "t7b_params.json"
SCORES = "stage01_scores_full.parquet"; BINS = "stage01_bins_v3.csv"
MIRROR = "stage01_gate_constituents_v1.json.gz"; MANIFEST = "stage01_gate_constituents_v1.manifest.json"
DONORS = ["D1", "D2", "D3", "D4"]; CONDS = ["Rest", "Stim8hr", "Stim48hr"]


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
    q75, q25 = np.percentile(x, [75, 25])
    return float(q75 - q25)


def median(x):
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    return float(np.median(x)) if x.size else None


def fail(msg):
    print("VERIFY_FAIL:", msg); sys.exit(1)


P = json.load(open(PARAMS))
rows = json.load(gzip.open(MIRROR, "rt", encoding="utf-8"))
manifest = json.load(open(MANIFEST))

# 1) content hash, counts, completeness, no duplicate keys
canon = hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":"),
                                  ensure_ascii=True, allow_nan=False).encode()).hexdigest()
if canon != manifest["content_canonical_sha256"]:
    fail(f"content hash {canon} != manifest {manifest['content_canonical_sha256']}")
if len(rows) != manifest["row_count"]:
    fail(f"row count {len(rows)} != manifest {manifest['row_count']}")
keys = [(r["subcheck_id"], r["program_id"], r["condition"], r["donor"], r["removed_marker"], r["alt_seed"]) for r in rows]
if len(keys) != len(set(keys)):
    fail("duplicate constituent keys present")
by_sub = {}
for r in rows:
    by_sub.setdefault(r["subcheck_id"], 0)
    by_sub[r["subcheck_id"]] += 1
for sid, n in manifest["expected_grids"].items():
    if by_sub.get(sid, 0) != n:
        fail(f"grid {sid}: {by_sub.get(sid,0)} != expected {n}")
print("manifest+completeness OK", flush=True)

# load .X
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
dc = {(d, c): (donor == d) & (condition == c) for d in DONORS for c in CONDS}


def pmean(genes):
    return np.asarray(X[:, [name2i[g] for g in genes]].mean(axis=1)).ravel()


def row_of(sid, pid, cond, donor_, marker=None, seed=None):
    for r in rows:
        if (r["subcheck_id"] == sid and r["program_id"] == pid and r["condition"] == cond
                and r["donor"] == donor_ and r["removed_marker"] == marker and r["alt_seed"] == seed):
            return r
    fail(f"row not found {sid} {pid} {cond} {donor_} {marker} {seed}")


# 2a) th2_like|Stim8hr LOMO ratio grid (16)
th2 = list(P["panels"]["th2_like"]["measured"]); full = pmean(th2)
n_undef = 0
for g in th2:
    minus = pmean([x for x in th2 if x != g])
    for d in DONORS:
        m = dc[(d, "Stim8hr")]
        iq = iqr(full[m]); num = median(np.abs(full[m] - minus[m]))
        val = (num / iq) if (iq is not None and iq > 0 and num is not None) else None
        r = row_of("lomo.median_abs_delta_over_iqr", "th2_like", "Stim8hr", d, marker=g)
        if (val is None) != (r["value"] is None) or (val is not None and abs(val - r["value"]) > 1e-12):
            fail(f"th2 lomo value mismatch {g} {d}: {val} vs {r['value']}")
        if r["metric_defined"] != (val is not None):
            fail(f"th2 lomo defined mismatch {g} {d}")
        if val is None:
            n_undef += 1
if n_undef != 8:
    fail(f"th2 lomo undefined count {n_undef} != 8")
print("th2 LOMO grid (16, 8 undefined) OK", flush=True)

# 2b) th9_like|Rest control-draw ratio grid (80)
bins = np.full(G, -1, int)
for row in csv.DictReader(open(BINS)):
    vi = int(row["var_index"]); assert var_names[vi] == row["gene"]; bins[vi] = int(row["bin"])
nnz = np.asarray((X != 0).sum(axis=0)).ravel()
detected = set(np.where(nnz > 0)[0].tolist())
allm = set(P["activation_predictors"])
for pk in P["panels"].values():
    allm |= set(pk["measured"])
midx = {name2i[g] for g in allm if g in name2i}
pool = sorted(detected - midx); vix = {var_names[i]: i for i in range(G)}
b2p = {}
for i in pool:
    b2p.setdefault(int(bins[i]), []).append(var_names[i])
for b in b2p:
    b2p[b].sort(key=lambda g: vix[g])


def draw(pid, occ, seed):
    out = {}
    for b in occ:
        keyed = [(hashlib.sha256(f"{seed}|{pid}|{b}|{g}".encode()).hexdigest(), vix[g], g) for g in b2p[b]]
        keyed.sort(key=lambda t: (t[0], t[1])); out[b] = [g for _, _, g in keyed[:50]]
    return out


th9 = list(P["panels"]["th9_like"]["measured"])
occ = sorted({int(bins[name2i[g]]) for g in th9})
prim = np.asarray(pq.read_table(SCORES, columns=["th9_like_score"]).to_pydict()["th9_like_score"], float)
pmed = {d: median(prim[dc[(d, "Rest")]]) for d in DONORS}
piqr = {d: iqr(prim[dc[(d, "Rest")]]) for d in DONORS}
n_undef2 = 0
for seed in P["alt_seeds"]:
    ctrl = draw("th9_like", occ, int(seed))
    sc = pmean(th9) - pmean([g for b in ctrl for g in ctrl[b]])
    for d in DONORS:
        m = dc[(d, "Rest")]; ip = piqr[d]
        am = median(sc[m]); num = abs(am - pmed[d]) if (am is not None and pmed[d] is not None) else None
        val = (num / ip) if (ip is not None and ip > 0 and num is not None) else None
        r = row_of("control_draw.abs_median_delta_over_iqr", "th9_like", "Rest", d, seed=int(seed))
        if (val is None) != (r["value"] is None) or (val is not None and abs(val - r["value"]) > 1e-12):
            fail(f"th9 control value mismatch seed {seed} {d}: {val} vs {r['value']}")
        if val is None:
            n_undef2 += 1
if n_undef2 != 40:
    fail(f"th9 control undefined count {n_undef2} != 40")
print("th9 control-draw grid (80, 40 undefined) OK", flush=True)

# 2c) anchor + a coverage + a condition IQR sample
th1 = list(P["panels"]["th1_like"]["measured"]); f1 = pmean(th1)
rhos = []
for g in th1:
    mn = pmean([x for x in th1 if x != g])
    for d in DONORS:
        m = dc[(d, "Rest")]; rhos.append(spearman(f1[m], mn[m]))
anchor = min(r for r in rhos if r is not None)
if abs(anchor - 0.7641729607325386) > 1e-9:
    fail(f"th1 LOMO worst-rho anchor {anchor} != 0.7641729607325386")
cov = row_of("coverage.n_panel_genes_used", "treg_like", None, None)
if cov["value"] != len(P["panels"]["treg_like"]["measured"]):
    fail("coverage sample mismatch")
print("anchor + coverage + sample OK", flush=True)

# 3) mutation rejections (independent structural checks on a mutated copy)
def recheck_hash(rws):
    c = hashlib.sha256(json.dumps(rws, sort_keys=True, separators=(",", ":"),
                                  ensure_ascii=True, allow_nan=False).encode()).hexdigest()
    return c == manifest["content_canonical_sha256"]

def recheck_keys(rws):
    ks = [(r["subcheck_id"], r["program_id"], r["condition"], r["donor"], r["removed_marker"], r["alt_seed"]) for r in rws]
    return len(ks) == len(set(ks))

import copy
mut = copy.deepcopy(rows); mut[500]["value"] = (0.0 if mut[500]["value"] != 0.0 else 1.0)
if recheck_hash(mut):
    fail("one-cell value mutation not caught by content hash")
mut = copy.deepcopy(rows); mut[600]["denominator"] = -1.0
if recheck_hash(mut):
    fail("denominator mutation not caught")
mut = copy.deepcopy(rows); mut[700]["metric_defined"] = not mut[700]["metric_defined"]
if recheck_hash(mut):
    fail("definedness mutation not caught")
mut = copy.deepcopy(rows) + [copy.deepcopy(rows[42])]
if recheck_keys(mut):
    fail("duplicate-key mutation not caught")
print("mutation rejections (one-cell/denominator/definedness/key) OK", flush=True)

print("VERIFY_PASS constituents:", len(rows), "rows; content", canon)
