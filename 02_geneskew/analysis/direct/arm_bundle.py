"""The ALL-ARM Direct bundle: one base effect per (program, target), two arms per program.

ROUND4_ADDENDUM c4773562. A Direct condition bundle carries EVERY admitted program's arms —
`increase` and `decrease` — for every perturbation target. There is no A/B pair anywhere in
it, and a pair is not what it is for: a pair is a JOIN of two arms out of this bundle, done
at display time, and it is not stored here.

ONE MEASUREMENT, TWO LOGICAL ARMS
---------------------------------
The base delta of a program on a target is computed ONCE. `increase` is that delta;
`decrease` is its exact negation. They are not two estimates — they are one estimate and a
sign, so they cannot disagree about a magnitude they share. The RANKS are then taken
SEPARATELY, per arm, because a rank is a statement about a population and reversing the
values genuinely reverses the order.

WHAT IS NOT HERE, AND WHY
-------------------------
  * NO pair fields (`away_from_A`, `toward_B`, A_*/B_*). The role a program plays is a
    property of a QUESTION, not of the program's effect. Storing the role would fuse the
    arm to one pair and make it un-reusable — the whole point of the migration;
  * NO Pareto, NO concordance, NO combined/balanced/weighted score. Pair-derived orderings
    are join-time display only: off by default, no new number, and never part of release
    completeness or Stage-3 admission;
  * NO p, NO q, NO FDR. `inference_status = not_calibrated`, as everywhere in this lane.
"""
from __future__ import annotations

from typing import Any, Optional

from . import arm_keys, config
from . import projection as proj
from .hashing import canonical_num, content_hash

SCHEMA_VERSION = "spot.stage02_direct_arm_bundle.v1"
BUNDLE_ID = "spot.stage02.direct.all_arm_bundle.v1"

ARM_ROW_COLUMNS = (
    "arm_key", "program_id", "desired_change", "condition", "target_id",
    "base_delta", "value", "rank", "evaluable", "projection_status",
    "base_state", "base_passed", "n_panel_surviving", "n_control_surviving",
)

# A rank exists only where the arm can actually be ranked. A target the arm could not score
# is ABSENT from the ranking — it is not a zero, and it is not last.
RANK_RULE_ID = "spot.stage02.direct.arm_rank.desc_value_tiebreak_target_id.v1"
RANK_RULE = ("ranked desc by the arm's own value, ties broken on target_id; a target that "
             "is not evaluable or has no finite value is not ranked at all")


def arm_rows_for_program(*, program_id: str, condition: str,
                         base: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Both arms of ONE program, from ONE set of base deltas.

    ``base`` is one entry per target: {target_id, delta, status, base_state, base_passed,
    n_panel_surviving, n_control_surviving}.
    """
    rows: list[dict[str, Any]] = []
    for change in arm_keys.DESIRED_CHANGES:
        key = arm_keys.direct_arm_key(program_id, change, condition)
        sign = arm_keys.SIGN[change]
        for b in base:
            delta = b["delta"]
            evaluable = bool(b["base_passed"]) and delta is not None \
                and b["status"] == proj.OK
            # the EXACT sign transform of the one base effect — never a re-estimate
            value = None if delta is None else (0.0 if delta == 0 else sign * float(delta))
            rows.append({
                "arm_key": key,
                "program_id": program_id,
                "desired_change": change,
                "condition": condition,
                "target_id": b["target_id"],
                "base_delta": canonical_num(delta),
                "value": canonical_num(value) if evaluable else None,
                "rank": None,                       # assigned below, per arm
                "evaluable": evaluable,
                "projection_status": b["status"],
                "base_state": b["base_state"],
                "base_passed": bool(b["base_passed"]),
                "n_panel_surviving": b["n_panel_surviving"],
                "n_control_surviving": b["n_control_surviving"],
            })
    return rows


def rank_in_place(rows: list[dict[str, Any]]) -> None:
    """Rank EACH arm separately, over its own evaluable population.

    Separately, because a rank is a statement about a population: negating the values really
    does reverse the order, and an arm that inherited the other's ranks would be reporting a
    position nothing put it in.
    """
    by_arm: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        by_arm.setdefault(r["arm_key"], []).append(r)

    for arm_rows in by_arm.values():
        rankable = [r for r in arm_rows
                    if r["evaluable"] and r["value"] is not None
                    and r["value"] == r["value"]
                    and r["value"] not in (float("inf"), float("-inf"))]
        rankable.sort(key=lambda r: (-r["value"], r["target_id"]))
        for i, r in enumerate(rankable, start=1):
            r["rank"] = i


def build_rows(*, condition: str, admitted: list[str],
               base_by_program: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Every arm row in this condition bundle: |admitted| x 2 arms x |targets|."""
    rows: list[dict[str, Any]] = []
    for program_id in admitted:
        rows += arm_rows_for_program(program_id=program_id, condition=condition,
                                     base=base_by_program[program_id])
    rank_in_place(rows)
    return rows


def arm_manifest(rows: list[dict[str, Any]], *, condition: str,
                 admitted: list[str]) -> list[dict[str, Any]]:
    """ONE entry per logical arm slot. The slot exists even when nothing in it is rankable.

    An arm missing from the manifest is indistinguishable from an arm that was computed and
    found empty — so every expected slot is emitted, and its emptiness is a value.
    """
    index: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        index.setdefault(r["arm_key"], []).append(r)

    out: list[dict[str, Any]] = []
    for program_id in admitted:
        for change in arm_keys.DESIRED_CHANGES:
            key = arm_keys.direct_arm_key(program_id, change, condition)
            arm_rows = index.get(key, [])
            ranked = [r for r in arm_rows if r["rank"] is not None]
            out.append({
                "arm_key": key,
                "program_id": program_id,
                "desired_change": change,
                "condition": condition,
                "n_targets": len(arm_rows),
                "n_evaluable": sum(1 for r in arm_rows if r["evaluable"]),
                "n_ranked": len(ranked),
                "rank_rule_id": RANK_RULE_ID,
                "arm_rows_sha256": content_hash(
                    [{k: r[k] for k in ("target_id", "value", "rank", "evaluable")}
                     for r in canonical_rows(arm_rows)]),
            })
    return out


def canonical_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The arm rows, in the ONE shape their hash is taken over.

    The hash has to be re-derivable BY A READER OF THE SHIPPED PARQUET, not just by the
    process that happened to hold the rows in memory. Parquet round-trips an integer rank to
    a float and a count to int64, so hashing the in-memory dicts would bind a number nobody
    reading the file could reproduce — the same "a count nobody can recount" defect this
    lane has already been bitten by once.

    So the projection is explicit: ranks and counts are ints or None, flags are bools, values
    are canonical floats or None. Anyone can apply it to the parquet and get the bound hash.
    """
    def _int(v):
        return None if v is None or v != v else int(v)

    out = []
    for r in rows:
        out.append({
            "arm_key": str(r["arm_key"]),
            "program_id": str(r["program_id"]),
            "desired_change": str(r["desired_change"]),
            "condition": str(r["condition"]),
            "target_id": str(r["target_id"]),
            "base_delta": canonical_num(r["base_delta"]),
            "value": canonical_num(r["value"]),
            "rank": _int(r["rank"]),
            "evaluable": bool(r["evaluable"]),
            "projection_status": str(r["projection_status"]),
            "base_state": str(r["base_state"]),
            "base_passed": bool(r["base_passed"]),
            "n_panel_surviving": _int(r["n_panel_surviving"]),
            "n_control_surviving": _int(r["n_control_surviving"]),
        })
    out.sort(key=lambda r: (r["arm_key"], r["target_id"]))
    return out


def rows_sha256(rows: list[dict[str, Any]]) -> str:
    """THE arm bytes. A function of the arm rows alone — nothing pair-derived enters it."""
    return content_hash(canonical_rows(rows))


def expected_slots(admitted: list[str]) -> int:
    """|admitted programs| x 2 desired changes. DERIVED — never a copied count."""
    return len(admitted) * len(arm_keys.DESIRED_CHANGES)


def method_block(view: dict[str, Any]) -> dict[str, Any]:
    """The method, as one hashable object. Ids, enums and booleans — no prose."""
    return {
        "bundle_id": BUNDLE_ID,
        "schema_version": SCHEMA_VERSION,
        "direct_method_id": config.METHOD_ID,
        "direct_method_version": config.METHOD_VERSION,
        "rank_rule_id": RANK_RULE_ID,
        "rank_rule": RANK_RULE,
        "arm_key_rule_id": arm_keys.ARM_KEY_RULE_ID,
        "mapping_rule_id": arm_keys.MAPPING_RULE_ID,
        "arms_are_sign_transforms_of_one_base_effect": True,
        "arm_key_carries_pole_or_role": False,
        "scorer_view_id": view["view_id"],
        "scorer_view_sha256": view["scorer_view_sha256"],
        "n_admitted_programs": view["n_admitted_programs"],
        "n_expected_arm_slots": expected_slots(view["admitted_program_ids"]),
        # what is deliberately NOT in this bundle
        "pair_fields_emitted": False,
        "pareto_emitted": False,
        "concordance_emitted": False,
        "combined_objective_permitted": config.COMBINED_OBJECTIVE_PERMITTED,
        "inference_status": config.INFERENCE_STATUS,
    }


def build(*, condition: str, view: dict[str, Any],
          base_by_program: dict[str, list[dict[str, Any]]],
          rows: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    """The bundle document: the arm manifest, the counts, and what the rows hash to."""
    admitted = view["admitted_program_ids"]
    rows = build_rows(condition=condition, admitted=admitted,
                      base_by_program=base_by_program) if rows is None else rows
    manifest = arm_manifest(rows, condition=condition, admitted=admitted)
    return {
        "schema_version": SCHEMA_VERSION,
        "condition": condition,
        "method": method_block(view),
        "scorer_view": view,
        "n_arm_slots": len(manifest),
        "n_expected_arm_slots": expected_slots(admitted),
        "n_arm_rows": len(rows),
        "arms": manifest,
        "arm_rows_sha256": rows_sha256(rows),
    }
