"""Independent resolver + hash-verifier for the Science evidence registry.

Separate implementation, per the generator/verifier separation rule: this module imports
NOTHING from ``druglink``. It restates the canonical-number rule and the record content
addressing from the specification and re-derives every hash from the bytes on disk.

A resolver that reused the writer's own hashing would prove only that the writer was
self-consistent — which is exactly the failure mode the registry exists to close.

Every link is checked, and every one fails CLOSED:

    the reference resolves in the registry index
    sha256(canonical bytes of the record content) == reference.science_evidence_sha256
    record.record_type                            == reference.record_type
    sha256(raw bytes on disk)                     == record.raw_sha256
    sha256(structured bytes on disk)              == record.structured_sha256

A missing record, an altered record, altered bytes, or a type mismatch is a failure.
Nothing warns and passes.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from decimal import Decimal
from typing import Any, Mapping, Optional

INDEX_FILE = "registry.json"

RECORD_TYPES = ("literature_support", "mechanistic_rationale", "contradiction",
                "uncertainty_note", "disease_context_review")
REF_FIELDS = ("science_evidence_id", "science_evidence_sha256", "record_type")
SELF_HASH_FIELDS = ("record_sha256",)


class RegistryVerifyError(ValueError):
    """The registry could not be read at all."""


# --------------------------------------------------------------------------- #
# The canonical-number rule, RESTATED (spot.stage03.canonical_number.v1).
# --------------------------------------------------------------------------- #
def _canonical_number(value: Any) -> str:
    if isinstance(value, bool):
        raise RegistryVerifyError("a bool is not a number")
    if isinstance(value, int):
        return format(Decimal(value).normalize(), "E")
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise RegistryVerifyError("non-finite number")
        # Shortest round-trip decimal, exact. No rounding.
        return format(Decimal(repr(value)).normalize(), "E")
    if isinstance(value, Decimal):
        return format(value.normalize(), "E")
    raise RegistryVerifyError(f"not a number: {value!r}")


def _canonicalise(node: Any) -> Any:
    if isinstance(node, bool) or node is None:
        return node
    if isinstance(node, (int, float, Decimal)):
        return _canonical_number(node)
    if isinstance(node, str):
        return node
    if isinstance(node, Mapping):
        return {str(k): _canonicalise(v) for k, v in node.items()}
    if isinstance(node, (list, tuple)):
        return [_canonicalise(v) for v in node]
    raise RegistryVerifyError(f"uncanonicalisable: {type(node).__name__}")


def canonical_bytes(obj: Any) -> bytes:
    return json.dumps(_canonicalise(obj), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def record_sha256(record: dict[str, Any]) -> str:
    return _sha(canonical_bytes(
        {k: v for k, v in record.items() if k not in SELF_HASH_FIELDS}))


# --------------------------------------------------------------------------- #
# Resolve + verify
# --------------------------------------------------------------------------- #
def load_index(registry_root: Optional[str]) -> dict[str, Any]:
    if not registry_root:
        raise RegistryVerifyError("no science-evidence registry root was supplied")
    path = os.path.join(registry_root, INDEX_FILE)
    if not os.path.isfile(path):
        raise RegistryVerifyError(f"no {INDEX_FILE} under {registry_root}")
    with open(path, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def verify_ref(registry_root: str, index: dict[str, Any],
               ref: dict[str, Any]) -> list[str]:
    """Resolve ONE reference and re-hash everything it points at. Returns failures."""
    where = str(ref.get("science_evidence_id"))
    fails: list[str] = []

    for field in REF_FIELDS:
        if not ref.get(field):
            fails.append(f"{where}: reference is missing {field}")
    if fails:
        return fails
    if ref["record_type"] not in RECORD_TYPES:
        return [f"{where}: record_type {ref['record_type']!r} is outside the closed enum"]

    entry = (index.get("records") or {}).get(where)
    if entry is None:
        return [f"{where}: REFERENCED but not present in the registry (dangling)"]

    record_path = os.path.join(registry_root, entry.get("record_file", ""))
    if not os.path.isfile(record_path):
        return [f"{where}: record file missing from the registry"]
    with open(record_path, "rb") as fh:
        record = json.loads(fh.read().decode("utf-8"))

    actual = record_sha256(record)
    if actual != ref["science_evidence_sha256"]:
        fails.append(
            f"{where}: record ALTERED — content hashes to {actual[:16]}…, reference "
            f"binds {str(ref['science_evidence_sha256'])[:16]}…")
    if str(record.get("record_type")) != ref["record_type"]:
        fails.append(
            f"{where}: record_type mismatch — registry {record.get('record_type')!r} vs "
            f"reference {ref['record_type']!r}")

    for kind, sha_field, file_field in (
            ("raw", "raw_sha256", "raw_file"),
            ("structured", "structured_sha256", "structured_file")):
        path = os.path.join(registry_root, entry.get(file_field, ""))
        if not os.path.isfile(path):
            fails.append(f"{where}: {kind} bytes missing from the registry")
            continue
        with open(path, "rb") as fh:
            data = fh.read()
        if _sha(data) != record.get(sha_field):
            fails.append(
                f"{where}: {kind} bytes ALTERED — they hash to {_sha(data)[:16]}…, the "
                f"record declares {str(record.get(sha_field))[:16]}…")

    # A record that cannot say who produced it cannot be attributed.
    prov = record.get("provenance") or {}
    for field in ("session_id", "model_id", "method_id"):
        if not prov.get(field):
            fails.append(f"{where}: record provenance is missing {field}")
    if not isinstance(prov.get("source_chain"), list):
        fails.append(f"{where}: record provenance.source_chain is not stated")

    return fails


def verify_refs(registry_root: Optional[str],
                refs: list[dict[str, Any]]) -> list[str]:
    """Resolve EVERY reference. An unresolvable reference is a failure, not a warning."""
    if not refs:
        return []
    try:
        index = load_index(registry_root)
    except RegistryVerifyError as exc:
        return [f"{len(refs)} Science record(s) referenced, but the registry could not "
                f"be read: {exc}"]
    fails: list[str] = []
    for ref in refs:
        fails += verify_ref(registry_root, index, ref)
    return fails


def collect_refs(rows: list[dict[str, Any]], field: str = "science_evidence_refs"
                 ) -> list[dict[str, Any]]:
    """Every typed reference carried by a set of emitted rows."""
    out: list[dict[str, Any]] = []
    for row in rows:
        for ref in (row.get(field) or []):
            if isinstance(ref, dict):
                out.append({k: ref.get(k) for k in REF_FIELDS})
    return out
