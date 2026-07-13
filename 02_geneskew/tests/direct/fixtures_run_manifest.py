"""FIXTURES for the aggregate run manifest. SYNTHETIC — not a run, not data, not science.

Every document these builders write is a FIXTURE and says so in its own bytes
(``"fixture": true``, ids prefixed ``FIXTURE-``). Nothing here is a measurement: the
scores, hashes and rankings are invented so the TOPOLOGY can be exercised. What IS real is
the CARDINALITY — 10 base-portable programs, 3 conditions, 2 gene-set sources — so the
300-slot / 15-bundle algebra is the algebra the real run will be held to.

The condition universe is NOT faked: it is read from the frozen batch policy that ships in
the tree, which is the same artifact the verifier binds.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any

# The real, frozen batch policy: the condition universe comes from it, here as in
# production. A fixture that invented its own conditions would exercise a topology the run
# does not have.
POLICY_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "analysis", "direct", "temporal", "batch_policy.v1.json")

# The ten base-portable programs of the frozen release. Real ids, so the fixture has the
# real cardinality; every VALUE attached to them below is synthetic.
FIXTURE_PROGRAMS = [
    "cd4_ctl_like", "diff_activated", "diff_checkpoint", "diff_memory", "diff_naive",
    "tfh_like", "th17_like", "th1_like", "th2_like", "treg_like",
]
# Excluded by the scorer view, exactly as the release excludes them.
FIXTURE_NON_PORTABLE = ["th9_like", "cd4_ctl_like_actadj"]

FIXTURE_SOURCES = ["go_bp", "reactome"]
PORTABILITY_FIELD = "base_portable"

INCREASE, DECREASE = "increase", "decrease"
DESIRED_CHANGES = (INCREASE, DECREASE)

# The frozen role x pole origins that map to each desired change (see the addendum).
ORIGINS = {
    DECREASE: [{"role": "away_from_A", "pole_direction": "high"},
               {"role": "toward_B", "pole_direction": "low"}],
    INCREASE: [{"role": "away_from_A", "pole_direction": "low"},
               {"role": "toward_B", "pole_direction": "high"}],
}

FIXTURE_SETS = {"FIXTURE-SET-1": ["treg_like", "th1_like", "tfh_like"],
                "FIXTURE-SET-2": ["diff_naive", "diff_memory"]}


def _canon(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True).encode()).hexdigest()


def _raw(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _write(path: str, doc: Any) -> tuple[str, str]:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return _raw(path), _canon(doc)


def _binding(out_dir: str, rel: str, doc: Any) -> dict[str, str]:
    raw, canon = _write(os.path.join(out_dir, rel), doc)
    return {"path": rel, "raw_sha256": raw, "canonical_sha256": canon}


def conditions() -> list[str]:
    with open(POLICY_PATH) as fh:
        return sorted(json.load(fh)["condition_composition"].keys())


def scorer_view(tmp_path, programs=None) -> str:
    """A FIXTURE v3 generic release / scorer view. The program set is re-derivable."""
    progs = list(FIXTURE_PROGRAMS if programs is None else programs)
    doc = {
        "fixture": True,
        "schema_version": "FIXTURE.spot.stage01_stage2_registry_view.v1",
        "method_version": "FIXTURE-stage1-continuous-v3.0.1",
        "base_portability_source_field": PORTABILITY_FIELD,
        "base_portable_programs": sorted(progs),
        "n_base_portable": len(progs),
        "programs": (
            [{"program_id": p, PORTABILITY_FIELD: True,
              "method_hash": _canon(f"FIXTURE-scorer-{p}")} for p in progs]
            + [{"program_id": p, PORTABILITY_FIELD: False,
                "method_hash": _canon(f"FIXTURE-scorer-{p}")}
               for p in FIXTURE_NON_PORTABLE]),
    }
    path = os.path.join(str(tmp_path), "FIXTURE_scorer_view.json")
    _write(path, doc)
    return path


def pinned_gene_sets(tmp_path) -> str:
    """The FIXTURE pinned source identities: the source universe, from outside the run."""
    doc = {src: {"fixture": True,
                 "raw_sha256": _canon(f"FIXTURE-raw-{src}"),
                 "canonical_sha256": _canon(f"FIXTURE-canon-{src}")}
           for src in FIXTURE_SOURCES}
    path = os.path.join(str(tmp_path), "FIXTURE_pinned_gene_sets.json")
    _write(path, doc)
    return path


def _code_identity() -> dict[str, Any]:
    return {"fixture": True, "commit": "f" * 40, "clean_tree": True,
            "manifest_sha256": _canon("FIXTURE-code-manifest"),
            "canonical_digest": _canon("FIXTURE-code-manifest")[:16],
            "n_files": 1, "clean_checkout_required": True}


def _selection_release(scorer_path: str) -> dict[str, Any]:
    return {"fixture": True, "release_id": "FIXTURE-stage1-v3-generic-release",
            "scorer_view_raw_sha256": _raw(scorer_path),
            "selection_schema_sha256": _canon("FIXTURE-v3-schema")}


def _inputs() -> list[dict[str, Any]]:
    return [{"name": n, "sha256": _canon(f"FIXTURE-input-{n}"), "size_bytes": 1}
            for n in ("GWCD4i.DE_stats.h5ad", "sgrna_library_metadata.suppl_table.csv")]


def _ranking(program: str, dc: str, ctx: dict) -> dict[str, Any]:
    """A FIXTURE arm ranking: target ids, canonical scores, ranks, evaluable flags."""
    targets = FIXTURE_SETS["FIXTURE-SET-1"] + FIXTURE_SETS["FIXTURE-SET-2"] + ["OTHER_1"]
    sign = 1.0 if dc == INCREASE else -1.0
    return {
        "fixture": True,
        "arm_key": "|".join(["", program, dc]).strip("|"),
        "context": ctx,
        "ranked": [{"target_id": t, "score": sign * (len(targets) - i),
                    "rank": i + 1, "evaluable": True}
                   for i, t in enumerate(targets)],
        "n_ranked": len(targets),
    }


def _pathway_bindings(out_dir: str) -> dict[str, dict]:
    """The BYTES every pathway count must be reconstructible from."""
    return {
        "gene_set_membership": _binding(out_dir, "gene_set_membership.json", {
            "fixture": True,
            "sets": {sid: {"genes_target": genes}
                     for sid, genes in FIXTURE_SETS.items()}}),
        "target_universe": _binding(out_dir, "target_universe.json", {
            "fixture": True,
            "target_ids": sorted({g for gs in FIXTURE_SETS.values() for g in gs}
                                 | {"OTHER_1"})}),
        "masked_signatures": _binding(out_dir, "masked_signatures.json", {
            "fixture": True,
            "signatures": {t: {"FIXTURE_GENE_1": 0.5}
                           for gs in FIXTURE_SETS.values() for t in gs}}),
        "readout_universe": _binding(out_dir, "readout_universe.json", {
            "fixture": True, "gene_ids": ["FIXTURE_GENE_1"]}),
    }


def build_bundle(root: str, lane: str, ctx: dict, scorer_path: str,
                 programs=None, arms_for=None) -> str:
    """Write ONE FIXTURE all-arm bundle and return its directory."""
    progs = list(FIXTURE_PROGRAMS if programs is None else programs)
    scorer = json.load(open(scorer_path))
    method = {p["program_id"]: p["method_hash"] for p in scorer["programs"]}

    if lane == "direct":
        slug, prov_name, ver_name = (
            ctx["condition"], "provenance.json", "verification.json")
    elif lane == "temporal":
        slug = f"{ctx['from_condition']}__{ctx['to_condition']}"
        prov_name, ver_name = "temporal_provenance.json", "temporal_verification.json"
    else:
        slug = f"{ctx['condition']}__{ctx['gene_set_source']}"
        prov_name, ver_name = "pathway_provenance.json", "pathway_verification.json"

    out_dir = os.path.join(root, lane, f"FIXTURE-{lane}-{slug}")
    os.makedirs(out_dir, exist_ok=True)

    bindings = _pathway_bindings(out_dir) if lane == "pathway" else {}
    membership = {sid: set(genes) for sid, genes in FIXTURE_SETS.items()}

    convergence_id = None
    if lane == "pathway":
        conv = {"fixture": True,
                "convergence_id": f"FIXTURE-CONV-{slug}",
                "note": "one convergence per (condition, source); shared by every arm",
                "pairs": []}
        raw, _canonical = _write(os.path.join(out_dir, "convergence.json"), conv)
        convergence_id = conv["convergence_id"]

    pairs = arms_for if arms_for is not None else [
        (p, dc) for p in progs for dc in DESIRED_CHANGES]

    arms = []
    for program, dc in pairs:
        ranking = _ranking(program, dc, ctx)
        rel = f"rankings/{program}__{dc}.json"
        arm: dict[str, Any] = {
            "arm_key": "|".join(
                [lane, program, dc]
                + ([ctx["condition"]] if lane == "direct" else
                   [ctx["from_condition"], ctx["to_condition"]] if lane == "temporal"
                   else [ctx["condition"], ctx["gene_set_source"]])),
            "program_id": program,
            "desired_change": dc,
            "program_method_hash": method[program],
            # ONE base effect per program/context; the two desired changes are exact sign
            # transforms of it — two logical arms, not two experimental estimates.
            "base_effect_sha256": _canon(f"FIXTURE-base-{program}-{slug}"),
            "arm_values_sha256": _canon(f"FIXTURE-values-{program}-{dc}-{slug}"),
            "n_ranked": ranking["n_ranked"],
            "derived_from_poles": ORIGINS[dc],
            "ranking": _binding(out_dir, rel, ranking),
        }
        if lane == "pathway":
            ranked = {r["target_id"] for r in ranking["ranked"]}
            arm["convergence_id"] = convergence_id
            # Declared AND reconstructible: the verifier recomputes this from the bound
            # membership and ranking bytes and refuses a declaration that disagrees.
            arm["n_hits_by_set"] = {sid: len(genes & ranked)
                                    for sid, genes in membership.items()}
        arms.append(arm)

    inv: dict[str, Any] = {
        "fixture": True,
        "schema_version": "spot.stage02_arm_bundle.v1",
        "lane": lane,
        "context": ctx,
        "scorer_view": {"raw_sha256": _raw(scorer_path),
                        "canonical_sha256": _canon(scorer),
                        "programs": sorted(progs)},
        "arms": arms,
        "n_arms": len(arms),
        "arms_are_independent": True,
    }
    if lane == "pathway":
        inv["bindings"] = bindings
        inv["gene_sets"] = {
            "gene_set_source": ctx["gene_set_source"],
            "release_id": f"FIXTURE-{ctx['gene_set_source']}-release",
            "raw_sha256": _canon(f"FIXTURE-raw-{ctx['gene_set_source']}"),
            "canonical_sha256": _canon(f"FIXTURE-canon-{ctx['gene_set_source']}")}
        inv["convergence"] = {
            "convergence_id": convergence_id,
            "sha256": _raw(os.path.join(out_dir, "convergence.json"))}
    inv["bundle_id"] = f"FIXTURE-{_canon(inv)[:16]}"
    _write(os.path.join(out_dir, "arm_bundle.json"), inv)

    _write(os.path.join(out_dir, prov_name), {
        "fixture": True,
        "schema_version": f"FIXTURE.spot.stage02_{lane}_provenance.v1",
        "run_binding": {
            "code_identity": _code_identity(),
            "selection_release": _selection_release(scorer_path),
            "stage2_inputs": _inputs(),
        },
    })
    _write(os.path.join(out_dir, ver_name), {
        "fixture": True,
        "schema_version": f"FIXTURE.spot.stage02_{lane}_verification.v1",
        "verifier_id": f"FIXTURE.spot.stage02.{lane}.verifier",
        "generator_is_not_verifier": True,
        "checks": [], "n_failed": 0, "verdict": "admit",
    })
    return out_dir


def complete_run(tmp_path, scorer_path=None) -> dict[str, Any]:
    """A COMPLETE FIXTURE run: every context, every program arm. 15 bundles, 300 slots."""
    root = os.path.join(str(tmp_path), "bundles")
    scorer_path = scorer_path or scorer_view(tmp_path)
    conds = conditions()

    direct = [build_bundle(root, "direct", {"condition": c}, scorer_path)
              for c in conds]
    temporal = [build_bundle(root, "temporal",
                             {"from_condition": a, "to_condition": b}, scorer_path)
                for a in conds for b in conds if a != b]
    pathway = [build_bundle(root, "pathway",
                            {"condition": c, "gene_set_source": s}, scorer_path)
               for c in conds for s in FIXTURE_SOURCES]
    return {"root": root, "scorer_view": scorer_path,
            "pinned_gene_sets": pinned_gene_sets(tmp_path),
            "batch_policy": POLICY_PATH,
            "direct": direct, "temporal": temporal, "pathway": pathway,
            "conditions": conds, "sources": list(FIXTURE_SOURCES)}
