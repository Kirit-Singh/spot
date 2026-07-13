"""The INDEPENDENT verifier for the P2S secondary arm artifact. generator != verifier.

It imports NOTHING from ``p2s_arms`` and NOTHING from ``direct``. Every rule below is this
module's OWN reimplementation of the written spec, held here so it can DISAGREE with the
generator. A verifier that called the producer's hash helper, or read the producer's
thresholds, would agree with it by construction — including with a rule quietly loosened to
make a result shippable, which is precisely the event this exists to catch.

It reads the SHIPPED BYTES back off disk. Never a caller's dict: a verifier handed the
object the producer still has in memory has verified the producer's intent, not its output.

WHAT IT RE-DERIVES, RATHER THAN READS
-------------------------------------
  * the content hashes, with its own canonical serialiser;
  * the arm-key grammar, and the frozen role x pole -> desired_change mapping;
  * the support-status rule, from the emitted frequencies;
  * the SIGN-TRANSFORM identity: the two arms of a program must be exact negations, because
    they are one measurement and a sign. If they are not, somebody re-fitted the second arm
    and the two can now disagree about a magnitude they share;
  * the key-name firewall, and the exact column allowlist per file.

Exit 0 = ADMIT. Exit 1 = REJECT. Fail-closed: any failed check rejects the artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from typing import Any

import pandas as pd

VERIFIER_ID = "spot.stage02.p2s_arms.independent_verifier.v1"

ADMIT, REJECT = "admit", "reject"
PASS, FAIL = "pass", "fail"

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
KEY_FIREWALL_EXCEPTIONS = frozenset({"scorer_view_sha256", "scorer_view_id"})

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


class Report:
    """Fail-closed. Any failed check REJECTS the artifact."""

    def __init__(self) -> None:
        self.checks: list[dict[str, Any]] = []

    def check(self, name: str, ok: bool, detail: str = "") -> bool:
        self.checks.append({"check": name, "status": PASS if ok else FAIL,
                            "detail": detail})
        return bool(ok)

    @property
    def failed(self) -> list[dict[str, Any]]:
        return [c for c in self.checks if c["status"] == FAIL]

    @property
    def verdict(self) -> str:
        return REJECT if self.failed else ADMIT

    def document(self) -> dict[str, Any]:
        doc = {
            "verifier_id": VERIFIER_ID,
            "verdict": self.verdict,
            "n_checks": len(self.checks),
            "n_failed": len(self.failed),
            "checks": self.checks,
        }
        doc["report_sha256"] = content_sha256(doc)
        return doc


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


# --------------------------------------------------------------------------- #
# The rules, re-derived.
# --------------------------------------------------------------------------- #
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


# --------------------------------------------------------------------------- #
def verify(out_dir: str) -> dict[str, Any]:
    """Read the shipped bytes and re-derive everything. Fail-closed."""
    rep = Report()

    present = [f for f in REQUIRED_FILES if os.path.exists(os.path.join(out_dir, f))]
    if not rep.check("every required file is present", len(present) == len(REQUIRED_FILES),
                     f"missing {sorted(set(REQUIRED_FILES) - set(present))}"):
        return rep.document()

    stray = [f for f in FORBIDDEN_FILES if os.path.exists(os.path.join(out_dir, f))]
    rep.check("no temporal artifact is emitted", not stray,
              "a DiD claim needs a field that is a function of BOTH endpoints, and this "
              f"lane emits no file in which to write one; found {stray}")

    with open(os.path.join(out_dir, DOC_FILE)) as fh:
        doc = json.load(fh)
    with open(os.path.join(out_dir, PROVENANCE_FILE)) as fh:
        prov = json.load(fh)

    support = pd.read_parquet(os.path.join(out_dir, SUPPORT_FILE)).to_dict("records")
    coefs = pd.read_parquet(os.path.join(out_dir, COEF_FILE)).to_dict("records")
    recon = pd.read_parquet(os.path.join(out_dir, RECON_FILE)).to_dict("records")

    # -- 1. content-addressed: the id must FOLLOW the content ------------------ #
    rep.check("support_rows_sha256 is the hash of the shipped support rows",
              doc.get("support_rows_sha256") == content_sha256(canonical_support(support)),
              "an artifact whose id does not follow its content can be edited and keep its "
              "name")
    rep.check("coefficient_rows_sha256 is the hash of the shipped coefficient rows",
              doc.get("coefficient_rows_sha256")
              == content_sha256(canonical_coefficients(coefs)))

    # -- 2. exact column allowlists: a rank/gate column is rejected by ABSENCE -- #
    for fname, allowed in ALLOWLISTS.items():
        cols = set(pd.read_parquet(os.path.join(out_dir, fname)).columns)
        rep.check(f"{fname} carries only allowlisted columns", cols <= allowed,
                  f"unexpected {sorted(cols - allowed)}")
    for fname, rows in ((SUPPORT_FILE, support), (COEF_FILE, coefs), (RECON_FILE, recon)):
        bad = {c for r in rows for c in r if "rank" in c.lower()}
        rep.check(f"{fname} emits no rank column", not bad, f"found {sorted(bad)}")

    # -- 3. the key-name firewall, over the WHOLE document, at any depth -------- #
    hits = forbidden_keys(doc) + forbidden_keys(prov)
    rep.check("no p / q / FDR / significance / combined / balanced / weighted / score key",
              not hits, f"forbidden key(s): {hits[:8]}")

    method = doc.get("method") or {}
    for key, expected in NEGATIVE_DECLARATIONS.items():
        rep.check(f"the artifact declares {key} = {expected}",
                  method.get(key) is expected,
                  f"got {method.get(key)!r}")

    # -- 4. this lane is SECONDARY and says so in its own bytes ----------------- #
    rep.check("lane_role is secondary_non_gating",
              doc.get("lane_role") == SPEC_LANE_ROLE and
              method.get("lane_role") == SPEC_LANE_ROLE)
    rep.check("the artifact declares no rank column",
              method.get("rank_column_emitted") is False)
    rep.check("the artifact declares no temporal artifact",
              method.get("temporal_artifact_emitted") is False)
    rep.check("the artifact binds base_portable", method.get("base_portable") is True)
    rep.check("the artifact binds the Direct scorer view",
              bool(method.get("scorer_view_sha256")))
    rep.check("the artifact binds the Direct arm rows it supports",
              bool(method.get("arm_rows_sha256")))
    rep.check("the Direct bundle it supports was ADMITTED by its own verifier",
              method.get("direct_verifier_verdict") == ADMIT)
    rep.check("the artifact does NOT carry a production_eligible gate",
              "production_eligible" not in json.dumps(doc),
              "the historical 0/33 LOMO result is descriptive evidence about single-marker "
              "dependence, not a production gate; a field pinned to it would read as one")

    # -- 5. every arm key is a DIRECT arm key. No ordered condition pair -------- #
    keys = sorted({str(r["arm_key"]) for r in support}
                  | {str(r["arm_key"]) for r in coefs})
    parsed: dict[str, dict[str, str]] = {}
    bad_keys: list[str] = []
    for k in keys:
        try:
            parsed[k] = parse_arm_key(k)
        except ValueError as e:
            bad_keys.append(str(e))
    rep.check("every arm key is a canonical direct arm key", not bad_keys,
              f"{bad_keys[:4]}")
    rep.check("no arm key is keyed on an ordered condition pair",
              all(len(k.split("|")) == 4 for k in keys),
              "a 5-part key would be a temporal arm, and this lane may not claim one")

    # the frozen role x pole mapping, RE-DERIVED — never read from the artifact
    derived = (prov.get("derived_from") or {})
    if derived.get("role") and derived.get("pole"):
        want = DESIRED_CHANGE_BY_ROLE_AND_POLE.get(
            (str(derived["role"]), str(derived["pole"])))
        changes = {p["desired_change"] for p in parsed.values()}
        rep.check("desired_change follows the frozen role x pole mapping",
                  want in changes,
                  f"role={derived['role']!r} pole={derived['pole']!r} implies {want!r}, "
                  f"but the artifact carries {sorted(changes)}")

    # -- 6. the two arms are ONE measurement and a sign ------------------------- #
    rep.check(*_check_sign_transform(coefs, parsed))

    # -- 7. the support status, re-derived from the emitted frequencies --------- #
    rep.check(*_check_support_status(support))

    # -- 8. determinism and the model pin -------------------------------------- #
    m = method.get("model") or {}
    rep.check("the wrapper seed is 42", m.get("random_state") == SPEC_RANDOM_STATE,
              f"got {m.get('random_state')!r}")
    rep.check("positive=False, so opposed contributors are kept, not zeroed",
              m.get("positive") is False)
    grid = m.get("l1_ratio_grid") or []
    rep.check("every l1 ratio lies in [0, 1]",
              bool(grid) and all(SPEC_L1_MIN <= float(v) <= SPEC_L1_MAX for v in grid),
              f"got {grid!r}")

    up = doc.get("upstream_software") or {}
    for field in ("upstream_repository", "upstream_commit", "upstream_version",
                  "upstream_license", "upstream_tree_sha256"):
        rep.check(f"the upstream pin binds {field}", bool(up.get(field)))
    rep.check("the upstream identity was resolved at runtime, not echoed",
              up.get("resolved_at_runtime") is True)

    # -- 9. no machine-local paths --------------------------------------------- #
    paths = machine_paths(doc) + machine_paths(prov)
    rep.check("no machine-local path is emitted", not paths, f"at {paths[:5]}")

    # -- 10. counting: a zero coefficient does not disappear from coverage ------ #
    bad_den = [r["target_id"] for r in support
               if int(r["n_selected_runs"]) > int(r["n_runs"])]
    rep.check("no target is selected in more runs than it appeared in", not bad_den,
              f"{bad_den[:4]}")
    rep.check("every support row ships its denominator",
              all(int(r["n_runs"]) > 0 for r in support))

    return rep.document()


def _check_sign_transform(coefs: list[dict[str, Any]],
                          parsed: dict[str, dict[str, str]]) -> tuple[str, bool, str]:
    """The two arms of a program must be EXACT negations of each other.

    They are one measurement and a sign. If they are not exact negations, the second arm was
    RE-FITTED — and two arms that were fitted separately can disagree, by a hair, about a
    magnitude they share. A reader comparing them would be reading a difference that nothing
    measured.
    """
    index: dict[tuple, dict[str, float]] = {}
    for r in coefs:
        p = parsed.get(str(r["arm_key"]))
        if not p:
            continue
        slot = (p["program_id"], p["condition"], str(r["target_id"]),
                str(r["effect_layer"]), str(r["model_config"]), str(r["donor_scope"]))
        index.setdefault(slot, {})[p["desired_change"]] = float(r["coefficient"])

    bad = []
    for slot, arms in index.items():
        if INCREASE in arms and DECREASE in arms:
            if abs(arms[INCREASE] + arms[DECREASE]) > SPEC_SIGN_TRANSFORM_TOL:
                bad.append((slot[0], slot[2], arms[INCREASE], arms[DECREASE]))
    return ("the two arms are exact sign transforms of one base effect", not bad,
            f"{len(bad)} slot(s) where increase != -decrease, e.g. {bad[:3]}")


def _check_support_status(support: list[dict[str, Any]]) -> tuple[str, bool, str]:
    """Re-derive every status, and check the opposed flag never launders into support."""
    bad, laundered = [], []
    for r in support:
        want = support_status(float(r["selection_frequency"]),
                              float(r["positive_frequency"]),
                              float(r["negative_frequency"]))
        got = str(r["support_status"])
        if got not in SPEC_STATUS_VALUES or got != want:
            bad.append((r["arm_key"], r["target_id"], got, want))
        if bool(r["opposed"]) != (got == OPPOSED):
            laundered.append((r["arm_key"], r["target_id"], got, r["opposed"]))
    ok = not bad and not laundered
    return ("every support status re-derives, and opposed is never converted to support",
            ok, f"mis-derived {bad[:3]}; opposed-flag disagreement {laundered[:3]}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Independent verifier for the P2S arm artifact")
    ap.add_argument("--out-dir", required=True, help="the P2S run directory to verify")
    ap.add_argument("--report", default=None, help="write the report here (JSON)")
    args = ap.parse_args(argv)

    doc = verify(args.out_dir)
    if args.report:
        with open(args.report, "w") as fh:
            json.dump(doc, fh, indent=2, sort_keys=True)
            fh.write("\n")
    print(json.dumps(doc, indent=2, sort_keys=True))
    return 0 if doc["verdict"] == ADMIT else 1


if __name__ == "__main__":
    raise SystemExit(main())
