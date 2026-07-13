"""The READOUT gene universe: what the reconstruction is allowed to be scored on.

Every gene that DEFINES a program — its panel and its control — is excluded, and so is every
perturbation TARGET gene. What is left is the readout.

WHY THE EXCLUSION IS THE WHOLE POINT
------------------------------------
The reconstruction target is the program's own expression direction, and a program score is
computed FROM its panel and control genes. Leave those genes in the readout and the model is
asked to reconstruct a quantity from the very genes that quantity was defined by — it will
succeed, brilliantly, and the r2 will mean nothing at all. It would be measuring the
definition, not the biology.

Target genes are excluded for the mirror-image reason: a CRISPRi perturbation of gene X
knocks down X, so X's own expression is the assay's positive control, not evidence that X
reconstructs a program.

The universe is ORDERED canonically and HASHED, so two runs that claim the same universe can
be shown to have used it.
"""
from __future__ import annotations

from typing import Any, Iterable

from direct.hashing import content_hash


class UniverseError(ValueError):
    """The readout universe is unusable. Refuse; never score on a contaminated one."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


def panel_and_control(programs: dict[str, dict], program_ids: Iterable[str]) -> set[str]:
    """Every panel and control gene of the named programs. Nulls dropped, never guessed."""
    out: set[str] = set()
    for pid in program_ids:
        p = programs.get(str(pid)) or {}
        for key in ("panel_ensembl", "control_ensembl"):
            for g in (p.get(key) or []):
                if g:
                    out.add(str(g))
    return out


def build(*, effect_gene_ids: Iterable[str], excluded_program_genes: Iterable[str],
          target_gene_ids: Iterable[str]) -> dict[str, Any]:
    """The ordered, hashed readout universe, and a full account of what left it."""
    effect_gene_ids = [str(g) for g in effect_gene_ids]
    excluded_program_genes = {str(g) for g in excluded_program_genes}
    target_gene_ids = {str(g) for g in target_gene_ids if g}

    excluded = excluded_program_genes | target_gene_ids
    kept = sorted(set(effect_gene_ids) - excluded)

    if not kept:
        raise UniverseError(
            "readout_universe_is_empty",
            "every measured gene was excluded as a program panel/control or a perturbation "
            "target, so there is no readout left to reconstruct on")

    n_panel_control_removed = len(excluded_program_genes & set(effect_gene_ids))
    n_target_removed = len((target_gene_ids - excluded_program_genes)
                           & set(effect_gene_ids))

    return {
        "gene_ids": kept,
        "n_universe": len(kept),
        "n_effect_genes": len(set(effect_gene_ids)),
        "n_panel_control_excluded": n_panel_control_removed,
        "n_target_genes_excluded": n_target_removed,
        "panel_control_genes_leaked": [],       # asserted below; emitted so it is falsifiable
        "gene_universe_sha256": content_hash(kept),
    }


def assert_clean(universe: dict[str, Any], excluded_program_genes: Iterable[str]) -> None:
    """No program panel or control gene may be in the readout. Checked, not assumed."""
    leak = sorted(set(universe["gene_ids"]) & {str(g) for g in excluded_program_genes})
    if leak:
        raise UniverseError(
            "panel_or_control_gene_leaked_into_the_readout",
            f"{len(leak)} program panel/control gene(s) are still in the readout universe "
            f"(e.g. {leak[:5]}). The reconstruction would be scored on the very genes the "
            "program score is computed from, and it would succeed for that reason alone")
