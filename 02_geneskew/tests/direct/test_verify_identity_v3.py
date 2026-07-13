"""The RUN VERIFIER could not verify a v3 run's identity — and nothing noticed.

``verify_binding.verify_identity`` re-derives a run's ``question_id`` and refuses a run whose
declared id does not follow from the biology it executed. It knew exactly ONE recipe — the
legacy one:

    sha256({A:{program_id,direction}, B:{program_id,direction}, analysis_condition})[:32]
    with a lane prefix (fx_ / rq_)

A v3-driven run does not carry that id. It used to stamp Stage-2's own 64-hex
``selection_biology_sha256`` (the substitution this branch repairs), and it now carries the
CONTRACT's 16-hex ``question_id``. Neither is reproducible by the legacy recipe — so the one
check standing between a v3 run and a re-attributed identity could only ever have FAILED on
an honest run. It was never called on one, so nobody found out.

The verifier now re-derives whichever recipe the run's contract actually used, and it derives
it FROM THE AXIS THAT RAN — never from the contract's own say-so.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "analysis",
                                "direct"))

import verify_binding as VB  # noqa: E402
import verify_rules as R  # noqa: E402
from direct import stage1_v3 as G  # noqa: E402
from verify_run import Report  # noqa: E402

CHECK = "question_id re-derives from the v3 biology alone (ordered endpoints)"
LEGACY_CHECK = "question_id re-derives from the biology alone"


def axis_doc(a="prog_alpha", dir_a="high", b="prog_beta", dir_b="low"):
    """The axis a run ACTUALLY executed — the shape `emit.axis_record` really writes.

    Note what is NOT here: `conditions` and `analysis_mode`. The emitted axis document does
    not carry them, and a verifier that reached for them would raise on every real run. (It
    did — an end-to-end drive of a real screen is what caught it.)
    """
    return {"A": {"program_id": a, "direction": dir_a},
            "B": {"program_id": b, "direction": dir_b},
            "analysis_condition": "Rest"}


def v3_block(a="prog_alpha", dir_a="high", b="prog_beta", dir_b="low",
             conditions=("Rest",), mode=G.MODE_WITHIN):
    """The v3 binding block, as `stage1_v3.binding_block` writes it into `run_binding`.

    This is where the ORDER and the MODE come from — and it is hashed into the run id, so it
    cannot be edited to match a forged question_id without renaming the run's directory.
    """
    conds = list(conditions)
    return {"analysis_mode": mode, "conditions": conds,
            "endpoints": {
                "A": {"program_id": a, "direction": dir_a, "condition": conds[0]},
                "B": {"program_id": b, "direction": dir_b, "condition": conds[-1]}}}


def binding(v3=None):
    b = {"lane": "production"}
    if v3 is not None:
        b["stage1_v3"] = v3
    return b


def prov(question_id, analysis_condition="Rest"):
    return {"question_id": question_id, "analysis_condition": analysis_condition}


def result(rep, name):
    """The named check's verdict — asserting on the WHOLE report would hide which one fired."""
    for n, ok, _ in rep.checks:
        if n == name:
            return ok
    return None


def run(prov_doc, axis, v3=None):
    rep = Report()
    # run_dir is only read by the OTHER checks in verify_identity; this file is about the
    # question_id branch, so the rest is the minimum that lets it run.
    try:
        VB.verify_identity(prov_doc, binding(v3), axis, "/nonexistent/run", rep)
    except KeyError:
        pass          # the run_binding / run_id checks need a real run dir; not our subject
    return rep


class TestAV3RunIsNowVERIFIABLE:
    def test_an_HONEST_v3_run_PASSES(self):
        axis, v3 = axis_doc(), v3_block()
        qid = VB._v3_question_id(axis, v3)
        assert result(run(prov(qid), axis, v3), CHECK) is True

    def test_the_verifier_derives_the_SAME_id_the_gate_does(self):
        """Two independent implementations of one recipe: the gate's, and the verifier's."""
        for mode, conds in ((G.MODE_WITHIN, ["Stim48hr"]),
                            (G.MODE_TEMPORAL, ["Stim8hr", "Stim48hr"])):
            from fixtures_stage1_contract import independent_question_id
            assert VB._v3_question_id(
                axis_doc(), v3_block(conditions=conds, mode=mode)) == \
                independent_question_id("prog_alpha", "high", "prog_beta", "low",
                                        conds, mode)

    def test_a_TEMPORAL_run_binds_the_ORDER_it_ran_in(self):
        axis = axis_doc()
        early = v3_block(conditions=["Rest", "Stim8hr"], mode=G.MODE_TEMPORAL)
        late = v3_block(conditions=["Rest", "Stim48hr"], mode=G.MODE_TEMPORAL)
        assert VB._v3_question_id(axis, early) != VB._v3_question_id(axis, late)

    def test_the_SAME_program_at_TWO_TIMES_verifies(self):
        """The comparison the stale consumer refused outright."""
        axis = axis_doc(a="prog_alpha", dir_a="high", b="prog_alpha", dir_b="high")
        v3 = v3_block(a="prog_alpha", dir_a="high", b="prog_alpha", dir_b="high",
                      conditions=["Stim8hr", "Stim48hr"], mode=G.MODE_TEMPORAL)
        assert result(run(prov(VB._v3_question_id(axis, v3)), axis, v3), CHECK) is True


class TestAReAttributedV3RunIsCAUGHT:
    def test_a_run_whose_question_id_names_a_DIFFERENT_BIOLOGY_fails(self):
        """The id is honest — for another question. Only re-deriving it catches that."""
        ran, v3 = axis_doc(a="prog_alpha"), v3_block()
        forged = VB._v3_question_id(axis_doc(a="A_DIFFERENT_PROGRAM"), v3)
        assert result(run(prov(forged), ran, v3), CHECK) is False

    def test_a_run_whose_question_id_names_a_DIFFERENT_TIME_fails(self):
        axis = axis_doc()
        ran = v3_block(conditions=["Rest", "Stim48hr"], mode=G.MODE_TEMPORAL)
        other = v3_block(conditions=["Rest", "Stim8hr"], mode=G.MODE_TEMPORAL)
        assert result(run(prov(VB._v3_question_id(axis, other)), axis, ran),
                      CHECK) is False

    def test_a_v3_block_whose_ENDPOINTS_are_not_the_axis_that_ran_is_CAUGHT(self):
        """The question_id derives from the AXIS, so a block naming other poles would
        otherwise ride in the run identity unchallenged."""
        ran = axis_doc(a="prog_alpha")
        lying = v3_block(a="A_DIFFERENT_PROGRAM")
        rep = run(prov(VB._v3_question_id(ran, lying)), ran, lying)
        assert result(rep, "the v3 endpoints name the axis that actually ran") is False

    def test_the_OLD_SUBSTITUTED_biology_hash_would_now_FAIL(self):
        """The defect, caught by the verifier that could not previously see it.

        The stale consumer stamped `selection_biology_sha256` as the question_id. That is a
        64-hex hash of different content — no recipe on this path reproduces it, so a run
        carrying it is refused rather than admitted on the strength of nobody looking.
        """
        axis, v3 = axis_doc(), v3_block()
        biology_sha = R.content_sha256({
            "A": {"program_id": "prog_alpha", "direction": "high"},
            "B": {"program_id": "prog_beta", "direction": "low"},
            "analysis_mode": G.MODE_WITHIN, "conditions": ["Rest"]})
        assert len(biology_sha) == 64
        assert result(run(prov(biology_sha), axis, v3), CHECK) is False


class TestTheLEGACYRecipeIsUNTOUCHED:
    """A legacy run must verify exactly as it did before. The v3 branch is additive."""

    def test_an_honest_LEGACY_run_still_passes_on_the_legacy_recipe(self):
        axis = axis_doc()
        legacy_q = R.content_sha256({
            "A": {"program_id": "prog_alpha", "direction": "high"},
            "B": {"program_id": "prog_beta", "direction": "low"},
            "analysis_condition": "Rest"})[:32]
        rep = run(prov(legacy_q), axis)            # no stage1_v3 block -> a legacy run
        assert result(rep, LEGACY_CHECK) is True
        assert result(rep, CHECK) is None          # the v3 branch did not fire

    def test_a_forged_LEGACY_run_still_fails(self):
        rep = run(prov("f" * 32), axis_doc())
        assert result(rep, LEGACY_CHECK) is False

    def test_a_LEGACY_run_is_NOT_checked_with_the_v3_recipe(self):
        """...and a v3 run is not checked with the legacy one. Applying the wrong recipe to
        an honest run reports a forgery; that is how a real verifier gets switched off."""
        axis = axis_doc()
        rep = run(prov(VB._v3_question_id(axis, v3_block())), axis)
        assert result(rep, LEGACY_CHECK) is False   # v3 id, legacy recipe -> mismatch
        assert result(rep, CHECK) is None
