"""THE W5 AUDIT DEFECTS: stale rankings, null Stage-1 bindings, cross-bundle identity.

Split out of ``verify_manifest_rules`` for size. INDEPENDENCE RULE holds: nothing here is
imported from the producer.
"""
from __future__ import annotations

import os
from typing import Any


# --------------------------------------------------------------------------- #
# THE W5 AUDIT DEFECTS. Each fails CLOSED here.
# --------------------------------------------------------------------------- #
def stale_rankings(bundle_dir: str, inv: Any, bundle_id: str) -> list[str]:
    """A ranking file NOBODY BINDS is a ranking nobody checked.

    It sits in the release looking exactly like evidence, and a reader who globs the
    rankings directory would read it. Every file under ``rankings/`` must be bound by
    exactly one arm.
    """
    rdir = os.path.join(bundle_dir, "rankings")
    if not os.path.isdir(rdir):
        return []
    bound = {str((a.get("ranking") or {}).get("path"))
             for a in ((inv or {}).get("arms") or [])}
    on_disk = {f"rankings/{f}" for f in os.listdir(rdir)
               if os.path.isfile(os.path.join(rdir, f))}
    extra = sorted(on_disk - bound)
    return [f"{bundle_id}: {len(extra)} STALE ranking file(s) nothing binds "
            f"(e.g. {extra[:3]}); an unbound ranking is unverified and indistinguishable "
            "from evidence"] if extra else []


# THE STAGE-1 BINDINGS A BUNDLE MUST CARRY, AND THEY MUST BE EXACT.
#
# Checking only that the scorer-view field was non-null left every OTHER Stage-1 identity
# free to be null: the release identity, the per-program projection, the selector. A bundle
# could bind a real scorer view and NOTHING ELSE, and be admitted. And a field that is
# merely non-null is not a binding either — it has to be the identity the RELEASE publishes,
# or it is a number that agrees with nothing.
#
# ``admitted_programs`` was worse: it was checked only ``if present``, so omitting it
# skipped the check entirely. An optional identity gate is not a gate.
STAGE1_EXACT = {
    "registry_scorer_view_sha256": "registry_scorer_view_canonical_sha256",
    "registry_scorer_projection_sha256": "registry_scorer_projection_sha256",
}

# The effect universe lives in the STAGE-1 binding, not inside ``stage2_inputs`` — the
# canonical inputs object is exactly three keys and nothing is duplicated into it.
STAGE1_NONNULL = ("effect_universe_sha256",)

# ...and the temporal method digest lives in its OWN explicit run_binding field, for the
# same reason: one fact, one home. A value duplicated into two places is a value that can
# disagree with itself.
LANE_METHOD_FIELD = {"temporal": "temporal_method_sha256"}


PROJECTION_MAP = "per_program_projection_sha256"
PROJECTION_RULE_FIELD = "per_program_projection_rule_id"
PROJECTION_RULE_ID = (
    "spot.stage01_stage2_registry_view.program_record.canonical_sha256.v1")


def method_field(prov: Any, lane: str, bundle_id: str) -> list[str]:
    """The lane's method digest, in its OWN explicit field. Never inside stage2_inputs."""
    field = LANE_METHOD_FIELD.get(lane)
    if not field:
        return []
    rb = (prov or {}).get("run_binding") or {}
    if not rb.get(field):
        return [f"{bundle_id}: run_binding.{field} is {rb.get(field)!r} — the method digest "
                "is bound in its own explicit field, not duplicated into stage2_inputs"]
    return []


def stage1_bindings(prov: Any, release: Any, admitted: list, bundle_id: str,
                    projection: Any = None) -> list[str]:
    """Every Stage-1 identity: PRESENT, NON-NULL, and EXACTLY the release's own.

    TWO PROJECTION BINDINGS, and NEITHER substitutes for the other:

      * the SCALAR ``registry_scorer_projection_sha256`` — the Stage-2-bound OVERALL
        projection identity the release publishes. It says WHICH projection was used;
      * the ``per_program_projection_sha256`` MAP — one canonical hash per admitted program,
        independently recomputed here from the staged scorer view's own records. It says
        WHAT each program's projection actually IS.

    A run can bind the right overall identity while a single program's panel, control or
    coefficients have drifted, and the scalar would never notice — it is one number over the
    whole view. Equally, a map with correct entries and the wrong scalar is bound to a
    projection the release does not publish. So both are required, the map's KEY SET must be
    exactly the admitted programs, and every value must match the recomputation.
    """
    bad: list[str] = []
    rel = release or {}
    sel = ((prov or {}).get("run_binding") or {}).get("selection_release") or {}

    for field in STAGE1_NONNULL:
        if not sel.get(field):
            bad.append(f"{bundle_id}: selection_release.{field} is {sel.get(field)!r} — "
                       "the effect universe is bound HERE, not inside stage2_inputs")

    for field, rel_field in sorted(STAGE1_EXACT.items()):
        got, want = sel.get(field), rel.get(rel_field)
        if not got:
            bad.append(f"{bundle_id}: selection_release.{field} is {got!r} — a null "
                       "Stage-1 binding binds nothing")
        elif want and got != want:
            bad.append(f"{bundle_id}: selection_release.{field} is {str(got)[:16]}; the "
                       f"bound release publishes {str(want)[:16]}")

    # THE SELECTOR IDENTITY. Required, never optional.
    adm = (prov or {}).get("program_admission") or {}
    progs = adm.get("programs")
    if not progs:
        bad.append(f"{bundle_id}: program_admission.programs is {progs!r} — the arms stand "
                   "on no declared program axis")
    elif admitted and sorted(str(p) for p in progs) != sorted(admitted):
        bad.append(f"{bundle_id}: its arms stand on {sorted(progs)[:3]}…; the release "
                   f"admits {sorted(admitted)[:3]}…")
    if not adm.get("registry_scorer_view_sha256"):
        bad.append(f"{bundle_id}: program_admission.registry_scorer_view_sha256 is null")

    # THE RULE the map was computed under. A map of hashes whose recipe is unstated is a
    # map of numbers: two lanes can each be internally consistent and be hashing different
    # things.
    got_rule = sel.get(PROJECTION_RULE_FIELD)
    if got_rule != PROJECTION_RULE_ID:
        bad.append(f"{bundle_id}: {PROJECTION_RULE_FIELD} is {got_rule!r}; the canonical "
                   f"rule is {PROJECTION_RULE_ID!r} — keys sorted, ARRAY ORDER PRESERVED, "
                   "over the whole emitted program record")

    # THE PER-PROGRAM PROJECTION MAP, re-derived. The scalar is one number over the whole
    # view; it cannot see a single program's projection drift.
    got_map = sel.get(PROJECTION_MAP)
    if not isinstance(got_map, dict) or not got_map:
        bad.append(f"{bundle_id}: selection_release.{PROJECTION_MAP} is {got_map!r} — the "
                   "scalar projection identity cannot see a single program's projection "
                   "drift, so the per-program map is required alongside it")
    elif projection:
        want_keys, got_keys = sorted(projection), sorted(str(k) for k in got_map)
        extra = sorted(set(got_keys) - set(want_keys))
        absent = sorted(set(want_keys) - set(got_keys))
        if extra:
            bad.append(f"{bundle_id}: {PROJECTION_MAP} carries {extra[:3]}, which the "
                       "release does NOT admit as base-portable. A projection for a program "
                       "no arm can stand on is a key that agrees with nothing")
        if absent:
            bad.append(f"{bundle_id}: {PROJECTION_MAP} is MISSING {absent[:3]} — every "
                       "admitted program's projection must be bound, or an arm stands on a "
                       "projection nobody pinned")
        if not extra and not absent and len(got_keys) != len(want_keys):
            bad.append(f"{bundle_id}: {PROJECTION_MAP} has {len(got_keys)} key(s); the "
                       f"release admits {len(want_keys)}")
        wrong = sorted(k for k in set(got_keys) & set(want_keys)
                       if got_map[k] != projection[k])
        if wrong:
            bad.append(f"{bundle_id}: {PROJECTION_MAP} disagrees with the staged scorer "
                       f"view for {wrong[:3]} — that program's projection is not the one "
                       "the release publishes")
    return bad


CROSS_BUNDLE_TOL = 1e-9


def check_cross_bundle(arm_values: dict) -> list[str]:
    """THE REVERSE-DIRECTION IDENTITY, re-derived ACROSS bundles.

    ``base_delta(A->B) = -base_delta(B->A)`` by construction, and an arm value is a fixed
    sign times that base. So for the SAME (program, desired_change) and the SAME target::

        arm_value(A->B) == -arm_value(B->A)

    Nothing WITHIN one bundle can see this. Six bundles that were each internally perfect
    could still disagree with one another about the same measurement, and the aggregate is
    the only place that can notice.
    """
    bad: list[str] = []
    for (frm, to, prog, dc), values in sorted(arm_values.items()):
        rev = arm_values.get((to, frm, prog, dc))
        if rev is None:
            continue
        for target, v in sorted(values.items()):
            w = rev.get(target)
            if v is None or w is None:
                if v is not None or w is not None:
                    bad.append(f"{prog}|{dc}: {target} is measured {frm}->{to} but not "
                               f"{to}->{frm}")
                continue
            if abs(float(v) + float(w)) > CROSS_BUNDLE_TOL:
                bad.append(
                    f"{prog}|{dc}|{target}: {frm}->{to} is {v} but {to}->{frm} is {w}; the "
                    "reverse of an ordered pair must be the exact negation")
    return bad


def inventory_matches_arms(inventory: Any, bound_rankings: dict) -> list[str]:
    """The INVENTORY may not name a ranking no ARM binds — nor omit one that an arm does.

    A fully-hashed, perfectly-resealed EXTRA ranking file passes every byte check there is:
    it is real JSON, its hashes are correct, and the inventory vouches for it. It is simply
    not part of the release — 121 files inventoried against 120 arms — and the only way to
    see that is to compare the two lists, which nothing did.
    """
    bad: list[str] = []
    for b in ((inventory or {}).get("bundles") or []):
        rel_dir = str(b.get("relative_dir") or "")
        listed = {str(k) for k in (b.get("rankings") or {})}
        bound = bound_rankings.get(rel_dir)
        if bound is None:
            continue
        extra, absent = sorted(listed - bound), sorted(bound - listed)
        if extra:
            bad.append(f"{rel_dir}: the inventory binds {len(listed)} ranking(s) but the "
                       f"arms bind {len(bound)}; {extra[:3]} belong to no arm")
        if absent:
            bad.append(f"{rel_dir}: the arms bind {absent[:3]}, which the inventory does "
                       "not name")
    return bad


# --------------------------------------------------------------------------- #
# THE ENVIRONMENT LOCK. Bound in every bundle, and CHECKED against the real bytes.
#
# CANONICAL CARRIER (the repo convention, emitted by run_screen / run_pathway / run_temporal
# via ``runid.env_lock_block``):
#
#     run_binding.environment_lock = {name, sha256, status}
#
# ``env_lock_sha256`` is accepted as a scalar ALIAS pending W5's confirmation, and if both
# are present they must AGREE — a value with two homes is a value that can disagree with
# itself.
#
# A lock that is merely NAMED proves nothing: the verifier is handed the actual lock file
# and compares its bytes. Two runs under different solved environments are two different
# runs, however identical their code.
# --------------------------------------------------------------------------- #
ENV_LOCK_BLOCK = "environment_lock"
ENV_LOCK_ID_EXPECTED = "spot.stage02.solver_lock.v1"
ENV_LOCK_SCALAR = "env_lock_sha256"
ENV_LOCK_LOCKED = "locked"


def env_lock_sha256(prov: Any) -> tuple:
    """The lock hash a bundle binds, from either carrier. ``(value, problems)``."""
    rb = (prov or {}).get("run_binding") or {}
    block = rb.get(ENV_LOCK_BLOCK) or {}
    from_block = block.get("sha256") if isinstance(block, dict) else None
    from_scalar = rb.get(ENV_LOCK_SCALAR)
    if from_block and from_scalar and from_block != from_scalar:
        return None, [f"{ENV_LOCK_BLOCK}.sha256 and {ENV_LOCK_SCALAR} disagree "
                      f"({str(from_block)[:16]} vs {str(from_scalar)[:16]})"]
    return (from_block or from_scalar), []


def check_env_lock(prov: Any, expected_sha256: Any, bundle_id: str) -> list[str]:
    """The bundle's lock must be PRESENT, LOCKED, and the lock the verifier was handed."""
    bad: list[str] = []
    got, problems = env_lock_sha256(prov)
    bad += [f"{bundle_id}: {p}" for p in problems]

    block = ((prov or {}).get("run_binding") or {}).get(ENV_LOCK_BLOCK) or {}
    # The producers' shared ``envlock`` block (fc9bdcd) carries its own identity and its own
    # expectation. Where they are present they are CHECKED: a block that verified itself
    # against a different constant verified nothing that matters here.
    if isinstance(block, dict):
        if block.get("lock_id") and block["lock_id"] != ENV_LOCK_ID_EXPECTED:
            bad.append(f"{bundle_id}: environment_lock.lock_id is {block['lock_id']!r}; the "
                       f"Stage-2 solver lock is {ENV_LOCK_ID_EXPECTED!r}")
        if block.get("expected_sha256") and \
                block["expected_sha256"] != AUTHORITATIVE_ENV_LOCK_SHA256:
            bad.append(f"{bundle_id}: the bundle verified its lock against "
                       f"{str(block['expected_sha256'])[:16]}, not the authoritative "
                       f"{AUTHORITATIVE_ENV_LOCK_SHA256[:16]}")
        if block.get("verified") is False:
            bad.append(f"{bundle_id}: environment_lock.verified is false")
    if isinstance(block, dict) and block.get("status") and \
            block["status"] != ENV_LOCK_LOCKED:
        bad.append(f"{bundle_id}: environment_lock.status is {block['status']!r} — a run "
                   "taken under no solved environment is not reproducible, and saying so "
                   "in the artifact does not make it so")
    if not got:
        bad.append(f"{bundle_id}: binds no environment lock. Two runs under different "
                   "solved environments are two different runs, however identical the code")
    elif expected_sha256 and got != expected_sha256:
        bad.append(f"{bundle_id}: binds env lock {str(got)[:16]}; the lock supplied to the "
                   f"verifier hashes to {str(expected_sha256)[:16]}")
    return bad


# --------------------------------------------------------------------------- #
# THE AUTHORITATIVE STAGE-2 SOLVER LOCK — a PROTECTED VERIFIER IDENTITY.
#
# The caller's ``--expect-env-lock-sha256`` is NOT an authority: it is a digest the operator
# chose. An independent probe built an aggregate in which EVERY lane bound b9284e63... AND
# the caller pinned b9284e63..., so every comparison agreed with every other — and the run
# was admitted. Everything was being compared to the wrong thing, consistently.
#
# So the verifier holds its OWN copy of the frozen fact, exactly as it holds its own copy of
# the desired-change table and the coverage thresholds. It can therefore DISAGREE with the
# operator, which is the only way the operator can ever be wrong.
#
#   authoritative : 02_geneskew/analysis/stage02_solver_lock.txt  (committed at c1f8e80)
#                   sha256 2983d140941f13d223dad93bae71434663882f23f25f6717c3debe59d2711abe
#   NOT the lock  : _requirements/base.lock (sha b9284e63...) is the REPO environment, not
#                   the Stage-2 solver lock. W5 4435366 bound it. They are different files
#                   describing different environments, and Stage-1 runs a third.
# --------------------------------------------------------------------------- #
AUTHORITATIVE_ENV_LOCK_SHA256 = (
    "2983d140941f13d223dad93bae71434663882f23f25f6717c3debe59d2711abe")
AUTHORITATIVE_ENV_LOCK_PATH = "02_geneskew/analysis/stage02_solver_lock.txt"

# Locks that are REAL, and are not this one. Named so the refusal says WHY.
KNOWN_WRONG_LOCKS = {
    "b9284e63": "_requirements/base.lock — the REPO environment, not the Stage-2 solver "
                "lock (bound by W5 4435366)",
}


def check_supplied_lock(supplied: Any, pinned: Any,
                        authoritative: str = AUTHORITATIVE_ENV_LOCK_SHA256) -> list[str]:
    """The lock must be THE authoritative one — not the one the operator nominated.

    Both the bytes handed to the verifier AND the caller's expected digest are checked
    against the verifier's own frozen constant. A run in which every lane, and the caller,
    consistently name the WRONG lock is still the wrong lock.
    """
    bad: list[str] = []
    if not supplied:
        return ["no environment lock was supplied to the verifier (--env-lock); the lock a "
                "bundle NAMES cannot be checked against bytes nobody handed us"]

    def _why(sha):
        note = KNOWN_WRONG_LOCKS.get(str(sha)[:8])
        return f" ({note})" if note else ""

    if supplied != authoritative:
        bad.append(
            f"the lock supplied to the verifier hashes to {supplied[:16]}{_why(supplied)}; "
            f"the AUTHORITATIVE Stage-2 solver lock is {authoritative[:16]} "
            f"({AUTHORITATIVE_ENV_LOCK_PATH}). Which environment the run used is not the "
            "operator's to choose")
    if not pinned:
        bad.append("no expected lock digest was pinned (--expect-env-lock-sha256)")
    elif pinned != authoritative:
        bad.append(
            f"the caller pinned {str(pinned)[:16]}{_why(pinned)} as the expected lock; the "
            f"AUTHORITATIVE one is {authoritative[:16]}. A digest the operator nominated is "
            "not an authority — that is the whole reason the verifier holds its own")
    return bad
