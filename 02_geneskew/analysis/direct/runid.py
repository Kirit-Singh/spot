"""run_id — the identifier that binds a Stage-2 result to everything that made it.

A result is NEVER keyed by the biology-only ``question_id`` / ``contrast_id``:
the same two programs and condition can be screened with different code, inputs,
masks or policy, and those are different results.

``run_id`` binds:
  selection_id + the immutable selection contract's own SHA-256;
  the Stage-1 registry / method / input-manifest / code / validation hashes;
  the Stage-2 method and its frozen config + eligibility policy;
  every Stage-2 input file's SHA-256;
  the exact guide manifest (or the documented rule that stood in for it);
  the emitted masks;
  the Stage-2 code tree;
  the environment lock.

It deliberately EXCLUDES timestamps, display labels and machine-local paths, so
a re-run of the same science yields the same run_id.
"""
from __future__ import annotations

import os
from typing import Any, Optional

from . import config
from .hashing import canonical_json, content_hash, file_sha256, sha256_hex

RUN_ID_LEN = 16


def code_tree_sha256(package_dir: str) -> str:
    """Content hash of the Stage-2 direct code tree (sorted, path-relative)."""
    entries = []
    for name in sorted(os.listdir(package_dir)):
        if not name.endswith(".py"):
            continue
        entries.append({"file": name,
                        "sha256": file_sha256(os.path.join(package_dir, name))})
    return content_hash(entries)


def method_block() -> dict[str, Any]:
    """The method, including BOTH arm definitions and the rank/direction outputs.

    Changing an arm formula, an arm's rank column, the evaluability policy or the
    combined-objective prohibition all change run_id.
    """
    return {
        "method_id": config.METHOD_ID,
        "method_version": config.METHOD_VERSION,
        "formula_id": config.FORMULA_ID,
        "effect_layer_primary": config.EFFECT_LAYER_PRIMARY,
        "effect_layer_sensitivity": config.EFFECT_LAYER_SENSITIVITY,
        "arms": list(config.ARMS),
        "arm_formula": dict(config.ARM_FORMULA),
        "arm_rank_column": dict(config.ARM_RANK_COLUMN),
        "arm_evaluable_column": {a: f"{config.ARM_POLE[a]}_evaluable"
                                 for a in config.ARMS},
        "rank_population": config.RANK_POPULATION,
        "rank_tie_break": config.RANK_TIE_BREAK,
        "rank_dtype": config.RANK_DTYPE,
        "combined_objective_permitted": config.COMBINED_OBJECTIVE_PERMITTED,
        "headline_arm_permitted": config.HEADLINE_ARM_PERMITTED,
    }


def config_sha256() -> str:
    """The frozen Stage-2 config, as one id: method + eligibility policy.

    Emitted on every screen row so the row can name the policy that produced it without
    a join. ``direct_method_version`` says WHICH method; this says which THRESHOLDS it
    ran with — and a loosened ``n_cells_min`` or ``min_surviving_control`` changes which
    targets are evaluable at all, so a row that names only the method version is naming
    half of what decided it.
    """
    return content_hash({"stage2_method": method_block(),
                         "stage2_eligibility_policy": config.ELIGIBILITY_POLICY})


def build_run_binding(*, selection, lane: str, stage1_release,
                      stage2_inputs: list[dict[str, Any]],
                      guide_manifest: dict[str, Any], mask_sha256: str,
                      gene_universe_sha256: str, code_tree: str,
                      env_lock: dict[str, Any],
                      support_contract: dict[str, Any],
                      evidence_domain: dict[str, Any],
                      release_gate: dict[str, Any],
                      code_identity: Optional[dict[str, Any]] = None,
                      stage1_v3: Optional[dict[str, Any]] = None
                      ) -> dict[str, Any]:
    """Assemble the canonical, timestamp-free content that run_id hashes.

    Three claims are bound here that a run could otherwise have changed while keeping
    its identity, and each of them changes what the emitted numbers MEAN:

      * ``support_contract`` — a run that quietly STARTED granting guide/donor support
        would be making a different scientific claim under the same id;
      * ``evidence_domain`` — the domain id, the domain RULE id and the size of the
        global pooled-main scope universe the manifest was matched against. A run whose
        universe is one scope smaller has a dropped scope, and that is invisible to
        every per-row check;
      * ``release_gate``    — WHAT proved the gate: for a release-grade lane, a strict
        replay that ran FRESH in the run's own invocation. A gate that is not bound into
        identity can be replaced afterwards by a friendlier one.
    """
    return {
        "lane": lane,
        "stage2_support_contract": support_contract,
        "stage2_evidence_domain": evidence_domain,
        "stage2_release_gate": release_gate,
        "selection": {
            "selection_id": selection.selection_id,
            "question_id": selection.question_id,
            "selection_contract_sha256": selection.contract_sha256,
            "A": {"program_id": selection.a.program_id,
                  "direction": selection.a.direction, "sign": selection.a.sign},
            "B": {"program_id": selection.b.program_id,
                  "direction": selection.b.direction, "sign": selection.b.sign},
            "analysis_condition": selection.analysis_condition,
        },
        "stage1_release": {
            "kind": stage1_release.kind,
            "method_version": stage1_release.method_version,
            "hashes": dict(stage1_release.hashes),
            "n_production_selectable":
                stage1_release.gate_evidence.get("n_production_selectable"),
            "n_pairs_evaluated":
                stage1_release.gate_evidence.get("n_pairs_evaluated"),
            "selectability_rule_id": config.SELECTABILITY_RULE_ID,
            "selectability_stored_boolean_read": False,
        },
        "stage1": {
            "registry_sha256": selection.registry_sha256,
            "method_version": selection.stage1_method_version,
            "input_manifest_sha256": selection.stage1_input_manifest_sha256,
            "code_sha256": selection.stage1_code_sha256,
            # null until the Stage-1 v3 validation artifact exists; filling it
            # later deliberately changes run_id.
            "validation_sha256": selection.stage1_validation_sha256,
        },
        "stage2_method": method_block(),
        "stage2_eligibility_policy": config.ELIGIBILITY_POLICY,
        "stage2_inputs": sorted(
            [{"name": i["name"], "sha256": i["sha256"], "size_bytes": i["size_bytes"]}
             for i in stage2_inputs],
            key=lambda i: i["name"]),
        "guide_manifest": guide_manifest,
        "mask_sha256": mask_sha256,
        "gene_universe_sha256": gene_universe_sha256,
        "code_tree_sha256": code_tree,
        # M2: the REPRODUCIBLE code-identity TUPLE — (commit, clean_tree, manifest_sha256,
        # canonical_digest). `code_tree_sha256` above hashes only the .py files in this one
        # package directory; this identifies the whole Stage-2 tree against a committed
        # history, by a recipe anybody can re-run (`python -m direct.code_digest`).
        "code_identity": code_identity,
        # WHICH v3 contract drove this run, or None. Emitted either way, so a reader can
        # tell a v3-driven run from a legacy one without inferring it.
        "stage1_v3": stage1_v3,
        "environment_lock": env_lock,
    }


def run_id_of(binding: dict[str, Any]) -> tuple[str, str]:
    """Return (run_id, full canonical sha256) for a run binding."""
    full = sha256_hex(canonical_json(binding))
    return full[:RUN_ID_LEN], full


def env_lock_block(path: Optional[str]) -> dict[str, Any]:
    """Environment lock as {name, sha256} — never a machine-local path."""
    if not path or not os.path.exists(path):
        return {"name": None, "sha256": None,
                "status": "environment_lock_not_supplied"}
    return {"name": os.path.basename(path), "sha256": file_sha256(path),
            "status": "locked"}
