"""Adapter registry and offline dispatch.

No adapter opens a socket. Each consumes raw bytes that a separate,
network-permitted acquisition step wrote, plus the manifest entry describing where
those bytes came from. A shape the adapter does not support raises
``UnsupportedSchema`` and becomes a disposition -- never a silent best-effort parse.
"""
from __future__ import annotations

import json
from typing import Any, Optional

from . import base, chembl, lanes, open_targets, pubchem, rxnorm, uniprot
from .base import (Adapter, FIXTURE_SHAPED, NOT_READY, PRODUCTION_READY,
                   RESEARCH_READY, UnsupportedSchema)

ADAPTERS: dict[str, Adapter] = {}
for _module in (chembl, uniprot, pubchem, rxnorm, open_targets, lanes):
    ADAPTERS.update(_module.ADAPTERS)


def adapter_for(name: str) -> Optional[Adapter]:
    return ADAPTERS.get(name)


def parse_raw(adapter: Adapter, data: bytes, entry: dict[str, Any],
              source_record_id: str) -> list[dict[str, Any]]:
    """Parse raw response bytes. Malformed JSON is an unsupported schema, not a crash."""
    try:
        raw = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UnsupportedSchema(f"raw response is not UTF-8 JSON: {exc}") from exc
    return adapter.parse(raw, entry, source_record_id)


__all__ = ["ADAPTERS", "Adapter", "FIXTURE_SHAPED", "NOT_READY", "PRODUCTION_READY",
           "RESEARCH_READY", "UnsupportedSchema", "adapter_for", "base", "parse_raw"]
