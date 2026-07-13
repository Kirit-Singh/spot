"""BINDING: what this run may speak for, and exactly why it refuses when it may not.

A secondary lane's whole safety rests on being bound to the primary artifact it supports. An
unbound one produces support for an arm that may not exist, under a program set the release
never admitted, against ranks that have since been edited — and every number in it looks fine.

THE CHAIN, IN ORDER
-------------------
  1. the SOLVER LOCK is verified against the pin (``direct.envlock``) — a run whose
     environment is unbound can be re-attributed to one it was not computed in;
  2. W10 — the INDEPENDENT Direct verifier, not the producer — must have ADMITTED this exact
     bundle. The report's identity is pinned, its hash is RE-DERIVED, its ``bound_artifact``
     is matched to the bundle on disk, and every shipped file is RE-HASHED. A bundle that
     arrived admitting itself is refused by name (see ``w10``);
  3. the ADMITTED PROGRAM SET is DERIVED from the bound Stage-1 v3 release's own
     ``base_portable`` flag — never a legacy registry, never a copied count. **Th9 is refused
     here**, because the release says it is not portable;
  4. the ARM must appear in the bundle's manifest, at the bundle's condition;
  5. the SCORER VIEW the bundle was built against must be the one this release derives;
  6. the ARM ROWS must RE-HASH to what the bundle and W10 both claim. This is what catches an
     ALTERED RANK: the value and the rank are inside the hashed projection.

MISSING STAYS MISSING, NEVER ZERO. A program with no surviving panel yields a REFUSED arm,
not a reconstruction of zeros. A zero is a measurement; an absence is not.

Every refusal is a TYPED disposition reason, so a scheduler can tell "P2S declined this arm,
for this reason" from "P2S crashed".
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

import pandas as pd
from direct import arm_bundle as direct_arm_bundle
from direct import envlock, scorer_view, trust
from direct import stage1_release_v3 as rel_v3

from . import armref, config, w10
from . import disposition as D

BUNDLE_FILE = "arm_bundle.json"
ROWS_FILE = "arms.parquet"
PROVENANCE_FILE = "provenance.json"

# Programs and poles this lane refuses OUTRIGHT, by name, whatever else is true of them.
SENSITIVITY_SUFFIXES = ("_actadj",)
SENSITIVITY_TOKENS = ("sensitivity",)
RESEARCH_NAMESPACE_PREFIXES = ("rq_", "ra_")


def verify_solver_lock(path: Optional[str]) -> dict[str, Any]:
    """The Stage-2 solver lock, hashed HERE and checked against THIS LANE'S OWN literal.

    NOT delegated to ``direct.envlock``. P2S is a CONSUMER of Direct's artifact, so with
    respect to that artifact it is a checker — and a pin the checker borrowed from the thing
    it checks is a pin nobody checked. If Direct's expected digest were ever wrong, a P2S
    that imported it would agree with the error, silently.

    So ``config.PINNED_SOLVER_LOCK_SHA256`` is this lane's own literal, and Direct's is then
    cross-checked against it. Two independently written pins that must AGREE: a drift between
    the lanes is loud instead of invisible.
    """
    if envlock.EXPECTED_SHA256 != config.PINNED_SOLVER_LOCK_SHA256:
        raise D.RefusalError(
            D.REFUSE_LOCK_MISMATCH,
            f"PIN DRIFT between lanes: Direct pins {envlock.EXPECTED_SHA256[:16]}... and "
            f"P2S pins {config.PINNED_SOLVER_LOCK_SHA256[:16]}.... The two lanes disagree "
            "about which environment Stage-2 runs in, and one of them is wrong. Refused "
            "rather than picking a side")

    if not path:
        raise D.RefusalError(
            D.REFUSE_LOCK_ABSENT,
            "no --env-lock was supplied. Every production invocation binds the Stage-2 "
            "solver lock into its run identity: a result whose environment is unrecorded "
            "cannot be reproduced, and one whose environment is unbound can be re-attributed "
            f"to an environment it was not computed in. The pinned lock is "
            f"{config.SOLVER_LOCK_FILENAME} ({config.PINNED_SOLVER_LOCK_SHA256[:16]}...)")
    if not os.path.exists(path):
        raise D.RefusalError(
            D.REFUSE_LOCK_ABSENT,
            f"the --env-lock at {os.path.basename(path)!r} does not exist")

    actual = w10.file_sha256(path)               # hashed HERE, from the bytes handed in
    if actual != config.PINNED_SOLVER_LOCK_SHA256:
        stage1 = os.path.basename(path) == envlock.STAGE1_LOCK_FILENAME
        hint = (" — that is the STAGE-1 lock. It is a valid, honest, content-addressed solver "
                "lock for a DIFFERENT environment (conda scvi_gpu, Python 3.11.15, pyarrow "
                "24.0.0). The two lanes run different environments and their locks are not "
                "interchangeable, so this is refused BY NAME rather than as a bare hash "
                "mismatch" if stage1 else "")
        raise D.RefusalError(
            D.REFUSE_LOCK_MISMATCH,
            f"the supplied --env-lock hashes to {actual[:16]}..., not the pinned Stage-2 "
            f"lock {config.PINNED_SOLVER_LOCK_SHA256[:16]}...{hint}. A lock whose bytes are "
            "decided by whoever supplies them pins whatever the supplier wanted it to")

    return {
        "lock_id": envlock.LOCK_ID,
        "name": os.path.basename(path),
        "sha256": actual,
        "expected_sha256": config.PINNED_SOLVER_LOCK_SHA256,
        "pin_is_this_lanes_own_literal": True,
        "verified": True,
        "status": "locked",
    }


def verify_p2s_runtime_lock(path: Optional[str]) -> dict[str, Any]:
    """The P2S RUNTIME lock — a SECOND, separate environment. Not the Direct lock.

    The Direct solver lock pins the environment the ADMITTED DIRECT ARMS were computed in. It
    contains neither sklearn nor pert2state_model, so it CANNOT execute this lane, and a run
    that bound only it would be claiming its numbers came out of an environment that cannot
    produce them.
    """
    if not path:
        raise D.RefusalError(
            D.REFUSE_P2S_LOCK_ABSENT,
            "no --p2s-env-lock was supplied. Two environments, two locks: the Direct solver "
            "lock pins the environment the ARMS were computed in and contains no sklearn and "
            "no pert2state_model — it cannot execute this lane. The P2S runtime lock is "
            f"{config.P2S_RUNTIME_LOCK_FILENAME} "
            f"({config.P2S_RUNTIME_LOCK_SHA256[:16]}...)")
    if not os.path.exists(path):
        raise D.RefusalError(
            D.REFUSE_P2S_LOCK_ABSENT,
            f"the --p2s-env-lock at {os.path.basename(path)!r} does not exist")

    actual = w10.file_sha256(path)
    if actual != config.P2S_RUNTIME_LOCK_SHA256:
        direct = actual == config.PINNED_SOLVER_LOCK_SHA256
        hint = (" — that is the DIRECT solver lock. It pins the environment the arms were "
                "computed in; it does not contain sklearn or pert2state_model and cannot "
                "execute this lane" if direct else "")
        raise D.RefusalError(
            D.REFUSE_P2S_LOCK_MISMATCH,
            f"the supplied --p2s-env-lock hashes to {actual[:16]}..., not the pinned P2S "
            f"runtime lock {config.P2S_RUNTIME_LOCK_SHA256[:16]}...{hint}")

    return {"lock_id": "spot.stage02.p2s_runtime_lock.v1",
            "name": os.path.basename(path), "sha256": actual,
            "expected_sha256": config.P2S_RUNTIME_LOCK_SHA256,
            "role": config.LOCK_ROLES["p2s_runtime_lock"],
            "verified": True, "status": "locked"}


def refuse_program(program_id: str, view: dict[str, Any]) -> None:
    """Th9, the activation covariate, the sensitivity lanes and research namespaces."""
    pid = str(program_id)

    # THE ACTIVATION COVARIATE IS NOT AN ARM. Fitting one would put the same quantity on both
    # sides of the design (`~ 1 + z_diff_activated + activation + ...` with z == activation) —
    # a perfectly collinear design whose beta is not identified. A number returned there would
    # be an arbitrary point on a ridge of equally good fits.
    if config.ACTIVATION_IS_NOT_AN_ARM and pid == config.ACTIVATION_PROGRAM_ID:
        raise D.RefusalError(
            D.REFUSE_ACTIVATION_ARM,
            f"{pid!r} IS the activation covariate of this lane's design. An arm for it would "
            "regress the program on itself — perfectly collinear, and the coefficient is not "
            "identified. It gets a TYPED UNAVAILABLE disposition, never a number, and it is "
            "not counted as a successful program-condition unit")

    if any(pid.endswith(s) for s in SENSITIVITY_SUFFIXES) or \
            any(t in pid for t in SENSITIVITY_TOKENS):
        raise D.RefusalError(
            D.REFUSE_SENSITIVITY_LANE,
            f"{pid!r} is a sensitivity / role-adjusted display-only lane. It is not a "
            "base-portable program and this lane will not carry an arm for it")
    if any(pid.startswith(p) for p in RESEARCH_NAMESPACE_PREFIXES):
        raise D.RefusalError(
            D.REFUSE_RESEARCH_NAMESPACE,
            f"{pid!r} is in a research-only namespace and may not enter a production lane")
    if pid not in view["admitted_program_ids"]:
        raise D.RefusalError(
            D.REFUSE_NOT_BASE_PORTABLE,
            f"{pid!r} is not marked base_portable by the bound v3 release, so it carries no "
            f"reusable arm. The release admits {view['n_admitted_programs']} program(s) and "
            f"excludes {view['excluded_program_ids']} — this set is DERIVED from the "
            "release's own bytes, never from a legacy registry or a copied count")


def check_panel(program_id: str, view: dict[str, Any]) -> None:
    """A program with no surviving panel is REFUSED, not reconstructed as zeros."""
    detail = view["programs"].get(str(program_id), {})
    if int(detail.get("n_panel", 0)) <= 0:
        raise D.RefusalError(
            D.REFUSE_NO_PANEL,
            f"{program_id!r} has no panel gene surviving into the effect universe, so there "
            "is no program direction to reconstruct. The arm is REFUSED — a reconstruction "
            "against an empty panel would be a table of zeros, and a zero is a measurement "
            "while an absence is not")


def load_release(*, release_path: str, kind: str = "production",
                 validation_path: Optional[str] = None,
                 gate_spec_path: Optional[str] = None,
                 release_root: Optional[str] = None) -> tuple[Any, dict[str, Any]]:
    """``(release, scorer_view)``. The admitted set is DERIVED from ``base_portable``.

    THE AUTHORITATIVE V3 RELEASE. Stage-1 v3.0.1 (539431d) ships a
    ``spot.stage01_v3_release.v1`` doc whose components are served under a STAGED ROOT; the
    legacy v1 manifest loader cannot read it. It is detected and loaded through Direct's OWN v3
    loader — the same one ``run_screen`` uses — so P2S binds the exact release object Direct
    did. The root is the staged tree the release doc sits at the top of: passed explicitly when
    supplied, otherwise the release file's own directory, and NEVER guessed into another tree.
    """
    if kind in config.RELEASE_LANES and os.path.isfile(release_path) \
            and rel_v3.is_v3_release(release_path):
        root = release_root or os.path.dirname(os.path.abspath(release_path))
        release = rel_v3.load(release_path, root=root, lane=kind)
        return release, scorer_view.view(release)
    if kind == "production":
        release = trust.load_production_release(release_path)
    elif kind == "research_only":
        release = trust.load_research_release(release_path)
    else:
        release = trust.load_fixture_release(release_path, validation_path, gate_spec_path)
    return release, scorer_view.view(release)


def load_bundle(bundle_dir: str) -> dict[str, Any]:
    """The bundle and its shipped rows, read back off DISK — never a caller's dict."""
    doc_path = os.path.join(bundle_dir, BUNDLE_FILE)
    rows_path = os.path.join(bundle_dir, ROWS_FILE)
    for p in (doc_path, rows_path):
        if not os.path.exists(p):
            raise D.RefusalError(
                D.REFUSE_BUNDLE_INCOMPLETE,
                f"the Direct bundle is missing {os.path.basename(p)}")
    with open(doc_path) as fh:
        doc = json.load(fh)
    rows = pd.read_parquet(rows_path).to_dict("records")
    return {"bundle": doc, "rows": rows, "bundle_dir": bundle_dir, "n_rows": len(rows)}


def check_rows_hash(loaded: dict[str, Any], admission: dict[str, Any]) -> str:
    """RECOMPUTE ``arm_rows_sha256`` from the shipped parquet. This catches an altered rank.

    Checked against BOTH the bundle's own claim and the value W10 admitted. Two independent
    statements about the same bytes: an edit that fixed up the bundle's claim would still have
    to forge W10's report, and forging that means re-deriving its content hash.
    """
    recomputed = direct_arm_bundle.rows_sha256(loaded["rows"])
    claimed = loaded["bundle"].get("arm_rows_sha256")
    admitted = admission.get("arm_rows_sha256")

    if claimed != recomputed:
        raise D.RefusalError(
            D.REFUSE_ALTERED_ROWS,
            f"the shipped arms.parquet hashes to {recomputed[:16]}... but the bundle claims "
            f"{str(claimed)[:16]}.... The arm values and ranks are inside the hashed "
            "projection, so the rows on disk are not the rows this bundle was written for. "
            "A secondary lane that supported edited ranks would be lending them its credit")

    if admitted is not None and admitted != recomputed:
        raise D.RefusalError(
            D.REFUSE_BUNDLE_STALE,
            f"the arm rows hash to {recomputed[:16]}... but W10 admitted "
            f"{str(admitted)[:16]}.... This is not the bundle that was admitted")
    return recomputed


def check_scorer_view(loaded: dict[str, Any], view: dict[str, Any],
                      admission: dict[str, Any]) -> None:
    """The bundle must have been built against THIS admitted program set."""
    derived = view["scorer_view_sha256"]
    claimed = (loaded["bundle"].get("scorer_view") or {}).get("scorer_view_sha256") \
        or (loaded["bundle"].get("method") or {}).get("scorer_view_sha256")

    if claimed != derived:
        raise D.RefusalError(
            D.REFUSE_SCORER_MISMATCH,
            f"the bundle was built against scorer view {str(claimed)[:16]}..., but the bound "
            f"v3 release derives {derived[:16]}.... Two releases that admit different "
            "programs — or the same programs on different panels — are not the same scorer "
            "view, and a bundle keyed only on program ids could be silently re-attributed "
            "from one to the other")

    admitted = admission.get("scorer_view_sha256")
    if admitted is not None and admitted != derived:
        raise D.RefusalError(
            D.REFUSE_BUNDLE_STALE,
            f"W10 admitted scorer view {str(admitted)[:16]}... but this release derives "
            f"{derived[:16]}...")


def find_arm(loaded: dict[str, Any], ref: armref.ArmRef,
             admission: dict[str, Any]) -> dict[str, Any]:
    """The arm's slot in the bundle manifest, at the admitted condition. Absent => refused."""
    condition = loaded["bundle"].get("condition")
    if str(condition) != ref.condition:
        raise D.RefusalError(
            D.REFUSE_ARM_WRONG_CONDITION,
            f"{ref.arm_key!r} is for condition {ref.condition!r} but the bundle is for "
            f"{condition!r}")

    admitted_condition = admission.get("condition")
    if admitted_condition is not None and str(admitted_condition) != ref.condition:
        raise D.RefusalError(
            D.REFUSE_ARM_WRONG_CONDITION,
            f"W10 admitted the bundle at condition {admitted_condition!r}, not "
            f"{ref.condition!r}")

    arms = {str(a["arm_key"]): a for a in loaded["bundle"].get("arms", [])}
    slot = arms.get(ref.arm_key)
    if slot is None:
        raise D.RefusalError(
            D.REFUSE_ARM_NOT_IN_BUNDLE,
            f"{ref.arm_key!r} is not one of the {len(arms)} arm(s) in the admitted bundle. "
            "An arm nobody computed cannot be supported, and inventing a slot for it would "
            "give a UI a lane that no primary artifact stands behind")
    return slot


def refuse_fixture_release(release, lane: str) -> None:
    """A FIXTURE release may never back a release-lane run. The TYPE is the lane.

    There is no ``is_fixture`` boolean to check — and there deliberately isn't one, because a
    boolean can be edited. What cannot be edited is the release TYPE: ``trust`` loads a
    fixture as a ``FixtureRelease``, and only a ``ProductionRelease`` may back production. A
    fixture cannot be relabelled into production by changing a string, because there is no
    string to change.
    """
    kind = getattr(release, "kind", None)
    if lane in config.RELEASE_LANES and kind != lane:
        raise D.RefusalError(
            D.REFUSE_FIXTURE_INPUT,
            f"this is a {lane!r} run but the bound Stage-1 release is a {kind!r} release. "
            "Fixture arms carry fixture numbers; reconstruction support attached to them and "
            "served under a release lane would be fixture output wearing a production "
            "artifact's provenance")


def admit_inputs(*, bundle_dir: str, w10_report: Optional[str], env_lock: Optional[str],
                 lane: str = "production") -> dict[str, Any]:
    """The RELEASE-INDEPENDENT half: the solver lock and W10's admission of this bundle.

    Run FIRST, and deliberately so. These are the cheap, typed refusals, and a bad bundle or
    a missing report must come back as a NAMED disposition — not as whatever error the
    Stage-1 release loader happens to raise on the way past it. A refusal that arrives as
    somebody else's exception is a refusal a scheduler cannot branch on.
    """
    lock = verify_solver_lock(env_lock)
    admission = w10.admit(bundle_dir=bundle_dir, report_path=w10_report,
                          run_lock_sha256=lock["sha256"], run_lane=lane)
    return {"solver_lock": lock, "admission": admission, "lane": lane}


def bind(*, arm_key: str, bundle_dir: str, w10_report: Optional[str],
         env_lock: Optional[str], view: dict[str, Any], release=None,
         lane: str = "production",
         admitted: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """The whole chain. Fail-closed, typed refusals, nothing assumed."""
    admitted = admitted or admit_inputs(bundle_dir=bundle_dir, w10_report=w10_report,
                                        env_lock=env_lock, lane=lane)
    lock, admission = admitted["solver_lock"], admitted["admission"]

    if release is not None:
        refuse_fixture_release(release, lane)

    ref = armref.parse(arm_key)                 # refuses a temporal/pathway/pole/role key
    refuse_program(ref.program_id, view)        # refuses Th9, sensitivity, research
    check_panel(ref.program_id, view)

    loaded = load_bundle(bundle_dir)
    check_scorer_view(loaded, view, admission)
    rows_sha = check_rows_hash(loaded, admission)
    slot = find_arm(loaded, ref, admission)

    return {
        "arm": ref,
        "arm_slot": slot,
        "bundle": loaded["bundle"],
        "rows": loaded["rows"],
        "lane": lane,
        "solver_lock": lock,
        "admission": admission,
        "arm_bundle_run_id": admission.get("arm_bundle_run_id")
        or loaded["bundle"].get("arm_bundle_run_id"),
        "arm_rows_sha256": rows_sha,
        "scorer_view_sha256": view["scorer_view_sha256"],
        "admitted_program_ids": view["admitted_program_ids"],
        "n_admitted_programs": view["n_admitted_programs"],
        "base_portable": True,
        "verifier": {"verdict": admission["w10_verdict"],
                     "verifier_id": admission["w10_verifier_id"],
                     "verifier_report_sha256": admission["w10_report_sha256"]},
    }


def bound_block(bound: dict[str, Any]) -> dict[str, Any]:
    """What the artifact records about what it was bound to. Ids and hashes only."""
    a = bound["admission"]
    return {
        "lane": bound["lane"],
        "solver_lock_sha256": bound["solver_lock"]["sha256"],
        "solver_lock_pinned_sha256": config.PINNED_SOLVER_LOCK_SHA256,
        "w10_verifier_id": a["w10_verifier_id"],
        # WHICH CODE produced the verdict — pinned, not merely recorded. An honestly resealed
        # report agrees with itself and still names no checker.
        "w10_verifier_code_sha256": a["w10_verifier_code_sha256"],
        "w10_verifier_code_pinned": a["w10_verifier_code_pinned"],
        "w10_spec_sha256": a["w10_spec_sha256"],
        "w10_verdict": a["w10_verdict"],
        "w10_report_sha256": a["w10_report_sha256"],
        "w10_report_sha256_rederived": True,
        "bundle_is_real_and_admitted": True,
        "arm_bundle_run_id": bound["arm_bundle_run_id"],
        "arm_bundle_run_sha256": a.get("arm_bundle_run_sha256"),
        "arm_rows_sha256": bound["arm_rows_sha256"],
        "scorer_view_sha256": bound["scorer_view_sha256"],
        "direct_bundle_artifact_sha256": a["direct_bundle_artifact_sha256"],
        # the WHOLE-BUNDLE fingerprint and BOTH identity hashes, so a run can prove its inputs
        # were prepared from the exact bundle it is admitting — the A-vs-B binding, field for
        # field, not a subset that a fail-open comparison would wave through.
        "direct_bundle_artifact_map_sha256": a["direct_bundle_artifact_map_sha256"],
        "target_identity_admitted_sha256": a["target_identity_admitted_sha256"],
        "target_identity_canonical_sha256": a["target_identity_canonical_sha256"],
    }
