#!/usr/bin/env python3
"""gen_stage1_scores_v3.py — deterministic, memory-bounded recompute of the Stage-1 v3
396,000-row transcriptional-program score table directly from the public h5ad ``.X``.

This is the *scoring-tier* reproduction entry point that closes external-review blocker
S1-B1: the previously committed tooling either rebuilt the historical v2 40k table
(``reproduce.sh``) or started *downstream* of scoring from an already-existing parquet
(``reproduce_t8.sh`` / ``_t8_staging/dcompute_tcefold.py`` only *read + hash* the parquet).
Nothing recomputed the v3 scores from ``.X``. This script does exactly that and proves it
reproduces the frozen canonical hash byte-for-byte.

Success criterion
-----------------
The canonical content sha256 of the recomputed 12-lane table equals::

    scores_canonical_content_sha256 = 43c4296d5166740c334441a69df23bb440a073382bbe79628a3bb89e43d51316

Recovered scoring method (frozen; see STAGE1_REMEDIATION_METHOD.md + registry v3)
--------------------------------------------------------------------------------
* Normalization: NONE is applied here. ``.X`` is *already* the authors' default
  ``normalize_total()`` (per-cell total scaled to the dataset median total, ~9819) + ``log1p``.
  There is no raw-counts layer to renormalize from, so ``.X`` is consumed as-is (float64).
* Per program the score is a plain panel-minus-control mean of normalized expression::

      score = mean_over_panel_genes(.X) - mean_over_control_genes(.X)

  i.e. ``panel_coef * sum(panel) + control_coef * sum(control)`` with
  ``panel_coef = 1/n_panel`` and ``control_coef = -1/n_control``. The registry's rounded
  ``coefficients`` (e.g. 0.1666666667 == 1/6, -0.0066666667 == 1/150) are exactly these means.
* Control genes are the FROZEN expression-bin-matched sets committed in
  ``stage01_controls_v3.csv`` (keyed-sha256 draw, master_seed 12345, 50 lowest hashes per
  occupied marker bin). We consume the frozen controls directly; the draw is not re-run.
* The 12th lane, ``cd4_ctl_like_score_actadj``, is the CD4 CTL-like score residualized on a
  linear activation-predictor score using the FROZEN regression coefficients::

      activation_predictor_score = mean(act_panel .X) - mean(act_controls .X)
      cd4_ctl_like_score_actadj  = cd4_ctl_like_score - (slope*activation_predictor_score + intercept)

  with ``slope = 0.3832196947475601`` and ``intercept = 0.13373652013357928`` (registry
  ``sensitivity_lanes[0].activation_predictor``; the fit is ``np.polyfit(S_act, raw_ctl, 1)``
  over all 396k cells, frozen so the residual is deterministic).

Canonicalization (reused EXACTLY from _t8_staging/dcompute_tcefold.py)
---------------------------------------------------------------------
Stable argsort on barcode; per row ``barcode\tdonor\tcondition\t`` followed by each score
field formatted ``f"{round(float(v),5):.5f}"``, tab-joined, trailing ``\n``; incremental sha256.
Score field order = the 11 primary ``{program_id}_score`` in registry order, then
``cd4_ctl_like_score_actadj``.

Run
---
Locally requires the pinned h5ad (sha 2edc6d31...). On tcefold::

    conda activate scvi_gpu
    python gen_stage1_scores_v3.py \
        --h5ad /home/tcelab/cs_scratch/ntc_clustered.h5ad \
        --registry 01_programs/app/data/stage01_program_registry_v3.json \
        --controls 01_programs/app/data/stage01_controls_v3.csv \
        --out /tmp/stage01_scores_full.recomputed.parquet \
        --reference-parquet /home/tcelab/cs_scratch/stage01_scores_full.parquet

Exit status 0 iff the canonical hash matches the frozen target.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time

import numpy as np
import scipy.sparse as sp

# ---------------------------------------------------------------------------
# Frozen identities (registry v3 / STAGE1_REMEDIATION_METHOD.md)
# ---------------------------------------------------------------------------
TARGET_SCORES_SHA256 = "43c4296d5166740c334441a69df23bb440a073382bbe79628a3bb89e43d51316"
H5AD_SHA256 = "2edc6d318415c8b0ee779d707ab86e26ddb6f0274db51ab4a12f21ebfda50e43"
HF_REPO = "KiritSingh/spot-CD4-Marson"
HF_REVISION = "e5fcf98b56a9302921d402e97fc5a190bd88f9a6"
HF_FILENAME = "ntc_clustered.h5ad"
ACTADJ_PROGRAM_ID = "activation_predictor"  # controls_by_bin lane id in stage01_controls_v3.csv
ROUND_DECIMALS = 5


# ---------------------------------------------------------------------------
# IO helpers
# ---------------------------------------------------------------------------
def sha256_file(path: str, chunk: int = 1 << 22) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _decode(values) -> np.ndarray:
    return np.array([v.decode() if isinstance(v, (bytes, bytearray)) else str(v) for v in values],
                    dtype=object)


def read_obs_str(handle, key: str) -> np.ndarray:
    """Return an obs column as a decoded str object-array (handles AnnData categoricals)."""
    import h5py
    node = handle[f"obs/{key}"]
    if isinstance(node, h5py.Group):  # categorical: categories[codes]
        cats = _decode(node["categories"][:])
        codes = node["codes"][:]
        return cats[codes]
    return _decode(node[:])


def load_registry(path: str) -> dict:
    with open(path) as fh:
        return json.load(fh)


def load_controls(path: str) -> dict[str, list[str]]:
    """program_id -> ordered list of control gene symbols (CSV row order = bin, rank_in_bin)."""
    import csv as _csv
    out: dict[str, list[str]] = {}
    with open(path, newline="") as fh:
        for row in _csv.DictReader(fh):
            out.setdefault(row["program_id"], []).append(row["control_symbol"])
    return out


def maybe_fetch_h5ad(path: str) -> str:
    """If the h5ad is absent, download the pinned public revision from Hugging Face."""
    if os.path.exists(path):
        return path
    from huggingface_hub import hf_hub_download
    print(f"[fetch] {path} absent; downloading {HF_REPO}@{HF_REVISION}:{HF_FILENAME}", flush=True)
    got = hf_hub_download(repo_id=HF_REPO, filename=HF_FILENAME, revision=HF_REVISION,
                          repo_type="dataset")
    return got


# ---------------------------------------------------------------------------
# Core scoring
# ---------------------------------------------------------------------------
def build_panels(registry: dict) -> tuple[list[str], dict[str, list[str]], list[str], float, float]:
    """Return (primary_program_ids_in_order, panel_by_program, actadj_panel, slope, intercept)."""
    primary = [p["program_id"] for p in registry["programs"]]
    panel_by_program = {p["program_id"]: list(p["panel_genes_measured"]) for p in registry["programs"]}
    lane = registry["sensitivity_lanes"][0]
    ap = lane["activation_predictor"]
    return primary, panel_by_program, list(ap["panel_measured"]), float(ap["slope"]), float(ap["intercept"])


def _lane_columns(genes: list[str], name_to_i: dict[str, int]) -> list[int]:
    missing = [g for g in genes if g not in name_to_i]
    if missing:
        raise KeyError(f"genes absent from var_names (cannot score): {missing}")
    return [name_to_i[g] for g in genes]


def build_float64_submatrix(X, name_to_i, used_syms):
    """Memory-bounded reduction: slice only the gene columns any lane needs into a
    float64 submatrix, so the panel/control means are computed in float64 (matching the
    reference generator) without ever materializing the full matrix as float64.

    Returns (sub_csr_float64, local_name_to_i) where local_name_to_i maps a gene symbol
    to its column position inside ``sub``.
    """
    needed_global = sorted({name_to_i[g] for g in used_syms})
    gpos = {gcol: k for k, gcol in enumerate(needed_global)}
    sub = X[:, needed_global].astype(np.float64)  # float64 BEFORE any summation
    if not sp.isspmatrix_csr(sub):
        sub = sub.tocsr()
    local_name_to_i = {g: gpos[name_to_i[g]] for g in used_syms}
    return sub, local_name_to_i


def panel_mean(X: sp.csr_matrix, cols: list[int]) -> np.ndarray:
    """Per-cell mean of the (float64) matrix over the given gene columns (zeros included)."""
    return np.asarray(X[:, cols].mean(axis=1), dtype=np.float64).ravel()


def compute_scores(X, name_to_i, primary, panel_by_program, controls,
                   actadj_panel, slope, intercept):
    """Return an ordered dict {score_field: np.ndarray[float64]} for all 12 lanes."""
    scores: dict[str, np.ndarray] = {}
    for pid in primary:
        panel_cols = _lane_columns(panel_by_program[pid], name_to_i)
        ctrl_syms = controls[pid]
        ctrl_cols = _lane_columns(ctrl_syms, name_to_i)
        scores[f"{pid}_score"] = panel_mean(X, panel_cols) - panel_mean(X, ctrl_cols)

    # activation-adjusted CD4 CTL-like sensitivity lane
    act_panel_cols = _lane_columns(actadj_panel, name_to_i)
    act_ctrl_cols = _lane_columns(controls[ACTADJ_PROGRAM_ID], name_to_i)
    s_act = panel_mean(X, act_panel_cols) - panel_mean(X, act_ctrl_cols)
    raw_ctl = scores["cd4_ctl_like_score"]
    scores["cd4_ctl_like_score_actadj"] = raw_ctl - (slope * s_act + intercept)
    return scores


def score_field_order(primary: list[str]) -> list[str]:
    return [f"{pid}_score" for pid in primary] + ["cd4_ctl_like_score_actadj"]


# ---------------------------------------------------------------------------
# Canonicalization (byte-identical to _t8_staging/dcompute_tcefold.py)
# ---------------------------------------------------------------------------
def canonical_scores_sha256(barcode, donor, condition, scores, fields) -> str:
    order = np.argsort(barcode, kind="stable")
    hc = hashlib.sha256()
    cols = [scores[f] for f in fields]
    for i in order:
        r = [str(barcode[i]), str(donor[i]), str(condition[i])]
        r += [f"{round(float(c[i]), ROUND_DECIMALS):.5f}" for c in cols]
        hc.update(("\t".join(r) + "\n").encode())
    return hc.hexdigest()


# ---------------------------------------------------------------------------
# Load .X (memory-bounded: native-dtype CSR sliced to the needed columns, cast float64)
# ---------------------------------------------------------------------------
def load_X_and_obs(h5ad_path: str):
    import h5py
    with h5py.File(h5ad_path, "r") as handle:
        Xg = handle["X"]
        enc = Xg.attrs.get("encoding-type", b"")
        enc = enc.decode() if isinstance(enc, (bytes, bytearray)) else str(enc)
        if enc != "csr_matrix":
            raise ValueError(f"expected csr_matrix .X, got {enc!r}")
        shape = tuple(int(x) for x in Xg.attrs["shape"])
        data = Xg["data"][:]
        indices = Xg["indices"][:]
        indptr = Xg["indptr"][:]
        var_names = _decode(handle["var/_index"][:])
        barcode = read_obs_str(handle, "barcode")
        donor = read_obs_str(handle, "donor")
        condition = read_obs_str(handle, "condition")
    X = sp.csr_matrix((data, indices, indptr), shape=shape)
    return X, var_names, barcode, donor, condition


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    default_data = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "app", "data")
    ap.add_argument("--h5ad", default="ntc_clustered.h5ad",
                    help="path to the pinned public ntc_clustered.h5ad")
    ap.add_argument("--registry", default=os.path.join(default_data, "stage01_program_registry_v3.json"))
    ap.add_argument("--controls", default=os.path.join(default_data, "stage01_controls_v3.csv"))
    ap.add_argument("--out", default=None, help="optional output parquet path for the 396k table")
    ap.add_argument("--reference-parquet", default=None,
                    help="optional reference parquet to validate against column-by-column")
    ap.add_argument("--fetch", action="store_true",
                    help="download the pinned h5ad from Hugging Face if absent")
    ap.add_argument("--skip-sha", action="store_true", help="skip the ~4GB h5ad sha256 verification")
    args = ap.parse_args(argv)

    t0 = time.time()
    registry = load_registry(os.path.normpath(args.registry))
    controls = load_controls(os.path.normpath(args.controls))
    primary, panel_by_program, actadj_panel, slope, intercept = build_panels(registry)
    fields = score_field_order(primary)

    h5ad = maybe_fetch_h5ad(args.h5ad) if args.fetch else args.h5ad
    if not os.path.exists(h5ad):
        print(f"ERROR: h5ad not found at {h5ad} (use --fetch to download the pinned revision)",
              file=sys.stderr)
        return 2

    if not args.skip_sha:
        got = sha256_file(h5ad)
        ok = got == H5AD_SHA256
        print(f"[h5ad sha256] {got} {'OK' if ok else 'MISMATCH'} ({time.time()-t0:.1f}s)", flush=True)
        if not ok:
            print(f"ERROR: h5ad sha256 mismatch (expected {H5AD_SHA256})", file=sys.stderr)
            return 3

    print(f"[load] reading .X + obs from {h5ad}", flush=True)
    X, var_names, barcode, donor, condition = load_X_and_obs(h5ad)
    name_to_i = {g: i for i, g in enumerate(var_names)}
    print(f"[load] X shape={X.shape} nnz={X.nnz:,} dtype={X.dtype} ({time.time()-t0:.1f}s)", flush=True)

    used_syms = set(actadj_panel) | set(controls[ACTADJ_PROGRAM_ID])
    for pid in primary:
        used_syms |= set(panel_by_program[pid]) | set(controls[pid])
    sub, local_name_to_i = build_float64_submatrix(X, name_to_i, used_syms)
    del X
    print(f"[score] reduced to {sub.shape[1]} float64 gene columns; computing 12 lanes from .X",
          flush=True)
    scores = compute_scores(sub, local_name_to_i, primary, panel_by_program, controls,
                            actadj_panel, slope, intercept)
    del sub

    # canonical hash proof
    print("[hash] canonicalizing (stable barcode argsort, 5dp)", flush=True)
    got_hash = canonical_scores_sha256(barcode, donor, condition, scores, fields)
    match = got_hash == TARGET_SCORES_SHA256
    print(f"[hash] scores_canonical_content_sha256 = {got_hash}")
    print(f"[hash] target                          = {TARGET_SCORES_SHA256}")
    print(f"[hash] MATCH = {match}")

    # optional validation vs reference parquet (column-by-column, 5dp)
    if args.reference_parquet:
        import pyarrow.parquet as pq
        ref = pq.read_table(args.reference_parquet).to_pydict()
        ridx = {bc: i for i, bc in enumerate(ref["barcode"])}
        perm = np.array([ridx[str(bc)] for bc in barcode])
        print("[validate] max abs error vs reference parquet (per column):")
        worst = 0.0
        worst_5dp_mismatch = 0
        for f in fields:
            mine = scores[f]
            refv = np.asarray(ref[f], dtype=np.float64)[perm]
            err = float(np.max(np.abs(mine - refv)))
            n_bad = int(np.sum(np.round(mine, ROUND_DECIMALS) != np.round(refv, ROUND_DECIMALS)))
            worst = max(worst, err)
            worst_5dp_mismatch += n_bad
            print(f"    {f:32s} max_abs_err={err:.3e}  5dp_mismatch_cells={n_bad}")
        print(f"[validate] worst max_abs_err={worst:.3e}  total_5dp_mismatch_cells={worst_5dp_mismatch}")

    # optional parquet emission of the recomputed table
    if args.out:
        import pyarrow as pa
        import pyarrow.parquet as pq
        table = pa.table({"barcode": pa.array([str(b) for b in barcode]),
                          "donor": pa.array([str(b) for b in donor]),
                          "condition": pa.array([str(b) for b in condition]),
                          **{f: pa.array(np.round(scores[f], ROUND_DECIMALS)) for f in fields}})
        pq.write_table(table, args.out)
        print(f"[out] wrote {args.out}")

    print(f"[done] {time.time()-t0:.1f}s")
    return 0 if match else 1


if __name__ == "__main__":
    raise SystemExit(main())
