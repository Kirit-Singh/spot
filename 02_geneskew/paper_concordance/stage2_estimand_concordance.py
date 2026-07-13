"""Read-only concordance of the CURRENT Stage-2 estimands against the Marson preprint.

The whole point of this module is to say HONESTLY where a comparison is permitted and where
it is NOT. Two different estimands are in play:

  * the PAPER's claim is a per-cytokine differential expression on regulator knockdown —
    a sign on ``d_X,g`` (log2FC) for one cytokine gene g, with FDR-based inference;
  * our RELEASED Stage-2 estimand is a target-masked DE-space PROGRAM PROJECTION
    (02_geneskew/analysis/direct/projection.py):

        delta_p(X) = mean_{g in P_p \\ M_X} d_X,g  -  mean_{g in C_p \\ M_X} d_X,g

    a panel mean minus a control mean. A single cytokine is at most ONE member of P_p.

Both are functions of the SAME released per-gene log_fc, so the substrate is shared — but a
program delta is NOT a per-cytokine quantity, and we never equate them. Every record carries a
typed comparability tier, and a directional VERDICT is emitted ONLY on the shared substrate.

NON-RANKING, NON-GATING, READ-ONLY: nothing here alters a score, a rank, or any Stage-2 output.
Paper FDR is recorded as upstream inference only; our production display carries no p/q.
"""
from __future__ import annotations

from typing import Any, Optional

CLASSIFICATION = "read_only_diagnostic_non_gating"

# --- typed comparability tiers ------------------------------------------------------- #
# A verdict is legitimate ONLY on this tier: same released quantity (per-gene log2FC).
TIER_SAME_SUBSTRATE = "same_substrate_exact"
# The cytokine IS a panel member, so it contributes to delta_p — but delta_p is a panel mean
# minus a control mean, so per-cytokine equivalence is NOT claimed. Descriptive, NO verdict.
TIER_PROJECTION_NOT_EQUIVALENT = "program_projection_not_equivalent"
# The cytokine is in NO released program panel -> our estimand says nothing about it.
TIER_CYTOKINE_ABSENT = "not_comparable_cytokine_absent_from_all_panels"
# The paper's broad claim counts affected cytokines; our estimand has no breadth measure.
TIER_NO_BREADTH = "not_comparable_no_breadth_estimand"
# The paper's arrayed validation measured PROTEIN (flow); our analysis is mRNA-only.
TIER_PROTEIN_MODALITY = "not_comparable_protein_modality"

PAPER_MODALITY = "mRNA (CRISPRi Perturb-seq differential expression)"
OUR_MODALITY = "mRNA (same released per-gene log2FC, projected onto a program panel)"
PAPER_INFERENCE = "FDR (paper-reported; screen-level FDR < 10%, figure stars 5%/1%/0.1%)"
OUR_INFERENCE = "none — production displays no p/q and draws no inference"

ESTIMAND_FORMULA = ("delta_p(X) = mean_{g in P_p \\ M_X} d_X,g - "
                    "mean_{g in C_p \\ M_X} d_X,g   (target-masked DE-space program "
                    "projection; 02_geneskew/analysis/direct/projection.py)")


def sign_of(v: Optional[float], eps: float = 1e-9) -> Optional[str]:
    if v is None:
        return None
    if v > eps:
        return "positive"
    if v < -eps:
        return "negative"
    return "zero"


def programs_containing(cytokine: str, registry: list[dict[str, Any]]) -> list[str]:
    """Released programs whose PANEL contains this cytokine (symbol join on panel_symbols)."""
    return [p["program_id"] for p in registry
            if cytokine in set(p.get("panel_symbols") or [])]


def comparability(cytokine: Optional[str], registry: list[dict[str, Any]], *,
                  kind: str = "directional") -> dict[str, Any]:
    """Typed tier for one paper control against the CURRENT released Stage-2 estimand."""
    if kind == "broad_effect":
        return {"tier": TIER_NO_BREADTH, "programs": [],
                "reason": ("the paper's claim is a COUNT of affected cytokines; the released "
                           "Stage-2 estimand is a single program projection and carries no "
                           "per-cytokine breadth measure")}
    progs = programs_containing(cytokine, registry) if cytokine else []
    if not progs:
        return {"tier": TIER_CYTOKINE_ABSENT, "programs": [],
                "reason": (f"{cytokine} is not a panel member of ANY released program, so the "
                           "Stage-2 program estimand says nothing about it")}
    return {"tier": TIER_PROJECTION_NOT_EQUIVALENT, "programs": progs,
            "reason": (f"{cytokine} is one panel member of {', '.join(progs)}; delta_p is a "
                       "panel mean minus a control mean, so a per-cytokine equivalence is not "
                       "claimed and no verdict is emitted")}


def substrate_verdict(expected_sign: str, observed_log_fc: Optional[float]) -> dict[str, Any]:
    """The ONE legitimate verdict: does the paper's stated direction reproduce from the
    identical released per-gene log2FC that our projection consumes?"""
    obs = sign_of(observed_log_fc)
    return {"tier": TIER_SAME_SUBSTRATE,
            "expected_log_fc_sign": expected_sign,
            "observed_log_fc_sign": obs,
            "concordant": (obs == expected_sign) if obs is not None else False,
            "modality_paper": PAPER_MODALITY, "modality_ours": OUR_MODALITY}


def projection_observation(program_id: str, delta: Optional[float], status: str,
                           n_panel: Optional[int], n_control: Optional[int]) -> dict[str, Any]:
    """Our released estimand, reported DESCRIPTIVELY — no verdict, no rank, no p/q."""
    return {"program_id": program_id, "estimand": ESTIMAND_FORMULA,
            "delta_p": delta, "delta_p_sign": sign_of(delta),
            "projection_status": status,
            "n_panel_surviving": n_panel, "n_control_surviving": n_control,
            "verdict": None,
            "note": ("descriptive only: a program delta is not a per-cytokine effect, so "
                     "agreement or disagreement with the paper's cytokine sign is NOT a "
                     "concordance result"),
            "inference": OUR_INFERENCE}
