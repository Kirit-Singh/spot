"""Descriptive, NON-GATING comparison of the eventual Stage-2 targets/pathways to the paper
sign controls.

The estimands differ: spot's Stage-2 output is a per-program base-delta over a reusable-arm
system; the paper controls are per-cytokine DESeq2 knockdown effects. So this overlay only
RECORDS which control regulators appear in the Stage-2 output, alongside their paper
control(s). It asserts NO directional equivalence, makes NO exact-replication claim, emits
NO pass/fail verdict on an overlap, and NEVER changes a rank or gates anything.
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

CLASSIFICATION = "diagnostic_non_gating"


def _index_stage2(stage2_rows: Sequence[dict[str, Any]],
                  symbol_to_ensembl: Optional[dict[str, str]]):
    by_symbol: dict[str, list] = {}
    by_ensembl: dict[str, list] = {}
    for row in stage2_rows:
        sym = row.get("target_symbol")
        ens = row.get("target_ensembl") or row.get("target_id")
        if sym:
            by_symbol.setdefault(sym, []).append(row)
        if ens:
            by_ensembl.setdefault(ens, []).append(row)
    return by_symbol, by_ensembl


def compare_to_stage2(spec: dict[str, Any], stage2_rows: Sequence[dict[str, Any]], *,
                      symbol_to_ensembl: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """One descriptive overlay. Join is on EXACT symbol (or the gene's exact Ensembl id via
    ``symbol_to_ensembl``) — never a partial/fuzzy match."""
    by_symbol, by_ensembl = _index_stage2(stage2_rows, symbol_to_ensembl)
    control_regs: dict[str, list] = {}
    for control in spec["controls"]:
        for reg in control["regulators"]:
            control_regs.setdefault(reg, []).append({
                "control_id": control["id"], "kind": control.get("kind"),
                "cytokine": control.get("cytokine"),
                "expected_role": control.get("expected_role"),
                "divergent": control.get("divergent")})

    overlaps = []
    n_in = 0
    for reg, controls in sorted(control_regs.items()):
        appearances = list(by_symbol.get(reg, []))
        ens = (symbol_to_ensembl or {}).get(reg)
        if ens:
            for row in by_ensembl.get(ens, []):
                if row not in appearances:
                    appearances.append(row)
        if appearances:
            n_in += 1
        overlaps.append({
            "regulator": reg,
            "in_stage2": bool(appearances),
            "stage2_appearances": [{"program_id": a.get("program_id"),
                                    "desired_change": a.get("desired_change"),
                                    "condition": a.get("condition")}
                                   for a in appearances],
            "paper_controls": controls,
            "descriptive_note": ("same gene appears in both the paper controls and the "
                                 "Stage-2 output; estimands differ, so no directional "
                                 "equivalence is asserted") if appearances
            else "not present in the Stage-2 output"})

    return {"classification": CLASSIFICATION, "does_not_alter_ranks": True,
            "does_not_gate": True, "does_not_claim_exact_replication": True,
            "estimand_note": spec.get("estimand_note"),
            "n_control_regulators": len(control_regs), "n_in_stage2": n_in,
            "overlaps": overlaps}
