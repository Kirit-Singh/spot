"""CP3b — load the constituent evidence table and aggregate it to typed subchecks.

Definedness is authoritative per-constituent (from the frozen compute-host recompute), never inferred
from a numeric zero or a metric name. A subcheck passes ONLY if every expected constituent
stratum is present and defined and meets its comparator:

    subcheck_pass = (n_present == n_expected)      # completeness (no missing stratum)
                 && (n_undefined == 0)             # every stratum defined
                 && all(defined predicate_met)     # every defined stratum meets comparator

`worst_defined_value` (min for >=, max for <=) is preserved as a DIAGNOSTIC only and is
never used to pass a check. Duplicate constituent keys and duplicate aggregates are rejected
before any evaluation.
"""
from __future__ import annotations

import gzip
import json
import os

import canonical

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYSIS = os.path.dirname(HERE)
PROGRAMS = os.path.dirname(ANALYSIS)
DATA = os.path.join(PROGRAMS, "app", "data")

CONDS = ("Rest", "Stim8hr", "Stim48hr")
DONORS = ("D1", "D2", "D3", "D4")
N_ALT_SEEDS = 20

# subcheck_id -> (gate_family, gate_class, operator, threshold, grid_kind)
MEASUREMENT_SUBCHECKS = {
    "coverage.n_panel_genes_used":
        ("global_coverage", "measurement_validity", ">=", 3, "program"),
    "condition_measurability.panel_score_iqr":
        ("condition_measurability", "measurement_validity", ">", 0, "donor"),
    "condition_measurability.n_panel_genes_detected_ge_1pct_cells":
        ("condition_measurability", "measurement_validity", ">=", 2, "donor"),
    "lomo.spearman_rho_full_minus_gene":
        ("lomo_panel_robustness", "measurement_validity", ">=", 0.80, "marker_donor"),
    "lomo.median_abs_delta_over_iqr":
        ("lomo_panel_robustness", "measurement_validity", "<=", 0.25, "marker_donor"),
    "control_draw.spearman_rho_primary_alt":
        ("control_draw_sensitivity", "measurement_validity", ">=", 0.90, "seed_donor"),
    "control_draw.abs_median_delta_over_iqr":
        ("control_draw_sensitivity", "measurement_validity", "<=", 0.25, "seed_donor"),
}
PORTABILITY_SUBCHECKS = {
    "base_portability.n_panel_in_effect_universe":
        ("stage2_base_portability", "base_portability", ">=", 3, "program"),
    "base_portability.n_control_in_effect_universe":
        ("stage2_base_portability", "base_portability", ">=", 10, "program"),
}
# the SEVEN production measurement subchecks (coverage 1 + condition 2 + LOMO 2 + control 2)
MEASUREMENT_HARD_GATE_IDS = tuple(MEASUREMENT_SUBCHECKS)


class ConstituentError(ValueError):
    """The constituent evidence could not be trusted. Refuse; never downgrade."""


def _require(cond, msg):
    if not cond:
        raise ConstituentError(msg)


def load_registry_markers() -> dict:
    reg = json.load(open(os.path.join(DATA, "stage01_program_registry_v3.json")))
    return {p["program_id"]: len(p["panel_genes_measured"])
            for p in reg["programs"] if p.get("role") == "primary"}


def load_constituents(mirror_path: str, manifest_path: str) -> tuple[list, dict]:
    with gzip.open(mirror_path, "rt", encoding="utf-8") as fh:
        rows = json.load(fh)
    manifest = json.load(open(manifest_path))
    got = canonical.content_hash(rows)
    _require(got == manifest["content_canonical_sha256"],
             f"constituent content hash mismatch: {got} != {manifest['content_canonical_sha256']}")
    _require(len(rows) == manifest["row_count"],
             f"constituent row count {len(rows)} != manifest {manifest['row_count']}")
    return rows, manifest


def _key(r) -> tuple:
    return (r["subcheck_id"], r["program_id"], r["condition"], r["donor"],
            r["removed_marker"], r["alt_seed"])


def expected_grid(subcheck_id: str, program_id: str, n_markers: dict) -> int:
    fam, cls, op, thr, kind = {**MEASUREMENT_SUBCHECKS, **PORTABILITY_SUBCHECKS}[subcheck_id]
    if kind == "program":
        return 1
    if kind == "donor":
        return len(DONORS)
    if kind == "marker_donor":
        return n_markers[program_id] * len(DONORS)
    if kind == "seed_donor":
        return N_ALT_SEEDS * len(DONORS)
    raise ConstituentError(f"unknown grid kind {kind}")


def _worst_defined(defined_values: list, operator: str):
    if not defined_values:
        return None
    return min(defined_values) if operator in (">=", ">") else max(defined_values)


def aggregate(rows: list, n_markers: dict) -> dict:
    """Return {(program_id, condition_or_None, subcheck_id): aggregate}. Rejects duplicate
    constituent keys before evaluating anything."""
    seen = set()
    grouped: dict = {}
    for r in rows:
        k = _key(r)
        _require(k not in seen, f"duplicate constituent key: {k}")
        seen.add(k)
        # program-level subchecks (coverage/portability) collapse condition to None
        _, _, _, _, kind = {**MEASUREMENT_SUBCHECKS, **PORTABILITY_SUBCHECKS}[r["subcheck_id"]]
        cond = None if kind == "program" else r["condition"]
        grouped.setdefault((r["program_id"], cond, r["subcheck_id"]), []).append(r)

    out = {}
    for (pid, cond, sid), members in grouped.items():
        fam, cls, op, thr, kind = {**MEASUREMENT_SUBCHECKS, **PORTABILITY_SUBCHECKS}[sid]
        n_expected = expected_grid(sid, pid, n_markers)
        n_present = len(members)
        defined = [m for m in members if m["metric_defined"]]
        undefined = [m for m in members if not m["metric_defined"]]
        defined_values = [m["value"] for m in defined]
        # every stratum's predicate_met must already be computed consistently by the generator
        for m in defined:
            _require(m["predicate_met"] is not None,
                     f"defined constituent has null predicate_met: {_key(m)}")
        complete = n_present == n_expected
        all_defined_pass = all(m["predicate_met"] for m in defined)
        subcheck_pass = complete and (len(undefined) == 0) and all_defined_pass
        out[(pid, cond, sid)] = {
            "program_id": pid, "condition": cond, "subcheck_id": sid,
            "gate_family": fam, "gate_class": cls, "operator": op, "threshold": thr,
            "n_expected": n_expected, "n_present": n_present,
            "n_defined": len(defined), "n_undefined": len(undefined),
            "complete": complete,
            "all_defined_predicates_pass": all_defined_pass,
            "subcheck_pass": bool(subcheck_pass),
            "worst_defined_value": _worst_defined(defined_values, op),
            "measurement_state": "undefined" if len(undefined) > 0 else "measured",
            "undefined_reasons": sorted({m["undefined_reason"] for m in undefined if m["undefined_reason"]}),
        }
    return out
