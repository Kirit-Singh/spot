"""The AUTHORITATIVE Stage-3 membership receipt. W6 consumes this exact schema.

A contract document is not admission. A gate that RAN leaves a receipt; a gate that was skipped
leaves nothing — and from the outside those look identical unless something names the bytes it
judged. This is that something.

GENERATOR IS NOT VERIFIER — and it is named, not asserted. `generator_is_not_verifier: true` is a
BOOLEAN a producer can simply write. Two explicit ids, required to differ, are a FACT a reader can
check. A producer that verifies its own output has not been verified.

PATHS ARE BUNDLE-RELATIVE. An absolute path is not portable and is not evidence: it names a place
on one machine. Every artifact ref resolves against the bundle directory the receipt sits in.
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
SELF_HASH_FIELD = "receipt_sha256"

GENERATOR_ID = "spot.stage03.selection_view.producer.v1"
VERIFIER_ID = cm.MEMBERSHIP_VERIFIER_ID
ADMIT, REFUSE = "admit", "refuse"

# The tables a downstream typed-evidence check reads. A corroboration from a table the receipt
# never covered comes from unverified bytes.
CORROBORATING_TABLES = ("candidates", "arm_summaries")


def _git(*args: str) -> str:
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True,
                             cwd=os.path.dirname(os.path.abspath(__file__)))
        return out.stdout.strip()
    except Exception:                                    # pragma: no cover - environment only
        return ""


def emit(*, view_path: str, bundle_dir: str | None = None) -> dict[str, Any]:
    """Judge the view; return the receipt. A refusal is a VERDICT, never a crash."""
    view_path = os.path.abspath(view_path)
    bundle_dir = os.path.abspath(bundle_dir or os.path.dirname(view_path))

    with open(view_path, encoding="utf-8") as fh:
        view = json.load(fh)

    verdict, failure = ADMIT, None
    try:
        vc.validate(dict(view))            # schema + rows + seal + membership v2 + browser
    except Exception as exc:
        verdict, failure = REFUSE, str(exc)[:400]

    store = view.get("store") or {}
    tables = dict(store.get("table_hashes") or {})
    uncovered = [t for t in CORROBORATING_TABLES if not tables.get(t)]

    doc: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA,
        # TWO IDS, NAMED AND UNEQUAL. Not a boolean the producer could simply assert.
        "generator_id": GENERATOR_ID,
        "verifier_id": VERIFIER_ID,
        "generator_is_not_verifier": GENERATOR_ID != VERIFIER_ID,
        "verdict": verdict,
        "failure": failure,
        "artifact_class": view.get("artifact_class"),

        "code_commit": _git("rev-parse", "HEAD") or "unknown",
        "producer_tree_is_clean": _git("status", "--porcelain") == "",

        # BUNDLE-RELATIVE. An absolute path names a place on one machine, not an artifact.
        "view": {
            "path": os.path.relpath(view_path, bundle_dir),
            "raw_sha256": file_sha256(view_path),
            "canonical_sha256": content_hash(view),
            "view_id": view.get("view_id"),
            "view_content_sha256": view.get("view_content_sha256"),
        },
        "store": {
            "universe_store_id": store.get("universe_store_id") or store.get("store_id"),
            "document_sha256": store.get("document_sha256"),
            "store_manifest_sha256": store.get("store_manifest_sha256"),
            "selection_view_vocabulary_digest":
                store.get("selection_view_vocabulary_digest"),
            "table_hashes": tables,
            "corroborating_tables": list(CORROBORATING_TABLES),
            "corroborating_tables_uncovered": uncovered,
        },
        "membership": {
            "schema": cm.MEMBERSHIP_SCHEMA,
            "rule_id": cm.MEMBERSHIP_RULE_ID,
            "verifier_id": cm.MEMBERSHIP_VERIFIER_ID,
            "retired_ids": sorted(cm.RETIRED_MEMBERSHIP_IDS),
            "vocabulary_digest_in_force": content_hash(sv.vocabularies()),
            "gates": sorted(v for k, v in vars(cm).items() if k.startswith("GATE_")),
        },
        "verification_command": (
            "PYTHONPATH=analysis python -c \"import json;"
            "from druglink import view_contract as vc;"
            "vc.validate(json.load(open('<view.json>')))\""),
        "this_receipt_is_not_admission_on_its_own":
            "admission is this receipt PLUS the full hash-bound view it names",
    }
    # The self-hash covers EVERYTHING except itself. A hash cannot cover itself.
    doc[SELF_HASH_FIELD] = content_hash({k: v for k, v in doc.items()
                                         if k != SELF_HASH_FIELD})
    return doc


def verify(receipt: Mapping[str, Any], *, bundle_dir: str) -> None:
    """Re-derive the receipt's OWN identity and the bytes it names. Never read a claim."""
    body = {k: v for k, v in receipt.items() if k != SELF_HASH_FIELD}
    if content_hash(body) != receipt.get(SELF_HASH_FIELD):
        raise ValueError("[the_receipt_does_not_recompute_its_own_identity] it was edited after "
                         "it was addressed")
    if receipt.get("generator_id") == receipt.get("verifier_id"):
        raise ValueError("[the_receipt_is_self_signed] a producer that verifies its own output "
                         "has not been verified")
    if receipt.get("verdict") != ADMIT:
        raise ValueError(f"[the_receipt_did_not_admit] verdict={receipt.get('verdict')!r}")
    ref = (receipt.get("view") or {}).get("path")
    path = os.path.join(bundle_dir, str(ref))
    if file_sha256(path) != (receipt.get("view") or {}).get("raw_sha256"):
        raise ValueError("[the_view_on_disk_is_not_the_view_the_receipt_judged]")


def write(doc: Mapping[str, Any], path: str) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(canonical_json(doc) + "\n")
    return path
