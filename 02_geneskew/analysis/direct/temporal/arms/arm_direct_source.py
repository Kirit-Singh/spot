"""The REAL temporal endpoint source: two ADMITTED Direct all-arm bundles.

There is no production ``effect_source.json``. The Direct all-arm bundle
(``spot.stage02_direct_arm_bundle.v1``) already carries, per ``(condition, program,
target)``, one ``base_delta`` (the masked program projection ``delta_p``) plus base QC and
panel/control survival. So a temporal endpoint at a condition IS a Direct bundle at that
condition, and the frozen temporal estimand

    base_temporal_delta(program, target, from->to)
        = delta_p(to) - delta_p(from)
        = Direct[to].base_delta - Direct[from].base_delta

is a difference of two admitted Direct bundles. This consumes the ACTUAL Direct bundle
directory (producer ``fc9bdcd``): ``arm_bundle.json`` (the doc + ``arm_bundle_run_id``),
``arms.parquet`` (the base_delta rows), ``provenance.json`` (the run binding: condition,
scorer view, gene universe, environment lock, ``arm_rows_sha256``), and ``verification.json``
— the independent per-run "W10" report, whose verdict must be an ADMIT, not the producer's
own ``pending_independent_verification`` placeholder.

FAIL-CLOSED, EACH AT A NAMED GATE
---------------------------------
  * NONE             — the Direct bundle directory/arm_bundle.json is missing.
  * AMBIGUOUS         — it is not a ``spot.stage02_direct_arm_bundle.v1`` (or the rows/prov
                        are unreadable).
  * FIXTURE_FALLBACK  — it is the temporal fixture effect source, not a real Direct bundle.
  * SWAPPED_CONDITION — the bundle's bound condition is not the endpoint asked for.
  * STALE_BUNDLE      — its arm_bundle.json bytes do not match the pinned Direct bundle sha.
  * DUPLICATE_MISMATCH— an increase/decrease pair whose base_delta or values disagree.
  * MISSING_W10       — verification.json is absent, still PENDING, or not an ADMIT.
  * WRONG_ENV_LOCK    — the Direct bundle was solved under a lock other than the pinned 2983.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from ...arm_keys import DECREASE, INCREASE
from ...hashing import file_sha256
from . import arm_bundle as ab
from . import arm_env

DIRECT_BUNDLE_SCHEMA = "spot.stage02_direct_arm_bundle.v1"
FIXTURE_EFFECT_SCHEMA = "spot.stage02_temporal_arm_effect_source.v1"
BUNDLE_FILE = "arm_bundle.json"
ROWS_FILE = "arms.parquet"
PROVENANCE_FILE = "provenance.json"
VERIFICATION_FILE = "verification.json"
PENDING_VERDICT = "pending_independent_verification"
_VALUE_EPS = 1e-12


class DirectSourceError(ValueError):
    """A Direct-bundle endpoint source is unusable. Refuse at a NAMED gate; never guess."""

    def __init__(self, gate: str, message: str):
        super().__init__(f"[{gate}] {message}")
        self.gate = gate


def _nan_to_none(x: Any) -> Any:
    """A parquet-round-tripped null float reads back as NaN; make it None again."""
    return None if x is None or (isinstance(x, float) and x != x) else x


def _int_or_none(x: Any) -> Optional[int]:
    """A survivor COUNT: None when null/NaN, else the integer form (parquet widens it to
    float). A NaN count would otherwise reach the content hash, which JSON refuses."""
    x = _nan_to_none(x)
    return None if x is None else int(x)


def _read_json(path: str, gate: str) -> dict[str, Any]:
    try:
        with open(path) as fh:
            doc = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        raise DirectSourceError(gate, f"{path!r} is not readable JSON: {exc}") from None
    if not isinstance(doc, dict):
        raise DirectSourceError(gate, f"{path!r} is not a document")
    return doc


def _read_rows(path: str) -> list[dict[str, Any]]:
    try:
        import pandas as pd
        return pd.read_parquet(path).to_dict("records")
    except Exception as exc:                       # noqa: BLE001 - any read failure is fatal
        raise DirectSourceError("AMBIGUOUS", f"{path!r} arm rows unreadable: {exc}") from None


def load_direct_bundle(bundle_dir: str, *, expect_condition: str,
                       expect_bundle_sha256: Optional[str] = None,
                       w10_report: Optional[str] = None) -> dict[str, Any]:
    """Load, verify and index ONE admitted Direct all-arm bundle for one condition.

    ``bundle_dir`` is the Direct bundle directory. ``w10_report`` overrides where the
    independent admission is read from (default: ``verification.json`` in the dir).
    """
    if not bundle_dir or not os.path.isdir(bundle_dir):
        raise DirectSourceError("NONE", f"no Direct all-arm bundle directory at "
                                f"{bundle_dir!r}: a temporal endpoint IS a Direct bundle")
    bundle_path = os.path.join(bundle_dir, BUNDLE_FILE)
    if not os.path.exists(bundle_path):
        raise DirectSourceError("NONE", f"no {BUNDLE_FILE} in {bundle_dir!r}")

    raw_sha = file_sha256(bundle_path)
    doc = _read_json(bundle_path, "AMBIGUOUS")
    schema = doc.get("schema_version")
    if schema == FIXTURE_EFFECT_SCHEMA:
        raise DirectSourceError(
            "FIXTURE_FALLBACK", "this is the temporal fixture effect source "
            f"({FIXTURE_EFFECT_SCHEMA}), not a real Direct all-arm bundle")
    if schema != DIRECT_BUNDLE_SCHEMA:
        raise DirectSourceError(
            "AMBIGUOUS", f"schema {schema!r} is not {DIRECT_BUNDLE_SCHEMA!r}")
    if expect_bundle_sha256 and raw_sha != str(expect_bundle_sha256):
        raise DirectSourceError(
            "STALE_BUNDLE", f"this Direct bundle hashes to {raw_sha[:16]}…, not the pinned "
            f"{str(expect_bundle_sha256)[:16]}… — a stale bundle admits superseded numbers")

    prov = _read_json(os.path.join(bundle_dir, PROVENANCE_FILE), "AMBIGUOUS")
    rb = (prov.get("run_binding") or {})
    condition = rb.get("condition") or doc.get("condition")
    if str(condition) != str(expect_condition):
        raise DirectSourceError(
            "SWAPPED_CONDITION", f"this Direct bundle is condition {condition!r} but the "
            f"endpoint asked for {expect_condition!r}")

    env = (rb.get("environment_lock") or {})
    env_sha = env.get("sha256") or env.get("env_lock_sha256")
    if env_sha != arm_env.AUTHORITATIVE_ENV_LOCK_SHA256:
        raise DirectSourceError(
            "WRONG_ENV_LOCK", f"this Direct bundle was solved under lock {str(env_sha)[:16]}…"
            f", not the authoritative {arm_env.AUTHORITATIVE_ENV_LOCK_SHA256[:16]}… — every "
            "lane must bind the SAME solver lock")

    ver_path = w10_report or os.path.join(bundle_dir, VERIFICATION_FILE)
    if not os.path.exists(ver_path):
        raise DirectSourceError("MISSING_W10", f"no independent admission at {ver_path!r}")
    ver = _read_json(ver_path, "MISSING_W10")
    # The independent admission arrives in one of two shapes, and BOTH are accepted: the Direct
    # lane's REAL external verification (schema spot.stage02_direct_arm_bundle_verification.v1 —
    # verdict "ADMIT", a verifier_id, independent_of_generator, n_failed 0, and NO admitted flag)
    # and the flag style (admitted=true). Either way the admission must be POSITIVE, INDEPENDENT
    # and clean of gate failures — never the producer's own pending/preflight placeholder, a
    # self-admission, or a REFUSE.
    verdict = str(ver.get("verdict") or "")
    admitted = verdict.upper() == "ADMIT" or ver.get("admitted") is True
    independent = (bool(ver.get("verifier_id")) and ver.get("self_admitted") is not True
                   and ver.get("independent_of_generator") is not False
                   and ver.get("is_an_external_admission") is not False)
    clean = (ver.get("n_failed") in (0, None)) and not ver.get("failed_gates")
    refused = verdict == PENDING_VERDICT or verdict.upper() in ("REFUSE", "REJECT")
    if refused or not (admitted and independent and clean):
        raise DirectSourceError(
            "MISSING_W10", f"the Direct bundle at {ver_path!r} is not independently admitted "
            f"(verdict={verdict!r}, verifier_id={ver.get('verifier_id')!r}, "
            f"n_failed={ver.get('n_failed')!r}, self_admitted={ver.get('self_admitted')!r}) — a "
            "temporal run may not stand on a Direct endpoint no independent lane admitted")

    rows = _read_rows(os.path.join(bundle_dir, ROWS_FILE))
    return {
        "bundle_id": doc.get("arm_bundle_run_id"),
        "condition": str(condition),
        "raw_sha256": raw_sha,
        "arm_rows_sha256": rb.get("arm_rows_sha256") or doc.get("arm_rows_sha256"),
        "scorer_view_sha256": rb.get("scorer_view_sha256"),
        "gene_universe_sha256": rb.get("gene_universe_sha256"),
        "env_lock_sha256": env_sha,
        "w10_verdict": verdict,
        "w10_report_sha256": file_sha256(ver_path),
        "base": _base_by_target(rows),
    }


def _base_by_target(rows: list[dict[str, Any]]) -> dict[str, dict[str, dict[str, Any]]]:
    """Dedupe the increase/decrease rows to ONE base delta per (program, target).

    The two arms are exact sign transforms of one base delta; here they must AGREE — the
    base_delta identical and the values exact negations — or the pair is refused.
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
                "missing one of the increase/decrease rows")
        # a null base_delta round-trips through parquet as NaN; normalise before comparing,
        # or NaN != NaN would refuse an honestly-null base delta.
        ibd, dbd = _nan_to_none(inc.get("base_delta")), _nan_to_none(dec.get("base_delta"))
        if ibd != dbd:
            raise DirectSourceError(
                "DUPLICATE_MISMATCH", f"{program_id}|{target_id}: increase.base_delta "
                f"{ibd!r} != decrease.base_delta {dbd!r}")
        iv, dv = _nan_to_none(inc.get("value")), _nan_to_none(dec.get("value"))
        if (iv is None) != (dv is None) or (
                iv is not None and abs(float(iv) + float(dv)) > _VALUE_EPS):
            raise DirectSourceError(
                "DUPLICATE_MISMATCH", f"{program_id}|{target_id}: increase.value {iv!r} and "
                f"decrease.value {dv!r} are not exact negations")
        # survivor COUNTS round-trip through parquet as floats and are NaN on the same rows a
        # null base_delta has (an unavailable projection). Normalise NaN -> None and restore the
        # integer form, or a NaN count reaches the content hash and JSON refuses it.
        base.setdefault(target_id, {})[program_id] = {
            "delta": ibd,
            "status": inc.get("projection_status"),
            "n_panel_surviving": _int_or_none(inc.get("n_panel_surviving")),
            "n_control_surviving": _int_or_none(inc.get("n_control_surviving")),
            "base_state": inc.get("base_state"),
            "base_passed": inc.get("base_passed"),
        }
    return base


def endpoints(direct: dict[str, Any],
              admitted: dict[str, dict[str, Any]]) -> list[ab.TargetEndpoint]:
    """One ``TargetEndpoint`` per target, its ``program_delta`` the Direct base deltas."""
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
        any_row = next(iter(by_program.values()))
        out.append(ab.TargetEndpoint(
            target_id=target_id, program_delta=program_delta,
            base_qc_passed=bool(any_row["base_passed"]),
            base_qc_state=str(any_row["base_state"])))
    return out


def source_binding(from_direct: dict[str, Any], to_direct: dict[str, Any]) -> dict[str, Any]:
    """WHICH two admitted Direct bundles (+ W10 admissions, scorer/universe/table hashes and
    the shared solver lock) this endpoint pair stood on. Bound into the temporal identity."""
    return {
        "endpoint_source": "two_admitted_direct_all_arm_bundles",
        "env_lock_sha256": from_direct["env_lock_sha256"],
        "from_direct_bundle_id": from_direct["bundle_id"],
        "from_direct_bundle_sha256": from_direct["raw_sha256"],
        "from_arm_rows_sha256": from_direct["arm_rows_sha256"],
        "from_scorer_view_sha256": from_direct["scorer_view_sha256"],
        "from_gene_universe_sha256": from_direct["gene_universe_sha256"],
        "from_w10_report_sha256": from_direct["w10_report_sha256"],
        "to_direct_bundle_id": to_direct["bundle_id"],
        "to_direct_bundle_sha256": to_direct["raw_sha256"],
        "to_arm_rows_sha256": to_direct["arm_rows_sha256"],
        "to_scorer_view_sha256": to_direct["scorer_view_sha256"],
        "to_gene_universe_sha256": to_direct["gene_universe_sha256"],
        "to_w10_report_sha256": to_direct["w10_report_sha256"],
    }
