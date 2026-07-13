"""The INDEPENDENT receipt: proof that the membership gate actually ran, over these exact bytes.

A contract document is not admission. A gate that ran leaves a receipt; a gate that was skipped
leaves nothing — and from the outside those look identical unless something names the bytes it
judged. This emits that something.

GENERATOR IS NOT VERIFIER. The receipt records who judged what, and it is emitted by the verifier
path, never by the producer of the view it judges.
"""
from __future__ import annotations

import json
import os
import subprocess
from typing import Any, Mapping

from . import candidate_membership as cm
from . import selection_view as sv
from . import view_contract as vc
from .hashing import canonical_json, content_hash, file_sha256

RECEIPT_SCHEMA = "spot.stage03_membership_receipt.v1"
VERIFIER_ID = cm.MEMBERSHIP_VERIFIER_ID
ADMIT = "admit"
REFUSE = "refuse"


def _commit() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                             cwd=os.path.dirname(os.path.abspath(__file__)))
        return out.stdout.strip() or "unknown"
    except Exception:                                     # pragma: no cover - environment only
        return "unknown"


def emit(*, view_path: str) -> dict[str, Any]:
    """Judge the view AT THIS PATH and return the receipt. Refusals are recorded, not raised."""
    with open(view_path, encoding="utf-8") as fh:
        view = json.load(fh)

    verdict, failure = ADMIT, None
    try:
        vc.validate(dict(view))                           # schema + rows + seal + membership
    except Exception as exc:                              # a refusal is a RESULT, not a crash
        verdict, failure = REFUSE, str(exc)[:400]

    store = view.get("store") or {}
    doc: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        "verifier_id": VERIFIER_ID,
        "generator_is_not_verifier": True,
        # WHAT WAS JUDGED — the artifact's own class, never dressed up.
        "artifact_class": view.get("artifact_class"),
        "code_commit": _commit(),
        "view": {
            "path": os.path.abspath(view_path),
            "raw_sha256": file_sha256(view_path),
            "canonical_sha256": content_hash(view),
            "view_id": view.get("view_id"),
            "view_content_sha256": view.get("view_content_sha256"),
        },
        "store": {
            "document_sha256": store.get("document_sha256"),
            "store_manifest_sha256": store.get("store_manifest_sha256"),
            "table_hashes": dict(store.get("table_hashes") or {}),
            "selection_view_vocabulary_digest":
                store.get("selection_view_vocabulary_digest"),
        },
        "membership": {
            "schema": cm.MEMBERSHIP_SCHEMA,
            "rule_id": cm.MEMBERSHIP_RULE_ID,
            "verifier_id": cm.MEMBERSHIP_VERIFIER_ID,
            "retired_ids": sorted(cm.RETIRED_MEMBERSHIP_IDS),
            "vocabulary_digest_in_force": content_hash(sv.vocabularies()),
            "gates": sorted(v for k, v in vars(cm).items() if k.startswith("GATE_")),
        },
        "verdict": verdict,
        "failure": failure,
        "verification_command":
            "PYTHONPATH=analysis python -c \"import json;"
            "from druglink import view_contract as vc;"
            "vc.validate(json.load(open('<view.json>')))\"",
        "this_receipt_is_not_admission_on_its_own":
            "admission is this receipt PLUS the full hash-bound view it names",
    }
    doc["receipt_sha256"] = content_hash(doc)
    return doc


def write(doc: Mapping[str, Any], path: str) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(canonical_json(doc) + "\n")
    return path
