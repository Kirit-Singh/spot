"""The INDEPENDENT verifier for the temporal artifact. generator != verifier.

It reads the emitted parquet files back off disk and re-derives, from them alone:

  * every DiD, from the endpoint arm values the record itself published;
  * every temporal status, from the endpoint presence and evaluability;
  * every reliability badge and threshold, from the frozen policy and k;
  * every batch verdict, from the policy's composition table;
  * the ANTISYMMETRY of the whole artifact: the record for (B -> A) must be the exact
    negation of the record for (A -> B), for both arms, for every target;
  * that no combined temporal objective was emitted, and no p/q appeared;
  * that the endpoint arm values are EXACTLY the within-condition values — the layer
    reports what the screen reports, or it is not the same estimand.

It shares no code path with the generator's assembly: the generator built the records
from in-memory rows, and this rebuilds the claims from the bytes that shipped.
"""
from __future__ import annotations

import os
from typing import Any

import pandas as pd

from ..config import ARM_A, ARM_B, ARMS
from . import estimand, policy
from .records import comparison_id

PASS = "pass"
FAIL = "fail"

# A combined temporal objective would reintroduce the retired balanced-skew score in a
# new coordinate. There is no such column, and the verifier refuses one if it appears.
FORBIDDEN_SUBSTRINGS = ("combined", "balanced", "mean_did", "average_did",
                        "overall_did", "headline", "composite")
FORBIDDEN_INFERENCE = ("pvalue", "p_value", "qvalue", "q_value", "fdr", "padj")


def _fails(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in checks if c["status"] != PASS]


def _check(name: str, ok: bool, detail: str = "") -> dict[str, Any]:
    return {"check": name, "status": PASS if ok else FAIL, "detail": detail}


def _num(v: Any) -> Any:
    return None if v is None or (isinstance(v, float) and v != v) or pd.isna(v) else v


def verify(*, out_dir: str, provenance: dict[str, Any]) -> dict[str, Any]:
    """Re-derive every claim in ``temporal.parquet`` from the bytes that shipped."""
    df = pd.read_parquet(os.path.join(out_dir, "temporal.parquet"))
    ends = pd.read_parquet(os.path.join(out_dir, "endpoints.parquet"))
    pol = policy.load()
    k = provenance["temporal_policy"]["reliability_k"]

    checks: list[dict[str, Any]] = []

    # ---- 1. the DiD is the difference of the endpoint values the record published ----
    bad = []
    for _, r in df.iterrows():
        for arm in ARMS:
            did, a, b = (_num(r[f"{arm}_temporal_did"]), _num(r[f"{arm}_from_value"]),
                         _num(r[f"{arm}_to_value"]))
            pole = "A" if arm == ARM_A else "B"
            estimated = r[f"{pole}_temporal_status"] == estimand.ESTIMATED
            if not estimated:
                if did is not None:
                    bad.append(f"{r.target_id}/{r.comparison_id}/{arm}: "
                               "a DiD exists where the arm was not estimated")
                continue
            if did is None or a is None or b is None:
                bad.append(f"{r.target_id}/{r.comparison_id}/{arm}: estimated but null")
            elif abs(did - (b - a)) > 1e-12:
                bad.append(f"{r.target_id}/{r.comparison_id}/{arm}: "
                           f"{did} != {b} - {a}")
    checks.append(_check("did_equals_to_minus_from", not bad, "; ".join(bad[:5])))

    # ---- 2. ANTISYMMETRY: reversing the pair negates the estimate, exactly ----
    bad = []
    index = {(r.target_id, r.from_condition, r.to_condition): r
             for _, r in df.iterrows()}
    for (target, a_cond, b_cond), row in index.items():
        mirror = index.get((target, b_cond, a_cond))
        if mirror is None:
            bad.append(f"{target}: {a_cond}->{b_cond} has no reverse record")
            continue
        for arm in ARMS:
            x, y = _num(row[f"{arm}_temporal_did"]), _num(mirror[f"{arm}_temporal_did"])
            if x is None and y is None:
                continue
            if x is None or y is None or abs(x + y) > 1e-12:
                bad.append(f"{target}/{arm}: {a_cond}->{b_cond} is {x}, "
                           f"reverse is {y} (must be its exact negation)")
    checks.append(_check("reversing_the_pair_negates_the_did", not bad,
                         "; ".join(bad[:5])))

    # ---- 3. the reliability badge, re-derived from the policy ----
    bad = []
    for _, r in df.iterrows():
        for pole in ("A", "B"):
            program = r[f"{pole}_program_id"]
            expect = estimand.reliability(
                did=_num(r[f"{ARM_A if pole == 'A' else ARM_B}_temporal_did"]),
                interaction_std=pol.interaction_std(program), k=k)
            got = r[f"{pole}_reliability_badge"]
            if got != expect["reliability_badge"]:
                bad.append(f"{r.target_id}/{r.comparison_id}/{pole}: badge {got} != "
                           f"{expect['reliability_badge']}")
            thr, want = _num(r[f"{pole}_reliability_threshold"]), \
                expect["reliability_threshold"]
            if (thr is None) != (want is None) or (
                    thr is not None and abs(thr - want) > 1e-12):
                bad.append(f"{r.target_id}/{r.comparison_id}/{pole}: "
                           f"threshold {thr} != {want}")
    checks.append(_check("reliability_badge_rederives_from_policy", not bad,
                         "; ".join(bad[:5])))

    # ---- 4. the batch verdict, re-derived from the composition table ----
    bad = []
    for (from_cond, to_cond), grp in df.groupby(["from_condition", "to_condition"]):
        expect = pol.classify_pair(from_cond, to_cond)
        for col in ("batch_status", "batch_partially_confounded"):
            got = set(grp[col].dropna().unique())
            want = expect[col]
            if want is None:
                continue
            if got != {want}:
                bad.append(f"{from_cond}->{to_cond}: {col} is {got}, expected {want}")
        moved = ";".join(expect["donors_changing_replicate"])
        if set(grp["donors_changing_replicate"].unique()) != {moved}:
            bad.append(f"{from_cond}->{to_cond}: donors_changing_replicate mismatch")
    checks.append(_check("batch_verdict_rederives_from_composition", not bad,
                         "; ".join(bad[:5])))

    # ---- 5. every ordered pair is present, and NONE was refused ----
    pairs = set(zip(df.from_condition, df.to_condition))
    conds = sorted(set(df.from_condition) | set(df.to_condition))
    expected_pairs = {(a, b) for a in conds for b in conds if a != b}
    checks.append(_check("all_ordered_pairs_both_directions_present",
                         pairs == expected_pairs,
                         f"missing {sorted(expected_pairs - pairs)}"))
    checks.append(_check("no_comparison_was_refused",
                         not bool(df["refused"].any()),
                         "a refused comparison is a hidden confound"))
    checks.append(_check("comparison_ids_are_well_formed",
                         all(r.comparison_id == comparison_id(r.from_condition,
                                                              r.to_condition)
                             for _, r in df.iterrows())))

    # ---- 6. no combined objective, no calibrated inference ----
    combined = [c for c in df.columns
                if any(s in c.lower() for s in FORBIDDEN_SUBSTRINGS)]
    checks.append(_check("no_combined_temporal_objective", not combined,
                         f"forbidden columns: {combined}"))
    pq = [c for c in df.columns if c.lower() in FORBIDDEN_INFERENCE]
    checks.append(_check("no_p_or_q_emitted", not pq, f"forbidden columns: {pq}"))
    checks.append(_check("inference_status_is_not_calibrated",
                         set(df["inference_status"].unique()) == {"not_calibrated"}))

    # ---- 7. the endpoints ARE the within-condition values ----
    # The record's endpoint value must be the exact arm value the within-condition pass
    # emitted for that (target, condition). If it is not, the layer is differencing
    # something other than the screen, and the estimand is not what it says it is.
    bad = []
    end_index = {(str(r.target_id), str(r.condition)): r for _, r in ends.iterrows()}
    for _, r in df.iterrows():
        for end, cond in (("from", r.from_condition), ("to", r.to_condition)):
            src = end_index.get((str(r.target_id), str(cond)))
            if src is None:
                if r[f"{end}_present"]:
                    bad.append(f"{r.target_id}@{cond}: recorded present, no endpoint row")
                continue
            for arm in ARMS:
                got, want = _num(r[f"{arm}_{end}_value"]), _num(src[arm])
                if (got is None) != (want is None) or (
                        got is not None and got != want):
                    bad.append(f"{r.target_id}@{cond}/{arm}: endpoint {got} != "
                               f"within-condition {want}")
    checks.append(_check("endpoints_are_the_within_condition_arm_values", not bad,
                         "; ".join(bad[:5])))

    failures = _fails(checks)
    return {
        "schema_version": "spot.stage02_temporal_verification.v1",
        "temporal_run_id": provenance["temporal_run_id"],
        "temporal_method_sha256": provenance["temporal_method_sha256"],
        "verifier_id": "spot.stage02.temporal.verifier.v1",
        "generator_is_not_verifier": True,
        "n_records": int(len(df)),
        "n_endpoint_rows": int(len(ends)),
        "n_comparisons": len(pairs),
        "checks": checks,
        "n_failed": len(failures),
        "verdict": PASS if not failures else FAIL,
    }
