"""Pure typed-state logic for the Stage-3 v2 GBM disease-context evidence layer.

DESCRIPTIVE, NON-RANKING, NON-GATING. The immune-cell effect axis (what perturbation
Stage-2 wants) and the tumor-cell context axis (DepMap GBM/glioma dependency) are kept
SEPARATE and are never fused into a single score. Disease association (Open Targets) is a
third, separate axis. Every function is pure so the logic is testable without any network
or HDF5. Missing evidence is ``not_evaluated`` and is never invented. Open Targets' own
aggregated scores are carried as ``open_targets_reported_upstream`` and are explicitly
``used_for_gating_or_ranking: False`` — they never gate, rank, or become a spot output.
"""
from __future__ import annotations

from typing import Any, Optional

CLASSIFICATION = "descriptive_non_gating"
NOT_EVALUATED = "not_evaluated"

# A production/handoff record must never carry a statistical-inference or ranking field.
BANNED_PRODUCTION_KEYS = frozenset({
    "rank", "score", "gate", "priority", "combined_score", "overall_rank",
    "production_candidate", "p_value", "pvalue", "q_value", "qvalue",
    "adj_p_value", "fdr"})

# --- immune axis (Stage-2 desired perturbation of the immune program) --------------- #
IMMUNE_INCREASE = "increase"
IMMUNE_DECREASE = "decrease"
IMMUNE_UNKNOWN = "unknown"


def immune_direction(desired_change: Any) -> str:
    """Map the arm's verbatim ``desired_change`` token to a direction. The vocabulary is
    Stage-2's own {"increase", "decrease"}; anything else is ``unknown`` (never guessed)."""
    if desired_change == IMMUNE_INCREASE:
        return IMMUNE_INCREASE
    if desired_change == IMMUNE_DECREASE:
        return IMMUNE_DECREASE
    return IMMUNE_UNKNOWN


# --- tumor axis (DepMap Public 26Q1 GBM/glioma cell-line dependency) ----------------- #
DEP_DEPENDENCY = "tumor_cell_dependency"
DEP_NON_DEPENDENCY = "no_tumor_cell_dependency"

# DepMap's own convention: CRISPRGeneDependency is the probability a gene is a dependency
# in a line; a line with probability >= 0.5 is counted as a dependent line. This threshold
# is a recorded parameter, not an invented cut.
DEFAULT_DEPENDENCY_PROB_THRESHOLD = 0.5


def tumor_dependency_state(metrics: Optional[dict[str, Any]], *,
                           dependency_prob_threshold: float = DEFAULT_DEPENDENCY_PROB_THRESHOLD
                           ) -> dict[str, Any]:
    """Descriptive tumor-cell dependency across the named GBM/glioma lines.

    ``metrics`` is ``None`` (or ``evaluated`` false) when no official DepMap bytes have been
    pinned -> ``not_evaluated`` with a recorded reason, never a fabricated direction. When
    evaluated, ``direction`` is dependency vs non-dependency and ``coverage`` records how
    many of the GBM/glioma lines were evaluated and how many are dependent at the threshold.
    """
    if not metrics or not metrics.get("evaluated"):
        return {"state": NOT_EVALUATED, "direction": None, "coverage": None,
                "median_gene_effect": None,
                "reason": (metrics or {}).get("reason",
                                              "depmap_official_bytes_not_pinned")}
    n_total = int(metrics["n_gbm_glioma_lines_evaluated"])
    n_dep = int(metrics["n_lines_dependent"])
    direction = DEP_DEPENDENCY if n_dep > 0 else DEP_NON_DEPENDENCY
    return {"state": "evaluated", "direction": direction,
            "coverage": {"n_gbm_glioma_lines_evaluated": n_total,
                         "n_lines_dependent": n_dep,
                         "dependency_prob_threshold": dependency_prob_threshold},
            "median_gene_effect": metrics.get("median_gene_effect")}


# --- disease axis (Open Targets target<->disease association evidence) ---------------- #
DA_PRESENT = "association_evidence_present"
DA_ABSENT = "no_association_evidence"


def disease_association_state(ot_result: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Descriptive disease-association evidence. ``ot_result`` is ``None`` when the OT
    axis was not run -> ``not_evaluated``. When evaluated but no disease carries evidence
    -> ``no_association_evidence`` (distinct from not-run). OT's own aggregated scores are
    carried but flagged non-gating; the datatype breakdown is the descriptive evidence."""
    if not ot_result or not ot_result.get("evaluated"):
        return {"state": NOT_EVALUATED, "diseases": {},
                "reason": (ot_result or {}).get("reason", "open_targets_not_queried")}
    diseases = ot_result.get("diseases") or {}
    if not diseases:
        return {"state": DA_ABSENT, "diseases": {}}
    out: dict[str, Any] = {}
    for mondo, rec in diseases.items():
        out[mondo] = {
            "name": rec.get("name"),
            "reported_overall_association_score": rec.get(
                "reported_overall_association_score"),
            "datatype_evidence": dict(rec.get("datatype_evidence") or {}),
            "label": "open_targets_reported_upstream",
            "used_for_gating_or_ranking": False}
    return {"state": DA_PRESENT, "diseases": out}


# --- typed compatibility interpretation (SUGGESTIVE, never causal, never a number) --- #
COMPAT_DUAL = "dual_mechanism_compatible_suggestive"
COMPAT_IMMUNE_ONLY = "immune_axis_only_no_tumor_dependency"
COMPAT_TUMOR_NOT_EVALUATED = "tumor_context_not_evaluated"
COMPAT_INDETERMINATE = "indeterminate"


def compatibility(immune_dir: str, tumor_state: dict[str, Any]) -> dict[str, Any]:
    """Interpret the immune axis against the tumor axis as a typed, SUGGESTIVE state.

    This is the ONLY place the two axes meet, and they meet as a category, never as a
    combined score: does knocking this gene plausibly serve BOTH the immune program and
    an anti-tumor dependency? The disease axis stays separate. Nothing here is causal.
    """
    tstate = tumor_state.get("state")
    if tstate == NOT_EVALUATED:
        state = COMPAT_TUMOR_NOT_EVALUATED
    elif tumor_state.get("direction") == DEP_DEPENDENCY:
        state = COMPAT_DUAL if immune_dir in (IMMUNE_INCREASE, IMMUNE_DECREASE) \
            else COMPAT_INDETERMINATE
    elif tumor_state.get("direction") == DEP_NON_DEPENDENCY:
        state = COMPAT_IMMUNE_ONLY
    else:
        state = COMPAT_INDETERMINATE
    return {"state": state, "suggestive": True, "causal": False,
            "immune_direction": immune_dir, "tumor_state": tstate}
