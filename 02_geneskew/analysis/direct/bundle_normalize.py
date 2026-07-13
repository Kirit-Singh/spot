"""TYPED NORMALIZERS: read the REAL native producer bundle shapes, one contract per lane.

An independent replay caught the aggregate reading a FICTIONAL generic bundle shape — a
top-level ``lane``/``bundle_id``/``context`` with arms carrying ``arm_key`` + a ``ranking``
binding. Only the TEMPORAL producer emits that. On real bytes:

  * Direct  ``arm_bundle.json`` — schema ``spot.stage02_direct_arm_bundle.v1``; identity in
    ``arm_bundle_run_id``; a bare top-level ``condition``; arms carry ``arm_key`` (no ranking
    file — the arm binds ``arm_rows_sha256``). NO top-level ``lane``/``bundle_id``/``context``.
  * Pathway ``arm_bundle.json`` — schema ``spot.stage02_pathway_arm_bundle.v1``; identity in
    ``pathway_run_id``; bare ``condition`` + ``source``; arms carry ``pathway_arm_key`` (no
    ranking file — the arm binds ``records_sha256``). NO top-level ``lane``/``bundle_id``.
  * Temporal ``arm_bundle.json`` — schema ``spot.stage02_temporal_arm_bundle.v1``; already
    carries ``lane``/``bundle_id``/``context`` + arms with ``arm_key`` + ``ranking``.

So discovery keyed on a top-level ``lane`` returned ``direct=[]``, ``temporal=['temporal']``,
``pathway=[]`` — the aggregate SILENTLY found nothing — while the fixture tests passed because
they hand-built the generic shape. This module closes that: each lane is recognised by its
NATIVE schema, and its canonical identity (lane, bundle_id, context, arm_keys) is read from
the REAL fields. An unrecognised shape is REFUSED, never silently treated as a lane.

The arm-key strings the real producers emit are already byte-identical to
``arm_topology.arm_key(lane, program, change, context)`` (direct/temporal via ``arm_key``,
pathway via ``pathway_arm_key``), so a normalised bundle drops straight into the slot algebra.
"""
from __future__ import annotations

from typing import Any, Optional

DIRECT_SCHEMA = "spot.stage02_direct_arm_bundle.v1"
TEMPORAL_SCHEMA = "spot.stage02_temporal_arm_bundle.v1"
PATHWAY_SCHEMA = "spot.stage02_pathway_arm_bundle.v1"

# The TEST logic-battery shape (mutation attacks). It carries an explicit ``lane`` field and
# is retained for the synthetic battery; the REAL contract is the three per-lane schemas.
GENERIC_FIXTURE_SCHEMA = "spot.stage02_arm_bundle.v1"

SCHEMA_LANE = {DIRECT_SCHEMA: "direct", TEMPORAL_SCHEMA: "temporal",
               PATHWAY_SCHEMA: "pathway"}
LANES = ("direct", "temporal", "pathway")

# The per-arm CONTENT binding each lane's arms actually carry (there is NO per-arm ranking
# FILE in Direct/pathway; the arm binds a content hash instead).
ARM_CONTENT_HASH_FIELD = {"direct": "arm_rows_sha256", "pathway": "records_sha256"}

REFUSE_UNRECOGNIZED = "arm_bundle_schema_is_not_a_native_producer_contract"
REFUSE_MISSING_IDENTITY = "the_native_bundle_is_missing_a_required_identity_field"


class BundleShapeError(ValueError):
    """An arm_bundle.json is not a recognised native producer bundle. Refuse."""

    def __init__(self, reason: str, message: str):
        super().__init__(f"[{reason}] {message}")
        self.reason = reason


def _require(value: Any, lane: str, field: str) -> str:
    if value is None or value == "":
        raise BundleShapeError(
            REFUSE_MISSING_IDENTITY,
            f"a {lane} bundle (schema present) has no {field!r}; a native {lane} bundle is "
            f"identified by {field!r}, and one that omits it is not a bundle this aggregate "
            "can attribute")
    return str(value)


def classify_lane(doc: dict[str, Any]) -> Optional[str]:
    """The lane a bundle belongs to, from its NATIVE schema. None if unrecognised.

    Discovery uses this: a directory whose arm_bundle.json is not a native producer bundle
    (and not the retained test-battery shape) is not a lane bundle and is skipped/refused —
    never guessed from a top-level ``lane`` the real producers do not write.
    """
    if not isinstance(doc, dict):
        return None
    schema = doc.get("schema_version")
    if schema in SCHEMA_LANE:
        return SCHEMA_LANE[schema]
    if schema == GENERIC_FIXTURE_SCHEMA:
        lane = doc.get("lane")
        return lane if lane in LANES else None
    return None


def normalize(doc: dict[str, Any]) -> dict[str, Any]:
    """Canonical identity of a bundle from its REAL fields: lane, bundle_id, context, arm_keys.

    Refuses an unrecognised schema and a native bundle missing its identity field.
    """
    if not isinstance(doc, dict):
        raise BundleShapeError(REFUSE_UNRECOGNIZED, "arm_bundle.json is not a JSON object")
    schema = doc.get("schema_version")

    if schema == DIRECT_SCHEMA:
        bid = _require(doc.get("arm_bundle_run_id"), "direct", "arm_bundle_run_id")
        cond = _require(doc.get("condition"), "direct", "condition")
        arm_keys = [str(a.get("arm_key")) for a in (doc.get("arms") or [])]
        return {"lane": "direct", "bundle_id": bid,
                "context": {"condition": cond}, "arm_keys": arm_keys,
                "id_field": "arm_bundle_run_id", "arm_key_field": "arm_key"}

    if schema == TEMPORAL_SCHEMA:
        bid = _require(doc.get("bundle_id"), "temporal", "bundle_id")
        ctx = doc.get("context") or {"from_condition": doc.get("from_condition"),
                                     "to_condition": doc.get("to_condition")}
        _require(ctx.get("from_condition"), "temporal", "context.from_condition")
        _require(ctx.get("to_condition"), "temporal", "context.to_condition")
        arm_keys = [str(a.get("arm_key")) for a in (doc.get("arms") or [])]
        return {"lane": "temporal", "bundle_id": bid,
                "context": {"from_condition": str(ctx["from_condition"]),
                            "to_condition": str(ctx["to_condition"])},
                "arm_keys": arm_keys, "id_field": "bundle_id",
                "arm_key_field": "arm_key"}

    if schema == PATHWAY_SCHEMA:
        bid = _require(doc.get("pathway_run_id"), "pathway", "pathway_run_id")
        cond = _require(doc.get("condition"), "pathway", "condition")
        src = _require(doc.get("source"), "pathway", "source")
        arm_keys = [str(a.get("pathway_arm_key")) for a in (doc.get("arms") or [])]
        return {"lane": "pathway", "bundle_id": bid,
                "context": {"condition": cond, "gene_set_source": src},
                "arm_keys": arm_keys, "id_field": "pathway_run_id",
                "arm_key_field": "pathway_arm_key"}

    if schema == GENERIC_FIXTURE_SCHEMA:
        lane = doc.get("lane")
        if lane not in LANES:
            raise BundleShapeError(
                REFUSE_UNRECOGNIZED,
                f"a test-battery bundle declares lane {lane!r}; expected one of {list(LANES)}")
        arm_keys = [str(a.get("arm_key")) for a in (doc.get("arms") or [])]
        return {"lane": lane, "bundle_id": str(doc.get("bundle_id")),
                "context": dict(doc.get("context") or {}), "arm_keys": arm_keys,
                "id_field": "bundle_id", "arm_key_field": "arm_key"}

    raise BundleShapeError(
        REFUSE_UNRECOGNIZED,
        f"arm_bundle.json schema {schema!r} is not a native producer contract "
        f"({DIRECT_SCHEMA} / {TEMPORAL_SCHEMA} / {PATHWAY_SCHEMA}). A directory that does "
        "not say what it is, in a field the real producer writes, is not a bundle")
