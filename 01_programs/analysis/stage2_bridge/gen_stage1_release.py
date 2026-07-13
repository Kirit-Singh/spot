"""Emit the Stage-1 v3 RELEASE BUNDLE + the concrete production selection contracts (round-4 finding #12;
fills the invocation-matrix $STAGE1_RELEASE / $REGISTRY / $STAGE1_SCHEMA / $SEL_WITHIN_* / $SEL_TEMPORAL_*).

Deterministic; re-emit is byte-stable. The bundle pins the frozen Stage-1 artifacts by BOTH raw and
canonical sha256, plus the scorer-projection (008c1da1) and the Stage-2-bound scorer VIEW canonical
(5d1d8c36) — what selection_id actually binds. The selections are the canonical biological question
treg_like/high (A = away-from) -> th1_like/high (B = toward): away from the immunosuppressive Treg-like
program, toward the Th1-like anti-tumor effector. Both are base-portable primary programs (real registry
IDs). One selection per condition (Direct within_condition) + one per ordered temporal pair.

The A/B pair + directions is the single OWNER-CONFIRMABLE scientific choice; it is recorded explicitly in
the index so the real run cannot silently adopt an unreviewed hypothesis.
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

import build_registry_view as rv        # noqa: E402
import canonical                        # noqa: E402
import emit_selection_contract as sc    # noqa: E402
import verify_stage1_provenance as prov  # noqa: E402

OUT = os.path.join(HERE, "release")
SELDIR = os.path.join(OUT, "selections")

# The canonical biological question (owner-confirmable). Real registry program IDs; both base-portable.
A = ("treg_like", "high")     # away_from_A: the immunosuppressive Treg-like program
B = ("th1_like", "high")      # toward_B:   the Th1-like anti-tumor effector program
CONDITIONS = ["Rest", "Stim8hr", "Stim48hr"]
ORDERED_PAIRS = [("Rest", "Stim8hr"), ("Stim8hr", "Rest"), ("Rest", "Stim48hr"),
                 ("Stim48hr", "Rest"), ("Stim8hr", "Stim48hr"), ("Stim48hr", "Stim8hr")]


def _raw(p): return hashlib.sha256(open(p, "rb").read()).hexdigest()
def _canon_json(p): return canonical.canonical_content_sha256(json.load(open(p)))
def _rel(p): return os.path.relpath(p, REPO)


def _effect_scientific_sha(path):
    effect = json.load(open(path))
    projection = {
        "n_genes": effect["provenance"]["n_genes"],
        "symbols_sha256": effect["symbols_sha256"],
        "symbol_to_ensembl": effect["symbol_to_ensembl"],
    }
    return canonical.content_hash(projection)


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
            "effect_universe": _component(
                os.path.join(ANALYSIS, "effect_universe_gwcd4i.json"),
                "effect_universe_target_space",
                extra={"scientific_projection_sha256": _effect_scientific_sha(
                    os.path.join(ANALYSIS, "effect_universe_gwcd4i.json")
                )},
            ),
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


def build_selections():
    entries = []
    for cond in CONDITIONS:
        c = sc.build_contract(A[0], A[1], B[0], B[1], [cond])
        p = os.path.join(SELDIR, f"stage01_selection_within_{cond}.v3.json")
        open(p, "w").write(sc.emit_json(c))
        entries.append(("SEL_WITHIN_" + cond, p, c, [cond]))
    for c1, c2 in ORDERED_PAIRS:
        c = sc.build_contract(A[0], A[1], B[0], B[1], [c1, c2])
        p = os.path.join(SELDIR, f"stage01_selection_temporal_{c1}_{c2}.v3.json")
        open(p, "w").write(sc.emit_json(c))
        entries.append((f"SEL_TEMPORAL_{c1}_{c2}", p, c, [c1, c2]))
    return entries


def main():
    os.makedirs(SELDIR, exist_ok=True)
    rel = build_release()
    rel_p = os.path.join(OUT, "stage01_v3_release.json")
    open(rel_p, "w").write(json.dumps(rel, indent=2, ensure_ascii=True, sort_keys=False) + "\n")

    entries = build_selections()
    index = {
        "schema": "spot.stage01_v3_release_index.v1",
        "biological_question": {
            "A_away_from": {"program_id": A[0], "direction": A[1]},
            "B_toward": {"program_id": B[0], "direction": B[1]},
            "arms": ["away_from_A", "toward_B"],
            "rationale": "canonical Stage-1 question: away from the immunosuppressive Treg-like program, "
                         "toward the Th1-like anti-tumor effector. Both are base-portable primary programs.",
            "owner_decision": "OWNER-CONFIRMABLE: the A/B pair + directions determine the biological hypothesis; "
                              "confirm or override before authorizing the real run (alternatives: B=cd4_ctl_like; direction variants).",
        },
        "release_bundle": _rel(rel_p),
        "release_self_release_sha256": rel["self_release_sha256"],
        "selection_schema": _rel(os.path.join(HERE, "schemas", "spot.stage01_selection.v3.schema.json")),
        "registry": _rel(os.path.join(DATA, "stage01_program_registry_v3.json")),
        "selections": [
            {"matrix_var": var, "path": _rel(p), "analysis_mode": c["analysis_mode"], "conditions": conds,
             "A": c["canonical_content"]["A"], "B": c["canonical_content"]["B"],
             "execution_status": c["execution_status"], "estimator_status": c["estimator_status"],
             "selection_id": c["selection_id"], "full_contract_content_sha256": c["full_contract_content_sha256"]}
            for var, p, c, conds in entries
        ],
    }
    idx_p = os.path.join(OUT, "stage01_v3_release_index.json")
    open(idx_p, "w").write(json.dumps(index, indent=2, ensure_ascii=True, sort_keys=False) + "\n")

    print("RELEASE BUNDLE:", _rel(rel_p))
    print("  self_release_sha256:", rel["self_release_sha256"])
    print("  raw_sha256:", _raw(rel_p))
    print("INDEX:", _rel(idx_p), "raw:", _raw(idx_p))
    print("\nSELECTIONS (matrix_var | mode | exec | selection_id | full_contract_content_sha256):")
    for e in index["selections"]:
        print(f"  {e['matrix_var']:26s} {e['analysis_mode']:22s} {e['execution_status']:18s} "
              f"{e['selection_id']} {e['full_contract_content_sha256']}")


if __name__ == "__main__":
    main()
