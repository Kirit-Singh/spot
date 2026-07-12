"""Open Targets adapter -- DELIBERATELY NOT READY.

Open Targets Platform Data 26.06 no longer serves ``target.knownDrugs``; the
previous build parsed a shape that the current public API does not return. Rather
than guess at the replacement, this adapter:

  * declares status ``not_ready_no_pinned_response``;
  * refuses to parse ANY payload, producing an explicit ``unsupported_schema``
    disposition;
  * documents exactly what must be acquired before it can be written.

It will become real only when a network-permitted acquisition step caches an exact
pinned current response (or the release's drug/mechanism-of-action dataset files)
and a fixture is built from those bytes. Until then Open Targets contributes no
mechanism, no directness and no development state to any lane.
"""
from __future__ import annotations

from typing import Any

from . import base

SOURCE = "open_targets"
VERSION = "open_targets-adapter-v0-unready"

REQUIRED_BEFORE_READY = (
    "a pinned Open Targets Data 26.06 (or later) response or release file, "
    "acquired with URL + access record + byte hash, for the current "
    "drug / mechanismOfAction schema; target.knownDrugs no longer exists"
)


def parse_unsupported(raw: Any, entry: dict[str, Any], src_id: str) -> list[dict[str, Any]]:
    raise base.UnsupportedSchema(
        "open_targets adapter is not ready: " + REQUIRED_BEFORE_READY)


ADAPTERS = {
    "open_targets_known_drugs": base.Adapter(
        "open_targets_known_drugs", VERSION, SOURCE, base.NOT_READY,
        ("graphql:target.knownDrugs [REMOVED in Data 26.06]",), parse_unsupported,
        note=REQUIRED_BEFORE_READY),
    "open_targets_drug_moa": base.Adapter(
        "open_targets_drug_moa", VERSION, SOURCE, base.NOT_READY,
        ("graphql:drug.mechanismsOfAction [no pinned response acquired]",),
        parse_unsupported, note=REQUIRED_BEFORE_READY),
}
