"""ADMISSION for the reusable temporal arm bundle: what may ship, and what is re-derived.

GENERATOR != EVALUATOR. Everything here runs on the SHIPPED BYTES, and re-derives the
claims from them alone. It never takes the producer's word, and it never takes the
producer's in-memory object: a checker that verifies the caller's copy of the thing it is
verifying is a formality with a hash beside it.

THREE FAIL-CLOSED GATES
-----------------------
1. THE EXACT KEY ALLOWLIST, per record kind. An unknown key is a REJECT, not a warning.
   A generator that grows a field has to come here and authorise it.

2. THE INHERITED p/q/COMBINED FIREWALL (``admission.forbidden_keys``), recursive and
   case-insensitive over the whole artifact. This lane has no calibrated null, so a number
   that LOOKS like significance would be READ as significance.

3. THE ARM FIREWALL — this artifact's own prohibition. A reusable arm may not carry a
   ROLE, a POLE, a PARETO tier, a CONCORDANCE class, a PAIR/SELECTION id or a BATCH field.
   Each is a JOIN-TIME or COMPARISON-SCOPED property, and a cached arm that carried one
   would be a pair-shaped artifact wearing a reusable arm's key — which is exactly the
   defect the reusable-arm topology exists to remove.

RE-DERIVATION
-------------
The shipped bytes must prove themselves:

  * every arm key re-derives from ``(program, desired_change, from, to)``;
  * every arm value re-derives as ``SIGN[desired_change] * base_delta`` of the base record
    it points at — so ``decrease`` is EXACTLY the negation of ``increase``;
  * every rank re-derives from the shipped values by the frozen rank rule;
  * the arm inventory is exactly ``n_programs x 2``, with no program missing and none
    invented;
  * the bundle id re-derives from the bundle's own content.
"""
from __future__ import annotations

import re
from typing import Any

from ...arm_keys import DESIRED_CHANGES, SIGN
from ...hashing import content_hash
from .. import admission as comparison_admission
from . import arm_bundle as ab
from . import arm_estimand as est

# --------------------------------------------------------------------------- #
# Gate 3: the arm firewall. A reusable arm carries NONE of these.
# --------------------------------------------------------------------------- #
ARM_FORBIDDEN_PATTERN = (
    r"pareto|concordance|away_from|toward_b|batch"
    r"|pair_id|pair_key|selection_id|question_id"
    r"|(^|_)(pole|poles|role|roles)(_|$)")
ARM_FORBIDDEN_RE = re.compile(ARM_FORBIDDEN_PATTERN, re.IGNORECASE)

# NEGATIVE DECLARATIONS: exempt ONLY while they still say "forbidden". The artifact has to
# be able to write down its own prohibition, or the rule would be unstatable — but it does
# not get to keep the exemption after flipping the prohibition off.
ARM_NEGATIVE_DECLARATIONS = {"bundle_carries_role_or_pole": False}

# THE ONE EXACT-NAME EXEMPTION from the INHERITED firewall (gate 2).
#
# ``registry_scorer_view_sha256`` matches ``/score/`` — because "scorer" contains "score".
# It is nonetheless legitimate: it is the Stage-1 v3 contract's OWN field name for the
# content hash of the program REGISTRY SCORER VIEW, and it is carried under the contract's
# spelling so a reader can trace the program axis back to the release it was derived from.
# It is the hash of a registry. It is not a score, not an objective and not a ranking
# quantity — nothing ranks, gates or sorts on it.
#
# The exemption is the EXACT SPELLING, not the shape. There is no pattern-shaped hole here
# for a ``combined_scorer`` or a ``scorer_value`` to walk through.
INHERITED_FIREWALL_EXCEPTIONS = frozenset({"registry_scorer_view_sha256"})


def inherited_forbidden_keys(obj: Any) -> list[str]:
    """The inherited p/q/combined firewall, minus the one exact-named exemption above."""
    return [hit for hit in comparison_admission.forbidden_keys(obj)
            if hit.rsplit(".", 1)[-1] not in INHERITED_FIREWALL_EXCEPTIONS]

BUNDLE_KEYS = frozenset({
    "schema_version", "bundle_kind", "bundle_key", "bundle_id",
    "from_condition", "to_condition",
    "n_programs", "n_desired_changes", "n_arms", "n_targets", "n_base_records",
    "arm_keys", "base_records", "arms", "program_admission", "estimand", "method",
    "bundle_is_pair_agnostic", "bundle_carries_role_or_pole",
})

ARM_KEYS_ALLOWED = frozenset({
    "arm_key", "program_id", "desired_change", "from_condition", "to_condition",
    "n_targets", "n_evaluable", "n_ranked", "records",
})

ARM_RECORD_KEYS = frozenset({
    "target_id", "base_key", "arm_value", "evaluable", "temporal_status", "rank",
})

_ENDS = ("from", "to")
BASE_RECORD_KEYS = frozenset(
    {"base_key", "program_id", "target_id", "target_symbol", "target_ensembl",
     "target_id_namespace", "from_condition", "to_condition", "temporal_status",
     "evaluable", "base_delta"}
    | {f"{e}_{k}" for e in _ENDS for k in
       ("present", "delta", "projection_status", "evaluable", "state", "reasons",
        "released_estimate_id", "base_qc_passed", "base_qc_state", "base_qc_reasons")}
    | {f"{e}_{k}" for e in _ENDS for k in ab.DECOMPOSITION}
    | {f"{e}_{k}" for e in _ENDS for k in ab.QC_FIELDS}
    | {f"{e}_{k}" for e in _ENDS for k in ab.MASK_FIELDS}
    | {f"{e}_{k}" for e in _ENDS for k in ab.DENOMINATORS})


class BundleRejected(ValueError):
    """The bundle is not admissible. Refuse; never repair, never downgrade to a warning."""


def arm_forbidden_keys(obj: Any, path: str = "") -> list[str]:
    """Every ROLE / POLE / PARETO / CONCORDANCE / PAIR / BATCH key, at ANY depth."""
    hits: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            here = f"{path}.{key}" if path else str(key)
            if ARM_FORBIDDEN_RE.search(str(key)) and not _exempt(str(key), value):
                hits.append(here)
            hits.extend(arm_forbidden_keys(value, here))
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            hits.extend(arm_forbidden_keys(value, f"{path}[{i}]"))
    return hits


def _exempt(key: str, value: Any) -> bool:
    if key in ARM_NEGATIVE_DECLARATIONS:
        # `is` on the literal, so a truthy 1 or "false" cannot pose as the prohibition
        return value is ARM_NEGATIVE_DECLARATIONS[key]
    return False


def _unknown(got: Any, allowed: frozenset, what: str) -> list[str]:
    return [f"{what}.{k}" for k in sorted(set(got) - set(allowed))]


def _missing(got: Any, allowed: frozenset, what: str) -> list[str]:
    return [f"{what}.{k}" for k in sorted(set(allowed) - set(got))]


def verify_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    """RE-DERIVE every claim in the bundle from the bundle. Returns a checked report.

    Raises ``BundleRejected`` on the first structural refusal; collects every
    re-derivation failure so a reader sees ALL of them rather than one at a time.
    """
    failures: list[str] = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        if not ok:
            failures.append(f"[{name}] {detail}")

    # ---- gate 1: the exact key allowlists ----
    problems = (_unknown(bundle, BUNDLE_KEYS, "bundle")
                + _missing(bundle, BUNDLE_KEYS, "bundle"))
    if problems:
        raise BundleRejected(
            f"bundle keys are not the contract: {problems}. An unknown key is an "
            "unauthorised claim; a missing one means this is not the artifact the "
            "contract describes")
    for arm in bundle["arms"]:
        p = _unknown(arm, ARM_KEYS_ALLOWED, "arm") + _missing(arm, ARM_KEYS_ALLOWED, "arm")
        if p:
            raise BundleRejected(f"arm {arm.get('arm_key')!r} keys are not the contract: {p}")
        for rec in arm["records"]:
            p = (_unknown(rec, ARM_RECORD_KEYS, "arm_record")
                 + _missing(rec, ARM_RECORD_KEYS, "arm_record"))
            if p:
                raise BundleRejected(f"arm record keys are not the contract: {p}")
    for base in bundle["base_records"]:
        p = (_unknown(base, BASE_RECORD_KEYS, "base_record")
             + _missing(base, BASE_RECORD_KEYS, "base_record"))
        if p:
            raise BundleRejected(f"base record keys are not the contract: {p}")

    # ---- gate 2: the inherited p / q / combined-objective firewall ----
    pq = inherited_forbidden_keys(bundle)
    check("no_pq_or_combined_objective", not pq, f"forbidden keys: {pq}")

    # ---- gate 3: the arm firewall ----
    arm_hits = arm_forbidden_keys(bundle)
    check("no_role_pole_pareto_concordance_pair_or_batch_field", not arm_hits,
          f"forbidden keys: {arm_hits}")

    # ---- the inventory: n_programs x 2, complete and not invented ----
    programs = bundle["program_admission"]["programs"]
    expected = {est.arm_key(p, c, bundle["from_condition"], bundle["to_condition"])
                for p in programs for c in DESIRED_CHANGES}
    got = {a["arm_key"] for a in bundle["arms"]}
    check("arm_inventory_is_every_program_x_every_desired_change", got == expected,
          f"missing={sorted(expected - got)} unexpected={sorted(got - expected)}")
    check("n_arms_is_n_programs_x_n_desired_changes",
          bundle["n_arms"] == len(programs) * len(DESIRED_CHANGES),
          f"n_arms={bundle['n_arms']} programs={len(programs)}")
    check("arm_keys_index_matches_the_arms", sorted(got) == list(bundle["arm_keys"]),
          "the arm_keys index disagrees with the arms it indexes")

    by_base = {b["base_key"]: b for b in bundle["base_records"]}

    for arm in bundle["arms"]:
        key = arm["arm_key"]
        # the KEY re-derives from its own parts — a forged key cannot survive this
        rederived = est.arm_key(arm["program_id"], arm["desired_change"],
                                arm["from_condition"], arm["to_condition"])
        check("arm_key_rederives_from_its_own_parts", key == rederived,
              f"shipped {key!r}, re-derived {rederived!r}")
        check("arm_is_scoped_to_the_bundles_ordered_pair",
              arm["from_condition"] == bundle["from_condition"]
              and arm["to_condition"] == bundle["to_condition"],
              f"arm {key!r} names a different ordered pair than its bundle")

        sign = SIGN[arm["desired_change"]]
        for rec in arm["records"]:
            base = by_base.get(rec["base_key"])
            if base is None:
                failures.append(f"[arm_record_points_at_a_real_base] {rec['base_key']!r}")
                continue
            # the VALUE is a sign transform of the ONE base delta. Not a re-estimate.
            b = base["base_delta"]
            want = None if b is None else (0.0 if b == 0 else sign * b)
            check("arm_value_is_the_sign_transform_of_the_base_delta",
                  rec["arm_value"] == want,
                  f"{key} / {rec['target_id']}: shipped {rec['arm_value']!r}, "
                  f"re-derived {want!r} from base_delta={b!r}")
            check("arm_evaluability_is_the_bases_evaluability",
                  rec["evaluable"] == base["evaluable"],
                  f"{key} / {rec['target_id']}: the two arms of a program share an "
                  "estimate, so they share its evaluability")

        # the RANK re-derives from the SHIPPED values, by the frozen rule
        _check_ranks(arm, check)

    # ---- the bundle id covers the bundle's own content ----
    payload = {k: v for k, v in bundle.items() if k != "bundle_id"}
    derived = content_hash(payload)[:ab.BUNDLE_ID_LEN]
    check("bundle_id_covers_its_own_content", bundle["bundle_id"] == derived,
          f"shipped {bundle['bundle_id']!r}, content hashes to {derived!r}")

    return {"admitted": not failures, "failures": failures,
            "n_arms": bundle["n_arms"], "n_base_records": bundle["n_base_records"],
            "bundle_id": bundle["bundle_id"], "bundle_key": bundle["bundle_key"]}


def _check_ranks(arm: dict[str, Any], check) -> None:
    """Re-derive this arm's ranks from its OWN shipped values, by the frozen rule.

    Descending on the canonical value; ties on ``target_id`` ascending; dense 1..n over the
    evaluable, non-null population; everything else null. Computed from the bytes, so a
    rank that was assigned by some other rule cannot survive.
    """
    rankable = [r for r in arm["records"]
                if r["evaluable"] and r["arm_value"] is not None]
    order = sorted(rankable, key=lambda r: (-r["arm_value"], r["target_id"]))
    want = {r["target_id"]: i for i, r in enumerate(order, start=1)}
    for rec in arm["records"]:
        expected = want.get(rec["target_id"])
        check("rank_rederives_by_the_frozen_rule", rec["rank"] == expected,
              f"{arm['arm_key']} / {rec['target_id']}: shipped rank {rec['rank']!r}, "
              f"re-derived {expected!r}")
    check("n_ranked_is_the_evaluable_population",
          arm["n_ranked"] == len(rankable) and arm["n_evaluable"] == len(rankable),
          f"{arm['arm_key']}: n_ranked={arm['n_ranked']} n_evaluable={arm['n_evaluable']} "
          f"rankable={len(rankable)}")
