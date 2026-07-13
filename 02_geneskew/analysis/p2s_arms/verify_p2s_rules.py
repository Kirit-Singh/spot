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
SPEC_MIN_SELECTION = 0.5
SPEC_SIGN_DOMINANCE = 0.75
SPEC_NONZERO_TOL = 1e-6
SPEC_SIGN_TRANSFORM_TOL = 1e-12

SUPPORTED, OPPOSED, MIXED, WEAK, NOT_SELECTED = (
    "p2s_supported", "p2s_opposed", "p2s_mixed", "p2s_weak", "p2s_not_selected")
SPEC_STATUS_VALUES = frozenset({SUPPORTED, OPPOSED, MIXED, WEAK, NOT_SELECTED})

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
    "n_runs", "n_selected_runs", "selection_frequency", "positive_frequency",
    "negative_frequency", "median_coefficient", "coefficient_min", "coefficient_max",
    "lodo_sign_agreement", "n_lodo_runs", "effect_layer_agreement", "n_effect_layers",
    "support_status", "opposed"})
COEF_COLUMNS = frozenset({
    "arm_key", "program_id", "desired_change", "condition", "target_id",
    "coefficient", "coef_fit_variation", "nonzero", "sign",
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


def support_status(sel: float, pos: float, neg: float) -> str:
    """The frozen categorical rule, re-derived from the emitted frequencies."""
    if sel <= 0:
        return NOT_SELECTED
    if sel < SPEC_MIN_SELECTION:
        return WEAK
    if pos >= SPEC_SIGN_DOMINANCE:
        return SUPPORTED
    if neg >= SPEC_SIGN_DOMINANCE:
        return OPPOSED
    return MIXED


def canonical_support(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = [{
        "arm_key": str(r["arm_key"]), "target_id": str(r["target_id"]),
        "n_runs": int(r["n_runs"]),
        "selection_frequency": num(r["selection_frequency"]),
        "positive_frequency": num(r["positive_frequency"]),
        "negative_frequency": num(r["negative_frequency"]),
        "median_coefficient": num(r["median_coefficient"]),
        "support_status": str(r["support_status"]),
        "opposed": bool(r["opposed"]),
    } for r in rows]
    out.sort(key=lambda r: (r["arm_key"], r["target_id"]))
    return out


def canonical_coefficients(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = [{
        "arm_key": str(r["arm_key"]), "target_id": str(r["target_id"]),
        "effect_layer": str(r["effect_layer"]), "model_config": str(r["model_config"]),
        "donor_scope": str(r["donor_scope"]), "coefficient": num(r["coefficient"]),
        "nonzero": bool(r["nonzero"]), "sign": int(r["sign"]),
    } for r in rows]
    out.sort(key=lambda r: (r["arm_key"], r["donor_scope"], r["effect_layer"],
                            r["model_config"], r["target_id"]))
    return out
