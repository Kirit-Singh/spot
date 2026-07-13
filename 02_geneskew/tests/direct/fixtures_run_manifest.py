"""FIXTURES for the aggregate run manifest. The BUNDLES are synthetic; the RELEASE is REAL.

Every bundle these builders write is a FIXTURE and says so in its own bytes
(``"fixture": true``, ids prefixed ``FIXTURE-``). Nothing in a bundle is a measurement:
the scores, hashes and rankings are invented so the TOPOLOGY can be exercised.

The RELEASE is not invented. An earlier version of this file manufactured a scorer view
with ``base_portability_source_field``, ``base_portable_programs`` and a per-program
``method_hash`` — NONE OF WHICH EXIST — so the suite was green against fields the real
release does not have, and proved only that the code agreed with the fiction. The
authoritative Stage-1 v3 release is now STAGED FROM GIT (``55899ac``) and bound as-is, so
the admitted programs (10, from ``program.base_portable``), the conditions
(``Rest, Stim8hr, Stim48hr``) and the pathway sources (``GO-BP, Reactome``) are the
release's, not ours.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from typing import Any

import pytest

# The authoritative Stage-1 v3 release. Staged, never fabricated.
RELEASE_COMMIT = "55899ac"
RELEASE_PATH = "01_programs/analysis/stage2_bridge/release/stage01_v3_release.json"
VIEW_PATH = "01_programs/app/data/stage01_stage2_registry_view.json"
REPO = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))))

PORTABLE_KEY = "base_portable"

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

# A member of FIXTURE-SET-1 that every arm RETAINS with rank null (W5 semantics). It is in
# the rows and not in the ranking, so it is never a hit.
UNRANKABLE_MEMBER = "tfh_like"


def _git_show(ref: str) -> bytes:
    out = subprocess.run(["git", "-C", REPO, "show", ref],
                         capture_output=True)
    if out.returncode != 0:
        pytest.skip(f"the authoritative release {ref} is not in this object store")
    return out.stdout


def stage_release(tmp_path) -> dict[str, Any]:
    """Materialise the REAL release + scorer view into an explicitly staged root."""
    root = os.path.join(str(tmp_path), "release_root")
    view_path = os.path.join(root, VIEW_PATH)
    os.makedirs(os.path.dirname(view_path), exist_ok=True)
    with open(view_path, "wb") as fh:
        fh.write(_git_show(f"{RELEASE_COMMIT}:{VIEW_PATH}"))

    release_path = os.path.join(root, "stage01_v3_release.json")
    raw = _git_show(f"{RELEASE_COMMIT}:{RELEASE_PATH}")
    with open(release_path, "wb") as fh:
        fh.write(raw)

    release = json.loads(raw)
    view = json.loads(open(view_path).read())
    admitted = sorted(p["program_id"] for p in view["programs"] if p[PORTABLE_KEY])
    return {
        "release_path": release_path,
        "release_root": root,
        "release": release,
        "view": view,
        "release_canonical_sha256": _canon(release),
        "programs": admitted,
        "conditions": list(release["selector"]["conditions"]),
        "sources": list(release["selector"]["pathway_sources"]),
        # the per-program projection id is SPECIFIED (the view carries none): the canonical
        # hash of that program's whole record
        "projection": {p["program_id"]: _canon(p)
                       for p in view["programs"] if p[PORTABLE_KEY]},
    }


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


def gene_set_identity(source: str) -> dict[str, Any]:
    """The FULL identity of one gene-set source. The pin and the bundle share this."""
    return {
        "release_id": f"FIXTURE-{source}-release-v1",
        "raw_sha256": _canon(f"FIXTURE-raw-{source}"),
        "canonical_sha256": _canon(f"FIXTURE-canon-{source}"),
        "gene_id_namespace": "ensembl_gene_id",
        "target_id_namespace": "ensembl_gene_id",
        "gene_set_license": f"FIXTURE-licence-{source}",
        "effect_universe_sha256": _canon("FIXTURE-effect-universe"),
        "target_universe_sha256": _canon("FIXTURE-target-universe"),
    }


def pinned_gene_sets(tmp_path, sources) -> str:
    """The FIXTURE pinned source identities: release, hashes, namespaces, licence and
    universe bindings — the whole identity, from OUTSIDE the run.

    A source NAME is not an identity. Checking only that the two sources differ let a
    forged 'reactome' pass, because nothing ever compared it to the Reactome that was
    actually pinned.
    """
    doc = {src: dict(gene_set_identity(src), fixture=True) for src in sources}
    path = os.path.join(str(tmp_path), "FIXTURE_pinned_gene_sets.json")
    _write(path, doc)
    return path


# WHO may admit an arm, and WHAT they must have checked. Pinned OUTSIDE the run: a forger
# writes the report, so the report cannot also be the authority on who wrote it.
LANE_VERIFIERS = {
    "direct": {"verifier_id": "FIXTURE.spot.stage02.direct.verifier.v1",
               "schema_version": "FIXTURE.spot.stage02_direct_verification.v1",
               "required_gates": ["screen_rows_reconstruct_from_the_inputs",
                                  "every_arm_ranks_over_its_own_population"]},
    # the REAL independent verifier id: W5's producer signs its PREFLIGHT with this, and
    # W11's root envelope signs the ADMISSION with it. Only the envelope admits.
    "temporal": {"verifier_id": "spot.stage02.temporal.arm.independent_verifier.v1",
                 "schema_version": "FIXTURE.spot.stage02_temporal_verification.v1",
                 "required_gates": ["endpoints_reconstruct",
                                    "the_did_is_a_difference_of_two_arm_values"]},
    "pathway": {"verifier_id": "FIXTURE.spot.stage02.pathway.verifier.v1",
                "schema_version": "FIXTURE.spot.stage02_pathway_verification.v1",
                "required_gates": ["coverage_and_per_arm_eligibility_rederive",
                                   "no_convergence_claim_rests_on_a_non_member"]},
}


def pinned_verifiers(tmp_path) -> str:
    path = os.path.join(str(tmp_path), "FIXTURE_pinned_verifiers.json")
    _write(path, LANE_VERIFIERS)
    return path


def expected_code_identity(tmp_path) -> str:
    """The pinned checkout every bundle must have been built from."""
    path = os.path.join(str(tmp_path), "FIXTURE_expected_code_identity.json")
    _write(path, _code_identity())
    return path


def _code_identity() -> dict[str, Any]:
    return {"fixture": True, "commit": "f" * 40, "clean_tree": True,
            "manifest_sha256": _canon("FIXTURE-code-manifest"),
            "canonical_digest": _canon("FIXTURE-code-manifest")[:16],
            "n_files": 1, "clean_checkout_required": True}


def _selection_release(staged: dict) -> dict[str, Any]:
    """W5's NATIVE Stage-1 binding: the scorer view its arms actually stood on."""
    return {"registry_scorer_view_sha256":
                staged["release"]["registry_scorer_view_canonical_sha256"],
            "programs_derived_from": "bound_stage1_v3_scorer_view",
            "effect_universe_sha256": _canon("FIXTURE-effect-universe")}


def _program_admission(staged: dict, progs: list) -> dict[str, Any]:
    """W5's NATIVE program_admission block: HOW the axis was derived."""
    return {"programs_derived_from": "bound_stage1_v3_scorer_view",
            "programs_copied_from_a_list": False,
            "program_count_is_derived": True,
            "registry_scorer_view_sha256":
                staged["release"]["registry_scorer_view_canonical_sha256"],
            "programs": sorted(progs),
            "n_programs": len(progs)}


def _inputs() -> dict[str, Any]:
    """A FIXED KEYED OBJECT. The role/value list it replaced is refused, not parsed."""
    return {
        "direct_method_version": "FIXTURE-direct-v1",
        "direct_config_sha256": _canon("FIXTURE-direct-config"),
        "effect_source_sha256": _canon("FIXTURE-effect-source"),
    }


def _ranking(program: str, dc: str, ctx: dict) -> dict[str, Any]:
    """A FIXTURE arm ranking in W5's NATIVE shape: ``records``, with RETAINED rows.

    ``UNRANKABLE_MEMBER`` is a member of FIXTURE-SET-1 that is retained with ``rank: null``
    — exactly what W5 emits for a target it could not evaluate. It must NOT count as a hit:
    counting rows instead of ranks would inflate every hit count by the targets the arm was
    least able to say anything about.
    """
    ranked = ([t for t in FIXTURE_SETS["FIXTURE-SET-1"] if t != UNRANKABLE_MEMBER]
              + FIXTURE_SETS["FIXTURE-SET-2"] + ["OTHER_1"])
    sign = 1.0 if dc == INCREASE else -1.0
    records = [{"target_id": t, "arm_value": sign * (len(ranked) - i),
                "evaluable": True, "rank": None}
               for i, t in enumerate(ranked)]
    # THE FROZEN RULE: value DESCENDING, ties broken on target_id ASCENDING. The verifier
    # re-derives exactly this, so a resealed rank-SWAP cannot hide behind matching counts.
    for i, r in enumerate(sorted(records,
                                 key=lambda r: (-r["arm_value"], r["target_id"]))):
        r["rank"] = i + 1
    # RETAINED, never dropped: present in the rows, absent from the ranking.
    records.append({"target_id": UNRANKABLE_MEMBER, "arm_value": None,
                    "evaluable": False, "rank": None})
    records.sort(key=lambda r: r["target_id"])
    return {
        "fixture": True,
        "context": ctx,
        "records": records,
        "n_targets": len(records),
        "n_ranked": sum(1 for r in records if r["rank"] is not None),
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


def build_bundle(root: str, lane: str, ctx: dict, staged: dict,
                 programs=None, arms_for=None) -> str:
    """Write ONE FIXTURE all-arm bundle and return its directory."""
    progs = list(staged["programs"] if programs is None else programs)

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

            # ONE base effect per program/context; the two desired changes are exact sign
            # transforms of it — two logical arms, not two experimental estimates.
            "base_effect_sha256": _canon(f"FIXTURE-base-{program}-{slug}"),
            "arm_values_sha256": _canon(f"FIXTURE-values-{program}-{dc}-{slug}"),
            "n_ranked": ranking["n_ranked"],
            # NO role, NO pole, NO pair-derived program id: a reusable arm is PAIR-AGNOSTIC.
            "ranking": _binding(out_dir, rel, ranking),
        }
        if lane == "pathway":
            ranked = {r["target_id"] for r in ranking["records"]
                      if r["rank"] is not None}
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
        "stage1_v3_release": {
            "release_canonical_sha256": staged["release_canonical_sha256"],
            "programs": sorted(progs),
            "conditions": list(staged["conditions"])},
        "arms": arms,
        "n_arms": len(arms),
        "arms_are_independent": True,
    }
    if lane == "pathway":
        inv["bindings"] = bindings
        inv["gene_sets"] = dict(gene_set_identity(ctx["gene_set_source"]),
                                gene_set_source=ctx["gene_set_source"])
        inv["convergence"] = {
            "convergence_id": convergence_id,
            "sha256": _raw(os.path.join(out_dir, "convergence.json"))}
    inv["bundle_id"] = f"FIXTURE-{_canon(inv)[:16]}"
    arm_raw, _ = _write(os.path.join(out_dir, "arm_bundle.json"), inv)

    prov_raw, _ = _write(os.path.join(out_dir, prov_name), {
        "fixture": True,
        "schema_version": f"FIXTURE.spot.stage02_{lane}_provenance.v1",
        "bundle_id": inv["bundle_id"],
        "lane": lane,
        "context": dict(ctx),
        # W5 native: HOW the program axis was derived, bound so it is checkable
        "program_admission": _program_admission(staged, progs),
        "run_binding": {
            # WHICH BUILD produced these bytes (recorded, never self-admitted)...
            "code_identity": _code_identity(),
            # ...and WHAT THE CODE DID, kept as a separate explicit role
            "temporal_method_sha256": _canon("FIXTURE-method"),
            "estimator_id": "FIXTURE.spot.stage02.arm.estimator.v1",
            "selection_release": _selection_release(staged),
            "stage2_inputs": _inputs(),
        },
    })
    # A TYPED admission from the pinned lane verifier, BINDING THE BUNDLE IT JUDGED.
    # A file that merely says {"verdict": "admit"} is not an independent admission.
    pin = LANE_VERIFIERS[lane]
    _write(os.path.join(out_dir, ver_name), {
        "fixture": True,
        "schema_version": pin["schema_version"],
        "verifier_id": pin["verifier_id"],
        "generator_is_not_verifier": True,
        "fail_closed": True,
        "bundle_id": inv["bundle_id"],
        "binds": {"arm_bundle_sha256": arm_raw, "provenance_sha256": prov_raw},
        "checks": [{"gate": g, "status": "pass"} for g in pin["required_gates"]],
        "n_failed": 0, "failed_gates": [], "verdict": "admit",
    })
    return out_dir


def complete_run(tmp_path, staged=None) -> dict[str, Any]:
    """A COMPLETE FIXTURE run against the REAL release: 15 bundles, 300 logical arms."""
    staged = staged or stage_release(tmp_path)
    root = os.path.join(str(tmp_path), "bundles")
    conds, sources = staged["conditions"], staged["sources"]

    direct = [build_bundle(root, "direct", {"condition": c}, staged) for c in conds]
    temporal = [build_bundle(root, "temporal",
                             {"from_condition": a, "to_condition": b}, staged)
                for a in conds for b in conds if a != b]
    pathway = [build_bundle(root, "pathway",
                            {"condition": c, "gene_set_source": s}, staged)
               for c in conds for s in sources]
    out = {"root": root, "staged": staged,
            "release_path": staged["release_path"],
            "release_root": staged["release_root"],
            "expect_release_sha256": staged["release_canonical_sha256"],
            "pinned_gene_sets": pinned_gene_sets(tmp_path, sources),
            "pinned_verifiers": pinned_verifiers(tmp_path),
            "expected_code_identity": expected_code_identity(tmp_path),
            "direct": direct, "temporal": temporal, "pathway": pathway,
            "conditions": list(conds), "sources": list(sources),
            "programs": list(staged["programs"])}
    write_inventory(out)
    write_external_admission(out)
    return out


# --------------------------------------------------------------------------- #
# THE ROOT ARTIFACTS. The producer's per-bundle report is a PREFLIGHT; these are what an
# admission actually rests on.
# --------------------------------------------------------------------------- #
INVENTORY_FILE = "temporal_arm_release.json"
ADMISSION_FILE = "temporal_arm_external_admission.json"
INDEPENDENT_VERIFIER_ID = "spot.stage02.temporal.arm.independent_verifier.v1"


def _bundle_entry(root: str, d: str) -> dict[str, Any]:
    rel_dir = os.path.relpath(d, root).replace(os.sep, "/")
    inv = json.load(open(os.path.join(d, "arm_bundle.json")))
    files, rankings = {}, {}
    for name in ("arm_bundle.json", "temporal_provenance.json",
                 "temporal_verification.json"):
        p = os.path.join(d, name)
        files[name] = {"raw_sha256": _raw(p),
                       "canonical_sha256": _canon(json.load(open(p)))}
    for arm in inv["arms"]:
        rel = arm["ranking"]["path"]
        p = os.path.join(d, rel)
        rankings[rel] = {"raw_sha256": _raw(p),
                         "canonical_sha256": _canon(json.load(open(p)))}
    return {"bundle_key": f"{inv['context']['from_condition']}->"
                          f"{inv['context']['to_condition']}",
            "bundle_id": inv["bundle_id"],
            "from_condition": inv["context"]["from_condition"],
            "to_condition": inv["context"]["to_condition"],
            "relative_dir": rel_dir, "files": files, "rankings": rankings}


def write_inventory(run: dict) -> str:
    """W5's IMMUTABLE, CONTENT-ADDRESSED six-bundle inventory. status is always PENDING."""
    root = run["root"]
    entries = [_bundle_entry(root, d) for d in run["temporal"]]
    doc = {
        "fixture": True,
        "schema_version": "spot.stage02_temporal_arm_release.v1",
        "release_id_rule": "sha256(canonical JSON excluding release_id)",
        "analysis_mode": "temporal_cross_condition",
        "stage1_binding": {"release_canonical_sha256":
                           run["staged"]["release_canonical_sha256"]},
        "n_bundles": len(entries),
        "n_logical_arms": sum(len(json.load(open(os.path.join(d, "arm_bundle.json")))
                                  ["arms"]) for d in run["temporal"]),
        "arm_keys": sorted(a["arm_key"] for d in run["temporal"]
                           for a in json.load(open(os.path.join(d, "arm_bundle.json")))
                           ["arms"]),
        "bundles": sorted(entries, key=lambda b: b["bundle_key"]),
        # 'pending' is the ONLY honest producer state: a producer cannot truthfully emit
        # the external verdict on itself.
        "external_admission": {
            "status": "pending",
            "required_verifier_id": INDEPENDENT_VERIFIER_ID,
            "required_report_schema_version":
                "spot.stage02_temporal_arm_verifier_report.v1",
        },
    }
    doc["release_id"] = _canon(doc)
    path = os.path.join(root, INVENTORY_FILE)
    _write(path, doc)
    return path


def write_external_admission(run: dict, release_id=None, verdict="ADMIT") -> str:
    """W11's SEPARATE envelope. The independent verifier alone emits this."""
    root = run["root"]
    inv_path = os.path.join(root, INVENTORY_FILE)
    inv = json.load(open(inv_path))
    doc = {
        "fixture": True,
        "schema_version": "spot.stage02_temporal_arm_external_admission.v1",
        "verifier_id": INDEPENDENT_VERIFIER_ID,
        "verdict": verdict,
        "binds": {
            "producer_release_id": release_id or inv["release_id"],
            "producer_release_raw_sha256": _raw(inv_path),
            "stage1_release_sha256": run["staged"]["release_canonical_sha256"],
        },
    }
    doc["report_id"] = _canon(doc)
    path = os.path.join(root, ADMISSION_FILE)
    _write(path, doc)
    return path


def seal_release(run: dict) -> dict:
    """Re-derive the inventory from the bytes on disk, then re-admit it. Used after a
    mutation, so an attack has to survive a FULLY consistent reseal."""
    write_inventory(run)
    write_external_admission(run)
    return run
