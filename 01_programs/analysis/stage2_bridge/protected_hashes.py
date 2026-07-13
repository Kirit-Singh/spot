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
    "stage2_registry_view": (DATA, "stage01_stage2_registry_view.json"),   # the executable projection selection_id binds (S1-M1)
    "activation_association": (DATA, "stage01_activation_association_v1.json"),   # descriptive activation artifact (S1-M4)
}


def load_baseline() -> dict:
    with open(BASELINE_PATH) as fh:
        return json.load(fh)


def tier2_leak(reg) -> list:
    """S1-M2: program_ids carrying a Tier-2 display-only field that must NEVER live in the Tier-1 registry."""
    import sys
    sys.path.insert(0, ANALYSIS)
    from gen_stage1_provenance import DISPLAY_ONLY_FIELDS
    return sorted({p.get("program_id") or p.get("score_field")
                   for grp in ("programs", "sensitivity_lanes") for p in reg.get(grp, [])
                   if any(f in p for f in DISPLAY_ONLY_FIELDS)})


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

    import sys
    sys.path.insert(0, HERE)
    sys.path.insert(0, ANALYSIS)
    # S1-M1: independently REBUILD the Stage-2 scorer view and bind its canonical hash. A view mutation that
    # omits a gene/coefficient moves this even though the source registry + numerical artifacts are untouched.
    import build_registry_view as rv
    rebuilt = rv.build_and_hash()[2]
    if rebuilt != base.get("stage2_view_canonical_sha256"):
        fails.append(f"stage2 view canonical drift: baseline={base.get('stage2_view_canonical_sha256')} rebuilt={rebuilt}")
    # scorer-core projection invariant (registry -> scorer projection) must match the frozen value.
    import verify_stage1_provenance as prov
    proj = prov._canon(prov._scoring_projection(reg))
    if proj != base.get("registry_scorer_projection_sha256"):
        fails.append(f"registry scorer-projection drift: baseline={base.get('registry_scorer_projection_sha256')} current={proj}")

    # S1-M2: NAMED failure — Tier-2 display fields must never live in the Tier-1 scientific registry, even
    # if its raw sha were resealed to a leaked baseline. (The normal reproduce path now runs this checker.)
    leaked = tier2_leak(reg)
    if leaked:
        fails.append(f"tier2_field_in_tier1_registry: display-only field(s) present in {leaked}")

    return fails


if __name__ == "__main__":
    problems = check_protected()
    if problems:
        print("PROTECTED BASELINE: DRIFT")
        for p in problems:
            print("  " + p)
        raise SystemExit(1)
    print("PROTECTED BASELINE: OK (all protected artifacts byte-identical)")
