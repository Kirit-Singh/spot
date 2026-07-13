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


def stage1_bindings(prov: Any, release: Any, admitted: list,
                    bundle_id: str) -> list[str]:
    """Every Stage-1 identity: PRESENT, NON-NULL, and EXACTLY the release's own."""
    bad: list[str] = []
    rel = release or {}
    sel = ((prov or {}).get("run_binding") or {}).get("selection_release") or {}

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
