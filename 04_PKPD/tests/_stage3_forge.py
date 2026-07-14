"""Forge a Stage-3 bundle the way an attacker would — every hash repaired, deliberately.

A test that mutates a bundle and forgets to re-seal its hashes is testing the hash chain, not
the firewall the hash chain cannot enforce. So these helpers re-seal exactly what a real
tamperer would, and the tests assert the firewall STILL refuses. Shared by the admission and
combined-objective suites so the forge logic lives in one place.
"""

from __future__ import annotations

import json
import os
import shutil

from analysis.method_config import STAGE4_DIR
from analysis.stage3_contract import content_hash, table_hash
from analysis.stage3_contract_v2 import (
    CANDIDATE_CONTENT_KEYS,
    DISPLAY_COLUMNS,
    READ_TABLES,
    _rows as read_rows,
    sha256_file,
)

PINNED_BUNDLE = os.path.join(STAGE4_DIR, "tests", "fixtures", "stage3_annotation",
                             "s3_0b119088734643bf")


def copy_bundle(tmp_path) -> str:
    dst = os.path.join(tmp_path, os.path.basename(PINNED_BUNDLE))
    shutil.copytree(PINNED_BUNDLE, dst)
    return dst


def reseal(bundle: str) -> None:
    """Re-seal every hash the Stage-4 restatement checks, exactly as an attacker would.

    `canonical_content_sha256` and `bundle_id` are deliberately NOT touched: a combined
    objective KEY is not canonical content, so they do not move. That is the point of the
    document-key attack — see `reseal_fully` for the column attack, which does move them.
    """
    doc_path = os.path.join(bundle, "drug_annotation.json")

    with open(doc_path, encoding="utf-8") as fh:
        doc = json.load(fh)
    doc["document_sha256"] = content_hash(
        {k: v for k, v in doc.items() if k != "document_sha256"})
    with open(doc_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)

    reseal_manifest(bundle)


def reseal_manifest(bundle: str) -> None:
    """Repair every file_sha256 and the manifest self-hash. The document is left as-is."""
    man_path = os.path.join(bundle, "manifest.json")
    with open(man_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    for entry in manifest.get("files", []):
        entry["file_sha256"] = sha256_file(os.path.join(bundle, entry["file"]))
    manifest["manifest_sha256"] = content_hash(
        {k: v for k, v in manifest.items() if k not in ("manifest_sha256", "created_at")})
    with open(man_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)


def edit_doc(bundle: str, mutate) -> None:
    path = os.path.join(bundle, "drug_annotation.json")
    with open(path, encoding="utf-8") as fh:
        doc = json.load(fh)
    mutate(doc)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)
    reseal(bundle)


def reseal_fully(bundle: str) -> None:
    """Re-seal the table hashes and canonical content too — a bundle sealed as Stage 3 would.

    A banned COLUMN in a CONSUMED table *is* canonical content — it changes the table's
    content hash, which lives inside canonical content. So a column attack that stops at
    `reseal` is caught by the table-hash check, and a test that stopped there would be testing
    the wrong gate. The real threat for a column is not a tamperer but an upstream Stage 3
    that EMITS one, every hash legitimately consistent from birth. This reproduces exactly
    that, so the column scan is the only thing left standing.
    """
    doc_path = os.path.join(bundle, "drug_annotation.json")
    with open(doc_path, encoding="utf-8") as fh:
        doc = json.load(fh)

    for table, sort_keys in READ_TABLES.items():
        rows = read_rows(bundle, table)
        if not rows:
            continue
        cols = [c for c in rows[0] if c not in DISPLAY_COLUMNS]
        keys = tuple(k for k in sort_keys if k in cols) or (cols[0],)
        doc["table_hashes"][table] = table_hash(
            [{c: r.get(c) for c in cols} for r in rows], keys)

    canonical = {
        "schema_version": doc["schema_version"],
        "artifact_class": doc["artifact_class"],
        "upstream": doc["upstream"],
        "acquisition": doc["acquisition"],
        "pathway_hypotheses": doc["pathway_hypotheses"],
        "stage2_joint_context": doc["stage2_joint_context"],
        "science_evidence_registry": doc["science_evidence_registry"],
        "disease_context_review": doc["disease_context_review"],
        "method": doc["method"],
        "deferred_lanes": dict(sorted(doc["deferred_lanes"].items())),
        "table_hashes": dict(sorted(doc["table_hashes"].items())),
        "candidates": [{k: c[k] for k in CANDIDATE_CONTENT_KEYS} for c in doc["candidates"]],
    }
    doc["canonical_content_sha256"] = content_hash(canonical)
    doc["bundle_id"] = "s3_" + doc["canonical_content_sha256"][:16]
    with open(doc_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, sort_keys=True)

    man_path = os.path.join(bundle, "manifest.json")
    with open(man_path, encoding="utf-8") as fh:
        manifest = json.load(fh)
    manifest["bundle_id"] = doc["bundle_id"]
    with open(man_path, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)

    reseal(bundle)  # document_sha256, every file_sha256, manifest_sha256
