"""THE STAGE-3 BRIDGE: a SEPARATE aggregate root, built AFTER the lanes are admitted.

WHY IT IS NOT WRITTEN INTO THE BUNDLES
--------------------------------------
An earlier version wrote ``stage3_rows.json`` INTO each native bundle directory. That is
wrong, and quietly destructive: adding a file to a bundle changes that bundle's file topology
AFTER its producer emitted it and AFTER its independent verifier admitted it — invalidating
exactly the bindings the admission rests on. W10's Direct report, the temporal admission and
the pathway admission all bind the tree they were shown.

The typed rows are a CONSUMER of admitted bytes, not part of them. So they live BESIDE the
lanes, in their own content-addressed root, BOUND BY HASH to: the native bundles they were
rebuilt from, the lane admissions that cleared those bundles, the Stage-1 release, and each
lane's exact identity/assay source.

The producer of this bridge admits nothing. ``verify_stage3_bridge`` reopens the admitted
native bytes and REBUILDS every row and context — because a self-hash proves only that a
document agrees with itself, and a forgery can be made to agree with itself.
"""
from __future__ import annotations

from typing import Any

from .stage3_rows import (
    DIRECT_IDENTITY_REQUIREMENT,
    ROW_RULE_ID,
    STAGE3_MATCHING_POLICY,
)

BRIDGE_FILE = "stage3_bridge.json"
BRIDGE_SCHEMA = "spot.stage02_stage3_bridge.v1"


def build_bridge(*, bindings: dict[str, Any], rows: list, contexts: list) -> dict[str, Any]:
    """The typed Stage-3 handoff, BOUND to the admitted native bytes it was rebuilt from."""
    import hashlib
    import json

    doc: dict[str, Any] = {
        "schema_version": BRIDGE_SCHEMA,
        "rule_id": ROW_RULE_ID,
        "matching_policy": STAGE3_MATCHING_POLICY,
        # WHAT IT WAS BUILT FROM: the native bundles + their file hashes, the lane admissions,
        # the Stage-1 hashes, and the exact identity/assay source of each lane.
        "bindings": bindings,
        "target_rows": list(rows),
        "n_target_rows": len(rows),
        "pathway_contexts": list(contexts),
        "n_pathway_contexts": len(contexts),
        "direct_identity_requirement": DIRECT_IDENTITY_REQUIREMENT,
        "verdict": "pending_independent_verification",
        "admitted": False,
        "self_admitted": False,
    }
    doc["bridge_sha256"] = hashlib.sha256(
        json.dumps(doc, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True).encode()).hexdigest()
    return doc
