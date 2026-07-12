"""Temporal cross-condition orchestrator. GENERATES artifacts; it does not verify them.

It runs the UNCHANGED within-condition pass (``run_screen.condition_rows``) once per
released condition, then differences the resulting arm values across every ordered pair
of conditions. It emits, under ``<out_root>/<temporal_run_id>/``:

    temporal.parquet            one record per (target, ordered condition pair)
    endpoints.parquet           the within-condition screen rows, one per (target, cond)
    temporal_provenance.json    the estimator, the confound policy, the run binding
    temporal_verification.json  the independent verifier's report

WHAT IT MAY NOT DO
------------------
It may not touch the within-condition result. It writes its own artifact under its own
id, computes its own method hash, and imports the direct lane one-way. No score, no
rank, no tier and no ``run_id`` of the within-condition screen can move because this
ran — that is asserted, not asserted-ish, by the invariance test.
"""
from __future__ import annotations

import datetime as _dt
import os
from typing import Any, Optional

from .. import emit, gate, runid
from .. import run_screen as rs
from ..hashing import canonical_json, content_hash, sha256_hex
from . import config, policy, records

_HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PROVENANCE = "spot.stage02_temporal_provenance.v1"
SCHEMA_ENDPOINTS = "spot.stage02_temporal_endpoints.v1"
TEMPORAL_RUN_ID_LEN = 16


def method_block(pol: policy.BatchPolicy) -> dict[str, Any]:
    """The temporal method, as one hashable object.

    It binds the WITHIN-CONDITION method too: an endpoint is a within-condition arm
    value, so a change to the direct method changes what this estimator differenced, and
    a temporal run that could keep its identity across such a change would be naming a
    number it no longer produces.
    """
    return {
        "estimator_id": config.ESTIMATOR_ID,
        "estimator_version": config.ESTIMATOR_VERSION,
        "temporal_policy": config.TEMPORAL_POLICY,
        "batch_policy": pol.block(),
        "within_condition_method": runid.method_block(),
        "within_condition_eligibility_policy": runid.config_sha256(),
        # both trees execute in a temporal run, so both are bound
        "direct_code_tree_sha256": runid.code_tree_sha256(
            os.path.dirname(os.path.abspath(rs.__file__))),
        "temporal_code_tree_sha256": runid.code_tree_sha256(_HERE),
    }


def temporal_method_sha256(pol: policy.BatchPolicy) -> str:
    return content_hash(method_block(pol))


def _rows_by_target(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(r["target_id"]): r for r in rows}


_COMPARISON_FIELDS = ("batch_status", "batch_partially_confounded",
                      "batch_status_reason", "donors_changing_replicate",
                      "donors_keeping_replicate", "refused")


def _comparison_block(from_cond: str, to_cond: str,
                      pol: policy.BatchPolicy) -> dict[str, Any]:
    """What this comparison IS, and what the confound policy says about it."""
    verdict = pol.classify_pair(from_cond, to_cond)
    return {"comparison_id": records.comparison_id(from_cond, to_cond),
            "from_condition": from_cond, "to_condition": to_cond,
            **{k: verdict[k] for k in _COMPARISON_FIELDS}}


def build_temporal(args, conditions: Optional[list[str]] = None) -> dict[str, Any]:
    """Compute every ordered cross-condition comparison the release can support."""
    created_at = _dt.datetime.now(_dt.timezone.utc).isoformat()
    pol = policy.load(getattr(args, "batch_policy", None))

    # THE SAME binding and THE SAME release gate the within-condition build runs. A
    # temporal run that could stand on inputs the screen would have refused would be a
    # back door around the gate.
    ctx = rs.prepare(args)
    from .. import preflight
    verdict = preflight.assess(args, ctx)
    if verdict["verdict"] != preflight.GO:
        detail = "; ".join(f"[{f['check']}] {f['error']}" for f in verdict["failures"])
        raise gate.GateError(
            "release gate refused this temporal run; no artifact was written. "
            f"{detail}", report=verdict)

    manifest = rs.stage2_input_manifest(args)
    identity_hashes = rs.identity_hashes_of(manifest)

    # ---- the endpoints: the UNCHANGED within-condition pass, once per condition ----
    released = sorted(ctx["identities_by_condition"])
    conds = sorted(conditions) if conditions else released
    unknown = [c for c in conds if c not in released]
    if unknown:
        raise ValueError(
            f"the release ships no pooled-main estimate for {unknown}; "
            f"released conditions are {released}")

    by_condition: dict[str, dict[str, dict[str, Any]]] = {}
    endpoint_rows: list[dict[str, Any]] = []
    for cond in conds:
        built = rs.condition_rows(ctx=ctx, args=args, cond=cond,
                                  identity_hashes=identity_hashes)
        by_condition[cond] = _rows_by_target(built["screen"])
        endpoint_rows += built["screen"]

    # ---- the comparisons: EVERY ordered pair, both directions, none refused ----
    programs = {"A": ctx["axis"]["A"]["program_id"],
                "B": ctx["axis"]["B"]["program_id"]}
    pairs = pol.ordered_pairs(conds)
    temporal_rows: list[dict[str, Any]] = []
    for from_cond, to_cond in pairs:
        batch = pol.classify_pair(from_cond, to_cond)
        # the union: a target the release ships at only ONE endpoint still gets a
        # record, with the absent endpoint named as absent rather than omitted
        targets = sorted(set(by_condition[from_cond]) | set(by_condition[to_cond]))
        for target in targets:
            temporal_rows.append(records.temporal_record(
                target_id=target, from_condition=from_cond, to_condition=to_cond,
                from_row=by_condition[from_cond].get(target),
                to_row=by_condition[to_cond].get(target),
                programs=programs, batch=batch, pol=pol,
                identity_hashes=identity_hashes))

    # ---- identity: the inputs, the policy and BOTH code trees are bound ----
    method_sha = temporal_method_sha256(pol)
    binding = {
        "temporal_method": method_block(pol),
        "temporal_method_sha256": method_sha,
        "conditions": conds,
        "comparisons": [records.comparison_id(a, b) for a, b in pairs],
        "selection": {
            "selection_id": ctx["selection"].selection_id,
            "question_id": ctx["selection"].question_id,
            "selection_contract_sha256": ctx["selection"].contract_sha256,
            "analysis_condition": ctx["selection"].analysis_condition,
        },
        "programs": programs,
        "lane": ctx["lane"],
        "stage2_inputs": sorted(
            [{"name": i["name"], "sha256": i["sha256"], "size_bytes": i["size_bytes"]}
             for i in manifest], key=lambda i: i["name"]),
        "gene_universe_sha256": ctx["gene_universe"]["sha256"],
        "evidence_domain": rs._domain_block(ctx),
        "support_contract": ctx["support_contract"],
        "release_gate": verdict["release_gate"],
        "environment_lock": runid.env_lock_block(args.env_lock),
    }
    full = sha256_hex(canonical_json(binding))
    temporal_run_id = full[:TEMPORAL_RUN_ID_LEN]

    for r in temporal_rows:
        r["temporal_run_id"] = temporal_run_id
        r["temporal_method_sha256"] = method_sha
    for r in endpoint_rows:
        r["run_id"] = None                 # this is NOT a within-condition release run
        r["temporal_run_id"] = temporal_run_id

    out_dir = os.path.join(args.out_root, temporal_run_id)
    os.makedirs(out_dir, exist_ok=True)
    ordered = records.emit_order(temporal_rows)
    emit.write_parquet(ordered, os.path.join(out_dir, "temporal.parquet"),
                       ["comparison_id", "target_id"],
                       nullable_int_columns=("A_from_rank", "A_to_rank",
                                             "B_from_rank", "B_to_rank",
                                             "from_pareto_tier", "to_pareto_tier"))
    emit.write_parquet(endpoint_rows, os.path.join(out_dir, "endpoints.parquet"),
                       ["condition", "target_id"],
                       nullable_int_columns=("rank_away_from_A", "rank_toward_B",
                                             "pareto_tier"))

    prov = {
        "schema_version": SCHEMA_PROVENANCE,
        "temporal_run_id": temporal_run_id,
        "temporal_run_sha256": full,
        "temporal_method_sha256": method_sha,
        "created_at": created_at,
        "estimator": {
            "estimator_id": config.ESTIMATOR_ID,
            "estimator_version": config.ESTIMATOR_VERSION,
            "formula_id": config.FORMULA_ID,
            "formula_expr": config.FORMULA_EXPR,
            "estimand_id": config.ESTIMAND_ID,
            "estimand_level": config.ESTIMAND_LEVEL,
            "estimand_is_per_cell_fate": config.ESTIMAND_IS_PER_CELL_FATE,
            "estimand_is_lineage_traced": config.ESTIMAND_IS_LINEAGE_TRACED,
            "not_a_fate_claim_rule_id": config.NOT_A_FATE_CLAIM_RULE_ID,
            "inference_status": config.INFERENCE_STATUS,
            "no_pq_reason": config.NO_PQ_REASON,
        },
        "temporal_policy": config.TEMPORAL_POLICY,
        "batch_policy": pol.block(),
        "run_binding": binding,
        "conditions": conds,
        "comparisons": [_comparison_block(a, b, pol) for a, b in pairs],
        "n_records": len(ordered),
        "n_endpoint_rows": len(endpoint_rows),
        "files": manifest,
    }
    emit.write_json(os.path.join(out_dir, "temporal_provenance.json"), prov)

    from . import verify_temporal
    verification = verify_temporal.verify(out_dir=out_dir, provenance=prov)
    emit.write_json(os.path.join(out_dir, "temporal_verification.json"), verification)

    return {
        "temporal_run_id": temporal_run_id,
        "temporal_run_sha256": full,
        "temporal_method_sha256": method_sha,
        "out_dir": out_dir,
        "conditions": conds,
        "n_comparisons": len(pairs),
        "n_records": len(ordered),
        "n_endpoint_rows": len(endpoint_rows),
        "verification": verification,
    }
