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
from typing import Any, Optional

import pandas as pd

from ..config import ARM_A, ARM_B, ARMS
from ..hashing import content_hash, file_sha256
from . import admission, estimand, policy
from .records import comparison_id

# The verdict is an ADMISSION decision, and it fails CLOSED: anything this verifier does
# not positively recognise is refused. "pass"/"fail" were the wrong words for it — they
# read like a test result, and a test that does not know about a defect simply passes.
ADMIT = "admit"
REJECT = "reject"
PASS = "pass"       # a single check's outcome (not the artifact's verdict)
FAIL = "fail"


def _fails(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in checks if c["status"] != PASS]


def _check(name: str, ok: bool, detail: str = "") -> dict[str, Any]:
    return {"check": name, "status": PASS if ok else FAIL, "detail": detail}


def _num(v: Any) -> Any:
    return None if v is None or (isinstance(v, float) and v != v) or pd.isna(v) else v


def _artifact_identity(out_dir: str) -> dict[str, Any]:
    """Bind the artifact: every required file, and the directory as a whole.

    A verifier that admits an artifact without naming the exact bytes it admitted has
    admitted nothing in particular — the file can be swapped afterwards and the report
    still reads as a clean bill of health.
    """
    files = {}
    for name in admission.REQUIRED_FILES:
        path = os.path.join(out_dir, name)
        files[name] = file_sha256(path) if os.path.exists(path) else None
    return {"files": files,
            "artifact_sha256": content_hash(files),
            "required_files": list(admission.REQUIRED_FILES)}


PROVENANCE_FILE = "temporal_provenance.json"


def verify(*, out_dir: str, provenance: Optional[dict[str, Any]] = None
           ) -> dict[str, Any]:
    """Re-derive every claim in the artifact from THE BYTES THAT SHIPPED.

    ``provenance`` is NOT the subject of verification. The shipped
    ``temporal_provenance.json`` is LOADED from disk here, and everything below — the
    firewall, the reliability re-derivation, the identity binding — runs on THAT. A
    caller-supplied dict is accepted only as a cross-check: if it differs from the
    shipped bytes, the artifact is REJECTED, because one of the two is a lie and the
    verifier does not get to pick the flattering one.

    (The previous version firewalled the caller's dict while merely HASHING the file.
    An independent audit poisoned the emitted provenance on disk with
    ``empirical_q_value``, handed the verifier the pristine in-memory dict, and got
    ADMIT — with the sha256 of the file it never opened printed in its own report.)

    FAIL-CLOSED. Absent file, unparseable file, caller mismatch, unknown column, or a
    forbidden key ANYWHERE at any depth → REJECT, before a single scientific claim is
    re-derived.
    """
    identity = _artifact_identity(out_dir)
    checks: list[dict[str, Any]] = []

    # ---- 0. THE ARTIFACT EXISTS, IN FULL. An absent file is a reject, not a skip. ----
    absent = [n for n, sha in identity["files"].items() if sha is None]
    checks.append(_check("every_required_file_is_present", not absent,
                         f"absent: {absent}"))
    if absent:
        return _report(provenance or {}, identity, checks, n_records=0,
                       n_endpoint_rows=0, n_comparisons=0)

    # ---- 0a. LOAD THE SHIPPED PROVENANCE. This, and not the caller's copy, is the
    # thing that gets verified. ----
    try:
        shipped = admission.load_shipped(out_dir, PROVENANCE_FILE)
    except admission.ShippedDocError as exc:
        checks.append(_check("shipped_provenance_loads_from_disk", False, str(exc)))
        return _report(provenance or {}, identity, checks, n_records=0,
                       n_endpoint_rows=0, n_comparisons=0)
    checks.append(_check("shipped_provenance_loads_from_disk", True))

    # the bytes we firewall ARE the bytes the report pins
    checks.append(_check(
        "the_provenance_we_verified_is_the_provenance_we_hashed",
        shipped["sha256"] == identity["files"][PROVENANCE_FILE],
        f"loaded {shipped['sha256'][:16]} != pinned "
        f"{str(identity['files'][PROVENANCE_FILE])[:16]}"))

    # a caller who hands us a DIFFERENT document than the one on disk is stale or lying
    checks.append(_check(
        "caller_provenance_matches_the_shipped_file",
        admission.caller_matches(shipped["doc"], provenance),
        "the caller's provenance dict differs from the shipped bytes; the shipped "
        "bytes are what is verified"))

    # FROM HERE ON, `provenance` means THE SHIPPED DOCUMENT.
    provenance = shipped["doc"]
    identity["provenance_canonical_sha256"] = shipped["canonical_sha256"]

    df = pd.read_parquet(os.path.join(out_dir, "temporal.parquet"))
    ends = pd.read_parquet(os.path.join(out_dir, "endpoints.parquet"))
    pol = policy.load()
    k = provenance["temporal_policy"]["reliability_k"]

    # ---- 0a. THE EXACT COLUMN ALLOWLIST. Unknown column -> REJECT (B4). ----
    for name, cols in (("temporal.parquet", list(df.columns)),
                       ("endpoints.parquet", list(ends.columns))):
        v = admission.column_violations(cols, name)
        checks.append(_check(
            ("temporal_columns_match_the_exact_allowlist"
             if name == "temporal.parquet"
             else "endpoint_columns_match_the_exact_allowlist"),
            not v["unknown"] and not v["missing"],
            f"{name}: unknown={v['unknown']} missing={v['missing']}"))

    # ---- 0b. THE RECURSIVE KEY FIREWALL, over EVERY SHIPPED object (B4). ----
    # Column names AND the LOADED provenance document, at any nesting depth. A p-value
    # buried three levels down in a diagnostics list is the shape a disguised one takes —
    # and it is now scanned in the bytes that actually shipped, not in the caller's copy.
    hits = (admission.forbidden_keys({c: None for c in df.columns})
            + admission.forbidden_keys({c: None for c in ends.columns})
            + admission.forbidden_keys(provenance))
    checks.append(_check("no_forbidden_key_at_any_depth", not hits,
                         f"forbidden keys: {sorted(set(hits))[:8]}"))

    # ---- 0c. THE IDENTITY BINDING: the records ARE this run's, by this method. ----
    run_ids = set(df["temporal_run_id"].unique())
    method_shas = set(df["temporal_method_sha256"].unique())
    bound = (run_ids == {provenance["temporal_run_id"]}
             and method_shas == {provenance["temporal_method_sha256"]})
    checks.append(_check(
        "records_are_bound_to_the_run_and_the_method", bound,
        f"run_ids={sorted(run_ids)} method_shas={sorted(method_shas)}"))

    # FAIL-CLOSED: the structural gates come FIRST and they are final. If the artifact is
    # not the shape the contract describes, it is refused here — re-deriving scientific
    # claims from a table whose columns we do not recognise would be re-deriving claims
    # from something else, and a crash midway would be an unhandled reject at best.
    if _fails(checks):
        return _report(provenance, identity, checks, n_records=len(df),
                       n_endpoint_rows=len(ends), n_comparisons=0)

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

    # ---- 2. ANTISYMMETRY: where BOTH directions were run, one negates the other ----
    # A v3 run emits exactly the ONE direction its contract asked for (B3), so the reverse
    # record legitimately does not exist. Its absence is checked against the DECLARED
    # SCOPE below (check 5), which is the stronger statement: the artifact must contain
    # exactly the comparisons its own binding says it ran — no more, no fewer.
    bad = []
    index = {(r.target_id, r.from_condition, r.to_condition): r
             for _, r in df.iterrows()}
    run_pairs = set(zip(df.from_condition, df.to_condition))
    for (target, a_cond, b_cond), row in index.items():
        if (b_cond, a_cond) not in run_pairs:
            continue                      # the reverse direction was never requested
        mirror = index.get((target, b_cond, a_cond))
        if mirror is None:
            # the reverse COMPARISON ran, but this target's reverse RECORD is missing
            bad.append(f"{target}: {a_cond}->{b_cond} has no reverse record, though "
                       f"{b_cond}->{a_cond} was run")
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

    # ---- 5. THE ARTIFACT CONTAINS EXACTLY THE COMPARISONS IT SAYS IT RAN ----
    # Stronger than "all ordered pairs present", and it is what B3 actually needs: an
    # artifact must answer the question its own binding says it was asked, and no other.
    # A run that silently emitted the reverse direction — or dropped a requested one —
    # fails here whether it was a v3 single-direction run or a full 6-pair sweep.
    binding = provenance["run_binding"]
    pairs = set(zip(df.from_condition, df.to_condition))
    declared = {tuple(c["comparison_id"].split("__to__"))
                for c in provenance["comparisons"]}
    checks.append(_check(
        "the_emitted_comparisons_are_exactly_the_declared_ones", pairs == declared,
        f"emitted-not-declared {sorted(pairs - declared)}; "
        f"declared-not-emitted {sorted(declared - pairs)}"))

    # ---- 5b. B3: a v3 run answered the CONTRACT'S question, on the CONTRACT'S axes ----
    v3 = binding.get("stage1_v3")
    if v3 is not None:
        want_pair = (v3["from_condition"], v3["to_condition"])
        checks.append(_check(
            "a_v3_run_emits_only_the_contracts_requested_direction",
            pairs == {want_pair},
            f"the contract asked for {want_pair}; the artifact emitted {sorted(pairs)}"))
        want_a, want_b = (v3["poles"]["A"]["program_id"],
                          v3["poles"]["B"]["program_id"])
        got_a = set(df["A_program_id"].unique())
        got_b = set(df["B_program_id"].unique())
        checks.append(_check(
            "a_v3_run_is_scored_on_the_contracts_own_poles",
            got_a == {want_a} and got_b == {want_b},
            f"the contract named A={want_a} B={want_b}; the artifact was scored on "
            f"A={sorted(got_a)} B={sorted(got_b)}"))
        checks.append(_check(
            "the_v3_full_contract_hash_is_bound",
            len(str(v3.get("full_contract_content_sha256", ""))) == 64,
            "a v3 run that does not bind the contract it executed can be pointed at "
            "another contract afterwards"))
        checks.append(_check(
            "the_v3_analysis_mode_is_temporal",
            v3["analysis_mode"] == "temporal_cross_condition"
            and binding["analysis_mode"] == "temporal_cross_condition"))

    checks.append(_check("no_comparison_was_refused",
                         not bool(df["refused"].any()),
                         "a refused comparison is a hidden confound"))
    checks.append(_check("comparison_ids_are_well_formed",
                         all(r.comparison_id == comparison_id(r.from_condition,
                                                              r.to_condition)
                             for _, r in df.iterrows())))

    # ---- 6. no calibrated inference ----
    # (the no-p/q and no-combined-objective refusals are the allowlist + firewall above,
    # at checks 0a/0b: they run BEFORE any claim is re-derived, and they fail closed.)
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

    return _report(provenance, identity, checks, n_records=len(df),
                   n_endpoint_rows=len(ends), n_comparisons=len(pairs))


def _report(provenance: dict[str, Any], identity: dict[str, Any],
            checks: list[dict[str, Any]], *, n_records: int, n_endpoint_rows: int,
            n_comparisons: int) -> dict[str, Any]:
    """The admission decision. ANY failed check refuses the artifact — fail-closed."""
    failures = _fails(checks)
    return {
        "schema_version": "spot.stage02_temporal_verification.v2",
        "temporal_run_id": provenance["temporal_run_id"],
        "temporal_method_sha256": provenance["temporal_method_sha256"],
        # v2: the verifier fails CLOSED — exact column allowlist + a recursive key-name
        # firewall at any depth + a bound artifact identity (B4).
        "verifier_id": "spot.stage02.temporal.verifier.v2",
        "generator_is_not_verifier": True,
        "fail_closed": True,
        "admission_policy": {
            "exact_column_allowlist": True,
            "unknown_column_is_a_reject": True,
            "forbidden_key_pattern": admission.FORBIDDEN_KEY_PATTERN,
            "key_firewall_is_recursive": True,
            "key_firewall_exceptions": sorted(admission.KEY_FIREWALL_EXCEPTIONS),
        },
        "artifact_identity": identity,
        "n_records": int(n_records),
        "n_endpoint_rows": int(n_endpoint_rows),
        "n_comparisons": int(n_comparisons),
        "checks": checks,
        "n_failed": len(failures),
        "verdict": ADMIT if not failures else REJECT,
    }
