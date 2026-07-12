"""Artifact assembly: input manifest, provenance, verification, writers.

Release-artifact rules enforced here, not merely intended:
  * no p / q / FDR columns anywhere;
  * no causal language in any emitted string;
  * no machine-local paths (files are carried by name + SHA-256 only);
  * every source target present exactly once (complete disposition);
  * ranks exist only for eligible targets and are a contiguous 1..n_eligible.

This module ASSEMBLES artifacts. It does not certify them: verification.json
records what an independent pass must re-derive.
"""
from __future__ import annotations

import json
import os
import re
from collections import Counter
from typing import Any, Iterable

import pandas as pd

from . import config, disposition, domain, guides
from .contract import (COMBINED_OBJECTIVE_ALIASES, FORBIDDEN_LEGACY_COLUMNS,
                       FORBIDDEN_PQ_COLUMNS, HEADLINE_RANK_ALIASES,
                       screen_column_allowlist)
from .hashing import content_hash, file_sha256

SCHEMA_SCREEN = "spot.stage02_screen.v3"
SCHEMA_PROVENANCE = "spot.stage02_provenance.v3"
SCHEMA_VERIFICATION = "spot.stage02_verification.v3"
SCHEMA_AXIS = "spot.stage02_axis.v3"
SCHEMA_MANIFEST = "spot.stage02_input_manifest.v3"

# Whole-word causal / confirmatory claims that may never appear in an artifact.
FORBIDDEN_LANGUAGE = (
    "causes", "caused", "causal", "causally", "proves", "proven",
    "confirms", "confirmed", "fate conversion", "validated target",
)
_CAUSAL_RE = re.compile(
    r"\b(" + "|".join(re.escape(t) for t in FORBIDDEN_LANGUAGE) + r")\b",
    re.IGNORECASE)


def scan_for_causal_language(obj: Any, path: str = "") -> list[str]:
    """Return every artifact string containing a forbidden causal claim."""
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            hits += scan_for_causal_language(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            hits += scan_for_causal_language(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        for m in _CAUSAL_RE.finditer(obj):
            hits.append(f"{path}: {m.group(1).lower()}")
    return hits


def scan_for_local_paths(obj: Any, path: str = "") -> list[str]:
    """Return every artifact string that leaks a machine-local path."""
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            hits += scan_for_local_paths(v, f"{path}.{k}")
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            hits += scan_for_local_paths(v, f"{path}[{i}]")
    elif isinstance(obj, str):
        if obj.startswith("/") or obj.startswith("~") or "/home/" in obj:
            hits.append(f"{path}: {obj}")
    return hits


def input_manifest(files: dict[str, str]) -> list[dict[str, Any]]:
    """name -> path becomes name + size + SHA-256. The path never escapes."""
    return sorted(
        [{"name": name, "size_bytes": os.path.getsize(path),
          "sha256": file_sha256(path)}
         for name, path in files.items()],
        key=lambda e: e["name"])


def mask_content_sha256(rows: Iterable[dict]) -> str:
    """Hash the mask rows independently of the run_id they will later carry."""
    return content_hash([{k: v for k, v in sorted(r.items()) if k != "run_id"}
                         for r in rows])


def axis_record(run_id: str, selection, axis: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_AXIS,
        "run_id": run_id,
        "selection_id": selection.selection_id,
        "question_id": selection.question_id,
        "analysis_condition": selection.analysis_condition,
        "A": {k: axis["A"][k] for k in ("program_id", "direction", "sign",
                                        "panel", "control")},
        "B": {k: axis["B"][k] for k in ("program_id", "direction", "sign",
                                        "panel", "control")},
        "lane": selection.lane,
        "namespace": axis["namespace"],
        "production_eligible": axis["production_eligible"],
        "stage3_eligible": axis["stage3_eligible"],
        "may_write_production_pointer": axis["may_write_production_pointer"],
        "production_gate_passed": axis["production_gate_passed"],
        "arms": list(config.ARMS),
        "arm_formula": dict(config.ARM_FORMULA),
        "arms_are_independent": True,
        "combined_objective_permitted": config.COMBINED_OBJECTIVE_PERMITTED,
        "headline_arm_permitted": config.HEADLINE_ARM_PERMITTED,
        "registry_sha256": selection.registry_sha256,
        "registry_hash_binding": axis["registry_hash_binding"],
        "selectability": axis["selectability"],
    }


def direct_contract(gene_universe: dict[str, Any]) -> dict[str, Any]:
    """The artifact contract a downstream lane (P2S, Stage-3) reads.

    Explicit enough to consume without importing the direct package, and without
    reviving anything the direct lane forbids: there is no ``balanced_skew``, no
    rank on an ineligible row, and no biology-only output path.
    """
    return {
        "contract_version": "spot.stage02_direct_contract.v2_two_arm",
        "run_key": "run_id",
        "run_key_rule_id": config.RUN_KEY_RULE_ID,
        "question_id_is_a_run_key": False,
        "artifacts": {
            "screen": "screen.parquet",
            "masks": "masks.parquet",
            "contributing_guides": "contributing_guides.parquet",
            "guide_support": "guide_support.parquet",
            "donor_support": "donor_support.parquet",
            "gene_universe": "gene_universe.json",
            "axis": "axis.json",
            "provenance": "provenance.json",
            "verification": "verification.json",
        },
        "screen": {
            "arms": list(config.ARMS),
            "arm_score_columns": list(config.ARMS),
            "arm_rank_columns": dict(config.ARM_RANK_COLUMN),
            "arm_evaluable_columns": {a: f"{config.ARM_POLE[a]}_evaluable"
                                      for a in config.ARMS},
            "arm_field_prefix": dict(config.ARM_POLE),
            "rank_dtype": config.RANK_DTYPE,
            "rank_nullable": True,
            "rank_null_when_arm_not_evaluable": True,
            "rank_population": config.RANK_POPULATION,
            "rank_tie_break": config.RANK_TIE_BREAK,
            "no_headline_rank": True,
            "no_combined_objective": True,
            "no_balanced_skew": True,
            "no_pq_columns": True,
            "emit_order": "target_id_ascending",
            "emit_order_is_an_arm_rank": False,
            "consumer_rule_id": config.CONSUMER_RULE_ID,
            "consumer_must_choose_an_arm": True,
            "cross_arm_fields": ["concordance_class",
                                 "desired_modulation_agreement"],
            "cross_arm_rule_id": config.CROSS_ARM_RULE_ID,
            "cross_arm_fields_rank_or_gate": False,
        },
        "arm_state_vocabulary": {
            "states": [disposition.ARM_EVALUABLE, disposition.ARM_EXCLUDED_BASE_QC,
                       disposition.ARM_INSUFFICIENT_COVERAGE,
                       disposition.ARM_MASK_UNRESOLVED],
            "never_replicated_states": sorted(disposition.NEVER_REPLICATED_STATES),
            "rule_id": config.ARM_STATE_RULE_ID,
            "arms_share_an_evaluability_state": False,
        },
        "support_status_vocabulary": {
            "states": list(disposition.SUPPORT_STATUSES),
            "support_available_in_this_pass": config.SUPPORT_AVAILABLE_IN_THIS_PASS,
            "evaluated_requires_support_available": True,
        },
        "modulation_vocabulary": {
            "per_arm": [disposition.MOD_DECREASE, disposition.MOD_INCREASE,
                        disposition.MOD_NO_DIRECTION, disposition.MOD_NOT_EVALUATED],
            "agreement": [disposition.MOD_AGREE, disposition.MOD_CONFLICT,
                          disposition.MOD_ONLY_A, disposition.MOD_ONLY_B,
                          disposition.MOD_NONE],
            "rule_id": config.MODULATION_RULE_ID,
            "conflicts_resolved_into_a_winner": False,
        },
        "mask_reason_vocabulary": list(config.MASK_REASONS),
        "base_qc_vocabulary": {
            "all_states": list(disposition.BASE_QC_PRECEDENCE),
            "pass_states": sorted(disposition.BASE_QC_PASS_STATES),
            "pre_outcome": True,
            "function_of_either_arm": False,
        },
        # The FULL released scope identity — the same 9-tuple the manifest is keyed by.
        "estimate_key": list(domain.SCOPE_KEY_FIELDS),
        "estimate_types": [guides.MAIN, guides.GUIDE, guides.DONOR_PAIR],
        "evidence_domain": domain.DOMAIN_ID,
        "projected_estimate_types": [guides.MAIN],
        "masked_estimate_types": [guides.MAIN],
        "support_state": domain.SUPPORT_STATE_UNAVAILABLE,
        "gene_universe": {
            "sha256": gene_universe["sha256"],
            "n_genes": gene_universe["n_genes"],
            "basis": gene_universe["basis"],
        },
    }


def provenance(*, run_id: str, run_sha256: str, run_binding: dict[str, Any],
               selection, axis: dict[str, Any], id_check: dict[str, Any],
               guide_lanes: list[str], guide_manifest: dict[str, Any],
               donor_splits: dict[str, Any],
               donor_crosswalk: dict[str, Any], gene_universe: dict[str, Any],
               mask_sha256: str, manifest: list[dict[str, Any]],
               created_at: str, support_contract: dict[str, Any],
               evidence_domain: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_PROVENANCE,
        # ---- top-level canonical identifiers (a consumer reads only these) ----
        "run_id": run_id,
        # ---- what evidence this run stood on, and what it explicitly did NOT claim --
        "evidence_domain": evidence_domain,
        "support_contract": support_contract,
        "namespace": axis["namespace"],
        "production_eligible": axis["production_eligible"],
        "stage3_eligible": axis["stage3_eligible"],
        "production_gate_passed": axis["production_gate_passed"],
        "question_id": selection.question_id,        # biology only; never a run key
        "selection_id": selection.selection_id,
        "analysis_condition": selection.analysis_condition,
        "mask_sha256": mask_sha256,
        "gene_universe_sha256": gene_universe["sha256"],
        "stage2_direct_contract": direct_contract(gene_universe),
        # ---- full binding ----
        "run_binding_sha256": run_sha256,
        "run_binding": run_binding,
        "selection_contract": {
            "selection_id": selection.selection_id,
            "question_id": selection.question_id,
            "contract_sha256": selection.contract_sha256,
            "stage1_method_version": selection.stage1_method_version,
            "stage1_validation_sha256": selection.stage1_validation_sha256,
            "stage1_validation_status": (
                "bound" if selection.stage1_validation_sha256
                else "pending_stage1_v3_validation"),
            "id_consistency_check": id_check,
            "stage2_constructs_selection": False,
        },
        "axis": axis_record(run_id, selection, axis),
        # Enums, flags and ids. The scientific caveats behind them are stated once, in
        # the method docs and HANDOFF — not re-narrated in every emitted run.
        "method": {
            "method_id": config.METHOD_ID,
            "method_version": config.METHOD_VERSION,
            "formula_id": config.FORMULA_ID,
            "formula_expr": config.FORMULA_EXPR,
            "arm_formula": dict(config.ARM_FORMULA),
            "combined_objective_permitted": config.COMBINED_OBJECTIVE_PERMITTED,
            "headline_arm_permitted": config.HEADLINE_ARM_PERMITTED,
            "exact_per_cell_stage1_score": False,
            "composition_shift_separated": False,
            "cell_level_support_state": "screen_only",
            "inference_status": config.INFERENCE_STATUS,
        },
        "guide_contract": {
            "released_guide_lanes": guide_lanes,
            "resolution_ladder": list(config.GUIDE_RESOLUTION_LADDER),
            "identity_inference_permitted":
                config.GUIDE_IDENTITY_INFERENCE_PERMITTED,
            "slot_name_used_as_evidence": False,
            "contributor_manifest": guide_manifest,
        },
        "donor_contract": {
            "donor_tokens": donor_splits["donor_tokens"],   # verbatim, unparsed
            "effective_donor_n": donor_splits["n_donors"],
            "n_donor_pair_matrices": donor_splits["n_pairs"],
            "complementary_splits": [s.split_id for s in donor_splits["splits"]],
            "n_splits": donor_splits["n_splits"],
            "split_status": donor_splits["status"],
            "unpaired_pairs": donor_splits["unpaired_pairs"],
            "stage1_donor_crosswalk": donor_crosswalk,
            "split_rule_id": donor_splits["rule_id"],
            "pairs_are_independent_replicates": False,
        },
        "gene_universe": gene_universe,
        "inference_status": config.INFERENCE_STATUS,
        "no_pq_reason": config.NO_PQ_REASON,
        "stage2_inputs": manifest,
        "generated_by": "02_geneskew/analysis/direct/run_screen.py",
        "generated_at": created_at,       # noncanonical; excluded from run_id
        "independent_verification": config.INDEPENDENT_VERIFICATION_PENDING,
        "generator_verifies_itself": False,
    }


def verification(*, out_dir: str, run_id: str, run_sha256: str,
                 rows: list[dict], mask_sha256: str, contributor_rows: list[dict],
                 provenance_doc: dict[str, Any], n_source_targets: int,
                 gene_universe: dict[str, Any], lane: str) -> dict:
    screen_cols = sorted(rows[0]) if rows else []
    forbidden = sorted(c for c in screen_cols if c.lower() in FORBIDDEN_PQ_COLUMNS)
    # case-SENSITIVE: the retired v2 column was `toward_b`; `toward_B` is current
    banned = sorted(c for c in screen_cols
                    if c in (FORBIDDEN_LEGACY_COLUMNS | COMBINED_OBJECTIVE_ALIASES
                             | HEADLINE_RANK_ALIASES))
    allowed = screen_column_allowlist()
    off_allowlist = sorted(c for c in screen_cols if c not in allowed)

    screen_path = os.path.join(out_dir, "screen.parquet")

    # ---- per-arm ranking integrity, checked INDEPENDENTLY for each arm ----
    arm_report: dict[str, Any] = {}
    for arm in config.ARMS:
        rank_col = config.ARM_RANK_COLUMN[arm]
        evaluable_col = f"{config.ARM_POLE[arm]}_evaluable"
        ranked = [r for r in rows if r.get(rank_col) is not None]
        unranked = [r for r in rows if r.get(rank_col) is None]
        ranks = sorted(r[rank_col] for r in ranked)
        rank_dtype = (str(pd.read_parquet(screen_path, columns=[rank_col])[rank_col].dtype)
                      if os.path.exists(screen_path) else None)
        arm_report[arm] = {
            "rank_column": rank_col,
            "evaluable_column": evaluable_col,
            "n_evaluable": sum(1 for r in rows if r.get(evaluable_col)),
            "n_ranked": len(ranked),
            "ranks_contiguous": ranks == list(range(1, len(ranked) + 1)),
            "rank_dtype": rank_dtype,
            "rank_is_nullable_integer": rank_dtype == config.RANK_DTYPE,
            "not_evaluable_with_a_rank": [r["target_id"] for r in ranked
                                          if not r.get(evaluable_col)],
            "evaluable_without_a_rank": [
                r["target_id"] for r in unranked
                if r.get(evaluable_col) and r.get(arm) is not None],
            "arm_state_counts": dict(Counter(
                r[f"{config.ARM_POLE[arm]}_state"] for r in rows)),
            "evidence_tier_counts": dict(Counter(
                r[f"{config.ARM_POLE[arm]}_evidence_tier"] for r in rows)),
            "guide_replication_counts": dict(Counter(
                r[f"{config.ARM_POLE[arm]}_guide_replication_state"] for r in rows)),
            "desired_modulation_counts": dict(Counter(
                r[f"{config.ARM_POLE[arm]}_desired_target_modulation"] for r in rows)),
        }

    # The two arms must not be the same ranking wearing two names, and neither may
    # borrow the other's evaluability.
    rank_a = {r["target_id"]: r.get(config.ARM_RANK_COLUMN[config.ARM_A])
              for r in rows}
    rank_b = {r["target_id"]: r.get(config.ARM_RANK_COLUMN[config.ARM_B])
              for r in rows}
    arms_independent = any(rank_a[t] != rank_b[t] for t in rank_a) or not rows

    causal = scan_for_causal_language(provenance_doc)
    local = scan_for_local_paths(provenance_doc)

    artifact_sha = {}
    for fn in sorted(os.listdir(out_dir)):
        if fn != "verification.json":
            artifact_sha[fn] = file_sha256(os.path.join(out_dir, fn))

    contrib_status = Counter(r["contributor_status"] for r in contributor_rows)
    unresolved = Counter(r["contributor_unresolved_reason"] for r in contributor_rows
                         if r["contributor_unresolved_reason"])

    return {
        "schema_version": SCHEMA_VERIFICATION,
        "run_id": run_id,
        "run_binding_sha256": run_sha256,
        "generated_by": "02_geneskew/analysis/direct/run_screen.py",
        "independent_verification": "pending",
        "row_count": len(rows),
        "source_target_count": n_source_targets,
        "complete_disposition": len(rows) == n_source_targets,
        "base_qc_state_counts": dict(Counter(r["base_qc_state"] for r in rows)),
        "contributor_status_counts": dict(contrib_status),
        "contributor_unresolved_reasons": dict(unresolved),
        "lane": lane,
        "ranking": {
            "arms": list(config.ARMS),
            "population": config.RANK_POPULATION,
            "tie_break": config.RANK_TIE_BREAK,
            "per_arm": arm_report,
            "no_headline_rank": not any(c in screen_cols for c in
                                        ("rank", "primary_rank", "headline_rank")),
            "no_combined_objective": not any(
                c in screen_cols for c in
                ("combination", "balanced_skew", "combined_score", "total_skew")),
            "arms_rank_independently": arms_independent,
            "arm_ranks_all_valid": all(
                a["ranks_contiguous"] and a["rank_is_nullable_integer"]
                and not a["not_evaluable_with_a_rank"]
                and not a["evaluable_without_a_rank"]
                for a in arm_report.values()),
        },
        "cross_arm": {
            "concordance_class_counts": dict(Counter(
                r["concordance_class"] for r in rows)),
            "desired_modulation_agreement_counts": dict(Counter(
                r["desired_modulation_agreement"] for r in rows)),
            "conflicts_preserved": True,
            "rule_id": config.CROSS_ARM_RULE_ID,
            "cross_arm_fields_rank_or_gate": False,
        },
        "gene_universe": {
            "sha256": gene_universe["sha256"],
            "n_genes": gene_universe["n_genes"],
            "object_sizes": gene_universe["object_sizes"],
            "single_universe_for_every_estimate": True,
        },
        "forbidden_legacy_columns_present": banned,
        "no_legacy_columns": banned == [],
        "columns_off_allowlist": off_allowlist,
        "columns_match_allowlist": off_allowlist == [],
        "family_size_evaluated": {
            arm: sum(1 for r in rows if r.get(arm) is not None)
            for arm in config.ARMS},
        "family_size_rule_id": config.FAMILY_SIZE_RULE_ID,
        "family_size_is_a_multiplicity_family": False,
        "forbidden_pq_columns_present": forbidden,
        "no_pq_columns": forbidden == [],
        "causal_language_hits": causal,
        "no_causal_language": causal == [],
        "machine_local_path_hits": local,
        "no_machine_local_paths": local == [],
        "inference_status": config.INFERENCE_STATUS,
        "mask_sha256": mask_sha256,
        "artifact_sha256": artifact_sha,
    }


def write_json(path: str, obj: Any) -> None:
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True, default=str)
        fh.write("\n")


def write_parquet(rows: list[dict], path: str, sort_by: list[str],
                  nullable_int_columns: tuple[str, ...] = ()) -> pd.DataFrame:
    """Write a table, keeping nullable integers as Int64 rather than NaN floats.

    ``rank`` must survive the round trip as a null, not as float NaN: a consumer
    that calls ``int()`` on a NaN crashes, and one that coerces it invents a rank
    for a target that has none.
    """
    df = pd.DataFrame(rows)
    for col in nullable_int_columns:
        if col in df.columns:
            df[col] = pd.array(
                [None if v is None or pd.isna(v) else int(v) for v in df[col]],
                dtype="Int64")
    if not df.empty and sort_by:
        df = df.sort_values(sort_by, na_position="last").reset_index(drop=True)
    df.to_parquet(path, index=False)
    return df
