#!/usr/bin/env python3
"""Generate the honest, fail-closed Stage-1 v3 T8 production layer from the IMMUTABLE T7b validation
artifact. Deterministic + timestamp-free (canonical self-hashes are reproducible).

Emits (into 01_programs/app/data/):
  stage01_selectability_v3.json      - 33 program x condition records, production_selectable derived
  stage01_validation_semantics.json  - row-identifiable disambiguation of the overloaded `pass` field
  stage01_current.json               - honest CANDIDATE pointer with SEPARATE release statuses
  stage01_release_manifest.json      - raw hashes of present artifacts; distinct lock/overlay/app gates

It NEVER modifies the immutable validation artifact, any preregistered gate/panel/score/seed/threshold,
or the v2 registry (only marks it historical). No p/q/FDR, no categorical cell labels.

Recovered v3 artifacts (registry_v3, full scores, summary, coordinates, overlay), when present in the
release-staging dir, are hash-bound into the manifest. They are NOT served/deployed while the overlay
release gate is false; the pointer stays `candidate`, never `current`/`locked`.
"""
import json, hashlib, os, sys
import stage1_t8_derive as D8

D = os.path.join(os.path.dirname(__file__), "..", "app", "data")
STAGING = os.path.join(os.path.dirname(__file__), "_t8_staging")   # non-served recovered/built v3 artifacts
def P(name): return os.path.join(D, name)

VALIDATION = "stage01_validation.json"
VALIDATION_RAW_SHA_EXPECTED = "1c14cd2884117f03bd26b56ff32d5575d92caa53c5391fa0e7e0ed4f3c815371"

# re-export taxonomy for downstream imports (generator side only)
HARD_SELECTABILITY_GATES = D8.HARD_SELECTABILITY_GATES
semantic_class = D8.semantic_class


def raw_sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest() if path and os.path.exists(path) else None


def canon_sha256(obj, exclude=("self_canonical_sha256",)):
    """Repository frozen canonical rule: sha256 of sort_keys + compact JSON, self-hash field excluded."""
    d = {k: v for k, v in obj.items() if k not in exclude}
    return hashlib.sha256(json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def row_canon_sha256(row):
    """Canonical hash of one immutable source result row (for per-row provenance in semantics)."""
    return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def write_canon(name, obj):
    obj = dict(obj)
    obj["self_canonical_sha256"] = canon_sha256(obj)
    with open(P(name), "w") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, sort_keys=False)
        f.write("\n")
    return obj["self_canonical_sha256"], raw_sha256(P(name))


def staged(name):
    """Raw sha + present flag for a recovered/built v3 artifact in the non-served (gitignored) staging dir."""
    p = os.path.join(STAGING, name)
    return {"file": name, "location": "release_staging_not_served", "raw_sha256": raw_sha256(p), "present": os.path.exists(p)}


def analysis_file(name):
    """Raw sha + present flag for a committed provenance artifact in the analysis dir."""
    p = os.path.join(os.path.dirname(__file__), name)
    return {"file": name, "location": "analysis", "raw_sha256": raw_sha256(p), "present": os.path.exists(p)}


def main():
    # 0) hash guard on the immutable validation artifact
    got = raw_sha256(P(VALIDATION))
    if got != VALIDATION_RAW_SHA_EXPECTED:
        print(f"ABORT: validation raw sha {got} != expected {VALIDATION_RAW_SHA_EXPECTED}", file=sys.stderr); sys.exit(2)
    v = json.load(open(P(VALIDATION)))
    method_version = v.get("method_version")
    gate_spec_sha = v["hash_bundle"]["gate_spec_sha256"]

    # per-metric definedness from the hash-bound constituent evidence (CP3c amendment: the deleted
    # zero-value/name heuristic is replaced by authoritative per-constituent definedness).
    defmap, constituent_evidence = D8.build_definedness_index()

    def binding(name): return {"file": name, "raw_sha256": raw_sha256(P(name)), "present": os.path.exists(P(name))}
    bind = {n: binding(n) for n in [
        VALIDATION, "stage01_gate_spec.json", "stage01_input_manifest.json", "stage01_control_method.json",
        "stage01_controls_v3.csv", "stage01_bins_v3.csv", "stage01_control_eligible_pool.json",
        "stage01_program_registry.json"]}

    # ---- 1) selectability_v3: 33 records with exact per-stratum failure detail (multiset preserved) ----
    records = D8.derive_selectability_records(v, defmap)
    assert len(records) == 33, f"expected 33 records, got {len(records)}"
    n_true = sum(1 for r in records if r["production_selectable"] is True)
    selectability = {
        "schema": "spot.stage01_selectability_v3.v2",
        "method_version": method_version,
        "derivation": "Deterministically derived from the immutable T7b validation (bound by raw sha below) via stage1_t8_derive. No retuning; a false hard-gate is never reinterpreted as advisory. failed_or_undefined_hard_gates is a MULTISET (a gate failing in two strata appears twice).",
        "production_selectable_default": False,
        "n_records": len(records),
        "n_production_selectable_true": n_true,
        "n_selectable_program_conditions": n_true,
        "portability_disclaimer": "stage2_base_portability is a SEPARATE necessary condition and DOES NOT confer stage-1 production selectability. No current program-condition pair cleared the frozen production gate.",
        "not_a_biological_invalidity_claim": "This records only that no current program-condition pair cleared the frozen production gate; it does not assert any program is biologically invalid.",
        "bound_hashes": {"validation_raw_sha256": bind[VALIDATION]["raw_sha256"],
                         "gate_spec_sha256": gate_spec_sha,
                         "input_manifest_raw_sha256": bind["stage01_input_manifest.json"]["raw_sha256"],
                         "control_method_raw_sha256": bind["stage01_control_method.json"]["raw_sha256"],
                         "v2_registry_raw_sha256": bind["stage01_program_registry.json"]["raw_sha256"]},
        "no_p_q_fdr": True, "no_categorical_cell_labels": True,
        "records": records,
    }
    sel_canon, sel_raw = write_canon("stage01_selectability_v3.json", selectability)

    # ---- 3) validation semantics adapter: one ROW-IDENTIFIABLE row per result, two dimensions ----
    sem_rows = D8.derive_semantics_rows(v, row_canon_sha256, defmap)
    semantics = {
        "schema": "spot.stage01_validation_semantics.v3",
        "method_version": method_version,
        "semantics_amendment": "stage1-validation-semantics-definedness-v1",
        "amendment_note": "CP3c definedness amendment: per-metric definedness is read from the hash-bound constituent-evidence tables (aggregate defined iff every expected constituent defined), replacing the deleted zero-value/name heuristic. The immutable stage01_validation.json (raw sha below) is UNCHANGED; only this interpretation layer is amended, so this artifact's raw/canonical hash changes while the source stays frozen.",
        "supersedes_semantics_raw_sha256": "68872d882ce7e7af30de4636a20ccb0c3f96cc34a1053febeed3739994980ce8",
        "binds_validation_raw_sha256": bind[VALIDATION]["raw_sha256"],
        "constituent_evidence": constituent_evidence,
        "purpose": "Hash-bound, row-identifiable interpretation over the immutable validation. Every source result gets source_result_index + source_row_canonical_sha256, and TWO preserved dimensions: metric_predicate_met/metric_defined/undefined_reason (metric level) and gate_outcome/flagged (gate level). Definedness comes from the hash-bound constituent evidence, NEVER a numeric zero or metric name; a false hard-gate is never reinterpreted as advisory; undefinedness is preserved even when the gate outcome is False.",
        "term_definitions": {
            "raw_pass": "the frozen results[*].pass = the original ALL-constituents subcheck outcome",
            "source_worst_defined_value": "the frozen observed_value = lossy extremum over DEFINED constituents (never the sole evaluator)",
            "metric_defined": "aggregate-level: every expected constituent stratum is defined (n_undefined_constituents == 0)",
            "metric_predicate_met": "completeness AND every constituent defined AND every defined constituent meets its comparator (reproduces raw_pass for hard rows)",
        },
        "gate_taxonomy": {"hard_selectability": sorted(D8.HARD_SELECTABILITY_GATES), "structural_selection": sorted(D8.STRUCTURAL_GATE),
                          "portability_not_selectability": sorted(D8.PORTABILITY_GATE), "overlay_release": sorted(D8.OVERLAY_RELEASE_GATES),
                          "advisory_flag": sorted(D8.ADVISORY_GATES), "descriptive_undefined": sorted(D8.DESCRIPTIVE_GATES)},
        "dimension_note": "metric_predicate_met and gate_outcome are SEPARATE. Per-metric portability/overlay rows carry gate_outcome only (NOT relabelled as aggregate gates). metric_defined can be false while gate_outcome is False; a real zero-numerator (positive denominator) is DEFINED.",
        "n_results": len(sem_rows),
        "results_semantics": sem_rows,
    }
    sem_canon, sem_raw = write_canon("stage01_validation_semantics.json", semantics)

    # ---- recovered/built v3 artifacts (non-served staging), hash-bound into the manifest ----
    v3 = {
        "stage01_program_registry_v3.json": staged("stage01_program_registry_v3.candidate.json"),
        "stage01_scores_full.parquet": staged("stage01_scores_full.candidate.parquet"),
        "stage01_summary.json": staged("stage01_summary.v3.json"),
        "stage01_umap_coordinates.json": staged("stage01_umap_coordinates.json"),
        "stage01_umap_overlay.json": staged("stage01_umap_overlay_v3.json"),
    }
    # verification receipt produced by the independent D-compute (committed provenance in analysis/)
    v3_verify = analysis_file("stage01_v3_recovery_verification.json")
    receipt_all_pass = False
    if v3_verify["present"]:
        try:
            receipt_all_pass = bool(json.load(open(os.path.join(os.path.dirname(__file__),
                                    "stage01_v3_recovery_verification.json"))).get("all_pass") is True)
        except Exception:
            receipt_all_pass = False

    overlay_release_ok = bool(v.get("overlay_release", {}).get("overlay_release_ok", False))
    measurement_inputs_present = all(v3[k]["present"] for k in
                                     ["stage01_program_registry_v3.json", "stage01_scores_full.parquet", "stage01_summary.json"])
    measurement_verified = bool(v3_verify["present"] and receipt_all_pass)
    # a real Linux conda solver lock (conda --explicit + in-env pip freeze) — separate from pip requirements alone
    solver_lock = analysis_file("stage01_solver_lock.txt")

    # ---- 2) current CANDIDATE pointer with SEPARATE statuses (item E) ----
    n_true = selectability["n_production_selectable_true"]
    measurement_bundle_lockable = bool(measurement_inputs_present and measurement_verified and solver_lock["present"])
    statuses = {
        "measurement_bundle_status": ("lockable" if measurement_bundle_lockable else "not_lockable"),
        "measurement_bundle_lockable": measurement_bundle_lockable,
        "measurement_bundle_blocker_codes": [b for b in [
            (None if measurement_inputs_present else "recovered_inputs_incomplete"),
            (None if measurement_verified else "recovery_receipt_absent"),
            (None if solver_lock["present"] else "solver_lock_absent"),
        ] if b],
        "panel_provenance_status": "PRIMARY_LOCATORS_VERIFIED_BOUNDED",
        "overlay_release_ok": overlay_release_ok,
        "overlay_deployment_status": ("deployable" if overlay_release_ok else "blocked_overlay_gate_false"),
        "app_deployment_ready": False,
    }
    # ---- v3.0.1 measurement/display release bindings (served copies the UI joins/binds to) ----
    regv3_p, ovl3_p, sum3_p = P("stage01_program_registry_v3.json"), P("stage01_umap_overlay_v3.json"), P("stage01_summary_v3.json")
    measurement_display_release = None
    if all(os.path.exists(p) for p in (regv3_p, ovl3_p, sum3_p)):
        regv3, ovl3, sum3 = json.load(open(regv3_p)), json.load(open(ovl3_p)), json.load(open(sum3_p))
        bp = v.get("stage2_base_portability", {})
        base_portable = sorted(k for k, val in bp.items() if isinstance(val, dict) and val.get("stage2_base_portable") is True)
        measurement_display_release = {
            "kind": "v3_measurement_display_release",
            "method_version": method_version,
            "join_rule": "coordinates_from_seed_scores_from_overlay_by_exact_barcode",
            "registry": {"file": "stage01_program_registry_v3.json", "raw_sha256": raw_sha256(regv3_p),
                         "registry_sha256": regv3.get("registry_sha256")},
            "overlay": {"file": "stage01_umap_overlay_v3.json", "raw_sha256": raw_sha256(ovl3_p),
                        "coordinates_sha256": ovl3.get("coordinates_sha256"),
                        "scores_canonical_content_sha256": ovl3.get("scores_canonical_content_sha256"),
                        "n_cells": ovl3.get("n_cells"), "score_fields": ovl3.get("score_fields")},
            "summary": {"file": "stage01_summary_v3.json", "raw_sha256": raw_sha256(sum3_p),
                        "scoring_universe_n": sum3.get("scoring_universe_n")},
            "validation_raw_sha256": bind[VALIDATION]["raw_sha256"],
            "source_h5ad_raw_sha256": (regv3.get("input_manifest", {}) or {}).get("raw_file_sha256"),
            "base_portable_programs": base_portable,
            "n_base_portable": len(base_portable),
            "base_portability_source_field": "stage2_base_portability.stage2_base_portable",
            "frozen_coordinate_shell": "stage01_umap_seed.json",
        }
    current = {
        "schema": "spot.stage01_current.v3",
        "method_version": method_version,
        "pointer_state": "candidate",
        "pointer_state_reason_codes": [c for c in [
            (None if measurement_bundle_lockable else "measurement_bundle_not_lockable"),
            (None if overlay_release_ok else "overlay_release_blocked"),
            "panel_provenance_bounded",
        ] if c],
        "stage1_kind": "continuous_measurement_and_generic_selector",
        "selection_routing": {
            "schema": "spot.stage01_selection.v3",
            "emitter": "stage2_bridge/emit_selection_contract.py",
            "execution_statuses": ["ready", "refused", "awaiting_estimator"],
            "within_condition_estimator_id": "within_condition_v1",
            "within_condition_estimator_status": "available",
            "temporal_cross_condition_estimator_id": "temporal_cross_condition_v1",
            "temporal_cross_condition_estimator_status": "available",   # W18: temporal estimator implemented + verified; contract binds its method identity (a word cannot pass Stage-2's re-verify)
            "current_served_selection": None,
        },
        "release_statuses": statuses,
        "historical_validation_source": {"artifact": "stage01_selectability_v3.json", "raw_sha256": sel_raw, "self_canonical_sha256": sel_canon,
                                         "kind": "frozen_lomo_within_condition_validation_v3", "active_gate": False},
        "validation_semantics_source": {"artifact": "stage01_validation_semantics.json", "raw_sha256": sem_raw, "self_canonical_sha256": sem_canon},
        "bound_validation_raw_sha256": bind[VALIDATION]["raw_sha256"],
        "v3_registry_source": {"artifact": "stage01_program_registry_v3.json", **{k: v3["stage01_program_registry_v3.json"][k] for k in ("location", "raw_sha256", "present")}},
        "v2_registry": {"file": "stage01_program_registry.json", "raw_sha256": bind["stage01_program_registry.json"]["raw_sha256"],
                        "method_version": "stage1-continuous-v2",
                        "status": "HISTORICAL_NOT_CURRENT", "status_reason_code": "superseded_by_v3_measurement_provenance"},
        "measurement_display_release": measurement_display_release,
        # S1-M4: bind the descriptive activation-association artifact so it cannot be silently swapped
        "activation_association_source": {"artifact": "stage01_activation_association_v1.json",
                                          "raw_sha256": raw_sha256(P("stage01_activation_association_v1.json")),
                                          "kind": "descriptive_activation_association_per_program_condition_donor",
                                          "inference_status": "descriptive_only_no_p_q_fdr", "active_gate": False},
    }
    cur_canon, cur_raw = write_canon("stage01_current.json", current)

    # ---- 5) release manifest: raw hashes; distinct measurement/overlay/app/production gates ----
    served_required = [
        VALIDATION, "stage01_validation_semantics.json", "stage01_selectability_v3.json", "stage01_current.json",
        "stage01_gate_spec.json", "stage01_input_manifest.json", "stage01_control_method.json",
        "stage01_controls_v3.csv", "stage01_bins_v3.csv", "stage01_control_eligible_pool.json",
        "stage01_validation_independent_check.json", "stage01_activation_association_v1.json",
    ]
    code_required = ["gen_stage1_t8.py", "stage1_t8_derive.py", "verify_stage1_t8.py", "stage1_t8_preflight.py",
                     "test_stage1_t8.py", "requirements.txt",
                     "gen_stage1_provenance.py", "verify_stage1_provenance.py", "test_stage1_provenance.py"]
    entries, missing = {}, []
    for name in served_required:
        sha = raw_sha256(P(name)); entries[name] = {"raw_sha256": sha, "present": sha is not None, "location": "served"}
        if sha is None: missing.append(name)
    for name in code_required:
        sha = raw_sha256(os.path.join(os.path.dirname(__file__), name))
        entries[name] = {"raw_sha256": sha, "present": sha is not None, "location": "analysis"}
        if sha is None: missing.append(name)
    for name, e in v3.items():
        entries[name] = e
        if not e["present"]: missing.append(name)
    entries["stage01_v3_recovery_verification.json"] = v3_verify
    entries["stage01_solver_lock.txt"] = solver_lock
    for extra in ("stage01_v3_recovery_verification.json", "stage01_solver_lock.txt"):
        if not entries[extra]["present"]: missing.append(extra)

    measurement_bundle_lockable = current["release_statuses"]["measurement_bundle_lockable"]
    manifest = {
        "schema": "spot.stage01_release_manifest.v2",
        "method_version": method_version,
        "bound_validation_raw_sha256": bind[VALIDATION]["raw_sha256"],
        "bound_evidence": {
            "semantics_amendment": "stage1-validation-semantics-definedness-v1",
            "constituent_evidence": constituent_evidence,
            "stage2_registry_view_raw_sha256": raw_sha256(P("stage01_stage2_registry_view.json")),
            "marker_diagnostics_raw_sha256": raw_sha256(P("stage01_marker_diagnostics_v2.json")),
            "generic_selection_schema": "spot.stage01_selection.v3",
            "selection_current_served": None,
        },
        "release_gates": {
            "measurement_bundle_lockable": measurement_bundle_lockable,
            "panel_provenance_status": current["release_statuses"]["panel_provenance_status"],
            "overlay_release_ok": overlay_release_ok,
            "app_deployment_ready": current["release_statuses"]["app_deployment_ready"],
        },
        "not_lockable_reason_codes": [r for r in [
            ("required_artifacts_missing" if missing else None),
            ("measurement_bundle_not_lockable" if not measurement_bundle_lockable else None),
            ("panel_provenance_unverified" if "UNVERIFIED" in current["release_statuses"]["panel_provenance_status"] else None),
            ("overlay_release_blocked" if not overlay_release_ok else None),
        ] if r],
        "missing_required_artifacts": missing,
        "artifacts": entries,
    }
    man_canon, man_raw = write_canon("stage01_release_manifest.json", manifest)

    print("WROTE:")
    for n, (c, rw) in [("stage01_selectability_v3.json", (sel_canon, sel_raw)),
                       ("stage01_validation_semantics.json", (sem_canon, sem_raw)),
                       ("stage01_current.json", (cur_canon, cur_raw)),
                       ("stage01_release_manifest.json", (man_canon, man_raw))]:
        print(f"  {n}  raw={rw[:16]}  canon={c[:16]}")
    print(f"records={len(records)}  production_selectable_true={n_true}  semantics_rows={len(sem_rows)}")
    print(f"measurement_bundle_lockable={measurement_bundle_lockable}  overlay_release_ok={overlay_release_ok}  "
          f"missing={len(missing)}  release_gates_note=distinct")


if __name__ == "__main__":
    main()
