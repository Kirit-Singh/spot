"""A content-addressed registry for referenced Claude Science evidence records.

Before this module, a Science reference was checked for SHAPE only: an id, a hex string
that looked like a hash, and a record type. Nothing ever opened the record. A reference
to a record that did not exist, or to bytes that had since changed, passed every check —
so the hash in the reference was decoration, not a binding.

A record is now RESOLVED and its bytes are RE-HASHED. The registry stores, per record:

  * ``provenance`` — the session, model, method and source chain that produced it;
  * the **raw** record bytes (what Claude Science actually emitted);
  * the **structured** record bytes (the typed form a consumer reads).

Both byte streams are hashed. The record document itself is content-addressed by
``canonical_sha256`` over its own content (excluding its self-hash), and THAT is the
``science_evidence_sha256`` a reference must carry.

Verification is therefore a chain, and every link is re-derived from bytes on disk:

    reference.science_evidence_id   -> a record exists in the registry
    reference.science_evidence_sha256 == canonical_sha256(record content)
    reference.record_type           == record.record_type
    record.raw_sha256               == sha256(raw bytes on disk)
    record.structured_sha256        == sha256(structured bytes on disk)

A missing record, an altered record, an altered byte stream, or a type mismatch is a
**typed refusal**. Nothing warns and passes.

This module WRITES and reads the registry. ``verifier/science_registry.py`` verifies it
with a SEPARATE implementation that imports nothing from this package — a resolver that
trusted the writer's own hashing would only prove the writer was self-consistent.
"""
from __future__ import annotations

import json
import os
from typing import Any, Iterable, Optional

from .canonical_number import canonical_bytes, canonical_sha256  # noqa: F401
from .hashing import sha256_hex

REGISTRY_SCHEMA = "spot.science_evidence_registry.v1"
RECORD_SCHEMA = "spot.science_evidence_record.v1"

INDEX_FILE = "registry.json"
RECORDS_DIR = "records"

# CLOSED enum. A record type outside this set is not a Science evidence record.
RECORD_TYPES = ("literature_support", "mechanistic_rationale", "contradiction",
                "uncertainty_note", "disease_context_review")

# The reference triple. An id alone is not a binding.
REF_FIELDS = ("science_evidence_id", "science_evidence_sha256", "record_type")

# Excluded from the record's own content hash (it cannot contain its own hash).
SELF_HASH_FIELDS = ("record_sha256",)


class ScienceRegistryError(ValueError):
    """A Science evidence record is missing, altered, mistyped, or unresolvable."""


# --------------------------------------------------------------------------- #
# Typed references
# --------------------------------------------------------------------------- #
def check_ref(where: str, ref: Any) -> dict[str, str]:
    """A Science reference is a TYPED TRIPLE. An embedded blob is not a reference."""
    if not isinstance(ref, dict):
        raise ScienceRegistryError(
            f"{where}: a Claude Science reference must be a typed record "
            f"{{science_evidence_id, science_evidence_sha256, record_type}}, not "
            f"{type(ref).__name__}. Interpretation is referenced, never embedded.")
    for field in REF_FIELDS:
        if not ref.get(field):
            raise ScienceRegistryError(
                f"{where}: science evidence reference is missing {field!r}. A record "
                "that is not identifiable and content-hashed cannot be verified or "
                "attributed.")
    if ref["record_type"] not in RECORD_TYPES:
        raise ScienceRegistryError(
            f"{where}: record_type={ref['record_type']!r} is not one of "
            f"{list(RECORD_TYPES)}. It is a CLOSED enum.")
    sha = str(ref["science_evidence_sha256"])
    if len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
        raise ScienceRegistryError(
            f"{where}: science_evidence_sha256={sha!r} is not a SHA-256 hex digest.")
    return {f: str(ref[f]) for f in REF_FIELDS}


def check_refs(where: str, refs: Any) -> list[dict[str, str]]:
    """Normalise a list of typed references, or refuse."""
    if refs is None:
        return []
    if not isinstance(refs, list):
        raise ScienceRegistryError(
            f"{where}: science_evidence_refs must be a list of TYPED references — never "
            "an embedded object or free-form string.")
    return [check_ref(where, ref) for ref in refs]


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #
def record_content(record: dict[str, Any]) -> dict[str, Any]:
    """Everything the record's content hash commits to (never its own hash)."""
    return {k: v for k, v in record.items() if k not in SELF_HASH_FIELDS}


def record_sha256(record: dict[str, Any]) -> str:
    """Content-address a record. This is the ``science_evidence_sha256`` a ref carries."""
    return canonical_sha256(record_content(record))


def build_record(*, science_evidence_id: str, record_type: str,
                 provenance: dict[str, Any], raw: bytes,
                 structured: Any) -> dict[str, Any]:
    """Assemble one Science evidence record and content-address it.

    ``raw`` is exactly what Claude Science emitted. ``structured`` is the typed form; it
    is stored as CANONICAL bytes, so its hash cannot drift with a serialiser's mood.
    """
    if record_type not in RECORD_TYPES:
        raise ScienceRegistryError(
            f"record_type={record_type!r} is not one of {list(RECORD_TYPES)}")
    for field in ("session_id", "model_id", "method_id"):
        if not provenance.get(field):
            raise ScienceRegistryError(
                f"{science_evidence_id}: provenance.{field} is required. A Science "
                "record whose session/model/method is unknown cannot be attributed.")
    if not isinstance(provenance.get("source_chain"), list):
        raise ScienceRegistryError(
            f"{science_evidence_id}: provenance.source_chain must be a list (it may be "
            "empty, but it must be stated).")

    structured_bytes = canonical_bytes(structured)
    record: dict[str, Any] = {
        "schema_version": RECORD_SCHEMA,
        "science_evidence_id": science_evidence_id,
        "record_type": record_type,
        "provenance": {
            "session_id": str(provenance["session_id"]),
            "model_id": str(provenance["model_id"]),
            "method_id": str(provenance["method_id"]),
            "source_chain": list(provenance["source_chain"]),
        },
        "raw_sha256": sha256_hex(raw),
        "raw_bytes": len(raw),
        "raw_media_type": str(provenance.get("raw_media_type") or "text/plain"),
        "structured_sha256": sha256_hex(structured_bytes),
        "structured_bytes": len(structured_bytes),
    }
    record["record_sha256"] = record_sha256(record)
    return record


def write(registry_root: str, records: Iterable[tuple[dict[str, Any], bytes, Any]]
          ) -> dict[str, Any]:
    """Write a registry: one index plus, per record, its raw and structured bytes."""
    os.makedirs(os.path.join(registry_root, RECORDS_DIR), exist_ok=True)
    index: dict[str, Any] = {"schema_version": REGISTRY_SCHEMA, "records": {}}

    for record, raw, structured in records:
        sha = record["record_sha256"]
        base = os.path.join(registry_root, RECORDS_DIR, sha)
        with open(f"{base}.record.json", "wb") as fh:
            fh.write(canonical_bytes(record))
        with open(f"{base}.raw", "wb") as fh:
            fh.write(raw)
        with open(f"{base}.structured.json", "wb") as fh:
            fh.write(canonical_bytes(structured))
        index["records"][record["science_evidence_id"]] = {
            "record_sha256": sha,
            "record_type": record["record_type"],
            "record_file": f"{RECORDS_DIR}/{sha}.record.json",
            "raw_file": f"{RECORDS_DIR}/{sha}.raw",
            "structured_file": f"{RECORDS_DIR}/{sha}.structured.json",
        }

    with open(os.path.join(registry_root, INDEX_FILE), "wb") as fh:
        fh.write(canonical_bytes(index))
    return index


def load_index(registry_root: Optional[str]) -> dict[str, Any]:
    """Open the registry index, or refuse. A missing registry is not an empty one."""
    if not registry_root:
        raise ScienceRegistryError(
            "no science-evidence registry was supplied, but Science records are "
            "referenced. A reference that cannot be resolved is not a binding.")
    path = os.path.join(registry_root, INDEX_FILE)
    if not os.path.isfile(path):
        raise ScienceRegistryError(
            f"no {INDEX_FILE} in the science-evidence registry root: {registry_root}")
    with open(path, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def resolve(registry_root: str, ref: dict[str, str]) -> dict[str, Any]:
    """Resolve ONE typed reference and RE-HASH the bytes it points at, or refuse.

    Every link is re-derived from bytes on disk. A missing record, an altered record, an
    altered byte stream, or a type mismatch fails closed.
    """
    index = load_index(registry_root)
    entry = (index.get("records") or {}).get(ref["science_evidence_id"])
    if entry is None:
        raise ScienceRegistryError(
            f"science evidence {ref['science_evidence_id']!r} is REFERENCED but is not "
            "in the registry. A dangling reference is not evidence.")

    record_path = os.path.join(registry_root, entry["record_file"])
    if not os.path.isfile(record_path):
        raise ScienceRegistryError(
            f"science evidence {ref['science_evidence_id']!r}: its record file is "
            "missing from the registry.")
    with open(record_path, "rb") as fh:
        record = json.loads(fh.read().decode("utf-8"))

    # The record must hash to what the REFERENCE claims. This is the binding.
    actual = record_sha256(record)
    if actual != ref["science_evidence_sha256"]:
        raise ScienceRegistryError(
            f"science evidence {ref['science_evidence_id']!r} was ALTERED: the record "
            f"content hashes to {actual[:16]}…, but the reference binds "
            f"{ref['science_evidence_sha256'][:16]}…. A record that no longer matches "
            "its reference is not the record that was cited.")
    if str(record.get("record_type")) != ref["record_type"]:
        raise ScienceRegistryError(
            f"science evidence {ref['science_evidence_id']!r}: the registry says "
            f"record_type={record.get('record_type')!r}, the reference says "
            f"{ref['record_type']!r}.")

    # ...and the stored byte streams must hash to what the RECORD declares.
    for kind, sha_field, file_field in (
            ("raw", "raw_sha256", "raw_file"),
            ("structured", "structured_sha256", "structured_file")):
        path = os.path.join(registry_root, entry[file_field])
        if not os.path.isfile(path):
            raise ScienceRegistryError(
                f"science evidence {ref['science_evidence_id']!r}: its {kind} bytes are "
                "missing from the registry.")
        with open(path, "rb") as fh:
            data = fh.read()
        if sha256_hex(data) != record[sha_field]:
            raise ScienceRegistryError(
                f"science evidence {ref['science_evidence_id']!r}: its {kind} bytes were "
                f"ALTERED (they hash to {sha256_hex(data)[:16]}…, the record declares "
                f"{str(record[sha_field])[:16]}…).")

    return record


def resolve_all(registry_root: Optional[str], refs: list[dict[str, str]],
                where: str = "") -> list[dict[str, Any]]:
    """Resolve every reference, or refuse. Nothing is resolved 'best effort'."""
    if not refs:
        return []
    if not registry_root:
        raise ScienceRegistryError(
            f"{where}: {len(refs)} Science record(s) are referenced but no registry was "
            "supplied. An unresolvable reference is not a binding.")
    return [resolve(registry_root, ref) for ref in refs]


def registry_ref(registry_root: Optional[str]) -> dict[str, Any]:
    """The registry block bound into the Stage-3 bundle. No local paths."""
    if not registry_root:
        return {"science_registry": "not_provided", "n_records": 0}
    index = load_index(registry_root)
    records = index.get("records") or {}
    return {
        "science_registry": "provided",
        "science_registry_schema": REGISTRY_SCHEMA,
        "science_registry_sha256": canonical_sha256(index),
        "n_records": len(records),
        "record_types": sorted({e["record_type"] for e in records.values()}),
    }
