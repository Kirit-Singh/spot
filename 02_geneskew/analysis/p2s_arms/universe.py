"""The READOUT gene universe: what the reconstruction is scored on.

WHAT IS SUBTRACTED GLOBALLY — AND WHAT IS EMPHATICALLY NOT
---------------------------------------------------------
Only the PROGRAM panel/control genes (and the activation covariate's) leave the universe
globally. A program score is computed FROM its panel and control genes, so leaving those in
the readout would ask the model to reconstruct a quantity from the very genes it was defined
by — it would succeed for that reason alone.

The perturbation TARGET genes are NOT subtracted globally. There are ~11,000 eligible targets
and only 10,282 readout genes; subtracting every target gene would delete almost the whole
assay (real overlap counts leave ~785-944 genes) — catastrophic, and not the paper's method.
A CRISPRi knockdown of gene X makes X its own positive control ONLY IN X'S COLUMN, not in
every other perturbation's column. So the target self-gene is neutralised PER COLUMN, by the
admitted Direct contributor mask (which already includes the target's own gene) — see
``pmatrix.build_masked_x``. This module does not touch it.

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


def build(*, effect_gene_ids: Iterable[str],
          excluded_program_genes: Iterable[str]) -> dict[str, Any]:
    """The ordered, hashed readout universe. GLOBAL exclusion = program panel/control ONLY.

    Perturbation target genes are NOT subtracted here — they are masked per column by the
    Direct contributor mask. Global target subtraction would delete most of the assay.
    """
    effect_gene_ids = [str(g) for g in effect_gene_ids]
    excluded_program_genes = {str(g) for g in excluded_program_genes}

    kept = sorted(set(effect_gene_ids) - excluded_program_genes)

    if not kept:
        raise UniverseError(
            "readout_universe_is_empty",
            "every measured gene was excluded as a program panel/control gene, so there is "
            "no readout left to reconstruct on")

    n_panel_control_removed = len(excluded_program_genes & set(effect_gene_ids))

    return {
        "gene_ids": kept,
        "n_universe": len(kept),
        "n_effect_genes": len(set(effect_gene_ids)),
        "n_panel_control_excluded": n_panel_control_removed,
        "target_genes_subtracted_globally": False,     # masked per column, never globally
        "self_gene_neutralised_per_column_by_direct_mask": True,
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
