"""Shared constants and the TargetSpec used by the direct fixtures.

No real data is read here. ``synthetic_run`` writes a tiny but structurally
faithful copy of the released artifacts (categorical obs, ``layers/log_fc``,
guide slots without guide IDs, six overlapping donor-pair modalities) so the
whole orchestrator can be exercised end to end without touching the pinned
dataset.
"""
from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Optional

import h5py
import numpy as np

# The one Ensembl rule, restated for the fixtures so they never depend on the code
# under test to decide what the release published.
ENSG_RE = re.compile(r"^ENSG[0-9]+$")

_ANALYSIS = os.path.join(os.path.dirname(__file__), "..", "..", "analysis")
sys.path.insert(0, os.path.abspath(_ANALYSIS))

CONDITION = "StimX"

A_PANEL = ["ENSG00000000001", "ENSG00000000002"]
B_PANEL = ["ENSG00000000003", "ENSG00000000004"]
CONTROLS = [f"ENSG000000001{i:02d}" for i in range(12)]      # 12 control genes
TARGET_GENES = [f"ENSG000000002{i:02d}" for i in range(14)]  # T0..T13
UNIVERSE = A_PANEL + B_PANEL + CONTROLS + TARGET_GENES

# The released objects do NOT agree on their gene sets (10,282 vs 10,273 in the
# real release). The donor object here is missing one control gene, so the tests
# exercise the common-intersection path rather than a single tidy universe.
DONOR_DROPPED_GENE = CONTROLS[-1]
DONOR_UNIVERSE = [g for g in UNIVERSE if g != DONOR_DROPPED_GENE]
COMMON_UNIVERSE = DONOR_UNIVERSE

# Release donor tokens are opaque; nothing may infer identity from their shape.
DONORS = ["CE0006864", "CE0008162", "CE0008678", "CE0010866"]
DONOR_PAIRS = [f"{a}_{b}" for i, a in enumerate(DONORS) for b in DONORS[i + 1:]]


# The public release's 12 non-ENSG obs.target_contrast dispositions (verified):
# 4 symbols x 3 conditions. Nine carry an ENSG-looking release key belonging to a
# DIFFERENT gene; OCLM's key is symbol-prefixed. All are ontarget_significant=false
# and low_target_gex=true, and all must still be emitted.
SYMBOL_TARGETS = {
    "MTRNR2L1": "ENSG00000256618",
    "MTRNR2L4": "ENSG00000232196",
    "MTRNR2L8": "ENSG00000255823",
    "OCLM": None,                     # symbol-prefixed release key
}
RELEASE_CONDITIONS = ("Rest", "Stim8hr", "Stim48hr")


@dataclass
class TargetSpec:
    """One synthetic target: its library guides, its declared n_guides, its effects."""
    target: str
    lib_guides: list[str]                 # sgRNA ids in the library
    n_guides: Optional[float]             # what the source says contributed
    a_effect: float                       # log_fc on the A panel (drives away_from_A)
    b_effect: float = 0.0
    n_cells: float = 500.0
    ontarget_significant: bool = True
    low_target_gex: bool = False
    guide_slot_effects: dict[str, float] = field(default_factory=dict)
    # a released slot's OWN declared n_guides (defaults to the pooled count)
    guide_slot_n_guides: dict[str, float] = field(default_factory=dict)
    donor_pair_effects: dict[str, float] = field(default_factory=dict)
    donor_pair_n_guides: dict[str, float] = field(default_factory=dict)
    # library guide -> genes it puts in the 30-kb window
    guide_neighbors: dict[str, list[str]] = field(default_factory=dict)
    # --- what the CONTRIBUTOR MANIFEST proves (the only identity path) ---
    manifest_main: Optional[list[str]] = None          # defaults to lib_guides
    manifest_slots: dict[str, str] = field(default_factory=dict)   # slot -> guide
    ambiguous_estimates: tuple[str, ...] = ()          # estimate_ids left unproven
    # The EXACT release key. Defaults to f"{target}_{CONDITION}", but a symbol
    # target may carry an ENSG-looking key that belongs to another gene.
    released_key_prefix: Optional[str] = None

    @property
    def released_estimate_id(self) -> str:
        return f"{self.released_key_prefix or self.target}_{CONDITION}"

    # ---- the RELEASED target identity this spec publishes ----
    # One source of truth: the h5ad writer puts these in obs, and the contributor
    # manifest / source records must carry exactly the same values.
    @property
    def target_id_namespace(self) -> str:
        return "ensembl_gene_id" if ENSG_RE.match(self.target) else "gene_symbol"

    @property
    def target_symbol(self) -> str:
        """obs.target_contrast_gene_name. Never null — verified across all 33,983
        released rows."""
        return (self.target if self.target in SYMBOL_TARGETS
                else f"SYM{self.target[-2:]}")

    @property
    def target_ensembl(self) -> Optional[str]:
        """Null for every symbol scope. The ENSG-looking release key is NOT it."""
        return self.target if ENSG_RE.match(self.target) else None

    @property
    def identity(self) -> dict:
        return {"released_estimate_id": self.released_estimate_id,
                "target_id": self.target,
                "target_id_namespace": self.target_id_namespace,
                "target_symbol": self.target_symbol,
                "target_ensembl": self.target_ensembl}


