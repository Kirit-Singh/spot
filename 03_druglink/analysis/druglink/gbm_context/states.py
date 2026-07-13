"""Pure typed-state logic for the Stage-3 v2 GBM disease-context evidence layer.

DESCRIPTIVE, NON-RANKING, NON-GATING. Immune-cell effect and tumor-cell context stay on
SEPARATE axes and never fuse into a single score. Disease association is a third axis, and
every disease number carries a ``source_provenance`` block (endpoint, HTTP status, API/data
version, raw sha256, licence, response artifact) so it traces to the exact pinned bytes.
Missing evidence is ``not_evaluated`` and is never invented. Open Targets' aggregated scores
are carried as ``open_targets_reported_upstream`` with ``used_for_gating_or_ranking: False``.
The DepMap dependency-call rule is the FROZEN engine's exact rule (strict > 0.5).
"""
from __future__ import annotations

from typing import Any, Optional

from . import depmap_bridge as _db

CLASSIFICATION = "descriptive_non_gating"
NOT_EVALUATED = "not_evaluated"

BANNED_PRODUCTION_KEYS = frozenset({
    "rank", "score", "gate", "priority", "combined_score", "overall_rank",
    "production_candidate", "p_value", "pvalue", "q_value", "qvalue",
    "adj_p_value", "fdr"})

# --- immune axis ------------------------------------------------------------------- #
IMMUNE_INCREASE = "increase"
IMMUNE_DECREASE = "decrease"
IMMUNE_UNKNOWN = "unknown"


def immune_direction(desired_change: Any) -> str:
    if desired_change == IMMUNE_INCREASE:
        return IMMUNE_INCREASE
    if desired_change == IMMUNE_DECREASE:
        return IMMUNE_DECREASE
    return IMMUNE_UNKNOWN


# --- tumor axis (DepMap Public 26Q1 GBM/glioma dependency) -------------------------- #
DEP_DEPENDENCY = "tumor_cell_dependency"
DEP_NON_DEPENDENCY = "no_tumor_cell_dependency"


def tumor_dependency_state(metrics: Optional[dict[str, Any]], *,
                           dependency_prob_threshold: float = _db.DEPENDENCY_PROB_THRESHOLD
                           ) -> dict[str, Any]:
    """Descriptive tumor-cell dependency across the named GBM/glioma lines. The recorded
    call rule is the FROZEN engine's: STRICT ``> 0.5``. ``metrics`` is ``None`` (or not
    evaluated) -> ``not_evaluated`` with a reason, never a fabricated direction."""
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
                         "dependency_prob_threshold": dependency_prob_threshold,
                         "dependency_prob_comparator": _db.DEPENDENCY_PROB_COMPARATOR,
                         "dependency_prob_strict": _db.DEPENDENCY_PROB_STRICT},
            "median_gene_effect": metrics.get("median_gene_effect"),
            "source_class": metrics.get("source_class")}


# --- disease axis (Open Targets association evidence) ------------------------------- #
DA_PRESENT = "association_evidence_present"
DA_ABSENT = "no_association_evidence"


def _source_provenance(ot: dict[str, Any]) -> dict[str, Any]:
    """Bind every displayed disease number to the exact pinned response bytes."""
    return {"endpoint": ot.get("endpoint"), "http_status": ot.get("http_status"),
            "api_version": ot.get("api_version"), "data_version": ot.get("data_version"),
            "raw_sha256": ot.get("raw_sha256"), "license": ot.get("license"),
            "response_artifact": ot.get("response_artifact")}


def disease_association_state(ot_result: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Descriptive disease-association evidence, with a ``source_provenance`` block on every
    outcome (present, absent, or not-evaluated) so a reader can trace to the bytes. OT's
    aggregated scores are carried but flagged non-gating."""
    ot = ot_result or {}
    prov = _source_provenance(ot)
    if not ot.get("evaluated"):
        return {"state": NOT_EVALUATED, "diseases": {},
                "reason": ot.get("reason", "open_targets_not_queried"),
                "source_provenance": prov}
    diseases = ot.get("diseases") or {}
    if not diseases:
        return {"state": DA_ABSENT, "diseases": {}, "source_provenance": prov}
    out: dict[str, Any] = {}
    for mondo, rec in diseases.items():
        out[mondo] = {
            "name": rec.get("name"),
            "reported_overall_association_score": rec.get(
                "reported_overall_association_score"),
            "datatype_evidence": dict(rec.get("datatype_evidence") or {}),
            "label": "open_targets_reported_upstream",
            "used_for_gating_or_ranking": False}
    return {"state": DA_PRESENT, "diseases": out, "source_provenance": prov}


# --- typed compatibility interpretation (SUGGESTIVE, never causal, never a number) -- #
COMPAT_DUAL = "dual_mechanism_compatible_suggestive"
COMPAT_IMMUNE_ONLY = "immune_axis_only_no_tumor_dependency"
COMPAT_TUMOR_NOT_EVALUATED = "tumor_context_not_evaluated"
COMPAT_INDETERMINATE = "indeterminate"


def compatibility(immune_dir: str, tumor_state: dict[str, Any]) -> dict[str, Any]:
    """Interpret the immune axis against the tumor axis as a typed, SUGGESTIVE category —
    never a combined score, never causal. The disease axis stays separate."""
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
