"""The bundle's EVIDENCE artifacts: masks, contributors, and pair-free support accounting.

BLOCKER 4. The all-arm bundle bound counts of its evidence and shipped none of it, so a reader
could not identify — let alone reconstruct — which masks and which guides produced the rows.
Binding the hash of bytes nobody can hold is the same defect as citing a gene-set file that
only exists on the producer's disk: a verifier can check the mask hashed to X and have no way
to obtain X.

WHY THE LEGACY SUPPORT ROWS COULD NOT BE REUSED
-----------------------------------------------
`arms.guide_support_rows` / `arms.donor_support_rows` are keyed on `config.ARMS`, and those
arms are the PAIR's poles — `away_from_A` and `toward_B`. Their rows carry an `arm` column
holding a pole, plus `internal_sign_agreement` and `agrees_with_target_estimate`, which are
statements about two arms seen side by side.

Emitting them here would smuggle the pair back into a bundle whose entire purpose is to not
have one — through the support artifacts, where nobody was looking. So the all-arm bundle
emits its OWN support rows: the same released estimates, enumerated for ACCOUNTING, with no
pole, no value and no concordance.

SUPPORT IS ENUMERATED, NEVER PROJECTED (`config.SUPPORT_AVAILABLE_IN_THIS_PASS = False`). The
release ships these slots and a silently absent row would read as "no such slot" rather than
"this slot was never evaluated" — so every one is emitted, and its unavailability is a value.
"""
from __future__ import annotations

from typing import Any, Optional

from . import config

SUPPORT_RULE_ID = "spot.stage02.direct.arm_support.enumerated_never_projected.v1"


def guide_support_rows(target: str, cond: str,
                       slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One row per released guide slot. NO pole, NO value — this pass never projects one."""
    return [{
        "target_id": target,
        "condition": cond,
        "estimate_id": s["estimate_id"],
        "guide_id": s["guide_id"],
        "support_available": config.SUPPORT_AVAILABLE_IN_THIS_PASS,
        "unresolved_reason": s["unresolved_reason"],
    } for s in slots]


def donor_support_rows(target: str, cond: str, pair_values: dict[str, dict],
                       splits: list) -> list[dict[str, Any]]:
    """One row per released donor split. The split is ENUMERATED; no half is projected.

    `pair_values` is passed only to enumerate the donor pairs the release actually ships for
    this target — its per-arm values are `empty_values()` in this lane and are never read.
    """
    rows: list[dict[str, Any]] = []
    for split in splits:
        rows.append({
            "target_id": target,
            "condition": cond,
            "split_id": split.split_id,
            "half_a": split.half_a,          # the donor-pair modality id, verbatim
            "half_b": split.half_b,          # ...and its released complement
            "n_donor_pairs_released": len(pair_values),
            "support_available": config.SUPPORT_AVAILABLE_IN_THIS_PASS,
        })
    return rows


def stamp(rows: list[dict[str, Any]], run_id: Optional[str]) -> list[dict[str, Any]]:
    """Stamp the bundle id onto evidence rows AFTER the identity is known."""
    for r in rows:
        r["arm_bundle_run_id"] = run_id
    return rows
