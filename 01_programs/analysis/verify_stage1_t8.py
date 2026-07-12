#!/usr/bin/env python3
"""INDEPENDENT standalone verifier for the fail-closed Stage-1 T8 production layer.

Adversarial design (generator != verifier): this file re-implements the selectability + semantics
derivation, the canonical-hash rule, AND the per-metric definedness rollup FROM SCRATCH. It
deliberately does NOT import the generator's / stage1_t8_derive's table/hash/definedness helpers for
any substantive check, so an attacker who edits the generator (or recomputes an artifact's self-hash
after forging its contents) is still caught here.

Definedness (CP3c): per-metric definedness is read from the HASH-BOUND constituent-evidence tables
(a metric is defined iff every expected constituent stratum is defined). The zero-value/name heuristic
is deleted. The constituent tables were independently reconstructed from .X on tcefold by
verify_gate_constituents.py; here we independently roll them up and bind them to the immutable
validation's frozen inputs.

Fail-closed: exits non-zero on ANY failure.
"""
import gzip
import hashlib
import json
import os
import sys

VALIDATION_RAW_SHA = "1c14cd2884117f03bd26b56ff32d5575d92caa53c5391fa0e7e0ed4f3c815371"
SELECTABILITY_RAW_SHA = "7c326a86d4586a851f5b91fb6f7e9796946e52eb41fe60123b41a6d3471d2420"

# constituent-evidence tables + their pinned canonical-content hashes (independent trust anchors).
HERE = os.path.dirname(os.path.abspath(__file__))
STAGING = os.path.join(HERE, "stage2_bridge", "_release_staging")
MAIN_GZ = os.path.join(STAGING, "stage01_gate_constituents_v1.json.gz")
MAIN_MANIFEST = os.path.join(STAGING, "stage01_gate_constituents_v1.manifest.json")
OVL_GZ = os.path.join(STAGING, "stage01_gate_constituents_overlay_donor_v1.json.gz")
OVL_MANIFEST = os.path.join(STAGING, "stage01_gate_constituents_overlay_donor_v1.manifest.json")
MAIN_CONTENT_SHA = "1813cab50df528391d5e07dc2503afd65c1d30cbdb2fa1934e2e25840bd2076a"
OVL_CONTENT_SHA = "10e76d83cb76ca7316a0578bba95f7f311685a25feb9e2b772beb1cd610d67df"

# --- independent taxonomy (re-declared, NOT imported) ---
_HARD = {"global_coverage", "condition_measurability", "lomo_panel_robustness", "control_draw_sensitivity"}
_STRUCT = {"selection_preflight"}
_PORT = {"stage2_base_portability"}
_OVERLAY = {"overlay_composition", "overlay_distributions", "overlay_correlations"}
_ADVISORY = {"pair_redundancy", "off_axis_association", "donor_sensitivity"}
_DESC = {"cp10k_v2_comparison"}

# constituent subcheck_id -> frozen (gate_id, metric); program-level subchecks; comparator direction.
_SUB2FROZEN = {
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
    "overlay_distributions.abs_median_over_iqr":
        ("overlay_distributions", "abs(median_overlay - median_full)/iqr_full"),
    "donor_sensitivity.lodo_ratio":
        ("donor_sensitivity", "max_lodo(abs(median_3donor - median_4donor)/iqr_4donor)"),
}
_PROGRAM_LEVEL = {"coverage.n_panel_genes_used", "base_portability.n_panel_in_effect_universe",
                  "base_portability.n_control_in_effect_universe"}
_OPDIR = {
    "coverage.n_panel_genes_used": ">=", "condition_measurability.panel_score_iqr": ">",
    "condition_measurability.n_panel_genes_detected_ge_1pct_cells": ">=",
    "lomo.spearman_rho_full_minus_gene": ">=", "lomo.median_abs_delta_over_iqr": "<=",
    "control_draw.spearman_rho_primary_alt": ">=", "control_draw.abs_median_delta_over_iqr": "<=",
    "base_portability.n_panel_in_effect_universe": ">=", "base_portability.n_control_in_effect_universe": ">=",
    "overlay_distributions.abs_median_over_iqr": "<=", "donor_sensitivity.lodo_ratio": ">",
}

FAILS = []
def check(name, ok, detail=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail and not ok else ""))
    if not ok: FAILS.append(name)


# --- independent primitives (own copies) ---
def _raw(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest() if path and os.path.exists(path) else None

def _canon(obj):
    d = {k: val for k, val in obj.items() if k != "self_canonical_sha256"}
    return hashlib.sha256(json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

def _rowhash(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

def _content_canon(rows):
    return hashlib.sha256(json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()).hexdigest()

def _sclass(gid):
    if gid in _HARD: return "hard_selectability"
    if gid in _STRUCT: return "structural_selection"
    if gid in _PORT: return "portability_not_selectability"
    if gid in _OVERLAY: return "overlay_release"
    if gid in _ADVISORY: return "advisory_flag"
    if gid in _DESC: return "descriptive_undefined"
    return "unknown"


# --- independent constituent rollup -> definedness index ---
def _build_defmap():
    def load(gz, mf, pinned):
        rows = json.load(gzip.open(gz, "rt", encoding="utf-8"))
        manifest = json.load(open(mf))
        c = _content_canon(rows)
        if c != manifest["content_canonical_sha256"] or c != pinned:
            raise SystemExit(f"VERIFY ABORT: constituent content hash {c} != manifest/pinned for {os.path.basename(gz)}")
        return rows, manifest
    main_rows, main_mf = load(MAIN_GZ, MAIN_MANIFEST, MAIN_CONTENT_SHA)
    ovl_rows, ovl_mf = load(OVL_GZ, OVL_MANIFEST, OVL_CONTENT_SHA)
    grouped = {}
    for r in main_rows + ovl_rows:
        sid = r["subcheck_id"]
        gm = _SUB2FROZEN.get(sid)
        if gm is None:
            continue
        gate_id, metric = gm
        stratum = r["program_id"] if sid in _PROGRAM_LEVEL else f"{r['program_id']}|{r['condition']}"
        grouped.setdefault((gate_id, metric, stratum), []).append((sid, r))
    idx = {}
    for key, members in grouped.items():
        sid = members[0][0]; op = _OPDIR[sid]; rows = [m[1] for m in members]
        defined = [r for r in rows if r["metric_defined"]]
        undefined = [r for r in rows if not r["metric_defined"]]
        for r in defined:
            if r.get("predicate_met") is None:
                raise SystemExit(f"VERIFY ABORT: defined constituent null predicate_met {key}")
        n_def, n_und = len(defined), len(undefined)
        all_pass = all(bool(r["predicate_met"]) for r in defined)
        md = n_und == 0
        mpm = md and all_pass
        reasons = sorted({r["undefined_reason"] for r in undefined if r.get("undefined_reason")})
        if n_und == 0:
            reason = None
        elif n_def == 0:
            reason = "all_constituents_undefined(" + ",".join(reasons) + ")"
        else:
            reason = "partial_constituents_undefined(" + ",".join(reasons) + ")"
        vals = [r["value"] for r in defined]
        worst = (None if not vals else (min(vals) if op in (">=", ">") else max(vals)))
        idx[key] = {"n_defined": n_def, "n_undefined": n_und, "metric_defined": md,
                    "metric_predicate_met": mpm, "worst_defined_value": worst, "undefined_reason": reason}
    evidence = {
        "main": {"content_canonical_sha256": main_mf["content_canonical_sha256"], "row_count": main_mf["row_count"]},
        "overlay_donor": {"content_canonical_sha256": ovl_mf["content_canonical_sha256"], "row_count": ovl_mf["row_count"]},
    }
    inputs = {"main": main_mf["inputs"], "ovl": ovl_mf["inputs"]}
    return idx, evidence, inputs


def _ckey(r):
    return (r["gate_id"], r.get("metric"), r.get("stratum_instance"))

def _mdefined(r, defmap):
    gid = r["gate_id"]
    if gid in _DESC or gid in _STRUCT:
        return False
    agg = defmap.get(_ckey(r))
    if agg is not None:
        return agg["metric_defined"]
    return r.get("observed_value") is not None

def _ureason(r, defmap):
    gid = r["gate_id"]
    if gid in _DESC: return "descriptive_only"
    if gid in _STRUCT: return "no_valid_selection_to_evaluate"
    agg = defmap.get(_ckey(r))
    if agg is not None:
        return agg["undefined_reason"]
    if r.get("observed_value") is None:
        return "observed_value_none"
    return None

def _mpm(r, defmap):
    agg = defmap.get(_ckey(r))
    return None if agg is None else agg["metric_predicate_met"]


def _derive_records(v, defmap):
    """Independent re-derivation of the 33 selectability records."""
    sel_in = v["stage1_selectable_by_condition"]
    by_key = {}
    for r in v["results"]:
        by_key.setdefault((r["gate_id"], r.get("stratum_instance")), []).append(r)
    out = []
    for key in sorted(sel_in):
        prog, cond = key.split("|", 1)
        raw = sel_in[key]
        details = []
        for gid in raw.get("failing_or_undefined_gates", []):
            cands = by_key.get((gid, key)) or by_key.get((gid, prog)) or []
            picked = None
            for rr in cands:
                if rr.get("pass") is False or rr.get("pass") is None:
                    picked = rr; break
            if picked is not None:
                by_key[(gid, key)] = [x for x in cands if x is not picked] + [picked]
                details.append({
                    "gate_id": picked["gate_id"], "stratum_instance": picked.get("stratum_instance"),
                    "metric": picked.get("metric"), "observed_value": picked.get("observed_value"),
                    "operator": picked.get("operator"), "threshold": picked.get("threshold"),
                    "result": "fail" if picked.get("pass") is False else "undefined",
                    "metric_defined": _mdefined(picked, defmap), "undefined_reason": _ureason(picked, defmap),
                    "consequence": picked.get("consequence"), "worst_donor": picked.get("worst_donor"),
                    "worst_marker": picked.get("worst_marker"), "worst_seed": picked.get("worst_seed")})
        out.append({"program_id": prog, "condition": cond,
                    "production_selectable": bool(raw.get("stage1_selectable") is True and not details),
                    "raw_stage1_selectable": raw.get("stage1_selectable"),
                    "failed_or_undefined_hard_gates": details})
    return out


def _derive_semantics(v, defmap):
    """Independent re-derivation of the full semantics row table (CP3c fields)."""
    out = []
    for i, r in enumerate(v["results"]):
        cls = _sclass(r["gate_id"]); p = r.get("pass"); md = _mdefined(r, defmap)
        agg = defmap.get(_ckey(r))
        row = {"source_result_index": i, "gate_id": r["gate_id"], "stratum_instance": r.get("stratum_instance"),
               "metric": r.get("metric"), "operator": r.get("operator"), "threshold": r.get("threshold"),
               "semantic_class": cls, "raw_pass": p, "source_worst_defined_value": r.get("observed_value"),
               "metric_defined": md, "undefined_reason": _ureason(r, defmap),
               "metric_predicate_met": None, "gate_outcome": None, "flagged": None,
               "source_row_canonical_sha256": _rowhash(r)}
        if agg is not None:
            row["n_defined_constituents"] = agg["n_defined"]
            row["n_undefined_constituents"] = agg["n_undefined"]
        if cls == "hard_selectability":
            mpm = _mpm(r, defmap)
            if mpm is not None and bool(mpm) != bool(p):
                raise SystemExit(f"VERIFY ABORT: metric_predicate_met {mpm} != frozen pass {p} for {_ckey(r)}")
            row["metric_predicate_met"] = mpm
            row["gate_outcome"] = p
        elif cls in ("portability_not_selectability", "overlay_release", "structural_selection", "descriptive_undefined"):
            row["gate_outcome"] = p
        elif cls == "advisory_flag":
            row["flagged"] = (False if p is True else True)
        out.append(row)
    return out


def _canonlist(objs):
    return sorted(json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False) for o in objs)


def main(data_dir=None):
    d = data_dir or os.path.join(os.path.dirname(__file__), "..", "app", "data")
    def PP(n): return os.path.join(d, n)
    v = json.load(open(PP("stage01_validation.json")))

    # 0) immutable validation hash guard
    check("validation_raw_sha_pinned", _raw(PP("stage01_validation.json")) == VALIDATION_RAW_SHA)

    # 0b) constituent evidence: content hashes reproduce (pinned) + bind to the frozen validation inputs
    defmap, evidence, cinputs = _build_defmap()
    hb = v.get("hash_bundle", {})
    val_h5ad = (hb.get("input_h5ad") or {}).get("raw_sha256_onhost") or (hb.get("input_h5ad") or {}).get("raw_sha256_expected")
    check("constituent_binds_h5ad", cinputs["main"]["h5ad_raw_sha256"] == val_h5ad,
          f"{cinputs['main']['h5ad_raw_sha256']} != {val_h5ad}")
    check("constituent_binds_bins_content",
          cinputs["main"]["bins_content_sha256"] == (hb.get("bins_v3_csv") or {}).get("content_sha256"))
    check("constituent_binds_scores_canonical",
          cinputs["main"]["scores_canonical_content_sha256"] == hb.get("scores_canonical_content_sha256")
          and cinputs["ovl"]["scores_parquet_raw_sha256"] == cinputs["main"]["scores_parquet_raw_sha256"])

    # 1) independent canonical self-hash reproduction for every T8 artifact
    arts = {}
    for n in ["stage01_selectability_v3.json", "stage01_validation_semantics.json",
              "stage01_current.json", "stage01_release_manifest.json"]:
        arts[n] = json.load(open(PP(n)))
        check(f"self_canonical_reproduces:{n}", arts[n].get("self_canonical_sha256") == _canon(arts[n]))
    sel, sem, cur, man = (arts["stage01_selectability_v3.json"], arts["stage01_validation_semantics.json"],
                          arts["stage01_current.json"], arts["stage01_release_manifest.json"])

    # 1b) semantics binds the same constituent evidence we independently reproduced
    ce = sem.get("constituent_evidence", {})
    check("semantics_binds_constituent_evidence",
          (ce.get("main") or {}).get("content_canonical_sha256") == MAIN_CONTENT_SHA and
          (ce.get("overlay_donor") or {}).get("content_canonical_sha256") == OVL_CONTENT_SHA)

    # 3) EXACT selectability re-derivation (multiset of full records incl. failure details)
    derived_rec = _derive_records(v, defmap)
    check("selectability_exact_match_independent_derivation",
          _canonlist(derived_rec) == _canonlist(sel.get("records", [])),
          "artifact records differ from independent re-derivation")
    check("selectability_record_count_33", len(sel.get("records", [])) == 33 == len(derived_rec))

    # 5) counts RECOMPUTED from rows (never trust the declared assertions)
    recomputed_true = sum(1 for r in sel.get("records", []) if r.get("production_selectable") is True)
    check("selectability_count_recomputed_matches_declared",
          sel.get("n_production_selectable_true") == recomputed_true == 0 and
          sel.get("n_records") == len(sel.get("records", [])) and
          sel.get("n_selectable_program_conditions") == recomputed_true,
          f"declared true={sel.get('n_production_selectable_true')} recomputed={recomputed_true}")
    check("selectability_all_records_false", all(r.get("production_selectable") is False for r in sel.get("records", [])))

    # bound-hash cross-pointers on selectability
    check("selectability_binds_validation", sel["bound_hashes"]["validation_raw_sha256"] == VALIDATION_RAW_SHA)
    check("selectability_binds_gate_spec", sel["bound_hashes"]["gate_spec_sha256"] == v["hash_bundle"]["gate_spec_sha256"])
    check("selectability_binds_v2_registry", sel["bound_hashes"]["v2_registry_raw_sha256"] == _raw(PP("stage01_program_registry.json")))

    # 4) EXACT semantics re-derivation (full 841-row table)
    derived_sem = _derive_semantics(v, defmap)
    check("semantics_binds_validation", sem["binds_validation_raw_sha256"] == VALIDATION_RAW_SHA)
    check("semantics_row_count", sem.get("n_results") == len(v["results"]) == len(sem.get("results_semantics", [])) == len(derived_sem))
    check("semantics_exact_match_independent_derivation",
          _canonlist(derived_sem) == _canonlist(sem.get("results_semantics", [])),
          "artifact semantics rows differ from independent re-derivation")
    # 6) explicit no-reinterpretation invariant (independent of the exact-match above)
    hard_ok = all((r["semantic_class"] != "hard_selectability" or r["flagged"] is None) and
                  (r["semantic_class"] != "advisory_flag" or r["metric_predicate_met"] is None)
                  for r in sem.get("results_semantics", []))
    check("semantics_no_hardgate_as_advisory_or_vice_versa", hard_ok)
    # undefinedness preserved wherever the independent derivation says undefined
    und_ok = all((not _mdefined(v["results"][r["source_result_index"]], defmap)) == (r["metric_defined"] is False)
                 for r in sem.get("results_semantics", []))
    check("semantics_undefinedness_preserved", und_ok)
    # regression budget derived from constituents (not program names): 8 wholly + 2 measurement partial
    hard_sem = [r for r in sem["results_semantics"] if r["semantic_class"] == "hard_selectability"]
    wholly = [r for r in hard_sem if r.get("n_undefined_constituents", 0) > 0 and r.get("n_defined_constituents", 1) == 0]
    partial = [r for r in hard_sem if r.get("n_undefined_constituents", 0) > 0 and r.get("n_defined_constituents", 0) > 0]
    zero_def = [r for r in sem["results_semantics"] if r["source_worst_defined_value"] == 0.0
                and r["metric_defined"] is True and r["raw_pass"] is True]
    check("regression_budget_8_wholly_2_partial_9_zerodef",
          len(wholly) == 8 and all("lomo" in r["gate_id"] for r in wholly) and len(partial) == 2 and len(zero_def) == 9,
          f"wholly={len(wholly)} partial={len(partial)} zero_def={len(zero_def)}")

    # 2) current pointer cross-pointers; no production/research split; frozen selectability is historical only
    check("current_schema_v3", cur.get("schema") == "spot.stage01_current.v3")
    check("current_pointer_is_candidate", cur.get("pointer_state") == "candidate")
    check("current_measurement_display_release_neutral",
          "measurement_display_release" in cur and "research_preview_v3" not in cur)
    check("current_no_split_or_0of33",
          not any(tok in json.dumps(cur).lower() for tok in
                  ("global_stage2_selectable", "production_stage2_ready", "n_selectable_program_conditions",
                   "0/33", "research_only", "per_condition_selectability_source")))
    check("current_stage1_kind_generic", cur.get("stage1_kind") == "continuous_measurement_and_generic_selector"
          and cur.get("selection_routing", {}).get("schema") == "spot.stage01_selection.v3")
    check("current_v2_historical", cur["v2_registry"]["status"] == "HISTORICAL_NOT_CURRENT"
          and cur["v2_registry"]["raw_sha256"] == _raw(PP("stage01_program_registry.json")))
    hv = cur["historical_validation_source"]
    check("current_historical_validation_source_by_hash",
          hv["active_gate"] is False and
          hv["raw_sha256"] == _raw(PP("stage01_selectability_v3.json")) == SELECTABILITY_RAW_SHA and
          hv["self_canonical_sha256"] == sel.get("self_canonical_sha256"))
    check("current_semantics_source_by_hash",
          cur["validation_semantics_source"]["raw_sha256"] == _raw(PP("stage01_validation_semantics.json")) and
          cur["validation_semantics_source"]["self_canonical_sha256"] == sem.get("self_canonical_sha256"))
    st = cur["release_statuses"]
    check("current_panel_provenance_bounded",
          st["panel_provenance_status"] == "PRIMARY_LOCATORS_VERIFIED_BOUNDED" and
          "UNVERIFIED" not in st["panel_provenance_status"])

    # 7) release manifest raw hashes match files; separate gates; not lockable while blocked
    hash_ok, present_ok = True, True
    for name, e in man["artifacts"].items():
        if e.get("location") == "release_staging_not_served":
            path = os.path.join(os.path.dirname(__file__), "_t8_staging", _staging_name(name))
        elif e.get("location") == "analysis" or name.endswith(".py") or name in ("requirements.txt", "stage01_solver_lock.txt"):
            path = os.path.join(os.path.dirname(__file__), name)
        else:
            path = PP(name)
        actual = _raw(path)
        if e.get("present") and e.get("raw_sha256") != actual: hash_ok = False
        if (actual is None) == bool(e.get("present")): present_ok = False
    check("manifest_hashes_match_files", hash_ok)
    check("manifest_present_flags_match_disk", present_ok)
    check("manifest_measurement_gate_and_no_production_gate",
          "measurement_bundle_lockable" in man["release_gates"] and
          "production_stage2_ready" not in man["release_gates"] and
          man.get("bound_evidence", {}).get("generic_selection_schema") == "spot.stage01_selection.v3")
    check("manifest_not_lockable_while_blocked", len(man["not_lockable_reason_codes"]) >= 1)

    # 8) selection routing (typed; NO production/research split, NO 0-of-33 gate)
    sys.path.insert(0, os.path.dirname(__file__))
    from stage1_t8_preflight import route_selection
    ready = route_selection({"A": {"program_id": "treg_like", "direction": "high"},
                             "B": {"program_id": "th1_like", "direction": "high"}, "conditions": ["Stim48hr"]}, d)
    check("routing_within_available_ready", ready.get("bundle_verified") is True and ready.get("execution_status") == "ready")
    temporal = route_selection({"A": {"program_id": "treg_like", "direction": "high"},
                                "B": {"program_id": "th1_like", "direction": "high"}, "conditions": ["Stim8hr", "Stim48hr"]}, d)
    _te = (temporal.get("contract") or {}).get("estimator", {})
    check("routing_temporal_ready_estimator_bound",
          temporal.get("execution_status") == "ready" and temporal.get("estimator_status") == "available"
          and _te.get("estimator_id") == "temporal_cross_condition_v1"
          and isinstance(_te.get("method_sha256"), str) and len(_te.get("method_sha256", "")) == 64)
    unavail = route_selection({"A": {"program_id": "th9_like", "direction": "low"},
                               "B": {"program_id": "th1_like", "direction": "high"}, "conditions": ["Rest"]}, d)
    check("routing_effect_unavailable_refused", unavail.get("execution_status") == "refused")

    print(f"\nT8 VERIFIER: {'PASS' if not FAILS else 'FAIL (' + ', '.join(FAILS) + ')'}")
    sys.exit(1 if FAILS else 0)


def _staging_name(manifest_name):
    m = {"stage01_program_registry_v3.json": "stage01_program_registry_v3.candidate.json",
         "stage01_scores_full.parquet": "stage01_scores_full.candidate.parquet",
         "stage01_summary.json": "stage01_summary.v3.json",
         "stage01_umap_coordinates.json": "stage01_umap_coordinates.json",
         "stage01_umap_overlay.json": "stage01_umap_overlay_v3.json",
         "stage01_v3_recovery_verification.json": "stage01_v3_recovery_verification.json",
         "stage01_solver_lock.txt": "stage01_solver_lock.txt"}
    return m.get(manifest_name, manifest_name)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
