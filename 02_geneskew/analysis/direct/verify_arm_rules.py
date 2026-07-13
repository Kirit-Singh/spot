"""The REUSABLE-ARM rules, REIMPLEMENTED from ROUND4_ADDENDUM.md (sha c4773562).

INDEPENDENCE RULE (test-enforced): this module imports NOTHING from the generator —
not ``arm_keys``, not ``arm_bundle``, not ``run_arms``, not ``scorer_view``, and not the
producer's hashing helpers. Every rule below is re-derived from the addendum's own text,
because a rule the checker borrows from the thing it is checking is a rule nobody checked.

M4b is the reason this module exists in the shape it does. The pair-bound verifier held a
STALE copy of a rule the generator had already fixed, the two disagreed, and a valid run
was refused over a DISPLAY label. Two lessons, both encoded here:

  * an independent reimplementation must be re-derived FROM THE SPEC, and updated with it;
  * a pair-derived quantity — Pareto, concordance, ``joint_status`` — is a function of TWO
    arms and therefore cannot decide whether ONE of them is admissible. Here they are not
    "off": they are FORBIDDEN, and ``forbidden_hits`` refuses a bundle that carries one.

THE FROZEN MAPPING, quoted from the addendum:

    away_from_A(high) -> decrease        toward_B(high) -> increase
    away_from_A(low)  -> increase        toward_B(low)  -> decrease
"""
from __future__ import annotations

import hashlib
import json
import math
import re
from typing import Any, Iterable, Optional


# --------------------------------------------------------------------------- #
# Canonical serialisation. Restated, not imported.
# --------------------------------------------------------------------------- #
def canonical_json(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def content_sha256(obj: Any) -> str:
    return sha256_hex(canonical_json(obj))


def sha256_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def canonical_num(x: Any) -> Optional[float]:
    """The canonical scientific value: full float64, or null. Never display-rounded.

    Non-finite values are not scores — NaN and +-inf become null and are never ranked.
    """
    if x is None:
        return None
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(xf) or math.isinf(xf):
        return None
    return xf


def canonical_int(x: Any) -> Optional[int]:
    """Parquet round-trips an integer rank to a float and a count to int64.

    So the projection is explicit: a rank or a count is an int or it is null. A hash taken
    over the in-memory dicts would bind a number nobody reading the shipped file could
    reproduce — the "count nobody can recount" defect, again.
    """
    if x is None:
        return None
    try:
        xf = float(x)
    except (TypeError, ValueError):
        return None
    if math.isnan(xf) or math.isinf(xf):
        return None
    return int(xf)


class ArmRuleError(ValueError):
    """The arm rule cannot be applied. Refuse; never guess — a guessed direction is a
    sign error nobody sees."""


# --------------------------------------------------------------------------- #
# The roles and poles (SELECTION metadata — never part of an arm key) and the one
# thing that IS: the perturbation's desired change.
# --------------------------------------------------------------------------- #
ROLE_AWAY, ROLE_TOWARD = "away_from_A", "toward_B"
ROLES = (ROLE_AWAY, ROLE_TOWARD)
POLE_HIGH, POLE_LOW = "high", "low"
POLES = (POLE_HIGH, POLE_LOW)

INCREASE, DECREASE = "increase", "decrease"
DESIRED_CHANGES = (INCREASE, DECREASE)

# The four addendum lines, transcribed. No default: an unknown combination is refused.
DESIRED_CHANGE_BY_ROLE_AND_POLE: dict[tuple[str, str], str] = {
    (ROLE_AWAY, POLE_HIGH): DECREASE,
    (ROLE_AWAY, POLE_LOW): INCREASE,
    (ROLE_TOWARD, POLE_HIGH): INCREASE,
    (ROLE_TOWARD, POLE_LOW): DECREASE,
}

# The sign each desired change applies to the ONE base effect.
SIGN = {INCREASE: 1, DECREASE: -1}

KIND_DIRECT = "direct"


def desired_change(role: str, pole: str) -> str:
    try:
        return DESIRED_CHANGE_BY_ROLE_AND_POLE[(str(role), str(pole))]
    except KeyError:
        raise ArmRuleError(
            f"no desired_change for role={role!r} pole={pole!r}; the mapping is exactly "
            f"{sorted(DESIRED_CHANGE_BY_ROLE_AND_POLE)}") from None


def _change(value: Any) -> str:
    v = str(value)
    if v not in DESIRED_CHANGES:
        hint = ""
        if v in POLES:
            hint = (" — that is a POLE. The same pole is an increase in one role and a "
                    "decrease in the other, which is exactly why it may not key an arm")
        elif v in ROLES:
            hint = " — that is a ROLE, and a role belongs to a QUESTION, not to an arm"
        raise ArmRuleError(
            f"desired_change must be one of {list(DESIRED_CHANGES)}, got {value!r}{hint}")
    return v


def _part(value: Any, what: str) -> str:
    v = str(value)
    if not v or "|" in v:
        raise ArmRuleError(f"{what} {value!r} is empty or contains the separator '|'")
    return v


def direct_arm_key(program_id: str, change: str, condition: str) -> str:
    """``direct|program|desired_change|condition``. No pole. No role."""
    return "|".join((KIND_DIRECT, _part(program_id, "program_id"), _change(change),
                     _part(condition, "condition")))


def expected_arm_keys(admitted: Iterable[str], condition: str) -> list[str]:
    """THE arm inventory a Direct condition bundle owes: every admitted program's two
    arms. DERIVED from the admitted set — never a copied list, never a copied count."""
    return sorted(direct_arm_key(p, c, condition)
                  for p in admitted for c in DESIRED_CHANGES)


def expected_slots(admitted: Iterable[str]) -> int:
    return len(list(admitted)) * len(DESIRED_CHANGES)


def arm_value(base_delta: Any, change: str) -> Optional[float]:
    """The arm's value: an EXACT sign transform of the ONE base effect.

    ``increase`` is the base; ``decrease`` is its negation. Not a re-estimate — so the two
    arms of a program in a context cannot disagree about a magnitude they share. ``0.0``
    negates to ``0.0``, never ``-0.0``: the data makes no such distinction and it would
    print as a different number.
    """
    sign = SIGN[_change(change)]
    v = canonical_num(base_delta)
    if v is None:
        return None
    return 0.0 if v == 0 else sign * v


# --------------------------------------------------------------------------- #
# THE FROZEN RANK CONTRACT, restated (addendum: the ranks are taken SEPARATELY per arm,
# because a rank is a statement about a population and negating the values genuinely
# reverses the order).
#
#   population : this arm's evaluable rows whose canonical value is non-null and finite;
#   direction  : descending — the largest arm value is rank 1;
#   tie-break  : target_id ascending, on exactly equal canonical values;
#   numbering  : dense 1..n; every other row is null — a target the arm could not score
#                is ABSENT from the ranking. It is not a zero and it is not last.
# --------------------------------------------------------------------------- #
RANK_DIRECTION = "descending"
RANK_TIE_BREAK = "target_id_ascending"
RANK_NULL_RULE = "not_evaluable_or_null_or_nonfinite_value -> null rank"


def is_rankable(row: dict) -> bool:
    return bool(row.get("evaluable")) and canonical_num(row.get("value")) is not None


def rank_arm(rows: list[dict]) -> dict[str, Optional[int]]:
    """The ranks of ONE arm, as {target_id: rank|None}. Order-invariant."""
    rankable = [r for r in rows if is_rankable(r)]
    rankable.sort(key=lambda r: (-canonical_num(r["value"]), str(r["target_id"])))
    ranks: dict[str, Optional[int]] = {str(r["target_id"]): None for r in rows}
    for i, r in enumerate(rankable, start=1):
        ranks[str(r["target_id"])] = i
    return ranks


# --------------------------------------------------------------------------- #
# The canonical arm-row projection: the ONE shape the bound hash is taken over, and the
# only one a reader of the SHIPPED parquet can reproduce.
# --------------------------------------------------------------------------- #
ARM_ROW_COLUMNS = (
    "arm_key", "program_id", "desired_change", "condition", "target_id",
    "base_delta", "value", "rank", "evaluable", "projection_status",
    "base_state", "base_passed", "n_panel_surviving", "n_control_surviving",
)
# The run id is stamped onto every shipped row but is NOT hashed: it is a function of the
# rows, so hashing it into them would be circular.
ARM_ROW_EXTRA_COLUMNS = ("arm_bundle_run_id",)

_STR_COLS = ("arm_key", "program_id", "desired_change", "condition", "target_id",
             "projection_status", "base_state")
_NUM_COLS = ("base_delta", "value")
_INT_COLS = ("rank", "n_panel_surviving", "n_control_surviving")
_BOOL_COLS = ("evaluable", "base_passed")


def canonical_rows(rows: Iterable[dict]) -> list[dict]:
    out = []
    for r in rows:
        row = {c: str(r[c]) for c in _STR_COLS}
        row.update({c: canonical_num(r[c]) for c in _NUM_COLS})
        row.update({c: canonical_int(r[c]) for c in _INT_COLS})
        row.update({c: bool(r[c]) for c in _BOOL_COLS})
        out.append(row)
    out.sort(key=lambda r: (r["arm_key"], r["target_id"]))
    return out


def rows_sha256(rows: Iterable[dict]) -> str:
    """THE arm bytes: a function of the arm rows ALONE. Nothing pair-derived enters it,
    so no display-time choice can change what a cached arm IS."""
    return content_sha256(canonical_rows(rows))


def arm_rows_sha256(rows: Iterable[dict]) -> str:
    """One arm's bytes, over the four fields the bundle's per-arm hash is taken on."""
    return content_sha256([{k: r[k] for k in ("target_id", "value", "rank", "evaluable")}
                           for r in canonical_rows(rows)])


# --------------------------------------------------------------------------- #
# WHAT A REUSABLE ARM MAY NOT CARRY (addendum: pair-derived views are join-time only).
#
# These are not "defaulted off" — they must be ABSENT. A field that is not emitted cannot
# come back as a gate in a later pass, and that is exactly what M4b was.
# --------------------------------------------------------------------------- #
FORBIDDEN_PATTERNS = (
    # pair-derived orderings and labels
    "pareto", "concordance", "concordant", "discordant", "joint_status", "joint_tier",
    "headline", "away_from_a", "toward_b",
    # a combined objective under ANY name
    "combined", "balanced", "weighted", "overall",
    # inference this lane does not calibrate
    "p_value", "pvalue", "pval", "q_value", "qvalue", "qval", "padj", "adj_p",
    "fdr", "benjamini", "bonferroni",
)

# The bundle is allowed — required, in fact — to SAY what it refuses to emit. A check that
# could not tell a disclosure from an emission would force it to stop declaring.
NEGATIVE_DECLARATIONS: dict[str, Any] = {
    "pareto_emitted": False,
    "concordance_emitted": False,
    "pair_fields_emitted": False,
    "combined_objective_permitted": False,
    "combined_arm_score_permitted": False,
    "arm_key_carries_pole_or_role": False,
    "names_a_program_pair": False,
    "pair_selection_is_compatibility_only": True,
}

_TOKEN = re.compile(r"[^a-z0-9]+")


def _matches(text: str) -> list[str]:
    low = _TOKEN.sub("_", str(text).lower())
    return [p for p in FORBIDDEN_PATTERNS if p in low]


def forbidden_hits(obj: Any, path: str = "$") -> list[str]:
    """Every display-only / pair-derived / inference field in ``obj``, RECURSIVELY.

    A negative declaration (``pareto_emitted: false``) is allowed at its required value
    and refused at any other — a bundle that flipped one to ``true`` would be announcing
    the very thing it is forbidden to do.
    """
    hits: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            here = f"{path}.{key}"
            if key in NEGATIVE_DECLARATIONS:
                if value != NEGATIVE_DECLARATIONS[key]:
                    hits.append(f"{here}: negative declaration is "
                                f"{value!r}, must be "
                                f"{NEGATIVE_DECLARATIONS[key]!r}")
                continue
            for pattern in _matches(key):
                hits.append(f"{here}: forbidden field (matches {pattern!r})")
            hits += forbidden_hits(value, here)
    elif isinstance(obj, (list, tuple)):
        for i, value in enumerate(obj):
            hits += forbidden_hits(value, f"{path}[{i}]")
    elif isinstance(obj, str):
        for pattern in _matches(obj):
            hits.append(f"{path}: forbidden token {pattern!r} in a string value")
    return hits


def forbidden_columns(columns: Iterable[str]) -> list[str]:
    """A pair-derived COLUMN is refused outright: no negative declaration lives in a
    table, so a column bearing one of these names is an emission, full stop."""
    out = []
    for col in columns:
        for pattern in _matches(col):
            out.append(f"column {col!r} (matches {pattern!r})")
    return out
