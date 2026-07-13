"""THE JOIN: the admitted native measurement, typed by the admitted bridge row.

``stage2_aggregate.admit_aggregate`` returns arms whose ``records`` are Stage-2's NATIVE ranking
rows, verbatim — ``{target_id, arm_value, evaluable, rank}``. They carry no namespace and no
modality, so the v2 edge builder (which refuses both by name rather than defaulting them) can
build NOTHING from them. ``stage2_bridge.admit_bridge`` supplies exactly those missing facts.

This module is the seam between them, and it is deliberately tiny — because the interesting work
is the REFUSAL, and that already happened. By the time a record reaches :func:`bind`, the bridge
has been proved to agree with the native bytes about every value the native bytes own. What is
left is a merge:

    typed record = the NATIVE record, plus the six fields the bridge is trusted for

The MEASUREMENT always stays the native one. ``arm_value``, ``evaluable`` and ``rank`` are copied
from the native row and are never taken from the bridge, even though the two have been proved
equal — because "proved equal today" and "read from the right place" are different guarantees,
and only the second one survives someone editing this file.

PATHWAY ARMS ARE LEFT EXACTLY AS THEY ARE. Their native records are gene-set enrichments; they
have no target to type and they yield no edges. A pathway arm that acquired a typed target record
here would be a set membership manufacturing a drug edge — so it is not merely skipped, it is
REFUSED if the bridge ever tries (``stage2_bridge`` gates that, and this asserts it again on the
rows it actually emits).
"""
from __future__ import annotations

import dataclasses
from typing import Any

from . import stage2_contract as C
from .stage2_bridge import BRIDGE_SUPPLIED, AdmittedBridge, Stage2BridgeError
from .stage2_contract import AdmittedAggregate, LoadedArm

GATE_ARM_IDENTITY_UNRESOLVED = "a_measured_arm_record_has_no_typed_bridge_row"
GATE_PATHWAY_ARM_WAS_TYPED = "a_pathway_arm_acquired_a_typed_target_record"


def _typed(arm: LoadedArm, rec: dict[str, Any],
           bridge: AdmittedBridge) -> dict[str, Any]:
    """One native ranking row, typed by the bridge row that names its identity and its assay."""
    key = (arm.lane, arm.arm_key, str(rec.get("target_id")))
    row = bridge.rows.get(key)
    if row is None:
        raise Stage2BridgeError(
            f"[{GATE_ARM_IDENTITY_UNRESOLVED}] arm {arm.arm_key!r} scored target "
            f"{rec.get('target_id')!r}, and the admitted bridge carries no typed row for it. The "
            "native ranking states no namespace and no modality, so without the bridge row this "
            "target has no identity to join on and no experiment to phenocopy — and a namespace "
            "GUESSED from the shape of an id attaches the wrong gene to a drug.")
    # The MEASUREMENT stays the NATIVE one. Only identity and modality come from the bridge.
    return {**rec, **{f: row.get(f) for f in BRIDGE_SUPPLIED}}


def bind(aggregate: AdmittedAggregate, bridge: AdmittedBridge) -> AdmittedAggregate:
    """The admitted aggregate, with every MEASURED arm's records typed by the admitted bridge.

    Returns a NEW aggregate: the one that was admitted is never mutated, so a caller still holding
    it holds the untyped bytes it actually admitted.
    """
    arms: list[LoadedArm] = []
    for arm in aggregate.arms:
        if arm.lane not in C.MEASURED_LANES:
            # A pathway arm has no target rows to type, and must not acquire any.
            if any((arm.lane, arm.arm_key, str(r.get("target_id"))) in bridge.rows
                   for r in arm.records):
                raise Stage2BridgeError(
                    f"[{GATE_PATHWAY_ARM_WAS_TYPED}] pathway arm {arm.arm_key!r} was handed a "
                    "typed target record. Pathway is CONTEXT: it may annotate a candidate an "
                    "eligible gene-arm edge already supports, and it may never create one.")
            arms.append(arm)
            continue
        arms.append(dataclasses.replace(
            arm, records=tuple(_typed(arm, dict(r), bridge) for r in arm.records)))

    counts = dict(aggregate.counts)
    counts.update({
        "n_typed_records": sum(len(a.records) for a in arms
                               if a.lane in C.MEASURED_LANES),
        "typed_by_bridge": True,
        "bridge_self_hash": bridge.bridge_self_hash,
        # Said out loud on the aggregate that feeds the edge builder: the bridge added identity
        # and modality, and changed no measurement.
        "measurement_is_the_native_one": True,
    })
    return dataclasses.replace(aggregate, arms=tuple(arms), counts=counts)
