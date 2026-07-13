"""The candidate id is ONE identity, traced through EVERY table. Stage 4 joins on it.

`a_candidate_id_is_not_the_same_identity_in_every_table` fired during a fixture migration, and the
first instinct was to call it stale-test noise. It was not noise — it was the gate doing its job on
a genuinely inconsistent world (a half-applied change in which the store carried a symbol-only
target that the arms did not). The producer's own `build()` is consistent; the gate caught the
INPUTS being inconsistent, which is exactly what it exists for.

But the gate had no test that made it FIRE. It was reachable only by accident, through a broken
fixture — and a gate nobody deliberately walks through is one edit away from being decoration.
This project has now met that shape five times (`check_edges` carrying an undefined name; the
`AdmittedAggregate` binding reading fields that did not exist; a CLI whose success path crashed;
`GATE_UNKNOWN_MODULATION` declared and never raised; a verifier that crashed and whose "refusals"
were exceptions escaping).

So: these tests make it fire, deliberately, from every direction.

WHY IT MATTERS. An edge that names a candidate no candidate row carries is a join that SILENTLY
DROPS. Stage 4 resolves `candidate_id` and finds nothing — not an error, just an empty result, and
an empty result is indistinguishable from a drug nobody found. A regenerated-per-table id is not an
identity; it is a coincidence that holds until two tables disagree, and then it joins the wrong
rows without saying so.

NOTHING HERE TOUCHES PATHWAY COUNTS. Zero pathway output is a fail-closed state pending W18, not a
result, and it is not encoded as an expectation anywhere in this file.
"""
from __future__ import annotations

import pytest

from druglink import candidates_v2 as cv2

MID_A = "AM:INCHIKEY:AAAAAAAAAAAAAAAAAAAAAAAAAA-N"
MID_B = "AM:INCHIKEY:BBBBBBBBBBBBBBBBBBBBBBBBBB-N"

# The three tables the seam is traced through. `source_records` carries the moiety but is NOT
# required to resolve to a candidate row: a source assertion exists whether or not a candidate was
# built from it, and demanding otherwise would make an unresolvable drug vanish rather than be
# stated.
REFERENCING_TABLES = ("target_drug_edges", "arm_summaries")


def _row(mid: str, **over):
    row = {"candidate_id": mid, "active_moiety_id": mid}
    row.update(over)
    return row


def _tables(*, candidates=None, edges=None, summaries=None, sources=None):
    return {
        "candidates": [_row(MID_A)] if candidates is None else candidates,
        "target_drug_edges": [_row(MID_A)] if edges is None else edges,
        "arm_summaries": [_row(MID_A)] if summaries is None else summaries,
        "source_records": [_row(MID_A)] if sources is None else sources,
    }


# --------------------------------------------------------------------------- #
# The honest world is admitted. (Without this, every refusal below is vacuous.)
# --------------------------------------------------------------------------- #
def test_a_consistent_world_is_ADMITTED():
    cv2.check_candidate_identity(_tables())


# --------------------------------------------------------------------------- #
# THE DEFECT, AS A TEST: a reference nobody can resolve.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("table", REFERENCING_TABLES)
def test_a_row_naming_a_candidate_that_DOES_NOT_EXIST_is_REFUSED(table):
    """The exact mismatch that fired during the migration. Stage 4 would resolve this id, find
    nothing, and read the empty result as 'this candidate has no evidence' — when the truth is
    'this evidence has no candidate'."""
    tables = _tables(**{{"target_drug_edges": "edges",
                         "arm_summaries": "summaries"}[table]: [_row(MID_B)]})
    with pytest.raises(cv2.CandidatesV2Error) as exc:
        cv2.check_candidate_identity(tables)
    assert exc.value.gate == cv2.GATE_CANDIDATE_ID_NOT_STABLE
    assert MID_B in str(exc.value)


@pytest.mark.parametrize("table", REFERENCING_TABLES)
def test_an_EMPTY_candidate_table_under_non_empty_evidence_is_REFUSED(table):
    """Every candidate dropped, evidence retained. The catastrophic case, and the one a
    'the key exists' test would sail straight past."""
    tables = _tables(candidates=[])
    with pytest.raises(cv2.CandidatesV2Error) as exc:
        cv2.check_candidate_identity(tables)
    assert exc.value.gate == cv2.GATE_CANDIDATE_ID_NOT_STABLE


# --------------------------------------------------------------------------- #
# The id is the MOIETY. Not a per-table regeneration.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("table", ("target_drug_edges", "arm_summaries", "source_records"))
def test_a_candidate_id_that_is_not_its_active_moiety_id_is_REFUSED(table):
    """A candidate_id regenerated per table is not an identity — it is a coincidence that holds
    until two tables disagree, and then it joins the WRONG rows in silence."""
    key = {"target_drug_edges": "edges", "arm_summaries": "summaries",
           "source_records": "sources"}[table]
    tables = _tables(**{key: [_row(MID_A, candidate_id=MID_B)]})
    with pytest.raises(cv2.CandidatesV2Error) as exc:
        cv2.check_candidate_identity(tables)
    assert exc.value.gate == cv2.GATE_CANDIDATE_ID_NOT_STABLE


def test_the_producer_DECLARES_that_the_candidate_is_the_moiety():
    """The rule is published, not merely enforced — Stage 4 reads fields, not source."""
    assert cv2.vocabularies()["candidate_id_is_the_active_moiety_id"] is True


# --------------------------------------------------------------------------- #
# A source record may name a moiety no candidate was built from — and MUST NOT be dropped.
# --------------------------------------------------------------------------- #
def test_a_source_record_for_an_unbuilt_candidate_is_CARRIED_not_refused_and_not_dropped():
    """The asymmetry is deliberate. A source assertion exists whether or not a candidate was built
    from it; refusing here would force the producer to DROP the assertion to pass, and a dropped
    assertion is indistinguishable from a drug nobody found."""
    cv2.check_candidate_identity(_tables(sources=[_row(MID_B)]))
