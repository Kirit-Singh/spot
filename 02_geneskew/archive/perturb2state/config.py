"""Frozen Perturb2State configuration (plan §6.2-§6.6).

EVERY value here was frozen BEFORE inspecting any target identity / coefficient
(plan §6.4, §6.6). Perturb2State is secondary; nothing in this module can change
the direct Stage-2 ranking (plan §6.7).
"""
from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# Pinned upstream software (plan §6, §12).
# --------------------------------------------------------------------------- #
P2S_REPO = "emdann/pert2state_model"
P2S_COMMIT = "2c2e30959ffafadecc6af5d4d7b5bde868ab5313"
P2S_LICENSE = "MIT"
P2S_PROVENANCE = (
    "Perturb2StateModel is pre-existing upstream MIT software by the dataset "
    "authors. spot contributes the Stage-1-selected contrast, broad "
    "target-signature construction, masking, stability design, execution, "
    "verification and UI integration. The authors' Th1/Th2 result is not a "
    "new spot result."
)

# --------------------------------------------------------------------------- #
# Broad target-signature construction (plan §6.2).
# --------------------------------------------------------------------------- #
ANALYSIS_CONDITION = "Stim48hr"           # inherited from the locked contrast
DONORS = ["D1", "D2", "D3", "D4"]         # all-donor scope; LODO leaves one out

# Activation covariate: the diff_activated program score. Neither selected pole
# (treg_like / th1_like) is the activation program, so there is no collinear
# activation confound (plan §6.2.7). Recorded in the signature manifest.
ACTIVATION_PROGRAM_ID = "diff_activated"

# Donor-stratified pseudobulk quantile bins from the continuous scores
# (plan §6.2.3 — NOT biological cell-type thresholds, §6.2.4).
N_SCORE_BINS = 10                          # deciles along z_A and along z_B

# Per-gene donor-aware continuous model (plan §6.2.5):
#   mean_expression_g ~ 1 + z_A + z_B + activation + donor
# fit by weighted least squares across pseudobulk units (weight = n_cells).
SIGNATURE_MODEL = ("WLS mean_expr_g ~ 1 + z_A + z_B + activation + donor(K-1 dummies); "
                   "weight=n_cells_unit")

# Signature normalisation (plan §6.2.11): z-score away/toward SEPARATELY across
# the readout gene universe, then combined = away_norm + toward_norm.
SIGNATURE_NORMALIZATION = ("per-gene-universe z-score of away and toward separately; "
                           "combined = away_norm + toward_norm")

# THE ARM LANES, named EXACTLY as Direct names its arms. They used to be spelled
# ``toward_b`` here and ``toward_B`` in Direct — the retired v2 casing on one side of a
# join and the current casing on the other. Nothing joined them, so nothing noticed; the
# first code to merge P2S onto the screen by lane name would have silently matched zero
# rows for that arm and reported no support where support existed.
ARM_LANES = ["away_from_A", "toward_B"]

# THE QUARANTINED LANE. ``combined_A_to_B`` is z(away) + z(toward): a combined objective.
# It is retained ONLY as a reconstruction diagnostic — it answers "does the fitted
# perturbation signature reconstruct the summed direction at all", which is a question
# about the MODEL, not about a target's priority. It may never rank, gate, order or
# promote anything, it is excluded from the integration lane a consumer reads, and the
# name says so.
RECONSTRUCTION_DIAGNOSTIC_LANE = "combined_A_to_B"
RECONSTRUCTION_DIAGNOSTIC_IS_RANKING = False
RECONSTRUCTION_DIAGNOSTIC_EXCLUDED_FROM = [
    "integration_lane", "joint_ordering", "support_status", "any_rank_or_gate",
]

LANES = ARM_LANES + [RECONSTRUCTION_DIAGNOSTIC_LANE]

# --------------------------------------------------------------------------- #
# Perturbation matrix (plan §6.3).
# --------------------------------------------------------------------------- #
EFFECT_LAYERS = ["zscore", "log_fc"]       # zscore = author-compatible; log_fc = sensitivity
AUTHOR_LAYER = "zscore"
# Only direct-screen ELIGIBLE targets become perturbation columns.
ELIGIBLE_STATES = ("eligible_two_guide", "eligible_single_guide")
MASK_NEUTRAL_VALUE = 0.0                    # masked coords -> 0 before scaling (§6.3)

# --------------------------------------------------------------------------- #
# Model configuration set (plan §6.4) — frozen bounded set.
# positive=False is REQUIRED: a negative coefficient = use of the INVERSE of the
# measured knockdown, i.e. OPPOSED for a CRISPRi/inhibition hypothesis (§6.4).
# --------------------------------------------------------------------------- #
POSITIVE = False
RANDOM_STATE = 42
N_SPLITS = 5                               # gene-fold CV (§6.4/§6.5)
N_REPEATS = 1
# CALIBRATION NOTE (frozen before unblinding): the matrix has ~7,163 features on
# ~9,900 genes, so each nested-CV ElasticNetCV fit costs ~90-170s. A single
# 5-fold gene split (N_REPEATS=1) and a 2-point alpha grid were chosen on
# COMPUTE + AGGREGATE-SPARSITY grounds only — a pre-flight calibration inspected
# wall-clock, the selection COUNT (387/7163 nonzero on the combined lane) and the
# CV-selected alpha (0.1), never which targets were selected. The full run stays
# under ~45 min and well under the 31 GB host limit.
EN_ALPHAS = [0.1, 1.0]
EN_L1_RATIOS = [0.5]


@dataclass(frozen=True)
class ModelConfig:
    name: str
    pca_transform: bool
    n_pcs: int


# PCA off + PCA on with a prospectively chosen component count supported by the
# matrix dimensions (genes >> n_pcs). No configuration was chosen by gene name.
CONFIGS = [
    ModelConfig("pca_off", False, 0),
    ModelConfig("pca_on_50", True, 50),
]

# --------------------------------------------------------------------------- #
# Stability (plan §6.6).
# --------------------------------------------------------------------------- #
# Numerical nonzero tolerance, frozen before inspecting any target identity.
NONZERO_TOL = 1e-6
# coef_sem from get_coefs() is variation across overlapping fits, NOT inference
# (plan §6.5). It is retained under this name and never emitted as a p-value.
COEF_SEM_SEMANTICS = "fit_variation_not_inference"
RECONSTRUCTION_CV_LABEL = "reconstruction_gene_cv"   # NEVER donor/guide/holdout/external

# Categorical support rule (plan §6.6) — frozen BEFORE unblinding target
# identities. The underlying frequencies/signs are ALWAYS retained regardless.
# A POSITIVE coefficient uses the measured knockdown signature as-is (supportive
# for a CRISPRi/inhibition hypothesis); a NEGATIVE coefficient uses its inverse
# (opposed).
#
# SUPPORT IS JUDGED PER ARM. It used to be judged on ``combined_A_to_B``, and that lane
# is z(away) + z(toward) — an unweighted sum of two z-scored arms, which is a COMBINED
# OBJECTIVE by any other name. Direct refuses one for the reason it always refuses one:
# summing the arms fixes an exchange rate between "moved away from A" and "moved toward
# B" that nobody has, and it lets a target that opposes B carry a strong combined score
# on the strength of its away arm alone.
#
# P2S never ranked anything, so this was not a Direct defect — but it was the same
# mistake one layer out. A consumer reading a single ``perturb2state_support_status``
# derived from the summed lane cannot tell WHICH arm the support is for, and "supported"
# on a target whose support is entirely away-arm and whose toward arm is opposed is a
# sentence that means the opposite of what it appears to mean.
#
# So support is emitted once PER DIRECT ARM, under the arms' own names, and the combined
# lane is quarantined below.
SUPPORT_LANES = ["away_from_A", "toward_B"]
SUPPORT_MIN_SELECTION = 0.5        # nonzero-selection frequency to be "selected"
SUPPORT_SIGN_DOMINANCE = 0.75      # fraction of selected runs sharing one sign
SUPPORT_STATUS_VALUES = [
    "p2s_supported",       # selected + positive sign dominant
    "p2s_opposed",         # selected + negative sign dominant (inverse knockdown)
    "p2s_mixed",           # selected but neither sign dominates
    "p2s_weak",            # selected in <50% of runs
    "p2s_not_selected",    # never selected
]
