"""ChEMBL ``max_phase``, preserved EXACTLY — and used for nothing.

``max_phase`` is the furthest clinical phase ChEMBL has seen a molecule reach. Stage 3
preserves it because a reader deserves to know it, and refuses to act on it because Stage 3
is not a clinical-development oracle.

WHY IT IS PRESERVED RAW *AND* CANONICAL
---------------------------------------
ChEMBL's ``max_phase`` is not a plain integer, and treating it as one destroys information:

    null   the molecule has no phase recorded — NOT phase 0, and not "never tried"
    -1     ChEMBL's explicit "unknown" sentinel — NOT a phase below 0
    0.5    a real value (early clinical) — an int cast silently makes it 0
    1..4   ordinary phases

Every one of those is DISTINCT, and three of them get destroyed the moment someone writes
``int(max_phase or 0)``. So the raw source string is kept verbatim, alongside a canonical
decimal, and null / -1 / 0.5 / integers can never collapse into one another.

WHY IT NEVER GATES OR RANKS — AND WHY THAT NEEDS SAYING
-------------------------------------------------------
It is the single most tempting field in the cache. "Phase 4 means approved, so rank it
first" is a recommendation dressed as a sort. But this stage's evidence is a CRISPRi screen
and a public target-drug mapping; a molecule's clinical phase says nothing about whether it
is direction-compatible with the arm in question. Letting phase touch the ordering would
mean an approved drug with no directional support outranking a direction-compatible one —
and the reader would have no way to see that the ordering had stopped being about the
biology.

So ``max_phase`` is **context only**. It is emitted, it is shown, and it is inert:
``may_gate`` and ``may_rank`` are constants, and they are ``False``.

RELATIONSHIP TO ``development_state``
-------------------------------------
The coarse ``development_state`` field stays exactly as it is. It does **not** preserve
``max_phase`` and this module does not claim it does — it is a separate, lossier summary.
Anyone who needs the phase reads the phase.
"""
from __future__ import annotations

from typing import Any, Optional

from .canonical_number import canonical_number

MAX_PHASE_RULE_ID = "spot.stage03.chembl_max_phase.preserve_exact.v1"

# ChEMBL's explicit "unknown" sentinel. It is NOT a phase, and it is NOT below phase 0.
UNKNOWN_SENTINEL = "-1"

# Stated as constants so they cannot be quietly flipped by a caller in a hurry.
MAY_GATE = False
MAY_RANK = False

NOT_RECORDED = "not_recorded"          # null: no phase on record
UNKNOWN = "unknown"                    # -1: ChEMBL says it does not know
RECORDED = "recorded"                  # an actual phase, including 0.5
PHASE_STATES = (NOT_RECORDED, UNKNOWN, RECORDED)


class MaxPhaseError(ValueError):
    """max_phase was used for something it may not be used for."""


def preserve(raw: Any, *, chembl_release: str,
             source_record_id: Optional[str] = None) -> dict[str, Any]:
    """Keep the phase EXACTLY: the source string verbatim, plus a canonical decimal.

    Nothing here rounds, casts, defaults or coalesces. A value that arrives as ``0.5``
    leaves as ``0.5``; a null stays null and never becomes ``0``.
    """
    if not chembl_release:
        raise MaxPhaseError(
            "max_phase is meaningless without the release that reported it: phases are "
            "revised, and a phase with no release provenance cannot be reproduced")

    if raw is None:
        return {
            "max_phase_source_string": None,
            "max_phase_canonical_decimal": None,
            "max_phase_state": NOT_RECORDED,
            "max_phase_is_unknown_sentinel": False,
            **_provenance(chembl_release, source_record_id),
        }

    source_string = str(raw)                       # VERBATIM. Not reformatted.
    is_sentinel = source_string.strip() == UNKNOWN_SENTINEL

    try:
        canonical = canonical_number(float(source_string))
    except (TypeError, ValueError) as exc:
        raise MaxPhaseError(
            f"max_phase {source_string!r} is not a number Stage 3 can canonicalise; it is "
            "not coerced to 0 and it is not dropped") from exc

    return {
        "max_phase_source_string": source_string,
        "max_phase_canonical_decimal": canonical,
        "max_phase_state": UNKNOWN if is_sentinel else RECORDED,
        "max_phase_is_unknown_sentinel": is_sentinel,
        **_provenance(chembl_release, source_record_id),
    }


def _provenance(chembl_release: str, source_record_id: Optional[str]) -> dict[str, Any]:
    return {
        "max_phase_source": "chembl",
        "max_phase_source_release": chembl_release,
        "max_phase_source_record_id": source_record_id,
        "max_phase_rule_id": MAX_PHASE_RULE_ID,
        # The whole point, stated in the row itself so a consumer cannot miss it.
        "max_phase_is_context_only": True,
        "max_phase_may_gate": MAY_GATE,
        "max_phase_may_rank": MAY_RANK,
        "development_state_preserves_max_phase": False,
    }


def refuse_if_used_for_ordering(sort_keys: list[str]) -> None:
    """A drug ordering may not name max_phase. Not as a key, not as a tie-break."""
    offenders = [k for k in sort_keys if "max_phase" in k or "phase" == k]
    if offenders:
        raise MaxPhaseError(
            f"the drug ordering names {offenders}. max_phase is CONTEXT ONLY: a molecule's "
            "clinical phase says nothing about whether it is direction-compatible with "
            "this arm. Ranking on it would let an approved drug with no directional "
            "support outrank a direction-compatible one, and the reader would have no way "
            "to see the ordering had stopped being about the biology.")


def distinct(a: dict[str, Any], b: dict[str, Any]) -> bool:
    """Two preserved phases differ if their SOURCE STRINGS differ. null != -1 != 0 != 0.5."""
    return a["max_phase_source_string"] != b["max_phase_source_string"]
