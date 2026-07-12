"""THE JOINT ORDERING: a Pareto frontier, and the things it must never become.

The requirement was an explicit Stage-2 combined ordering that does NOT erase the two
components. Those pull against each other, and every easy way to satisfy the first
violates the second: a weighted sum, a mean, a "balanced skew", any single number that
answers both arms at once has to fix an exchange rate between "moved away from A" and
"moved toward B" that nobody has. Fix it wrongly — and there is no way to fix it rightly —
and a target that moves hard away from A while actively OPPOSING B outranks one that
genuinely moves toward B.

Dominance needs no exchange rate, so the joint ordering is a Pareto frontier:

    dominates(X, Y)  <->  X.away >= Y.away and X.toward >= Y.toward
                          and (X.away > Y.away or X.toward > Y.toward)

    tier 1 = the non-dominated set. Peel it. Repeat.

The rule was written down (``pareto.py``, and restated in ``verify_pareto.py``) BEFORE any
real ranking was looked at. That is the whole reason it is worth anything: an ordering
chosen after seeing which targets it promotes is a preference with a method's paperwork.

WHAT THE TIER IS NOT
--------------------
It is not a score. It has no units, it cannot be averaged, and two targets in one tier are
not TIED — they are INCOMPARABLE, which is the honest answer and a different one. Nothing
in the emitted screen is a combined magnitude a consumer could sort as if it were one, and
the tests below try to put one there.
"""
from __future__ import annotations

import os

import pandas as pd
import pytest
from direct import config, pareto, verify_pareto
from direct import projection as proj
from direct.run_screen import build_screen
from test_source_replay import verify

A, B = config.ARM_A, config.ARM_B
TIER, STATUS = pareto.TIER_COLUMN, pareto.STATUS_COLUMN

TIER_CHECK = "every pareto_tier re-derives from the EMITTED arm values"
STATUS_CHECK = "every joint_status re-derives from the ARM DIRECTIONS"


def row(target, away, toward, a_eval=True, b_eval=True):
    return {"target_id": target, A: away, B: toward,
            "A_evaluable": a_eval, "B_evaluable": b_eval}


def tiers(rows):
    pareto.assign_tiers(rows)
    return {r["target_id"]: r[TIER] for r in rows}


# --------------------------------------------------------------------------- #
# 1. DOMINANCE.
# --------------------------------------------------------------------------- #
def test_a_dominated_target_is_never_on_the_frontier():
    """X beats Y on both arms, so Y cannot be tier 1 no matter how good it looks."""
    t = tiers([row("X", 1.0, 1.0), row("Y", 0.5, 0.5)])
    assert t == {"X": 1, "Y": 2}


def test_the_frontier_peels_into_dense_tiers():
    t = tiers([row("T1", 3.0, 3.0), row("T2", 2.0, 2.0), row("T3", 1.0, 1.0)])
    assert t == {"T1": 1, "T2": 2, "T3": 3}


def test_two_incomparable_targets_SHARE_a_tier():
    """Better on one arm, worse on the other. Neither dominates; both are tier 1.

    This is the case a combined score exists to destroy: it would rank them, and the
    ranking would be an artefact of the weights, not of the biology.
    """
    t = tiers([row("HIGH_AWAY", 5.0, 0.1), row("HIGH_TOWARD", 0.1, 5.0)])
    assert t == {"HIGH_AWAY": 1, "HIGH_TOWARD": 1}


def test_a_target_strong_on_one_arm_cannot_dominate_a_balanced_one():
    """The retired balanced objective would have promoted A_MONSTER. Dominance does not."""
    t = tiers([row("A_MONSTER", 99.0, -50.0), row("BALANCED", 1.0, 1.0)])
    assert t["A_MONSTER"] == 1 and t["BALANCED"] == 1     # incomparable, not ordered


# --------------------------------------------------------------------------- #
# 2. TIES, BOUNDARIES, PERMUTATION.
# --------------------------------------------------------------------------- #
def test_EXACTLY_equal_points_share_a_tier():
    """Equal points do not dominate each other. Same tier — and not a broken tie."""
    t = tiers([row("P", 1.25, 2.5), row("Q", 1.25, 2.5), row("R", 1.24, 2.5)])
    assert t["P"] == t["Q"] == 1
    assert t["R"] == 2                                   # strictly worse on one arm


def test_a_float_hair_apart_is_NOT_a_tie():
    """Dominance is on the exact canonical float64 that is emitted — never a rounded one.

    Rounding first would turn distinct scores into an emitted tie, and the emitted tie
    would then contradict the tier actually assigned.
    """
    hair = 1.0 + 2 ** -52                                # the next float above 1.0
    assert hair != 1.0
    t = tiers([row("HAIR", hair, 1.0), row("ONE", 1.0, 1.0)])
    assert t == {"HAIR": 1, "ONE": 2}


def test_the_tiers_are_INVARIANT_to_input_row_order():
    """The frontier of a set is a property of the set, not of how it was listed."""
    import itertools

    base = [row("T1", 3.0, 1.0), row("T2", 1.0, 3.0), row("T3", 2.0, 2.0),
            row("T4", 0.5, 0.5), row("T5", 2.0, 2.0)]
    expected = None
    for perm in itertools.permutations(range(len(base))):
        got = tiers([dict(base[i]) for i in perm])
        expected = expected or got
        assert got == expected, perm


# --------------------------------------------------------------------------- #
# 3. NOT JOINTLY EVALUABLE -> NULL. Not tier 0, not last, not a sentinel.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("kw", [
    {"a_eval": False}, {"b_eval": False}, {"a_eval": False, "b_eval": False},
])
def test_a_target_missing_an_arm_gets_a_NULL_tier(kw):
    rows = [row("GOOD", 1.0, 1.0), row("PARTIAL", 9.0, 9.0, **kw)]
    t = tiers(rows)
    assert t["GOOD"] == 1
    assert t["PARTIAL"] is None, "a target that cannot be compared on both arms was " \
                                 "given a frontier position anyway"


def test_a_null_arm_score_is_not_jointly_evaluable():
    rows = [row("GOOD", 1.0, 1.0), row("NULLSCORE", None, 5.0)]
    assert tiers(rows)["NULLSCORE"] is None


def test_a_NON_FINITE_arm_score_is_never_compared():
    """NaN and inf are not scores. They never enter a comparison and never get a tier."""
    for bad in (float("nan"), float("inf"), float("-inf")):
        assert tiers([row("GOOD", 1.0, 1.0), row("BAD", bad, 1.0)])["BAD"] is None


def test_an_excluded_target_does_not_shift_the_frontier_of_the_others():
    """Dropping the incomparable ones must not change who is on the frontier."""
    with_partial = tiers([row("X", 2.0, 2.0), row("Y", 1.0, 1.0),
                          row("P", 9.0, 9.0, a_eval=False)])
    without = tiers([row("X", 2.0, 2.0), row("Y", 1.0, 1.0)])
    assert with_partial["X"] == without["X"] == 1
    assert with_partial["Y"] == without["Y"] == 2


# --------------------------------------------------------------------------- #
# 4. JOINT STATUS — derived from the ARM DIRECTIONS, never from the tier.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("away,toward,expected", [
    (1.0, 1.0, pareto.JOINT_BOTH),
    (1.0, -1.0, pareto.JOINT_OPPOSED),          # away from A, but AWAY from B too
    (-1.0, 1.0, pareto.JOINT_OPPOSED),
    (1.0, 0.0, pareto.JOINT_AWAY_ONLY),
    (0.0, 1.0, pareto.JOINT_TOWARD_ONLY),
    (0.0, 0.0, pareto.JOINT_NOT_EVALUABLE),     # evaluable, but no direction either way
    (-1.0, -1.0, pareto.JOINT_NOT_EVALUABLE),   # both opposing: no favorable arm at all
])
def test_joint_status_is_derived_from_the_arm_directions(away, toward, expected):
    assert pareto.joint_status(row("T", away, toward)) == expected


def test_an_OPPOSED_target_can_still_be_on_the_frontier_and_says_so():
    """The frontier is about dominance; the status is about direction. Both are emitted.

    A target that moves hard away from A while opposing B is not dominated by anything —
    nothing else matches its away value — so it IS tier 1. It is also ``opposed``, and a
    reader sees both. A combined score would have shown only the promotion.
    """
    rows = [row("OPPOSED", 9.0, -9.0), row("HONEST", 1.0, 1.0)]
    pareto.assign_tiers(rows)
    opp = next(r for r in rows if r["target_id"] == "OPPOSED")
    assert opp[TIER] == 1
    assert opp[STATUS] == pareto.JOINT_OPPOSED
    assert opp[A] == 9.0 and opp[B] == -9.0     # the components are never erased


def test_joint_status_does_not_read_the_tier():
    """Two targets in the SAME tier can have DIFFERENT statuses — proof they are
    independent derivations."""
    rows = [row("BOTH", 5.0, 0.1), row("OPP", 0.1, -5.0), row("X", 6.0, -9.0)]
    pareto.assign_tiers(rows)
    by_t = {r["target_id"]: r for r in rows}
    assert by_t["BOTH"][STATUS] == pareto.JOINT_BOTH
    assert by_t["X"][STATUS] == pareto.JOINT_OPPOSED
    assert by_t["BOTH"][TIER] == by_t["X"][TIER] == 1     # same tier, different status


def test_every_emitted_status_is_in_the_frozen_vocabulary():
    rows = [row(f"T{i}", a, b) for i, (a, b) in enumerate(
        [(1, 1), (1, -1), (-1, 1), (1, 0), (0, 1), (0, 0), (-1, -1)])]
    pareto.assign_tiers(rows)
    assert {r[STATUS] for r in rows} <= set(pareto.JOINT_STATUSES)


# --------------------------------------------------------------------------- #
# 5. THE ARMS ARE UNTOUCHED. This is the load-bearing guarantee.
# --------------------------------------------------------------------------- #
def _arm_cols(path):
    df = pd.read_parquet(path).set_index("target_id").sort_index()
    return {c: df[c] for c in
            list(config.ARMS) + list(config.ARM_RANK_COLUMN.values())}


def test_the_direct_arms_are_BYTE_IDENTICAL_with_and_without_the_joint_fields(
        synthetic_run, monkeypatch):
    """Add the joint ordering and NOTHING about either arm may move.

    The joint fields are computed from the arm values, so the only way they could feed
    back is a bug — and a bug here would be invisible: every arm score would still look
    plausible. So it is proven, not asserted. The run is built twice over identical
    inputs, once with ``assign_tiers`` replaced by a no-op, and both arms' score AND rank
    columns are compared exactly, dtype included.
    """
    with_joint = build_screen(synthetic_run())["out_dir"]

    monkeypatch.setattr(pareto, "assign_tiers", lambda rows: rows)
    without_joint = build_screen(synthetic_run())["out_dir"]

    a = _arm_cols(os.path.join(with_joint, "screen.parquet"))
    b = _arm_cols(os.path.join(without_joint, "screen.parquet"))

    # the no-op run really did omit the joint fields, or this proves nothing
    assert TIER not in pd.read_parquet(
        os.path.join(without_joint, "screen.parquet")).columns
    assert TIER in pd.read_parquet(
        os.path.join(with_joint, "screen.parquet")).columns

    for col in list(config.ARMS) + list(config.ARM_RANK_COLUMN.values()):
        pd.testing.assert_series_equal(a[col], b[col], check_dtype=True,
                                       check_names=True)


def test_assign_tiers_writes_ONLY_its_own_three_columns():
    before = row("T", 1.0, 2.0)
    before["rank_away_from_A"] = 7
    snapshot = dict(before)

    pareto.assign_tiers([before])

    added = set(before) - set(snapshot)
    assert added == set(pareto.JOINT_COLUMNS)
    for k, v in snapshot.items():
        assert before[k] == v, f"assign_tiers mutated {k}"


# --------------------------------------------------------------------------- #
# 6. NO COMBINED MAGNITUDE MAY ENTER. Tried two ways.
# --------------------------------------------------------------------------- #
def test_a_NUMERIC_combined_field_injected_into_the_screen_is_REJECTED(synthetic_run):
    """The frontier does not license a score. Injecting one must fail the contract."""
    args = synthetic_run()
    args.out_dir = build_screen(args)["out_dir"]
    path = os.path.join(args.out_dir, "screen.parquet")

    df = pd.read_parquet(path)
    df["pareto_score"] = df[A].fillna(0) + df[B].fillna(0)     # the forbidden thing
    df.to_parquet(path, index=False)

    assert verify(args, strict=False) == 1


@pytest.mark.parametrize("alias", ["balanced_skew", "combined_score", "total_skew",
                                   "mean_arm_score", "rank"])
def test_a_KNOWN_combined_alias_is_rejected_by_name(synthetic_run, alias):
    args = synthetic_run()
    args.out_dir = build_screen(args)["out_dir"]
    path = os.path.join(args.out_dir, "screen.parquet")

    df = pd.read_parquet(path)
    df[alias] = 1.0
    df.to_parquet(path, index=False)

    assert verify(args, strict=False) == 1


def test_the_emitted_screen_carries_no_field_a_consumer_could_sort_as_a_score(
        synthetic_run):
    """The joint ordering contributes a tier and a label. Nothing else."""
    result = build_screen(synthetic_run())
    df = pd.read_parquet(os.path.join(result["out_dir"], "screen.parquet"))

    joint = set(pareto.JOINT_COLUMNS)
    assert joint <= set(df.columns)
    # of the three, exactly one is numeric — and it is a nullable INTEGER tier
    numeric = {c for c in joint if str(df[c].dtype) not in ("object", "string")}
    assert numeric == {TIER}
    assert str(df[TIER].dtype) == "Int64"
    assert set(df[TIER].dropna().unique()) <= set(range(1, len(df) + 1))


# --------------------------------------------------------------------------- #
# 7. A DOWNSTREAM TIER REWRITE. One cell edit; nothing else in the lane can see it.
# --------------------------------------------------------------------------- #
def test_a_REWRITTEN_tier_is_caught_by_the_standalone_verifier(synthetic_run):
    """Promote a target to the frontier after emission.

    Every arm score stays right. Every arm rank stays right. Every hash stays right — the
    tier is not what the ranks were derived from, so nothing else in the run contradicts
    it. It is caught only because the verifier RE-DERIVES the tier from the emitted arm
    values, by a rule it restates rather than imports.
    """
    args = synthetic_run()
    args.out_dir = build_screen(args)["out_dir"]
    path = os.path.join(args.out_dir, "screen.parquet")

    df = pd.read_parquet(path)
    victim = df[df[TIER].notna() & (df[TIER] > 1)]["target_id"].iloc[0]
    df.loc[df["target_id"] == victim, TIER] = 1        # a single cell
    df.to_parquet(path, index=False)

    from direct.verify_run import Report, reconstruct
    rep = Report()
    reconstruct(args.out_dir, os.path.dirname(args.selection), rep, strict=False)
    failed = [n for n, _d in rep.failures]

    assert TIER_CHECK in failed, failed
    # ...and it is NOT an incidental hash / rank / schema failure
    assert not [c for c in failed if "sha256" in c or "rank" in c]
    assert verify(args, strict=False) == 1


def test_a_REWRITTEN_joint_status_is_caught(synthetic_run):
    args = synthetic_run()
    args.out_dir = build_screen(args)["out_dir"]
    path = os.path.join(args.out_dir, "screen.parquet")

    df = pd.read_parquet(path)
    victim = df[df[STATUS] != pareto.JOINT_BOTH]["target_id"].iloc[0]
    df.loc[df["target_id"] == victim, STATUS] = pareto.JOINT_BOTH
    df.to_parquet(path, index=False)

    from direct.verify_run import Report, reconstruct
    rep = Report()
    reconstruct(args.out_dir, os.path.dirname(args.selection), rep, strict=False)
    assert STATUS_CHECK in [n for n, _d in rep.failures]


def test_a_tier_granted_to_a_NON_JOINTLY_EVALUABLE_target_is_caught(synthetic_run):
    """The null is load-bearing: it is what keeps un-comparable targets off the frontier."""
    args = synthetic_run()
    args.out_dir = build_screen(args)["out_dir"]
    path = os.path.join(args.out_dir, "screen.parquet")

    df = pd.read_parquet(path)
    orphans = df[df[TIER].isna()]
    assert not orphans.empty, "the fixture no longer exercises a null tier"
    df.loc[df["target_id"] == orphans["target_id"].iloc[0], TIER] = 1
    df.to_parquet(path, index=False)

    from direct.verify_run import Report, reconstruct
    rep = Report()
    reconstruct(args.out_dir, os.path.dirname(args.selection), rep, strict=False)
    failed = [n for n, _d in rep.failures]
    assert "no scope that is not jointly evaluable carries a tier" in failed


# --------------------------------------------------------------------------- #
# 8. THE VERIFIER RESTATES THE RULE — it does not import it.
# --------------------------------------------------------------------------- #
def test_the_verifier_agrees_with_the_generator_on_a_shared_population():
    """Two implementations, written separately, must land on the same frontier."""
    rows = [row("T1", 3.0, 1.0), row("T2", 1.0, 3.0), row("T3", 2.0, 2.0),
            row("T4", 0.5, 0.5), row("T5", 2.0, 2.0), row("T6", 9.0, -9.0),
            row("T7", 1.0, 1.0, b_eval=False)]
    generated = tiers([dict(r) for r in rows])
    restated = verify_pareto.derive_tiers([dict(r) for r in rows])
    assert generated == restated

    for r in rows:
        assert pareto.joint_status(r) == verify_pareto.joint_status(r)


def test_the_two_method_ids_are_the_same_frozen_id():
    assert pareto.METHOD_ID == verify_pareto.METHOD_ID == \
        "spot.stage02.pareto.two_arm.v1"
    assert pareto.METHOD_ID          # non-empty, as the contract requires


def test_the_ranks_are_still_per_arm_and_the_tier_is_not_a_rank():
    """A tier is not an arm rank and must never be mistaken for one."""
    rows = [row("T1", 3.0, 1.0), row("T2", 1.0, 3.0), row("T3", 2.0, 2.0)]
    for arm in config.ARMS:
        proj.rank_arm(rows, arm, evaluable_key=f"{config.ARM_POLE[arm]}_evaluable",
                      rank_column=config.ARM_RANK_COLUMN[arm])
    pareto.assign_tiers(rows)

    by_t = {r["target_id"]: r for r in rows}
    # T1 is rank 1 away, rank 3 toward, and tier 1 — three different numbers, all true
    assert by_t["T1"]["rank_away_from_A"] == 1
    assert by_t["T1"]["rank_toward_B"] == 3
    assert by_t["T1"][TIER] == 1
