"""STAGE-1's IDENTITIES, re-derived — and every Stage-1-READY selection, accepted.

Two things no fixture of our own can prove:

  1. that Stage-3's INDEPENDENT re-derivation of `question_id` / `selection_id` reproduces the
     numbers STAGE-1 ACTUALLY EMITTED. A fixture checked only against itself proves only that its
     author agreed with themselves, so these tests read Stage-1's REAL bytes out of git;
  2. that no selection Stage-1 calls READY is refused here. A gate that turns away a valid
     scientific question is as much a defect as one that admits an invalid one — it just fails in
     the direction that looks safe.
"""
from __future__ import annotations

import json
import os

import pytest
import selection_fixture as SF

from druglink import arm_selection as asel
from druglink import selection_v3 as s3
from druglink import selection_view as sv
from druglink import view_contract as vc

from selection_world import (             # the ONE sealed store, built once
    STAGE3, TEMPORAL, WITHIN, _conditions, _programs, _selection, _verified, _view,
)

# =========================================================================== #
# STAGE-1's REAL BYTES. Not a fixture of our own — a fixture checked only against
# itself proves only that its author agreed with themselves.
# =========================================================================== #
STAGE1_COMMIT = "539431d"
STAGE1_FIXTURES = "01_programs/analysis/stage2_bridge/fixtures"

# The pins. Recomputed here from Stage-1's own emitted contract, byte for byte.
REAL_TEMPORAL_QUESTION_ID = "3203d63970720d4f"
REAL_TEMPORAL_SELECTION_ID = "7a77f6b314b9c0f3"


def _stage1_bytes(name):
    """Stage-1's REAL contract, read out of git. Skips if this worktree cannot reach it."""
    import subprocess
    for repo in (STAGE3, os.path.abspath(os.path.join(STAGE3, "..")),
                 "/home/tcelab/worktrees/spot-stage2-w3"):
        try:
            out = subprocess.run(
                ["git", "show", f"{STAGE1_COMMIT}:{STAGE1_FIXTURES}/{name}"],
                cwd=repo, capture_output=True, check=True).stdout
            return json.loads(out)
        except (subprocess.CalledProcessError, FileNotFoundError, ValueError):
            continue
    pytest.skip(f"Stage-1 {STAGE1_COMMIT}:{name} is not reachable from this host")


class TestBothIdentitiesRederiveFromStage1sOwnBytes:
    """The whole point of an independent re-derivation: it must reproduce SOMEONE ELSE'S number."""

    def test_the_question_id_recomputes_from_stage1s_REAL_temporal_contract(self):
        doc = _stage1_bytes("stage01_selection_temporal_ready_example.json")
        assert doc["question_id"] == REAL_TEMPORAL_QUESTION_ID          # the pin, from THEIR bytes
        assert s3.derive_question_id(doc) == doc["question_id"]
        # 16 LOWERCASE HEX — not the 64-hex form.
        assert len(doc["question_id"]) == 16
        # ...and the CONDITION is inside each pole. Drop it and the two questions collide.
        content = s3.question_content(doc)
        assert content["A"]["condition"] == doc["canonical_content"]["conditions"][0]
        assert content["B"]["condition"] == doc["canonical_content"]["conditions"][-1]

    def test_the_selection_id_recomputes_from_stage1s_REAL_temporal_contract(self):
        doc = _stage1_bytes("stage01_selection_temporal_ready_example.json")
        assert doc["selection_id"] == REAL_TEMPORAL_SELECTION_ID
        assert s3.derive_selection_id(doc) == doc["selection_id"]
        assert s3.derive_selection_full_sha256(doc) == doc["selection_full_sha256"]

    def test_both_identities_recompute_from_stage1s_REAL_within_contract(self):
        doc = _stage1_bytes("stage01_selection_within_ready_example.json")
        assert s3.derive_question_id(doc) == doc["question_id"]
        assert s3.derive_selection_id(doc) == doc["selection_id"]

    def test_the_two_identities_are_DISTINCT_and_answer_different_questions(self):
        doc = _stage1_bytes("stage01_selection_temporal_ready_example.json")
        assert doc["question_id"] != doc["selection_id"]
        # question_id is BIOLOGY-ONLY: bump the method and the QUESTION does not move...
        bumped = json.loads(json.dumps(doc))
        bumped["canonical_content"]["stage1_method_version"] = "stage1-continuous-v9.9.9"
        assert s3.derive_question_id(bumped) == doc["question_id"]
        # ...but the RUN does. Binding only one would let a method bump look like a new
        # question, or let a stale run masquerade as the current one.
        assert s3.derive_selection_id(bumped) != doc["selection_id"]

    def test_the_condition_INSIDE_the_pole_is_what_separates_two_cross_time_questions(self):
        """Same program, same direction, two different times. Drop the condition -> ONE id."""
        doc = _stage1_bytes("stage01_selection_temporal_ready_example.json")
        same = json.loads(json.dumps(doc))
        cc = same["canonical_content"]
        cc["B"] = dict(cc["A"])                       # SAME program, SAME direction as A
        ids = set()
        for conditions in (["Rest", "Stim8hr"], ["Stim8hr", "Stim48hr"]):
            cc["conditions"] = conditions
            ids.add(s3.derive_question_id(same))
        assert len(ids) == 2, (
            "two cross-time questions on the same program+direction at DIFFERENT times collapsed "
            "to one question_id — the condition was dropped from the pole")
        # And the naive derivation that omits the condition really does collapse them:
        naive = {"A": {"program_id": cc["A"]["program_id"],
                       "direction": cc["A"]["direction"]},
                 "B": {"program_id": cc["B"]["program_id"],
                       "direction": cc["B"]["direction"]},
                 "analysis_mode": cc["analysis_mode"]}
        assert naive["A"] == naive["B"]               # <- one pole compared with itself


# =========================================================================== #
# ARBITRARY-SELECTION PARITY. No Stage-1-READY tuple may unexpectedly fail.
#
# A gate that refuses a VALID scientific question is as much a defect as one that admits an
# invalid one — it just fails in the direction that looks safe.
# =========================================================================== #
def _stage1_ready_tuples(programs, conditions):
    """Every ordered selection Stage-1 calls READY.

    Stage-1's ONLY self-comparison refusal (emit_selection_contract.build_contract,
    `objective_incompatible_same_pole`) is: same program AND same direction AND within_condition.
    Same program + same direction at DIFFERENT times is explicitly a VALID temporal comparison —
    the condition disambiguates the poles.
    """
    poles = [(p, d) for p in programs for d in ("high", "low")]
    out = []
    for (ap, ad) in poles:
        for (bp, bd) in poles:
            for c in conditions:
                if not (ap == bp and ad == bd):        # Stage-1's within-condition refusal
                    out.append((ap, ad, bp, bd, WITHIN, [c]))
            for frm in conditions:
                for to in conditions:
                    if frm != to:                      # every ORDERED pair; identical poles OK
                        out.append((ap, ad, bp, bd, TEMPORAL, [frm, to]))
    return out


class TestNoStage1ReadySelectionUnexpectedlyFails:

    def test_EVERY_stage1_ready_tuple_resolves(self, world):
        programs, conditions = _programs(world), _conditions(world)
        tuples = _stage1_ready_tuples(programs, conditions)
        # Stage-2's OWN published capacity: 3 x 20 x 19 within + 6 x 20 x 20 temporal.
        assert len(tuples) == 3540, len(tuples)

        shared = 0
        for a, ad, b, bd, mode, conds in tuples:
            sel = _verified(world, a=a, b=b, mode=mode, conditions=conds,
                            a_dir=ad, b_dir=bd)
            arms = asel.resolve(sel, world["aggregate"], manifest=world["manifest"])
            assert len(arms.gene_arm_keys) in (1, 2)
            shared += arms.one_arm_carries_both_roles
        # ...and the one-arm-both-roles case really OCCURS, so the support is not vacuous.
        assert shared > 0, "no ready tuple exercised the shared-arm case"

    def test_a_shared_arm_carries_BOTH_roles_and_is_not_double_counted(self, world):
        """away_from_A(high) and toward_B(low) are BOTH `decrease`: ONE reusable arm, two roles."""
        programs, conditions = _programs(world), _conditions(world)
        sel = _verified(world, a=programs[2], b=programs[2], mode=WITHIN,
                        conditions=[conditions[0]], a_dir="high", b_dir="low")
        arms = asel.resolve(sel, world["aggregate"], manifest=world["manifest"])
        assert arms.one_arm_carries_both_roles
        assert len(arms.gene_arm_keys) == 1                       # ONE arm...
        assert arms.roles_of(arms.a.arm_key) == ["away_from_A", "toward_B"]   # ...TWO roles

        view = _view(world, sel)
        vc.validate(view)
        assert view["tables"]["target_drug_edges"]
        assert view["selected_arms"]["one_arm_carries_both_roles"] is True
        for edge in view["tables"]["target_drug_edges"]:
            assert edge["selection_roles"] == ["away_from_A", "toward_B"]
        # The arm is listed ONCE in the edge table — not duplicated per role.
        assert len({e["edge_id"] for e in view["tables"]["target_drug_edges"]}) == \
            len(view["tables"]["target_drug_edges"])

    def test_same_program_same_direction_CROSS_TIME_is_ready_and_gives_TWO_arms(self, world):
        """Stage-1 admits it; the condition disambiguates the poles. Two independent arms."""
        programs, conditions = _programs(world), _conditions(world)
        sel = _verified(world, a=programs[3], b=programs[3], mode=TEMPORAL,
                        conditions=[conditions[0], conditions[2]], a_dir="high", b_dir="high")
        arms = asel.resolve(sel, world["aggregate"], manifest=world["manifest"])
        # away_from_A(high) -> decrease ; toward_B(high) -> increase. Two arms, one program.
        assert arms.a.desired_change == "decrease"
        assert arms.b.desired_change == "increase"
        assert not arms.one_arm_carries_both_roles
        assert len(arms.gene_arm_keys) == 2
        # The POLES differ only in their condition — A at the from end, B at the to end.
        assert sel.pole(s3.ROLE_A)["condition"] == conditions[0]
        assert sel.pole(s3.ROLE_B)["condition"] == conditions[2]
        view = _view(world, sel)
        vc.validate(view)
        assert view["tables"]["target_drug_edges"]


def test_a_RESEALED_selection_over_the_WRONG_store_is_still_refused(world):
    """A forger with repo access recomputes every id, and the contract agrees with itself
    perfectly. The ids are therefore NOT the last gate: an internally flawless selection over a
    release it was never minted against is still scientifically wrong."""
    programs, conditions = _programs(world), _conditions(world)
    doc = _selection(world, a=programs[0], b=programs[1], mode=WITHIN,
                     conditions=[conditions[0]])
    doc["canonical_content"]["registry_scorer_view_sha256"] = "9" * 64   # ANOTHER release
    # ...and RE-SEAL all four identities, exactly as the forger would.
    doc = SF.selection(
        a_program=programs[0], a_direction="high", b_program=programs[1], b_direction="high",
        analysis_mode=WITHIN, conditions=[conditions[0]], registry_view_sha256="9" * 64)
    verified = s3.verify(doc)                    # internally CONSISTENT: every id re-derives
    assert s3.derive_question_id(doc) == doc["question_id"]
    assert s3.derive_selection_id(doc) == doc["selection_id"]
    with pytest.raises(sv.SelectionViewError) as exc:
        _view(world, verified)
    assert sv.GATE_STALE_SELECTION in str(exc.value)
