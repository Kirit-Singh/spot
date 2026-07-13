"""The gap MY OWN audit missed: containment is not row-deep, it is ASSERTION-deep.

The regenerated store gets the ROW right — an `ambiguous_identity` target carries `drugs: []`.
I checked exactly that, and reported green.

But the copied source assertions live one level down, under `ambiguous_source_assertions[]`,
and SIX of them still carry `general_gene_rankable: true` — mec_ids 6210 and 6862, on
CALM1/CALM2/CALM3. Those three genes encode an *identical* calmodulin protein, so they share
every accession: the textbook shared-identity case, and the very rows from the original attack.

A consumer that flattens assertions — and flattening is the obvious thing to do — reads
`general_gene_rankable: true` and ranks them. The row said no. The assertion says yes. The
assertion is what gets read.

**A gate that holds only at the depth you happened to look at is not a gate.** My row-level
check was exactly that, which is why this is here and why the scan is recursive and
container-agnostic: it does not care what the container is called, however honestly it is named.
"""
from __future__ import annotations

import pytest

from verifier import cache_evidence as ce
from verifier.report import Report


def _failed(rep):
    return [n for n, ok, _ in rep.checks if not ok]


def _assertion(mec, rankable, **over):
    a = {"source_row_id": mec, "action_type_source": "INHIBITOR", "variant_id": None,
         "general_gene_rankable": rankable,
         "disposition": ce.DISP_AMBIGUOUS_SOURCE_ASSERTION}
    a.update(over)
    return a


def _ambiguous_row(target_id, rankable, **over):
    """An ambiguous row: drugs=[] at the row level, copied assertions one level down."""
    r = {"target_id": target_id, "disposition": ce.DISP_AMBIGUOUS_IDENTITY,
         "drugs": [],                       # the row-level gate is CORRECT
         "ambiguous_source_assertions": [
             _assertion(6210, rankable), _assertion(6862, rankable)]}
    r.update(over)
    return r


# --------------------------------------------------------------------------- #
# The REAL occurrence, reproduced.
# --------------------------------------------------------------------------- #
def test_the_real_six_occurrences_across_CALM1_2_3_are_refused():
    """2 unique mec_ids x 3 calmodulin genes = the 6 copied assertions in the real store."""
    rows = [_ambiguous_row(g, True) for g in ce.CALMODULIN_GENES]
    rep = Report()
    ce.check_no_rankable_assertion_inside_an_ambiguous_row(rep, rows)

    failed = _failed(rep)
    assert any("ANY nesting depth" in n for n in failed)
    detail = next(d for n, ok, d in rep.checks if not ok and "ANY nesting depth" in n)
    assert "6210" in detail or "6862" in detail


def test_the_row_level_gate_ALONE_would_have_passed():
    """This is precisely the check I ran, and precisely why it was not enough."""
    rows = [_ambiguous_row(g, True) for g in ce.CALMODULIN_GENES]
    assert all(r["drugs"] == [] for r in rows)          # row level: clean
    rep = Report()
    ce.check_no_rankable_assertion_inside_an_ambiguous_row(rep, rows)
    assert _failed(rep), "clean at the row, rankable at the assertion"


# --------------------------------------------------------------------------- #
# THE REQUIRED FIXTURE: flip it to true, it must be refused.
# --------------------------------------------------------------------------- #
def test_flipping_a_contained_ambiguous_assertion_to_TRUE_is_refused():
    contained = [_ambiguous_row(g, False) for g in ce.CALMODULIN_GENES]
    rep = Report()
    ce.check_no_rankable_assertion_inside_an_ambiguous_row(rep, contained)
    assert not _failed(rep), "the contained store must pass"

    contained[0]["ambiguous_source_assertions"][0]["general_gene_rankable"] = True
    rep2 = Report()
    ce.check_no_rankable_assertion_inside_an_ambiguous_row(rep2, contained)
    assert _failed(rep2), "flipping ONE nested assertion to true must be REFUSED"


@pytest.mark.parametrize("value", [True, None, "false", 0, 1])
def test_general_gene_rankable_must_be_EXPLICITLY_false_at_assertion_depth(value):
    """Absence is not permission — the same rule, one level deeper."""
    rows = [_ambiguous_row("ENSG_X", value)]
    rep = Report()
    ce.check_no_rankable_assertion_inside_an_ambiguous_row(rep, rows)
    assert _failed(rep)


def test_a_properly_contained_ambiguous_row_passes():
    rep = Report()
    ce.check_no_rankable_assertion_inside_an_ambiguous_row(
        rep, [_ambiguous_row(g, False) for g in ce.CALMODULIN_GENES])
    assert not _failed(rep)


# --------------------------------------------------------------------------- #
# Container-agnostic: renaming the container does not launder the claim.
# --------------------------------------------------------------------------- #
def test_the_scan_does_not_care_what_the_CONTAINER_is_called():
    """`ambiguous_source_assertions` is an honest name. The next one might not be."""
    row = {"target_id": "ENSG_Y", "disposition": ce.DISP_AMBIGUOUS_IDENTITY, "drugs": [],
           "preserved_for_reference": {"nested": {"deep": [_assertion(6210, True)]}}}
    rep = Report()
    ce.check_no_rankable_assertion_inside_an_ambiguous_row(rep, [row])
    assert _failed(rep), "depth and container name must not matter"


def test_a_NON_ambiguous_row_may_still_rank_its_assertions():
    """The gate must not refuse everything — resolved identities still produce evidence."""
    row = {"target_id": "ENSG_OK", "disposition": "drug_evidence",
           "drugs": [{"assertions": [_assertion(99, True, disposition=None)]}]}
    rep = Report()
    ce.check_no_rankable_assertion_inside_an_ambiguous_row(rep, [row])
    assert not _failed(rep)


def test_a_preserved_ambiguous_assertion_must_be_NAMED():
    rows = [_ambiguous_row("ENSG_Z", False)]
    rows[0]["ambiguous_source_assertions"][0].pop("disposition")
    rep = Report()
    ce.check_no_rankable_assertion_inside_an_ambiguous_row(rep, rows)
    assert any("named" in n for n in _failed(rep))


def test_the_real_mec_ids_and_genes_are_pinned():
    assert ce.AMBIGUOUS_ASSERTION_MEC_IDS == (6210, 6862)
    assert len(ce.CALMODULIN_GENES) == 3
