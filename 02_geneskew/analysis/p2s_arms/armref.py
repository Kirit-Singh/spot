"""The ARM REFERENCE: the one thing this lane is allowed to be asked about.

P2S v2 has exactly ONE primitive — reconstruction support for a WITHIN-CONDITION Direct
arm:

    direct | program_id | desired_change | condition

and this module is the gate that admits only that. A temporal or pathway key handed in here
is REFUSED rather than coerced, and that refusal is what makes the temporal firewall
structural: the endpoints of a temporal question resolve to two DIRECT arm keys, which
already exist, and the consumer joins them. There is nothing here that could accept an
ordered condition pair, so there is nothing that could difference one.

THE KEY GRAMMAR IS DIRECT'S, NOT OURS
-------------------------------------
The canonical construction lives in ``direct.arm_keys`` and is imported, not restated. A
secondary lane that kept its own copy of the key grammar would drift from the primary lane
it exists to support, and the first thing to notice would be a UI joining zero rows.

Importing it is safe for the byte-identity invariant: reading a module does not modify it.
This lane writes NO byte under ``analysis/direct/``.
"""
from __future__ import annotations

from dataclasses import dataclass

from direct import arm_keys

KIND_DIRECT = arm_keys.KIND_DIRECT
DESIRED_CHANGES = arm_keys.DESIRED_CHANGES

# The kinds this lane REFUSES, and why. Named, so a refusal reads as a decision.
REFUSED_KINDS = {
    arm_keys.KIND_TEMPORAL: (
        "a temporal arm is keyed on an ORDERED CONDITION PAIR, and this lane may not claim "
        "a temporal difference-in-differences, a fate or a lineage. The endpoints of a "
        "temporal question are two DIRECT arm keys — ask for those, separately, and join "
        "them at display time"),
    arm_keys.KIND_PATHWAY: (
        "a pathway arm is an enrichment over a RANKED LIST; this lane reconstructs a "
        "program's expression direction and has nothing to say about a gene set"),
    arm_keys.KIND_CONVERGENCE: (
        "convergence is a property of a (condition, source), not of a program's arm"),
}


class ArmRefError(ValueError):
    """The arm reference is not one this lane may answer. Refuse; never coerce."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class ArmRef:
    """One reusable Direct arm. The ONLY thing this lane computes support for."""

    arm_key: str
    program_id: str
    desired_change: str
    condition: str

    @property
    def sign(self) -> int:
        """+1 for ``increase``, -1 for ``decrease``. The sign of the ONE base effect."""
        return arm_keys.SIGN[self.desired_change]


def parse(arm_key: str) -> ArmRef:
    """Parse a ``direct|program|desired_change|condition`` key, or refuse.

    Refuses a POLE or a ROLE in the desired_change slot by name. The same pole is an
    increase in one role and a decrease in the other, so a key carrying one would fuse two
    opposite perturbations — which is exactly the failure the reusable key exists to stop,
    and it would be invisible in the values.
    """
    parts = str(arm_key).split("|")
    kind = parts[0] if parts else ""

    if kind in REFUSED_KINDS:
        raise ArmRefError(
            f"p2s_refuses_{kind}_arm",
            f"p2s_arms was handed a {kind!r} arm key ({arm_key!r}): "
            f"{REFUSED_KINDS[kind]}")

    if kind != KIND_DIRECT or len(parts) != 4:
        raise ArmRefError(
            "not_a_direct_arm_key",
            f"{arm_key!r} is not a direct arm key. The grammar is exactly "
            f"'{KIND_DIRECT}|program_id|desired_change|condition' — four parts, and this "
            "lane answers about nothing else")

    _, program_id, change, condition = parts

    if change not in DESIRED_CHANGES:
        hint = ""
        if change in arm_keys.POLES:
            hint = (" — that is a POLE. The same pole is an increase in one role and a "
                    "decrease in the other, so it may not key an arm")
        elif change in arm_keys.ROLES:
            hint = (" — that is a ROLE. A role is a position in somebody's pair, not a "
                    "property of the arm, so it may not key one")
        raise ArmRefError(
            "desired_change_is_not_a_desired_change",
            f"desired_change must be one of {list(DESIRED_CHANGES)}, got {change!r}{hint}")

    if not program_id or not condition:
        raise ArmRefError(
            "empty_key_part",
            f"{arm_key!r} has an empty program_id or condition; an arm with no program or "
            "no context is not an arm")

    # RE-DERIVED, never trusted: the key we were handed must be the key this program,
    # change and condition actually make. A hand-edited key that parses is still a key
    # nothing produced.
    rebuilt = arm_keys.direct_arm_key(program_id, change, condition)
    if rebuilt != arm_key:
        raise ArmRefError(
            "arm_key_is_not_canonical",
            f"{arm_key!r} is not the canonical form of its own parts (that would be "
            f"{rebuilt!r})")

    return ArmRef(arm_key=arm_key, program_id=program_id, desired_change=change,
                  condition=condition)


def base_change() -> str:
    """The desired change the ONE fit is taken on. The other arm is its exact negation."""
    return arm_keys.INCREASE


def sibling(ref: ArmRef) -> ArmRef:
    """The same program and condition, the opposite desired change.

    The two arms of a program in a condition are ONE measurement and a sign — not two
    estimates — so they are always produced together, from one fit.
    """
    other = (arm_keys.DECREASE if ref.desired_change == arm_keys.INCREASE
             else arm_keys.INCREASE)
    return parse(arm_keys.direct_arm_key(ref.program_id, other, ref.condition))


def both_arms(program_id: str, condition: str) -> tuple[ArmRef, ArmRef]:
    """``(increase, decrease)`` for one program in one condition, in that order."""
    return (parse(arm_keys.direct_arm_key(program_id, arm_keys.INCREASE, condition)),
            parse(arm_keys.direct_arm_key(program_id, arm_keys.DECREASE, condition)))
