"""THE THREE NATIVE BUNDLE SHAPES, and one normalized view of them.

THE DEFECT THIS CLOSES
----------------------
The aggregate identified a bundle's lane by reading a top-level ``lane`` key, and its id by
reading ``bundle_id``. **Only the temporal producer emits either.** On real bytes:

    discover(direct)  -> []          Direct  emits `condition` + `arm_bundle_run_id`
    discover(temporal)-> [6 bundles] temporal emits `lane` + `bundle_id` + `context`
    discover(pathway) -> []          pathway emits `condition` + `source` + `pathway_run_id`

So the 15-bundle release was 6 bundles wearing a fixture, and every test that "proved" 3/6/6
was proving it against a schema no producer writes. A fixture that agrees with the consumer
instead of the producer is not a fixture, it is a mirror.

WHAT REPLACES IT
----------------
The lane is identified by the artifact's own ``schema_version`` — the one field every
producer does emit, and the one that actually *means* "which lane wrote this". A bundle whose
schema names no known lane is REFUSED rather than guessed at: three producers, three
contracts, and an unrecognised fourth is a bundle nobody can read.

Each lane then declares, explicitly and by name, WHERE its identity and its context live.
No inference, no fallback, no "well, it looks like a direct bundle".
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

try:                                    # as a package module — the PRODUCER side
    from .arm_topology import LANE_DIRECT, LANE_PATHWAY, LANE_TEMPORAL, RunManifestError
except ImportError:                     # ...and FLAT, the way the verifier loads its modules
    # The verifier does not import the producer's package (arm_topology reaches for
    # `config`, which only resolves under `direct.`), and it should not: it reimplements the
    # contract independently in `verify_manifest_rules`. So take the lane names from THERE —
    # if the two ever disagree about what a lane is called, that is a finding, not a detail
    # to paper over with a second copy of the literals.
    from verify_manifest_rules import (  # type: ignore  # noqa: I001
        LANE_DIRECT,
        LANE_PATHWAY,
        LANE_TEMPORAL,
    )

    class RunManifestError(Exception):   # type: ignore[no-redef]
        """The flat-mode refusal. Same meaning; the verifier owns its own type."""

# --------------------------------------------------------------------------- #
# THE NATIVE CONTRACTS, read from the producers' own bytes:
#   Direct    fc9bdcd   arm_bundle.py  SCHEMA_VERSION / STAMPED run id
#   temporal  2021d90   temporal/arms/arm_bundle.py  SCHEMA_BUNDLE
#   pathway   2435b92   pathway_arms.py SCHEMA_VERSION, stamped by run_pathway_arms
# --------------------------------------------------------------------------- #
NATIVE_BUNDLE = {
    LANE_DIRECT: {
        "schema_version": "spot.stage02_direct_arm_bundle.v1",
        "id_field": "arm_bundle_run_id",
        "provenance": "provenance.json",
        "context_fields": ("condition",),
    },
    LANE_TEMPORAL: {
        "schema_version": "spot.stage02_temporal_arm_bundle.v1",
        "id_field": "bundle_id",
        "provenance": "temporal_provenance.json",
        "context_fields": ("from_condition", "to_condition"),
    },
    LANE_PATHWAY: {
        "schema_version": "spot.stage02_pathway_arm_bundle.v1",
        "id_field": "pathway_run_id",
        "provenance": "pathway_provenance.json",
        "context_fields": ("condition", "source"),
    },
}

LANE_OF_SCHEMA = {spec["schema_version"]: lane
                  for lane, spec in NATIVE_BUNDLE.items()}

BUNDLE_FILE = "arm_bundle.json"

# The aggregate's own context vocabulary. The pathway lane calls it `source`; the arm key
# calls it `gene_set_source`. One rename, stated once, rather than two words for one thing.
_CONTEXT_ALIAS = {"source": "gene_set_source"}


def lane_of(doc: Any) -> Optional[str]:
    """WHICH LANE wrote this, by the only field every producer emits: its schema."""
    if not isinstance(doc, dict):
        return None
    return LANE_OF_SCHEMA.get(str(doc.get("schema_version")))


def normalize(doc: Any, *, where: str = "") -> dict[str, Any]:
    """One shape for three producers. Explicit per lane; nothing inferred.

    Returns ``{lane, bundle_id, context, arms, n_arms, schema_version}``.
    """
    lane = lane_of(doc)
    if lane is None:
        raise RunManifestError(
            f"{where or 'bundle'}: schema_version {str((doc or {}).get('schema_version'))!r}"
            f" names no known lane. The three native contracts are "
            f"{sorted(LANE_OF_SCHEMA)} — an unrecognised fourth is a bundle nobody can read")
    spec = NATIVE_BUNDLE[lane]

    bundle_id = doc.get(spec["id_field"])
    if not bundle_id:
        raise RunManifestError(
            f"{where or lane}: no {spec['id_field']!r} — this lane names its bundles by that "
            "field, and a bundle with no id cannot be told apart from a copy of itself")

    context: dict[str, Any] = {}
    nested = doc.get("context") if isinstance(doc.get("context"), dict) else {}
    for field in spec["context_fields"]:
        value = doc.get(field, nested.get(field))
        if value is None:
            raise RunManifestError(
                f"{where or lane}: no {field!r} — this lane's bundles are keyed by "
                f"{list(spec['context_fields'])}, and a bundle that does not say which slot "
                "it fills cannot fill one")
        context[_CONTEXT_ALIAS.get(field, field)] = value

    arms = doc.get("arms") or []
    return {
        "lane": lane,
        "schema_version": doc.get("schema_version"),
        "bundle_id": str(bundle_id),
        "context": context,
        "arms": arms,
        "n_arms": len(arms),
    }


def read(bundle_dir: str) -> Optional[dict[str, Any]]:
    """The normalized view of a directory, or None if it is not a bundle at all."""
    path = os.path.join(bundle_dir, BUNDLE_FILE)
    if not os.path.exists(path):
        return None
    try:
        with open(path) as fh:
            doc = json.load(fh)
    except (OSError, json.JSONDecodeError):
        raise RunManifestError(
            f"{bundle_dir}: {BUNDLE_FILE} is not readable JSON — a directory that cannot be "
            "opened is not a bundle") from None
    return normalize(doc, where=bundle_dir)
