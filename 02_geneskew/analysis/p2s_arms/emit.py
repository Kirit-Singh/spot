"""EMIT: the content-addressed secondary artifact, keyed by reusable ``arm_key``.

Atomic, into a run directory named for its own content hash. Never overwritten by biology
id: a result you can overwrite by naming the same biology twice is a result whose bytes do
not identify it.

WHAT IS NOT HERE
----------------
  * NO rank column, in any file. A lane with no rank column has no surface on which to
    reorder anything;
  * NO combined / balanced / weighted lane. Not quarantined — ABSENT;
  * NO temporal artifact. A DiD claim needs a field that is a function of both endpoints,
    and there is no file in which to write one;
  * NO p, NO q, NO FDR;
  * NO machine-local paths;
  * NO ``production_eligible``. The historical 0/33 LOMO result is descriptive evidence
    about single-marker dependence, not a production gate, and a field pinned to it would
    read as one. This lane binds ``base_portable`` and ``lane_role`` instead.
"""
from __future__ import annotations

import json
import os
from typing import Any

import pandas as pd
from direct.hashing import canonical_json, content_hash, file_sha256, sha256_hex

from . import binding, config, model, stability

SUPPORT_FILE = "p2s_arm_support.parquet"
COEF_FILE = "p2s_coefficients.parquet"
RECON_FILE = "p2s_reconstruction.parquet"
DOC_FILE = "p2s_support.json"
PROVENANCE_FILE = "p2s_provenance.json"

ARTIFACT_FILES = (SUPPORT_FILE, COEF_FILE, RECON_FILE, DOC_FILE)

SUPPORT_COLUMNS = (
    "arm_key", "program_id", "desired_change", "condition", "target_id",
    "n_runs", "n_selected_runs", "selection_frequency", "positive_frequency",
    "negative_frequency", "median_coefficient", "coefficient_min", "coefficient_max",
    "lodo_sign_agreement", "n_lodo_runs", "effect_layer_agreement", "n_effect_layers",
    "support_status", "opposed",
)

COEF_COLUMNS = (
    "arm_key", "program_id", "desired_change", "condition", "target_id",
    "coefficient", config.COEF_SEM_COLUMN, "nonzero", "sign",
    "effect_layer", "model_config", "donor_scope", "quantity",
)

RECON_COLUMNS = (
    "arm_key", "program_id", "desired_change", "condition",
    "effect_layer", "model_config", "donor_scope",
    "reconstruction_gene_cv_test_r2_mean", "reconstruction_gene_cv_test_r2_median",
    "reconstruction_gene_cv_test_spearman_mean", "reconstruction_gene_cv_train_r2_mean",
    "n_folds", "cv_label", "cv_semantics", "seconds", "metrics_are_sign_invariant",
)


def write_json(path: str, obj: Any) -> None:
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True, default=str)
        fh.write("\n")


def write_parquet(rows: list[dict], path: str, columns: tuple[str, ...],
                  sort_by: list[str]) -> pd.DataFrame:
    """Write exactly the allowlisted columns, in order. An extra column is a defect.

    The verifier checks the shipped columns against its own copy of this allowlist, so a
    column that slipped in here — a rank, a gate, a combined objective — is rejected by
    ABSENCE from the allowlist rather than by a rule that has to anticipate its name.
    """
    df = pd.DataFrame(rows, columns=list(columns))
    if not df.empty and sort_by:
        df = df.sort_values(sort_by, na_position="last").reset_index(drop=True)
    df.to_parquet(path, index=False)
    return df


def method_block(bound: dict[str, Any]) -> dict[str, Any]:
    """The method, as one hashable object. Ids, enums, numbers and booleans — no prose."""
    return {
        "method_id": config.METHOD_ID,
        "method_version": config.METHOD_VERSION,
        "schema_version": config.SCHEMA_SUPPORT,
        "lane_role": config.LANE_ROLE,
        "signature_model_id": config.SIGNATURE_MODEL_ID,
        "signature_model": config.SIGNATURE_MODEL,
        "signature_normalisation": config.SIGNATURE_NORMALIZATION,
        "binning_axes": list(config.BINNING_AXES),
        "n_bins": config.N_SCORE_BINS,
        "solver": config.SOLVER,
        "normal_equations_permitted": config.NORMAL_EQUATIONS_PERMITTED,
        "stage1_values_read_by_barcode_never_recomputed": config.STAGE1_VALUES_READ_BY_BARCODE,
        "activation_program_id": config.ACTIVATION_PROGRAM_ID,
        "arms_are_sign_transforms_of_one_base_effect": True,
        "arm_key_carries_pole_or_role": False,
        "temporal_artifact_emitted": config.TEMPORAL_ARTIFACT_EMITTED,
        "rank_column_emitted": config.RANK_COLUMN_EMITTED,
        "model": model.model_block(),
        "support": stability.method_block(),
        # what this lane is bound to, and derived from. THE ADMISSION CHAIN: the solver
        # lock, W10's independent ADMIT (its hash RE-DERIVED, not quoted), and the exact
        # bytes of the Direct bundle those arms came from.
        "base_portable": bound["base_portable"],
        "n_admitted_programs": bound["n_admitted_programs"],
        **binding.bound_block(bound),
        # the NEGATIVE DECLARATIONS. Exempt from the key-name firewall only while false.
        **dict(config.NEGATIVE_DECLARATIONS),
    }


def support_document(*, bound: dict[str, Any], support_rows: list[dict[str, Any]],
                     coef_rows: list[dict[str, Any]], recon_rows: list[dict[str, Any]],
                     upstream: dict[str, Any], universe: dict[str, Any]) -> dict[str, Any]:
    """The bundle document. Content-addressed: its id follows its content."""
    arm_keys_seen = sorted({str(r["arm_key"]) for r in support_rows})
    return {
        "schema_version": config.SCHEMA_SUPPORT,
        "lane_role": config.LANE_ROLE,
        "arm_key": bound["arm"].arm_key,
        "sibling_arm_key": _sibling_key(bound, arm_keys_seen),
        "program_id": bound["arm"].program_id,
        "condition": bound["arm"].condition,
        "arm_keys": arm_keys_seen,
        "n_arms": len(arm_keys_seen),
        "n_support_rows": len(support_rows),
        "n_coefficient_rows": len(coef_rows),
        "n_reconstruction_rows": len(recon_rows),
        "method": method_block(bound),
        "upstream_software": upstream,
        "gene_universe": universe,
        "support_rows_sha256": content_hash(canonical_support(support_rows)),
        "coefficient_rows_sha256": content_hash(canonical_coefficients(coef_rows)),
    }


def _sibling_key(bound: dict[str, Any], arm_keys_seen: list[str]) -> Any:
    other = [k for k in arm_keys_seen if k != bound["arm"].arm_key]
    return other[0] if len(other) == 1 else None


def _num(v: Any) -> Any:
    if v is None:
        return None
    f = float(v)
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return round(f, 6)


def canonical_support(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The ONE shape the support hash is taken over — re-derivable from the shipped parquet.

    Explicit, because parquet round-trips an int count to int64 and a null float to NaN.
    A hash over the in-memory dicts would bind a number no reader of the file could
    reproduce.
    """
    out = []
    for r in rows:
        out.append({
            "arm_key": str(r["arm_key"]),
            "target_id": str(r["target_id"]),
            "n_runs": int(r["n_runs"]),
            "selection_frequency": _num(r["selection_frequency"]),
            "positive_frequency": _num(r["positive_frequency"]),
            "negative_frequency": _num(r["negative_frequency"]),
            "median_coefficient": _num(r["median_coefficient"]),
            "support_status": str(r["support_status"]),
            "opposed": bool(r["opposed"]),
        })
    out.sort(key=lambda r: (r["arm_key"], r["target_id"]))
    return out


def canonical_coefficients(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The ONE shape the coefficient hash is taken over."""
    out = []
    for r in rows:
        out.append({
            "arm_key": str(r["arm_key"]),
            "target_id": str(r["target_id"]),
            "effect_layer": str(r["effect_layer"]),
            "model_config": str(r["model_config"]),
            "donor_scope": str(r["donor_scope"]),
            "coefficient": _num(r["coefficient"]),
            "nonzero": bool(r["nonzero"]),
            "sign": int(r["sign"]),
        })
    out.sort(key=lambda r: (r["arm_key"], r["donor_scope"], r["effect_layer"],
                            r["model_config"], r["target_id"]))
    return out


def run_id_for(binding: dict[str, Any]) -> tuple[str, str]:
    """``(run_id, run_sha256)`` — the run's identity IS its content."""
    full = sha256_hex(canonical_json(binding))
    return full[:config.RUN_ID_LEN], full


def write(out_root: str, *, doc: dict[str, Any], provenance: dict[str, Any],
          support_rows: list[dict[str, Any]], coef_rows: list[dict[str, Any]],
          recon_rows: list[dict[str, Any]], run_id: str) -> dict[str, Any]:
    """Write the run directory. Its NAME is its content hash — never a biology id."""
    out_dir = os.path.join(out_root, run_id)
    os.makedirs(out_dir, exist_ok=True)

    write_parquet(support_rows, os.path.join(out_dir, SUPPORT_FILE), SUPPORT_COLUMNS,
                  sort_by=["arm_key", "target_id"])
    write_parquet(coef_rows, os.path.join(out_dir, COEF_FILE), COEF_COLUMNS,
                  sort_by=["arm_key", "donor_scope", "effect_layer", "model_config",
                           "target_id"])
    write_parquet(recon_rows, os.path.join(out_dir, RECON_FILE), RECON_COLUMNS,
                  sort_by=["arm_key", "donor_scope", "effect_layer", "model_config"])
    write_json(os.path.join(out_dir, DOC_FILE), dict(doc, p2s_run_id=run_id))

    prov = dict(provenance)
    prov["artifact_sha256"] = {
        name: file_sha256(os.path.join(out_dir, name)) for name in ARTIFACT_FILES}
    write_json(os.path.join(out_dir, PROVENANCE_FILE), prov)

    return {"out_dir": out_dir, "p2s_run_id": run_id,
            "artifact_sha256": prov["artifact_sha256"]}
