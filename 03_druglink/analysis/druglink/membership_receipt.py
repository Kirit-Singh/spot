"""The INDEPENDENT receipt, in W6\'s schema. ONE contract, and it is THEIRS.

Stage-4 hardcodes `spot.stage03_independent_receipt.v2`. I had emitted
`spot.stage03_membership_receipt.v1` — a second, private shape for the same artifact. Two schemas
for one handoff is how a chain silently breaks: each side verifies happily against its own idea of
the document and neither is verifying the other.

So this adopts W6\'s schema EXACTLY — their field names, their SELF_HASH_FIELD, their canonical
hash rule (plain sha256 over sort_keys/compact JSON, NOT Stage-3\'s content_hash, which rejects
floats because it addresses OUR scientific content and would refuse an honest receipt for speaking
the shared language).

GENERATOR IS NOT VERIFIER. W6 refuses a receipt whose `generated_by` equals its `verifier_id`, and
they are right to: a producer that verifies its own output has not been verified. It also refuses a
DIRTY producer tree — a receipt that cannot name reproducible bytes names nothing.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
from typing import Any, Mapping

from . import candidate_membership as cm
from . import selection_view as sv
from . import view_contract as vc
from .hashing import content_hash, file_sha256

# W6\'s contract. Read from their source, not negotiated.
RECEIPT_SCHEMA = "spot.stage03_independent_receipt.v2"
SELF_HASH_FIELD = "self_sha256"
GENERATED_BY = "spot.stage03.selection_view.producer.v1"        # the PRODUCER
VERIFIER_ID = cm.MEMBERSHIP_VERIFIER_ID                          # the INDEPENDENT verifier
ADMIT, REFUSE = "admit", "refuse"

# W6 reads these tables for its typed evidence-class check. A corroboration drawn from a table the
# receipt never covered comes from unverified bytes.
CORROBORATING_TABLES = ("candidates", "arm_summaries")


def canonical_sha256(doc: Mapping[str, Any]) -> str:
    """W6\'s rule, verbatim: sha256 over sort_keys / compact JSON."""
    return hashlib.sha256(
        json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _git(*args: str) -> str:
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True,
                             cwd=os.path.dirname(os.path.abspath(__file__)))
        return out.stdout.strip()
    except Exception:                                    # pragma: no cover - environment only
        return ""


def emit(*, view_path: str) -> dict[str, Any]:
    """Judge the view at this path; return a receipt in W6\'s schema. A refusal is a VERDICT."""
    with open(view_path, encoding="utf-8") as fh:
        view = json.load(fh)

    verdict, failure = ADMIT, None
    try:
        vc.validate(dict(view))               # schema + rows + seal + membership v2 + browser
    except Exception as exc:                  # a refusal is recorded, never raised
        verdict, failure = REFUSE, str(exc)[:400]

    store = view.get("store") or {}
    tables = dict(store.get("table_hashes") or {})
    doc: dict[str, Any] = {
        "receipt_schema": RECEIPT_SCHEMA,
        "universe_store_id": store.get("universe_store_id") or store.get("store_id"),
        "store_canonical_content_sha256": store.get("document_sha256"),
        "table_hashes": tables,
        "view_raw_sha256": file_sha256(view_path),
        "view_canonical_sha256": canonical_sha256(view),
        "view_id": view.get("view_id"),
        "membership_contract": {
            "schema": cm.MEMBERSHIP_SCHEMA,
            "rule_id": cm.MEMBERSHIP_RULE_ID,
            "verifier_id": cm.MEMBERSHIP_VERIFIER_ID,
            "retired_ids": sorted(cm.RETIRED_MEMBERSHIP_IDS),
            "vocabulary_digest_in_force": content_hash(sv.vocabularies()),
            "gates": sorted(v for k, v in vars(cm).items() if k.startswith("GATE_")),
        },
        "verifier_id": VERIFIER_ID,
        "verifier_verdict": verdict,
        "generated_by": GENERATED_BY,
        "producer_commit": _git("rev-parse", "HEAD") or "unknown",
        "producer_tree_is_clean": _git("status", "--porcelain") == "",
        "artifact_class": view.get("artifact_class"),
        "failure": failure,
        "verification_command": (
            "PYTHONPATH=analysis python -c \"import json;"
            "from druglink import view_contract as vc;"
            "vc.validate(json.load(open('<view.json>')))\""),
        "this_receipt_is_not_admission_on_its_own":
            "admission is this receipt PLUS the full hash-bound view it names",
    }
    doc[SELF_HASH_FIELD] = canonical_sha256({k: v for k, v in doc.items()
                                             if k != SELF_HASH_FIELD})
    return doc


def write(doc: Mapping[str, Any], path: str) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path
