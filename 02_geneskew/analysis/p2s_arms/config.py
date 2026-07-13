"""Frozen configuration for the v2 reusable-arm SECONDARY lane.

Everything here was frozen BEFORE inspecting any target identity or coefficient.

WHAT THIS LANE IS
-----------------
Reconstruction support for ONE reusable Direct arm, keyed

    direct | program_id | desired_change | condition

It is SECONDARY and NON-GATING. It is not part of "complete Stage-2" (Direct + Pareto +
temporal + pathway), it cannot gate that set, and it cannot alter it. Nothing here can
promote, demote, rescue, admit, gate, reorder or re-rank a Direct target, and nothing here
validates a Direct result merely by agreeing with it.

WHY THERE IS NO LANE LIST
-------------------------
The legacy lane carried ``ARM_LANES = ["away_from_A", "toward_B"]`` — a pair vocabulary. A
role is a position in somebody's PAIR, not a property of an arm, so it cannot key one. The
v2 lane keys on the arm's DESIRED CHANGE and therefore needs no lane list at all: the arm
key IS the lane. There is likewise no ``combined_A_to_B``: not quarantined, ABSENT.

WHY THERE IS NO ``production_eligible``
---------------------------------------
The historical 0/33 LOMO selectability result is descriptive evidence about single-marker
dependence. It is NOT a production blocker and it does not suppress an otherwise
base-portable arm. Execution is governed by the Stage-1 v3 scorer view's ``base_portable``
programs (10 of 11; Th9 excluded as non-portable). A ``production_eligible=false`` field
pinned to 0/33 would be a misleading gate, so this lane emits none. It binds
``base_portable`` and ``lane_role`` instead, and any LOMO diagnostic stays separately
traceable downstream.
"""
from __future__ import annotations

from dataclasses import dataclass

# --------------------------------------------------------------------------- #
# Identity.
# --------------------------------------------------------------------------- #
METHOD_ID = "spot.stage02.p2s_arms.reusable_arm_reconstruction_support"
METHOD_VERSION = "stage2-p2s-arms-v2-per-program-refit"
SCHEMA_SUPPORT = "spot.stage02_p2s_arm_support.v1"
SCHEMA_PROVENANCE = "spot.stage02_p2s_arm_provenance.v1"
RUNNER_ID = "spot.stage02.p2s_arms.runner.v1"
RUN_ID_LEN = 16

# THE role of this lane, in its own bytes. A consumer that reads nothing else reads this.
LANE_ROLE = "secondary_non_gating"

# --------------------------------------------------------------------------- #
# Pinned upstream software. VERIFIED AT RUNTIME (see ``upstream.py``) — never echoed.
# --------------------------------------------------------------------------- #
UPSTREAM_REPOSITORY = "emdann/pert2state_model"
UPSTREAM_COMMIT = "2c2e30959ffafadecc6af5d4d7b5bde868ab5313"
UPSTREAM_LICENSE = "MIT"
UPSTREAM_VERSION = "0.0.1"
UPSTREAM_PROVENANCE = (
    "Perturb2StateModel is pre-existing upstream MIT software by the dataset authors. "
    "spot contributes the per-program signature construction, masking, stability design, "
    "execution, verification and UI integration. The authors' result is not a spot result.")

# --------------------------------------------------------------------------- #
# The per-program base signature (the pair binding removed).
#
# Legacy fit BOTH programs in one model:
#     mean_expr_g ~ 1 + z_A + z_B + activation + donor
# so an arm's value depended on WHICH OTHER PROGRAM shared the fit. The same arm_key would
# carry different values in different pairs — cached, and served interchangeably.
#
# v2 fits ONE program:
#     mean_expr_g ~ 1 + z_P + activation + donor(K-1)
# and the arm is reusable by construction.
# --------------------------------------------------------------------------- #
ACTIVATION_PROGRAM_ID = "diff_activated"

# Donor-stratified 2-D quantile pseudobulk, on EXACTLY the axes that are regressed on:
# (z_P, activation). Legacy binned on (z_A, z_B) because those were its two regressors;
# the rule is the same, the regressors changed. Binning on z_P alone would average
# activation away inside each bin and strip the covariate of the leverage it exists to
# have — the confound would leak straight back into beta_P.
N_SCORE_BINS = 10                    # 10 x 10 = 100 units/donor, as legacy
BINNING_AXES = ("z_program", "activation")

SIGNATURE_MODEL_ID = "spot.stage02.p2s_arms.signature.per_program_wls.v1"
SIGNATURE_MODEL = ("WLS mean_expr_g ~ 1 + z_program + activation + donor(K-1 dummies); "
                   "weight=n_cells_unit; solved by lstsq on sqrt(W)D and sqrt(W)Y")
SIGNATURE_NORMALIZATION = "per-gene-universe standardisation of the fitted z_program beta"

# Remediation rule 8: a stable least-squares solve, NEVER the normal equations. D'WD is the
# square of the condition number, and a rank-deficient donor block would come back as
# plausible numbers rather than as a failure.
SOLVER = "lstsq_on_sqrt_w_design"
NORMAL_EQUATIONS_PERMITTED = False

# Stage-1 v3 scores are READ BY BARCODE. Never silently recomputed: a recomputed score is a
# different score wearing the released one's name.
STAGE1_VALUES_READ_BY_BARCODE = True

# --------------------------------------------------------------------------- #
# The perturbation matrix.
# --------------------------------------------------------------------------- #
EFFECT_LAYERS = ("zscore", "log_fc")     # values, not key names
AUTHOR_LAYER = "zscore"
ELIGIBLE_STATES = ("eligible_two_guide", "eligible_single_guide")
MASK_NEUTRAL_VALUE = 0.0

# --------------------------------------------------------------------------- #
# The model. Deterministic; the grid frozen before unblinding.
# --------------------------------------------------------------------------- #
RANDOM_STATE = 42

# REQUIRED. A negative coefficient is use of the INVERSE of the measured knockdown — i.e.
# OPPOSED for a CRISPRi/inhibition hypothesis. Forcing positivity would silently convert
# every opposed contributor into a zero, which is the one thing this lane must not do.
#
# It is also what makes the two arms an exact sign transform: the ElasticNet objective is
# symmetric in b, so y -> -y implies b* -> -b*. With positive=True it is not.
POSITIVE = False

N_SPLITS = 5                             # gene-fold CV
N_REPEATS = 1
ALPHA_GRID = (0.1, 1.0)
L1_RATIO_GRID = (0.5,)

# The l1 ratio is a MIXING fraction. Anything outside [0, 1] is not a weaker or stronger
# penalty — it is not a penalty at all, and sklearn will either refuse it or silently
# produce a fit nobody can interpret. Validated, never assumed.
L1_RATIO_MIN = 0.0
L1_RATIO_MAX = 1.0

NONZERO_TOL = 1e-6

# ``coef_sem`` from the upstream model is variation ACROSS OVERLAPPING FITS. It is not
# inference, and it is never emitted under a name that could be read as one.
COEF_SEM_COLUMN = "coef_fit_variation"
COEFFICIENT_SEMANTICS = "conditional_reconstruction_weight_not_inference_not_causal"

# Gene-fold CV. NEVER donor / guide / holdout / external validation.
RECONSTRUCTION_CV_LABEL = "reconstruction_gene_cv"
RECONSTRUCTION_CV_SEMANTICS = (
    "cross-validation across GENE folds of the reconstruction fit; it is not donor "
    "validation, not guide validation, not a perturbation holdout and not external "
    "validation")


@dataclass(frozen=True)
class ModelConfig:
    name: str
    pca_transform: bool
    n_pcs: int


CONFIGS = (ModelConfig("pca_off", False, 0),
           ModelConfig("pca_on_50", True, 50))

# --------------------------------------------------------------------------- #
# Support. Judged PER ARM — there is no other kind of support here.
# --------------------------------------------------------------------------- #
SUPPORT_MIN_SELECTION = 0.5           # nonzero-selection frequency to count as "selected"
SUPPORT_SIGN_DOMINANCE = 0.75         # fraction of selected runs sharing one sign

SUPPORTED = "p2s_supported"           # selected + positive sign dominant
OPPOSED = "p2s_opposed"               # selected + negative sign dominant (inverse knockdown)
MIXED = "p2s_mixed"                   # selected, neither sign dominates
WEAK = "p2s_weak"                     # selected in < 50% of runs
NOT_SELECTED = "p2s_not_selected"     # never selected
SUPPORT_STATUS_VALUES = (SUPPORTED, OPPOSED, MIXED, WEAK, NOT_SELECTED)

# --------------------------------------------------------------------------- #
# What this lane does NOT emit. Absence, not prohibition-by-check.
# --------------------------------------------------------------------------- #
# NO rank column, anywhere. A lane with no rank column has no surface on which to reorder
# anything — which is a stronger guarantee than a rule saying it must not.
RANK_COLUMN_EMITTED = False

# The NEGATIVE DECLARATIONS. Each is exempt from the key-name firewall ONLY while it still
# says ``false``: an artifact has to be able to write down its own prohibition, but it does
# not get to keep the exemption after flipping the prohibition off.
NEGATIVE_DECLARATIONS: dict[str, bool] = {
    "combined_objective_permitted": False,
    "p2s_may_rank_or_gate": False,
    "coefficients_are_causal_effects": False,
    "coefficients_are_significance_tests": False,
    "temporal_did_claimed": False,
    "validates_direct_by_agreement": False,
}

# There is NO temporal artifact. A DiD claim needs a field that is a function of BOTH
# endpoints, and no file exists in which to write one. The endpoints of a temporal question
# are two DIRECT arm keys, which already exist; the consumer joins them.
TEMPORAL_ARTIFACT_EMITTED = False
