"""The two records a membership IS: the selection it is bound to, and the arms it holds in it.

Kept apart from `stage3_v2_membership` because they are the DATA; that module is the RULES. The
identity payloads live here so there is exactly one definition of what gets hashed — a second
definition of the same identity is how two hashes of "the same thing" come to disagree.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping

from .selection_roles import RoleArm

MEMBERSHIP_CONTRACT = "spot.stage04.stage3_v2_membership.v1"

# Stage 3 states this guarantee in its own selection view. Stage 4 re-states it as an executable
# rule: an arm key is matched by EXACT full-string equality, never by prefix, never by display name.
EXACT_MATCH_RULE = "arm_keys_are_matched_by_exact_string_equality_never_by_prefix"


@dataclass(frozen=True)
class SelectionBinding:
    """The identity of the ONE question a projection answers. Every field is bound into the hash.

    Nothing here is Stage-4's to choose: each value is copied from Stage 3's selection view, and a
    projection that cannot state all of them is refused rather than displayed under a guess.
    """

    # The RUN identity. `selection_id` names WHICH selection; `selection_full_sha256` and
    # `full_contract_content_sha256` are the FULL contract's identity, not just the canonical
    # (biology-only) content. Binding the canonical hash ALONE would let two selections that pose
    # the same biological question under different endpoint/run contracts hash identically — the
    # canonical hash is deliberately narrower, and a projection bound only to it cannot tell a
    # re-run under a changed contract from the original.
    selection_id: str
    selection_full_sha256: str
    full_contract_content_sha256: str
    question_id: str
    selection_canonical_sha256: str
    analysis_mode: str
    conditions: tuple[str, ...]
    selected_arm_keys: frozenset[str]
    # THE ORDERED, PER-ROLE ARMS. `selected_arm_keys` is a SET, and a set is symmetric: swapping
    # which arm is A and which is B — or swapping the ROLES away_from_A / toward_B — leaves it
    # bit-for-bit identical. Yet a role swap asks the OPPOSITE biological question. So the ordered
    # role records are bound too, and they are what makes an A/B or role swap move the hash.
    role_arms: tuple[RoleArm, ...]
    view_id: str
    view_content_sha256: str

    def identity(self) -> dict[str, Any]:
        return {
            "selection_id": self.selection_id,
            "selection_full_sha256": self.selection_full_sha256,
            "full_contract_content_sha256": self.full_contract_content_sha256,
            "question_id": self.question_id,
            "selection_canonical_sha256": self.selection_canonical_sha256,
            "analysis_mode": self.analysis_mode,
            "conditions": list(self.conditions),
            "selected_arm_keys": sorted(self.selected_arm_keys),
            # ORDERED — never sorted into a set. The order and the labels ARE the question.
            "role_arms": [a.identity() for a in self.role_arms],
            "view_id": self.view_id,
            "view_content_sha256": self.view_content_sha256,
        }


@dataclass(frozen=True)
class Membership:
    """One candidate's re-derived membership in one selection."""

    candidate_id: str
    selection: SelectionBinding
    # The exact arm keys this candidate holds IN this selection, per typed store column. Empty
    # column -> the column is still present, with an empty list: absence is stated, never omitted.
    arm_keys_by_column: Mapping[str, tuple[str, ...]]
    in_view: bool

    @property
    def all_arm_keys(self) -> tuple[str, ...]:
        keys: set[str] = set()
        for v in self.arm_keys_by_column.values():
            keys.update(v)
        return tuple(sorted(keys))

    def membership_sha256(self) -> str:
        """Content-addressed membership. Change the selection, the condition, the view, or ONE arm
        key, and this moves — which is what makes a re-pointed projection detectable rather than
        merely wrong."""
        payload = {
            "contract": MEMBERSHIP_CONTRACT,
            "candidate_id": self.candidate_id,
            "selection": self.selection.identity(),
            "arm_keys_by_column": {k: list(v) for k, v in sorted(self.arm_keys_by_column.items())},
            "exact_match_rule": EXACT_MATCH_RULE,
        }
        blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode()).hexdigest()
