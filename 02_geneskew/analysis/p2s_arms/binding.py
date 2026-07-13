"""BINDING: what this run is entitled to say something about, and what it refuses.

A secondary lane's whole safety rests on being bound to the primary artifact it supports.
An unbound one produces support for an arm that may not exist, under a program set the
release never admitted, against ranks that have since been edited — and every number in it
looks fine.

So five things are bound, and each has a named refusal:

  1. the ADMITTED PROGRAM SET — DERIVED from the bound Stage-1 v3 release's own
     ``base_portable`` flag, never from a legacy registry and never from a copied count.
     Th9 is excluded because the release says it is not portable, not because a constant
     somewhere says "10";
  2. the ARM — it must appear in the bound all-arm bundle's manifest. An arm nobody
     computed cannot be supported;
  3. the SCORER VIEW — the bundle's ``scorer_view_sha256`` must equal the one re-derived
     from the bound release. A bundle built against a different program set is a bundle
     about different arms;
  4. the ARM ROWS — ``arm_rows_sha256``, RECOMPUTED from the shipped ``arms.parquet``, must
     equal the bundle's claim. This is what catches an ALTERED RANK: the value and the rank
     are inside the hashed projection, so a rank edited after the fact cannot pass;
  5. the VERIFIER REPORT — the bundle's independent verifier must have said ADMIT. Support
     for an arm its own verifier rejected is support for nothing.

MISSING STAYS MISSING, NEVER ZERO. A program with no surviving panel yields a REFUSED arm,
not a reconstruction of zeros. A zero is a measurement; an absence is not.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

import pandas as pd
from direct import arm_bundle as direct_arm_bundle
from direct import scorer_view, trust

from . import armref

BUNDLE_FILE = "arm_bundle.json"
ROWS_FILE = "arms.parquet"

ADMIT = "admit"

# Programs and poles this lane refuses OUTRIGHT, by name, whatever else is true of them.
SENSITIVITY_SUFFIXES = ("_actadj",)
SENSITIVITY_TOKENS = ("sensitivity",)
RESEARCH_NAMESPACE_PREFIXES = ("rq_", "ra_")


class BindingError(ValueError):
    """This run may not proceed against what it was given. Refuse; never assume."""

    def __init__(self, reason: str, message: str):
        super().__init__(message)
        self.reason = reason


class ArmMismatchError(BindingError):
    """The requested arm is not in the bound bundle."""


class ScorerMismatchError(BindingError):
    """The bundle was built against a different admitted program set."""


class AlteredRankError(BindingError):
    """The shipped arm rows do not hash to what the bundle claims."""


class VerifierRejectedError(BindingError):
    """The bundle's own independent verifier did not admit it."""


class PanelMissingError(BindingError):
    """The program has no surviving panel. Missing stays missing, never zero."""


class ProgramRefusedError(BindingError):
    """A Th9, sensitivity or research-lane program. Refused by name."""


def _load_json(path: str) -> dict[str, Any]:
    with open(path) as fh:
        return json.load(fh)


def refuse_program(program_id: str, view: dict[str, Any]) -> None:
    """Th9, the sensitivity/actadj lanes and research namespaces. Named, not silent."""
    pid = str(program_id)
    if any(pid.endswith(s) for s in SENSITIVITY_SUFFIXES) or \
            any(t in pid for t in SENSITIVITY_TOKENS):
        raise ProgramRefusedError(
            "sensitivity_lane_refused",
            f"{pid!r} is a sensitivity / role-adjusted display-only lane. It is not a "
            "base-portable program and this lane will not carry an arm for it")
    if any(pid.startswith(p) for p in RESEARCH_NAMESPACE_PREFIXES):
        raise ProgramRefusedError(
            "research_namespace_refused",
            f"{pid!r} is in a research-only namespace and may not enter a production lane")
    if pid not in view["admitted_program_ids"]:
        raise ProgramRefusedError(
            "program_is_not_base_portable",
            f"{pid!r} is not marked base_portable by the bound v3 release, so it carries no "
            f"reusable arm. The release admits {view['n_admitted_programs']} program(s) and "
            f"excludes {view['excluded_program_ids']} — this set is DERIVED from the "
            "release's own bytes, never from a legacy registry or a copied count")


def check_panel(program_id: str, view: dict[str, Any]) -> None:
    """A program with no surviving panel is REFUSED, not reconstructed as zeros."""
    detail = view["programs"].get(str(program_id), {})
    if int(detail.get("n_panel", 0)) <= 0:
        raise PanelMissingError(
            "program_has_no_surviving_panel",
            f"{program_id!r} has no panel gene surviving into the effect universe, so there "
            "is no program direction to reconstruct. The arm is REFUSED — a reconstruction "
            "against an empty panel would be a table of zeros, and a zero is a measurement "
            "while an absence is not")


def load_release(*, release_path: str, kind: str = "production",
                 validation_path: Optional[str] = None,
                 gate_spec_path: Optional[str] = None) -> tuple[Any, dict[str, Any]]:
    """``(release, scorer_view)``. The admitted set is DERIVED from ``base_portable``.

    The release itself comes back too: the panel and control gene LISTS live on it, and they
    are what the readout universe must exclude. The view carries only their hashes.
    """
    if kind == "production":
        release = trust.load_production_release(release_path)
    elif kind == "research_only":
        release = trust.load_research_release(release_path)
    else:
        release = trust.load_fixture_release(release_path, validation_path, gate_spec_path)
    return release, scorer_view.view(release)


def load_scorer_view(**kw) -> dict[str, Any]:
    """The scorer view alone, for callers that do not need the panels."""
    return load_release(**kw)[1]


def load_bundle(bundle_dir: str) -> dict[str, Any]:
    """The all-arm bundle and its shipped rows, read back off DISK — never a caller's dict."""
    bundle_path = os.path.join(bundle_dir, BUNDLE_FILE)
    rows_path = os.path.join(bundle_dir, ROWS_FILE)
    for p in (bundle_path, rows_path):
        if not os.path.exists(p):
            raise BindingError(
                "bundle_is_incomplete",
                f"the all-arm bundle at {os.path.basename(bundle_dir)} is missing "
                f"{os.path.basename(p)}")

    doc = _load_json(bundle_path)
    rows = pd.read_parquet(rows_path).to_dict("records")
    return {"bundle": doc, "rows": rows,
            "bundle_dir": bundle_dir, "n_rows": len(rows)}


def check_rows_hash(loaded: dict[str, Any]) -> str:
    """RECOMPUTE ``arm_rows_sha256`` from the shipped parquet. This catches an altered rank.

    The projection is Direct's own ``canonical_rows`` — the shape the hash was taken over,
    written so that a READER OF THE PARQUET can re-derive it. The rank and the value are
    inside it, so a rank edited after the bundle was written cannot survive this.
    """
    claimed = loaded["bundle"].get("arm_rows_sha256")
    recomputed = direct_arm_bundle.rows_sha256(loaded["rows"])
    if claimed != recomputed:
        raise AlteredRankError(
            "arm_rows_do_not_hash_to_the_bundle_claim",
            f"the shipped arms.parquet hashes to {recomputed!r} but the bundle claims "
            f"{claimed!r}. The arm values and ranks are inside the hashed projection, so "
            "the rows on disk are not the rows this bundle was written for. Refused: a "
            "secondary lane that supported edited ranks would be lending them its credit")
    return recomputed


def check_scorer_view(loaded: dict[str, Any], view: dict[str, Any]) -> None:
    """The bundle must have been built against THIS admitted program set."""
    claimed = (loaded["bundle"].get("method") or {}).get("scorer_view_sha256")
    if claimed != view["scorer_view_sha256"]:
        raise ScorerMismatchError(
            "bundle_scorer_view_does_not_match_the_bound_release",
            f"the bundle was built against scorer view {claimed!r}, but the bound v3 "
            f"release derives {view['scorer_view_sha256']!r}. Two releases that admit "
            "different programs — or the same programs on different panels — are not the "
            "same scorer view, and a bundle keyed only on program ids could be silently "
            "re-attributed from one to the other")


def check_verifier(report: dict[str, Any]) -> dict[str, Any]:
    """The bundle's INDEPENDENT verifier must have said ADMIT."""
    verdict = str(report.get("verdict", "")).lower()
    if verdict != ADMIT:
        raise VerifierRejectedError(
            "bundle_was_not_admitted_by_its_verifier",
            f"the all-arm bundle's independent verifier returned {verdict!r}, not "
            f"{ADMIT!r}. A secondary lane may only support an INDEPENDENTLY ADMITTED arm — "
            "support for a rejected bundle would launder its rejection into evidence")
    return {"verdict": verdict,
            "verifier_id": report.get("verifier_id"),
            "verifier_report_sha256": report.get("report_sha256")}


def find_arm(loaded: dict[str, Any], ref: armref.ArmRef) -> dict[str, Any]:
    """The arm's slot in the bundle manifest. Absent => refused."""
    arms = {str(a["arm_key"]): a for a in loaded["bundle"].get("arms", [])}
    slot = arms.get(ref.arm_key)
    if slot is None:
        raise ArmMismatchError(
            "arm_is_not_in_the_bound_bundle",
            f"{ref.arm_key!r} is not one of the {len(arms)} arm(s) in the bound bundle "
            f"(condition {loaded['bundle'].get('condition')!r}). An arm nobody computed "
            "cannot be supported, and inventing a slot for it would give a UI a lane that "
            "no primary artifact stands behind")
    if str(loaded["bundle"].get("condition")) != ref.condition:
        raise ArmMismatchError(
            "arm_condition_is_not_the_bundle_condition",
            f"{ref.arm_key!r} is for condition {ref.condition!r} but the bundle is for "
            f"{loaded['bundle'].get('condition')!r}")
    return slot


def bind(*, arm_key: str, bundle_dir: str, view: dict[str, Any],
         verifier_report: dict[str, Any]) -> dict[str, Any]:
    """Everything this run is entitled to say something about. Fail-closed, all five checks."""
    ref = armref.parse(arm_key)
    refuse_program(ref.program_id, view)
    check_panel(ref.program_id, view)

    loaded = load_bundle(bundle_dir)
    check_scorer_view(loaded, view)
    rows_sha = check_rows_hash(loaded)
    verifier = check_verifier(verifier_report)
    slot = find_arm(loaded, ref)

    return {
        "arm": ref,
        "arm_slot": slot,
        "bundle": loaded["bundle"],
        "rows": loaded["rows"],
        "arm_bundle_run_id": loaded["bundle"].get("arm_bundle_run_id"),
        "arm_rows_sha256": rows_sha,
        "scorer_view_sha256": view["scorer_view_sha256"],
        "admitted_program_ids": view["admitted_program_ids"],
        "n_admitted_programs": view["n_admitted_programs"],
        "base_portable": True,
        "verifier": verifier,
    }
