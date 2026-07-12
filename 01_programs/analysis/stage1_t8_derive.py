#!/usr/bin/env python3
"""Pure derivation of the Stage-1 T8 selectability records + validation-semantics rows from the
IMMUTABLE T7b validation artifact, with per-metric DEFINEDNESS taken from the hash-bound
constituent-evidence tables (never a value/name heuristic).

USED BY THE GENERATOR ONLY. The standalone verifier (verify_stage1_t8.py) deliberately re-implements
this same derivation independently (its own constituent rollup) and MUST NOT import from this module
for its substantive checks (generator != verifier). The shared trust anchor is the hash-bound
constituent table (independently reconstructed from .X on tcefold by verify_gate_constituents.py),
NOT a shared Python function.

Definedness contract (CP3c amendment):
  * A hard/overlay/donor metric's aggregate is DEFINED iff every expected constituent stratum is
    defined (n_undefined_constituents == 0). Definedness is read per-constituent from the frozen
    denominator (iqr>0) / correlation, NEVER from `observed_value == 0` or the metric name. A real
    zero numerator over a positive denominator is a DEFINED zero.
  * `metric_predicate_met` (aggregate) = completeness AND every constituent defined AND every defined
    constituent meets its comparator = the frozen per-check `pass`. Asserted equal to raw `pass`.
  * The 8 wholly-undefined + 2 partially-undefined LOMO/control aggregates are undefined; the 9
    frozen zero-numerator (pass:true) rows stay DEFINED.

No p/q/FDR, no categorical cell labels, no retuning. A false hard-gate is never reinterpreted as
advisory (or vice versa); undefinedness is preserved.
"""
import gzip
import hashlib
import json
import os

# ---- gate taxonomy: how each pre-registered gate's `pass` must be interpreted --------------------
HARD_SELECTABILITY_GATES = {"global_coverage", "condition_measurability", "lomo_panel_robustness", "control_draw_sensitivity"}
STRUCTURAL_GATE = {"selection_preflight"}                 # structural; undefined when no valid selection exists
PORTABILITY_GATE = {"stage2_base_portability"}            # SEPARATE; never confers selectability
OVERLAY_RELEASE_GATES = {"overlay_composition", "overlay_distributions", "overlay_correlations"}
ADVISORY_GATES = {"pair_redundancy", "off_axis_association", "donor_sensitivity"}  # flag/record only
DESCRIPTIVE_GATES = {"cp10k_v2_comparison"}               # undefined/descriptive; not numeric evidence

# ---- constituent-evidence tables (hash-bound; produced + independently verified on tcefold) ------
HERE = os.path.dirname(os.path.abspath(__file__))
STAGING = os.path.join(HERE, "stage2_bridge", "_release_staging")
MAIN_GZ = os.path.join(STAGING, "stage01_gate_constituents_v1.json.gz")
MAIN_MANIFEST = os.path.join(STAGING, "stage01_gate_constituents_v1.manifest.json")
OVL_GZ = os.path.join(STAGING, "stage01_gate_constituents_overlay_donor_v1.json.gz")
OVL_MANIFEST = os.path.join(STAGING, "stage01_gate_constituents_overlay_donor_v1.manifest.json")

# constituent subcheck_id -> the (gate_id, metric) of the frozen validation result it explains.
CONSTITUENT_TO_FROZEN = {
    "coverage.n_panel_genes_used": ("global_coverage", "n_panel_genes_used"),
    "condition_measurability.panel_score_iqr": ("condition_measurability", "panel_score_iqr"),
    "condition_measurability.n_panel_genes_detected_ge_1pct_cells":
        ("condition_measurability", "n_panel_genes_detected_ge_1pct_cells"),
    "lomo.spearman_rho_full_minus_gene":
        ("lomo_panel_robustness", "spearman_rho(panel_mean_full, panel_mean_minus_gene)"),
    "lomo.median_abs_delta_over_iqr":
        ("lomo_panel_robustness", "median(abs(delta_panel))/iqr(panel_mean_full)"),
    "control_draw.spearman_rho_primary_alt":
        ("control_draw_sensitivity", "spearman_rho(score_primary, score_alt_seed)"),
    "control_draw.abs_median_delta_over_iqr":
        ("control_draw_sensitivity", "abs(median_alt - median_primary)/iqr_primary"),
    "base_portability.n_panel_in_effect_universe":
        ("stage2_base_portability", "n_panel_in_effect_universe"),
    "base_portability.n_control_in_effect_universe":
        ("stage2_base_portability", "n_control_in_effect_universe"),
    # companion (non-production) ratio metrics the deleted heuristic mislabelled
    "overlay_distributions.abs_median_over_iqr":
        ("overlay_distributions", "abs(median_overlay - median_full)/iqr_full"),
    "donor_sensitivity.lodo_ratio":
        ("donor_sensitivity", "max_lodo(abs(median_3donor - median_4donor)/iqr_4donor)"),
}
# program-level subchecks whose stratum is the program alone (no condition suffix).
_PROGRAM_LEVEL_SUBCHECKS = {"coverage.n_panel_genes_used",
                            "base_portability.n_panel_in_effect_universe",
                            "base_portability.n_control_in_effect_universe"}
# comparator direction per subcheck (for the defined extremum).
_OP = {
    "coverage.n_panel_genes_used": ">=",
    "condition_measurability.panel_score_iqr": ">",
    "condition_measurability.n_panel_genes_detected_ge_1pct_cells": ">=",
    "lomo.spearman_rho_full_minus_gene": ">=",
    "lomo.median_abs_delta_over_iqr": "<=",
    "control_draw.spearman_rho_primary_alt": ">=",
    "control_draw.abs_median_delta_over_iqr": "<=",
    "base_portability.n_panel_in_effect_universe": ">=",
    "base_portability.n_control_in_effect_universe": ">=",
    "overlay_distributions.abs_median_over_iqr": "<=",
    "donor_sensitivity.lodo_ratio": ">",
}


def _canonical_content_sha256(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True, allow_nan=False).encode()).hexdigest()


def _load_gz_verified(gz_path, manifest_path):
    with gzip.open(gz_path, "rt", encoding="utf-8") as fh:
        rows = json.load(fh)
    manifest = json.load(open(manifest_path))
    got = _canonical_content_sha256(rows)
    if got != manifest["content_canonical_sha256"]:
        raise ValueError(f"constituent content hash mismatch for {os.path.basename(gz_path)}: "
                         f"{got} != {manifest['content_canonical_sha256']}")
    if len(rows) != manifest["row_count"]:
        raise ValueError(f"constituent row count mismatch for {os.path.basename(gz_path)}")
    return rows, manifest


def _worst_defined(values, op):
    if not values:
        return None
    return min(values) if op in (">=", ">") else max(values)


def build_definedness_index(staging_dir=STAGING):
    """Aggregate the two hash-bound constituent tables into
    (gate_id, metric, stratum_instance) -> aggregate-definedness dict, plus the binding evidence.

    Definedness is read per-constituent from the frozen `metric_defined` flag (denominator/correlation),
    NEVER from a numeric zero or a metric name.
    """
    main_gz = os.path.join(staging_dir, "stage01_gate_constituents_v1.json.gz")
    main_mf = os.path.join(staging_dir, "stage01_gate_constituents_v1.manifest.json")
    ovl_gz = os.path.join(staging_dir, "stage01_gate_constituents_overlay_donor_v1.json.gz")
    ovl_mf = os.path.join(staging_dir, "stage01_gate_constituents_overlay_donor_v1.manifest.json")

    main_rows, main_manifest = _load_gz_verified(main_gz, main_mf)
    ovl_rows, ovl_manifest = _load_gz_verified(ovl_gz, ovl_mf)

    grouped = {}   # (gate_id, metric, stratum_instance) -> list of constituent rows
    for r in main_rows + ovl_rows:
        sid = r["subcheck_id"]
        gm = CONSTITUENT_TO_FROZEN.get(sid)
        if gm is None:
            continue
        gate_id, metric = gm
        if sid in _PROGRAM_LEVEL_SUBCHECKS:
            stratum = r["program_id"]
        else:
            stratum = f"{r['program_id']}|{r['condition']}"
        grouped.setdefault((gate_id, metric, stratum), []).append((sid, r))

    index = {}
    for key, members in grouped.items():
        sid = members[0][0]
        op = _OP[sid]
        rows = [m[1] for m in members]
        defined = [r for r in rows if r["metric_defined"]]
        undefined = [r for r in rows if not r["metric_defined"]]
        # every defined constituent must carry a boolean predicate_met (generator invariant)
        for r in defined:
            if r.get("predicate_met") is None:
                raise ValueError(f"defined constituent with null predicate_met in {key}")
        n_present = len(rows)
        n_defined = len(defined)
        n_undefined = len(undefined)
        all_defined_pass = all(bool(r["predicate_met"]) for r in defined)
        metric_defined = n_undefined == 0
        metric_predicate_met = metric_defined and all_defined_pass
        reasons = sorted({r["undefined_reason"] for r in undefined if r.get("undefined_reason")})
        if n_undefined == 0:
            reason = None
        elif n_defined == 0:
            reason = "all_constituents_undefined(" + ",".join(reasons) + ")"
        else:
            reason = "partial_constituents_undefined(" + ",".join(reasons) + ")"
        index[key] = {
            "subcheck_id": sid,
            "n_present": n_present,
            "n_defined": n_defined,
            "n_undefined": n_undefined,
            "all_defined_predicates_pass": all_defined_pass,
            "metric_defined": bool(metric_defined),
            "metric_predicate_met": bool(metric_predicate_met),
            "worst_defined_value": _worst_defined([r["value"] for r in defined], op),
            "undefined_reason": reason,
        }
    evidence = {
        "main": {"artifact": os.path.basename(main_gz),
                 "content_canonical_sha256": main_manifest["content_canonical_sha256"],
                 "raw_sha256": _raw_sha256(main_gz), "row_count": main_manifest["row_count"],
                 "manifest_raw_sha256": _raw_sha256(main_mf)},
        "overlay_donor": {"artifact": os.path.basename(ovl_gz),
                          "content_canonical_sha256": ovl_manifest["content_canonical_sha256"],
                          "raw_sha256": _raw_sha256(ovl_gz), "row_count": ovl_manifest["row_count"],
                          "manifest_raw_sha256": _raw_sha256(ovl_mf)},
        "note": ("Per-metric definedness is read from these hash-bound constituent tables (aggregate is "
                 "defined iff every expected constituent is defined); the deleted zero-value/name "
                 "heuristic is not used anywhere."),
    }
    return index, evidence


def _raw_sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest() if path and os.path.exists(path) else None


def semantic_class(gate_id):
    if gate_id in HARD_SELECTABILITY_GATES: return "hard_selectability"
    if gate_id in STRUCTURAL_GATE: return "structural_selection"
    if gate_id in PORTABILITY_GATE: return "portability_not_selectability"
    if gate_id in OVERLAY_RELEASE_GATES: return "overlay_release"
    if gate_id in ADVISORY_GATES: return "advisory_flag"
    if gate_id in DESCRIPTIVE_GATES: return "descriptive_undefined"
    return "unknown"


def _constituent_key(r):
    return (r["gate_id"], r.get("metric"), r.get("stratum_instance"))


def metric_defined(r, defmap):
    """Is the underlying METRIC defined? From the hash-bound constituent evidence when available,
    else by class (descriptive/structural undefined) or the presence of a numeric observation.
    NEVER inferred from a numeric zero or a metric name."""
    gid = r["gate_id"]
    if gid in DESCRIPTIVE_GATES or gid in STRUCTURAL_GATE:
        return False
    agg = defmap.get(_constituent_key(r))
    if agg is not None:
        return agg["metric_defined"]
    # no constituent table for this metric (ecdf / composition / correlations / advisory rho):
    # defined iff the generator emitted a numeric observation. No value/name heuristic.
    return r.get("observed_value") is not None


def undefined_reason(r, defmap):
    """Exact reason a metric is undefined, or None if defined."""
    gid = r["gate_id"]
    if gid in DESCRIPTIVE_GATES:
        return "descriptive_only"
    if gid in STRUCTURAL_GATE:
        return "no_valid_selection_to_evaluate"
    agg = defmap.get(_constituent_key(r))
    if agg is not None:
        return agg["undefined_reason"]
    if r.get("observed_value") is None:
        return "observed_value_none"
    return None


def metric_predicate_met(r, defmap):
    """Completeness AND every constituent defined AND every defined constituent meets its comparator.
    Only meaningful for constituent-backed metric rows; None otherwise."""
    agg = defmap.get(_constituent_key(r))
    if agg is None:
        return None
    return agg["metric_predicate_met"]


def hard_gate_detail(rr, defmap):
    """The exact, order-stable failure/undefined detail for one hard/structural result."""
    return {
        "gate_id": rr["gate_id"],
        "stratum_instance": rr.get("stratum_instance"),
        "metric": rr.get("metric"),
        "observed_value": rr.get("observed_value"),
        "operator": rr.get("operator"),
        "threshold": rr.get("threshold"),
        "result": "fail" if rr.get("pass") is False else "undefined",
        "metric_defined": metric_defined(rr, defmap),
        "undefined_reason": undefined_reason(rr, defmap),
        "consequence": rr.get("consequence"),
        "worst_donor": rr.get("worst_donor"),
        "worst_marker": rr.get("worst_marker"),
        "worst_seed": rr.get("worst_seed"),
    }


def derive_selectability_records(v, defmap):
    """33 records deterministically derived from the immutable validation + constituent definedness.

    For each program x condition, list the EXACT failing/undefined hard-gate detail rows (a multiset,
    not a set). production_selectable is always False under the frozen 0/33 outcome, but derived.
    """
    sel_in = v["stage1_selectable_by_condition"]
    by_key = {}
    for r in v["results"]:
        by_key.setdefault((r["gate_id"], r.get("stratum_instance")), []).append(r)

    records = []
    for key in sorted(sel_in):
        prog, cond = key.split("|", 1)
        raw = sel_in[key]
        details = []
        for gid in raw.get("failing_or_undefined_gates", []):
            cands = by_key.get((gid, key)) or by_key.get((gid, prog)) or []
            picked = None
            for rr in cands:
                if rr.get("pass") is False or rr.get("pass") is None:
                    picked = rr
                    break
            if picked is not None:
                by_key[(gid, key)] = [x for x in cands if x is not picked] + ([picked] if picked in cands else [])
                details.append(hard_gate_detail(picked, defmap))
        derived_selectable = bool(raw.get("stage1_selectable") is True and not details)
        records.append({
            "program_id": prog,
            "condition": cond,
            "production_selectable": derived_selectable,
            "raw_stage1_selectable": raw.get("stage1_selectable"),
            "failed_or_undefined_hard_gates": details,
        })
    return records


def derive_semantics_rows(v, row_hash_fn, defmap):
    """One semantics row per raw validation result, in immutable result order.

    Preserves the metric-level definedness (from the hash-bound constituents) AND the gate-level
    outcome. Terminology (CP3c amendment):
      raw_pass                    = the frozen results[*].pass (original ALL-constituents outcome)
      source_worst_defined_value  = the frozen observed_value (lossy extremum over DEFINED constituents)
      metric_defined              = every expected constituent defined (n_undefined == 0)
      metric_predicate_met        = completeness AND every constituent defined AND all defined pass
    """
    rows = []
    for i, r in enumerate(v["results"]):
        cls = semantic_class(r["gate_id"])
        p = r.get("pass")
        mdef = metric_defined(r, defmap)
        agg = defmap.get(_constituent_key(r))
        row = {
            "source_result_index": i,
            "gate_id": r["gate_id"],
            "stratum_instance": r.get("stratum_instance"),
            "metric": r.get("metric"),
            "operator": r.get("operator"),
            "threshold": r.get("threshold"),
            "semantic_class": cls,
            "raw_pass": p,
            "source_worst_defined_value": r.get("observed_value"),
            "metric_defined": mdef,
            "undefined_reason": undefined_reason(r, defmap),
            "metric_predicate_met": None,
            "gate_outcome": None,
            "flagged": None,
            "source_row_canonical_sha256": row_hash_fn(r),
        }
        if agg is not None:
            row["n_defined_constituents"] = agg["n_defined"]
            row["n_undefined_constituents"] = agg["n_undefined"]
        if cls == "hard_selectability":
            # metric predicate re-derived from constituents; must reproduce the frozen `pass`.
            mpm = metric_predicate_met(r, defmap)
            if mpm is not None and bool(mpm) != bool(p):
                raise ValueError(f"constituent metric_predicate_met {mpm} != frozen pass {p} "
                                 f"for {r['gate_id']} {r.get('metric')} {r.get('stratum_instance')}")
            row["metric_predicate_met"] = mpm
            row["gate_outcome"] = p
        elif cls == "portability_not_selectability":
            row["gate_outcome"] = p
        elif cls == "overlay_release":
            row["gate_outcome"] = p
        elif cls == "advisory_flag":
            row["flagged"] = (False if p is True else True)
        elif cls in ("structural_selection", "descriptive_undefined"):
            row["gate_outcome"] = p
        rows.append(row)
    return rows
