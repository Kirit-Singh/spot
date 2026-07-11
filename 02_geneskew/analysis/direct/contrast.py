"""Canonical contrast construction and content-addressed identifiers.

contrast_id hashes canonical SCIENTIFIC content only (plan §4.5): objective,
condition, donor scope, A/B program+field+direction, Stage-1 method version,
program-registry hash, dataset id, pinned HF revision, source h5ad SHA-256,
effect-universe id. It excludes timestamps, display labels and UI ordering.
"""
from __future__ import annotations

from typing import Any

from .config import Contrast
from .hashing import canonical_json, sha256_hex

CONTRAST_ID_LEN = 16  # hex chars of the canonical sha used as the directory id


def canonical_contrast_content(contrast: Contrast, registry_sha256: str) -> dict[str, Any]:
    """Return the canonical scientific-content dict for hashing."""
    return {
        "objective": contrast.objective,
        "analysis_condition": contrast.analysis_condition,
        "donor_scope": contrast.donor_scope,
        "A": {
            "program_id": contrast.a.program_id,
            "score_field": contrast.a.score_field,
            "direction": contrast.a.direction,
        },
        "B": {
            "program_id": contrast.b.program_id,
            "score_field": contrast.b.score_field,
            "direction": contrast.b.direction,
        },
        "stage1_method_version": contrast.stage1_method_version,
        "program_registry_sha256": registry_sha256,
        "dataset_id": contrast.dataset_id,
        "effect_universe_id": contrast.effect_universe_id,
        "source_hf_revision": contrast.source_hf_revision,
        "source_h5ad_sha256": contrast.source_h5ad_sha256,
    }


def contrast_identifiers(contrast: Contrast, registry_sha256: str) -> tuple[str, str, dict]:
    """Return (contrast_id, canonical_sha256, canonical_content_dict)."""
    content = canonical_contrast_content(contrast, registry_sha256)
    full = sha256_hex(canonical_json(content))
    return full[:CONTRAST_ID_LEN], full, content


def build_stage01_selection(contrast: Contrast, registry_sha256: str,
                            created_at: str) -> dict[str, Any]:
    """Emit a spot.stage01_selection.v1 record (plan §4.5)."""
    contrast_id, canonical_sha, content = contrast_identifiers(contrast, registry_sha256)
    return {
        "schema_version": "spot.stage01_selection.v1",
        "contrast_id": contrast_id,
        "canonical_contrast_sha256": canonical_sha,
        "objective": contrast.objective,
        "analysis_condition": contrast.analysis_condition,
        "donor_scope": contrast.donor_scope,
        "A_program_id": contrast.a.program_id,
        "A_score_field": contrast.a.score_field,
        "A_direction": contrast.a.direction,
        "B_program_id": contrast.b.program_id,
        "B_score_field": contrast.b.score_field,
        "B_direction": contrast.b.direction,
        "stage1_method_version": contrast.stage1_method_version,
        "program_registry_sha256": registry_sha256,
        "dataset_id": contrast.dataset_id,
        "source_hf_repo": "KiritSingh/spot-CD4-Marson",
        "source_hf_revision": contrast.source_hf_revision,
        "source_h5ad_sha256": contrast.source_h5ad_sha256,
        "stage1_code_commit": None,
        "validation_status": "constructed_default",
        "validation_reasons": [
            "default canonical selection constructed by Stage-2 (Stage-1 UI in parallel)",
        ],
        "canonical_content": content,
        "created_at": created_at,  # noncanonical; excluded from contrast_id
    }


def build_axis(contrast: Contrast, registry_sha256: str,
               registry_meta: dict[str, Any]) -> dict[str, Any]:
    """Emit a spot.stage02_axis.v1 record (plan §7 / §11)."""
    contrast_id, canonical_sha, content = contrast_identifiers(contrast, registry_sha256)
    a_meta = registry_meta[contrast.a.program_id]
    b_meta = registry_meta[contrast.b.program_id]
    return {
        "schema_version": "spot.stage02_axis.v1",
        "contrast_id": contrast_id,
        "canonical_contrast_sha256": canonical_sha,
        "objective": contrast.objective,
        "analysis_condition": contrast.analysis_condition,
        "donor_scope": contrast.donor_scope,
        "A": {
            "program_id": contrast.a.program_id,
            "score_field": contrast.a.score_field,
            "direction": contrast.a.direction,
            "sign": contrast.a.sign,
            "display_label": a_meta.get("display_label"),
            "panel_ensembl": a_meta.get("panel_ensembl"),
            "control_ensembl": a_meta.get("control_ensembl"),
        },
        "B": {
            "program_id": contrast.b.program_id,
            "score_field": contrast.b.score_field,
            "direction": contrast.b.direction,
            "sign": contrast.b.sign,
            "display_label": b_meta.get("display_label"),
            "panel_ensembl": b_meta.get("panel_ensembl"),
            "control_ensembl": b_meta.get("control_ensembl"),
        },
        "program_registry_sha256": registry_sha256,
        "canonical_content": content,
    }
