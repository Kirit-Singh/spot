"""THE SPEC, REIMPLEMENTED. The verifier's own copy of every rule it checks.

Held here, apart from the gates, so this module can DISAGREE with the producer. Nothing in it
is imported from ``p2s_arms`` or from ``direct``: a verifier that read the generator's
thresholds would ratify whatever the generator currently says — including a rule quietly
loosened to make a result shippable, which is precisely the event it exists to catch.

The pins are LITERALS. A pin the checker borrowed from the thing it checks is a pin nobody
checked.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any

VERIFIER_ID = "spot.stage02.p2s_arms.independent_verifier.v1"

ADMIT, REJECT = "admit", "reject"          # THIS verifier's own verdict
PASS, FAIL = "pass", "fail"

# W10's verdict, in W10's spelling. NEVER transliterated: the standing cross-lane policy is
# that a translated verdict is a verdict nobody checked. W10 writes "ADMIT"; we compare to
# "ADMIT", and if the envelopes are ever unified that is W1's call, not a `.lower()` here.
W10_VERDICT_ADMIT = "ADMIT"
W10_VERIFIER_ID = "spot.stage02.direct.arm_bundle.verifier.v1"
W10_SPEC_SHA256 = "c477356278c5b7d2842659f5354792c9db7203ee774f8dd70653921124477a9f"

# WHICH CHECKER RAN. Restated here as this verifier's OWN literal, independently re-derived
# from W10's eight modules at commit 3119900. Without it, an honestly RESEALED report — one
# whose verifier_code_sha256 was blanked and whose body was then re-hashed so it agrees with
# itself — satisfies every other gate while naming no code at all.
W10_VERIFIER_CODE_SHA256 = \
    "3bc55ba51f6a8a619e9a8f47e4fd8d6318811c92048948159e8d03a93210a834"

# The Stage-2 solver lock, restated HERE as this verifier's own literal. A pin the checker
# borrowed from the thing it checks is a pin nobody checked.
PINNED_SOLVER_LOCK_SHA256 = \
    "2983d140941f13d223dad93bae71434663882f23f25f6717c3debe59d2711abe"

SUPPORT_FILE = "p2s_arm_support.parquet"
COEF_FILE = "p2s_coefficients.parquet"
RECON_FILE = "p2s_reconstruction.parquet"
DOC_FILE = "p2s_support.json"
PROVENANCE_FILE = "p2s_provenance.json"
REQUIRED_FILES = (SUPPORT_FILE, COEF_FILE, RECON_FILE, DOC_FILE, PROVENANCE_FILE)

# A temporal artifact must NOT exist. The endpoints of a temporal question are two DIRECT
# arm keys; a file keyed on an ordered condition pair is where a DiD claim would live.
FORBIDDEN_FILES = ("p2s_temporal.parquet", "p2s_temporal_endpoints.json",
                   "p2s_endpoints.parquet")

# --------------------------------------------------------------------------- #
# THE SPEC, REIMPLEMENTED. Not imported from the generator's config.
# --------------------------------------------------------------------------- #
SPEC_LANE_ROLE = "secondary_non_gating"
SPEC_RANDOM_STATE = 42
SPEC_L1_MIN, SPEC_L1_MAX = 0.0, 1.0
SPEC_NONZERO_TOL = 1e-6
SPEC_SIGN_TRANSFORM_TOL = 1e-12

# CONTINUOUS support: the SVD backprojection is dense, so there is NO discrete verdict. The
# per-row SIGN FACT is the only categorical, and it is not a support verdict.
SIGN_SUPPORTIVE, SIGN_OPPOSED, SIGN_ZERO = "supportive", "opposed", "zero"
SPEC_SIGN_VALUES = frozenset({SIGN_SUPPORTIVE, SIGN_OPPOSED, SIGN_ZERO})

# The PRIMARY estimand — exactly one fit family. Restated here as the verifier's OWN literal.
SPEC_PRIMARY_SCOPE = "all_donor"
SPEC_PRIMARY_LAYER = "zscore"
SPEC_PRIMARY_MODEL_CONFIG = "pca_on_60"
# Discrete-support / rank tokens that must NEVER appear as a support column.
FORBIDDEN_SUPPORT_TOKENS = ("support_status", "selection_frequency", "p2s_supported", "rank")

INCREASE, DECREASE = "increase", "decrease"
DESIRED_CHANGES = frozenset({INCREASE, DECREASE})
ROLES = frozenset({"away_from_A", "toward_B"})
POLES = frozenset({"high", "low"})

# The FROZEN mapping, RE-DERIVED here rather than read from the artifact.
DESIRED_CHANGE_BY_ROLE_AND_POLE = {
    ("away_from_A", "high"): DECREASE,
    ("away_from_A", "low"): INCREASE,
    ("toward_B", "high"): INCREASE,
    ("toward_B", "low"): DECREASE,
}

# The key-name firewall, written from the failures it exists to catch.
FORBIDDEN_KEY_RE = re.compile(
    r"p_value|q_value|q_val|qval|fdr|pval|padj|adj_|significance"
    r"|combined|balanced|weighted|score", re.IGNORECASE)
# ...and a STANDALONE p/q token. A substring rule for "p" would refuse every key containing
# the letter, and a firewall that refuses everything is one somebody turns off.
FORBIDDEN_TOKEN_RE = re.compile(r"(^|_)[pq](_|$)", re.IGNORECASE)

# Exempt by EXACT spelling. ``scorer_view_*`` contains "score" only because Direct's own
# field for the admitted-program view is spelled that way; it is a HASH and an ID, not a
# statistic, and renaming it would break the join it exists to make.
KEY_FIREWALL_EXCEPTIONS = frozenset({
    "scorer_view_sha256", "scorer_view_id", "stage1_scorer_view_canonical_sha256",
    "registry_scorer_projection_sha256"})

# Exempt ONLY while they still say ``false``. An artifact must be able to write down its own
# prohibition; it does not get to keep the exemption after flipping the prohibition off.
NEGATIVE_DECLARATIONS = {
    "combined_objective_permitted": False,
    "p2s_may_rank_or_gate": False,
    "coefficients_are_causal_effects": False,
    "coefficients_are_significance_tests": False,
    "temporal_did_claimed": False,
    "validates_direct_by_agreement": False,
}

# EXACT column allowlists. A rank, a gate or a promotion column is rejected by ABSENCE from
# this list — not by a name rule that would have to anticipate what it was called.
SUPPORT_COLUMNS = frozenset({
    "arm_key", "program_id", "desired_change", "condition", "target_id",
    "n_runs", "primary_coefficient", "primary_abs_coefficient", "primary_sign",
    "opposed", "primary_available",
    "sens_log_fc_sign_concordance", "n_log_fc",
    "sens_pca_off_sign_concordance", "n_pca_off",
    "lodo_sign_concordance", "n_lodo"})
COEF_COLUMNS = frozenset({
    "arm_key", "program_id", "desired_change", "condition", "target_id",
    "coefficient", "coef_fit_variation", "sign",
    "effect_layer", "model_config", "donor_scope", "quantity"})
RECON_COLUMNS = frozenset({
    "arm_key", "program_id", "desired_change", "condition",
    "effect_layer", "model_config", "donor_scope",
    "reconstruction_gene_cv_test_r2_mean", "reconstruction_gene_cv_test_r2_median",
    "reconstruction_gene_cv_test_spearman_mean", "reconstruction_gene_cv_train_r2_mean",
    "n_folds", "cv_label", "cv_semantics", "seconds", "metrics_are_sign_invariant"})
ALLOWLISTS = {SUPPORT_FILE: SUPPORT_COLUMNS, COEF_FILE: COEF_COLUMNS,
              RECON_FILE: RECON_COLUMNS}

MACHINE_PATH_RE = re.compile(r"(^|[\s\"'=(])(/home/|/Users/|/mnt/|/tmp/|[A-Za-z]:\\\\)")




# --------------------------------------------------------------------------- #
# The verifier's OWN canonical hash. Not the generator's helper.
# --------------------------------------------------------------------------- #
def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)


def content_sha256(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def num(v: Any) -> Any:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, 6)


def forbidden_keys(obj: Any, path: str = "") -> list[str]:
    """Every key matching the firewall, at ANY depth, as a dotted path.

    Walks dicts AND lists: a disguised inference field buried in a list of diagnostics is
    exactly the shape one would take.
    """
    out: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            here = f"{path}.{k}" if path else str(k)
            if _forbidden(str(k)) and not _exempt(str(k), v):
                out.append(here)
            out += forbidden_keys(v, here)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += forbidden_keys(v, f"{path}[{i}]")
    return out


def _forbidden(key: str) -> bool:
    return bool(FORBIDDEN_KEY_RE.search(key) or FORBIDDEN_TOKEN_RE.search(key))


def _exempt(key: str, value: Any) -> bool:
    if key in KEY_FIREWALL_EXCEPTIONS:
        return True
    # a negative declaration keeps its exemption only while it still says "forbidden"
    if key in NEGATIVE_DECLARATIONS:
        return value is False
    return False


def machine_paths(obj: Any, path: str = "") -> list[str]:
    out: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out += machine_paths(v, f"{path}.{k}" if path else str(k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += machine_paths(v, f"{path}[{i}]")
    elif isinstance(obj, str) and MACHINE_PATH_RE.search(obj):
        out.append(path)
    return out


def parse_arm_key(arm_key: str) -> dict[str, str]:
    """``direct|program|desired_change|condition``. Anything else is not this lane's."""
    parts = str(arm_key).split("|")
    if len(parts) != 4 or parts[0] != "direct":
        raise ValueError(f"{arm_key!r} is not a 4-part direct arm key")
    _, program_id, change, condition = parts
    if change not in DESIRED_CHANGES:
        what = ("a POLE" if change in POLES else
                "a ROLE" if change in ROLES else "not a desired change")
        raise ValueError(f"{arm_key!r} carries {what} in the desired_change slot")
    if not program_id or not condition:
        raise ValueError(f"{arm_key!r} has an empty program_id or condition")
    return {"program_id": program_id, "desired_change": change, "condition": condition}




def canonical_support(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = [{
        "arm_key": str(r["arm_key"]), "target_id": str(r["target_id"]),
        "n_runs": int(r["n_runs"]),
        "primary_coefficient": num(r["primary_coefficient"]),
        "primary_sign": str(r["primary_sign"]),
        "opposed": bool(r["opposed"]),
        "sens_log_fc_sign_concordance": num(r["sens_log_fc_sign_concordance"]),
        "sens_pca_off_sign_concordance": num(r["sens_pca_off_sign_concordance"]),
        "lodo_sign_concordance": num(r["lodo_sign_concordance"]),
    } for r in rows]
    out.sort(key=lambda r: (r["arm_key"], r["target_id"]))
    return out


def canonical_coefficients(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = [{
        "arm_key": str(r["arm_key"]), "target_id": str(r["target_id"]),
        "effect_layer": str(r["effect_layer"]), "model_config": str(r["model_config"]),
        "donor_scope": str(r["donor_scope"]), "coefficient": num(r["coefficient"]),
        "coef_fit_variation": num(r["coef_fit_variation"]),
        "sign": int(r["sign"]),
    } for r in rows]
    out.sort(key=lambda r: (r["arm_key"], r["donor_scope"], r["effect_layer"],
                            r["model_config"], r["target_id"]))
    return out


# --------------------------------------------------------------------------- #
# THE SCIENCE REPLAY. The verifier re-derives every support row FROM the coefficient parquet,
# so an artifact cannot ship arbitrary support values that merely self-hash. Reimplemented
# here, independently of the generator's stability module.
# --------------------------------------------------------------------------- #
COEFFICIENT_DECIMALS = 6
SPEC_QUANTITY = "p2s_base_coefficient"


def _sign_str(coef):
    if coef is None:
        return SIGN_ZERO
    r = round(float(coef), COEFFICIENT_DECIMALS)
    if r == 0.0:
        return SIGN_ZERO
    return SIGN_SUPPORTIVE if r > 0 else SIGN_OPPOSED


def _fam(scope, layer, cfg):
    if scope.startswith("lodo_") and layer == SPEC_PRIMARY_LAYER \
            and cfg == SPEC_PRIMARY_MODEL_CONFIG:
        return "donor_lodo"
    if scope == SPEC_PRIMARY_SCOPE and cfg == SPEC_PRIMARY_MODEL_CONFIG and layer == "log_fc":
        return "effect_layer_log_fc"
    if scope == SPEC_PRIMARY_SCOPE and layer == SPEC_PRIMARY_LAYER and cfg == "pca_off":
        return "model_config_pca_off"
    return None


def derive_support_from_coefficients(coefs):
    """Re-derive the support rows FROM the coefficient parquet. The verifier's own copy."""
    by_key = {}
    for r in coefs:
        by_key.setdefault((str(r["arm_key"]), str(r["target_id"])), []).append(r)
    out = {}
    for (arm_key, target_id), rows in by_key.items():
        primary = next((r for r in rows
                        if str(r["donor_scope"]) == SPEC_PRIMARY_SCOPE
                        and str(r["effect_layer"]) == SPEC_PRIMARY_LAYER
                        and str(r["model_config"]) == SPEC_PRIMARY_MODEL_CONFIG), None)
        pc = round(float(primary["coefficient"]), COEFFICIENT_DECIMALS) if primary else None
        psign = _sign_str(pc)
        fams = {"donor_lodo": [], "effect_layer_log_fc": [], "model_config_pca_off": []}
        for r in rows:
            f = _fam(str(r["donor_scope"]), str(r["effect_layer"]), str(r["model_config"]))
            if f:
                fams[f].append(r)

        def conc(fl):
            if psign == SIGN_ZERO or not fl:
                return None, len(fl)
            agree = sum(1 for r in fl
                        if _sign_str(round(float(r["coefficient"]), COEFFICIENT_DECIMALS))
                        == psign)
            return round(agree / len(fl), 6), len(fl)

        lc, nl = conc(fams["donor_lodo"])
        gc, ng = conc(fams["effect_layer_log_fc"])
        oc, no = conc(fams["model_config_pca_off"])
        out[(arm_key, target_id)] = {
            "n_runs": len(rows),
            "primary_coefficient": pc,
            "primary_sign": psign,
            "opposed": psign == SIGN_OPPOSED,
            "primary_available": primary is not None,
            "sens_log_fc_sign_concordance": gc, "n_log_fc": ng,
            "sens_pca_off_sign_concordance": oc, "n_pca_off": no,
            "lodo_sign_concordance": lc, "n_lodo": nl,
        }
    return out
