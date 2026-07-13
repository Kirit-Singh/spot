"""THE ENDPOINTS ARE TWO ADMITTED DIRECT BUNDLES — reopened, rehashed, and RE-DIFFERENCED.

A temporal arm is a difference of two within-condition numbers. Where those two numbers came
from is the whole question: if they came from a fixture effect source, the temporal release
is a difference of two things nobody measured, and every gate downstream of it is checking
the arithmetic of an invention.

So each endpoint must be an ADMITTED DIRECT ALL-ARM BUNDLE, and this module proves it from
the bytes:

  * the bundle is a real Direct all-arm bundle (``spot.stage02_direct_arm_bundle.v1``) — the
    temporal FIXTURE effect source is refused BY NAME, because a fixture that can stand in
    for a measurement is a fixture that eventually will;
  * it is the condition the endpoint asked for — a swapped endpoint silently differences the
    wrong two populations, and every number that comes out looks entirely reasonable;
  * it is the exact bundle the temporal release BOUND — a stale bundle admits a run against
    numbers that were superseded;
  * an INDEPENDENT lane admitted it. W5 hashes the W10 report; it never reads it. So this
    lane opens it: the report must be W10's schema, signed with W10's id, and its verdict
    must actually say ADMIT. A report that is merely PRESENT admits nothing.

THE TWO DIRECT ARMS MUST AGREE ABOUT THE NUMBER THEY SHARE
----------------------------------------------------------
A Direct bundle carries an ``increase`` and a ``decrease`` row per (program, target). They
are exact sign transforms of ONE base delta, so they are deduplicated to one — and they must
agree: the same ``base_delta``, and values that are exact negations. A Direct bundle whose
two arms disagree about a magnitude they share is internally broken, and a temporal run built
on it would inherit the disagreement while looking perfectly consistent.

AND THEN THE DiD IS RECOMPUTED
------------------------------
    base_delta(temporal) == direct_base(to_condition) - direct_base(from_condition)

recomputed here, for every (program, target, ordered pair), from the ADMITTED DIRECT NUMBERS
— not from the temporal bundle's own account of its endpoints. That is the difference between
checking that a release is self-consistent and checking that it is true.
"""
from __future__ import annotations

import json
import os
from typing import Any, Optional

from .canonical import content_hash, file_sha256

DIRECT_BUNDLE_SCHEMA = "spot.stage02_direct_arm_bundle.v1"

# A Direct bundle is a DIRECTORY, not a file: the manifest, the rows, the provenance, and the
# producer's own placeholder verdict.
BUNDLE_FILE = "arm_bundle.json"
ROWS_FILE = "arms.parquet"
PROVENANCE_FILE = "provenance.json"
VERIFICATION_FILE = "verification.json"

# THE PRODUCER'S PLACEHOLDER SLOT. Not an admission, and it says so itself: it ships with a
# PENDING verdict under the SLOT schema, waiting for an independent lane to fill it.
PENDING_VERDICT = "pending_independent_verification"
VERIFICATION_SLOT_SCHEMA = "spot.stage02_arm_bundle_verification.v1"

# THE REAL W10 REPORT. Its own schema, its own id, and — the point — its own EVIDENCE.
#
# It carries no ``admitted`` boolean, and it does not need one: a boolean is a claim, and
# this report ships the thing the claim would have been about. It is self-hashed, it lists
# every gate it ran, it records that it did not import the generator, and its
# ``bound_artifact`` says WHICH bundle it is about — by condition, by rows hash, by solver
# lock, and by a map of every file's sha256. So the admission is checked against the bundle
# in hand rather than taken on the word of a flag that could be set by anyone.
W10_REPORT_SCHEMA = "spot.stage02_direct_arm_bundle_verification.v1"
W10_VERIFIER_ID = "spot.stage02.direct.arm_bundle.verifier.v1"
W10_ADMIT = "ADMIT"

AUTHORITATIVE_ENV_LOCK_SHA256 = (
    "2983d140941f13d223dad93bae71434663882f23f25f6717c3debe59d2711abe")

# The temporal lane's own fixture effect source. Named here for exactly one reason: so it can
# be refused by name if it is ever handed in where a measurement belongs.
FIXTURE_EFFECT_SCHEMA = "spot.stage02_temporal_arm_effect_source.v1"

# W10 — the INDEPENDENT verifier of the Direct release. Its report is opened and read here,
# not merely hashed.

ENDPOINT_SOURCE_REQUIRED = "two_admitted_direct_all_arm_bundles"

DESIRED_CHANGES = ("increase", "decrease")
SIGN = {"increase": 1, "decrease": -1}


def _json(path: str) -> dict[str, Any]:
    with open(path) as fh:
        return json.load(fh)


def _rows(bundle_dir: str) -> list[dict[str, Any]]:
    """The arm rows. A NaN round-tripped through parquet is a null, not a number."""
    import pandas as pd

    out = pd.read_parquet(os.path.join(bundle_dir, ROWS_FILE)).to_dict("records")
    for r in out:
        for k, v in list(r.items()):
            if isinstance(v, float) and v != v:
                r[k] = None
    return out


def load(f, condition: str, bundle_dir: Optional[str], w10_path: Optional[str], *,
         expect_bundle_sha256: Optional[str] = None,
         expect_w10_sha256: Optional[str] = None,
         expect_rows_sha256: Optional[str] = None) -> Optional[dict[str, Any]]:
    """ONE admitted Direct endpoint, proved from its four files."""
    where = f"direct:{condition}"
    if not f.check("a_direct_all_arm_bundle_was_supplied_for_every_condition",
                   bool(bundle_dir) and os.path.isdir(str(bundle_dir)), where,
                   f"no Direct all-arm bundle directory for condition {condition!r}. A "
                   "temporal endpoint IS a Direct bundle; there is nothing here to "
                   "difference"):
        return None

    bpath = os.path.join(str(bundle_dir), BUNDLE_FILE)
    for name in (BUNDLE_FILE, ROWS_FILE, PROVENANCE_FILE):
        if not f.check("the_direct_bundle_ships_every_file_it_is_made_of",
                       os.path.exists(os.path.join(str(bundle_dir), name)), where,
                       f"{name} is missing; a bundle short a file is not the bundle"):
            return None

    raw = file_sha256(bpath)
    doc = _json(bpath)
    schema = doc.get("schema_version")

    if not f.check("no_fixture_json_may_stand_in_for_a_direct_bundle",
                   schema != FIXTURE_EFFECT_SCHEMA, where,
                   "this is the temporal FIXTURE effect source, not a measurement. A "
                   "fixture that can stand in for a Direct bundle is a fixture that "
                   "eventually will, and the release would be a difference of two things "
                   "nobody measured"):
        return None
    if not f.check("the_endpoint_is_a_real_direct_all_arm_bundle",
                   schema == DIRECT_BUNDLE_SCHEMA, where,
                   f"schema {schema!r} is not {DIRECT_BUNDLE_SCHEMA!r}"):
        return None

    prov = _json(os.path.join(str(bundle_dir), PROVENANCE_FILE))
    rb = prov.get("run_binding") or {}

    got_cond = rb.get("condition") or doc.get("condition")
    if not f.check("the_direct_bundle_is_the_condition_the_endpoint_asked_for",
                   str(got_cond) == str(condition), where,
                   f"this bundle is condition {got_cond!r}, the endpoint asked for "
                   f"{condition!r}. A swapped endpoint differences the wrong two "
                   "populations, and every number that comes out looks reasonable"):
        return None

    if expect_bundle_sha256:
        f.check("the_direct_bundle_is_the_one_the_temporal_release_bound",
                raw == str(expect_bundle_sha256), where,
                f"the bundle on disk hashes to {raw[:16]}…; the temporal release bound "
                f"{str(expect_bundle_sha256)[:16]}…. A stale or swapped bundle admits a run "
                "against numbers that were superseded")

    # THE DIRECT LANE MUST HAVE BEEN SOLVED UNDER THE SAME ENVIRONMENT. Otherwise the two
    # endpoints being differenced were computed by two different solvers.
    env = rb.get("environment_lock") or {}
    env_sha = env.get("sha256") or env.get("env_lock_sha256")
    f.check("the_direct_bundle_was_solved_under_the_authoritative_env_lock",
            env_sha == AUTHORITATIVE_ENV_LOCK_SHA256, where,
            f"solved under {str(env_sha)[:16]}…, not the authoritative "
            f"{AUTHORITATIVE_ENV_LOCK_SHA256[:16]}…")

    rows = _rows(str(bundle_dir))
    rows_sha = content_hash(rows)
    declared_rows = rb.get("arm_rows_sha256") or doc.get("arm_rows_sha256")
    f.check("the_direct_rows_hash_to_what_the_bundle_declares",
            declared_rows == rows_sha, where,
            f"the rows on disk hash to {rows_sha[:16]}…; the bundle declares "
            f"{str(declared_rows)[:16]}…")
    if expect_rows_sha256:
        f.check("the_direct_rows_are_the_ones_the_temporal_release_bound",
                declared_rows == str(expect_rows_sha256), where,
                f"the release bound rows {str(expect_rows_sha256)[:16]}…")

    _w10(f, condition, str(bundle_dir), w10_path, expect_w10_sha256, declared_rows)

    return {"bundle_id": doc.get("arm_bundle_run_id"), "condition": str(condition),
            "raw_sha256": raw, "arm_rows_sha256": declared_rows,
            "base": _dedupe(f, rows, where)}


def _w10(f, condition: str, bundle_dir: str, w10_path: Optional[str],
         expect_w10_sha256: Optional[str], rows_sha256: Optional[str]) -> None:
    """The INDEPENDENT admission — validated against its OWN evidence, not a boolean.

    W10's report carries no ``admitted`` flag, and requiring one would be requiring a field
    that does not exist: a false refusal of a sound report. It does not need one. A boolean is
    a claim; this report ships the thing the claim would have been about — it is self-hashed,
    it names every gate it ran, it records that it never imported the generator, and its
    ``bound_artifact`` says WHICH bundle it admitted, by condition, by rows hash, by solver
    lock and by a map of every file's sha256.

    So the admission is checked against the bundle IN HAND. That is strictly stronger than a
    flag, because a flag can be set by anyone about anything.

    The producer's own ``verification.json`` is still refused, by path and by content: it
    ships PENDING under the SLOT schema and is an empty slot, not a verdict.
    """
    where = f"direct:{condition}"
    placeholder = os.path.join(bundle_dir, VERIFICATION_FILE)

    if not f.check("an_independent_w10_admission_accompanies_every_direct_bundle",
                   bool(w10_path) and os.path.exists(str(w10_path)), where,
                   "no W10 report was supplied. The producer's own verification.json is an "
                   "empty SLOT, not an admission: a temporal run may not stand on a Direct "
                   "endpoint that no independent lane admitted"):
        return

    f.check("the_w10_report_is_not_the_producers_own_placeholder",
            os.path.abspath(str(w10_path)) != os.path.abspath(placeholder), where,
            "the supplied W10 report IS the producer's in-bundle placeholder slot. A "
            "producer that could admit itself by shipping a file with the right name in the "
            "right place would not be admitted by anybody")

    raw = file_sha256(str(w10_path))
    if expect_w10_sha256:
        f.check("the_w10_report_is_the_one_the_temporal_release_bound",
                raw == str(expect_w10_sha256), where,
                f"the report on disk hashes to {raw[:16]}…; the release bound "
                f"{str(expect_w10_sha256)[:16]}…")

    rep = _json(str(w10_path))
    verdict = str(rep.get("verdict") or "")

    if not f.check("the_w10_report_is_the_native_independent_direct_verifiers_report",
                   rep.get("schema_version") == W10_REPORT_SCHEMA
                   and rep.get("verifier_id") == W10_VERIFIER_ID
                   and rep.get("schema_version") != VERIFICATION_SLOT_SCHEMA
                   and verdict != PENDING_VERDICT, where,
                   f"schema {rep.get('schema_version')!r} / verifier "
                   f"{rep.get('verifier_id')!r} / verdict {verdict!r}. The admission is the "
                   f"NATIVE {W10_REPORT_SCHEMA!r} report; the producer's PENDING slot is not "
                   "one, and neither is anything else"):
        return

    # THE VERDICT, and the gates behind it. An ADMIT with a failed gate is not an admit.
    f.check("the_w10_report_actually_ADMITS_this_direct_bundle",
            verdict == W10_ADMIT and int(rep.get("n_failed") or 0) == 0
            and not (rep.get("failed_gates") or []), where,
            f"verdict={verdict!r} n_failed={rep.get('n_failed')!r} "
            f"failed_gates={(rep.get('failed_gates') or [])[:3]}")
    f.check("the_w10_report_was_written_by_a_lane_that_did_not_produce_the_bytes",
            rep.get("independent_of_generator") is True, where,
            "a report that imported the generator is the generator's opinion of itself")

    # THE SELF-HASH. A report that could be edited after it was cited is a claim, not a
    # result: the verdict could be swapped for a friendlier one, or the report re-attributed
    # to a bundle it is not about.
    body = {k: v for k, v in rep.items() if k != "report_sha256"}
    f.check("the_w10_report_sha256_covers_its_own_content",
            rep.get("report_sha256") == content_hash(body), where,
            f"shipped {str(rep.get('report_sha256'))[:16]}…, its own content hashes to "
            f"{content_hash(body)[:16]}…")
    f.check("the_w10_gate_inventory_hash_covers_the_gates_it_lists",
            rep.get("gate_inventory_sha256")
            == content_hash(list(rep.get("gate_inventory") or [])), where, "")

    _w10_bound(f, rep, condition, bundle_dir, rows_sha256, where)


def _w10_bound(f, rep: dict[str, Any], condition: str, bundle_dir: str,
               rows_sha256: Optional[str], where: str) -> None:
    """WHICH bundle the report admitted. Checked against the bundle actually in hand."""
    bound = rep.get("bound_artifact") or {}

    f.check("the_w10_report_admitted_THIS_condition",
            str(bound.get("condition")) == str(condition), where,
            f"the report admits condition {bound.get('condition')!r}; this endpoint is "
            f"{condition!r}. An admission of another condition admits something else")
    if rows_sha256:
        f.check("the_w10_report_admitted_THESE_arm_rows",
                bound.get("arm_rows_sha256") == str(rows_sha256), where,
                f"the report admits rows {str(bound.get('arm_rows_sha256'))[:16]}…; the rows "
                f"on disk hash to {str(rows_sha256)[:16]}…. An admission of other rows is an "
                "admission of other numbers")
    f.check("the_w10_report_admitted_a_bundle_solved_under_the_authoritative_lock",
            bound.get("solver_lock_sha256") == AUTHORITATIVE_ENV_LOCK_SHA256, where,
            f"the report admits a bundle solved under "
            f"{str(bound.get('solver_lock_sha256'))[:16]}…, not the authoritative "
            f"{AUTHORITATIVE_ENV_LOCK_SHA256[:16]}…")

    # THE ARTIFACT MAP. Every file the report says it admitted must still hash to what it
    # hashed to when the report was written — otherwise the admission is of bytes that are
    # no longer there.
    amap = bound.get("artifact_sha256") or {}
    f.check("the_w10_artifact_map_names_the_files_it_admitted", bool(amap), where,
            "the report binds no artifact map; an admission that does not say WHICH bytes it "
            "admitted cannot be checked against them")
    drift = []
    for rel, sha in sorted(amap.items()):
        fp = os.path.join(bundle_dir, os.path.basename(str(rel)))
        if not os.path.exists(fp):
            drift.append(f"{rel}:absent")
        elif file_sha256(fp) != sha:
            drift.append(f"{rel}:changed")
    f.check("every_file_the_w10_report_admitted_still_hashes_to_what_it_admitted",
            not drift, where,
            f"{drift[:4]}. The admission is of bytes that are no longer on disk")


def _dedupe(f, rows: list[dict[str, Any]], where: str) -> dict[str, dict[str, Any]]:
    """increase/decrease -> ONE base delta per (program, target), and they must AGREE."""
    grouped: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for r in rows:
        key = (str(r.get("program_id")), str(r.get("target_id")))
        change = str(r.get("desired_change"))
        if change not in DESIRED_CHANGES:
            f.check("every_direct_row_names_a_real_desired_change", False, where,
                    f"{key}: {change!r}")
            continue
        if change in grouped.setdefault(key, {}):
            f.check("no_direct_row_appears_twice_for_one_arm", False, where, f"{key} {change}")
            continue
        grouped[key][change] = r

    base: dict[str, dict[str, Any]] = {}
    for (pid, tid), by_change in sorted(grouped.items()):
        missing = [c for c in DESIRED_CHANGES if c not in by_change]
        if not f.check("every_direct_program_target_carries_both_arms", not missing, where,
                       f"{pid}/{tid} is missing {missing}"):
            continue

        deltas = {c: by_change[c].get("base_delta") for c in DESIRED_CHANGES}
        if not f.check("the_two_direct_arms_agree_about_the_base_delta_they_share",
                       deltas["increase"] == deltas["decrease"], where,
                       f"{pid}/{tid}: increase says {deltas['increase']!r}, decrease says "
                       f"{deltas['decrease']!r}. They are sign transforms of ONE number; a "
                       "bundle whose two arms disagree about it is internally broken, and a "
                       "temporal run would inherit the disagreement while looking consistent"):
            continue

        bd = deltas["increase"]

        # A Direct row the Direct lane DECLINED to score is not a number to difference.
        # Differencing a declined score would smuggle it back in under a new name — the
        # temporal lane's own rule, applied to the source it now stands on.
        row = by_change["increase"]
        if not (bool(row.get("base_passed")) and bool(row.get("evaluable"))):
            bd = None

        for c in DESIRED_CHANGES:
            raw_bd = deltas["increase"]
            want = None if raw_bd is None else (0.0 if raw_bd == 0 else SIGN[c] * raw_bd)
            f.check("every_direct_arm_value_is_the_sign_transform_of_its_base_delta",
                    by_change[c].get("value") == want, where,
                    f"{pid}/{tid} {c}: value {by_change[c].get('value')!r}, "
                    f"SIGN[{c}] * {raw_bd!r} = {want!r}")

        base.setdefault(pid, {})[tid] = bd
    return base


def recompute(f, doc: dict[str, Any], from_base: dict[str, dict[str, Any]],
              to_base: dict[str, dict[str, Any]], where: str) -> int:
    """RE-DIFFERENCE every temporal base delta from the ADMITTED DIRECT numbers.

    Not from the temporal bundle's own account of its endpoints. This is the difference
    between checking that a release is self-consistent and checking that it is true.
    """
    n = 0
    for rec in doc.get("base_records", []):
        pid, tid = str(rec.get("program_id")), str(rec.get("target_id"))
        a = (from_base.get(pid) or {}).get(tid)
        b = (to_base.get(pid) or {}).get(tid)
        if pid not in from_base or pid not in to_base:
            f.check("the_direct_bundles_cover_every_admitted_program", False, where, pid)
            continue
        if tid not in from_base[pid] or tid not in to_base[pid]:
            f.check("the_direct_bundles_cover_every_target_the_release_reports", False,
                    where, f"{pid}/{tid}")
            continue
        want = None if (a is None or b is None) else b - a
        f.check("every_temporal_base_delta_recomputes_from_the_admitted_direct_bundles",
                rec.get("base_delta") == want, where,
                f"{pid}/{tid}: the release says {rec.get('base_delta')!r}; the admitted "
                f"Direct bundles give {b!r} - {a!r} = {want!r}")
        n += 1
    return n

def verify_endpoints(f, bound, docs: list[dict[str, Any]],
                     direct_bundles: dict, w10_reports: dict) -> None:
    """RE-DIFFERENCE the whole release from the ADMITTED DIRECT bundles it stood on.

    The temporal bundle's own account of its endpoints is not evidence for the endpoints: it
    is the thing being checked. So the two Direct bundles are reopened, rehashed, read for
    their W10 admission, deduplicated to one base delta per (program, target), and the
    difference-in-differences is computed AGAIN from those numbers.
    """
    if not f.check("the_admitted_direct_bundles_were_supplied_to_the_verifier",
                   bool(direct_bundles), "release",
                   "--direct-bundle was not supplied for any condition, so the numbers the "
                   "release differenced could not be checked against anything. An endpoint "
                   "nobody re-read is an endpoint nobody verified"):
        return

    # EVERY released condition must have one — the six ordered pairs are built from all of
    # them, and a missing endpoint is a comparison nobody can reproduce.
    missing = sorted(c for c in bound.conditions if c not in direct_bundles)
    f.check("every_released_condition_has_an_admitted_direct_bundle", not missing,
            "release", f"{missing} have no Direct bundle; the release's six ordered pairs "
                       "are built from all of them")

    # WHICH bundle each condition's endpoint BOUND — taken from the release, then proved.
    pinned: dict[str, tuple] = {}
    for d in docs:
        es = d["doc"].get("endpoint_source") or {}
        for end, cond in (("from", d["from_condition"]), ("to", d["to_condition"])):
            pin = (es.get(f"{end}_direct_bundle_id"), es.get(f"{end}_direct_bundle_sha256"),
                   es.get(f"{end}_w10_report_sha256"), es.get(f"{end}_arm_rows_sha256"))
            if cond in pinned and pinned[cond] != pin:
                f.check("one_direct_bundle_per_condition_across_the_whole_release", False,
                        "release",
                        f"condition {cond!r} is bound to two different Direct bundles across "
                        "the release; the six pairs would not be differences of one screen")
            pinned[cond] = pin

    loaded: dict[str, dict] = {}
    for cond in bound.conditions:
        bid, bsha, wsha, rsha = pinned.get(cond, (None, None, None, None))
        got = load(f, cond, direct_bundles.get(cond), w10_reports.get(cond),
                   expect_bundle_sha256=bsha, expect_w10_sha256=wsha,
                   expect_rows_sha256=rsha)
        if got is None:
            continue
        f.check("the_direct_bundle_is_the_one_the_release_names",
                bid is None or got["bundle_id"] == bid, f"direct:{cond}",
                f"the release names Direct bundle {bid!r}; the one supplied is "
                f"{got['bundle_id']!r}")
        loaded[cond] = got

    n = 0
    for d in docs:
        frm, to = d["from_condition"], d["to_condition"]
        if frm not in loaded or to not in loaded:
            continue
        n += recompute(f, d["doc"], loaded[frm]["base"], loaded[to]["base"],
                                     d["dirname"])
    f.check("every_ordered_pair_was_re_differenced_from_the_direct_bundles",
            not loaded or n == sum(len(x["doc"].get("base_records", [])) for x in docs),
            "release", f"{n} base deltas re-differenced")


