"""Emit stage01_selection_bundle.json — the dataset-level CONSTANTS the browser needs to build a
byte-identical spot.stage01_selection.v3 contract (external review S1-B2).

The live page must emit the SAME v3 contract as emit_selection_contract.build_contract (so Stage-2 receives
the reviewed contract, not the legacy v1 handoff). Everything that is constant across selections — the
scorer-VIEW binding (what selection_id binds), source identity, per-program pole projection counts, the
estimator registry, and all trust/provenance/historical bindings — is generated HERE by the Python emitter
and served; the browser only fills in the per-selection A/B/conditions and recomputes selection_id +
full-contract hash. Because canonical_content carries no floats (only strings/enums/lists), the two agree
byte-for-byte.
"""
from __future__ import annotations

import json
import os

import build_registry_view as rv
import emit_selection_contract as sc

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(os.path.dirname(os.path.dirname(HERE)), "app", "data")
OUT = os.path.join(DATA, "stage01_selection_bundle.json")


def build_bundle() -> dict:
    view, _raw, view_canon = rv.build_and_hash()
    min_panel, min_ctrl = sc._effect_universe_thresholds()
    poles = {}
    for vp in view["programs"]:
        # projection counts are direction-independent; the browser supplies the direction per pole
        pole, _avail = sc._pole(vp, "high", min_panel, min_ctrl)
        poles[vp["program_id"]] = {
            "program_id": vp["program_id"],
            "effect_projection_status": pole["effect_projection_status"],
            "n_measured": pole["n_measured"],
            "n_panel_in_effect_universe": pole["n_panel_in_effect_universe"],
            "n_control_in_effect_universe": pole["n_control_in_effect_universe"],
            "reason_codes": pole["reason_codes"],
        }
    # lift the constant contract blocks verbatim from a reference emit (they are selection-invariant)
    ref = sc.build_contract("treg_like", "high", "th1_like", "high", ["Stim48hr"])
    return {
        "schema": "spot.stage01_selection_bundle.v1",
        "for_selection_schema": sc.SCHEMA,
        "stage1_method_version": sc.STAGE1_METHOD_VERSION,
        "dataset_id": sc.DATASET_ID,
        "donor_scope": sc.DONOR_SCOPE,
        "effect_universe_id": sc.EFFECT_UNIVERSE_ID,
        "source_h5ad_sha256": sc.SOURCE_H5AD_SHA256,
        "source_hf_revision": sc.SOURCE_HF_REVISION,
        "registry_scorer_view_sha256": view_canon,
        "real_conditions": list(sc.REAL_CONDITIONS),
        "directions": list(sc.DIRECTIONS),
        "implemented_estimators": list(sc.IMPLEMENTED_ESTIMATORS),
        "estimator_for_mode": sc.ESTIMATOR_FOR_MODE,
        "estimator_registry": sc.ESTIMATOR_REGISTRY,
        "poles": poles,
        "trust_bindings": ref["trust_bindings"],
        "provenance_bindings": ref["provenance_bindings"],
        "historical_validation_provenance": ref["historical_validation_provenance"],
    }


if __name__ == "__main__":
    b = build_bundle()
    with open(OUT, "w") as fh:
        json.dump(b, fh, indent=2, ensure_ascii=True, sort_keys=False)
        fh.write("\n")
    print("wrote", os.path.relpath(OUT, os.path.dirname(DATA)))
    print("  registry_scorer_view_sha256:", b["registry_scorer_view_sha256"])
    print("  n poles:", len(b["poles"]), "| implemented estimators:", b["implemented_estimators"])
