"""Generate the JSON-Schema artifacts in 04_PKPD/schemas/ from the code itself.

Hand-written schemas drift away from the models they describe. These are generated from
the pydantic models and the parquet table declarations, and a test regenerates them and
compares — so the published contract cannot silently disagree with the enforced one.

Regenerate:  python -m analysis.schemas_export
"""

from __future__ import annotations

import json
import os
from typing import Any

from pydantic import BaseModel

from .contracts import (
    STAGE3_CONTRACT_STATUS,
    STAGE3_SCHEMA_ID,
    STAGE4_METHOD_VERSION,
    EvidenceContext,
    SourceRecord,
    Stage3DrugCandidateSet,
)
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
from .method_config import STAGE4_DIR
from .tables import SORT_KEYS, TABLE_SCHEMAS

SCHEMA_DIR = os.path.join(STAGE4_DIR, "schemas")

EVIDENCE_MODELS: dict[str, type[BaseModel]] = {
    "EvidenceContext": EvidenceContext,
    "SourceRecord": SourceRecord,
    "PropertyRecord": PropertyRecord,
    "PotencyRecord": PotencyRecord,
    "TransporterObservation": TransporterObservation,
    "ExposureMeasurement": ExposureMeasurement,
    "DeliveryAssignment": DeliveryAssignment,
    "NebpiObservation": NebpiObservation,
    "SafetyEvidenceRecord": SafetyEvidenceRecord,
    # Result-affecting, source-bound evidence rows. They were absent from the published
    # contract while the engine was consuming them, which is how an unregistered
    # potency-context source and a caller-authored negative search went unnoticed.
    "PotencyContextLink": PotencyContextLink,
    "SearchManifest": SearchManifest,
}


def stage3_schema() -> dict[str, Any]:
    schema = Stage3DrugCandidateSet.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = STAGE3_SCHEMA_ID
    schema["description"] = (
        "PROVISIONAL, ADAPTER-BOUND — authored unilaterally by Stage 4 and NOT agreed with "
        "Stage 3, which has not landed (03_druglink/ is scaffolding and emits nothing). This "
        "is what Stage 4 is willing to CONSUME, not a description of an existing producer. "
        "Expect reconciliation via a Stage-3 -> Stage-4 adapter plus a version bump here. "
        "Content-addressed: candidate_rows_sha256 is the sha256 of the canonical JSON of the "
        "candidate rows (sorted by candidate_id, sorted keys, no whitespace, floats rounded to "
        "10 dp, timestamps/labels/paths excluded), and the Stage-4 firewall recomputes it "
        "rather than trusting it."
    )
    schema["x-spot-stage3-contract-status"] = STAGE3_CONTRACT_STATUS
    return schema


def evidence_inputs_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "spot.stage04_evidence_inputs.v1",
        "description": (
            "One row per actual observation, each bound to a public source response "
            "(source_record_id + access_date + raw_response_sha256 + exact extraction "
            "transform). Nothing here is derived, imputed or summarized."
        ),
        "stage4_method_version": STAGE4_METHOD_VERSION,
        "records": {name: model.model_json_schema() for name, model in EVIDENCE_MODELS.items()},
    }


def tables_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "spot.stage04_evidence_tables.v1",
        "description": (
            "The four parquet evidence tables. Column order, dtypes and row order are part "
            "of the contract: content_sha256 is taken over the canonical rows in this exact "
            "shape, so a reordering is a content change."
        ),
        "float_rules": {
            "canonical_hash_decimals": 10,
            "publication_rounding": "ROUND_HALF_UP",
            "nan_inf": "rejected in canonical content",
        },
        "tables": {
            name: {
                "columns": list(schema.names),
                "dtypes": [str(f.type) for f in schema],
                "sort_key": list(SORT_KEYS[name]),
            }
            for name, schema in TABLE_SCHEMAS.items()
        },
    }


GENERATED = {
    "spot.stage03_drug_candidate_set.v1.schema.json": stage3_schema,
    "spot.stage04_evidence_inputs.v1.schema.json": evidence_inputs_schema,
    "spot.stage04_evidence_tables.v1.schema.json": tables_schema,
}


def render(doc: dict[str, Any]) -> str:
    return json.dumps(doc, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def write_all(schema_dir: str = SCHEMA_DIR) -> list[str]:
    os.makedirs(schema_dir, exist_ok=True)
    written = []
    for filename, builder in GENERATED.items():
        path = os.path.join(schema_dir, filename)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(render(builder()))
        written.append(path)
    return written


if __name__ == "__main__":
    for p in write_all():
        print("wrote", p)
