"""Stage-2's numbers leave Stage 3 exactly as they arrived. Byte for byte.

Stage 2 owns the ranks, the arm values, ``joint_status`` and ``pareto_tier``. Stage 3 is a
CONSUMER of them. It may carry them, key on them, and refuse without them — it may never
recompute, reorder, rescale, re-tier or "improve" them. A stage that quietly re-derives
its input's ordering is no longer annotating that input; it is replacing it, while still
citing it.

So this is asserted on the emitted fixture bundle, not inspected by eye: snapshot the
Stage-2-owned values BEFORE Stage 3 runs, and compare them to what actually lands in the
parquet AFTER. Anything that differs is a defect, not a judgement call.
"""
from __future__ import annotations

import os

import pandas as pd
import pytest

from druglink import armlever, artifacts, joint_context

# Stage-2-owned, in the emitted rows. Stage 3 never writes these; it copies them.
STAGE2_OWNED = ("arm_value_source_string", "arm_delta_source_string", "arm_rank")
JOINT_OWNED = ("joint_status", "pareto_tier", "joint_ordering_method_id")


def _upstream(screen: pd.DataFrame) -> dict[tuple[str, str], dict[str, str]]:
    """The Stage-2 values as they arrive, rendered EXACTLY, before Stage 3 touches them."""
    snapshot: dict[tuple[str, str], dict[str, str]] = {}
    for row in screen.to_dict("records"):
        for arm in armlever.ARMS:
            rank = row[armlever.ARM_RANK_COLUMN[arm]]
            value = row[arm]
            snapshot[(row["target_id"], arm)] = {
                # repr() of the raw cell — if Stage 3 alters a single bit, this differs.
                # An estimate Stage 2 never made is ABSENT, and stays absent: it must not
                # arrive downstream as a zero, and must not be repaired into a number.
                "value": None if pd.isna(value) else repr(value),
                "rank": None if pd.isna(rank) else int(rank),
            }
    return snapshot


# --------------------------------------------------------------------------- #
# Ranks and arm values: byte-identical, before vs after.
# --------------------------------------------------------------------------- #
def test_stage2_ranks_and_arm_values_are_byte_identical_after_stage3(
        tmp_path, loaded_direct, analysis_build):
    """The invariant, asserted on the SERIALIZED bundle a consumer really reads."""
    before = _upstream(loaded_direct.screen)

    bundle = artifacts.write_bundle(
        output_root=str(tmp_path / "out"), artifact_class="analysis",
        document=analysis_build["document"], doc_id=analysis_build["document_id"],
        tables=analysis_build["tables"], created_at="2026-07-12T00:00:00+00:00")
    levers = pd.read_parquet(os.path.join(bundle, "arm_levers.parquet"))

    assert not levers.empty, "an empty table proves nothing"
    checked = 0

    for row in levers.to_dict("records"):
        key = (row["target_id"], row["desired_arm"])
        want = before.get(key)
        assert want is not None, f"Stage 3 emitted a row Stage 2 never released: {key}"

        # The arm VALUE, verbatim. Stage 3 stores the source string precisely so this
        # comparison is possible: a value that survives as a float is a value nobody can
        # check.
        assert row["arm_value_source_string"] == want["value"], (
            f"{key}: Stage 3 CHANGED a Stage-2 arm value — "
            f"{want['value']!r} became {row['arm_value_source_string']!r}")

        # The RANK, verbatim — including a null rank, which stays null.
        got = row["arm_rank"]
        got = None if pd.isna(got) else int(got)
        assert got == want["rank"], (
            f"{key}: Stage 3 CHANGED a Stage-2 rank — {want['rank']} became {got}")
        checked += 1

    assert checked >= 2, "the invariant must be exercised on real rows"


def test_stage3_never_reorders_a_stage2_rank(loaded_direct, analysis_build):
    """Carrying a rank is allowed. Re-deriving one is not.

    Stage 3 picks levers in rank order — but the ORDER it reads must be the order Stage 2
    released, never one Stage 3 recomputed from a value it prefers.
    """
    levers = analysis_build["tables"]["arm_levers"]
    upstream = _upstream(loaded_direct.screen)

    for arm in armlever.ARMS:
        rows = [r for r in levers if r["desired_arm"] == arm
                and r["arm_rank"] is not None]
        for row in rows:
            assert row["arm_rank"] == upstream[(row["target_id"], arm)]["rank"]


# --------------------------------------------------------------------------- #
# joint_status / pareto_tier: copied verbatim, never re-derived.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("status", joint_context.JOINT_STATUS_VALUES)
@pytest.mark.parametrize("tier", [1, 2, 7, None])
def test_joint_status_and_pareto_tier_pass_through_verbatim(status, tier):
    """Every value of the closed enum, and a null tier, survive untouched."""
    row = {"joint_status": status, "pareto_tier": tier,
           "joint_ordering_method_id": "stage2.pareto.v3"}
    carried = joint_context.from_screen_row(row)

    assert carried["joint_status"] == status
    assert carried["pareto_tier"] == tier
    assert carried["joint_ordering_method_id"] == "stage2.pareto.v3"
    # A tier is an ordinal Stage 2 assigned. Stage 3 does not make it a score.
    assert carried["pareto_tier"] is None or isinstance(carried["pareto_tier"], int)


def test_stage3_refuses_to_alter_a_stage2_joint_value():
    """A tier Stage 3 cannot read is a refusal, never a repaired or invented one."""
    for bad_tier in (0, -1, 1.5, "1", True):
        with pytest.raises(joint_context.JointContextError):
            joint_context.from_screen_row({"pareto_tier": bad_tier})

    for bad_status in ("promising", "tier_1", "both", ""):
        with pytest.raises(joint_context.JointContextError):
            joint_context.from_screen_row({"joint_status": bad_status})


def test_the_joint_status_enum_stays_closed_at_five_values():
    assert joint_context.JOINT_STATUS_VALUES == (
        "both_arms", "away_from_A_only", "toward_B_only", "opposed", "not_evaluable")


def test_joint_context_is_carried_verbatim_or_left_honestly_absent(
        loaded_direct, analysis_build):
    """Whatever Stage 2 says about joint context, Stage 3 repeats — or admits it wasn't said.

    Both worlds are asserted, because Stage 2 is expected to start releasing joint context
    and this invariant must hold across that change rather than being rewritten after it:

      * Stage 2 RELEASES it  -> every value is carried byte-identically, per target.
      * Stage 2 is SILENT    -> the field is emitted as absent. Stage 3 does not
        synthesise a joint_status from the two arms it CAN see, and does not tier what it
        was not given.
    """
    cross = analysis_build["tables"]["cross_arm"]
    assert cross, "the cross-arm table must exist to make this claim"

    screen = loaded_direct.screen
    released = [f for f in JOINT_OWNED if f in screen.columns]

    if released:
        # Pass-through, byte for byte, against the row Stage 2 actually released.
        upstream = {row["target_id"]: row for row in screen.to_dict("records")}
        for row in cross:
            source = upstream[row["target_id"]]
            for field in released:
                want = source[field]
                want = None if pd.isna(want) else want
                assert row[field] == want, (
                    f"{row['target_id']}: Stage 3 CHANGED a Stage-2 {field} — "
                    f"{want!r} became {row[field]!r}")
        return

    # Stage 2 is silent. Absence is recorded as absence, never filled in with a guess.
    for row in cross:
        for field in JOINT_OWNED:
            assert row[field] is None, (
                f"Stage 3 INVENTED a Stage-2 joint value for {field}: {row[field]!r}")

    # The run-level record says the same thing in words, so a reader is never left to
    # infer that a null meant "not applicable" rather than "Stage 2 never said".
    joint = analysis_build["document"]["stage2_joint_context"]
    assert joint["stage2_joint_context"] == joint_context.NOT_PROVIDED
    assert joint["rewritten_by_stage3"] is False
    assert joint["used_to_rank_or_filter_arms"] is False
