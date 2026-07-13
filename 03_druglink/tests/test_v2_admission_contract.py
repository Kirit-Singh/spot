"""Adversarial tests for the FROZEN Stage-3 v2 admission contract.

These are written **before** the loader exists, by the **verifier** lane, and that ordering
is the point: they are what the producer's loader will be judged against. Written after it,
the loader would decide what "correct" means — which is how a generator ends up grading its
own homework.

I nearly did exactly that. `analysis/druglink/arm_query.py` and `pathway_bridge.py` are
producer-side modules I authored, and the v2 loader was going to sit beside them. That would
have made me generator *and* verifier of the same code — the defect this lane has spent the
whole cache review catching in others (B6; M4b; the temporal `verification_ref`; the
producer's `pending` release read as an admission) and once, painfully, in myself, when I
admitted `b20ec29b` because *my* check passed while the *producer's* gate was fail-open.

A verifier that also wrote the thing it verifies can only prove that it agreed with itself.
"""
from __future__ import annotations

import pytest

from verifier import v2_admission as v2
from verifier.report import Report

DIGEST = "a" * 64


def _failed(rep):
    return [n for n, ok, _ in rep.checks if not ok]


def _row(origin=v2.ORIGIN_DIRECT, **over):
    r = {"edge_id": "e1", "target_id": "ENSG1", "arm_key": "k1", "drug_id": "CHEMBL1",
         "evidence_origin": origin, "arm_rank": 1,
         "axis_order_preserved": True,
         "action_type_source": "INHIBITOR",
         "intervention_effect": "functional_inhibition",
         "direction_vocabulary_digest": DIGEST}
    if origin == v2.ORIGIN_TEMPORAL:
        r.update({"from_condition": "Rest", "to_condition": "Stim48hr",
                  "condition_pair_is_ordered": True})
    if origin == v2.ORIGIN_PATHWAY:
        r["arm_rank"] = None
    r.update(over)
    return r


def _bundle(**over):
    b = {"artifact_class": "analysis",
         "universe_store_binding": {
             "store_id": v2.ADMITTED_STORE_ID,
             "producer_commit": v2.ADMITTED_PRODUCER_COMMIT,
             "admitted_by": "stage3_external_verifier",
             "admission_report_sha256": v2.ADMISSION_REPORT_SHA256}}
    b.update(over)
    return b


def _rows():
    return [_row(v2.ORIGIN_DIRECT), _row(v2.ORIGIN_TEMPORAL, edge_id="e2"),
            _row(v2.ORIGIN_PATHWAY, edge_id="e3")]


def _verify(bundle=None, rows=None):
    rep = Report()
    v2.verify(rep, bundle=bundle or _bundle(), rows=rows or _rows(),
              expected_vocabulary_digest=DIGEST)
    return rep


# --------------------------------------------------------------------------- #
# The honest bundle.
# --------------------------------------------------------------------------- #
def test_a_conforming_v2_bundle_is_admitted():
    assert not _failed(_verify())


def test_the_contract_is_frozen_to_the_ADMITTED_store_and_producer():
    assert v2.ADMITTED_STORE_ID.startswith("bdf41b69")
    assert v2.ADMITTED_PRODUCER_COMMIT.startswith("d268a74")
    assert v2.ADMISSION_REPORT_SHA256.startswith("4aba8b58")


# --------------------------------------------------------------------------- #
# 1. Three origins, typed and SEPARATE.
# --------------------------------------------------------------------------- #
def test_an_untyped_evidence_row_is_refused():
    rep = _verify(rows=[_row(origin="something_else")])
    assert any("exactly one origin" in n for n in _failed(rep))


def test_the_three_origins_are_disjoint():
    assert not (v2.MEASURED_ORIGINS & v2.INFERRED_ORIGINS)
    assert set(v2.ORIGINS) == v2.MEASURED_ORIGINS | v2.INFERRED_ORIGINS


def test_a_pathway_origin_row_carrying_a_measured_RANK_is_refused():
    """Nobody perturbed it. A rank on an inferred row is a measurement that never happened."""
    rep = _verify(rows=[_row(v2.ORIGIN_PATHWAY, arm_rank=1)])
    assert any("no rank to carry" in n for n in _failed(rep))


def test_direct_and_temporal_are_BOTH_measured_but_still_distinct():
    assert v2.ORIGIN_DIRECT in v2.MEASURED_ORIGINS
    assert v2.ORIGIN_TEMPORAL in v2.MEASURED_ORIGINS
    assert v2.ORIGIN_DIRECT != v2.ORIGIN_TEMPORAL, (
        "same-time and cross-time are different measurements and must not be merged")


# --------------------------------------------------------------------------- #
# 2. No combined score, at any depth, under any name.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("banned", sorted(v2.BANNED_V2_KEYS))
def test_every_combined_score_synonym_is_refused(banned):
    rep = Report()
    v2.check_no_combined_score(rep, {"candidates": [{banned: 0.9}]})
    assert _failed(rep)


def test_a_combined_score_is_refused_at_ANY_nesting_depth():
    rep = Report()
    v2.check_no_combined_score(
        rep, {"a": {"b": {"c": [{"deep": {"fused_evidence": 1.0}}]}}})
    assert _failed(rep)


def test_a_bundle_with_no_combined_score_passes():
    rep = Report()
    v2.check_no_combined_score(rep, {"candidates": [{"arm_rank": 1}]})
    assert not _failed(rep)


# --------------------------------------------------------------------------- #
# 3. Ordered axes and conditions.
# --------------------------------------------------------------------------- #
def test_a_temporal_row_that_lost_its_ORDER_is_refused():
    """Rest→Stim48 is not Stim48→Rest. A sorted pair is a different question."""
    rep = _verify(rows=[_row(v2.ORIGIN_TEMPORAL, condition_pair_is_ordered=False)])
    assert any("ORDERED condition pair" in n for n in _failed(rep))


def test_a_temporal_row_missing_an_endpoint_is_refused():
    rep = _verify(rows=[_row(v2.ORIGIN_TEMPORAL, to_condition=None)])
    assert any("ORDERED condition pair" in n for n in _failed(rep))


def test_a_row_that_lost_the_SELECTIONS_axis_order_is_refused():
    """The axis belongs to the selection. Re-sorting it swaps which program is A."""
    rep = _verify(rows=[_row(axis_order_preserved=False)])
    assert any("axis order" in n for n in _failed(rep))


# --------------------------------------------------------------------------- #
# 4. Direction comes from the frozen engine, at view time.
# --------------------------------------------------------------------------- #
def test_a_row_bound_to_a_DIFFERENT_direction_vocabulary_is_refused():
    """A silent reclassification is exactly what the digest exists to make loud."""
    rep = _verify(rows=[_row(direction_vocabulary_digest="b" * 64)])
    assert any("vocabulary DIGEST" in n for n in _failed(rep))


def test_an_interpretation_without_its_VERBATIM_source_is_refused():
    """If the source string is gone, nobody can re-translate under a corrected vocabulary."""
    rep = _verify(rows=[_row(action_type_source=None)])
    assert any("verbatim source string" in n for n in _failed(rep))


# --------------------------------------------------------------------------- #
# 5. NO FIXTURE FALLBACK.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("marker", v2.FIXTURE_MARKERS)
def test_a_fixture_artifact_inside_an_ANALYSIS_bundle_is_refused(marker):
    """A loader that substitutes a fixture for a missing artifact is how a synthetic number
    becomes a result. The only honest response to a missing artifact is to refuse."""
    rep = Report()
    v2.check_no_fixture_fallback(
        rep, {"artifact_class": "analysis",
              "upstream": {"source": f"{marker}_bundle"}})
    assert any("no fixture/synthetic/mock" in n for n in _failed(rep))


def test_an_analysis_bundle_with_no_fixture_passes():
    rep = Report()
    v2.check_no_fixture_fallback(rep, {"artifact_class": "analysis",
                                       "upstream": {"source": "admitted_store"}})
    assert not _failed(rep)


def test_a_bundle_not_declaring_artifact_class_analysis_is_refused():
    rep = _verify(bundle=_bundle(artifact_class="fixture"))
    assert any("artifact_class=analysis" in n for n in _failed(rep))


# --------------------------------------------------------------------------- #
# 6. NO CACHE SELF-ADMISSION. Exact store identity bound.
# --------------------------------------------------------------------------- #
def test_the_WRONG_store_id_is_refused():
    b = _bundle()
    b["universe_store_binding"]["store_id"] = "b20ec29b" + "0" * 56
    rep = _verify(bundle=b)
    assert any("EXACT admitted universe store_id" in n for n in _failed(rep))


def test_the_SAME_BYTES_under_a_DIFFERENT_PRODUCER_are_refused():
    """bdf41b69 built by d6066b7 shipped a fail-open provenance gate. Same store, no admission."""
    b = _bundle()
    b["universe_store_binding"]["producer_commit"] = "d6066b7759a8bc57190365732f316b111eab85a1"
    rep = _verify(bundle=b)
    assert any("admitted producer commit" in n for n in _failed(rep))


def test_a_PRODUCER_SELF_ADMISSION_is_refused():
    """The producer's verify_report is the producer agreeing with itself."""
    b = _bundle()
    b["universe_store_binding"]["admitted_by"] = "stage3-universe-verify-v1"
    rep = _verify(bundle=b)
    assert any("INDEPENDENT verifier" in n for n in _failed(rep))


def test_an_admission_naming_NO_REPORT_is_refused():
    b = _bundle()
    b["universe_store_binding"]["admission_report_sha256"] = None
    rep = _verify(bundle=b)
    assert any("bound by SHA-256" in n for n in _failed(rep))


def test_a_bundle_with_NO_store_binding_at_all_is_refused():
    rep = _verify(bundle=_bundle(universe_store_binding={}))
    assert len(_failed(rep)) >= 3, "store_id, producer, admitter and report all missing"


# --------------------------------------------------------------------------- #
# The contract is frozen BEFORE the loader exists. That is the point.
# --------------------------------------------------------------------------- #
def test_this_contract_does_not_import_the_producer():
    """Generator != verifier. A verifier that imports the thing it verifies proves nothing."""
    import inspect

    src = inspect.getsource(v2)
    assert "from druglink" not in src
    assert "import druglink" not in src
