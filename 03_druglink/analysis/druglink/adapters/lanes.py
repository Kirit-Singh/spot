"""Annotation-lane adapters: GBM patient-level context, LINCS support, method manifests.

Stage 3 computes NOTHING in these lanes. Patient-level GBM aggregation and LINCS
connectivity are produced upstream, frozen, and handed in as raw bytes with a
method manifest that states the rule, the required fields and the denominators.

A lane row may only be ``supporting`` if a method manifest is bound to it. Without
one, the row is downgraded to ``not_evaluated`` -- an assertion of support with no
declared method and no denominator is not evidence.
"""
from __future__ import annotations

from typing import Any

from . import base
from .base import require

VERSION = "lanes-adapter-v2"


def parse_method_manifest(raw: Any, entry: dict[str, Any],
                          src_id: str) -> list[dict[str, Any]]:
    require(isinstance(raw, dict) and isinstance(raw.get("method_manifests"), list),
            "method-manifest response must carry a 'method_manifests' array")
    return [base.lane_row("method_manifest", source=entry["source"],
                          source_record_id=src_id, payload=m)
            for m in raw["method_manifests"]]


def parse_gbm(raw: Any, entry: dict[str, Any], src_id: str) -> list[dict[str, Any]]:
    require(isinstance(raw, dict) and isinstance(raw.get("rows"), list),
            "GBM patient-level summary must carry a 'rows' array")
    return [base.lane_row("gbm_row", source=entry["source"],
                          source_record_id=src_id, payload=r)
            for r in raw["rows"]]


def parse_lincs(raw: Any, entry: dict[str, Any], src_id: str) -> list[dict[str, Any]]:
    require(isinstance(raw, dict) and isinstance(raw.get("rows"), list),
            "LINCS support response must carry a 'rows' array")
    return [base.lane_row("lincs_row", source=entry["source"],
                          source_record_id=src_id, payload=r)
            for r in raw["rows"]]


ADAPTERS = {
    "gbm_patient_summary": base.Adapter(
        "gbm_patient_summary", VERSION, "gbm_atlas", base.FIXTURE_SHAPED,
        ("frozen patient-level summary export",), parse_gbm),
    "lincs_signature_support": base.Adapter(
        "lincs_signature_support", VERSION, "lincs", base.FIXTURE_SHAPED,
        ("frozen signature-level export",), parse_lincs),
    "gbm_method_manifest": base.Adapter(
        "gbm_method_manifest", VERSION, "gbm_atlas", base.FIXTURE_SHAPED,
        ("frozen method manifest",), parse_method_manifest),
    "lincs_method_manifest": base.Adapter(
        "lincs_method_manifest", VERSION, "lincs", base.FIXTURE_SHAPED,
        ("frozen method manifest",), parse_method_manifest),
}
