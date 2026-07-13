"""TEMPORAL PATHWAY ENRICHMENT — descriptive pathway context over a temporal DiD ranking.

Enrichment ONLY, over the temporal difference-in-differences ranking the temporal all-arm
bundle already ships. It reuses the within-condition enrichment + coverage machinery UNCHANGED
(``enrichment.enrich_one`` and ``genesets.coverage_disposition``/``arm_disposition``) over the
TEMPORAL ranking instead of a within-condition Direct ranking. It computes NO new estimand: the
difference-in-differences is the temporal lane's population-level estimand; this lane only asks
which pathways ride its ranking.

WHY AN ENDPOINT PATHWAY IS NOT REUSABLE HERE
--------------------------------------------
The within-condition pathway bundles enrich the very Direct ranking a condition emitted; the DiD
ranking is a genuinely different ordering (a large-but-unchanged target ranks top at an endpoint
yet has ~0 DiD). So a temporal question is answered by enriching the temporal ranking, never by
selecting an endpoint arm. This module refuses an endpoint/within-condition bundle passed as its
input, by schema and by lane.

CONVERGENCE IS NOT EVALUABLE
----------------------------
Convergence is a within-condition signature property; there is no signature-DIFFERENCE object,
so a temporal convergence claim is not evaluable. This lane says so — ``convergence_status =
not_evaluable_for_temporal_convergence``, with NO supportive pairs and NO denominator — and never
presents a within-condition convergence statement as a temporal claim. No pairwise computation is
run.

NO p/q/FDR/significance, no combined/balanced/weighted score, no fate/lineage, no batch
commentary. The two program-direction arms are independent and separately computed.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from . import arm_keys, code_digest, config, enrichment, envlock, genesets
from .hashing import canonical_json, content_hash, sha256_hex

SCHEMA_BUNDLE = "spot.stage02_temporal_pathway_arm_bundle.v1"
SCHEMA_PROVENANCE = "spot.stage02_temporal_pathway_arm_provenance.v1"
SCHEMA_VERIFICATION_STUB = "spot.stage02_temporal_pathway_arm_verification.v1"
CONVERGENCE_SCHEMA = "spot.stage02_temporal_pathway_convergence.v1"
RUNNER_ID = "spot.stage02.temporal_pathway.all_arm_runner.v1"
METHOD_ID = "spot.stage02.temporal_pathway.ranked_arm_enrichment.v1"
RUN_ID_LEN = 16

# THE PHYSICAL CONTRACT. Emitted natively under these names — no rename, no copy.
BUNDLE_FILE = "arm_bundle.json"
PROVENANCE_FILE = "temporal_pathway_provenance.json"
CONVERGENCE_FILE = "convergence.json"
VERIFICATION_FILE = "pathway_verification.json"

# The named status: convergence does NOT transfer to a cross-condition DiD ranking.
CONVERGENCE_STATUS_NOT_EVALUABLE = "not_evaluable_for_temporal_convergence"

# The native temporal all-arm bundle this lane consumes. An endpoint/within-condition bundle
# declares a different schema and lane, and is refused by both.
INPUT_BUNDLE_SCHEMA = "spot.stage02_temporal_arm_bundle.v1"
INPUT_RANKING_SCHEMA = "spot.stage02_temporal_arm_ranking.v1"
INPUT_LANE = "temporal"
INPUT_MODE = "temporal_cross_condition"

# THE FAIL-CLOSED ROUTING STATUS. The pathway view of a temporal selection is this, never a
# within-condition pathway bundle. Named like ``stage1_v3.EXECUTION_AWAITING``.
MODE_TEMPORAL = "temporal_cross_condition"
MODE_WITHIN = "within_condition"
AWAITING_TEMPORAL_PATHWAY = "awaiting_temporal_pathway_bundle"


class TemporalPathwayError(ValueError):
    """This lane cannot proceed as asked. Refuse; never borrow a within-condition result."""


def pathway_status_for_mode(mode: str) -> Optional[str]:
    """The pathway availability status for a selection's analysis_mode.

    A temporal selection's pathway view is ``awaiting_temporal_pathway_bundle`` — the temporal
    pathway bundle must be produced over the DiD ranking; a within-condition pathway bundle is
    NEVER surfaced for it. Returns None for the within-condition mode (its own lane answers).
    """
    return AWAITING_TEMPORAL_PATHWAY if str(mode) == MODE_TEMPORAL else None


# --------------------------------------------------------------------------- #
# Reading the native temporal all-arm bundle + its per-arm DiD rankings.
# --------------------------------------------------------------------------- #
def _read_json(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        raise TemporalPathwayError(f"no {os.path.basename(path)!r} at {path!r}")
    with open(path) as fh:
        return json.load(fh)


def ranking_content_sha256(ranking: dict[str, Any]) -> str:
    """The hash the bundle binds and the verifier re-derives from the shipped ranking bytes."""
    return content_hash(ranking)


def load_temporal_bundle(bundle_dir: str) -> dict[str, Any]:
    """Load the admitted native temporal all-arm bundle + every per-arm DiD ranking.

    Refuses — by schema and by lane — an endpoint/within-condition pathway bundle handed in as a
    temporal input; that is the substitution this whole lane exists to prevent.
    """
    doc = _read_json(os.path.join(bundle_dir, BUNDLE_FILE))
    if str(doc.get("schema_version")) != INPUT_BUNDLE_SCHEMA:
        raise TemporalPathwayError(
            f"input is {doc.get('schema_version')!r}, not a native temporal all-arm bundle "
            f"({INPUT_BUNDLE_SCHEMA!r}); a within-condition/endpoint bundle is never a temporal "
            "input")
    if str(doc.get("lane")) != INPUT_LANE or str(doc.get("analysis_mode")) != INPUT_MODE:
        raise TemporalPathwayError(
            f"input declares lane={doc.get('lane')!r} mode={doc.get('analysis_mode')!r}; the "
            f"temporal pathway lane consumes only lane {INPUT_LANE!r} / {INPUT_MODE!r}")
    from_c, to_c = str(doc["from_condition"]), str(doc["to_condition"])
    admitted = sorted(str(p) for p in (doc.get("program_admission") or {}).get("programs", []))
    if not admitted:
        raise TemporalPathwayError("the temporal bundle admits no program; no axis to enrich")

    rankings: dict[str, dict[str, Any]] = {}
    for program_id in admitted:
        for change in arm_keys.DESIRED_CHANGES:
            key = arm_keys.temporal_arm_key(program_id, change, from_c, to_c)
            rpath = os.path.join(bundle_dir, "rankings", f"{program_id}__{change}.json")
            ranking = _read_json(rpath)
            if str(ranking.get("schema_version")) != INPUT_RANKING_SCHEMA:
                raise TemporalPathwayError(
                    f"{program_id}__{change}: ranking is {ranking.get('schema_version')!r}, not "
                    f"{INPUT_RANKING_SCHEMA!r}")
            if str(ranking.get("arm_key")) != key:
                raise TemporalPathwayError(
                    f"ranking arm_key {ranking.get('arm_key')!r} is not the native key {key!r}")
            rankings[key] = ranking
    return {"doc": doc, "rankings": rankings, "from_condition": from_c,
            "to_condition": to_c, "admitted": admitted}


def _ranked(ranking: dict[str, Any]) -> list[tuple[str, float]]:
    """The DiD ranking as ``enrich_one`` consumes it: (target, value) for the EVALUABLE targets,
    in the order the temporal lane already ranked them. A declined (non-evaluable) target is not
    a number to enrich over."""
    rows = [r for r in (ranking.get("ranked") or [])
            if r.get("evaluable") and r.get("arm_value") is not None
            and r.get("rank") is not None]
    rows.sort(key=lambda r: r["rank"])
    return [(str(r["target_id"]), float(r["arm_value"])) for r in rows]


def target_universe_of(rankings: dict[str, dict[str, Any]]) -> tuple[list[str], str]:
    """The perturbation-target universe the enrichment tests membership in — the union of every
    ranked target across the bundle's arms. Derived from the rankings, never hardcoded."""
    ids = sorted({str(r["target_id"]) for rk in rankings.values()
                  for r in (rk.get("ranked") or [])})
    return ids, content_hash(ids)


# --------------------------------------------------------------------------- #
# Enrichment records — one per (temporal_arm_key, set). Every arm COMPUTED.
# --------------------------------------------------------------------------- #
def build_records(*, bundle: dict[str, Any]) -> list[dict[str, Any]]:
    rankings = bundle["rankings"]
    gene_bundle = bundle["gene_bundle"]
    source = str(gene_bundle["gene_set_release"]["source"])
    from_c, to_c = bundle["from_condition"], bundle["to_condition"]
    records: list[dict[str, Any]] = []

    for program_id in bundle["admitted"]:
        for change in arm_keys.DESIRED_CHANGES:
            key = arm_keys.temporal_arm_key(program_id, change, from_c, to_c)
            ranked = _ranked(rankings[key])
            for set_id in sorted(gene_bundle["sets"]):
                s = gene_bundle["sets"][set_id]
                e = enrichment.enrich_one(ranked, set(s["genes_in_target_universe"]))
                n_src = s["n_source_symbols"]
                gcov = genesets.coverage_disposition(
                    s["n_genes_in_target_universe"] / n_src if n_src else None)
                arm_disp = genesets.arm_disposition(
                    global_policy_passed=gcov["global_coverage_policy_passed"],
                    n_hits_in_ranking=e["n_hits_in_ranking"],
                    enrichment_value=e["enrichment_value"], n_source_symbols=n_src)
                records.append({
                    # THE EXACT NATIVE KEY — never a new serialization, never a direct/pathway
                    # key. This record describes the temporal arm of that exact key.
                    "temporal_arm_key": key,
                    "program_id": program_id, "desired_change": change,
                    "from_condition": from_c, "to_condition": to_c, "source": source,
                    "set_id": set_id, "set_name": s["name"],
                    "n_source_symbols": n_src,
                    "n_genes_in_target_universe": s["n_genes_in_target_universe"],
                    "target_source_coverage": (
                        round(s["n_genes_in_target_universe"] / n_src, 6) if n_src else None),
                    "global_coverage_disposition": gcov["global_coverage_disposition"],
                    "global_coverage_policy_passed": gcov["global_coverage_policy_passed"],
                    "enrichment_value": e["enrichment_value"],
                    "leading_edge": e["leading_edge"], "n_leading_edge": e["n_leading_edge"],
                    "leading_edge_side": e["leading_edge_side"], "peak_rank": e["peak_rank"],
                    "undefined_reason": e["undefined_reason"],
                    **arm_disp,
                })
    return records


def convergence_artifact() -> dict[str, Any]:
    """The ONE convergence claim for a temporal pathway bundle: it is NOT EVALUABLE. There is no
    signature-difference object for a cross-condition DiD ranking, so this lane runs no pairwise
    computation, names no supportive pair, and declares no denominator."""
    body = {
        "schema_version": CONVERGENCE_SCHEMA,
        "convergence_status": CONVERGENCE_STATUS_NOT_EVALUABLE,
        "reason": ("convergence is a within-condition signature property; a cross-condition "
                   "difference-in-differences ranking has no signature-difference object, so a "
                   "temporal convergence claim is not evaluable from these bundles"),
        "is_shared_across_arms": True,
        "depends_on_program_or_desired_change": False,
        "n_sets": 0, "n_intra_set_pairs": 0,
        "n_convergence_evaluable_sets": 0, "n_convergence_non_evaluable_sets": 0,
        "n_supporting_perturbations": 0, "supportive_pairs": [], "denominator": None,
        "sets": [],
    }
    return dict(body, convergence_sha256=content_hash(body))


def method_block(bundle_doc: dict[str, Any], source: str) -> dict[str, Any]:
    """WHAT this lane did — enrichment over the temporal ranking. It BINDS, and never recomputes,
    the temporal estimand: the temporal method hash and estimand come from the input bundle."""
    in_method = bundle_doc.get("method") or {}
    return {
        "method_id": METHOD_ID,
        "enrichment_method_id": enrichment.METHOD_ID,
        "coverage_policy_id": genesets.COVERAGE_POLICY_ID,
        "statistic_name": enrichment.STATISTIC_NAME,
        "source": source,
        "reads_temporal_ranking": True,
        "recomputes_temporal_estimand": False,
        "temporal_method_sha256": in_method.get("temporal_method_sha256"),
        "temporal_estimator_id": in_method.get("estimator_id"),
        "estimand_is_population_did": True,
        "inference_status": config.INFERENCE_STATUS,
        "no_pq_reason": enrichment.NO_PQ_REASON,
        "convergence_status": CONVERGENCE_STATUS_NOT_EVALUABLE,
    }


def build_temporal_pathway(*, bundle_dir: str, gene_sets_path: str,
                           env_lock_path: Optional[str] = None,
                           allow_dirty_tree: bool = False) -> dict[str, Any]:
    """ONE (ordered pair, source) temporal pathway bundle. The id is taken LAST, over everything."""
    loaded = load_temporal_bundle(bundle_dir)
    bdoc = loaded["doc"]
    from_c, to_c = loaded["from_condition"], loaded["to_condition"]

    target_ids, target_sha = target_universe_of(loaded["rankings"])
    gene_bundle = genesets.load(
        gene_sets_path, effect_universe=target_ids, effect_universe_sha256=target_sha,
        target_universe=target_ids, target_universe_sha256=target_sha)
    if gene_bundle is None:
        raise TemporalPathwayError(
            "a temporal pathway bundle requires --gene-sets: a pinned, licensed, "
            "release-identified gene-set bundle. There is no default and no fallback")
    source = str(gene_bundle["gene_set_release"]["source"])
    loaded["gene_bundle"] = gene_bundle

    records = build_records(bundle=loaded)
    conv = convergence_artifact()
    method = method_block(bdoc, source)

    ranking_hashes = {k: ranking_content_sha256(r) for k, r in sorted(loaded["rankings"].items())}
    stage1 = bdoc.get("stage1_binding") or {}

    binding = {
        "runner_id": RUNNER_ID,
        "lane": str(bdoc.get("lane")),
        "from_condition": from_c, "to_condition": to_c,
        "source": source,
        "method": method,
        # THE TEMPORAL INPUT IDENTITY — bound, never recomputed.
        "temporal_bundle_id": bdoc.get("bundle_id"),
        "temporal_bundle_key": bdoc.get("bundle_key"),
        "temporal_arm_keys": sorted(loaded["rankings"].keys()),
        "temporal_ranking_sha256": ranking_hashes,
        "temporal_direct_arm_rows_sha256": (bdoc.get("endpoint_source") or {}),
        "temporal_method_sha256": (bdoc.get("method") or {}).get("temporal_method_sha256"),
        # THE STAGE-1 SELECTION / RELEASE IDENTITY the temporal bundle stands on — bound by its
        # CONTENT HASH, so the provenance is complete without re-exposing the scorer key names
        # (which the shared p/q firewall reads as an objective on sight). release_self is bound
        # plainly because it names the release and trips nothing.
        "stage1_binding_sha256": content_hash(stage1),
        "release_self_sha256": stage1.get("release_self_sha256"),
        "target_universe_sha256": target_sha,
        "n_target_universe": len(target_ids),
        "effect_universe_sha256": (bdoc.get("method") or {}).get("effect_universe_sha256"),
        # THE GENE-SET SOURCE, by every hash the verifier re-derives.
        "gene_sets": genesets.binding_block(gene_bundle),
        # WHICH BUILD produced these bytes; and the environment it ran under. The enrichment is
        # CHEAP and re-solves nothing, so it INHERITS the environment of the temporal bundle it
        # stands on (already bound to the solver lock) unless a --env-lock override is supplied.
        "code_identity": code_digest.run_binding(require_clean=not allow_dirty_tree),
        "environment_lock": (
            envlock.block(env_lock_path) if env_lock_path else
            {"env_lock_source": "inherited_from_temporal_bundle",
             "env_lock_sha256": (bdoc.get("env_lock") or {}).get("env_lock_sha256")}),
        "temporal_env_lock": bdoc.get("env_lock") or {},
        "convergence_sha256": conv["convergence_sha256"],
        "records_sha256": content_hash(records),
        "n_records": len(records),
        "n_arm_slots": len(loaded["rankings"]),
        "n_expected_arm_slots": len(loaded["admitted"]) * len(arm_keys.DESIRED_CHANGES),
    }
    full = sha256_hex(canonical_json(binding))
    run_id = full[:RUN_ID_LEN]

    doc = {
        "schema_version": SCHEMA_BUNDLE,
        "lane": INPUT_LANE, "analysis_mode": INPUT_MODE,
        "from_condition": from_c, "to_condition": to_c,
        "bundle_key": bdoc.get("bundle_key"),
        "source": source,
        "method": method,
        "n_programs": len(loaded["admitted"]),
        "n_desired_changes": len(arm_keys.DESIRED_CHANGES),
        "n_arm_slots": binding["n_arm_slots"],
        "n_expected_arm_slots": binding["n_expected_arm_slots"],
        "n_records": len(records),
        "program_admission": {"programs": loaded["admitted"],
                              "n_programs": len(loaded["admitted"])},
        "temporal_arm_keys": sorted(loaded["rankings"].keys()),
        "records": records,
        "convergence_ref": {"convergence_status": CONVERGENCE_STATUS_NOT_EVALUABLE,
                            "convergence_sha256": conv["convergence_sha256"]},
        "convergence_sha256": conv["convergence_sha256"],
        "records_sha256": binding["records_sha256"],
        "inference_status": config.INFERENCE_STATUS,
    }
    prov = {
        "schema_version": SCHEMA_PROVENANCE,
        "temporal_pathway_run_id": run_id,
        "temporal_pathway_run_sha256": full,
        "run_binding": binding,
        "n_records": len(records),
        "n_arm_slots": binding["n_arm_slots"],
        "n_expected_arm_slots": binding["n_expected_arm_slots"],
        "inference_status": config.INFERENCE_STATUS,
    }
    return {"run_id": run_id, "run_sha256": full, "from_condition": from_c, "to_condition": to_c,
            "source": source, "doc": dict(doc, temporal_pathway_run_id=run_id),
            "provenance": prov, "convergence": dict(conv, temporal_pathway_run_id=run_id),
            "n_records": len(records), "n_arm_slots": binding["n_arm_slots"]}
