"""The canonical contributing-guide manifest: the ONLY source of guide identity.

The released by-guide object carries no per-row sgRNA identity. The public CZI v1.0.0
release README DOES define the slots — guide_1/guide_2 by alphanumeric guide-ID rank,
and the donor modalities by named donor pairs (``data_sharing_readme.md``, sha256
9275bad99701534e109691f2ce6ff8c474dacb3912e9a6f22cbaa009237ceab7, lines 135-153). That
rank is a PUBLISHED rule, not a guess, and any comment in this lane still calling it one
is wrong. What it is not is evidence of which guide contributed to which estimate — the
thing a mask actually needs — so Stage-2 still takes guide identity only from an
explicit manifest that:

  * pins every source by name + immutable revision + SHA-256;
  * covers EXACTLY the GLOBAL all-condition POOLED-MAIN released scope universe
    (``domain.py``) — no extra scope, no missing scope, no duplicate scope, no null
    key. This is NOT the selected-condition main+guide+donor universe: the audited
    artifact is pooled-main only, and demanding it cover the support estimates was the
    P0 bug;
  * proves each determined row (identity_method + source_sha256 + evidence_state) and
    RESOLVES its citation against a hash-pinned source-record table whose ids bind
    their own completeness proof (``record_id.py``), and which the raw source itself
    has confirmed COMPLETE (``replay.py``), not merely existent.

Anything else fails closed. A row whose evidence is ambiguous makes THAT estimate
unavailable; it never silently changes another estimate, and it never changes the
pooled primary.

This module LOADS and BINDS. The frozen vocabulary lives in ``manifest_schema`` and
the refusals in ``manifest_validate``; both are re-exported here, so ``manifest`` is
still the one name the rest of the lane imports.

A manifest emitted by an unaudited or quarantined process must not be used: the
checks here are structural, and they cannot certify that a well-formed manifest
is scientifically correct.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from . import domain, sources
from .hashing import content_hash, file_sha256
from .manifest_schema import (  # noqa: F401  (the frozen vocabulary, re-exported)
    ADMISSIBLE_IDENTITY_METHODS, ALLOWED_IDENTITY_METHODS, AMBIGUOUS, DETERMINED,
    EVIDENCE_STATES, MUTABLE_REVISIONS, NON_NULL_ROW_KEYS, PROOF_ROW_KEYS,
    QUARANTINED_SOURCES, REPLAY_COMPLETE, REPLAY_COMPLETENESS_KEYS, REPLAY_REPLAYED,
    REPLAY_SCHEMA, REQUIRED_ROW_KEYS, SCHEMA_PREFIX, SCHEMA_VERSION,
    SOURCE_CLASS_MARSON, SOURCE_CLASSES, SOURCE_RECORD_TABLE_SCHEMA,
    SUPERSEDED_REPLAY_SCHEMAS, SUPERSEDED_SCHEMA_VERSIONS,
    ManifestError, canonical_row_key, canonical_rows, is_nullish, require,
    scope_of)
from .manifest_replay import validate_replay          # noqa: F401  (the release gate)
from .manifest_validate import (  # noqa: F401
    validate_rows, validate_sources)

_require = require          # the historical private name, kept for call sites


def load(path: Optional[str],
         released_scopes: Optional[set[tuple]] = None,
         source_registry: Optional[dict[str, dict]] = None,
         base_dir: str = "",
         source_records_path: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Load, independently verify, validate AND RESOLVE the manifest.

    Structural validity is not evidence. Every determined row is resolved against
    the hash-pinned source-record table (``sources.py``): the cited record must
    exist and must itself carry the full estimate key and the same guide identity.
    """
    if not path:
        return None
    with open(path) as fh:
        doc = json.load(fh)
    require(isinstance(doc, dict),
            "contributor manifest: top level must be an object carrying "
            "'sources' and 'rows'")
    schema = str(doc.get("schema_version", ""))
    require(schema not in SUPERSEDED_SCHEMA_VERSIONS,
            f"contributor manifest: schema_version {schema!r} is SUPERSEDED. Its "
            "citations name source-record ids minted under the obsolete rule "
            "(a truncated digest over a payload that omitted the offset proof), so a "
            "record's evidence could be swapped without changing the id that cites "
            f"it. Re-issue the pair under {SCHEMA_VERSION!r}; superseded ids are never "
            "grandfathered")
    require(schema == SCHEMA_VERSION,
            f"contributor manifest: schema_version must be exactly "
            f"{SCHEMA_VERSION!r}, got {schema!r}")

    # The manifest must say WHICH source-record schema its citations resolve in, and
    # it must be the one the table actually is. The superseded pair declared
    # 'spot.stage02_source_records.target_id_proposal.v1' over a table that said
    # 'spot.stage02_source_records.v1' — two names for the evidence, and nothing
    # comparing them.
    declared_table_schema = str(doc.get("source_record_table_schema_version", ""))
    require(declared_table_schema == SOURCE_RECORD_TABLE_SCHEMA,
            f"contributor manifest: 'source_record_table_schema_version' must be "
            f"exactly {SOURCE_RECORD_TABLE_SCHEMA!r}, got "
            f"{declared_table_schema!r}; a manifest that names a different evidence "
            "schema than the table it cites is not resolvable")

    source_class = doc.get("source_class")
    require(source_class in SOURCE_CLASSES,
            f"contributor manifest: 'source_class' must be one of "
            f"{list(SOURCE_CLASSES)}, got {source_class!r}")

    declared_sources = validate_sources(doc.get("sources"), source_registry, base_dir)
    source_shas = {s["name"]: s["sha256"] for s in declared_sources}
    rows = doc.get("rows")
    validate_rows(rows, released_scopes, source_shas, str(source_class))

    # RESOLVE the cited evidence. A locator is not a proof because it is a string.
    table_name = doc.get("source_record_table")
    require(bool(table_name),
            "contributor manifest: 'source_record_table' is required; it names the "
            "hash-pinned source-record table that its citations must resolve in")
    require(str(table_name) in source_shas,
            f"contributor manifest: source_record_table {table_name!r} is not one "
            "of the manifest's verified sources")
    if source_records_path is None:
        pin = (source_registry or {}).get(str(table_name)) or {}
        source_records_path = os.path.join(base_dir, str(pin.get("path", "")))
    table = sources.load_table(source_records_path)
    resolution = sources.resolve_manifest(rows, table, source_shas)
    replay = validate_replay(doc, rows, table, source_shas, source_registry,
                             base_dir, str(table_name), released_scopes)

    ordered = canonical_rows(rows)
    return {
        "schema_version": schema,
        "source_record_table_schema_version": declared_table_schema,
        "identity_method": doc.get("identity_method"),
        "source_class": str(source_class),
        "evidence_domain": domain.DOMAIN_ID,
        "source_record_table": str(table_name),
        "source_replay_report": str(doc.get("source_replay_report")),
        "sources": declared_sources,
        "rows": ordered,
        "resolution": resolution,
        "source_replay": replay,
        "manifest_sha256": file_sha256(path),
        # Recomputed from the parsed content, independent of any self-declared hash,
        # and over CANONICALLY ORDERED rows and sources: reordering or reformatting
        # the file is not a different scientific input.
        "canonical_sha256": content_hash({
            "schema_version": schema,
            "source_record_table_schema_version": declared_table_schema,
            "source_class": str(source_class),
            "evidence_domain": domain.DOMAIN_ID,
            "source_record_table": str(table_name),
            "source_replay_report": str(doc.get("source_replay_report")),
            "sources": declared_sources,
            "rows": ordered,
        }),
        "n_rows": len(ordered),
        "n_scopes": len({scope_of(r) for r in ordered}),
    }


# Absence is a STATE, emitted as enums and flags — not a paragraph. With no manifest,
# guide identity is unavailable, every main estimate is mask_unresolved, and no target
# is eligible; the lane still never infers identity from a slot name.
ABSENT_BLOCK = {
    "status": "absent",
    "identity_method": None,
    "sources": [],
    "guide_identity_available": False,
    "eligible_targets_possible": False,
}


def binding_block(doc: Optional[dict[str, Any]]) -> dict[str, Any]:
    """What run_id binds about guide identity — the SEMANTICS, including absence.

    The manifest's raw FILE hash is deliberately not here. Re-indenting the file, or
    listing the same rows in another order, is not a different scientific input, and
    must not produce a different run_id. What is bound instead is the canonical hash
    — taken over canonically ordered rows and sources — plus the byte hashes of the
    PINNED upstream artifacts (the raw source, the source-record table, the replay
    report), which genuinely are the evidence. The raw manifest hash is kept in
    provenance for audit.
    """
    if doc is None:
        return dict(ABSENT_BLOCK)
    return {
        "status": "bound",
        "schema_version": doc["schema_version"],
        "source_record_table_schema_version":
            doc["source_record_table_schema_version"],
        "identity_method": doc["identity_method"],
        "source_class": doc["source_class"],
        "evidence_domain": doc["evidence_domain"],
        "source_record_table": doc["source_record_table"],
        "source_replay_report": doc["source_replay_report"],
        "canonical_sha256": doc["canonical_sha256"],
        "allowed_identity_methods": list(ALLOWED_IDENTITY_METHODS),
        "admissible_identity_methods":
            list(ADMISSIBLE_IDENTITY_METHODS[doc["source_class"]]),
        "sources": doc["sources"],
        "evidence_resolution": doc["resolution"],
        "source_replay": doc["source_replay"],
        "n_rows": doc["n_rows"],
        "n_scopes": doc["n_scopes"],
    }


def provenance_block(doc: Optional[dict[str, Any]]) -> dict[str, Any]:
    """The binding, plus the exact bytes the manifest arrived as (audit only)."""
    if doc is None:
        return dict(ABSENT_BLOCK, manifest_sha256=None)
    return dict(binding_block(doc), manifest_sha256=doc["manifest_sha256"])
