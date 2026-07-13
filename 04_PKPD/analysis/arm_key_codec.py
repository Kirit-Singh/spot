"""Decoding a Stage-3 arm-key column — where a string is NOT a list.

Stage 3 v2 serializes its arm-key columns (`arm_keys`, `observed_perturbation_arm_keys`, …) as JSON
STRINGS inside parquet, not as native list columns. That single fact is load-bearing enough to own a
module: getting it wrong does not raise, it silently makes every candidate a member of everything.

Kept apart from `stage3_v2_membership` because it is a different concern — that module is about WHICH
selection a candidate belongs to; this one is about how to read a column without lying about it.
"""

from __future__ import annotations

import json
from typing import Any

from .firewall import Rejection


class MembershipError(Rejection):
    """A candidate's selection membership cannot be re-derived from the store, or disagrees."""


def arm_key_list(value: Any, *, where: str) -> tuple[str, ...]:
    """Decode ONE arm-key column. Stage 3 writes these as JSON STRINGS in parquet, not as lists.

    THIS FUNCTION EXISTS BECAUSE OF A NEAR MISS. The first version of this module did

        for key in (candidate.get(column) or ()):   ...

    which is correct for a list and CATASTROPHIC for a string: iterating `'["direct|P|..."]'` yields
    CHARACTERS. Run against the real bundle, every one of the 19 candidates "matched" the selection
    — because the selected key `,` appears in every serialized list. A 100% membership rate, no
    error, no warning, and every candidate displayed on every arm.

    So a string is decoded as JSON and must decode to a LIST OF STRINGS. A bare string that is not
    JSON is REFUSED rather than iterated — silently treating it as a sequence of one-character arm
    keys is the exact failure above.
    """
    if value is None:
        return ()
    if isinstance(value, (list, tuple)):
        items = list(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            return ()
        try:
            items = json.loads(text)
        except json.JSONDecodeError as exc:
            raise MembershipError(
                "stage3_arm_key_column_is_not_a_list",
                f"{where} is the bare string {value[:40]!r}, which is not a JSON list of arm keys. "
                "Stage 4 will NOT iterate it: a string iterates into CHARACTERS, and a "
                "one-character 'arm key' silently matches almost any selection — a 100% membership "
                "rate with no error raised anywhere.",
            ) from exc
        if not isinstance(items, list):
            raise MembershipError(
                "stage3_arm_key_column_is_not_a_list",
                f"{where} decodes to {type(items).__name__}, not a list of arm keys.",
            )
    else:
        raise MembershipError(
            "stage3_arm_key_column_is_not_a_list",
            f"{where} is a {type(value).__name__}, not a list of arm keys.",
        )

    for item in items:
        if not isinstance(item, str) or not item:
            raise MembershipError(
                "stage3_arm_key_is_not_a_string",
                f"{where} contains {item!r}, which is not an arm key. An arm key is the exact "
                "string Stage 2 minted; anything else cannot be matched by equality.",
            )
    return tuple(items)
