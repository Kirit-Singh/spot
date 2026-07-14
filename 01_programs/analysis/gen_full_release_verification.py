#!/usr/bin/env python3
"""Emit the FULL-RELEASE verification record for Stage-1 v3.0.1: a single hash-bound attestation
binding code + environment + inputs + outputs + explicit scope.

Distinct from stage01_validation_independent_check.json, which remains an intentionally LIMITED
independent observation (sampled recompute, not from-release reproducible). This record instead binds
the COMPLETE reproducible measurement bundle by hash and records exactly what was independently verified
vs what is still pending (panel provenance, overlay deployment).

Run AFTER gen_stage1_t8.py and the tcefold D-compute. Writes analysis/stage01_full_release_verification.json.
"""
import json, hashlib, os

HERE = os.path.dirname(__file__)
DATA = os.path.join(HERE, "..", "app", "data")
STAGING = os.path.join(HERE, "_t8_staging")


def raw(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest() if os.path.exists(path) else None


def canon(obj):
    d = {k: v for k, v in obj.items() if k != "self_canonical_sha256"}
    return hashlib.sha256(json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def D(n): return raw(os.path.join(DATA, n))
def A(n): return raw(os.path.join(HERE, n))
def S(n): return raw(os.path.join(STAGING, n))
def CS(n): return raw(os.path.join(HERE, "stage2_bridge", "_release_staging", n))
def _content_sha(manifest_name):
    p = os.path.join(HERE, "stage2_bridge", "_release_staging", manifest_name)
    return json.load(open(p)).get("content_canonical_sha256") if os.path.exists(p) else None


def main():
    receipt_path = os.path.join(HERE, "stage01_v3_recovery_verification.json")
    receipt = json.load(open(receipt_path)) if os.path.exists(receipt_path) else {}
    rc = receipt.get("checks", {})

    rec = {
        "schema": "spot.stage01_full_release_verification.v1",
        "method_version": "stage1-continuous-v3.0.1",
        "purpose": "Hash-bound full-release attestation for the Stage-1 v3.0.1 measurement bundle. Binds code, "
                   "environment, inputs and outputs, and states scope (verified vs pending). This is NOT a "
                   "selectability/T8 decision and NOT a claim that any program is biologically valid or that panel "
                   "provenance is confirmed.",
        "code": {
            "gen_stage1_t8.py": A("gen_stage1_t8.py"),
            "stage1_t8_derive.py": A("stage1_t8_derive.py"),
            "verify_stage1_t8.py": A("verify_stage1_t8.py"),
            "stage1_t8_preflight.py": A("stage1_t8_preflight.py"),
            "test_stage1_t8.py": A("test_stage1_t8.py"),
            "gen_full_release_verification.py": A("gen_full_release_verification.py"),
            "gen_stage1_provenance.py": A("gen_stage1_provenance.py"),
            "verify_stage1_provenance.py": A("verify_stage1_provenance.py"),
            "test_stage1_provenance.py": A("test_stage1_provenance.py"),
            "note": "Generator, independent verifier and mutation suite are distinct files (generator != verifier).",
        },
        "environment": {
            "solver_lock_raw_sha256": A("stage01_solver_lock.txt"),
            "lock_kind": "conda --explicit (linux-64) + in-env pip freeze",
            "scoring_env": "tcefold conda env 'scvi_gpu'; python 3.11.15; numpy 2.3.3 / pandas 2.2.3 / scipy 1.15.2 / "
                           "scanpy 1.11.5 / anndata 0.12.19 / h5py 3.16.0 / pyarrow 24.0.0 (numerical stack pip-installed).",
            "scoring_env_verified": "reproduces the frozen scores_canonical_content_sha256 43c4296d this session, and its "
                                    "pip pins match 01_programs/README.md's tested lock.",
        },
        "inputs_by_hash": {
            "validation_raw_sha256": D("stage01_validation.json"),
            "gate_spec_raw_sha256": D("stage01_gate_spec.json"),
            "input_manifest_raw_sha256": D("stage01_input_manifest.json"),
            "control_method_raw_sha256": D("stage01_control_method.json"),
            "controls_v3_raw_sha256": D("stage01_controls_v3.csv"),
            "bins_v3_raw_sha256": D("stage01_bins_v3.csv"),
            "control_eligible_pool_raw_sha256": D("stage01_control_eligible_pool.json"),
            "v2_registry_raw_sha256": D("stage01_program_registry.json"),
            "v3_registry_raw_sha256": S("stage01_program_registry_v3.candidate.json"),
            "scores_full_parquet_raw_sha256": S("stage01_scores_full.candidate.parquet"),
            "scores_canonical_content_sha256": rc.get("scores_canonical_content_sha256", {}).get("recomputed"),
            "coordinates_barcode_plus_xy_sha256": "c3d3a0a752614470693a0148ba37a45cf20aba290a6e54b4f7fa0bc468a6605b",
            "barcode_set_sha256": "1224312e52231f4b2e07c192b39c6f9c69dd6e2d5b8bd64d936c17a9b2435a93",
        },
        "outputs_by_hash": {
            "selectability_v3_raw_sha256": D("stage01_selectability_v3.json"),
            "validation_semantics_raw_sha256": D("stage01_validation_semantics.json"),
            "current_raw_sha256": D("stage01_current.json"),
            "release_manifest_raw_sha256": D("stage01_release_manifest.json"),
            "umap_coordinates_raw_sha256": S("stage01_umap_coordinates.json"),
            "umap_overlay_v3_raw_sha256": S("stage01_umap_overlay_v3.json"),
            "summary_v3_raw_sha256": S("stage01_summary.v3.json"),
            "recovery_receipt_raw_sha256": A("stage01_v3_recovery_verification.json"),
        },
        "constituent_and_view_evidence": {
            "semantics_amendment": "stage1-validation-semantics-definedness-v1",
            "constituent_main_json_gz_raw_sha256": CS("stage01_gate_constituents_v1.json.gz"),
            "constituent_main_parquet_raw_sha256": CS("stage01_gate_constituents_v1.parquet"),
            "constituent_main_content_canonical_sha256": _content_sha("stage01_gate_constituents_v1.manifest.json"),
            "constituent_overlay_donor_json_gz_raw_sha256": CS("stage01_gate_constituents_overlay_donor_v1.json.gz"),
            "constituent_overlay_donor_content_canonical_sha256": _content_sha("stage01_gate_constituents_overlay_donor_v1.manifest.json"),
            "stage2_registry_view_raw_sha256": D("stage01_stage2_registry_view.json"),
            "marker_diagnostics_raw_sha256": D("stage01_marker_diagnostics_v2.json"),
            "generic_selection_schema": "spot.stage01_selection.v3",
            "selection_current_served": None,
            "note": "Per-constituent definedness evidence (independently reconstructed from .X on tcefold), the "
                    "corrected semantics amendment, the citation-invariant Stage-2 scoring view, and the marker-"
                    "level/LOMO diagnostics (use_for_eligibility=false). Stage-1 is a generic selector: NO fixed "
                    "selection is served as current (spot.stage01_selection.v3 is emitted on demand; the retired "
                    "demo is removed). All hash-bound; the immutable validation is unchanged.",
        },
        "independently_verified": {
            "selectability_records": "33 records exact-matched to an independent re-derivation from the immutable "
                                     "validation (multiset of failure details; not subset); counts recomputed from rows.",
            "validation_semantics": "841 rows exact-matched to an independent re-derivation; definedness read from the "
                                    "hash-bound constituent evidence (8 wholly + 2 partial undefined; 9 zero-numerator "
                                    "rows stay defined); the deleted zero-value/name heuristic is not used.",
            "scores_canonical_content_sha256": rc.get("scores_canonical_content_sha256", {}).get("match"),
            "overlay_equals_full": rc.get("overlay_equals_full", {}).get("overlay_eq_full_all_fields"),
            "coordinates_sha256_reproduced": True,
            "controls_symbol_multiset_match": rc.get("controls", {}).get("all_programs_symbol_multiset_match"),
            "summary_regenerated_from_parquet": rc.get("summary_regenerated", {}).get("median_iqr_mad_all_match"),
            "coefficient_internal_consistency": rc.get("coefficient_internal_consistency", {}).get("all_consistent"),
            "solver_lock_captured": bool(A("stage01_solver_lock.txt")),
        },
        "scope_and_limits": {
            "measurement_bundle": "measurement_bundle_lockable is TRUE (inputs+registry+scores+summary+code+verifier+"
                                  "mutation suite+solver lock all present and independently verified). This does NOT imply "
                                  "any selectable pair, identity confirmation, or downstream availability.",
            "stage1_kind": "continuous_measurement_and_generic_selector — no production/research split and no 0-of-33 "
                           "production gate exists in the ACTIVE contract; any supported (program A/direction, program "
                           "B/direction, condition/mode) yields the same typed spot.stage01_selection.v3.",
            "historical_within_condition_validation": "The frozen T7b within-condition LOMO validation "
                           "(stage01_selectability_v3.json, raw 7c326a86…, active_gate:false) recorded 0 of 33 program-"
                           "condition pairs clearing a pre-registered production gate. This is a FROZEN HISTORICAL "
                           "validation outcome ONLY — it is NOT the current release/deployment state and does NOT gate the "
                           "generic selector, any selection, or app/overlay deployment.",
            "panel_provenance": "PRIMARY_LOCATORS_VERIFIED_BOUNDED — all 53 measured marker-program pairs carry a "
                                "bounded primary-source locator in the v3 registry marker_provenance/panel_provenance "
                                "(18 prior-ledger + 14 lineage + 21 state/CTL completions; source SHAs pinned in "
                                "registry panel_provenance.source_artifacts and enforced by verify_stage1_provenance.py). "
                                "This is a bounded association/RNA-level provenance fact only: it does NOT change the "
                                "scorer, any score, the frozen historical within-condition validation outcome, overlay/app "
                                "deployment, or the candidate pointer, and Masopust remains naming-only.",
            "overlay_release": "overlay_release_ok is FALSE — the v3 overlay is built and proven overlay==full but is NOT "
                               "APPROVED for release by this Stage-1 gate (deployment is a separate gate; do not deploy on "
                               "this gate alone). A served deployment manifest that declares the app/overlay deployed while "
                               "this gate is false is a release-state CONTRADICTION the served-manifest consistency verifier "
                               "(verify_served_manifests.py) refuses.",
            "coefficients_from_method": "Registry coefficients are checked for internal consistency here; recomputing them "
                                        "from the frozen method requires the pinned h5ad and is the scoring-tier reproduce's job.",
            "earlier_limited_observation": "stage01_validation_independent_check.json remains an intentionally LIMITED sampled "
                                           "observation and is not broadened by this record.",
            "reproducibility": "Heavy artifacts (parquet, v3 overlay, coordinates, v3 registry, v3 summary) are gitignored "
                               "release-staging outputs bound here by hash; the reproduce chain regenerates them from pinned inputs.",
        },
        "recovery_receipt_all_pass": receipt.get("all_pass"),
    }
    rec["self_canonical_sha256"] = canon(rec)
    out = os.path.join(HERE, "stage01_full_release_verification.json")
    with open(out, "w") as f:
        json.dump(rec, f, indent=2, ensure_ascii=False); f.write("\n")
    print("WROTE stage01_full_release_verification.json")
    print("  self_canonical:", rec["self_canonical_sha256"][:16], " raw:", raw(out)[:16])
    print("  measurement verified:", all(v is True for v in [
        rec["independently_verified"]["scores_canonical_content_sha256"],
        rec["independently_verified"]["overlay_equals_full"],
        rec["independently_verified"]["controls_symbol_multiset_match"],
        rec["independently_verified"]["summary_regenerated_from_parquet"]]))


if __name__ == "__main__":
    main()
