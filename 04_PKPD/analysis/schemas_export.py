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

from pydantic import TypeAdapter

from .acquisition import ACQUISITION_SCHEMA_ID, HARD_RULES, AcquisitionManifest
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
from .acquisition import SourceAcquisitionRecord
from .assay_records import AssayBinding
from .organ_system import OrganSystemEvidence
from .method_config import STAGE4_DIR
from .pk_records import (
    FractionUnboundRecord,
    PkDetail,
    RatioReport,
    SamplingDetail,
    UnboundDerivation,
)
from .contract_version import ContractVersion
from .tables import sort_keys, table_schemas

SCHEMA_DIR = os.path.join(STAGE4_DIR, "schemas")

# `OrganSystemEvidence` is acquisition's frozen dataclass, not a pydantic model: it is
# consumed as-is rather than re-declared, because a second declaration of the same
# evidence shape is exactly the drift this schema exists to prevent. `_json_schema`
# handles both kinds.
EVIDENCE_MODELS: dict[str, Any] = {
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
    # v2. The acquisition contract, the assay binding, and the PK context that makes a
    # clinical concentration mean something. Published so a producer can build against them.
    "SourceAcquisitionRecord": SourceAcquisitionRecord,
    "FractionUnboundRecord": FractionUnboundRecord,
    "OrganSystemEvidence": OrganSystemEvidence,
    "AssayBinding": AssayBinding,
    "PkDetail": PkDetail,
    "SamplingDetail": SamplingDetail,
    "RatioReport": RatioReport,
    "UnboundDerivation": UnboundDerivation,
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


def _json_schema(model: Any) -> dict[str, Any]:
    """Pydantic models and stdlib dataclasses alike.

    `OrganSystemEvidence` is acquisition's frozen dataclass and is consumed here as-is rather
    than re-declared as a pydantic model — a second declaration of the same evidence shape is
    exactly the drift this schema exists to prevent.
    """
    if hasattr(model, "model_json_schema"):
        return model.model_json_schema()
    return TypeAdapter(model).json_schema()


def evidence_inputs_schema() -> dict[str, Any]:
    """v2 — the acquisition-complete contract.

    v1 is NOT regenerated. It is frozen on disk (see FROZEN below) and remains a true
    description of an admissible v1 document: every v2 field is additive and optional, so a
    v1 bundle still validates, and `contract_profile.py` refuses a v1 bundle that smuggles a
    v2 cell. What v2 adds is what an ACQUISITION must show — and a v1 bundle can never claim
    to be acquisition-complete.
    """
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "spot.stage04_evidence_inputs.v2",
        "description": (
            "One row per actual observation, each bound to a public source response "
            "(source_record_id + access_date + raw_response_sha256 + exact extraction "
            "transform). Nothing here is derived, imputed or summarized. v2 adds the "
            "acquisition contract: a SourceAcquisitionRecord per source (canonical query, "
            "accessed_at_utc, HTTP status/media type/headers, release, terms URL, raw bytes "
            "+ hash, stable content hash, transform, adapter code hash, review status and an "
            "explicit observation state), structured assay/PK bindings, and reported-vs-"
            "derived ratios. v1 documents remain readable and remain NOT acquisition-complete."
        ),
        "supersedes": "spot.stage04_evidence_inputs.v1",
        "migration": (
            "v1 -> v2 is additive: every new field is optional on the model, so a v1 document "
            "validates unchanged. It does NOT become acquisition-complete by validating. To "
            "reach v2 a document must declare schema_id spot.stage04_evidence_bundle.v2 and "
            "satisfy analysis/contract_profile.py, which requires the acquisition manifest and "
            "the per-lane bindings above."
        ),
        "stage4_method_version": STAGE4_METHOD_VERSION,
        "records": {name: _json_schema(model) for name, model in EVIDENCE_MODELS.items()},
    }


def tables_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "spot.stage04_evidence_tables.v2",
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
        "contract_versions": {
            version.value: {
                name: {
                    "columns": list(schema.names),
                    "dtypes": [str(f.type) for f in schema],
                    "sort_key": list(sort_keys(version)[name]),
                }
                for name, schema in table_schemas(version).items()
            }
            for version in (ContractVersion.V1, ContractVersion.V2)
        },
        "note": (
            "v1 is FROZEN and is a strict column PREFIX of v2: a v1 release carries exactly the "
            "v1 columns, not the v1 columns plus nulls, and hashes exactly as it always did."
        ),
        "tables": {
            name: {
                "columns": list(schema.names),
                "dtypes": [str(f.type) for f in schema],
                "sort_key": list(sort_keys(ContractVersion.V2)[name]),
            }
            for name, schema in table_schemas(ContractVersion.V2).items()
        },
    }


def acquisition_manifest_schema() -> dict[str, Any]:
    schema = AcquisitionManifest.model_json_schema()
    schema["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    schema["$id"] = ACQUISITION_SCHEMA_ID
    schema["description"] = (
        "One record per source response: canonical URL + query, UTC access time, HTTP status, "
        "media type and selected response headers, source release/last_updated, licence/terms "
        "URL, raw byte count + SHA-256 (plus a stable content hash where the transport envelope "
        "is volatile), the adapter code hash, the exact extraction transform, and the review "
        "status. Raw bytes are cached OUTSIDE Git under a caller-supplied run root and are "
        "addressed by their own SHA-256; `cache_relpath` is relative to that root. Absent "
        "evidence is stated in `missing`, never left as an empty field."
    )
    schema["x-spot-hard-rules"] = list(HARD_RULES)
    return schema


GENERATED = {
    "spot.stage03_drug_candidate_set.v1.schema.json": stage3_schema,
    # W8 (canonical, b287f72): the acquisition manifest a source must show to be re-fetchable.
    "spot.stage04_acquisition_manifest.v1.schema.json": acquisition_manifest_schema,
    # W9 (canonical, 56864a0): the evidence contract is v2. v1 is FROZEN below, NOT regenerated.
    "spot.stage04_evidence_inputs.v2.schema.json": evidence_inputs_schema,
    "spot.stage04_evidence_tables.v2.schema.json": tables_schema,
}

# FROZEN. These files are the v1 contract as it was published. They are NOT regenerated, and
# their bytes are pinned by a test: "backwards compatible" is a claim about the OLD contract,
# and a claim you can edit is not a guarantee. A v1 document still validates against the v2
# models (every v2 field is additive and optional) and still means exactly what it meant.
FROZEN = {
    "spot.stage04_evidence_inputs.v1.schema.json":
        "5667ef89d86ff5b8c37df8caea912648977f8fa85acd663434e0cc51f1cd8528",
    "spot.stage04_evidence_tables.v1.schema.json":
        "8c38e6952f1624644cb0762257ba64ba4d790b810c25c028fb112ccfe5ed3bff",
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
