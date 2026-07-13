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

# THE SOURCE-TREE CONTENT HASH — MANDATORY, not optional. Re-derived independently from the
# installed package directory. A commit id cannot detect a file EDITED under a pinned commit;
# the bytes can.
UPSTREAM_TREE_SHA256 = \
    "623b24ffae078d4eff7ad3484df0366ce59b884ac2b692746539ebd7fc8e5a28"
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

# THE CELL MATRIX SEMANTICS — frozen, and NEVER called raw expression. The pinned
# ntc_clustered.h5ad .X is already median-total normalised (target ~9819) then log1p, with NO
# raw counts layer. The per-program WLS beta is computed on THIS scale, so a consumer that
# assumed raw counts would misread every magnitude. Verified by the NTC pin (byte-exact) and
# declared here + in the manifest.
CELL_MATRIX_SEMANTICS = {
    "normalization": "median_total_normalize(target~9819) then log1p",
    "target_total": 9819,
    "has_raw_counts_layer": False,
    "is_raw_expression": False,
    "source": "Stage-1 ntc_clustered.h5ad .X (pinned)",
}

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
# THE ONE coefficient precision rule, used by BOTH armfit and stability. A coefficient is
# rounded to this many decimals FIRST, and its sign is the sign of the rounded value (0.0 ->
# zero). There is no second, raw-value threshold anywhere: raw 1.4e-6 must not read nonzero
# in one place and zero in another.
COEFFICIENT_DECIMALS = 6

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


# THE PAPER'S METHOD, MADE DETERMINISTIC. Marson Methods p.46 uses truncated SVD (to mitigate
# multicollinearity) then elastic net, DEFAULT D=60. Real-input validation on tcefold (Stim8
# Th2/Th1, 8947 genes x 3926 targets) settled the config:
#
#   * PCA-OFF IS MATERIALLY DIFFERENT, not a faithful P2S: coef Spearman rho 0.268 vs seeded
#     PCA, nonzero Jaccard 0.029, mean test R2 .086 vs .124. So pca_off is a NAMED SENSITIVITY,
#     never the primary — calling it method-faithful P2S would be wrong;
#   * SEEDED D=60 SVD IS BYTE-DETERMINISTIC: repeat max coefficient delta 0.0 (Spearman 1.0).
#     The determinism comes from `deterministic_p2s.seeded_upstream_svd`, which injects the
#     model's own random_state into upstream TruncatedSVD (which omits it at commit 2c2e3095).
#     Surgical: one estimator, one seed, no other upstream byte changed.
PRIMARY_CONFIG = ModelConfig("pca_on_60", True, 60)          # seeded SVD, the paper's D=60
SENSITIVITY_CONFIG = ModelConfig("pca_off", False, 0)        # named sensitivity ONLY
CONFIGS = (PRIMARY_CONFIG, SENSITIVITY_CONFIG)
N_PCS = 60

PCA_DETERMINISM_MECHANISM = (
    "seeded via deterministic_p2s.seeded_upstream_svd — it injects model.random_state into "
    "upstream TruncatedSVD, which omits it at commit 2c2e3095. Verified on tcefold: repeat "
    "max coefficient delta = 0.0 for the seeded D=60 SVD; the UNSEEDED magnitude is "
    "data-dependent and materially nonzero, which is why the seed is required")
DETERMINISM_SCOPE = (
    "seeded D=60 SVD is the method-faithful PRIMARY (Marson Methods p.46); pca_off is a NAMED "
    "SENSITIVITY that materially differs (coef rho 0.268) and is labelled as such")
# We read coefficients via get_coefs() and metrics via model.eval, NEVER get_prediction —
# whose pca=None branch uses the UNSCALED X_array despite fitting on a StandardScaler. The
# deterministic wrapper refuses pca_off for exactly this reason (fails closed).
UPSTREAM_PREDICTION_PATH_USED = False

# --------------------------------------------------------------------------- #
# SUPPORT — CONTINUOUS, because the SVD backprojection is DENSE.
#
# Under the seeded D=60 SVD, get_coefs() back-projects the elastic-net coefficients through
# the PCA components, and that projection is DENSE: real-input validation found 3923/3926
# targets nonzero. A "selection frequency" built on `coefficient != 0` would therefore mark
# nearly EVERY target as selected — the flag would say "supported" about almost everything and
# mean nothing.
#
# So there is NO discrete p2s_supported/opposed/weak flag. The lane emits the CONTINUOUS
# quantities a reader can threshold PROSPECTIVELY for themselves: the coefficient magnitude,
# its sign, and the sign AGREEMENT across runs. No threshold is invented here.
SUPPORT_IS_CONTINUOUS = True
SUPPORT_IS_DISCRETE_FLAG = False
DENSE_BACKPROJECTION_NOTE = (
    "the seeded SVD backprojection is dense (~3923/3926 targets nonzero), so a "
    "nonzero-selection-frequency cannot define support; this lane emits continuous "
    "coefficient magnitude + sign stability and defines no discrete support threshold")
# The sign a coefficient carries is still meaningful (a negative coefficient is OPPOSED — the
# inverse of the measured knockdown). Sign STABILITY across runs is emitted; a magnitude
# threshold is the consumer's, defined prospectively, never here.
SIGN_OPPOSED = "opposed"              # a per-row sign fact, NOT a support verdict
SIGN_SUPPORTIVE = "supportive"
SIGN_ZERO = "zero"

# THE PRIMARY ESTIMAND — exactly one fit family. Everything else is a NAMED SENSITIVITY and
# is never pooled into the primary magnitude or sign. Pooling across donor scopes, effect
# layers and config families would blend different estimands and let a sensitivity move the
# number a reader sees as "the" P2S coefficient.
PRIMARY_SCOPE = "all_donor"
PRIMARY_LAYER = AUTHOR_LAYER               # zscore
PRIMARY_MODEL_CONFIG = "pca_on_60"         # the seeded D=60 SVD

# The sensitivity families, each typed. A reader compares them to the primary; they never
# determine it.
SENSITIVITY_FAMILIES = {
    "effect_layer_log_fc": "same fit, log_fc instead of zscore",
    "model_config_pca_off": "same fit, PCA disabled (materially different; see config)",
    "donor_lodo": "leave-one-donor-out; OVERLAPPING, not independent replicates",
}

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


# --------------------------------------------------------------------------- #
# THE W10 ADMISSION CONTRACT.
#
# P2S may run ONLY from a real Direct arm bundle that W10 -- the INDEPENDENT on-disk
# verifier, which is not the producer -- has ADMITTED. Everything below is pinned so that a
# report cannot be swapped for a friendlier one, and so that a bundle cannot arrive
# ADMITTING ITSELF.
#
# A generator that signs its own homework is the same process asserting twice. The Direct
# producer therefore writes `verdict: pending_independent_verification` and
# `verifier_id: null` into its own verification.json -- that is a SLOT, not a verdict -- and
# W10 fills it from outside. A "report" carrying the pending verdict, or a null verifier id,
# is a bundle admitting itself and is REFUSED.
# --------------------------------------------------------------------------- #
W10_VERIFIER_ID = "spot.stage02.direct.arm_bundle.verifier.v1"

# WHICH CHECKER RAN. The sha256 over W10's verifier modules, exactly as
# `verify_arm_report.verifier_code_sha256()` combines them: {module: sha256(file)} ->
# canonical json -> sha256.
#
# RE-DERIVED INDEPENDENTLY from the git blobs at W10 head f6da804 — not copied from a
# report, and not imported from W10's code. It matched (see the re-derivation test).
#
# THIS IS THE PRODUCER-CODE-ROOT W10 (independently GO at f6da804). It supersedes the
# target-identity-aware 2c3031e (8290…715f): gate_code_identity now re-derives the code
# manifest from the PRODUCER's SUPPLIED git checkout — proving the producer tree's git HEAD is
# the bound commit and its working state is the declared one — instead of walking the verifier's
# own checkout. Three verifier modules changed, so the code hash moved with them (still NINE
# modules). A P2S pinned to any earlier hash would reject every valid report the current Direct
# producer emits — this is the pin that keeps them consumable.
#
# WHY IT IS PINNED AND NOT MERELY RECORDED. Without this, an HONESTLY RESEALED report
# passes: take a real ADMIT, set `verifier_code_sha256` to 00...00, re-hash the body so
# `report_sha256` agrees with it, and every other gate is satisfied. The report is then
# internally consistent and says nothing about which code produced the verdict. A checker
# that will not name its own code is unfalsifiable, and a name nobody checks is not a name.
W10_VERIFIER_CODE_SHA256 = \
    "943d32bd5317bbc84d2705a39f98de024f10548d1995cd6bc42ed56fb9efc174"
W10_VERIFIER_COMMIT_HINT = "f6da804"
W10_VERIFIER_N_MODULES = 9
W10_REPORT_SCHEMA = "spot.stage02_direct_arm_bundle_verification.v1"
W10_SPEC_SHA256 = "c477356278c5b7d2842659f5354792c9db7203ee774f8dd70653921124477a9f"
W10_VERDICT_ADMIT = "ADMIT"                       # uppercase, as W10 writes it
W10_VERDICT_REFUSE = "REFUSE"
W10_VERDICT_PENDING = "pending_independent_verification"   # the producer's SLOT, not a verdict

# The Stage-2 solver lock (W7), pinned. The Direct arms P2S supports must have been computed
# under the SAME lock this run executes under -- otherwise support computed in one
# environment is being attached to arms computed in another, and nothing says so.
PINNED_SOLVER_LOCK_SHA256 = \
    "2983d140941f13d223dad93bae71434663882f23f25f6717c3debe59d2711abe"
SOLVER_LOCK_FILENAME = "stage02_solver_lock.txt"

# The files an ADMITTED Direct bundle ships — THE AUTHORITATIVE INVENTORY, imported from
# Direct's own `arm_artifacts.VERIFIED_PATHS` (one shared constant, incl. target_identity.json).
# Every one is re-hashed and matched EXACTLY against the report's `artifact_sha256` map.
# `verification.json` is NOT in this set: it is the producer's empty slot that W10 fills, and
# it is checked separately (self-admission), not as a producer artifact.
from direct import arm_artifacts as _arm_artifacts  # noqa: E402

DIRECT_BUNDLE_FILES = tuple(_arm_artifacts.VERIFIED_PATHS)
TARGET_IDENTITY_FILE = _arm_artifacts.TARGET_IDENTITY_FILE

# A RELEASE lane. `synthetic` is not one: synthetic arms may never carry production support.
RELEASE_LANES = ("production", "research_only")
LANE_SYNTHETIC = "synthetic"
LANES = RELEASE_LANES + (LANE_SYNTHETIC,)


# --------------------------------------------------------------------------- #
# THE PINNED PUBLIC INPUTS. Marson GWCD4i only; nothing else is an experimental source.
#
# Hashed at RUNTIME from the bytes handed in, and refused on any mismatch. A path is not an
# input: two files can sit at the same path on two hosts and be different science.
# --------------------------------------------------------------------------- #
# The Stage-1 cell matrix. Public: HF KiritSingh/spot-CD4-Marson @ e5fcf98b.
# 396,000 cells x 18,130 genes; var/_index is SYMBOLS (see the namespace rule below).
NTC_H5AD_SHA256 = \
    "2edc6d318415c8b0ee779d707ab86e26ddb6f0274db51ab4a12f21ebfda50e43"
NTC_HF_SOURCE = "KiritSingh/spot-CD4-Marson"
NTC_HF_REVISION = "e5fcf98b56a9302921d402e97fc5a190bd88f9a6"
NTC_N_CELLS = 396000

# The pooled DE readout. var/gene_ids is ENSEMBL; var/gene_name is the SYMBOL.
#
# TCEFOLD ONLY. tcedirector reads this file NON-DETERMINISTICALLY -- stable mtime and size,
# a DIFFERENT sha256 on re-read (c355f535 -> dc503816). A run whose input hashes differently
# on two reads cannot be content-addressed at all, so preparation REFUSES on any host where
# the bytes do not hash to the pin. That refusal is the gate working.
DE_MAIN_SHA256 = \
    "c355f535ff32cf7ba1edc49cf9c6039fe84f2c9ebe4d005515cba75790cfbb62"

CONDITIONS = ("Rest", "Stim8hr", "Stim48hr")

# THE SCORE FIELD RULE. Stage-1 names a program's score column `<program_id>_score`, and the
# scores are READ BY BARCODE from the authoritative full table -- never recomputed here. A
# recomputed score is a different score wearing the released one's name, and it would agree
# with the released one closely enough that nobody would check.
SCORE_FIELD_SUFFIX = "_score"
STAGE1_SCORES_N_ROWS = 396000

# THE NAMESPACE RULE. The cell matrix is keyed on SYMBOLS; the readout universe is ENSEMBL.
# The crosswalk is the DE readout's own (gene_name -> gene_ids), and an AMBIGUOUS symbol --
# one naming more than one Ensembl id -- is DROPPED with a named reason, never guessed.
GENE_NAMESPACE_CELLS = "symbol"
GENE_NAMESPACE_READOUT = "ensembl"
NAMESPACE_RULE_ID = "spot.stage02.p2s.namespace.symbol_to_ensembl_via_de_readout.v1"

# Preparation output identity.
SCHEMA_INPUTS = "spot.stage02_p2s_prepared_inputs.v1"
PREPARE_ID = "spot.stage02.p2s_arms.prepare_inputs.v1"


# --------------------------------------------------------------------------- #
# TWO ENVIRONMENTS, TWO LOCKS. They are not interchangeable and neither stands in for the
# other.
#
#   * the DIRECT solver lock (2983d140) pins the environment the ADMITTED DIRECT ARMS were
#     computed in. It does NOT contain sklearn and it does NOT contain pert2state_model, so
#     it cannot execute this lane and it is a lie to imply that it does;
#   * the P2S RUNTIME lock pins the environment THIS lane executes in — sklearn, and the
#     pinned pert2state_model tree.
#
# Both are bound. A run that recorded only the Direct lock would be claiming its numbers came
# out of an environment that cannot produce them.
# --------------------------------------------------------------------------- #
P2S_RUNTIME_LOCK_SHA256 = \
    "93823984bda6053c19bf758c38abd91644e50a761d62679449a48cf5312a5c42"
P2S_RUNTIME_LOCK_FILENAME = "stage02_p2s_runtime_lock.txt"
# Committed beside the package (like the Direct lock), copied byte-for-byte from tcefold.
import os as _os  # noqa: E402

P2S_RUNTIME_LOCK_PATH = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
    "analysis", P2S_RUNTIME_LOCK_FILENAME)
LOCK_ROLES = {
    "direct_solver_lock": "the environment the ADMITTED DIRECT ARMS were computed in",
    "p2s_runtime_lock": "the environment THIS lane executes in (sklearn + pert2state_model)",
}
DIRECT_LOCK_EXECUTES_P2S = False

# --------------------------------------------------------------------------- #
# STAGE-1 SCORES. Both hashes are AUTHORITATIVE and HARD-GATED — raw AND canonical.
# --------------------------------------------------------------------------- #
STAGE1_SCORES_RAW_SHA256 = \
    "de63b496e8121c77babe380e0c3b5ddfd66f9ce67d0d4e80f55645d177e27e5f"
# REPRODUCED and GATED. The recipe: primary field order (NOT alphabetical), stable
# argsort(barcode), f"{round(x,5):.5f}" per field, rows tab-joined, body newline-joined WITH
# a trailing newline. See ``stage1_canonical``. The earlier "could not reproduce" was a wrong
# FIELD ORDER; with the correct order it matches the parquet byte-for-byte.
STAGE1_SCORES_CANONICAL_SHA256 = \
    "43c4296d5166740c334441a69df23bb440a073382bbe79628a3bb89e43d51316"
STAGE1_SCORES_CANONICAL_INDEPENDENTLY_REPRODUCED = True
STAGE1_SCORES_CANONICAL_STATUS = (
    "REPRODUCED byte-for-byte from the parquet and GATED (not advisory). Both the raw sha256 "
    "and this canonical hash are hard gates: the raw pins the bytes, the canonical pins the "
    "science those bytes encode in Stage-1's frozen form")
STAGE1_SCORES_N_ROWS_PER_CONDITION = 132000

# --------------------------------------------------------------------------- #
# THE ACTIVATION COVARIATE IS NOT A PROGRAM ARM.
#
# `diff_activated` IS the activation covariate. Fitting an arm for it would put the same
# quantity on both sides of the design — `mean_expr ~ 1 + z_diff_activated + activation +
# donor` with z == activation — a perfectly collinear design whose beta is not identified.
# The lane emits a TYPED UNAVAILABLE disposition for it rather than a number, and it is NOT
# counted as a successful program-condition unit.
# --------------------------------------------------------------------------- #
ACTIVATION_IS_NOT_AN_ARM = True
ACTIVATION_ARM_UNAVAILABLE_REASON = "program_is_the_activation_covariate_of_its_own_design"

# The DIRECT screen's REAL eligibility states (the admitted bundle's own vocabulary).
QC_PASS_STATES = ("qc_pass_single_guide", "qc_pass_two_guide", "qc_pass_multi_guide")
# Eligibility is decided by the arms.parquet `evaluable` BOOLEAN (arm-specific), not by
# matching base_state to a vocabulary. base_state is recorded as provenance; the real Direct
# vocabulary is QC_PASS_STATES, and the fixtures use it.

# The DIRECT mask contract: masks are selected by the FULL estimate identity, never unioned
# across scopes. A guide-scope or donor-scope mask row is a mask for a DIFFERENT estimate.
MASK_GENE_COLUMN = "masked_gene_ensembl"
MASK_MAIN_ESTIMATE_TYPE = "main"
MASK_MAIN_ESTIMATE_ID = "main"
MASK_SCOPES_MAY_BE_UNIONED = False
