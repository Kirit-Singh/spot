"""Every ABSENCE, NAMED. Split from :mod:`druglink.edges_v2` at the 500-line gate.

A disposition is how Stage 3 says "nothing is here, and this is why" — so that a target nobody
looked up, a target with no drug evidence, an assertion that may never rank, and a lane that was
not admitted are four DIFFERENT facts rather than one silence. Re-exported from ``edges_v2``.
"""
from __future__ import annotations

from typing import Any

from .hashing import short_id

DISPOSITION_COLUMNS: tuple[str, ...] = (
    "disposition_id", "subject_kind", "subject_id", "state", "reason", "detail",
    "target_id", "target_id_namespace", "arm_key", "origin_type", "candidate_id",
    "source_record_id",
)
DISPOSITION_KEY: tuple[str, ...] = ("disposition_id",)

# Disposition states. Every absence is NAMED: a target the acquisition route cannot reach is not
# a target with no drug evidence, and nor is a target nobody looked up.
STATE_NOT_IN_UNIVERSE = "target_not_in_admitted_typed_universe"
STATE_NO_DRUG_EVIDENCE = "target_carries_no_source_drug_assertion"
STATE_UNSUPPORTED_NAMESPACE = "target_namespace_unreachable_by_this_acquisition_route"
STATE_NON_RANKABLE = "source_assertion_is_not_general_gene_rankable"
# The pathway lane is CONTEXT — and right now it is NOT ADMITTED. Its absence from the edge table
# is a STATED fact, not a silence.
STATE_PATHWAY_IS_TYPED_CONTEXT = "pathway_is_typed_context_not_a_measured_lever"
STATE_PATHWAY_LANE_NOT_ADMITTED = "pathway_lane_not_admitted_verifier_fails_open"


def disposition(**row: Any) -> dict[str, Any]:
    full = {c: row.get(c) for c in DISPOSITION_COLUMNS if c != "disposition_id"}
    return {"disposition_id": short_id(full), **full}
