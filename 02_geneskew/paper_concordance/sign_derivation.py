"""Deterministic re-derivation of the Marson (Zhu/Dann 2025) Results-section cytokine
SIGN CONTROLS. NON-RANKING, NON-GATING diagnostic.

Sign convention (preprint p9, verbatim): the readout is the cytokine's log2 fold-change on
regulator KNOCKDOWN vs non-targeting control.
  * negative regulator  ->  knockdown log2FC > 0  (KD raises the cytokine; represses it)
  * positive regulator  ->  knockdown log2FC < 0  (KD lowers the cytokine; promotes it)

This module derives, per control, whether the pinned DE object reproduces the paper's SIGN
at a significant condition. It NEVER ranks, gates, or alters any production output, and it
never claims exact replication (spot's production estimand differs). Upstream FDR is carried
only as a ``provenance_diagnostics`` field, explicitly ``used_for_gating_or_ranking: false``.

The DE object is abstracted behind an ``observe(regulator, cytokine, condition)`` callable
so the deterministic logic is testable without any HDF5 dependency.
"""
from __future__ import annotations

from typing import Any, Callable, Sequence

SPEC_ID = "spot.stage02.paper_concordance.sign_controls.v1"
POLICY_VERSION = "spot.stage02.paper_concordance.sign_derivation.v1"

SIGN_POSITIVE = "positive"    # log_fc > 0  (negative regulator)
SIGN_NEGATIVE = "negative"    # log_fc < 0  (positive regulator)
SIGN_ZERO = "zero"

CLASSIFICATION = "diagnostic_non_gating"
BANNED_PRODUCTION_KEYS = frozenset({
    "rank", "score", "gate", "production_candidate", "priority", "combined_score"})


def sign_of(log_fc: Any, eps: float = 1e-9) -> Any:
    if log_fc is None:
        return None
    if log_fc > eps:
        return SIGN_POSITIVE
    if log_fc < -eps:
        return SIGN_NEGATIVE
    return SIGN_ZERO


def expected_sign_for_role(role: str) -> Any:
    if role == "negative_regulator":
        return SIGN_POSITIVE
    if role == "positive_regulator":
        return SIGN_NEGATIVE
    return None


def _num_str(x: Any) -> Any:
    """Exact source rendering; a float never enters an identity as a bare float."""
    return None if x is None else repr(float(x))


def _observation(reg: str, cyto: str, cond: str, o: dict[str, Any],
                 expected_sign: str, adj_p_threshold: float) -> dict[str, Any]:
    prov_absent = {"adj_p_value": None, "label": "authors_reported_upstream",
                   "significant_at_5pct": False, "used_for_gating_or_ranking": False}
    if not o.get("present"):
        return {"regulator": reg, "cytokine": cyto, "condition": cond, "present": False,
                "observed_sign": None, "expected_log_fc_sign": expected_sign,
                "concordant": False, "provenance_diagnostics": prov_absent}
    log_fc, adj_p = o.get("log_fc"), o.get("adj_p")
    obs_sign = sign_of(log_fc)
    sig = adj_p is not None and adj_p < adj_p_threshold
    return {"regulator": reg, "cytokine": cyto, "condition": cond, "present": True,
            "observed_log_fc_source_string": _num_str(log_fc),
            "observed_sign": obs_sign, "expected_log_fc_sign": expected_sign,
            "concordant": obs_sign == expected_sign,
            "provenance_diagnostics": {
                "adj_p_value": _num_str(adj_p), "label": "authors_reported_upstream",
                "significant_at_5pct": bool(sig), "used_for_gating_or_ranking": False}}


def _pairs(control: dict[str, Any]) -> list[dict[str, str]]:
    if control.get("divergent"):
        return list(control["divergent"])
    return [{"cytokine": control["cytokine"],
             "expected_log_fc_sign": control["expected_log_fc_sign"]}]


def derive_control(control: dict[str, Any], *,
                   observe: Callable[[str, str, str], dict[str, Any]],
                   conditions: Sequence[str],
                   adj_p_threshold: float = 0.05) -> dict[str, Any]:
    """One directional control -> per-(regulator, cytokine, condition) observations + a
    concordance outcome. A DIVERGENT control passes only if EVERY cytokine is satisfied."""
    observations: list[dict[str, Any]] = []
    satisfied: dict[str, bool] = {}
    for pair in _pairs(control):
        cyto, expected = pair["cytokine"], pair["expected_log_fc_sign"]
        satisfied.setdefault(cyto, False)
        for reg in control["regulators"]:
            for cond in conditions:
                rec = _observation(reg, cyto, cond, observe(reg, cyto, cond), expected,
                                   adj_p_threshold)
                observations.append(rec)
                if (rec["present"] and rec["concordant"]
                        and rec["provenance_diagnostics"]["significant_at_5pct"]):
                    satisfied[cyto] = True
    concordant_sig = bool(satisfied) and all(satisfied.values())
    return {"control_id": control["id"], "kind": "directional",
            "classification": CLASSIFICATION, "cytokines": list(satisfied.keys()),
            "source": control.get("source"), "observations": observations,
            "outcome": {"concordant_significant": concordant_sig,
                        "cytokine_satisfied": satisfied,
                        "claims_exact_replication": False}}


def derive_broad_control(control: dict[str, Any], *,
                         observe: Callable[[str, str, str], dict[str, Any]],
                         conditions: Sequence[str], cytokine_panel: Sequence[str],
                         adj_p_threshold: float = 0.05,
                         broad_min_cytokines: int = 5) -> dict[str, Any]:
    """A broad-effect control: each regulator should significantly affect a LARGE set of
    cytokines (counted over the 30-cytokine panel), stimulation-specifically."""
    per_reg: dict[str, Any] = {}
    for reg in control["regulators"]:
        per_cond: dict[str, int] = {}
        for cond in conditions:
            n_sig = 0
            for cyto in cytokine_panel:
                o = observe(reg, cyto, cond)
                if (o.get("present") and o.get("adj_p") is not None
                        and o["adj_p"] < adj_p_threshold):
                    n_sig += 1
            per_cond[cond] = n_sig
        per_reg[reg] = {"max_n_significant_cytokines": max(per_cond.values(), default=0),
                        "per_condition": per_cond}
    broad = any(v["max_n_significant_cytokines"] >= broad_min_cytokines
                for v in per_reg.values())
    return {"control_id": control["id"], "kind": "broad_effect",
            "classification": CLASSIFICATION, "source": control.get("source"),
            "per_regulator": per_reg,
            "outcome": {"broad": broad, "broad_min_cytokines": broad_min_cytokines,
                        "claims_exact_replication": False}}


def derive_all(spec: dict[str, Any], *,
               observe: Callable[[str, str, str], dict[str, Any]]) -> dict[str, Any]:
    """Derive every control in a frozen spec. Pure over ``observe``; no ranking, no gating."""
    conditions = spec["conditions"]
    panel = spec.get("cytokine_panel") or spec.get("cytokine_panel_paper_named") or []
    thr = spec.get("adj_p_diagnostic_threshold", 0.05)
    results = []
    for control in spec["controls"]:
        if control.get("kind") == "broad_effect":
            results.append(derive_broad_control(
                control, observe=observe, conditions=conditions, cytokine_panel=panel,
                adj_p_threshold=thr,
                broad_min_cytokines=spec.get("broad_min_cytokines", 5)))
        else:
            results.append(derive_control(control, observe=observe,
                                          conditions=conditions, adj_p_threshold=thr))
    return {"spec_id": spec.get("spec_id", SPEC_ID), "policy_version": POLICY_VERSION,
            "classification": CLASSIFICATION, "results": results}
