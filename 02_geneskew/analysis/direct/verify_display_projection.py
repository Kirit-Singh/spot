"""THE INDEPENDENT CHECK ON THE DISPLAY PROJECTION. It reopens the native bytes and rebuilds it.

A served view is the only artifact most readers will ever look at. If it can be wrong while
looking right, then everything upstream — the admissions, the reconstructions, the hashes —
protected bytes nobody reads and left the page unguarded.

So this does not ask whether the projection agrees with itself. It reopens the ADMITTED NATIVE
ARTIFACTS, rebuilds each arm's prefix under the frozen cap policy, and proves:

  * the row emitted at rank r IS THE NATIVE ROW AT RANK r — same target, same effect, verbatim.
    Not a plausible row at a plausible position.
  * the prefix is the FIRST N in NATIVE RANK ORDER — not a reordering, not a sample, and not
    the top N by some quantity re-derived here.
  * every emitted target was EVALUABLE and RANKED. A target the arm could not score is not
    ranked, is not emitted, and is COUNTED.
  * the counts describe the WHOLE arm, so a prefix cannot read as the answer.
  * the cap is the FROZEN one. A raised cap is a different method, and a projection that
    silently served more (or fewer) rows than its own policy is not the view it claims to be.
  * NO CROSS-ARM ORDER exists anywhere in the document.

It restates the cap policy rather than importing it: a verifier that reads the producer's cap
agrees with it by construction and could never catch it moving.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any

# the verifier's own modules load FLAT — never through the producer's package
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# RE-STATED, NOT IMPORTED. A drift between these and the producer's is the finding.
CAP_OF = {"direct": 100, "temporal": 100, "pathway": 50}
CAP_POLICY_ID = "spot.stage02.display_projection.first_n_native_order.v1"
METHOD_VERSION = "spot.stage02.display_projection.v2"
SCHEMA = "spot.stage02_display_projection.v2"

# The frozen crosswalk's identity, RESTATED — not imported from the producer.
CROSSWALK_ID = "spot.stage01.effect_universe_gwcd4i.symbol_to_ensembl.v1"
CROSSWALK_SOURCE_FIELD = "symbol_to_ensembl"
SYMBOL_NAMESPACE = "hgnc_symbol"

G_SELF_HASH = "the_projection_hashes_to_what_it_says_it_does"
G_CAP = "the_cap_is_the_frozen_method_versioned_one"
G_SOURCE_BYTES = "the_native_bytes_it_was_read_from_are_unchanged"
G_PREFIX = "the_emitted_rows_are_the_FIRST_N_in_NATIVE_RANK_ORDER"
G_ROW_IS_NATIVE = "the_row_emitted_at_rank_r_IS_the_native_row_at_rank_r"
G_COUNTS = "the_counts_describe_the_WHOLE_arm_not_the_prefix"
G_UNRANKED_EMITTED = "an_unevaluable_or_unranked_target_was_served_as_evidence"
G_CROSS_ARM = "no_combined_pair_or_cross_arm_ordering_is_emitted"
G_SELECTION = "the_projection_is_selection_independent"

FORBIDDEN_ANYWHERE = ("combined_score", "balanced_score", "pair_rank", "headline_rank",
                      "overall_rank", "p_value", "q_value", "pval", "qval", "padj", "fdr",
                      "significance", "std_error", "stderr", "se", "ci_low", "ci_high",
                      "analysis_mode_result")

# EXACTLY what a served target row may carry. A symbol is DISPLAY METADATA; a standard error
# would be a new statistic, and a plot that showed one would be asserting a precision nobody
# computed.
TARGET_ROW_ALLOWED = frozenset({"target_id", "target_symbol", "rank", "value", "arm_value",
                                "pareto_tier", "joint_status", "joint_ordering_method_id"})
G_UNKNOWN_ROW_FIELD = "a_served_row_carries_a_field_the_display_contract_does_not_have"


def _raw(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def _canon(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=True).encode()).hexdigest()


def _num(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "item"):
        try:
            value = value.item()
        except (AttributeError, ValueError):
            return value
    if isinstance(value, float) and value != value:
        return None
    return value


def _native_target_rows(bundles_root: str, rel: str, lane: str) -> dict[str, list]:
    """Every native row, per arm, for a TARGET-evidence lane."""
    base = os.path.join(bundles_root, rel)
    out: dict[str, list] = {}
    if lane == "direct":
        import pandas as pd
        path = os.path.join(base, "arms.parquet")
        if not os.path.exists(path):
            return out
        for rec in pd.read_parquet(path).to_dict("records"):
            out.setdefault(str(rec["arm_key"]), []).append(
                {"target_id": str(rec["target_id"]), "rank": _num(rec.get("rank")),
                 "arm_value": _num(rec.get("value")),
                 "evaluable": bool(rec.get("evaluable"))})
        return out

    rdir = os.path.join(base, "rankings")
    for fname in sorted(os.listdir(rdir)) if os.path.isdir(rdir) else []:
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(rdir, fname)) as fh:
            doc = json.load(fh)
        arm_key = str(doc.get("arm_key") or "")
        recs = doc.get("records") if doc.get("records") is not None else (doc.get("ranked") or [])
        out.setdefault(arm_key, []).extend(
            {"target_id": str(r.get("target_id")), "rank": _num(r.get("rank")),
             "arm_value": _num(r.get("arm_value")),
             "evaluable": bool(r.get("evaluable"))} for r in recs)
    return out


def _native_pathway_records(bundles_root: str, rel: str) -> dict[str, list]:
    path = os.path.join(bundles_root, rel, "arm_bundle.json")
    if not os.path.exists(path):
        return {}
    with open(path) as fh:
        doc = json.load(fh)
    out: dict[str, list] = {}
    for rec in (doc.get("records") or []):
        out.setdefault(str(rec.get("pathway_arm_key")), []).append(rec)
    return out


def verify(projection_path: str, *, bundles_root: str) -> dict[str, Any]:
    """Rebuild the view from the native bytes and refuse anything that differs."""
    failures: list[str] = []
    with open(projection_path) as fh:
        doc = json.load(fh)

    if doc.get("schema_version") != SCHEMA:
        failures.append(f"{G_SELF_HASH}: schema {doc.get('schema_version')!r}")
    claimed = doc.get("projection_sha256")
    derived = _canon({k: v for k, v in doc.items() if k != "projection_sha256"})
    if claimed != derived:
        failures.append(f"{G_SELF_HASH}: says {str(claimed)[:16]}; hashes to {derived[:16]}")

    # (1) THE FROZEN CAP. A raised cap is a different method — and a UI must never be able to
    # reach it. `chosen_before_inspecting_any_value` is not decoration: a cap picked after
    # looking at the numbers is a result, not a policy.
    policy = doc.get("cap_policy") or {}
    if policy.get("cap_policy_id") != CAP_POLICY_ID:
        failures.append(f"{G_CAP}: cap_policy_id {policy.get('cap_policy_id')!r}")
    if doc.get("method_version") != METHOD_VERSION:
        failures.append(f"{G_CAP}: method_version {doc.get('method_version')!r}")
    if policy.get("caps") != CAP_OF:
        failures.append(f"{G_CAP}: caps {policy.get('caps')!r} are not the frozen "
                        f"{CAP_OF!r}. A projection that served a different number of rows "
                        "than its own policy is not the view it claims to be")
    if policy.get("configurable_from_the_ui") is not False:
        failures.append(f"{G_CAP}: the cap is marked UI-configurable. A UI that could raise "
                        "the cap could change what a reader believes the evidence is")

    # (2) SELECTION-INDEPENDENT. No selection, no analysis_mode, no pair.
    if doc.get("selection_independent") is not True or doc.get("selection_id") is not None:
        failures.append(f"{G_SELECTION}: this view carries a selection. The display projection "
                        "is the same view whatever question is later asked of the release")
    if doc.get("analysis_mode") is not None:
        failures.append(f"{G_SELECTION}: analysis_mode belongs to a per-selection projection, "
                        "not to the all-arm view")

    # (3) NO CROSS-ARM ORDER, anywhere in the served bytes.
    blob = json.dumps(doc).lower()
    for banned in FORBIDDEN_ANYWHERE:
        if f'"{banned}"' in blob:
            failures.append(f"{G_CROSS_ARM}: the served view carries {banned!r}")

    # (4) THE BYTES IT WAS READ FROM.
    sources = (doc.get("bindings") or {}).get("native_bundles") or {}
    for rel, bound in sources.items():
        for name, entry in (bound.get("files") or {}).items():
            p = os.path.join(bundles_root, rel, name)
            if not os.path.exists(p):
                failures.append(f"{G_SOURCE_BYTES}: {rel}/{name} is bound but absent")
            elif _raw(p) != entry.get("raw_sha256"):
                failures.append(f"{G_SOURCE_BYTES}: {rel}/{name} changed after the view was "
                                "built")

    # (4b) THE SYMBOLS. Reopen the BOUND crosswalk and prove every one of them.
    inverse, cw_failures = _crosswalk(doc, bundles_root)
    failures += cw_failures

    # (5) THE RECONSTRUCTION — the whole point.
    native_targets: dict[str, list] = {}
    native_pathway: dict[str, list] = {}
    for rel, bound in sources.items():
        lane = str(bound.get("lane"))
        if lane == "pathway":
            native_pathway.update(_native_pathway_records(bundles_root, rel))
        else:
            native_targets.update(_native_target_rows(bundles_root, rel, lane))

    for arm_key, view in (doc.get("arms") or {}).items():
        lane = str(view.get("lane"))
        if lane == "pathway":
            failures += _check_pathway(arm_key, view, native_pathway.get(arm_key))
        else:
            failures += _check_target(arm_key, view, native_targets.get(arm_key), lane)
            failures += _check_symbols(arm_key, view, inverse)

    # ---- THE SUBJECT. A receipt that does not name WHICH projection it judged is a receipt
    # for any projection with the same shape.
    #
    # THE DEFECT: this receipt carried a verifier id, some booleans, n_arms, failures and a
    # verdict — and NOTHING that identified the bytes. So a UI could take an ALTERED projection
    # (one arm_value 1.6758342617 -> 125.1318342617, declared projection_sha256 left alone) and
    # pair it with the ORIGINAL receipt, and both parsed: the only thing tying them together was
    # n_arms, which the mutation does not change. A verdict about bytes nobody named is not a
    # verdict about these bytes.
    with open(projection_path, "rb") as fh:
        raw_bytes = fh.read()
    subject = {
        "projection_file": os.path.basename(projection_path),
        # RECOMPUTED from the file on disk — not copied from the document's own claim
        "projection_raw_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "projection_canonical_sha256": _canon(doc),
        "projection_self_sha256_declared": doc.get("projection_sha256"),
        "projection_self_sha256_recomputed": derived,
        "self_hash_agrees": claimed == derived,
    }

    # ---- THE ADMITTED INPUTS. `rebuilt_from_admitted_native_bytes` was a hard-coded TRUE:
    # it meant "a directory was found", not "an admission was validated". It is now the RESULT
    # of loading each lane's external admission and its bound inventory.
    admitted_inputs, admission_failures = _admitted_inputs(doc, bundles_root)
    failures += admission_failures

    return {
        "verifier_id": "spot.stage02.display_projection.independent_verifier.v1",
        "generator_is_not_verifier": True,
        # ONLY after the lane admissions were loaded AND validated.
        "rebuilt_from_admitted_native_bytes": bool(admitted_inputs) and not admission_failures,
        "subject": subject,
        "admitted_inputs": admitted_inputs,
        "n_arms": len(doc.get("arms") or {}),
        "n_failed": len(failures),
        "failures": failures[:50],
        "verdict": "admit" if not failures else "reject",
    }


G_SUBJECT = "the_receipt_does_not_name_the_exact_projection_it_judged"
G_CROSSWALK = "the_symbol_crosswalk_is_not_bound_or_is_not_the_bytes_it_says_it_is"
G_SYMBOL = "an_emitted_target_symbol_is_not_the_one_the_frozen_crosswalk_gives_that_target"
G_AMBIGUOUS = "a_symbol_was_emitted_for_a_target_whose_inversion_is_ambiguous"
G_ADMITTED_INPUTS = "the_lane_admissions_behind_this_view_were_not_loaded_and_validated"


def _admitted_inputs(doc: dict, bundles_root: str) -> tuple:
    """Load and VALIDATE each lane's external admission. Finding a directory is not admission.

    `rebuilt_from_admitted_native_bytes` used to be a literal `True`. It said a root existed.
    It is now the result of actually opening each lane's admission and its bound inventory,
    through the verifier's OWN restatement of the contract.
    """
    import verify_admission_rules as AR

    sources = (doc.get("bindings") or {}).get("native_bundles") or {}
    out: dict[str, Any] = {}
    bad: list[str] = []

    # ---- DIRECT: W10 admits ONE BUNDLE AT A TIME, so EVERY Direct bundle this view read must
    # carry its own admission. Skipping past Direct — as this did — meant a MIXED Direct +
    # temporal projection could claim `rebuilt_from_admitted_native_bytes` on the strength of
    # the TEMPORAL admission alone, while its Direct rows rested on nothing.
    for rel, b in sorted(sources.items()):
        if str(b.get("lane")) != "direct":
            continue
        bd = os.path.join(bundles_root, rel)
        try:
            with open(os.path.join(bd, "arm_bundle.json")) as fh:
                bundle = json.load(fh)
            condition = str(bundle.get("condition"))
            arm_key = next((k for k, a in (doc.get("arms") or {}).items()
                            if a.get("source_bundle") == rel), None)
            if arm_key is None:
                raise AR.AdmissionError(
                    AR.G_ARM_NOT_VERIFIED,
                    f"[direct] {rel}: this view names no arm from that bundle")
            res = AR.check_direct(bundles_root, condition=condition, bundle_dir=bd,
                                  arm_key=arm_key, stage1={})
            out[f"direct:{condition}"] = {
                "admission_file": AR.W10_REPORT_FILE.format(condition=condition),
                "report_sha256": res["report_sha256"], "n_gates": res["n_gates"],
                "n_arms_verified": res["n_arms_verified"],
                "recompute_mode": res["recompute_mode"],
            }
        except (AR.AdmissionError, OSError, ValueError, KeyError) as exc:
            bad.append(f"{G_ADMITTED_INPUTS}: [direct] {rel}: {exc}")

    # ---- TEMPORAL / PATHWAY: the FULL external check, never a shallow one.
    lanes = {str(b.get("lane")) for b in sources.values()} & set(AR.EXTERNAL)
    for lane in sorted(lanes):
        rel = next(r for r, b in sorted(sources.items()) if str(b.get("lane")) == lane)
        try:
            res = AR.check_external(bundles_root, lane,
                                    bundle_dir=os.path.join(bundles_root, rel), stage1={})
            out[lane] = {"admission_file": AR.EXTERNAL[lane]["file"],
                         "report_id": res["report_id"], "n_gates": res["n_gates"],
                         "n_bundles": res["n_bundles"],
                         "bound_inventory": res["bound_inventory"],
                         "bound_inventory_sha256": res["bound_inventory_sha256"]}
        except (AR.AdmissionError, OSError, ValueError, KeyError) as exc:
            bad.append(f"{G_ADMITTED_INPUTS}: [{lane}] {exc}")

    if not out and not bad:
        bad.append(f"{G_ADMITTED_INPUTS}: this view names no admitted lane input at all. "
                   "Finding a directory is not an admission")
    return out, bad


def _crosswalk(doc: dict, bundles_root: str) -> tuple:
    """Reopen the BOUND crosswalk and rebuild the one-to-one inverse INDEPENDENTLY.

    The producer's inverse is not read: a verifier that trusted the producer's map would prove
    only that the producer agrees with itself. The forward map is reopened from the bound bytes
    and inverted here, and an AMBIGUOUS id is dropped here too — so a label the producer minted
    from a collision has nothing to match against.
    """
    b = (doc.get("bindings") or {}).get("symbol_crosswalk")
    if not b:
        # No crosswalk bound: then NO row may carry a symbol. Silence is not permission.
        bad = []
        for arm_key, view in (doc.get("arms") or {}).items():
            for r in (view.get("rows") or []):
                if r.get("target_symbol") is not None:
                    bad.append(f"{G_CROSSWALK}: {arm_key}: a symbol was emitted with NO "
                               "crosswalk bound. A label with no source is a label nobody "
                               "can check")
                    break
        return {}, bad

    bad = []
    if b.get("crosswalk_id") != CROSSWALK_ID:
        bad.append(f"{G_CROSSWALK}: crosswalk_id {b.get('crosswalk_id')!r}")
    if b.get("symbol_namespace") != SYMBOL_NAMESPACE:
        bad.append(f"{G_CROSSWALK}: symbol_namespace {b.get('symbol_namespace')!r}")

    path = _find_crosswalk(bundles_root, str(b.get("path")))
    if path is None:
        return {}, bad + [f"{G_CROSSWALK}: the bound crosswalk {b.get('path')!r} is not on "
                          "disk; its symbols cannot be proved"]
    if _raw(path) != b.get("raw_sha256"):
        return {}, bad + [
            f"{G_CROSSWALK}: the crosswalk on disk hashes to {_raw(path)[:16]}; the projection "
            f"bound {str(b.get('raw_sha256'))[:16]}. It was labelled from different bytes"]
    with open(path) as fh:
        body = json.load(fh)
    if _canon(body) != b.get("canonical_sha256"):
        bad.append(f"{G_CROSSWALK}: the crosswalk's canonical hash does not match")

    forward = body.get(CROSSWALK_SOURCE_FIELD) or {}
    seen: dict = {}
    for symbol, ensembl in forward.items():
        seen.setdefault(str(ensembl), []).append(str(symbol))
    inverse = {e: s[0] for e, s in seen.items() if len(s) == 1}
    n_ambig = sum(1 for s in seen.values() if len(s) > 1)

    if b.get("n_one_to_one") != len(inverse):
        bad.append(f"{G_CROSSWALK}: the projection claims {b.get('n_one_to_one')} one-to-one "
                   f"entries; the bound bytes give {len(inverse)}")
    if b.get("n_ambiguous_dropped") != n_ambig:
        bad.append(f"{G_AMBIGUOUS}: the projection claims {b.get('n_ambiguous_dropped')} "
                   f"ambiguous ids; the bound bytes have {n_ambig}")
    return inverse, bad


def _find_crosswalk(bundles_root: str, name: str) -> Any:
    """The bound crosswalk, by NAME — beside the release, or under it. Never an absolute path
    baked into the artifact: a binding that carried this host's layout would bind a machine."""
    for cand in (os.path.join(bundles_root, name),
                 os.path.join(bundles_root, "inputs", name)):
        if os.path.exists(cand):
            return cand
    for base, _dirs, files in os.walk(bundles_root):
        if name in files:
            return os.path.join(base, name)
    return None


def _check_symbols(arm_key: str, view: dict, inverse: dict) -> list:
    """EVERY emitted symbol IS the one the frozen crosswalk gives that target_id."""
    bad = []
    shown = 0
    for i, r in enumerate(view.get("rows") or []):
        tid = str(r.get("target_id"))
        got = r.get("target_symbol")
        want = inverse.get(tid)              # None when unmapped — an EXPLICIT null
        if got == want:
            continue
        if shown >= 3:
            bad.append(f"{G_SYMBOL}: {arm_key}: ...and further symbols differ (truncated)")
            break
        if got is not None and want is None:
            bad.append(
                f"{G_SYMBOL}: {arm_key}[{i}]: {tid} is not in the frozen crosswalk, yet it was "
                f"labelled {got!r}. An unmapped target is an EXPLICIT null — never a guess, and "
                "never its own id wearing a symbol's field")
        else:
            bad.append(f"{G_SYMBOL}: {arm_key}[{i}]: {tid} is labelled {got!r}; the frozen "
                       f"crosswalk gives {want!r}")
        shown += 1
    return bad


def _check_target(arm_key: str, view: dict, native: Any, lane: str) -> list:
    bad: list[str] = []
    if native is None:
        return [f"{G_ROW_IS_NATIVE}: {arm_key}: the native bytes contain no such arm"]

    evaluable = [r for r in native if r["evaluable"]]
    ranked = sorted((r for r in evaluable if r["rank"] is not None),
                    key=lambda r: int(r["rank"]))
    cap = CAP_OF[lane]
    want = ranked[:cap]

    # THE COUNTS DESCRIBE THE WHOLE ARM. A prefix that reads as the answer is the failure.
    for field, value in (("n_rows_total", len(native)), ("n_evaluable", len(evaluable)),
                         ("n_ranked", len(ranked)), ("n_emitted", len(want)),
                         ("cap", cap)):
        if view.get(field) != value:
            bad.append(f"{G_COUNTS}: {arm_key}: {field}={view.get(field)!r}; the native bytes "
                       f"say {value!r}")

    rows = view.get("rows") or []
    if len(rows) > cap:
        bad.append(f"{G_CAP}: {arm_key}: served {len(rows)} rows over a cap of {cap}")

    # THE STRUCTURAL GATES FIRST. A reordering makes EVERY row disagree, and a hundred
    # row-level messages would crowd the one that actually says what happened out of the
    # report. The most diagnostic failure must never be the one that gets truncated.
    served_ranks = [r.get("rank") for r in rows]
    if served_ranks != sorted(served_ranks):
        bad.append(f"{G_PREFIX}: {arm_key}: the served rows are not in native rank order")
    if served_ranks != [r["rank"] for r in want]:
        bad.append(f"{G_PREFIX}: {arm_key}: the served rows are not the FIRST {cap} in native "
                   "rank order — a reordering, a sample, or a different population")

    # ...and THEN: the row at rank r IS the native row at rank r. Verbatim, not plausible.
    # Bounded per arm, so one broken arm cannot hide every other arm's failures.
    n_row_failures = 0
    for i, (got, exp) in enumerate(zip(rows, want)):
        if n_row_failures >= 3:
            bad.append(f"{G_ROW_IS_NATIVE}: {arm_key}: ...and further rows differ "
                       "(truncated; the arm's structure is already refused above)")
            break
        if got.get("target_id") != exp["target_id"] or got.get("rank") != exp["rank"]:
            bad.append(
                f"{G_ROW_IS_NATIVE}: {arm_key}[{i}]: served "
                f"{got.get('target_id')!r} at rank {got.get('rank')!r}; the native row at "
                f"that position is {exp['target_id']!r} at rank {exp['rank']!r}")
            n_row_failures += 1
            continue
        if got.get("arm_value") != exp["arm_value"]:
            bad.append(f"{G_ROW_IS_NATIVE}: {arm_key}[{i}]: {exp['target_id']} served with "
                       f"value {got.get('arm_value')!r}; natively it is {exp['arm_value']!r}")
            n_row_failures += 1

    # NOTHING ON THE ROW THE CONTRACT DOES NOT HAVE.
    for i, r in enumerate(rows):
        extra = sorted(set(r) - TARGET_ROW_ALLOWED)
        if extra:
            bad.append(f"{G_UNKNOWN_ROW_FIELD}: {arm_key}[{i}]: carries {extra}")
            break

    # AN UNRANKED TARGET WAS NEVER SERVED AS EVIDENCE.
    by_id = {r["target_id"]: r for r in native}
    for r in rows:
        n = by_id.get(str(r.get("target_id")))
        if n is None or not n["evaluable"] or n["rank"] is None:
            bad.append(f"{G_UNRANKED_EMITTED}: {arm_key}: {r.get('target_id')!r} was served "
                       "but the arm could not score it. It is not a zero and it is not last")
    return bad


def _check_pathway(arm_key: str, view: dict, native: Any) -> list:
    bad: list[str] = []
    if native is None:
        return [f"{G_ROW_IS_NATIVE}: {arm_key}: the native bytes contain no such pathway arm"]

    cap = CAP_OF["pathway"]
    want = native[:cap]

    if view.get("rows_are_ranked") is not False:
        bad.append(f"{G_PREFIX}: {arm_key}: the pathway rows claim to be RANKED. The native "
                   "record carries no rank of gene sets against each other, so a ranking here "
                   "would have been derived by the projection itself")
    for field, value in (("n_sets_total", len(native)), ("n_emitted", len(want)),
                         ("cap", cap)):
        if view.get(field) != value:
            bad.append(f"{G_COUNTS}: {arm_key}: {field}={view.get(field)!r}; native {value!r}")

    # the disposition counts are over EVERY set, not merely the prefix
    counts: dict[str, int] = {}
    for rec in native:
        d = str(rec.get("global_coverage_disposition"))
        counts[d] = counts.get(d, 0) + 1
    if view.get("coverage_disposition_counts") != dict(sorted(counts.items())):
        bad.append(f"{G_COUNTS}: {arm_key}: the coverage/disposition counts are not the counts "
                   "over every set in this arm")

    for i, (got, exp) in enumerate(zip(view.get("rows") or [], want)):
        if got.get("set_id") != str(exp.get("set_id")) and got.get("set_id") != exp.get("set_id"):
            bad.append(f"{G_ROW_IS_NATIVE}: {arm_key}[{i}]: served set {got.get('set_id')!r}; "
                       f"the native record at that position is {exp.get('set_id')!r}")
            continue
        for field in ("enrichment_value", "target_source_coverage",
                      "global_coverage_disposition"):
            if got.get(field) != _num(exp.get(field)):
                bad.append(f"{G_ROW_IS_NATIVE}: {arm_key}[{i}]: {field}={got.get(field)!r}; "
                           f"natively {_num(exp.get(field))!r}")
    return bad


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(
        description="Reopen the ADMITTED native bytes and prove the served view is a faithful, "
                    "capped prefix of them. Trusts nothing the projection says about itself.")
    ap.add_argument("--projection", required=True)
    ap.add_argument("--bundles-root", required=True)
    ap.add_argument("--report", required=True)
    args = ap.parse_args(argv)

    report = verify(args.projection, bundles_root=args.bundles_root)
    with open(args.report, "w") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
    print(json.dumps({k: v for k, v in report.items() if k != "failures"}, indent=2))
    for f in report["failures"][:10]:
        print(f"  - {f}")
    return 0 if report["verdict"] == "admit" else 1


if __name__ == "__main__":
    raise SystemExit(main())
