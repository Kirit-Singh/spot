"""Freeze the pre-change protected baseline (run ONCE, before any bridge output).

Captures the raw SHA-256 of every protected numerical/scorer artifact plus the exact
scorer projection (the registry scorer-core invariant) and the registry/validation/
selectability canonical content hashes. The committed PROTECTED_HASHES.json is the frozen
record; verify_bridge.check_protected() re-checks it at CP7 to prove nothing moved.

Nothing here writes into the release bundle; it only reads frozen inputs and writes the
one baseline file next to this module.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYSIS = os.path.dirname(HERE)
PROGRAMS = os.path.dirname(ANALYSIS)          # 01_programs/
DATA = os.path.join(PROGRAMS, "app", "data")  # 01_programs/app/data/
sys.path.insert(0, HERE)
sys.path.insert(0, ANALYSIS)

import canonical  # noqa: E402
import verify_stage1_provenance as prov  # noqa: E402  (independent scorer-projection recipe)

BASELINE_PATH = os.path.join(HERE, "PROTECTED_HASHES.json")

# Protected artifacts that MUST remain byte-identical across this task. Paths are
# relative to the repo dirs above. Staged (gitignored) release inputs included by hash.
PROTECTED_RAW = {
    "registry_v3": (DATA, "stage01_program_registry_v3.json"),
    "validation": (DATA, "stage01_validation.json"),
    "validation_semantics": (DATA, "stage01_validation_semantics.json"),
    "selectability_v3": (DATA, "stage01_selectability_v3.json"),
    "summary_v3": (DATA, "stage01_summary_v3.json"),
    "umap_overlay_v3": (DATA, "stage01_umap_overlay_v3.json"),
    "controls_v3_csv": (DATA, "stage01_controls_v3.csv"),
    "bins_v3_csv": (DATA, "stage01_bins_v3.csv"),
    "gate_spec": (DATA, "stage01_gate_spec.json"),
    "input_manifest": (DATA, "stage01_input_manifest.json"),
    "control_method": (DATA, "stage01_control_method.json"),
    "control_eligible_pool": (DATA, "stage01_control_eligible_pool.json"),
    "effect_universe": (ANALYSIS, "effect_universe_gwcd4i.json"),
    "solver_lock": (ANALYSIS, "stage01_solver_lock.txt"),
    "requirements": (ANALYSIS, "requirements.txt"),
    "scores_parquet_staged": (os.path.join(ANALYSIS, "_t8_staging"), "stage01_scores_full.candidate.parquet"),
    "umap_coordinates_staged": (os.path.join(ANALYSIS, "_t8_staging"), "stage01_umap_coordinates.json"),
}


def compute_baseline() -> dict:
    reg = json.load(open(os.path.join(DATA, "stage01_program_registry_v3.json")))
    val = json.load(open(os.path.join(DATA, "stage01_validation.json")))
    sel = json.load(open(os.path.join(DATA, "stage01_selectability_v3.json")))

    raw = {}
    for name, (root, fn) in PROTECTED_RAW.items():
        p = os.path.join(root, fn)
        raw[name] = canonical.file_sha256(p) if os.path.exists(p) else None

    reg_minus_top = {k: v for k, v in reg.items() if k != "registry_sha256"}
    return {
        "_schema": "spot.stage2_bridge.protected_baseline.v1",
        "_note": "Frozen pre-change baseline. Every value here MUST be reproduced at "
                 "verification; a mismatch means a protected scorer/numeric artifact moved.",
        "raw_sha256": raw,
        "registry_self_declared_sha256": reg.get("registry_sha256"),
        # The registry's frozen rule = canonical over reg WITHOUT the top-level
        # registry_sha256 only.
        "registry_selfrule_recomputed_sha256": canonical.content_hash(reg_minus_top),
        # Direct's canonical_content_sha256 strips registry_sha256/self_sha256/sha256
        # RECURSIVELY, so it ALSO drops the 5 nested panel_provenance.source_artifacts
        # sha256 keys -> a DIFFERENT value from the self-declared one. Recorded as
        # informational; Direct never binds the full registry in this bridge (it binds
        # the Stage-2 registry VIEW, which carries no panel_provenance / nested sha256).
        "registry_direct_canonical_content_sha256": canonical.canonical_content_sha256(reg),
        "registry_scorer_projection_sha256": prov._canon(prov._scoring_projection(reg)),
        "validation_direct_canonical_content_sha256": canonical.canonical_content_sha256(val),
        "selectability_direct_canonical_content_sha256": canonical.canonical_content_sha256(sel),
    }


def _self_check(base: dict) -> None:
    """canonical.py must reproduce the independently-known frozen values.
    One-time reseal 2026-07-12: display_label reclassified as a Tier-2 display field and dropped from the
    registry, so the three registry-derived pins advanced ONCE (self 2493896a→84da49c9, scorer-projection
    9621067b→008c1da1, raw 91ba78df→20f91fdd). The Stage-2-bound scorer VIEW / selection_id is unchanged."""
    assert base["registry_self_declared_sha256"] == \
        "84da49c9bc6508b845c6d8527f6e1f2abc01d4d3abe74fbb74e377401b0aa7fa", \
        "registry self-declared sha drift"
    # Validates canonical_json + content_hash (sort_keys, compact seps, ensure_ascii)
    # against the registry's own frozen rule.
    assert base["registry_selfrule_recomputed_sha256"] == base["registry_self_declared_sha256"], \
        "canonical.py content_hash != registry self-declared rule (canonical.py drift)"
    assert base["registry_scorer_projection_sha256"] == \
        "008c1da121a1ea3b08871f1bc0339b120d5dc9b46d01619768eebd046331bd85", \
        "scorer-projection invariant drift"
    assert base["raw_sha256"]["registry_v3"] == \
        "20f91fdd2c02335790cc580bab034fa83f422678442c0c0fc1472e6b25386d4f", \
        "served registry raw sha drift"


if __name__ == "__main__":
    base = compute_baseline()
    _self_check(base)
    with open(BASELINE_PATH, "w") as fh:
        json.dump(base, fh, indent=2, sort_keys=True)
        fh.write("\n")
    print("canonical.py self-check PASSED (84da49c9 + 008c1da1 reproduced; Tier-2 display de-baked)")
    print("wrote", os.path.relpath(BASELINE_PATH, ANALYSIS))
    for k, v in base["raw_sha256"].items():
        print(f"  {k:26s} {v}")
