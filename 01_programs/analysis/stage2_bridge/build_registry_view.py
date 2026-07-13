"""CP2 — build the executable Stage-2 registry VIEW (scorer projection).

The primary registry `stage01_program_registry_v3.json` stays the full measurement +
provenance registry and is NEVER mutated. This module derives a SEPARATE, deterministic,
hash-bound `stage01_stage2_registry_view.json` carrying ONLY the executable scorer
projection Direct needs. Its canonical content hash is `hashes.registry_sha256` for
Direct (and therefore the registry input to `selection_id`).

Deterministic inputs (all frozen):
  * the 11 primary programs of the v3 registry  (role == "primary"; the actadj
    sensitivity lane is EXCLUDED from selectable programs);
  * the effect_universe symbol->Ensembl crosswalk (the 10,282-gene Stage-2 gene space);
  * the frozen validation stage2_base_portability records.

No score, control, coefficient, or metric value is recomputed. panel_ensembl /
control_ensembl are emitted ONLY for symbols present in the effect universe; retained /
missing symbol lists + counts are explicit. The counts are independently verified to
equal the frozen base_portability observed values (build asserts this).

Citations / rationales / provenance never enter this view, so its canonical hash is
invariant to citation-only edits of the primary registry.
"""
from __future__ import annotations

import json
import os

import canonical

VIEW_SCHEMA = "spot.stage01_stage2_registry_view.v1"
METHOD_VERSION = "stage1-continuous-v3.0.1"


def _flatten_controls(controls_by_bin: dict) -> list[str]:
    """Deterministic control-symbol order: bins ascending by integer key, then the
    stored within-bin order. First occurrence wins if a symbol repeats across bins."""
    out: list[str] = []
    seen: set[str] = set()
    for b in sorted(controls_by_bin, key=lambda x: int(x)):
        for s in controls_by_bin[b]:
            if s not in seen:
                seen.add(s)
                out.append(s)
    return out


def _project_program(prog: dict, sym2ens: dict, base_portability: dict) -> dict:
    pid = prog["program_id"]
    role = prog["role"]

    panel_symbols = list(prog.get("panel_genes_measured", []))
    panel_retained = [s for s in panel_symbols if s in sym2ens]
    panel_missing = [s for s in panel_symbols if s not in sym2ens]
    panel_ensembl = [sym2ens[s] for s in panel_retained]

    control_symbols = _flatten_controls(prog.get("controls_by_bin", {}))
    control_retained = [s for s in control_symbols if s in sym2ens]
    control_missing = [s for s in control_symbols if s not in sym2ens]
    control_ensembl = [sym2ens[s] for s in control_retained]

    bp = base_portability.get(pid, {})
    base_portable = bp.get("stage2_base_portable")

    return {
        "program_id": pid,
        "score_field": prog["score_field"],
        "role": role,
        "primary": role == "primary",
        "base_portable": base_portable,
        "scoring_method": prog.get("scoring_method"),
        "normalization": prog.get("normalization"),
        "coefficients": prog.get("coefficients"),
        "n_bins": prog.get("n_bins"),
        "ctrl_size": prog.get("ctrl_size"),
        "panel_symbols": panel_symbols,
        "panel_symbols_retained": panel_retained,
        "panel_symbols_missing": panel_missing,
        "n_panel_symbols": len(panel_symbols),
        "n_panel_in_effect_universe": len(panel_ensembl),
        "panel_ensembl": panel_ensembl,
        "control_symbols_retained": control_retained,
        "control_symbols_missing": control_missing,
        "n_control_symbols": len(control_symbols),
        "n_control_in_effect_universe": len(control_ensembl),
        "control_ensembl": control_ensembl,
    }


def build_view(registry: dict, effect_universe: dict, validation: dict) -> dict:
    """Pure, deterministic. Returns the Stage-2 registry-view document."""
    sym2ens = effect_universe["symbol_to_ensembl"]
    base_portability = validation["stage2_base_portability"]

    primaries = [p for p in registry["programs"] if p.get("role") == "primary"]
    programs = [_project_program(p, sym2ens, base_portability) for p in primaries]

    view = {
        "schema_version": VIEW_SCHEMA,
        "method_version": METHOD_VERSION,
        "view_kind": "executable_scorer_projection",
        "note": ("Executable scorer projection of the primary v3 registry into the "
                 "Stage-2 effect-universe gene space. Citation/rationale/provenance are "
                 "intentionally excluded so this hash is invariant to provenance-only "
                 "edits. panel_ensembl/control_ensembl carry ONLY symbols present in the "
                 "effect universe; retained/missing lists are explicit. No value recomputed."),
        "effect_universe_id": effect_universe.get("provenance", {}).get("effect_universe_id")
        or "marson2025_gwcd4_perturbseq : GWCD4i.DE_stats.h5ad",
        "effect_universe_symbols_sha256": effect_universe.get("symbols_sha256"),
        "effect_universe_n_symbols": len(sym2ens),
        "n_programs": len(programs),
        "sensitivity_lane_excluded": [s.get("program_id") for s in registry.get("sensitivity_lanes", [])],
        "programs": programs,
    }
    return view


def _assert_counts_match_frozen(view: dict, validation: dict) -> None:
    """Independent guard: the crosswalk-derived in-universe counts MUST equal the
    frozen base_portability observed values (proves same universe; no recomputation)."""
    bp = validation["stage2_base_portability"]
    for p in view["programs"]:
        pid = p["program_id"]
        metrics = {m["metric"]: m["observed"] for m in bp[pid]["metrics"]}
        assert p["n_panel_in_effect_universe"] == metrics["n_panel_in_effect_universe"], \
            f"{pid}: panel-in-universe {p['n_panel_in_effect_universe']} != frozen {metrics['n_panel_in_effect_universe']}"
        assert p["n_control_in_effect_universe"] == metrics["n_control_in_effect_universe"], \
            f"{pid}: control-in-universe {p['n_control_in_effect_universe']} != frozen {metrics['n_control_in_effect_universe']}"
        assert p["base_portable"] == bp[pid]["stage2_base_portable"], \
            f"{pid}: base_portable mismatch"


HERE = os.path.dirname(os.path.abspath(__file__))
ANALYSIS = os.path.dirname(HERE)
PROGRAMS = os.path.dirname(ANALYSIS)
DATA = os.path.join(PROGRAMS, "app", "data")


def load_sources() -> tuple[dict, dict, dict]:
    reg = json.load(open(os.path.join(DATA, "stage01_program_registry_v3.json")))
    eu = json.load(open(os.path.join(ANALYSIS, "effect_universe_gwcd4i.json")))
    val = json.load(open(os.path.join(DATA, "stage01_validation.json")))
    return reg, eu, val


def build_and_hash() -> tuple[dict, str, str]:
    reg, eu, val = load_sources()
    view = build_view(reg, eu, val)
    _assert_counts_match_frozen(view, val)
    raw = canonical.dumps_indent1(view)
    return view, raw, canonical.canonical_content_sha256(view)


def write_view() -> tuple[dict, str, str]:
    """Serve the executable scorer projection to app/data. Its canonical_content_sha256 is the
    citation-invariant registry_sha256 Direct binds; provenance-only edits of the primary registry
    do not change it."""
    view, raw, canon = build_and_hash()
    out = os.path.join(DATA, "stage01_stage2_registry_view.json")
    with open(out, "w") as fh:
        fh.write(raw)
    return view, out, canon


if __name__ == "__main__":
    view, out, canon = write_view()
    print("wrote Stage-2 registry view:", os.path.relpath(out, PROGRAMS), "|", view["n_programs"], "primary programs")
    print("view canonical_content_sha256 (== hashes.registry_sha256):", canon)
    print("view raw_sha256:", canonical.file_sha256(out))
    for p in view["programs"]:
        print(f"  {p['program_id']:16s} primary={p['primary']} base_portable={p['base_portable']} "
              f"panelE={p['n_panel_in_effect_universe']} ctrlE={p['n_control_in_effect_universe']}")
