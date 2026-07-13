"""The variant gate WAS FAIL-OPEN. This is the regression that closes it.

The old check fired only when:

    variant_id AND NOT variant_specific AND general_gene_rankable

The real store sets ``variant_specific = true`` and simply **omits**
``general_gene_rankable``. So the condition never fired, the gate reported green, and **29
assertions** — specific mutations plus the ``-1`` UNDEFINED MUTATION sentinel — could enter
general-gene ranking. The flag was set correctly. It gated nothing.

The mistake is worth naming precisely, because it is the same one twice in this cache:
**absence was treated as permission.** The old gate asked "is this marked rankable?" and let
a missing field mean no. The new gate asks "has this been EXPLICITLY excluded?" and lets a
missing field mean **fail**.
"""
from __future__ import annotations

import pytest

from verifier import cache_evidence as ce
from verifier.report import Report


def _failed(rep):
    return [n for n, ok, _ in rep.checks if not ok]


def _contained(**over):
    """A properly contained variant assertion."""
    a = {"source_row_id": 1, "variant_id": 42, "variant_specific": True,
         "general_gene_rankable": False, "lane": ce.LANE_VARIANT_NON_RANKABLE}
    a.update(over)
    return a


# --------------------------------------------------------------------------- #
# The fail-open bug, stated directly.
# --------------------------------------------------------------------------- #
def test_the_STORES_shape_variant_specific_true_with_no_rankable_flag_now_FAILS():
    """This is the exact row that sailed through: the flag is set, the gate is absent."""
    store_row = {"source_row_id": 6001, "variant_id": 42, "variant_specific": True}
    ok, reason = ce.variant_is_contained(store_row)
    assert not ok
    assert "EXPLICITLY false" in reason
    assert "absent field is not a denial" in reason


def test_an_absent_general_gene_rankable_is_NOT_a_denial():
    rep = Report()
    ce.check_variant_assertions_are_contained(
        rep, [{"source_row_id": 1, "variant_id": 7, "variant_specific": True}])
    assert _failed(rep)


@pytest.mark.parametrize("rankable", [True, None, "false", 0])
def test_general_gene_rankable_must_be_EXPLICITLY_false(rankable):
    """Not truthy-false. Not a string. Explicitly the boolean False."""
    ok, _ = ce.variant_is_contained(_contained(general_gene_rankable=rankable))
    assert not ok


def test_a_variant_not_typed_as_variant_specific_fails():
    ok, reason = ce.variant_is_contained(
        _contained(variant_specific=False))
    assert not ok and "must be TYPED as one" in reason


def test_a_contained_variant_passes():
    ok, reason = ce.variant_is_contained(_contained())
    assert ok and reason == "variant_contained"

    rep = Report()
    ce.check_variant_assertions_are_contained(rep, [_contained()])
    assert not _failed(rep)


def test_a_variant_must_sit_in_the_NAMED_non_rankable_lane():
    ok, reason = ce.variant_is_contained(
        _contained(lane="direct_gene_mechanism"))
    assert not ok and ce.LANE_VARIANT_NON_RANKABLE in reason


# --------------------------------------------------------------------------- #
# The real mutations.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("mutation", ce.REAL_VARIANT_ATTACKS)
def test_a_real_variant_inhibitor_may_not_rank_the_WILD_TYPE_gene(mutation):
    """A JAK2 V617F inhibitor is evidence about V617F. The whole clinical point is that it
    does not act on wild-type JAK2 — and the screen perturbed the wild-type gene."""
    leaking = {"source_row_id": 6002, "variant_id": 101, "variant_mutation": mutation,
               "variant_specific": True}          # ...and no general_gene_rankable
    ok, _ = ce.variant_is_contained(leaking)
    assert not ok, f"{mutation} must not rank the wild-type gene"

    rep = Report()
    ce.check_variant_assertions_are_contained(rep, [leaking])
    assert any("V617F" in n for n in _failed(rep))


def test_both_real_mutations_are_pinned():
    assert ce.REAL_VARIANT_ATTACKS == ("V617F", "V600E")


# --------------------------------------------------------------------------- #
# The -1 sentinel. The most dangerous misreading available.
# --------------------------------------------------------------------------- #
def test_variant_id_minus_one_is_a_VARIANT_not_a_null():
    """-1 is ChEMBL's UNDEFINED MUTATION: 'there IS a mutation and we do not know which'.

    Reading it as null converts an unknown mutant into a wild-type claim.
    """
    assert ce.VARIANT_UNDEFINED_MUTATION == -1
    sentinel = {"source_row_id": 6003, "variant_id": -1}
    assert ce.is_variant_assertion(sentinel) is True


def test_the_minus_one_sentinel_may_not_enter_general_gene_ranking():
    rep = Report()
    ce.check_variant_assertions_are_contained(
        rep, [{"source_row_id": 6003, "variant_id": -1, "variant_specific": True}])
    failed = _failed(rep)
    assert any("UNDEFINED MUTATION" in n for n in failed)


def test_a_contained_minus_one_sentinel_passes():
    rep = Report()
    ce.check_variant_assertions_are_contained(rep, [_contained(variant_id=-1)])
    assert not _failed(rep)


def test_a_null_variant_id_is_NOT_a_variant_assertion():
    """The gate must not refuse everything — a wild-type assertion still ranks."""
    assert ce.is_variant_assertion({"variant_id": None}) is False
    ok, reason = ce.variant_is_contained({"source_row_id": 1, "variant_id": None})
    assert ok and reason == "not_a_variant_assertion"


def test_the_real_leak_count_is_recorded():
    assert ce.REAL_VARIANT_ASSERTION_COUNT == 29


def test_a_mixed_batch_names_only_the_leaking_rows():
    rep = Report()
    ce.check_variant_assertions_are_contained(rep, [
        _contained(source_row_id=1),                                  # contained
        {"source_row_id": 2, "variant_id": None},                     # wild-type
        {"source_row_id": 3, "variant_id": -1, "variant_specific": True},   # LEAK
    ])
    detail = next(d for n, ok, d in rep.checks if not ok and "VARIANT assertion" in n)
    assert "mec 3" in detail
    assert "mec 1" not in detail and "mec 2" not in detail
