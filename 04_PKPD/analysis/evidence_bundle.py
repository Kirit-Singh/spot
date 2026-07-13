"""Load a Stage-4 evidence input bundle (spot.stage04_evidence_bundle.v1).

This is the OTHER half of the door. `stage3_adapter` brings in WHICH molecules to
characterise; this brings in the observations to characterise them WITH. Stage 4 has no
scraper: every row here is a public-source observation someone acquired, bound to a
response hash, and reviewed. There is deliberately no path that invents one.

The rule the CLI enforces around this module: a candidate set with no evidence bundle
produces an admission RECEIPT, never a scorecard. Running the engine over ten empty lanes
would emit a complete-looking artifact set whose every lane says "not_evaluated" — a
document that reads like a result and contains none. An empty lane is not a finding.
"""

from __future__ import annotations

import json
import os
from typing import Any

from pydantic import ValidationError

from .acquisition_records import SourceAcquisitionRecord
from .contract_version import SCHEMA_TO_VERSION, ContractVersion
from .contracts import EvidenceContext, SourceRecord
from .pk_records import FractionUnboundRecord
from .evidence_records import (
    DeliveryAssignment,
    ExposureMeasurement,
    NebpiObservation,
    PotencyContextLink,
    PotencyRecord,
    PropertyRecord,
    SafetyEvidenceRecord,
    SearchManifest,
    TransporterObservation,
)
from .firewall import Rejection

EVIDENCE_BUNDLE_SCHEMA_V1 = "spot.stage04_evidence_bundle.v1"
EVIDENCE_BUNDLE_SCHEMA_V2 = "spot.stage04_evidence_bundle.v2"

# Back-compat: the v1 name other modules already import.
EVIDENCE_BUNDLE_SCHEMA = EVIDENCE_BUNDLE_SCHEMA_V1

# lane -> the model every row in it must validate against. v1 has ten lanes; v2 adds two.
LANE_MODELS_V1: dict[str, Any] = {
    "contexts": EvidenceContext,
    "properties": PropertyRecord,
    "potencies": PotencyRecord,
    "potency_context_links": PotencyContextLink,
    "transporters": TransporterObservation,
    "exposures": ExposureMeasurement,
    "delivery_assignments": DeliveryAssignment,
    "nebpi_observations": NebpiObservation,
    "safety_records": SafetyEvidenceRecord,
    "search_manifests": SearchManifest,
}

# The two lanes that exist only under v2. A v1 bundle carrying one is REFUSED rather than
# quietly ignored: the v1 digest does not cover these rows, so accepting them would let a
# bundle claim an acquisition manifest that never entered the release's identity.
LANE_MODELS_V2: dict[str, Any] = {
    **LANE_MODELS_V1,
    "fraction_unbound": FractionUnboundRecord,
    "source_acquisition": SourceAcquisitionRecord,
}

LANE_MODELS = {
    ContractVersion.V1: LANE_MODELS_V1,
    ContractVersion.V2: LANE_MODELS_V2,
}


def load_evidence_bundle(path: str) -> dict[str, Any]:
    """-> {lane: [validated rows], "sources": {...}, "config": {...}}. Refuses, never guesses."""
    if not os.path.exists(path):
        raise Rejection("evidence_bundle_missing", f"no evidence bundle at {path!r}")
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)

    schema = doc.get("schema_id")
    if schema not in SCHEMA_TO_VERSION:
        raise Rejection(
            "evidence_bundle_schema_unknown",
            f"evidence bundle schema_id is {schema!r}; Stage 4 reads "
            f"{EVIDENCE_BUNDLE_SCHEMA_V1!r} and {EVIDENCE_BUNDLE_SCHEMA_V2!r}",
        )
    version = SCHEMA_TO_VERSION[schema]
    lanes = LANE_MODELS[version]

    unknown = sorted(set(doc) - set(lanes) - {"schema_id", "sources", "config"})
    if unknown:
        raise Rejection(
            "evidence_bundle_unknown_lane",
            f"evidence bundle carries unknown lane(s) {unknown}. Stage 4 will not silently "
            "ignore evidence it does not understand.",
        )

    out: dict[str, Any] = {}
    for lane, model in lanes.items():
        rows = doc.get(lane, []) or []
        if not isinstance(rows, list):
            raise Rejection("evidence_bundle_lane_invalid", f"lane {lane!r} is not a list")
        try:
            out[lane] = [model.model_validate(r) for r in rows]
        except ValidationError as exc:
            raise Rejection(
                "evidence_bundle_row_invalid",
                f"a row in lane {lane!r} does not satisfy the Stage-4 evidence contract",
                {"lane": lane, "errors": exc.errors(include_url=False)[:3]},
            ) from exc

    sources: dict[str, SourceRecord] = {}
    for sid, rec in (doc.get("sources") or {}).items():
        try:
            sources[sid] = SourceRecord.model_validate(rec)
        except ValidationError as exc:
            raise Rejection(
                "evidence_bundle_source_invalid",
                f"source record {sid!r} does not satisfy the Stage-4 source contract",
                {"errors": exc.errors(include_url=False)[:3]},
            ) from exc

    out["sources"] = sources
    out["config"] = dict(doc.get("config") or {})
    out["contract_version"] = version
    return out


def is_empty(bundle: dict[str, Any]) -> bool:
    """No observation in any lane. Running the engine over this would fabricate a result."""
    version = bundle.get("contract_version", ContractVersion.V1)
    return not any(bundle.get(lane) for lane in LANE_MODELS[version])
