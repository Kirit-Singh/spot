"""Frozen Stage-2 primary configuration.

EVERY threshold and policy in this module was frozen BEFORE inspecting any
Stage-2 target rank (plan §5.3-§5.5). Changing a value here changes the
canonical contrast and therefore the contrast_id.

The default contrast is constructed here because the Stage-1 selection UI is
being built in parallel; it reproduces the canonical balanced Treg-like ->
Th1-like selection (plan §4.5 / §11).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

# ---------------------------------------------------------------------------
# Pinned upstream data identifiers (from the Stage-1 program registry).
# ---------------------------------------------------------------------------
DATASET_ID = "marson2025_gwcd4_perturbseq"
EFFECT_UNIVERSE_ID = "marson2025_gwcd4_perturbseq : GWCD4i.DE_stats.h5ad"
SOURCE_HF_REPO = "KiritSingh/spot-CD4-Marson"
SOURCE_HF_REVISION = "e5fcf98b56a9302921d402e97fc5a190bd88f9a6"
SOURCE_H5AD_SHA256 = (
    "2edc6d318415c8b0ee779d707ab86e26ddb6f0274db51ab4a12f21ebfda50e43"
)
STAGE1_METHOD_VERSION = "stage1-continuous-v2"

# ---------------------------------------------------------------------------
# Frozen analysis scope.
# ---------------------------------------------------------------------------
ANALYSIS_CONDITION = "Stim48hr"       # one executable analysis condition
DONOR_SCOPE = "all"                   # all four donors (plan §4.3)
OBJECTIVE = "balanced_a_to_b"         # frozen BEFORE execution (plan §5.3)

# Pole sign s: +1 high pole, -1 low pole.
POLE_SIGN = {"high": +1, "low": -1}

# ---------------------------------------------------------------------------
# Frozen A / B axis definition (default canonical selection).
# ---------------------------------------------------------------------------
A_PROGRAM_ID = "treg_like"
A_SCORE_FIELD = "treg_like_score"
A_DIRECTION: Literal["high", "low"] = "high"

B_PROGRAM_ID = "th1_like"
B_SCORE_FIELD = "th1_like_score"
B_DIRECTION: Literal["high", "low"] = "high"

# ---------------------------------------------------------------------------
# Frozen mask policy (plan §5.4).
# ---------------------------------------------------------------------------
# Use the dataset's own pre-computed 30-kb neighborhood column; it is the
# already-defined upstream window carried in the sgRNA library metadata.
MASK_NEIGHBORHOOD_COLUMN = "nearby_gene_within_30kb"
MASK_WINDOW_KB = 30

# ---------------------------------------------------------------------------
# Frozen coverage / eligibility thresholds (plan §5.4-§5.5).
# ---------------------------------------------------------------------------
MIN_SURVIVING_PANEL = 1     # >=1 panel gene must survive masking
MIN_SURVIVING_CONTROL = 10  # >=10 control genes for a stable baseline mean
N_CELLS_MIN = 30            # below -> underpowered_cells

# Sign tolerance for "agreement": treat |x| below this as no-sign (null).
SIGN_EPS = 1e-9

INFERENCE_STATUS = "not_calibrated"       # no calibrated null -> no p/q
CRISPRI_MODALITY = "CRISPRi_knockdown"


@dataclass(frozen=True)
class Pole:
    program_id: str
    score_field: str
    direction: str

    @property
    def sign(self) -> int:
        return POLE_SIGN[self.direction]


@dataclass(frozen=True)
class Contrast:
    objective: str = OBJECTIVE
    analysis_condition: str = ANALYSIS_CONDITION
    donor_scope: str = DONOR_SCOPE
    a: Pole = field(default_factory=lambda: Pole(A_PROGRAM_ID, A_SCORE_FIELD, A_DIRECTION))
    b: Pole = field(default_factory=lambda: Pole(B_PROGRAM_ID, B_SCORE_FIELD, B_DIRECTION))
    stage1_method_version: str = STAGE1_METHOD_VERSION
    dataset_id: str = DATASET_ID
    effect_universe_id: str = EFFECT_UNIVERSE_ID
    source_hf_revision: str = SOURCE_HF_REVISION
    source_h5ad_sha256: str = SOURCE_H5AD_SHA256


DEFAULT_CONTRAST = Contrast()
