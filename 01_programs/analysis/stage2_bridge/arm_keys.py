"""Canonical reusable-ARM KEYING + frozen topology for Stage-1 selections.

Frozen by ROUND4_ADDENDUM.md sha c4773562 (owner Rule 2). ONE source of truth, imported by the materializer
(emit_selection_contract), the independent verifier, and the release generator — so all three agree byte-for-byte.

A reusable arm is keyed by the perturbation's DESIRED CHANGE in the program score (increase|decrease), NEVER
the pole direction (high|low) or the role: the same `high` pole means OPPOSITE perturbations by role, so a
cached arm must not depend on role/pole. Pole (high|low) + role stay SELECTION metadata and never alter an arm.

Frozen (role, pole) -> desired_change mapping (the verifier re-derives it):
    away_from_A(high) -> decrease      away_from_A(low) -> increase
    toward_B(high)    -> increase      toward_B(low)    -> decrease

The admitted program set is derived from the bound v3 SCORER VIEW (base_portable primaries; Th9 excluded) and
BINDS the view's canonical sha256 — never a legacy registry path. Logical arm space = 300 slots
(60 Direct + 120 temporal + 120 pathway x 2 sources), compiled onto 15 content-addressed all-arm bundles
(3 Direct + 6 ordered-temporal + 6 pathway condition/source), each carrying all 20 (program x desired_change)
arms; the 6 pathway bundles each emit ONE shared convergence artifact referenced by that bundle's 20 enrichment
arms (no rank-antisymmetry inference). Selector capacity = 3,540 valid ordered selections.
"""
from __future__ import annotations

import itertools
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ANALYSIS = os.path.dirname(HERE)
for _p in (HERE, ANALYSIS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import build_registry_view as rv  # noqa: E402  (independent Stage-2 scorer-view rebuild)

SPEC = "ROUND4_ADDENDUM.md"
SPEC_SHA256 = "c477356278c5b7d2842659f5354792c9db7203ee774f8dd70653921124477a9f"

DIRECTIONS = ("high", "low")                 # pole directions (selection metadata only)
DESIRED_CHANGES = ("decrease", "increase")   # the reusable-arm key dimension
CONDITIONS = ("Rest", "Stim8hr", "Stim48hr")
PATHWAY_SOURCES = ("GO-BP", "Reactome")      # ROUND4 Standing: Reactome / GO-BP only

# Frozen role x pole -> desired_change (ROUND4_ADDENDUM c4773562). away_from_A INVERTS the pole; toward_B
# FOLLOWS it. `high` means "raise the score"; the desired change is what the perturbation should do to it.
_DESIRED = {
    ("away_from_A", "high"): "decrease",
    ("away_from_A", "low"): "increase",
    ("toward_B", "high"): "increase",
    ("toward_B", "low"): "decrease",
}


def desired_change(role, direction):
    """(role, pole direction) -> desired change in the program score. Re-derivable by the verifier."""
    try:
        return _DESIRED[(role, direction)]
    except KeyError:
        raise ValueError(f"no desired_change for role={role!r} direction={direction!r}")


def direct_key(program_id, dc, condition):
    return f"direct|{program_id}|{dc}|{condition}"


def temporal_key(program_id, dc, frm, to):
    return f"temporal|{program_id}|{dc}|{frm}|{to}"


def pathway_key_base(program_id, dc, condition):
    return f"pathway|{program_id}|{dc}|{condition}"


def pathway_key(program_id, dc, condition, source):
    return f"{pathway_key_base(program_id, dc, condition)}|{source}"


def ordered_condition_pairs(conditions=CONDITIONS):
    """All ordered (from, to) with from != to — 6 for 3 conditions."""
    return list(itertools.permutations(conditions, 2))


def base_portable_programs():
    """Admitted program set: base-portable primaries from the FROZEN v3 scorer VIEW (Th9 excluded).

    Returns (sorted_program_ids, view_canonical_sha256). The view canonical sha is the binding the release +
    verifier pin; this never reads a legacy stage01_program_registry.json path or a copied count.
    """
    view, _raw, canon = rv.build_and_hash()
    progs = sorted(p["program_id"] for p in view["programs"] if p.get("base_portable"))
    return progs, canon


def enumerate_logical(programs, conditions=CONDITIONS, sources=PATHWAY_SOURCES):
    """The full logical arm space as {lane: sorted[keys]} — 300 slots for 10 programs / 3 conds / 2 sources."""
    direct, temporal, pathway = set(), set(), set()
    for p in programs:
        for dc in DESIRED_CHANGES:
            for c in conditions:
                direct.add(direct_key(p, dc, c))
                for s in sources:
                    pathway.add(pathway_key(p, dc, c, s))
            for frm, to in ordered_condition_pairs(conditions):
                temporal.add(temporal_key(p, dc, frm, to))
    return {"direct": sorted(direct), "temporal": sorted(temporal), "pathway": sorted(pathway)}


def physical_bundles(programs, conditions=CONDITIONS, sources=PATHWAY_SOURCES):
    """15 content-addressed ALL-ARM bundles; each carries every (program x desired_change) arm. The 6 pathway
    (condition, source) bundles each declare ONE shared convergence artifact for their 20 enrichment arms."""
    pd = [(p, dc) for p in programs for dc in DESIRED_CHANGES]     # 20 arms per bundle
    bundles = []
    for c in conditions:                                          # 3 Direct condition bundles
        bundles.append({"kind": "direct", "bundle_id": f"direct|{c}",
                        "arms": sorted(direct_key(p, dc, c) for p, dc in pd)})
    for frm, to in ordered_condition_pairs(conditions):          # 6 temporal ordered-pair bundles
        bundles.append({"kind": "temporal", "bundle_id": f"temporal|{frm}|{to}",
                        "arms": sorted(temporal_key(p, dc, frm, to) for p, dc in pd)})
    for c in conditions:                                         # 6 pathway (condition, source) bundles
        for s in sources:
            bundles.append({"kind": "pathway", "bundle_id": f"pathway|{c}|{s}",
                            "convergence_artifact": f"convergence|{c}|{s}",   # shared by this bundle's 20 arms
                            "arms": sorted(pathway_key(p, dc, c, s) for p, dc in pd)})
    return bundles


def selection_capacity(n_programs, conditions=CONDITIONS):
    """Valid ordered selections; only an exactly-identical (program, pole, condition) tuple is refused."""
    n_states = n_programs * len(DIRECTIONS)                       # 20 states per condition (10 programs x 2 poles)
    within = len(conditions) * n_states * (n_states - 1)         # 3 x 20 x 19 = 1,140 (exclude identical tuple)
    n_pairs = len(conditions) * (len(conditions) - 1)            # 6 ordered condition pairs
    temporal = n_pairs * n_states * n_states                     # 6 x 20 x 20 = 2,400 (conditions differ)
    return {"n_states_per_condition": n_states, "within_condition": within,
            "temporal_cross_condition": temporal, "total": within + temporal}


def topology(programs=None, view_canon=None):
    """Full frozen topology bound to the v3 scorer VIEW; Task-C inventory the verifier checks against c4773562."""
    if programs is None or view_canon is None:
        programs, view_canon = base_portable_programs()
    logical = enumerate_logical(programs)
    counts = {k: len(v) for k, v in logical.items()}
    counts["total"] = sum(counts.values())
    bundles = physical_bundles(programs)
    return {
        "spec": SPEC,
        "spec_sha256": SPEC_SHA256,
        "program_set_source": "v3_scorer_view",
        "registry_scorer_view_canonical_sha256": view_canon,
        "base_portable_programs": list(programs),
        "n_programs": len(programs),
        "excluded_nonportable": ["th9_like"],
        "conditions": list(CONDITIONS),
        "pathway_sources": list(PATHWAY_SOURCES),
        "desired_change_mapping": {f"{r}({d})": desired_change(r, d)
                                   for r in ("away_from_A", "toward_B") for d in DIRECTIONS},
        "arm_keying": {
            "direct": "(program, desired_change, condition)",
            "temporal": "(program, desired_change, from, to)",
            "pathway": "(program, desired_change, condition, source)",
        },
        "logical_slots": counts,                                  # {direct:60, temporal:120, pathway:120, total:300}
        "physical_bundles": {"direct": len(CONDITIONS),
                             "temporal": len(ordered_condition_pairs()),
                             "pathway": len(CONDITIONS) * len(PATHWAY_SOURCES),
                             "total": len(bundles)},              # 3 + 6 + 6 = 15
        "convergence_artifacts": sum(1 for b in bundles if b["kind"] == "pathway"),   # 6 (one per pathway bundle)
        "selection_capacity": selection_capacity(len(programs)),  # {within:1140, temporal:2400, total:3540}
        "pair_semantics": "a pair = a join of two INDEPENDENT per-program reusable arms (away_from_A on A + "
                          "toward_B on B); no combined/balanced/weighted score; any pair-derived Pareto/"
                          "concordance is join-time display-only, off by default, not stored, not in this manifest",
    }


if __name__ == "__main__":
    import json
    t = topology()
    print(json.dumps({k: v for k, v in t.items() if k != "base_portable_programs"}, indent=2))
    print("base_portable_programs:", t["base_portable_programs"])
