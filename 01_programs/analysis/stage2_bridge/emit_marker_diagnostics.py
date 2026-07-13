"""Stage-1 marker-level leave-one-marker-out (LOMO) DIAGNOSTICS (schema v2).

Derived from the hash-bound constituent evidence (no new compute). These are neutral, continuous
DIAGNOSTICS — NOT eligibility gates, NOT a binary single-gene label, and NO threshold. `use_for_eligibility`
is a hard `false`. The marker-removal robustness that produced the frozen 0/33 result is preserved as
historical evidence (`stage01_selectability_v3.json`) and reclassified here as descriptive.

Neutral naming (no "dominant" / no "breadth"):
  min_leave_one_marker_out_rho   : min spearman_rho(full, full-minus-marker) — LOWER = the panel score
                                   moves more when this marker is removed (continuous, not a label)
  max_leave_one_marker_out_shift : max median(|delta|)/iqr(full) on removal
  most_sensitive_removed_marker  : the removed marker with the lowest rho in that stratum (a pointer,
                                   not a verdict)

STRATIFIED so the SELECTED condition can be evaluated (never collapsed into one global worst):
per program × removed marker × condition summary + per-donor rows; plus a per-condition program summary.
"""
from __future__ import annotations

import json
import os

import canonical
import constituents as C

SCHEMA = "spot.stage01_marker_diagnostics.v2"
METHOD_VERSION = "stage1-continuous-v3.0.1"
CONDITIONS = list(C.CONDS)
DONORS = list(C.DONORS)

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYSIS = os.path.dirname(HERE)
PROGRAMS = os.path.dirname(ANALYSIS)
DATA = os.path.join(PROGRAMS, "app", "data")
STAGING = os.path.join(HERE, "_release_staging")

RHO_SUBCHECK = "lomo.spearman_rho_full_minus_gene"
SHIFT_SUBCHECK = "lomo.median_abs_delta_over_iqr"


def build_diagnostics() -> dict:
    rows, manifest = C.load_constituents(
        os.path.join(STAGING, "stage01_gate_constituents_v1.json.gz"),
        os.path.join(STAGING, "stage01_gate_constituents_v1.manifest.json"))

    # (program, marker, condition, donor) -> {rho, shift}
    cell = {}
    markers_of = {}
    for r in rows:
        sid = r["subcheck_id"]
        if sid not in (RHO_SUBCHECK, SHIFT_SUBCHECK):
            continue
        key = (r["program_id"], r["removed_marker"], r["condition"], r["donor"])
        c = cell.setdefault(key, {"rho": None, "shift": None})
        if sid == RHO_SUBCHECK:
            c["rho"] = r["value"] if r["metric_defined"] else None
        else:
            c["shift"] = r["value"] if r["metric_defined"] else None
        markers_of.setdefault(r["program_id"], set()).add(r["removed_marker"])

    programs = []
    for pid in sorted(markers_of):
        markers = []
        for mk in sorted(markers_of[pid]):
            by_condition = []
            for cond in CONDITIONS:
                donor_rows = []
                rhos, shifts, n_undef = [], [], 0
                for d in DONORS:
                    c = cell.get((pid, mk, cond, d), {"rho": None, "shift": None})
                    defined = c["rho"] is not None
                    if defined:
                        rhos.append(c["rho"])
                    if c["shift"] is not None:
                        shifts.append(c["shift"])
                    if not defined:
                        n_undef += 1
                    donor_rows.append({"donor": d, "rho": c["rho"], "shift": c["shift"], "defined": defined})
                by_condition.append({
                    "condition": cond,
                    "min_leave_one_marker_out_rho": (min(rhos) if rhos else None),
                    "max_leave_one_marker_out_shift": (max(shifts) if shifts else None),
                    "n_undefined": n_undef,
                    "donors": donor_rows,
                })
            markers.append({"removed_marker": mk, "by_condition": by_condition})

        per_condition = []
        for cond in CONDITIONS:
            best = None  # (min_rho, marker)
            for m in markers:
                bc = next(x for x in m["by_condition"] if x["condition"] == cond)
                if bc["min_leave_one_marker_out_rho"] is not None:
                    if best is None or bc["min_leave_one_marker_out_rho"] < best[0]:
                        best = (bc["min_leave_one_marker_out_rho"], m["removed_marker"])
            per_condition.append({
                "condition": cond,
                "most_sensitive_removed_marker": (best[1] if best else None),
                "min_leave_one_marker_out_rho": (best[0] if best else None),
            })
        programs.append({"program_id": pid, "n_markers": len(markers),
                         "markers": markers, "per_condition": per_condition})

    return {
        "schema_version": SCHEMA,
        "method_version": METHOD_VERSION,
        "use_for_eligibility": False,
        "source_constituent_content_sha256": manifest["content_canonical_sha256"],
        "conditions": CONDITIONS,
        "donors": DONORS,
        "n_programs": len(programs),
        "programs": programs,
    }


def write_diagnostics() -> tuple[dict, str, str]:
    d = build_diagnostics()
    raw = canonical.dumps_indent1(d)
    out = os.path.join(DATA, "stage01_marker_diagnostics_v2.json")
    with open(out, "w") as fh:
        fh.write(raw)
    return d, out, canonical.canonical_content_sha256(d)


if __name__ == "__main__":
    d, out, canon = write_diagnostics()
    print("wrote", os.path.relpath(out, PROGRAMS), "| programs:", d["n_programs"],
          "| use_for_eligibility:", d["use_for_eligibility"])
    print("content_canonical_sha256:", canon)
    for p in d["programs"]:
        s48 = next(x for x in p["per_condition"] if x["condition"] == "Stim48hr")
        print(f"  {p['program_id']:16s} n={p['n_markers']}  Stim48hr most_sensitive={s48['most_sensitive_removed_marker']}"
              f" min_rho={s48['min_leave_one_marker_out_rho']}")
