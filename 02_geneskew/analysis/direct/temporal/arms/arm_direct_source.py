"""The REAL temporal endpoint source: two admitted Direct all-arm bundles.

There is no production ``effect_source.json`` — inventing one would be a giant serialized
artifact nobody else produces. The Direct all-arm bundle ALREADY carries, per
``(condition, program, target)``, the one ``base_delta`` (the masked program projection
``delta_p``) plus its base QC and panel/control survival. So a temporal endpoint at a
condition IS a Direct bundle at that condition, and the frozen temporal estimand

    base_temporal_delta(program, target, from->to)
        = delta_p(to) - delta_p(from)
        = Direct[to].base_delta - Direct[from].base_delta

is a difference of two Direct bundles' base deltas. This consumes the content-addressed,
independently-admitted Direct bundles and refuses anything else.

FAIL-CLOSED, EACH AT A NAMED GATE
---------------------------------
  * NONE           — a Direct bundle is missing/absent.
  * AMBIGUOUS       — it is not a readable ``spot.stage02_direct_arm_bundle.v1``.
  * FIXTURE_FALLBACK— it is the temporal fixture effect source, not a real Direct bundle.
  * SWAPPED_CONDITION— the bundle's condition is not the endpoint asked for.
  * STALE_BUNDLE    — its bytes do not match the pinned Direct bundle sha.
  * DUPLICATE_MISMATCH— an increase/decrease pair whose values are not exact negations, or a
                      program/target row that disagrees with its twin about the base delta.
  * MISSING_W10     — no admitting W10 report accompanies the Direct bundle.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from ...arm_keys import DECREASE, INCREASE
from ...hashing import file_sha256
from . import arm_bundle as ab

DIRECT_BUNDLE_SCHEMA = "spot.stage02_direct_arm_bundle.v1"
FIXTURE_EFFECT_SCHEMA = "spot.stage02_temporal_arm_effect_source.v1"
DIRECT_BUNDLE_FILENAME = "arm_bundle.json"

# the base-record fields a Direct arm row carries and a temporal endpoint needs
_ROW_FIELDS = ("base_delta", "base_state", "base_passed", "projection_status",
               "n_panel_surviving", "n_control_surviving", "evaluable", "value")
_VALUE_EPS = 1e-12


class DirectSourceError(ValueError):
    """A Direct-bundle endpoint source is unusable. Refuse at a NAMED gate; never guess."""

    def __init__(self, gate: str, message: str):
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


def _load(path: str) -> dict[str, Any]:
    if not path or not os.path.exists(path):
        raise DirectSourceError("NONE", f"no Direct all-arm bundle at {path!r}: a temporal "
                                "endpoint is a Direct bundle, and there is none here")
    p = os.path.join(path, DIRECT_BUNDLE_FILENAME) if os.path.isdir(path) else path
    if not os.path.exists(p):
        raise DirectSourceError("NONE", f"no {DIRECT_BUNDLE_FILENAME} in {path!r}")
    try:
        with open(p, "rb") as fh:
            raw = fh.read()
        doc = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise DirectSourceError("AMBIGUOUS", f"{p!r} is not readable JSON: {exc}") from None
    if not isinstance(doc, dict):
        raise DirectSourceError("AMBIGUOUS", f"{p!r} is not a bundle document")
    doc["__raw_sha256__"] = file_sha256(p)
    return doc


def _rows(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """The arm rows, wherever the Direct bundle keeps them (flat list or under ``arms``)."""
    if isinstance(doc.get("rows"), list):
        return doc["rows"]
    if isinstance(doc.get("arm_rows"), list):
        return doc["arm_rows"]
    rows: list[dict[str, Any]] = []
    for arm in (doc.get("arms") or []):
        rows += arm.get("rows") or arm.get("records") or []
    return rows


def load_direct_bundle(path: str, *, expect_condition: str,
                       expect_bundle_sha256: Optional[str] = None,
                       w10_report: Optional[str] = None) -> dict[str, Any]:
    """Load, verify and index ONE admitted Direct all-arm bundle for one condition.

    Refuses a missing/ambiguous bundle, the temporal fixture source, the wrong condition, a
    stale (unpinned-mismatch) bundle, and a Direct bundle with no admitting W10 report.
    Returns ``{bundle_id, condition, raw_sha256, base}`` where ``base`` maps
    ``target_id -> {program_id -> {base_delta, ...}}``.
    """
    doc = _load(path)
    schema = doc.get("schema_version")
    if schema == FIXTURE_EFFECT_SCHEMA:
        raise DirectSourceError(
            "FIXTURE_FALLBACK", "this is the temporal fixture effect source "
            f"({FIXTURE_EFFECT_SCHEMA}), not a real Direct all-arm bundle. No fixture JSON "
            "may stand in for a Direct bundle in a real run")
    if schema != DIRECT_BUNDLE_SCHEMA:
        raise DirectSourceError(
            "AMBIGUOUS", f"schema {schema!r} is not {DIRECT_BUNDLE_SCHEMA!r}; the temporal "
            "endpoint is a Direct all-arm bundle, nothing else")

    condition = doc.get("condition") or (doc.get("context") or {}).get("condition")
    if str(condition) != str(expect_condition):
        raise DirectSourceError(
            "SWAPPED_CONDITION", f"this Direct bundle is condition {condition!r} but the "
            f"endpoint asked for {expect_condition!r} — a swapped endpoint would silently "
            "difference the wrong two populations")
    if expect_bundle_sha256 and doc["__raw_sha256__"] != str(expect_bundle_sha256):
        raise DirectSourceError(
            "STALE_BUNDLE", f"this Direct bundle hashes to {doc['__raw_sha256__'][:16]}…, "
            f"not the pinned {str(expect_bundle_sha256)[:16]}… — a stale bundle admits a run "
            "against numbers that were superseded")
    if not (w10_report and os.path.exists(w10_report)):
        raise DirectSourceError(
            "MISSING_W10", "no admitting W10 report accompanies this Direct bundle; a "
            "temporal run may not stand on a Direct endpoint no independent lane admitted")

    return {
        "bundle_id": doc.get("bundle_id"),
        "condition": str(condition),
        "raw_sha256": doc["__raw_sha256__"],
        "w10_report_sha256": file_sha256(w10_report),
        "base": _base_by_target(_rows(doc), str(condition)),
    }


def _base_by_target(rows: list[dict[str, Any]],
                    condition: str) -> dict[str, dict[str, dict[str, Any]]]:
    """Dedupe the increase/decrease rows to ONE base delta per (program, target).

    The two arms are exact sign transforms of one base delta; here they must AGREE — the
    base_delta identical and the values exact negations — or the pair is refused. A Direct
    bundle whose two arms disagree about the magnitude they share is internally broken, and
    a temporal run built on it would inherit the disagreement.
    """
    grouped: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for r in rows:
        key = (str(r["program_id"]), str(r["target_id"]))
        grouped.setdefault(key, {})[str(r["desired_change"])] = r

    base: dict[str, dict[str, dict[str, Any]]] = {}
    for (program_id, target_id), byd in grouped.items():
        inc, dec = byd.get(INCREASE), byd.get(DECREASE)
        if inc is None or dec is None:
            raise DirectSourceError(
                "DUPLICATE_MISMATCH", f"{program_id}|{target_id}: the Direct bundle is "
                "missing one of the increase/decrease rows — a base delta with only one arm "
                "cannot be checked for agreement")
        if inc.get("base_delta") != dec.get("base_delta"):
            raise DirectSourceError(
                "DUPLICATE_MISMATCH", f"{program_id}|{target_id}: increase.base_delta "
                f"{inc.get('base_delta')!r} != decrease.base_delta {dec.get('base_delta')!r}")
        iv, dv = inc.get("value"), dec.get("value")
        if (iv is None) != (dv is None) or (
                iv is not None and abs(float(iv) + float(dv)) > _VALUE_EPS):
            raise DirectSourceError(
                "DUPLICATE_MISMATCH", f"{program_id}|{target_id}: increase.value {iv!r} and "
                f"decrease.value {dv!r} are not exact negations")
        # the ONE base delta + its provenance, taken from the (now-agreeing) increase row
        base.setdefault(target_id, {})[program_id] = {
            "delta": inc.get("base_delta"),
            "status": inc.get("projection_status"),
            "n_panel_surviving": inc.get("n_panel_surviving"),
            "n_control_surviving": inc.get("n_control_surviving"),
            "base_state": inc.get("base_state"),
            "base_passed": inc.get("base_passed"),
        }
    return base


def endpoints(direct: dict[str, Any],
              admitted: dict[str, dict[str, Any]]) -> list[ab.TargetEndpoint]:
    """One ``TargetEndpoint`` per target, its ``program_delta`` the Direct base deltas.

    The endpoint's per-program projection is EXACTLY the Direct bundle's base delta, so the
    temporal difference-in-differences the arm bundle then computes is a difference of two
    admitted Direct bundles — never a re-projection.
    """
    programs = sorted(admitted)
    out: list[ab.TargetEndpoint] = []
    for target_id, by_program in sorted(direct["base"].items()):
        missing = [p for p in programs if p not in by_program]
        if missing:
            raise DirectSourceError(
                "AMBIGUOUS", f"Direct bundle target {target_id!r} carries no base delta for "
                f"admitted program(s) {missing[:3]}; the program axis is incomplete")
        program_delta = {
            p: {"delta": by_program[p]["delta"], "status": by_program[p]["status"],
                "panel_mean": None, "control_mean": None,
                "n_panel_surviving": by_program[p]["n_panel_surviving"],
                "n_control_surviving": by_program[p]["n_control_surviving"]}
            for p in programs}
        # base QC is per target; take it from any program's row (all equal per target)
        any_row = next(iter(by_program.values()))
        out.append(ab.TargetEndpoint(
            target_id=target_id, program_delta=program_delta,
            base_qc_passed=bool(any_row["base_passed"]),
            base_qc_state=str(any_row["base_state"])))
    return out


def source_binding(from_direct: dict[str, Any], to_direct: dict[str, Any]) -> dict[str, Any]:
    """WHICH two Direct bundles (and their W10 admissions) this endpoint pair stood on.

    Bound into the temporal identity so a temporal run is attributable to the exact Direct
    bundles it differenced — a stale or swapped bundle changes this and cannot keep the id.
    """
    return {
        "endpoint_source": "two_admitted_direct_all_arm_bundles",
        "from_direct_bundle_id": from_direct["bundle_id"],
        "from_direct_bundle_sha256": from_direct["raw_sha256"],
        "from_w10_report_sha256": from_direct["w10_report_sha256"],
        "to_direct_bundle_id": to_direct["bundle_id"],
        "to_direct_bundle_sha256": to_direct["raw_sha256"],
        "to_w10_report_sha256": to_direct["w10_report_sha256"],
    }
