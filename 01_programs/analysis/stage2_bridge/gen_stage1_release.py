"""Emit the GENERIC Stage-1 v3 RELEASE BUNDLE + a deterministic materializer index (round-4 finding #12;
fills the invocation-matrix $STAGE1_RELEASE / $REGISTRY / $STAGE1_SCHEMA).

The release is GENERIC (Round-4 Addendum Rule 2 — corrects 209edb2, which wrongly hard-coded Treg->Th1 as
canonical): it pins the frozen Stage-1 artifacts by BOTH raw and canonical sha256 and DECLARES the generic
selector — registry + v3 schema + the deterministic materializer emit_selection_contract.build_contract,
which builds a valid spot.stage01_selection.v3 for ANY (program pair, directions, timepoints). NO biological
pair is canonical.

A pair is expressed as TWO INDEPENDENT per-program arm references (away_from_A on A + toward_B on B; no
combined score), keyed for reusable arm artifacts: Direct (program, direction, condition); temporal
(program, direction, from, to); pathway (program, direction, condition, source).

treg_like/high -> th1_like/high is emitted only as a clearly-labelled DEMO/DEFAULT fixture (owner-confirmable),
never the release's canonical biology.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYSIS = os.path.dirname(HERE)
PROGRAMS = os.path.dirname(ANALYSIS)
REPO = os.path.dirname(PROGRAMS)
DATA = os.path.join(PROGRAMS, "app", "data")
sys.path.insert(0, ANALYSIS)
sys.path.insert(0, HERE)

import arm_keys as ak                   # noqa: E402  (frozen desired_change topology, ROUND4 c4773562)
import build_registry_view as rv        # noqa: E402
import canonical                        # noqa: E402
import emit_selection_contract as sc    # noqa: E402
import verify_stage1_provenance as prov  # noqa: E402

OUT = os.path.join(HERE, "release")
SELDIR = os.path.join(OUT, "selections")

# DEMO/DEFAULT only — NOT the release's canonical biology. Owner-confirmable at run time; any pair is valid.
DEMO_A = ("treg_like", "high")
DEMO_B = ("th1_like", "high")
CONDITIONS = ["Rest", "Stim8hr", "Stim48hr"]
ORDERED_PAIRS = [("Rest", "Stim8hr"), ("Stim8hr", "Rest"), ("Rest", "Stim48hr"),
                 ("Stim48hr", "Rest"), ("Stim8hr", "Stim48hr"), ("Stim48hr", "Stim8hr")]


def _raw(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def _canon_json(p): return canonical.canonical_content_sha256(json.load(open(p)))
def _rel(p): return os.path.relpath(p, REPO)


def _selfhash(obj, field):
    d = {k: v for k, v in obj.items() if k != field}
    return hashlib.sha256(json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def _component(path, role, universe=None, extra=None):
    c = {"path": _rel(path), "raw_sha256": _raw(path)}
    if path.endswith(".json"):
        c["canonical_content_sha256"] = _canon_json(path)
    c["role"] = role
    if universe:
        c["universe"] = universe
    if extra:
        c.update(extra)
    return c


def build_release() -> dict:
    reg_p = os.path.join(DATA, "stage01_program_registry_v3.json")
    reg = json.load(open(reg_p))
    schema_p = os.path.join(HERE, "schemas", "spot.stage01_selection.v3.schema.json")
    prot = json.load(open(os.path.join(HERE, "PROTECTED_HASHES.json")))
    topo = ak.topology()   # 10 admitted programs derived from the v3 scorer VIEW; binds its canonical sha
    b = {
        "schema": "spot.stage01_v3_release.v1",
        "method_version": sc.STAGE1_METHOD_VERSION,
        "stage1_registry_sha256": reg["registry_sha256"],
        "registry_scorer_projection_sha256": prov._canon(prov._scoring_projection(reg)),
        "registry_scorer_view_canonical_sha256": rv.build_and_hash()[2],
        "scores_canonical_content_sha256": reg["scores_canonical_content_sha256"],
        "coordinates_sha256": reg["coordinates_sha256"],
        "source_h5ad_sha256": sc.SOURCE_H5AD_SHA256,
        "source_hf_revision": sc.SOURCE_HF_REVISION,
        "effect_universe_id": sc.EFFECT_UNIVERSE_ID,
        # GENERIC selector — NO biological pair is canonical. The admitted program set + arm topology are
        # DERIVED from the v3 scorer VIEW (10 base-portable; Th9 excluded) and BIND its canonical sha256.
        "selector": {
            "kind": "generic_continuous_program_selector",
            "materializer": "stage2_bridge/emit_selection_contract.build_contract",
            "selection_schema": "spot.stage01_selection.v3",
            "program_set_source": topo["program_set_source"],                                  # v3_scorer_view
            "registry_scorer_view_canonical_sha256": topo["registry_scorer_view_canonical_sha256"],
            "admitted_programs": topo["base_portable_programs"],                               # 10, from the VIEW
            "excluded_nonportable": topo["excluded_nonportable"],
            "directions": list(sc.DIRECTIONS),
            "conditions": topo["conditions"],
            "pathway_sources": topo["pathway_sources"],
            "modes": ["within_condition", "temporal_cross_condition"],
            "desired_change_mapping": topo["desired_change_mapping"],   # (role, pole) -> increase|decrease
            "arm_keying": topo["arm_keying"],                          # keyed on desired_change, not pole
            "arm_topology": {
                "spec": topo["spec"], "spec_sha256": topo["spec_sha256"],
                "logical_slots": topo["logical_slots"],                # {direct:60, temporal:120, pathway:120, total:300}
                "physical_bundles": topo["physical_bundles"],          # {direct:3, temporal:6, pathway:6, total:15}
                "convergence_artifacts": topo["convergence_artifacts"],   # 6 (one per pathway bundle)
            },
            "selection_capacity": topo["selection_capacity"],          # {within:1140, temporal:2400, total:3540}
            "pair_semantics": topo["pair_semantics"],
        },
        "components": {
            "registry_v3": _component(reg_p, "program_registry", "effect_universe_gwcd4i"),
            "validation": _component(os.path.join(DATA, "stage01_validation.json"), "frozen_validation"),
            "selectability_v3": _component(os.path.join(DATA, "stage01_selectability_v3.json"),
                                           "historical_within_condition_validation", extra={"active_gate": False}),
            "gate_spec": _component(os.path.join(DATA, "stage01_gate_spec.json"), "pre_registered_gate_spec"),
            "selection_schema_v3": _component(schema_p, "selection_contract_schema"),
            "stage2_registry_view": _component(os.path.join(DATA, "stage01_stage2_registry_view.json"),
                                               "executable_scorer_view",
                                               extra={"note": "canonical == registry_scorer_view_canonical_sha256; what selection_id binds"}),
            "effect_universe": _component(os.path.join(ANALYSIS, "effect_universe_gwcd4i.json"),
                                          "effect_universe_target_space"),
            "scores_parquet": {"role": "continuous_program_scores_396k",
                               "canonical_content_sha256": reg["scores_canonical_content_sha256"],
                               "raw_sha256_staged": prot["raw_sha256"]["scores_parquet_staged"],
                               "location": "release_staging_not_served", "n_rows": 396000,
                               "note": "gitignored; regenerated from the public h5ad by gen_stage1_scores_v3.py, proves 43c4296d"},
            "activation_association": _component(os.path.join(DATA, "stage01_activation_association_v1.json"),
                                                 "descriptive_activation_association", extra={"active_gate": False}),
        },
    }
    b["self_release_sha256"] = _selfhash(b, "self_release_sha256")
    return b


def _entry(matrix_var, path, c, conds):
    return {"matrix_var": matrix_var, "path": _rel(path), "analysis_mode": c["analysis_mode"],
            "conditions": conds, "A": c["canonical_content"]["A"], "B": c["canonical_content"]["B"],
            "arms": c["arms"], "execution_status": c["execution_status"], "estimator_status": c["estimator_status"],
            "selection_id": c["selection_id"], "full_contract_content_sha256": c["full_contract_content_sha256"]}


def build_demo_selections():
    entries = []
    for cond in CONDITIONS:
        c = sc.build_contract(DEMO_A[0], DEMO_A[1], DEMO_B[0], DEMO_B[1], [cond])
        p = os.path.join(SELDIR, f"stage01_selection_within_{cond}.v3.json")
        open(p, "w").write(sc.emit_json(c))
        entries.append(_entry("SEL_WITHIN_" + cond, p, c, [cond]))
    for c1, c2 in ORDERED_PAIRS:
        c = sc.build_contract(DEMO_A[0], DEMO_A[1], DEMO_B[0], DEMO_B[1], [c1, c2])
        p = os.path.join(SELDIR, f"stage01_selection_temporal_{c1}_{c2}.v3.json")
        open(p, "w").write(sc.emit_json(c))
        entries.append(_entry(f"SEL_TEMPORAL_{c1}_{c2}", p, c, [c1, c2]))
    return entries


def main():
    os.makedirs(SELDIR, exist_ok=True)
    rel = build_release()
    rel_p = os.path.join(OUT, "stage01_v3_release.json")
    open(rel_p, "w").write(json.dumps(rel, indent=2, ensure_ascii=True, sort_keys=False) + "\n")

    entries = build_demo_selections()
    index = {
        "schema": "spot.stage01_v3_release_index.v1",
        "release_bundle": _rel(rel_p),
        "release_self_release_sha256": rel["self_release_sha256"],
        "selection_schema": _rel(os.path.join(HERE, "schemas", "spot.stage01_selection.v3.schema.json")),
        "registry": _rel(os.path.join(DATA, "stage01_program_registry_v3.json")),
        "materializer": "stage2_bridge/emit_selection_contract.build_contract",
        "selector_is_generic": True,
        "demo_default_selection": {
            "role": "demo_default_only",
            "note": "DEMO/DEFAULT fixture ONLY — NOT the release's canonical biology. The selector is generic "
                    "(any program pair, independent directions, same or different timepoints); the owner confirms "
                    "the real A/B at run time. Alternatives: B=cd4_ctl_like; direction variants; any registry pair.",
            "A_away_from": {"program_id": DEMO_A[0], "direction": DEMO_A[1]},
            "B_toward": {"program_id": DEMO_B[0], "direction": DEMO_B[1]},
            "arms": ["away_from_A", "toward_B"],
        },
        "demo_selections": entries,
    }
    idx_p = os.path.join(OUT, "stage01_v3_release_index.json")
    open(idx_p, "w").write(json.dumps(index, indent=2, ensure_ascii=True, sort_keys=False) + "\n")

    print("GENERIC RELEASE BUNDLE:", _rel(rel_p))
    print("  self_release_sha256:", rel["self_release_sha256"], "| raw:", _raw(rel_p))
    print("  selector.kind:", rel["selector"]["kind"], "| admitted programs:", len(rel["selector"]["admitted_programs"]),
          "| logical arms:", rel["selector"]["arm_topology"]["logical_slots"]["total"],
          "| capacity:", rel["selector"]["selection_capacity"]["total"])
    print("INDEX:", _rel(idx_p), "raw:", _raw(idx_p))
    print("\nDEMO/DEFAULT selections (matrix_var | mode | exec | selection_id | full_contract_content_sha256):")
    for e in entries:
        print(f"  {e['matrix_var']:26s} {e['analysis_mode']:22s} {e['execution_status']:6s} "
              f"{e['selection_id']} {e['full_contract_content_sha256']}")


if __name__ == "__main__":
    main()
