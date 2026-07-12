"""The disease-context review is an ingestible RESULT that must pay for itself.

The old contract was a one-way flag: ``pending_claude_science_plausibility_review``. It
could be set and never resolved — there was no shape for a COMPLETED review to arrive in,
so a review that had actually been done had nowhere to land. A flag that can only ever say
"not yet" is not a contract.

A completed review now carries a verdict AND the evidence that pays for it. The failures
these tests pin down are the ones that matter:

  * a favourable verdict citing nothing is DOWNGRADED to ``insufficient``, never accepted;
  * a verdict whose evidence does not resolve is REFUSED outright — the verdict is not
    quietly kept while the evidence under it is dropped;
  * a pending review has no result, and no code path gives it one. It cannot drift
    favourable by default, by omission, or by absence of a registry.
"""
from __future__ import annotations

import json

import pytest
import science_fixture

from druglink import science_registry as sr, science_review as rv

REVIEWED_BY = {"session_id": "cs_sess_1", "model_id": "claude-opus-4-8",
               "method_id": "claude-science.disease-context-review.v1"}


def _doc(direct, reviews):
    return {"schema_version": rv.REVIEW_SCHEMA, "artifact_class": "analysis",
            "direct_run_id": direct.run_id, "reviews": reviews}


def _completed(candidate_id, result, refs):
    return {"candidate_id": candidate_id, "review_status": rv.COMPLETED,
            "review_result": result, "review_evidence_refs": refs,
            "reviewed_by": dict(REVIEWED_BY)}


# --------------------------------------------------------------------------- #
# All four results are sayable — and each must resolve its bindings.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("result", rv.REVIEW_RESULTS)
def test_each_completed_result_validates_and_resolves_its_bindings(
        result, tmp_path, loaded_direct):
    root = str(tmp_path / "registry")
    refs = science_fixture.make(root)
    cited = [refs["sci_4"]]

    admitted = rv.admit(_doc(loaded_direct, [_completed("M1", result, cited)]),
                        artifact_class="analysis", direct=loaded_direct,
                        science_registry_root=root)
    got = admitted["by_candidate"]["M1"]

    assert got["disease_context_review_status"] == rv.COMPLETED
    assert got["disease_context_review_result"] == result
    assert got["disease_context_review_reason"] == rv.REASON_COMPLETED
    # The FULL typed triple is carried — never the id alone.
    assert got["disease_context_review_evidence_refs"] == cited
    assert got["disease_context_reviewed_by"] == REVIEWED_BY

    # ...and every binding really does resolve and re-hash.
    for ref in got["disease_context_review_evidence_refs"]:
        assert sr.resolve(root, ref)["record_type"] == ref["record_type"]

    assert admitted["ref"]["n_completed"] == 1
    assert admitted["ref"]["a_pending_review_can_never_become_favourable"] is True


def test_insufficient_is_a_real_outcome_and_needs_no_evidence():
    """``insufficient`` is not a soft yes and not a reviewer failure. It may cite nothing."""
    assert rv.INSUFFICIENT in rv.REVIEW_RESULTS
    assert rv.INSUFFICIENT not in rv.SUBSTANTIVE_RESULTS
    assert rv.SUBSTANTIVE_RESULTS == frozenset({"supportive", "contradictory", "mixed"})


# --------------------------------------------------------------------------- #
# A substantive verdict that cites nothing is downgraded. Never favourable by default.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("result", sorted(rv.SUBSTANTIVE_RESULTS))
def test_a_substantive_verdict_citing_nothing_is_downgraded_to_insufficient(
        result, tmp_path, loaded_direct):
    """An opinion in the costume of a finding is not promoted to a finding."""
    root = str(tmp_path / "registry")
    science_fixture.make(root)

    admitted = rv.admit(_doc(loaded_direct, [_completed("M1", result, [])]),
                        artifact_class="analysis", direct=loaded_direct,
                        science_registry_root=root)
    got = admitted["by_candidate"]["M1"]

    assert got["disease_context_review_result"] == rv.INSUFFICIENT
    assert got["disease_context_review_result"] != result
    assert got["disease_context_review_reason"] == rv.REASON_DOWNGRADED_NO_BINDINGS
    assert admitted["ref"]["n_downgraded_to_insufficient"] == 1


def test_an_unresolvable_binding_refuses_the_review_it_does_not_drop_the_evidence(
        tmp_path, loaded_direct):
    """The favourable verdict is NOT kept while the evidence under it quietly vanishes."""
    root = str(tmp_path / "registry")
    science_fixture.make(root)
    dangling = {"science_evidence_id": "sci_never_written",
                "science_evidence_sha256": "d" * 64,
                "record_type": "disease_context_review"}

    with pytest.raises(sr.ScienceRegistryError, match="not in the registry|dangling"):
        rv.admit(_doc(loaded_direct, [_completed("M1", rv.SUPPORTIVE, [dangling])]),
                 artifact_class="analysis", direct=loaded_direct,
                 science_registry_root=root)


def test_an_altered_record_refuses_the_review(tmp_path, loaded_direct):
    import os

    root = str(tmp_path / "registry")
    refs = science_fixture.make(root)
    entry = sr.load_index(root)["records"]["sci_4"]
    with open(os.path.join(root, entry["raw_file"]), "wb") as fh:
        fh.write(b"a different reading, substituted after the fact")

    with pytest.raises(sr.ScienceRegistryError, match="ALTERED"):
        rv.admit(_doc(loaded_direct, [_completed("M1", rv.SUPPORTIVE, [refs["sci_4"]])]),
                 artifact_class="analysis", direct=loaded_direct,
                 science_registry_root=root)


def test_a_supportive_verdict_with_no_registry_at_all_is_refused(tmp_path,
                                                                 loaded_direct):
    """Absence of a registry is not permission to believe the verdict."""
    root = str(tmp_path / "registry")
    refs = science_fixture.make(root)

    with pytest.raises(sr.ScienceRegistryError, match="no registry was supplied"):
        rv.admit(_doc(loaded_direct, [_completed("M1", rv.SUPPORTIVE, [refs["sci_1"]])]),
                 artifact_class="analysis", direct=loaded_direct,
                 science_registry_root=None)


# --------------------------------------------------------------------------- #
# A pending review stays pending.
# --------------------------------------------------------------------------- #
def test_a_pending_review_stays_pending_and_carries_no_result(loaded_direct):
    admitted = rv.admit(
        _doc(loaded_direct, [{"candidate_id": "M1", "review_status": rv.PENDING}]),
        artifact_class="analysis", direct=loaded_direct)
    got = admitted["by_candidate"]["M1"]

    assert got["disease_context_review_status"] == rv.PENDING
    assert got["disease_context_review_result"] is None
    assert got["disease_context_review_reason"] == rv.REASON_PENDING
    assert got["disease_context_review_evidence_refs"] == []


def test_a_pending_review_that_declares_a_result_is_refused(loaded_direct):
    """A pending review claiming a finding it has not made is a contradiction."""
    for result in rv.REVIEW_RESULTS:
        doc = _doc(loaded_direct, [{"candidate_id": "M1", "review_status": rv.PENDING,
                                    "review_result": result}])
        with pytest.raises(rv.ReviewError, match="Only a COMPLETED review has a result"):
            rv.admit(doc, artifact_class="analysis", direct=loaded_direct)


def test_an_unreviewed_inverse_hypothesis_is_pending_never_favourable():
    """With NO review supplied, an inverse hypothesis is pending — not not_required."""
    got = rv.for_candidate({}, "M1", has_inverse=True)
    assert got["disease_context_review_status"] == rv.PENDING
    assert got["disease_context_review_result"] is None
    assert got["disease_context_review_reason"] == rv.REASON_PENDING

    # Nothing to review is a different statement from "not yet reviewed".
    none_needed = rv.for_candidate({}, "M2", has_inverse=False)
    assert none_needed["disease_context_review_status"] == rv.NOT_REQUIRED
    assert none_needed["disease_context_review_result"] is None


# --------------------------------------------------------------------------- #
# Structure: closed enums, attribution, no double verdicts.
# --------------------------------------------------------------------------- #
def test_the_result_enum_is_closed(loaded_direct):
    doc = _doc(loaded_direct, [_completed("M1", "promising", [])])
    with pytest.raises(rv.ReviewError, match="must carry review_result in"):
        rv.admit(doc, artifact_class="analysis", direct=loaded_direct)

    doc = _doc(loaded_direct, [{"candidate_id": "M1", "review_status": "approved"}])
    with pytest.raises(rv.ReviewError, match="review_status must be one of"):
        rv.admit(doc, artifact_class="analysis", direct=loaded_direct)


def test_a_completed_review_must_say_who_made_it(loaded_direct):
    for missing in ("session_id", "model_id", "method_id"):
        who = {k: v for k, v in REVIEWED_BY.items() if k != missing}
        review = dict(_completed("M1", rv.INSUFFICIENT, []), reviewed_by=who)
        with pytest.raises(rv.ReviewError, match=f"reviewed_by.{missing}"):
            rv.admit(_doc(loaded_direct, [review]), artifact_class="analysis",
                     direct=loaded_direct)


def test_two_verdicts_for_one_candidate_is_refused(loaded_direct):
    """Stage 3 does not get to choose which of two verdicts it likes."""
    doc = _doc(loaded_direct, [_completed("M1", rv.SUPPORTIVE, []),
                               _completed("M1", rv.CONTRADICTORY, [])])
    with pytest.raises(rv.ReviewError, match="duplicate review"):
        rv.admit(doc, artifact_class="analysis", direct=loaded_direct)


def test_a_review_of_a_different_run_is_refused(loaded_direct):
    doc = _doc(loaded_direct, [])
    doc["direct_run_id"] = "some_other_run"
    with pytest.raises(rv.ReviewError, match="reviews a different question"):
        rv.admit(doc, artifact_class="analysis", direct=loaded_direct)


def test_a_fixture_review_cannot_enter_an_analysis_run(loaded_direct):
    doc = _doc(loaded_direct, [])
    doc["artifact_class"] = "fixture"
    with pytest.raises(rv.ReviewError, match="refuses a review declaring"):
        rv.admit(doc, artifact_class="analysis", direct=loaded_direct)


def test_a_review_document_loads_from_disk(tmp_path, loaded_direct):
    root = str(tmp_path / "registry")
    refs = science_fixture.make(root)
    path = tmp_path / "review.json"
    path.write_text(json.dumps(
        _doc(loaded_direct, [_completed("M1", rv.CONTRADICTORY, [refs["sci_3"]])])))

    admitted = rv.load(str(path), artifact_class="analysis", direct=loaded_direct,
                       science_registry_root=root)
    assert admitted["by_candidate"]["M1"][
        "disease_context_review_result"] == rv.CONTRADICTORY
    assert admitted["ref"]["disease_context_review"] == "provided"

    # No review lane at all is recorded as absent, not as a passing one.
    absent = rv.load(None, artifact_class="analysis", direct=loaded_direct)
    assert absent["ref"] == rv.NOT_PROVIDED
