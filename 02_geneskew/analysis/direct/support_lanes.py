"""The SUPPORT LANES: enumerated, explicitly unavailable, never projected.

The audited contributor artifact is global, all-condition, POOLED-MAIN only. The
guide-slot and donor-pair estimates carry no contributor evidence in it, so they get
none: no mask, no projection, no replication claim, and no power to elevate an evidence
tier. Nothing about a support object can refuse a valid main estimate.

They are still ENUMERATED, and that is the whole point of this module. A silently absent
estimate reads as "the release does not ship it", which is a different — and false —
claim from "the release ships it and we have no evidence about it". Each one is emitted
with an explicit unavailable state and a named reason.
"""
from __future__ import annotations

from . import arms, guides


# --------------------------------------------------------------------------- #
# Support lanes: EXPLICITLY UNAVAILABLE in this release pass.
#
# The audited contributor artifact is global, all-condition, POOLED-MAIN only. The
# guide-slot and donor-pair estimates have no contributor evidence in it, so they get
# none: no mask, no projection, no replication claim, and no power to elevate an
# evidence tier. They are still ENUMERATED and emitted with an explicit unavailable
# state, because a silently absent estimate reads as "the release does not ship it".
# --------------------------------------------------------------------------- #
def _unavailable_estimate(est: guides.Estimate) -> tuple[list, dict]:
    """One support estimate, refused for a named reason. No mask. No projection."""
    contrib = guides.resolve(est, library={}, manifest_index=None)
    return guides.contributor_rows(est, contrib), {
        "estimate_id": est.estimate_id,
        "guide_id": None,                       # never guessed from a slot name
        "values": arms.empty_values(),          # never projected
        "unresolved_reason": contrib.reason,
    }


def guide_lane(ident, cond: str, guide_ids: dict) -> tuple[list, list]:
    """Per-slot contributor rows and slot records for one target — all unavailable.

    ``guide_ids`` maps modality -> {target -> {"released_estimate_id"}} and is METADATA
    ONLY: the slot's effect vector is never read, and its ``n_guides`` is never read
    either. In this release that field is a COPY of the pooled estimate's count, not
    the slot's own contributor count, so reading it as the slot's own would be the
    same class of error this pass exists to remove.
    """
    contrib_rows, slots = [], []
    for mod_id in sorted(guide_ids):
        entry = guide_ids[mod_id]["by_target"].get(ident.target_id)
        if entry is None:
            continue
        rows, slot = _unavailable_estimate(guides.Estimate(
            estimate_type=guides.GUIDE, estimate_id=mod_id,
            released_estimate_id=entry["released_estimate_id"],
            target_id=ident.target_id, target_ensembl=ident.target_ensembl,
            condition=cond, n_guides=None,
            target_id_namespace=ident.target_id_namespace,
            target_symbol=ident.target_symbol,
            released_target_ensembl=ident.released_target_ensembl))
        contrib_rows += rows
        slots.append(slot)
    return contrib_rows, slots


def donor_lane(ident, cond: str, donor_ids: dict) -> tuple[list, dict]:
    """Per-donor-pair contributor rows for one target — all unavailable."""
    contrib_rows: list[dict] = []
    values: dict[str, dict] = {}
    for pair_id in sorted(donor_ids):
        entry = donor_ids[pair_id]["by_target"].get(ident.target_id)
        values[pair_id] = arms.empty_values()   # never projected
        if entry is None:
            continue
        rows, _slot = _unavailable_estimate(guides.Estimate(
            estimate_type=guides.DONOR_PAIR, estimate_id=pair_id,
            released_estimate_id=entry["released_estimate_id"],
            target_id=ident.target_id, target_ensembl=ident.target_ensembl,
            condition=cond, n_guides=None, donor_pair=pair_id,
            target_id_namespace=ident.target_id_namespace,
            target_symbol=ident.target_symbol,
            released_target_ensembl=ident.released_target_ensembl))
        contrib_rows += rows
    return contrib_rows, values
