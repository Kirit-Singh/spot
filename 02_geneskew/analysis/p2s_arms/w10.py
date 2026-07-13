"""THE W10 ADMISSION GATE: P2S runs only from a real Direct bundle W10 has ADMITTED.

W10 is the INDEPENDENT on-disk Direct verifier. It is not the producer, and that is the whole
point: a generator that signs its own homework is the same process asserting twice.

WHAT THIS MODULE REFUSES, AND WHY EACH ONE IS A REAL ATTACK
----------------------------------------------------------
  * **a SELF-ADMITTED bundle.** The Direct producer writes `verdict:
    pending_independent_verification` and `verifier_id: null` into its own
    `verification.json`. That is a SLOT, not a verdict — W10 fills it from outside. Hand
    that file in as the report and a run would proceed on a bundle that admitted itself;
  * **a REPORT FROM ANOTHER CHECKER.** `verifier_id` and `spec_sha256` are pinned. A
    weakened checker that passed itself off as W10 would admit whatever it liked;
  * **a TAMPERED report.** `report_sha256` is RE-DERIVED here from the report's own body,
    with this lane's own hash function — never read and trusted. A verdict that could be
    edited to `ADMIT` after the fact is a claim, not a result;
  * **a report about ANOTHER BUNDLE.** `bound_artifact` names what W10 actually looked at.
    A real ADMIT report for bundle X, handed in beside bundle Y, would otherwise launder X's
    admission onto Y. Every bound field is matched against the bundle ON DISK;
  * **a STALE or SWAPPED bundle.** Every one of the ten shipped files is RE-HASHED and
    matched against the report's `artifact_sha256` map. A bundle with an edited parquet keeps
    its directory name and its `arm_bundle.json`;
  * **a DIFFERENT ENVIRONMENT.** The report carries `solver_lock_sha256`. Support computed
    under one solver lock, attached to arms computed under another, is a comparison nobody
    made — so the locks must be the same lock, and it must be the PINNED one;
  * **a SYNTHETIC bundle.** `lane` must be a release lane. Synthetic arms may never carry
    production support.

Nothing here is imported from the Direct producer or from W10. The hash is re-implemented, so
this gate can DISAGREE with both.
"""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Optional

from direct import target_identity as ti

from . import config
from . import disposition as D

REPORT_SELF_HASH_FIELD = "report_sha256"
BUNDLE_FILE = "arm_bundle.json"


def canonical_json(obj: Any) -> str:
    """The ONE serialisation the report hash is taken over. Re-implemented, not imported."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False)


def content_sha256(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def file_sha256(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def load_report(path: Optional[str]) -> dict[str, Any]:
    """Read the W10 report off disk. Never a caller's dict."""
    if not path:
        raise D.RefusalError(
            D.REFUSE_W10_REPORT_MISSING,
            "no --w10-report was supplied. P2S may run only from a Direct arm bundle that "
            "the INDEPENDENT verifier has ADMITTED; without the report there is nothing "
            "saying this bundle was ever checked by anyone but the process that wrote it")
    if not os.path.exists(path):
        raise D.RefusalError(
            D.REFUSE_W10_REPORT_MISSING,
            f"the --w10-report at {os.path.basename(path)!r} does not exist")
    try:
        with open(path) as fh:
            return json.load(fh)
    except (ValueError, OSError) as e:
        raise D.RefusalError(
            D.REFUSE_W10_REPORT_UNREADABLE,
            f"the --w10-report is not readable JSON ({e})") from e


def check_identity(report: dict[str, Any]) -> None:
    """WHICH checker ran, and against WHICH spec. Both pinned; neither inferred."""
    verifier_id = report.get("verifier_id")

    # THE SELF-ADMISSION REFUSAL. Checked FIRST and by name, because the file that trips it
    # is the one sitting in the bundle directory called `verification.json` — the easiest
    # wrong file in the world to pass to --w10-report.
    if verifier_id is None or report.get("verdict") == config.W10_VERDICT_PENDING:
        raise D.RefusalError(
            D.REFUSE_W10_SELF_ADMITTED,
            "this is the bundle's OWN verification.json — the producer's empty slot "
            f"(verifier_id={verifier_id!r}, verdict={report.get('verdict')!r}), not a "
            "verdict. The Direct producer writes it precisely so it cannot admit itself; "
            "W10 fills it from outside. Pass W10's report, not the bundle's placeholder")

    if verifier_id != config.W10_VERIFIER_ID:
        raise D.RefusalError(
            D.REFUSE_W10_WRONG_VERIFIER,
            f"the report was written by {verifier_id!r}, not the pinned independent Direct "
            f"verifier {config.W10_VERIFIER_ID!r}. A checker that is not W10 admitting a "
            "bundle as if it were W10 is the one thing an admission chain cannot survive")

    if report.get("spec_sha256") != config.W10_SPEC_SHA256:
        raise D.RefusalError(
            D.REFUSE_W10_SPEC_DRIFT,
            f"the report was written against spec {str(report.get('spec_sha256'))[:16]}..., "
            f"not the pinned {config.W10_SPEC_SHA256[:16]}.... The gates it ran are not the "
            "gates this lane believes it ran")

    if report.get("independent_of_generator") is not True:
        raise D.RefusalError(
            D.REFUSE_W10_NOT_INDEPENDENT,
            "the report does not declare independent_of_generator: true. generator != "
            "verifier is the property being relied on here; a report that will not assert "
            "it is not an independent admission")

    # WHICH CODE ACTUALLY RAN. Without this, an HONESTLY RESEALED report passes: take a real
    # ADMIT, blank `verifier_code_sha256` to 00...00, re-hash the body so `report_sha256`
    # agrees with it again, and every other gate here is satisfied. The report is then
    # perfectly self-consistent and says NOTHING about which checker produced the verdict —
    # a weakened checker, or no checker at all, is indistinguishable from W10.
    #
    # Self-consistency is not authenticity. Only a pin refuses this.
    code = report.get("verifier_code_sha256")
    if not code:
        raise D.RefusalError(
            D.REFUSE_W10_WRONG_CODE,
            "the report does not name the code that produced it (verifier_code_sha256 is "
            f"{code!r}). A checker that will not name its own code is unfalsifiable, and a "
            "verdict attributed to no code is a verdict nobody can re-run")

    if code != config.W10_VERIFIER_CODE_SHA256:
        raise D.RefusalError(
            D.REFUSE_W10_WRONG_CODE,
            f"the report was produced by verifier code {str(code)[:16]}..., not the pinned "
            f"{config.W10_VERIFIER_CODE_SHA256[:16]}... (W10's {config.W10_VERIFIER_N_MODULES} "
            f"modules at commit {config.W10_VERIFIER_COMMIT_HINT}). The verdict may be "
            "honestly sealed and the report internally consistent — a resealed report agrees "
            "with itself — but it was not produced by the checker this lane admits, and a "
            "weakened checker admits whatever it likes")


def check_verdict(report: dict[str, Any]) -> None:
    """ADMIT, or nothing. A REFUSE is not a weaker admit."""
    verdict = report.get("verdict")
    if verdict != config.W10_VERDICT_ADMIT:
        failed = report.get("failed_gates") or []
        raise D.RefusalError(
            D.REFUSE_W10_NOT_ADMITTED,
            f"W10 returned {verdict!r}, not {config.W10_VERDICT_ADMIT!r}"
            + (f" (failed gates: {failed[:4]})" if failed else "")
            + ". Support for a bundle its own independent verifier refused would launder "
              "that refusal into evidence")


def check_report_hash(report: dict[str, Any]) -> str:
    """RE-DERIVE report_sha256 from the report's own body. Never read and trust it.

    W10's hash is `sha256(canonical_json(body))` over the body WITHOUT its self-hash field —
    a document cannot attest to itself. Re-deriving it here, with this lane's own function,
    is what makes "W10 said ADMIT" a checkable statement rather than a quoted one.
    """
    claimed = report.get(REPORT_SELF_HASH_FIELD)
    body = {k: v for k, v in report.items() if k != REPORT_SELF_HASH_FIELD}
    derived = content_sha256(body)
    if claimed != derived:
        raise D.RefusalError(
            D.REFUSE_W10_REPORT_TAMPERED,
            f"the report claims {str(claimed)[:16]}... but its content hashes to "
            f"{derived[:16]}.... A verdict that can be edited after it was cited is a claim, "
            "not a result — and the edit that matters is REFUSE -> ADMIT")
    return derived


def check_not_self_admitted(bundle_dir: str, report: dict[str, Any]) -> None:
    """The BUNDLE'S OWN verification.json must still be the producer's EMPTY SLOT.

    Checked on the bundle, not only on the report. The producer ships
    ``verdict: pending_independent_verification``, ``admitted: false``, ``self_admitted:
    false``, ``verifier_id: null`` — a slot for an outsider to fill. A bundle that arrived
    with that slot already filled in by whatever wrote it is a generator signing its own
    homework, and the W10 report beside it proves nothing about it.

    And the admitting verifier must not BE the producer: ``verifier_id`` may never equal the
    bundle's own ``produced_by``.
    """
    path = os.path.join(bundle_dir, "verification.json")
    if not os.path.exists(path):
        raise D.RefusalError(
            D.REFUSE_BUNDLE_INCOMPLETE,
            "the Direct bundle ships no verification.json, so there is no slot saying it was "
            "left for an independent verifier to fill")
    try:
        with open(path) as fh:
            v = json.load(fh)
    except (ValueError, OSError) as e:
        raise D.RefusalError(
            D.REFUSE_BUNDLE_INCOMPLETE,
            f"the bundle's verification.json is not readable JSON ({e})") from e

    if v.get("self_admitted") is True or v.get("admitted") is True:
        raise D.RefusalError(
            D.REFUSE_W10_SELF_ADMITTED,
            f"the bundle's own verification.json declares self_admitted="
            f"{v.get('self_admitted')!r} admitted={v.get('admitted')!r}. The producer ships "
            "it UN-admitted precisely so it cannot admit itself; a bundle that arrived "
            "already admitting itself is the same process asserting twice")

    if v.get("verifier_id") is not None or \
            v.get("verdict") != config.W10_VERDICT_PENDING:
        raise D.RefusalError(
            D.REFUSE_W10_SELF_ADMITTED,
            f"the bundle's verification.json is not the producer's empty slot "
            f"(verifier_id={v.get('verifier_id')!r}, verdict={v.get('verdict')!r}; expected "
            f"null and {config.W10_VERDICT_PENDING!r}). Something filled the slot before the "
            "independent verifier did")

    produced_by = v.get("produced_by")
    if produced_by and report.get("verifier_id") == produced_by:
        raise D.RefusalError(
            D.REFUSE_W10_SELF_ADMITTED,
            f"the admitting verifier_id ({report.get('verifier_id')!r}) IS the bundle's own "
            f"producer ({produced_by!r}). generator != verifier is the entire property being "
            "relied on")


def check_lock(report: dict[str, Any], bundle_dir: str, run_lock_sha256: str) -> None:
    """THREE-WAY. This run's lock, the pin, and the lock the BUNDLE bound must all agree.

    Self-consistency is not authenticity. A substituted lock whose binding was honestly
    re-sealed makes the bundle internally consistent — every hash inside it agrees — and the
    only thing that refuses it is the HARD PIN, checked from outside.
    """
    bound = report.get("bound_artifact") or {}
    arms_lock = bound.get("solver_lock_sha256")

    if arms_lock != config.PINNED_SOLVER_LOCK_SHA256:
        raise D.RefusalError(
            D.REFUSE_LOCK_DISAGREES_WITH_BUNDLE,
            f"the admitted arms were computed under solver lock {str(arms_lock)[:16]}..., "
            f"not the pinned Stage-2 lock {config.PINNED_SOLVER_LOCK_SHA256[:16]}.... A "
            "substituted lock that was honestly re-sealed agrees with itself, and agreeing "
            "with yourself is not the same as being right")

    if run_lock_sha256 != arms_lock:
        raise D.RefusalError(
            D.REFUSE_LOCK_DISAGREES_WITH_BUNDLE,
            f"this run's solver lock ({run_lock_sha256[:16]}...) is not the lock the arms "
            f"were computed under ({str(arms_lock)[:16]}...). Reconstruction support computed "
            "in one environment, attached to arms computed in another, is a comparison "
            "nobody made and nothing in the numbers would say so")

    # ...and the third leg: what the BUNDLE ITSELF bound, read off its own provenance.
    prov_path = os.path.join(bundle_dir, "provenance.json")
    if os.path.exists(prov_path):
        with open(prov_path) as fh:
            prov = json.load(fh)
        bundle_lock = ((prov.get("run_binding") or {}).get("environment_lock") or {}
                       ).get("sha256")
        if bundle_lock is not None and bundle_lock != config.PINNED_SOLVER_LOCK_SHA256:
            raise D.RefusalError(
                D.REFUSE_LOCK_DISAGREES_WITH_BUNDLE,
                f"the bundle's own provenance binds solver lock {str(bundle_lock)[:16]}..., "
                f"not the pin {config.PINNED_SOLVER_LOCK_SHA256[:16]}...")


def check_lane(report: dict[str, Any], run_lane: str) -> str:
    """A synthetic bundle may never carry production support."""
    bound = report.get("bound_artifact") or {}
    lane = bound.get("lane")

    if lane not in config.LANES:
        raise D.RefusalError(
            D.REFUSE_LANE_MISMATCH,
            f"the admitted bundle declares lane {lane!r}, which is not one of "
            f"{list(config.LANES)}")

    if run_lane in config.RELEASE_LANES and lane == config.LANE_SYNTHETIC:
        raise D.RefusalError(
            D.REFUSE_FIXTURE_INPUT,
            f"the bundle was produced in the {config.LANE_SYNTHETIC!r} lane, and this is a "
            f"{run_lane!r} run. Synthetic arms carry synthetic numbers; support attached to "
            "them and served under a release lane would be fixture output wearing a "
            "production artifact's provenance")

    if lane != run_lane:
        raise D.RefusalError(
            D.REFUSE_LANE_MISMATCH,
            f"this is a {run_lane!r} run but the bundle was produced in the {lane!r} lane")
    return lane


def check_bundle_files(report: dict[str, Any], bundle_dir: str) -> dict[str, str]:
    """RE-HASH every shipped file and match it to what W10 admitted.

    This is what catches a STALE or SWAPPED bundle. The directory name is
    `arm_bundle_run_id`, and a bundle whose parquet has been edited keeps that name, keeps
    its `arm_bundle.json`, and keeps W10's real ADMIT report sitting beside it.
    """
    bound = report.get("bound_artifact") or {}
    admitted: dict[str, str] = dict(bound.get("artifact_sha256") or {})
    if not admitted:
        raise D.RefusalError(
            D.REFUSE_W10_REPORT_IS_ABOUT_ANOTHER_BUNDLE,
            "the report carries no artifact_sha256 map, so there is nothing tying it to the "
            "bytes of any particular bundle")

    # THE KEY SET MUST BE EXACTLY WHAT W10 ADMITS. The producer-code-root W10 re-hashes every
    # shipped file — the 10 producer artifacts PLUS the verification.json slot it verifies — so
    # the authoritative admitted inventory is 11 keys. Not a subset that happens to be
    # non-empty: a resealed report that dropped target_identity.json (or added a decoy) would
    # otherwise pass by covering only the files it kept. Missing AND extra are both refused.
    required = set(config.ADMITTED_BUNDLE_FILES)
    keys = set(admitted)
    if keys != required:
        raise D.RefusalError(
            D.REFUSE_BUNDLE_SWAPPED_FILE,
            f"the report's artifact_sha256 key set is not the authoritative admitted inventory: "
            f"missing {sorted(required - keys)}, extra {sorted(keys - required)}. Every "
            f"admitted file — including {config.TARGET_IDENTITY_FILE} and "
            f"{config.VERIFICATION_FILE} — must be present, and nothing else may be")

    missing = [f for f in config.ADMITTED_BUNDLE_FILES
               if not os.path.exists(os.path.join(bundle_dir, f))]
    if missing:
        raise D.RefusalError(
            D.REFUSE_BUNDLE_INCOMPLETE,
            f"the Direct bundle is missing {missing}. An admitted bundle ships all "
            f"{len(config.ADMITTED_BUNDLE_FILES)} files")

    observed: dict[str, str] = {}
    swapped: list[str] = []
    for name in sorted(admitted):
        path = os.path.join(bundle_dir, name)
        if not os.path.exists(path):
            swapped.append(f"{name} (admitted, but absent on disk)")
            continue
        got = file_sha256(path)
        observed[name] = got
        if got != admitted[name]:
            swapped.append(f"{name} (admitted {admitted[name][:12]}..., on disk "
                           f"{got[:12]}...)")

    if swapped:
        raise D.RefusalError(
            D.REFUSE_BUNDLE_SWAPPED_FILE,
            f"{len(swapped)} file(s) in the Direct bundle do not hash to the values W10 "
            f"admitted: {swapped[:3]}. The bundle on disk is not the bundle that was "
            "admitted — a directory keeps its name when its contents are edited")

    # THE REPORT'S arm_bundle_run_id must equal BOTH the directory name AND arm_bundle.json's
    # own id. A report about bundle B beside directory A is refused even if every file hashes
    # (they can't, but the identity check is the belt to the hash's braces).
    claimed_id = bound.get("arm_bundle_run_id")
    dir_id = os.path.basename(os.path.normpath(bundle_dir))
    with open(os.path.join(bundle_dir, BUNDLE_FILE)) as fh:
        bundle_doc = json.load(fh)
    doc_id = bundle_doc.get("arm_bundle_run_id")
    if claimed_id != dir_id or claimed_id != doc_id:
        raise D.RefusalError(
            D.REFUSE_W10_REPORT_IS_ABOUT_ANOTHER_BUNDLE,
            f"the report's arm_bundle_run_id ({str(claimed_id)[:16]}) does not match the "
            f"bundle directory ({dir_id[:16]}) and/or arm_bundle.json ({str(doc_id)[:16]}). "
            "A report about a different bundle beside this directory is refused")
    return observed


def target_identity_canonical(bundle_dir: str) -> str:
    """The CANONICAL hash of the bound target_identity.json — through Direct's own loader.

    W10 re-hashes every shipped file's RAW bytes; the canonical hash is a separate statement
    the prepare side also records (``direct.target_identity`` computes it with
    ``direct.hashing.content_hash``). Computing it HERE with the same loader is what lets a run
    prove the identity it is admitting is the identity its inputs were prepared against — not
    merely the same file NAME. A malformed artifact is a typed refusal, not a raw exception.
    """
    try:
        return ti.load(bundle_dir)["canonical_sha256"]
    except ti.TargetIdentityError as e:
        raise D.RefusalError(
            D.REFUSE_BUNDLE_INCOMPLETE,
            f"the admitted bundle's {config.TARGET_IDENTITY_FILE} does not verify through "
            f"Direct's shared loader ({e}). W10 admitted its bytes, but the bound identity is "
            "the artifact this lane joins on, and it must parse") from e


def admit(*, bundle_dir: str, report_path: Optional[str], run_lock_sha256: str,
          run_lane: str) -> dict[str, Any]:
    """The whole gate. Returns the BOUND admission, or refuses with a typed reason."""
    if not bundle_dir or not os.path.isdir(bundle_dir):
        raise D.RefusalError(
            D.REFUSE_BUNDLE_MISSING,
            f"--direct-bundle {bundle_dir!r} is not a directory. P2S supports REAL, admitted "
            "Direct arms; there is no other input it will run from")

    report = load_report(report_path)
    check_identity(report)                      # incl. the placeholder-as-report refusal
    check_verdict(report)
    report_sha256 = check_report_hash(report)   # RE-DERIVED, never trusted
    check_not_self_admitted(bundle_dir, report)
    check_lock(report, bundle_dir, run_lock_sha256)     # three-way
    lane = check_lane(report, run_lane)
    observed = check_bundle_files(report, bundle_dir)
    ti_canonical = target_identity_canonical(bundle_dir)

    bound = report.get("bound_artifact") or {}
    return {
        "w10_verifier_id": report["verifier_id"],
        "w10_verifier_code_sha256": report["verifier_code_sha256"],
        "w10_verifier_code_pinned": True,
        "w10_spec_sha256": report["spec_sha256"],
        "w10_verdict": report["verdict"],
        "w10_report_sha256": report_sha256,
        "w10_report_sha256_rederived": True,
        "w10_gate_inventory_sha256": report.get("gate_inventory_sha256"),
        "w10_n_gates": report.get("n_gates"),
        "arm_bundle_run_id": bound.get("arm_bundle_run_id"),
        "arm_bundle_run_sha256": bound.get("arm_bundle_run_sha256"),
        "arm_rows_sha256": bound.get("arm_rows_sha256"),
        "scorer_view_sha256": bound.get("scorer_view_sha256"),
        "stage1_scorer_view_canonical_sha256":
            bound.get("stage1_scorer_view_canonical_sha256"),
        "condition": bound.get("condition"),
        "lane": lane,
        "solver_lock_sha256": bound.get("solver_lock_sha256"),
        "n_admitted_programs": bound.get("n_admitted_programs"),
        "n_arm_slots": bound.get("n_arm_slots"),
        "n_arm_rows": bound.get("n_arm_rows"),
        "direct_bundle_artifact_sha256": observed,
        "direct_bundle_artifact_map_sha256": content_sha256(observed),
        "target_identity_admitted_sha256": observed.get(config.TARGET_IDENTITY_FILE),
        # BOTH hashes of the bound identity: the RAW file bytes (above, what W10 re-hashed) and
        # the CANONICAL doc hash — the same function the prepare side uses, so the two can be
        # compared byte-for-byte when a run cross-checks that the inputs were prepared from the
        # bundle it is admitting (see prepared.load_and_verify's A-vs-B binding).
        "target_identity_canonical_sha256": ti_canonical,
        "bundle_is_real_and_admitted": True,
    }
