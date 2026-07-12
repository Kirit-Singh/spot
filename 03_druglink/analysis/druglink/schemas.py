"""Schema loading, cross-file $ref resolution, and schema-tree hashing.

Schemas are DATA, not instructions. They are loaded from disk, hashed, and the
hash of the whole schema tree is bound into every run ID, so a contract cannot be
loosened after the fact without changing the artifact identity.
"""
from __future__ import annotations

import functools
import json
import os
from typing import Any

import jsonschema
from jsonschema import Draft202012Validator

from .hashing import content_hash, tree_hash

_HERE = os.path.dirname(os.path.abspath(__file__))
STAGE3_SCHEMA_DIR = os.path.abspath(os.path.join(_HERE, "..", "..", "schemas"))
SHARED_SCHEMA_DIR = os.path.abspath(os.path.join(_HERE, "..", "..", "..", "schemas"))

ACQUISITION = "spot.stage03_acquisition_manifest.v1"

# Per-record JSON-schema validation was REPLACED by independent reconstruction in
# ``03_druglink/verifier/``: the verifier restates the contract and re-derives every
# arm fact, intervention effect, translation class and eligibility bit from the
# sources, which is strictly stronger than shape-checking the generator's own output
# against a schema the generator also ships. The document schema is retained because
# it enum-LOCKS the vocabularies, and its hash is bound into the bundle ID.


class SchemaError(ValueError):
    """A document or record does not satisfy its contract."""


@functools.lru_cache(maxsize=1)
def _store() -> dict[str, dict[str, Any]]:
    store: dict[str, dict[str, Any]] = {}
    for root in (STAGE3_SCHEMA_DIR, SHARED_SCHEMA_DIR):
        for name in sorted(os.listdir(root)):
            if not name.endswith(".json"):
                continue
            with open(os.path.join(root, name), "r", encoding="utf-8") as fh:
                schema = json.load(fh)
            sid = schema.get("$id") or name[:-5]
            store[sid] = schema
            store[name[:-5]] = schema
    return store


def load_schema(name: str) -> dict[str, Any]:
    store = _store()
    if name not in store:
        raise SchemaError(f"schema not found: {name}")
    return store[name]


@functools.lru_cache(maxsize=None)
def _validator(name: str, defs_key: str | None) -> Draft202012Validator:
    schema = load_schema(name)
    target: dict[str, Any] = schema
    if defs_key is not None:
        if defs_key not in schema.get("$defs", {}):
            raise SchemaError(f"{name} has no $defs/{defs_key}")
        target = dict(schema["$defs"][defs_key])
        target.setdefault("$defs", schema["$defs"])
    resolver = jsonschema.RefResolver(base_uri=schema.get("$id", ""),
                                      referrer=schema, store=dict(_store()))
    return Draft202012Validator(target, resolver=resolver)


def validate(instance: Any, schema_name: str, defs_key: str | None = None,
             context: str = "") -> Any:
    errors = sorted(_validator(schema_name, defs_key).iter_errors(instance),
                    key=lambda e: list(e.path))
    if errors:
        first = errors[0]
        loc = "/".join(str(p) for p in first.path) or "<root>"
        where = f"{context or schema_name}{'/' + defs_key if defs_key else ''}"
        raise SchemaError(f"{where}: {loc}: {first.message} "
                          f"({len(errors)} error(s))")
    return instance


@functools.lru_cache(maxsize=1)
def schemas_tree() -> dict[str, Any]:
    """Hash of every schema file Stage-3 validates against."""
    stage3 = tree_hash(STAGE3_SCHEMA_DIR, (".json",))
    shared = tree_hash(SHARED_SCHEMA_DIR, (".json",))
    return {
        "stage3_schema_files": stage3["files"],
        "shared_schema_files": shared["files"],
        "schemas_sha256": content_hash({"stage3": stage3["tree_sha256"],
                                        "shared": shared["tree_sha256"]}),
    }
