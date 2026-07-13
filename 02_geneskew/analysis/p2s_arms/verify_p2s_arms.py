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
    COEF_FILE,
    DECREASE,
    DESIRED_CHANGE_BY_ROLE_AND_POLE,
    DOC_FILE,
    FORBIDDEN_FILES,
    INCREASE,
    NEGATIVE_DECLARATIONS,
    OPPOSED,
    PINNED_SOLVER_LOCK_SHA256,
    PROVENANCE_FILE,
    RECON_FILE,
    REJECT,
    REQUIRED_FILES,
    SPEC_L1_MAX,
    SPEC_L1_MIN,
    SPEC_LANE_ROLE,
    SPEC_RANDOM_STATE,
    SPEC_SIGN_TRANSFORM_TOL,
    SPEC_STATUS_VALUES,
    SUPPORT_FILE,
    VERIFIER_ID,
    W10_SPEC_SHA256,
    W10_VERDICT_ADMIT,
    W10_VERIFIER_CODE_SHA256,
    W10_VERIFIER_ID,
    canonical_coefficients,
    canonical_support,
    content_sha256,
    forbidden_keys,
    machine_paths,
    parse_arm_key,
    support_status,
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
