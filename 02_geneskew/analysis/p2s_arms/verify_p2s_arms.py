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
import json
import os
import sys
from typing import Any

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from verify_p2s_rules import (  # noqa: E402  (the verifier-side reimplementation)
    ADMIT,
    ALLOWLISTS,
    ARTIFACT_MAP_FILES,
    COEF_FILE,
    DECREASE,
    DESIRED_CHANGE_BY_ROLE_AND_POLE,
    DOC_FILE,
    FORBIDDEN_FILES,
    INCREASE,
    NEGATIVE_DECLARATIONS,
    PINNED_SOLVER_LOCK_SHA256,
    PROVENANCE_FILE,
    RECON_FILE,
    REJECT,
    REQUIRED_FILES,
    SPEC_L1_MAX,
    SPEC_L1_MIN,
    SPEC_LANE_ROLE,
    SPEC_PRIMARY_LAYER,
    SPEC_PRIMARY_MODEL_CONFIG,
    SPEC_PRIMARY_SCOPE,
    SPEC_QUANTITY,
    SPEC_RANDOM_STATE,
    SPEC_SIGN_TRANSFORM_TOL,
    SPEC_SIGN_VALUES,
    SUPPORT_FILE,
    VERIFIER_ID,
    W10_SPEC_SHA256,
    W10_VERDICT_ADMIT,
    W10_VERIFIER_CODE_SHA256,
    W10_VERIFIER_ID,
    canonical_coefficients,
    canonical_reconstruction,
    canonical_support,
    content_sha256,
    derive_support_from_coefficients,
    file_sha256,
    forbidden_keys,
    machine_paths,
    parse_arm_key,
)

PASS, FAIL = "pass", "fail"

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
    rep.check("reconstruction_rows_sha256 is the hash of the shipped reconstruction rows",
              doc.get("reconstruction_rows_sha256")
              == content_sha256(canonical_reconstruction(recon)),
              "every scientific table is hashed into the doc")

    # -- 1c. RE-DERIVE the run id from provenance.run_binding, and match the directory ------ #
    rb = prov.get("run_binding") or {}
    rederived_id = content_sha256(rb)[:16]
    claimed_id = prov.get("p2s_run_id")
    dir_id = os.path.basename(os.path.normpath(out_dir))
    rep.check("the p2s_run_id RE-DERIVES from provenance.run_binding and names the directory",
              rederived_id == claimed_id == dir_id,
              f"rederived {rederived_id}, claimed {claimed_id}, dir {dir_id}")
    # the run binding must fold in every scientific table hash
    for key in ("support_rows_sha256", "coefficient_rows_sha256",
                "reconstruction_rows_sha256"):
        rep.check(f"run_binding folds in {key}", rb.get(key) == doc.get(key))

    # -- 1d. RAW-REHASH every emitted file against the provenance artifact map -------------- #
    # This catches a byte changed in ANY file — including a support column that is not in a
    # canonical projection (e.g. primary_abs_coefficient), or a top-level field edited in
    # p2s_support.json — WITHOUT the change having to touch a canonical hash. The map itself
    # is in the provenance, so a change that does not also reseal the map is refused here.
    amap = prov.get("artifact_sha256") or {}
    rep.check("the provenance carries a raw artifact_sha256 map for every emitted file",
              set(amap) == set(ARTIFACT_MAP_FILES),
              f"missing {sorted(set(ARTIFACT_MAP_FILES) - set(amap))}, "
              f"extra {sorted(set(amap) - set(ARTIFACT_MAP_FILES))}")
    rehash_bad = []
    for name in ARTIFACT_MAP_FILES:
        path = os.path.join(out_dir, name)
        got = file_sha256(path) if os.path.exists(path) else None
        if got != amap.get(name):
            rehash_bad.append((name, str(amap.get(name))[:12], str(got)[:12]))
    rep.check("every emitted file RAW-REHASHES to the provenance artifact map", not rehash_bad,
              f"{rehash_bad[:4]}; a value edited without resealing the map is refused here")

    # -- 1e. BIND the emitted key universe to the ROW keys — no vacuous top-level field ----- #
    rep.check(*_check_key_universe(doc, rb, support, coefs, recon))

    # -- 2. exact column allowlists: a rank/gate column is rejected by ABSENCE -- #
    for fname, allowed in ALLOWLISTS.items():
        cols = set(pd.read_parquet(os.path.join(out_dir, fname)).columns)
        rep.check(f"{fname} carries EXACTLY the allowlisted columns", cols == allowed,
                  f"unexpected {sorted(cols - allowed)}; missing {sorted(allowed - cols)}")
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
    # -- THE W10 ADMISSION CHAIN, re-derived ----------------------------------- #
    rep.check("the Direct bundle was ADMITTED by W10, the INDEPENDENT verifier",
              method.get("w10_verdict") == W10_VERDICT_ADMIT,
              f"got {method.get('w10_verdict')!r}; W10 writes {W10_VERDICT_ADMIT!r} and a "
              "transliterated verdict is a verdict nobody checked")
    rep.check("the admitting verifier is the pinned W10 arm-bundle verifier",
              method.get("w10_verifier_id") == W10_VERIFIER_ID,
              f"got {method.get('w10_verifier_id')!r}")
    rep.check("W10's report was written against the pinned spec",
              method.get("w10_spec_sha256") == W10_SPEC_SHA256)
    rep.check("the report names the PINNED W10 verifier CODE that produced it",
              method.get("w10_verifier_code_sha256") == W10_VERIFIER_CODE_SHA256,
              f"got {str(method.get('w10_verifier_code_sha256'))[:16]}...; an honestly "
              "resealed report agrees with itself and still names no checker")
    rep.check("the verifier code was PINNED, not merely recorded",
              method.get("w10_verifier_code_pinned") is True)
    rep.check("W10's report hash was RE-DERIVED, not quoted",
              method.get("w10_report_sha256_rederived") is True
              and bool(method.get("w10_report_sha256")))
    rep.check("the run binds the arms it supports to a REAL, admitted bundle",
              method.get("bundle_is_real_and_admitted") is True
              and bool(method.get("arm_bundle_run_id")))
    rep.check("every file of the Direct bundle was re-hashed and bound",
              bool(method.get("direct_bundle_artifact_sha256")))

    # -- THE SOLVER LOCK, against THIS verifier's own literal -------------------- #
    rep.check("the run bound the PINNED Stage-2 solver lock",
              method.get("solver_lock_sha256") == PINNED_SOLVER_LOCK_SHA256,
              f"got {str(method.get('solver_lock_sha256'))[:16]}...; a run whose environment "
              "is unbound can be re-attributed to one it was not computed in")
    rep.check("the arms and the support were computed under the SAME lock",
              method.get("solver_lock_pinned_sha256") == PINNED_SOLVER_LOCK_SHA256)
    rep.check("the run declares a release lane, not a fixture",
              method.get("lane") in ("production", "research_only", "synthetic"))
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

    # -- 5b. EXACTLY 7 rows + 7 unique OFAT slots per (arm, target); recon ships the same 7 - #
    rep.check(*_check_exact_grid(coefs, recon))

    # -- 6. the two arms are ONE measurement and a sign ------------------------- #
    rep.check(*_check_sign_transform(coefs, parsed))

    # -- 7. CONTINUOUS support: primary estimand + no discrete verdict ---------- #
    rep.check(*_check_continuous_support(support, method))

    # -- 7b. SCIENCE REPLAY: re-derive every support row FROM the coefficients --- #
    rep.check(*_check_support_replay(support, coefs))

    # -- 7c. every coefficient is the p2s base quantity, and columns match the key #
    rep.check("every coefficient row is the p2s base quantity",
              all(str(r.get("quantity")) == SPEC_QUANTITY for r in coefs),
              f"expected quantity={SPEC_QUANTITY!r}")
    rep.check("coef_fit_variation is finite and non-negative",
              all(r.get("coef_fit_variation") is not None
                  and float(r["coef_fit_variation"]) >= 0
                  and float(r["coef_fit_variation"]) == float(r["coef_fit_variation"])
                  for r in coefs))
    rep.check(*_check_columns_match_key(support, coefs, recon))

    # -- 8. determinism and the model pin -------------------------------------- #
    m = method.get("model") or {}
    rep.check("the wrapper seed is 42", m.get("random_state") == SPEC_RANDOM_STATE,
              f"got {m.get('random_state')!r}")
    # the ACTUAL RECORDED run seed — not only the method's declared wrapper seed. A run that
    # was fitted under a different seed but declared 42 in its method block is caught here.
    rep.check("the RUN recorded the pinned seed in its binding",
              rb.get("seed") == SPEC_RANDOM_STATE,
              f"got run_binding.seed={rb.get('seed')!r}; a release run is pinned to seed "
              f"{SPEC_RANDOM_STATE}")
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

    # -- 10. counting: each FAMILY ships its own denominator; no pooled aggregate -- #
    bad_den = [r["target_id"] for r in support
               if int(r["n_log_fc"]) < 0 or int(r["n_pca_off"]) < 0 or int(r["n_lodo"]) < 0]
    rep.check("every sensitivity family ships a non-negative denominator", not bad_den,
              f"{bad_den[:4]}")
    rep.check("no pooled sensitivity aggregate is emitted",
              all("n_sensitivity_fits" not in r for r in support),
              "pooling LODO (4x) with log_fc and pca_off weights donor deletion 4-fold")
    rep.check("every support row ships its run denominator",
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


def _sibling_of(arm_key: str) -> str:
    """The canonical sibling arm — the SAME program and condition, the opposite sign."""
    p = parse_arm_key(arm_key)
    other = DECREASE if p["desired_change"] == INCREASE else INCREASE
    return f"direct|{p['program_id']}|{other}|{p['condition']}"


def _check_key_universe(doc, rb, support, coefs, recon) -> tuple[str, bool, str]:
    """Every top-level program/condition/arm field must RE-DERIVE from the ROW keys.

    A top-level field that NO row constrains can be edited to anything and still self-hash —
    which is how ``p2s_support.json.condition`` could be forged to FORGED_CONDITION and pass.
    So the row keys are the authority: EXACTLY the requested arm and its canonical sibling, ONE
    program, ONE condition, and a COMPLETE arm pair for every (target, fit slot). Missing all
    sibling rows, or a third program/condition, is refused here rather than passing vacuously.
    """
    row_keys = sorted({str(r["arm_key"]) for r in (support + coefs + recon)})
    if not row_keys:
        return ("top-level arm/program/condition fields re-derive from the row keys",
                False, "no row carries an arm_key — nothing binds the top-level fields")
    try:
        parsed = {k: parse_arm_key(k) for k in row_keys}
    except ValueError as e:
        return ("top-level arm/program/condition fields re-derive from the row keys",
                False, f"a row arm_key does not parse: {e}")

    programs = {p["program_id"] for p in parsed.values()}
    conditions = {p["condition"] for p in parsed.values()}
    bad = []
    if len(programs) != 1:
        bad.append(("programs", sorted(programs)))
    if len(conditions) != 1:
        bad.append(("conditions", sorted(conditions)))

    requested = doc.get("arm_key")
    sibling = _sibling_of(requested) if requested else None
    want_keys = sorted({str(requested), sibling}) if requested else []
    if set(row_keys) != set(want_keys):
        bad.append(("arm_keys", f"rows carry {row_keys}, want {want_keys}"))

    prog = next(iter(programs)) if len(programs) == 1 else None
    cond = next(iter(conditions)) if len(conditions) == 1 else None
    for name, got, exp in (
            ("program_id", doc.get("program_id"), prog),
            ("condition", doc.get("condition"), cond),
            ("sibling_arm_key", doc.get("sibling_arm_key"), sibling),
            ("n_arms", doc.get("n_arms"), len(want_keys)),
            ("arm_keys", sorted(str(k) for k in (doc.get("arm_keys") or [])), want_keys),
            ("run_binding.arm_key", rb.get("arm_key"), requested)):
        if got != exp:
            bad.append((name, f"doc {got!r} != derived {exp!r}"))

    # COMPLETE arm pairs: every (target, fit slot) present on one arm must appear on BOTH.
    by_cell: dict[tuple, set] = {}
    for r in coefs:
        p = parsed.get(str(r["arm_key"]))
        if not p:
            continue
        cell = (str(r["target_id"]), str(r["effect_layer"]), str(r["model_config"]),
                str(r["donor_scope"]))
        by_cell.setdefault(cell, set()).add(p["desired_change"])
    incomplete = [c for c, ch in by_cell.items() if ch != {INCREASE, DECREASE}]
    if incomplete:
        bad.append(("incomplete_arm_pairs",
                    f"{len(incomplete)} (target, fit slot) cell(s) lack a sign arm, e.g. "
                    f"{incomplete[:2]}"))

    return ("top-level arm/program/condition fields re-derive from the row keys",
            not bad, f"{bad[:4]}")


EXPECTED_ALL_DONOR = frozenset({
    ("all_donor", "zscore", "pca_on_60"),
    ("all_donor", "log_fc", "pca_on_60"),
    ("all_donor", "zscore", "pca_off")})
N_EXPECTED_FITS = 7            # 3 all_donor OFAT + 4 distinct LODO donors
N_EXPECTED_LODO = 4
LODO_PRIMARY = ("zscore", "pca_on_60")     # a LODO fit changes ONLY the donor set


def _slots_ok(slots: set) -> tuple[bool, str]:
    """The unique slot SET is exactly the 3 all_donor OFAT + 4 distinct LODO-donor fits."""
    all_donor = {s for s in slots if s[0] == "all_donor"}
    lodo = {s for s in slots if s[0].startswith("lodo_")}
    other = slots - all_donor - lodo
    if other:
        return False, f"non-OFAT slot(s) {sorted(other)}"
    if all_donor != EXPECTED_ALL_DONOR:
        return False, f"all_donor slots {sorted(all_donor)}"
    off = [s for s in lodo if (s[1], s[2]) != LODO_PRIMARY]
    if off:
        return False, f"a LODO slot changed more than the donor: {sorted(off)}"
    donors = {s[0] for s in lodo}
    if len(lodo) != N_EXPECTED_LODO or len(donors) != N_EXPECTED_LODO:
        return False, f"{len(lodo)} LODO slot(s), {len(donors)} distinct donor(s)"
    if len(slots) != N_EXPECTED_FITS:
        return False, f"{len(slots)} unique slots"
    return True, ""


def _check_exact_grid(coefs, recon) -> tuple[str, bool, str]:
    """Per (arm, target): EXACTLY 7 coefficient ROWS and 7 UNIQUE slots — 3 all_donor OFAT +
    4 distinct LODO donors — and the reconstruction ships those SAME 7 fit slots per arm.

    A set-only check is not enough: it passes a DUPLICATED row (8 rows, 7 unique slots) and an
    EMPTY parquet (no keys, so nothing disagrees) vacuously. So the ROW COUNT is compared to 7
    and the key set is required non-empty, on both the coefficient and the reconstruction table.
    """
    rows_by_key: dict[tuple, list] = {}
    for r in coefs:
        k = (str(r["arm_key"]), str(r["target_id"]))
        rows_by_key.setdefault(k, []).append(
            (str(r["donor_scope"]), str(r["effect_layer"]), str(r["model_config"])))
    if not rows_by_key:
        return ("exactly 7 OFAT slots per (arm, target); reconstruction ships the same 7",
                False, "the coefficient parquet is EMPTY — a set-only check would pass it "
                       "vacuously, so the empty table is refused")

    bad = []
    coef_slots_by_arm: dict[str, set] = {}
    for k, slot_list in rows_by_key.items():
        coef_slots_by_arm.setdefault(k[0], set()).update(slot_list)
        if len(slot_list) != N_EXPECTED_FITS:
            bad.append((k, f"{len(slot_list)} coefficient ROWS (want {N_EXPECTED_FITS}); "
                           f"{len(set(slot_list))} unique"))
            continue
        ok, why = _slots_ok(set(slot_list))
        if not ok:
            bad.append((k, why))

    # the reconstruction must carry those SAME 7 fit slots per arm — no more, no fewer, once each
    recon_by_arm: dict[str, list] = {}
    for r in recon:
        recon_by_arm.setdefault(str(r["arm_key"]), []).append(
            (str(r["donor_scope"]), str(r["effect_layer"]), str(r["model_config"])))
    for arm, want in coef_slots_by_arm.items():
        got = recon_by_arm.get(arm, [])
        if len(got) != N_EXPECTED_FITS or set(got) != want:
            bad.append((arm, f"reconstruction slots {sorted(set(got))} (n={len(got)}) != "
                             f"coefficient slots {sorted(want)}"))

    return ("exactly 7 OFAT slots per (arm, target); reconstruction ships the same 7",
            not bad, f"{bad[:3]}")


def _check_support_replay(support, coefs) -> tuple[str, bool, str]:
    """RE-DERIVE every support row from the coefficient parquet and compare, field by field.

    Arbitrary support values that merely self-hash cannot pass: they must be what the
    coefficients actually imply — primary from zscore/pca_on_60/all_donor, family-specific
    concordance with exact 1/1/4 denominators, n_runs = 7.
    """
    want = derive_support_from_coefficients(coefs)
    bad = []
    for r in support:
        k = (str(r["arm_key"]), str(r["target_id"]))
        w = want.get(k)
        if w is None:
            bad.append((k, "no coefficients for this support row"))
            continue
        for field in ("n_runs", "primary_coefficient", "primary_sign", "opposed",
                      "primary_available", "sens_log_fc_sign_concordance", "n_log_fc",
                      "sens_pca_off_sign_concordance", "n_pca_off",
                      "lodo_sign_concordance", "n_lodo"):
            got, exp = r.get(field), w[field]
            # parquet round-trips a null float to NaN; normalise before comparing
            if isinstance(got, float) and got != got:
                got = None
            if isinstance(exp, float) and got is not None:
                if abs(float(got) - exp) > 1e-9:
                    bad.append((k, field, got, exp))
            elif not isinstance(exp, float) and got != exp:
                bad.append((k, field, got, exp))
    return ("every support row RE-DERIVES from the coefficient parquet", not bad,
            f"{bad[:3]}")


def _check_columns_match_key(support, coefs, recon) -> tuple[str, bool, str]:
    """program_id / desired_change / condition must equal what the arm_key parses to."""
    bad = []
    for name, rows in (("support", support), ("coefs", coefs), ("recon", recon)):
        for r in rows:
            try:
                p = parse_arm_key(str(r["arm_key"]))
            except ValueError as e:
                bad.append((name, str(e)))
                continue
            if (str(r.get("program_id")) != p["program_id"]
                    or str(r.get("desired_change")) != p["desired_change"]
                    or str(r.get("condition")) != p["condition"]):
                bad.append((name, r["arm_key"], "columns disagree with parsed key"))
    return ("program_id/desired_change/condition match the parsed arm_key", not bad,
            f"{bad[:3]}")


def _check_continuous_support(support: list[dict[str, Any]],
                              method: dict[str, Any]) -> tuple[str, bool, str]:
    """Support is CONTINUOUS: a primary sign, sensitivity denominators, and NO discrete verdict.

    Re-derives the OPPOSED fact from the primary sign (not from a selection frequency), and
    confirms the primary estimand is the single seeded-SVD family — never pooled.
    """
    bad = []
    for r in support:
        sign = str(r["primary_sign"])
        if sign not in SPEC_SIGN_VALUES:
            bad.append((r["arm_key"], r["target_id"], "sign", sign))
        # opposed is EXACTLY the primary-sign-is-opposed fact, never a laundered verdict
        if bool(r["opposed"]) != (sign == "opposed"):
            bad.append((r["arm_key"], r["target_id"], "opposed", r["opposed"]))
        # a concordance without its n is not a fraction; each family carries its own n
        for conc, n in (("sens_log_fc_sign_concordance", "n_log_fc"),
                        ("sens_pca_off_sign_concordance", "n_pca_off"),
                        ("lodo_sign_concordance", "n_lodo")):
            if r.get(conc) is not None and int(r[n]) == 0:
                bad.append((r["arm_key"], r["target_id"], f"{conc} without {n}", None))

    sup = method.get("support") or {}
    prim = sup.get("primary_estimand") or {}
    primary_ok = (prim.get("donor_scope") == SPEC_PRIMARY_SCOPE
                  and prim.get("effect_layer") == SPEC_PRIMARY_LAYER
                  and prim.get("model_config") == SPEC_PRIMARY_MODEL_CONFIG
                  and sup.get("families_are_pooled_into_primary") is False
                  and sup.get("support_is_discrete_flag") is False)
    ok = not bad and primary_ok
    return ("support is continuous: primary sign + sensitivity denominators, no pooled "
            "families, no discrete verdict",
            ok, f"row issues {bad[:3]}; primary_estimand ok={primary_ok}")


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
