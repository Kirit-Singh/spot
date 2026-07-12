"""Load + check the frozen protected baseline (generator != verifier).

`freeze_protected.py` writes PROTECTED_HASHES.json once (pre-change). This module only
READS it and re-checks the live tree against it, so the verifier never regenerates the
baseline it is meant to guard.
"""
from __future__ import annotations

import json
import os

import canonical

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYSIS = os.path.dirname(HERE)
PROGRAMS = os.path.dirname(ANALYSIS)
DATA = os.path.join(PROGRAMS, "app", "data")
BASELINE_PATH = os.path.join(HERE, "PROTECTED_HASHES.json")

# name -> (root_dir, filename) — must match freeze_protected.PROTECTED_RAW.
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


def load_baseline() -> dict:
    with open(BASELINE_PATH) as fh:
        return json.load(fh)


def check_protected() -> list[str]:
    """Return a list of drift messages (empty == every protected artifact byte-identical)."""
    base = load_baseline()
    fails: list[str] = []
    want = base["raw_sha256"]
    for name, (root, fn) in PROTECTED_RAW.items():
        p = os.path.join(root, fn)
        cur = canonical.file_sha256(p) if os.path.exists(p) else None
        if cur != want.get(name):
            fails.append(f"protected raw drift: {name} baseline={want.get(name)} current={cur}")
    # derived scorer invariants (registry byte-identity implies these, but check anyway)
    reg = json.load(open(os.path.join(DATA, "stage01_program_registry_v3.json")))
    reg_minus_top = {k: v for k, v in reg.items() if k != "registry_sha256"}
    if canonical.content_hash(reg_minus_top) != base["registry_self_declared_sha256"]:
        fails.append("registry self-rule canonical drift")
    return fails


if __name__ == "__main__":
    problems = check_protected()
    if problems:
        print("PROTECTED BASELINE: DRIFT")
        for p in problems:
            print("  " + p)
        raise SystemExit(1)
    print("PROTECTED BASELINE: OK (all protected artifacts byte-identical)")
