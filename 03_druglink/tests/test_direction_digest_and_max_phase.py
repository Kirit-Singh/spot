"""Two cache corrections: direction is decided in STAGE 3, and max_phase is inert.

1. **Direction.** The frozen `direction.py` classifies `DISRUPTING AGENT` and
   `PARTIAL AGONIST` as explicit *unknown* — they name a physical interaction, not a
   signalling effect, so the source never said which way the target moves. Compatibility is
   computed HERE, from the exact frozen vocabulary; the cache preserves `action_type`
   verbatim and classifies nothing. The vocabulary is hashed so a silent edit is visible.

2. **max_phase.** Preserved exactly (raw string + canonical decimal; null / -1 / 0.5 /
   integers all distinct), carried with release provenance, and used for **nothing**.
"""
from __future__ import annotations

import pytest

from druglink import development_phase as dp
from druglink import direction

RELEASE = "CHEMBL_37"


# --------------------------------------------------------------------------- #
# 1a. The frozen vocabulary — read from the code, not copied from a memo.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("action", ["DISRUPTING AGENT", "PARTIAL AGONIST"])
def test_disrupting_agent_and_partial_agonist_are_explicit_unknown(action):
    assert action in direction.ACTION_EXPLICIT_UNKNOWN
    effect, reason = direction.intervention_effect(action)
    assert effect == direction.EFFECT_UNKNOWN
    assert "no_enumerated_intervention_effect" in reason


@pytest.mark.parametrize("action", ["DISRUPTING AGENT", "PARTIAL AGONIST"])
def test_they_are_NOT_inhibition_and_NOT_activation(action):
    """The failure this prevents: reading 'disrupting' as inhibition and ranking on it."""
    effect, _ = direction.intervention_effect(action)
    assert effect != direction.FUNCTIONAL_INHIBITION
    assert effect != direction.FUNCTIONAL_ACTIVATION
    assert effect != direction.ABUNDANCE_REDUCTION


def test_an_unrecognised_action_type_FAILS_CLOSED_to_unknown():
    effect, reason = direction.intervention_effect("SOME BRAND NEW ACTION")
    assert effect == direction.EFFECT_UNKNOWN
    assert reason


def test_a_null_action_type_fails_closed():
    effect, _ = direction.intervention_effect(None)
    assert effect == direction.EFFECT_UNKNOWN


def test_unknown_is_in_the_closed_effect_set():
    assert direction.EFFECT_UNKNOWN in direction.INTERVENTION_EFFECTS


# --------------------------------------------------------------------------- #
# 1b. The vocabulary is BOUND by digest, so an edit cannot be silent.
# --------------------------------------------------------------------------- #
def test_the_vocabulary_digest_is_stable_across_calls():
    assert direction.vocabulary_digest() == direction.vocabulary_digest()
    assert len(direction.vocabulary_digest()) == 64


def test_moving_an_action_type_between_sets_MOVES_the_digest(monkeypatch):
    """The point of the digest: a quiet reclassification becomes visible."""
    before = direction.vocabulary_digest()
    monkeypatch.setattr(
        direction, "ACTION_FUNCTIONAL_INHIBITION",
        frozenset(direction.ACTION_FUNCTIONAL_INHIBITION | {"DISRUPTING AGENT"}))
    assert direction.vocabulary_digest() != before, (
        "promoting DISRUPTING AGENT to inhibition must move the digest — otherwise a "
        "drug silently starts ranking and nothing records that the rule changed")


def test_editing_the_policy_version_moves_the_digest(monkeypatch):
    before = direction.vocabulary_digest()
    monkeypatch.setattr(direction, "DIRECTION_POLICY_VERSION", "stage3-direction-v5")
    assert direction.vocabulary_digest() != before


# --------------------------------------------------------------------------- #
# 1c. The CACHE preserves verbatim; STAGE 3 classifies.
# --------------------------------------------------------------------------- #
def test_the_cache_preserves_action_type_verbatim_and_classifies_nothing():
    """`action_type_source` is the source's word; `intervention_effect` is Stage-3's."""
    from druglink import artifacts
    cols = artifacts.TABLES["mechanism_assertions"][0]
    assert "action_type_source" in cols, "the source string must survive verbatim"
    assert "action_type_normalized" in cols
    assert "intervention_effect" in cols, "and Stage 3 computes the compatibility"
    assert "intervention_effect_reason" in cols


def test_a_verbatim_action_type_survives_even_when_it_classifies_to_unknown():
    effect, _ = direction.intervention_effect("DISRUPTING AGENT")
    assert effect == direction.EFFECT_UNKNOWN
    # The source string is not erased just because Stage 3 could not use it.
    assert direction.normalize_action_type("DISRUPTING AGENT") == "DISRUPTING AGENT"


# --------------------------------------------------------------------------- #
# 2. max_phase: exact, distinct, provenanced — and inert.
# --------------------------------------------------------------------------- #
def test_null_is_not_recorded_and_is_NOT_phase_zero():
    got = dp.preserve(None, chembl_release=RELEASE)
    assert got["max_phase_state"] == dp.NOT_RECORDED
    assert got["max_phase_source_string"] is None
    assert got["max_phase_canonical_decimal"] is None
    assert got["max_phase_canonical_decimal"] != 0


def test_minus_one_is_the_UNKNOWN_sentinel_not_a_phase_below_zero():
    got = dp.preserve(-1, chembl_release=RELEASE)
    assert got["max_phase_state"] == dp.UNKNOWN
    assert got["max_phase_is_unknown_sentinel"] is True
    assert got["max_phase_source_string"] == "-1"


def test_half_phase_survives_and_is_not_cast_to_zero():
    """`int(0.5)` is 0. That single cast is the whole bug.

    The SOURCE STRING is verbatim "0.5". The canonical decimal is the frozen exponential
    form (`5E-1`) — exact, not rounded, and emphatically not `0`. Both representations are
    lossless; what matters is that neither one collapses 0.5 into 0.
    """
    half = dp.preserve(0.5, chembl_release=RELEASE)
    zero = dp.preserve(0, chembl_release=RELEASE)

    assert half["max_phase_state"] == dp.RECORDED
    assert half["max_phase_source_string"] == "0.5"          # verbatim
    assert half["max_phase_canonical_decimal"] != zero["max_phase_canonical_decimal"]
    assert dp.distinct(half, zero)


def test_an_integer_phase_is_recorded():
    got = dp.preserve(4, chembl_release=RELEASE)
    assert got["max_phase_state"] == dp.RECORDED
    assert got["max_phase_source_string"] == "4"


def test_null_minus_one_zero_and_half_are_ALL_DISTINCT():
    vals = [dp.preserve(v, chembl_release=RELEASE) for v in (None, -1, 0, 0.5, 1)]
    for i, a in enumerate(vals):
        for b in vals[i + 1:]:
            assert dp.distinct(a, b), (
                f"{a['max_phase_source_string']!r} and {b['max_phase_source_string']!r} "
                "collapsed into one another")


def test_a_phase_without_a_release_is_refused():
    with pytest.raises(dp.MaxPhaseError, match="without the release"):
        dp.preserve(4, chembl_release="")


def test_every_preserved_phase_carries_release_provenance():
    got = dp.preserve(3, chembl_release=RELEASE, source_record_id="rec_1")
    assert got["max_phase_source"] == "chembl"
    assert got["max_phase_source_release"] == RELEASE
    assert got["max_phase_source_record_id"] == "rec_1"
    assert got["max_phase_rule_id"] == dp.MAX_PHASE_RULE_ID


def test_a_garbage_phase_is_refused_not_coerced_to_zero():
    with pytest.raises(dp.MaxPhaseError, match="not coerced to 0"):
        dp.preserve("phase four", chembl_release=RELEASE)


# --------------------------------------------------------------------------- #
# max_phase is CONTEXT ONLY. This is the load-bearing part.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("value", [None, -1, 0, 0.5, 1, 4])
def test_every_preserved_phase_declares_itself_inert(value):
    got = dp.preserve(value, chembl_release=RELEASE)
    assert got["max_phase_is_context_only"] is True
    assert got["max_phase_may_gate"] is False
    assert got["max_phase_may_rank"] is False


def test_max_phase_may_never_gate_or_rank_as_constants():
    assert dp.MAY_GATE is False and dp.MAY_RANK is False


@pytest.mark.parametrize("key", ["max_phase", "max_phase_canonical_decimal", "phase"])
def test_an_ordering_that_names_max_phase_is_refused(key):
    with pytest.raises(dp.MaxPhaseError, match="CONTEXT ONLY"):
        dp.refuse_if_used_for_ordering(["arm_rank", key])


def test_an_ordering_that_does_not_name_it_is_fine():
    dp.refuse_if_used_for_ordering(["arm_rank", "intervention_effect"])


def test_development_state_does_NOT_claim_to_preserve_max_phase():
    """The coarse field stays; it just must not pretend to be the phase."""
    got = dp.preserve(4, chembl_release=RELEASE)
    assert got["development_state_preserves_max_phase"] is False
