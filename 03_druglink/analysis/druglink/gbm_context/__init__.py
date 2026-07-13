"""Stage-3 v2 GBM disease-context evidence layer (descriptive, NON-RANKING, NON-GATING).

Assembles, for each gene in the selected Stage-2 arms, three SEPARATE descriptive
evidence axes — the desired immune perturbation direction (Stage-2 arm), the tumor-cell
dependency across named GBM/glioma cell lines (DepMap Public 26Q1), and the disease-
association evidence (Open Targets) — plus a typed, SUGGESTIVE compatibility interpretation.
It never ranks, gates, or alters any Stage-2 output; missing evidence is ``not_evaluated``
and is never invented; no p/q ever reaches a production field.
"""
from __future__ import annotations


class GbmContextError(Exception):
    """A contract violation in the GBM disease-context layer."""


CLASSIFICATION = "descriptive_non_gating"
