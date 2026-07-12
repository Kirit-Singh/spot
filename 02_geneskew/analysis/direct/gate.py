"""THE RELEASE GATE: what a run must have PROVEN before it may write a result.

Two refusals live here, and both are fail-closed by construction.

CONTRIBUTOR EVIDENCE MUST BE PRESENT
------------------------------------
A run with no contributor manifest has no guide identity, so every pooled estimate is
``mask_unresolved`` and nothing is scoreable. Emitting that as a *result* — a complete
screen of nulls, with a run_id, a provenance block and a verification record — dresses
"we were never shown the evidence" up as "we looked and found nothing". It is refused,
and the refusal happens before a single artifact is written.

STRICT REPLAY MUST BE FRESH, IN THIS INVOCATION
-----------------------------------------------
The pinned replay report is a CLAIM by the producer. For a release-grade lane
(``production`` / ``research_only``) trusting it is not a gate, so the run must
re-derive the completeness verdict from the raw source ITSELF, in the same invocation
that writes the result, and that fresh verdict must agree with the pinned report.

There is exactly ONE way to pass. There used to be a second — a "pinned strict-preflight
GO artifact", trusted on presentation and hashed into run_id — and it was a forgery
surface, not a gate:

  * the artifact was authenticated against NOTHING. Any five-field JSON saying
    ``verdict: GO`` and ``strict_replay: {ran: true, agrees_with_pinned_report: true}``
    was accepted, because those fields were the whole check. A hand-authored file
    passed;
  * it was bound to no CONTEXT. Nothing tied the artifact to this run's manifest, its
    sources, its source-record table or its evidence domain, so a genuine GO from run A
    authorised an unrelated run B over different evidence;
  * hashing it into run_id proved only that the run had committed to WHICH forgery it
    stood on. Binding an unauthenticated claim makes the claim immutable, not true.

A gate that can be satisfied by writing a file is not a gate, so the shortcut is gone
rather than repaired: there is no argument, no state and no code path for it. A
release-grade run with ``strict_replay=false`` refuses — before the dense read, before
any artifact exists. The synthetic fixture lane needs no gate and says so explicitly;
it is a unit-test lane, never a release lane.
"""
from __future__ import annotations

from typing import Any, Optional

from . import config

GATE_ID = "spot.stage02.direct.release_gate.v2"

# Lanes whose output is release-grade. The synthetic lane is a fixture lane.
RELEASE_LANES = (config.LANE_PRODUCTION, config.LANE_RESEARCH)

# The frozen gate states. Enums, not prose. There is no pinned state: a gate a producer
# can satisfy by authoring a JSON file is not a gate, and an unauthenticated claim does
# not become true by being hashed into run_id.
GATE_FRESH = "fresh_strict_replay"
GATE_NOT_REQUIRED = "not_required_fixture_lane"
GATE_STATES = (GATE_FRESH, GATE_NOT_REQUIRED)

CHECK_MANIFEST = "contributor_manifest_resolves"
CHECK_STRICT = "strict_replay_is_fresh"


class GateError(ValueError):
    """The run has not proven what it must prove. Refuse; never write a result."""

    def __init__(self, message: str, report: Optional[dict[str, Any]] = None):
        super().__init__(message)
        self.report = report


def requires_strict_replay(lane: str) -> bool:
    return lane in RELEASE_LANES


def release_gate(*, lane: str, strict_replay: dict[str, Any]) -> dict[str, Any]:
    """What this run may stand on. Bound into run_id, so it cannot be swapped later.

    ``strict_replay`` is THIS invocation's strict-replay block (from ``preflight``): it
    counts only if it actually RAN, here, and actually AGREED with the pinned report.
    No other evidence is accepted, and there is nowhere else for it to come from.
    """
    fresh = bool(strict_replay.get("ran")
                 and strict_replay.get("agrees_with_pinned_report"))
    if not requires_strict_replay(lane):
        return {"gate_id": GATE_ID, "lane": lane, "strict_replay_required": False,
                "state": GATE_NOT_REQUIRED, "strict_replay_ran": fresh}
    if fresh:
        return {"gate_id": GATE_ID, "lane": lane, "strict_replay_required": True,
                "state": GATE_FRESH, "strict_replay_ran": True}
    raise GateError(
        f"lane {lane!r} is release-grade: it may not stand on the pinned replay report, "
        "and there is no artifact that can stand in for a strict replay. Re-run with "
        "--strict-replay --pseudobulk <raw source> (on tcefold) so the completeness "
        "verdict is re-derived from the raw source in THIS invocation")
