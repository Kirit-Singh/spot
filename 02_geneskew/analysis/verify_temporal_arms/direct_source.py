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

from . import w10 as w10_mod
from .canonical import content_hash, file_sha256

DIRECT_BUNDLE_SCHEMA = "spot.stage02_direct_arm_bundle.v1"

# A Direct bundle is a DIRECTORY, not a file: the manifest, the rows, the provenance, and the
# producer's own placeholder verdict.
BUNDLE_FILE = "arm_bundle.json"
ROWS_FILE = "arms.parquet"
PROVENANCE_FILE = "provenance.json"
VERIFICATION_FILE = "verification.json"

# The W10 admission contract lives in ``w10``: the WHOLE of it, not the parts that were easy
# to parse. Re-exported here so a caller has one import site.
PENDING_VERDICT = w10_mod.PENDING_VERDICT
VERIFICATION_SLOT_SCHEMA = w10_mod.VERIFICATION_SLOT_SCHEMA
W10_REPORT_SCHEMA = w10_mod.W10_REPORT_SCHEMA
W10_VERIFIER_ID = w10_mod.W10_VERIFIER_ID
W10_ADMIT = w10_mod.W10_ADMIT
W10_EXPECTED_FILES = w10_mod.EXPECTED_FILES

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
         expect_rows_sha256: Optional[str] = None,
         w10_pins=None) -> Optional[dict[str, Any]]:
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

    # WHAT THE BUNDLE ACTUALLY IS — so the report's recomputation counts can be checked
    # against it rather than against themselves.
    facts = {"n_targets": len({str(r.get("target_id")) for r in rows}),
             "n_arm_rows": len(rows)}
    _w10(f, condition, str(bundle_dir), w10_path, expect_w10_sha256, declared_rows,
         pins=w10_pins, bundle_facts=facts)

    return {"bundle_id": doc.get("arm_bundle_run_id"), "condition": str(condition),
            "raw_sha256": raw, "arm_rows_sha256": declared_rows,
            "base": _dedupe(f, rows, where)}


def _w10(f, condition: str, bundle_dir: str, w10_path: Optional[str],
         expect_w10_sha256: Optional[str], rows_sha256: Optional[str],
         pins=None, bundle_facts=None) -> None:
    """The INDEPENDENT admission, checked against the WHOLE W10 contract.

    Not against the fields that were easy to parse. A partial parser is a forger's
    specification: check the schema, the id, the verdict and a self-hash, and you have
    described exactly the document an attacker will write — correct everywhere you looked and
    fabricated everywhere else.

    The producer's own ``verification.json`` is refused by PATH as well as by content: it
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

    w10_mod.check(f, _json(str(w10_path)), condition=condition, bundle_dir=bundle_dir,
                  rows_sha256=rows_sha256,
                  solver_lock_sha256=AUTHORITATIVE_ENV_LOCK_SHA256, where=where, pins=pins,
                  bundle_facts=bundle_facts or {})


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
                     direct_bundles: dict, w10_reports: dict, w10_pins=None) -> None:
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
                   expect_rows_sha256=rsha, w10_pins=w10_pins)
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


